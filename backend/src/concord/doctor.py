"""``concord doctor``: one-command diagnostics and a support report.

The report is meant to be sent to whoever supports a Concord installation, so it contains
facts about the *installation* only. It never contains neural data or personal data:
``EXCLUDED`` lists what is left out, and every string in the report is passed through
``concord.security.redact`` (home directory -> ``~``, host name, e-mail and IP addresses,
secrets, numeric arrays) before it is written.

Works without the server extra (it then reports what is missing). Stdlib only at import.
"""

from __future__ import annotations

import asyncio
import contextlib
import importlib
import json
import logging
import os
import re
import shutil
import socket
import stat
import sys
import tempfile
import time
import urllib.request
from collections.abc import Callable
from pathlib import Path
from typing import Any

from concord import __version__
from concord.config import ConfigError, frozen, load_config, source_checkout
from concord.environment import packages, platform_info, plugins
from concord.security import is_loopback, open_permissions, redact

log = logging.getLogger(__name__)

REPORT_FORMAT = "concord.support-report/1"
EXCLUDED = [
    "neural data of any kind: recordings, dataset files, sample values, features, decoder "
    "outputs, model weights",
    "names of recordings, research sessions, models and sources",
    "operator names, session notes and any other free text entered in Concord",
    "the content of any file in the data directory (only counts, sizes and permissions)",
    "environment variables, the user name, the host name, the home directory path (shown "
    "as ~), e-mail and IP addresses (except loopback)",
    "secrets (none are stored; anything that looks like one in a log line is redacted)",
]
LOG_LEVELS = ("WARNING", "ERROR", "CRITICAL")
LOG_LINE = re.compile(r"^\S+ \S+ (WARNING|ERROR|CRITICAL)\s")
OPEN_EPHYS_PORTS = (5556, 5557)
BCI2000_PORT = 20321
DISK_WARN_BYTES = 2 * 1024**3
DISK_FAIL_BYTES = 200 * 1024**2


def _check(
    cid: str, title: str, status: str, detail: str, hint: str | None = None
) -> dict[str, Any]:
    out = {"id": cid, "title": title, "status": status, "detail": detail}
    if hint:
        out["hint"] = hint
    return out


def _import_version(module: str, attr: Callable[[Any], str] | None = None) -> tuple[bool, str]:
    try:
        mod = importlib.import_module(module)
    except Exception as exc:  # ImportError, or a native library that fails to load
        return False, f"{type(exc).__name__}: {exc}"
    try:
        return True, attr(mod) if attr else str(getattr(mod, "__version__", "installed"))
    except Exception as exc:
        return False, f"{type(exc).__name__}: {exc}"


def _port_state(port: int, host: str = "127.0.0.1") -> str:
    with socket.socket() as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            s.bind((host, port))
        except OSError:
            return "in_use"
    return "free"


def _udp_port_free(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        try:
            s.bind(("127.0.0.1", port))
        except OSError:
            return False
    return True


def _get(url: str, timeout: float = 2.0) -> Any:
    with urllib.request.urlopen(url, timeout=timeout) as r:
        return json.loads(r.read())


# --------------------------------------------------------------------------- sections


def _install(cfg_check: dict[str, Any]) -> dict[str, Any]:
    kind = "desktop app" if frozen() else ("source checkout" if source_checkout() else "package")
    return {"version": __version__, "install": kind, "config": cfg_check}


def _config_check(config_path: Path | None) -> tuple[dict[str, Any], dict[str, Any]]:
    try:
        cfg = load_config(config_path)
    except ConfigError as exc:
        c = _check(
            "config",
            "Config file",
            "fail",
            str(exc),
            "fix or remove the file; see docs/SECURITY.md",
        )
        return {"path": str(config_path) if config_path else None, "valid": False}, c
    info: dict[str, Any] = {
        "path": str(cfg.path),
        "exists": cfg.exists,
        "valid": True,
        "keys": sorted(f"{s}.{k}" for s, body in cfg.values.items() for k in body),
    }
    if not cfg.exists:
        return info, _check("config", "Config file", "ok", "none (safe defaults apply)")
    mode = stat.S_IMODE(cfg.path.stat().st_mode)
    status = "ok" if os.name != "posix" or not mode & (stat.S_IRWXG | stat.S_IRWXO) else "warn"
    hint = None if status == "ok" else f"chmod 600 {cfg.path}"
    return info, _check(
        "config",
        "Config file",
        status,
        f"valid; mode {mode:o}; {len(info['keys'])} key(s) set",
        hint,
    )


def _optional() -> list[dict[str, Any]]:
    checks = []
    ok, v = _import_version("numpy")
    ok2, v2 = _import_version("scipy")
    checks.append(
        _check(
            "dsp",
            "Signal processing (numpy, scipy)",
            "ok" if ok and ok2 else "warn",
            f"numpy {v}; scipy {v2}" if ok and ok2 else f"numpy: {v}; scipy: {v2}",
            None if ok and ok2 else "pipeline and calibration need: pip install 'concordos[dsp]'",
        )
    )
    ok, v = _import_version("pynwb")
    checks.append(
        _check(
            "nwb",
            "NWB datasets (pynwb)",
            "ok" if ok else "warn",
            v,
            None if ok else "offline datasets need: pip install 'concordos[nwb]'",
        )
    )
    ok, v = _import_version(
        "pylsl", lambda m: f"pylsl {m.__version__}; liblsl {m.library_version()}"
    )
    checks.append(
        _check(
            "lsl",
            "Lab Streaming Layer (pylsl + liblsl)",
            "ok" if ok else "warn",
            v,
            None if ok else "LSL sources need: pip install 'concordos[live]' (bundles liblsl)",
        )
    )
    ok, v = _import_version("zmq", lambda m: f"pyzmq {m.__version__}; libzmq {m.zmq_version()}")
    checks.append(
        _check(
            "zmq",
            "Open Ephys ZMQ (pyzmq)",
            "ok" if ok else "warn",
            v,
            None if ok else "Open Ephys sources need: pip install 'concordos[live]'",
        )
    )
    ok, v = _import_version("brainflow", lambda m: "installed")
    with contextlib.suppress(Exception):
        import importlib.metadata as md

        v = md.version("brainflow") if ok else v
    checks.append(
        _check(
            "brainflow",
            "BrainFlow (optional)",
            "ok" if ok else "info",
            v if ok else "not installed",
            None
            if ok
            else "only needed for the BrainFlow plugin: pip-install the concord_brainflow wheel "
            "from the release page (docs/CONNECT_YOUR_EQUIPMENT.md)",
        )
    )
    bci = any(
        p["name"] == "bci2000" or (p.get("package") or "") == "concord-bci2000" for p in plugins()
    )
    free = _udp_port_free(BCI2000_PORT)
    prog = os.environ.get("BCI2000_PROG_DIR")
    detail = (
        f"plugin {'installed' if bci else 'not installed'}; UDP {BCI2000_PORT} "
        f"{'free' if free else 'in use (BCI2000 output or another receiver is bound)'}; "
        f"BCI2000_PROG_DIR {'set' if prog else 'not set'}"
    )
    checks.append(
        _check(
            "bci2000",
            "BCI2000 App Connector (reachability hint)",
            "info",
            detail,
            "Concord cannot probe BCI2000 (UDP, receive-only): set BCI2000's "
            f"ConnectorOutputAddress to this computer's address and port {BCI2000_PORT}, "
            "then connect the BCI2000 source; see docs/LAB_SETUP.md",
        )
    )
    if frozen() or sys.platform == "darwin":
        ok, v = _import_version("tkinter", lambda m: f"Tk {m.TkVersion}")
        checks.append(
            _check(
                "tk",
                "Desktop app window (Tk)",
                "ok" if ok else "info",
                v,
                None
                if ok
                else "the desktop app then runs without its window; quit with `concord stop`",
            )
        )
    return checks


def _network(
    host: str, port: int, allow_remote: bool
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    checks = []
    if is_loopback(host):
        checks.append(_check("bind", "Bind address", "ok", f"{host} (this computer only)"))
    else:
        checks.append(
            _check(
                "bind",
                "Bind address",
                "warn" if allow_remote else "fail",
                f"{host}: "
                + ("allowed by allow_remote" if allow_remote else "refused (allow_remote is off)"),
                "Concord has no authentication; keep host = 127.0.0.1 (docs/SECURITY.md)",
            )
        )
    server: dict[str, Any] = {"running": False}
    state = _port_state(port)
    if state == "free":
        checks.append(_check("port", f"Port {port}", "ok", "free (Concord is not running)"))
    else:
        try:
            health = _get(f"http://127.0.0.1:{port}/api/v1/health")
            server = {
                "running": True,
                "version": health.get("version"),
                "schema_version": health.get("schema_version"),
                "pid": health.get("pid"),
                "read_only": health.get("read_only"),
            }
            checks.append(
                _check("port", f"Port {port}", "ok", f"in use by Concord {health.get('version')}")
            )
        except Exception:
            checks.append(
                _check(
                    "port",
                    f"Port {port}",
                    "fail",
                    "in use by another program",
                    "set [server] port in the config file or pass --port",
                )
            )
    oe = {p: _port_state(p) for p in OPEN_EPHYS_PORTS}
    checks.append(
        _check(
            "openephys_ports",
            "Open Ephys ZMQ default ports (local)",
            "info",
            ", ".join(f"{p}: {s}" for p, s in oe.items()),
            "in use on this computer usually means the Open Ephys GUI runs here (expected)",
        )
    )
    return server, checks


def _storage(data_dir: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    checks = []
    info: dict[str, Any] = {"data_dir": str(data_dir), "exists": data_dir.exists()}
    if not data_dir.exists():
        checks.append(
            _check(
                "data_dir", "Data directory", "ok", "not created yet (created 0700 at first start)"
            )
        )
        parent = data_dir.parent
        while not parent.exists() and parent != parent.parent:
            parent = parent.parent
        usage = shutil.disk_usage(parent)
    else:
        st = data_dir.lstat()
        mode = stat.S_IMODE(data_dir.stat().st_mode)
        owned = os.name != "posix" or st.st_uid == os.getuid()
        writable = False
        with (
            contextlib.suppress(OSError),
            tempfile.NamedTemporaryFile(dir=data_dir, prefix=".doctor-"),
        ):
            writable = True
        info.update(
            {
                "mode": f"{mode:o}",
                "owned_by_user": owned,
                "writable": writable,
                "symlink": data_dir.is_symlink(),
            }
        )
        status = "ok"
        problems: list[str] = []
        if not owned:
            status, problems = "fail", [*problems, "owned by another user"]
        if not writable:
            status, problems = "fail", [*problems, "not writable"]
        if os.name == "posix" and mode & (stat.S_IRWXG | stat.S_IRWXO):
            status = "warn" if status == "ok" else status
            problems.append(f"mode {mode:o} lets other users in (Concord sets 0700 at start)")
        checks.append(
            _check(
                "data_dir",
                "Data directory",
                status,
                "; ".join(problems) or f"mode {mode:o}, owned by you, writable",
            )
        )
        d, f = open_permissions(data_dir, skip=("datasets",))
        info["open_permissions"] = {"dirs": d, "files": f}
        checks.append(
            _check(
                "permissions",
                "Private files",
                "ok" if d + f == 0 else "warn",
                f"{d} director(ies) and {f} file(s) readable by other users"
                if d + f
                else "all directories 0700 and files 0600 (datasets excluded)",
                None
                if d + f == 0
                else "Concord tightens them at the next start, or: chmod -R go-rwx <data dir>",
            )
        )
        info["counts"] = _counts(data_dir)
        usage = shutil.disk_usage(data_dir)
    info["disk_free_bytes"] = usage.free
    info["disk_total_bytes"] = usage.total
    free_gb = usage.free / 1024**3
    status = (
        "ok"
        if usage.free >= DISK_WARN_BYTES
        else ("warn" if usage.free >= DISK_FAIL_BYTES else "fail")
    )
    checks.append(
        _check(
            "disk",
            "Disk space",
            status,
            f"{free_gb:.1f} GiB free of {usage.total / 1024**3:.0f} GiB",
            None
            if status == "ok"
            else "recordings need space (up to 200 MB each); free space or set a retention policy",
        )
    )
    return info, checks


def _counts(data_dir: Path) -> dict[str, Any]:
    """Numbers only: never names or contents."""
    rec = data_dir / "recordings"
    recordings = list(rec.glob("*.concord.jsonl")) if rec.is_dir() else []
    incomplete = len(list(rec.glob("*.recovery.json"))) if rec.is_dir() else 0
    models = data_dir / "models"
    sessions = data_dir / "sessions"
    exports = list(sessions.glob("*/exports/*.zip")) if sessions.is_dir() else []
    return {
        "recordings": len(recordings),
        "recordings_bytes": sum(p.stat().st_size for p in recordings),
        "recordings_incomplete": incomplete,
        "models": len(list(models.glob("*.json"))) if models.is_dir() else 0,
        "sessions": len([p for p in sessions.iterdir() if p.is_dir()]) if sessions.is_dir() else 0,
        "exports": len(exports),
        "dataset_files": len(list((data_dir / "datasets").rglob("*.nwb")))
        if (data_dir / "datasets").is_dir()
        else 0,
    }


def _logs(logs_dir: Path, limit: int) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    files = [logs_dir / "concord.log.1", logs_dir / "concord.log", logs_dir / "console.log"]
    lines: list[str] = []
    counts = {lvl: 0 for lvl in LOG_LEVELS}
    for f in files:
        if not f.is_file():
            continue
        with contextlib.suppress(OSError), f.open(encoding="utf-8", errors="replace") as fh:
            for line in fh:
                m = LOG_LINE.match(line)
                if m:
                    counts[m.group(1)] += 1
                    lines.append(line.rstrip()[:600])
    recent = lines[-limit:]
    status = "ok" if counts["ERROR"] + counts["CRITICAL"] == 0 else "warn"
    detail = (
        f"{counts['WARNING']} warning(s), {counts['ERROR']} error(s), {counts['CRITICAL']} critical"
        if any(f.is_file() for f in files)
        else "no log file yet"
    )
    return {"recent": recent, "counts": counts}, [
        _check("logs", "Recent log problems", status, detail)
    ]


def _plugin_status(server: dict[str, Any], port: int, discover: bool) -> list[dict[str, Any]]:
    """Validation status of installed plugins: from the running server, else a fresh discovery."""
    installed = {p["name"]: dict(p) for p in plugins()}
    records: list[dict[str, Any]] = []
    if server.get("running"):
        with contextlib.suppress(Exception):
            records = _get(f"http://127.0.0.1:{port}/api/v1/plugins", timeout=5).get("plugins", [])
    elif discover and installed:
        with contextlib.suppress(Exception):
            from concord.runtime.plugins import PluginRegistry

            reg = PluginRegistry()
            recs = asyncio.run(asyncio.wait_for(reg.discover(), 90))
            records = [
                {
                    "name": r.name,
                    "status": r.status,
                    "reason": r.reason,
                    "problems": [p for p in (getattr(r, "problems", None) or [])],
                }
                for r in recs
            ]
    for r in records:
        name = str(r.get("name"))
        entry = installed.setdefault(name, {"name": name})
        entry["status"] = r.get("status")
        entry["reason"] = r.get("reason")
        entry["problems"] = len(r.get("problems") or [])
    for entry in installed.values():
        entry.setdefault("status", "not checked")
    return sorted(installed.values(), key=lambda e: str(e["name"]))


def _redact_all(obj: Any) -> Any:
    if isinstance(obj, str):
        return redact(obj)
    if isinstance(obj, list):
        return [_redact_all(x) for x in obj]
    if isinstance(obj, dict):
        return {k: _redact_all(v) for k, v in obj.items()}
    return obj


def run(
    *,
    data_dir: Path,
    host: str = "127.0.0.1",
    port: int = 8000,
    allow_remote: bool = False,
    config_path: Path | None = None,
    discover_plugins: bool = True,
    log_lines: int = 40,
) -> dict[str, Any]:
    cfg_info, cfg_check = _config_check(config_path)
    server, net_checks = _network(host, port, allow_remote)
    storage, storage_checks = _storage(data_dir)
    logs, log_checks = _logs(data_dir / "logs", log_lines)
    pkgs = packages()
    server_extra = all(
        next((p["installed"] for p in pkgs if p["name"] == n), False)
        for n in ("fastapi", "uvicorn", "concord-adapter-sdk")
    )
    checks = [
        _check("concord", "Concord", "ok", f"{__version__} ({_install(cfg_check)['install']})"),
        _check(
            "server_extra",
            "Runtime server",
            "ok" if server_extra else "warn",
            "installed" if server_extra else "not installed (application SDK only)",
            None if server_extra else 'pip install "concordos[server]"',
        ),
        cfg_check,
        *_optional(),
        *net_checks,
        *storage_checks,
        *log_checks,
    ]
    plugin_rows = _plugin_status(server, port, discover_plugins and server_extra)
    bad = [p for p in plugin_rows if p.get("status") not in ("compatible", "not checked")]
    checks.append(
        _check(
            "plugins",
            "Source plugins",
            "warn" if bad else "ok",
            f"{len(plugin_rows)} installed" + (f"; {len(bad)} not usable" if bad else ""),
        )
    )
    summary = {s: sum(c["status"] == s for c in checks) for s in ("ok", "info", "warn", "fail")}
    report: dict[str, Any] = {
        "format": REPORT_FORMAT,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "concord": _install(cfg_check) | {"config": cfg_info},
        "platform": platform_info(),
        "summary": summary,
        "checks": checks,
        "packages": pkgs,
        "plugins": plugin_rows,
        "server": server,
        "storage": storage,
        "logs": logs,
        "excluded": EXCLUDED,
    }
    return _redact_all(report)  # type: ignore[no-any-return]


ICON = {"ok": "ok", "info": "info", "warn": "WARN", "fail": "FAIL"}


def to_markdown(report: dict[str, Any]) -> str:
    s = report["summary"]
    lines = [
        "# Concord support report",
        "",
        f"Generated {report['generated_at']} · Concord {report['concord']['version']} "
        f"({report['concord']['install']}) · {report['platform']['system']} "
        f"{report['platform'].get('macos') or report['platform']['release']} "
        f"{report['platform']['machine']} · Python {report['platform']['python']}",
        "",
        f"**{s['fail']} failed, {s['warn']} warnings, {s['ok']} ok, {s['info']} info.**",
        "",
        "| Check | Status | Detail |",
        "| --- | --- | --- |",
    ]
    for c in report["checks"]:
        detail = c["detail"] + (f" — {c['hint']}" if c.get("hint") else "")
        lines.append(f"| {c['title']} | {ICON[c['status']]} | {detail.replace('|', '/')} |")
    lines += ["", "## Packages", "", "| Package | Version | Fingerprint |", "| --- | --- | --- |"]
    for p in report["packages"]:
        if p["installed"]:
            fp = (p.get("fingerprint") or "")[:16]
            edit = " (editable)" if p.get("editable") else ""
            lines.append(f"| {p['name']} | {p['version']}{edit} | {fp} |")
    lines += [
        "",
        "Not installed: "
        + (", ".join(p["name"] for p in report["packages"] if not p["installed"]) or "—"),
    ]
    lines += ["", "## Source plugins", ""]
    if report["plugins"]:
        lines += ["| Plugin | Package | Status |", "| --- | --- | --- |"]
        for p in report["plugins"]:
            status = p.get("status") or "?"
            if p.get("reason"):
                status += f" ({p['reason']})"
            lines.append(
                f"| {p['name']} | {p.get('package') or '?'} {p.get('version') or ''} | {status} |"
            )
    else:
        lines.append("None installed.")
    st = report["storage"]
    lines += ["", "## Storage", "", f"Data directory: `{st['data_dir']}`"]
    if st.get("counts"):
        c = st["counts"]
        lines.append(
            f"{c['recordings']} recording(s) ({c['recordings_bytes'] / 1024**2:.1f} MiB, "
            f"{c['recordings_incomplete']} incomplete), {c['models']} model(s), {c['sessions']} "
            f"session(s), {c['exports']} export(s), {c['dataset_files']} dataset file(s)."
        )
    lines += ["", "## Recent warnings and errors (redacted)", ""]
    recent = report["logs"]["recent"]
    lines += ["```", *recent, "```"] if recent else ["None."]
    lines += ["", "## Not included in this report", ""]
    lines += [f"- {e}" for e in report["excluded"]]
    lines.append("")
    return "\n".join(lines)


def write(report: dict[str, Any], out_dir: Path) -> tuple[Path, Path]:
    from concord.security import ensure_private_dir, write_private

    ensure_private_dir(out_dir)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    j = write_private(
        out_dir / f"concord-support-{stamp}.json", json.dumps(report, indent=1) + "\n"
    )
    m = write_private(out_dir / f"concord-support-{stamp}.md", to_markdown(report))
    return j, m
