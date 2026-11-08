"""Build the Concord desktop bundle with PyInstaller (and the .dmg on macOS).

    python packaging/build_app.py [--build-console] [--dmg]

Prerequisites in the active Python environment: Concord with the lab extra, the plugin host
SDK and the BCI2000 plugin, and the pinned build tools::

    pip install -e packages/concord-adapter-sdk -e "backend[lab]" -e packages/concord-bci2000
    pip install -r packaging/requirements.txt

Outputs (packaging/dist/, git-ignored):

- macOS: ``Concord.app`` and, with ``--dmg``, ``Concord-<version>-macos-<arch>.dmg``
  (the app plus an Applications shortcut). Unsigned: ad-hoc signature only, not notarized.
- Linux: ``Concord/Concord`` (same layout; validates the packaging, not a Linux installer).

``packaging/smoke_test.py`` then runs the bundle headless and checks it end to end.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PKG = ROOT / "packaging"
DIST = PKG / "dist"
WORK = PKG / "build"


def version() -> str:
    text = (ROOT / "backend" / "src" / "concord" / "__init__.py").read_text()
    m = re.search(r'__version__ = "([^"]+)"', text)
    assert m is not None
    return m.group(1)


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        while chunk := fh.read(1 << 20):
            h.update(chunk)
    return h.hexdigest()


def tree_size(path: Path) -> int:
    return sum(p.stat().st_size for p in path.rglob("*") if p.is_file() and not p.is_symlink())


def macos_minimum(bundle: Path) -> dict[str, object]:
    """The highest `minos` of any Mach-O file in the bundle: the real minimum macOS."""
    otool = shutil.which("otool")
    if otool is None:
        return {"macos_min_required": None, "macos_min_detail": "otool not available"}
    best: tuple[int, ...] = (0,)
    best_file = ""
    for p in bundle.rglob("*"):
        if p.is_symlink() or not p.is_file() or p.suffix not in ("", ".so", ".dylib"):
            continue
        with p.open("rb") as fh:
            magic = fh.read(4)
        if magic not in (b"\xcf\xfa\xed\xfe", b"\xca\xfe\xba\xbe"):  # Mach-O 64 / universal
            continue
        out = subprocess.run([otool, "-l", str(p)], capture_output=True, text=True, check=False)
        for m in re.finditer(r"\bminos (\d+(?:\.\d+)*)", out.stdout):
            ver = tuple(int(x) for x in m.group(1).split("."))
            if ver > best:
                best, best_file = ver, str(p.relative_to(bundle))
    return {
        "macos_min_required": ".".join(map(str, best)) if best != (0,) else None,
        "macos_min_set_by": best_file or None,
    }


def make_dmg(app: Path, out: Path) -> Path:
    hdiutil = shutil.which("hdiutil")
    if hdiutil is None:
        raise SystemExit("hdiutil not found: .dmg images can only be made on macOS")
    with tempfile.TemporaryDirectory() as tmp:
        stage = Path(tmp) / "Concord"
        stage.mkdir()
        # symlinks=True keeps the bundle's internal links (Python.framework layout) intact
        shutil.copytree(app, stage / app.name, symlinks=True)
        os.symlink("/Applications", stage / "Applications")
        out.unlink(missing_ok=True)
        subprocess.run(
            [
                hdiutil,
                "create",
                "-volname",
                "Concord",
                "-srcfolder",
                str(stage),
                "-ov",
                "-format",
                "UDZO",
                str(out),
            ],
            check=True,
        )
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--build-console", action="store_true", help="npm build the console first")
    ap.add_argument("--dmg", action="store_true", help="macOS: also make the .dmg")
    args = ap.parse_args(argv)

    stage = [sys.executable, str(PKG / "stage_console.py")]
    subprocess.run([*stage, "--build"] if args.build_console else stage, check=True)
    subprocess.run(
        [
            sys.executable,
            "-m",
            "PyInstaller",
            "--noconfirm",
            "--clean",
            "--log-level",
            "WARN",
            "--distpath",
            str(DIST),
            "--workpath",
            str(WORK),
            str(PKG / "concord.spec"),
        ],
        check=True,
        cwd=ROOT,
    )
    mac = sys.platform == "darwin"
    bundle = DIST / ("Concord.app" if mac else "Concord")
    exe = bundle / "Contents" / "MacOS" / "Concord" if mac else bundle / "Concord"
    if not exe.is_file():
        raise SystemExit(f"build did not produce {exe}")
    info: dict[str, object] = {
        "version": version(),
        "platform": sys.platform,
        "machine": platform.machine(),
        "python": platform.python_version(),
        "bundle": str(bundle.relative_to(ROOT)),
        "executable": str(exe.relative_to(ROOT)),
        "bundle_bytes": tree_size(bundle),
        "signed": "ad-hoc (PyInstaller default on Apple Silicon); not notarized" if mac else None,
    }
    if mac:
        info.update(macos_minimum(bundle))
        required = str(info.get("macos_min_required") or "0")
        parts = [int(x) for x in required.split(".")]
        if tuple(parts + [0] * (3 - len(parts))) > (14, 0, 0):  # "14.0" is not above 14
            # the app would claim to run where it cannot: fail the build (set_by names the file)
            raise SystemExit(
                f"bundled library {info.get('macos_min_set_by')} needs macOS {required}; the app "
                "declares 14.0 (LSMinimumSystemVersion). Exclude it on macOS or raise the minimum "
                "in concord.spec and docs/INSTALL_MAC.md."
            )
    if args.dmg:
        if not mac:
            raise SystemExit("--dmg needs macOS (hdiutil)")
        dmg = make_dmg(bundle, DIST / f"Concord-{version()}-macos-{platform.machine()}.dmg")
        info.update(
            {
                "dmg": str(dmg.relative_to(ROOT)),
                "dmg_bytes": dmg.stat().st_size,
                "dmg_sha256": sha256(dmg),
            }
        )
    (DIST / "build-info.json").write_text(json.dumps(info, indent=1) + "\n")
    print(json.dumps(info, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
