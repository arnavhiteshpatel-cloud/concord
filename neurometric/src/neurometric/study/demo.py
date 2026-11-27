"""Demo seed: a clearly labelled SYNTHETIC demo study ("DEMO - synthetic data, not patients").

Synthetic participants are simulated with :mod:`neurometric.simulator` (modalities +
``run_iso`` / ``run_grid`` / ``run_typing`` / ``run_adl``). The simulator returns per-trial
outcomes; this module turns them into canonical event streams (markers, straight-line pointer
paths to the simulated selection end-point, selections, keystrokes reconstructed from the
simulated error counts) and uploads them through the normal service path, so they are
validated and scored server-side exactly like recorded sessions. Every event is
``synthetic=True``, every record ``is_demo=1``, in a demo organization; nothing here is
patient data. Path-shape metrics (e.g. path efficiency) of reconstructed streams are not
meaningful; times, accuracy, throughput and text-entry metrics follow the simulator.
"""
from __future__ import annotations

import os
import secrets
import uuid
from datetime import datetime, time, timedelta, timezone
from typing import Any, Optional

import numpy as np

from ..simulator.modalities import MODALITIES, sample_population
from ..simulator.tasks import run_adl, run_grid, run_iso, run_typing
from ..tasks.battery import stimuli as battery_stimuli
from .audit import SYSTEM
from .db import iso
from .permissions import Actor
from .service import StudyService

DEMO_TITLE = "DEMO — synthetic data, not patients"
DEMO_STUDY_CODE = "DEMO-NM-001"
DEMO_MODALITIES = ("mouse_sim", "bci_cursor_good_sim", "eye_gaze_sim", "switch_scan_sim")

DEMO_SCHEDULE = {
    "visits": [
        {"code": "baseline", "day": 0, "window_before": 0, "window_after": 7, "type": "clinic",
         "tasks": ["A2", "A4", "E1", "F1"], "instruments": ["NM-SESSION", "SUS", "NASA-TLX"]},
        {"code": "week_02", "day": 14, "window_before": 3, "window_after": 3, "type": "clinic",
         "tasks": ["A2", "A4", "E1", "F1"], "instruments": ["NM-SESSION"]},
        {"code": "week_04", "day": 28, "window_before": 3, "window_after": 3, "type": "clinic",
         "tasks": ["A2", "A4", "E1", "F1"], "instruments": ["NM-SESSION", "SUS"]},
    ],
    "recurrences": [
        {"code_prefix": "home", "start_day": 7, "every_days": 7, "count": 3, "window_before": 1,
         "window_after": 2, "type": "home", "tasks": ["A4"], "instruments": ["NM-DAU"]},
    ],
}


class _Stream:
    def __init__(self, sim_modality: str):
        self.sid = f"demo-{uuid.uuid4().hex[:12]}"
        self.seq = 0
        self.t = 0.0
        self.events: list[dict[str, Any]] = []
        self.sim_modality = sim_modality

    def add(self, kind: str, dt: float = 0.0, **kw) -> None:
        self.t += max(dt, 0.0)
        meta = kw.pop("meta", {})
        ev = {"t_ms": round(self.t, 3), "kind": kind, "session_id": self.sid, "stream_id": "sim",
              "modality": "simulated", "seq": self.seq, "synthetic": True,
              "meta": {"sim_modality": self.sim_modality, **meta}}
        ev.update({k: v for k, v in kw.items() if v is not None})
        self.events.append(ev)
        self.seq += 1

    def path(self, a, b, duration: float, n: int = 8) -> None:
        for k in range(1, n + 1):
            f = k / n
            self.add("pointer_move", duration / n, x=round(a[0] + (b[0] - a[0]) * f, 2),
                     y=round(a[1] + (b[1] - a[1]) * f, 2))


def _note(st: _Stream) -> None:
    st.add("marker", 0.0, meta={"marker": "session_note",
                                "note": "synthetic demo stream reconstructed from simulator trial "
                                        "outcomes (straight-line paths)"})


def iso_events(row_df, D: float, W: float, block: int, targets: list[dict], pointer: bool,
               sim_modality: str, max_ms: float = 15000.0) -> list[dict[str, Any]]:
    st = _Stream(sim_modality)
    _note(st)
    first = targets[0]
    st.add("click", 300.0, x=first["x"], y=first["y"])  # unscored first selection
    prev = (first["x"], first["y"])
    for _, r in row_df.sort_values("selection_index").iterrows():
        k = int(r["selection_index"])
        tg, src = targets[k], targets[k - 1]
        u = np.array([tg["x"] - src["x"], tg["y"] - src["y"]], float)
        u /= max(np.linalg.norm(u), 1e-9)
        st.add("marker", 0.0, meta={"marker": "stimulus_on", "trial": k, "block": block,
                                    "D": D, "W": W, "target": {"x": tg["x"], "y": tg["y"], "w": W}})
        if bool(r["timeout"]):
            st.path(prev, (tg["x"] - u[0] * W, tg["y"] - u[1] * W), max_ms)
            st.add("marker", 0.0, meta={"marker": "trial_end", "outcome": "timeout"})
            prev = (tg["x"] - u[0] * W, tg["y"] - u[1] * W)
            continue
        dx = float(r["endpoint_dx_px"]) if np.isfinite(r["endpoint_dx_px"]) else 0.0
        end = (round(tg["x"] + u[0] * dx, 2), round(tg["y"] + u[1] * dx, 2))
        if bool(r["success"]) and np.hypot(end[0] - tg["x"], end[1] - tg["y"]) > W / 2:
            end = (tg["x"], tg["y"])
        mt = float(r["movement_time_ms"])
        st.path(prev, end, mt * 0.95)
        st.add("click" if pointer else "dwell_select", mt * 0.05, x=end[0], y=end[1])
        st.add("marker", 0.0, meta={"marker": "trial_end",
                                    "outcome": "hit" if bool(r["success"]) else "miss"})
        prev = end
    return st.events


def grid_events(row_df, stim: dict, sim_modality: str, scan: bool,
                max_ms: float = 20000.0) -> list[dict[str, Any]]:
    st = _Stream(sim_modality)
    _note(st)
    items = stim["items"]
    cues = stim["cues"]
    prev = (640.0, 400.0)
    for i, (_, r) in enumerate(row_df.sort_values("trial").iterrows()):
        tg = items[cues[i % len(cues)]]
        st.add("marker", 400.0, meta={"marker": "stimulus_on", "trial": i % len(cues),
                                      "n_items": len(items)})
        if bool(r["timeout"]):
            st.add("marker", max_ms, meta={"marker": "trial_end", "outcome": "timeout"})
            continue
        if bool(r["success"]):
            sel = tg
        else:
            sel = items[(cues[i % len(cues)] + 1) % len(items)]
        mt = float(r["movement_time_ms"])
        end = (sel["x"], sel["y"])
        if scan:
            st.add("switch", mt, x=end[0], y=end[1], switch_id="s1")
        else:
            st.path(prev, end, mt * 0.95)
            st.add("click", mt * 0.05, x=end[0], y=end[1])
        st.add("marker", 0.0, meta={"marker": "trial_end",
                                    "outcome": "hit" if bool(r["success"]) else "miss",
                                    **({} if bool(r["success"]) else {"item": 1})})
        prev = end
    return st.events


def typing_events(row_df, stim: dict, sim_modality: str, rng) -> list[dict[str, Any]]:
    st = _Stream(sim_modality)
    _note(st)
    for _, r in row_df.iterrows():
        idx = stim["phrases"].index(r["phrase"])
        ph = list(r["phrase"])
        for _ in range(int(r["INF"])):  # uncorrected substitutions
            j = int(rng.integers(0, len(ph)))
            ph[j] = "x" if ph[j] != "x" else "z"
        n_fix = int(r["F"])
        keys: list[str] = []
        fix_at = set(rng.choice(len(ph), size=min(n_fix, len(ph)), replace=False).tolist()) if n_fix else set()
        for j, ch in enumerate(ph):
            if j in fix_at:
                keys += ["q" if ch != "q" else "w", "\b"]
            keys.append(ch)
        secs = float(r["seconds"]) if np.isfinite(r["seconds"]) and r["seconds"] > 0 else len(keys)
        dt = secs * 1000.0 / max(len(keys) - 1, 1)
        st.add("marker", 500.0, meta={"marker": "phrase_start", "phrase": idx})
        for k, ch in enumerate(keys):
            st.add("text_input", 0.0 if k == 0 else dt, text=ch)
        st.add("marker", 0.0, meta={"marker": "phrase_end"})
    return st.events


def adl_events(r, sim_modality: str) -> list[dict[str, Any]]:
    st = _Stream(sim_modality)
    _note(st)
    st.add("marker", 300.0, meta={"marker": "stimulus_on", "trial": 0})
    total = float(r["time_spent_ms"])
    n_wrong = int(r["wrong_selections"])
    steps = n_wrong + 1
    for _ in range(n_wrong):
        st.add("select", total / steps, meta={"correct": False})
    if bool(r["completed"]):
        st.add("select", total / steps, meta={"correct": True})
        st.add("marker", 0.0, meta={"marker": "trial_end", "outcome": "completed"})
    else:
        st.add("marker", total / steps, meta={"marker": "trial_end", "outcome": "abandoned"})
    return st.events


def seed_demo(svc: StudyService, *, n_per_modality: int = 2, seed: int = 7,
              password: Optional[str] = None, include_home: bool = True) -> dict[str, Any]:
    """Create the synthetic demo organization, users, study and data. Returns credentials."""
    rng = np.random.default_rng(seed)
    password = password or os.environ.get("NEUROMETRIC_DEMO_PASSWORD") or (
        "demo-" + secrets.token_urlsafe(9))
    org = svc.create_organization("NeuroMetric DEMO organization (synthetic)", is_demo=True)
    oid = org["id"]
    suffix = oid[-6:]
    sysa = Actor("system", oid, "system", "demo-seed")
    admin = svc.create_user(SYSTEM, org_id=oid, username=f"demo-admin-{suffix}", password=password,
                            role="admin", display_name="Demo Admin (fictional)")
    A = svc.actor_for_user(svc.db.one("SELECT * FROM users WHERE id=?", (admin["id"],)))
    site = svc.create_site(A, "DEMO-01", "Demo site (fictional)")
    sponsor = svc.create_sponsor(A, "Demo sponsor (fictional)")
    users = {"admin": admin["username"]}
    staff = {}
    for role, name in (("coordinator", "Demo Coordinator"), ("investigator", "Demo Investigator"),
                       ("sponsor_analyst", "Demo Sponsor Analyst")):
        u = svc.create_user(A, org_id=oid, username=f"demo-{role.replace('_', '-')}-{suffix}",
                            password=password, role=role, display_name=f"{name} (fictional)",
                            site_ids=[site["id"]] if role != "sponsor_analyst" else [])
        users[role] = u["username"]
        staff[role] = svc.actor_for_user(svc.db.one("SELECT * FROM users WHERE id=?", (u["id"],)))
    INV, CO = staff["investigator"], staff["coordinator"]
    study = svc.create_study(INV, DEMO_STUDY_CODE, DEMO_TITLE, sponsor_id=sponsor["id"],
                             is_demo=True, min_cell_size=2)
    svc.add_site_to_study(INV, study["id"], site["id"])
    pv = svc.add_protocol_version(INV, study["id"], "1.0-demo", svc.db.now().date().isoformat(),
                                  "Synthetic demo protocol", "DEMO-CONSENT-v1")
    sch = svc.create_schedule(INV, study["id"], "Demo schedule", DEMO_SCHEDULE, pv["id"])
    svc.update_study(INV, study["id"], {"status": "active"}, "demo study activated")
    today = svc.db.now().date()
    anchor = today - timedelta(days=30)
    a2 = battery_stimuli("A2", seed)
    blk = a2["blocks"][0]
    a4 = battery_stimuli("A4", seed)
    e1 = battery_stimuli("E1", seed)
    f1 = battery_stimuli("F1", seed)
    participants = []
    for mname in DEMO_MODALITIES:
        mod = MODALITIES[mname]
        z = rng.standard_normal(n_per_modality)
        pids = []
        for i in range(n_per_modality):
            p = svc.create_participant(CO, study["id"], site["id"], cohort="demo",
                                       primary_modality=mname)
            pid = p["id"]
            scopes = {k: True for k in ("task_battery", "questionnaires", "home_telemetry",
                                        "telemetry_app_categories", "sharing_with_sponsor",
                                        "future_research")}
            svc.record_consent(CO, pid, "DEMO-CONSENT", "v1", scopes)
            svc.transition(CO, pid, "consented")
            svc.transition(CO, pid, "enrolled")
            svc.add_device_config(CO, pid, mname, "Simulated device (no real hardware)",
                                  {"simulator_profile": mname}, "not_applicable")
            svc.generate_visits(CO, pid, sch["id"], anchor.isoformat())
            pu = svc.create_user(A, org_id=oid, username=f"demo-participant-{pid.lower()}",
                                 password=password, role="participant",
                                 display_name="Synthetic participant", participant_id=pid)
            pids.append((pid, pu))
            participants.append(pid)
        visits = {pid: {v["visit_code"]: v for v in svc.list_visits(CO, pid)} for pid, _ in pids}
        codes = ["baseline", "week_02", "week_04"]
        n = n_per_modality
        # one vectorised simulator call per task covers all clinic visits (batch = visit x
        # participant); simulated ability improves across visits (synthetic learning effect)
        users_all, _ = sample_population(mod.user, n * len(codes), rng,
                                         ability=np.concatenate([z + 0.25 * vi
                                                                 for vi in range(len(codes))]))
        nb = n * len(codes)
        iso_tr = run_iso(mod, users_all, nb, rng, blk["D"], blk["W"])[0] if mod.kind == "pointer" else None
        grid = run_grid(mod, users_all, nb, rng, n_trials=8)
        typ = run_typing(mod, users_all, nb, rng, e1["phrases"][:1])
        adl = run_adl(mod, users_all, nb, rng, "F1")
        for vi, code in enumerate(codes):
            for i, (pid, _) in enumerate(pids):
                j = vi * n + i  # simulator batch index
                if code == "week_04" and i == n - 1 and mname == DEMO_MODALITIES[-1]:
                    continue  # one synthetic participant misses week 4 (missing-data demo)
                v = visits[pid][code]
                when = iso(datetime.combine(date_of(v["target_date"]), time(10, 0),
                                            timezone.utc))
                common = dict(visit_id=v["id"], provenance="simulated", modality=mname,
                              performed_at=when)
                if mod.kind == "pointer":
                    svc.upload_session(CO, pid, task_id="A2", stimulus_seed=seed,
                                       stimulus_hash=a2["stimulus_hash"],
                                       events=iso_events(iso_tr[iso_tr.participant == j],
                                                         blk["D"], blk["W"], 0, blk["targets"],
                                                         mod.selection == "click", mname),
                                       **common)
                svc.upload_session(CO, pid, task_id="A4", stimulus_seed=seed,
                                   stimulus_hash=a4["stimulus_hash"],
                                   events=grid_events(grid[grid.participant == j], a4, mname,
                                                      mod.kind == "scan"), **common)
                svc.upload_session(CO, pid, task_id="E1", stimulus_seed=seed,
                                   stimulus_hash=e1["stimulus_hash"],
                                   events=typing_events(typ[typ.participant == j], e1, mname, rng),
                                   **common)
                svc.upload_session(CO, pid, task_id="F1", stimulus_seed=seed,
                                   stimulus_hash=f1["stimulus_hash"],
                                   events=adl_events(adl[adl.participant == j].iloc[0], mname),
                                   **common)
                lvl = max(0, min(10, int(round(6 - 1.0 * vi + rng.normal(0, 1)))))
                svc.submit_response(CO, pid, "NM-SESSION", {
                    "fatigue": lvl, "effort": max(0, min(10, lvl + 1)),
                    "frustration": max(0, lvl - 1), "satisfaction": min(10, 10 - lvl + 1),
                    "comfort": 7, "device_problem": bool(rng.random() < 0.2)}, visit_id=v["id"])
                if code in ("baseline", "week_04"):
                    svc.submit_response(CO, pid, "SUS", {
                        f"sus{k}": int(np.clip(round((4 if k % 2 else 2) + rng.normal(0, 0.7)
                                                     + (0.3 * vi if k % 2 else -0.3 * vi)), 1, 5))
                        for k in range(1, 11)}, visit_id=v["id"])
                if code == "baseline":
                    svc.submit_response(CO, pid, "NASA-TLX", {
                        **{k: int(5 * round(np.clip(rng.normal(50, 15), 0, 100) / 5))
                           for k in ("mental", "physical", "temporal", "performance", "effort",
                                     "frustration")},
                        "w_mental": 4, "w_physical": 1, "w_temporal": 2, "w_performance": 3,
                        "w_effort": 3, "w_frustration": 2}, visit_id=v["id"])
        if include_home:
            users_h, _ = sample_population(mod.user, n * 3, rng,
                                           ability=np.concatenate([z + 0.1] * 3))
            grid = run_grid(mod, users_h, n * 3, rng, n_trials=6)
            for k in range(1, 4):
                for i, (pid, _) in enumerate(pids):
                    j = (k - 1) * n + i
                    v = visits[pid][f"home_{k:02d}"]
                    when = iso(datetime.combine(date_of(v["target_date"]), time(18, 0),
                                                timezone.utc))
                    svc.upload_session(CO, pid, task_id="A4", stimulus_seed=seed,
                                       stimulus_hash=a4["stimulus_hash"], visit_id=v["id"],
                                       events=grid_events(grid[grid.participant == j], a4, mname,
                                                          mod.kind == "scan"),
                                       provenance="simulated", modality=mname, performed_at=when)
                    total = int(rng.integers(60, 240))
                    indep = int(total * rng.uniform(0.3, 0.9))
                    svc.submit_response(CO, pid, "NM-DAU", {
                        "activities": ["messaging", "web"], "minutes_digital_total": total,
                        "minutes_independent": indep, "minutes_with_assistance": total - indep,
                        "assistance_types": ["setup"], "minutes_care_partner_help": int(
                            rng.integers(5, 45)), "main_access_method": "other",
                        "independence_rating": int(rng.integers(3, 9)), "unmet_activity": False},
                        visit_id=v["id"])
        # telemetry: a week of daily aggregate batches from each synthetic participant's app
        for pid, pu in pids:
            P = svc.actor_for_user(svc.db.one("SELECT * FROM users WHERE id=?", (pu["id"],)))
            dsid = f"demo-{uuid.uuid4().hex[:16]}"
            for d in range(7, 0, -1):
                day = today - timedelta(days=d)
                start = datetime.combine(day, time(8, 0), timezone.utc)
                active = float(rng.integers(40, 200))
                svc.ingest_telemetry(P, {
                    "schema_version": "nm.telemetry/1", "participant": pid,
                    "device_session_id": dsid, "period_start": iso(start),
                    "period_end": iso(start + timedelta(hours=12)), "active_minutes": active,
                    "device_assisted_sessions": int(rng.integers(1, 4)),
                    "interaction_counts": {"pointer": int(rng.integers(500, 5000)),
                                           "select": int(rng.integers(50, 400)),
                                           "text_chars_count": int(rng.integers(0, 600))},
                    "interruptions": int(rng.integers(0, 5)),
                    "app_category_minutes": {"communication": round(active * 0.4, 1),
                                             "web": round(active * 0.3, 1)},
                    "self_reported_assistance": [{"type": "setup", "minutes": 10}],
                    "self_reported_fatigue": int(rng.integers(2, 8)),
                    "self_reported_burden": int(rng.integers(1, 6)),
                    "client": {"app_version": "0.1.0", "platform": "web"}})
    svc.mark_missed_visits(sysa, study["id"])
    first = participants[0]
    svc.report_deviation(CO, study["id"], "procedure", "Synthetic example: task order changed",
                         "minor", participant_id=first)
    sess = svc.list_sessions(CO, first)[0]
    q = svc.raise_query(INV, study["id"], "functional_sessions", sess["id"],
                        "Synthetic example query: please confirm device configuration.")
    svc.answer_query(CO, q["id"], "Confirmed (synthetic).")
    svc.withdraw_consent(CO, participants[-1], "synthetic example of withdrawal",
                         action="retain")
    return {"organization_id": oid, "study_id": study["id"], "study_title": DEMO_TITLE,
            "users": users, "password": password, "participants": participants,
            "note": "All demo data are synthetic (simulated); not patients."}


def date_of(s: str):
    from datetime import date
    return date.fromisoformat(s)
