"""Milestone 3 reference app (backend/examples/reference_app): SDK-only (M3-AT-14).

The same, unchanged app instance runs against a simulator, a prerecorded FALCON block streamed
over LSL (with and without a decoder + router) and an Open Ephys ZMQ stream. It only ever moves
on commands the runtime grants; raw signals and features never become commands by themselves.
"""

from __future__ import annotations

import ast
import asyncio
import importlib.util
import os
import sys
import threading
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

from .helpers import wait_for

REPO = Path(__file__).resolve().parents[2]
APP_DIR = REPO / "backend" / "examples" / "reference_app"


def _load_app() -> ModuleType:
    spec = importlib.util.spec_from_file_location("cursor_app", APP_DIR / "cursor_app.py")
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules["cursor_app"] = mod
    spec.loader.exec_module(mod)
    return mod


def test_reference_app_imports_only_the_public_sdk() -> None:
    allowed_prefix = "concord.sdk"
    stdlib = set(sys.stdlib_module_names) | {"__future__"}
    for path in APP_DIR.glob("*.py"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            names: list[str] = []
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [node.module or ""]
            for n in names:
                ok = n.split(".")[0] in stdlib or n == allowed_prefix
                assert ok, f"{path.name} imports {n}; reference apps may use only concord.sdk"
        text = path.read_text(encoding="utf-8")
        for word in ("sim-a", "sim-b", "lsl:", "openephys", "nwb:", "falcon"):
            assert word not in text.lower(), f"{path.name} mentions device/source {word!r}"


def test_app_state_machine_ignores_events_when_not_granted() -> None:
    app_mod = _load_app()
    from concord.contracts.protocol import AppStatus, NegotiationResult
    from concord.sdk import NegotiationUpdate

    from .helpers import valid_event

    app = app_mod.CursorApp()
    app.handle(
        NegotiationUpdate(
            NegotiationResult(device_id=None, status=AppStatus.SUSPENDED, granted=[], rejected=[])
        )
    )
    from concord.contracts import parse_envelope

    env = parse_envelope(valid_event("intent.pointer"))
    app.handle(env)
    assert app.commands == 0 and app.ignored == 1 and (app.x, app.y) == (0.0, 0.0)


async def test_same_app_unchanged_across_sources(
    live_server: str, tmp_path: Path, publishers: list[Any]
) -> None:
    pytest.importorskip("pylsl")
    pytest.importorskip("scipy")
    pytest.importorskip("zmq")
    from concord.sdk import ConcordError, RuntimeClient
    from concord.testing.lsl_publishers import FalconLSLPublisher

    from .test_pipeline_live import EVAL_FILE, HAVE_DATA, TRAIN_FILE, _train

    if not HAVE_DATA:
        pytest.skip("real FALCON H1 files not found; run `make dataset`")
    model = _train(TRAIN_FILE, tmp_path / "data" / "models")  # served by live_server
    app_mod = _load_app()
    app = app_mod.CursorApp()
    stop = asyncio.Event()
    runner = asyncio.create_task(app_mod.run(app, live_server, stop))

    async with RuntimeClient(live_server) as op:
        # 1) simulator: commands are simulated intent
        await op.connect("sim-a")
        await wait_for(lambda: app.status == "active" and app.commands >= 5, timeout=10)

        # 2) prerecorded FALCON over LSL: features only -> the app is suspended
        hold = threading.Event()
        pub = FalconLSLPublisher(EVAL_FILE, speed=10, source_prefix=f"app-{os.getpid()}", hold=hold)
        pub.start()
        publishers.append(pub)
        await op.discover_lsl(1.5)
        k = pub.prefix
        desc = await op.configure_lsl(f"{k}-counts", f"{k}-behavior", f"{k}-markers")
        assert desc.kind.value == "replay"
        await op.switch(desc.device_id)
        await wait_for(lambda: app.status == "suspended", timeout=10)
        await op.start_pipeline("features_passthrough")  # features flow, still no commands
        hold.set()
        n0 = app.commands
        await asyncio.sleep(1.5)
        assert (await op.pipeline())["counters"]["inputs"] > 20
        assert app.status == "suspended" and app.commands == n0

        # a decoder without the router still yields no commands
        await op.start_pipeline("features_passthrough", model_id=model.model_id)
        await asyncio.sleep(1.0)
        assert app.status == "suspended" and app.commands == n0

        # 3) operator enables the router: the app now waits for the operator's authorization
        await op.set_router(enabled=True, x_dim="tx", y_dim="ty", gain=0.5)
        await wait_for(lambda: app.waiting_for_authorization, timeout=10)
        await asyncio.sleep(0.5)
        assert app.status == "suspended" and app.commands == n0
        # ... and once the operator authorizes it, decoded commands reach the unchanged app
        await op.authorize_app(app_mod.APP_ID, ["pointer_intent"])
        await wait_for(lambda: app.status == "active" and app.commands >= n0 + 50, timeout=15)

        # an incompatible request is refused with a reason, through the SDK
        with pytest.raises(ConcordError) as exc:
            await op.start_pipeline("spikeband_threshold")
        assert exc.value.code == "capability_unsupported"

        # 4) Open Ephys ZMQ (synthetic test publisher): raw signal only -> suspended again
        from concord.adapters.openephys.publisher import OpenEphysTestPublisher

        from .test_openephys import free_port_pair

        port = free_port_pair()
        oe = OpenEphysTestPublisher(data_port=port, channels=tuple(range(4))).start()
        publishers.append(oe)
        oe_desc = await op.configure_openephys(host="127.0.0.1", data_port=port)
        await op.switch(oe_desc.device_id)
        await wait_for(lambda: app.status == "suspended", timeout=10)
        n1 = app.commands
        await op.start_pipeline("spikeband_threshold")
        await asyncio.sleep(1.0)
        assert app.status == "suspended" and app.commands == n1
        await op.disconnect()

    stop.set()
    await runner
    kinds = {(s.kind, s.model_id, s.prerecorded) for s in app.sources.values()}
    assert ("simulated_intent", None, False) in kinds
    assert ("decoded_intent", model.model_id, True) in kinds
    assert all("lsl:" in s.device_id or s.device_id == "sim-a" for s in app.sources.values())
    assert app.summary()["commands"] == app.commands


OPERATOR_CALLS = (
    "authorize_app",
    "revoke_app",
    "stop_control",
    "set_router",
    "start_pipeline",
    "/control",
    "/pipeline",
    "RuntimeClient",
)


@pytest.mark.parametrize("name", ["cursor_app", "menu_app"])
def test_reference_apps_never_act_as_the_operator(name: str) -> None:
    """M4: apps declare capabilities and wait; authorization is the operator's decision."""
    text = (APP_DIR / f"{name}.py").read_text(encoding="utf-8")
    for word in OPERATOR_CALLS:
        assert word not in text, f"{name} uses operator API {word!r}"
    assert "CommandGuard" in text  # both apps act on commands through the SDK guard


def _load_named(name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, APP_DIR / f"{name}.py")
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def test_menu_app_state_machine() -> None:
    import time

    from concord.contracts import parse_envelope
    from concord.contracts.protocol import (
        AppStatus,
        CapabilityRejection,
        NegotiationResult,
        RejectionReason,
    )
    from concord.sdk import Capability, NegotiationUpdate

    from .helpers import valid_event

    m = _load_named("menu_app")
    app = m.MenuApp()

    def neg(granted: list[Capability], reason: str | None = None) -> NegotiationUpdate:
        rej = []
        if reason:
            rej = [
                CapabilityRejection(
                    capability=Capability.SELECTION, reason=RejectionReason(reason), required=True
                )
            ]
        status = AppStatus.SUSPENDED if rej else AppStatus.ACTIVE
        return NegotiationUpdate(
            NegotiationResult(device_id="d", status=status, granted=granted, rejected=rej)
        )

    def act(action: str) -> None:
        ev = valid_event("intent.selection", timestamp_ns=time.time_ns())
        ev["payload"]["action"] = action
        app.handle(parse_envelope(ev))

    app.handle(neg([], "not_authorized"))
    assert app.waiting_for_authorization and "authorization" in app.line()
    act("activate")
    assert app.path == [] and app.ignored == 1  # not authorized: nothing happens
    app.handle(neg([Capability.SELECTION]))
    act("primary")  # highlight "Lights"
    act("activate")  # open it
    assert app.path == ["Lights"] and app.items[app.highlight] == "On"
    act("activate")  # choose "On": back to the top level
    assert app.chosen == ["Lights / On"] and app.path == []
    assert app.items[app.highlight] == "Lights"
    act("activate")
    act("cancel")
    assert app.path == []
    app.handle(parse_envelope(valid_event("intent.text", timestamp_ns=time.time_ns())))
    assert app.message == ""  # text_intent was not granted: ignored
    app.handle(neg([], "not_authorized"))
    assert app.stops == ["authorization revoked"]


def test_menu_app_navigation_and_control_state() -> None:
    """M5-C: the menu app follows intent.navigate (schema 1.4) and the runtime's control.state;
    with control_status granted it acts only while the runtime says delivery is active."""
    import time

    from concord.contracts import parse_envelope
    from concord.contracts.protocol import AppStatus, NegotiationResult
    from concord.sdk import Capability, NegotiationUpdate, RuntimeUpdate
    from concord.sdk.client import RuntimeSnapshot

    from .helpers import valid_event

    m = _load_named("menu_app")
    app = m.MenuApp()
    granted = [Capability.SELECTION, Capability.NAVIGATION, Capability.CONTROL_STATUS]
    app.handle(
        NegotiationUpdate(
            NegotiationResult(device_id="d", status=AppStatus.ACTIVE, granted=granted, rejected=[])
        )
    )
    session = valid_event("intent.navigate")["session_id"]
    app.handle(
        RuntimeUpdate(
            RuntimeSnapshot.model_validate(
                {
                    "state": "streaming",
                    "device": None,
                    "session_id": session,
                    "state_since_ns": 0,
                    "last_error": None,
                    "recording": None,
                    "apps": [],
                }
            )
        )
    )

    def ctl(active: bool, reason: str) -> None:
        ev = valid_event("control.state", timestamp_ns=time.time_ns())
        caps = ["navigation", "selection"] if active else []
        ev["payload"] = {"active": active, "capabilities": caps, "reason": reason}
        app.handle(parse_envelope(ev))

    def nav(direction: str) -> None:
        ev = valid_event("intent.navigate", timestamp_ns=time.time_ns())
        ev["payload"]["direction"] = direction
        app.handle(parse_envelope(ev))

    nav("down")
    assert app.highlight == 0 and app.ignored == 1  # no control.state yet: not acted on
    ctl(True, "command input active")
    nav("down")
    nav("down")
    nav("up")
    assert app.items[app.highlight] == "Lights"
    nav("right")  # opens "Lights"
    assert app.path == ["Lights"]
    nav("next")
    nav("right")  # chooses "Off"
    assert app.chosen == ["Lights / Off"] and app.path == []
    nav("right")
    nav("left")  # back
    assert app.path == []
    ctl(False, "command output stopped: stopped by operator")
    assert app.stops[-1] == "command output stopped: stopped by operator"
    assert "command output stopped" in app.line()
    nav("down")
    assert app.items[app.highlight] == "Lights"  # nothing after the stop
    assert app.summary()["control"] == "inactive: command output stopped: stopped by operator"
