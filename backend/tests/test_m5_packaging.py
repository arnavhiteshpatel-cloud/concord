"""Milestone 5 (D): the desktop bundle's entry point routing (packaging/app_entry.py) and the
staged-console lookup. The bundle itself is built and smoke-tested by packaging/build_app.py and
packaging/smoke_test.py (CI jobs package-linux and package-macos)."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest

REPO = Path(__file__).resolve().parents[2]


def _load(name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, REPO / "packaging" / f"{name}.py")
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.mark.parametrize(
    ("argv", "kind", "args"),
    [
        (
            ["-m", "brainos_adapter_sdk.host", "--list"],
            "module",
            ["brainos_adapter_sdk.host", "--list"],
        ),
        (["-m", "os"], "refuse", ["os"]),  # the bundle is not a general Python interpreter
        (["-c", "print(1)"], "app", ["-c", "print(1)"]),
        (["doctor", "--json", "x.json"], "cli", ["doctor", "--json", "x.json"]),
        (["status"], "cli", ["status"]),
        (["--version"], "cli", ["--version"]),
        ([], "app", []),
        (["--headless", "--port", "8010"], "app", ["--headless", "--port", "8010"]),
    ],
)
def test_bundle_entry_routing(argv: list[str], kind: str, args: list[str]) -> None:
    entry = _load("app_entry")
    assert entry.route(argv) == (kind, args)


def test_desktop_ignores_the_finder_process_serial_number() -> None:
    from brainos.desktop import parse

    args = parse(["-psn_0_12345", "--no-browser", "--port", "8123"])
    assert args.no_browser and args.port == 8123 and not args.headless


def test_packaged_console_is_preferred_outside_a_checkout(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from brainos import config

    console = tmp_path / "console"
    console.mkdir()
    (console / "index.html").write_text("<title>BrainOS</title>")
    monkeypatch.setattr(config, "source_checkout", lambda: None)
    monkeypatch.setattr(config, "packaged_console_dir", lambda: console)
    assert config.default_static_dir() == console
    assert config.default_data_dir() == config.user_dir() / "data"
    (console / "index.html").unlink()
    assert config.default_static_dir() is None  # API only; never a wrong directory
