"""Deletion and the retention policy (``[retention]`` in the config file).

Deleting unlinks files; it does not securely erase them (SSD wear levelling, backups and
snapshots may keep copies — docs/SECURITY.md). Nothing in use is ever deleted: the active
recording, the active research session, and the model of the running pipeline.
"""

from __future__ import annotations

import contextlib
import logging
import re
import time
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel

from brainos.config import Retention
from brainos.runtime.recorder import Recorder, RecorderError
from brainos.runtime.sessions import SessionError, SessionManager

log = logging.getLogger(__name__)

MODEL_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.\-]{0,127}$")
DAY_NS = 86_400 * 1_000_000_000


class RetentionError(Exception):
    pass


class RetentionAction(BaseModel):
    kind: str  # recording | session | export | model
    name: str
    age_days: float
    bytes: int


class RetentionResult(BaseModel):
    ran_at_ns: int
    policy: dict[str, float | None]
    deleted: list[RetentionAction]
    kept_in_use: list[str]
    errors: list[str]


def model_path(models_dir: Path, model_id: str) -> Path:
    if not MODEL_ID.match(model_id) or model_id.endswith(".json"):
        raise RetentionError(f"invalid model id {model_id!r}")
    return models_dir / f"{model_id}.json"


def model_created_ns(path: Path) -> int:
    """A model file's creation time: its ``created_at`` field, else the file's mtime."""
    import json

    with contextlib.suppress(ValueError, OSError, TypeError):
        created = json.loads(path.read_text(encoding="utf-8")).get("created_at")
        if isinstance(created, str) and created:
            dt = datetime.fromisoformat(created.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=UTC)
            return int(dt.timestamp() * 1e9)
    return path.stat().st_mtime_ns


def delete_model(models_dir: Path, model_id: str, *, in_use: str | None) -> int:
    if in_use is not None and model_id == in_use:
        raise RetentionError(f"model {model_id} is used by the running pipeline; stop it first")
    path = model_path(models_dir, model_id)
    if not path.is_file():
        raise RetentionError(f"no model {model_id!r}")
    size = path.stat().st_size
    path.unlink()
    log.info("model %s deleted", model_id)
    return size


def enforce(
    policy: Retention,
    *,
    recorder: Recorder,
    sessions: SessionManager,
    models_dir: Path,
    model_in_use: str | None = None,
    now_ns: int | None = None,
) -> RetentionResult:
    """Delete what the policy says is too old. Called once at server start."""
    now = now_ns if now_ns is not None else time.time_ns()
    deleted: list[RetentionAction] = []
    kept: list[str] = []
    errors: list[str] = []

    def too_old(created_ns: int, days: float | None) -> float | None:
        if days is None:
            return None
        age = (now - created_ns) / DAY_NS
        return age if age > days else None

    if policy.recordings_days is not None:
        for rec in recorder.list():
            age = too_old(rec.created_at_ns, policy.recordings_days)
            if age is None:
                continue
            if rec.active:
                kept.append(f"recording {rec.name} (being written)")
                continue
            try:
                freed = recorder.delete(rec.name)
                deleted.append(
                    RetentionAction(
                        kind="recording", name=rec.name, age_days=round(age, 2), bytes=freed
                    )
                )
            except (RecorderError, OSError) as exc:
                errors.append(f"recording {rec.name}: {exc}")

    active = sessions.active.id if sessions.active else None
    for s in sessions.list():
        if s.id == active:
            if policy.sessions_days is not None or policy.exports_days is not None:
                kept.append(f"session {s.id} (active)")
            continue
        ended = s.closed_at_ns or s.created_at_ns
        age = too_old(ended, policy.sessions_days)
        if age is not None:
            try:
                freed = sessions.delete(s.id)
                deleted.append(
                    RetentionAction(kind="session", name=s.id, age_days=round(age, 2), bytes=freed)
                )
            except (SessionError, OSError) as exc:
                errors.append(f"session {s.id}: {exc}")
            continue
        if policy.exports_days is not None:
            exports = sessions.folder(s.id) / "exports"
            for z in sorted(exports.glob("*.zip")) if exports.is_dir() else []:
                age = too_old(z.stat().st_mtime_ns, policy.exports_days)
                if age is None:
                    continue
                try:
                    size = z.stat().st_size
                    z.unlink()
                    deleted.append(
                        RetentionAction(
                            kind="export",
                            name=f"{s.id}/{z.name}",
                            age_days=round(age, 2),
                            bytes=size,
                        )
                    )
                except OSError as exc:
                    errors.append(f"export {z.name}: {exc}")

    if policy.models_days is not None and models_dir.is_dir():
        for p in sorted(models_dir.glob("*.json")):
            model_id = p.name.removesuffix(".json")
            age = too_old(model_created_ns(p), policy.models_days)
            if age is None:
                continue
            if model_id == model_in_use:
                kept.append(f"model {model_id} (running)")
                continue
            try:
                freed = delete_model(models_dir, model_id, in_use=model_in_use)
                deleted.append(
                    RetentionAction(
                        kind="model", name=model_id, age_days=round(age, 2), bytes=freed
                    )
                )
            except (RetentionError, OSError) as exc:
                errors.append(f"model {model_id}: {exc}")

    result = RetentionResult(
        ran_at_ns=now, policy=policy.as_dict(), deleted=deleted, kept_in_use=kept, errors=errors
    )
    if deleted or errors:
        log.info(
            "retention policy: deleted %d item(s) (%s); %d error(s)",
            len(deleted),
            ", ".join(f"{d.kind} {d.name}" for d in deleted) or "-",
            len(errors),
        )
    return result
