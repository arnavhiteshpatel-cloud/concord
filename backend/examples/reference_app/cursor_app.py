"""Concord reference application: a center-out cursor task driven by pointer commands.

Uses ONLY the public Python SDK (``concord.sdk``) and the standard library. It knows nothing
about devices, adapters, decoders or datasets: it declares that it *requires*
``pointer_intent`` and reacts to whatever the runtime grants.

* When no connected source can provide pointer commands (e.g. a raw stream without a decoder
  and router), the runtime suspends the app. It does not move, and it never derives commands
  from raw signals or features itself.
* Decoded commands additionally need the operator's authorization of this app
  (``reference-cursor``) in the console: until then the runtime withholds them
  (negotiation reason ``not_authorized``) and the app says it is waiting for that.
* A :class:`~concord.sdk.CommandGuard` decides which commands to act on: none while the app
  is not authorized / the source is not streaming / the stream is closed; none older than
  500 ms; and the cursor stops (zero velocity) after 500 ms without a pointer command.
* When commands arrive, it shows where they come from (provenance): simulated intent from a
  simulator, or decoded intent from a named model, and whether the underlying data is
  prerecorded or synthetic.

Run against a running Concord (``make run``)::

    python backend/examples/reference_app/cursor_app.py --url http://127.0.0.1:8000 --seconds 30

This is a research demo, not an assistive or clinical interface.
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import json
import math
import sys
from dataclasses import dataclass, field
from typing import Any

from concord.sdk import (
    CommandGuard,
    ConcordError,
    EventStream,
    NegotiationUpdate,
    RuntimeUpdate,
    StreamItem,
    is_event,
)

APP_ID = "reference-cursor"
TARGET_RADIUS = 0.15
DWELL_S = 0.3
MAX_DT_S = 0.1  # a longer pause between commands does not teleport the cursor
TICK_S = 0.02
TARGETS = [
    (0.7 * math.cos(2 * math.pi * k / 8), 0.7 * math.sin(2 * math.pi * k / 8)) for k in range(8)
]


@dataclass
class SourceSeen:
    device_id: str
    kind: str  # provenance kind of the commands: simulated_intent | decoded_intent
    model_id: str | None
    prerecorded: bool
    synthetic: bool
    commands: int = 0

    @property
    def label(self) -> str:
        what = (
            f"decoded by model {self.model_id}"
            if self.kind == "decoded_intent"
            else "simulated intent"
        )
        tags = [
            t
            for t, on in (("prerecorded data", self.prerecorded), ("synthetic", self.synthetic))
            if on
        ]
        return f"{self.device_id}: {what}" + (f" ({', '.join(tags)})" if tags else "")


@dataclass
class CursorApp:
    """Pure state machine; feed it SDK stream items with :meth:`handle`."""

    status: str = "connecting"  # negotiation status: active | suspended | no_device
    x: float = 0.0
    y: float = 0.0
    target: int = 0
    acquired: int = 0
    commands: int = 0
    ignored: int = 0  # events not acted on (not commands, or refused by the guard)
    sources: dict[tuple[str, str, str | None], SourceSeen] = field(default_factory=dict)
    device_id: str | None = None
    stops: list[str] = field(default_factory=list)  # why command input stopped, in order
    control: str | None = None  # the runtime's last control.state (schema 1.4), as text
    guard: CommandGuard = field(init=False)
    _last_ts: int | None = None
    _dwell_s: float = 0.0
    _reaching_center: bool = True

    def __post_init__(self) -> None:
        self.guard = CommandGuard(["pointer_intent"], on_stop=self._stopped)

    def _stopped(self, reason: str) -> None:
        self.stops.append(reason)
        self._last_ts = None  # never integrate across a stop

    @property
    def waiting_for_authorization(self) -> bool:
        return "pointer_intent" in self.guard.waiting_for_authorization

    def handle(self, item: StreamItem) -> None:
        if isinstance(item, NegotiationUpdate):
            self.status = item.negotiation.status.value
            if self.status != "active":
                self._last_ts = None  # do not integrate across a suspension
        elif isinstance(item, RuntimeUpdate):
            dev = item.runtime.device
            if (dev.device_id if dev else None) != self.device_id:
                self.device_id = dev.device_id if dev else None
                self._last_ts = None
        env = self.guard.handle(item)
        if is_event(item) and item.event_type.value == "control.state":
            p = item.payload
            self.control = f"{'active' if p.active else 'inactive'}: {p.reason}"  # type: ignore[union-attr]
            if not p.active:  # type: ignore[union-attr]
                self._last_ts = None  # never integrate across a stop
            return
        if is_event(item):
            if env is None or env.event_type.value != "intent.pointer" or self.status != "active":
                self.ignored += 1
                return
            self._command(env)

    def _command(self, env: Any) -> None:
        p = env.provenance
        key = (env.device_id, p.kind.value, p.model_id)
        src = self.sources.get(key)
        if src is None:
            src = self.sources[key] = SourceSeen(
                env.device_id, p.kind.value, p.model_id, bool(p.replayed), bool(p.synthetic)
            )
        src.commands += 1
        self.commands += 1
        ts = env.device_timestamp_ns or env.timestamp_ns
        dt = 0.0 if self._last_ts is None else min(MAX_DT_S, max(0.0, (ts - self._last_ts) / 1e9))
        self._last_ts = ts
        vx, vy = self.guard.velocity
        self.x = max(-1.0, min(1.0, self.x + vx * dt))
        self.y = max(-1.0, min(1.0, self.y + vy * dt))
        tx, ty = (0.0, 0.0) if self._reaching_center else TARGETS[self.target]
        if math.hypot(self.x - tx, self.y - ty) <= TARGET_RADIUS:
            self._dwell_s += dt
            if self._dwell_s >= DWELL_S:
                if not self._reaching_center:
                    self.acquired += 1
                    self.target = (self.target + 1) % len(TARGETS)
                self._reaching_center = not self._reaching_center
                self._dwell_s = 0.0
        else:
            self._dwell_s = 0.0

    def summary(self) -> dict[str, Any]:
        g = self.guard.stats
        return {
            "status": self.status,
            "device_id": self.device_id,
            "cursor": [round(self.x, 3), round(self.y, 3)],
            "commands": self.commands,
            "ignored_events": self.ignored,
            "dropped_stale": g.dropped_stale + g.dropped_late,
            "deadman_stops": g.deadman,
            "stops": self.stops,
            "control": self.control,
            "targets_acquired": self.acquired,
            "sources": [s.label + f" — {s.commands} commands" for s in self.sources.values()],
        }

    def line(self) -> str:
        if self.waiting_for_authorization:
            return (
                f"[{self.status}] waiting for operator authorization: commands are available "
                f"but the operator has not authorized '{APP_ID}' to receive them"
            )
        if self.status != "active":
            return f"[{self.status}] waiting: no source currently provides pointer commands"
        if not self.guard.is_active("pointer_intent") and self.control:
            return f"[{self.status}] stopped (runtime: {self.control})"
        src = next(reversed(self.sources.values()), None)
        where = src.label if src else "no commands yet"
        vx, vy = self.guard.velocity
        moving = "moving" if (vx, vy) != (0.0, 0.0) else "still"
        return (
            f"[active] cursor ({self.x:+.2f}, {self.y:+.2f}) {moving}, "
            f"acquired {self.acquired} | {where}"
        )


async def run(app: CursorApp, base_url: str, stop: asyncio.Event) -> CursorApp:
    """Consume the event stream until ``stop`` is set."""
    async with await EventStream.connect(
        app_id=APP_ID,
        app_name="Reference cursor app",
        required=["pointer_intent"],
        optional=["control_status"],
        base_url=base_url,
    ) as stream:
        app.status = stream.negotiation.status.value
        app.device_id = stream.runtime.device.device_id if stream.runtime.device else None
        app.handle(NegotiationUpdate(stream.negotiation))
        app.handle(RuntimeUpdate(stream.runtime))

        async def consume() -> None:
            async for item in stream:
                app.handle(item)

        async def tick() -> None:  # dead-man timer
            while True:
                await asyncio.sleep(TICK_S)
                app.guard.tick()

        tasks = [asyncio.create_task(consume()), asyncio.create_task(tick())]
        await stop.wait()
        for t in tasks:
            t.cancel()
        for t in tasks:
            with contextlib.suppress(asyncio.CancelledError, ConcordError):
                await t
    app.guard.on_closed()
    return app


async def _main(args: argparse.Namespace) -> int:
    app, stop = CursorApp(), asyncio.Event()
    runner = asyncio.create_task(run(app, args.url, stop))
    loop = asyncio.get_running_loop()
    deadline = loop.time() + args.seconds
    try:
        while loop.time() < deadline and not runner.done():
            await asyncio.sleep(1.0)
            print(app.line(), flush=True)
    finally:
        stop.set()
        try:
            await runner
        except (ConcordError, OSError) as exc:
            print(f"cannot reach Concord at {args.url}: {exc}", file=sys.stderr)
            return 1
    print(json.dumps(app.summary(), indent=2))
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--url", default="http://127.0.0.1:8000")
    ap.add_argument("--seconds", type=float, default=30.0)
    return asyncio.run(_main(ap.parse_args(argv)))


if __name__ == "__main__":
    raise SystemExit(main())
