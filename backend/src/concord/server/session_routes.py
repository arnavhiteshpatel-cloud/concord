"""REST for the researcher workflow (Milestone 5, D): research sessions, export, safe stop,
stored data (deletion, retention) and the support report.

Operator endpoints on a localhost-only server. Deletions require ``confirm`` equal to the
name of what is deleted, so a mistyped or replayed request cannot delete something else.
"""

from __future__ import annotations

import asyncio
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Query
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse
from pydantic import BaseModel, ConfigDict, Field

from concord.runtime.export import (
    ExportInfo,
    ExportOptions,
    export_path,
    export_session,
    list_exports,
)
from concord.runtime.recorder import RecorderError
from concord.runtime.retention import RetentionError, RetentionResult, delete_model
from concord.runtime.safe_stop import SafeStopReport, safe_stop
from concord.runtime.sessions import SessionError, SessionInfo
from concord.server.deps import AppServices, services

router = APIRouter(prefix="/api/v1")
Svc = Annotated[AppServices, Depends(services)]


class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status, self.code, self.message = status, code, message


def api_error_response(exc: ApiError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status, content={"error": {"code": exc.code, "message": exc.message}}
    )


def _session_error(exc: SessionError) -> ApiError:
    if exc.not_found:
        return ApiError(404, "not_found", str(exc))
    return ApiError(409, "invalid_state", str(exc))


def _confirm(given: str | None, expected: str) -> None:
    if given != expected:
        raise ApiError(
            400,
            "confirmation_required",
            f"deleting is permanent: repeat the name in confirm={expected!r} to confirm",
        )


class _Body(BaseModel):
    model_config = ConfigDict(extra="forbid")


class NewSession(_Body):
    name: str = Field(min_length=1, max_length=80)
    operator: str | None = Field(default=None, max_length=80)
    notes: str | None = Field(default=None, max_length=4000)


class CloseSession(_Body):
    safe_stop: bool = True  # stop control, recording, decoding and the source first


class SafeStopRequest(_Body):
    reason: str | None = Field(default=None, max_length=200)


class SessionsStatus(BaseModel):
    active: SessionInfo | None
    sessions: list[SessionInfo]


class ExportFile(BaseModel):
    file: str
    size_bytes: int
    created_at_ns: int


class SessionDetail(BaseModel):
    session: SessionInfo
    log: list[dict[str, Any]]
    log_total: int
    exports: list[ExportFile]


class ClosedSession(BaseModel):
    session: SessionInfo
    safe_stop: SafeStopReport | None


class Deleted(BaseModel):
    deleted: str
    bytes: int
    also_deleted: list[str] = []


class UsageItem(BaseModel):
    count: int
    bytes: int


class StorageStatus(BaseModel):
    data_dir: str
    usage: dict[str, UsageItem]
    retention: dict[str, float | None]
    last_retention: RetentionResult | None
    recovered_recordings: list[str]
    interrupted_sessions: list[str]


# --------------------------------------------------------------------------- sessions


@router.get("/sessions")
async def list_sessions(svc: Svc) -> SessionsStatus:
    sm = svc.sessions
    return SessionsStatus(active=sm.active, sessions=await asyncio.to_thread(sm.list))


@router.post("/sessions")
async def create_session(body: NewSession, svc: Svc) -> SessionInfo:
    try:
        return svc.sessions.create(body.name, body.operator, body.notes)
    except SessionError as exc:
        raise _session_error(exc) from None


@router.get("/sessions/{session_id}")
async def get_session(
    session_id: str, svc: Svc, tail: int = Query(200, ge=0, le=5000)
) -> SessionDetail:
    sm = svc.sessions
    try:
        info = sm.get(session_id)
        entries = await asyncio.to_thread(sm.entries, session_id)
    except SessionError as exc:
        raise _session_error(exc) from None
    return SessionDetail(
        session=info,
        log=entries[-tail:] if tail else [],
        log_total=len(entries),
        exports=[ExportFile(**e) for e in list_exports(sm, session_id)],
    )


@router.post("/sessions/{session_id}/close")
async def close_session(
    session_id: str, svc: Svc, body: CloseSession | None = None
) -> ClosedSession:
    sm = svc.sessions
    if sm.active is None or sm.active.id != session_id:
        raise ApiError(409, "invalid_state", f"session {session_id} is not the active session")
    report = None
    if body is None or body.safe_stop:
        report = await safe_stop(svc.runtime, "session ended by operator")
        sm.record("safe_stop", **report.model_dump())
    return ClosedSession(session=sm.close("ended by operator"), safe_stop=report)


@router.post("/sessions/{session_id}/export")
async def export(session_id: str, svc: Svc, body: ExportOptions | None = None) -> ExportInfo:
    options = body or ExportOptions()
    try:
        return await asyncio.to_thread(
            export_session,
            svc.sessions,
            session_id,
            recorder=svc.runtime.recorder,
            models_dir=svc.runtime.registry.catalog.models_dir,
            reports_dir=svc.settings.reports_dir,
            options=options,
        )
    except SessionError as exc:
        raise _session_error(exc) from None


@router.get("/sessions/{session_id}/exports/{file}")
async def download_export(session_id: str, file: str, svc: Svc) -> FileResponse:
    try:
        path = export_path(svc.sessions, session_id, file)
    except SessionError as exc:
        raise _session_error(exc) from None
    return FileResponse(path, media_type="application/zip", filename=file)


@router.delete("/sessions/{session_id}")
async def delete_session(
    session_id: str,
    svc: Svc,
    confirm: str | None = None,
    delete_recordings: bool = False,
) -> Deleted:
    _confirm(confirm, session_id)
    sm = svc.sessions
    try:
        info = sm.get(session_id)
    except SessionError as exc:
        raise _session_error(exc) from None
    also: list[str] = []
    freed = 0
    if delete_recordings:
        for name in info.recordings:
            try:
                freed += svc.runtime.recorder.delete(name)
                also.append(name)
            except RecorderError:
                continue  # already deleted, or being written (kept)
    try:
        freed += sm.delete(session_id)
    except SessionError as exc:
        raise _session_error(exc) from None
    return Deleted(deleted=session_id, bytes=freed, also_deleted=also)


# --------------------------------------------------------------------------- safe stop


@router.post("/safe-stop")
async def safe_stop_route(svc: Svc, body: SafeStopRequest | None = None) -> SafeStopReport:
    """Command output off, recording stopped, decoding stopped, source disconnected."""
    report = await safe_stop(svc.runtime, "safe stop by operator")
    svc.sessions.record("safe_stop", **report.model_dump())
    return report


# --------------------------------------------------------------------------- stored data


def _usage(svc: AppServices) -> dict[str, UsageItem]:
    recs = svc.runtime.recorder.list()
    models_dir = svc.runtime.registry.catalog.models_dir
    models = list(models_dir.glob("*.json")) if models_dir.is_dir() else []
    sessions_dir = svc.settings.sessions_dir
    exports = list(sessions_dir.glob("*/exports/*.zip")) if sessions_dir.is_dir() else []
    sessions = [p for p in sessions_dir.iterdir() if p.is_dir()] if sessions_dir.is_dir() else []
    return {
        "recordings": UsageItem(count=len(recs), bytes=sum(r.size_bytes for r in recs)),
        "models": UsageItem(count=len(models), bytes=sum(p.stat().st_size for p in models)),
        "sessions": UsageItem(
            count=len(sessions),
            bytes=sum(f.stat().st_size for d in sessions for f in d.rglob("*") if f.is_file()),
        ),
        "exports": UsageItem(count=len(exports), bytes=sum(p.stat().st_size for p in exports)),
    }


@router.get("/storage")
async def storage(svc: Svc) -> StorageStatus:
    return StorageStatus(
        data_dir=str(svc.settings.data_dir),
        usage=await asyncio.to_thread(_usage, svc),
        retention=svc.settings.retention.as_dict(),
        last_retention=svc.last_retention,
        recovered_recordings=[name for name, _ in svc.runtime.recorder.recovered],
        interrupted_sessions=svc.interrupted_sessions,
    )


@router.delete("/recordings/{name}")
async def delete_recording(name: str, svc: Svc, confirm: str | None = None) -> Deleted:
    _confirm(confirm, name)
    try:
        freed = svc.runtime.recorder.delete(name)
    except RecorderError as exc:
        status = 404 if "no recording" in str(exc) or "invalid" in str(exc) else 409
        raise ApiError(
            status, "not_found" if status == 404 else "invalid_state", str(exc)
        ) from None
    return Deleted(deleted=name, bytes=freed)


@router.delete("/models/{model_id}")
async def delete_model_route(model_id: str, svc: Svc, confirm: str | None = None) -> Deleted:
    _confirm(confirm, model_id)
    st = svc.runtime.pipeline.status()
    running = st.decoder["model_id"] if st.running and st.decoder else None
    try:
        freed = delete_model(svc.runtime.registry.catalog.models_dir, model_id, in_use=running)
    except RetentionError as exc:
        status = 409 if "running pipeline" in str(exc) else 404
        raise ApiError(
            status, "invalid_state" if status == 409 else "not_found", str(exc)
        ) from None
    return Deleted(deleted=model_id, bytes=freed)


# --------------------------------------------------------------------------- support report


@router.get("/system/doctor", response_model=None)
async def doctor_report(
    svc: Svc, format: Literal["json", "markdown"] = "json"
) -> dict[str, Any] | PlainTextResponse:
    """The ``concord doctor`` support report for this server (no neural or personal data)."""
    from concord import doctor

    s = svc.settings
    report = await asyncio.to_thread(
        doctor.run,
        data_dir=s.data_dir,
        host=s.host,
        port=s.port,
        allow_remote=s.allow_remote,
        config_path=s.config_path,
        discover_plugins=False,  # this server's own discovery status is not re-run here
    )
    if format == "markdown":
        return PlainTextResponse(doctor.to_markdown(report), media_type="text/markdown")
    return report
