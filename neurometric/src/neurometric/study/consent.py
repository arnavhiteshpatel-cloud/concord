"""Consent records, withdrawal handling, retention policies with a purge job, and data-subject
export / deletion."""
from __future__ import annotations

from datetime import timedelta
from typing import Any, Iterable, Optional

from .audit import SYSTEM
from .collection import decompress_events
from .core import StudyServiceBase, jload, new_id
from .db import canonical_json, iso
from .errors import InvalidTransition, ReasonRequired, ValidationFailed
from .permissions import Actor, require

CONSENT_SCOPES = {
    "task_battery": "Functional task battery sessions (canonical input events and scores).",
    "questionnaires": "Questionnaire responses (structured answers).",
    "home_telemetry": "Aggregate home usage summaries from the NeuroMetric app (no content).",
    "telemetry_app_categories": "Coarse app-category minutes within home telemetry.",
    "free_text": "Optional free-text answers / text typed outside copy-typing tasks.",
    "audio_none": "Acknowledgement that NeuroMetric records no audio (always true).",
    "sharing_with_sponsor": "Pseudonymous data may be shared with the study sponsor.",
    "future_research": "Pseudonymous data may be reused for future research.",
}
#: data categories deleted per withdrawn scope when the withdrawal action is 'delete'
SCOPE_DATA = {
    "task_battery": ["functional_sessions"],
    "questionnaires": ["questionnaire_responses"],
    "home_telemetry": ["telemetry_batches"],
    "telemetry_app_categories": [],
    "free_text": ["free_text"],
    "sharing_with_sponsor": [],
    "future_research": [],
    "audio_none": [],
}

#: Retention data categories -> how the purge job applies them.
RETENTION_CATEGORIES = {
    "raw_events": "Compressed raw canonical event blobs (metrics are kept).",
    "functional_sessions": "Whole functional session records (metadata, metrics, raw).",
    "questionnaire_responses": "Questionnaire responses.",
    "questionnaire_free_text": "Free-text answers inside questionnaire responses.",
    "telemetry": "Aggregate telemetry batches.",
    "telemetry_receipts": "Telemetry receipt log (outcomes and reason codes).",
}


class ConsentMixin(StudyServiceBase):
    # ------------------------------------------------------------------ consent
    def record_consent(self, actor: Actor, pid: str, consent_document_id: str,
                       consent_version: str, scopes: dict[str, bool]) -> dict[str, Any]:
        p = self._participant(actor, pid, "consent.record")
        unknown = set(scopes) - set(CONSENT_SCOPES)
        if unknown:
            raise ValidationFailed(f"unknown consent scopes {sorted(unknown)}")
        if not all(isinstance(v, bool) for v in scopes.values()):
            raise ValidationFailed("consent scope values must be true/false")
        if p["enrollment_state"] in ("withdrawn", "completed"):
            raise InvalidTransition(f"participant is {p['enrollment_state']}")
        full = {k: bool(scopes.get(k, False)) for k in CONSENT_SCOPES}
        full["audio_none"] = True
        if full["telemetry_app_categories"] and not full["home_telemetry"]:
            raise ValidationFailed("telemetry_app_categories requires home_telemetry")
        now = self.db.now_iso()
        row = {"id": new_id("cns"), "org_id": actor.org_id, "study_id": p["study_id"],
               "participant_id": pid, "consent_document_id": consent_document_id,
               "consent_version": consent_version, "scopes_json": canonical_json(full),
               "status": "active", "given_at": now, "recorded_by": actor.user_id,
               "ended_at": None, "is_demo": p["is_demo"]}
        with self.db.tx():
            for old in self.db.query("SELECT id FROM consent_records WHERE participant_id=? AND "
                                     "status='active'", (pid,)):
                self._update(actor, "consent_records", old["id"],
                             {"status": "superseded", "ended_at": now},
                             "superseded by new consent record")
            self._insert(actor, "consent_records", row)
            self._sync_telemetry_state(actor, p, full)
        return {**row, "scopes": full}

    def _sync_telemetry_state(self, actor: Actor, p: dict[str, Any], scopes: dict[str, bool]):
        st = self.db.one("SELECT * FROM telemetry_state WHERE participant_id=?", (p["id"],))
        target = "active" if scopes.get("home_telemetry") else "stopped"
        if st is None:
            self._insert(actor, "telemetry_state", {
                "participant_id": p["id"], "org_id": p["org_id"], "study_id": p["study_id"],
                "state": target, "updated_at": self.db.now_iso(), "updated_by": actor.user_id,
                "is_demo": p["is_demo"]}, audit_key=p["id"])
        elif target == "stopped" and st["state"] != "stopped":
            self.db.execute("UPDATE telemetry_state SET state='stopped', updated_at=?, "
                            "updated_by=? WHERE participant_id=?",
                            (self.db.now_iso(), actor.user_id, p["id"]))
            self.audit.append(actor, "update", "telemetry_state", p["id"], org_id=p["org_id"],
                              reason="consent scope home_telemetry not active",
                              old={"state": st["state"]}, new={"state": "stopped"})
        elif target == "active" and st["state"] == "stopped":
            self.db.execute("UPDATE telemetry_state SET state='active', updated_at=?, "
                            "updated_by=? WHERE participant_id=?",
                            (self.db.now_iso(), actor.user_id, p["id"]))
            self.audit.append(actor, "update", "telemetry_state", p["id"], org_id=p["org_id"],
                              reason="home_telemetry consent given",
                              old={"state": "stopped"}, new={"state": "active"})

    def get_consent(self, actor: Actor, pid: str) -> dict[str, Any]:
        self._participant(actor, pid, "consent.read")
        return self._consent_view(actor.org_id, pid)

    def _consent_view(self, org_id: str, pid: str) -> dict[str, Any]:
        actor = Actor("system", org_id, "system")
        rows = self.db.query("SELECT * FROM consent_records WHERE participant_id=? AND org_id=? "
                             "ORDER BY given_at", (pid, actor.org_id))
        for r in rows:
            r["scopes"] = jload(r.pop("scopes_json"), {})
        wd = self.db.query("SELECT * FROM consent_withdrawals WHERE participant_id=? AND org_id=? "
                           "ORDER BY at", (pid, actor.org_id))
        for w in wd:
            w["scopes"] = jload(w.pop("scopes_json"), [])
            w["deleted_counts"] = jload(w.pop("deleted_counts_json"), {})
        active = next((r for r in rows if r["status"] == "active"), None)
        return {"active": active, "history": rows, "withdrawals": wd}

    def withdraw_consent(self, actor: Actor, pid: str, reason: str, *,
                         scopes: Optional[Iterable[str]] = None,
                         action: Optional[str] = None) -> dict[str, Any]:
        """Withdraw consent (fully, or for some scopes). Collection stops immediately; the
        protocol's action ('retain' collected data or 'delete' it) is applied and recorded."""
        p = self._participant(actor, pid, "consent.withdraw")
        if not reason or not reason.strip():
            raise ReasonRequired("a reason (may be 'participant choice') is required")
        study = self.db.one("SELECT * FROM studies WHERE id=?", (p["study_id"],))
        action = action or study["withdrawal_action_default"]
        if action not in ("retain", "delete"):
            raise ValidationFailed("action must be retain or delete")
        current = self._active_consent(pid)
        if current is None:
            raise InvalidTransition("no active consent to withdraw")
        full = scopes is None
        withdrawn = sorted(k for k, v in current["scopes"].items() if v) if full else sorted(scopes)
        unknown = set(withdrawn) - set(CONSENT_SCOPES)
        if unknown:
            raise ValidationFailed(f"unknown scopes {sorted(unknown)}")
        now = self.db.now_iso()
        counts: dict[str, int] = {}
        with self.db.tx():
            if full:
                self._update(actor, "consent_records", current["id"],
                             {"status": "withdrawn", "ended_at": now}, f"consent withdrawn: {reason}")
                self._set_telemetry(actor, p, "stopped", "consent withdrawn")
                if p["enrollment_state"] not in ("withdrawn", "completed"):
                    self._transition(actor, p, "withdrawn", f"consent withdrawn: {reason}")
                for v in self.db.query("SELECT id FROM visits WHERE participant_id=? AND "
                                       "status='scheduled'", (pid,)):
                    self._update(actor, "visits", v["id"], {"status": "cancelled"},
                                 "consent withdrawn")
                for a in self.db.query("SELECT id FROM questionnaire_assignments WHERE "
                                       "participant_id=? AND status='pending'", (pid,)):
                    self._update(actor, "questionnaire_assignments", a["id"],
                                 {"status": "cancelled"}, "consent withdrawn")
                self.db.execute("UPDATE reminders SET status='cancelled' WHERE participant_id=? "
                                "AND status='scheduled'", (pid,))
            else:
                new_scopes = {**current["scopes"], **{s: False for s in withdrawn}}
                if "home_telemetry" in withdrawn:
                    new_scopes["telemetry_app_categories"] = False
                self._update(actor, "consent_records", current["id"],
                             {"status": "superseded", "ended_at": now},
                             f"partial withdrawal: {reason}")
                self._insert(actor, "consent_records", {
                    "id": new_id("cns"), "org_id": p["org_id"], "study_id": p["study_id"],
                    "participant_id": pid, "consent_document_id": current["consent_document_id"],
                    "consent_version": current["consent_version"],
                    "scopes_json": canonical_json(new_scopes), "status": "active",
                    "given_at": now, "recorded_by": actor.user_id, "ended_at": None,
                    "is_demo": p["is_demo"]}, reason=f"partial withdrawal of {withdrawn}")
                if not new_scopes.get("home_telemetry"):
                    self._set_telemetry(actor, p, "stopped", "home_telemetry consent withdrawn")
            if action == "delete":
                cats = set()
                for s in withdrawn:
                    cats.update(SCOPE_DATA.get(s, []))
                counts = self._delete_participant_data(actor, p, cats,
                                                       f"consent withdrawal ({reason}): delete per protocol")
            w = {"id": new_id("cwd"), "org_id": p["org_id"], "study_id": p["study_id"],
                 "participant_id": pid, "scopes_json": canonical_json(withdrawn),
                 "full_withdrawal": int(full), "action": action, "reason": reason,
                 "deleted_counts_json": canonical_json(counts), "at": now,
                 "by_user": actor.user_id, "is_demo": p["is_demo"]}
            self._insert(actor, "consent_withdrawals", w, reason=reason)
        return {"withdrawal_id": w["id"], "full_withdrawal": full, "scopes": withdrawn,
                "action": action, "deleted_counts": counts}

    def _set_telemetry(self, actor: Actor, p: dict[str, Any], state: str, reason: str) -> None:
        st = self.db.one("SELECT * FROM telemetry_state WHERE participant_id=?", (p["id"],))
        if st is None or st["state"] == state:
            return
        self.db.execute("UPDATE telemetry_state SET state=?, updated_at=?, updated_by=? WHERE "
                        "participant_id=?", (state, self.db.now_iso(), actor.user_id, p["id"]))
        self.audit.append(actor, "update", "telemetry_state", p["id"], org_id=p["org_id"],
                          reason=reason, old={"state": st["state"]}, new={"state": state})

    def _delete_participant_data(self, actor: Actor, p: dict[str, Any], categories: set[str],
                                 reason: str) -> dict[str, int]:
        a = actor if actor.org_id == p["org_id"] else Actor(actor.user_id, p["org_id"],
                                                            actor.role, actor.username)
        counts: dict[str, int] = {}
        pid = p["id"]
        if "functional_sessions" in categories:
            counts["functional_sessions"] = self._delete_where(
                a, "functional_sessions", "participant_id=?", [pid], reason)
        if "questionnaire_responses" in categories:
            self.db.execute("UPDATE questionnaire_assignments SET response_id=NULL WHERE "
                            "participant_id=?", (pid,))
            counts["questionnaire_responses"] = self._delete_where(
                a, "questionnaire_responses", "participant_id=?", [pid], reason)
        if "telemetry_batches" in categories:
            counts["telemetry_batches"] = self._delete_where(
                a, "telemetry_batches", "participant_id=?", [pid], reason)
        if "free_text" in categories:
            rows = self.db.query("SELECT id FROM questionnaire_responses WHERE participant_id=? "
                                 "AND free_text_json IS NOT NULL", (pid,))
            for r in rows:
                self._update(a, "questionnaire_responses", r["id"], {"free_text_json": None},
                             reason, action="delete_free_text")
            counts["free_text_answers"] = len(rows)
        return counts

    # ------------------------------------------------------------------ retention
    def set_retention_policy(self, actor: Actor, study_id: str, data_category: str,
                             retain_days: int) -> dict[str, Any]:
        require(actor, "retention.manage")
        s = self._study(actor, study_id)
        if data_category not in RETENTION_CATEGORIES:
            raise ValidationFailed(f"data_category must be one of {sorted(RETENTION_CATEGORIES)}")
        if not isinstance(retain_days, int) or retain_days < 0:
            raise ValidationFailed("retain_days must be a non-negative integer")
        existing = self.db.one("SELECT * FROM retention_policies WHERE study_id=? AND "
                               "data_category=?", (study_id, data_category))
        if existing:
            return self._update(actor, "retention_policies", existing["id"],
                                {"retain_days": retain_days}, "retention policy changed")
        row = {"id": new_id("ret"), "org_id": actor.org_id, "study_id": study_id,
               "data_category": data_category, "retain_days": retain_days,
               "is_demo": s["is_demo"], "created_at": self.db.now_iso()}
        return self._insert(actor, "retention_policies", row)

    def list_retention_policies(self, actor: Actor, study_id: str) -> list[dict[str, Any]]:
        require(actor, "retention.manage")
        return self.db.query("SELECT * FROM retention_policies WHERE study_id=? AND org_id=?",
                             (study_id, actor.org_id))

    def run_retention_purge(self, actor: Actor) -> list[dict[str, Any]]:
        """Apply every retention policy of the actor's organization (records older than
        ``retain_days`` by their server time stamp are purged; each run is logged + audited)."""
        require(actor, "retention.run")
        out = []
        now = self.db.now()
        for pol in self.db.query("SELECT * FROM retention_policies WHERE org_id=?",
                                 (actor.org_id,)):
            cutoff = iso(now - timedelta(days=pol["retain_days"]))
            reason = (f"retention purge: {pol['data_category']} older than "
                      f"{pol['retain_days']} days (policy {pol['id']})")
            sid = pol["study_id"]
            cat = pol["data_category"]
            with self.db.tx():
                if cat == "raw_events":
                    rows = self.db.query("SELECT id FROM functional_sessions WHERE study_id=? AND "
                                         "uploaded_at < ? AND raw_purged=0", (sid, cutoff))
                    for r in rows:
                        self._update(actor, "functional_sessions", r["id"],
                                     {"events_blob": None, "raw_purged": 1}, reason,
                                     action="purge_raw")
                    n = len(rows)
                elif cat == "functional_sessions":
                    n = self._delete_where(actor, "functional_sessions",
                                           "study_id=? AND uploaded_at < ?", [sid, cutoff], reason)
                elif cat == "questionnaire_responses":
                    self.db.execute("UPDATE questionnaire_assignments SET response_id=NULL WHERE "
                                    "response_id IN (SELECT id FROM questionnaire_responses "
                                    "WHERE study_id=? AND submitted_at < ?)", (sid, cutoff))
                    n = self._delete_where(actor, "questionnaire_responses",
                                           "study_id=? AND submitted_at < ?", [sid, cutoff], reason)
                elif cat == "questionnaire_free_text":
                    rows = self.db.query("SELECT id FROM questionnaire_responses WHERE study_id=? "
                                         "AND submitted_at < ? AND free_text_json IS NOT NULL",
                                         (sid, cutoff))
                    for r in rows:
                        self._update(actor, "questionnaire_responses", r["id"],
                                     {"free_text_json": None}, reason, action="purge_free_text")
                    n = len(rows)
                elif cat == "telemetry":
                    n = self._delete_where(actor, "telemetry_batches",
                                           "study_id=? AND received_at < ?", [sid, cutoff], reason)
                elif cat == "telemetry_receipts":
                    cur = self.db.execute(
                        "DELETE FROM telemetry_receipts WHERE org_id=? AND received_at < ? AND "
                        "participant_id IN (SELECT id FROM participants WHERE study_id=?)",
                        (actor.org_id, cutoff, sid))
                    n = cur.rowcount
                else:  # pragma: no cover - guarded by set_retention_policy
                    continue
                log = {"id": new_id("prg"), "org_id": actor.org_id, "study_id": sid,
                       "policy_id": pol["id"], "data_category": cat, "cutoff": cutoff,
                       "n_affected": n, "run_at": self.db.now_iso(), "run_by": actor.user_id}
                self._insert(actor, "purge_log", log, reason=reason)
            out.append(log)
        return out

    # ------------------------------------------------------------------ data subject rights
    def export_subject(self, actor: Actor, pid: str) -> dict[str, Any]:
        """Everything stored about one participant, as JSON (data-subject access)."""
        p = self._participant(actor, pid, "subject.export")
        out: dict[str, Any] = {"format": "neurometric.subject_export/1",
                               "generated_at": self.db.now_iso(), "participant": p}
        out["consent"] = self._consent_view(actor.org_id, pid)
        for t in ("enrollment_events", "visits", "device_configs", "protocol_deviations",
                  "missing_data", "data_queries", "questionnaire_assignments"):
            out[t] = self.db.query(f"SELECT * FROM {t} WHERE participant_id=? AND org_id=?",
                                   (pid, actor.org_id))
        sessions = []
        for r in self.db.query("SELECT * FROM functional_sessions WHERE participant_id=? AND "
                               "org_id=?", (pid, actor.org_id)):
            v = self._session_view(r, include_events=True)
            sessions.append(v)
        out["functional_sessions"] = sessions
        out["questionnaire_responses"] = [
            self._response_view(r, include_free_text=True) for r in self.db.query(
                "SELECT * FROM questionnaire_responses WHERE participant_id=? AND org_id=?",
                (pid, actor.org_id))]
        out["telemetry_batches"] = [
            {**{k: v for k, v in r.items() if k != "payload_json"},
             "payload": jload(r["payload_json"], {})} for r in self.db.query(
                "SELECT * FROM telemetry_batches WHERE participant_id=? AND org_id=?",
                (pid, actor.org_id))]
        out["telemetry_state"] = self.db.one("SELECT * FROM telemetry_state WHERE participant_id=?",
                                             (pid,))
        out["re_identification_key_on_file"] = bool(self.db.one(
            "SELECT 1 FROM reidentification_keys WHERE participant_id=?", (pid,)))
        self.audit.append(actor, "subject_export", "participants", pid, org_id=actor.org_id)
        return out

    def delete_subject(self, actor: Actor, pid: str, reason: str) -> dict[str, int]:
        """Erase a participant's data (data-subject deletion). The audit trail keeps
        pseudonymous tombstones (record ids, hashes, reason) - see DATA_GOVERNANCE.md."""
        p = self._participant(actor, pid, "subject.delete")
        if not reason or not reason.strip():
            raise ReasonRequired("a reason is required for subject deletion")
        counts: dict[str, int] = {}
        with self.db.tx():
            for t in ("reminders", "questionnaire_assignments", "questionnaire_responses",
                      "functional_sessions", "telemetry_batches", "missing_data",
                      "data_queries", "protocol_deviations", "device_configs", "visits",
                      "consent_records", "enrollment_events", "telemetry_state",
                      "reidentification_keys"):
                key = "participant_id=?"
                counts[t] = self._delete_where(actor, t, key, [pid], reason)
            counts["telemetry_receipts"] = self.db.execute(
                "DELETE FROM telemetry_receipts WHERE participant_id=?", (pid,)).rowcount
            for u in self.db.query("SELECT id FROM users WHERE participant_id=?", (pid,)):
                self.db.execute("DELETE FROM auth_tokens WHERE user_id=?", (u["id"],))
                self._update(actor, "users", u["id"], {"active": 0, "participant_id": None,
                                                       "role": "participant"},
                             f"subject deleted: {reason}")
            self.db.execute("DELETE FROM care_partner_links WHERE participant_id=?", (pid,))
            counts["participants"] = self._delete_where(actor, "participants", "id=?", [pid],
                                                        reason)
        return counts
