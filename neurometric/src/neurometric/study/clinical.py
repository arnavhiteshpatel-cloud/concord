"""Study set-up and clinical operations: sponsors, sites, studies, protocol versions, assessment
schedules and visit generation, participants and enrollment, re-identification keys, device
configurations, deviations, missing data, data queries, review / e-signatures and corrections."""
from __future__ import annotations

import json
import re
from datetime import date, timedelta
from typing import Any, Optional

from ..tasks.battery import TASKS
from .core import StudyServiceBase, jload, new_id, new_pseudonym
from .db import canonical_json
from .errors import (Conflict, InvalidTransition, NotFound, PermissionDenied, ReasonRequired,
                     ValidationFailed)
from .permissions import Actor, require
from .security import decrypt_field, encrypt_field

ENROLLMENT_STATES = ("screening", "consented", "enrolled", "active", "completed", "withdrawn",
                     "lost")
TRANSITIONS: dict[str, frozenset[str]] = {
    "screening": frozenset({"consented", "withdrawn"}),
    "consented": frozenset({"enrolled", "withdrawn"}),
    "enrolled": frozenset({"active", "withdrawn", "lost"}),
    "active": frozenset({"completed", "withdrawn", "lost"}),
    "lost": frozenset({"active", "withdrawn"}),
    "completed": frozenset(),
    "withdrawn": frozenset(),
}
REASON_REQUIRED_STATES = frozenset({"withdrawn", "lost", "completed"})
COLLECTING_STATES = frozenset({"enrolled", "active"})
TASK_IDS = {t.id for t in TASKS}
_CODE = re.compile(r"^[a-z0-9_]{1,40}$")

#: Fields that may be corrected through the generic correction workflow.
CORRECTABLE: dict[str, frozenset[str]] = {
    "participants": frozenset({"cohort", "primary_modality"}),
    "visits": frozenset({"notes", "visit_type", "target_date", "window_start", "window_end"}),
    "device_configs": frozenset({"modality", "make_model", "settings_json", "calibration_state"}),
    "protocol_deviations": frozenset({"category", "description", "severity", "status"}),
    "missing_data": frozenset({"reason_code", "note"}),
    "questionnaire_responses": frozenset({"answers"}),
    "functional_sessions": frozenset({"status"}),
}

MISSING_REASONS = ("participant_unwell", "device_problem", "participant_declined",
                   "scheduling", "technical_failure", "missed_visit", "withdrawn",
                   "not_applicable", "other")


def validate_schedule(defn: dict[str, Any], instrument_ids: set[str]) -> None:
    errs = []
    if not isinstance(defn, dict):
        raise ValidationFailed("schedule definition must be an object")
    codes = set()

    def common(v, label):
        for k in ("window_before", "window_after"):
            if not isinstance(v.get(k, 0), int) or v.get(k, 0) < 0:
                errs.append(f"{label}: {k} must be a non-negative integer")
        if v.get("type", "clinic") not in ("clinic", "home", "remote"):
            errs.append(f"{label}: type must be clinic, home or remote")
        for t in v.get("tasks", []):
            if t not in TASK_IDS:
                errs.append(f"{label}: unknown task {t}")
        for i in v.get("instruments", []):
            if i not in instrument_ids:
                errs.append(f"{label}: unknown instrument {i}")

    for v in defn.get("visits", []):
        code = v.get("code", "")
        if not _CODE.match(str(code)):
            errs.append(f"visit code {code!r} must match [a-z0-9_]")
        if code in codes:
            errs.append(f"duplicate visit code {code}")
        codes.add(code)
        if not isinstance(v.get("day"), int) or v["day"] < 0:
            errs.append(f"{code}: day must be a non-negative integer")
        common(v, code)
    for r in defn.get("recurrences", []):
        pre = r.get("code_prefix", "")
        if not _CODE.match(str(pre)):
            errs.append(f"recurrence prefix {pre!r} invalid")
        if not isinstance(r.get("every_days"), int) or r["every_days"] < 1:
            errs.append(f"{pre}: every_days must be >= 1")
        if not isinstance(r.get("start_day"), int) or r["start_day"] < 0:
            errs.append(f"{pre}: start_day must be >= 0")
        if not (isinstance(r.get("count"), int) and r["count"] >= 1) and not isinstance(
                r.get("until_day"), int):
            errs.append(f"{pre}: count (>=1) or until_day is required")
        if isinstance(r.get("count"), int) and r["count"] > 520:
            errs.append(f"{pre}: count too large")
        common(r, pre)
    if not defn.get("visits") and not defn.get("recurrences"):
        errs.append("schedule needs at least one visit or recurrence")
    if errs:
        raise ValidationFailed("invalid schedule: " + "; ".join(errs), errors=errs)


def expand_schedule(defn: dict[str, Any], anchor: date) -> list[dict[str, Any]]:
    """Expand a schedule definition into concrete visits (pure function, sorted by date)."""
    out = []
    for v in defn.get("visits", []):
        t = anchor + timedelta(days=v["day"])
        out.append({"visit_code": v["code"], "day": v["day"], "visit_type": v.get("type", "clinic"),
                    "target_date": t, "window_start": t - timedelta(days=v.get("window_before", 0)),
                    "window_end": t + timedelta(days=v.get("window_after", 0)),
                    "tasks": v.get("tasks", []), "instruments": v.get("instruments", [])})
    for r in defn.get("recurrences", []):
        days = []
        d = r["start_day"]
        while True:
            if isinstance(r.get("count"), int) and len(days) >= r["count"]:
                break
            if isinstance(r.get("until_day"), int) and d > r["until_day"]:
                break
            days.append(d)
            d += r["every_days"]
            if len(days) > 520:
                break
        for k, day in enumerate(days, 1):
            t = anchor + timedelta(days=day)
            out.append({"visit_code": f"{r['code_prefix']}_{k:02d}", "day": day,
                        "visit_type": r.get("type", "home"), "target_date": t,
                        "window_start": t - timedelta(days=r.get("window_before", 0)),
                        "window_end": t + timedelta(days=r.get("window_after", 0)),
                        "tasks": r.get("tasks", []), "instruments": r.get("instruments", [])})
    out.sort(key=lambda v: (v["target_date"], v["visit_code"]))
    return out


class ClinicalMixin(StudyServiceBase):
    # ------------------------------------------------------------------ sponsors & sites
    def create_sponsor(self, actor: Actor, name: str) -> dict[str, Any]:
        require(actor, "sponsor.manage")
        demo = self.db.scalar("SELECT is_demo FROM organizations WHERE id=?", (actor.org_id,))
        row = {"id": new_id("spn"), "org_id": actor.org_id, "name": name, "is_demo": demo,
               "created_at": self.db.now_iso()}
        return self._insert(actor, "sponsors", row)

    def list_sponsors(self, actor: Actor) -> list[dict[str, Any]]:
        require(actor, "study.read")
        return self.db.query("SELECT * FROM sponsors WHERE org_id=? ORDER BY name", (actor.org_id,))

    def create_site(self, actor: Actor, code: str, name: str) -> dict[str, Any]:
        require(actor, "site.manage")
        demo = self.db.scalar("SELECT is_demo FROM organizations WHERE id=?", (actor.org_id,))
        row = {"id": new_id("site"), "org_id": actor.org_id, "code": code, "name": name,
               "is_demo": demo, "created_at": self.db.now_iso()}
        return self._insert(actor, "sites", row)

    def list_sites(self, actor: Actor) -> list[dict[str, Any]]:
        if actor.role not in ("admin", "coordinator", "investigator", "sponsor_analyst"):
            raise PermissionDenied("sites not visible to this role")
        return self.db.query("SELECT * FROM sites WHERE org_id=? ORDER BY code", (actor.org_id,))

    # ------------------------------------------------------------------ studies
    def create_study(self, actor: Actor, code: str, title: str, *, sponsor_id: Optional[str] = None,
                     is_demo: bool = False, withdrawal_action_default: str = "retain",
                     min_cell_size: int = 3) -> dict[str, Any]:
        require(actor, "study.create")
        if sponsor_id:
            self._get(actor, "sponsors", sponsor_id)
        if withdrawal_action_default not in ("retain", "delete"):
            raise ValidationFailed("withdrawal_action_default must be retain or delete")
        now = self.db.now_iso()
        row = {"id": new_id("std"), "org_id": actor.org_id, "sponsor_id": sponsor_id,
               "code": code, "title": title, "is_demo": int(bool(is_demo)), "status": "setup",
               "withdrawal_action_default": withdrawal_action_default,
               "min_cell_size": int(min_cell_size), "created_at": now, "updated_at": now}
        return self._insert(actor, "studies", row)

    def get_study(self, actor: Actor, study_id: str) -> dict[str, Any]:
        require(actor, "study.read")
        s = self._study(actor, study_id)
        s["sites"] = self.db.query(
            "SELECT s.* FROM sites s JOIN study_sites ss ON ss.site_id=s.id WHERE ss.study_id=?",
            (study_id,))
        return s

    def list_studies(self, actor: Actor) -> list[dict[str, Any]]:
        if actor.role in ("participant", "care_partner"):
            pids = [actor.participant_id] if actor.role == "participant" else list(actor.linked_participants)
            if not pids:
                return []
            q = ",".join("?" * len(pids))
            return self.db.query(
                f"SELECT id, code, title, is_demo, status FROM studies WHERE org_id=? AND id IN "
                f"(SELECT study_id FROM participants WHERE id IN ({q}))", [actor.org_id, *pids])
        require(actor, "study.read")
        return self.db.query("SELECT * FROM studies WHERE org_id=? ORDER BY created_at",
                             (actor.org_id,))

    def update_study(self, actor: Actor, study_id: str, changes: dict[str, Any], reason: str):
        require(actor, "study.update")
        allowed = {"title", "status", "sponsor_id", "withdrawal_action_default", "min_cell_size"}
        bad = set(changes) - allowed
        if bad:
            raise ValidationFailed(f"fields not updatable: {sorted(bad)}")
        if changes.get("status") not in (None, "setup", "active", "closed"):
            raise ValidationFailed("invalid status")
        return self._update(actor, "studies", study_id,
                            {**changes, "updated_at": self.db.now_iso()}, reason)

    def add_site_to_study(self, actor: Actor, study_id: str, site_id: str) -> None:
        require(actor, "study.update")
        self._study(actor, study_id)
        self._get(actor, "sites", site_id)
        self._insert(actor, "study_sites", {"study_id": study_id, "site_id": site_id,
                                            "org_id": actor.org_id},
                     audit_key=f"{study_id}:{site_id}")

    # ------------------------------------------------------------------ protocol & schedules
    def add_protocol_version(self, actor: Actor, study_id: str, version: str,
                             effective_date: str, summary: str = "",
                             consent_document_id: str = "") -> dict[str, Any]:
        require(actor, "protocol.manage")
        s = self._study(actor, study_id)
        date.fromisoformat(effective_date)
        row = {"id": new_id("prv"), "org_id": actor.org_id, "study_id": study_id,
               "version": version, "effective_date": effective_date, "summary": summary,
               "consent_document_id": consent_document_id, "is_demo": s["is_demo"],
               "created_at": self.db.now_iso()}
        return self._insert(actor, "protocol_versions", row)

    def list_protocol_versions(self, actor: Actor, study_id: str) -> list[dict[str, Any]]:
        require(actor, "study.read")
        self._study(actor, study_id)
        return self.db.query("SELECT * FROM protocol_versions WHERE study_id=? AND org_id=? "
                             "ORDER BY effective_date", (study_id, actor.org_id))

    def create_schedule(self, actor: Actor, study_id: str, name: str, definition: dict[str, Any],
                        protocol_version_id: Optional[str] = None) -> dict[str, Any]:
        require(actor, "schedule.manage")
        s = self._study(actor, study_id)
        if protocol_version_id:
            pv = self._get(actor, "protocol_versions", protocol_version_id)
            if pv["study_id"] != study_id:
                raise ValidationFailed("protocol version belongs to another study")
        validate_schedule(definition, set(self.instruments.versions()))
        row = {"id": new_id("sch"), "org_id": actor.org_id, "study_id": study_id,
               "protocol_version_id": protocol_version_id, "name": name,
               "definition_json": canonical_json(definition), "is_demo": s["is_demo"],
               "created_at": self.db.now_iso()}
        return self._insert(actor, "assessment_schedules", row)

    def list_schedules(self, actor: Actor, study_id: str) -> list[dict[str, Any]]:
        require(actor, "study.read")
        rows = self.db.query("SELECT * FROM assessment_schedules WHERE study_id=? AND org_id=?",
                             (study_id, actor.org_id))
        for r in rows:
            r["definition"] = jload(r.pop("definition_json"), {})
        return rows

    # ------------------------------------------------------------------ participants
    def create_participant(self, actor: Actor, study_id: str, site_id: str, *, cohort: str = "",
                           primary_modality: str = "", identifier: Optional[str] = None
                           ) -> dict[str, Any]:
        require(actor, "participant.create")
        s = self._study(actor, study_id)
        self._get(actor, "sites", site_id)
        if actor.role != "system" and site_id not in actor.site_ids:
            raise PermissionDenied("you are not assigned to this site")
        if not self.db.one("SELECT 1 FROM study_sites WHERE study_id=? AND site_id=?",
                           (study_id, site_id)):
            raise ValidationFailed("site does not participate in this study")
        if s["status"] == "closed":
            raise ValidationFailed("study is closed")
        now = self.db.now_iso()
        for _ in range(5):
            pid = new_pseudonym()
            if not self.db.one("SELECT 1 FROM participants WHERE id=?", (pid,)):
                break
        row = {"id": pid, "org_id": actor.org_id, "study_id": study_id, "site_id": site_id,
               "enrollment_state": "screening", "cohort": cohort,
               "primary_modality": primary_modality, "enrolled_on": None,
               "is_demo": s["is_demo"], "created_at": now, "updated_at": now}
        with self.db.tx():
            self._insert(actor, "participants", row)
            if identifier:
                self.set_reidentification(actor, pid, identifier)
        return row

    def get_participant(self, actor: Actor, pid: str) -> dict[str, Any]:
        return self._participant(actor, pid, "participant.read")

    def list_participants(self, actor: Actor, study_id: str) -> list[dict[str, Any]]:
        require(actor, "participant.read")
        self._study(actor, study_id)
        rows = self.db.query("SELECT * FROM participants WHERE study_id=? AND org_id=? "
                             "ORDER BY created_at", (study_id, actor.org_id))
        out = []
        for r in rows:
            try:
                self._check_scope(actor, r)
                out.append(r)
            except (NotFound, PermissionDenied):
                continue
        return out

    def set_reidentification(self, actor: Actor, pid: str, identifier: str) -> None:
        """Store the site's re-identification key, encrypted (AES-256-GCM, AAD = pseudonym)."""
        p = self._participant(actor, pid, "reid.write")
        if not identifier or not identifier.strip():
            raise ValidationFailed("identifier must be non-empty")
        scheme, blob = encrypt_field(identifier, pid)
        row = {"participant_id": pid, "org_id": actor.org_id, "study_id": p["study_id"],
               "site_id": p["site_id"], "enc_scheme": scheme, "enc_identifier": blob,
               "is_demo": p["is_demo"], "created_at": self.db.now_iso(),
               "created_by": actor.user_id}
        if self.db.one("SELECT 1 FROM reidentification_keys WHERE participant_id=?", (pid,)):
            raise Conflict("re-identification key exists; delete it first (with reason)")
        self._insert(actor, "reidentification_keys", row, audit_key=pid)

    def get_reidentification(self, actor: Actor, pid: str, reason: str) -> str:
        """Site staff only; every read is audited with its reason."""
        if not reason or not reason.strip():
            raise ReasonRequired("a reason is required to re-identify a participant")
        p = self._participant(actor, pid, "reid.read")
        r = self.db.one("SELECT * FROM reidentification_keys WHERE participant_id=? AND org_id=?",
                        (pid, actor.org_id))
        if r is None or r["site_id"] != p["site_id"]:
            raise NotFound("no re-identification key")
        self.audit.append(actor, "reidentify", "reidentification_keys", pid, reason=reason)
        return decrypt_field(r["enc_scheme"], r["enc_identifier"], pid)

    # ------------------------------------------------------------------ enrollment
    def transition(self, actor: Actor, pid: str, to_state: str, reason: str = "") -> dict[str, Any]:
        p = self._participant(actor, pid, "enrollment.transition")
        return self._transition(actor, p, to_state, reason)

    def _transition(self, actor: Actor, p: dict[str, Any], to_state: str, reason: str):
        frm = p["enrollment_state"]
        if to_state not in ENROLLMENT_STATES:
            raise ValidationFailed(f"unknown state {to_state!r}")
        if to_state not in TRANSITIONS[frm]:
            raise InvalidTransition(f"{frm} -> {to_state} is not allowed",
                                    allowed=sorted(TRANSITIONS[frm]))
        if to_state in REASON_REQUIRED_STATES and not (reason or "").strip():
            raise ReasonRequired(f"a reason is required to move to '{to_state}'")
        if to_state == "consented" and not self._active_consent(p["id"]):
            raise InvalidTransition("cannot mark consented without an active consent record")
        changes = {"enrollment_state": to_state, "updated_at": self.db.now_iso()}
        if to_state == "enrolled":
            changes["enrolled_on"] = self.db.now().date().isoformat()
        with self.db.tx():
            out = self._update(actor, "participants", p["id"], changes,
                               reason or f"enrollment transition {frm} -> {to_state}",
                               action="transition")
            self._insert(actor, "enrollment_events", {
                "id": new_id("enr"), "org_id": p["org_id"], "study_id": p["study_id"],
                "participant_id": p["id"], "from_state": frm, "to_state": to_state,
                "reason": reason or "", "at": self.db.now_iso(), "by_user": actor.user_id,
                "is_demo": p["is_demo"]})
        return out

    def enrollment_history(self, actor: Actor, pid: str) -> list[dict[str, Any]]:
        self._participant(actor, pid, "participant.read")
        return self.db.query("SELECT * FROM enrollment_events WHERE participant_id=? AND org_id=? "
                             "ORDER BY at", (pid, actor.org_id))

    # ------------------------------------------------------------------ visits
    def generate_visits(self, actor: Actor, pid: str, schedule_id: str,
                        anchor_date: Optional[str] = None) -> list[dict[str, Any]]:
        p = self._participant(actor, pid, "visit.manage")
        sch = self._get(actor, "assessment_schedules", schedule_id)
        if sch["study_id"] != p["study_id"]:
            raise ValidationFailed("schedule belongs to another study")
        anchor = date.fromisoformat(anchor_date or p["enrolled_on"] or
                                    self.db.now().date().isoformat())
        defn = jload(sch["definition_json"], {})
        created = []
        now = self.db.now_iso()
        with self.db.tx():
            for v in expand_schedule(defn, anchor):
                if self.db.one("SELECT 1 FROM visits WHERE participant_id=? AND visit_code=?",
                               (pid, v["visit_code"])):
                    continue
                row = {"id": new_id("vis"), "org_id": actor.org_id, "study_id": p["study_id"],
                       "participant_id": pid, "schedule_id": schedule_id,
                       "visit_code": v["visit_code"], "visit_type": v["visit_type"],
                       "target_date": v["target_date"].isoformat(),
                       "window_start": v["window_start"].isoformat(),
                       "window_end": v["window_end"].isoformat(), "status": "scheduled",
                       "completed_at": None, "tasks_json": json.dumps(v["tasks"]),
                       "instruments_json": json.dumps(v["instruments"]), "notes": "",
                       "is_demo": p["is_demo"], "created_at": now}
                self._insert(actor, "visits", row)
                for iid in v["instruments"]:
                    aid = new_id("qas")
                    self._insert(actor, "questionnaire_assignments", {
                        "id": aid, "org_id": actor.org_id, "study_id": p["study_id"],
                        "participant_id": pid, "visit_id": row["id"], "instrument_id": iid,
                        "due_date": row["window_end"], "status": "pending", "response_id": None,
                        "is_demo": p["is_demo"], "created_at": now})
                    for rd in sorted({row["target_date"], row["window_end"]}):
                        self._insert(actor, "reminders", {
                            "id": new_id("rem"), "org_id": actor.org_id,
                            "study_id": p["study_id"], "participant_id": pid,
                            "assignment_id": aid, "remind_on": rd, "channel": "record_only",
                            "status": "scheduled", "is_demo": p["is_demo"], "created_at": now})
                created.append(row)
        return created

    def list_visits(self, actor: Actor, pid: str) -> list[dict[str, Any]]:
        self._participant(actor, pid, "visit.read")
        rows = self.db.query("SELECT * FROM visits WHERE participant_id=? AND org_id=? "
                             "ORDER BY target_date, visit_code", (pid, actor.org_id))
        for r in rows:
            r["tasks"] = jload(r.pop("tasks_json"), [])
            r["instruments"] = jload(r.pop("instruments_json"), [])
        return rows

    def _visit_for(self, actor: Actor, visit_id: str, pid: str) -> dict[str, Any]:
        v = self._get(actor, "visits", visit_id)
        if v["participant_id"] != pid:
            raise ValidationFailed("visit belongs to another participant")
        return v

    def complete_visit(self, actor: Actor, visit_id: str, reason: str = "visit completed",
                       when: Optional[date] = None) -> dict[str, Any]:
        v = self._get(actor, "visits", visit_id)
        self._participant(actor, v["participant_id"],
                          None if actor.role == "system" else "session.upload")
        return self._complete_visit(actor, v, reason, when)

    def _complete_visit(self, actor: Actor, v: dict[str, Any], reason: str,
                        when: Optional[date] = None) -> dict[str, Any]:
        if v["status"] in ("completed", "completed_out_of_window"):
            return v
        if v["status"] == "cancelled":
            raise ValidationFailed("visit is cancelled")
        d = when or self.db.now().date()
        in_window = date.fromisoformat(v["window_start"]) <= d <= date.fromisoformat(v["window_end"])
        status = "completed" if in_window else "completed_out_of_window"
        with self.db.tx():
            out = self._update(actor, "visits", v["id"], {"status": status,
                                                          "completed_at": self.db.now_iso()}, reason)
            if not in_window:
                self._insert(actor, "protocol_deviations", {
                    "id": new_id("dev"), "org_id": v["org_id"], "study_id": v["study_id"],
                    "participant_id": v["participant_id"], "visit_id": v["id"],
                    "category": "visit_out_of_window",
                    "description": f"visit {v['visit_code']} completed on {d.isoformat()} outside "
                                   f"window {v['window_start']}..{v['window_end']}",
                    "severity": "minor", "status": "open", "is_demo": v["is_demo"],
                    "reported_at": self.db.now_iso(), "reported_by": actor.user_id},
                    reason="automatic deviation: out-of-window visit")
        return out

    def mark_missed_visits(self, actor: Actor, study_id: str) -> int:
        """Visits whose window has closed without completion -> missed (+ missing-data rows)."""
        if actor.role != "system":
            require(actor, "visit.manage")
        self._study(actor, study_id)
        today = self.db.now().date().isoformat()
        rows = self.db.query("SELECT * FROM visits WHERE study_id=? AND org_id=? AND "
                             "status='scheduled' AND window_end < ?", (study_id, actor.org_id, today))
        n = 0
        for v in rows:
            if actor.role != "system":
                try:
                    self._participant(actor, v["participant_id"])
                except (NotFound, PermissionDenied):
                    continue
            with self.db.tx():
                self._update(actor, "visits", v["id"], {"status": "missed"},
                             "visit window closed without completion")
                self._insert(actor, "missing_data", {
                    "id": new_id("mis"), "org_id": v["org_id"], "study_id": v["study_id"],
                    "participant_id": v["participant_id"], "visit_id": v["id"],
                    "item_type": "visit", "item_ref": v["visit_code"],
                    "reason_code": "missed_visit", "note": "", "is_demo": v["is_demo"],
                    "recorded_at": self.db.now_iso(), "recorded_by": actor.user_id})
                for a in self.db.query("SELECT id FROM questionnaire_assignments WHERE visit_id=? "
                                       "AND status='pending'", (v["id"],)):
                    self._update(actor, "questionnaire_assignments", a["id"], {"status": "missed"},
                                 "visit missed")
            n += 1
        return n

    # ------------------------------------------------------------------ devices
    def add_device_config(self, actor: Actor, pid: str, modality: str, make_model: str = "",
                          settings: Optional[dict] = None,
                          calibration_state: str = "unknown") -> dict[str, Any]:
        p = self._participant(actor, pid, "device.manage")
        if calibration_state not in ("unknown", "uncalibrated", "calibrated", "recalibration_due",
                                     "not_applicable"):
            raise ValidationFailed("invalid calibration_state")
        if len(make_model) > 200:
            raise ValidationFailed("make_model too long")
        row = {"id": new_id("dvc"), "org_id": actor.org_id, "study_id": p["study_id"],
               "participant_id": pid, "modality": modality, "make_model": make_model,
               "settings_json": canonical_json(settings or {}),
               "calibration_state": calibration_state, "is_demo": p["is_demo"],
               "created_at": self.db.now_iso()}
        return self._insert(actor, "device_configs", row)

    def list_device_configs(self, actor: Actor, pid: str) -> list[dict[str, Any]]:
        self._participant(actor, pid, "visit.read")
        return self.db.query("SELECT * FROM device_configs WHERE participant_id=? AND org_id=?",
                             (pid, actor.org_id))

    # ------------------------------------------------------------------ deviations & missing
    def report_deviation(self, actor: Actor, study_id: str, category: str, description: str,
                         severity: str = "minor", participant_id: Optional[str] = None,
                         visit_id: Optional[str] = None) -> dict[str, Any]:
        require(actor, "deviation.manage")
        s = self._study(actor, study_id)
        if participant_id:
            p = self._participant(actor, participant_id)
            if p["study_id"] != study_id:
                raise ValidationFailed("participant belongs to another study")
        if visit_id:
            self._visit_for(actor, visit_id, participant_id)
        if severity not in ("minor", "major"):
            raise ValidationFailed("severity must be minor or major")
        row = {"id": new_id("dev"), "org_id": actor.org_id, "study_id": study_id,
               "participant_id": participant_id, "visit_id": visit_id, "category": category,
               "description": description, "severity": severity, "status": "open",
               "is_demo": s["is_demo"], "reported_at": self.db.now_iso(),
               "reported_by": actor.user_id}
        return self._insert(actor, "protocol_deviations", row)

    def list_deviations(self, actor: Actor, study_id: str) -> list[dict[str, Any]]:
        require(actor, "deviation.manage")
        self._study(actor, study_id)
        rows = self.db.query("SELECT * FROM protocol_deviations WHERE study_id=? AND org_id=?",
                             (study_id, actor.org_id))
        return [r for r in rows if self._visible(actor, r)]

    def record_missing(self, actor: Actor, pid: str, item_type: str, item_ref: str,
                       reason_code: str, note: str = "",
                       visit_id: Optional[str] = None) -> dict[str, Any]:
        p = self._participant(actor, pid, "missing.record")
        if reason_code not in MISSING_REASONS:
            raise ValidationFailed(f"reason_code must be one of {MISSING_REASONS}")
        if visit_id:
            self._visit_for(actor, visit_id, pid)
        row = {"id": new_id("mis"), "org_id": actor.org_id, "study_id": p["study_id"],
               "participant_id": pid, "visit_id": visit_id, "item_type": item_type,
               "item_ref": item_ref, "reason_code": reason_code, "note": note,
               "is_demo": p["is_demo"], "recorded_at": self.db.now_iso(),
               "recorded_by": actor.user_id}
        return self._insert(actor, "missing_data", row)

    def _visible(self, actor: Actor, row: dict[str, Any]) -> bool:
        if not row.get("participant_id"):
            return True
        try:
            p = self.db.one("SELECT * FROM participants WHERE id=? AND org_id=?",
                            (row["participant_id"], actor.org_id))
            if p is None:
                return False
            self._check_scope(actor, p)
            return True
        except (NotFound, PermissionDenied):
            return False

    # ------------------------------------------------------------------ data queries
    def raise_query(self, actor: Actor, study_id: str, record_table: str, record_id: str,
                    question: str, field: str = "") -> dict[str, Any]:
        require(actor, "query.raise")
        s = self._study(actor, study_id)
        rec = self._get(actor, record_table, record_id)
        if rec.get("study_id") != study_id:
            raise ValidationFailed("record belongs to another study")
        if actor.role != "sponsor_analyst" and rec.get("participant_id"):
            self._participant(actor, rec["participant_id"])
        if not question.strip():
            raise ValidationFailed("question is required")
        row = {"id": new_id("qry"), "org_id": actor.org_id, "study_id": study_id,
               "participant_id": rec.get("participant_id"), "record_table": record_table,
               "record_id": record_id, "field": field, "question": question, "status": "open",
               "answer": "", "raised_by": actor.user_id, "raised_at": self.db.now_iso(),
               "answered_by": None, "answered_at": None, "closed_by": None, "closed_at": None,
               "is_demo": s["is_demo"]}
        return self._insert(actor, "data_queries", row)

    def answer_query(self, actor: Actor, qid: str, answer: str) -> dict[str, Any]:
        require(actor, "query.answer")
        q = self._get(actor, "data_queries", qid)
        if q["participant_id"]:
            self._participant(actor, q["participant_id"])
        if q["status"] != "open":
            raise InvalidTransition(f"query is {q['status']}")
        if not answer.strip():
            raise ValidationFailed("answer is required")
        return self._update(actor, "data_queries", qid, {
            "status": "answered", "answer": answer, "answered_by": actor.user_id,
            "answered_at": self.db.now_iso()}, "query answered", action="query_answer")

    def close_query(self, actor: Actor, qid: str, reason: str) -> dict[str, Any]:
        require(actor, "query.close")
        q = self._get(actor, "data_queries", qid)
        if q["status"] == "closed":
            raise InvalidTransition("query already closed")
        if q["status"] == "open" and not reason.strip():
            raise ReasonRequired("closing an unanswered query requires a reason")
        return self._update(actor, "data_queries", qid, {
            "status": "closed", "closed_by": actor.user_id, "closed_at": self.db.now_iso()},
            reason or "query closed", action="query_close")

    def reopen_query(self, actor: Actor, qid: str, reason: str) -> dict[str, Any]:
        require(actor, "query.close")
        q = self._get(actor, "data_queries", qid)
        if q["status"] != "answered":
            raise InvalidTransition("only answered queries can be re-opened")
        return self._update(actor, "data_queries", qid, {"status": "open"}, reason,
                            action="query_reopen")

    def list_queries(self, actor: Actor, study_id: str, status: Optional[str] = None):
        if actor.role not in ("coordinator", "investigator", "sponsor_analyst"):
            raise PermissionDenied("queries not visible to this role")
        self._study(actor, study_id)
        sql = "SELECT * FROM data_queries WHERE study_id=? AND org_id=?"
        params: list[Any] = [study_id, actor.org_id]
        if status:
            sql += " AND status=?"
            params.append(status)
        rows = self.db.query(sql, params)
        if actor.role == "sponsor_analyst":
            return rows  # pseudonymous only (no re-identification data in this table)
        return [r for r in rows if self._visible(actor, r)]

    # ------------------------------------------------------------------ signatures & review
    def sign(self, actor: Actor, password: str, record_table: str, record_id: str,
             meaning: str) -> dict[str, Any]:
        """Electronic signature: re-authentication, then a signature record bound to the
        SHA-256 of the signed record's content (manifestation: signer name, meaning, UTC time)."""
        if meaning == "approved":
            require(actor, "signature.approve")
        elif meaning in ("reviewed", "verified", "authored"):
            require(actor, "signature.review")
        else:
            raise ValidationFailed("meaning must be authored, reviewed, approved or verified")
        if record_table == "casebook":
            p = self._participant(actor, record_id)
            study_id, is_demo = p["study_id"], p["is_demo"]
        else:
            rec = self._get(actor, record_table, record_id)
            if rec.get("participant_id"):
                self._participant(actor, rec["participant_id"])
            study_id, is_demo = rec.get("study_id"), rec.get("is_demo", 0)
        self.reauthenticate(actor, password)
        rh = self.record_hash(actor, record_table, record_id)
        row = {"id": new_id("sig"), "org_id": actor.org_id, "study_id": study_id,
               "signer_user_id": actor.user_id, "signer_username": actor.username,
               "signer_display_name": actor.display_name or actor.username,
               "signer_role": actor.role, "meaning": meaning, "record_table": record_table,
               "record_id": record_id, "record_hash": rh, "reauth_method": "password",
               "signed_at": self.db.now_iso(), "is_demo": is_demo}
        self._insert(actor, "e_signatures", row, reason=f"electronic signature: {meaning}")
        return row

    def verify_signature(self, actor: Actor, sig_id: str) -> dict[str, Any]:
        sig = self._get(actor, "e_signatures", sig_id)
        try:
            current = self.record_hash(actor, sig["record_table"], sig["record_id"])
        except NotFound:
            current = None
        status = ("valid" if current == sig["record_hash"] else
                  "record_deleted" if current is None else "record_changed_since_signing")
        return {"signature": sig, "current_hash": current, "status": status}

    def list_signatures(self, actor: Actor, record_table: str, record_id: str):
        return self.db.query("SELECT * FROM e_signatures WHERE org_id=? AND record_table=? AND "
                             "record_id=? ORDER BY signed_at", (actor.org_id, record_table,
                                                                record_id))

    # ------------------------------------------------------------------ corrections
    def correct_record(self, actor: Actor, table: str, record_id: str, changes: dict[str, Any],
                       reason: str) -> dict[str, Any]:
        """Data correction with mandatory reason; old/new values go to the audit trail."""
        require(actor, "data.correct")
        if not isinstance(reason, str) or not reason.strip():
            raise ReasonRequired("a reason for change is required for every correction")
        if table not in CORRECTABLE:
            raise ValidationFailed(f"records of {table} are not correctable")
        bad = set(changes) - CORRECTABLE[table]
        if bad:
            raise ValidationFailed(f"fields not correctable: {sorted(bad)}")
        rec = self._get(actor, table, record_id)
        if rec.get("participant_id"):
            self._participant(actor, rec["participant_id"])
        elif table == "participants":
            self._participant(actor, record_id)
        if table == "questionnaire_responses":
            return self._correct_response(actor, rec, changes["answers"], reason)
        if "settings_json" in changes and not isinstance(changes["settings_json"], str):
            changes = {**changes, "settings_json": canonical_json(changes["settings_json"])}
        if table == "functional_sessions" and changes.get("status") not in ("valid", "invalidated"):
            raise ValidationFailed("status must be valid or invalidated")
        return self._update(actor, table, record_id, changes, reason, action="correction")

    def record_history(self, actor: Actor, table: str, record_id: str) -> list[dict[str, Any]]:
        require(actor, "record.history")
        rec = self.db.one(f"SELECT * FROM {_safe(table)} WHERE id=? AND org_id=?",
                          (record_id, actor.org_id)) if "id" in _cols(self, table) else None
        if rec is not None and rec.get("participant_id") and actor.role != "admin":
            self._participant(actor, rec["participant_id"])
        return self.audit.history(actor.org_id, table, record_id)


def _safe(table: str) -> str:
    from .core import _check_table
    return _check_table(table)


def _cols(svc: StudyServiceBase, table: str) -> set[str]:
    return {c["name"] for c in svc.db.columns(_safe(table))}
