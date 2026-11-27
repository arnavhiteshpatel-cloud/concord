"""Backup (SQLite online backup API), integrity verification and restore.

A backup is a consistent copy of the live database plus a sidecar manifest
(``<backup>.manifest.json``) holding the file's SHA-256, the schema version, the audit-chain
head hash and entry count, and the UTC time. Verification recomputes the file hash, runs
``PRAGMA integrity_check`` and re-verifies the audit chain against the manifest's head hash.
Restore refuses an unverified backup and writes into a new database file via the backup API.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path
from typing import Any

from .audit import AuditTrail
from .db import Database


def _file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def backup_database(db: Database, dest: str | Path) -> dict[str, Any]:
    dest = Path(dest)
    if dest.exists():
        raise FileExistsError(f"{dest} exists; backups are never overwritten")
    dest.parent.mkdir(parents=True, exist_ok=True)
    with db._lock:
        target = sqlite3.connect(str(dest))
        try:
            db.conn.backup(target)
            target.execute("PRAGMA journal_mode=DELETE")  # self-contained single file
        finally:
            target.close()
    audit = AuditTrail(db)
    manifest = {"format": "neurometric.backup/1", "created_at": db.now_iso(),
                "source": Path(db.path).name, "file": dest.name, "sha256": _file_sha256(dest),
                "size_bytes": dest.stat().st_size, "schema_version": db.schema_version(),
                "audit_head": audit.head(), "audit_entries": audit.count()}
    Path(str(dest) + ".manifest.json").write_text(json.dumps(manifest, indent=2), "utf-8")
    return manifest


def verify_backup(path: str | Path) -> dict[str, Any]:
    path = Path(path)
    problems = []
    mpath = Path(str(path) + ".manifest.json")
    if not path.exists():
        return {"ok": False, "problems": ["backup file missing"]}
    if not mpath.exists():
        return {"ok": False, "problems": ["manifest missing"]}
    manifest = json.loads(mpath.read_text("utf-8"))
    if _file_sha256(path) != manifest.get("sha256"):
        problems.append("file SHA-256 differs from manifest")
    try:
        con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        try:
            res = con.execute("PRAGMA integrity_check").fetchone()[0]
        finally:
            con.close()
        if res != "ok":
            problems.append(f"integrity_check: {res}")
    except sqlite3.DatabaseError as e:
        problems.append(f"not a readable database: {e}")
        return {"ok": False, "problems": problems, "manifest": manifest}
    if not problems:
        db = Database(path, readonly=True)
        try:
            chain = AuditTrail(db).verify_chain(expected_head=manifest.get("audit_head"))
        finally:
            db.close()
        if not chain["ok"]:
            problems.append("audit chain verification failed")
        if chain["entries"] != manifest.get("audit_entries"):
            problems.append("audit entry count differs from manifest")
    return {"ok": not problems, "problems": problems, "manifest": manifest}


def restore_database(backup_path: str | Path, target_path: str | Path) -> dict[str, Any]:
    v = verify_backup(backup_path)
    if not v["ok"]:
        raise ValueError(f"backup failed verification: {v['problems']}")
    target_path = Path(target_path)
    if target_path.exists():
        raise FileExistsError(f"{target_path} exists; restore into a new file and switch over")
    src = sqlite3.connect(f"file:{backup_path}?mode=ro", uri=True)
    dst = sqlite3.connect(str(target_path))
    try:
        src.backup(dst)
    finally:
        src.close()
        dst.close()
    db = Database(target_path)
    try:
        chain = AuditTrail(db).verify_chain(expected_head=v["manifest"]["audit_head"])
    finally:
        db.close()
    return {"restored_to": str(target_path), "audit_chain_ok": chain["ok"],
            "audit_head": chain["head"], "manifest": v["manifest"]}
