"""Runtime orchestrator.

Owns the device lifecycle (connect / switch / pause / resume / reconnect /
disconnect), turns adapter drafts into validated envelopes, assigns sequence
numbers, and routes events to subscribers via the bus.

Concurrency model: everything runs on one asyncio loop. Commands are
serialized by ``_lock``. Envelope stamping (``_ingest``) contains no awaits, so
seq assignment is atomic and strictly increasing per session.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import secrets
import time
import uuid
from collections.abc import Sequence

from pydantic import ValidationError

from brainos.adapters.base import (
    DeviceAdapter,
    DeviceLinkError,
    EndOfStream,
    EventDraft,
    PacketDecodeError,
    PlaybackControl,
)
from brainos.contracts.capabilities import EVENT_CAPABILITY, Capability, EventType
from brainos.contracts.events import (
    SCHEMA_VERSION,
    DeviceState,
    Provenance,
    ProvenanceKind,
    Quality,
    QualityFlag,
    parse_envelope,
)
from brainos.contracts.protocol import (
    AppInfo,
    DeviceDescriptor,
    ErrorCode,
    NegotiationResult,
    PlaybackStatus,
    RuntimeSnapshot,
    RuntimeState,
)
from brainos.runtime.bus import DEFAULT_QUEUE_SIZE, EventBus, Subscriber
from brainos.runtime.diagnostics import Diagnostics, DiagnosticsSnapshot
from brainos.runtime.negotiation import negotiate
from brainos.runtime.pipeline import (
    PipelineError,
    PipelineManager,
    PipelineStartRequest,
    PipelineStatus,
    RouterSpec,
)
from brainos.runtime.recorder import Recorder, RecorderError, RecordingInfo
from brainos.runtime.registry import DeviceNotFoundError, DeviceOpenError, DeviceRegistry

log = logging.getLogger(__name__)

RUNTIME_ADAPTER = "brainos.runtime@0.1.0"
OPEN_TIMEOUT_S = 5.0
DEFAULT_BACKOFF_S: tuple[float, ...] = (0.2, 0.5, 1.0)


class RuntimeCommandError(Exception):
    def __init__(self, code: ErrorCode, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(f"{code}: {message}")


class Runtime:
    def __init__(
        self,
        registry: DeviceRegistry,
        recorder: Recorder,
        *,
        queue_size: int = DEFAULT_QUEUE_SIZE,
        reconnect_backoff_s: Sequence[float] = DEFAULT_BACKOFF_S,
    ) -> None:
        self.registry = registry
        self.recorder = recorder
        self.bus = EventBus()
        self.bus.add_tap(recorder.on_event)
        self.pipeline = PipelineManager(
            registry.catalog.models_dir, self._ingest_derived, self._renegotiate_all
        )
        self.bus.add_tap(self.pipeline.tap)
        self.diagnostics = Diagnostics()
        self._queue_size = queue_size
        self._backoff = tuple(reconnect_backoff_s)
        self._lock = asyncio.Lock()
        self._state = RuntimeState.IDLE
        self._state_since_ns = time.time_ns()
        self._device: DeviceDescriptor | None = None
        self._adapter: DeviceAdapter | None = None
        self._session_id: str | None = None
        self._seq = 0
        self._last_device_ts: int | None = None
        self._last_error: str | None = None
        self._paused = False
        self._pump_task: asyncio.Task[None] | None = None
        self._background: set[asyncio.Future[None]] = set()

    # ------------------------------------------------------------------ queries
    @property
    def state(self) -> RuntimeState:
        return self._state

    @property
    def adapter(self) -> DeviceAdapter | None:
        return self._adapter

    @property
    def device(self) -> DeviceDescriptor | None:
        return self._device

    def snapshot(self) -> RuntimeSnapshot:
        return RuntimeSnapshot(
            state=self._state,
            device=self._device,
            session_id=self._session_id,
            state_since_ns=self._state_since_ns,
            last_error=self._last_error,
            recording=self.recorder.active_name,
            apps=[s.info() for s in self.bus.subscribers],
        )

    def diagnostics_snapshot(self) -> DiagnosticsSnapshot:
        return self.diagnostics.snapshot([s.info() for s in self.bus.subscribers])

    def _active_device(self) -> DeviceDescriptor | None:
        """The device apps negotiate against: only one that is delivering events."""
        if self._adapter is None or self._state in (RuntimeState.ERROR, RuntimeState.ENDED):
            return None
        extra = self.pipeline.capability_descriptors() if self._device is not None else []
        if not extra or self._device is None:
            return self._device
        # Negotiate against device capabilities plus what the running pipeline derives.
        have = self._device.capability_set
        merged = list(self._device.capabilities) + [c for c in extra if c.capability not in have]
        return self._device.model_copy(update={"capabilities": merged})

    # ------------------------------------------------------------- applications
    def register_app(
        self, app: AppInfo, required: list[Capability], optional: list[Capability]
    ) -> Subscriber:
        sub = Subscriber(
            connection_id=f"con_{uuid.uuid4().hex[:12]}",
            app=app,
            required=required,
            optional=optional,
            negotiation=negotiate(required, optional, self._active_device()),
            max_queue=self._queue_size,
        )
        self.bus.add(sub)
        log.info(
            "app connected: %s (%s) status=%s", app.id, sub.connection_id, sub.negotiation.status
        )
        self._broadcast_runtime()
        return sub

    def unregister_app(self, connection_id: str) -> None:
        sub = self.bus.remove(connection_id)
        if sub is not None:
            log.info("app disconnected: %s (%s)", sub.app.id, connection_id)
            self._broadcast_runtime()

    def preview_negotiation(
        self, device_id: str | None, required: list[Capability], optional: list[Capability]
    ) -> NegotiationResult:
        device = self._describe(device_id) if device_id else self._active_device()
        return negotiate(required, optional, device)

    def _renegotiate_all(self) -> None:
        device = self._active_device()
        for sub in self.bus.subscribers:
            result = negotiate(sub.required, sub.optional, device)
            if result != sub.negotiation:
                sub.set_negotiation(result)
                sub.offer_control(
                    '{"type":"negotiation","negotiation":' + result.model_dump_json() + "}"
                )

    def _broadcast_runtime(self) -> None:
        self.bus.broadcast_control(
            '{"type":"runtime","runtime":' + self.snapshot().model_dump_json() + "}"
        )

    def _set_state(self, state: RuntimeState) -> None:
        if state is not self._state:
            log.info("runtime state %s -> %s", self._state, state)
            self._state = state
            self._state_since_ns = time.time_ns()
        self._broadcast_runtime()

    # ---------------------------------------------------------------- commands
    def _describe(self, device_id: str) -> DeviceDescriptor:
        try:
            return self.registry.describe(device_id)
        except DeviceNotFoundError:
            raise RuntimeCommandError(
                ErrorCode.DEVICE_NOT_FOUND, f"unknown device '{device_id}'"
            ) from None

    async def connect(self, device_id: str) -> RuntimeSnapshot:
        async with self._lock:
            if self._adapter is not None:
                raise RuntimeCommandError(
                    ErrorCode.INVALID_STATE,
                    f"device '{self._device.device_id if self._device else '?'}' is connected; "
                    "use switch or disconnect first",
                )
            await self._connect(device_id)
            return self.snapshot()

    async def switch(self, device_id: str) -> RuntimeSnapshot:
        async with self._lock:
            self._describe(device_id)  # fail fast before tearing down the current device
            t0 = time.perf_counter()
            previous = self._device.device_id if self._adapter and self._device else None
            if self._adapter is not None:
                await self._disconnect(f"switching to {device_id}")
            await self._connect(device_id)
            self.diagnostics.record_switch(previous, device_id, (time.perf_counter() - t0) * 1000)
            return self.snapshot()

    async def disconnect(self) -> RuntimeSnapshot:
        async with self._lock:
            if self._adapter is not None:
                await self._disconnect("operator disconnect")
            else:
                # clear error/ended states
                if self.recorder.active_name:
                    self.recorder.stop("operator disconnect")
                self._device = None
                self._session_id = None
                self._last_error = None
                self._set_state(RuntimeState.IDLE)
            return self.snapshot()

    async def pause(self) -> RuntimeSnapshot:
        async with self._lock:
            if self._state is not RuntimeState.STREAMING or self._adapter is None:
                raise RuntimeCommandError(
                    ErrorCode.INVALID_STATE, f"cannot pause in state {self._state}"
                )
            self._paused = True
            self._adapter.set_paused(True)
            self._emit_status(DeviceState.PAUSED, "paused by operator")
            self._set_state(RuntimeState.PAUSED)
            return self.snapshot()

    async def resume(self) -> RuntimeSnapshot:
        async with self._lock:
            if self._state is not RuntimeState.PAUSED or self._adapter is None:
                raise RuntimeCommandError(
                    ErrorCode.INVALID_STATE, f"cannot resume in state {self._state}"
                )
            self._paused = False
            self._adapter.set_paused(False)
            self._emit_status(DeviceState.STREAMING, "resumed by operator")
            self._set_state(RuntimeState.STREAMING)
            return self.snapshot()

    # ------------------------------------------------------------- playback
    def _playback(self) -> PlaybackControl:
        adapter = self._adapter
        if adapter is None:
            raise RuntimeCommandError(ErrorCode.INVALID_STATE, "no device connected")
        if not isinstance(adapter, PlaybackControl):
            raise RuntimeCommandError(
                ErrorCode.UNSUPPORTED_OPERATION,
                f"{adapter.descriptor.display_name} is a live source; "
                "playback control applies to recordings",
            )
        return adapter

    def playback_status(self) -> PlaybackStatus:
        return self._playback().playback_status()

    async def set_playback_speed(self, speed: float) -> PlaybackStatus:
        async with self._lock:
            pb = self._playback()
            try:
                pb.set_speed(speed)
            except ValueError as exc:
                raise RuntimeCommandError(ErrorCode.PROTOCOL_ERROR, str(exc)) from None
            log.info("playback speed set to %gx", speed)
            return pb.playback_status()

    # ------------------------------------------------------------- pipeline
    def _adapter_origin(self) -> str | None:
        origin = getattr(self._adapter, "origin", None)
        return origin if isinstance(origin, str) else None

    def start_pipeline(self, req: PipelineStartRequest) -> PipelineStatus:
        if self._state not in (RuntimeState.STREAMING, RuntimeState.PAUSED):
            raise RuntimeCommandError(
                ErrorCode.INVALID_STATE, f"cannot start a pipeline in state {self._state}"
            )
        try:
            return self.pipeline.start(req, self._device, self._session_id, self._adapter_origin())
        except PipelineError as exc:
            raise RuntimeCommandError(exc.code, exc.message) from None

    def set_router(self, router: RouterSpec) -> PipelineStatus:
        try:
            return self.pipeline.set_router(router)
        except PipelineError as exc:
            raise RuntimeCommandError(exc.code, exc.message) from None

    def stop_pipeline(self) -> PipelineStatus:
        self.pipeline.stop("stopped by operator")
        return self.pipeline.status()

    def start_recording(self, name: str | None = None) -> str:
        if (
            self._adapter is None
            or self._device is None
            or self._state
            not in (
                RuntimeState.STREAMING,
                RuntimeState.PAUSED,
            )
        ):
            raise RuntimeCommandError(ErrorCode.INVALID_STATE, "connect a device before recording")
        try:
            rec = self.recorder.start(self._device, name)
        except RecorderError as exc:
            raise RuntimeCommandError(ErrorCode.RECORDING_ERROR, str(exc)) from exc
        self._broadcast_runtime()
        return rec

    def stop_recording(self) -> RecordingInfo:
        info = self.recorder.stop("stopped by operator")
        if info is None:
            raise RuntimeCommandError(ErrorCode.RECORDING_ERROR, "not recording")
        self._broadcast_runtime()
        return info

    async def shutdown(self) -> None:
        await self.pipeline.aclose()
        async with self._lock:
            if self._adapter is not None:
                await self._disconnect("runtime shutdown")
            self.recorder.stop("runtime shutdown")

    # ---------------------------------------------------------------- internals
    async def _connect(self, device_id: str) -> None:
        try:
            # off the event loop: opening a dataset file can take a few hundred ms
            adapter = await asyncio.to_thread(self.registry.create, device_id)
        except DeviceOpenError as exc:
            self._fail(str(exc), kind="connect_error")
            raise RuntimeCommandError(ErrorCode.DEVICE_ERROR, str(exc)) from None
        except DeviceNotFoundError:
            raise RuntimeCommandError(
                ErrorCode.DEVICE_NOT_FOUND, f"unknown device '{device_id}'"
            ) from None
        self._device = adapter.descriptor
        self._session_id = f"ses_{secrets.token_hex(8)}"
        self._seq = 0
        self._last_device_ts = None
        self._last_error = None
        self._paused = False
        self.diagnostics.reset_rates()
        self._set_state(RuntimeState.CONNECTING)
        try:
            await asyncio.wait_for(adapter.open(), OPEN_TIMEOUT_S)
        except (DeviceLinkError, TimeoutError) as exc:
            msg = str(exc) or "open timed out"
            await adapter.close()
            self._fail(f"connect failed: {msg}", kind="connect_error")
            raise RuntimeCommandError(ErrorCode.DEVICE_ERROR, msg) from exc
        self._adapter = adapter
        # Live adapters learn channels/rates/units during open(); use the refined descriptor.
        self._device = adapter.descriptor
        self._renegotiate_all()  # before emitting, so apps receive the 'connected' status
        self._emit_status(DeviceState.CONNECTED, f"connected to {adapter.descriptor.display_name}")
        self._emit_status(DeviceState.STREAMING, "streaming")
        self._set_state(RuntimeState.STREAMING)
        self._pump_task = asyncio.create_task(self._pump(adapter), name=f"pump:{device_id}")
        self._pump_task.add_done_callback(self._pump_done)

    async def _disconnect(self, reason: str) -> None:
        self.pipeline.stop(f"device disconnected ({reason})")
        self._set_state(RuntimeState.DISCONNECTING)
        await self._stop_pump()
        if self.recorder.active_name:
            self.recorder.stop(f"device disconnected ({reason})")
        self._emit_status(DeviceState.DISCONNECTED, reason)
        if self._adapter is not None:
            await self._adapter.close()
        self._adapter = None
        self._device = None
        self._session_id = None
        self._paused = False
        self._set_state(RuntimeState.IDLE)
        self._renegotiate_all()

    async def _stop_pump(self) -> None:
        task, self._pump_task = self._pump_task, None
        if task is not None and task is not asyncio.current_task():
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task

    def _pump_done(self, task: asyncio.Task[None]) -> None:
        """Watchdog: a pump that dies from an unexpected exception must not leave the
        runtime claiming to stream."""
        if task.cancelled() or task.exception() is None:
            return
        exc = task.exception()
        log.error("event pump crashed", exc_info=exc)
        if self._pump_task is not task:
            return
        self._pump_task = None
        adapter = self._adapter
        self._fail(f"internal error in event pump: {exc!r}", kind="pump_crash")
        if adapter is not None:
            close = asyncio.ensure_future(adapter.close())
            self._background.add(close)
            close.add_done_callback(self._background.discard)

    def _fail(self, message: str, *, kind: str) -> None:
        log.error("runtime error (%s): %s", kind, message)
        self.pipeline.stop(f"runtime error: {kind}")
        if self.recorder.active_name:
            self.recorder.stop(f"runtime error: {kind}")
        self._last_error = message
        self.diagnostics.record_error(
            kind, self._device.device_id if self._device else None, message
        )
        self._adapter = None
        self._set_state(RuntimeState.ERROR)
        self._renegotiate_all()

    async def _pump(self, adapter: DeviceAdapter) -> None:
        device_id = adapter.device_id
        while True:
            try:
                packet = await adapter.read()
            except DeviceLinkError as exc:
                if not await self._reconnect(adapter, exc):
                    return
                continue
            except EndOfStream as exc:
                log.info("%s: %s", device_id, exc)
                self._emit_status(DeviceState.ENDED, str(exc))
                if self.recorder.active_name:
                    self.recorder.stop("source ended")
                self.pipeline.stop("source ended")
                self._set_state(RuntimeState.ENDED)
                self._renegotiate_all()
                return
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # adapter bug: treat as a link failure, never crash the pump
                log.exception("%s: unexpected adapter error in read()", device_id)
                if not await self._reconnect(adapter, DeviceLinkError(f"adapter error: {exc!r}")):
                    return
                continue

            if self._paused:
                self.diagnostics.discarded_while_paused += 1
                continue
            try:
                drafts = adapter.normalize(packet)
            except PacketDecodeError as exc:
                self.diagnostics.decode_errors += 1
                self.diagnostics.record_error("decode_error", device_id, str(exc))
                log.warning("%s: dropped undecodable packet: %s", device_id, exc)
                continue
            except Exception as exc:
                self.diagnostics.decode_errors += 1
                self.diagnostics.record_error(
                    "decode_error", device_id, f"normalize crashed: {exc!r}"
                )
                log.exception("%s: normalize() raised unexpectedly", device_id)
                continue
            for draft in drafts:
                self._ingest(draft, packet.read_monotonic_ns)

    async def _reconnect(self, adapter: DeviceAdapter, error: DeviceLinkError) -> bool:
        device_id = adapter.device_id
        self.diagnostics.link_errors += 1
        self.diagnostics.record_error("link_error", device_id, str(error))
        log.warning("%s: link error: %s; attempting reconnect", device_id, error)
        self._emit_status(DeviceState.RECONNECTING, str(error))
        self._set_state(RuntimeState.RECONNECTING)
        await adapter.close()
        last: Exception = error
        for attempt, delay in enumerate(self._backoff, start=1):
            await asyncio.sleep(delay)
            self.diagnostics.reconnect_attempts += 1
            try:
                await asyncio.wait_for(adapter.open(), OPEN_TIMEOUT_S)
            except (DeviceLinkError, TimeoutError) as exc:
                last = exc
                log.warning("%s: reconnect attempt %d failed: %s", device_id, attempt, exc)
                continue
            self.diagnostics.reconnect_successes += 1
            if adapter.descriptor != self._device:
                # e.g. the stream came back with a different channel layout
                log.warning("%s: descriptor changed on reconnect", device_id)
                self._device = adapter.descriptor
                self._renegotiate_all()
            adapter.set_paused(self._paused)
            self._emit_status(DeviceState.STREAMING, f"reconnected after {attempt} attempt(s)")
            self._set_state(RuntimeState.PAUSED if self._paused else RuntimeState.STREAMING)
            return True
        message = f"link lost; {len(self._backoff)} reconnect attempts failed: {last}"
        self._emit_status(DeviceState.ERROR, message)
        await adapter.close()
        self._pump_task = None
        self._fail(message, kind="reconnect_failed")
        return False

    def _emit_status(self, state: DeviceState, detail: str) -> None:
        if self._device is None or self._session_id is None:
            return
        draft = EventDraft(
            event_type=EventType.DEVICE_STATUS,
            payload={"state": state.value, "detail": detail[:512]},
            quality=Quality(
                score=1.0, flags=[QualityFlag.SYNTHETIC] if self._device.synthetic else []
            ),
            provenance=Provenance(
                kind=ProvenanceKind.RUNTIME,
                adapter=RUNTIME_ADAPTER,
                synthetic=self._device.synthetic,
                origin="runtime",
            ),
        )
        self._ingest(draft, time.monotonic_ns(), from_runtime=True)

    def _ingest_derived(self, drafts: list[EventDraft]) -> None:
        now = time.monotonic_ns()
        for d in drafts:
            self._ingest(d, now, derived=True)

    def _ingest(
        self, draft: EventDraft, read_ns: int, *, from_runtime: bool = False, derived: bool = False
    ) -> None:
        """Stamp, validate, publish. Synchronous by design (atomic seq assignment)."""
        device = self._device
        if device is None or self._session_id is None:
            return
        capability = EVENT_CAPABILITY.get(draft.event_type)
        allowed = from_runtime or (capability is not None and device.supports(capability))
        if not allowed and derived and capability in self.pipeline.capabilities:
            allowed = True
        if capability is None or not allowed:
            self.diagnostics.undeclared_capability += 1
            self.diagnostics.record_error(
                "undeclared_capability",
                device.device_id,
                f"adapter emitted {draft.event_type} but did not declare {capability}",
            )
            return
        quality = draft.quality
        dev_ts = draft.device_timestamp_ns
        if dev_ts is not None:
            if self._last_device_ts is not None and dev_ts < self._last_device_ts:
                self.diagnostics.timestamp_regressions += 1
                back_ms = (self._last_device_ts - dev_ts) / 1e6
                self.diagnostics.record_error(
                    "timestamp_regression",
                    device.device_id,
                    f"device clock went backwards by {back_ms:.3f} ms",
                )
                quality = Quality(
                    score=min(quality.score, 0.5),
                    flags=[*quality.flags, QualityFlag.TIMESTAMP_REGRESSION],
                )
            self._last_device_ts = dev_ts
        try:
            envelope = parse_envelope(
                {
                    "schema_version": SCHEMA_VERSION,
                    "session_id": self._session_id,
                    "device_id": device.device_id,
                    "seq": self._seq,
                    "timestamp_ns": time.time_ns(),
                    "device_timestamp_ns": dev_ts,
                    "event_type": draft.event_type,
                    "capability": capability,
                    "payload": draft.payload,
                    "quality": quality,
                    "provenance": draft.provenance,
                }
            )
        except ValidationError as exc:
            self.diagnostics.validation_errors += 1
            errs = exc.errors()
            where = f"{errs[0]['loc']} {errs[0]['msg']}" if errs else str(exc)
            msg = f"{draft.event_type}: {where}"
            self.diagnostics.record_error("validation_error", device.device_id, msg)
            log.warning("%s: dropped invalid event: %s", device.device_id, msg)
            return
        self._seq += 1
        event_json = envelope.model_dump_json()
        self.bus.publish(envelope, capability, event_json)
        self.diagnostics.record_event(draft.event_type.value, time.monotonic_ns() - read_ns)
