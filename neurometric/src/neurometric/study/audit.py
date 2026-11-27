"""Append-only, hash-chained audit trail and electronic-signature records.

These are *technical controls oriented to* 21 CFR Part 11 (audit trail, record integrity,
signature manifestation and linking). Their existence does not make a deployment Part 11
compliant: that needs validation, procedures, training and an organisation's controls
(see docs/quality/VALIDATION_STRATEGY.md).

Audit entry = who (user id + role), what (action, table, record id, old and new values), when
(server UTC clock), why (reason; mandatory for every update or deletion of entered data).
Each entry stores ``prev_hash`` (the previous entry's hash) and its own ``entry_hash`` =
SHA-256 over the canonical JSON of all its fields, so any edit, deletion or re-ordering of
entries breaks the chain and is detected by :func:`verify_chain`. Truncation of the most recent
entries is only detectable against an externally kept head hash (export manifests and backup
manifests record it; pass it as ``expected_head``).

Sensitive values (re-identification identifiers, free text, raw event blobs) are never copied
into the audit trail: they are replaced by their SHA-256.
"""
from __future__ import annotations

import json
from typing import Any, Optional

from .db import Database, canonical_json, sha256_hex
from .permissions import Actor

GENESIS = "0" * 64

#: Fields whose values are replaced by a hash in audit old/new values.
REDACT_FIELDS = frozenset({"enc_identifier", "identifier", "free_text_json", "events_blob",
                           "password_hash", "payload_json", "events"})

SYSTEM = Actor(user_id="system", org_id="system", role="system", username="system")


def _redact(values: Optional[dict]) -> Optional[dict]:
    if values is None:
        return None
    out = {}
    for k, v in values.items():
        if k in REDACT_FIELDS and v is not None:
            b = v if isinstance(v, (bytes, bytearray)) else canonical_json(v).encode()
            out[k] = {"redacted_sha256": sha256_hex(bytes(b))}
        elif isinstance(v, (bytes, bytearray)):
            out[k] = {"bytes_sha256": sha256_hex(bytes(v))}
        else:
            out[k] = v
    return out


def _entry_hash(e: dict[str, Any]) -> str:
    fields = {k: e[k] for k in ("id", "org_id", "at", "actor_user_id", "actor_role", "action",
                                "table_name", "record_id", "reason", "old_json", "new_json",
                                "prev_hash")}
    return sha256_hex(canonical_json(fields))


class AuditTrail:
    def __init__(self, db: Database):
        self.db = db

    def append(self, actor: Actor, action: str, table: str, record_id: str, *,
               org_id: Optional[str] = None, reason: str = "", old: Optional[dict] = None,
               new: Optional[dict] = None) -> dict[str, Any]:
        with self.db.tx():
            last = self.db.one("SELECT id, entry_hash FROM audit_log ORDER BY id DESC LIMIT 1")
            e = {
                "id": (last["id"] + 1) if last else 1,
                "org_id": org_id or actor.org_id,
                "at": self.db.now_iso(),
                "actor_user_id": actor.user_id,
                "actor_role": actor.role,
                "action": action,
                "table_name": table,
                "record_id": str(record_id),
                "reason": reason or "",
                "old_json": canonical_json(_redact(old)) if old is not None else None,
                "new_json": canonical_json(_redact(new)) if new is not None else None,
                "prev_hash": last["entry_hash"] if last else GENESIS,
            }
            e["entry_hash"] = _entry_hash(e)
            self.db.execute(
                "INSERT INTO audit_log (id, org_id, at, actor_user_id, actor_role, action, "
                "table_name, record_id, reason, old_json, new_json, prev_hash, entry_hash) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                [e[k] for k in ("id", "org_id", "at", "actor_user_id", "actor_role", "action",
                                "table_name", "record_id", "reason", "old_json", "new_json",
                                "prev_hash", "entry_hash")])
            return e

    def head(self) -> str:
        r = self.db.one("SELECT entry_hash FROM audit_log ORDER BY id DESC LIMIT 1")
        return r["entry_hash"] if r else GENESIS

    def count(self) -> int:
        return int(self.db.scalar("SELECT COUNT(*) FROM audit_log"))

    def verify_chain(self, expected_head: Optional[str] = None) -> dict[str, Any]:
        """Recompute the whole chain. Detects edited, deleted, inserted or re-ordered entries;
        with ``expected_head`` also detects truncation of the newest entries."""
        prev = GENESIS
        n = 0
        problems: list[dict[str, Any]] = []
        for e in self.db.query("SELECT * FROM audit_log ORDER BY id"):
            n += 1
            if e["id"] != n:
                problems.append({"id": e["id"], "problem": f"sequence gap (expected id {n})"})
                n = e["id"]
            if e["prev_hash"] != prev:
                problems.append({"id": e["id"], "problem": "prev_hash does not link to previous entry"})
            if _entry_hash(e) != e["entry_hash"]:
                problems.append({"id": e["id"], "problem": "entry content does not match entry_hash"})
            prev = e["entry_hash"]
        if expected_head is not None and prev != expected_head:
            problems.append({"id": None, "problem": "head hash differs from expected anchor "
                                                    "(entries truncated or replaced)"})
        return {"ok": not problems, "entries": n, "head": prev, "problems": problems,
                "first_bad_id": problems[0]["id"] if problems else None}

    def history(self, org_id: str, table: str, record_id: str) -> list[dict[str, Any]]:
        rows = self.db.query(
            "SELECT * FROM audit_log WHERE org_id=? AND table_name=? AND record_id=? ORDER BY id",
            (org_id, table, str(record_id)))
        for r in rows:
            r["old"] = json.loads(r.pop("old_json")) if r.get("old_json") else None
            r["new"] = json.loads(r.pop("new_json")) if r.get("new_json") else None
        return rows

    def entries(self, org_id: str, limit: int = 200, offset: int = 0,
                table: Optional[str] = None) -> list[dict[str, Any]]:
        sql = "SELECT * FROM audit_log WHERE org_id=?"
        params: list[Any] = [org_id]
        if table:
            sql += " AND table_name=?"
            params.append(table)
        sql += " ORDER BY id DESC LIMIT ? OFFSET ?"
        params += [int(limit), int(offset)]
        return self.db.query(sql, params)
