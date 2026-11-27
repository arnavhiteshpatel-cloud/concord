"""Functional testing sessions: validation of canonical events, server-side scoring with
known answers, raw-event storage (compressed + SHA-256), access rules."""
from __future__ import annotations

import hashlib
import json
import math
import zlib

import numpy as np
import pytest

from neurometric.events.model import InputEvent
from neurometric.study import ConsentRequired, PermissionDenied, StudyService, ValidationFailed
from neurometric.study.db import canonical_json
from neurometric.study.scoring import score_session
from neurometric.study.testing import (FakeClock, a1_events, build_world, e1_events,
                                       ensure_test_key, upload_a1)
from neurometric.tasks.battery import stimuli

ensure_test_key()


@pytest.fixture
def svc(tmp_path):
    s = StudyService(tmp_path / "nm.sqlite", FakeClock())
    yield s
    s.db.close()


@pytest.fixture
def w(svc):
    return build_world(svc, "A")


def _parse(evs):
    return [InputEvent.from_dict(e) for e in evs]


# --------------------------------------------------------------------------- known answers
def test_a1_known_answers():
    m = score_session("A1", _parse(a1_events(0, mt_ms=1000.0)), 0)
    assert m["n_trials"] == 12 and m["success_rate"] == 1.0
    assert m["movement_time_ms_mean"] == pytest.approx(1000.0)
    assert m["path_efficiency_mean"] == pytest.approx(1.0)
    assert m["endpoint_error_px_mean"] == pytest.approx(0.0, abs=1e-9)
    assert m["timeout_rate"] == 0.0 and m["assisted_trials"] == 0


def test_a1_misses_and_assistance():
    m = score_session("A1", _parse(a1_events(0, miss=(0, 5, 7), assist_trial=2)), 0)
    assert m["success_rate"] == pytest.approx(9 / 12)
    assert m["error_rate"] == pytest.approx(3 / 12)
    assert m["assisted_trials"] == 1
    assert m["session"]["assist_events"] == 1.0


def test_a1_target_geometry_from_stimuli():
    st = stimuli("A1", 4)
    m = score_session("A1", _parse(a1_events(4)), 4)
    assert m["success_rate"] == 1.0
    # wrong seed -> the same clicks miss the (different) targets
    m2 = score_session("A1", _parse(a1_events(4)), 5)
    assert m2["success_rate"] < 1.0
    assert st["stimulus_hash"] != stimuli("A1", 5)["stimulus_hash"]


def test_a2_throughput_matches_iso_formula():
    st = stimuli("A2", 0)
    blk = st["blocks"][0]
    D, W, T = blk["D"], blk["W"], blk["targets"]
    rng = np.random.default_rng(1)
    offs = rng.normal(0, W / 6, 12)
    mt = 800.0
    evs, t, seq = [], 0.0, 0
    sid = "s-a2"

    def add(kind, **kw):
        nonlocal seq
        evs.append({"t_ms": t, "kind": kind, "session_id": sid, "stream_id": "d",
                    "modality": "mouse", "seq": seq, **kw})
        seq += 1
    add("click", x=T[0]["x"], y=T[0]["y"])
    prev = np.array([T[0]["x"], T[0]["y"]])
    dxs, amps = [], []
    for k in range(1, 13):
        tg = np.array([T[k]["x"], T[k]["y"]])
        u = (tg - prev) / np.linalg.norm(tg - prev)
        end = tg + u * offs[k - 1]
        add("marker", meta={"marker": "stimulus_on", "trial": k, "block": 0, "D": D, "W": W,
                            "target": {"x": T[k]["x"], "y": T[k]["y"], "w": W}})
        for f in (0.25, 0.5, 0.75, 1.0):
            t += mt / 4
            p = prev + (end - prev) * f
            add("pointer_move", x=float(p[0]), y=float(p[1]))
        add("click", x=float(end[0]), y=float(end[1]))
        add("marker", meta={"marker": "trial_end"})
        dxs.append(float((end - tg) @ u))
        amps.append(float((end - prev) @ u))
        prev = end
    we = math.sqrt(2 * math.pi * math.e) * float(np.std(dxs, ddof=1))
    expected = math.log2(float(np.mean(amps)) / we + 1) / (mt / 1000)
    m = score_session("A2", _parse(evs), 0)
    assert m["fitts_throughput_bps"] == pytest.approx(expected, rel=1e-6)
    assert m["conditions"][0]["n"] == 12


def test_e1_known_answers():
    st = stimuli("E1", 0)
    phrase = st["phrases"][0]
    m = score_session("E1", _parse(e1_events(0, seconds=10.0)), 0)
    assert m["n_phrases"] == 1
    assert m["wpm_mean"] == pytest.approx((len(phrase) - 1) / 10.0 * 60 / 5)
    assert m["msd_error_rate_mean"] == 0.0 and m["total_error_rate_mean"] == 0.0
    typed = list(phrase[:3]) + ["x", "\b"] + list(phrase[3:])
    m2 = score_session("E1", _parse(e1_events(0, typed=typed, seconds=12.0)), 0)
    assert m2["corrected_error_rate_mean"] > 0 and m2["msd_error_rate_mean"] == 0
    assert m2["phrases"][0]["keystrokes"] == len(phrase) + 2


def test_generic_adl_scoring():
    evs = [{"t_ms": 0, "kind": "marker", "session_id": "s", "stream_id": "d", "modality": "switch",
            "seq": 0, "meta": {"marker": "stimulus_on"}},
           {"t_ms": 500, "kind": "select", "session_id": "s", "stream_id": "d",
            "modality": "switch", "seq": 1, "meta": {"correct": False}},
           {"t_ms": 2000, "kind": "select", "session_id": "s", "stream_id": "d",
            "modality": "switch", "seq": 2, "meta": {"correct": True}},
           {"t_ms": 2000, "kind": "marker", "session_id": "s", "stream_id": "d",
            "modality": "switch", "seq": 3, "meta": {"marker": "trial_end", "outcome": "completed"}}]
    m = score_session("F1", _parse(evs), 0)
    assert m["completion_rate"] == 1.0 and m["time_to_complete_ms_mean"] == 2000
    assert m["wrong_selections"] == 1


# --------------------------------------------------------------------------- upload rules
def test_upload_stores_compressed_events_with_hash(svc, w):
    s = upload_a1(svc, w.co, w.pid)
    assert s["metrics"]["success_rate"] == 1.0 and s["n_events"] > 0
    row = svc.db.one("SELECT * FROM functional_sessions WHERE id=?", (s["id"],))
    raw = zlib.decompress(row["events_blob"])
    assert hashlib.sha256(raw).hexdigest() == row["events_sha256"]
    assert len(row["events_blob"]) < len(raw)
    full = svc.get_session(w.co, s["id"], include_events=True)
    assert canonical_json(full["events"]).encode() == raw
    assert s["stimulus_hash"] == stimuli("A1", 0)["stimulus_hash"]
    assert s["battery_version"] == "1.0.0" and s["scorer_version"].startswith("neurometric")
    assert svc.get_participant(w.co, w.pid)["enrollment_state"] == "active"


def test_upload_rejections(svc, w):
    good = a1_events(0)
    h = stimuli("A1", 0)["stimulus_hash"]

    def up(events=good, **kw):
        args = dict(task_id="A1", events=events, stimulus_seed=0, stimulus_hash=h)
        args.update(kw)
        return svc.upload_session(w.co, w.pid, **args)

    cases = {
        "stimulus_mismatch": dict(stimulus_hash="0" * 16),
        "battery_version": dict(battery_version="0.9.0"),
    }
    for code, kw in cases.items():
        with pytest.raises(ValidationFailed) as e:
            up(**kw)
        assert e.value.code == code
    with pytest.raises(ValidationFailed):
        up(task_id="Z9")
    with pytest.raises(ValidationFailed):
        up(events=[])
    bad = [dict(e) for e in good]
    bad[5] = {k: v for k, v in bad[5].items() if k not in ("x", "y")}
    bad[5]["kind"] = "click"
    with pytest.raises(ValidationFailed) as e:
        up(events=bad)
    assert "requires x and y" in json.dumps(e.value.detail)
    mixed = [dict(e) for e in good]
    mixed[3]["session_id"] = "other"
    with pytest.raises(ValidationFailed):
        up(events=mixed)
    dup = [dict(e) for e in good]
    dup[4]["seq"] = dup[3]["seq"]
    with pytest.raises(ValidationFailed) as e:
        up(events=dup)
    assert e.value.code == "duplicate_events"
    fab = [dict(e) for e in good]
    fab[2]["confidence"] = 0.9  # confidence without a source is never stored
    with pytest.raises(ValidationFailed):
        up(events=fab)
    up()
    with pytest.raises(ValidationFailed) as e:
        up()
    assert e.value.code == "duplicate_upload"


def test_text_outside_copy_typing_needs_free_text_consent(svc, w):
    evs = a1_events(0)
    evs.append({"t_ms": evs[-1]["t_ms"] + 10, "kind": "text_input", "text": "private words",
                "session_id": evs[0]["session_id"], "stream_id": "dev1", "modality": "mouse",
                "seq": len(evs)})
    with pytest.raises(ConsentRequired):
        svc.upload_session(w.co, w.pid, task_id="A1", events=evs, stimulus_seed=0,
                           stimulus_hash=stimuli("A1", 0)["stimulus_hash"])
    # copy typing of predefined phrases is allowed without free_text consent
    svc.upload_session(w.co, w.pid, task_id="E1", events=e1_events(0), stimulus_seed=0,
                       stimulus_hash=stimuli("E1", 0)["stimulus_hash"])


def test_upload_roles(svc, w):
    upload_a1(svc, w.part, w.pid, seed=1)  # participant (self)
    upload_a1(svc, w.cp, w.pid, seed=2)  # linked care partner
    with pytest.raises(PermissionDenied):
        upload_a1(svc, w.sa, w.pid, seed=3)
    with pytest.raises(PermissionDenied):
        upload_a1(svc, w.admin, w.pid, seed=3)
    assert len(svc.list_sessions(w.part, w.pid)) == 2
    with pytest.raises(PermissionDenied):
        svc.list_sessions(w.cp, w.pid)  # care partners upload but do not browse raw sessions


def test_device_config_link(svc, w):
    d = svc.add_device_config(w.co, w.pid, "bci_cursor", "Research BCI (make/model text)",
                              {"gain": 1.2}, "calibrated")
    s = upload_a1(svc, w.co, w.pid, device_config_id=d["id"])
    assert s["device_config_id"] == d["id"]
    with pytest.raises(ValidationFailed):
        svc.add_device_config(w.co, w.pid, "x", calibration_state="perfect")
