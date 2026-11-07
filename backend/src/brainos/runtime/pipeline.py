"""Real-time processing pipeline: acquisition -> features -> decoder -> (router) -> app events.

Runs as its own asyncio task, fed by a bus tap through a bounded queue (overflow drops the
oldest input and is counted). Derived events re-enter the runtime through the same ingest
path as device events, so they get sequence numbers, validation and provenance like
everything else.

Separation rules enforced here:
  * features are ``processed_feature`` (never intents);
  * decoder output is ``intent.kinematics`` with ``decoded_intent`` + ``model_id`` — not
    actionable by applications that ask for pointer/selection;
  * only the explicitly enabled **command router** turns decoded output into
    ``intent.pointer`` (still ``decoded_intent`` + ``model_id``).
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

if TYPE_CHECKING:
    from brainos.decoding.ridge import RidgeDecoder, StreamingDecoder
    from brainos.processing import SignalChain

log = logging.getLogger(__name__)

PIPELINE_ADAPTER = "brainos.pipeline@0.3.0"
QUEUE_MAX = 4096
LATENCY_WINDOW = 2048


class RouterSpec(BaseModel):
    """Explicit mapping of two decoded dimensions to pointer velocity."""

    model_config = ConfigDict(extra="forbid")

    enabled: bool = False
    x_dim: str
    y_dim: str
    gain: float = Field(default=1.0, gt=0, le=10, description="workspace/s per training-std unit")
    deadzone: float = Field(default=0.3, ge=0, lt=3, description="in training-std units")
    invert_y: bool = False
    max_speed: float = Field(default=2.0, gt=0, le=10)


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
    decoder: RidgeDecoder | None
    streaming: StreamingDecoder | None
    router: RouterSpec | None
    cross_source: bool
    warnings: list[str]
    behavior_std: list[float] | None
    capabilities: list[CapabilityDescriptor]
    started_at_ns: int = field(default_factory=time.time_ns)


class PipelineManager:
    def __init__(
        self,
        models_dir: Path,
        ingest: Callable[[list[EventDraft]], None],
        on_capabilities_changed: Callable[[], None],
    ) -> None:
        self.models_dir = models_dir
        self._ingest = ingest
        self._caps_changed = on_capabilities_changed
        self.available, self.unavailable_reason = _probe()
        self._run: _Running | None = None
        self._queue: deque[EventEnvelope] = deque()
        self._wake = asyncio.Event()
        self._task: asyncio.Task[None] | None = None
        self.last_error: str | None = None
        self._proc_us: deque[float] = deque(maxlen=LATENCY_WINDOW)
        self._lat_ms: deque[float] = deque(maxlen=LATENCY_WINDOW)
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
            "errors": 0,
        }

    # ------------------------------------------------------------------ capabilities
    @property
    def running(self) -> bool:
        return self._run is not None

    def capability_descriptors(self) -> list[CapabilityDescriptor]:
        return list(self._run.capabilities) if self._run else []

    @property
    def capabilities(self) -> frozenset[Capability]:
        return frozenset(c.capability for c in self.capability_descriptors())

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
        from brainos.decoding.ridge import RidgeDecoder
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
            try:
                chain = SignalChain(spec, fs, n, unit)
            except StageConfigError as exc:
                raise PipelineError(ErrorCode.CAPABILITY_UNSUPPORTED, str(exc)) from None
            labels = rec.params.get("channel_labels")
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

        decoder = None
        cross = False
        warnings: list[str] = []
        behavior_std = None
        if req.model_id:
            path = self.models_dir / f"{req.model_id}.json"
            if not path.exists():
                raise PipelineError(ErrorCode.DEVICE_NOT_FOUND, f"no model {req.model_id}")
            decoder = RidgeDecoder.load(path)
            from brainos.datasets import session_of

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
            )
            if not compat.ok:
                raise PipelineError(ErrorCode.INCOMPATIBLE_DECODER, "; ".join(compat.errors))
            cross, warnings = compat.cross_source, compat.warnings
            std = decoder.training.get("behavior_std")
            behavior_std = [float(v) for v in std] if isinstance(std, list) else None
            out_caps.append(
                CapabilityDescriptor(
                    capability=Capability.KINEMATIC_INTENT,
                    params={
                        "model_id": decoder.model_id,
                        "dims": decoder.dims,
                        "space": decoder.space,
                    },
                    description="decoded_intent from a calibrated model (not an app command)",
                )
            )
        router = req.router
        if router is not None and router.enabled:
            self._validate_router(router, decoder, behavior_std)
            out_caps.append(self._router_cap(router, decoder))

        self.stop("restarting")
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
        self._queue.clear()
        self._task = asyncio.get_running_loop().create_task(self._loop(), name="brainos-pipeline")
        log.info(
            "pipeline started: %s on %s (decoder %s)", spec.preset, device.device_id, req.model_id
        )
        self._caps_changed()
        return self.status()

    @staticmethod
    def _validate_router(
        router: RouterSpec, decoder: RidgeDecoder | None, std: list[float] | None
    ) -> None:
        if decoder is None:
            raise PipelineError(
                ErrorCode.PROTOCOL_ERROR, "the command router needs a loaded decoder"
            )
        for d in (router.x_dim, router.y_dim):
            if d not in decoder.dims:
                raise PipelineError(
                    ErrorCode.PROTOCOL_ERROR, f"decoder has no dimension {d!r} ({decoder.dims})"
                )
        if std is None:
            raise PipelineError(
                ErrorCode.PROTOCOL_ERROR,
                "model lacks training behavior_std; retrain it to use the router",
            )

    @staticmethod
    def _router_cap(router: RouterSpec, decoder: RidgeDecoder | None) -> CapabilityDescriptor:
        return CapabilityDescriptor(
            capability=Capability.POINTER_INTENT,
            params={
                "source": "command_router",
                "model_id": decoder.model_id if decoder else "",
                "x_dim": router.x_dim,
                "y_dim": router.y_dim,
                "gain": router.gain,
            },
            description="Pointer commands routed from a decoder by explicit operator mapping",
        )

    def set_router(self, router: RouterSpec) -> PipelineStatus:
        run = self._run
        if run is None:
            raise PipelineError(ErrorCode.INVALID_STATE, "no pipeline running")
        caps = [c for c in run.capabilities if c.capability is not Capability.POINTER_INTENT]
        if router.enabled:
            self._validate_router(router, run.decoder, run.behavior_std)
            caps.append(self._router_cap(router, run.decoder))
        run.router = router
        run.capabilities = caps
        self._caps_changed()
        return self.status()

    def stop(self, reason: str = "stopped") -> None:
        task, self._task = self._task, None
        if task is not None:
            task.cancel()
        had = self._run is not None
        self._run = None
        self._queue.clear()
        if had:
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

    async def _loop(self) -> None:
        while True:
            if not self._queue:
                self._wake.clear()
                await self._wake.wait()
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
                values = [float(v) for v in pred]
                if not all(math.isfinite(v) for v in values):
                    self.counters["errors"] += 1
                    continue
                out.append(
                    EventDraft(
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
                )
                self.counters["decoded_out"] += 1
                r = run.router
                if r is not None and r.enabled and run.behavior_std is not None:
                    v = self._route(r, run.decoder.dims, values, run.behavior_std)
                    out.append(
                        EventDraft(
                            EventType.INTENT_POINTER,
                            {"vx": v[0], "vy": v[1]},
                            q,
                            mk(ProvenanceKind.DECODED_INTENT, model_id=model_id),
                            ts,
                        )
                    )
                    self.counters["commands_out"] += 1
        return out

    @staticmethod
    def _route(
        r: RouterSpec, dims: list[str], values: list[float], std: list[float]
    ) -> tuple[float, float]:
        res = []
        for d in (r.x_dim, r.y_dim):
            i = dims.index(d)
            z = values[i] / std[i] if std[i] > 0 else 0.0
            if abs(z) < r.deadzone:
                z = 0.0
            v = max(-r.max_speed, min(r.max_speed, r.gain * z))
            res.append(round(v, 6))
        if r.invert_y:
            res[1] = -res[1]
        return res[0], res[1]

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
        )

    async def aclose(self) -> None:
        task, self._task = self._task, None
        self._run = None
        if task is not None:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task


def _probe() -> tuple[bool, str | None]:
    try:
        import numpy  # noqa: F401
        import scipy  # noqa: F401
    except ImportError as exc:
        return False, f"signal processing not installed ({exc.name}); pip install 'brainos[dsp]'"
    return True, None
