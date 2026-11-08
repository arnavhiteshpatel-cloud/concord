"""Copy the built console (frontend/dist) into the Python package for wheels and the app.

    python packaging/stage_console.py [--build]

``--build`` runs ``npm ci && npm run build`` in frontend/ first. The staged copy lives in
backend/src/brainos/server/console/ (git-ignored); hatch ships it in the wheel
(``artifacts``), PyInstaller in the app. Without it, a wheel install serves the API only and
``brainos start`` says so.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "frontend" / "dist"
TARGET = ROOT / "backend" / "src" / "brainos" / "server" / "console"


def build() -> None:
    npm = shutil.which("npm")
    if npm is None:
        raise SystemExit("npm not found: install Node 20+ to build the console")
    if not (ROOT / "frontend" / "node_modules").is_dir():
        subprocess.run([npm, "ci"], cwd=ROOT / "frontend", check=True)
    subprocess.run([npm, "run", "build"], cwd=ROOT / "frontend", check=True)


def stage() -> Path:
    if not (DIST / "index.html").is_file():
        raise SystemExit(f"no built console in {DIST}; run with --build (or `make build`)")
    if TARGET.exists():
        shutil.rmtree(TARGET)
    shutil.copytree(DIST, TARGET)
    return TARGET


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--build", action="store_true", help="build the console with npm first")
    args = ap.parse_args(argv)
    if args.build:
        build()
    target = stage()
    files = sum(1 for p in target.rglob("*") if p.is_file())
    print(f"console staged: {target} ({files} files)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
