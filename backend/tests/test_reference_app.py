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
    allowed_prefix = "brainos.sdk"
    stdlib = set(sys.stdlib_module_names) | {"__future__"}
    for path in APP_DIR.glob("*.py"):
        for node in ast.walk(ast.parse(path.read_text())):
            names: list[str] = []
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [node.module or ""]
            for n in names:
                ok = n.split(".")[0] in stdlib or n == allowed_prefix
                assert ok, f"{path.name} imports {n}; reference apps may use only brainos.sdk"
        text = path.read_text()
        for word in ("sim-a", "sim-b", "lsl:", "openephys", "nwb:", "falcon"):
            assert word not in text.lower(), f"{path.name} mentions device/source {word!r}"


def test_app_state_machine_ignores_events_when_not_granted() -> None:
    app_mod = _load_app()
    from brainos.contracts.protocol import AppStatus, NegotiationResult
    from brainos.sdk import NegotiationUpdate

    from .helpers import valid_event

    app = app_mod.CursorApp()
    app.handle(
        NegotiationUpdate(
            NegotiationResult(device_id=None, status=AppStatus.SUSPENDED, granted=[], rejected=[])
        )
    )
    from brainos.contracts import parse_envelope

    env = parse_envelope(valid_event("intent.pointer"))
    app.handle(env)
    assert app.commands == 0 and app.ignored == 1 and (app.x, app.y) == (0.0, 0.0)


async def test_same_app_unchanged_across_sources(
    live_server: str, tmp_path: Path, publishers: list[Any]
) -> None:
    pytest.importorskip("pylsl")
    pytest.importorskip("scipy")
    pytest.importorskip("zmq")
    from brainos.sdk import BrainOSError, RuntimeClient
    from brainos.testing.lsl_publishers import FalconLSLPublisher

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

        # 3) operator enables the router -> decoded commands reach the unchanged app
        await op.set_router(enabled=True, x_dim="tx", y_dim="ty", gain=0.5)
        await wait_for(lambda: app.status == "active" and app.commands >= n0 + 50, timeout=15)

        # an incompatible request is refused with a reason, through the SDK
        with pytest.raises(BrainOSError) as exc:
            await op.start_pipeline("spikeband_threshold")
        assert exc.value.code == "capability_unsupported"

        # 4) Open Ephys ZMQ (synthetic test publisher): raw signal only -> suspended again
        from brainos.adapters.openephys.publisher import OpenEphysTestPublisher

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
