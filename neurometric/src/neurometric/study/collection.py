"""Data collection: functional testing sessions (canonical events) and questionnaire responses."""
from __future__ import annotations

import json
import zlib
from typing import Any, Optional

from ..events.model import (EventKind, EventValidationError, InputEvent, check_stream,
                            validate_event)
from ..instruments.engine import ResponseError, score as score_instrument, validate_response
from ..tasks.battery import BATTERY_VERSION, stimuli as battery_stimuli
from .core import StudyServiceBase, jload, new_id
from .db import canonical_json, sha256_hex
from .errors import ConsentRequired, NotFound, ValidationFailed
from .permissions import Actor, require
from .scoring import SCORER_VERSION, TASK_IDS, score_session

MAX_EVENTS = 200_000
TEXT_ALLOWED_TASKS = frozenset({"E1"})  # copy typing of predefined phrases only


def compress_events(events: list[dict[str, Any]]) -> tuple[bytes, str]:
    raw = canonical_json(events).encode("utf-8")
    return zlib.compress(raw, 9), sha256_hex(raw)


def decompress_events(blob: bytes) -> list[dict[str, Any]]:
    return json.loads(zlib.decompress(blob).decode("utf-8"))


class CollectionMixin(StudyServiceBase):
    # ------------------------------------------------------------------ functional sessions
    def upload_session(self, actor: Actor, pid: str, *, task_id: str, events: list[dict[str, Any]],
                       stimulus_seed: int, stimulus_hash: str,
                       battery_version: str = BATTERY_VERSION, visit_id: Optional[str] = None,
                       device_config_id: Optional[str] = None, provenance: str = "live",
                       modality: Optional[str] = None) -> dict[str, Any]:
        p = self._participant(actor, pid, "session.upload")
        if p["enrollment_state"] not in ("enrolled", "active"):
            raise ValidationFailed(f"participant is '{p['enrollment_state']}': collection is only "
                                   "allowed while enrolled or active", code="not_collecting")
        self._require_consent(pid, "task_battery")
        if task_id not in TASK_IDS:
            raise ValidationFailed(f"unknown task {task_id!r}")
        if battery_version != BATTERY_VERSION:
            raise ValidationFailed(f"battery version {battery_version} is not supported by this "
                                   f"server ({BATTERY_VERSION})", code="battery_version")
        if provenance not in ("live", "simulated", "replayed"):
            raise ValidationFailed("provenance must be live, simulated or replayed")
        stim = battery_stimuli(task_id, int(stimulus_seed))
        if stim["stimulus_hash"] != stimulus_hash:
            raise ValidationFailed("stimulus_hash does not match the server's stimuli for this "
                                   "task, seed and battery version", code="stimulus_mismatch",
                                   expected=stim["stimulus_hash"])
        if not isinstance(events, list) or not events:
            raise ValidationFailed("events must be a non-empty list")
        if len(events) > MAX_EVENTS:
            raise ValidationFailed(f"too many events (> {MAX_EVENTS})")
        parsed: list[InputEvent] = []
        errors = []
        for i, d in enumerate(events):
            try:
                ev = InputEvent.from_dict(d)
                validate_event(ev)
                parsed.append(ev)
            except (EventValidationError, KeyError, TypeError, ValueError) as e:
                errors.append(f"event {i}: {e}")
                if len(errors) >= 20:
                    break
        if errors:
            raise ValidationFailed("invalid canonical events", errors=errors)
        sids = {e.session_id for e in parsed}
        if len(sids) != 1:
            raise ValidationFailed("all events of an upload must share one session_id")
        synthetic = any(e.synthetic for e in parsed)
        if synthetic and not p["is_demo"] and provenance != "simulated":
            raise ValidationFailed("synthetic events must be declared provenance='simulated'",
                                   code="synthetic_provenance")
        if synthetic and not p["is_demo"]:
            raise ValidationFailed("synthetic events cannot be stored in a non-demo study",
                                   code="demo_mix")
        has_text = any(e.kind == EventKind.TEXT_INPUT or (e.kind == EventKind.KEY and e.key and
                       len(e.key) == 1) for e in parsed)
        if has_text and task_id not in TEXT_ALLOWED_TASKS and not self.has_consent(pid, "free_text"):
            raise ConsentRequired("text input outside copy-typing tasks requires free_text "
                                  "consent", scope="free_text")
        report = check_stream(parsed)
        if report["duplicate_seq"]:
            raise ValidationFailed("duplicate (stream_id, seq) pairs in event stream",
                                   code="duplicate_events", report=report)
        if visit_id:
            visit = self._visit_for(actor, visit_id, pid)
        else:
            visit = None
        if device_config_id:
            dc = self._get(actor, "device_configs", device_config_id)
            if dc["participant_id"] != pid:
                raise ValidationFailed("device configuration belongs to another participant")
        metrics = score_session(task_id, parsed, int(stimulus_seed), stim)
        blob, digest = compress_events([e.to_dict() for e in parsed])
        if self.db.one("SELECT id FROM functional_sessions WHERE participant_id=? AND "
                       "events_sha256=?", (pid, digest)):
            raise ValidationFailed("this event stream was already uploaded",
                                   code="duplicate_upload")
        mod = modality or parsed[0].modality.value
        row = {"id": new_id("ses"), "org_id": actor.org_id, "study_id": p["study_id"],
               "participant_id": pid, "visit_id": visit_id, "device_config_id": device_config_id,
               "task_id": task_id, "battery_version": battery_version,
               "stimulus_seed": int(stimulus_seed), "stimulus_hash": stimulus_hash,
               "modality": mod, "provenance": provenance, "events_blob": blob,
               "events_sha256": digest, "n_events": len(parsed), "raw_purged": 0,
               "stream_report_json": canonical_json(report), "metrics_json": canonical_json(metrics),
               "scorer_version": SCORER_VERSION, "status": "valid", "is_demo": p["is_demo"],
               "uploaded_at": self.db.now_iso(), "uploaded_by": actor.user_id}
        with self.db.tx():
            self._insert(actor, "functional_sessions", row)
            if p["enrollment_state"] == "enrolled":
                self._transition(actor, p, "active", "first functional session uploaded")
            if visit is not None:
                self._complete_visit(actor, visit, "functional session uploaded")
        return self._session_view(row)

    def _session_view(self, row: dict[str, Any], include_events: bool = False) -> dict[str, Any]:
        out = {k: v for k, v in row.items() if k not in ("events_blob", "metrics_json",
                                                          "stream_report_json")}
        out["metrics"] = jload(row["metrics_json"], {})
        out["stream_report"] = jload(row["stream_report_json"], {})
        if include_events and row.get("events_blob"):
            out["events"] = decompress_events(row["events_blob"])
        return out

    def get_session(self, actor: Actor, session_id: str, include_events: bool = False):
        require(actor, "session.read")
        row = self._get(actor, "functional_sessions", session_id)
        self._participant(actor, row["participant_id"])
        return self._session_view(row, include_events)

    def list_sessions(self, actor: Actor, pid: str) -> list[dict[str, Any]]:
        self._participant(actor, pid, "session.read")
        rows = self.db.query("SELECT * FROM functional_sessions WHERE participant_id=? AND "
                             "org_id=? ORDER BY uploaded_at", (pid, actor.org_id))
        return [self._session_view(r) for r in rows]

    def verify_session_integrity(self, session_row: dict[str, Any]) -> bool:
        if session_row.get("events_blob") is None:
            return bool(session_row.get("raw_purged"))
        try:
            raw = zlib.decompress(session_row["events_blob"])
        except zlib.error:
            return False
        return sha256_hex(raw) == session_row["events_sha256"]

    # ------------------------------------------------------------------ questionnaires
    def submit_response(self, actor: Actor, pid: str, instrument_id: str,
                        answers: dict[str, Any], *, version: Optional[str] = None,
                        visit_id: Optional[str] = None, language: str = "en") -> dict[str, Any]:
        p = self._participant(actor, pid, "questionnaire.respond")
        if p["enrollment_state"] not in ("consented", "enrolled", "active"):
            raise ValidationFailed(f"participant is '{p['enrollment_state']}': collection is not "
                                   "allowed", code="not_collecting")
        self._require_consent(pid, "questionnaires")
        try:
            inst = self.instruments.get(instrument_id, version)
        except KeyError:
            raise NotFound(f"instrument {instrument_id}@{version or 'latest'} not found") from None
        rt = inst.definition["respondent_type"]
        allowed_roles = {"PRO": {"participant", "coordinator", "investigator"},
                         "ObsRO": {"care_partner", "coordinator", "investigator"},
                         "ClinRO": {"coordinator", "investigator"},
                         "PerfO": {"coordinator", "investigator"}}[rt]
        if actor.role not in allowed_roles:
            raise ValidationFailed(f"{instrument_id} is a {rt} instrument; role '{actor.role}' "
                                   "cannot submit it", code="respondent_type")
        lang_status = inst.definition["languages"].get(language)
        if lang_status != "source":
            raise ValidationFailed(f"language {language!r}: {lang_status or 'not available'}",
                                   code="translation_unavailable")
        try:
            clean, free, missing = validate_response(
                inst, answers, allow_free_text=self.has_consent(pid, "free_text"))
        except ResponseError as e:
            code = "license_required" if "license_required" in e.errors else "invalid_response"
            raise ValidationFailed(str(e), code=code, errors=e.errors) from None
        if visit_id:
            self._visit_for(actor, visit_id, pid)
        scores = score_instrument(inst, clean)
        row = {"id": new_id("qrs"), "org_id": actor.org_id, "study_id": p["study_id"],
               "participant_id": pid, "visit_id": visit_id, "instrument_id": inst.id,
               "instrument_version": inst.version, "respondent_type": rt,
               "respondent_role": actor.role, "answers_json": canonical_json(clean),
               "free_text_json": canonical_json(free) if free else None,
               "score_json": canonical_json({"scales": scores, "missing_items": missing}),
               "completion": "partial" if missing else "complete", "language": language,
               "is_demo": p["is_demo"], "submitted_at": self.db.now_iso(),
               "submitted_by": actor.user_id}
        with self.db.tx():
            self._insert(actor, "questionnaire_responses", row)
            asg = self.db.one(
                "SELECT * FROM questionnaire_assignments WHERE participant_id=? AND "
                "instrument_id=? AND status='pending' AND (visit_id IS ? OR ? IS NULL) "
                "ORDER BY due_date LIMIT 1", (pid, inst.id, visit_id, visit_id))
            if asg:
                self._update(actor, "questionnaire_assignments", asg["id"],
                             {"status": "completed", "response_id": row["id"]},
                             "questionnaire completed")
                self.db.execute("UPDATE reminders SET status='cancelled' WHERE assignment_id=? "
                                "AND status='scheduled'", (asg["id"],))
        return self._response_view(row)

    def _response_view(self, row: dict[str, Any], include_free_text: bool = False):
        out = {k: v for k, v in row.items() if k not in ("answers_json", "score_json",
                                                          "free_text_json")}
        out["answers"] = jload(row["answers_json"], {})
        sc = jload(row["score_json"], {})
        out["scores"] = sc.get("scales", {})
        out["missing_items"] = sc.get("missing_items", [])
        out["has_free_text"] = bool(row.get("free_text_json"))
        if include_free_text and row.get("free_text_json"):
            out["free_text"] = jload(row["free_text_json"], {})
        return out

    def list_responses(self, actor: Actor, pid: str) -> list[dict[str, Any]]:
        self._participant(actor, pid, "questionnaire.read")
        rows = self.db.query("SELECT * FROM questionnaire_responses WHERE participant_id=? AND "
                             "org_id=? ORDER BY submitted_at", (pid, actor.org_id))
        own = actor.role in ("participant", "care_partner")
        return [self._response_view(r, include_free_text=own or actor.role in
                                    ("coordinator", "investigator")) for r in rows]

    def list_assignments(self, actor: Actor, pid: str) -> list[dict[str, Any]]:
        self._participant(actor, pid, "questionnaire.read")
        rows = self.db.query("SELECT * FROM questionnaire_assignments WHERE participant_id=? AND "
                             "org_id=? ORDER BY due_date", (pid, actor.org_id))
        for r in rows:
            r["reminders"] = self.db.query("SELECT remind_on, channel, status FROM reminders "
                                           "WHERE assignment_id=? ORDER BY remind_on", (r["id"],))
        return rows

    def _correct_response(self, actor: Actor, rec: dict[str, Any], answers: dict[str, Any],
                          reason: str) -> dict[str, Any]:
        inst = self.instruments.get(rec["instrument_id"], rec["instrument_version"])
        try:
            clean, free, missing = validate_response(
                inst, answers, allow_free_text=self.has_consent(rec["participant_id"], "free_text"))
        except ResponseError as e:
            raise ValidationFailed(str(e), errors=e.errors) from None
        scores = score_instrument(inst, clean)
        changes = {"answers_json": canonical_json(clean),
                   "score_json": canonical_json({"scales": scores, "missing_items": missing}),
                   "completion": "partial" if missing else "complete"}
        if free:
            changes["free_text_json"] = canonical_json(free)
        row = self._update(actor, "questionnaire_responses", rec["id"], changes, reason,
                           action="correction")
        return self._response_view(row)
