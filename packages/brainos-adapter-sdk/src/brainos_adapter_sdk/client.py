"""Synchronous client for one plugin-host process (``python -m brainos_adapter_sdk.host``).

Used by ``host --list`` / ``host --check`` and by plugin authors' own tests: it runs the
plugin exactly as BrainOS does (separate process, binary IPC, host-side validation).
BrainOS's runtime has its own asyncio client speaking the same protocol.
"""

from __future__ import annotations

import contextlib
import os
import queue
import subprocess
import sys
import threading
from collections import deque
from collections.abc import Mapping, Sequence
from typing import IO, Any

from numpy.typing import NDArray

from brainos_adapter_sdk import ipc
from brainos_adapter_sdk.api import Chunk, MarkerChunk


class HostError(Exception):
    """The host answered with an error (``type`` is one of the ``ipc`` error constants)."""

    def __init__(
        self,
        type_: str,
        message: str,
        traceback: str | None = None,
        problems: Sequence[Mapping[str, Any]] = (),
    ) -> None:
        self.type = type_
        self.message = message
        self.traceback = traceback
        self.problems = list(problems)
        super().__init__(f"{type_}: {message}")


class HostDied(Exception):
    """The host process exited, hung past a timeout, or broke the protocol."""


_EOF = object()


def host_command(plugin_ref: str, python: str | None = None) -> list[str]:
    return [python or sys.executable, "-m", "brainos_adapter_sdk.host", plugin_ref]


class SyncHostClient:
    def __init__(
        self,
        plugin_ref: str,
        *,
        python: str | None = None,
        env: Mapping[str, str] | None = None,
        hello_timeout_s: float = 30.0,
    ) -> None:
        self.plugin_ref = plugin_ref
        self.proc = subprocess.Popen(
            host_command(plugin_ref, python),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env={**os.environ, **(env or {})},
        )
        self.stderr_tail: deque[str] = deque(maxlen=200)
        self._inbox: queue.Queue[object] = queue.Queue()
        self._id = 0
        assert self.proc.stdout is not None and self.proc.stderr is not None
        threading.Thread(target=self._reader, args=(self.proc.stdout,), daemon=True).start()
        threading.Thread(target=self._drain, args=(self.proc.stderr,), daemon=True).start()
        self.hello = self._next(hello_timeout_s)[0]
        if self.hello.get("type") != "hello" or self.hello.get("protocol") != ipc.PROTOCOL:
            self.kill()
            raise HostDied(f"unexpected first message from host: {self.hello!r}"[:300])

    def _reader(self, f: IO[bytes]) -> None:
        try:
            while True:
                msg = ipc.read_message(f)
                if msg is None:
                    break
                self._inbox.put(msg)
        except Exception as exc:  # protocol violation: surfaced to the caller
            self._inbox.put(exc)
        self._inbox.put(_EOF)

    def _drain(self, f: IO[bytes]) -> None:
        for line in f:
            self.stderr_tail.append(line.decode("utf-8", "replace").rstrip())

    def _next(self, timeout_s: float) -> tuple[dict[str, Any], list[NDArray[Any]]]:
        try:
            item = self._inbox.get(timeout=timeout_s)
        except queue.Empty:
            self.kill()
            raise HostDied(f"plugin host did not answer within {timeout_s:g} s (killed)") from None
        if item is _EOF:
            code = self.proc.wait(timeout=5)
            tail = " | ".join(list(self.stderr_tail)[-5:])
            raise HostDied(f"plugin host exited (code {code}){': ' + tail if tail else ''}")
        if isinstance(item, Exception):
            self.kill()
            raise HostDied(f"protocol error from plugin host: {item}")
        return item  # type: ignore[return-value]

    def request(
        self, cmd: str, args: Mapping[str, Any] | None = None, *, timeout_s: float = 30.0
    ) -> tuple[dict[str, Any], list[NDArray[Any]]]:
        self._id += 1
        assert self.proc.stdin is not None
        try:
            ipc.write_message(
                self.proc.stdin, {"id": self._id, "cmd": cmd, "args": dict(args or {})}
            )
        except (BrokenPipeError, OSError) as exc:
            raise HostDied(f"plugin host is gone: {exc}") from None
        header, arrays = self._next(timeout_s)
        if header.get("id") != self._id:
            self.kill()
            raise HostDied(f"response id {header.get('id')!r} != request id {self._id}")
        if not header.get("ok"):
            e = header.get("error") or {}
            raise HostError(
                str(e.get("type", "Unknown")),
                str(e.get("message", "")),
                e.get("traceback"),
                e.get("problems") or [],
            )
        result = header.get("result")
        return (result if isinstance(result, dict) else {}), arrays

    # convenience wrappers
    def manifest(self) -> dict[str, Any]:
        return self.request("manifest")[0]

    def discover(self, timeout_s: float = 1.0) -> dict[str, Any]:
        return self.request("discover", {"timeout_s": timeout_s}, timeout_s=timeout_s + 30)[0]

    def open(self, device_key: str, options: Mapping[str, Any] | None = None) -> dict[str, Any]:
        return self.request("open", {"device_key": device_key, "options": dict(options or {})})[0]

    def read(self, timeout_s: float = 0.1, grace_s: float = 10.0) -> list[Chunk | MarkerChunk]:
        result, arrays = self.request(
            "read", {"timeout_s": timeout_s}, timeout_s=timeout_s + grace_s
        )
        return ipc.chunks_from_wire(result.get("chunks", []), arrays)

    def stats(self) -> dict[str, Any]:
        return self.request("stats")[0]

    def close_session(self) -> None:
        self.request("close")

    def kill(self) -> None:
        if self.proc.poll() is None:
            self.proc.kill()
        with contextlib.suppress(subprocess.TimeoutExpired):
            self.proc.wait(timeout=5)

    def shutdown(self, timeout_s: float = 5.0) -> None:
        if self.proc.poll() is None:
            try:
                self.request("shutdown", timeout_s=timeout_s)
                self.proc.wait(timeout=timeout_s)
            except (HostDied, HostError, subprocess.TimeoutExpired):
                pass
        self.kill()
        for f in (self.proc.stdin, self.proc.stdout, self.proc.stderr):
            if f is not None:
                with contextlib.suppress(OSError):
                    f.close()

    def __enter__(self) -> SyncHostClient:
        return self

    def __exit__(self, *exc: object) -> None:
        self.shutdown()
