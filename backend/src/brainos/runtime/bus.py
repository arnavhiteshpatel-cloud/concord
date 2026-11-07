"""Event bus: fan-out of validated envelopes to subscribers with bounded queues.

* Events are delivered only for capabilities granted to the subscriber.
* Each subscriber has a bounded event queue. On overflow the *oldest* event is
  dropped and counted. ``delivery_seq`` is assigned at enqueue time, so drops
  are visible to clients as gaps.
* Control messages (negotiation, runtime snapshot) use a separate queue and are
  never dropped.
* Decoded commands (``decoded_intent`` on a command capability) are delivered only to
  subscribers whose application the operator authorized for that capability, even if
  negotiation granted the capability (defense in depth; see runtime/control.py). When
  command output stops or an authorization is revoked, decoded commands still waiting in a
  subscriber queue are withdrawn (``purge_commands``) so no stale command is sent later.
* JSON is produced lazily and once per envelope (M5-E): an envelope is serialized only when
  a subscriber actually sends it or a tap needs the text, and the text is shared by every
  subscriber. Frames dropped from a slow subscriber's queue are never serialized.
* Event queues are also bounded in (estimated) bytes (M5-E): at high channel counts a
  count bound alone lets a stalled client pin gigabytes of raw frames.
"""

from __future__ import annotations

import asyncio
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field

from brainos.contracts.capabilities import Capability
from brainos.contracts.events import EventEnvelope
from brainos.contracts.protocol import AppInfo, ConnectedApp, NegotiationResult
from brainos.runtime.control import is_decoded_command
from brainos.runtime.fastjson import envelope_json

DEFAULT_QUEUE_SIZE = 2048
DEFAULT_QUEUE_BYTES = 64 * 1024 * 1024  # per subscriber; ~26 frames of 1024 ch x 300 samples
SMALL_EVENT_BYTES = 512  # size estimate for an event without a sample array
MAX_CONTROL_QUEUE = 256  # a client this far behind on control messages is disconnected


class SubscriberOverflowError(Exception):
    """The subscriber stopped reading; its control queue overflowed."""


Tap = Callable[[EventEnvelope, str], None]


class EventJson:
    """One published envelope and its JSON text, computed on first use and then shared."""

    __slots__ = ("_text", "envelope", "nbytes")

    def __init__(self, envelope: EventEnvelope | None, text: str | None = None) -> None:
        self.envelope = envelope
        self._text = text
        samples = getattr(envelope.payload, "samples", None) if envelope is not None else None
        nbytes = getattr(samples, "nbytes", None)
        self.nbytes: int = (
            int(nbytes)
            if nbytes is not None
            else (len(text) if text is not None else SMALL_EVENT_BYTES)
        )

    @property
    def text(self) -> str:
        if self._text is None:
            assert self.envelope is not None
            self._text = envelope_json(self.envelope)
        return self._text


@dataclass(slots=True)
class Subscriber:
    connection_id: str
    app: AppInfo
    required: list[Capability]
    optional: list[Capability]
    negotiation: NegotiationResult
    max_queue: int = DEFAULT_QUEUE_SIZE
    max_queue_bytes: int = DEFAULT_QUEUE_BYTES
    connected_at_ns: int = field(default_factory=time.time_ns)
    delivered: int = 0
    dropped: int = 0
    _next_delivery_seq: int = 0
    _queued_bytes: int = 0
    # (delivery_seq, event, enqueue monotonic ns, decoded-command capability or None)
    _events: deque[tuple[int, EventJson, int, Capability | None]] = field(default_factory=deque)
    _control: deque[str] = field(default_factory=deque)
    _wake: asyncio.Event = field(default_factory=asyncio.Event)
    allowed: frozenset[Capability] = frozenset()
    # command capabilities the operator authorized this subscriber's app id for
    authorized: frozenset[Capability] = frozenset()
    refused_commands: int = 0  # decoded commands not delivered: app not authorized
    purged_commands: int = 0  # queued decoded commands withdrawn after stop / revocation
    control_overflow: bool = False

    def __post_init__(self) -> None:
        self.allowed = frozenset(self.negotiation.granted)

    def set_negotiation(self, negotiation: NegotiationResult) -> None:
        self.negotiation = negotiation
        self.allowed = frozenset(negotiation.granted)

    def offer_event(self, event: EventJson | str, command: Capability | None = None) -> None:
        if isinstance(event, str):
            event = EventJson(None, event)
        if not self._events:
            self._queued_bytes = 0  # self-healing if a caller emptied the deque directly
        # count bound, then byte bound (the newest event is always kept)
        while self._events and (
            len(self._events) >= self.max_queue
            or self._queued_bytes + event.nbytes > self.max_queue_bytes
        ):
            self._queued_bytes -= self._events.popleft()[1].nbytes
            self.dropped += 1
        self._events.append((self._next_delivery_seq, event, time.monotonic_ns(), command))
        self._queued_bytes += event.nbytes
        self._next_delivery_seq += 1
        self._wake.set()

    def purge_commands(self, capabilities: frozenset[Capability] | None = None) -> int:
        """Withdraw queued (not yet sent) decoded commands, optionally only for some
        capabilities. The remaining queue is renumbered so ``delivery_seq`` stays contiguous
        from the client's point of view (withdrawn commands were never sent)."""
        if not self._events:
            return 0
        keep = [
            e
            for e in self._events
            if e[3] is None or (capabilities is not None and e[3] not in capabilities)
        ]
        removed = len(self._events) - len(keep)
        if removed:
            base = self._events[0][0]
            self._events = deque((base + i, ev, t, cmd) for i, (_, ev, t, cmd) in enumerate(keep))
            self._queued_bytes = sum(e[1].nbytes for e in self._events)
            self._next_delivery_seq = base + len(keep)
            self.purged_commands += removed
        return removed

    def offer_control(self, message_json: str) -> None:
        if len(self._control) >= MAX_CONTROL_QUEUE:
            self.control_overflow = True  # never grow without bound; transport disconnects
        else:
            self._control.append(message_json)
        self._wake.set()

    @property
    def queue_depth(self) -> int:
        return len(self._events)

    async def next_message(self) -> tuple[str, int | None]:
        """Return (frame_json, enqueue_monotonic_ns or None for control)."""
        while True:
            if self.control_overflow:
                raise SubscriberOverflowError(self.connection_id)
            if self._control:
                return self._control.popleft(), None
            if self._events:
                dseq, ev, t_enq, _ = self._events.popleft()
                self._queued_bytes -= ev.nbytes
                self.delivered += 1
                return f'{{"type":"event","delivery_seq":{dseq},"event":{ev.text}}}', t_enq
            self._wake.clear()
            await self._wake.wait()

    def info(self) -> ConnectedApp:
        return ConnectedApp(
            connection_id=self.connection_id,
            app=self.app,
            negotiation=self.negotiation,
            connected_at_ns=self.connected_at_ns,
            delivered=self.delivered,
            dropped=self.dropped,
            queue_depth=self.queue_depth,
        )


@dataclass(frozen=True, slots=True)
class _TapEntry:
    tap: Tap
    json: bool
    when: Callable[[EventEnvelope], bool] | None


class EventBus:
    def __init__(self) -> None:
        self._subs: dict[str, Subscriber] = {}
        self._taps: list[_TapEntry] = []

    @property
    def subscribers(self) -> list[Subscriber]:
        return list(self._subs.values())

    def add(self, sub: Subscriber) -> None:
        self._subs[sub.connection_id] = sub

    def remove(self, connection_id: str) -> Subscriber | None:
        return self._subs.pop(connection_id, None)

    def get(self, connection_id: str) -> Subscriber | None:
        return self._subs.get(connection_id)

    def add_tap(
        self,
        tap: Tap,
        *,
        json: bool = True,
        when: Callable[[EventEnvelope], bool] | None = None,
    ) -> None:
        """Call ``tap(envelope, event_json)`` for every published envelope.

        ``json=False``: the tap never reads the text; it receives ``""`` and publishing does
        not serialize for it. ``when``: the tap is called only for envelopes it accepts
        (the text is then produced only for those)."""
        self._taps.append(_TapEntry(tap, json, when))

    def publish(
        self, envelope: EventEnvelope, capability: Capability, event_json: str | None = None
    ) -> None:
        """Fan out ``envelope``. ``event_json`` may be given if already serialized; otherwise
        the text is produced on first use (send or tap) and shared."""
        event = EventJson(envelope, event_json)
        command = capability if is_decoded_command(envelope, capability) else None
        for sub in self._subs.values():
            if capability not in sub.allowed:
                continue
            if command is not None and command not in sub.authorized:
                sub.refused_commands += 1  # granted by negotiation but not authorized
                continue
            sub.offer_event(event, command)
        for t in self._taps:
            if t.when is not None and not t.when(envelope):
                continue
            t.tap(envelope, event.text if t.json else "")

    def purge_commands(self, capabilities: frozenset[Capability] | None = None) -> int:
        return sum(s.purge_commands(capabilities) for s in self._subs.values())

    def broadcast_control(self, message_json: str) -> None:
        for sub in self._subs.values():
            sub.offer_control(message_json)
