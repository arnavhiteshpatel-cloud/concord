"""Builders for tests and validation scripts (OQ): a fully set-up organization ("world"),
canonical event streams with known geometry, and a controllable clock. Not used at runtime."""
from __future__ import annotations

import base64
import os
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from typing import Any, Optional

from ..tasks.battery import stimuli
from .audit import SYSTEM
from .permissions import Actor
from .service import StudyService

TEST_PASSWORD = "correct-horse-battery-staple-1"
ALL_SCOPES = {"task_battery": True, "questionnaires": True, "home_telemetry": True,
              "telemetry_app_categories": True, "free_text": False, "sharing_with_sponsor": True,
              "future_research": False}
SCHEDULE = {
    "visits": [
        {"code": "baseline", "day": 0, "window_before": 0, "window_after": 7, "type": "clinic",
         "tasks": ["A1", "E1"], "instruments": ["NM-SESSION"]},
        {"code": "week_02", "day": 14, "window_before": 3, "window_after": 3, "type": "clinic",
         "tasks": ["A1"], "instruments": ["NM-SESSION", "SUS"]},
    ],
    "recurrences": [{"code_prefix": "home", "start_day": 7, "every_days": 7, "count": 3,
                     "window_before": 1, "window_after": 2, "type": "home", "tasks": ["A4"],
                     "instruments": ["NM-DAU"]}],
}


def ensure_test_key() -> None:
    """Set a throw-away field-encryption key for tests if none is configured."""
    os.environ.setdefault("NEUROMETRIC_REID_KEY", base64.urlsafe_b64encode(b"k" * 32).decode())


@dataclass
class FakeClock:
    now: datetime = field(default_factory=lambda: datetime(2026, 3, 2, 9, 0, tzinfo=timezone.utc))

    def __call__(self) -> datetime:
        return self.now

    def advance(self, **kw) -> None:
        self.now = self.now + timedelta(**kw)


def actor_of(svc: StudyService, user: dict[str, Any]) -> Actor:
    return svc.actor_for_user(svc.db.one("SELECT * FROM users WHERE id=?", (user["id"],)))


def build_world(svc: StudyService, name: str = "A", *, is_demo: bool = False,
                enrolled: bool = True) -> SimpleNamespace:
    """Organization with all six roles, one site, one study, schedule and one enrolled,
    consented participant (with participant and care-partner accounts)."""
    ensure_test_key()
    w = SimpleNamespace(svc=svc)
    w.org = svc.create_organization(f"Org {name}", is_demo=False)
    oid = w.org["id"]
    u = lambda role, **kw: svc.create_user(  # noqa: E731
        SYSTEM, org_id=oid, username=f"{name.lower()}-{role}-{uuid.uuid4().hex[:6]}",
        password=TEST_PASSWORD, role=role, display_name=f"{name} {role}", **kw)
    w.admin = actor_of(svc, u("admin"))
    w.site = svc.create_site(w.admin, f"S{name}", f"Site {name}")
    w.site2 = svc.create_site(w.admin, f"T{name}", f"Other site {name}")
    w.sponsor = svc.create_sponsor(w.admin, f"Sponsor {name}")
    w.co = actor_of(svc, u("coordinator", site_ids=[w.site["id"]]))
    w.inv = actor_of(svc, u("investigator", site_ids=[w.site["id"]]))
    w.co2 = actor_of(svc, u("coordinator", site_ids=[w.site2["id"]]))
    w.sa = actor_of(svc, u("sponsor_analyst"))
    w.study = svc.create_study(w.inv, f"ST-{name}", f"Study {name}", sponsor_id=w.sponsor["id"],
                               is_demo=is_demo, min_cell_size=1)
    svc.add_site_to_study(w.inv, w.study["id"], w.site["id"])
    svc.add_site_to_study(w.inv, w.study["id"], w.site2["id"])
    w.pv = svc.add_protocol_version(w.inv, w.study["id"], "1.0", "2026-01-01", "initial", "ICF-1")
    w.schedule = svc.create_schedule(w.inv, w.study["id"], "main", SCHEDULE, w.pv["id"])
    w.p = svc.create_participant(w.co, w.study["id"], w.site["id"], cohort="c1",
                                 primary_modality="mouse", identifier=f"MRN-{name}-0001")
    w.pid = w.p["id"]
    svc.record_consent(w.co, w.pid, "ICF-1", "1.0", dict(ALL_SCOPES))
    if enrolled:
        svc.transition(w.co, w.pid, "consented")
        svc.transition(w.co, w.pid, "enrolled")
    w.part_user = u("participant", participant_id=w.pid)
    w.part = actor_of(svc, w.part_user)
    w.cp_user = u("care_partner", linked_participants=[w.pid])
    w.cp = actor_of(svc, w.cp_user)
    w.users = {"admin": w.admin, "coordinator": w.co, "investigator": w.inv,
               "sponsor_analyst": w.sa, "participant": w.part, "care_partner": w.cp}
    return w


class _S:
    def __init__(self, session_id: Optional[str] = None, synthetic: bool = False,
                 modality: str = "mouse"):
        self.sid = session_id or f"s-{uuid.uuid4().hex[:10]}"
        self.t = 0.0
        self.seq = 0
        self.ev: list[dict[str, Any]] = []
        self.synthetic = synthetic
        self.modality = modality

    def add(self, kind: str, dt: float = 0.0, **kw) -> None:
        self.t += dt
        e = {"t_ms": self.t, "kind": kind, "session_id": self.sid, "stream_id": "dev1",
             "modality": self.modality, "seq": self.seq, "synthetic": self.synthetic}
        e.update(kw)
        self.ev.append(e)
        self.seq += 1


def a1_events(seed: int = 0, mt_ms: float = 1000.0, miss: tuple[int, ...] = (),
              n: Optional[int] = None, synthetic: bool = False, steps: int = 10,
              assist_trial: Optional[int] = None) -> list[dict[str, Any]]:
    """A1 single-target stream: straight path from the start button to each target, selection
    at the target centre (or 3 target widths away for trials in ``miss``)."""
    st = stimuli("A1", seed)
    s = _S(synthetic=synthetic)
    trials = st["trials"][: n or len(st["trials"])]
    for i, tr in enumerate(trials):
        sx, sy = tr["start"]["x"], tr["start"]["y"]
        s.add("pointer_move", 500.0, x=sx, y=sy)
        s.add("marker", 0.0, meta={"marker": "stimulus_on", "trial": i})
        tx, ty = tr["x"], tr["y"]
        if i in miss:
            tx, ty = tx + 3 * tr["w"], ty
        for k in range(1, steps + 1):
            f = k / steps
            s.add("pointer_move", mt_ms / steps, x=sx + (tx - sx) * f, y=sy + (ty - sy) * f)
        if assist_trial == i:
            s.add("assist", 0.0, meta={"assist_type": "verbal"})
        s.add("click", 0.0, x=tx, y=ty, button=0)
        s.add("marker", 0.0, meta={"marker": "trial_end"})
    return s.ev


def e1_events(seed: int = 0, typed: Optional[list[str]] = None, seconds: float = 10.0,
              phrase_index: int = 0) -> list[dict[str, Any]]:
    """E1 copy typing of stimulus phrase ``phrase_index``; ``typed`` is the keystroke list
    (``'\\b'`` = backspace), default = the phrase typed perfectly."""
    st = stimuli("E1", seed)
    phrase = st["phrases"][phrase_index]
    keys = list(phrase) if typed is None else typed
    s = _S()
    s.add("marker", 100.0, meta={"marker": "phrase_start", "phrase": phrase_index})
    dt = seconds * 1000.0 / max(len(keys) - 1, 1)
    for k, ch in enumerate(keys):
        s.add("text_input", 0.0 if k == 0 else dt, text=ch)
    s.add("marker", 0.0, meta={"marker": "phrase_end"})
    return s.ev


def upload_a1(svc: StudyService, actor: Actor, pid: str, seed: int = 0, **kw) -> dict:
    ev_kw = {k: kw.pop(k) for k in ("mt_ms", "miss", "n", "synthetic", "assist_trial") if k in kw}
    return svc.upload_session(actor, pid, task_id="A1", events=a1_events(seed, **ev_kw),
                              stimulus_seed=seed, stimulus_hash=stimuli("A1", seed)["stimulus_hash"],
                              **kw)


def telemetry_payload(pid: str, start: datetime, hours: float = 1.0, **over) -> dict[str, Any]:
    from .db import iso
    p = {"schema_version": "nm.telemetry/1", "participant": pid,
         "device_session_id": "devsess-0001", "period_start": iso(start),
         "period_end": iso(start + timedelta(hours=hours)), "active_minutes": 30,
         "device_assisted_sessions": 1,
         "interaction_counts": {"pointer": 1200, "select": 80, "text_chars_count": 150},
         "interruptions": 2, "self_reported_assistance": [{"type": "setup", "minutes": 5}],
         "self_reported_fatigue": 4, "self_reported_burden": 3,
         "client": {"app_version": "0.1.0", "platform": "web"}}
    p.update(over)
    return p
