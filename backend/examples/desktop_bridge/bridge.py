"""Concord desktop control bridge — OPT-IN, OFF BY DEFAULT. Read SAFETY.md first.

A separate process that maps **authorized, decoded** pointer and selection commands from
Concord to operating-system pointer events (relative moves and a primary-button click)
through a pluggable backend (``dry-run``, ``xdotool``, ``pynput``). It is not one of the
reference applications and nothing else in Concord starts it.

It uses only the public Python SDK (``concord.sdk``), the standard library and its backends.
It never accepts raw signals, features, behavior labels or simulated intents: it acts only on
``intent.pointer`` / ``intent.selection`` events with provenance ``decoded_intent``, which
reach an application only after the operator authorized it in Concord (app id
``desktop-bridge``) and started command output.

Safety behaviour (details and limits in SAFETY.md):

* refuses to start without ``--enable``; refuses ``--focus`` with a backend that cannot tell
  which window has focus;
* every command passes the SDK ``CommandGuard``: nothing while not authorized / not streaming
  / the runtime's control.state is inactive; commands older than 500 ms are dropped; pointer
  velocity falls to zero 500 ms after the last pointer command (dead-man);
* bounded output: at most ``--rate-hz`` pointer moves per second, speed clamped to
  ``--max-speed``, at most one click per ``--click-interval-ms``;
* with ``--focus TEXT``: acts only while the focused window's title contains TEXT;
* stops at once on control.state inactive, revocation, command output stopped, disconnect;
  exits on Ctrl-C, the backend's stop hotkey (pynput: Ctrl+Alt+B), or the stream closing.

    python backend/examples/desktop_bridge/bridge.py --url http://127.0.0.1:8000 \\
        --enable --backend xdotool --focus "Communication Board" --seconds 120

Research software: not an accessibility product, not validated with any person.
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import json
import math
import signal
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from backends import BackendError, PointerBackend, make_backend

from concord.sdk import (
    CommandGuard,
    ConcordError,
    EventStream,
    NegotiationUpdate,
    RuntimeUpdate,
    StreamItem,
    is_event,
)

APP_ID = "desktop-bridge"
MAX_DT_S = 0.1


class BridgeRefused(RuntimeError):
    """The bridge will not start with this configuration."""


@dataclass
class BridgeConfig:
    enable: bool = False
    pixels_per_unit: float = 800.0  # OS pixels per workspace unit
    max_speed: float = 1.0  # workspace units / s (vector magnitude clamp)
    rate_hz: float = 60.0  # at most this many OS pointer moves per second
    click_interval_ms: float = 500.0  # at most one click per this interval
    min_confidence: float = 0.0  # clicks below this selection confidence are ignored
    focus: str | None = None  # act only while the focused window title contains this

    def check(self) -> None:
        if not self.enable:
            raise BridgeRefused(
                "the desktop bridge is off by default: pass --enable after reading SAFETY.md"
            )
        if not (0 < self.pixels_per_unit <= 10_000 and 0 < self.max_speed <= 5):
            raise BridgeRefused("pixels-per-unit must be in (0, 10000], max-speed in (0, 5]")
        if not (1 <= self.rate_hz <= 240 and 100 <= self.click_interval_ms <= 10_000):
            raise BridgeRefused("rate-hz must be in [1, 240], click-interval-ms in [100, 10000]")
        if not 0 <= self.min_confidence <= 1:
            raise BridgeRefused("min-confidence must be in [0, 1]")


@dataclass
class BridgeStats:
    moves: int = 0
    clicks: int = 0
    refused_provenance: int = 0  # commands that were not decoded_intent (e.g. simulated)
    refused_focus: int = 0  # actions withheld: the focused window did not match
    refused_click_rate: int = 0
    refused_confidence: int = 0
    pauses: int = 0


@dataclass
class Bridge:
    """State machine: feed stream items with :meth:`handle`, call :meth:`tick` at ``rate_hz``."""

    config: BridgeConfig
    backend: PointerBackend
    clock: Callable[[], float] = time.monotonic
    stats: BridgeStats = field(default_factory=BridgeStats)
    log: list[str] = field(default_factory=list)
    stopped: str | None = None  # latched: hotkey, Ctrl-C, stream closed -> exit
    control: str | None = None  # the runtime's last control.state, as text
    guard: CommandGuard = field(init=False)
    _vel: tuple[float, float] = (0.0, 0.0)
    _acc: list[float] = field(default_factory=lambda: [0.0, 0.0])
    _last_tick: float | None = None
    _last_click: float | None = None

    def __post_init__(self) -> None:
        self.config.check()
        if self.config.focus and not self.backend.can_report_focus:
            raise BridgeRefused(
                f"--focus was requested but the {self.backend.name} backend cannot tell which "
                "window has focus; refusing to start"
            )
        self.guard = CommandGuard(["pointer_intent", "selection"], on_stop=self._paused)
        if self.backend.has_hotkey:
            with contextlib.suppress(BackendError):
                self.backend.start_hotkey(lambda: self.stop("stop hotkey"))

    # ------------------------------------------------------------------ control
    def _say(self, msg: str) -> None:
        self.log.append(msg)

    def _paused(self, reason: str) -> None:
        self.stats.pauses += 1
        self._vel, self._acc, self._last_tick = (0.0, 0.0), [0.0, 0.0], None
        self._say(f"stopped acting: {reason}")

    def stop(self, reason: str) -> None:
        """Latched stop: no OS event after this; the process exits."""
        if self.stopped is None:
            self.stopped = reason
            self._vel, self._acc = (0.0, 0.0), [0.0, 0.0]
            self._say(f"bridge stopped: {reason}")

    @property
    def waiting_for_authorization(self) -> list[str]:
        return self.guard.waiting_for_authorization

    def _focus_ok(self) -> bool:
        want = self.config.focus
        if not want:
            return True
        title = self.backend.focused_window()
        if title is None or want not in title:
            self.stats.refused_focus += 1
            return False
        return True

    # ------------------------------------------------------------------ input
    def handle(self, item: StreamItem) -> None:
        if self.stopped is not None:
            return
        env = self.guard.handle(item)
        if not is_event(item):
            return
        if item.event_type.value == "control.state":
            p = item.payload
            self.control = f"{'active' if p.active else 'inactive'}: {p.reason}"  # type: ignore[union-attr]
            return
        if env is None or env.event_type.value not in ("intent.pointer", "intent.selection"):
            return
        if env.provenance.kind.value != "decoded_intent":
            # simulated intents are not gated by operator authorization: never act on them
            self.stats.refused_provenance += 1
            if env.event_type.value == "intent.pointer":
                self._vel = (0.0, 0.0)
            return
        if env.event_type.value == "intent.pointer":
            p = env.payload
            self._vel = (float(p.vx), float(p.vy))  # type: ignore[union-attr]
        else:
            self._click(float(env.payload.confidence), str(env.payload.action))  # type: ignore[union-attr]

    def _click(self, confidence: float, action: str) -> None:
        if action not in ("primary", "activate"):
            return  # cancel has no OS meaning here
        if confidence < self.config.min_confidence:
            self.stats.refused_confidence += 1
            return
        now = self.clock()
        if self._last_click is not None and (now - self._last_click) * 1000 < (
            self.config.click_interval_ms
        ):
            self.stats.refused_click_rate += 1
            return
        if not self._focus_ok():
            return
        self._last_click = now
        self.backend.click()
        self.stats.clicks += 1

    def tick(self) -> None:
        """Move the OS pointer by velocity x elapsed time (at most once per call)."""
        now = self.clock()
        last, self._last_tick = self._last_tick, now
        if self.stopped is not None or not self.guard.is_active("pointer_intent"):
            self._acc = [0.0, 0.0]
            return
        vx, vy = self._vel if self.guard.velocity != (0.0, 0.0) else (0.0, 0.0)  # dead-man
        if last is None or (vx, vy) == (0.0, 0.0):
            return
        speed = math.hypot(vx, vy)
        if speed > self.config.max_speed:
            vx, vy = vx * self.config.max_speed / speed, vy * self.config.max_speed / speed
        dt = min(MAX_DT_S, max(0.0, now - last))
        self._acc[0] += vx * dt * self.config.pixels_per_unit
        self._acc[1] += vy * dt * self.config.pixels_per_unit
        dx, dy = round(self._acc[0]), round(self._acc[1])  # whole pixels; the rest carries over
        if (dx, dy) == (0, 0):
            return
        if not self._focus_ok():
            self._acc = [0.0, 0.0]  # motion withheld is dropped, never replayed later
            return
        self._acc[0] -= dx
        self._acc[1] -= dy
        self.backend.move_by(dx, dy)
        self.stats.moves += 1

    def summary(self) -> dict[str, Any]:
        return {
            "backend": self.backend.name,
            "stopped": self.stopped,
            "control": self.control,
            "waiting_for_authorization": self.waiting_for_authorization,
            "stats": self.stats.__dict__,
            "guard": self.guard.stats.__dict__,
            "log": self.log[-20:],
        }


async def run(bridge: Bridge, base_url: str, stop: asyncio.Event) -> Bridge:
    """Connect, act until ``stop`` is set or the bridge stops itself."""
    async with await EventStream.connect(
        app_id=APP_ID,
        app_name="Desktop control bridge",
        required=[],
        optional=["pointer_intent", "selection", "control_status"],
        base_url=base_url,
    ) as stream:
        bridge.handle(NegotiationUpdate(stream.negotiation))
        bridge.handle(RuntimeUpdate(stream.runtime))

        async def consume() -> None:
            try:
                async for item in stream:
                    bridge.handle(item)
            except ConcordError as exc:
                bridge.stop(f"stream closed: {exc.message}")
                raise
            bridge.stop("stream closed")

        async def ticker() -> None:
            period = 1.0 / bridge.config.rate_hz
            while bridge.stopped is None:
                bridge.tick()
                bridge.guard.tick()
                await asyncio.sleep(period)

        tasks = [asyncio.create_task(consume()), asyncio.create_task(ticker())]
        waiter = asyncio.create_task(stop.wait())
        await asyncio.wait([waiter, *tasks], return_when=asyncio.FIRST_COMPLETED)
        bridge.stop(bridge.stopped or "stop requested")
        for t in (*tasks, waiter):
            t.cancel()
        for t in (*tasks, waiter):
            with contextlib.suppress(asyncio.CancelledError, ConcordError):
                await t
    bridge.guard.on_closed()
    return bridge


async def _main(args: argparse.Namespace) -> int:
    cfg = BridgeConfig(
        enable=args.enable,
        pixels_per_unit=args.pixels_per_unit,
        max_speed=args.max_speed,
        rate_hz=args.rate_hz,
        click_interval_ms=args.click_interval_ms,
        min_confidence=args.min_confidence,
        focus=args.focus,
    )
    try:
        cfg.check()
        backend = make_backend(args.backend)
        bridge = Bridge(cfg, backend)
    except (BridgeRefused, BackendError) as exc:
        print(f"desktop bridge refused to start: {exc}", file=sys.stderr)
        return 2
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()

    def on_signal(name: str) -> None:
        bridge.stop(name)
        stop.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        with contextlib.suppress(NotImplementedError):  # not on Windows event loops
            loop.add_signal_handler(sig, on_signal, sig.name)
    loop.call_later(args.seconds, stop.set)
    print(
        f"desktop bridge on ({backend.name}); waiting for the operator to authorize "
        f"'{APP_ID}' in Concord. Stop: Ctrl-C"
        + (" or Ctrl+Alt+B" if backend.has_hotkey and backend.name == "pynput" else ""),
        flush=True,
    )
    try:
        await run(bridge, args.url, stop)
    except (ConcordError, OSError) as exc:
        print(f"cannot reach Concord at {args.url}: {exc}", file=sys.stderr)
        return 1
    finally:
        backend.close()
    print(json.dumps(bridge.summary(), indent=2))
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--url", default="http://127.0.0.1:8000")
    ap.add_argument("--enable", action="store_true", help="required: the bridge is off by default")
    ap.add_argument("--backend", default="dry-run", choices=["dry-run", "xdotool", "pynput"])
    ap.add_argument("--focus", default=None, help="act only while this window title has focus")
    ap.add_argument("--pixels-per-unit", type=float, default=800.0)
    ap.add_argument("--max-speed", type=float, default=1.0, help="workspace units / s")
    ap.add_argument("--rate-hz", type=float, default=60.0, help="max OS pointer moves / s")
    ap.add_argument("--click-interval-ms", type=float, default=500.0)
    ap.add_argument("--min-confidence", type=float, default=0.0)
    ap.add_argument("--seconds", type=float, default=60.0)
    return asyncio.run(_main(ap.parse_args(argv)))


if __name__ == "__main__":
    raise SystemExit(main())
