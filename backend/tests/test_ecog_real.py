"""Milestone 5 / workstream B against GENUINE human ECoG (AJILE12, DANDI 000055, sub-07).

These need the pinned demo slices (~157 MiB, streamed from DANDI with HTTP range requests):
    python -m concord.datasets.fetch ajile12
They are skipped — loudly — if the extracts are absent. CI fetches them first.

Nothing here is hardware or human-in-the-loop validation: it is offline replay of a recording
made during clinical monitoring (docs/VALIDATION_LEVELS.md).
"""

from __future__ import annotations

import asyncio
import importlib.util
import os
import shutil
import sys
from collections.abc import AsyncIterator, Iterator
from pathlib import Path
from types import ModuleType
from typing import Any

import numpy as np
import pytest

pytest.importorskip("pynwb")
pytest.importorskip("scipy")

from concord.adapters.nwb import NWBElectricalSource, device_id_for, verify_electrical
from concord.adapters.nwb.source import DecoderLeakageError
from concord.contracts import parse_envelope
from concord.contracts.protocol import ErrorCode, Modality
from concord.datasets import manifest
from concord.decoding import evaluate_ecog as ev
from concord.decoding.lda import LDAClassifier

from .conftest import free_port, make_settings, serve, subscribe
from .helpers import drain, events, link_or_copy, wait_for

REPO = Path(__file__).resolve().parents[2]
DATA = Path(os.environ.get("CONCORD_TEST_ECOG", REPO / "data" / "datasets" / "dandi-000055"))
FALCON = Path(os.environ.get("CONCORD_TEST_DATASETS", REPO / "data" / "datasets" / "dandi-000954"))
M = manifest("ajile12")
TRAIN_SLICE = next(s for s in M.slices if s.demo and s.role == "train")
TEST_SLICE = next(s for s in M.slices if s.demo and s.role == "test")
TRAIN_FILE, TEST_FILE = DATA / TRAIN_SLICE.filename, DATA / TEST_SLICE.filename
TRAIN_ID, TEST_ID = device_id_for(TRAIN_FILE), device_id_for(TEST_FILE)
APP_DIR = Path(__file__).resolve().parents[1] / "examples" / "reference_app"

pytestmark = pytest.mark.skipif(
    not (TRAIN_FILE.exists() and TEST_FILE.exists()),
    reason=f"real AJILE12 ECoG extracts not found in {DATA}; run "
    "`python -m concord.datasets.fetch ajile12`",
)


@pytest.fixture(scope="module")
def slices() -> tuple[ev.SliceData, ev.SliceData]:
    return ev.load_slice(TRAIN_FILE), ev.load_slice(TEST_FILE)


@pytest.fixture(scope="module")
def demo_model(
    slices: tuple[ev.SliceData, ev.SliceData], tmp_path_factory: pytest.TempPathFactory
) -> tuple[LDAClassifier, dict[str, Any], Path]:
    """Train on the day-5 demo slice; score on the held-out day-6 demo slice."""
    train, test = slices
    model = ev.train([train])
    res = ev.evaluate(model, [test])
    model.evaluations.append({"split": "held-out session 6 (demo slices)", **res})
    models = tmp_path_factory.mktemp("models")
    model.save(models / f"{model.model_id}.json")
    return model, res, models


@pytest.fixture
def data_root(tmp_path: Path, demo_model: tuple[LDAClassifier, dict[str, Any], Path]) -> Path:
    root = tmp_path / "data"
    (root / "datasets").mkdir(parents=True)
    for f in (TRAIN_FILE, TEST_FILE):
        link_or_copy(root / "datasets" / f.name, f)
    link_or_copy(root / "models", demo_model[2])
    return root


@pytest.fixture
async def rt(data_root: Path) -> AsyncIterator[Any]:
    from concord.adapters.simulated import OperatorIntentSource
    from concord.runtime import DeviceRegistry, Recorder, Runtime

    reg = DeviceRegistry(OperatorIntentSource(), data_root / "recordings", seed=1)
    runtime = Runtime(reg, Recorder(data_root / "recordings"))
    yield runtime
    await runtime.shutdown()


# ------------------------------------------------------------- integrity & metadata


def test_extracts_are_the_pinned_slices_and_tampering_is_detected(tmp_path: Path) -> None:
    for f, s in ((TRAIN_FILE, TRAIN_SLICE), (TEST_FILE, TEST_SLICE)):
        v = verify_electrical(f)
        assert v.verified and v.slice == s and v.manifest is M
        assert v.asset is not None and v.asset.path == s.asset_path
        assert v.asset.sha256 == M.by_path(s.asset_path).sha256  # type: ignore[union-attr]
    import h5py

    bad = tmp_path / TEST_FILE.name
    shutil.copy(TEST_FILE, bad)
    with h5py.File(bad, "r+") as f:
        d = f["acquisition/ElectricalSeries/data"]
        d[1000, 3] = d[1000, 3] + 1.0  # one microvolt on one sample
    assert not verify_electrical(bad).verified
    src = NWBElectricalSource(bad)
    assert src.origin == f"file:{bad.name}" and src.modality is None  # no longer declared


def test_real_metadata_is_reported_as_the_file_states_it() -> None:
    src = NWBElectricalSource(TEST_FILE)
    rec = src.rec
    assert rec.fs == 500.0 and rec.channel_count == 64 and rec.n_samples == 337_500
    assert rec.unit == "uV" and rec.declared_unit == "volts" and rec.conversion == 1e-6
    assert rec.channel_labels == [f"RFGRID/{i}" for i in range(64)]
    assert rec.bad_channels == ["RFGRID/0"]
    assert {e.group_description for e in rec.electrodes} == {"Right Frontal ECoG grid"}
    assert rec.species == "Homo sapiens" and rec.subject_id == "07"
    assert rec.t0_s == pytest.approx(TEST_SLICE.samples[0] / 500.0)
    d = src.descriptor()
    assert d.modality is Modality.ECOG and d.invasive is True and d.synthetic is False
    assert d.display_name == "Recorded Human ECoG — Offline Replay"
    assert src.origin == "dandi:000055/sub-07/sub-07_ses-6_behavior+ecephys.nwb#t=47925-48600"
    meta = src.metadata()
    assert meta.signal is not None and meta.signal.line_hz == 60 and meta.signal.frame_samples == 50
    assert meta.signal.first_sample_index == TEST_SLICE.samples[0]
    assert meta.slice is not None and meta.slice.role == "test"
    assert meta.behavior is not None and len(meta.behavior.dims) == 18
    assert meta.behavior.unit == "arbitrary"
    tables = {i.table: i for i in meta.intervals}
    assert tables["reaches"].rows == 15 and tables["epochs"].rows >= 6
    notes = " ".join(meta.notes)
    for expected in ("de-identification", "conversion nan", "'unknown' for every electrode"):
        assert expected in notes, expected


def test_recording_site_mains_is_60_hz_as_declared() -> None:
    """The manifest's 60 Hz is measured, not assumed: the stored signal shows notch dips at
    60/120/180 Hz (the authors' upstream filtering), none at 50 Hz."""
    from scipy import signal as sps

    rec = NWBElectricalSource(TRAIN_FILE).rec
    x = rec.samples(0, 60_000)[:, [e.index for e in rec.electrodes if not e.bad]]
    f, pxx = sps.welch(x, fs=rec.fs, nperseg=2048, axis=0)
    m = pxx.mean(axis=1)

    def ratio(fq: float) -> float:
        i = int(np.argmin(np.abs(f - fq)))
        return float(m[i] / np.r_[m[i - 12 : i - 4], m[i + 4 : i + 12]].mean())

    assert ratio(60) < 0.3 and ratio(120) < 0.5 and ratio(180) < 0.6
    assert 0.7 < ratio(50) < 1.4


# ------------------------------------------------------------- through the runtime


async def test_real_ecog_flows_through_runtime_as_raw_signal(rt: Any) -> None:
    sub = subscribe(rt)
    await rt.connect(TEST_ID)
    assert rt.device.modality is Modality.ECOG and rt.device.invasive is True
    await rt.set_playback_speed(16.0)
    await wait_for(lambda: rt.diagnostics.totals["recording.frame"] >= 40, timeout=15)
    evs = [parse_envelope(e) for e in events(drain(sub))]
    frames = [e for e in evs if e.event_type == "recording.frame"]
    assert frames and [e for e in evs if e.event_type == "behavior.sample"]
    origin = "dandi:000055/sub-07/sub-07_ses-6_behavior+ecephys.nwb#t=47925-48600"
    for e in frames:
        assert e.provenance.kind == "raw_signal" and e.provenance.replayed is True
        assert e.provenance.synthetic is False and e.provenance.origin == origin
    # end-to-end integrity: µV in the events == stored values (conversion 1e-6 V)
    import h5py

    with h5py.File(TEST_FILE, "r") as f:
        stored = f["acquisition/ElectricalSeries/data"][: 50 * 20, :].astype(np.float64)
    first = frames[0].payload
    assert first.unit == "uV" and first.first_sample_index == TEST_SLICE.samples[0]  # type: ignore[union-attr]
    got = np.concatenate([np.array(e.payload.samples).T for e in frames[:20]])  # type: ignore[union-attr]
    assert np.array_equal(got, stored)
    assert frames[1].device_timestamp_ns - frames[0].device_timestamp_ns == 100_000_000  # type: ignore[operator]
    assert not [e for e in evs if e.event_type.startswith("intent.")]
    assert rt.diagnostics.validation_errors == 0 and rt.diagnostics.decode_errors == 0


async def test_pipeline_features_equal_the_offline_analysis(
    rt: Any, slices: tuple[ev.SliceData, ev.SliceData]
) -> None:
    """Train/deploy parity: the live pipeline computes exactly the features the evaluation
    used (same chain, source-declared 60 Hz mains, CAR without the bad electrode)."""
    from concord.runtime.pipeline import PipelineStartRequest

    sub = subscribe(rt)
    await rt.connect(TEST_ID)
    st = rt.start_pipeline(
        PipelineStartRequest(processing={"preset": "ecog_high_gamma", "bin_ms": 100})
    )
    assert st.stages == slices[1].stages
    assert "excluded as bad: RFGRID/0" in " ".join(st.stages)
    await rt.set_playback_speed(16.0)
    await wait_for(lambda: rt.diagnostics.totals["features.vector"] >= 60, timeout=20)
    feats = [parse_envelope(e) for e in events(drain(sub), "features.vector")]
    online = np.array([e.payload.values for e in feats[:60]])  # type: ignore[union-attr]
    assert np.allclose(online, slices[1].features[:60], rtol=1e-9, atol=1e-12)
    assert all(e.provenance.kind == "processed_feature" for e in feats)


async def test_decoder_online_equals_offline_and_beats_controls(
    rt: Any, demo_model: tuple[LDAClassifier, dict[str, Any], Path], slices: Any
) -> None:
    model, res, _ = demo_model
    print(
        f"\nECoG demo (train day 5 slice, held-out day 6 slice): balanced accuracy "
        f"{res['balanced_accuracy']:.3f} (time-shift null max "
        f"{res['control_time_shift_max_balanced_accuracy']:.3f}), AUC {res['auc']:.3f} "
        f"(null max {res['control_time_shift_max_auc']:.3f}), reaches "
        f"{res['reaches_detected']}/{res['reaches_scored']}"
    )
    assert res["balanced_accuracy"] > res["control_time_shift_max_balanced_accuracy"]
    assert res["auc"] > res["control_time_shift_max_auc"]
    from concord.runtime.pipeline import PipelineStartRequest

    sub = subscribe(rt)
    await rt.connect(TEST_ID)
    rt.start_pipeline(
        PipelineStartRequest(
            processing={"preset": "ecog_high_gamma", "bin_ms": 100}, model_id=model.model_id
        )
    )
    await rt.set_playback_speed(16.0)
    await wait_for(lambda: rt.diagnostics.totals["intent.kinematics"] >= 50, timeout=20)
    dec = [parse_envelope(e) for e in events(drain(sub), "intent.kinematics")]
    assert all(e.provenance.kind == "decoded_intent" for e in dec)
    assert {e.provenance.model_id for e in dec} == {model.model_id}
    online = np.array([e.payload.values for e in dec[:50]])  # type: ignore[union-attr]
    offline = model.predict_proba(slices[1].features[:50])
    assert np.allclose(online, offline, atol=1e-9)
    # without the router, nothing actionable reaches applications
    assert not [e for e in events(drain(sub)) if e["event_type"] in ("intent.selection",)]


# ------------------------------------------------------------- leakage & modality


async def test_model_is_refused_on_its_training_session(
    rt: Any, demo_model: tuple[LDAClassifier, dict[str, Any], Path], slices: Any
) -> None:
    from concord.runtime import RuntimeCommandError
    from concord.runtime.pipeline import PipelineError, PipelineStartRequest

    model = demo_model[0]
    with pytest.raises(DecoderLeakageError):
        ev.evaluate(model, [slices[0]])
    await rt.connect(TRAIN_ID)
    with pytest.raises((PipelineError, RuntimeCommandError)) as info:
        rt.start_pipeline(
            PipelineStartRequest(
                processing={"preset": "ecog_high_gamma", "bin_ms": 100},
                model_id=model.model_id,
                allow_cross_source=True,
            )
        )
    assert info.value.code is ErrorCode.INCOMPATIBLE_DECODER
    assert "training session 5" in info.value.message


async def test_modality_guards_on_real_streams(
    tmp_path: Path, data_root: Path, demo_model: tuple[LDAClassifier, dict[str, Any], Path]
) -> None:
    """ECoG model refused on intracortical spike counts; intracortical model refused on ECoG;
    an EEG-declared model refused on ECoG — even with the cross-source override."""
    from concord.adapters.simulated import OperatorIntentSource
    from concord.decoding.ridge import RidgeDecoder
    from concord.runtime import DeviceRegistry, Recorder, Runtime, RuntimeCommandError
    from concord.runtime.pipeline import PipelineError, PipelineStartRequest

    model = demo_model[0]
    models = data_root / "models"
    models.unlink()  # a private models dir: do not add models to the module's shared one
    models.mkdir()
    shutil.copy(demo_model[2] / f"{model.model_id}.json", models)
    eeg = LDAClassifier.from_dict({**model.__dict__, "model_id": "eeg-declared-lda-test"})
    eeg.input = {**model.input, "modality": "eeg"}
    eeg.save(models / f"{eeg.model_id}.json")
    falcon_file = FALCON / "sub-HumanPitt-held-in-calib_ses-19250108T110520.nwb"
    if not falcon_file.exists():
        pytest.skip(
            f"FALCON H1 demo files not found in {FALCON}; run `python -m concord.datasets.fetch`"
        )
    # A FALCON-shaped ridge model (weights are irrelevant: the guard refuses before decoding).
    # It declares no modality itself; it inherits "intracortical" from the FALCON manifest.
    n_ch, dims = 176, ["tx", "ty", "tz", "rx", "g1", "g2", "g3"]
    ridge = RidgeDecoder(
        model_id="falcon-h1-ridge-guardtest",
        space="falcon_h1_7dof",
        quantity="velocity",
        dims=dims,
        unit="arbitrary",
        bin_ms=20.0,
        tau_ms=240.0,
        kernel=[1.0],
        x_mean=[0.0] * n_ch,
        x_std=[1.0] * n_ch,
        weights=[[0.0] * len(dims) for _ in range(n_ch)],
        intercept=[0.0] * len(dims),
        alpha=1.0,
        training={"dataset": "DANDI:000954", "session": "19250108T110520"},
        source={"identity": "dandi:000954:HumanPitt"},
    )
    assert "modality" not in ridge.input
    ridge.save(models / f"{ridge.model_id}.json")
    link_or_copy(data_root / "datasets" / falcon_file.name, falcon_file)
    reg = DeviceRegistry(OperatorIntentSource(), data_root / "recordings", seed=1)
    rt = Runtime(reg, Recorder(data_root / "recordings"))
    ecog_spec = {"preset": "ecog_high_gamma", "bin_ms": 100}

    async def refused(device: str, processing: dict[str, Any], model_id: str) -> str:
        await rt.connect(device)
        with pytest.raises((PipelineError, RuntimeCommandError)) as info:
            rt.start_pipeline(
                PipelineStartRequest(
                    processing=processing, model_id=model_id, allow_cross_source=True
                )
            )
        await rt.disconnect()
        assert info.value.code is ErrorCode.INCOMPATIBLE_DECODER
        return str(info.value.message)

    try:
        falcon_id = device_id_for(falcon_file)
        assert reg.describe(falcon_id).modality is Modality.INTRACORTICAL
        msg = await refused(falcon_id, {"preset": "features_passthrough"}, model.model_id)
        assert "trained on ecog recordings; this source is intracortical" in msg
        msg = await refused(TEST_ID, ecog_spec, ridge.model_id)
        assert "trained on intracortical recordings; this source is ecog" in msg
        msg = await refused(TEST_ID, ecog_spec, eeg.model_id)
        assert "trained on eeg recordings; this source is ecog" in msg
    finally:
        await rt.shutdown()


# ------------------------------------------------------------- same app, new modality


def _load_app(name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, APP_DIR / f"{name}.py")
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def ecog_server(tmp_path: Path, data_root: Path) -> Iterator[str]:
    from concord.server import create_app

    port = free_port()
    yield from serve(create_app(make_settings(tmp_path, port=port, data_dir=data_root)), port)


async def test_unchanged_menu_app_gets_decoded_commands_from_ecog_after_authorization(
    ecog_server: str, demo_model: tuple[LDAClassifier, dict[str, Any], Path]
) -> None:
    """The SDK-only reference menu app — the same file that runs on the synthetic EEG plugin
    (test_m4_demo) and synthetic MI source (test_control_e2e) — receives decoded selection
    commands from real human ECoG (offline replay of a held-out day) only after the operator
    authorizes it, with decoded_intent provenance and the model id; nothing after disconnect."""
    import httpx

    from concord.sdk import ConcordError, RuntimeClient

    model = demo_model[0]
    menu_mod = _load_app("menu_app")
    menu, stop = menu_mod.MenuApp(), asyncio.Event()
    runner = asyncio.create_task(menu_mod.run(menu, ecog_server, stop))
    rules = [
        {
            "output": "move",
            "action": "primary",
            "threshold": 0.8,
            "hold_ms": 200,
            "refractory_ms": 1500,
        },
    ]
    try:
        async with RuntimeClient(ecog_server) as op:
            devs = {d.device_id: d for d in await op.devices()}
            assert devs[TEST_ID].modality is not None and devs[TEST_ID].modality.value == "ecog"
            await op.connect(TEST_ID)
            await wait_for(lambda: menu.status == "suspended", timeout=10)
            # a classifier cannot drive a pointer (refused, as on every other source)
            with pytest.raises(ConcordError) as exc:
                await op.start_pipeline(
                    "ecog_high_gamma",
                    model_id=model.model_id,
                    router={"enabled": True, "x_dim": "rest", "y_dim": "move"},
                    bin_ms=100,
                )
            assert exc.value.code in ("incompatible_decoder", "capability_unsupported")
            await op.start_pipeline(
                "ecog_high_gamma",
                model_id=model.model_id,
                router={"enabled": True, "discrete": rules},
                bin_ms=100,
            )
            async with httpx.AsyncClient(base_url=ecog_server) as h:
                r = await h.post("/api/v1/runtime/playback", json={"speed": 8})
                assert r.status_code == 200
            await wait_for(lambda: menu.waiting_for_authorization, timeout=15)
            await asyncio.sleep(6.0)  # ~48 s of recording: the decoder fires (P(move) > 0.8)
            st = await op.pipeline()
            assert st["counters"]["selections_out"] >= 1, st["counters"]
            assert sum(menu.actions.values()) == 0, "an unauthorized app received a command"

            await op.authorize_app("reference-menu", ["selection"])
            await wait_for(lambda: sum(menu.actions.values()) >= 2, timeout=60)
            assert ("decoded_intent", model.model_id) in menu.provenance
            assert set(menu.actions) == {"primary"}
            print(f"\nmenu app on real ECoG: {menu.summary()}")

            await op.disconnect()
            await wait_for(lambda: bool(menu.stops), timeout=5)
            n = sum(menu.actions.values())
            await asyncio.sleep(1.5)
            assert sum(menu.actions.values()) == n
    finally:
        stop.set()
        await runner
