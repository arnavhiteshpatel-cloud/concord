# PyInstaller spec for the Concord desktop app. Build with: python packaging/build_app.py
#
# One-directory bundle (fast start, no unpacking to a temp directory on every launch):
#   macOS: dist/Concord.app (windowed .app, ad-hoc signed by PyInstaller, NOT notarized)
#   Linux: dist/Concord/Concord (same layout; used to validate the packaging on CI and locally)
#   Windows: dist/Concord/Concord.exe (windowed: the desktop app) and dist/Concord/concord-cli.exe
#     (console: the `concord` command and the helper processes), sharing one _internal folder.
#     Two programs because a Windows program is either windowed or a console program; the names
#     differ in more than case because Windows file names are case-insensitive. Unsigned.
#
# Bundled: CPython, Concord (server, console, processing, NWB, LSL, Open Ephys), the source
# plugin host and the BCI2000 plugin (pure Python). Not bundled: BrainFlow (native libraries
# per board; use the pip installation), developer tools.
# ruff: noqa
# mypy: ignore-errors

import re
import sys
from pathlib import Path

from PyInstaller.utils.hooks import (
    collect_data_files,
    collect_submodules,
    copy_metadata,
)

ROOT = Path(SPECPATH).resolve().parent  # noqa: F821 (provided by PyInstaller)
SRC = ROOT / "backend" / "src"
CONSOLE = SRC / "concord" / "server" / "console"
if not (CONSOLE / "index.html").is_file():
    raise SystemExit("the console is not staged: python packaging/stage_console.py --build")
VERSION = re.search(r'__version__ = "([^"]+)"', (SRC / "concord" / "__init__.py").read_text(encoding="utf-8"))[1]
MAC = sys.platform == "darwin"
WIN = sys.platform == "win32"
# Windows: the program icon, drawn here by packaging/make_icon.py (no binary file in the repo)
ICON = ROOT / "packaging" / "build" / "icon" / "concord.ico"
if WIN:
    sys.path.insert(0, str(ROOT / "packaging"))
    from make_icon import write_ico

    write_ico(ICON)

hiddenimports = [
    *collect_submodules("concord"),
    *collect_submodules("concord_adapter_sdk"),
    *collect_submodules("concord_decoder_sdk"),  # isolated decoder host (M5-A)
    *collect_submodules("concord_bci2000"),
    *collect_submodules("uvicorn"),
    *collect_submodules("hdmf"),
    *collect_submodules("pynwb"),
    "tkinter",
]
if WIN:
    # zmq.asyncio imports it inside a function, on the Proactor event loop (Open Ephys)
    hiddenimports.append("tornado.platform.asyncio")
datas = [(str(CONSOLE), "concord/server/console")]
if WIN:
    datas.append((str(ICON), "."))  # the Tk window's icon (concord.desktop.window_icon)
datas += collect_data_files("concord", excludes=["server/console/**"])  # dataset manifests
datas += collect_data_files("pynwb") + collect_data_files("hdmf")  # NWB schema files
# package metadata: versions in support reports and export manifests, and the plugin entry
# points (`concord.sources`) that plugin discovery reads
for dist in (
    "concordos",
    "concord-adapter-sdk",
    "concord-decoder-sdk",
    "concord-bci2000",
    "pydantic",
    "fastapi",
    "uvicorn",
    "httpx",
    "websockets",
    "numpy",
    "scipy",
    "pynwb",
    "hdmf",
    "h5py",
    "pylsl",
    "pyzmq",
    *(["tornado"] if WIN else []),
):
    try:
        datas += copy_metadata(dist)
    except Exception as exc:  # not installed in the build environment
        print(f"spec: no metadata for {dist}: {exc}")

a = Analysis(  # noqa: F821
    [str(ROOT / "packaging" / "app_entry.py")],
    pathex=[str(SRC)],
    datas=datas,
    hiddenimports=hiddenimports,
    # orjson (M5-E's fast array encoder) is left out on macOS: its macOS wheels require macOS 15,
    # which would raise the app's minimum above the 14.0 it declares. Concord then uses its
    # byte-identical pure-Python encoder (runtime/fastjson.py), ~2.5x slower for raw frames.
    excludes=["pytest", "mypy", "ruff", "IPython", "matplotlib", "notebook", "jupyter"]
    + (["orjson"] if MAC else []),
    noarchive=False,
)
pyz = PYZ(a.pure)  # noqa: F821
exe = EXE(  # noqa: F821
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Concord",
    # macOS: a windowed .app; Windows: windowed Concord.exe (no terminal window on double-click);
    # Linux: keep stdout for the smoke test
    console=not (MAC or WIN),
    argv_emulation=False,
    codesign_identity=None,  # unsigned (ad-hoc on Apple Silicon); see docs/INSTALL_MAC.md
    entitlements_file=None,
    icon=str(ICON) if WIN else None,
    upx=False,  # never compress with UPX (if installed): it breaks DLLs and alarms antivirus
)
executables = [exe]
if WIN:
    executables.append(
        EXE(  # noqa: F821
            pyz,
            a.scripts,
            [],
            exclude_binaries=True,
            name="concord-cli",
            console=True,
            argv_emulation=False,
            icon=str(ICON),
            upx=False,
        )
    )
coll = COLLECT(*executables, a.binaries, a.datas, upx=False, name="Concord")  # noqa: F821
if MAC:
    app = BUNDLE(  # noqa: F821
        coll,
        name="Concord.app",
        bundle_identifier="org.concord.desktop",
        version=VERSION,
        info_plist={
            "CFBundleName": "Concord",
            "CFBundleDisplayName": "Concord",
            "CFBundleShortVersionString": VERSION,
            "CFBundleVersion": VERSION,
            # numpy/scipy arm64 wheels pip selects on current macOS link Accelerate and are
            # built for macOS 14; a clear "requires macOS 14" beats a crash on older systems
            "LSMinimumSystemVersion": "14.0",
            "NSHighResolutionCapable": True,
            "NSHumanReadableCopyright": "Research use only. Not a medical device.",
        },
    )
