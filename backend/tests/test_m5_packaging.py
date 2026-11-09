"""Milestone 5 (D): the desktop bundle's entry point routing (packaging/app_entry.py) and the
staged-console lookup. The bundle itself is built and smoke-tested by packaging/build_app.py and
packaging/smoke_test.py (CI jobs package-linux, package-macos and package-windows)."""

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
            ["-m", "concord_adapter_sdk.host", "--list"],
            "module",
            ["concord_adapter_sdk.host", "--list"],
        ),
        (  # the isolated decoder host (M5-A) runs from the bundle too
            ["-m", "concord_decoder_sdk.host", "--model", "m.json"],
            "module",
            ["concord_decoder_sdk.host", "--model", "m.json"],
        ),
        (["-m", "os"], "refuse", ["os"]),  # the bundle is not a general Python interpreter
        (["-c", "print(1)"], "app", ["-c", "print(1)"]),
        (["doctor", "--json", "x.json"], "cli", ["doctor", "--json", "x.json"]),
        (["status"], "cli", ["status"]),
        # 0.3.1: test streams for rehearsing without hardware, from the app's own program
        (
            ["publish", "lsl-ephys", "--channels", "8"],
            "cli",
            ["publish", "lsl-ephys", "--channels", "8"],
        ),
        (["--version"], "cli", ["--version"]),
        ([], "app", []),
        (["--headless", "--port", "8010"], "app", ["--headless", "--port", "8010"]),
    ],
)
def test_bundle_entry_routing(argv: list[str], kind: str, args: list[str]) -> None:
    entry = _load("app_entry")
    assert entry.route(argv) == (kind, args)


@pytest.mark.parametrize(
    ("argv", "kind", "args"),
    [
        ([], "cli", ["--help"]),  # the console program never opens the desktop app
        (["stop"], "cli", ["stop"]),
        (["--headless"], "cli", ["--headless"]),  # argparse explains it is not a command
        (["-m", "concord_adapter_sdk.host", "x"], "module", ["concord_adapter_sdk.host", "x"]),
        (["-m", "os"], "refuse", ["os"]),
    ],
)
def test_windows_console_program_is_the_concord_command(
    argv: list[str], kind: str, args: list[str]
) -> None:
    """Windows ships Concord.exe (windowed) and concord-cli.exe (console) from one entry
    point; concord-cli.exe answers like the `concord` command."""
    entry = _load("app_entry")
    assert entry.route(argv, cli_program=True) == (kind, args)
    assert entry.is_cli_program(r"C:\Users\a\Downloads\Concord\concord-cli.exe")
    assert entry.is_cli_program("/x/CONCORD-CLI.EXE")  # Windows names ignore case
    assert not entry.is_cli_program(r"C:\Users\a\Downloads\Concord\Concord.exe")


def test_windows_icon_is_a_valid_ico() -> None:
    """The program and window icon is drawn at build time (packaging/make_icon.py)."""
    import struct

    icon = _load("make_icon")
    data = icon.ico()
    reserved, kind, count = struct.unpack_from("<HHH", data)
    assert (reserved, kind, count) == (0, 1, len(icon.SIZES))
    for i, size in enumerate(icon.SIZES):
        w, h, _, _, planes, bpp, length, offset = struct.unpack_from("<BBBBHHII", data, 6 + 16 * i)
        assert (w, h) == (size % 256, size % 256) and planes == 1 and bpp == 32
        header = struct.unpack_from("<IiiHHI", data, offset)
        assert header == (40, size, 2 * size, 1, 32, 0)  # BITMAPINFOHEADER, XOR + AND rows
        assert offset + length <= len(data)
    px = icon.pixels(32)
    assert px[0][3] == 0 and px[16 * 32 + 4][3] == 255  # transparent corner, opaque inside


def test_windows_download_zip_has_the_concord_folder_at_its_top(tmp_path: Path) -> None:
    import zipfile

    build = _load("build_app")
    folder = tmp_path / "Concord"
    (folder / "_internal" / "sub").mkdir(parents=True)
    (folder / "Concord.exe").write_bytes(b"MZ")
    (folder / "_internal" / "sub" / "x.pyd").write_bytes(b"x")
    out = build.make_zip(folder, tmp_path / "Concord-0.0.0-windows-x86_64.zip")
    with zipfile.ZipFile(out) as zf:
        assert sorted(zf.namelist()) == ["Concord/Concord.exe", "Concord/_internal/sub/x.pyd"]


def test_desktop_ignores_the_finder_process_serial_number() -> None:
    from concord.desktop import parse

    args = parse(["-psn_0_12345", "--no-browser", "--port", "8123"])
    assert args.no_browser and args.port == 8123 and not args.headless


def test_packaged_console_is_preferred_outside_a_checkout(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from concord import config

    console = tmp_path / "console"
    console.mkdir()
    (console / "index.html").write_text("<title>Concord</title>", encoding="utf-8")
    monkeypatch.setattr(config, "source_checkout", lambda: None)
    monkeypatch.setattr(config, "packaged_console_dir", lambda: console)
    assert config.default_static_dir() == console
    assert config.default_data_dir() == config.user_dir() / "data"
    (console / "index.html").unlink()
    assert config.default_static_dir() is None  # API only; never a wrong directory


def test_publish_command_hands_its_arguments_to_the_test_publishers(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """`concord publish …` is `python -m concord.testing.publish …` (also inside the app)."""
    from concord.cli import main

    with pytest.raises(SystemExit) as exc:
        main(["publish", "--help"])
    assert exc.value.code == 0
    out = capsys.readouterr().out
    assert "lsl-ephys" in out and "openephys" in out and "falcon" in out


def test_dataset_command_explains_an_unknown_dataset(capsys: pytest.CaptureFixture[str]) -> None:
    """Regression (0.3.1): `concord dataset t15` crashed with a KeyError traceback."""
    from concord.cli import main

    assert main(["dataset", "t15", "--list"]) == 2
    err = capsys.readouterr().err
    assert "unknown dataset 't15'" in err and "falcon-h1" in err and "Dryad" in err


def test_messages_name_the_desktop_apps_own_program(monkeypatch: pytest.MonkeyPatch) -> None:
    """A desktop app has no `concord` command: its stop hint names the app's program (regression)."""
    from concord import oscompat
    from concord.config import command_hint

    # the Windows form is tested in test_m5_windows
    monkeypatch.setattr(oscompat, "is_windows", lambda: False)
    monkeypatch.delattr(sys, "frozen", raising=False)
    assert command_hint("stop") == "concord stop"
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", "/home/me/Downloads/Concord/Concord")
    assert command_hint("stop") == "/home/me/Downloads/Concord/Concord stop"
    monkeypatch.setattr(sys, "executable", "/Users/me/My Apps/Concord.app/Contents/MacOS/Concord")
    assert command_hint("stop") == '"/Users/me/My Apps/Concord.app/Contents/MacOS/Concord" stop'
