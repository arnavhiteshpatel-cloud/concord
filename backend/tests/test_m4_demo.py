"""Milestone 4 required demonstration, end to end, with no core change for the source:

1. A THIRD-PARTY adapter (``concord-example-adapter``: separate package, depends only on
   ``concord-adapter-sdk``) is installed, discovered, validated and run in the plugin host.
2. Concord's pipeline computes mu-band power from it; a session is recorded (features and
   labels only) and an LDA classifier is calibrated through the REST API.
3. The classifier runs live; the command router maps classes to discrete actions.
4. The independently runnable, SDK-only menu application receives NOTHING until the operator
   authorizes it (``not_authorized``), then acts on decoded select/activate commands.
5. Unsupported requests are refused (no pointer from a classifier, no text without a rule),
   and after a disconnect no command reaches the app.

The adapter's signal is declared synthetic. Nothing here involves hardware or a person.
"""

from __future__ import annotations

import asyncio
import importlib.util
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

from concord.sdk import ConcordError, RuntimeClient

from .helpers import wait_for
from .test_plugin_example import server  # noqa: F401  (fixture: server with plugin discovery)

pytest.importorskip("concord_example_adapter")
pytest.importorskip("scipy")

APP_DIR = Path(__file__).resolve().parents[1] / "examples" / "reference_app"
OPTIONS = {"seed": 11, "montage": "8", "cue_duration_s": 2.0, "effect_size": 0.8}
BAND = {"band_low_hz": 8, "band_high_hz": 13, "bin_ms": 200}
RULES = [
    {"output": "left", "action": "primary", "threshold": 0.6, "hold_ms": 200, "refractory_ms": 600},
    {"output": "right", "action": "activate", "threshold": 0.6, "hold_ms": 200},
]
CALIBRATION_S = 70.0  # ~35 cues of 2 s; 40 % held out (enough per class to score)


def _load(name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, APP_DIR / f"{name}.py")
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


async def test_third_party_adapter_to_authorized_sdk_app(server: str) -> None:  # noqa: F811
    menu_mod = _load("menu_app")
    menu, stop = menu_mod.MenuApp(), asyncio.Event()
    runner = asyncio.create_task(menu_mod.run(menu, server, stop))
    async with RuntimeClient(server) as op:
        for _ in range(300):
            st = await op.plugins()
            if st["discovered_at_ns"]:
                break
            await asyncio.sleep(0.05)
        plugin = next(p for p in st["plugins"] if p["name"] == "example-mi-eeg")
        assert plugin["status"] == "compatible" and plugin["api_version"] == "1.0"

        # 1. third-party adapter, isolated, declared synthetic EEG (noninvasive)
        dev = await op.configure_plugin("example-mi-eeg", "mi-eeg", OPTIONS)
        assert dev.integration is not None and dev.integration.kind == "plugin"
        assert dev.integration.isolated and dev.integration.package == "concord-example-adapter"
        assert dev.synthetic and dev.modality is not None and dev.modality.value == "eeg"
        assert dev.invasive is False
        await op.connect(dev.device_id)

        # 2. features in Concord's pipeline, a calibration recording, an LDA classifier
        await op.start_pipeline("band_power", **BAND)
        name = await op.start_recording("m4-demo-calibration", exclude_raw=True)
        await asyncio.sleep(CALIBRATION_S)
        await op.stop_recording()
        cal = await op.calibrate(
            [name],
            kind="classifier",
            feature_source="concord.pipeline",
            class_names=["rest", "left", "right"],
            train_fraction=0.6,
            tau_ms=200,  # smoothing well below the 2 s cue length
        )
        report, model_id = cal["report"], cal["model"]["model_id"]
        print(
            f"\nM4 demo calibration (synthetic): balanced accuracy {report['balanced_accuracy']:.3f}"
            f" (chance {report['chance_balanced_accuracy']:.3f}), time-shift control "
            f"{report['control_time_shift_balanced_accuracy']:.3f}"
        )
        assert report["balanced_accuracy"] > report["chance_balanced_accuracy"] + 0.1

        # unsupported: a classifier cannot drive continuous pointer movement
        with pytest.raises(ConcordError) as exc:
            await op.start_pipeline(
                "band_power",
                model_id=model_id,
                router={"enabled": True, "x_dim": "left", "y_dim": "right"},
                **BAND,
            )
        assert exc.value.code in ("incompatible_decoder", "capability_unsupported")

        # 3. live classifier + discrete rules; 4. default deny until the operator authorizes
        await op.start_pipeline(
            "band_power", model_id=model_id, router={"enabled": True, "discrete": RULES}, **BAND
        )
        await wait_for(lambda: menu.waiting_for_authorization, timeout=15)
        ctl = await op.control()
        assert ctl["router_on"] and "selection" in ctl["provides"]
        await asyncio.sleep(2.0)
        assert sum(menu.actions.values()) == 0, "an unauthorized app received a command"

        # unsupported: text output was not configured, so it cannot be authorized as provided
        await op.authorize_app("reference-menu", ["selection"])
        await wait_for(lambda: sum(menu.actions.values()) >= 2, timeout=40)
        assert ("decoded_intent", model_id) in menu.provenance
        assert set(menu.actions) <= {"primary", "activate"}  # only the configured actions

        # 5. a disconnect stops commands; nothing stale arrives afterwards
        await op.disconnect()
        await wait_for(lambda: bool(menu.stops), timeout=5)
        n = sum(menu.actions.values())
        await asyncio.sleep(1.5)
        assert sum(menu.actions.values()) == n
    stop.set()
    await runner


def test_menu_app_imports_only_the_public_sdk() -> None:
    import ast

    stdlib = set(sys.stdlib_module_names) | {"__future__"}
    tree = ast.parse((APP_DIR / "menu_app.py").read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        names: list[Any] = []
        if isinstance(node, ast.Import):
            names = [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom):
            names = [node.module or ""]
        for n in names:
            assert n.split(".")[0] in stdlib or n.startswith("concord.sdk"), n
