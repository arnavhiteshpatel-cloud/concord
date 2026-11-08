"""REST for live sources, the processing pipeline, decoders and calibration (/api/v1).

All endpoints are operator controls on a localhost-only server. They never send anything
to acquisition devices (read-only): LSL inlets and Open Ephys SUB sockets only receive.
"""

from __future__ import annotations

import asyncio
from typing import Annotated, Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field

from concord.contracts.protocol import DeviceDescriptor, ErrorCode
from concord.runtime import RuntimeCommandError
from concord.runtime.pipeline import PipelineStartRequest, PipelineStatus, RouterSpec
from concord.server.deps import AppServices, services

router = APIRouter(prefix="/api/v1")
Svc = Annotated[AppServices, Depends(services)]


class _Body(BaseModel):
    model_config = ConfigDict(extra="forbid")


# --------------------------------------------------------------------------- LSL


class DiscoverRequest(_Body):
    wait_s: float = Field(default=1.5, ge=0.2, le=10)


class LSLStreamInfo(BaseModel):
    key: str
    device_id: str | None
    name: str
    type: str
    source_id: str | None
    hostname: str
    channel_count: int
    nominal_srate: float
    channel_format: str
    channels_described: bool
    units: list[str | None]
    declared_prerecorded: bool | None
    declared_synthetic: bool | None
    usable_as_signal: bool
    reason: str | None


class LSLDiscovery(BaseModel):
    library: str | None
    discovered_at_ns: int | None
    streams: list[LSLStreamInfo]
    error: str | None


class LSLSourceRequest(_Body):
    signal: str
    behavior: str | None = None
    markers: str | None = None


def _stream_info(s: Any) -> LSLStreamInfo:
    m = s.meta
    return LSLStreamInfo(
        key=s.key,
        device_id=("lsl:" + s.key) if s.usable_as_signal else None,
        name=m.name,
        type=m.type,
        source_id=m.source_id or None,
        hostname=m.hostname,
        channel_count=m.channel_count,
        nominal_srate=m.nominal_srate,
        channel_format=m.channel_format,
        channels_described=len(m.channels) == m.channel_count,
        units=sorted({c.unit for c in m.channels}, key=lambda u: u or "") if m.channels else [],
        declared_prerecorded=m.declaration.prerecorded,
        declared_synthetic=m.declaration.synthetic,
        usable_as_signal=s.usable_as_signal,
        reason=s.reason,
    )


def _library() -> str | None:
    try:
        from concord.adapters.lsl import discovery

        return discovery.library_info()
    except Exception:
        return None


@router.get("/sources/lsl")
async def lsl_streams(svc: Svc) -> LSLDiscovery:
    live = svc.runtime.registry.live
    return LSLDiscovery(
        library=_library(),
        discovered_at_ns=live.last_discovery_ns,
        streams=[_stream_info(s) for s in live.streams()],
        error=live.last_discovery_error,
    )


@router.post("/sources/lsl/discover")
async def lsl_discover(body: DiscoverRequest, svc: Svc) -> LSLDiscovery:
    live = svc.runtime.registry.live
    try:
        streams = await asyncio.to_thread(live.discover_lsl, body.wait_s)
    except Exception as exc:  # liblsl missing or network failure
        raise RuntimeCommandError(
            ErrorCode.UNSUPPORTED_OPERATION, f"LSL discovery failed: {exc}"
        ) from None
    return LSLDiscovery(
        library=_library(),
        discovered_at_ns=live.last_discovery_ns,
        streams=[_stream_info(s) for s in streams],
        error=None,
    )


@router.post("/sources/lsl")
async def lsl_configure(body: LSLSourceRequest, svc: Svc) -> DeviceDescriptor:
    try:
        return svc.runtime.registry.live.configure_lsl(body.signal, body.behavior, body.markers)
    except KeyError as exc:
        raise RuntimeCommandError(ErrorCode.DEVICE_NOT_FOUND, str(exc).strip("'\"")) from None
    except ValueError as exc:
        raise RuntimeCommandError(ErrorCode.PROTOCOL_ERROR, str(exc)) from None


# ------------------------------------------------------------------ Open Ephys


@router.post("/sources/openephys")
async def openephys_configure(body: dict[str, Any], svc: Svc) -> DeviceDescriptor:
    try:
        from concord.adapters.openephys import OpenEphysConfig
    except ImportError as exc:
        raise RuntimeCommandError(
            ErrorCode.UNSUPPORTED_OPERATION, f"Open Ephys support unavailable: {exc}"
        ) from None
    try:
        config = OpenEphysConfig.model_validate(body)
    except ValueError as exc:
        raise RuntimeCommandError(
            ErrorCode.PROTOCOL_ERROR, f"invalid Open Ephys config: {exc}"
        ) from None
    return svc.runtime.registry.live.configure_openephys(config)


@router.delete("/sources/{device_id}")
async def remove_source(device_id: str, svc: Svc) -> dict[str, bool]:
    rt = svc.runtime
    if rt.device is not None and rt.device.device_id == device_id and rt.adapter is not None:
        raise RuntimeCommandError(
            ErrorCode.INVALID_STATE, "disconnect the source before removing it"
        )
    removed = rt.registry.live.remove(device_id) or rt.registry.plugins.remove(device_id)
    return {"removed": removed}


# -------------------------------------------------------------------- pipeline


@router.get("/pipeline")
async def pipeline_status(svc: Svc) -> PipelineStatus:
    return svc.runtime.pipeline.status()


@router.post("/pipeline/start")
async def pipeline_start(body: PipelineStartRequest, svc: Svc) -> PipelineStatus:
    return await svc.runtime.start_pipeline_async(body)


@router.post("/pipeline/stop")
async def pipeline_stop(svc: Svc) -> PipelineStatus:
    return svc.runtime.stop_pipeline()


@router.post("/pipeline/router")
async def pipeline_router(body: RouterSpec, svc: Svc) -> PipelineStatus:
    return svc.runtime.set_router(body)


@router.get("/pipeline/presets")
async def pipeline_presets() -> dict[str, str]:
    try:
        from concord.processing import PRESET_INFO
    except ImportError:
        return {}
    from concord.runtime.pipeline import DECODED_PASSTHROUGH

    return {
        **PRESET_INFO,
        DECODED_PASSTHROUGH: (
            "Source already delivers decoder outputs (a replayed research decoder or an external "
            "system's decoder): pass them to the command router unchanged. No model is loaded."
        ),
    }


# Decoders (/models) and calibration (/calibration/*) moved to decoder_routes.py (M5).
