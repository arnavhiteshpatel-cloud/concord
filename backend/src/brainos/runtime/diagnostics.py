"""Runtime diagnostics. Every number here is measured in-process; nothing is estimated."""

from __future__ import annotations

import os
import platform
import sys
import time
from collections import Counter, deque

from pydantic import BaseModel

from brainos.contracts.protocol import ConnectedApp

RATE_WINDOW_S = 5.0
LATENCY_WINDOW = 4096


class LatencySummary(BaseModel):
    count: int
    p50_us: float | None
    p95_us: float | None
    p99_us: float | None
    max_us: float | None


class EventTypeStats(BaseModel):
    event_type: str
    total: int
    rate_hz: float


class SwitchRecord(BaseModel):
    from_device: str | None
    to_device: str
    duration_ms: float
    at_ns: int


class ErrorRecord(BaseModel):
    at_ns: int
    kind: str
    device_id: str | None
    message: str


class Counters(BaseModel):
    events_published: int
    decode_errors: int
    validation_errors: int
    undeclared_capability: int
    timestamp_regressions: int
    discarded_while_paused: int
    link_errors: int
    reconnect_attempts: int
    reconnect_successes: int
    subscriber_drops: int


class DiagnosticsSnapshot(BaseModel):
    uptime_s: float
    measured_at_ns: int
    counters: Counters
    event_types: list[EventTypeStats]
    pipeline_latency: LatencySummary
    delivery_latency: LatencySummary
    switches: list[SwitchRecord]
    recent_errors: list[ErrorRecord]
    apps: list[ConnectedApp]
    process: dict[str, str]


class _RollingRate:
    __slots__ = ("_times",)

    def __init__(self) -> None:
        self._times: deque[float] = deque()

    def hit(self, now: float) -> None:
        self._times.append(now)
        self._prune(now)

    def _prune(self, now: float) -> None:
        cutoff = now - RATE_WINDOW_S
        while self._times and self._times[0] < cutoff:
            self._times.popleft()

    def rate(self, now: float, since: float) -> float:
        self._prune(now)
        window = min(RATE_WINDOW_S, max(now - since, 1e-9))
        return len(self._times) / window


def _summarize(samples: deque[float]) -> LatencySummary:
    if not samples:
        return LatencySummary(count=0, p50_us=None, p95_us=None, p99_us=None, max_us=None)
    s = sorted(samples)
    n = len(s)

    def pct(p: float) -> float:
        return round(s[min(n - 1, int(p * (n - 1) + 0.5))], 1)

    return LatencySummary(
        count=n, p50_us=pct(0.5), p95_us=pct(0.95), p99_us=pct(0.99), max_us=round(s[-1], 1)
    )


class Diagnostics:
    def __init__(self) -> None:
        self.started_monotonic = time.monotonic()
        self._rate_origin = self.started_monotonic
        self.totals: Counter[str] = Counter()
        self._rates: dict[str, _RollingRate] = {}
        self.events_published = 0
        self.decode_errors = 0
        self.validation_errors = 0
        self.undeclared_capability = 0
        self.timestamp_regressions = 0
        self.discarded_while_paused = 0
        self.link_errors = 0
        self.reconnect_attempts = 0
        self.reconnect_successes = 0
        self._pipeline_us: deque[float] = deque(maxlen=LATENCY_WINDOW)
        self._delivery_us: deque[float] = deque(maxlen=LATENCY_WINDOW)
        self._switches: deque[SwitchRecord] = deque(maxlen=20)
        self._errors: deque[ErrorRecord] = deque(maxlen=50)

    def reset_rates(self) -> None:
        """Called on connect so rates reflect the current device only."""
        self._rates.clear()
        self._rate_origin = time.monotonic()

    def record_event(self, event_type: str, pipeline_ns: int) -> None:
        now = time.monotonic()
        self.events_published += 1
        self.totals[event_type] += 1
        rate = self._rates.get(event_type)
        if rate is None:
            rate = self._rates[event_type] = _RollingRate()
        rate.hit(now)
        self._pipeline_us.append(pipeline_ns / 1000)

    def record_delivery(self, queued_ns: int) -> None:
        self._delivery_us.append(queued_ns / 1000)

    def record_switch(self, from_device: str | None, to_device: str, duration_ms: float) -> None:
        self._switches.append(
            SwitchRecord(
                from_device=from_device,
                to_device=to_device,
                duration_ms=round(duration_ms, 2),
                at_ns=time.time_ns(),
            )
        )

    def record_error(self, kind: str, device_id: str | None, message: str) -> None:
        self._errors.append(
            ErrorRecord(at_ns=time.time_ns(), kind=kind, device_id=device_id, message=message[:500])
        )

    def snapshot(self, apps: list[ConnectedApp]) -> DiagnosticsSnapshot:
        now = time.monotonic()
        return DiagnosticsSnapshot(
            uptime_s=round(now - self.started_monotonic, 3),
            measured_at_ns=time.time_ns(),
            counters=Counters(
                events_published=self.events_published,
                decode_errors=self.decode_errors,
                validation_errors=self.validation_errors,
                undeclared_capability=self.undeclared_capability,
                timestamp_regressions=self.timestamp_regressions,
                discarded_while_paused=self.discarded_while_paused,
                link_errors=self.link_errors,
                reconnect_attempts=self.reconnect_attempts,
                reconnect_successes=self.reconnect_successes,
                subscriber_drops=sum(a.dropped for a in apps),
            ),
            event_types=[
                EventTypeStats(
                    event_type=t,
                    total=self.totals[t],
                    rate_hz=round(self._rates[t].rate(now, self._rate_origin), 2)
                    if t in self._rates
                    else 0.0,
                )
                for t in sorted(self.totals)
            ],
            pipeline_latency=_summarize(self._pipeline_us),
            delivery_latency=_summarize(self._delivery_us),
            switches=list(self._switches),
            recent_errors=list(self._errors),
            apps=apps,
            process={
                "python": sys.version.split()[0],
                "platform": platform.platform(),
                "machine": platform.machine(),
                "pid": str(os.getpid()),
            },
        )
