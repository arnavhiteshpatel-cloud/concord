"""What is installed: platform, package versions with build fingerprints, plugins.

Used by session export manifests (reproducibility) and by ``brainos doctor`` (support). It
reads package metadata only; plugin code is never imported here. Stdlib only.

A package *fingerprint* is the SHA-256 of its installed ``RECORD`` file, which itself lists a
hash of every installed file: two installs with the same fingerprint have identical files.
Editable (development) installs are flagged; their fingerprint does not cover the sources.
"""

from __future__ import annotations

import hashlib
import importlib.metadata as md
import json
import platform
import sys
from typing import Any

from brainos import __version__

# BrainOS packages first, then the dependencies that shape results or connectivity.
PACKAGES = (
    "brainos",
    "brainos-adapter-sdk",
    "brainos-decoder-sdk",
    "brainos-certify",
    "brainos-bci2000",
    "brainos-brainflow",
    "brainos-example-adapter",
    "pydantic",
    "fastapi",
    "uvicorn",
    "httpx",
    "websockets",
    "numpy",
    "scipy",
    "pynwb",
    "h5py",
    "pylsl",
    "pyzmq",
    "brainflow",
)
PLUGIN_GROUP = "brainos.sources"


def package(name: str) -> dict[str, Any]:
    try:
        dist = md.distribution(name)
    except md.PackageNotFoundError:
        return {"name": name, "installed": False, "version": None}
    record = dist.read_text("RECORD")
    direct = dist.read_text("direct_url.json")
    editable = False
    if direct:
        try:
            editable = bool(json.loads(direct).get("dir_info", {}).get("editable"))
        except ValueError:
            editable = False
    return {
        "name": name,
        "installed": True,
        "version": dist.version,
        "editable": editable,
        "fingerprint": hashlib.sha256(record.encode()).hexdigest() if record else None,
    }


def packages(names: tuple[str, ...] = PACKAGES) -> list[dict[str, Any]]:
    return [package(n) for n in names]


def plugins() -> list[dict[str, Any]]:
    """Installed source plugins (entry points), without importing them."""
    out: list[dict[str, Any]] = []
    for ep in sorted(md.entry_points(group=PLUGIN_GROUP), key=lambda e: e.name):
        dist = getattr(ep, "dist", None)
        out.append(
            {
                "name": ep.name,
                "entry": ep.value,
                "package": dist.metadata["Name"] if dist is not None else None,
                "version": dist.version if dist is not None else None,
            }
        )
    return out


def platform_info() -> dict[str, Any]:
    """No host name, user name or paths: only what determines behaviour."""
    info: dict[str, Any] = {
        "system": platform.system(),
        "release": platform.release(),
        "machine": platform.machine(),
        "python": platform.python_version(),
        "implementation": platform.python_implementation(),
        "frozen_app": bool(getattr(sys, "frozen", False)),
        "brainos": __version__,
    }
    if sys.platform == "darwin":
        info["macos"] = platform.mac_ver()[0]
    return info
