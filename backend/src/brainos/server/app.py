"""FastAPI application factory."""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from brainos import __version__
from brainos.adapters.simulated import OperatorIntentSource
from brainos.runtime import DeviceRegistry, Recorder, Runtime, RuntimeCommandError
from brainos.runtime.plugins import PluginRegistry
from brainos.runtime.retention import enforce
from brainos.runtime.sessions import SessionManager
from brainos.security import ensure_private_dir, harden_tree
from brainos.server import (
    compat_routes,
    control_routes,
    decoder_routes,
    live_routes,
    plugin_routes,
    routes,
    session_routes,
    sim_routes,
    ws,
)
from brainos.server.audit import SessionAuditMiddleware
from brainos.server.deps import AppServices, error_response
from brainos.server.origin import LocalOriginMiddleware
from brainos.server.settings import Settings

log = logging.getLogger(__name__)


async def _discover(plugins: PluginRegistry, runtime: Runtime | None = None) -> object:
    try:
        return await plugins.discover()
    except Exception as exc:  # reported via GET /plugins (error); the runtime keeps working
        log.warning("startup plugin discovery failed: %s", exc)
        return None
    finally:
        if runtime is not None:
            try:  # decoder plugins (M5), reported via GET /models/discovery
                await runtime.pipeline.registry.discover_plugins()
            except Exception as exc:
                log.warning("startup decoder plugin discovery failed: %s", exc)


def startup_maintenance(svc: AppServices) -> None:
    """Private permissions, crash recovery and the retention policy (Milestone 5, D).

    Runs before the server accepts requests. Failures are logged and never prevent startup.
    """
    s = svc.settings
    try:
        # the data directory itself; subdirectories are created 0700 by their owners when
        # first needed (recorder, sessions, logging) and existing ones are tightened here.
        # Public datasets are left as they are (they may be shared with other users).
        ensure_private_dir(s.data_dir)
        fixed = harden_tree(s.data_dir, skip=("datasets",))
        if fixed.dirs_fixed or fixed.files_fixed:
            log.info(
                "data directory permissions tightened: %d dir(s) -> 0700, %d file(s) -> 0600",
                fixed.dirs_fixed,
                fixed.files_fixed,
            )
    except OSError as exc:
        log.error("could not secure the data directory permissions: %s", exc)
    rt = svc.runtime
    try:
        recovered = rt.recorder.recover()
        if recovered:
            log.warning(
                "%d interrupted recording(s) recovered and marked incomplete", len(recovered)
            )
    except OSError as exc:
        log.error("recording recovery failed: %s", exc)
    try:
        svc.interrupted_sessions = svc.sessions.recover()
    except OSError as exc:
        log.error("session recovery failed: %s", exc)
    if s.retention.active:
        try:
            svc.last_retention = enforce(
                s.retention,
                recorder=rt.recorder,
                sessions=svc.sessions,
                models_dir=rt.registry.catalog.models_dir,
            )
        except OSError as exc:
            log.error("retention policy failed: %s", exc)


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings.from_env()
    intents = OperatorIntentSource()
    registry = DeviceRegistry(
        intents,
        settings.recordings_dir,
        seed=settings.seed,
        datasets_dir=settings.datasets_dir,
        models_dir=settings.models_dir,
        plugins=PluginRegistry(python=settings.plugin_python, extra_path=settings.plugin_path),
    )
    recorder = Recorder(
        settings.recordings_dir,
        max_duration_s=settings.recording_max_duration_s,
        max_duration_no_raw_s=settings.recording_max_duration_no_raw_s,
        max_bytes=settings.recording_max_bytes,
        min_free_bytes=settings.recording_min_free_bytes,
    )
    runtime = Runtime(
        registry,
        recorder,
        queue_size=settings.queue_size,
        reconnect_backoff_s=settings.reconnect_backoff_s,
    )
    # decoder hosts run with the same interpreter / extra path as source-plugin hosts
    runtime.pipeline.registry.configure(settings.plugin_python, settings.plugin_path)
    sessions = SessionManager(settings.sessions_dir)
    recorder.listeners.append(sessions.on_recording)
    runtime.bus.add_tap(sessions.tap)
    svc = AppServices(settings=settings, runtime=runtime, intents=intents, sessions=sessions)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        await asyncio.to_thread(startup_maintenance, svc)
        log.info("BrainOS runtime %s ready (simulation=%s)", __version__, settings.enable_sim)
        discovery: asyncio.Task[object] | None = None
        if settings.discover_plugins:
            # in the background: plugin hosts start in subprocesses; startup does not wait
            discovery = asyncio.create_task(
                _discover(registry.plugins, runtime), name="plugin-discovery"
            )
        yield
        if discovery is not None:
            discovery.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await discovery
        await runtime.shutdown()
        if sessions.active is not None:  # a clean stop closes the session (a crash cannot)
            sessions.close("BrainOS was stopped while the session was active")

    app = FastAPI(
        title="BrainOS Runtime API",
        version=__version__,
        description="Hardware-agnostic, read-only neural interface runtime (MVP). "
        "All devices in v1 are simulated or replayed.",
        lifespan=lifespan,
    )
    app.state.services = svc

    @app.exception_handler(RuntimeCommandError)
    async def _command_error(_: Request, exc: RuntimeCommandError) -> JSONResponse:
        return error_response(exc)

    @app.exception_handler(session_routes.ApiError)
    async def _api_error(_: Request, exc: session_routes.ApiError) -> JSONResponse:
        return session_routes.api_error_response(exc)

    app.add_middleware(SessionAuditMiddleware)
    # outermost: web pages on other sites must not reach the unauthenticated local API
    app.add_middleware(LocalOriginMiddleware, allow_remote=settings.allow_remote)
    app.include_router(routes.router)
    app.include_router(live_routes.router)
    app.include_router(decoder_routes.router)
    app.include_router(plugin_routes.router)
    app.include_router(control_routes.router)
    app.include_router(compat_routes.router)
    app.include_router(session_routes.router)
    if settings.enable_sim:
        app.include_router(sim_routes.router)
    app.include_router(ws.router)

    if settings.static_dir and (settings.static_dir / "index.html").exists():
        app.mount("/", StaticFiles(directory=settings.static_dir, html=True), name="console")
    else:
        log.info("no built console at %s (run `make build`); API only", settings.static_dir)
    return app
