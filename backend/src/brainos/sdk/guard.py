"""Command-safety helpers for applications that act on commands.

:class:`CommandGuard` is a small, pure state machine an application feeds every stream item
(``guard.handle(item)``) and ticks periodically (``guard.tick()``). It

* tracks, per command capability (``pointer_intent``, ``selection``, ``text_intent``,
  ``navigation``), whether the app may act on it now: granted by negotiation **and** the
  source is streaming **and** the stream is open **and**, when the app was granted
  ``control_status`` (schema 1.4), the runtime's latest ``control.state`` for this session
  says that capability is active. ``waiting_for_authorization`` lists capabilities the
  runtime withholds until the operator authorizes this app (reason ``not_authorized``);
* drops stale commands: older than ``max_age_ms`` by the envelope's runtime timestamp vs the
  local wall clock (``compare_wall_clock``; turn off when the runtime runs on another
  machine), or delayed more than ``max_age_ms`` relative to the fastest delivery seen
  (arrival-time minus timestamp, which needs no clock agreement and catches commands that
  were held up and then arrive in a burst);
* dead-man: if no pointer command arrives for ``deadman_ms``, the velocity it reports is zero
  (``on_deadman`` is called once per idle period);
* calls ``on_stop(reason)`` immediately when a previously usable command capability stops
  being usable: revoked authorization, command output stopped, app suspended, source paused,
  disconnected or switched, a ``control.state`` with ``active: false`` (its reason), or the
  stream closed. The velocity is zeroed at the same time.

:class:`ControlChannel` wraps an :class:`~brainos.sdk.client.EventStream` with a guard and
runs the dead-man timer for you. Neither talks to the runtime: authorization is an operator
decision, never something an application can request or grant itself.
"""

from __future__ import annotations

import asyncio
import contextlib
import time
from collections.abc import AsyncIterator, Callable, Iterable
from dataclasses import dataclass

from brainos.contracts.events import EventEnvelope
from brainos.contracts.protocol import AppStatus, NegotiationResult, RejectionReason
from brainos.sdk.client import (
    EventStream,
    NegotiationUpdate,
    RuntimeUpdate,
    StreamClosedError,
    StreamItem,
    is_event,
)

COMMAND_EVENT_CAPABILITY = {
    "intent.pointer": "pointer_intent",
    "intent.selection": "selection",
    "intent.text": "text_intent",
    "intent.navigate": "navigation",  # schema 1.4
}
CONTROL_STATE_EVENT = "control.state"
COMMAND_CAPABILITY_NAMES = tuple(dict.fromkeys(COMMAND_EVENT_CAPABILITY.values()))
DEFAULT_MAX_AGE_MS = 500.0
DEFAULT_DEADMAN_MS = 500.0


@dataclass
class GuardStats:
    accepted: int = 0
    dropped_inactive: int = 0  # command for a capability the app may not act on now
    dropped_stale: int = 0  # older than max_age_ms by the wall clock
    dropped_late: int = 0  # delivered > max_age_ms later than the fastest delivery seen
    stops: int = 0
    deadman: int = 0


class CommandGuard:
    def __init__(
        self,
        capabilities: Iterable[str] = COMMAND_CAPABILITY_NAMES,
        *,
        max_age_ms: float = DEFAULT_MAX_AGE_MS,
        deadman_ms: float = DEFAULT_DEADMAN_MS,
        compare_wall_clock: bool = True,
        on_stop: Callable[[str], None] | None = None,
        on_deadman: Callable[[], None] | None = None,
        wall_clock_ns: Callable[[], int] = time.time_ns,
        monotonic_ns: Callable[[], int] = time.monotonic_ns,
    ) -> None:
        caps = list(dict.fromkeys(capabilities))
        unknown = [c for c in caps if c not in COMMAND_CAPABILITY_NAMES]
        if unknown:
            raise ValueError(f"not command capabilities: {unknown}")
        if max_age_ms <= 0 or deadman_ms <= 0:
            raise ValueError("max_age_ms and deadman_ms must be positive")
        self.capabilities = caps
        self.max_age_ms, self.deadman_ms = max_age_ms, deadman_ms
        self.compare_wall_clock = compare_wall_clock
        self.on_stop, self.on_deadman = on_stop, on_deadman
        self._wall, self._mono = wall_clock_ns, monotonic_ns
        self.stats = GuardStats()
        # capability -> why it is not usable ("" when granted by negotiation)
        self._negotiated: dict[str, str] = dict.fromkeys(caps, "connecting")
        self._source: str = "unknown"  # runtime state; "unknown" until the first snapshot
        self._session: str | None = None
        self._closed = False
        self._active: frozenset[str] = frozenset()
        self.stop_reason: str | None = None
        self._min_offset_ns: int | None = None
        self._last_pointer_ns: int | None = None
        self._velocity = (0.0, 0.0)
        self._idle = True
        # schema 1.4: True while negotiation grants control_status (then control.state rules)
        self._control_required = False
        # latest control.state: (session id, active, capabilities, reason)
        self._control: tuple[str, bool, frozenset[str], str] | None = None

    # ------------------------------------------------------------------ state
    def is_active(self, capability: str) -> bool:
        return capability in self._active

    @property
    def active(self) -> frozenset[str]:
        return self._active

    def state(self, capability: str) -> str:
        """``active`` or why not: ``not_authorized``, ``unavailable``, ``no_device``,
        ``suspended``, ``source_<state>``, ``closed``, ``connecting``, ``not_requested``,
        ``control_inactive`` (the runtime's control.state says so; see ``control_state``)."""
        if capability not in self._negotiated:
            return "not_requested"
        if capability in self._active:
            return "active"
        if self._closed:
            return "closed"
        why = self._negotiated[capability]
        if why:
            return why
        if self._source not in ("streaming", "unknown"):
            return f"source_{self._source}"
        return "control_inactive"

    @property
    def control_state(self) -> tuple[bool, frozenset[str], str] | None:
        """The runtime's latest control.state for this session: (active, capabilities,
        reason), or None if none was received (or the app did not ask for control_status)."""
        c = self._control
        if c is None or (self._session is not None and c[0] != self._session):
            return None
        return c[1], c[2], c[3]

    @property
    def waiting_for_authorization(self) -> list[str]:
        return [c for c in self.capabilities if self._negotiated[c] == "not_authorized"]

    @property
    def velocity(self) -> tuple[float, float]:
        """Current pointer velocity: the last fresh command, or zero (dead-man / stopped)."""
        if "pointer_intent" in self._active and not self._idle:
            return self._velocity
        return (0.0, 0.0)

    # ------------------------------------------------------------------ inputs
    def handle(self, item: StreamItem) -> EventEnvelope | None:
        """Feed any stream item. Returns the event if the app should process it (fresh,
        usable commands and every non-command event); None otherwise."""
        if isinstance(item, NegotiationUpdate):
            self.on_negotiation(item.negotiation)
            return None
        if isinstance(item, RuntimeUpdate):
            self.on_runtime(item.runtime.state.value, item.runtime.session_id)
            return None
        if is_event(item):
            if item.event_type.value == CONTROL_STATE_EVENT:
                self.on_control_state(item)
                return item  # the app may show it; it is never a command
            if item.event_type.value not in COMMAND_EVENT_CAPABILITY:
                return item
            return item if self.accept(item) else None
        return None

    def on_negotiation(self, n: NegotiationResult) -> None:
        rejected = {r.capability.value: r.reason for r in n.rejected}
        granted = {c.value for c in n.granted}
        for cap in self.capabilities:
            if cap in granted:
                self._negotiated[cap] = ""
            elif cap in rejected:
                reason = rejected[cap]
                self._negotiated[cap] = (
                    "not_authorized"
                    if reason is RejectionReason.NOT_AUTHORIZED
                    else "no_device"
                    if reason is RejectionReason.NO_DEVICE
                    else "unavailable"
                )
            elif n.status is AppStatus.NO_DEVICE:
                self._negotiated[cap] = "no_device"
            else:  # not rejected but not granted: the app is suspended for another capability
                self._negotiated[cap] = "suspended"
        self._control_required = "control_status" in granted
        self._update()

    def on_control_state(self, env: EventEnvelope) -> None:
        """Feed a ``control.state`` event (schema 1.4). ``active: false`` stops at once."""
        if env.event_type.value != CONTROL_STATE_EVENT:
            return
        p = env.payload
        active = bool(p.active)  # type: ignore[union-attr]
        caps = frozenset(str(c) for c in p.capabilities)  # type: ignore[union-attr]
        reason = str(p.reason)  # type: ignore[union-attr]
        if self._session is None:
            self._session = env.session_id
        self._control = (env.session_id, active, caps if active else frozenset(), reason)
        self._update(None if active else reason or "command output inactive")

    def on_runtime(self, state: str, session_id: str | None) -> None:
        if session_id != self._session:
            self._session = session_id
            self._min_offset_ns = None  # a new source: forget its delivery baseline
            self._last_pointer_ns = None
        self._source = state
        self._update()

    def on_closed(self, reason: str = "stream closed") -> None:
        self._closed = True
        self._update(reason)

    def accept(self, env: EventEnvelope) -> bool:
        cap = COMMAND_EVENT_CAPABILITY.get(env.event_type.value)
        if cap is None:
            return False
        if cap not in self._active:
            self.stats.dropped_inactive += 1
            return False
        now_mono = self._mono()
        if self.compare_wall_clock and (self._wall() - env.timestamp_ns) / 1e6 > self.max_age_ms:
            self.stats.dropped_stale += 1
            return False
        offset = now_mono - env.timestamp_ns
        if self._min_offset_ns is None or offset < self._min_offset_ns:
            self._min_offset_ns = offset
        if (offset - self._min_offset_ns) / 1e6 > self.max_age_ms:
            self.stats.dropped_late += 1
            return False
        self.stats.accepted += 1
        if cap == "pointer_intent":
            p = env.payload
            self._velocity = (float(p.vx), float(p.vy))  # type: ignore[union-attr]
            self._last_pointer_ns = now_mono
            self._idle = False
        return True

    def tick(self) -> bool:
        """Dead-man check; call every few tens of ms. Returns True when it just fired."""
        if self._idle or self._last_pointer_ns is None:
            return False
        if (self._mono() - self._last_pointer_ns) / 1e6 <= self.deadman_ms:
            return False
        self._idle = True
        self.stats.deadman += 1
        if self.on_deadman is not None:
            self.on_deadman()
        return True

    # ------------------------------------------------------------------ internals
    def _control_allows(self, cap: str) -> bool:
        if not self._control_required:
            return True
        c = self._control
        return c is not None and c[0] == self._session and c[1] and cap in c[2]

    def _update(self, reason: str | None = None) -> None:
        streaming = self._source in ("streaming", "unknown")
        new = frozenset(
            c
            for c in self.capabilities
            if not self._closed
            and streaming
            and self._negotiated[c] == ""
            and self._control_allows(c)
        )
        lost = self._active - new
        self._active = new
        if lost:
            cap = sorted(lost)[0]
            why = reason or self._why(cap)
            self.stop_reason = why
            self.stats.stops += 1
            self._velocity = (0.0, 0.0)
            self._idle = True
            self._last_pointer_ns = None
            if self.on_stop is not None:
                self.on_stop(why)
        elif new:
            self.stop_reason = None

    def _why(self, cap: str) -> str:
        n = self._negotiated[cap]
        if n == "not_authorized":
            return "authorization revoked"
        if n == "unavailable":
            return "command output stopped"
        if n == "no_device":
            return "source disconnected"
        if n == "suspended":
            return "application suspended"
        if self._source not in ("streaming", "unknown"):
            return f"source {self._source}"
        c = self._control
        if self._control_required and c is not None and c[0] == self._session and c[3]:
            return c[3]
        return "command output inactive"


class ControlChannel:
    """An event stream seen through a :class:`CommandGuard`, with the dead-man timer running.

    ``async for item in ControlChannel(stream, guard)`` yields negotiation/runtime updates and
    notices unchanged, every non-command event, and only fresh, usable command events. When
    the stream ends (or fails) the guard's ``on_stop`` fires with ``stream closed``.
    """

    def __init__(self, stream: EventStream, guard: CommandGuard, *, tick_s: float = 0.02) -> None:
        self.stream, self.guard, self.tick_s = stream, guard, tick_s
        guard.on_negotiation(stream.negotiation)
        guard.on_runtime(stream.runtime.state.value, stream.runtime.session_id)

    async def _ticker(self) -> None:
        while True:
            await asyncio.sleep(self.tick_s)
            self.guard.tick()

    def __aiter__(self) -> AsyncIterator[StreamItem]:
        return self._iterate()

    async def _iterate(self) -> AsyncIterator[StreamItem]:
        ticker = asyncio.create_task(self._ticker())
        reason = "stream closed"
        try:
            async for item in self.stream:
                out = self.guard.handle(item)
                if is_event(item):
                    if out is not None:
                        yield out
                else:
                    yield item
        except StreamClosedError as exc:
            reason = f"stream closed: {exc.message}"
            raise
        finally:
            ticker.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await ticker
            self.guard.on_closed(reason)
