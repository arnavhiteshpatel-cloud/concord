"""Milestone 5 (P0) tests against GENUINE human intracortical data: the Singer-Clark et al.
cursor + click dataset (participant T15, Dryad doi:10.5061/dryad.prr4xgxzq, CC0).

Needs the demo subset: ``python -m concord.datasets.dryad`` (day 468 blocks 0-3, ~90 MiB;
Dryad requires an API token, see the module docstring). Skipped -- loudly -- when the files are
absent, unless ``CONCORD_REQUIRE_T15=1`` (set in CI when Dryad credentials are configured), in
which case missing files fail the run.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

import numpy as np
import pytest

pytest.importorskip("scipy")

from concord.adapters.cursorclick.reader import load
from concord.adapters.cursorclick.source import (
    HISTORICAL_CLICK,
    HISTORICAL_VELOCITY,
    T15CursorClickSource,
    device_id_for,
)
from concord.adapters.simulated import OperatorIntentSource
from concord.contracts import Capability, parse_envelope
from concord.contracts.protocol import Modality
from concord.datasets.dryad import manifest, verify_file
from concord.decoding import click as clickdec
from concord.decoding import kalman
from concord.runtime import DeviceRegistry, Recorder, Runtime

from .conftest import subscribe
from .helpers import drain, events, wait_for

REPO = Path(__file__).resolve().parents[2]
DATA = Path(os.environ.get("CONCORD_TEST_T15", REPO / "data" / "datasets" / "dryad-prr4xgxzq"))
NAMES = [f.filename for f in manifest("t15-cursor-click").blocks(468) if f.block in (0, 1, 2, 3)]
FILES = [DATA / n for n in NAMES]
CAL, GRID = FILES[:3], FILES[3]
PRESENT = all(f.exists() for f in FILES)

if not PRESENT and os.environ.get("CONCORD_REQUIRE_T15") == "1":
    raise RuntimeError(f"CONCORD_REQUIRE_T15=1 but the T15 demo files are missing in {DATA}")

pytestmark = pytest.mark.skipif(
    not PRESENT,
    reason=f"T15 cursor+click files not found in {DATA}; run `python -m concord.datasets.dryad`",
)


@pytest.fixture(scope="module")
def grid() -> object:
    return load(GRID)


# ----------------------------------------------------------------- files & reader


def test_files_are_the_pinned_dryad_files() -> None:
    for f in FILES:
        v = verify_file(f)
        assert v.verified, f
        assert v.manifest is not None and v.manifest.doi == "10.5061/dryad.prr4xgxzq"
        assert v.manifest.license == "CC0-1.0"


def test_reader_matches_the_published_layout(grid: object) -> None:
    b = load(GRID)
    assert (b.participant, b.day, b.block, b.task) == ("t15", 468, 3, "grid_evaluation")
    assert b.channel_count == 256 and b.n_bins > 17_000
    assert sorted(set(b.array_labels)) == ["4", "55b", "d6v", "v6v"]
    assert all(b.array_labels.count(a) == 64 for a in set(b.array_labels))
    assert b.fully_neural and b.has_click
    assert b.grid_rows == 14 and b.cell_half() == pytest.approx(0.92 / 14 / 2)


def test_trial_structure_matches_the_authors_scoring() -> None:
    """The authors' grid scoring: every trial ends with a click in the bin before the next
    trial start; the cursor is on the cued cell at most trial-ending clicks (the session's
    success rate). A few clicks end no trial (the task ignored them); they stay in the data."""
    b = load(GRID)
    clicks = set(b.click_bins().tolist())
    ends = b.trial_start_bin[1:] - 1
    assert set(ends.tolist()) <= clicks
    assert len(clicks) - len(ends) <= 0.1 * len(ends)
    on = b.on_target()[ends]
    assert 0.85 < on.mean() <= 1.0  # recorded success rate of the online session
    assert np.min(np.diff(sorted(clicks))) >= 100  # >= 1 s between clicks


def test_historical_velocity_integrates_to_the_recorded_cursor_per_trial() -> None:
    """The recorded decoder output (units/s) integrated over each trial reproduces the
    recorded cursor displacement closely (the display loop updates ~every 20 ms, so not
    exactly), and anchored per trial it reproduces the session's selections."""
    b = load(GRID)
    integ = np.vstack([np.zeros((1, 2)), np.cumsum(b.cursor_decoder, axis=0) * 0.01])
    starts = b.trial_start_bin
    errs, hits = [], []
    for k in range(len(starts) - 1):
        s, e = int(starts[k]), int(starts[k + 1] - 1)
        disp = b.cursor[e] - b.cursor[s]
        pred = integ[e + 1] - integ[s + 1]
        errs.append(np.linalg.norm(disp - pred))
        hits.append(bool(np.all(np.abs(b.cursor[s] + pred - b.target[e]) < b.cell_half())))
    assert np.median(errs) < 0.25 * 2 * (b.cell_half() or 0)  # well under a quarter cell
    assert abs(np.mean(hits) - b.on_target()[b.trial_start_bin[1:] - 1].mean()) < 0.05


# ----------------------------------------------------------------- source & runtime


def test_descriptor_declares_modality_streams_and_historical_decoders() -> None:
    src = T15CursorClickSource(GRID)
    d = src.descriptor()
    assert d.device_id == device_id_for(src.block) == "t15:day00468-block03-grid-evaluation"
    assert d.modality is Modality.INTRACORTICAL and d.invasive is True and not d.synthetic
    caps = {c.capability: c.params for c in d.capabilities}
    streams = caps[Capability.NEURAL_FEATURES]["streams"]
    assert [s["feature"] for s in streams] == ["threshold_crossing_count", "spike_band_power"]
    decs = caps[Capability.KINEMATIC_INTENT]["decoders"]
    assert {x["model_id"] for x in decs} == {HISTORICAL_VELOCITY, HISTORICAL_CLICK}
    assert all(x["model_origin"] == "historical" for x in decs)
    vel = next(x for x in decs if x["model_id"] == HISTORICAL_VELOCITY)
    assert vel["y_axis"] == "up"  # dataset frame; the router must invert y for the pointer
    assert "SHA-256 verified" in d.description and "Offline replay" in d.description
    # no command capability: recorded data never becomes a command by itself
    assert not d.capability_set & {Capability.POINTER_INTENT, Capability.SELECTION}


def test_records_validate_and_label_historical_outputs() -> None:
    src = T15CursorClickSource(GRID)
    recs = []
    for r in src.records():
        recs.append(r)
        if len(recs) > 400:
            break
    kinds: dict[str, set[str]] = {}
    for i, r in enumerate(recs):
        env = {
            "schema_version": "1.4",
            "session_id": "ses_t15test",
            "device_id": "t15:day00468-block03",
            "seq": i,
            "timestamp_ns": 1,
            "capability": "neural_features",
            **r.envelope,
            "quality": r.envelope["quality"].model_dump(),
            "provenance": r.envelope["provenance"].model_dump(),
        }
        from concord.contracts.capabilities import EVENT_CAPABILITY, EventType

        env["capability"] = EVENT_CAPABILITY[EventType(env["event_type"])].value
        ev = parse_envelope(env)
        kinds.setdefault(ev.event_type, set()).add(ev.provenance.kind)
        if ev.event_type == "intent.kinematics":
            assert ev.provenance.model_origin == "historical" and ev.provenance.replayed
            assert ev.provenance.model_id in (HISTORICAL_VELOCITY, HISTORICAL_CLICK)
    assert kinds["features.binned"] == {"processed_feature"}
    assert kinds["features.vector"] == {"processed_feature"}
    assert kinds["behavior.sample"] == {"behavioral_label"}
    assert kinds["intent.kinematics"] == {"decoded_intent"}


@pytest.fixture
async def rt(tmp_path: Path) -> Iterator[Runtime]:  # type: ignore[misc]
    root = tmp_path / "data"
    (root / "datasets").mkdir(parents=True)
    for f in FILES:
        (root / "datasets" / f.name).symlink_to(f)
    reg = DeviceRegistry(OperatorIntentSource(), root / "recordings", seed=1)
    runtime = Runtime(reg, Recorder(root / "recordings"))
    yield runtime
    await runtime.shutdown()


async def test_block_replays_through_the_runtime(rt: Runtime) -> None:
    ids = [d.device_id for d in rt.registry.list() if d.device_id.startswith("t15:")]
    assert len(ids) == 4
    gid = "t15:day00468-block03-grid-evaluation"
    sub = subscribe(rt)
    await rt.connect(gid)
    await rt.set_playback_speed(16.0)
    await wait_for(lambda: rt.diagnostics.totals["features.vector"] >= 200, timeout=15)
    evs = [parse_envelope(e) for e in events(drain(sub))]
    tx = [e for e in evs if e.event_type == "features.binned"]
    sbp = [e for e in evs if e.event_type == "features.vector"]
    b = load(GRID)
    for e in tx[:100]:
        i = e.payload.bin_index  # type: ignore[union-attr]
        assert e.payload.counts == b.tx[i].tolist()  # type: ignore[union-attr]
    for e in sbp[:100]:
        i = e.payload.bin_index  # type: ignore[union-attr]
        assert np.allclose(e.payload.values, b.sbp[i])  # type: ignore[union-attr]
    # both feature streams carry identical bin-end times (a decoder joins them per bin)
    assert {e.device_timestamp_ns for e in tx[:100]} == {e.device_timestamp_ns for e in sbp[:100]}
    origin = "dryad:10.5061/dryad.prr4xgxzq/" + GRID.name
    data = [e for e in evs if e.provenance.kind != "runtime"]  # device.status, control.state
    assert data and all(e.provenance.origin == origin and e.provenance.replayed for e in data)
    assert not [e for e in evs if e.event_type in ("intent.pointer", "intent.selection")]
    assert rt.diagnostics.validation_errors == 0 and rt.diagnostics.decode_errors == 0


# ----------------------------------------------------------------- Concord decoders


def _intention(b: object) -> np.ndarray:
    from concord.evaluation.cursorclick import intention_labels

    return intention_labels(b)  # type: ignore[arg-type]


def test_kalman_and_click_decoders_on_held_out_block() -> None:
    """Train on calibration blocks 0-2 only; decode grid block 3 (recorded later).

    Thresholds are loose floors well above controls; the measured values are reported by
    ``scripts/eval_cursorclick.py`` (docs/CURSOR_CLICK.md), not asserted here."""
    from concord.adapters.cursorclick.source import neural_streams

    cal = [load(f) for f in CAL]
    g = load(GRID)
    inputs = neural_streams(g)
    feats = [np.hstack([b.tx, b.sbp]).astype(np.float64) for b in cal]
    model = kalman.fit(
        feats,
        [_intention(b) for b in cal],
        inputs=inputs,
        transforms=["identity", "log1p"],
        smoothing_tau_ms=30.0,
        shrinkage=0.9,
        dims=["vx", "vy"],
        unit="screen_height/s",
        space="t15_screen",
    )
    x = np.hstack([g.tx, g.sbp]).astype(np.float64)
    pred = model.predict(x)
    y = _intention(g)
    r2 = 1 - ((pred - y) ** 2).sum() / ((y - y.mean(0)) ** 2).sum()
    shifted = model.predict(np.roll(x, len(x) // 2, axis=0))
    r2_shift = 1 - ((shifted - y) ** 2).sum() / ((y - y.mean(0)) ** 2).sum()
    assert r2 > 0.3 and r2_shift < 0.05, (r2, r2_shift)
    # streaming == offline
    s = model.streaming()
    online = np.array([s.step(x[i]) for i in range(300)])
    assert np.allclose(online, pred[:300], atol=1e-9)
    assert s.covariance().shape == (2, 2)
    # click: P(click) is higher while the cursor is on the target than while moving
    c = clickdec.fit(
        feats,
        [b.on_target().astype(float) for b in cal],
        inputs=inputs,
        transforms=["identity", "log1p"],
        smoothing_tau_ms=100.0,
        l2=1000.0,
        space="t15_screen",
    )
    p = c.predict(x)[:, 0]
    on = g.on_target()
    assert p[on].mean() > p[~on].mean() + 0.2
