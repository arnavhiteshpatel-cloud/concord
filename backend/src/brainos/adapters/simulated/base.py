"""Shared machinery for simulated adapters: scheduling, pause, fault injection.

Subclasses define the profile (capabilities, rates) and — importantly — their own
*native wire format* and ``normalize()``. The scheduling here is device-side
behaviour; nothing in this module knows about envelopes or sequencing.
"""

from __future__ import annotations

import asyncio
import logging
import random
import time
from abc import abstractmethod
from collections import deque
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from brainos.adapters.base import DeviceAdapter, DeviceLinkError, NativePacket
from brainos.adapters.simulated.intent_source import DiscreteIntent, OperatorIntentSource

log = logging.getLogger(__name__)

REGRESSION_US = 50_000  # how far back the clock jumps for an injected regression
MAX_CATCHUP_PERIODS = 5  # scheduler resyncs rather than bursting after a stall


class Fault(StrEnum):
    LINK_DROP = "link_drop"  # link drops once; reopening succeeds
    LINK_FAIL = "link_fail"  # link drops and every reopen fails until a new connect
    MALFORMED_PACKET = "malformed_packet"  # next packet is corrupt on the wire
    TIMESTAMP_REGRESSION = "timestamp_regression"  # next packet's device clock jumps back


@dataclass(slots=True)
class _Stream:
    name: str
    period_s: float
    next_due: float = 0.0


class SimulatedAdapter(DeviceAdapter):
    ADAPTER_VERSION = "0.1.0"
    #: simulated device-side latency from operator intent to emitted packet
    DISCRETE_LATENCY_S: float = 0.0

    def __init__(self, intents: OperatorIntentSource, *, seed: int | None = None) -> None:
        self._intents = intents
        self._rng = random.Random(seed)
        self._open = False
        self._ever_opened = False
        self._paused = False
        self._link_failed = False
        self._faults: deque[Fault] = deque()
        self._pending: deque[NativePacket] = deque()
        self._delayed: list[tuple[float, DiscreteIntent]] = []
        self._clock_origin = 0.0
        self._regress_next = False
        self._streams = [_Stream(n, p) for n, p in self.stream_periods().items()]

    # ------------------------------------------------------------- profile hooks
    @abstractmethod
    def stream_periods(self) -> dict[str, float]:
        """Periodic native streams and their periods in seconds."""

    @abstractmethod
    def produce(self, stream: str, clock_us: int) -> list[Any]:
        """Produce native packet data for a due periodic stream."""

    @abstractmethod
    def encode_discrete(self, intent: DiscreteIntent, clock_us: int) -> Any | None:
        """Encode an operator discrete intent natively; ``None`` if unsupported."""

    @abstractmethod
    def malformed(self, clock_us: int) -> Any:
        """A corrupt native packet, for fault injection."""

    # ------------------------------------------------------------------ contract
    async def open(self) -> None:
        await asyncio.sleep(0.01)  # a real link takes time to establish
        if self._link_failed:
            raise DeviceLinkError(
                f"{self.device_id}: simulated link failure (device not responding)"
            )
        now = time.monotonic()
        if not self._ever_opened:
            self._clock_origin = now
            self._intents.clear()
            self._ever_opened = True
        self._reset_schedule(now)
        self._open = True
        log.info("simulated device %s opened", self.device_id)

    async def close(self) -> None:
        self._open = False
        self._pending.clear()

    def set_paused(self, paused: bool) -> None:
        self._paused = paused
        if not paused:
            self._reset_schedule(time.monotonic())

    def inject_fault(self, fault: Fault) -> None:
        log.warning("fault injected on %s: %s", self.device_id, fault)
        self._faults.append(fault)

    async def read(self) -> NativePacket:
        while True:
            if not self._open:
                raise DeviceLinkError(f"{self.device_id}: link not open")
            if self._faults:
                pkt = self._apply_fault(self._faults.popleft())
                if pkt is not None:
                    return pkt
                continue
            if self._pending:
                return self._pending.popleft()
            if self._paused:
                self._intents.drain_discrete()  # intents while paused are not buffered
                await asyncio.sleep(0.05)
                continue
            self._produce_due(time.monotonic())
            if self._pending:
                continue
            await self._intents.wait_changed(self._next_wake() - time.monotonic())

    # ------------------------------------------------------------------ internals
    def _apply_fault(self, fault: Fault) -> NativePacket | None:
        if fault is Fault.LINK_DROP:
            self._open = False
            raise DeviceLinkError(f"{self.device_id}: simulated link drop")
        if fault is Fault.LINK_FAIL:
            self._open = False
            self._link_failed = True
            raise DeviceLinkError(f"{self.device_id}: simulated link failure")
        if fault is Fault.MALFORMED_PACKET:
            return NativePacket(self.malformed(self._clock_us()))
        self._regress_next = True  # TIMESTAMP_REGRESSION
        return None

    def _clock_us(self) -> int:
        us = int((time.monotonic() - self._clock_origin) * 1_000_000)
        if self._regress_next:
            self._regress_next = False
            us = max(0, us - REGRESSION_US)
        return us

    def _reset_schedule(self, now: float) -> None:
        for s in self._streams:
            s.next_due = now + s.period_s

    def _produce_due(self, now: float) -> None:
        for intent in self._intents.drain_discrete():
            self._delayed.append((now + self.DISCRETE_LATENCY_S, intent))
        if self._delayed:
            ready = [d for d in self._delayed if d[0] <= now]
            self._delayed = [d for d in self._delayed if d[0] > now]
            for _, intent in ready:
                data = self.encode_discrete(intent, self._clock_us())
                if data is None:
                    log.info("%s: dropped unsupported intent %s", self.device_id, intent.kind)
                else:
                    self._pending.append(NativePacket(data))
        for s in self._streams:
            if s.next_due > now:
                continue
            if now - s.next_due > MAX_CATCHUP_PERIODS * s.period_s:
                s.next_due = now  # stalled (e.g. debugger); resync instead of bursting
            while s.next_due <= now:
                for data in self.produce(s.name, self._clock_us()):
                    self._pending.append(NativePacket(data))
                s.next_due += s.period_s

    def _next_wake(self) -> float:
        dues = [s.next_due for s in self._streams]
        dues.extend(d[0] for d in self._delayed)
        return min(dues)
