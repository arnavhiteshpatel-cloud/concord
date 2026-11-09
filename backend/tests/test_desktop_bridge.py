"""M5-C opt-in desktop control bridge (backend/examples/desktop_bridge): off by default, acts
only on authorized decoded commands through the SDK CommandGuard, bounded rate / speed /
clicks, focus restriction, immediate stop. Dry-run backend everywhere; a real X11 backend
test (Xvfb + xdotool) when both are installed.
"""

from __future__ import annotations

import ast
import asyncio
import os
import shutil
import subprocess
import sys
import time
from collections.abc import Iterator
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

from concord.contracts import parse_envelope
from concord.contracts.protocol import AppStatus, NegotiationResult, RuntimeSnapshot
from concord.sdk import Capability, NegotiationUpdate, RuntimeUpdate

from .helpers import valid_event, wait_for

BRIDGE_DIR = Path(__file__).resolve().parents[1] / "examples" / "desktop_bridge"
SESSION = valid_event("intent.pointer")["session_id"]


def _load() -> tuple[ModuleType, ModuleType]:
    if str(BRIDGE_DIR) not in sys.path:
        sys.path.insert(0, str(BRIDGE_DIR))
    import backends
    import bridge

    return bridge, backends


class Clock:
    def __init__(self) -> None:
        self.t = 100.0

    def __call__(self) -> float:
        return self.t


def _ready(b: Any, caps: tuple[str, ...] = ("pointer_intent", "selection")) -> None:
    granted = [Capability(c) for c in (*caps, "control_status")]
    b.handle(
        NegotiationUpdate(
            NegotiationResult(device_id="d", status=AppStatus.ACTIVE, granted=granted, rejected=[])
        )
    )
    b.handle(
        RuntimeUpdate(
            RuntimeSnapshot.model_validate(
                {
                    "state": "streaming",
                    "device": None,
                    "session_id": SESSION,
                    "state_since_ns": 0,
                    "last_error": None,
                    "recording": None,
                    "apps": [],
                }
            )
        )
    )
    _ctl(b, True, list(caps), "decoded command output active")


def _ctl(b: Any, active: bool, caps: list[str], reason: str) -> None:
    ev = valid_event("control.state", timestamp_ns=time.time_ns())
    ev["payload"] = {"active": active, "capabilities": caps if active else [], "reason": reason}
    b.handle(parse_envelope(ev))


def _cmd(
    b: Any, event_type: str, kind: str = "decoded_intent", age_ms: float = 0, **pl: Any
) -> None:
    ev = valid_event(event_type, timestamp_ns=time.time_ns() - round(age_ms * 1e6))
    if kind == "decoded_intent":
        ev["provenance"].update(kind="decoded_intent", model_id="m1")
    ev["payload"].update(pl)
    b.handle(parse_envelope(ev))


def _bridge(**cfg: Any) -> tuple[Any, Any, Clock]:
    bridge, backends = _load()
    clock = Clock()
    be = backends.DryRunBackend(focus=cfg.pop("window", "dry-run"))
    b = bridge.Bridge(bridge.BridgeConfig(enable=True, **cfg), be, clock=clock)
    return b, be, clock


def test_bridge_is_sdk_only_and_never_the_operator() -> None:
    stdlib = set(sys.stdlib_module_names) | {"__future__"}
    for path in BRIDGE_DIR.glob("*.py"):
        text = path.read_text(encoding="utf-8")
        for node in ast.walk(ast.parse(text)):
            names: list[str] = []
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [node.module or ""]
            for n in names:
                assert n.split(".")[0] in stdlib or n in ("concord.sdk", "backends"), (path, n)
        for word in ("authorize_app", "set_router", "start_pipeline", "/control", "RuntimeClient"):
            assert word not in text, f"{path.name} uses operator API {word!r}"
        assert "recording.frame" not in text and "features." not in text  # never raw signals
    assert (BRIDGE_DIR / "SAFETY.md").exists()
    ref = Path(__file__).resolve().parents[1] / "examples" / "reference_app"
    for path in ref.glob("*.py"):  # the reference apps never drive the OS
        assert "desktop_bridge" not in path.read_text(
            encoding="utf-8"
        ) and "xdotool" not in path.read_text(encoding="utf-8")


def test_off_by_default_and_refusals() -> None:
    bridge, backends = _load()
    with pytest.raises(bridge.BridgeRefused, match="off by default"):
        bridge.Bridge(bridge.BridgeConfig(), backends.DryRunBackend())
    with pytest.raises(bridge.BridgeRefused, match="cannot tell which window has focus"):
        bridge.Bridge(
            bridge.BridgeConfig(enable=True, focus="Board"), backends.DryRunBackend(focus=None)
        )
    with pytest.raises(bridge.BridgeRefused):
        bridge.BridgeConfig(enable=True, rate_hz=1000).check()
    # the CLI refuses before touching the network or the pointer
    out = subprocess.run(
        [sys.executable, str(BRIDGE_DIR / "bridge.py"), "--url", "http://127.0.0.1:9"],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert out.returncode == 2 and "off by default" in out.stderr


def test_acts_only_on_usable_decoded_commands_with_bounded_speed_and_rate() -> None:
    b, be, clock = _bridge(pixels_per_unit=800, max_speed=1.0)
    _cmd(b, "intent.pointer", vx=0.5, vy=0.0)
    b.tick()
    assert be.actions == []  # not granted yet: the guard drops it
    _ready(b)
    _cmd(b, "intent.pointer", vx=0.5, vy=0.0)
    b.tick()  # first tick only sets the clock
    clock.t += 0.05
    b.tick()
    assert be.actions == [("move", 20, 0)]  # 0.5 units/s x 50 ms x 800 px
    _cmd(b, "intent.pointer", vx=3.0, vy=4.0)  # |v| = 5 > max 1: clamped along its direction
    clock.t += 0.1
    b.tick()
    assert be.actions[-1] == ("move", 48, 64)
    clock.t += 5.0  # a long gap is clamped to 0.1 s
    b.tick()
    assert be.actions[-1] == ("move", 48, 64)
    assert b.stats.moves == 3  # at most one move per tick: the rate is bounded by rate_hz
    # simulated intent is not operator-authorized: refused, and it zeroes the velocity
    _cmd(b, "intent.pointer", kind="simulated_intent", vx=1.0, vy=0.0)
    clock.t += 0.05
    b.tick()
    assert b.stats.refused_provenance == 1 and b.stats.moves == 3
    # stale commands never move the pointer
    _cmd(b, "intent.pointer", age_ms=800, vx=1.0, vy=0.0)
    clock.t += 0.05
    b.tick()
    assert b.stats.moves == 3 and b.guard.stats.dropped_stale == 1


def test_clicks_are_debounced_gated_and_cancel_is_ignored() -> None:
    b, be, clock = _bridge(click_interval_ms=500, min_confidence=0.6)
    _ready(b)
    _cmd(b, "intent.selection", action="primary", confidence=0.9)
    _cmd(b, "intent.selection", action="activate", confidence=0.9)  # within 500 ms
    clock.t += 0.6
    _cmd(b, "intent.selection", action="cancel", confidence=0.9)
    _cmd(b, "intent.selection", action="primary", confidence=0.5)  # below min confidence
    _cmd(b, "intent.selection", action="activate", confidence=0.7)
    assert [a for a in be.actions if a[0] == "click"] == [("click", 0, 0)] * 2
    assert b.stats.refused_click_rate == 1 and b.stats.refused_confidence == 1


def test_stops_immediately_on_control_state_inactive_and_on_the_hotkey() -> None:
    b, be, clock = _bridge()
    _ready(b)
    _cmd(b, "intent.pointer", vx=1.0, vy=1.0)
    b.tick()
    clock.t += 0.05
    b.tick()
    n = len(be.actions)
    _ctl(b, False, [], "command output stopped: stopped by operator")
    assert b.log[-1] == "stopped acting: command output stopped: stopped by operator"
    for _ in range(5):
        _cmd(b, "intent.pointer", vx=1.0, vy=1.0)
        _cmd(b, "intent.selection", action="primary", confidence=0.9)
        clock.t += 0.05
        b.tick()
    assert len(be.actions) == n
    _ctl(b, True, ["pointer_intent", "selection"], "on again")  # the operator re-enabled it
    _cmd(b, "intent.pointer", vx=1.0, vy=0.0)
    b.tick()
    clock.t += 0.05
    b.tick()
    assert len(be.actions) == n + 1
    be.press_hotkey()  # the user's stop: latched, the process exits
    assert b.stopped == "stop hotkey"
    _cmd(b, "intent.pointer", vx=1.0, vy=0.0)
    clock.t += 0.05
    b.tick()
    assert len(be.actions) == n + 1


def test_deadman_and_focus_restriction() -> None:
    b, be, clock = _bridge(focus="Communication Board", window="Terminal")
    _ready(b)
    _cmd(b, "intent.pointer", vx=1.0, vy=0.0)
    _cmd(b, "intent.selection", action="primary", confidence=0.9)
    b.tick()
    clock.t += 0.05
    b.tick()
    assert be.actions == [] and b.stats.refused_focus == 2  # wrong window: no move, no click
    be.focus = "Concord — Communication Board"
    clock.t += 0.05
    b.tick()
    assert be.actions[-1][0] == "move"
    # dead-man: no pointer command for > 500 ms -> no more movement
    deadline = time.monotonic() + 0.6
    while time.monotonic() < deadline:
        b.guard.tick()
        time.sleep(0.02)
    n = len(be.actions)
    clock.t += 0.05
    b.tick()
    assert len(be.actions) == n and b.guard.stats.deadman == 1


# ------------------------------------------------------------------ real server (e2e)


@pytest.fixture
def scripted_server(tmp_path: Path) -> Iterator[str]:
    pytest.importorskip("scipy")
    from concord.server import create_app
    from concord.testing import scripted

    from .conftest import free_port, make_settings, serve

    port = free_port()
    settings = make_settings(tmp_path, port=port)
    scripted.write_identity_model(settings.models_dir)
    app = create_app(settings)
    program = scripted.click_program([(0.625, 0.125)] * 3)
    app.state.services.runtime.registry.register(
        scripted.descriptor(),
        lambda: scripted.ScriptedFeatureSource(program, start_after_s=0.5, loop=True),
    )
    yield from serve(app, port)


async def test_bridge_end_to_end_needs_authorization_and_stops_on_operator_stop(
    scripted_server: str,
) -> None:
    from concord.sdk import RuntimeClient
    from concord.testing import scripted

    bridge, backends = _load()
    be = backends.DryRunBackend()
    b = bridge.Bridge(bridge.BridgeConfig(enable=True, rate_hz=50), be)
    stop = asyncio.Event()
    runner = asyncio.create_task(bridge.run(b, scripted_server, stop))
    async with RuntimeClient(scripted_server) as op:
        await op.connect(scripted.DEVICE_ID)
        await op.start_pipeline(
            "features_passthrough", model_id=scripted.MODEL_ID, router=scripted.ROUTER
        )
        await wait_for(lambda: b.waiting_for_authorization != [], timeout=10)
        await asyncio.sleep(1.0)
        assert be.actions == []  # decoded commands exist, but the operator has not authorized
        await op.authorize_app(bridge.APP_ID, ["pointer_intent", "selection"])
        await wait_for(lambda: b.stats.moves >= 5 and b.stats.clicks >= 1, timeout=15)
        assert b.control and b.control.startswith("active")
        t0 = time.monotonic()
        await op.stop_control("e2e stop")
        await wait_for(lambda: b.control is not None and b.control.startswith("inactive"), 1.0)
        assert time.monotonic() - t0 < 1.0
        n = len(be.actions)
        await asyncio.sleep(1.0)
        assert len(be.actions) == n, "an OS event after the operator's stop"
        assert "command output stopped: e2e stop" in (b.control or "")
        await op.disconnect()
    stop.set()
    await runner
    assert b.stopped is not None


# ------------------------------------------------------------------ real X11 backend


@pytest.fixture
def xdisplay() -> Iterator[str]:
    if not (shutil.which("Xvfb") and shutil.which("xdotool")):
        pytest.skip("Xvfb and xdotool are not installed (apt-get install xvfb xdotool)")
    display = f":{90 + os.getpid() % 50}"
    # -noreset: keep pointer state between xdotool invocations (each is a new X client)
    proc = subprocess.Popen(
        ["Xvfb", display, "-screen", "0", "1024x768x24", "-noreset", "-nolisten", "tcp"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    old = os.environ.get("DISPLAY")
    os.environ["DISPLAY"] = display
    try:
        deadline = time.monotonic() + 5
        while subprocess.run(["xdotool", "getmouselocation"], capture_output=True).returncode:
            if time.monotonic() > deadline:
                pytest.skip("Xvfb did not start")
            time.sleep(0.1)
        yield display
    finally:
        if old is None:
            os.environ.pop("DISPLAY", None)
        else:
            os.environ["DISPLAY"] = old
        proc.terminate()
        proc.wait(timeout=5)


def test_x11_backend_moves_the_real_pointer_and_honours_focus(xdisplay: str) -> None:
    bridge, backends = _load()
    x11 = backends.XdotoolBackend()
    subprocess.run(["xdotool", "mousemove", "100", "100"], check=True)
    clock = Clock()
    b = bridge.Bridge(bridge.BridgeConfig(enable=True, pixels_per_unit=800), x11, clock=clock)
    _ready(b)
    _cmd(b, "intent.pointer", vx=0.5, vy=0.25)
    b.tick()
    clock.t += 0.1
    b.tick()
    assert x11.location() == (140, 120)  # 0.5 x 0.1 x 800 = 40 px, 0.25 x 0.1 x 800 = 20 px
    # focus restriction against a real window
    if not shutil.which("xterm"):
        pytest.skip("xterm not installed: focus restriction not exercised on X11")
    # no shell inside: a shell prompt would retitle the window
    term = subprocess.Popen(
        ["xterm", "-T", "Communication Board test window", "-e", "sleep", "60"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        fb = bridge.Bridge(
            bridge.BridgeConfig(enable=True, focus="Communication Board"), x11, clock=clock
        )
        _ready(fb)
        _cmd(fb, "intent.pointer", vx=0.5, vy=0.0)
        fb.tick()
        clock.t += 0.1
        fb.tick()
        assert fb.stats.refused_focus == 1 and x11.location() == (140, 120)  # nothing focused
        deadline = time.monotonic() + 10
        focused = False
        while not focused and time.monotonic() < deadline:  # the window maps asynchronously
            r = subprocess.run(
                ["xdotool", "search", "--onlyvisible", "--name", "Communication Board test"],
                capture_output=True,
                text=True,
            )
            ids = r.stdout.split()
            focused = bool(ids) and (
                subprocess.run(
                    ["xdotool", "windowfocus", "--sync", ids[0]], capture_output=True, timeout=5
                ).returncode
                == 0
            )
            time.sleep(0.1)
        assert focused, "could not focus the test window"
        assert "Communication Board" in (x11.focused_window() or "")
        clock.t += 0.1
        fb.tick()
        assert x11.location() == (180, 120)
    finally:
        term.terminate()
        term.wait(timeout=5)
