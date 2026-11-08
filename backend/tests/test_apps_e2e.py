"""M5-C end to end with a real server and the public SDK: decoded commands from real pipeline
paths drive SDK-only apps, the runtime's control.state reaches them over the WebSocket in
order, and nothing arrives after an inactive notice.

Sources (declared synthetic, nothing neural or human): the in-test motor-imagery source with
an LDA fitted on separate synthetic data (discrete: navigate + select rules), and the scripted
decoder test source with its hand-written identity test decoder (continuous cursor + click).
"""

from __future__ import annotations

import asyncio
import importlib.util
import sys
import time
from collections.abc import Iterator
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

pytest.importorskip("scipy")

from concord.server import create_app
from concord.testing import scripted

from .conftest import free_port, make_settings, serve
from .helpers import wait_for
from .mi_source import MotorImageryAdapter, train_offline_lda

APP_DIR = Path(__file__).resolve().parents[1] / "examples" / "reference_app"
BAND = {"band_low_hz": 8, "band_high_hz": 13, "bin_ms": 200}
NAV_RULES = [
    {"output": "left", "action": "navigate:next", "threshold": 0.6, "hold_ms": 200},
    {"output": "right", "action": "activate", "threshold": 0.6, "hold_ms": 200},
]
COMMANDS = {"intent.pointer", "intent.selection", "intent.text", "intent.navigate"}


def _load(name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, APP_DIR / f"{name}.py")
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def server(tmp_path: Path) -> Iterator[tuple[str, str]]:
    port = free_port()
    settings = make_settings(tmp_path, port=port)
    app = create_app(settings)
    reg = app.state.services.runtime.registry
    reg.register(
        MotorImageryAdapter(device_id="test-mi", speed=20.0, seed=7).descriptor,
        lambda: MotorImageryAdapter(device_id="test-mi", speed=20.0, seed=7),
    )
    program = scripted.click_program([(0.2, 0.8), (0.8, 0.2)])
    reg.register(
        scripted.descriptor(),
        lambda: scripted.ScriptedFeatureSource(program, start_after_s=0.3, loop=True),
    )
    settings.models_dir.mkdir(parents=True, exist_ok=True)
    model = train_offline_lda(settings.models_dir)
    scripted.write_identity_model(settings.models_dir)
    for base in serve(app, port):
        yield base, model.model_id


class Recorder:
    """A plain SDK client that records, in arrival order, control.state and commands."""

    def __init__(self) -> None:
        self.items: list[tuple[str, Any]] = []
        self.stream: Any = None

    async def run(self, base: str, app_id: str, optional: list[str]) -> None:
        from concord.sdk import EventStream, is_event

        self.stream = await EventStream.connect(
            app_id=app_id, app_name=app_id, optional=optional, base_url=base
        )
        async with self.stream as s:
            async for item in s:
                if not is_event(item):
                    continue
                et = item.event_type.value
                if et == "control.state":
                    self.items.append(("on" if item.payload.active else "off", item.payload))  # type: ignore[union-attr]
                elif et in COMMANDS:
                    self.items.append(("cmd", et))

    def seq(self) -> list[str]:
        return [k for k, _ in self.items]


def _no_command_while_off(seq: list[str]) -> None:
    on = False
    for x in seq:
        if x in ("on", "off"):
            on = x == "on"
        else:
            assert on, f"a command arrived while control.state was inactive: {seq}"


async def test_navigation_drives_the_menu_and_control_state_is_ordered_over_the_wire(
    server: tuple[str, str],
) -> None:
    from concord.sdk import RuntimeClient

    base, model_id = server
    menu_mod = _load("menu_app")
    menu, stop = menu_mod.MenuApp(), asyncio.Event()
    runners = [asyncio.create_task(menu_mod.run(menu, base, stop))]
    rec = Recorder()
    runners.append(
        asyncio.create_task(
            rec.run(base, "order-check", ["selection", "navigation", "control_status"])
        )
    )
    async with RuntimeClient(base) as op:
        await op.connect("test-mi")
        await op.start_pipeline(
            "band_power", model_id=model_id, router={"enabled": True, "discrete": NAV_RULES}, **BAND
        )
        ctl = await op.control()
        assert sorted(ctl["provides"]) == ["navigation", "selection"]
        await wait_for(lambda: menu.waiting_for_authorization, timeout=10)
        await op.authorize_app("reference-menu", ["selection", "navigation"])
        await op.authorize_app("order-check", ["selection", "navigation"])
        await wait_for(
            lambda: (
                any(k.startswith("navigate:") for k in menu.actions)
                and menu.actions.get("activate", 0) >= 1
            ),
            timeout=30,
        )
        assert menu.control is not None and menu.control.startswith("active")
        assert {p for p in menu.provenance} == {("decoded_intent", model_id)}
        await wait_for(lambda: rec.seq().count("cmd") >= 3, timeout=20)
        t0 = time.monotonic()
        await op.stop_control("e2e stop")
        await wait_for(lambda: rec.seq()[-1] == "off", timeout=1.0)
        assert time.monotonic() - t0 < 1.0
        await wait_for(lambda: (menu.control or "").startswith("inactive"), timeout=1.0)
        n = len(rec.items)
        await asyncio.sleep(1.0)
        assert rec.seq()[n:] == [], "anything after the stop"
        last = rec.items[-1][1]
        assert last.reason == "command output stopped: e2e stop" and last.capabilities == []
        ctl = await op.control()
        entry = next(a for a in ctl["apps"] if a["app_id"] == "order-check")
        assert entry["control_active"] is False and "e2e stop" in entry["control_reason"]
        await op.disconnect()
    stop.set()
    await runners[0]
    runners[1].cancel()
    seq = rec.seq()
    assert seq.count("on") >= 1 and seq.count("cmd") >= 3
    _no_command_while_off(seq)
    assert menu.stops and "command output stopped" in menu.stops[0]


async def test_scripted_decoder_drives_the_cursor_app_until_revoked(
    server: tuple[str, str],
) -> None:
    from concord.sdk import RuntimeClient

    base, _ = server
    cursor_mod = _load("cursor_app")
    cursor, stop = cursor_mod.CursorApp(), asyncio.Event()
    runner = asyncio.create_task(cursor_mod.run(cursor, base, stop))
    async with RuntimeClient(base) as op:
        await op.connect(scripted.DEVICE_ID)
        await op.start_pipeline(
            "features_passthrough", model_id=scripted.MODEL_ID, router=scripted.ROUTER
        )
        await wait_for(lambda: cursor.waiting_for_authorization, timeout=10)
        assert cursor.commands == 0
        await op.authorize_app("reference-cursor", ["pointer_intent"])
        await wait_for(lambda: cursor.commands >= 50, timeout=15)
        assert any(
            "decoded by model test-scripted-identity" in s.label for s in cursor.sources.values()
        )
        assert (cursor.x, cursor.y) != (0.0, 0.0)
        await op.revoke_app("reference-cursor")
        await wait_for(lambda: bool(cursor.stops), timeout=1.0)
        n = cursor.commands
        await asyncio.sleep(0.8)
        assert cursor.commands == n
        assert (cursor.control or "").startswith("inactive")
        await op.disconnect()
    stop.set()
    await runner
