"""Privacy-preserving home telemetry: AGGREGATE usage summaries only, explicit opt-in,
application-scoped (DECISIONS D-008).

What is accepted: per period (<= 24 h) and device session, counts and minutes - active minutes,
device-assisted sessions, interaction counts by category (pointer, select, scroll, switch,
dwell, and the NUMBER of text characters - never the characters), interruptions, coarse
app-category minutes (only with the ``telemetry_app_categories`` consent scope), self-reported
assistance (type, minutes) and self-reported fatigue / burden (0-10).

What is rejected: anything not on the allowlist. The validator rejects unknown keys, keys that
look like content (text, url, title, window, screenshot, keystrokes, clipboard ...), strings
outside the few enumerated / patterned string fields, URL-like values and arrays where none are
allowed (e.g. keystroke arrays). Rejected payloads are never stored: only a receipt with reason
codes is kept.

Integrity rules (Experiment O): idempotent on (participant, device_session_id, period); a
re-sent identical batch is acknowledged as a duplicate, a different batch for the same key is a
conflict; overlapping periods within a device session are rejected; out-of-order arrival is
accepted and flagged; periods ending in the future beyond a tolerance are rejected (small skew is
flagged); every stored batch carries the SHA-256 of its canonical JSON, and a client-supplied
``batch_sha256`` must match.
"""
from __future__ import annotations

import math
import re
from datetime import datetime, timedelta
from typing import Any, Optional

from ..events.model import ASSIST_TYPES
from .core import StudyServiceBase, jload, new_id
from .db import canonical_json, iso, parse_iso, sha256_hex
from .errors import ConsentRequired, NotFound, ValidationFailed
from .permissions import Actor, require

SCHEMA = "nm.telemetry/1"
CLOCK_SKEW_TOLERANCE = timedelta(minutes=5)
MAX_PERIOD = timedelta(hours=24)
APP_CATEGORIES = ("communication", "web", "media", "productivity", "social", "games", "health",
                  "smart_home", "accessibility_tools", "other")
INTERACTION_KEYS = ("pointer", "select", "scroll", "switch_activations", "dwell_selections",
                    "text_chars_count")
ASSIST_SELF_TYPES = tuple(ASSIST_TYPES) + ("none",)
PLATFORMS = ("web", "windows", "macos", "linux", "ios", "android", "chromeos")

_PSEUDONYM = re.compile(r"^NM-[A-Z0-9]{10}$")
_DEVICE_SESSION = re.compile(r"^[A-Za-z0-9_-]{8,64}$")
_ISO = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(:\d{2}(\.\d{1,6})?)?(Z|[+-]\d{2}:\d{2})$")
_SEMVER = re.compile(r"^\d{1,3}\.\d{1,3}\.\d{1,4}$")
_HEX64 = re.compile(r"^[0-9a-f]{64}$")
_URLISH = re.compile(r"(https?:|www\.|://|\.com\b|\.org\b|@|file:)", re.I)
FORBIDDEN_KEY_HINTS = ("text", "content", "url", "uri", "href", "link", "title", "window",
                       "screenshot", "screen", "image", "keystroke", "keylog", "keys", "key_",
                       "clipboard", "message", "body", "query", "search", "typed", "password",
                       "email", "name", "address", "location", "gps", "audio", "transcript",
                       "html", "dom", "page", "domain", "contact", "file", "path")


def _sanitize_key(k: Any) -> str:
    s = re.sub(r"[^a-z0-9_]", "_", str(k).lower())[:40]
    return s or "_"


def _num(v: Any, lo: float, hi: float, integer: bool = False) -> bool:
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        return False
    if isinstance(v, float) and not math.isfinite(v):
        return False
    if integer and not (isinstance(v, int) or float(v).is_integer()):
        return False
    return lo <= v <= hi


class _V:
    def __init__(self):
        self.reasons: list[str] = []

    def add(self, r: str) -> None:
        if r not in self.reasons and len(self.reasons) < 50:
            self.reasons.append(r)

    def key(self, path: str, k: Any) -> None:
        sk = _sanitize_key(k)
        low = str(k).lower()
        if any(h in low for h in FORBIDDEN_KEY_HINTS) or _URLISH.search(str(k)):
            self.add(f"forbidden_field:{path}{sk}")
        else:
            self.add(f"unknown_field:{path}{sk}")

    def scan_value(self, path: str, v: Any) -> None:
        """Values in unknown/forbidden places: flag content-like data explicitly."""
        if isinstance(v, str):
            self.add(f"content_like_value:{path}")
            if _URLISH.search(v):
                self.add(f"url_like_value:{path}")
        elif isinstance(v, list):
            self.add(f"array_not_allowed:{path}")


def validate_payload(payload: Any) -> list[str]:
    """Allowlist validation. Returns a list of reason codes (empty = valid)."""
    v = _V()
    if not isinstance(payload, dict):
        return ["payload_not_object"]
    required = ("schema_version", "participant", "device_session_id", "period_start",
                "period_end", "active_minutes", "interaction_counts")
    for k in required:
        if k not in payload:
            v.add(f"missing_field:{k}")
    for k, val in payload.items():
        if k == "schema_version":
            if val != SCHEMA:
                v.add("invalid_value:schema_version")
        elif k == "participant":
            if not isinstance(val, str) or not _PSEUDONYM.match(val):
                v.add("invalid_value:participant")
        elif k == "device_session_id":
            if not isinstance(val, str) or not _DEVICE_SESSION.match(val):
                v.add("invalid_value:device_session_id")
        elif k in ("period_start", "period_end"):
            if not isinstance(val, str) or not _ISO.match(val):
                v.add(f"invalid_value:{k}")
        elif k == "active_minutes":
            if not _num(val, 0, 1440):
                v.add("invalid_value:active_minutes")
        elif k == "device_assisted_sessions":
            if not _num(val, 0, 1000, integer=True):
                v.add("invalid_value:device_assisted_sessions")
        elif k == "interruptions":
            if not _num(val, 0, 10000, integer=True):
                v.add("invalid_value:interruptions")
        elif k in ("self_reported_fatigue", "self_reported_burden"):
            if not _num(val, 0, 10, integer=True):
                v.add(f"invalid_value:{k}")
        elif k == "interaction_counts":
            if not isinstance(val, dict):
                v.add("invalid_value:interaction_counts")
                v.scan_value("interaction_counts", val)
                continue
            for ik, iv in val.items():
                if ik not in INTERACTION_KEYS:
                    v.key("interaction_counts.", ik)
                    v.scan_value(f"interaction_counts.{_sanitize_key(ik)}", iv)
                elif not _num(iv, 0, 10_000_000, integer=True):
                    v.add(f"invalid_value:interaction_counts.{ik}")
                    v.scan_value(f"interaction_counts.{ik}", iv)
        elif k == "app_category_minutes":
            if not isinstance(val, dict):
                v.add("invalid_value:app_category_minutes")
                v.scan_value("app_category_minutes", val)
                continue
            for ck, cv in val.items():
                if ck not in APP_CATEGORIES:
                    # app names / bundle ids / window titles are content, not categories
                    v.add(f"forbidden_field:app_category_minutes.{_sanitize_key(ck)}")
                elif not _num(cv, 0, 1440):
                    v.add(f"invalid_value:app_category_minutes.{ck}")
        elif k == "self_reported_assistance":
            if not isinstance(val, list) or len(val) > 10:
                v.add("invalid_value:self_reported_assistance")
                continue
            for i, a in enumerate(val):
                if not isinstance(a, dict):
                    v.add(f"invalid_value:self_reported_assistance.{i}")
                    continue
                for ak, av in a.items():
                    if ak == "type":
                        if av not in ASSIST_SELF_TYPES:
                            v.add(f"invalid_value:self_reported_assistance.{i}.type")
                    elif ak == "minutes":
                        if not _num(av, 0, 1440):
                            v.add(f"invalid_value:self_reported_assistance.{i}.minutes")
                    else:
                        v.key(f"self_reported_assistance.{i}.", ak)
                        v.scan_value(f"self_reported_assistance.{i}.{_sanitize_key(ak)}", av)
                if "type" not in a or "minutes" not in a:
                    v.add(f"missing_field:self_reported_assistance.{i}")
        elif k == "client":
            if not isinstance(val, dict):
                v.add("invalid_value:client")
                continue
            for ck, cv in val.items():
                if ck == "app_version":
                    if not isinstance(cv, str) or not _SEMVER.match(cv):
                        v.add("invalid_value:client.app_version")
                elif ck == "platform":
                    if cv not in PLATFORMS:
                        v.add("invalid_value:client.platform")
                else:
                    v.key("client.", ck)
                    v.scan_value(f"client.{_sanitize_key(ck)}", cv)
        elif k == "batch_sha256":
            if not isinstance(val, str) or not _HEX64.match(val):
                v.add("invalid_value:batch_sha256")
        else:
            v.key("", k)
            v.scan_value(_sanitize_key(k), val)
    return v.reasons


def batch_digest(payload: dict[str, Any]) -> str:
    """SHA-256 of the canonical JSON of the payload without its own batch_sha256."""
    return sha256_hex(canonical_json({k: v for k, v in payload.items() if k != "batch_sha256"}))


class TelemetryMixin(StudyServiceBase):
    def _receipt(self, org_id: str, pid: Optional[str], outcome: str, reasons: list[str],
                 batch_id: Optional[str] = None) -> None:
        self.db.execute("INSERT INTO telemetry_receipts VALUES (?,?,?,?,?,?,?)",
                        (new_id("trc"), org_id, pid, outcome, canonical_json(reasons), batch_id,
                         self.db.now_iso()))

    def _reject(self, actor: Actor, pid: Optional[str], reasons: list[str]):
        self._receipt(actor.org_id, pid, "rejected", reasons)
        return ValidationFailed("telemetry batch rejected", code="telemetry_rejected",
                                reasons=reasons)

    def ingest_telemetry(self, actor: Actor, payload: dict[str, Any]) -> dict[str, Any]:
        require(actor, "telemetry.ingest")
        reasons = validate_payload(payload)
        pid = payload.get("participant") if isinstance(payload, dict) else None
        own = (actor.role == "participant" and pid == actor.participant_id) or (
            actor.role == "care_partner" and pid in actor.linked_participants)
        if reasons:
            raise self._reject(actor, pid if own else None, reasons)
        if not own:
            raise self._reject(actor, None, ["participant_mismatch"])
        p = self._participant(actor, pid)
        if not self.has_consent(pid, "home_telemetry"):
            self._receipt(actor.org_id, pid, "rejected", ["consent_required:home_telemetry"])
            raise ConsentRequired("home_telemetry consent is not active", scope="home_telemetry")
        st = self.db.one("SELECT state FROM telemetry_state WHERE participant_id=?", (pid,))
        state = st["state"] if st else "stopped"
        if state != "active":
            raise self._reject(actor, pid, [f"telemetry_{state}"])
        if payload.get("app_category_minutes") and not self.has_consent(
                pid, "telemetry_app_categories"):
            raise self._reject(actor, pid, ["app_categories_not_consented"])
        start, end = parse_iso(payload["period_start"]), parse_iso(payload["period_end"])
        now = self.db.now()
        flags: list[str] = []
        rs: list[str] = []
        if end <= start:
            rs.append("period_end_not_after_start")
        if end - start > MAX_PERIOD:
            rs.append("period_too_long")
        if end > now + CLOCK_SKEW_TOLERANCE:
            rs.append("future_period")
        elif end > now:
            flags.append("clock_skew_tolerated")
        period_min = (end - start).total_seconds() / 60.0
        if payload["active_minutes"] > period_min + 0.5:
            rs.append("active_minutes_exceed_period")
        assist_min = sum(a["minutes"] for a in payload.get("self_reported_assistance", []))
        if assist_min > period_min + 0.5:
            rs.append("assistance_minutes_exceed_period")
        app_min = sum(payload.get("app_category_minutes", {}).values())
        if app_min > payload["active_minutes"] + 0.5:
            rs.append("app_minutes_exceed_active_minutes")
        digest = batch_digest(payload)
        if "batch_sha256" in payload and payload["batch_sha256"] != digest:
            rs.append("hash_mismatch")
        if rs:
            raise self._reject(actor, pid, rs)
        s_iso, e_iso = iso(start), iso(end)
        dsid = payload["device_session_id"]
        rejected: list[str] = []
        with self.db.tx():
            same = self.db.one("SELECT * FROM telemetry_batches WHERE participant_id=? AND "
                               "device_session_id=? AND period_start=? AND period_end=?",
                               (pid, dsid, s_iso, e_iso))
            if same is not None:
                if same["payload_sha256"] == digest:
                    self._receipt(actor.org_id, pid, "duplicate", ["duplicate_batch"], same["id"])
                    return {"batch_id": same["id"], "status": "duplicate",
                            "payload_sha256": digest, "flags": jload(same["flags_json"], [])}
                rejected = ["conflicting_duplicate"]
            else:
                overlaps = self.db.query(
                    "SELECT id, device_session_id FROM telemetry_batches WHERE participant_id=? "
                    "AND period_start < ? AND period_end > ?", (pid, e_iso, s_iso))
                if any(o["device_session_id"] == dsid for o in overlaps):
                    rejected = ["overlapping_period"]
                else:
                    if overlaps:
                        flags.append("overlaps_other_device_session")
                    if self.db.one("SELECT 1 FROM telemetry_batches WHERE participant_id=? AND "
                                   "device_session_id=? AND period_start > ?",
                                   (pid, dsid, s_iso)):
                        flags.append("out_of_order")
                    row = {"id": new_id("tlm"), "org_id": actor.org_id, "study_id": p["study_id"],
                           "participant_id": pid, "device_session_id": dsid,
                           "period_start": s_iso, "period_end": e_iso,
                           "payload_json": canonical_json(payload), "payload_sha256": digest,
                           "flags_json": canonical_json(flags),
                           "received_at": self.db.now_iso(), "is_demo": p["is_demo"]}
                    self._insert(actor, "telemetry_batches", row, reason="telemetry ingest")
                    self._receipt(actor.org_id, pid, "accepted", flags, row["id"])
        if rejected:  # recorded outside the transaction so the receipt is kept
            raise self._reject(actor, pid, rejected)
        return {"batch_id": row["id"], "status": "accepted", "payload_sha256": digest,
                "flags": flags}

    def set_telemetry_state(self, actor: Actor, pid: str, state: str, reason: str = "") -> dict:
        """Visible recording controls: pause / resume (participant-controlled) and stop."""
        p = self._participant(actor, pid, "telemetry.control")
        if state not in ("active", "paused", "stopped"):
            raise ValidationFailed("state must be active, paused or stopped")
        if state == "active" and not self.has_consent(pid, "home_telemetry"):
            raise ConsentRequired("home_telemetry consent is not active", scope="home_telemetry")
        st = self.db.one("SELECT * FROM telemetry_state WHERE participant_id=?", (pid,))
        if st is None:
            raise NotFound("telemetry has never been enabled for this participant")
        if st["state"] != state:
            self.db.execute("UPDATE telemetry_state SET state=?, updated_at=?, updated_by=? "
                            "WHERE participant_id=?", (state, self.db.now_iso(), actor.user_id, pid))
            self.audit.append(actor, "update", "telemetry_state", pid, org_id=p["org_id"],
                              reason=reason or f"telemetry {state} by {actor.role}",
                              old={"state": st["state"]}, new={"state": state})
        return self.db.one("SELECT * FROM telemetry_state WHERE participant_id=?", (pid,))

    def telemetry_state(self, actor: Actor, pid: str) -> dict[str, Any]:
        self._participant(actor, pid, "telemetry.control")
        st = self.db.one("SELECT * FROM telemetry_state WHERE participant_id=?", (pid,))
        return st or {"participant_id": pid, "state": "stopped"}

    def review_own_telemetry(self, actor: Actor, pid: str) -> dict[str, Any]:
        """Local review: the participant sees exactly what was stored (byte-identical payloads)
        and every receipt (including rejections and their reason codes)."""
        self._participant(actor, pid, "telemetry.review_own")
        batches = self.db.query("SELECT id, device_session_id, period_start, period_end, "
                                "payload_json, payload_sha256, flags_json, received_at FROM "
                                "telemetry_batches WHERE participant_id=? ORDER BY period_start",
                                (pid,))
        receipts = self.db.query("SELECT outcome, reason_codes_json, batch_id, received_at FROM "
                                 "telemetry_receipts WHERE participant_id=? ORDER BY received_at",
                                 (pid,))
        return {"state": self.db.one("SELECT state, updated_at FROM telemetry_state WHERE "
                                     "participant_id=?", (pid,)),
                "batches": [{**{k: v for k, v in b.items() if k not in ("payload_json",
                                                                         "flags_json")},
                             "payload": jload(b["payload_json"], {}),
                             "flags": jload(b["flags_json"], [])} for b in batches],
                "receipts": [{"outcome": r["outcome"], "reasons": jload(r["reason_codes_json"], []),
                              "batch_id": r["batch_id"], "received_at": r["received_at"]}
                             for r in receipts]}

    def telemetry_summary(self, actor: Actor, pid: str) -> dict[str, Any]:
        """Aggregates for one participant (staff view)."""
        self._participant(actor, pid, "participant.read")
        rows = self.db.query("SELECT * FROM telemetry_batches WHERE participant_id=? AND org_id=? "
                             "ORDER BY period_start", (pid, actor.org_id))
        return summarize_batches(rows)

    def verify_telemetry_integrity(self) -> dict[str, Any]:
        bad = [r["id"] for r in self.db.query("SELECT id, payload_json, payload_sha256 FROM "
                                              "telemetry_batches")
               if batch_digest(jload(r["payload_json"], {})) != r["payload_sha256"]]
        return {"ok": not bad, "bad_batches": bad}


def summarize_batches(rows: list[dict[str, Any]]) -> dict[str, Any]:
    tot: dict[str, Any] = {"n_batches": len(rows), "active_minutes": 0.0,
                           "device_assisted_sessions": 0, "interruptions": 0,
                           "interaction_counts": {k: 0 for k in INTERACTION_KEYS},
                           "app_category_minutes": {}, "assistance_minutes": {},
                           "fatigue_mean": None, "burden_mean": None, "flagged_batches": 0,
                           "days": {}}
    fat, bur = [], []
    for r in rows:
        p = jload(r["payload_json"], {})
        tot["active_minutes"] += p.get("active_minutes", 0)
        tot["device_assisted_sessions"] += p.get("device_assisted_sessions", 0)
        tot["interruptions"] += p.get("interruptions", 0)
        for k, v in p.get("interaction_counts", {}).items():
            tot["interaction_counts"][k] += v
        for k, v in p.get("app_category_minutes", {}).items():
            tot["app_category_minutes"][k] = tot["app_category_minutes"].get(k, 0) + v
        for a in p.get("self_reported_assistance", []):
            tot["assistance_minutes"][a["type"]] = tot["assistance_minutes"].get(a["type"], 0) + a["minutes"]
        if "self_reported_fatigue" in p:
            fat.append(p["self_reported_fatigue"])
        if "self_reported_burden" in p:
            bur.append(p["self_reported_burden"])
        if jload(r.get("flags_json"), []):
            tot["flagged_batches"] += 1
        day = r["period_start"][:10]
        tot["days"][day] = tot["days"].get(day, 0) + p.get("active_minutes", 0)
    tot["fatigue_mean"] = sum(fat) / len(fat) if fat else None
    tot["burden_mean"] = sum(bur) / len(bur) if bur else None
    return tot
