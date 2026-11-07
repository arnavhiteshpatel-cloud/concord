"""Milestone 3: live acquisition -> pipeline -> decoder -> router, end to end over real LSL.

Real FALCON H1 blocks (DANDI 000954) are streamed with genuine liblsl outlets, declared as
*prerecorded*. Passing these tests shows the streaming path reproduces the offline result on
the same data; it does not demonstrate live human decoding.
"""

from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from typing import Any

import numpy as np
import pytest

pytest.importorskip("pylsl")
pytest.importorskip("scipy")
pytest.importorskip("pynwb")

from brainos.adapters.nwb.reader import load
from brainos.adapters.simulated import OperatorIntentSource
from brainos.contracts import Capability
from brainos.contracts.protocol import AppStatus, DeviceKind, ErrorCode
from brainos.datasets import session_of
from brainos.datasets.fetch import DEMO_FILES
from brainos.decoding import model as models
from brainos.decoding.calibrate import CalibrationError, calibrate, chronological_split
from brainos.decoding.ridge import RidgeDecoder, evaluate, fit
from brainos.runtime import DeviceRegistry, Recorder, Runtime, RuntimeCommandError
from brainos.runtime.pipeline import PipelineManager, PipelineStartRequest, RouterSpec
from brainos.testing.lsl_publishers import FalconLSLPublisher, SyntheticEphysPublisher

from .conftest import subscribe
from .helpers import drain, events, wait_for

REPO = Path(__file__).resolve().parents[2]
DATA = Path(os.environ.get("BRAINOS_TEST_DATASETS", REPO / "data" / "datasets" / "dandi-000954"))
TRAIN_FILE, EVAL_FILE = DATA / DEMO_FILES[0], DATA / DEMO_FILES[1]
HAVE_DATA = TRAIN_FILE.exists() and EVAL_FILE.exists()
needs_data = pytest.mark.skipif(
    not HAVE_DATA, reason=f"real FALCON H1 files not found in {DATA}; run `make dataset`"
)
SPEED = 20.0  # 6786 bins of 20 ms -> ~6.8 s


def _train(path: Path, models_dir: Path) -> RidgeDecoder:
    """Train on a whole block, exactly as the offline tooling records it."""
    rec = load(path)
    assert rec.behavior is not None
    b = rec.behavior
    counts = np.vstack([c for _, c in rec.iter_counts()]).astype(np.float64)
    m = fit(
        counts,
        b.values,
        b.valid,
        dims=b.dims,
        unit=b.unit,
        bin_ms=rec.bin_s * 1000,
        space="falcon_h1_7dof",
        training={"dataset": "DANDI:000954", "file": path.name, "session": session_of(path.name)},
        source={"identity": "dandi:000954:HumanPitt"},
    )
    m.save(models_dir / f"{m.model_id}.json")
    return m


@pytest.fixture(scope="module")
def trained(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, RidgeDecoder, RidgeDecoder]:
    if not HAVE_DATA:
        pytest.skip("real FALCON H1 files not found")
    d = tmp_path_factory.mktemp("models")
    return d, _train(TRAIN_FILE, d), _train(EVAL_FILE, d)


async def _falcon_source(
    tmp_path: Path, models_dir: Path, publishers: list[Any], hold: threading.Event
) -> tuple[Runtime, FalconLSLPublisher, str]:
    pub = FalconLSLPublisher(
        EVAL_FILE, speed=SPEED, source_prefix=f"t{os.getpid()}-{id(hold):x}", hold=hold
    )
    pub.start()
    publishers.append(pub)
    reg = DeviceRegistry(OperatorIntentSource(), tmp_path / "rec", models_dir=models_dir)
    reg.live.discover_lsl(1.5)
    k = pub.prefix
    desc = reg.live.configure_lsl(f"{k}-counts", f"{k}-behavior", f"{k}-markers")
    assert desc.kind is DeviceKind.REPLAY  # declared prerecorded -> never presented as live
    rt = Runtime(reg, Recorder(tmp_path / "rec"))
    return rt, pub, desc.device_id


async def _collect(sub: Any, until: Any, timeout: float) -> list[dict[str, Any]]:
    """Drain a subscriber continuously (its queue is bounded) until ``until()`` holds."""
    out: list[dict[str, Any]] = []

    def step() -> bool:
        out.extend(drain(sub))
        return bool(until())

    await wait_for(step, timeout=timeout, interval=0.02)
    out.extend(drain(sub))
    return out


def _read_recording(path: Path) -> list[dict[str, Any]]:
    with path.open() as fh:
        return [json.loads(line) for i, line in enumerate(fh) if i > 0 and line.strip()]


def _file_arrays(path: Path) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    rec = load(path)
    assert rec.behavior is not None
    counts = np.vstack([c for _, c in rec.iter_counts()]).astype(np.float64)
    return counts, rec.behavior.values, rec.behavior.valid


# ------------------------------------------------------------------ calibration (M3-AT-10)


@needs_data
async def test_calibrate_from_falcon_streamed_over_lsl(
    tmp_path: Path, trained: tuple[Path, RidgeDecoder, RidgeDecoder], publishers: list[Any]
) -> None:
    """Record a FALCON block streamed over LSL, calibrate from the recording.

    Every bin arrives exactly once and in order, provenance stays 'prerecorded', and the
    calibrated model scores the same held-out R² as fitting the file arrays directly.
    """
    hold = threading.Event()
    rt, pub, did = await _falcon_source(tmp_path, tmp_path / "models", publishers, hold)
    await rt.connect(did)
    name = rt.start_recording("falcon-lsl")
    hold.set()
    await wait_for(pub.finished.is_set, timeout=60)
    n = load(EVAL_FILE).n_bins
    await wait_for(lambda: rt.diagnostics.totals["features.binned"] >= n, timeout=10)
    await wait_for(lambda: rt.diagnostics.totals["behavior.sample"] >= n, timeout=10)
    info = rt.stop_recording()
    assert info.name == name
    path = tmp_path / "rec" / f"{name}.brainos.jsonl"
    msgs = _read_recording(path)
    feats = [e for e in msgs if e["event_type"] == "features.binned"]
    counts, beh, valid = _file_arrays(EVAL_FILE)
    got = np.array([e["payload"]["counts"] for e in feats], dtype=np.float64)
    assert got.shape == counts.shape and np.array_equal(got, counts)  # bit-exact, no loss
    for e in feats[:: max(1, len(feats) // 50)]:
        p = e["provenance"]
        assert p["replayed"] is True and p["synthetic"] is False
        assert p["origin"].startswith("dandi:000954/") and "replayed" in e["quality"]["flags"]
    assert rt.diagnostics.timestamp_regressions == 0
    trials = load(EVAL_FILE).behavior.trial  # type: ignore[union-attr]
    marks = [e["payload"]["label"] for e in msgs if e["event_type"] == "recording.annotation"]
    assert trials is not None and marks == [f"trial {int(t)}" for t in dict.fromkeys(trials)]
    await rt.shutdown()

    model, report = calibrate([path], models_dir=tmp_path / "models")
    assert model.training["session"] == "19250108T111022"
    assert model.training["prerecorded_source"] is True
    assert model.source["identity"] == "dandi:000954:HumanPitt"
    assert model.input["channel_labels"] and len(model.input["channel_labels"]) == 176
    assert (tmp_path / "models" / f"{model.model_id}.json").exists()

    # independent reference: same split on the file's own arrays
    split = report["train_bins"]
    test_start = split + report["gap_bins"]
    ref = fit(
        counts[:split],
        beh[:split],
        valid[:split],
        dims=model.dims,
        unit=model.unit,
        bin_ms=20.0,
        space="ref",
        training={},
    )
    res = evaluate(
        ref, counts[test_start:], beh[test_start:], valid[test_start:], skip_first=len(ref.kernel)
    )
    assert abs(report["r2"] - res["r2"]) < 2e-3  # behavior travels as float32 over LSL
    assert report["r2"] > report["control_mean_predictor_r2"] + 0.05
    assert report["labelled_bins"] == int(valid.sum())


def test_chronological_split_moves_to_trial_boundary() -> None:
    assert chronological_split(1000, 0.8, [100, 815, 900]) == 815
    assert chronological_split(1000, 0.8, [100, 990]) == 800  # too close to the end
    assert chronological_split(1000, 0.8, []) == 800


def test_calibration_refuses_recordings_without_labels(tmp_path: Path) -> None:
    path = tmp_path / "x.brainos.jsonl"
    lines: list[dict[str, Any]] = [{"format": "brainos.recording/1", "device": {}}]
    for i in range(10):
        lines.append(
            {
                "event_type": "features.binned",
                "device_timestamp_ns": i * 20_000_000,
                "provenance": {"adapter": "x@1", "origin": "o"},
                "payload": {"feature": "spike_count", "bin_ms": 20.0, "counts": [1, 2]},
            }
        )
    path.write_text("\n".join(json.dumps(x) for x in lines))
    with pytest.raises(CalibrationError, match="no behavioral targets"):
        calibrate([path])


# ------------------------------------------------- streaming decode + router (M3-AT-9/11/12)


@needs_data
async def test_falcon_over_lsl_decodes_like_offline_and_routes_only_on_request(
    tmp_path: Path, trained: tuple[Path, RidgeDecoder, RidgeDecoder], publishers: list[Any]
) -> None:
    models_dir, held_in, same_session = trained
    hold = threading.Event()
    rt, _pub, did = await _falcon_source(tmp_path, models_dir, publishers, hold)
    sub = subscribe(rt)
    pointer_app = subscribe(rt, required=[Capability.POINTER_INTENT], app_id="pointer-app")
    await rt.connect(did)
    assert pointer_app.negotiation.status is AppStatus.SUSPENDED  # raw features != commands

    # leakage guard: a model trained on this very block is refused
    with pytest.raises(RuntimeCommandError) as exc:
        rt.start_pipeline(
            PipelineStartRequest(
                processing={"preset": "features_passthrough"}, model_id=same_session.model_id
            )
        )
    assert exc.value.code is ErrorCode.INCOMPATIBLE_DECODER
    assert "training session" in exc.value.message

    st = rt.start_pipeline(
        PipelineStartRequest(
            processing={"preset": "features_passthrough"}, model_id=held_in.model_id
        )
    )
    assert st.running and not st.cross_source_override
    # decoder loaded, router off: still no pointer capability, app stays suspended
    assert pointer_app.negotiation.status is AppStatus.SUSPENDED
    hold.set()
    before = await _collect(sub, lambda: rt.pipeline.counters["decoded_out"] >= 1500, 30)
    assert events(before, "intent.pointer") == []

    rt.set_router(RouterSpec(enabled=True, x_dim="tx", y_dim="ty", gain=0.5))
    # M4: decoded commands need the operator's authorization of the app (default deny)
    assert pointer_app.negotiation.status is AppStatus.SUSPENDED
    ptr = [r for r in pointer_app.negotiation.rejected if r.capability is Capability.POINTER_INTENT]
    assert [r.reason.value for r in ptr] == ["not_authorized"]
    rt.authorize_app("pointer-app", [Capability.POINTER_INTENT])
    rt.authorize_app("test", [Capability.POINTER_INTENT])
    assert pointer_app.negotiation.status is AppStatus.ACTIVE
    n = load(EVAL_FILE).n_bins
    after = await _collect(sub, lambda: rt.pipeline.counters["decoded_out"] >= n, 60)
    assert sub.dropped == 0
    status = rt.pipeline.status()
    await rt.shutdown()

    msgs = before + after
    feats = events(msgs, "features.binned")
    decoded = events(msgs, "intent.kinematics")
    pointers = events(after, "intent.pointer")
    counts, _, _ = _file_arrays(EVAL_FILE)
    got = np.array([e["payload"]["counts"] for e in feats], dtype=np.float64)
    assert np.array_equal(got, counts)
    # the streaming decoder equals the offline decoder on the same input, bin for bin
    pred = np.array([e["payload"]["values"] for e in decoded])
    assert pred.shape == (n, 7)
    np.testing.assert_allclose(pred, held_in.predict_counts(counts), rtol=1e-9, atol=1e-9)
    assert [e["device_timestamp_ns"] for e in decoded] == [e["device_timestamp_ns"] for e in feats]
    p = decoded[0]["provenance"]
    assert p["kind"] == "decoded_intent" and p["model_id"] == held_in.model_id
    assert p["replayed"] is True and p["origin"].startswith("dandi:000954/")
    # commands: only after the router was enabled, derived from the decoded values
    assert len(pointers) > 100
    assert all(e["provenance"]["model_id"] == held_in.model_id for e in pointers)
    std = held_in.training["behavior_std"]
    by_ts = {e["device_timestamp_ns"]: e["payload"]["values"] for e in decoded}
    for e in pointers[:200]:
        v = by_ts[e["device_timestamp_ns"]]
        exp = PipelineManager._route(
            RouterSpec(enabled=True, x_dim="tx", y_dim="ty", gain=0.5), held_in.dims, v, std
        )
        assert (e["payload"]["vx"], e["payload"]["vy"]) == exp
    assert status.counters["dropped_inputs"] == 0 and status.counters["errors"] == 0
    assert status.processing_us.count > 0


@needs_data
async def test_incompatible_decoders_are_refused_with_reasons(
    tmp_path: Path, trained: tuple[Path, RidgeDecoder, RidgeDecoder], publishers: list[Any]
) -> None:
    """A 176-unit FALCON model on an 8-channel synthetic stream: refused, with reasons."""
    models_dir, held_in, _ = trained
    pub = SyntheticEphysPublisher(channels=8, source_id=f"syn-incompat-{os.getpid()}")
    pub.start()
    publishers.append(pub)
    reg = DeviceRegistry(OperatorIntentSource(), tmp_path / "rec", models_dir=models_dir)
    reg.live.discover_lsl(1.5)
    rt = Runtime(reg, Recorder(tmp_path / "rec"))
    await rt.connect(f"lsl:{pub.source_id}")
    with pytest.raises(RuntimeCommandError) as exc:
        rt.start_pipeline(
            PipelineStartRequest(
                processing={"preset": "spikeband_threshold"},
                model_id=held_in.model_id,
                allow_cross_source=True,
            )
        )
    assert exc.value.code is ErrorCode.INCOMPATIBLE_DECODER
    assert "176 channels" in exc.value.message
    with pytest.raises(RuntimeCommandError) as exc:
        rt.start_pipeline(PipelineStartRequest(processing={"preset": "features_passthrough"}))
    assert exc.value.code is ErrorCode.CAPABILITY_UNSUPPORTED
    with pytest.raises(RuntimeCommandError) as exc:
        rt.start_pipeline(
            PipelineStartRequest(
                processing={"preset": "spikeband_threshold"},
                router=RouterSpec(enabled=True, x_dim="tx", y_dim="ty"),
            )
        )
    assert "needs a loaded decoder" in exc.value.message
    await rt.shutdown()


def test_cross_source_requires_explicit_override(
    trained: tuple[Path, RidgeDecoder, RidgeDecoder],
) -> None:
    _, held_in, _ = trained
    kw: dict[str, Any] = {
        "event_type": "features.binned",
        "feature": "spike_count",
        "bin_ms": 20.0,
        "channel_count": 176,
        "channel_labels": None,
        "stream_identity": "lsl:other-lab-rig",
    }
    c = models.check(held_in, **kw)
    assert not c.ok and "explicit override required" in c.errors[0]
    c = models.check(held_in, allow_cross_source=True, **kw)
    assert c.ok and c.cross_source and c.warnings[-1].startswith("CROSS-SOURCE OVERRIDE")
    c = models.check(
        held_in, **{**kw, "stream_identity": "dandi:000954:HumanPitt"}, stream_session=None
    )
    assert c.ok and not c.cross_source


# --------------------------------------------- raw signal -> features -> calibrate -> decode


async def test_synthetic_raw_stream_full_loop(tmp_path: Path, publishers: list[Any]) -> None:
    """Broadband 30 kHz synthetic ephys over LSL -> spike-band thresholding in the pipeline ->
    recorded -> calibrated -> loaded back on a new connection. Synthetic data, declared so."""
    pub = SyntheticEphysPublisher(channels=16, source_id=f"syn-loop-{os.getpid()}", seed=3)
    pub.start()
    publishers.append(pub)
    models_dir = tmp_path / "models"
    reg = DeviceRegistry(OperatorIntentSource(), tmp_path / "rec", models_dir=models_dir)
    reg.live.discover_lsl(1.5)
    did = f"lsl:{pub.source_id}"
    reg.live.configure_lsl(pub.source_id, pub.source_id + "-behavior", None)
    rt = Runtime(reg, Recorder(tmp_path / "rec"))
    await rt.connect(did)
    assert rt.device is not None and rt.device.kind is DeviceKind.SIMULATED
    st = rt.start_pipeline(PipelineStartRequest(processing={"preset": "spikeband_threshold"}))
    assert st.output is not None and st.output["event_type"] == "features.binned"
    assert st.warmup_remaining_s > 0  # RMS threshold estimation
    await wait_for(lambda: rt.pipeline.status().warmup_remaining_s == 0, timeout=10)
    name = rt.start_recording("syn-cal")
    await wait_for(lambda: rt.pipeline.counters["features_out"] >= 900, timeout=40)
    rt.stop_recording()
    status = rt.pipeline.status()
    assert status.counters["dropped_inputs"] == 0 and status.counters["errors"] == 0
    assert rt.diagnostics.timestamp_regressions == 0
    await rt.disconnect()

    path = tmp_path / "rec" / f"{name}.brainos.jsonl"
    model, report = calibrate([path], models_dir=models_dir, feature_source="brainos.pipeline")
    assert report["synthetic_source"] is True and report["source_identity"]
    # synthetic units are cosine-tuned to the latent velocity, so this must be decodable
    assert report["r2"] > 0.3 > report["control_mean_predictor_r2"]

    await rt.connect(did)
    st = rt.start_pipeline(
        PipelineStartRequest(
            processing={"preset": "spikeband_threshold"},
            model_id=model.model_id,
            router=RouterSpec(enabled=True, x_dim="vx", y_dim="vy"),
        )
    )
    assert st.decoder is not None and not st.cross_source_override
    rt.authorize_app("test", [Capability.POINTER_INTENT])  # authorizations survive reconnects
    sub = subscribe(rt)
    await wait_for(lambda: rt.pipeline.counters["commands_out"] >= 20, timeout=20)
    ptr = events(drain(sub), "intent.pointer")
    assert ptr and all(e["provenance"]["synthetic"] for e in ptr)
    lat = rt.pipeline.status().pipeline_latency_ms
    assert lat.count > 0 and lat.p50 is not None
    await rt.shutdown()


# ------------------------------------------- Open Ephys + LSL through one runtime (M3-AT-13)


async def test_same_app_and_pipeline_across_open_ephys_and_lsl(
    tmp_path: Path, publishers: list[Any]
) -> None:
    """An unchanged app follows a switch between an Open Ephys ZMQ source and an LSL source;
    the same spike-band pipeline runs on both, and neither yields commands by itself."""
    pytest.importorskip("zmq")
    from brainos.adapters.openephys import OpenEphysConfig
    from brainos.adapters.openephys.publisher import OpenEphysTestPublisher
    from brainos.testing.lsl_publishers import SyntheticEphys

    from .test_openephys import free_port_pair

    gen = SyntheticEphys(channels=8, fs=30_000.0, seed=4)

    def signal(_s: int, n: int, chans: tuple[int, ...]) -> np.ndarray:
        return gen.chunk(n, 0.5, 0.0).T[: len(chans)].astype(np.float32)

    port = free_port_pair()
    oe = OpenEphysTestPublisher(
        data_port=port, channels=tuple(range(8)), block_size=1024, signal=signal
    ).start()
    publishers.append(oe)
    lsl = SyntheticEphysPublisher(channels=8, source_id=f"syn-switch-{os.getpid()}")
    lsl.start()
    publishers.append(lsl)

    reg = DeviceRegistry(OperatorIntentSource(), tmp_path / "rec", models_dir=tmp_path / "m")
    oe_desc = reg.live.configure_openephys(
        OpenEphysConfig(host="127.0.0.1", data_port=port, unit="uV")
    )
    reg.live.discover_lsl(1.5)
    rt = Runtime(reg, Recorder(tmp_path / "rec"))
    viewer = subscribe(rt, required=[Capability.NEURAL_FEATURES], app_id="viewer")
    cursor = subscribe(rt, required=[Capability.POINTER_INTENT], app_id="cursor")

    for did in (oe_desc.device_id, f"lsl:{lsl.source_id}", oe_desc.device_id):
        if rt.device is None:
            await rt.connect(did)
        else:
            await rt.switch(did)
        assert rt.device is not None
        assert rt.device.kind in (DeviceKind.STREAM, DeviceKind.SIMULATED)  # LSL: declared syn.
        # raw recording only: the feature viewer waits, the cursor app is never activated
        assert viewer.negotiation.status is AppStatus.SUSPENDED
        st = rt.start_pipeline(PipelineStartRequest(processing={"preset": "spikeband_threshold"}))
        assert st.running and st.output is not None and st.output["channel_count"] == 8
        assert viewer.negotiation.status is AppStatus.ACTIVE
        assert cursor.negotiation.status is AppStatus.SUSPENDED
        await wait_for(lambda: rt.pipeline.counters["features_out"] >= 25, timeout=20)
        msgs = drain(viewer)
        feats = [
            e
            for e in events(msgs, "features.binned")
            if e["provenance"]["adapter"].startswith("brainos.pipeline")
        ]
        assert feats and all(e["device_id"] == did for e in feats)
        assert events(msgs, "intent.pointer") == []
        assert rt.pipeline.counters["errors"] == 0
    assert rt.diagnostics.validation_errors == 0
    await rt.shutdown()
