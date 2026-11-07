"""REST API (/api/v1). Operator and developer control surface; read-only toward devices."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field

from brainos import __version__
from brainos.contracts.capabilities import (
    CAPABILITY_DESCRIPTIONS,
    EVENT_CAPABILITY,
    Capability,
    UnknownCapabilityError,
    parse_capabilities,
)
from brainos.contracts.events import SCHEMA_VERSION, envelope_json_schema
from brainos.contracts.protocol import (
    STREAM_PROTOCOL,
    DeviceDescriptor,
    ErrorCode,
    NegotiationResult,
    RuntimeSnapshot,
)
from brainos.runtime import DiagnosticsSnapshot, RecordingInfo, RuntimeCommandError
from brainos.runtime.registry import DeviceNotFoundError
from brainos.server.deps import AppServices, services
from brainos.server.reports import TestReport, load_reports

router = APIRouter(prefix="/api/v1")
Svc = Annotated[AppServices, Depends(services)]


class _Body(BaseModel):
    model_config = ConfigDict(extra="forbid")


class DeviceRequest(_Body):
    device_id: str = Field(min_length=1, max_length=64)


class NegotiateRequest(_Body):
    device_id: str | None = None
    required: list[str] = Field(default_factory=list, max_length=16)
    optional: list[str] = Field(default_factory=list, max_length=16)


class RecordingStartRequest(_Body):
    name: str | None = Field(default=None, max_length=48)


class RecordingStarted(BaseModel):
    name: str


class CapabilityInfo(BaseModel):
    capability: Capability
    description: str
    event_types: list[str]


class Health(BaseModel):
    status: str
    version: str
    schema_version: str
    stream_protocol: str
    simulation_enabled: bool
    read_only: bool


@router.get("/health")
async def health(svc: Svc) -> Health:
    return Health(
        status="ok",
        version=__version__,
        schema_version=SCHEMA_VERSION,
        stream_protocol=STREAM_PROTOCOL,
        simulation_enabled=svc.settings.enable_sim,
        read_only=True,
    )


@router.get("/capabilities")
async def capabilities() -> list[CapabilityInfo]:
    return [
        CapabilityInfo(
            capability=cap,
            description=CAPABILITY_DESCRIPTIONS[cap],
            event_types=[e.value for e, c in EVENT_CAPABILITY.items() if c is cap],
        )
        for cap in Capability
    ]


@router.get("/devices")
async def list_devices(svc: Svc) -> list[DeviceDescriptor]:
    return svc.runtime.registry.list()


@router.get("/devices/{device_id}")
async def get_device(device_id: str, svc: Svc) -> DeviceDescriptor:
    try:
        return svc.runtime.registry.describe(device_id)
    except DeviceNotFoundError:
        msg = f"unknown device '{device_id}'"
        raise RuntimeCommandError(ErrorCode.DEVICE_NOT_FOUND, msg) from None


@router.get("/runtime")
async def runtime_state(svc: Svc) -> RuntimeSnapshot:
    return svc.runtime.snapshot()


@router.post("/runtime/connect")
async def connect(body: DeviceRequest, svc: Svc) -> RuntimeSnapshot:
    return await svc.runtime.connect(body.device_id)


@router.post("/runtime/switch")
async def switch(body: DeviceRequest, svc: Svc) -> RuntimeSnapshot:
    return await svc.runtime.switch(body.device_id)


@router.post("/runtime/disconnect")
async def disconnect(svc: Svc) -> RuntimeSnapshot:
    return await svc.runtime.disconnect()


@router.post("/runtime/pause")
async def pause(svc: Svc) -> RuntimeSnapshot:
    return await svc.runtime.pause()


@router.post("/runtime/resume")
async def resume(svc: Svc) -> RuntimeSnapshot:
    return await svc.runtime.resume()


@router.get("/diagnostics")
async def diagnostics(svc: Svc) -> DiagnosticsSnapshot:
    return svc.runtime.diagnostics_snapshot()


@router.post("/negotiate")
async def negotiate_preview(body: NegotiateRequest, svc: Svc) -> NegotiationResult:
    """Dry-run negotiation against a device (or the active device if none given)."""
    try:
        required = parse_capabilities(body.required)
        optional = parse_capabilities(body.optional)
    except UnknownCapabilityError as exc:
        raise RuntimeCommandError(ErrorCode.UNKNOWN_CAPABILITY, str(exc)) from None
    return svc.runtime.preview_negotiation(body.device_id, required, optional)


@router.get("/schema/event")
async def event_schema() -> dict[str, Any]:
    return envelope_json_schema()


@router.get("/recordings")
async def list_recordings(svc: Svc) -> list[RecordingInfo]:
    return svc.runtime.recorder.list()


@router.post("/recordings/start")
async def start_recording(body: RecordingStartRequest, svc: Svc) -> RecordingStarted:
    return RecordingStarted(name=svc.runtime.start_recording(body.name))


@router.post("/recordings/stop")
async def stop_recording(svc: Svc) -> RecordingInfo:
    return svc.runtime.stop_recording()


@router.get("/system/tests")
async def test_reports(svc: Svc) -> list[TestReport]:
    return load_reports(svc.settings.reports_dir)
