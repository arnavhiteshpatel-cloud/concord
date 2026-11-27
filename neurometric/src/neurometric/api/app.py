"""NeuroMetric FastAPI application.

``create_app(db_path)`` returns an app over one SQLite study database. Run with
``python -m neurometric.api serve --db nm.sqlite`` (see ``neurometric/api/__main__.py``).

Hardening defaults: CORS off (enable only with explicit origins), security headers, request
size limits, login rate limiting, bearer tokens with expiry, OpenAPI docs off unless
``NEUROMETRIC_API_DOCS=1``, static web app served from ``web/dist`` when present.
"""
from __future__ import annotations

import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Optional

from fastapi import APIRouter, Body, Depends, FastAPI, Query, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse, Response
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from ..instruments.engine import ResponseError, score as score_instrument, validate_response
from ..study import StudyService
from ..study.errors import AuthenticationFailed, NotFound, StudyError, ValidationFailed
from ..study.exports import verify_export, zip_dir
from ..study.permissions import Actor, matrix, require
from ..tasks.battery import BATTERY_VERSION, TASKS, battery_manifest, stimuli
from . import models as M
from .middleware import (BodySizeLimitMiddleware, LoginRateLimiter, SecurityHeadersMiddleware,
                         env_int)

DEFAULT_WEB_DIST = Path(__file__).resolve().parents[3] / "web" / "dist"
_bearer = HTTPBearer(auto_error=False)


def create_app(db_path: str | Path, *, web_dist: Optional[str | Path] = None,
               cors_origins: Optional[list[str]] = None, clock: Optional[Callable] = None,
               max_body_bytes: Optional[int] = None,
               rate_limiter: Optional[LoginRateLimiter] = None,
               backup_dir: Optional[str | Path] = None) -> FastAPI:
    docs = os.environ.get("NEUROMETRIC_API_DOCS") == "1"
    app = FastAPI(title="NeuroMetric API", version=BATTERY_VERSION,
                  description="Research software; not a medical device. Technical controls "
                              "only: not Part 11 / HIPAA compliant.",
                  docs_url="/api/docs" if docs else None, redoc_url=None,
                  openapi_url="/api/openapi.json" if docs else None)
    svc = StudyService(db_path, clock)
    app.state.svc = svc
    app.state.limiter = rate_limiter or LoginRateLimiter()
    app.state.backup_dir = Path(backup_dir or os.environ.get("NEUROMETRIC_BACKUP_DIR") or
                                Path(str(db_path)).resolve().parent / "backups")

    @app.exception_handler(StudyError)
    async def _study_error(request: Request, exc: StudyError):
        body = {"error": exc.code, "message": str(exc)}
        if exc.detail:
            body["detail"] = jsonable_encoder(exc.detail)
        headers = {"WWW-Authenticate": "Bearer"} if exc.status == 401 else None
        return JSONResponse(body, status_code=exc.status, headers=headers)

    @app.exception_handler(ValueError)
    async def _value_error(request: Request, exc: ValueError):
        return JSONResponse({"error": "validation_failed", "message": str(exc)}, status_code=422)

    def actor(cred: Optional[HTTPAuthorizationCredentials] = Depends(_bearer)) -> Actor:
        if cred is None or cred.scheme.lower() != "bearer":
            raise AuthenticationFailed("missing bearer token")
        return svc.actor_from_token(cred.credentials)

    r = APIRouter(prefix="/api")

    # ------------------------------------------------------------------ public
    @r.get("/health")
    def health():
        return {"status": "ok", "battery_version": BATTERY_VERSION,
                "notice": "Research software; not a medical device."}

    @r.get("/battery")
    def get_battery():
        return battery_manifest()

    @r.get("/battery/{task_id}/stimuli")
    def get_stimuli(task_id: str, seed: int = Query(0, ge=0, le=2 ** 31 - 1)):
        if task_id not in {t.id for t in TASKS}:
            raise NotFound(f"task {task_id} not found")
        return jsonable_encoder(stimuli(task_id, seed))

    # ------------------------------------------------------------------ auth
    @r.post("/auth/login")
    def login(body: M.LoginIn, request: Request):
        ip = request.client.host if request.client else "unknown"
        lim: LoginRateLimiter = app.state.limiter
        if not lim.check(ip, body.username):
            return JSONResponse({"error": "rate_limited",
                                 "message": "too many login attempts; try again later"},
                                status_code=429, headers={"Retry-After": str(int(lim.window))})
        try:
            out = svc.login(body.username, body.password)
        except AuthenticationFailed:
            lim.failure(ip, body.username)
            raise
        lim.success(ip, body.username)
        return out

    @r.post("/auth/logout")
    def logout(cred: Optional[HTTPAuthorizationCredentials] = Depends(_bearer)):
        if cred:
            svc.logout(cred.credentials)
        return {"status": "logged_out"}

    @r.get("/auth/me")
    def me(a: Actor = Depends(actor)):
        return {"user_id": a.user_id, "org_id": a.org_id, "role": a.role, "username": a.username,
                "display_name": a.display_name, "participant_id": a.participant_id,
                "site_ids": sorted(a.site_ids), "linked_participants": sorted(a.linked_participants)}

    @r.get("/permissions")
    def permissions(a: Actor = Depends(actor)):
        return matrix()

    # ------------------------------------------------------------------ administration
    @r.post("/users", status_code=201)
    def create_user(body: M.UserIn, a: Actor = Depends(actor)):
        return svc.create_user(a, org_id=a.org_id, **body.model_dump())

    @r.get("/users")
    def list_users(a: Actor = Depends(actor)):
        return svc.list_users(a)

    @r.post("/users/{user_id}/deactivate")
    def deactivate(user_id: str, body: M.ReasonIn, a: Actor = Depends(actor)):
        svc.deactivate_user(a, user_id, body.reason)
        return {"status": "deactivated"}

    @r.post("/sites", status_code=201)
    def create_site(body: M.SiteIn, a: Actor = Depends(actor)):
        return svc.create_site(a, body.code, body.name)

    @r.get("/sites")
    def list_sites(a: Actor = Depends(actor)):
        return svc.list_sites(a)

    @r.post("/sponsors", status_code=201)
    def create_sponsor(body: M.SponsorIn, a: Actor = Depends(actor)):
        return svc.create_sponsor(a, body.name)

    @r.get("/sponsors")
    def list_sponsors(a: Actor = Depends(actor)):
        return svc.list_sponsors(a)

    # ------------------------------------------------------------------ studies
    @r.post("/studies", status_code=201)
    def create_study(body: M.StudyIn, a: Actor = Depends(actor)):
        return svc.create_study(a, **body.model_dump())

    @r.get("/studies")
    def list_studies(a: Actor = Depends(actor)):
        return svc.list_studies(a)

    @r.get("/studies/{sid}")
    def get_study(sid: str, a: Actor = Depends(actor)):
        return svc.get_study(a, sid)

    @r.patch("/studies/{sid}")
    def patch_study(sid: str, body: M.StudyPatch, a: Actor = Depends(actor)):
        return svc.update_study(a, sid, body.changes, body.reason)

    @r.post("/studies/{sid}/sites/{site_id}", status_code=201)
    def add_study_site(sid: str, site_id: str, a: Actor = Depends(actor)):
        svc.add_site_to_study(a, sid, site_id)
        return {"study_id": sid, "site_id": site_id}

    @r.post("/studies/{sid}/protocol-versions", status_code=201)
    def add_protocol(sid: str, body: M.ProtocolIn, a: Actor = Depends(actor)):
        return svc.add_protocol_version(a, sid, **body.model_dump())

    @r.get("/studies/{sid}/protocol-versions")
    def list_protocols(sid: str, a: Actor = Depends(actor)):
        return svc.list_protocol_versions(a, sid)

    @r.post("/studies/{sid}/schedules", status_code=201)
    def create_schedule(sid: str, body: M.ScheduleIn, a: Actor = Depends(actor)):
        return svc.create_schedule(a, sid, body.name, body.definition, body.protocol_version_id)

    @r.get("/studies/{sid}/schedules")
    def list_schedules(sid: str, a: Actor = Depends(actor)):
        return svc.list_schedules(a, sid)

    @r.post("/studies/{sid}/participants", status_code=201)
    def create_participant(sid: str, body: M.ParticipantIn, a: Actor = Depends(actor)):
        return svc.create_participant(a, sid, **body.model_dump())

    @r.get("/studies/{sid}/participants")
    def list_participants(sid: str, a: Actor = Depends(actor)):
        return svc.list_participants(a, sid)

    @r.post("/studies/{sid}/missed-visits")
    def missed(sid: str, a: Actor = Depends(actor)):
        return {"marked_missed": svc.mark_missed_visits(a, sid)}

    @r.get("/studies/{sid}/dashboard")
    def dashboard(sid: str, a: Actor = Depends(actor)):
        return svc.dashboard(a, sid)

    @r.post("/studies/{sid}/deviations", status_code=201)
    def report_deviation(sid: str, body: M.DeviationIn, a: Actor = Depends(actor)):
        return svc.report_deviation(a, sid, **body.model_dump())

    @r.get("/studies/{sid}/deviations")
    def list_deviations(sid: str, a: Actor = Depends(actor)):
        return svc.list_deviations(a, sid)

    @r.post("/studies/{sid}/queries", status_code=201)
    def raise_query(sid: str, body: M.QueryIn, a: Actor = Depends(actor)):
        return svc.raise_query(a, sid, body.record_table, body.record_id, body.question, body.field)

    @r.get("/studies/{sid}/queries")
    def list_queries(sid: str, status: Optional[str] = None, a: Actor = Depends(actor)):
        return svc.list_queries(a, sid, status)

    @r.put("/studies/{sid}/retention")
    def set_retention(sid: str, body: M.RetentionIn, a: Actor = Depends(actor)):
        return svc.set_retention_policy(a, sid, body.data_category, body.retain_days)

    @r.get("/studies/{sid}/retention")
    def get_retention(sid: str, a: Actor = Depends(actor)):
        return svc.list_retention_policies(a, sid)

    @r.post("/studies/{sid}/exports")
    def export(sid: str, audience: str = Query("sponsor", pattern="^(sponsor|full)$"),
               a: Actor = Depends(actor)):
        """Build the export in a temporary directory, verify it, return it as a zip; no copy
        of the exported data is left on the server."""
        with tempfile.TemporaryDirectory(prefix="nm-export-") as d:
            manifest = svc.export_study(a, sid, d, audience)
            v = verify_export(d)
            if not v["ok"]:  # pragma: no cover - defensive
                raise ValidationFailed("export failed self-verification", detail=v)
            data = zip_dir(d)
        name = f"neurometric-{manifest['study']['code']}-{audience}.zip"
        return Response(data, media_type="application/zip", headers={
            "Content-Disposition": f'attachment; filename="{name}"',
            "X-NeuroMetric-Audit-Head": manifest["audit_chain_head"]})

    # ------------------------------------------------------------------ participants
    @r.get("/participants/{pid}")
    def get_participant(pid: str, a: Actor = Depends(actor)):
        return svc.get_participant(a, pid)

    @r.post("/participants/{pid}/transition")
    def transition(pid: str, body: M.TransitionIn, a: Actor = Depends(actor)):
        return svc.transition(a, pid, body.to_state, body.reason)

    @r.get("/participants/{pid}/enrollment-history")
    def enrollment_history(pid: str, a: Actor = Depends(actor)):
        return svc.enrollment_history(a, pid)

    @r.put("/participants/{pid}/reid")
    def set_reid(pid: str, body: M.ReidIn, a: Actor = Depends(actor)):
        svc.set_reidentification(a, pid, body.identifier)
        return {"status": "stored_encrypted"}

    @r.post("/participants/{pid}/reid/reveal")
    def reveal_reid(pid: str, body: M.ReasonIn, a: Actor = Depends(actor)):
        return {"identifier": svc.get_reidentification(a, pid, body.reason)}

    @r.post("/participants/{pid}/consent", status_code=201)
    def consent(pid: str, body: M.ConsentIn, a: Actor = Depends(actor)):
        return svc.record_consent(a, pid, body.consent_document_id, body.consent_version,
                                  body.scopes)

    @r.get("/participants/{pid}/consent")
    def get_consent(pid: str, a: Actor = Depends(actor)):
        return svc.get_consent(a, pid)

    @r.post("/participants/{pid}/consent/withdraw")
    def withdraw(pid: str, body: M.WithdrawIn, a: Actor = Depends(actor)):
        return svc.withdraw_consent(a, pid, body.reason, scopes=body.scopes, action=body.action)

    @r.post("/participants/{pid}/visits/generate", status_code=201)
    def gen_visits(pid: str, body: M.GenerateVisitsIn, a: Actor = Depends(actor)):
        return svc.generate_visits(a, pid, body.schedule_id, body.anchor_date)

    @r.get("/participants/{pid}/visits")
    def list_visits(pid: str, a: Actor = Depends(actor)):
        return svc.list_visits(a, pid)

    @r.post("/visits/{vid}/complete")
    def complete_visit(vid: str, body: M.ReasonIn, a: Actor = Depends(actor)):
        return svc.complete_visit(a, vid, body.reason)

    @r.post("/participants/{pid}/devices", status_code=201)
    def add_device(pid: str, body: M.DeviceIn, a: Actor = Depends(actor)):
        return svc.add_device_config(a, pid, body.modality, body.make_model, body.settings,
                                     body.calibration_state)

    @r.get("/participants/{pid}/devices")
    def list_devices(pid: str, a: Actor = Depends(actor)):
        return svc.list_device_configs(a, pid)

    @r.post("/participants/{pid}/sessions", status_code=201)
    def upload_session(pid: str, body: M.SessionIn, a: Actor = Depends(actor)):
        d = body.model_dump()
        d["battery_version"] = d["battery_version"] or BATTERY_VERSION
        return svc.upload_session(a, pid, **d)

    @r.get("/participants/{pid}/sessions")
    def list_sessions(pid: str, a: Actor = Depends(actor)):
        return svc.list_sessions(a, pid)

    @r.get("/sessions/{session_id}")
    def get_session(session_id: str, include_events: bool = False, a: Actor = Depends(actor)):
        return jsonable_encoder(svc.get_session(a, session_id, include_events))

    @r.post("/participants/{pid}/questionnaires", status_code=201)
    def submit_response(pid: str, body: M.ResponseIn, a: Actor = Depends(actor)):
        return svc.submit_response(a, pid, body.instrument_id, body.answers, version=body.version,
                                   visit_id=body.visit_id, language=body.language)

    @r.get("/participants/{pid}/questionnaires")
    def list_responses(pid: str, a: Actor = Depends(actor)):
        return svc.list_responses(a, pid)

    @r.get("/participants/{pid}/assignments")
    def list_assignments(pid: str, a: Actor = Depends(actor)):
        return svc.list_assignments(a, pid)

    @r.post("/participants/{pid}/missing", status_code=201)
    def record_missing(pid: str, body: M.MissingIn, a: Actor = Depends(actor)):
        return svc.record_missing(a, pid, **body.model_dump())

    @r.get("/participants/{pid}/telemetry/summary")
    def telemetry_summary(pid: str, a: Actor = Depends(actor)):
        return svc.telemetry_summary(a, pid)

    @r.get("/participants/{pid}/telemetry/state")
    def get_tstate(pid: str, a: Actor = Depends(actor)):
        return svc.telemetry_state(a, pid)

    @r.put("/participants/{pid}/telemetry/state")
    def set_tstate(pid: str, body: M.TelemetryStateIn, a: Actor = Depends(actor)):
        return svc.set_telemetry_state(a, pid, body.state, body.reason)

    @r.get("/participants/{pid}/export")
    def subject_export(pid: str, a: Actor = Depends(actor)):
        return jsonable_encoder(svc.export_subject(a, pid))

    @r.delete("/participants/{pid}")
    def subject_delete(pid: str, body: M.ReasonIn, a: Actor = Depends(actor)):
        return {"deleted": svc.delete_subject(a, pid, body.reason)}

    # ------------------------------------------------------------------ instruments
    @r.get("/instruments")
    def list_instruments(a: Actor = Depends(actor)):
        require(a, "instrument.read")
        return svc.instruments.list()

    @r.get("/instruments/{iid}")
    def get_instrument(iid: str, version: Optional[str] = None, a: Actor = Depends(actor)):
        require(a, "instrument.read")
        try:
            return svc.instruments.get(iid, version).public()
        except KeyError:
            raise NotFound(f"instrument {iid} not found") from None

    @r.post("/instruments/{iid}/score")
    def score(iid: str, body: M.ScoreIn, a: Actor = Depends(actor)):
        """Score answers without storing them (preview / calculator)."""
        require(a, "instrument.read")
        try:
            inst = svc.instruments.get(iid, body.version)
        except KeyError:
            raise NotFound(f"instrument {iid} not found") from None
        try:
            clean, _, missing = validate_response(inst, body.answers, allow_free_text=False)
        except ResponseError as e:
            raise ValidationFailed(str(e), errors=e.errors) from None
        return {"instrument_id": inst.id, "version": inst.version,
                "scores": score_instrument(inst, clean), "missing_items": missing}

    # ------------------------------------------------------------------ telemetry
    @r.post("/telemetry/ingest", status_code=201)
    def ingest(payload: dict[str, Any] = Body(...), a: Actor = Depends(actor)):
        return svc.ingest_telemetry(a, payload)

    @r.get("/telemetry/mine")
    def telemetry_mine(participant_id: Optional[str] = None, a: Actor = Depends(actor)):
        pid = participant_id or a.participant_id
        if not pid:
            raise ValidationFailed("participant_id is required")
        return svc.review_own_telemetry(a, pid)

    # ------------------------------------------------------------------ data management
    @r.post("/queries/{qid}/answer")
    def answer_query(qid: str, body: M.AnswerIn, a: Actor = Depends(actor)):
        return svc.answer_query(a, qid, body.answer)

    @r.post("/queries/{qid}/close")
    def close_query(qid: str, body: M.CloseIn, a: Actor = Depends(actor)):
        return svc.close_query(a, qid, body.reason)

    @r.post("/queries/{qid}/reopen")
    def reopen_query(qid: str, body: M.ReasonIn, a: Actor = Depends(actor)):
        return svc.reopen_query(a, qid, body.reason)

    @r.patch("/records/{table}/{rid}")
    def correct(table: str, rid: str, body: M.CorrectionIn, a: Actor = Depends(actor)):
        return jsonable_encoder(svc.correct_record(a, table, rid, body.changes, body.reason))

    @r.get("/records/{table}/{rid}/history")
    def history(table: str, rid: str, a: Actor = Depends(actor)):
        return svc.record_history(a, table, rid)

    @r.post("/signatures", status_code=201)
    def sign(body: M.SignIn, a: Actor = Depends(actor)):
        return svc.sign(a, body.password, body.record_table, body.record_id, body.meaning)

    @r.get("/signatures/{sig_id}/verify")
    def verify_sig(sig_id: str, a: Actor = Depends(actor)):
        return svc.verify_signature(a, sig_id)

    # ------------------------------------------------------------------ audit & admin
    @r.get("/audit")
    def audit(table: Optional[str] = None, limit: int = Query(200, ge=1, le=1000),
              offset: int = Query(0, ge=0), a: Actor = Depends(actor)):
        require(a, "audit.read")
        return svc.audit.entries(a.org_id, limit, offset, table)

    @r.get("/audit/verify")
    def audit_verify(expected_head: Optional[str] = None, a: Actor = Depends(actor)):
        require(a, "audit.verify")
        return svc.audit.verify_chain(expected_head)

    @r.get("/admin/integrity")
    def integrity(a: Actor = Depends(actor)):
        return svc.integrity_check(a)

    @r.post("/admin/backup", status_code=201)
    def backup(a: Actor = Depends(actor)):
        require(a, "backup.run")
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        return svc.backup(a, app.state.backup_dir / f"neurometric-{stamp}.sqlite")

    @r.post("/admin/backup/verify")
    def backup_verify(body: M.BackupVerifyIn, a: Actor = Depends(actor)):
        require(a, "backup.run")
        return svc.verify_backup(app.state.backup_dir / body.name)

    @r.post("/admin/retention/run")
    def retention_run(a: Actor = Depends(actor)):
        return {"purges": svc.run_retention_purge(a)}

    app.include_router(r)

    # ------------------------------------------------------------------ middleware & static
    limits = {"/api/telemetry": 64 * 1024, "/api/auth": 8 * 1024}
    app.add_middleware(BodySizeLimitMiddleware,
                       default_limit=max_body_bytes or env_int("NEUROMETRIC_MAX_BODY_BYTES",
                                                               16 * 1024 * 1024),
                       limits=limits)
    origins = cors_origins if cors_origins is not None else [
        o for o in os.environ.get("NEUROMETRIC_CORS_ORIGINS", "").split(",") if o.strip()]
    if origins:  # CORS is off unless origins are configured explicitly
        from fastapi.middleware.cors import CORSMiddleware
        app.add_middleware(CORSMiddleware, allow_origins=origins, allow_credentials=False,
                           allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
                           allow_headers=["Authorization", "Content-Type"])
    app.add_middleware(SecurityHeadersMiddleware)
    dist = Path(web_dist) if web_dist else Path(os.environ.get("NEUROMETRIC_WEB_DIST",
                                                               DEFAULT_WEB_DIST))
    if dist.is_dir():
        from fastapi.staticfiles import StaticFiles
        app.mount("/", StaticFiles(directory=str(dist), html=True), name="web")
    return app


def app_from_env() -> FastAPI:
    """Factory for ``uvicorn --factory neurometric.api.app:app_from_env`` (NEUROMETRIC_DB)."""
    db = os.environ.get("NEUROMETRIC_DB")
    if not db:
        raise RuntimeError("set NEUROMETRIC_DB to the study database path")
    return create_app(db)
