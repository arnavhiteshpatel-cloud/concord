"""Service base: repository helpers (tenant-scoped reads, audited writes), authentication and
record-scope checks. Domain operations live in the mixins combined in :mod:`.service`."""
from __future__ import annotations

import json
import secrets
import sqlite3
from datetime import timedelta
from typing import Any, Iterable, Optional

from ..instruments.engine import Registry
from .audit import SYSTEM, AuditTrail
from .db import Database, canonical_json, parse_iso, sha256_hex
from .errors import (AuthenticationFailed, Conflict, ConsentRequired, DemoMixError, NotFound,
                     PermissionDenied, ReasonRequired, StudyError, ValidationFailed)
from .permissions import ROLES, SITE_STAFF, Actor, require
from .security import (check_password_policy, dummy_verify, hash_password, new_token,
                       token_hash, token_ttl_minutes, verify_password)

#: Tables the service layer may address by name (guards every dynamic SQL identifier).
TABLES = frozenset({
    "organizations", "users", "sponsors", "sites", "studies", "study_sites", "protocol_versions",
    "assessment_schedules", "participants", "reidentification_keys", "enrollment_events",
    "visits", "device_configs", "functional_sessions", "questionnaire_assignments", "reminders",
    "questionnaire_responses", "protocol_deviations", "missing_data", "data_queries",
    "consent_records", "consent_withdrawals", "telemetry_state", "telemetry_batches",
    "telemetry_receipts", "retention_policies", "purge_log", "e_signatures", "care_partner_links",
    "user_sites", "auth_tokens",
})


def new_id(prefix: str) -> str:
    return f"{prefix}_{secrets.token_hex(10)}"


def new_pseudonym() -> str:
    """Random, non-derivable participant pseudonym (not computed from any identifier)."""
    alphabet = "ABCDEFGHJKMNPQRSTVWXYZ23456789"  # no 0/O/1/I/L/U look-alikes
    return "NM-" + "".join(secrets.choice(alphabet) for _ in range(10))


def jload(s: Optional[str], default: Any = None) -> Any:
    return json.loads(s) if s else default


def _check_table(t: str) -> str:
    if t not in TABLES:
        raise ValidationFailed(f"unknown table {t!r}")
    return t


class StudyServiceBase:
    def __init__(self, db: Database | str, clock=None):
        self.db = db if isinstance(db, Database) else Database(db, clock)
        self.audit = AuditTrail(self.db)
        self.instruments = Registry()

    # ------------------------------------------------------------------ low-level repository
    def _translate(self, e: sqlite3.Error) -> StudyError:
        msg = str(e)
        if "demo_mix" in msg:
            return DemoMixError(msg)
        if "another study" in msg:
            return ValidationFailed(msg, code="cross_study_reference")
        if "UNIQUE" in msg:
            return Conflict(msg)
        if "append-only" in msg:
            return PermissionDenied(msg, code="append_only")
        return ValidationFailed(msg)

    def _insert(self, actor: Actor, table: str, row: dict[str, Any], *, reason: str = "",
                audit_key: Optional[str] = None) -> dict[str, Any]:
        _check_table(table)
        cols = list(row)
        try:
            with self.db.tx():
                self.db.execute(
                    f"INSERT INTO {table} ({', '.join(cols)}) VALUES ({', '.join('?' * len(cols))})",
                    [row[c] for c in cols])
                self.audit.append(actor, "create", table, audit_key or row.get("id", ""),
                                  org_id=row.get("org_id") or actor.org_id, reason=reason, new=row)
        except sqlite3.Error as e:
            raise self._translate(e) from e
        return row

    def _get(self, actor: Actor, table: str, rid: str) -> dict[str, Any]:
        _check_table(table)
        row = self.db.one(f"SELECT * FROM {table} WHERE id=? AND org_id=?", (rid, actor.org_id))
        if row is None:
            raise NotFound(f"{table} {rid} not found")
        return row

    def _update(self, actor: Actor, table: str, rid: str, changes: dict[str, Any], reason: str,
                *, action: str = "update") -> dict[str, Any]:
        """Audited update; a reason for change is always mandatory."""
        _check_table(table)
        if not isinstance(reason, str) or not reason.strip():
            raise ReasonRequired("a reason for change is required for every update")
        old = self._get(actor, table, rid)
        diff = {k: v for k, v in changes.items() if old.get(k) != v}
        unknown = set(changes) - set(old)
        if unknown:
            raise ValidationFailed(f"unknown fields {sorted(unknown)}")
        if not diff:
            return old
        try:
            with self.db.tx():
                sets = ", ".join(f"{k}=?" for k in diff)
                self.db.execute(f"UPDATE {table} SET {sets} WHERE id=? AND org_id=?",
                                [*diff.values(), rid, actor.org_id])
                self.audit.append(actor, action, table, rid, reason=reason.strip(),
                                  old={k: old[k] for k in diff}, new=diff)
        except sqlite3.Error as e:
            raise self._translate(e) from e
        return {**old, **diff}

    def _delete_where(self, actor: Actor, table: str, where: str, params: Iterable[Any],
                      reason: str) -> int:
        """Audited deletion (each deleted row gets an audit entry with redacted old values)."""
        _check_table(table)
        if not reason.strip():
            raise ReasonRequired("a reason is required for every deletion")
        params = list(params)
        with self.db.tx():
            rows = self.db.query(f"SELECT * FROM {table} WHERE org_id=? AND ({where})",
                                 [actor.org_id, *params])
            for r in rows:
                key = r.get("id") or r.get("participant_id") or ""
                self.audit.append(actor, "delete", table, key, reason=reason,
                                  old={"record_sha256": record_digest(r),
                                       **{k: r[k] for k in ("participant_id", "study_id") if k in r}})
            self.db.execute(f"DELETE FROM {table} WHERE org_id=? AND ({where})",
                            [actor.org_id, *params])
        return len(rows)

    # ------------------------------------------------------------------ organizations & users
    def create_organization(self, name: str, is_demo: bool = False) -> dict[str, Any]:
        org = {"id": new_id("org"), "name": name, "is_demo": int(bool(is_demo)),
               "created_at": self.db.now_iso()}
        return self._insert(SYSTEM, "organizations", {**org}, reason="organization created") and org

    def create_user(self, actor: Actor, *, org_id: str, username: str, password: str, role: str,
                    display_name: str = "", participant_id: Optional[str] = None,
                    site_ids: Iterable[str] = (), linked_participants: Iterable[str] = ()
                    ) -> dict[str, Any]:
        if actor is not SYSTEM:
            require(actor, "user.manage")
            if org_id != actor.org_id:
                raise NotFound("organization not found")
        if role not in ROLES:
            raise ValidationFailed(f"unknown role {role!r}")
        check_password_policy(password)
        if self.db.one("SELECT id FROM organizations WHERE id=?", (org_id,)) is None:
            raise NotFound("organization not found")
        org_demo = self.db.scalar("SELECT is_demo FROM organizations WHERE id=?", (org_id,))
        if role == "participant":
            if not participant_id:
                raise ValidationFailed("participant users must be linked to a participant record")
            if not self.db.one("SELECT id FROM participants WHERE id=? AND org_id=?",
                               (participant_id, org_id)):
                raise NotFound("participant not found")
        elif participant_id:
            raise ValidationFailed("only participant users link to a participant record")
        now = self.db.now_iso()
        uid = new_id("usr")
        row = {"id": uid, "org_id": org_id, "username": username, "display_name": display_name,
               "password_hash": hash_password(password), "role": role,
               "participant_id": participant_id, "active": 1, "is_demo": int(org_demo or 0),
               "created_at": now, "password_changed_at": now}
        a = actor if actor is not SYSTEM else Actor("system", org_id, "system", "system")
        self._insert(a, "users", row, reason="user created")
        for sid in site_ids:
            self.assign_site(a, uid, sid, _bootstrap=actor is SYSTEM)
        for pid in linked_participants:
            self.link_care_partner(a, uid, pid, _bootstrap=actor is SYSTEM)
        return {k: v for k, v in row.items() if k != "password_hash"}

    def assign_site(self, actor: Actor, user_id: str, site_id: str, _bootstrap: bool = False):
        if not _bootstrap:
            require(actor, "user.manage")
        u = self._get(actor, "users", user_id)
        if u["role"] not in SITE_STAFF:
            raise ValidationFailed("only coordinators and investigators are assigned to sites")
        self._get(actor, "sites", site_id)
        self._insert(actor, "user_sites", {"user_id": user_id, "site_id": site_id,
                                           "org_id": actor.org_id},
                     reason="site assignment", audit_key=f"{user_id}:{site_id}")

    def link_care_partner(self, actor: Actor, user_id: str, participant_id: str,
                          _bootstrap: bool = False):
        if not _bootstrap:
            require(actor, "user.manage")
        u = self._get(actor, "users", user_id)
        if u["role"] != "care_partner":
            raise ValidationFailed("only care_partner users are linked to participants")
        self._get(actor, "participants", participant_id)
        self._insert(actor, "care_partner_links", {"user_id": user_id,
                                                   "participant_id": participant_id,
                                                   "org_id": actor.org_id},
                     reason="care partner linked", audit_key=f"{user_id}:{participant_id}")

    def list_users(self, actor: Actor) -> list[dict[str, Any]]:
        require(actor, "user.manage")
        return self.db.query(
            "SELECT id, org_id, username, display_name, role, participant_id, active, is_demo, "
            "created_at FROM users WHERE org_id=? ORDER BY created_at", (actor.org_id,))

    def deactivate_user(self, actor: Actor, user_id: str, reason: str) -> None:
        require(actor, "user.manage")
        self._update(actor, "users", user_id, {"active": 0}, reason)
        self.db.execute("UPDATE auth_tokens SET revoked=1 WHERE user_id=?", (user_id,))

    def actor_for_user(self, user: dict[str, Any]) -> Actor:
        sites = frozenset(r["site_id"] for r in self.db.query(
            "SELECT site_id FROM user_sites WHERE user_id=?", (user["id"],)))
        links = frozenset(r["participant_id"] for r in self.db.query(
            "SELECT participant_id FROM care_partner_links WHERE user_id=?", (user["id"],)))
        return Actor(user_id=user["id"], org_id=user["org_id"], role=user["role"],
                     username=user["username"], display_name=user["display_name"],
                     participant_id=user["participant_id"], site_ids=sites,
                     linked_participants=links)

    def login(self, username: str, password: str) -> dict[str, Any]:
        user = self.db.one("SELECT * FROM users WHERE username=?", (username,))
        if user is None:
            dummy_verify(password)
            raise AuthenticationFailed("invalid credentials")
        actor = self.actor_for_user(user)
        if not user["active"] or not verify_password(password, user["password_hash"]):
            self.audit.append(actor, "login_failed", "users", user["id"], org_id=user["org_id"])
            raise AuthenticationFailed("invalid credentials")
        token = new_token()
        now = self.db.now()
        exp = now + timedelta(minutes=token_ttl_minutes())
        from .db import iso
        self.db.execute("INSERT INTO auth_tokens VALUES (?,?,?,?,?,0)",
                        (token_hash(token), user["id"], user["org_id"], iso(now), iso(exp)))
        self.audit.append(actor, "login", "users", user["id"], org_id=user["org_id"])
        return {"token": token, "token_type": "bearer", "expires_at": iso(exp),
                "role": user["role"], "org_id": user["org_id"], "user_id": user["id"],
                "participant_id": user["participant_id"]}

    def actor_from_token(self, token: str) -> Actor:
        if not token:
            raise AuthenticationFailed("missing token")
        row = self.db.one("SELECT * FROM auth_tokens WHERE token_hash=?", (token_hash(token),))
        if row is None or row["revoked"]:
            raise AuthenticationFailed("invalid token")
        if parse_iso(row["expires_at"]) <= self.db.now():
            raise AuthenticationFailed("token expired", code="token_expired")
        user = self.db.one("SELECT * FROM users WHERE id=?", (row["user_id"],))
        if user is None or not user["active"]:
            raise AuthenticationFailed("invalid token")
        return self.actor_for_user(user)

    def logout(self, token: str) -> None:
        self.db.execute("UPDATE auth_tokens SET revoked=1 WHERE token_hash=?", (token_hash(token),))

    def purge_expired_tokens(self) -> int:
        cur = self.db.execute("DELETE FROM auth_tokens WHERE expires_at < ? OR revoked=1",
                              (self.db.now_iso(),))
        return cur.rowcount

    def reauthenticate(self, actor: Actor, password: str) -> None:
        """Re-authentication (password re-entry) required at signing time."""
        user = self.db.one("SELECT * FROM users WHERE id=? AND org_id=?",
                           (actor.user_id, actor.org_id))
        if user is None or not user["active"] or not verify_password(password or "",
                                                                     user["password_hash"]):
            self.audit.append(actor, "reauth_failed", "users", actor.user_id)
            raise AuthenticationFailed("re-authentication failed", code="reauth_failed")

    # ------------------------------------------------------------------ scope checks
    def _participant(self, actor: Actor, pid: str, perm: Optional[str] = None) -> dict[str, Any]:
        if perm:
            require(actor, perm)
        p = self._get(actor, "participants", pid)
        self._check_scope(actor, p)
        return p

    def _check_scope(self, actor: Actor, p: dict[str, Any]) -> None:
        if actor.role == "participant":
            ok = actor.participant_id == p["id"]
        elif actor.role == "care_partner":
            ok = p["id"] in actor.linked_participants
        elif actor.role in SITE_STAFF:
            ok = p["site_id"] in actor.site_ids
        elif actor.role == "system":
            ok = True
        else:
            raise PermissionDenied(f"participant-level data is not available to role "
                                   f"'{actor.role}'", code="aggregate_only")
        if not ok:
            raise NotFound(f"participant {p['id']} not found")

    def _study(self, actor: Actor, sid: str) -> dict[str, Any]:
        return self._get(actor, "studies", sid)

    def _active_consent(self, pid: str) -> Optional[dict[str, Any]]:
        c = self.db.one("SELECT * FROM consent_records WHERE participant_id=? AND status='active' "
                        "ORDER BY given_at DESC LIMIT 1", (pid,))
        if c:
            c["scopes"] = jload(c["scopes_json"], {})
        return c

    def has_consent(self, pid: str, scope: str) -> bool:
        c = self._active_consent(pid)
        return bool(c and c["scopes"].get(scope))

    def _require_consent(self, pid: str, scope: str) -> None:
        if not self.has_consent(pid, scope):
            raise ConsentRequired(f"no active consent for scope '{scope}'", scope=scope)

    # ------------------------------------------------------------------ record hashing
    def record_hash(self, actor: Actor, table: str, rid: str) -> str:
        if table == "casebook":
            return self.casebook_hash(actor, rid)
        return record_digest(self._get(actor, table, rid))

    def casebook_hash(self, actor: Actor, pid: str) -> str:
        """Hash over a participant's complete record set (used for investigator sign-off)."""
        p = self._get(actor, "participants", pid)
        parts = {"participant": record_digest(p)}
        for t in ("consent_records", "visits", "functional_sessions", "questionnaire_responses",
                  "protocol_deviations", "missing_data", "device_configs"):
            rows = self.db.query(f"SELECT * FROM {t} WHERE participant_id=? AND org_id=? "
                                 "ORDER BY id", (pid, actor.org_id))
            parts[t] = [record_digest(r) for r in rows]
        return sha256_hex(canonical_json(parts))


def record_digest(row: dict[str, Any]) -> str:
    clean = {k: (sha256_hex(bytes(v)) if isinstance(v, (bytes, bytearray)) else v)
             for k, v in row.items()}
    return sha256_hex(canonical_json(clean))
