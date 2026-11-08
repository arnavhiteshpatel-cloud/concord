"""Milestone 5 (workstream A): decoders through the runtime pipeline.

Built-in (in-process) and isolated (ONNX file, pickle with an explicit trust decision,
decoder plugins) decoders behind one interface; compatibility refusals and the explicit
channel mapping; decoder failure containment; joined multi-feature inputs; several decoders
routed together; decoded passthrough of a source's historical decoder; drift; calibration
round trip across a runtime restart. All data here is SYNTHETIC (declared so).
"""

from __future__ import annotations

import asyncio
import json
import pickle
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from concord.adapters.simulated import OperatorIntentSource
from concord.contracts import Capability
from concord.contracts.protocol import ErrorCode
from concord.decoding.calibrate import CalibrationError, calibrate_capability
from concord.decoding.lda import fit_lda
from concord.decoding.ridge import RidgeDecoder, fit
from concord.runtime import DeviceRegistry, Recorder, Runtime, RuntimeCommandError
from concord.runtime.pipeline import DECODED_PASSTHROUGH, PipelineStartRequest, RouterSpec
from concord.runtime.router import DiscreteRule

from .conftest import subscribe
from .decoder_helpers import (
    BIN_MS,
    FeatureSource,
    SourceDecoder,
    Stream,
    make_decoder_dist,
    plugin_env,
    tuned_data,
)
from .helpers import drain, events, wait_for

LABELS = ["e1", "e2", "e3", "e4"]
W = np.array([[0.5, -0.25], [0.125, 0.75], [-0.5, 0.0625], [0.25, 0.25]])  # test plugin's
TX = "threshold_crossing_count"
SPEC = {
    "event_type": "features.binned",
    "feature": TX,
    "bin_ms": BIN_MS,
    "channel_count": 4,
    "channel_labels": LABELS,
    "unit": "count",
}
PASS = {"preset": "features_passthrough"}


def _ridge(counts: np.ndarray, vel: np.ndarray, models_dir: Path, **kw: Any) -> RidgeDecoder:
    spec = kw.pop("input_spec", {**SPEC, "channel_count": counts.shape[1]})
    m = fit(
        counts,
        vel,
        np.ones(len(counts), bool),
        dims=["vx", "vy"],
        unit="workspace/s",
        bin_ms=BIN_MS,
        space="test",
        training={"dataset": "synthetic"},
        input_spec=spec,
        source={"identity": "test:feature-source"},
        **kw,
    )
    m.save(models_dir / f"{m.model_id}.json")
    return m


@pytest.fixture
def models_dir(tmp_path: Path) -> Path:
    d = tmp_path / "models"
    d.mkdir()
    return d


@pytest.fixture
async def make_rt(tmp_path: Path, models_dir: Path) -> AsyncIterator[Any]:
    made: list[Runtime] = []

    async def make(src: FeatureSource) -> Runtime:
        reg = DeviceRegistry(OperatorIntentSource(), tmp_path / "rec", models_dir=models_dir)
        reg.register(src.descriptor, lambda: src)
        rt = Runtime(reg, Recorder(tmp_path / "rec"))
        made.append(rt)
        await rt.connect(src.device_id)
        return rt

    yield make
    for rt in made:
        await rt.shutdown()


def _decoded(msgs: list[dict[str, Any]], model_id: str) -> np.ndarray:
    return np.array(
        [
            e["payload"]["values"]
            for e in events(msgs, "intent.kinematics")
            if e["provenance"]["model_id"] == model_id
        ]
    )


async def _run(
    rt: Runtime, src: FeatureSource, sub: Any, until: Any, timeout: float = 30
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    src.release.set()

    def step() -> bool:
        out.extend(drain(sub))
        return bool(until())

    await wait_for(step, timeout=timeout, interval=0.01)
    await asyncio.sleep(0.05)
    out.extend(drain(sub))
    return out


# ----------------------------------------------------------------------------- built-in


async def test_builtin_decoder_output_equals_offline_bit_for_bit(
    make_rt: Any, models_dir: Path
) -> None:
    counts, vel = tuned_data(300, 4, seed=1)
    m = _ridge(counts[:200], vel[:200], models_dir)
    src = FeatureSource(streams=[Stream("features.binned", TX, counts[200:], LABELS, "count")])
    rt = await make_rt(src)
    sub = subscribe(rt)
    st = rt.start_pipeline(PipelineStartRequest(processing=PASS, model_id=m.model_id))
    assert st.decoder is not None and st.decoder["family"] == "ridge"
    assert st.decoder["origin"] == "concord-trained" and st.decoder["execution"] == "in_process"
    msgs = await _run(rt, src, sub, lambda: rt.pipeline.counters["decoded_out"] >= 100)
    got = _decoded(msgs, m.model_id)
    assert np.array_equal(got, m.predict_counts(counts[200:]))  # bit for bit
    p = events(msgs, "intent.kinematics")[0]["provenance"]
    assert p["model_origin"] == "concord" and p["kind"] == "decoded_intent"
    assert p["adapter"].startswith("concord.pipeline@")


# ----------------------------------------------------------------------------- model files

onnx = pytest.importorskip("onnx", reason="onnx builds the test ONNX model (decoder SDK dev extra)")


def _onnx_bundle(models_dir: Path, w: np.ndarray, b: np.ndarray, tmp: Path) -> str:
    from concord_decoder_sdk import (
        API_VERSION,
        InputSpec,
        Modality,
        ModelManifest,
        OutputKind,
        OutputSpec,
        ParticipantCompat,
    )
    from concord_decoder_sdk.formats import write_bundle
    from onnx import TensorProto, helper, numpy_helper

    g = helper.make_graph(
        [
            helper.make_node("MatMul", ["x", "W"], ["xw"]),
            helper.make_node("Add", ["xw", "b"], ["y"]),
        ],
        "lin",
        [helper.make_tensor_value_info("x", TensorProto.DOUBLE, [1, 4])],
        [helper.make_tensor_value_info("y", TensorProto.DOUBLE, [1, 2])],
        [numpy_helper.from_array(w, "W"), numpy_helper.from_array(b, "b")],
    )
    model = helper.make_model(g, opset_imports=[helper.make_opsetid("", 17)])
    model.ir_version = 8
    onnx.save(model, str(tmp / "lin.onnx"))
    man = ModelManifest(
        model_id="onnx-linear",
        name="ONNX linear",
        version="1.0.0",
        api_version=API_VERSION,
        family="onnx",
        description="exported linear decoder (test)",
        author="tests",
        license="CC0",
        modalities=frozenset({Modality.INTRACORTICAL}),
        inputs=(InputSpec("features.binned", TX, BIN_MS, 4, tuple(LABELS), "count"),),
        output=OutputSpec(
            OutputKind.CONTINUOUS, "velocity", ("vx", "vy"), "workspace/s", "s", (1.0, 1.0)
        ),
        compatibility=ParticipantCompat(source_identity="test:feature-source"),
    )
    io = {"input": {"name": "x", "shape": [1, 4]}, "output": {"name": "y", "shape": [1, 2]}}
    write_bundle(models_dir, man, tmp / "lin.onnx", "onnx", io)
    return man.model_id


async def test_onnx_model_file_runs_isolated_and_matches(
    make_rt: Any, models_dir: Path, tmp_path: Path
) -> None:
    rng = np.random.default_rng(2)
    w, b = rng.standard_normal((4, 2)), rng.standard_normal(2)
    mid = _onnx_bundle(models_dir, w, b, tmp_path)
    counts, _ = tuned_data(120, 4, seed=3)
    src = FeatureSource(streams=[Stream("features.binned", TX, counts, LABELS, "count")])
    rt = await make_rt(src)
    sub = subscribe(rt)
    st = await rt.start_pipeline_async(PipelineStartRequest(processing=PASS, model_id=mid))
    d = st.decoder
    assert d is not None and d["origin"] == "imported" and d["execution"] == "isolated"
    assert d["state"] == "ready" and d["pid"]
    msgs = await _run(rt, src, sub, lambda: rt.pipeline.counters["decoded_out"] >= 120)
    np.testing.assert_allclose(_decoded(msgs, mid), counts @ w + b, rtol=1e-12, atol=1e-12)


async def test_pickle_is_refused_until_the_operator_trusts_the_file(
    make_rt: Any, models_dir: Path, tmp_path: Path
) -> None:
    sklearn = pytest.importorskip("sklearn", reason="scikit-learn (decoder SDK sklearn extra)")
    from concord_decoder_sdk import (
        API_VERSION,
        InputSpec,
        Modality,
        ModelManifest,
        OutputKind,
        OutputSpec,
        ParticipantCompat,
    )
    from concord_decoder_sdk.formats import write_bundle

    counts, vel = tuned_data(200, 4, seed=4)
    est = sklearn.linear_model.Ridge().fit(counts, vel)
    (tmp_path / "r.pkl").write_bytes(pickle.dumps(est))
    man = ModelManifest(
        model_id="pickled-ridge",
        name="pickled",
        version="1.0.0",
        api_version=API_VERSION,
        family="sklearn",
        description="pickled sklearn ridge (test)",
        author="t",
        license="CC0",
        modalities=frozenset({Modality.INTRACORTICAL}),
        inputs=(InputSpec("features.binned", TX, BIN_MS, 4, tuple(LABELS), "count"),),
        output=OutputSpec(OutputKind.CONTINUOUS, "velocity", ("vx", "vy"), "workspace/s", "s"),
        compatibility=ParticipantCompat(source_identity="test:feature-source"),
    )
    write_bundle(models_dir, man, tmp_path / "r.pkl", "pickle", {"method": "predict"})
    src = FeatureSource(streams=[Stream("features.binned", TX, counts[:50], LABELS, "count")])
    rt = await make_rt(src)
    with pytest.raises(RuntimeCommandError) as exc:
        await rt.start_pipeline_async(
            PipelineStartRequest(processing=PASS, model_id="pickled-ridge")
        )
    assert exc.value.code is ErrorCode.INCOMPATIBLE_DECODER
    assert "mark this exact file trusted" in exc.value.message
    reg = rt.pipeline.registry
    trust = reg.set_trust("pickled-ridge", True, by="pytest operator")
    assert trust is not None and trust["by"] == "pytest operator"
    sub = subscribe(rt)
    st = await rt.start_pipeline_async(
        PipelineStartRequest(processing=PASS, model_id="pickled-ridge")
    )
    assert st.decoder is not None and st.decoder["trust"]["by"] == "pytest operator"
    msgs = await _run(rt, src, sub, lambda: rt.pipeline.counters["decoded_out"] >= 50)
    np.testing.assert_allclose(
        _decoded(msgs, "pickled-ridge"), est.predict(counts[:50]), rtol=1e-12
    )


# ----------------------------------------------------------------------------- plugins


@pytest.fixture
async def plugins(tmp_path: Path) -> list[str]:
    site = make_decoder_dist(
        tmp_path / "site",
        {
            "test-linear": "concord_backend_decoders:LabelledLinear",
            "test-crash": "concord_backend_decoders:CrashAfter",
            "test-hang": "concord_backend_decoders:HangAfter",
            "test-nan": "concord_backend_decoders:NaNAfter",
            "test-eeg": "concord_backend_decoders:EEGOnly",
            "test-variance": "concord_backend_decoders:WithVariance",
        },
    )
    return plugin_env(site)


async def _with_plugins(rt: Runtime, extra: list[str]) -> None:
    rt.pipeline.registry.configure(None, extra)
    await rt.pipeline.registry.discover_plugins()


async def test_decoder_plugin_with_explicit_label_mapping(make_rt: Any, plugins: list[str]) -> None:
    counts, _ = tuned_data(80, 5, seed=5)
    src_labels = ["e3", "x9", "e1", "e4", "e2"]
    src = FeatureSource(streams=[Stream("features.binned", TX, counts, src_labels, "count")])
    rt = await make_rt(src)
    await _with_plugins(rt, plugins)
    rec = rt.pipeline.registry.get("test-plugin-linear")
    assert rec is not None and rec.origin == "plugin" and rec.status == "ok"
    with pytest.raises(RuntimeCommandError) as exc:
        await rt.start_pipeline_async(
            PipelineStartRequest(processing=PASS, model_id="test-plugin-linear")
        )
    assert "enable explicit channel mapping by label" in exc.value.message
    assert (
        "model expects 4 channels labelled e1, e2, e3, …; source provides 5 channels labelled e3, x9, e1, …"
        in exc.value.message
    )
    sub = subscribe(rt)
    st = await rt.start_pipeline_async(
        PipelineStartRequest(
            processing=PASS, model_id="test-plugin-linear", allow_channel_mapping=True
        )
    )
    assert st.channel_mapping and any("mapped by label" in w for w in st.compatibility_warnings)
    assert st.decoder is not None and st.decoder["origin"] == "plugin"
    msgs = await _run(rt, src, sub, lambda: rt.pipeline.counters["decoded_out"] >= 80)
    idx = [src_labels.index(lbl) for lbl in LABELS]
    np.testing.assert_array_equal(_decoded(msgs, "test-plugin-linear"), counts[:, idx] @ W)


async def test_modality_mismatch_is_refused(make_rt: Any, plugins: list[str]) -> None:
    counts, _ = tuned_data(10, 4)
    rt = await make_rt(
        FeatureSource(streams=[Stream("features.binned", TX, counts, LABELS, "count")])
    )
    await _with_plugins(rt, plugins)
    with pytest.raises(RuntimeCommandError) as exc:
        await rt.start_pipeline_async(
            PipelineStartRequest(processing=PASS, model_id="test-plugin-eeg")
        )
    assert "model was trained on eeg recordings; this source is intracortical" in exc.value.message


@pytest.mark.parametrize(
    ("model_id", "reason"),
    [
        ("test-plugin-crash", "exited"),
        ("test-plugin-nan", "InvalidOutput"),
        ("test-plugin-hang", "did not answer"),
    ],
)
async def test_failing_plugin_is_stopped_and_stops_commands(
    make_rt: Any, plugins: list[str], model_id: str, reason: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    from concord.decoding import engine

    monkeypatch.setattr(engine, "STEP_TIMEOUT_S", 1.0)
    counts, _ = tuned_data(60, 4, seed=6)
    src = FeatureSource(streams=[Stream("features.binned", TX, counts, LABELS, "count")], end=False)
    rt = await make_rt(src)
    await _with_plugins(rt, plugins)
    rt.authorize_app("test", [Capability.POINTER_INTENT])
    sub = subscribe(rt)
    await rt.start_pipeline_async(
        PipelineStartRequest(
            processing=PASS,
            model_id=model_id,
            router=RouterSpec(enabled=True, x_dim="vx", y_dim="vy"),
        )
    )
    assert rt.pipeline.router_on
    await _run(rt, src, sub, lambda: rt.pipeline.counters["decoder_failures"] >= 1, timeout=20)
    st = rt.pipeline.status()
    assert st.running and st.decoder is not None and st.decoder["state"] == "failed"
    assert reason in (st.decoder["error"] or "") and reason in (st.last_error or "")
    assert not rt.pipeline.router_on  # no stale commands from a dead decoder
    assert st.last_router_stop is not None and "failed" in st.last_router_stop.reason
    assert st.counters["decoded_out"] <= 10
    with pytest.raises(RuntimeCommandError, match="failed"):
        rt.set_router(RouterSpec(enabled=True, x_dim="vx", y_dim="vy"))


async def test_isolated_confidence_and_plugin_listing(make_rt: Any, plugins: list[str]) -> None:
    counts, _ = tuned_data(20, 4, seed=8)
    src = FeatureSource(streams=[Stream("features.binned", TX, counts, LABELS, "count")])
    rt = await make_rt(src)
    await _with_plugins(rt, plugins)
    ids = {r.model_id: r for r in rt.pipeline.registry.records()}
    assert {"test-plugin-linear", "test-plugin-crash", "test-plugin-variance"} <= set(ids)
    st = await rt.start_pipeline_async(
        PipelineStartRequest(processing=PASS, model_id="test-plugin-variance")
    )
    assert st.decoder is not None and st.decoder["confidence"] == "variance"
    sub = subscribe(rt)
    msgs = await _run(rt, src, sub, lambda: rt.pipeline.counters["decoded_out"] >= 20)
    np.testing.assert_array_equal(_decoded(msgs, "test-plugin-variance"), counts @ W)


# ----------------------------------------------------------------------------- multi-input


async def test_two_feature_streams_are_joined_by_bin(make_rt: Any, models_dir: Path) -> None:
    counts, vel = tuned_data(260, 4, seed=9)
    sbp = np.log1p(counts) * 3.0 + np.random.default_rng(9).standard_normal(counts.shape) * 0.1
    both = np.hstack([counts, sbp])
    sbp_spec = {
        **SPEC,
        "event_type": "features.vector",
        "feature": "spike_band_power",
        "unit": "arbitrary^2",
    }
    m = _ridge(both[:180], vel[:180], models_dir, input_spec={**SPEC, "channel_count": 8})
    m.inputs = [dict(SPEC), sbp_spec]
    m.save(models_dir / f"{m.model_id}.json")
    streams = [
        Stream("features.binned", TX, counts[180:], LABELS, "count"),
        Stream("features.vector", "spike_band_power", sbp[180:], LABELS, "arbitrary^2"),
    ]
    src = FeatureSource(streams=streams)
    rt = await make_rt(src)
    sub = subscribe(rt)
    st = rt.start_pipeline(PipelineStartRequest(processing=PASS, model_id=m.model_id))
    assert [o["feature"] for o in st.outputs] == [TX, "spike_band_power"]
    msgs = await _run(rt, src, sub, lambda: rt.pipeline.counters["decoded_out"] >= 80)
    assert np.array_equal(_decoded(msgs, m.model_id), m.predict_counts(both[180:]))
    # a bin missing in one stream is never decoded with stale or padded values
    src2 = FeatureSource(device_id="test-features-2", streams=streams, drop={(1, 10)})
    rt2 = await make_rt(src2)
    rt2.start_pipeline(PipelineStartRequest(processing=PASS, model_id=m.model_id))
    sub2 = subscribe(rt2)
    msgs2 = await _run(rt2, src2, sub2, lambda: rt2.pipeline.counters["decoded_out"] >= 79)
    assert rt2.pipeline.counters["join_dropped"] == 1
    ts = [e["device_timestamp_ns"] for e in events(msgs2, "intent.kinematics")]
    assert len(ts) == 79 and int((10 + 1) * BIN_MS * 1e6) not in ts


# ----------------------------------------------------------------------------- two decoders


async def test_velocity_and_click_decoders_routed_together(make_rt: Any, models_dir: Path) -> None:
    counts, vel = tuned_data(500, 6, seed=10)
    click = (vel[:, 0] > 0.8).astype(float)
    counts[:, 5] += click * 8  # channel 6 fires during "clicks"
    spec6 = {**SPEC, "channel_count": 6, "channel_labels": [*LABELS, "e5", "e6"]}
    ridge = _ridge(counts[:300], vel[:300], models_dir, input_spec=spec6)
    lda = fit_lda(
        counts[:300],
        click[:300],
        np.ones(300, bool),
        class_values=[0.0, 1.0],
        class_names=["no_click", "click"],
        bin_ms=BIN_MS,
        tau_ms=60.0,
        space="click",
        training={},
        input_spec=spec6,
        source={"identity": "test:feature-source"},
    )
    lda.save(models_dir / f"{lda.model_id}.json")
    src = FeatureSource(
        streams=[Stream("features.binned", TX, counts[300:], spec6["channel_labels"], "count")]
    )
    rt = await make_rt(src)
    rt.authorize_app("test", [Capability.POINTER_INTENT, Capability.SELECTION])
    sub = subscribe(rt)
    router = RouterSpec(
        enabled=True,
        x_dim="vx",
        y_dim="vy",
        discrete=[
            DiscreteRule(
                output="click", threshold=0.6, hold_ms=0, refractory_ms=100, action="primary"
            )
        ],
    )
    st = rt.start_pipeline(
        PipelineStartRequest(
            processing=PASS, model_id=ridge.model_id, model_ids=[lda.model_id], router=router
        )
    )
    assert [d["model_id"] for d in st.decoders] == [ridge.model_id, lda.model_id]
    assert set(st.router_capabilities) == {Capability.POINTER_INTENT, Capability.SELECTION}
    msgs = await _run(rt, src, sub, lambda: rt.pipeline.counters["decoded_out"] >= 400)
    ptr, sel = events(msgs, "intent.pointer"), events(msgs, "intent.selection")
    assert len(ptr) == 200 and all(e["provenance"]["model_id"] == ridge.model_id for e in ptr)
    assert sel and all(e["provenance"]["model_id"] == lda.model_id for e in sel)
    assert all(e["provenance"]["model_origin"] == "concord" for e in ptr + sel)
    other = _ridge(counts[:250], vel[:250], models_dir, input_spec=spec6)  # also outputs vx, vy
    with pytest.raises(RuntimeCommandError, match="distinct output names"):
        rt.start_pipeline(
            PipelineStartRequest(
                processing=PASS, model_id=ridge.model_id, model_ids=[other.model_id]
            )
        )


# ----------------------------------------------------------------------------- passthrough


def _passthrough_source(**kw: Any) -> FeatureSource:
    rng = np.random.default_rng(11)
    n = 200
    vel = rng.standard_normal((n, 2))
    click = np.zeros((n, 1))
    click[[30, 31, 90, 150, 151, 152], 0] = 1.0  # three click decisions
    decs = [
        SourceDecoder("hist-velocity", ["vx", "vy"], vel, y_axis="up", scale=[2.0, 2.0]),
        SourceDecoder(
            "hist-click", ["click"], click, quantity="click_decision", unit="probability"
        ),
    ]
    return FeatureSource(decoders=decs, replayed=True, **kw)


async def test_decoded_passthrough_keeps_model_id_and_historical_origin(make_rt: Any) -> None:
    src = _passthrough_source()
    rt = await make_rt(src)
    rt.authorize_app("test", [Capability.POINTER_INTENT, Capability.SELECTION])
    sub = subscribe(rt)
    rule = DiscreteRule(output="click", threshold=0.5, hold_ms=0, refractory_ms=0, action="primary")
    with pytest.raises(RuntimeCommandError, match="declares \\+y up"):
        rt.start_pipeline(
            PipelineStartRequest(
                processing={"preset": DECODED_PASSTHROUGH},
                router=RouterSpec(enabled=True, x_dim="vx", y_dim="vy", discrete=[rule]),
            )
        )
    router = RouterSpec(
        enabled=True, x_dim="vx", y_dim="vy", invert_y=True, gain=0.5, deadzone=0.0, discrete=[rule]
    )
    st = rt.start_pipeline(
        PipelineStartRequest(processing={"preset": DECODED_PASSTHROUGH}, router=router)
    )
    assert [s["model_origin"] for s in st.source_decoders] == ["historical", "historical"]
    assert st.decoders == [] and st.source_decoders[0]["y_axis"] == "up"
    msgs = await _run(rt, src, sub, lambda: rt.pipeline.counters["decoded_in"] >= 400)
    kin = events(msgs, "intent.kinematics")
    assert len(kin) == 400 and all(
        not e["provenance"]["adapter"].startswith("concord.pipeline") for e in kin
    )
    ptr, sel = events(msgs, "intent.pointer"), events(msgs, "intent.selection")
    assert len(ptr) == 200 and len(sel) == 3
    for e in ptr + sel:
        p = e["provenance"]
        assert p["model_origin"] == "historical" and p["replayed"] is True
        assert p["adapter"].startswith("concord.pipeline@")
    assert {e["provenance"]["model_id"] for e in ptr} == {"hist-velocity"}
    assert {e["provenance"]["model_id"] for e in sel} == {"hist-click"}
    vel = src.decoders[0].values
    exp = [
        (round(max(-2, min(2, 0.5 * v[0] / 2.0)), 6), -round(max(-2, min(2, 0.5 * v[1] / 2.0)), 6))
        for v in vel
    ]
    assert [(e["payload"]["vx"], e["payload"]["vy"]) for e in ptr] == exp
    assert rt.pipeline.counters["decoded_out"] == 0  # nothing re-labelled as concord output


async def test_decoded_passthrough_refuses_concord_or_unlabelled_outputs(make_rt: Any) -> None:
    rng = np.random.default_rng(12)
    src = FeatureSource(
        decoders=[
            SourceDecoder("own", ["vx", "vy"], rng.standard_normal((5, 2)), model_origin="concord")
        ]
    )
    rt = await make_rt(src)
    with pytest.raises(
        RuntimeCommandError, match="does not declare model_origin 'historical' or 'external'"
    ):
        rt.start_pipeline(PipelineStartRequest(processing={"preset": DECODED_PASSTHROUGH}))
    with pytest.raises(RuntimeCommandError, match="loads no model"):
        rt.start_pipeline(
            PipelineStartRequest(processing={"preset": DECODED_PASSTHROUGH}, model_id="x")
        )
    counts, _ = tuned_data(5, 4)
    rt2 = await make_rt(
        FeatureSource(
            device_id="feat-only", streams=[Stream("features.binned", TX, counts, LABELS, "count")]
        )
    )
    with pytest.raises(RuntimeCommandError, match="provides no decoder output"):
        rt2.start_pipeline(PipelineStartRequest(processing={"preset": DECODED_PASSTHROUGH}))


# ----------------------------------------------------------------------------- drift


async def test_drift_flags_a_shifted_stream_only(make_rt: Any, models_dir: Path) -> None:
    counts, vel = tuned_data(1200, 8, seed=13)
    spec = {**SPEC, "channel_count": 8, "channel_labels": [f"e{i}" for i in range(1, 9)]}
    m = _ridge(counts[:600], vel[:600], models_dir, input_spec=spec)
    assert m.training["feature_stats"]["bins"] == 600
    results = {}
    for name, data in (("same", counts[600:]), ("shifted", counts[600:] + 4.0)):
        src = FeatureSource(
            device_id=f"drift-{name}",
            streams=[Stream("features.binned", TX, data, spec["channel_labels"], "count")],
            behavior=vel[600:],
            end=False,
        )
        rt = await make_rt(src)
        rt.start_pipeline(PipelineStartRequest(processing=PASS, model_id=m.model_id))
        sub = subscribe(rt)
        await _run(rt, src, sub, lambda rt=rt: rt.pipeline.counters["decoded_out"] >= 600)
        results[name] = rt.pipeline.status()
    same, shifted = results["same"], results["shifted"]
    mon_s = same.decoders[0]["monitor"]
    mon_x = shifted.decoders[0]["monitor"]
    assert not same.recalibration_recommended and mon_s["features"]["shift_z_rms"] < 0.5
    assert mon_s["labels"]["metric"] == "r2" and mon_s["labels"]["pairs"] >= 400
    assert shifted.recalibration_recommended and mon_x["features"]["shift_z_rms"] > 1.0
    assert any("moved" in r for r in mon_x["reasons"])


# ----------------------------------------------------------------------------- calibration


async def _record(make_rt: Any, src: FeatureSource) -> Path:
    rt: Runtime = await make_rt(src)
    rt.start_pipeline(PipelineStartRequest(processing=PASS))
    name = rt.start_recording(f"cal-{src.device_id}", exclude_raw=True)
    src.release.set()
    await wait_for(lambda: rt.diagnostics.totals["behavior.sample"] >= src.n, timeout=30)
    await asyncio.sleep(0.05)
    rt.stop_recording()
    path = rt.recorder.directory / f"{name}.concord.jsonl"
    await rt.shutdown()
    return path


async def test_calibration_round_trip_across_a_restart(
    make_rt: Any, models_dir: Path, tmp_path: Path
) -> None:
    counts, vel = tuned_data(1500, 6, seed=14)
    labels6 = [f"e{i}" for i in range(1, 7)]
    src = FeatureSource(
        streams=[Stream("features.binned", TX, counts[:1000], labels6, "count")],
        behavior=vel[:1000],
        behavior_params={"y_axis": "down"},
        end=False,
    )
    path = await _record(make_rt, src)
    model, report = calibrate_capability([path], "continuous", models_dir=models_dir)
    assert report["capability"] == "continuous" and report["family"] == "ridge"
    assert report["r2"] > 0.3 > report["control_mean_predictor_r2"]
    ve = report["velocity_error"]
    assert 0 < ve["mean_vector_error"] < ve["mean_target_speed"]
    man = model.manifest
    assert man["modalities"] == ["intracortical"] and man["inputs"][0]["channel_labels"] == labels6
    assert man["output"]["y_axis"] == "down" and man["calibration"]["label_dims"] == ["vx", "vy"]
    assert (
        model.training["output_stats"]
        and model.training["feature_stats"]["bins"] == report["train_bins"]
    )
    saved = json.loads((models_dir / f"{model.model_id}.json").read_text())
    assert saved["manifest"]["model_id"] == model.model_id
    # "restart": a new registry and runtime load the saved file and decode new data
    src2 = FeatureSource(
        device_id="later-session",
        streams=[Stream("features.binned", TX, counts[1000:], labels6, "count")],
    )
    rt = await make_rt(src2)
    sub = subscribe(rt)
    st = rt.start_pipeline(PipelineStartRequest(processing=PASS, model_id=model.model_id))
    assert st.decoder is not None and st.decoder["modalities"] == ["intracortical"]
    msgs = await _run(rt, src2, sub, lambda: rt.pipeline.counters["decoded_out"] >= 500)
    assert np.array_equal(_decoded(msgs, model.model_id), model.predict_counts(counts[1000:]))


async def test_click_and_class_calibration_and_label_checks(make_rt: Any, models_dir: Path) -> None:
    counts, vel = tuned_data(1500, 6, seed=15)
    click = np.zeros(1500)
    for start in range(40, 1500, 60):
        click[start : start + 4] = 1.0
    counts[:, :2] += click[:, None] * 25
    labels6 = [f"e{i}" for i in range(1, 7)]
    src = FeatureSource(
        streams=[Stream("features.binned", TX, counts, labels6, "count")],
        behavior=np.c_[vel, click],
        behavior_dims=["vx", "vy", "click"],
        end=False,
    )
    path = await _record(make_rt, src)
    model, report = calibrate_capability([path], "click", models_dir=models_dir, tau_ms=20.0)
    ev = report["events"]
    assert report["family"] == "lda" and model.classes == ["no_click", "click"]
    assert ev["true_events"] >= 3 and ev["event_recall"] > 0.5 and ev["event_precision"] > 0.5
    assert ev["event_hits"] + ev["event_false_positives"] == ev["detected_events"]
    assert ev["roc_auc"] > 0.9
    with pytest.raises(CalibrationError, match="0 \\(no click\\) / 1 \\(click\\)"):
        calibrate_capability([path], "click", label_dim="vx")
    with pytest.raises(CalibrationError, match="choose the class label with label_dim"):
        calibrate_capability([path], "classes")
    m2, r2 = calibrate_capability(
        [path], "classes", label_dim="click", class_names=["idle", "press"], tau_ms=20.0
    )
    assert m2.classes == ["idle", "press"] and r2["balanced_accuracy"] > 0.6
    from concord.decoding.calibrate import check_recordings

    chk = check_recordings([path], "continuous")
    assert chk.ok and chk.label_dims == ["vx", "vy", "click"]
    lab_only = FeatureSource(
        device_id="codes",
        streams=[Stream("features.binned", TX, counts[:600], labels6, "count")],
        behavior=np.c_[click[:600], click[:600]],
        end=False,
    )
    p2 = await _record(make_rt, lab_only)
    bad = check_recordings([p2], "continuous")
    assert not bad.ok and "small integer codes" in bad.problems[0]
