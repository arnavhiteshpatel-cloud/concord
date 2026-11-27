"""The study service: one object combining all domain operations over one database."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from .backup import backup_database, restore_database, verify_backup
from .clinical import ClinicalMixin
from .collection import CollectionMixin
from .consent import ConsentMixin
from .exports import ExportMixin
from .permissions import Actor, require
from .telemetry import TelemetryMixin


class StudyService(ClinicalMixin, CollectionMixin, ConsentMixin, TelemetryMixin, ExportMixin):
    """Entry point: ``StudyService(path)`` opens (and migrates) a SQLite study database."""

    def integrity_check(self, actor: Actor) -> dict[str, Any]:
        """Record integrity: SQLite page check, audit chain, raw-event hashes, telemetry hashes,
        and signature status for the actor's organization."""
        require(actor, "integrity.check")
        page = self.db.scalar("PRAGMA integrity_check")
        fk = self.db.query("PRAGMA foreign_key_check")
        chain = self.audit.verify_chain()
        bad_sessions = [r["id"] for r in self.db.query(
            "SELECT id, events_blob, events_sha256, raw_purged FROM functional_sessions WHERE "
            "org_id=?", (actor.org_id,)) if not self.verify_session_integrity(r)]
        tel = self.verify_telemetry_integrity()
        sigs = [self.verify_signature(actor, s["id"])["status"] for s in self.db.query(
            "SELECT id FROM e_signatures WHERE org_id=?", (actor.org_id,))]
        return {"ok": page == "ok" and not fk and chain["ok"] and not bad_sessions and tel["ok"],
                "sqlite_integrity": page, "foreign_key_violations": len(fk),
                "audit_chain": chain, "sessions_with_bad_hash": bad_sessions,
                "telemetry": tel,
                "signatures": {s: sigs.count(s) for s in sorted(set(sigs))}}

    def backup(self, actor: Actor, dest: str | Path) -> dict[str, Any]:
        require(actor, "backup.run")
        m = backup_database(self.db, dest)
        self.audit.append(actor, "backup", "database", Path(dest).name, new={"sha256": m["sha256"]})
        return m

    verify_backup = staticmethod(verify_backup)
    restore = staticmethod(restore_database)
