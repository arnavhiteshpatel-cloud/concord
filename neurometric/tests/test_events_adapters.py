"""Input conformance suite: canonical events, ordering, adapters, Concord import, round trips."""
from pathlib import Path

import numpy as np
import pytest

from neurometric.adapters.concord import ConcordImportError, import_recording
from neurometric.adapters.sessions import events_to_pointing_trials, replay, step_to_events
from neurometric.events.model import (EventKind, EventValidationError, InputEvent, Modality,
                                      check_stream, merge_streams, validate_event)
from neurometric.metrics.pointing import PointingTrials, trial_metrics
from neurometric.simulator.decoder import PROFILES
from neurometric.simulator.engine import Simulation
from neurometric.users.models import UserParams

FIX = Path(__file__).parent / "fixtures" / "concord"


def ev(t, kind=EventKind.POINTER_MOVE, stream="s1", seq=0, **kw):
    base = dict(t_ms=t, kind=kind, session_id="ses_x", stream_id=stream, modality=Modality.MOUSE,
                seq=seq)
    if kind in (EventKind.POINTER_MOVE, EventKind.CLICK):
        base.update(x=1.0, y=2.0)
    base.update(kw)
    return InputEvent(**base)


class TestValidation:
    def test_valid_move(self):
        validate_event(ev(0.0))

    @pytest.mark.parametrize("bad", [
        dict(t_ms=-1.0), dict(t_ms=float("nan")), dict(x=None), dict(x=float("inf")),
    ])
    def test_invalid_pointer(self, bad):
        with pytest.raises(EventValidationError):
            validate_event(ev(0.0, **{k: v for k, v in bad.items() if k != "t_ms"})
                           if "t_ms" not in bad else ev(bad["t_ms"]))

    def test_confidence_requires_source(self):
        with pytest.raises(EventValidationError, match="confidence_source"):
            validate_event(ev(0.0, kind=EventKind.CLICK, confidence=0.9))
        validate_event(ev(0.0, kind=EventKind.CLICK, confidence=0.9,
                          meta={"confidence_source": "device:sdk"}))

    def test_confidence_range(self):
        with pytest.raises(EventValidationError):
            validate_event(ev(0.0, kind=EventKind.CLICK, confidence=1.5,
                              meta={"confidence_source": "x"}))

    def test_assist_requires_type(self):
        with pytest.raises(EventValidationError):
            validate_event(ev(0.0, kind=EventKind.ASSIST))
        validate_event(ev(0.0, kind=EventKind.ASSIST, meta={"assist_type": "verbal"}))

    def test_switch_and_text(self):
        with pytest.raises(EventValidationError):
            validate_event(ev(0.0, kind=EventKind.SWITCH))
        with pytest.raises(EventValidationError):
            validate_event(ev(0.0, kind=EventKind.TEXT_INPUT))
        with pytest.raises(EventValidationError):
            validate_event(ev(0.0, kind=EventKind.SCROLL))

    def test_roundtrip_dict(self):
        e = ev(5.5, kind=EventKind.CLICK, button=0, meta={"a": 1})
        assert InputEvent.from_dict(e.to_dict()) == e


class TestOrdering:
    def test_check_stream_detects_problems(self):
        s = [ev(0, seq=0), ev(10, seq=1), ev(5, seq=2), ev(20, seq=2), ev(30, seq=6)]
        r = check_stream(s)
        assert r["non_monotonic"] == 1
        assert r["duplicate_seq"] == 1
        assert r["seq_gaps"] == 1 and r["gap_events"] == 3

    def test_clean_stream(self):
        r = check_stream([ev(i * 8.0, seq=i) for i in range(100)])
        assert r["non_monotonic"] == r["duplicate_seq"] == r["seq_gaps"] == 0

    def test_merge_multiple_streams_is_stable(self):
        a = [ev(i * 10.0, stream="mouse", seq=i) for i in range(5)]
        b = [ev(i * 10.0, stream="switch", seq=i, kind=EventKind.SWITCH, switch_id="s1")
             for i in range(5)]
        m = merge_streams(b, a)
        assert [e.stream_id for e in m[:2]] == ["mouse", "switch"]
        for s in ("mouse", "switch"):
            assert [e.seq for e in m if e.stream_id == s] == list(range(5))
        assert m == merge_streams(a, b)

    def test_replay_preserves_geometry_and_marks(self):
        a = [ev(i * 10.0, seq=i) for i in range(5)]
        r = replay(a, speed=2.0)
        assert [e.t_ms for e in r] == [0, 5, 10, 15, 20]
        assert all(e.meta["replayed_from"] == "ses_x" and e.modality == Modality.REPLAY for e in r)
        assert [(e.x, e.y) for e in r] == [(e.x, e.y) for e in a]


class TestConcordImport:
    def test_scripted_decoded_click_position(self):
        evs = import_recording(FIX / "scripted_decoded_click.concord.jsonl")
        moves = [e for e in evs if e.kind == EventKind.POINTER_MOVE]
        clicks = [e for e in evs if e.kind == EventKind.CLICK]
        assert len(moves) == 171 and len(clicks) == 1
        c = clicks[0]
        assert c.x == pytest.approx(0.625 * 1280, abs=1e-3)
        assert c.y == pytest.approx(0.125 * 800, abs=1e-3)
        # decoded intent: confidence kept only with its source
        assert c.confidence == 1.0 and c.meta["confidence_source"].startswith("concord:")
        assert c.modality == Modality.BCI_SELECT
        for e in evs:
            validate_event(e)
        r = check_stream(evs)
        assert r["non_monotonic"] == 0 and r["duplicate_seq"] == 0
        assert all(e.meta["source"]["sha256"] for e in evs)

    def test_simulated_confidence_dropped(self):
        evs = import_recording(FIX / "sim_a_pointer_select.concord.jsonl")
        sel = [e for e in evs if e.kind == EventKind.CLICK]
        assert len(sel) == 2
        assert all(e.confidence is None for e in sel)
        assert all(e.modality == Modality.SIMULATED for e in evs)
        assert all(e.synthetic for e in evs)

    def test_text_and_select_without_pointer(self):
        evs = import_recording(FIX / "sim_b_select_text.concord.jsonl")
        kinds = [e.kind for e in evs]
        assert kinds.count(EventKind.TEXT_INPUT) == 2 and kinds.count(EventKind.SELECT) == 1
        assert "".join(e.text for e in evs if e.kind == EventKind.TEXT_INPUT) == "hi"

    def test_rejects_other_formats(self, tmp_path):
        p = tmp_path / "x.jsonl"
        p.write_text('{"format":"other"}\n')
        with pytest.raises(ConcordImportError):
            import_recording(p)

    def test_truncated_last_line_tolerated(self, tmp_path):
        src = (FIX / "sim_b_select_text.concord.jsonl").read_text()
        p = tmp_path / "t.jsonl"
        p.write_text(src.rstrip("\n") + '\n{"schema_version": "1.4", "sess')
        assert len(import_recording(p)) == 3


def test_simulated_step_roundtrip_identical_metrics():
    """Simulation -> canonical events -> segmentation -> metrics == direct metrics."""
    rng = np.random.default_rng(4)
    B = 12
    sim = Simulation("feedback", UserParams(), PROFILES["bci_good"], B, rng)
    items = np.tile([[900.0, 300.0, 40, 40]], (B, 1, 1))
    st = sim.acquire(items, end_on_empty=True, max_ms=8000)
    direct = trial_metrics(PointingTrials.from_step(st))
    streams = step_to_events(st, "ses_sim")
    for b, evs in enumerate(streams):
        for e in evs:
            validate_event(e)
        tr = events_to_pointing_trials(evs)
        m = trial_metrics(tr)
        for k in ("success", "movement_time_ms", "path_length_px", "path_efficiency",
                  "endpoint_error_px", "target_reentries", "overshoot_px"):
            a, b_ = direct[k][b], m[k][0]
            if isinstance(a, (bool, np.bool_)):
                assert a == b_
            else:
                assert (np.isnan(a) and np.isnan(b_)) or a == pytest.approx(b_, rel=1e-9, abs=1e-9), k
