"""Real-time processing pipeline: acquisition -> features -> decoder(s) -> (router) -> app events.

Runs as its own asyncio task, fed by a bus tap through a bounded queue (overflow drops the
oldest input and is counted). Derived events re-enter the runtime through the same ingest
path as device events, so they get sequence numbers, validation and provenance like
everything else.

Decoders (Milestone 5) are invoked through ONE interface (``decoding/engine.py``):
built-in JSON families in-process, model files and decoder plugins in an isolated decoder
host. Several decoders may run together (e.g. a velocity decoder and a click decoder), each
publishing its own ``intent.kinematics`` with ``model_origin = "brainos"``. A model with
several inputs (e.g. threshold crossings + spike-band power) receives the streams joined by
bin end time. Every decoder is checked against the source and the pipeline output before it
runs (``decoding/model.py``); the only transformation offered is an explicit,
operator-enabled channel mapping by label.

``decoded_passthrough`` (Milestone 5): no model; the source's own decoder outputs
(``intent.kinematics`` with ``model_origin`` ``historical`` — recorded outputs of a research
system's original decoder, replayed — or ``external`` — e.g. BCI2000's live control signal)
are handed to the command router unchanged (model id and origin preserved). It is an explicit
operator choice; ``brainos``-origin or unlabelled source outputs are refused.

Separation rules enforced here:
  * features are ``processed_feature`` (never intents);
  * decoder output is ``intent.kinematics`` with ``decoded_intent`` + ``model_id`` — not
    actionable by applications that ask for pointer/selection;
  * only the explicitly enabled **command router** (runtime/router.py) turns decoder output
    into ``intent.pointer`` / ``intent.selection`` / ``intent.text`` (still
    ``decoded_intent`` + ``model_id``), and it accepts nothing but decoder output;
  * behavioral labels feed only the drift monitor's metrics, never a decoder or the router.

Stale-command prevention: the router is off after every (re)start unless the start request
itself enables it, is switched off by ``stop`` (source change, error, end), by
``stop_router`` (operator stop, pause, link loss) and when a decoder it uses fails, and
switches itself off when the decoder receives no input for longer than
``max(stall_ms, 3 x bin)`` once it has received any.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import math
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from brainos.adapters.base import EventDraft
from brainos.contracts.capabilities import Capability, CapabilityDescriptor, EventType
from brainos.contracts.events import (
    EventEnvelope,
    Provenance,
    ProvenanceKind,
    Quality,
    QualityFlag,
)
from brainos.contracts.protocol import DeviceDescriptor, ErrorCode
from brainos.runtime.control import COMMAND_CAPABILITIES
from brainos.runtime.router import (
    ClickRule,
    CommandRouter,
    DiscreteRule,
    RouterConfigError,
    RouterSpec,
    pointer_velocity,
    router_capabilities,
    validate_router,
)

if TYPE_CHECKING:
    from brainos.decoding.engine import PipelineDecoder
    from brainos.decoding.model import Compatibility
    from brainos.decoding.monitor import DriftMonitor
    from brainos.decoding.registry import ModelRegistry
    from brainos.processing import SignalChain

log = logging.getLogger(__name__)

__all__ = [
    "DECODED_PASSTHROUGH",
    "ClickRule",
    "DiscreteRule",
    "PipelineError",
    "PipelineManager",
    "PipelineStartRequest",
    "PipelineStatus",
    "RouterSpec",
]

PIPELINE_ADAPTER = "brainos.pipeline@0.5.0"
QUEUE_MAX = 4096
# M5-E: the input queue is also bounded in queued sample values (memory): 16 M values is
# ~0.5 s of 1024 ch at 30 kHz (128 MB as float64), many seconds at common sizes.
QUEUE_MAX_VALUES = 16_000_000
LATENCY_WINDOW = 2048
STALL_BINS = 3  # the stall limit is never shorter than this many feature bins
STALL_CHECK_S = 0.05
ROUTER_LOG = 50
JOIN_PENDING = 8  # incomplete multi-stream bins kept before the oldest is dropped
MAX_DECODERS = 4
DECODED_PASSTHROUGH = "decoded_passthrough"
SOURCE_ORIGINS = frozenset({"historical", "external"})
START_WAIT_S = 120.0


class PipelineStartRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    processing: dict[str, Any]
    model_id: str | None = None
    allow_cross_source: bool = False
    router: RouterSpec | None = None
    # Milestone 5 (additive)
    model_ids: list[str] = Field(default_factory=list, max_length=MAX_DECODERS - 1)
    allow_channel_mapping: bool = False
    calibration_profile: str | None = Field(default=None, max_length=128)


class LatencyStats(BaseModel):
    count: int
    p50: float | None
    p95: float | None
    p99: float | None
    max: float | None


class RouterEvent(BaseModel):
    at_ns: int
    on: bool
    reason: str


class PipelineStatus(BaseModel):
    available: bool
    unavailable_reason: str | None
    running: bool
    device_id: str | None
    session_id: str | None
    preset: str | None
    stages: list[str]
    input_event_type: str | None
    output: dict[str, Any] | None
    warmup_remaining_s: float
    decoder: dict[str, Any] | None
    compatibility_warnings: list[str]
    cross_source_override: bool
    router: RouterSpec | None
    counters: dict[str, int]
    processing_us: LatencyStats
    pipeline_latency_ms: LatencyStats
    last_error: str | None
    started_at_ns: int | None
    # Milestone 4 (additive)
    router_capabilities: list[Capability] = []
    stall_limit_ms: float | None = None
    last_router_stop: RouterEvent | None = None
    router_log: list[RouterEvent] = []
    # Milestone 5 (additive)
    outputs: list[dict[str, Any]] = []
    decoders: list[dict[str, Any]] = []
    source_decoders: list[dict[str, Any]] = []
    channel_mapping: bool = False
    recalibration_recommended: bool = False


def _stats(values: deque[float]) -> LatencyStats:
    if not values:
        return LatencyStats(count=0, p50=None, p95=None, p99=None, max=None)
    s = sorted(values)
    n = len(s)

    def p(q: float) -> float:
        return round(s[min(n - 1, int(q * (n - 1) + 0.5))], 3)

    return LatencyStats(count=n, p50=p(0.5), p95=p(0.95), p99=p(0.99), max=round(s[-1], 3))


class PipelineError(Exception):
    def __init__(self, code: ErrorCode, message: str) -> None:
        self.code, self.message = code, message
        super().__init__(message)


@dataclass
class _Dec:
    """One BrainOS-run decoder in the pipeline."""

    dec: PipelineDecoder
    streams: list[int]  # per input: index into the pipeline's output streams
    mapping: list[list[int] | None]  # per input: source channel per model channel
    compat: Compatibility
    summary: dict[str, Any]
    monitor: DriftMonitor | None = None


@dataclass
class _SourceDec:
    """A decoder output the source itself provides (decoded passthrough)."""

    model_id: str
    dims: list[str]
    quantity: str
    unit: str
    space: str
    model_origin: str
    scale: list[float] | None
    y_axis: str | None = None
    received: int = 0


@dataclass
class _Target:
    """Something the router can take decoder output from."""

    model_id: str
    dims: list[str]
    classes: list[str] | None
    std: list[float] | None
    origin: str  # brainos | historical | external
    y_axis: str | None = None  # direction of +y in the decoder's space, if declared


@dataclass
class _Running:
    device: DeviceDescriptor
    session_id: str
    preset: str
    input_types: frozenset[str]
    chain: SignalChain | None
    fs: float | None
    outputs: list[dict[str, Any]]
    decoders: list[_Dec]
    source_decoders: list[_SourceDec]
    router: RouterSpec | None
    cross_source: bool
    warnings: list[str]
    capabilities: list[CapabilityDescriptor]
    started_at_ns: int = field(default_factory=time.time_ns)
    routers: dict[int, CommandRouter] = field(default_factory=dict)  # target index -> router
    # monotonic time of the last decoder input since the router was enabled (stall watchdog)
    last_decoder_input: float | None = None
    join: dict[int, dict[int, Any]] = field(default_factory=dict)  # bin end ns -> stream -> values
    ready: asyncio.Event = field(default_factory=asyncio.Event)
    start_error: str | None = None

    @property
    def output(self) -> dict[str, Any] | None:
        return self.outputs[0] if self.outputs else None

    @property
    def passthrough(self) -> bool:
        return self.preset == DECODED_PASSTHROUGH

    def targets(self) -> list[_Target]:
        if self.passthrough:
            return [
                _Target(
                    s.model_id,
                    s.dims,
                    s.dims if _is_probability(s.quantity, s.unit) else None,
                    s.scale or [1.0] * len(s.dims),
                    s.model_origin,
                    s.y_axis,
                )
                for s in self.source_decoders
            ]
        return [
            _Target(
                d.dec.model_id,
                d.dec.dims,
                d.dec.classes,
                d.dec.behavior_std,
                "brainos",
                d.dec.y_axis,
            )
            for d in self.decoders
        ]


def _is_probability(quantity: str, unit: str) -> bool:
    return unit == "probability" or quantity in (
        "class_posterior",
        "click_probability",
        "click_decision",
    )


def _router_on(run: _Running | None) -> bool:
    return run is not None and run.router is not None and run.router.enabled


class PipelineManager:
    def __init__(
        self,
        models_dir: Path,
        ingest: Callable[[list[EventDraft]], None],
        on_capabilities_changed: Callable[[], None],
        on_commands_stopped: Callable[[str], None] | None = None,
    ) -> None:
        self.models_dir = models_dir
        self._ingest = ingest
        self._caps_changed = on_capabilities_changed
        self._commands_stopped = on_commands_stopped or (lambda _reason: None)
        self.available, self.unavailable_reason = _probe()
        self._registry: ModelRegistry | None = None
        self._run: _Running | None = None
        self._queue: deque[EventEnvelope] = deque()
        self._queued_values = 0  # sample values held by _queue (memory bound, M5-E)
        self._wake = asyncio.Event()
        self._task: asyncio.Task[None] | None = None
        self._closing: set[asyncio.Task[None]] = set()
        self.last_error: str | None = None
        self._proc_us: deque[float] = deque(maxlen=LATENCY_WINDOW)
        self._lat_ms: deque[float] = deque(maxlen=LATENCY_WINDOW)
        self.router_log: deque[RouterEvent] = deque(maxlen=ROUTER_LOG)
        self.counters: dict[str, int] = {}
        self._reset_counters()

    @property
    def registry(self) -> ModelRegistry:
        if self._registry is None:
            from brainos.decoding.registry import ModelRegistry

            self._registry = ModelRegistry(self.models_dir)
        return self._registry

    def _reset_counters(self) -> None:
        self.counters = {
            "inputs": 0,
            "input_samples": 0,
            "dropped_inputs": 0,
            "features_out": 0,
            "decoded_out": 0,
            "commands_out": 0,
            "selections_out": 0,
            "texts_out": 0,
            "navigations_out": 0,
            "clicks_gated": 0,
            "router_stalls": 0,
            "errors": 0,
            # Milestone 5
            "decoded_in": 0,
            "rejected_inputs": 0,
            "join_dropped": 0,
            "labels_in": 0,
            "decoder_failures": 0,
        }

    # ------------------------------------------------------------------ capabilities
    @property
    def running(self) -> bool:
        return self._run is not None

    @property
    def router_on(self) -> bool:
        return _router_on(self._run)

    def capability_descriptors(self) -> list[CapabilityDescriptor]:
        return list(self._run.capabilities) if self._run else []

    @property
    def capabilities(self) -> frozenset[Capability]:
        return frozenset(c.capability for c in self.capability_descriptors())

    @property
    def command_capabilities(self) -> frozenset[Capability]:
        """Command capabilities the running router currently provides (decoded commands)."""
        return self.capabilities & COMMAND_CAPABILITIES

    @property
    def last_router_stop(self) -> RouterEvent | None:
        return next((e for e in reversed(self.router_log) if not e.on), None)

    def _log_router(self, on: bool, reason: str) -> None:
        self.router_log.append(RouterEvent(at_ns=time.time_ns(), on=on, reason=reason[:256]))
        log.info("command router %s (%s)", "on" if on else "off", reason)

    def _router_stopped(self, reason: str) -> None:
        self._log_router(False, reason)
        self._commands_stopped(reason)

    # ------------------------------------------------------------------ planning
    @staticmethod
    def _plan(
        spec: Any, device: DeviceDescriptor
    ) -> tuple[
        list[dict[str, Any]], SignalChain | None, float | None, frozenset[str], dict[str, Any]
    ]:
        """Feature streams the pipeline will output for ``spec`` on ``device``."""
        from brainos.processing import SignalChain, StageConfigError

        caps = {c.capability: c for c in device.capabilities}
        if spec.preset == "features_passthrough":
            feat = caps.get(Capability.NEURAL_FEATURES)
            if feat is None:
                raise PipelineError(
                    ErrorCode.CAPABILITY_UNSUPPORTED,
                    f"{device.display_name} provides no neural_features to pass through",
                )
            outputs = _feature_streams(dict(feat.params))
            return outputs, None, None, frozenset(o["event_type"] for o in outputs), {}
        rec = caps.get(Capability.RECORDING)
        if rec is None or "sample_rate_hz" not in rec.params:
            raise PipelineError(
                ErrorCode.CAPABILITY_UNSUPPORTED,
                f"{device.display_name} provides no continuous raw signal (recording frames)",
            )
        fs = float(rec.params["sample_rate_hz"])  # type: ignore[arg-type]
        n = int(rec.params["channel_count"])  # type: ignore[arg-type]
        unit = str(rec.params.get("unit", "uV"))
        labels = rec.params.get("channel_labels")
        # workstream B: the source's mains frequency and bad channels (left out of the CAR)
        spec, car_exclude = _source_specific(spec, dict(rec.params), n)
        try:
            chain = SignalChain(
                spec,
                fs,
                n,
                unit,
                car_exclude=car_exclude,
                channel_labels=[str(x) for x in labels] if isinstance(labels, list) else None,
            )
        except StageConfigError as exc:
            raise PipelineError(ErrorCode.CAPABILITY_UNSUPPORTED, str(exc)) from None
        band = getattr(chain, "band", None) if chain.out.event_type == "features.vector" else None
        output = {
            "event_type": chain.out.event_type,
            "feature": chain.out.feature,
            "bin_ms": chain.out.bin_ms,
            "channel_count": n,
            "channel_labels": list(labels) if isinstance(labels, list) and labels else None,
            "unit": chain.out.unit,
            "band_hz": list(band) if band else None,
        }
        params: dict[str, Any] = {}
        if spec.preset == "spikeband_threshold":
            params = {"threshold_k": spec.threshold_k, "rms_window_s": spec.rms_window_s}
            params["car"] = chain.car
        elif spec.preset == "band_power":
            params = {"band_low_hz": spec.band_low_hz, "band_high_hz": spec.band_high_hz}
        elif spec.preset == "ecog_high_gamma":
            params = {"line_hz": spec.line_hz}
        return [output], chain, fs, frozenset({"recording.frame"}), params

    def plan_outputs(self, processing: dict[str, Any], device: DeviceDescriptor) -> dict[str, Any]:
        """What a start request would produce (for compatibility previews)."""
        if processing.get("preset") == DECODED_PASSTHROUGH:
            return {"preset": DECODED_PASSTHROUGH, "outputs": [], "params": {}}
        from brainos.processing import ProcessingSpec

        try:
            spec = ProcessingSpec.model_validate(processing)
        except ValueError as exc:
            raise PipelineError(
                ErrorCode.PROTOCOL_ERROR, f"invalid processing spec: {exc}"
            ) from None
        outputs, _chain, _fs, _types, params = self._plan(spec, device)
        return {"preset": spec.preset, "outputs": outputs, "params": params}

    # ------------------------------------------------------------------ control
    def start(
        self,
        req: PipelineStartRequest,
        device: DeviceDescriptor | None,
        session_id: str | None,
        origin: str | None,
    ) -> PipelineStatus:
        if not self.available:
            raise PipelineError(
                ErrorCode.UNSUPPORTED_OPERATION, self.unavailable_reason or "unavailable"
            )
        if device is None or session_id is None:
            raise PipelineError(
                ErrorCode.INVALID_STATE, "connect a device before starting a pipeline"
            )
        if req.processing.get("preset") == DECODED_PASSTHROUGH:
            run = self._start_passthrough(req, device, session_id)
        else:
            run = self._start_features(req, device, session_id, origin)
        router = req.router
        if router is not None and router.enabled:
            subs = self._validate_router(router, run)
            run.capabilities.extend(_router_caps(subs, run.targets()))
        self.stop("pipeline restarted")
        self._reset_counters()
        self._proc_us.clear()
        self._lat_ms.clear()
        self.last_error = None
        self._run = run
        if router is not None and router.enabled:
            run.router = router
            run.routers = self._make_routers(run, router)
            self._log_router(True, "enabled with the pipeline start")
        self._queue.clear()
        self._queued_values = 0
        self._task = asyncio.get_running_loop().create_task(self._loop(), name="brainos-pipeline")
        log.info(
            "pipeline started: %s on %s (decoders %s)",
            run.preset,
            device.device_id,
            [d.dec.model_id for d in run.decoders] or [s.model_id for s in run.source_decoders],
        )
        self._caps_changed()
        return self.status()

    async def start_async(
        self,
        req: PipelineStartRequest,
        device: DeviceDescriptor | None,
        session_id: str | None,
        origin: str | None,
    ) -> PipelineStatus:
        """Start, then wait until isolated decoders are loaded; a decoder that fails to load
        stops the pipeline and is reported as the error."""
        self.start(req, device, session_id, origin)
        run = self._run
        assert run is not None
        try:
            await asyncio.wait_for(run.ready.wait(), START_WAIT_S)
        except TimeoutError:
            self.stop("decoder start timed out")
            raise PipelineError(ErrorCode.INCOMPATIBLE_DECODER, "decoder did not start") from None
        if run.start_error is not None:
            if self._run is run:
                self.stop("decoder failed to start")
            raise PipelineError(ErrorCode.INCOMPATIBLE_DECODER, run.start_error)
        return self.status()

    def _start_passthrough(
        self, req: PipelineStartRequest, device: DeviceDescriptor, session_id: str
    ) -> _Running:
        if req.model_id or req.model_ids:
            raise PipelineError(
                ErrorCode.PROTOCOL_ERROR,
                "decoded passthrough uses the source's own decoder outputs; it loads no model",
            )
        if set(req.processing) - {"preset"}:
            raise PipelineError(ErrorCode.PROTOCOL_ERROR, "decoded_passthrough takes no parameters")
        streams = _source_decoders(device)
        if not streams:
            raise PipelineError(
                ErrorCode.CAPABILITY_UNSUPPORTED,
                f"{device.display_name} provides no decoder output (kinematic_intent) to pass "
                "through",
            )
        bad = [s for s in streams if s.model_origin not in SOURCE_ORIGINS]
        if bad:
            raise PipelineError(
                ErrorCode.INCOMPATIBLE_DECODER,
                f"the source's decoder output {bad[0].model_id} does not declare model_origin "
                "'historical' or 'external'; only an external system's or a replayed research "
                "decoder's outputs can be passed through",
            )
        dims = [d for s in streams for d in s.dims]
        if len(set(dims)) != len(dims):
            raise PipelineError(
                ErrorCode.INCOMPATIBLE_DECODER,
                f"the source's decoder outputs share dimension names {dims}; they cannot be routed",
            )
        warnings = [
            f"{s.model_id}: no declared output scale; the router uses its values as they are"
            for s in streams
            if s.scale is None and not _is_probability(s.quantity, s.unit)
        ]
        return _Running(
            device=device,
            session_id=session_id,
            preset=DECODED_PASSTHROUGH,
            input_types=frozenset({"intent.kinematics"}),
            chain=None,
            fs=None,
            outputs=[],
            decoders=[],
            source_decoders=streams,
            router=None,
            cross_source=False,
            warnings=warnings,
            capabilities=[],
        )

    def _start_features(
        self,
        req: PipelineStartRequest,
        device: DeviceDescriptor,
        session_id: str,
        origin: str | None,
    ) -> _Running:
        from brainos.processing import ProcessingSpec

        try:
            spec = ProcessingSpec.model_validate(req.processing)
        except ValueError as exc:
            raise PipelineError(
                ErrorCode.PROTOCOL_ERROR, f"invalid processing spec: {exc}"
            ) from None
        outputs, chain, fs, input_types, params = self._plan(spec, device)
        out_caps: list[CapabilityDescriptor] = []
        if chain is not None:
            o = outputs[0]
            out_caps.append(
                CapabilityDescriptor(
                    capability=Capability.NEURAL_FEATURES,
                    params={
                        "feature": o["feature"],
                        "bin_ms": o["bin_ms"],
                        "channel_count": o["channel_count"],
                        "unit": o["unit"],
                        "source": "pipeline",
                    },
                    description=f"BrainOS pipeline ({spec.preset})",
                )
            )
        ids = [m for m in [req.model_id, *req.model_ids] if m]
        if len(set(ids)) != len(ids):
            raise PipelineError(ErrorCode.PROTOCOL_ERROR, f"a model is listed twice: {ids}")
        decs = [
            self._prepare_decoder(mid, req, device, origin, outputs, spec.preset, params)
            for mid in ids
        ]
        all_dims = [d for x in decs for d in x.dec.dims]
        if len(set(all_dims)) != len(all_dims):
            raise PipelineError(
                ErrorCode.INCOMPATIBLE_DECODER,
                f"decoders run together must have distinct output names; got {all_dims}",
            )
        warnings = [w for x in decs for w in x.compat.warnings]
        warnings += [n for x in decs for n in x.compat.mapping_notes]
        for x in decs:
            for note in x.compat.mapping_notes:
                log.warning("pipeline on %s: %s", device.device_id, note)
        if decs:
            first = decs[0].dec
            params_k: dict[str, Any] = {
                "model_id": first.model_id,
                "dims": first.dims,
                "space": first.space,
                "quantity": first.quantity,
            }
            if first.classes is not None:
                params_k["outputs"] = "classes" if first.output_kind == "classes" else "events"
            if len(decs) > 1:
                params_k["decoders"] = [
                    {
                        "model_id": x.dec.model_id,
                        "dims": x.dec.dims,
                        "quantity": x.dec.quantity,
                        "unit": x.dec.unit,
                        "space": x.dec.space,
                        "model_origin": "brainos",
                    }
                    for x in decs
                ]
            out_caps.append(
                CapabilityDescriptor(
                    capability=Capability.KINEMATIC_INTENT,
                    params=params_k,
                    description="decoded_intent from a calibrated model (not an app command)",
                )
            )
        if any(len(x.dec.inputs) > 1 for x in decs) or len(outputs) > 1:
            input_types = frozenset(
                {*input_types, *(outputs[i]["event_type"] for x in decs for i in x.streams)}
            )
        if decs:
            input_types = frozenset({*input_types, "behavior.sample"})  # drift metrics only
        return _Running(
            device=device,
            session_id=session_id,
            preset=spec.preset,
            input_types=input_types,
            chain=chain,
            fs=fs,
            outputs=outputs,
            decoders=decs,
            source_decoders=[],
            router=None,
            cross_source=any(x.compat.cross_source for x in decs),
            warnings=warnings,
            capabilities=out_caps,
        )

    def _prepare_decoder(
        self,
        model_id: str,
        req: PipelineStartRequest,
        device: DeviceDescriptor,
        origin: str | None,
        outputs: list[dict[str, Any]],
        preset: str,
        params: dict[str, Any],
    ) -> _Dec:
        from brainos.datasets import session_of
        from brainos.decoding import model as models
        from brainos.decoding.engine import make_decoder
        from brainos.decoding.monitor import DriftMonitor

        reg = self.registry
        try:
            record = reg.get(model_id)
        except (ValueError, TypeError, KeyError, OSError) as exc:
            raise PipelineError(
                ErrorCode.INCOMPATIBLE_DECODER, f"cannot load model {model_id}: {exc}"
            ) from None
        if record is None:
            raise PipelineError(ErrorCode.DEVICE_NOT_FOUND, f"no model {model_id}")
        if record.status != "ok":
            raise PipelineError(
                ErrorCode.INCOMPATIBLE_DECODER, f"model {model_id} is unusable: {record.reason}"
            )
        manifest = record.manifest
        if record.model is not None and models.model_input(record.model).get("inferred"):
            manifest = {**manifest, "inputs": [{**manifest["inputs"][0], "inferred": True}]}
        compat = models.check_manifest(
            manifest,
            streams=outputs,
            stream_identity=models.source_identity(origin),
            stream_session=session_of(origin or ""),
            modality=str(device.modality) if device.modality else None,
            preset=preset,
            preset_params=params,
            calibration_profile=req.calibration_profile,
            allow_cross_source=req.allow_cross_source,
            allow_channel_mapping=req.allow_channel_mapping,
            bad_channels=_bad_channels(device),
        )
        if not compat.ok:
            raise PipelineError(ErrorCode.INCOMPATIBLE_DECODER, "; ".join(compat.errors))
        if record.unsafe_format and reg.trust_of(record) is None:
            raise PipelineError(
                ErrorCode.INCOMPATIBLE_DECODER,
                f"model {model_id} is a {(manifest.get('artifact') or {}).get('format')} file, "
                "which can run arbitrary code when loaded; mark this exact file trusted first",
            )
        dec = make_decoder(
            record,
            trusted_sha256=reg.trusted_sha256(record),
            python=reg.python,
            extra_path=reg.extra_path,
        )
        summary = record.summary(reg.trust_of(record))
        monitor = None
        training = record.model.training if record.model is not None else {}
        ev = (
            record.model.evaluations[-1]
            if record.model is not None and record.model.evaluations
            else {}
        )
        bin_ms = float(outputs[compat.streams[0]]["bin_ms"]) if compat.streams else 0.0
        monitor = DriftMonitor(
            model_id=dec.model_id,
            dims=dec.dims,
            output_kind=dec.output_kind,
            bin_ms=bin_ms,
            feature_stats=training.get("feature_stats"),
            output_stats=training.get("output_stats"),
            reference={
                "r2": ev.get("r2"),
                "balanced_accuracy": ev.get("balanced_accuracy"),
                "chance_balanced_accuracy": ev.get("chance_balanced_accuracy"),
            },
            class_values=list(getattr(record.model, "class_values", []) or []) or None,
        )
        return _Dec(dec, compat.streams, compat.mapping, compat, summary, monitor)

    def _validate_router(self, router: RouterSpec, run: _Running) -> dict[int, RouterSpec]:
        """Check the mapping against the running decoders; per target, the part it serves."""
        targets = run.targets()
        if not targets:
            raise PipelineError(
                ErrorCode.PROTOCOL_ERROR, "the command router needs a loaded decoder"
            )
        if not router.pointer and not router.discrete and router.click is None:
            raise PipelineError(
                ErrorCode.CAPABILITY_UNSUPPORTED,
                "the command router has nothing to emit: map two decoder dimensions to the "
                "pointer (x_dim, y_dim), add discrete rules, or a click output",
            )
        for d in run.decoders:
            if d.dec.state == "failed":
                raise PipelineError(
                    ErrorCode.INCOMPATIBLE_DECODER,
                    f"decoder {d.dec.model_id} failed: {d.dec.error}",
                )
        subs: dict[int, RouterSpec] = {}
        if router.pointer:
            if len(targets) == 1 and targets[0].classes is not None:
                t = targets[0]
                raise PipelineError(
                    ErrorCode.INCOMPATIBLE_DECODER,
                    f"pointer movement needs a continuous decoder; {t.model_id} is a "
                    f"classifier (classes {t.classes}). Use discrete rules instead.",
                )
            dims = [d for t in targets for d in t.dims]
            for dim in (router.x_dim, router.y_dim):
                if dim not in dims:
                    raise PipelineError(
                        ErrorCode.PROTOCOL_ERROR, f"decoder has no dimension {dim!r} ({dims})"
                    )
            owner = next(
                (
                    i
                    for i, t in enumerate(targets)
                    if router.x_dim in t.dims and router.y_dim in t.dims
                ),
                None,
            )
            if owner is None:
                raise PipelineError(
                    ErrorCode.PROTOCOL_ERROR, "x_dim and y_dim must come from the same decoder"
                )
            t = targets[owner]
            if t.classes is not None:
                raise PipelineError(
                    ErrorCode.INCOMPATIBLE_DECODER,
                    f"pointer movement needs a continuous decoder; {t.model_id} is a "
                    f"classifier (classes {t.classes}). Use discrete rules instead.",
                )
            if t.std is None and router.pointer_scale == "training_std":
                raise PipelineError(
                    ErrorCode.PROTOCOL_ERROR,
                    "model lacks training behavior_std; retrain it, or use pointer_scale "
                    "'native' if its output already is a velocity in workspace units",
                )
            if t.y_axis == "up" and not router.invert_y:
                raise PipelineError(
                    ErrorCode.PROTOCOL_ERROR,
                    f"decoder {t.model_id} declares +y up; the pointer workspace's +y is down: "
                    "enable invert_y",
                )
            subs[owner] = router.model_copy(update={"discrete": [], "click": None})
        if router.discrete:
            if all(t.classes is None for t in targets):
                t0 = targets[0]
                raise PipelineError(
                    ErrorCode.INCOMPATIBLE_DECODER,
                    f"discrete actions need a classifier (outputs: classes); {t0.model_id} "
                    f"outputs continuous {_quantity(run, 0)} {t0.dims}",
                )
            for r in router.discrete:
                owner = next(
                    (i for i, t in enumerate(targets) if t.classes and r.output in t.classes), None
                )
                if owner is None:
                    t0 = next(t for t in targets if t.classes is not None)
                    raise PipelineError(
                        ErrorCode.INCOMPATIBLE_DECODER,
                        f"decoder {t0.model_id} has no class {r.output!r} ({t0.classes})",
                    )
                base = subs.get(owner) or router.model_copy(
                    update={"x_dim": None, "y_dim": None, "discrete": [], "click": None}
                )
                subs[owner] = base.model_copy(update={"discrete": [*base.discrete, r]})
        if router.click is not None:
            # the click goes to the (continuous / event) decoder that outputs it, e.g. a click
            # decoder running next to a Kalman cursor decoder (M5 P0)
            out_name = router.click.output
            owner = next((i for i, t in enumerate(targets) if out_name in t.dims), None)
            if owner is None:
                dims = [d for t in targets for d in t.dims]
                raise PipelineError(
                    ErrorCode.INCOMPATIBLE_DECODER,
                    f"no running decoder outputs {out_name!r} for the click ({dims})",
                )
            base = subs.get(owner) or router.model_copy(
                update={"x_dim": None, "y_dim": None, "discrete": [], "click": None}
            )
            subs[owner] = base.model_copy(update={"click": router.click})
        # every per-decoder router passes the router's own validation (workstream C)
        for i, sub in subs.items():
            t = targets[i]
            try:
                validate_router(
                    sub,
                    model_id=t.model_id,
                    dims=t.dims,
                    classes=t.classes,
                    has_std=t.std is not None,
                    quantity=_quantity(run, i),
                )
            except RouterConfigError as exc:
                raise PipelineError(exc.code, exc.message) from None
        return subs

    def _make_routers(self, run: _Running, router: RouterSpec) -> dict[int, CommandRouter]:
        targets = run.targets()
        out: dict[int, CommandRouter] = {}
        for i, sub in self._validate_router(router, run).items():
            t = targets[i]
            out[i] = CommandRouter(
                sub.model_copy(update={"enabled": router.enabled}),
                model_id=t.model_id,
                dims=t.dims,
                behavior_std=t.std,
            )
        return out

    @staticmethod
    def _route(
        r: RouterSpec, dims: list[str], values: list[float], std: list[float]
    ) -> tuple[float, float]:
        return pointer_velocity(r, dims, values, std)

    def set_router(
        self, router: RouterSpec, reason: str = "disabled by operator"
    ) -> PipelineStatus:
        run = self._run
        if run is None:
            raise PipelineError(ErrorCode.INVALID_STATE, "no pipeline running")
        subs = self._validate_router(router, run) if router.enabled else {}
        was_on = _router_on(run)
        caps = [c for c in run.capabilities if c.capability not in COMMAND_CAPABILITIES]
        if router.enabled:
            caps.extend(_router_caps(subs, run.targets()))
        run.router = router
        run.capabilities = caps
        # fresh rule states and stall watchdog on every change; never carry state over
        run.routers = self._make_routers(run, router) if router.enabled else {}
        run.last_decoder_input = None
        if router.enabled:
            self._log_router(True, "settings changed" if was_on else "enabled by operator")
            if was_on:
                self._commands_stopped("router settings changed")
        elif was_on:
            self._router_stopped(reason)
        self._caps_changed()
        return self.status()

    def stop_router(self, reason: str) -> bool:
        """Turn command output off (keeps the mapping). Returns whether it was on."""
        run = self._run
        if run is None or run.router is None or not run.router.enabled:
            return False
        self.set_router(run.router.model_copy(update={"enabled": False}), reason)
        return True

    def stop(self, reason: str = "stopped") -> None:
        task, self._task = self._task, None
        if task is not None:
            task.cancel()
        run = self._run
        was_on = _router_on(run)
        self._run = None
        self._queue.clear()
        self._queued_values = 0
        if was_on:
            self._router_stopped(reason)
        if run is not None:
            for d in run.decoders:
                self._close_later(d.dec)
            log.info("pipeline stopped (%s)", reason)
            self._caps_changed()

    def _close_later(self, dec: PipelineDecoder) -> None:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:  # pragma: no cover - always called from the event loop
            return
        t = loop.create_task(dec.close(), name=f"close-decoder-{dec.model_id}")
        self._closing.add(t)
        t.add_done_callback(self._closing.discard)

    # ------------------------------------------------------------------ data path
    def tap(self, env: EventEnvelope, _json: str) -> None:
        run = self._run
        if (
            run is None
            or env.session_id != run.session_id
            or env.event_type.value not in run.input_types
        ):
            return
        if env.provenance.adapter == PIPELINE_ADAPTER:
            return
        size = _input_values(env)
        while self._queue and (
            len(self._queue) >= QUEUE_MAX or self._queued_values + size > QUEUE_MAX_VALUES
        ):
            self._queued_values -= _input_values(self._queue.popleft())
            self.counters["dropped_inputs"] += 1
        self._queue.append(env)
        self._queued_values += size
        self._wake.set()

    def stall_limit_ms(self, run: _Running | None = None) -> float | None:
        run = run or self._run
        if run is None or run.router is None or not run.router.enabled:
            return None
        bin_ms = float((run.output or {}).get("bin_ms") or 0.0)
        return max(run.router.stall_ms, STALL_BINS * bin_ms)

    def check_stall(self, now: float | None = None) -> bool:
        """Stop command output if the decoder has had no input for too long. Armed only
        after the first decoder input since the router was enabled (before that, nothing
        has been emitted that could go stale)."""
        run = self._run
        limit = self.stall_limit_ms(run)
        if run is None or limit is None or run.last_decoder_input is None:
            return False
        idle_ms = ((now if now is not None else time.monotonic()) - run.last_decoder_input) * 1e3
        if idle_ms <= limit:
            return False
        self.counters["router_stalls"] += 1
        self.stop_router(f"input stalled: no decoder input for {idle_ms:.0f} ms (limit {limit:g})")
        return True

    async def _start_decoders(self, run: _Running) -> None:
        from brainos.decoding.engine import DecoderFailed

        try:
            for d in run.decoders:
                if d.dec.state == "starting":
                    try:
                        await d.dec.start()
                    except DecoderFailed as exc:
                        run.start_error = f"decoder {d.dec.model_id} failed to start: {exc}"
                        self.counters["decoder_failures"] += 1
                        self.last_error = run.start_error
                        self._decoder_failed(run, d)
        finally:
            run.ready.set()

    def _decoder_failed(self, run: _Running, d: _Dec) -> None:
        if self._run is run and _router_on(run):
            self.stop_router(f"decoder {d.dec.model_id} failed: {d.dec.error}")

    async def _loop(self) -> None:
        run0 = self._run
        if run0 is not None:
            await self._start_decoders(run0)
        while True:
            if not self._queue:
                self._wake.clear()
                timeout = STALL_CHECK_S if self.router_on else None
                with contextlib.suppress(TimeoutError):
                    await asyncio.wait_for(self._wake.wait(), timeout)
                self.check_stall()
                continue
            env = self._queue.popleft()
            self._queued_values -= _input_values(env)
            run = self._run
            if run is None:
                return
            t0 = time.perf_counter()
            try:
                drafts = await self._process(run, env)
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # never let one bad input kill the pipeline
                self.counters["errors"] += 1
                self.last_error = f"{type(exc).__name__}: {exc}"
                log.exception("pipeline error on %s", env.event_type)
                continue
            if self._run is not run:
                return
            self._proc_us.append((time.perf_counter() - t0) * 1e6)
            if drafts:
                self._ingest(drafts)
                self._lat_ms.append((time.time_ns() - env.timestamp_ns) / 1e6)
            self.check_stall()
            await asyncio.sleep(0)  # yield between inputs

    @staticmethod
    def _provenance(
        prov: Provenance,
        kind: ProvenanceKind,
        *,
        model_id: str | None = None,
        model_origin: Literal["brainos", "external", "historical"] | None = None,
    ) -> Provenance:
        return Provenance(
            kind=kind,
            adapter=PIPELINE_ADAPTER,
            synthetic=prov.synthetic,
            model_id=model_id,
            origin=prov.origin,
            replayed=prov.replayed,
            model_origin=model_origin,
        )

    async def _process(self, run: _Running, env: EventEnvelope) -> list[EventDraft]:
        import numpy as np

        if env.event_type is EventType.BEHAVIOR_SAMPLE:
            lab: Any = env.payload
            self.counters["labels_in"] += 1
            for d in run.decoders:
                if d.monitor is not None:
                    d.monitor.add_label(
                        env.device_timestamp_ns or 0,
                        [float(v) for v in lab.values],
                        bool(lab.valid),
                        list(lab.dims),
                    )
            return []
        if run.passthrough:
            return self._passthrough(run, env)
        prov = env.provenance
        flags: list[QualityFlag] = [
            f for f in env.quality.flags if f in (QualityFlag.SYNTHETIC, QualityFlag.REPLAYED)
        ]
        gap = QualityFlag.DROPPED_SAMPLES in env.quality.flags
        out: list[EventDraft] = []
        bins: list[tuple[int, dict[int, Any]]] = []  # (bin end ns, stream -> values)
        self.counters["inputs"] += 1
        if run.chain is not None:
            frame: Any = env.payload
            samples = np.asarray(frame.samples, dtype=np.float64).T
            self.counters["input_samples"] += samples.shape[0]
            p0 = run.chain.processed
            frames = run.chain.push(samples)
            t_first = env.device_timestamp_ns or 0
            assert run.fs is not None
            fq = Quality(
                score=0.5 if gap else 1.0,
                flags=[*flags, *([QualityFlag.DROPPED_SAMPLES] if gap else [])],
            )
            for f in frames:
                ts = t_first + round((f.end_sample - p0) / run.fs * 1e9)
                payload: dict[str, Any]
                if f.event_type == "features.binned":
                    payload = {
                        "feature": f.feature,
                        "unit": "count",
                        "bin_ms": f.bin_ms,
                        "bin_index": f.bin_index,
                        "channel_count": len(f.values),
                        "counts": [int(v) for v in f.values],
                    }
                    et = EventType.FEATURES_BINNED
                else:
                    payload = {
                        "feature": f.feature,
                        "unit": f.unit,
                        "band_hz": list(f.band_hz) if f.band_hz else None,
                        "bin_ms": f.bin_ms,
                        "bin_index": f.bin_index,
                        "channel_count": len(f.values),
                        "values": [float(v) for v in f.values],
                    }
                    et = EventType.FEATURES_VECTOR
                draft = EventDraft(
                    et, payload, fq, self._provenance(prov, ProvenanceKind.PROCESSED_FEATURE), ts
                )
                out.append(draft)
                bins.append((ts, {0: f.values}))
            self.counters["features_out"] += len(frames)
        else:
            fp: Any = env.payload
            feature = getattr(fp, "feature", None)
            idx = next(
                (
                    i
                    for i, o in enumerate(run.outputs)
                    if o["event_type"] == env.event_type.value and o["feature"] == feature
                ),
                None,
            )
            if idx is None:
                return out
            vals = fp.counts if env.event_type == EventType.FEATURES_BINNED else fp.values
            ts = env.device_timestamp_ns or 0
            values = np.asarray(vals, dtype=np.float64)
            if len(run.outputs) == 1:
                bins.append((ts, {idx: values}))
            else:
                bins.extend(self._join(run, ts, idx, values))
        if not run.decoders or not bins:
            return out
        return out + await self._decode(run, bins, prov, flags, gap)

    def _join(
        self, run: _Running, ts: int, idx: int, values: Any
    ) -> list[tuple[int, dict[int, Any]]]:
        """Collect one bin per stream; complete bins (every stream the decoders need) out."""
        need = {i for d in run.decoders for i in d.streams}
        slot = run.join.setdefault(ts, {})
        slot[idx] = values
        # a bin still incomplete once JOIN_PENDING newer bins exist will never complete
        bin_ns = round(float(run.outputs[idx].get("bin_ms") or 0.0) * 1e6)
        horizon = ts - JOIN_PENDING * bin_ns
        for old in [t for t in run.join if t < horizon or (bin_ns == 0 and t < ts)]:
            if bin_ns == 0 and len(run.join) <= JOIN_PENDING:
                break
            del run.join[old]
            self.counters["join_dropped"] += 1
        if need <= set(slot):
            del run.join[ts]
            return [(ts, slot)]
        return []

    async def _decode(
        self,
        run: _Running,
        bins: list[tuple[int, dict[int, Any]]],
        prov: Provenance,
        flags: list[QualityFlag],
        gap: bool,
    ) -> list[EventDraft]:
        import numpy as np

        from brainos.decoding.engine import DecoderFailed

        results: list[tuple[_Dec, Any, Any]] = []  # (decoder, X, values)
        for d in run.decoders:
            if d.dec.state != "ready":
                continue
            rows = []
            for _ts, streams in bins:
                parts = []
                for s, m in zip(d.streams, d.mapping, strict=True):
                    v = streams[s]
                    parts.append(v if m is None else v[m])
                rows.append(parts[0] if len(parts) == 1 else np.concatenate(parts))
            X = np.asarray(rows, dtype=np.float64)
            try:
                values, _conf = await d.dec.step(X, [ts / 1e9 for ts, _ in bins])
            except DecoderFailed as exc:
                self.counters["decoder_failures"] += 1
                self.counters["errors"] += 1
                self.last_error = f"decoder {d.dec.model_id} stopped: {exc}"
                self._decoder_failed(run, d)
                continue
            if self._run is not run:
                return []
            results.append((d, X, values))
        if run.routers:
            run.last_decoder_input = time.monotonic()
        targets_index = {d.dec.model_id: i for i, d in enumerate(run.decoders)}
        out: list[EventDraft] = []
        for k, (ts, _streams) in enumerate(bins):
            for d, X, values in results:
                vals = [float(v) for v in values[k]]
                if not all(math.isfinite(v) for v in vals):
                    self.counters["errors"] += 1
                    continue
                if d.monitor is not None:
                    d.monitor.add(ts, X[k], values[k])
                q = Quality(score=0.5 if (d.compat.cross_source or gap) else 1.0, flags=flags)
                decoded = EventDraft(
                    EventType.INTENT_KINEMATICS,
                    {
                        "quantity": d.dec.quantity,
                        "dims": d.dec.dims,
                        "unit": d.dec.unit,
                        "values": vals,
                        "space": d.dec.space,
                    },
                    q,
                    self._provenance(
                        prov,
                        ProvenanceKind.DECODED_INTENT,
                        model_id=d.dec.model_id,
                        model_origin="brainos",
                    ),
                    ts,
                )
                out.append(decoded)
                self.counters["decoded_out"] += 1
                router = run.routers.get(targets_index[d.dec.model_id])
                if router is not None:
                    out.extend(self._route_counted(router, decoded))
        return out

    def _passthrough(self, run: _Running, env: EventEnvelope) -> list[EventDraft]:
        prov = env.provenance
        p = env.payload
        dims = list(getattr(p, "dims", []))
        idx = next(
            (
                i
                for i, s in enumerate(run.source_decoders)
                if s.model_id == prov.model_id and s.dims == dims
            ),
            None,
        )
        reason = None
        if prov.kind is not ProvenanceKind.DECODED_INTENT:
            reason = f"not decoder output ({prov.kind})"
        elif prov.model_origin not in SOURCE_ORIGINS:
            reason = f"model_origin {prov.model_origin!r} is not historical or external"
        elif idx is None:
            reason = f"undeclared decoder output {prov.model_id} {dims}"
        if reason is not None:
            self.counters["rejected_inputs"] += 1
            self.last_error = f"passthrough input refused: {reason}"
            return []
        assert idx is not None
        src = run.source_decoders[idx]
        src.received += 1
        self.counters["inputs"] += 1
        self.counters["decoded_in"] += 1
        router = run.routers.get(idx)
        if router is None:
            return []
        run.last_decoder_input = time.monotonic()
        values = [float(v) for v in getattr(p, "values", [])]
        draft = EventDraft(
            EventType.INTENT_KINEMATICS,
            {
                "quantity": getattr(p, "quantity", src.quantity),
                "dims": dims,
                "unit": getattr(p, "unit", src.unit),
                "values": values,
                "space": getattr(p, "space", src.space),
            },
            env.quality,
            self._provenance(
                prov,
                ProvenanceKind.DECODED_INTENT,
                model_id=prov.model_id,
                model_origin=prov.model_origin,
            ),
            env.device_timestamp_ns,
        )
        return self._route_counted(router, draft)

    def _route_counted(self, router: CommandRouter, decoded: EventDraft) -> list[EventDraft]:
        gated = router.clicks_gated
        cmds = self._count_commands(router.route(decoded))
        self.counters["clicks_gated"] += router.clicks_gated - gated
        return cmds

    def _count_commands(self, cmds: list[EventDraft]) -> list[EventDraft]:
        for cmd in cmds:
            if cmd.event_type is EventType.INTENT_POINTER:
                self.counters["commands_out"] += 1
            elif cmd.event_type is EventType.INTENT_SELECTION:
                self.counters["selections_out"] += 1
            elif cmd.event_type is EventType.INTENT_NAVIGATE:
                self.counters["navigations_out"] += 1
            else:
                self.counters["texts_out"] += 1
        return cmds

    # ------------------------------------------------------------------ status
    def _decoder_status(self, run: _Running, d: _Dec) -> dict[str, Any]:
        c = d.compat
        return {
            **d.summary,
            **d.dec.info(),
            "compatibility": {
                "ok": c.ok,
                "errors": c.errors,
                "warnings": c.warnings,
                "cross_source": c.cross_source,
                "mapping_applied": c.mapping_applied,
                "mapping_notes": c.mapping_notes,
            },
            "streams": [run.outputs[i]["feature"] for i in d.streams if i >= 0],
            "monitor": d.monitor.status() if d.monitor is not None else None,
        }

    def status(self) -> PipelineStatus:
        run = self._run
        warm = 0.0
        if run is not None and run.chain is not None and run.fs and run.chain.tc is not None:
            remaining = run.chain.warmup_samples - run.chain.processed
            warm = max(0.0, remaining / run.fs)
        decoders = [self._decoder_status(run, d) for d in run.decoders] if run else []
        sources = (
            [
                {
                    "model_id": s.model_id,
                    "dims": s.dims,
                    "quantity": s.quantity,
                    "unit": s.unit,
                    "space": s.space,
                    "model_origin": s.model_origin,
                    "origin": s.model_origin,
                    "family": DECODED_PASSTHROUGH,
                    "scale": s.scale,
                    "y_axis": s.y_axis,
                    "received": s.received,
                    "outputs": {"type": "event", "events": s.dims}
                    if _is_probability(s.quantity, s.unit)
                    else {"type": "continuous"},
                }
                for s in run.source_decoders
            ]
            if run
            else []
        )
        first = decoders[0] if decoders else (sources[0] if sources else None)
        stages: list[str] = []
        if run is not None:
            if run.chain is not None:
                stages = run.chain.stages
            elif run.passthrough:
                stages = ["decoder outputs from the source (decoded passthrough)"]
            else:
                stages = ["features from source (passthrough)"]
        recal = any((d.get("monitor") or {}).get("recalibration_recommended") for d in decoders)
        return PipelineStatus(
            available=self.available,
            unavailable_reason=self.unavailable_reason,
            running=run is not None,
            device_id=run.device.device_id if run else None,
            session_id=run.session_id if run else None,
            preset=run.preset if run else None,
            stages=stages,
            input_event_type=(
                "intent.kinematics"
                if run.passthrough
                else "recording.frame"
                if run.chain is not None
                else (run.output or {}).get("event_type")
            )
            if run
            else None,
            output=run.output if run else None,
            warmup_remaining_s=round(warm, 3),
            decoder=first,
            compatibility_warnings=run.warnings if run else [],
            cross_source_override=run.cross_source if run else False,
            router=run.router if run else None,
            counters={**self.counters, "queue_depth": len(self._queue)},
            processing_us=_stats(self._proc_us),
            pipeline_latency_ms=_stats(self._lat_ms),
            last_error=self.last_error,
            started_at_ns=run.started_at_ns if run else None,
            router_capabilities=sorted(self.command_capabilities),
            stall_limit_ms=self.stall_limit_ms(run),
            last_router_stop=self.last_router_stop,
            router_log=list(self.router_log)[-10:],
            outputs=run.outputs if run else [],
            decoders=decoders,
            source_decoders=sources,
            channel_mapping=bool(run and any(d.compat.mapping_applied for d in run.decoders)),
            recalibration_recommended=bool(recal),
        )

    async def aclose(self) -> None:
        task, self._task = self._task, None
        run = self._run
        if _router_on(run):
            self._router_stopped("runtime shutdown")
        self._run = None
        if task is not None:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task
        if run is not None:
            for d in run.decoders:
                with contextlib.suppress(Exception):
                    await d.dec.close()
        if self._closing:
            await asyncio.gather(*self._closing, return_exceptions=True)


def _quantity(run: _Running, i: int) -> str:
    if run.passthrough:
        return run.source_decoders[i].quantity
    return run.decoders[i].dec.quantity


def _router_caps(subs: dict[int, RouterSpec], targets: list[_Target]) -> list[CapabilityDescriptor]:
    """Router capabilities of every sub-router; one descriptor per capability."""
    merged: dict[Capability, CapabilityDescriptor] = {}
    for i, sub in subs.items():
        for c in router_capabilities(sub.model_copy(update={"enabled": True}), targets[i].model_id):
            have = merged.get(c.capability)
            if have is None:
                merged[c.capability] = c
                continue
            params = dict(have.params)
            for key in ("actions", "text_modes"):
                if key in c.params:
                    old = params.get(key)
                    new = c.params[key]
                    if isinstance(old, list) and isinstance(new, list):
                        params[key] = sorted({*old, *new})
            params["model_id"] = f"{have.params.get('model_id')},{targets[i].model_id}"[:128]
            merged[c.capability] = have.model_copy(update={"params": params})
    return list(merged.values())


def _feature_streams(params: dict[str, Any]) -> list[dict[str, Any]]:
    """Feature streams a source declares in its neural_features capability: the M5
    ``streams`` list, else the single-stream parameters."""
    raw = params.get("streams")
    if isinstance(raw, list) and raw:
        out = []
        for s in raw:
            if not isinstance(s, dict):
                continue
            feature = str(s.get("feature", ""))
            event_type = str(
                s.get("event_type")
                or ("features.binned" if feature in _BINNED else "features.vector")
            )
            labels = s.get("channel_labels")
            band = s.get("band_hz")
            out.append(
                {
                    "event_type": event_type,
                    "feature": feature,
                    "bin_ms": float(str(s.get("bin_ms", 0) or 0)),
                    "channel_count": int(str(s.get("channel_count", 0) or 0)),
                    "channel_labels": list(labels) if isinstance(labels, list) else None,
                    "unit": s.get("unit") or ("count" if event_type == "features.binned" else None),
                    "band_hz": list(band) if isinstance(band, list) else None,
                }
            )
        if out:
            return out
    feature = str(params.get("feature", "spike_count"))
    event_type = "features.binned" if feature in _BINNED else "features.vector"
    labels_param = params.get("channel_labels")
    unit = params.get("unit")
    band = params.get("band_hz")
    return [
        {
            "event_type": event_type,
            "feature": feature,
            "bin_ms": float(str(params.get("bin_ms", 0) or 0)),
            "channel_count": int(str(params.get("channel_count", 0) or 0)),
            "channel_labels": list(labels_param) if isinstance(labels_param, list) else None,
            "unit": str(unit) if unit else ("count" if event_type == "features.binned" else None),
            "band_hz": list(band) if isinstance(band, list) else None,
        }
    ]


_BINNED = frozenset({"spike_count", "threshold_crossing_count"})


def _source_decoders(device: DeviceDescriptor) -> list[_SourceDec]:
    """Decoder outputs a source declares (``kinematic_intent`` params: one decoder, or the
    M5 ``decoders`` list)."""
    out: list[_SourceDec] = []
    for cap in device.capabilities:
        if cap.capability is not Capability.KINEMATIC_INTENT:
            continue
        p: dict[str, Any] = dict(cap.params)
        entries: Any = p.get("decoders") if isinstance(p.get("decoders"), list) else [p]
        for e in entries or []:
            if not isinstance(e, dict) or not e.get("model_id") or not e.get("dims"):
                continue
            scale = e.get("scale")
            out.append(
                _SourceDec(
                    model_id=str(e["model_id"]),
                    dims=[str(d) for d in e["dims"]],
                    quantity=str(e.get("quantity", "decoder_output")),
                    unit=str(e.get("unit", "")),
                    space=str(e.get("space", "")),
                    model_origin=str(e.get("model_origin") or ""),
                    scale=[float(v) for v in scale] if isinstance(scale, list) else None,
                    y_axis=str(e["y_axis"]) if e.get("y_axis") in ("up", "down") else None,
                )
            )
    return out


def _recording_params(device: DeviceDescriptor) -> dict[str, Any] | None:
    rec = next((c for c in device.capabilities if c.capability is Capability.RECORDING), None)
    return dict(rec.params) if rec is not None else None


def _bad_channels(device: DeviceDescriptor) -> list[str] | None:
    params = _recording_params(device)
    bad = params.get("bad_channels") if params else None
    return [str(b) for b in bad] if isinstance(bad, list) else None


def _source_specific(spec: Any, params: dict[str, Any], n: int) -> tuple[Any, list[int]]:
    """Apply what the source declares (M5, workstream B): its mains frequency for the
    line-noise notch and its bad channels, which are left out of the common average reference.

    An explicitly requested notch frequency that contradicts the source's declaration is
    refused (``line_hz: null`` = no notch, e.g. for data notch-filtered upstream, is allowed).
    """
    declared = params.get("line_hz")
    if spec.preset == "ecog_high_gamma" and isinstance(declared, int | float) and declared:
        if "line_hz" not in spec.model_fields_set:
            if declared not in (50, 60):
                raise PipelineError(
                    ErrorCode.CAPABILITY_UNSUPPORTED,
                    f"source declares {declared:g} Hz mains; only 50/60 Hz notches exist",
                )
            spec = spec.model_copy(update={"line_hz": int(declared)})
        elif spec.line_hz is not None and float(spec.line_hz) != float(declared):
            raise PipelineError(
                ErrorCode.CAPABILITY_UNSUPPORTED,
                f"notch at {spec.line_hz} Hz requested, but the source declares "
                f"{declared:g} Hz mains (line_hz: null disables the notch)",
            )
    labels = params.get("channel_labels")
    bad = params.get("bad_channels")
    exclude: list[int] = []
    if isinstance(bad, list) and bad:
        if not isinstance(labels, list) or len(labels) != n:
            raise PipelineError(
                ErrorCode.CAPABILITY_UNSUPPORTED,
                "source declares bad channels without channel labels; cannot exclude them",
            )
        index = {str(lbl): i for i, lbl in enumerate(labels)}
        unknown = [b for b in bad if str(b) not in index]
        if unknown:
            raise PipelineError(
                ErrorCode.CAPABILITY_UNSUPPORTED, f"bad channels {unknown} are not source channels"
            )
        exclude = [index[str(b)] for b in bad]
    return spec, exclude


def _input_values(env: EventEnvelope) -> int:
    """Number of sample values an input carries (the queue's memory bound counts these)."""
    p = env.payload
    if env.event_type is EventType.RECORDING_FRAME:
        samples = p.samples  # type: ignore[union-attr]
        shape = getattr(samples, "shape", None)
        n = int(shape[1]) if shape is not None else (len(samples[0]) if samples else 0)
        return int(p.channel_count) * n  # type: ignore[union-attr]
    return int(getattr(p, "channel_count", 1) or 1)


def _probe() -> tuple[bool, str | None]:
    try:
        import numpy  # noqa: F401
        import scipy  # noqa: F401
    except ImportError as exc:
        return False, f"signal processing not installed ({exc.name}); pip install 'brainos[dsp]'"
    return True, None
