"""Milestone 2 tests against GENUINE human intracortical recordings (DANDI 000954).

These need the real files: `python -m brainos.datasets.fetch` (demo set, ~8.7 MiB).
They are skipped — loudly — if the files are absent. CI downloads them first.
"""

from __future__ import annotations

import asyncio
import json
import os
import time
from collections import Counter
from collections.abc import Iterator
from pathlib import Path

import numpy as np
import pytest
from fastapi.testclient import TestClient

pytest.importorskip("pynwb")

from brainos.adapters.nwb import (
    DecoderLeakageError,
    NWBUnitsSource,
    device_id_for,
    load,
)
from brainos.adapters.simulated import OperatorIntentSource
from brainos.contracts import Capability, parse_envelope
from brainos.contracts.protocol import AppStatus, ErrorCode, RuntimeState
from brainos.datasets import manifest, verify_file
from brainos.datasets.fetch import DEMO_FILES
from brainos.decoding.ridge import RidgeDecoder, evaluate, fit
from brainos.runtime import DeviceRegistry, Recorder, Runtime, RuntimeCommandError
from brainos.server import create_app

from .conftest import make_settings, subscribe
from .helpers import drain, events, wait_for

REPO = Path(__file__).resolve().parents[2]
DATA = Path(os.environ.get("BRAINOS_TEST_DATASETS", REPO / "data" / "datasets" / "dandi-000954"))
TRAIN_FILE, EVAL_FILE = DATA / DEMO_FILES[0], DATA / DEMO_FILES[1]

pytestmark = pytest.mark.skipif(
    not (TRAIN_FILE.exists() and EVAL_FILE.exists()),
    reason=f"real FALCON H1 files not found in {DATA}; run `python -m brainos.datasets.fetch`",
)
TRAIN_ID, EVAL_ID = device_id_for(TRAIN_FILE), device_id_for(EVAL_FILE)
DIMS = ["tx", "ty", "tz", "rx", "g1", "g2", "g3"]


def reference_counts(path: Path) -> np.ndarray:
    """Independent re-implementation of FALCON's bin_units for H1 (np.histogram per unit)."""
    from pynwb import NWBHDF5IO

    with NWBHDF5IO(str(path), "r") as io:
        f = io.read()
        k = f.acquisition["OpenLoopKinematics"]
        ts = k.offset + np.arange(k.data.shape[0]) * k.rate  # authors' timestamp rule
        edges = np.concatenate([[ts[0] - 0.02], ts])
        return np.stack(
            [
                np.histogram(np.asarray(f.units["spike_times"][i]), bins=edges)[0]
                for i in range(len(f.units.id))
            ],
            axis=1,
        )


@pytest.fixture(scope="module")
def demo_model(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Train on TRAIN_FILE (block 1), evaluate on EVAL_FILE (block 2); save like the CLI does."""
    a, b = load(TRAIN_FILE), load(EVAL_FILE)
    ca = np.concatenate([c for _, c in a.iter_counts()]).astype(float)
    cb = np.concatenate([c for _, c in b.iter_counts()]).astype(float)
    assert a.behavior is not None and b.behavior is not None
    sha_a, sha_b = verify_file(TRAIN_FILE).sha256, verify_file(EVAL_FILE).sha256
    model = fit(
        ca,
        a.behavior.values,
        a.behavior.valid,
        dims=a.behavior.dims,
        unit=a.behavior.unit,
        bin_ms=20.0,
        space="falcon_h1_7dof",
        training={"file": TRAIN_FILE.name, "sha256": sha_a, "session": "19250108T110520"},
    )
    res = evaluate(model, cb, b.behavior.values, b.behavior.valid, skip_first=12)
    model.evaluations.append({"file": EVAL_FILE.name, "sha256": sha_b, **res})
    models = tmp_path_factory.mktemp("models")
    model.save(models / f"{model.model_id}.json")
    return models


@pytest.fixture
def data_root(tmp_path: Path, demo_model: Path) -> Path:
    """A data dir whose datasets/ points at the real files and models/ holds the demo model."""
    root = tmp_path / "data"
    (root / "datasets").mkdir(parents=True)
    for f in (TRAIN_FILE, EVAL_FILE):
        (root / "datasets" / f.name).symlink_to(f)
    (root / "models").symlink_to(demo_model, target_is_directory=True)
    return root


@pytest.fixture
async def rt(data_root: Path) -> Iterator[Runtime]:  # type: ignore[misc]
    reg = DeviceRegistry(OperatorIntentSource(), data_root / "recordings", seed=1)
    runtime = Runtime(reg, Recorder(data_root / "recordings"))
    yield runtime
    await runtime.shutdown()


# ------------------------------------------------------------- loading & integrity


def test_files_are_the_published_dandi_assets() -> None:
    """M2-AT-1: checksums match the pinned DANDI 000954 manifest."""
    m = manifest("falcon-h1")
    for f in (TRAIN_FILE, EVAL_FILE):
        v = verify_file(f)
        assert v.verified and v.manifest is m and v.asset is not None
        assert v.asset.filename == f.name


def test_metadata_extracted_and_gaps_reported() -> None:
    """M2-AT-2/3: real metadata, explicit notes for corrections and missing metadata."""
    rec = load(TRAIN_FILE)
    assert rec.species == "Homo sapiens"
    assert rec.channel_count == 176 and rec.n_bins == 12233
    assert rec.bin_s == pytest.approx(0.02) and rec.duration_s == pytest.approx(244.66)
    assert (
        rec.behavior is not None and rec.behavior.dims == DIMS and rec.behavior.unit == "arbitrary"
    )
    assert rec.profile == "falcon-h1"
    notes = " ".join(rec.notes)
    assert "Timebase correction" in notes and "No electrode table" in notes and "eval_mask" in notes


def test_binning_matches_independent_reference() -> None:
    """M2-AT-4: counts are bit-identical to the dataset authors' binning definition."""
    rec = load(EVAL_FILE)
    mine = np.concatenate([c for _, c in rec.iter_counts(chunk=333)])
    ref = reference_counts(EVAL_FILE)
    assert mine.shape == ref.shape
    assert np.array_equal(mine, ref)


# ------------------------------------------------------------- through the runtime


async def test_real_data_flows_through_runtime_with_correct_provenance(rt: Runtime) -> None:
    """M2-AT-6/7: genuine samples pass through the unchanged runtime, labelled correctly."""
    sub = subscribe(rt)
    await rt.connect(TRAIN_ID)
    await rt.set_playback_speed(16.0)
    await wait_for(lambda: rt.diagnostics.totals["features.binned"] >= 300, timeout=10)
    evs = [parse_envelope(e) for e in events(drain(sub))]
    feats = [e for e in evs if e.event_type == "features.binned"]
    behav = [e for e in evs if e.event_type == "behavior.sample"]
    assert feats and behav
    assert [e.seq for e in evs] == sorted(e.seq for e in evs)
    ts = [e.device_timestamp_ns for e in feats]
    assert ts == sorted(ts) and ts[1] - ts[0] == 20_000_000
    origin = "dandi:000954/sub-HumanPitt-held-in-calib/" + TRAIN_FILE.name
    for e in feats:
        assert e.provenance.kind == "processed_feature" and e.provenance.synthetic is False
        assert e.provenance.replayed is True and e.provenance.origin == origin
    for e in behav:
        assert e.provenance.kind == "behavioral_label"
    # no intents of any kind come from a file with no attached decoder
    assert not [e for e in evs if e.event_type.startswith("intent.")]
    # end-to-end data integrity: payload counts == file counts
    rec = load(TRAIN_FILE)
    first = {e.payload.bin_index: e.payload.counts for e in feats}  # type: ignore[union-attr]
    expected = rec.counts(0, 50)
    for i in range(50):
        assert first[i] == expected[i].tolist()
    assert rt.diagnostics.validation_errors == 0 and rt.diagnostics.decode_errors == 0


async def test_decoded_intents_only_on_held_out_block(rt: Runtime) -> None:
    """M2-AT-11: decoder attached only to the evaluated block, emits decoded_intent + model_id."""
    assert Capability.KINEMATIC_INTENT not in rt.registry.describe(TRAIN_ID).capability_set
    assert Capability.KINEMATIC_INTENT in rt.registry.describe(EVAL_ID).capability_set
    sub = subscribe(rt)
    await rt.connect(EVAL_ID)
    await rt.set_playback_speed(16.0)
    await wait_for(lambda: rt.diagnostics.totals["intent.kinematics"] >= 50, timeout=10)
    dec = [parse_envelope(e) for e in events(drain(sub), "intent.kinematics")]
    assert all(e.provenance.kind == "decoded_intent" and e.provenance.model_id for e in dec)
    assert all(e.payload.space == "falcon_h1_7dof" for e in dec)  # type: ignore[union-attr]
    # online (streamed through the runtime) == offline prediction
    model = RidgeDecoder.load(next(rt.registry.catalog.models_dir.glob("*.json")))
    offline = model.predict_counts(load(EVAL_FILE).counts(0, 50).astype(float))
    online = np.array([e.payload.values for e in dec[:50]])  # type: ignore[union-attr]
    assert np.allclose(online, offline, atol=1e-9)


def test_leakage_guard_refuses_training_session(demo_model: Path) -> None:
    """M2-AT-11: a model may never decode its own training session (incl. minival subsets)."""
    model = RidgeDecoder.load(next(demo_model.glob("*.json")))
    with pytest.raises(DecoderLeakageError, match="trained on session"):
        NWBUnitsSource(TRAIN_FILE, decoder=model)


async def test_playback_controls(rt: Runtime) -> None:
    """M2-AT-8: start, pause, resume, speed, status, stop."""
    await rt.connect(TRAIN_ID)
    st = rt.playback_status()
    assert st.duration_s == pytest.approx(244.66) and st.speed == 1.0
    await asyncio.sleep(0.4)
    p1 = rt.playback_status().position_s
    assert 0.2 < p1 < 0.6
    await rt.pause()
    paused_at = rt.playback_status().position_s
    await asyncio.sleep(0.3)
    assert rt.playback_status().position_s == pytest.approx(paused_at, abs=0.03)
    assert rt.playback_status().paused
    await rt.resume()
    await rt.set_playback_speed(8.0)
    t0, p0 = time.monotonic(), rt.playback_status().position_s
    await asyncio.sleep(0.5)
    rate = (rt.playback_status().position_s - p0) / (time.monotonic() - t0)
    assert 6.0 < rate < 9.0  # ~8 s of recording per second
    snap = await rt.disconnect()  # stop
    assert snap.state is RuntimeState.IDLE
    with pytest.raises(RuntimeCommandError) as info:
        rt.playback_status()
    assert info.value.code is ErrorCode.INVALID_STATE


async def test_playback_unsupported_on_live_simulated_device(rt: Runtime) -> None:
    await rt.connect("sim-a")
    with pytest.raises(RuntimeCommandError) as info:
        await rt.set_playback_speed(2.0)
    assert info.value.code is ErrorCode.UNSUPPORTED_OPERATION


async def test_switching_real_and_simulated_sources(rt: Runtime) -> None:
    """M2-AT-9: NWB -> sim -> NWB; the board-like app is suspended on NWB, active on sim."""
    board = subscribe(
        rt, required=[Capability.SELECTION], optional=[Capability.POINTER_INTENT], app_id="board"
    )
    await rt.connect(TRAIN_ID)
    assert board.negotiation.status is AppStatus.SUSPENDED
    await rt.switch("sim-a")
    assert board.negotiation.status is AppStatus.ACTIVE
    await wait_for(lambda: rt.diagnostics.totals["intent.pointer"] > 5)
    await rt.switch(EVAL_ID)
    assert board.negotiation.status is AppStatus.SUSPENDED
    await rt.set_playback_speed(8.0)
    n = rt.diagnostics.totals["features.binned"]
    await wait_for(lambda: rt.diagnostics.totals["features.binned"] > n + 20)
    sw = rt.diagnostics_snapshot().switches
    assert [s.to_device for s in sw] == ["sim-a", EVAL_ID]
    # the board never received a single neural/behavior/decoded event
    assert {e["event_type"] for e in events(drain(board))} <= {"intent.pointer", "intent.selection"}


async def test_real_time_rate_at_1x(rt: Runtime) -> None:
    """M2-AT-13: at 1x, bins are delivered at the recording's 50 Hz (±10%)."""
    await rt.connect(TRAIN_ID)
    await asyncio.sleep(0.3)
    n0, t0 = rt.diagnostics.totals["features.binned"], time.monotonic()
    await asyncio.sleep(1.5)
    rate = (rt.diagnostics.totals["features.binned"] - n0) / (time.monotonic() - t0)
    assert 45 <= rate <= 55


# ----------------------------------------------------------------- server & SDK


def test_rest_source_metadata_and_datasets(data_root: Path, tmp_path: Path) -> None:
    """M2-AT-2/12: provenance & channel metadata over REST; sims have none."""
    with TestClient(create_app(make_settings(tmp_path, data_dir=data_root))) as c:
        meta = c.get(f"/api/v1/devices/{EVAL_ID}/source").json()
        assert meta["label"] == "Recorded Human Intracranial Data — Offline Replay"
        assert meta["live"] is False and meta["file"]["verified"] is True
        assert meta["dataset"]["dandiset"] == "000954" and meta["dataset"]["license"] == "CC-BY-4.0"
        assert meta["species"] == "Homo sapiens" and meta["channel_count"] == 176
        assert len(meta["channels"]) == 176 and meta["channels"][0]["electrode"] is None
        assert meta["decoder"]["evaluated_r2"] is not None
        assert c.get("/api/v1/devices/sim-a/source").status_code == 404
        ds = c.get("/api/v1/datasets").json()
        assert ds["nwb_support"] and sorted(ds["devices"]) == sorted([TRAIN_ID, EVAL_ID])
        c.post("/api/v1/runtime/connect", json={"device_id": TRAIN_ID})
        r = c.post("/api/v1/runtime/playback", json={"speed": 4})
        assert r.status_code == 200 and r.json()["speed"] == 4
        assert c.post("/api/v1/runtime/playback", json={"speed": 1000}).status_code == 422
        assert c.post("/api/v1/sim/select").status_code == 409  # replay is not a simulator


async def test_python_sdk_receives_real_data(data_root: Path, tmp_path: Path) -> None:
    """M2-AT-10: the Python SDK negotiates the new capabilities and validates events."""
    import socket
    import threading

    import uvicorn

    from brainos.sdk import EventStream, RuntimeClient, is_event

    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    server = uvicorn.Server(
        uvicorn.Config(
            create_app(make_settings(tmp_path, data_dir=data_root)), port=port, log_level="warning"
        )
    )
    th = threading.Thread(target=server.run, daemon=True)
    th.start()
    while not server.started:
        await asyncio.sleep(0.05)
    base = f"http://127.0.0.1:{port}"
    try:
        async with RuntimeClient(base) as rc:
            assert any(d.device_id == EVAL_ID and not d.synthetic for d in await rc.devices())
            await rc.connect(EVAL_ID)
            async with await EventStream.connect(
                app_id="research",
                app_name="research",
                optional=["neural_features", "behavior", "kinematic_intent"],
                base_url=base,
            ) as stream:
                assert set(stream.negotiation.granted) == {
                    "neural_features",
                    "behavior",
                    "kinematic_intent",
                }
                seen: Counter[str] = Counter()

                async def consume() -> None:
                    async for item in stream:
                        if is_event(item):
                            seen[item.event_type] += 1
                            if min(seen.values()) >= 10 and len(seen) == 3:
                                return

                await asyncio.wait_for(consume(), 10)
                assert stream.stats.invalid == 0 and stream.stats.out_of_order == 0
            # a 1.0-era app that never asked for the new capabilities receives none of them
            async with await EventStream.connect(
                app_id="legacy",
                app_name="legacy",
                optional=["selection", "pointer_intent"],
                base_url=base,
            ) as legacy:
                assert legacy.negotiation.granted == []
    finally:
        server.should_exit = True
        th.join(timeout=10)


def test_model_json_is_plain_data(demo_model: Path) -> None:
    raw = json.loads(next(demo_model.glob("*.json")).read_text())
    assert raw["training"]["session"] == "19250108T110520"
    assert raw["evaluations"][0]["file"] == EVAL_FILE.name
