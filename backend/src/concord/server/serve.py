"""Run the Concord server process: the one code path behind ``concord serve``, ``concord start``,
``concord-server`` and the desktop app.

Before anything listens: the bind policy (non-loopback refused without ``allow_remote``), a
0077 umask (everything Concord writes is private to the user), redacting log handlers
(stderr + ``<data>/logs/concord.log``), and a single-instance lock on ``<data>/concord.pid``
(two servers must never write the same recordings directory).
"""

from __future__ import annotations

import contextlib
import json
import logging
import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from concord import __version__
from concord.config import command_hint
from concord.security import BindRefused, check_bind, configure_logging, ensure_private_dir
from concord.server.settings import Settings

try:
    import fcntl
except ImportError:  # pragma: no cover - Windows
    fcntl = None  # type: ignore[assignment]

log = logging.getLogger(__name__)


class AlreadyRunning(Exception):
    def __init__(self, info: dict[str, Any]) -> None:
        super().__init__(
            f"another Concord server (pid {info.get('pid')}, {info.get('url')}) uses this data "
            f"directory; stop it first ({command_hint('stop')})"
        )
        self.info = info


@dataclass
class InstanceLock:
    path: Path
    fd: int

    def release(self) -> None:
        with contextlib.suppress(OSError):
            self.path.unlink()
        with contextlib.suppress(OSError):
            os.close(self.fd)


def read_instance(pid_file: Path) -> dict[str, Any] | None:
    """The running server's pid-file contents, or None if no live server holds it."""
    try:
        fd = os.open(pid_file, os.O_RDONLY)
    except OSError:
        return None
    try:
        raw = os.read(fd, 4096)
        try:
            info = json.loads(raw) if raw else {}
        except ValueError:
            info = {}
        if not isinstance(info, dict):
            info = {}
        if fcntl is not None:
            try:
                fcntl.flock(fd, fcntl.LOCK_SH | fcntl.LOCK_NB)
            except OSError:
                return info  # held: the server is alive
            return None  # nobody holds it: stale (the server died)
        pid = info.get("pid")
        if isinstance(pid, int):
            try:
                os.kill(pid, 0)
                return info
            except OSError:
                return None
        return None
    finally:
        os.close(fd)


def acquire_instance(settings: Settings) -> InstanceLock:
    ensure_private_dir(settings.data_dir)
    path = settings.pid_file
    fd = os.open(path, os.O_RDWR | os.O_CREAT, 0o600)
    if fcntl is not None:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            os.close(fd)
            raise AlreadyRunning(read_instance(path) or {}) from None
    info = {
        "pid": os.getpid(),
        "url": settings.url,
        "host": settings.host,
        "port": settings.port,
        "version": __version__,
        "started_at": time.time(),
        "executable": sys.executable,
    }
    os.ftruncate(fd, 0)
    os.lseek(fd, 0, os.SEEK_SET)
    os.write(fd, json.dumps(info).encode())
    return InstanceLock(path, fd)


def prepare(settings: Settings) -> tuple[InstanceLock, str | None]:
    """Everything that must hold before the server listens. Returns the lock and a warning."""
    warning = check_bind(settings.host, settings.allow_remote)  # raises BindRefused
    os.umask(0o077)
    ensure_private_dir(settings.data_dir)
    configure_logging(settings.log_level, settings.log_file)
    if warning:
        log.warning(warning)
    lock = acquire_instance(settings)
    log.info(
        "Concord %s: data directory %s, config %s",
        __version__,
        settings.data_dir,
        settings.config_path or "(none; defaults)",
    )
    return lock, warning


def uvicorn_config(settings: Settings, app: Any) -> Any:
    import uvicorn

    return uvicorn.Config(
        app,
        host=settings.host,
        port=settings.port,
        log_level=settings.log_level.lower(),
        log_config=None,  # the root handlers configured in prepare() (redacting)
        access_log=settings.log_level == "DEBUG",
        ws_max_size=64 * 1024,
        # M5-E: no permessage-deflate. The server is local; compressing JSON sample frames
        # cost ~13 ms of CPU per 180 KB frame (docs/PERFORMANCE.md) for no benefit.
        ws_per_message_deflate=False,
    )


def run(settings: Settings) -> int:
    """Run in the foreground until SIGINT/SIGTERM (graceful: recordings are closed)."""
    import uvicorn

    from concord.server.app import create_app

    try:
        lock, _ = prepare(settings)
    except BindRefused as exc:
        print(f"concord: {exc}", file=sys.stderr)
        return 2
    except AlreadyRunning as exc:
        print(f"concord: {exc}", file=sys.stderr)
        return 3
    try:
        server = uvicorn.Server(uvicorn_config(settings, create_app(settings)))
        # uvicorn re-raises Ctrl-C after its graceful shutdown (uvicorn.run swallows it too)
        with contextlib.suppress(KeyboardInterrupt):
            server.run()
        return 0 if server.started else 1
    finally:
        lock.release()
