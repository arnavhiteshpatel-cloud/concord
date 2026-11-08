"""Helpers for plugin tests: test-plugin path, temporary entry points, adapter specs."""

from __future__ import annotations

import importlib
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from concord_adapter_sdk import PluginManifest

from concord.adapters.plugin import PluginSpec

PLUGINS_DIR = Path(__file__).parent / "plugins"
TEST_MODULE = "concord_test_plugins"
# tests may import the test plugins directly (e.g. to compute expected values); the runtime
# under test never does - it reaches them through plugin-host subprocesses.
if str(PLUGINS_DIR) not in sys.path:
    sys.path.insert(0, str(PLUGINS_DIR))


def ref(cls_name: str) -> str:
    return f"{TEST_MODULE}:{cls_name}"


def make_dist(site: Path, entries: Mapping[str, str], name: str = "concord-test-plugins") -> Path:
    """A minimal installed distribution (``*.dist-info``) declaring ``concord.sources``
    entry points, so discovery can be tested without installing anything."""
    site.mkdir(parents=True, exist_ok=True)
    info = site / f"{name.replace('-', '_')}-0.0.1.dist-info"
    info.mkdir(exist_ok=True)
    (info / "METADATA").write_text(f"Metadata-Version: 2.1\nName: {name}\nVersion: 0.0.1\n")
    lines = ["[concord.sources]", *(f"{k} = {v}" for k, v in entries.items())]
    (info / "entry_points.txt").write_text("\n".join(lines) + "\n")
    return site


def manifest_of(cls_name: str) -> PluginManifest:
    mod = importlib.import_module(TEST_MODULE)
    m: PluginManifest = getattr(mod, cls_name).manifest
    return m


def spec(cls_name: str, *, device_key: str = "dev0", **over: Any) -> PluginSpec:
    options = over.pop("options", {"fail_after": 0, "unit": "microvolts"})
    base: dict[str, Any] = {
        "device_id": f"plugin:test:{cls_name.lower()}"[:64],
        "entry_point": ref(cls_name),
        "device_key": device_key,
        "options": options,
        "manifest": manifest_of(cls_name),
        "extra_path": (str(PLUGINS_DIR),),
        "start_timeout_s": 10.0,
        "open_timeout_s": 10.0,
        "read_grace_s": 1.5,
    }
    base.update(over)
    return PluginSpec(**base)
