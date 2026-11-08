# PyInstaller spec for the BrainOS desktop app. Build with: python packaging/build_app.py
#
# One-directory bundle (fast start, no unpacking to a temp directory on every launch):
#   macOS: dist/BrainOS.app (windowed .app, ad-hoc signed by PyInstaller, NOT notarized)
#   Linux: dist/BrainOS/BrainOS (same layout; used to validate the packaging on CI and locally)
#
# Bundled: CPython, BrainOS (server, console, processing, NWB, LSL, Open Ephys), the source
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
CONSOLE = SRC / "brainos" / "server" / "console"
if not (CONSOLE / "index.html").is_file():
    raise SystemExit("the console is not staged: python packaging/stage_console.py --build")
VERSION = re.search(r'__version__ = "([^"]+)"', (SRC / "brainos" / "__init__.py").read_text())[1]
MAC = sys.platform == "darwin"

hiddenimports = [
    *collect_submodules("brainos"),
    *collect_submodules("brainos_adapter_sdk"),
    *collect_submodules("brainos_decoder_sdk"),  # isolated decoder host (M5-A)
    *collect_submodules("brainos_bci2000"),
    *collect_submodules("uvicorn"),
    *collect_submodules("hdmf"),
    *collect_submodules("pynwb"),
    "tkinter",
]
datas = [(str(CONSOLE), "brainos/server/console")]
datas += collect_data_files("brainos", excludes=["server/console/**"])  # dataset manifests
datas += collect_data_files("pynwb") + collect_data_files("hdmf")  # NWB schema files
# package metadata: versions in support reports and export manifests, and the plugin entry
# points (`brainos.sources`) that plugin discovery reads
for dist in (
    "brainos",
    "brainos-adapter-sdk",
    "brainos-decoder-sdk",
    "brainos-bci2000",
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
    # which would raise the app's minimum above the 14.0 it declares. BrainOS then uses its
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
    name="BrainOS",
    console=not MAC,  # macOS: a windowed .app; Linux: keep stdout for the smoke test
    argv_emulation=False,
    codesign_identity=None,  # unsigned (ad-hoc on Apple Silicon); see docs/INSTALL_MAC.md
    entitlements_file=None,
)
coll = COLLECT(exe, a.binaries, a.datas, name="BrainOS")  # noqa: F821
if MAC:
    app = BUNDLE(  # noqa: F821
        coll,
        name="BrainOS.app",
        bundle_identifier="org.brainos.desktop",
        version=VERSION,
        info_plist={
            "CFBundleName": "BrainOS",
            "CFBundleDisplayName": "BrainOS",
            "CFBundleShortVersionString": VERSION,
            "CFBundleVersion": VERSION,
            # numpy/scipy arm64 wheels pip selects on current macOS link Accelerate and are
            # built for macOS 14; a clear "requires macOS 14" beats a crash on older systems
            "LSMinimumSystemVersion": "14.0",
            "NSHighResolutionCapable": True,
            "NSHumanReadableCopyright": "Research use only. Not a medical device.",
        },
    )
