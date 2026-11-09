"""What exactly was tested: plugin identity (entry point, distribution, file hashes) and the
environment the run happened in.

Plugin identity is collected by a small stdlib-only script run with the SAME interpreter and
``PYTHONPATH`` as the plugin host, so it sees the same installed distributions. The script
reads package metadata and hashes files; it never imports plugin code.
"""

from __future__ import annotations

import contextlib
import json
import os
import platform
import subprocess
import sys
from collections.abc import Sequence
from importlib import metadata
from pathlib import Path
from typing import Any

from concord_adapter_sdk import API_VERSION
from concord_adapter_sdk import __version__ as SDK_VERSION

from concord_certify import REPORT_VERSION, __version__

IDENTITY_TIMEOUT_S = 60.0

# Runs in the plugin host's interpreter: stdlib only, prints one JSON document.
IDENTITY_SCRIPT = r"""
import base64, hashlib, importlib.metadata as md, importlib.util, json, os, re, sys

GROUP = "concord.sources"
MAX_FILES = 2000
ref = sys.argv[1]
want_versions = sys.argv[2:]
out = {"ref": ref, "kind": None, "entry_point": None, "distribution": None, "module": None,
       "versions": {}, "errors": []}

def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h

def version_of(name):
    try:
        return md.version(name)
    except md.PackageNotFoundError:
        return None

dist = None
module = None
if ":" in ref:
    out["kind"] = "module"
    module = ref.split(":", 1)[0]
    top = module.split(".")[0]
    names = sorted(set(md.packages_distributions().get(top, [])))
    if len(names) == 1:
        try:
            dist = md.distribution(names[0])
        except md.PackageNotFoundError:
            dist = None
else:
    out["kind"] = "entry_point"
    eps = list(md.entry_points(group=GROUP, name=ref))
    providers = sorted({ep.dist.name if ep.dist else "?" for ep in eps})
    out["entry_point"] = {"group": GROUP, "name": ref, "count": len(eps),
                          "value": eps[0].value if len(eps) == 1 else None,
                          "providers": providers}
    if len(eps) == 1:
        dist = eps[0].dist
        module = eps[0].value.split(":", 1)[0]

if dist is not None:
    d = {"name": dist.metadata["Name"], "version": dist.version, "editable": False,
         "direct_url": None, "requires": [], "record": None}
    raw = dist.read_text("direct_url.json")
    if raw:
        try:
            du = json.loads(raw)
            d["direct_url"] = du.get("url")
            d["editable"] = bool((du.get("dir_info") or {}).get("editable"))
        except ValueError:
            out["errors"].append("direct_url.json is not valid JSON")
    for req in dist.requires or []:
        if "extra ==" in req:
            continue
        m = re.match(r"^\s*([A-Za-z0-9][A-Za-z0-9._-]*)", req)
        if m:
            d["requires"].append({"requirement": req, "installed": version_of(m.group(1))})
    record = dist.read_text("RECORD")
    if record is not None:
        files = verified = unhashed = 0
        mismatched, missing = [], []
        for line in record.splitlines():
            if not line.strip():
                continue
            parts = line.rsplit(",", 2)
            if len(parts) != 3:
                continue
            path, digest, _size = parts
            files += 1
            if not digest:
                unhashed += 1
                continue
            algo, _, expected = digest.partition("=")
            target = dist.locate_file(path)
            if not os.path.isfile(target):
                missing.append(path)
                continue
            if algo != "sha256":
                unhashed += 1
                continue
            got = base64.urlsafe_b64encode(sha256(target).digest()).rstrip(b"=").decode()
            if got == expected:
                verified += 1
            else:
                mismatched.append(path)
        d["record"] = {"files": files, "verified": verified, "unhashed": unhashed,
                       "mismatched": mismatched[:50], "missing": missing[:50],
                       "sha256": hashlib.sha256(record.encode()).hexdigest()}
    out["distribution"] = d

if module:
    top = module.split(".")[0]
    try:
        spec = importlib.util.find_spec(top)  # top-level only: does not execute the package
    except (ImportError, ValueError) as exc:
        spec = None
        out["errors"].append(f"cannot locate module {top!r}: {exc}")
    if spec is not None:
        paths = []
        root = None
        if spec.submodule_search_locations:
            root = list(spec.submodule_search_locations)[0]
            for dirpath, dirnames, filenames in os.walk(root):
                dirnames[:] = sorted(x for x in dirnames if x != "__pycache__")
                for fn in sorted(filenames):
                    if not fn.endswith((".pyc", ".pyo")):
                        paths.append(os.path.join(dirpath, fn))
        elif spec.origin and os.path.isfile(spec.origin):
            root = os.path.dirname(spec.origin)
            paths = [spec.origin]
        entries = []
        tree = hashlib.sha256()
        for p in sorted(paths)[:MAX_FILES]:
            rel = os.path.relpath(p, root).replace(os.sep, "/")
            digest = sha256(p).hexdigest()
            entries.append({"path": rel, "sha256": digest, "bytes": os.path.getsize(p)})
            tree.update(f"{rel}\0{digest}\n".encode())
        out["module"] = {"name": module, "package": top, "path": root,
                         "files": entries, "file_count": len(paths),
                         "tree_sha256": tree.hexdigest()}

for name in want_versions:
    out["versions"][name] = version_of(name)
print(json.dumps(out))
"""


def host_env(extra_path: Sequence[str] = ()) -> dict[str, str]:
    """Environment of the plugin host (same rule as Concord: extra paths first)."""
    env = dict(os.environ)
    paths = [*extra_path, *([env["PYTHONPATH"]] if env.get("PYTHONPATH") else [])]
    if paths:
        env["PYTHONPATH"] = os.pathsep.join(paths)
    env["PYTHONUNBUFFERED"] = "1"
    return env


def collect_identity(
    ref: str,
    *,
    python: str | None = None,
    extra_path: Sequence[str] = (),
    versions: Sequence[str] = (),
) -> dict[str, Any]:
    """Plugin identity as seen by the host interpreter (never imports plugin code)."""
    cmd = [python or sys.executable, "-c", IDENTITY_SCRIPT, ref, *versions]
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            env=host_env(extra_path),
            timeout=IDENTITY_TIMEOUT_S,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"ref": ref, "error": f"identity probe failed: {exc}"}
    if proc.returncode != 0:
        tail = " | ".join(proc.stderr.strip().splitlines()[-3:])
        return {"ref": ref, "error": f"identity probe exited {proc.returncode}: {tail}"[:500]}
    try:
        doc = json.loads(proc.stdout)
    except ValueError as exc:
        return {"ref": ref, "error": f"identity probe printed invalid JSON: {exc}"}
    if not isinstance(doc, dict):
        return {"ref": ref, "error": "identity probe printed an unexpected document"}
    path = (doc.get("module") or {}).get("path")
    if isinstance(path, str):
        doc["git"] = git_info(Path(path))
    return doc


def git_info(path: Path) -> dict[str, Any] | None:
    """Commit and cleanliness of the source tree, if it lives in a git work tree."""

    def git(*args: str) -> str | None:
        try:
            p = subprocess.run(
                ["git", "-C", str(path), *args],
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            return None
        return p.stdout.strip() if p.returncode == 0 else None

    commit = git("rev-parse", "HEAD")
    if not commit:
        return None
    status = git("status", "--porcelain", "--", ".")
    return {
        "commit": commit,
        "dirty": bool(status),
        "dirty_files": (status or "").count("\n") + 1 if status else 0,
    }


def _cpu_model() -> str | None:
    with contextlib.suppress(OSError):
        for line in Path("/proc/cpuinfo").read_text(encoding="utf-8").splitlines():
            if line.lower().startswith("model name"):
                return line.split(":", 1)[1].strip()
    return platform.processor() or None


def _mem_total_mib() -> int | None:
    with contextlib.suppress(OSError, ValueError, IndexError):
        for line in Path("/proc/meminfo").read_text(encoding="utf-8").splitlines():
            if line.startswith("MemTotal:"):
                return int(line.split()[1]) // 1024
    return None


def concord_version() -> str | None:
    try:
        return metadata.version("concordos")
    except metadata.PackageNotFoundError:
        return None


def environment(host_hello: dict[str, Any] | None = None) -> dict[str, Any]:
    """Machine and software the run happened on (no host name, no user name)."""
    env: dict[str, Any] = {
        "os": platform.system(),
        "os_release": platform.release(),
        "platform": platform.platform(),
        "machine": platform.machine(),
        "cpu_model": _cpu_model(),
        "cpu_count": os.cpu_count(),
        "memory_total_mib": _mem_total_mib(),
        "python": platform.python_version(),
        "python_implementation": platform.python_implementation(),
        "certify_version": __version__,
        "report_version": REPORT_VERSION,
        "sdk_version": SDK_VERSION,
        "sdk_api_version": API_VERSION,
        "concord_version": concord_version(),
        "host_python": None,
        "host_sdk_version": None,
        "host_api_version": None,
    }
    if host_hello:
        env["host_python"] = host_hello.get("python")
        env["host_sdk_version"] = host_hello.get("sdk_version")
        env["host_api_version"] = host_hello.get("api_version")
    return env
