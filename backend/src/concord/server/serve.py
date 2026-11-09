"""Run the Concord server process: the one code path behind ``concord serve``, ``concord start``,
``concord-server`` and the desktop app.

Before anything listens: the bind policy (non-loopback refused without ``allow_remote``), a
0077 umask (everything Concord writes is private to the user), redacting log handlers
(stderr + ``<data>/logs/concord.log``), and a single-instance lock on ``<data>/concord.pid``
(two servers must never write the same recordings directory).

Stopping from another process (``concord stop``): on POSIX a SIGTERM, which uvicorn turns into
a graceful shutdown. Windows has no SIGTERM that a process can catch, so ``concord stop`` writes
a stop request (``<data>/concord.stop``, naming the server's pid) and the server, which watches
for it, shuts down the same graceful way. The data folder is private to the user, so only they
can ask (the same trust as the pid file itself).
"""

from __future__ import annotations

import contextlib
import json
import logging
import os
import sys
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from concord import __version__
from concord.config import command_hint
from concord.oscompat import O_BINARY, is_locked, try_lock, unlink_before_close, unlock
from concord.security import (
    BindRefused,
    check_bind,
    configure_logging,
    ensure_private_dir,
    write_private,
)
from concord.server.settings import Settings

log = logging.getLogger(__name__)

STOP_REQUEST = "concord.stop"
STOP_POLL_S = 0.25


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
        if unlink_before_close():
            # POSIX: delete while still locked, so no other process sees an unlocked pid file
            with contextlib.suppress(OSError):
                self.path.unlink()
            with contextlib.suppress(OSError):
                os.close(self.fd)
            return
        # Windows cannot delete an open file: unlock, close, then delete (if a new server has
        # opened it meanwhile, the delete fails and its file is kept)
        unlock(self.fd)
        with contextlib.suppress(OSError):
            os.close(self.fd)
        with contextlib.suppress(OSError):
            self.path.unlink()


def read_instance(pid_file: Path) -> dict[str, Any] | None:
    """The running server's pid-file contents, or None if no live server holds it."""
    try:
        fd = os.open(pid_file, os.O_RDONLY | O_BINARY)
    except OSError:
        return None
    try:
        raw = os.read(fd, 4096)
    finally:
        os.close(fd)
    try:
        info = json.loads(raw) if raw else {}
    except ValueError:
        info = {}
    if not isinstance(info, dict):
        info = {}
    # locked: the server is alive; not locked (or gone): stale, the server died
    return info if is_locked(pid_file) else None


def acquire_instance(settings: Settings) -> InstanceLock:
    ensure_private_dir(settings.data_dir)
    path = settings.pid_file
    fd = os.open(path, os.O_RDWR | os.O_CREAT | O_BINARY, 0o600)
    if not try_lock(fd):
        os.close(fd)
        raise AlreadyRunning(read_instance(path) or {})
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
    # a stop request left by an earlier run (its server exited before reading it)
    with contextlib.suppress(OSError):
        stop_request_path(path).unlink()
    return InstanceLock(path, fd)


# --------------------------------------------------------------------------- stop requests


def stop_request_path(pid_file: Path) -> Path:
    return pid_file.with_name(STOP_REQUEST)


def request_stop(pid_file: Path, pid: int) -> Path:
    """Ask the server ``pid`` that holds ``pid_file`` to shut down gracefully (any platform;
    the graceful way on Windows)."""
    body = json.dumps({"pid": pid, "requested_at": time.time()})
    return write_private(stop_request_path(pid_file), body)


def take_stop_request(pid_file: Path, pid: int | None = None) -> bool:
    """True (and the request is consumed) if a stop request for ``pid`` (default: this
    process) exists. A request naming another process is stale (the caller holds the instance
    lock, so that process is not serving this data folder) and is removed."""
    path = stop_request_path(pid_file)
    try:
        body = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    with contextlib.suppress(OSError):
        path.unlink()
    target = body.get("pid") if isinstance(body, dict) else None
    if target != (os.getpid() if pid is None else pid):
        log.warning("ignored a stop request for another process (pid %s)", target)
        return False
    log.info("stop requested by another process (concord stop)")
    return True


class StopWatcher:
    """Calls ``on_stop`` once, from a background thread, when a stop request for this
    process appears."""

    def __init__(
        self, pid_file: Path, on_stop: Callable[[], None], interval_s: float = STOP_POLL_S
    ) -> None:
        self.pid_file = pid_file
        self.on_stop = on_stop
        self.interval_s = interval_s
        self._done = threading.Event()
        self._thread = threading.Thread(target=self._run, name="concord-stop-watch", daemon=True)

    def start(self) -> StopWatcher:
        self._thread.start()
        return self

    def close(self) -> None:
        self._done.set()

    def _run(self) -> None:
        while not self._done.wait(self.interval_s):
            try:
                requested = take_stop_request(self.pid_file)
            except Exception:  # never let the watcher die silently
                log.exception("stop-request watcher failed")
                return
            if requested:
                self.on_stop()
                return


# --------------------------------------------------------------------------- running


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
    """Run in the foreground until SIGINT/SIGTERM (Ctrl-Break on Windows) or a stop request
    (graceful: recordings are closed)."""
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
    watcher: StopWatcher | None = None
    try:
        server = uvicorn.Server(uvicorn_config(settings, create_app(settings)))

        def _exit() -> None:
            server.should_exit = True

        watcher = StopWatcher(settings.pid_file, _exit).start()
        # uvicorn re-raises Ctrl-C after its graceful shutdown (uvicorn.run swallows it too)
        with contextlib.suppress(KeyboardInterrupt):
            server.run()
        return 0 if server.started else 1
    finally:
        if watcher is not None:
            watcher.close()
        lock.release()
