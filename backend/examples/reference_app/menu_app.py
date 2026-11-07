"""BrainOS reference application: a discrete menu / speller driven by selection commands.

Uses ONLY the public Python SDK (``brainos.sdk``) and the standard library. Different needs
from the cursor app: it *requires* ``selection`` (discrete actions) and optionally uses
``text_intent``; it never moves a pointer.

* ``select`` (selection action ``primary``) moves the highlight to the next item;
* ``activate`` opens the highlighted submenu or chooses the highlighted entry;
* ``cancel`` goes back one level (a "Back" entry does the same where cancel is not offered);
* ``text`` intents are appended to the message line (a speller);
* ``navigation`` (schema 1.4, optional): up / previous and down / next move the highlight,
  right opens / chooses (like activate), left goes back (like cancel);
* ``control_status`` (schema 1.4, optional): the runtime's ``control.state`` notices are
  shown, and the guard acts on commands only while they say command delivery is active.

Which actions exist depends on the source and the operator's rules; the app adapts to what
arrives and never derives actions from raw signals, features or behavior labels itself.
Decoded actions need the operator's authorization of this app (``reference-menu``); until
then the app says it is waiting for authorization. A :class:`~brainos.sdk.CommandGuard`
drops commands older than 500 ms and reports immediately when commands stop (revocation,
command output stopped, source paused / switched / disconnected, stream closed).

    python backend/examples/reference_app/menu_app.py --url http://127.0.0.1:8000 --seconds 60

This is a research demo, not an assistive or clinical interface.
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import json
import sys
from dataclasses import dataclass, field
from typing import Any

from brainos.sdk import (
    BrainOSError,
    CommandGuard,
    EventStream,
    NegotiationUpdate,
    RuntimeUpdate,
    StreamItem,
    is_event,
)

APP_ID = "reference-menu"
TICK_S = 0.05
BACK = "Back"
MAX_MESSAGE = 120
# A two-level menu: top-level entries open a submenu; leaves are chosen.
MENU: dict[str, list[str]] = {
    "Messages": ["Yes", "No", "Thank you", BACK],
    "Lights": ["On", "Off", BACK],
    "Music": ["Play", "Pause", "Next", BACK],
    "Call someone": ["Family", "Caregiver", BACK],
}


@dataclass
class MenuApp:
    """Pure state machine; feed it SDK stream items with :meth:`handle`."""

    status: str = "connecting"  # negotiation status: active | suspended | no_device
    path: list[str] = field(default_factory=list)  # [] = top level, [entry] = in a submenu
    highlight: int = 0
    message: str = ""
    chosen: list[str] = field(default_factory=list)  # "Entry / Leaf" in the order chosen
    actions: dict[str, int] = field(default_factory=dict)  # action -> count acted on
    ignored: int = 0
    stops: list[str] = field(default_factory=list)
    provenance: set[tuple[str, str | None]] = field(default_factory=set)  # (kind, model_id)
    control: str | None = None  # the runtime's last control.state, as text
    guard: CommandGuard = field(init=False)

    def __post_init__(self) -> None:
        self.guard = CommandGuard(
            ["selection", "text_intent", "navigation"], on_stop=self.stops.append
        )

    # ------------------------------------------------------------------ state
    @property
    def items(self) -> list[str]:
        return MENU[self.path[0]] if self.path else list(MENU)

    @property
    def waiting_for_authorization(self) -> bool:
        return "selection" in self.guard.waiting_for_authorization

    @property
    def can_act(self) -> bool:
        return self.guard.is_active("selection")

    def handle(self, item: StreamItem) -> None:
        if isinstance(item, NegotiationUpdate):
            self.status = item.negotiation.status.value
        env = self.guard.handle(item)
        if not is_event(item):
            return
        if item.event_type.value == "control.state":  # shown even while suspended
            p = item.payload
            on = "active" if p.active else "inactive"  # type: ignore[union-attr]
            self.control = f"{on}: {p.reason}"  # type: ignore[union-attr]
            return
        if env is None or self.status != "active":
            self.ignored += 1
            return
        et = env.event_type.value
        if et == "intent.selection":
            self._act(str(env.payload.action))  # type: ignore[union-attr]
        elif et == "intent.text":
            self._type(str(env.payload.text))  # type: ignore[union-attr]
        elif et == "intent.navigate":
            self._navigate(str(env.payload.direction))  # type: ignore[union-attr]
        else:
            self.ignored += 1
            return
        self.provenance.add((env.provenance.kind.value, env.provenance.model_id))

    def _act(self, action: str) -> None:
        self.actions[action] = self.actions.get(action, 0) + 1
        items = self.items
        if action == "primary":  # select: move the highlight
            self.highlight = (self.highlight + 1) % len(items)
        elif action == "activate":
            self._open_or_choose()
        elif action == "cancel":
            self._back()

    def _open_or_choose(self) -> None:
        entry = self.items[self.highlight]
        if not self.path:
            self.path, self.highlight = [entry], 0
        elif entry == BACK:
            self._back()
        else:
            self.chosen.append(f"{self.path[0]} / {entry}")
            self._back()

    def _navigate(self, direction: str) -> None:
        self.actions[f"navigate:{direction}"] = self.actions.get(f"navigate:{direction}", 0) + 1
        n = len(self.items)
        if direction in ("down", "next"):
            self.highlight = (self.highlight + 1) % n
        elif direction in ("up", "previous"):
            self.highlight = (self.highlight - 1) % n
        elif direction == "right":
            self._open_or_choose()
        elif direction == "left":
            self._back()

    def _back(self) -> None:
        if self.path:
            top = self.path[0]
            self.path, self.highlight = [], list(MENU).index(top)

    def _type(self, text: str) -> None:
        self.actions["text"] = self.actions.get("text", 0) + 1
        sep = "" if len(text) == 1 or not self.message else " "
        self.message = (self.message + sep + text)[-MAX_MESSAGE:]

    # ------------------------------------------------------------------ output
    def line(self) -> str:
        if self.waiting_for_authorization:
            return (
                f"[{self.status}] waiting for operator authorization: the operator has not "
                f"authorized '{APP_ID}' to receive selection commands"
            )
        if self.status != "active" or not self.can_act:
            why = f" ({self.stops[-1]})" if self.stops else ""
            if self.control:
                why = f" (runtime: {self.control})"
            return f"[{self.status}] waiting: no source currently provides selection{why}"
        where = " > ".join(["Menu", *self.path])
        entries = " ".join(
            f"[{x}]" if i == self.highlight else f" {x} " for i, x in enumerate(self.items)
        )
        msg = f" | message: {self.message}" if self.message else ""
        return f"[active] {where}: {entries}{msg}"

    def summary(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "menu": " > ".join(["Menu", *self.path]),
            "highlighted": self.items[self.highlight],
            "chosen": self.chosen,
            "message": self.message,
            "actions": self.actions,
            "ignored_events": self.ignored,
            "stops": self.stops,
            "control": self.control,
            "commands_from": sorted(f"{k} ({m})" if m else k for k, m in self.provenance),
        }


async def run(app: MenuApp, base_url: str, stop: asyncio.Event) -> MenuApp:
    """Consume the event stream until ``stop`` is set."""
    async with await EventStream.connect(
        app_id=APP_ID,
        app_name="Reference menu app",
        required=["selection"],
        optional=["text_intent", "navigation", "control_status"],
        base_url=base_url,
    ) as stream:
        app.handle(NegotiationUpdate(stream.negotiation))
        app.handle(RuntimeUpdate(stream.runtime))

        async def consume() -> None:
            async for item in stream:
                app.handle(item)

        async def tick() -> None:
            while True:
                await asyncio.sleep(TICK_S)
                app.guard.tick()

        tasks = [asyncio.create_task(consume()), asyncio.create_task(tick())]
        await stop.wait()
        for t in tasks:
            t.cancel()
        for t in tasks:
            with contextlib.suppress(asyncio.CancelledError, BrainOSError):
                await t
    app.guard.on_closed()
    return app


async def _main(args: argparse.Namespace) -> int:
    app, stop = MenuApp(), asyncio.Event()
    runner = asyncio.create_task(run(app, args.url, stop))
    loop = asyncio.get_running_loop()
    deadline = loop.time() + args.seconds
    last = ""
    try:
        while loop.time() < deadline and not runner.done():
            await asyncio.sleep(0.25)
            line = app.line()
            if line != last:
                print(line, flush=True)
                last = line
    finally:
        stop.set()
        try:
            await runner
        except (BrainOSError, OSError) as exc:
            print(f"cannot reach BrainOS at {args.url}: {exc}", file=sys.stderr)
            return 1
    print(json.dumps(app.summary(), indent=2))
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--url", default="http://127.0.0.1:8000")
    ap.add_argument("--seconds", type=float, default=60.0)
    return asyncio.run(_main(ap.parse_args(argv)))


if __name__ == "__main__":
    raise SystemExit(main())
