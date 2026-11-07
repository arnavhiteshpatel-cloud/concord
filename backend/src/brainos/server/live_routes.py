"""REST for live sources, the processing pipeline, decoders and calibration (/api/v1).

All endpoints are operator controls on a localhost-only server. They never send anything
to acquisition devices (read-only): LSL inlets and Open Ephys SUB sockets only receive.
"""

from __future__ import annotations

import asyncio
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field

from brainos.contracts.protocol import DeviceDescriptor, ErrorCode
from brainos.runtime import RuntimeCommandError
from brainos.runtime.pipeline import PipelineStartRequest, PipelineStatus, RouterSpec
from brainos.server.deps import AppServices, services

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
        from brainos.adapters.lsl import discovery

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
        from brainos.adapters.openephys import OpenEphysConfig
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
    return svc.runtime.start_pipeline(body)


@router.post("/pipeline/stop")
async def pipeline_stop(svc: Svc) -> PipelineStatus:
    return svc.runtime.stop_pipeline()


@router.post("/pipeline/router")
async def pipeline_router(body: RouterSpec, svc: Svc) -> PipelineStatus:
    return svc.runtime.set_router(body)


@router.get("/pipeline/presets")
async def pipeline_presets() -> dict[str, str]:
    try:
        from brainos.processing import PRESET_INFO
    except ImportError:
        return {}
    return dict(PRESET_INFO)


# ----------------------------------------------------------------------- models


class ModelInfo(BaseModel):
    summary: dict[str, Any]
    compatible: bool | None
    errors: list[str]
    warnings: list[str]


@router.get("/models")
async def list_models(svc: Svc) -> list[ModelInfo]:
    """All decoder models, with compatibility against the running pipeline's output (if any)."""
    try:
        from brainos.datasets import session_of
        from brainos.decoding import model as models
    except ImportError:
        return []
    rt = svc.runtime
    out_spec = rt.pipeline.status().output
    origin = rt._adapter_origin()
    result = []
    for m in await asyncio.to_thread(models.list_models, rt.registry.catalog.models_dir):
        if out_spec is None:
            result.append(
                ModelInfo(summary=models.summary(m), compatible=None, errors=[], warnings=[])
            )
            continue
        c = models.check(
            m,
            event_type=out_spec["event_type"],
            feature=out_spec["feature"],
            bin_ms=out_spec["bin_ms"],
            channel_count=out_spec["channel_count"],
            channel_labels=out_spec.get("channel_labels"),
            stream_identity=models.source_identity(origin),
            stream_session=session_of(origin or ""),
            stream_modality=dev.modality.value if (dev := rt.device) and dev.modality else None,
        )
        result.append(
            ModelInfo(
                summary=models.summary(m), compatible=c.ok, errors=c.errors, warnings=c.warnings
            )
        )
    return result


# ------------------------------------------------------------------ calibration


class CalibrationRequest(_Body):
    recordings: list[str] = Field(min_length=1, max_length=16)
    train_fraction: float = Field(default=0.8, ge=0.5, le=0.95)
    gap_bins: int = Field(default=12, ge=0, le=1000)
    feature_source: str | None = Field(default=None, max_length=64)
    # Milestone 4: "classifier" fits an LDA on a class-label behavior stream (discrete decoding)
    kind: Literal["regression", "classifier"] = "regression"
    label_dim: str | None = Field(default=None, max_length=32)
    class_names: list[str] | None = Field(default=None, max_length=16)
    tau_ms: float | None = Field(default=None, ge=0, le=5000)


class CalibrationResult(BaseModel):
    model: dict[str, Any]
    report: dict[str, Any]
    report_markdown: str


@router.post("/calibration/train")
async def calibration_train(body: CalibrationRequest, svc: Svc) -> CalibrationResult:
    """Fit a decoder on recordings (chronological train/held-out split) and save it.

    Recordings are referred to by name and must be closed BrainOS recordings in the
    recordings directory; nothing outside it is read.
    """
    try:
        from brainos.adapters.replay.format import RecordingFormatError, recording_path
        from brainos.decoding import model as models
        from brainos.decoding.calibrate import (
            CalibrationError,
            calibrate,
            calibrate_classifier,
            classifier_report_markdown,
            report_markdown,
        )
        from brainos.decoding.lda import DEFAULT_TAU_MS
    except ImportError as exc:
        raise RuntimeCommandError(
            ErrorCode.UNSUPPORTED_OPERATION, f"calibration unavailable: {exc}"
        ) from None
    rt = svc.runtime
    paths = []
    for name in body.recordings:
        if name == rt.recorder.active_name:
            raise RuntimeCommandError(
                ErrorCode.INVALID_STATE, f"recording {name!r} is still being written"
            )
        try:
            p = recording_path(svc.settings.recordings_dir, name)
        except RecordingFormatError as exc:
            raise RuntimeCommandError(ErrorCode.PROTOCOL_ERROR, str(exc)) from None
        if not p.exists():
            raise RuntimeCommandError(ErrorCode.DEVICE_NOT_FOUND, f"no recording {name!r}")
        paths.append(p)
    models_dir = rt.registry.catalog.models_dir
    model: models.Decoder
    try:
        if body.kind == "classifier":
            model, report = await asyncio.to_thread(
                calibrate_classifier,
                paths,
                label_dim=body.label_dim,
                class_names=body.class_names,
                train_fraction=body.train_fraction,
                gap_bins=body.gap_bins,
                tau_ms=body.tau_ms if body.tau_ms is not None else DEFAULT_TAU_MS,
                models_dir=models_dir,
                feature_source=body.feature_source,
            )
            md = classifier_report_markdown(report)
        else:
            model, report = await asyncio.to_thread(
                calibrate,
                paths,
                train_fraction=body.train_fraction,
                gap_bins=body.gap_bins,
                models_dir=models_dir,
                feature_source=body.feature_source,
            )
            md = report_markdown(report)
    except (CalibrationError, ValueError) as exc:
        raise RuntimeCommandError(ErrorCode.PROTOCOL_ERROR, f"calibration failed: {exc}") from None
    out = svc.settings.reports_dir / "calibration" / f"{model.model_id}.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(md)
    return CalibrationResult(model=models.summary(model), report=report, report_markdown=md)
