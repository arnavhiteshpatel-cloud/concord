"""Research sessions: a named, operator-attributed record of one experiment.

A research session is a folder ``<data>/sessions/<id>/``:

    session.json   who/what/when (name, operator, notes, times, recordings, models) — 0600
    log.jsonl      the session log: device status changes, operator actions with their
                   configuration (pipeline, router, calibration), recordings — 0600
    exports/       reproducibility bundles (brainos.runtime.export)

It is distinct from the runtime's per-connection ``session_id`` (``ses_…``). One research
session is active at a time. A session that was active when BrainOS stopped unexpectedly is
marked ``interrupted`` at the next start (never resumed silently).

Personal data (operator, notes) lives only in ``session.json``: never in the session log,
the application log, or support reports; exports include it only when asked.
"""

from __future__ import annotations

import builtins
import contextlib
import json
import logging
import os
import re
import secrets
import shutil
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel

from brainos import __version__
from brainos.contracts.capabilities import EventType
from brainos.contracts.events import EventEnvelope
from brainos.security import ensure_private_dir, open_private, write_private

log = logging.getLogger(__name__)

SESSION_FORMAT = "brainos.session/1"
ID_PATTERN = re.compile(r"^\d{8}-\d{6}-[0-9a-f]{4}$")
MAX_NAME = 80
MAX_OPERATOR = 80
MAX_NOTES = 4000
MAX_LOG_ENTRY = 64 * 1024

Status = Literal["active", "closed", "interrupted"]


class SessionError(Exception):
    def __init__(self, message: str, *, not_found: bool = False) -> None:
        super().__init__(message)
        self.not_found = not_found


class SessionInfo(BaseModel):
    format: str = SESSION_FORMAT
    id: str
    name: str
    operator: str | None = None
    notes: str | None = None
    created_at_ns: int
    closed_at_ns: int | None = None
    status: Status = "active"
    end_reason: str | None = None
    brainos_version: str
    recordings: list[str] = []
    models: list[str] = []
    log_entries: int = 0


def _clean(text: str | None, limit: int, what: str) -> str | None:
    if text is None:
        return None
    text = text.strip()
    if len(text) > limit:
        raise SessionError(f"{what} is longer than {limit} characters")
    if any(ord(c) < 32 and c not in "\n\t" for c in text):
        raise SessionError(f"{what} contains control characters")
    return text or None


class SessionManager:
    def __init__(self, directory: Path) -> None:
        self.directory = directory
        self._active: SessionInfo | None = None

    # ------------------------------------------------------------------ queries
    @property
    def active(self) -> SessionInfo | None:
        return self._active

    def folder(self, session_id: str) -> Path:
        if not ID_PATTERN.match(session_id):
            raise SessionError(f"invalid session id {session_id!r}", not_found=True)
        return self.directory / session_id

    def get(self, session_id: str) -> SessionInfo:
        if self._active is not None and self._active.id == session_id:
            return self._active
        path = self.folder(session_id) / "session.json"
        if not path.exists():
            raise SessionError(f"no session {session_id!r}", not_found=True)
        try:
            return SessionInfo.model_validate_json(path.read_text(encoding="utf-8"))
        except (ValueError, OSError) as exc:
            raise SessionError(f"session {session_id!r} is unreadable: {exc}") from None

    def list(self) -> list[SessionInfo]:
        out: list[SessionInfo] = []
        if not self.directory.exists():
            return out
        for d in sorted(self.directory.iterdir()):
            if d.is_dir() and ID_PATTERN.match(d.name):
                try:
                    out.append(self.get(d.name))
                except SessionError as exc:
                    log.warning("skipping session %s: %s", d.name, exc)
        return sorted(out, key=lambda s: s.created_at_ns, reverse=True)

    def entries(self, session_id: str) -> builtins.list[dict[str, Any]]:
        return [*self.iter_entries(session_id)]

    def iter_entries(self, session_id: str) -> Iterator[dict[str, Any]]:
        path = self.folder(session_id) / "log.jsonl"
        if not path.exists():
            return
        with path.open(encoding="utf-8") as fh:
            for line in fh:
                with contextlib.suppress(ValueError):
                    obj = json.loads(line)
                    if isinstance(obj, dict):
                        yield obj

    # ------------------------------------------------------------------ lifecycle
    def recover(self) -> builtins.list[str]:
        """Mark sessions left active by a previous process as interrupted (server start)."""
        marked: builtins.list[str] = []
        for s in self.list():
            if s.status == "active":
                s = s.model_copy(
                    update={
                        "status": "interrupted",
                        "end_reason": "BrainOS stopped while the session was active",
                        "closed_at_ns": None,
                    }
                )
                self._save(s)
                self._append(
                    s.id, {"kind": "session_interrupted", "detected_at_ns": time.time_ns()}
                )
                marked.append(s.id)
                log.warning("research session %s was interrupted; marked as such", s.id)
        return marked

    def create(
        self, name: str, operator: str | None = None, notes: str | None = None
    ) -> SessionInfo:
        if self._active is not None:
            raise SessionError(f"session {self._active.id} is active; end it first")
        clean_name = _clean(name, MAX_NAME, "session name")
        if not clean_name:
            raise SessionError("a session name is required")
        now = time.time_ns()
        sid = time.strftime("%Y%m%d-%H%M%S", time.localtime(now / 1e9)) + "-" + secrets.token_hex(2)
        folder = ensure_private_dir(self.folder(sid))
        ensure_private_dir(folder / "exports")
        info = SessionInfo(
            id=sid,
            name=clean_name,
            operator=_clean(operator, MAX_OPERATOR, "operator"),
            notes=_clean(notes, MAX_NOTES, "notes"),
            created_at_ns=now,
            brainos_version=__version__,
        )
        self._active = info
        self._save(info)
        self.record("session_created", session=sid, brainos_version=__version__)
        log.info("research session %s started", sid)  # never the name, operator or notes
        return info

    def close(self, reason: str = "ended by operator") -> SessionInfo:
        info = self._active
        if info is None:
            raise SessionError("no active session")
        self.record("session_closed", reason=reason[:200])
        info = info.model_copy(
            update={"status": "closed", "closed_at_ns": time.time_ns(), "end_reason": reason[:200]}
        )
        self._active = None
        self._save(info)
        log.info("research session %s closed", info.id)
        return info

    def delete(self, session_id: str) -> int:
        if self._active is not None and self._active.id == session_id:
            raise SessionError("end the session before deleting it")
        folder = self.folder(session_id)
        if not folder.is_dir():
            raise SessionError(f"no session {session_id!r}", not_found=True)
        freed = sum(p.stat().st_size for p in folder.rglob("*") if p.is_file())
        shutil.rmtree(folder)
        log.info("research session %s deleted (%d bytes)", session_id, freed)
        return freed

    # ------------------------------------------------------------------ the session log
    def record(self, kind: str, **fields: Any) -> None:
        """Append an entry to the active session's log (no-op without an active session)."""
        info = self._active
        if info is None:
            return
        entry = {"at_ns": time.time_ns(), "kind": kind, **fields}
        self._append(info.id, entry)
        info.log_entries += 1

    def _append(self, session_id: str, entry: dict[str, Any]) -> None:
        line = json.dumps(entry, default=str, separators=(",", ":"))
        if len(line) > MAX_LOG_ENTRY:
            line = json.dumps(
                {"at_ns": entry.get("at_ns"), "kind": entry.get("kind"), "truncated": len(line)}
            )
        path = self.folder(session_id) / "log.jsonl"
        try:
            fd = open_private(path, "a")
            with os.fdopen(fd, "a", encoding="utf-8") as fh:
                fh.write(line + "\n")
        except OSError as exc:
            log.error("session %s: cannot write the session log: %s", session_id, exc)

    def add_model(self, model_id: str) -> None:
        info = self._active
        if info is not None and model_id not in info.models:
            info.models.append(model_id)
            self._save(info)

    def on_recording(self, kind: str, name: str, details: dict[str, Any]) -> None:
        """Recorder listener: recordings started during the session belong to it."""
        info = self._active
        if info is None:
            return
        if kind == "started" and name not in info.recordings:
            info.recordings.append(name)
            self._save(info)
        if kind in ("started", "stopped", "deleted", "recovered"):
            self.record(f"recording_{kind}", recording=name, **details)

    def tap(self, envelope: EventEnvelope, _json: str) -> None:
        """Bus tap: device status changes go to the session log (no data events)."""
        if self._active is None or envelope.event_type is not EventType.DEVICE_STATUS:
            return
        p = envelope.payload
        state = getattr(p, "state", None)
        self.record(
            "device_status",
            device_id=envelope.device_id,
            runtime_session=envelope.session_id,
            state=str(getattr(state, "value", state)),
            detail=str(getattr(p, "detail", ""))[:300],
        )

    def _save(self, info: SessionInfo) -> None:
        folder = ensure_private_dir(self.folder(info.id))
        write_private(folder / "session.json", info.model_dump_json(indent=1))
