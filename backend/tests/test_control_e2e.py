"""Milestone 4 control bridge end to end: a real server, the public SDK and the two unchanged
SDK-only reference apps (cursor: continuous pointer; menu: discrete selection + text).

The discrete source is the in-test synthetic motor-imagery adapter (tests/mi_source.py,
declared synthetic); its LDA is fitted on separately generated synthetic data.
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

import httpx
import pytest

pytest.importorskip("scipy")

from brainos.server import create_app

from .conftest import free_port, make_settings, serve
from .helpers import wait_for
from .mi_source import MotorImageryAdapter, train_offline_lda

APP_DIR = Path(__file__).resolve().parents[1] / "examples" / "reference_app"
RULES = [
    {"output": "left", "action": "primary", "threshold": 0.7, "hold_ms": 200, "refractory_ms": 600},
    {"output": "right", "action": "activate", "threshold": 0.7, "hold_ms": 200},
]
BAND = {"band_low_hz": 8, "band_high_hz": 13, "bin_ms": 200}
STOP_BOUND_S = 1.0  # an app learns that commands stopped within this time


def load_app(name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, APP_DIR / f"{name}.py")
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def control_server(tmp_path: Path) -> Iterator[tuple[str, str]]:
    """A real server with synthetic MI sources registered and an LDA model available."""
    port = free_port()
    settings = make_settings(tmp_path, port=port)
    app = create_app(settings)
    rt = app.state.services.runtime
    variants: dict[str, dict[str, Any]] = {
        "test-mi": {"speed": 20.0, "seed": 7},
        "test-mi-raw": {"speed": 20.0, "behavior": False},
        "test-mi-labels": {"speed": 20.0, "signal": False},
    }
    for did, kw in variants.items():
        k = {"device_id": did, **kw}
        rt.registry.register(
            MotorImageryAdapter(**k).descriptor, lambda k=k: MotorImageryAdapter(**k)
        )
    settings.models_dir.mkdir(parents=True, exist_ok=True)
    model = train_offline_lda(settings.models_dir)
    for base in serve(app, port):
        yield base, model.model_id


class Watcher:
    """A plain SDK client that counts command events it receives."""

    def __init__(self) -> None:
        self.commands = 0
        self.stream: Any = None

    async def run(self, base: str, app_id: str, required: list[str]) -> None:
        from brainos.sdk import EventStream, is_event

        self.stream = await EventStream.connect(
            app_id=app_id, app_name=app_id, required=required, base_url=base
        )
        async with self.stream as s:
            async for item in s:
                if is_event(item) and item.event_type.value.startswith("intent."):
                    self.commands += 1


def _total(app: Any) -> int:
    return sum(app.actions.values())


async def _still(app: Any, seconds: float = 1.0) -> None:
    n = _total(app)
    await asyncio.sleep(seconds)
    assert _total(app) == n, "a command arrived after commands stopped"


async def test_authorization_gates_decoded_actions_and_every_stop_reaches_the_app(
    control_server: tuple[str, str],
) -> None:
    from brainos.sdk import BrainOSError, RuntimeClient

    base, model_id = control_server
    menu_mod, cursor_mod = load_app("menu_app"), load_app("cursor_app")
    menu, cursor, stop = menu_mod.MenuApp(), cursor_mod.CursorApp(), asyncio.Event()
    runners = [
        asyncio.create_task(menu_mod.run(menu, base, stop)),
        asyncio.create_task(cursor_mod.run(cursor, base, stop)),
    ]
    intruder = Watcher()
    runners.append(asyncio.create_task(intruder.run(base, "intruder", ["selection"])))

    async with RuntimeClient(base) as op:
        await op.connect("test-mi")
        await wait_for(lambda: menu.status == "suspended", timeout=10)
        await op.start_pipeline(
            "band_power",
            model_id=model_id,
            router={"enabled": True, "discrete": RULES},
            **BAND,
        )
        # commands exist now, but no app is authorized: default deny
        await wait_for(lambda: menu.waiting_for_authorization, timeout=10)
        assert "waiting for operator authorization" in menu.line()
        await wait_for(lambda: intruder.stream is not None, timeout=5)
        await wait_for(lambda: intruder.stream.negotiation.status.value == "suspended", timeout=5)
        assert [r.reason.value for r in intruder.stream.negotiation.rejected] == ["not_authorized"]
        ctl = await op.control()
        entry = next(a for a in ctl["apps"] if a["app_id"] == "reference-menu")
        assert entry["receiving"] == [] and entry["authorized"] == []
        assert [(w["capability"], w["reason"]) for w in entry["waiting"]] == [
            ("selection", "not_authorized"),
            ("text_intent", "unsupported_by_device"),  # no text rule configured
            ("navigation", "unsupported_by_device"),  # M5: optional, no navigate rule
        ]
        assert ctl["router_on"] and ctl["provides"] == ["selection"]
        await wait_for(lambda: True, timeout=0.1)
        sel0 = (await op.pipeline())["counters"]["selections_out"]
        await asyncio.sleep(1.0)
        assert (await op.pipeline())["counters"]["selections_out"] > sel0  # the router runs
        assert _total(menu) == 0 and intruder.commands == 0
        # the dry run tells an app id where it stands
        dry = await op.negotiate(["selection"], app_id="reference-menu")
        assert dry.rejected[0].reason.value == "not_authorized"

        # the operator authorizes the menu app: decoded actions reach it, and only it
        await op.authorize_app("reference-menu", ["selection"])
        await wait_for(lambda: _total(menu) >= 4, timeout=20)
        assert menu.provenance == {("decoded_intent", model_id)}
        assert set(menu.actions) <= {"primary", "activate"}
        assert intruder.commands == 0
        ctl = await op.control()
        entry = next(a for a in ctl["apps"] if a["app_id"] == "reference-menu")
        assert entry["receiving"] == ["selection"] and entry["authorized"] == ["selection"]
        intr = next(a for a in ctl["apps"] if a["app_id"] == "intruder")
        assert intr["waiting"][0]["reason"] == "not_authorized"
        # the cursor app needs pointer movement, which a classifier does not provide
        assert cursor.status == "suspended" and cursor.commands == 0
        assert not cursor.waiting_for_authorization

        async def stopped_within_bound(action: Any, reason: str) -> None:
            n = len(menu.stops)
            t0 = time.monotonic()
            await action
            await wait_for(lambda: len(menu.stops) > n, timeout=STOP_BOUND_S)
            assert menu.stops[-1] == reason, menu.stops
            assert time.monotonic() - t0 < STOP_BOUND_S
            await _still(menu)

        await stopped_within_bound(op.revoke_app("reference-menu"), "authorization revoked")
        assert menu.waiting_for_authorization

        await op.authorize_app("reference-menu", ["selection"])
        n = _total(menu)
        await wait_for(lambda: _total(menu) > n, timeout=20)
        await stopped_within_bound(op.stop_control("e2e stop"), "command output stopped")
        again = await op.stop_control()  # idempotent
        assert not again["router_on"] and again["last_stop"]["reason"] == "e2e stop"
        kinds = [h["kind"] for h in again["history"]]
        assert kinds.count("authorized") == 2 and "revoked" in kinds and "router_off" in kinds

        await op.set_router(enabled=True, discrete=RULES)
        n = _total(menu)
        await wait_for(lambda: _total(menu) > n, timeout=20)
        # disconnect stops the pipeline (and with it command output) before the source goes
        await stopped_within_bound(op.disconnect(), "command output stopped")
        await wait_for(lambda: menu.status == "no_device", timeout=5)

        # raw signal only: features, no decoder -> nothing to route, apps stay suspended
        await op.connect("test-mi-raw")
        await op.start_pipeline("band_power", **BAND)
        with pytest.raises(BrainOSError) as exc:
            await op.set_router(enabled=True, discrete=RULES)
        assert exc.value.code == "protocol_error" and exc.value.status == 400
        # behavior labels only: no pipeline at all, labels are never commands
        await op.switch("test-mi-labels")
        with pytest.raises(BrainOSError) as exc:
            await op.start_pipeline("band_power", **BAND)
        assert exc.value.code == "capability_unsupported" and exc.value.status == 409
        await _still(menu, 1.0)
        assert menu.status == "suspended" and intruder.commands == 0 and cursor.commands == 0
        await op.disconnect()

    stop.set()
    await asyncio.gather(*runners[:2])
    runners[2].cancel()
    s = menu.summary()
    assert s["commands_from"] == [f"decoded_intent ({model_id})"]
    assert menu.stops[:3] == [
        "authorization revoked",
        "command output stopped",
        "command output stopped",
    ]
    assert len(menu.stops) == 3  # closing while nothing was usable is not another stop
    assert menu.guard.state("selection") == "closed"


async def test_rest_refusals_for_control_requests(control_server: tuple[str, str]) -> None:
    base, model_id = control_server
    async with httpx.AsyncClient(base_url=base + "/api/v1") as http:
        r = await http.post("/control/apps/x/authorize", json={"capabilities": ["recording"]})
        assert r.status_code == 400 and r.json()["error"]["code"] == "protocol_error"
        r = await http.post("/control/apps/x/authorize", json={"capabilities": ["telepathy"]})
        assert r.status_code == 422 and r.json()["error"]["code"] == "unknown_capability"
        r = await http.post("/control/apps/x/authorize", json={"capabilities": []})
        assert r.status_code == 422
        r = await http.post("/control/apps/bad id!/authorize", json={"capabilities": ["selection"]})
        assert r.status_code == 400
        r = await http.post("/control/apps/x/revoke")  # nothing to revoke: fine
        assert r.status_code == 200 and r.json()["apps"] == []
        r = await http.post("/control/stop")  # nothing running: idempotent
        assert r.status_code == 200 and r.json()["router_on"] is False
        await http.post("/runtime/connect", json={"device_id": "test-mi"})
        r = await http.post(
            "/pipeline/start",
            json={"processing": {"preset": "band_power", **BAND}, "model_id": model_id},
        )
        assert r.status_code == 200
        r = await http.post(
            "/pipeline/router", json={"enabled": True, "x_dim": "left", "y_dim": "right"}
        )
        assert r.status_code == 409 and r.json()["error"]["code"] == "incompatible_decoder"
        r = await http.post("/pipeline/router", json={"enabled": True})
        assert r.status_code == 409 and r.json()["error"]["code"] == "capability_unsupported"
        r = await http.post(
            "/pipeline/router",
            json={"enabled": True, "discrete": [{"output": "left", "action": "text"}]},
        )
        assert r.status_code == 422  # malformed rule (text action without text)
        r = await http.post(
            "/control/apps/reference-menu/authorize",
            json={"capabilities": ["selection", "text_intent"]},
        )
        assert r.status_code == 200
        entry = r.json()["apps"][0]
        assert entry["app_id"] == "reference-menu" and entry["connections"] == 0
        assert entry["authorized"] == ["selection", "text_intent"]
        r = await http.post(
            "/control/apps/reference-menu/revoke", json={"capabilities": ["text_intent"]}
        )
        assert r.json()["apps"][0]["authorized"] == ["selection"]
        await http.post("/runtime/disconnect")


async def test_same_unchanged_menu_app_on_simulated_profiles(
    control_server: tuple[str, str],
) -> None:
    """Simulated profiles emit simulated_intent natively: no decoder, no router, no operator
    authorization (documented); the unchanged menu app follows them and the MI source."""
    from brainos.sdk import RuntimeClient

    base, model_id = control_server
    menu_mod = load_app("menu_app")
    menu, stop = menu_mod.MenuApp(), asyncio.Event()
    runner = asyncio.create_task(menu_mod.run(menu, base, stop))
    async with RuntimeClient(base) as op, httpx.AsyncClient(base_url=base + "/api/v1") as http:
        await op.connect("sim-b")  # selection + text
        await wait_for(lambda: menu.status == "active" and menu.can_act, timeout=10)
        for _ in range(3):
            assert (await http.post("/sim/select")).status_code == 200
        await http.post("/sim/text", json={"text": "hi"})
        await wait_for(
            lambda: menu.actions.get("primary", 0) >= 3 and "hi" in menu.message, timeout=10
        )
        assert ("simulated_intent", None) in menu.provenance
        # the same app instance on the decoded synthetic source, once authorized
        await op.switch("test-mi")
        await wait_for(lambda: menu.status == "suspended", timeout=10)
        await op.authorize_app("reference-menu", ["selection", "text_intent"])
        rules = [
            *RULES,
            {
                "output": "rest",
                "action": "text",
                "text": "ok",
                "threshold": 0.7,
                "hold_ms": 400,
                "refractory_ms": 3000,
            },
        ]
        await op.start_pipeline(
            "band_power", model_id=model_id, router={"enabled": True, "discrete": rules}, **BAND
        )
        n = _total(menu)
        await wait_for(lambda: _total(menu) >= n + 3, timeout=20)
        await wait_for(lambda: "ok" in menu.message, timeout=20)
        assert ("decoded_intent", model_id) in menu.provenance
        await op.disconnect()
    stop.set()
    await runner
