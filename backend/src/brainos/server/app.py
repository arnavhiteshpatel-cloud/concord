"""FastAPI application factory."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from brainos import __version__
from brainos.adapters.simulated import OperatorIntentSource
from brainos.runtime import DeviceRegistry, Recorder, Runtime, RuntimeCommandError
from brainos.server import control_routes, live_routes, routes, sim_routes, ws
from brainos.server.deps import AppServices, error_response
from brainos.server.settings import Settings

log = logging.getLogger(__name__)


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings.from_env()
    intents = OperatorIntentSource()
    registry = DeviceRegistry(
        intents,
        settings.recordings_dir,
        seed=settings.seed,
        datasets_dir=settings.datasets_dir,
        models_dir=settings.models_dir,
    )
    runtime = Runtime(
        registry,
        Recorder(settings.recordings_dir),
        queue_size=settings.queue_size,
        reconnect_backoff_s=settings.reconnect_backoff_s,
    )

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        log.info("BrainOS runtime %s ready (simulation=%s)", __version__, settings.enable_sim)
        yield
        await runtime.shutdown()

    app = FastAPI(
        title="BrainOS Runtime API",
        version=__version__,
        description="Hardware-agnostic, read-only neural interface runtime (MVP). "
        "All devices in v1 are simulated or replayed.",
        lifespan=lifespan,
    )
    app.state.services = AppServices(settings=settings, runtime=runtime, intents=intents)

    @app.exception_handler(RuntimeCommandError)
    async def _command_error(_: Request, exc: RuntimeCommandError) -> JSONResponse:
        return error_response(exc)

    app.include_router(routes.router)
    app.include_router(live_routes.router)
    app.include_router(control_routes.router)
    if settings.enable_sim:
        app.include_router(sim_routes.router)
    app.include_router(ws.router)

    if settings.static_dir and (settings.static_dir / "index.html").exists():
        app.mount("/", StaticFiles(directory=settings.static_dir, html=True), name="console")
    else:
        log.info("no built console at %s (run `make build`); API only", settings.static_dir)
    return app
