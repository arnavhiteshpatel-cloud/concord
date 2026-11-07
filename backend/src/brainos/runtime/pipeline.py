"""Real-time processing pipeline: acquisition -> features -> decoder -> (router) -> app events.

Runs as its own asyncio task, fed by a bus tap through a bounded queue (overflow drops the
oldest input and is counted). Derived events re-enter the runtime through the same ingest
path as device events, so they get sequence numbers, validation and provenance like
everything else.

Separation rules enforced here:
  * features are ``processed_feature`` (never intents);
  * decoder output is ``intent.kinematics`` with ``decoded_intent`` + ``model_id`` — not
    actionable by applications that ask for pointer/selection;
  * only the explicitly enabled **command router** (runtime/router.py) turns decoder output
    into ``intent.pointer`` / ``intent.selection`` / ``intent.text`` (still
    ``decoded_intent`` + ``model_id``), and it accepts nothing but decoder output.

Stale-command prevention: the router is off after every (re)start unless the start request
itself enables it, is switched off by ``stop`` (source change, error, end) and by
``stop_router`` (operator stop, pause, link loss), and switches itself off when the decoder
receives no input for longer than ``max(stall_ms, 3 x bin)`` once it has received any.
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
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, ConfigDict

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
    from brainos.decoding.model import Decoder
    from brainos.processing import SignalChain

log = logging.getLogger(__name__)

__all__ = [
    "ClickRule",
    "DiscreteRule",
    "PipelineError",
    "PipelineManager",
    "PipelineStartRequest",
    "PipelineStatus",
    "RouterSpec",
]

PIPELINE_ADAPTER = "brainos.pipeline@0.4.0"
QUEUE_MAX = 4096
LATENCY_WINDOW = 2048
STALL_BINS = 3  # the stall limit is never shorter than this many feature bins
STALL_CHECK_S = 0.05
ROUTER_LOG = 50


class PipelineStartRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    processing: dict[str, Any]
    model_id: str | None = None
    allow_cross_source: bool = False
    router: RouterSpec | None = None


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
class _Running:
    device: DeviceDescriptor
    session_id: str
    preset: str
    input_types: frozenset[str]
    chain: SignalChain | None
    fs: float | None
    output: dict[str, Any]
    decoder: Decoder | None
    streaming: Any  # StreamingDecoder | StreamingLDA: .step(features) -> values
    router: RouterSpec | None
    cross_source: bool
    warnings: list[str]
    behavior_std: list[float] | None
    capabilities: list[CapabilityDescriptor]
    started_at_ns: int = field(default_factory=time.time_ns)
    command_router: CommandRouter | None = None
    # monotonic time of the last decoder input since the router was enabled (stall watchdog)
    last_decoder_input: float | None = None


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
        self._run: _Running | None = None
        self._queue: deque[EventEnvelope] = deque()
        self._wake = asyncio.Event()
        self._task: asyncio.Task[None] | None = None
        self.last_error: str | None = None
        self._proc_us: deque[float] = deque(maxlen=LATENCY_WINDOW)
        self._lat_ms: deque[float] = deque(maxlen=LATENCY_WINDOW)
        self.router_log: deque[RouterEvent] = deque(maxlen=ROUTER_LOG)
        self.counters: dict[str, int] = {}
        self._reset_counters()

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
        from brainos.decoding import model as models
        from brainos.processing import ProcessingSpec, SignalChain, StageConfigError

        try:
            spec = ProcessingSpec.model_validate(req.processing)
        except ValueError as exc:
            raise PipelineError(
                ErrorCode.PROTOCOL_ERROR, f"invalid processing spec: {exc}"
            ) from None

        caps = {c.capability: c for c in device.capabilities}
        output: dict[str, Any]
        chain = None
        fs = None
        out_caps: list[CapabilityDescriptor] = []
        if spec.preset == "features_passthrough":
            feat = caps.get(Capability.NEURAL_FEATURES)
            if feat is None:
                raise PipelineError(
                    ErrorCode.CAPABILITY_UNSUPPORTED,
                    f"{device.display_name} provides no neural_features to pass through",
                )
            prm = feat.params
            feature = str(prm.get("feature", "spike_count"))
            event_type = (
                "features.binned"
                if feature in {"spike_count", "threshold_crossing_count"}
                else "features.vector"
            )
            labels_param = prm.get("channel_labels")
            output = {
                "event_type": event_type,
                "feature": feature,
                "bin_ms": float(str(prm.get("bin_ms", 0) or 0)),
                "channel_count": int(str(prm.get("channel_count", 0) or 0)),
                "channel_labels": list(labels_param) if isinstance(labels_param, list) else None,
                "unit": "count",
            }
            input_types = frozenset({event_type})
        else:
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
            spec, car_exclude = _source_specific(spec, rec.params, n)
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
            output = {
                "event_type": chain.out.event_type,
                "feature": chain.out.feature,
                "bin_ms": chain.out.bin_ms,
                "channel_count": n,
                "channel_labels": list(labels) if isinstance(labels, list) and labels else None,
                "unit": chain.out.unit,
            }
            input_types = frozenset({"recording.frame"})
            out_caps.append(
                CapabilityDescriptor(
                    capability=Capability.NEURAL_FEATURES,
                    params={
                        "feature": output["feature"],
                        "bin_ms": output["bin_ms"],
                        "channel_count": n,
                        "unit": output["unit"],
                        "source": "pipeline",
                    },
                    description=f"BrainOS pipeline ({spec.preset})",
                )
            )

        decoder: Decoder | None = None
        cross = False
        warnings: list[str] = []
        behavior_std = None
        if req.model_id:
            path = self.models_dir / f"{req.model_id}.json"
            if not path.exists():
                raise PipelineError(ErrorCode.DEVICE_NOT_FOUND, f"no model {req.model_id}")
            try:
                decoder = models.load_model(path)
            except (ValueError, TypeError, KeyError, OSError) as exc:
                raise PipelineError(
                    ErrorCode.INCOMPATIBLE_DECODER, f"cannot load model {req.model_id}: {exc}"
                ) from None
            from brainos.datasets import session_of

            bad = (
                rec_params.get("bad_channels")
                if (rec_params := _recording_params(device))
                else None
            )
            compat = models.check(
                decoder,
                event_type=output["event_type"],
                feature=output["feature"],
                bin_ms=output["bin_ms"],
                channel_count=output["channel_count"],
                channel_labels=output["channel_labels"],
                stream_identity=models.source_identity(origin),
                stream_session=session_of(origin or ""),
                allow_cross_source=req.allow_cross_source,
                stream_modality=device.modality.value if device.modality else None,
                stream_bad_channels=[str(b) for b in bad] if isinstance(bad, list) else None,
            )
            if not compat.ok:
                raise PipelineError(ErrorCode.INCOMPATIBLE_DECODER, "; ".join(compat.errors))
            cross, warnings = compat.cross_source, compat.warnings
            std = decoder.training.get("behavior_std")
            behavior_std = [float(v) for v in std] if isinstance(std, list) else None
            params: dict[str, Any] = {
                "model_id": decoder.model_id,
                "dims": decoder.dims,
                "space": decoder.space,
                "quantity": decoder.quantity,
            }
            classes = models.output_classes(decoder)
            if classes is not None:
                params["outputs"] = "classes"
            out_caps.append(
                CapabilityDescriptor(
                    capability=Capability.KINEMATIC_INTENT,
                    params=params,
                    description="decoded_intent from a calibrated model (not an app command)",
                )
            )
        router = req.router
        if router is not None and router.enabled:
            self._validate_router(router, decoder, behavior_std)
            assert decoder is not None
            out_caps.extend(router_capabilities(router, decoder.model_id))

        self.stop("pipeline restarted")
        self._reset_counters()
        self._proc_us.clear()
        self._lat_ms.clear()
        self.last_error = None
        self._run = _Running(
            device=device,
            session_id=session_id,
            preset=spec.preset,
            input_types=input_types,
            chain=chain,
            fs=fs,
            output=output,
            decoder=decoder,
            streaming=decoder.streaming() if decoder else None,
            router=router,
            cross_source=cross,
            warnings=warnings,
            behavior_std=behavior_std,
            capabilities=out_caps,
        )
        if router is not None and router.enabled and decoder is not None:
            self._run.command_router = self._make_router(self._run, router)
            self._log_router(True, "enabled with the pipeline start")
        self._queue.clear()
        self._task = asyncio.get_running_loop().create_task(self._loop(), name="brainos-pipeline")
        log.info(
            "pipeline started: %s on %s (decoder %s)", spec.preset, device.device_id, req.model_id
        )
        self._caps_changed()
        return self.status()

    @staticmethod
    def _validate_router(
        router: RouterSpec, decoder: Decoder | None, std: list[float] | None
    ) -> None:
        if decoder is None:
            raise PipelineError(
                ErrorCode.PROTOCOL_ERROR, "the command router needs a loaded decoder"
            )
        from brainos.decoding.model import output_classes

        try:
            validate_router(
                router,
                model_id=decoder.model_id,
                dims=decoder.dims,
                classes=output_classes(decoder),
                has_std=std is not None,
                quantity=decoder.quantity,
            )
        except RouterConfigError as exc:
            raise PipelineError(exc.code, exc.message) from None

    @staticmethod
    def _make_router(run: _Running, router: RouterSpec) -> CommandRouter:
        assert run.decoder is not None
        return CommandRouter(
            router,
            model_id=run.decoder.model_id,
            dims=run.decoder.dims,
            behavior_std=run.behavior_std,
        )

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
        if router.enabled:
            self._validate_router(router, run.decoder, run.behavior_std)
        was_on = _router_on(run)
        caps = [c for c in run.capabilities if c.capability not in COMMAND_CAPABILITIES]
        if router.enabled:
            assert run.decoder is not None
            caps.extend(router_capabilities(router, run.decoder.model_id))
        run.router = router
        run.capabilities = caps
        # fresh rule states and stall watchdog on every change; never carry state over
        run.command_router = self._make_router(run, router) if router.enabled else None
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
        if was_on:
            self._router_stopped(reason)
        if run is not None:
            log.info("pipeline stopped (%s)", reason)
            self._caps_changed()

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
        if len(self._queue) >= QUEUE_MAX:
            self._queue.popleft()
            self.counters["dropped_inputs"] += 1
        self._queue.append(env)
        self._wake.set()

    def stall_limit_ms(self, run: _Running | None = None) -> float | None:
        run = run or self._run
        if run is None or run.router is None or not run.router.enabled:
            return None
        bin_ms = float(run.output.get("bin_ms") or 0.0)
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

    async def _loop(self) -> None:
        while True:
            if not self._queue:
                self._wake.clear()
                timeout = STALL_CHECK_S if self.router_on else None
                with contextlib.suppress(TimeoutError):
                    await asyncio.wait_for(self._wake.wait(), timeout)
                self.check_stall()
                continue
            env = self._queue.popleft()
            run = self._run
            if run is None:
                return
            t0 = time.perf_counter()
            try:
                drafts = self._process(run, env)
            except Exception as exc:  # never let one bad input kill the pipeline
                self.counters["errors"] += 1
                self.last_error = f"{type(exc).__name__}: {exc}"
                log.exception("pipeline error on %s", env.event_type)
                continue
            self._proc_us.append((time.perf_counter() - t0) * 1e6)
            if drafts:
                self._ingest(drafts)
                self._lat_ms.append((time.time_ns() - env.timestamp_ns) / 1e6)
            self.check_stall()
            await asyncio.sleep(0)  # yield between inputs

    def _process(self, run: _Running, env: EventEnvelope) -> list[EventDraft]:
        import numpy as np

        prov = env.provenance
        flags = [f for f in env.quality.flags if f in (QualityFlag.SYNTHETIC, QualityFlag.REPLAYED)]
        gap = QualityFlag.DROPPED_SAMPLES in env.quality.flags

        def mk(kind: ProvenanceKind, *, model_id: str | None = None) -> Provenance:
            return Provenance(
                kind=kind,
                adapter=PIPELINE_ADAPTER,
                synthetic=prov.synthetic,
                model_id=model_id,
                origin=prov.origin,
                replayed=prov.replayed,
            )

        out: list[EventDraft] = []
        features: list[tuple[Any, int]] = []  # (values, device_ts_ns)
        self.counters["inputs"] += 1
        if run.chain is not None:
            p = env.payload
            samples = np.asarray(p.samples, dtype=np.float64).T  # type: ignore[union-attr]
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
                out.append(EventDraft(et, payload, fq, mk(ProvenanceKind.PROCESSED_FEATURE), ts))
                features.append((f.values, ts))
            self.counters["features_out"] += len(frames)
        else:
            p = env.payload
            vals = p.counts if env.event_type == EventType.FEATURES_BINNED else p.values  # type: ignore[union-attr]
            features.append((np.asarray(vals, dtype=np.float64), env.device_timestamp_ns or 0))

        dec = run.streaming
        if dec is not None and run.decoder is not None:
            model_id = run.decoder.model_id
            q = Quality(score=0.5 if (run.cross_source or gap) else 1.0, flags=flags)
            for vals, ts in features:
                pred = dec.step(vals)
                if run.command_router is not None:
                    run.last_decoder_input = time.monotonic()
                values = [float(v) for v in pred]
                if not all(math.isfinite(v) for v in values):
                    self.counters["errors"] += 1
                    continue
                decoded = EventDraft(
                    EventType.INTENT_KINEMATICS,
                    {
                        "quantity": run.decoder.quantity,
                        "dims": run.decoder.dims,
                        "unit": run.decoder.unit,
                        "values": values,
                        "space": run.decoder.space,
                    },
                    q,
                    mk(ProvenanceKind.DECODED_INTENT, model_id=model_id),
                    ts,
                )
                out.append(decoded)
                self.counters["decoded_out"] += 1
                if run.command_router is not None:
                    gated = run.command_router.clicks_gated
                    for cmd in run.command_router.route(decoded):
                        out.append(cmd)
                        if cmd.event_type is EventType.INTENT_POINTER:
                            self.counters["commands_out"] += 1
                        elif cmd.event_type is EventType.INTENT_SELECTION:
                            self.counters["selections_out"] += 1
                        elif cmd.event_type is EventType.INTENT_NAVIGATE:
                            self.counters["navigations_out"] += 1
                        else:
                            self.counters["texts_out"] += 1
                    self.counters["clicks_gated"] += run.command_router.clicks_gated - gated
        return out

    # ------------------------------------------------------------------ status
    def status(self) -> PipelineStatus:
        run = self._run
        warm = 0.0
        if run is not None and run.chain is not None and run.fs and run.chain.tc is not None:
            remaining = run.chain.warmup_samples - run.chain.processed
            warm = max(0.0, remaining / run.fs)
        from_decoder = None
        if run is not None and run.decoder is not None:
            from brainos.decoding.model import summary

            from_decoder = summary(run.decoder)
        return PipelineStatus(
            available=self.available,
            unavailable_reason=self.unavailable_reason,
            running=run is not None,
            device_id=run.device.device_id if run else None,
            session_id=run.session_id if run else None,
            preset=run.preset if run else None,
            stages=run.chain.stages
            if run and run.chain
            else (["features from source (passthrough)"] if run else []),
            input_event_type=next(iter(run.input_types)) if run else None,
            output=run.output if run else None,
            warmup_remaining_s=round(warm, 3),
            decoder=from_decoder,
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
        )

    async def aclose(self) -> None:
        task, self._task = self._task, None
        if _router_on(self._run):
            self._router_stopped("runtime shutdown")
        self._run = None
        if task is not None:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task


def _recording_params(device: DeviceDescriptor) -> dict[str, Any] | None:
    rec = next((c for c in device.capabilities if c.capability is Capability.RECORDING), None)
    return dict(rec.params) if rec is not None else None


def _source_specific(spec: Any, params: dict[str, Any], n: int) -> tuple[Any, list[int]]:
    """Apply what the source declares (M5): its mains frequency for the line-noise notch and its
    bad channels, which are left out of the common average reference.

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


def _probe() -> tuple[bool, str | None]:
    try:
        import numpy  # noqa: F401
        import scipy  # noqa: F401
    except ImportError as exc:
        return False, f"signal processing not installed ({exc.name}); pip install 'brainos[dsp]'"
    return True, None
