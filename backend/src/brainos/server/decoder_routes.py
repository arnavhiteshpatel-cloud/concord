"""REST for decoders and calibration (/api/v1, Milestone 5).

``GET /models`` lists every decoder BrainOS can run (BrainOS-trained JSON models, imported
model files, decoder plugins) with its compatibility verdict against the running pipeline's
output, or against what a given preset would produce on the connected source. Model files in
unsafe formats are refused until the operator marks the exact file trusted
(``POST /models/{id}/trust``); the decision is recorded with its time.

Calibration: ``GET /calibration/options`` (capabilities, families, what each needs),
``POST /calibration/check`` (do these recordings provide the labels?), ``POST
/calibration/train`` (fit, evaluate, save model + manifest + report). Recordings are named,
closed BrainOS recordings in the recordings directory; nothing outside it is read.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict, Field

from brainos.contracts.protocol import ErrorCode
from brainos.runtime import RuntimeCommandError
from brainos.runtime.pipeline import PipelineError
from brainos.server.deps import AppServices, services

router = APIRouter(prefix="/api/v1")
Svc = Annotated[AppServices, Depends(services)]


class _Body(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ModelInfo(BaseModel):
    summary: dict[str, Any]
    compatible: bool | None
    errors: list[str]
    warnings: list[str]
    # Milestone 5
    mapping_available: bool = False
    checked_against: str | None = None  # "running pipeline" | "<preset> preview"


class DiscoveryStatus(BaseModel):
    discovering: bool
    discovered_at_ns: int | None
    error: str | None
    plugins: int


def _check(svc: AppServices, preset: str | None, bin_ms: float | None, mapping: bool) -> Any:
    """Streams + context to check models against: the running pipeline, or a preview."""
    from brainos.datasets import session_of
    from brainos.decoding import model as models

    rt = svc.runtime
    st = rt.pipeline.status()
    origin = rt._adapter_origin()
    device = rt.device
    if st.running and st.outputs:
        streams, label, pre, params = st.outputs, "running pipeline", st.preset, None
    elif preset and device is not None and rt.pipeline.available:
        processing: dict[str, Any] = {"preset": preset}
        if bin_ms is not None:
            processing["bin_ms"] = bin_ms
        try:
            plan = rt.pipeline.plan_outputs(processing, device)
        except PipelineError:
            return None
        streams, label, pre, params = plan["outputs"], f"{preset} preview", preset, plan["params"]
        if not streams:
            return None
    else:
        return None

    def run(manifest: dict[str, Any], allow_mapping: bool) -> Any:
        return models.check_manifest(
            manifest,
            streams=streams,
            stream_identity=models.source_identity(origin),
            stream_session=session_of(origin or ""),
            modality=str(device.modality) if device and device.modality else None,
            preset=pre,
            preset_params=params,
            allow_channel_mapping=allow_mapping,
        )

    return run, label, mapping


@router.get("/models")
async def list_models(
    svc: Svc,
    preset: Annotated[str | None, Query(max_length=32)] = None,
    bin_ms: Annotated[float | None, Query(gt=0, le=1000)] = None,
    allow_channel_mapping: bool = False,
) -> list[ModelInfo]:
    """Every decoder, with compatibility against the running pipeline's output or, with
    ``preset``, against what that preset would produce on the connected source."""
    try:
        from brainos.decoding.registry import ModelRecord  # noqa: F401
    except ImportError:
        return []
    reg = svc.runtime.pipeline.registry
    records = await asyncio.to_thread(reg.records)
    ctx = _check(svc, preset, bin_ms, allow_channel_mapping)
    out = []
    for r in records:
        summary = r.summary(reg.trust_of(r))
        if ctx is None or r.status != "ok":
            out.append(
                ModelInfo(
                    summary=summary,
                    compatible=None if r.status == "ok" else False,
                    errors=[] if r.status == "ok" else [r.reason or r.status],
                    warnings=[],
                )
            )
            continue
        run, label, mapping = ctx
        c = run(r.manifest, mapping)
        errors = list(c.errors)
        if r.unsafe_format and reg.trust_of(r) is None:
            errors.append(
                "this file format can run code when loaded; it stays refused until you mark "
                "this exact file trusted"
            )
        out.append(
            ModelInfo(
                summary=summary,
                compatible=not errors,
                errors=errors,
                warnings=c.warnings + c.mapping_notes,
                mapping_available=c.mapping_available,
                checked_against=label,
            )
        )
    return out


@router.get("/models/discovery")
async def models_discovery(svc: Svc) -> DiscoveryStatus:
    reg = svc.runtime.pipeline.registry
    return DiscoveryStatus(
        discovering=reg.discovering,
        discovered_at_ns=reg.last_discovery_ns,
        error=reg.discovery_error,
        plugins=len(reg._plugins),
    )


@router.post("/models/discover")
async def models_discover(svc: Svc) -> DiscoveryStatus:
    """Probe installed decoder plugins again (each in its own process)."""
    reg = svc.runtime.pipeline.registry
    try:
        await reg.discover_plugins()
    except Exception as exc:
        raise RuntimeCommandError(
            ErrorCode.UNSUPPORTED_OPERATION, f"decoder discovery failed: {exc}"
        ) from None
    return await models_discovery(svc)


class TrustRequest(_Body):
    trusted: bool


@router.post("/models/{model_id}/trust")
async def models_trust(model_id: str, body: TrustRequest, svc: Svc) -> dict[str, Any]:
    """Record (or withdraw) the operator's decision to trust one exact model file."""
    reg = svc.runtime.pipeline.registry
    try:
        trust = reg.set_trust(model_id, body.trusted)
    except KeyError as exc:
        raise RuntimeCommandError(ErrorCode.DEVICE_NOT_FOUND, str(exc).strip("'\"")) from None
    return {"model_id": model_id, "trust": trust}


# ------------------------------------------------------------------ calibration

Capability = Literal["continuous", "classes", "click"]


@router.get("/calibration/options")
async def calibration_options() -> dict[str, Any]:
    try:
        from brainos.decoding.calibrate import CAPABILITIES, DEFAULT_FAMILY
        from brainos.decoding.families import calibration_families
    except ImportError:
        return {"capabilities": []}
    caps = []
    for name, info in CAPABILITIES.items():
        fams = calibration_families(name)  # type: ignore[arg-type]
        caps.append(
            {
                "name": name,
                **info,
                "default_family": DEFAULT_FAMILY[name],
                "families": [{"name": f.name, "description": f.description} for f in fams],
            }
        )
    return {"capabilities": caps}


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
    # Milestone 5: the output to calibrate (overrides kind), the family, joined features
    capability: Capability | None = None
    family: str | None = Field(default=None, max_length=48)
    join_features: bool = False
    event_tolerance_ms: float = Field(default=300.0, gt=0, le=5000)

    @property
    def effective_capability(self) -> str:
        if self.capability is not None:
            return self.capability
        return "classes" if self.kind == "classifier" else "continuous"


class CalibrationResult(BaseModel):
    model: dict[str, Any]
    report: dict[str, Any]
    report_markdown: str


def _paths(svc: AppServices, names: list[str]) -> list[Path]:
    from brainos.adapters.replay.format import RecordingFormatError, recording_path

    rt = svc.runtime
    paths = []
    for name in names:
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
    return paths


@router.post("/calibration/check")
async def calibration_check(body: CalibrationRequest, svc: Svc) -> dict[str, Any]:
    """Whether the chosen recordings provide the labels the chosen output needs."""
    try:
        from brainos.decoding.calibrate import check_recordings
    except ImportError as exc:
        raise RuntimeCommandError(
            ErrorCode.UNSUPPORTED_OPERATION, f"calibration unavailable: {exc}"
        ) from None
    paths = _paths(svc, body.recordings)
    res = await asyncio.to_thread(
        check_recordings,
        paths,
        body.effective_capability,
        label_dim=body.label_dim,
        class_names=body.class_names,
        feature_source=body.feature_source,
        join_features=body.join_features,
    )
    return res.to_dict()


@router.post("/calibration/train")
async def calibration_train(body: CalibrationRequest, svc: Svc) -> CalibrationResult:
    """Fit a decoder for the chosen output on recordings (chronological train / held-out
    split), save it with its manifest, and write the report."""
    try:
        from brainos.decoding import model as models
        from brainos.decoding.calibrate import (
            CalibrationError,
            calibrate_capability,
            capability_report_markdown,
        )
    except ImportError as exc:
        raise RuntimeCommandError(
            ErrorCode.UNSUPPORTED_OPERATION, f"calibration unavailable: {exc}"
        ) from None
    paths = _paths(svc, body.recordings)
    models_dir = svc.runtime.pipeline.models_dir
    try:
        model, report = await asyncio.to_thread(
            calibrate_capability,
            paths,
            body.effective_capability,
            family=body.family,
            label_dim=body.label_dim,
            class_names=body.class_names,
            train_fraction=body.train_fraction,
            gap_bins=body.gap_bins,
            tau_ms=body.tau_ms,
            models_dir=models_dir,
            feature_source=body.feature_source,
            join_features=body.join_features,
            event_tolerance_ms=body.event_tolerance_ms,
        )
    except (CalibrationError, ValueError) as exc:
        raise RuntimeCommandError(ErrorCode.PROTOCOL_ERROR, f"calibration failed: {exc}") from None
    md = capability_report_markdown(report)
    out = svc.settings.reports_dir / "calibration" / f"{model.model_id}.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(md)
    return CalibrationResult(model=models.summary(model), report=report, report_markdown=md)
