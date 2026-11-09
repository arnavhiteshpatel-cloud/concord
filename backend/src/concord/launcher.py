"""Start, stop and inspect a background Concord server (``concord start/stop/status``).

The server runs as its own process (``concord serve``), detached from the terminal, writing
to ``<data>/logs/``. It holds an exclusive lock on ``<data>/concord.pid`` while it runs, so
``status`` and ``stop`` find it without guessing, and a stale pid file after a crash is
recognised as stale. Stdlib only (works without the server extra for status/stop).

Windows: the server is started in its own hidden console and process group (no window, not
stopped by closing the terminal), and stopped by a stop request in the data folder instead of
SIGTERM (``concord.server.serve.request_stop``); TerminateProcess only if it does not exit.
"""

from __future__ import annotations

import contextlib
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
import webbrowser
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from concord.config import command_hint, frozen
from concord.oscompat import (
    background_kwargs,
    force_kill,
    helper_executable,
    is_windows,
    pid_alive,
    terminate,
)
from concord.security import ensure_private_dir, open_private, redact

START_TIMEOUT_S = 90.0  # first launch of a desktop bundle on macOS can be slow (Gatekeeper)
STOP_TIMEOUT_S = 30.0


class LaunchError(Exception):
    pass


@dataclass
class Instance:
    pid: int | None
    url: str
    health: dict[str, Any] | None
    from_pid_file: bool  # found through this data directory's instance lock
    launched: bool = False  # start() launched it just now, for this data directory


def http_json(url: str, method: str = "GET", body: Any = None, timeout: float = 3.0) -> Any:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        url, data=data, method=method, headers={"content-type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        raw = r.read()
    return json.loads(raw) if raw else None


def health(url: str, timeout: float = 1.5) -> dict[str, Any] | None:
    try:
        h = http_json(url + "/api/v1/health", timeout=timeout)
    except (OSError, ValueError, urllib.error.URLError):
        return None
    return h if isinstance(h, dict) and h.get("status") == "ok" else None


def find(url: str, pid_file: Path) -> Instance | None:
    """The Concord server for this data directory/port, if one is running."""
    from concord.server.serve import read_instance

    info = read_instance(pid_file)
    if info is not None:
        inst_url = str(info.get("url") or url)
        return Instance(
            pid=info.get("pid") if isinstance(info.get("pid"), int) else None,
            url=inst_url,
            health=health(inst_url),
            from_pid_file=True,
        )
    h = health(url)
    if h is not None:
        pid = h.get("pid")
        return Instance(
            pid=pid if isinstance(pid, int) else None, url=url, health=h, from_pid_file=False
        )
    return None


def differences(instance: Instance, *, version: str, stream_protocol: str) -> list[str]:
    """How a running server differs from the one this installation would run here.

    ``"data_dir"``: it does not hold this data directory's instance lock (found only by its
    URL), so it is another installation, a build from before the lock, or a server started
    with another data directory. ``"version"`` and ``"stream_protocol"``: its health report
    names another version or stream protocol (or none). Empty: it is this data directory's
    own server at this version.
    """
    h = instance.health or {}
    out: list[str] = []
    if not (instance.from_pid_file or instance.launched):
        out.append("data_dir")
    if h.get("version") != version:
        out.append("version")
    if h.get("stream_protocol") != stream_protocol:
        out.append("stream_protocol")
    return out


def serve_command() -> list[str]:
    if frozen():  # the bundled program answers `serve` (packaging/app_entry.py)
        return [helper_executable(), "serve"]
    return [sys.executable, "-m", "concord", "serve"]


def _port_busy(host: str, port: int) -> bool:
    import socket

    with socket.socket() as s:
        s.settimeout(0.5)
        return s.connect_ex(("127.0.0.1" if host in ("0.0.0.0", "::") else host, port)) == 0


def _tail(path: Path, lines: int = 15) -> str:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
    return redact("\n".join(text.splitlines()[-lines:]))


def start(
    *,
    url: str,
    host: str,
    port: int,
    data_dir: Path,
    pid_file: Path,
    env: dict[str, str],
    timeout_s: float = START_TIMEOUT_S,
) -> Instance:
    """Start ``concord serve`` in the background and wait until it is healthy.

    A server that already answers is returned as found (``launched`` False), even one found
    only by its URL; ``differences()`` tells whether it is this data directory's."""
    running = find(url, pid_file)
    if running is not None and running.health is not None:
        return running
    if _port_busy(host, port):
        raise LaunchError(
            f"port {port} is in use by another program. Choose another port: "
            f"{command_hint('start --port 8010')} (or [server] port in the config file)."
        )
    logs = ensure_private_dir(data_dir / "logs")
    console = logs / "console.log"
    fd = open_private(console, "a")
    with os.fdopen(fd, "a", encoding="utf-8") as out:
        out.write(f"\n--- concord start {time.strftime('%Y-%m-%d %H:%M:%S')} ---\n")
        out.flush()
        proc = subprocess.Popen(
            serve_command(),
            env={**env, "PYTHONIOENCODING": "utf-8"},  # the log is UTF-8 on every platform
            stdin=subprocess.DEVNULL,
            stdout=out,
            stderr=subprocess.STDOUT,
            close_fds=True,
            **background_kwargs(),
        )
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        code = proc.poll()
        if code is not None:
            raise LaunchError(
                f"the server exited during startup (code {code}). Last lines of {console}:\n"
                + _tail(console)
            )
        h = health(url, timeout=1.0)
        if h is not None:
            return Instance(pid=proc.pid, url=url, health=h, from_pid_file=False, launched=True)
        time.sleep(0.25)
    with contextlib.suppress(OSError):
        proc.terminate()
    raise LaunchError(f"the server did not become healthy within {timeout_s:.0f} s; see {console}")


def _alive(pid: int) -> bool:
    # a zombie child of this process counts as gone
    return pid_alive(pid, reap=True)


def _ask_to_exit(pid: int, pid_file: Path | None) -> str:
    """The graceful stop for this platform; returns how it was asked."""
    from concord.server.serve import read_instance, request_stop

    if is_windows():
        # no catchable SIGTERM on Windows: a stop request the server watches for
        info = read_instance(pid_file) if pid_file is not None else None
        if info is not None and info.get("pid") == pid and pid_file is not None:
            request_stop(pid_file, pid)
            return "stop request"
        # a server of another data folder (found by its port): nothing to ask it with; the
        # safe stop has already closed its recording, so it is ended directly
        with contextlib.suppress(OSError):
            terminate(pid)
        return "terminated"
    with contextlib.suppress(ProcessLookupError):
        terminate(pid)  # SIGTERM: uvicorn's graceful shutdown
    return "SIGTERM"


def stop(
    instance: Instance, timeout_s: float = STOP_TIMEOUT_S, pid_file: Path | None = None
) -> dict[str, Any]:
    """Safe stop (command output off, recording closed, source disconnected), then SIGTERM
    (Windows: a stop request in the data folder, see ``concord.server.serve``).

    Killed (SIGKILL; TerminateProcess on Windows) only if the server does not exit within
    ``timeout_s``; an active recording is then recovered (marked incomplete) at the next
    start. With ``pid_file``, a server whose instance lock is released and whose API is gone
    counts as stopped even if its process has not been reaped yet (containers without an init
    process).
    """
    from concord.server.serve import read_instance

    def gone(pid: int) -> bool:
        if not _alive(pid):
            return True
        return (
            pid_file is not None
            and read_instance(pid_file) is None
            and (health(instance.url, timeout=0.3) is None)
        )

    result: dict[str, Any] = {"pid": instance.pid, "safe_stop": None, "forced": False}
    if instance.health is not None:
        with contextlib.suppress(OSError, ValueError, urllib.error.URLError):
            result["safe_stop"] = http_json(
                instance.url + "/api/v1/safe-stop", "POST", {"reason": "concord stop"}, timeout=10
            )
    pid = instance.pid
    if pid is None:
        raise LaunchError("cannot determine the server's process id; stop it where it runs")
    result["asked_by"] = _ask_to_exit(pid, pid_file)
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if gone(pid):
            result["forced"] = result["asked_by"] == "terminated"
            return result
        time.sleep(0.1)
    with contextlib.suppress(ProcessLookupError, OSError):
        force_kill(pid)
    result["forced"] = True
    return result


def open_browser(url: str) -> bool:
    with contextlib.suppress(Exception):
        return bool(webbrowser.open(url, new=2))
    return False
