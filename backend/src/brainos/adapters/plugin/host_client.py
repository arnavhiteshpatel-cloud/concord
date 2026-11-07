"""asyncio client for one plugin-host process (``python -m brainos_adapter_sdk.host``).

The host runs third-party code, so everything about it is untrusted: every wait has a
timeout, every frame length is bounded, and any surprise (exit, hang, garbage on the pipe)
ends the process and raises :class:`HostFailure`. Nothing here imports plugin code.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import signal
import sys
from collections import deque
from collections.abc import Mapping, Sequence
from typing import Any

from brainos_adapter_sdk import ipc
from numpy.typing import NDArray

log = logging.getLogger(__name__)

STDERR_LOG_LINES = 200  # per process; later lines are kept in the tail only


class HostFailure(Exception):
    """The host process exited, hung or broke the protocol (it has been stopped)."""


class HostExited(HostFailure):
    pass


class HostTimeout(HostFailure):
    pass


class HostProtocolError(HostFailure):
    pass


class RemoteError(Exception):
    """The host answered a request with a typed error."""

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


def host_env(extra_path: Sequence[str] = ()) -> dict[str, str]:
    env = dict(os.environ)
    paths = [*extra_path, *([env["PYTHONPATH"]] if env.get("PYTHONPATH") else [])]
    if paths:
        env["PYTHONPATH"] = os.pathsep.join(paths)
    env["PYTHONUNBUFFERED"] = "1"
    return env


class AsyncHostClient:
    def __init__(
        self,
        plugin_ref: str,
        *,
        python: str | None = None,
        extra_path: Sequence[str] = (),
        label: str | None = None,
        pending_timeout_s: float = 6.0,
    ) -> None:
        self.plugin_ref = plugin_ref
        # a request cancelled while waiting for its answer (e.g. the runtime stopping the
        # pump on disconnect) leaves that answer in the pipe: it is drained before the next
        # request, waiting at most this long, so close() can still shut the plugin down cleanly
        self.pending_timeout_s = pending_timeout_s
        self._pending: int | None = None
        self._in_message = False
        self.python = python or sys.executable
        self.extra_path = list(extra_path)
        self.label = label or plugin_ref
        self.proc: asyncio.subprocess.Process | None = None
        self.hello: dict[str, Any] = {}
        self.stderr_tail: deque[str] = deque(maxlen=200)
        self._stderr_task: asyncio.Task[None] | None = None
        self._lock = asyncio.Lock()
        self._id = 0
        self._broken: str | None = None

    @property
    def pid(self) -> int | None:
        return self.proc.pid if self.proc else None

    @property
    def alive(self) -> bool:
        return self.proc is not None and self.proc.returncode is None and self._broken is None

    async def start(self, timeout_s: float) -> dict[str, Any]:
        self.proc = await asyncio.create_subprocess_exec(
            self.python,
            "-m",
            "brainos_adapter_sdk.host",
            self.plugin_ref,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=host_env(self.extra_path),
            start_new_session=True,  # a signal to the runtime's process group spares it
        )
        self._stderr_task = asyncio.create_task(
            self._drain_stderr(), name=f"plugin-stderr:{self.label}"
        )
        try:
            header, _ = await asyncio.wait_for(self._read_message(), timeout_s)
        except TimeoutError:
            await self._fail(f"no hello from the plugin host within {timeout_s:g} s")
            raise HostTimeout(f"plugin host did not start within {timeout_s:g} s") from None
        if header.get("type") != "hello" or header.get("protocol") != ipc.PROTOCOL:
            await self._fail("bad hello")
            raise HostProtocolError(
                f"unexpected first message from the plugin host: {header!r}"[:300]
            )
        self.hello = header
        return header

    async def _drain_stderr(self) -> None:
        assert self.proc is not None and self.proc.stderr is not None
        logged = 0
        while True:
            line = await self.proc.stderr.readline()
            if not line:
                return
            text = line.decode("utf-8", "replace").rstrip()[:1000]
            self.stderr_tail.append(text)
            if logged < STDERR_LOG_LINES:
                log.info("[plugin %s] %s", self.label, text)
                logged += 1
                if logged == STDERR_LOG_LINES:
                    log.warning(
                        "[plugin %s] further output is kept only in the log tail", self.label
                    )

    async def _read_exact(self, n: int) -> bytes:
        assert self.proc is not None and self.proc.stdout is not None
        try:
            return await self.proc.stdout.readexactly(n)
        except asyncio.IncompleteReadError as exc:
            code = await self._wait_exit()
            raise HostExited(self._exit_message(code, partial=bool(exc.partial))) from None

    async def _read_message(self) -> tuple[dict[str, Any], list[NDArray[Any]]]:
        try:
            head = await self._read_exact(4)
            self._in_message = True  # from here on, a cancellation desynchronises the stream
            n = ipc.check_length(ipc.LENGTH.unpack(head)[0], ipc.MAX_HEADER_BYTES)
            header = ipc.decode_header(await self._read_exact(n))
            arrays = []
            for dt, shape in ipc.buffer_specs(header):
                m = ipc.check_length(ipc.LENGTH.unpack(await self._read_exact(4))[0])
                arrays.append(ipc.decode_buffer(dt, shape, await self._read_exact(m) if m else b""))
        except ipc.WireError as exc:
            await self._fail(f"protocol error: {exc}")
            raise HostProtocolError(f"plugin host broke the IPC protocol: {exc}") from None
        self._in_message = False
        return header, arrays

    async def _wait_exit(self) -> int | None:
        assert self.proc is not None
        try:
            return await asyncio.wait_for(self.proc.wait(), 2.0)
        except TimeoutError:
            self._kill()
            return await self.proc.wait()

    def _exit_message(self, code: int | None, *, partial: bool = False) -> str:
        if code is not None and code < 0:
            try:
                how = f"was killed by {signal.Signals(-code).name}"
            except ValueError:
                how = f"was killed by signal {-code}"
        else:
            how = f"exited with code {code}"
        tail = [x for x in self.stderr_tail if x.strip()][-3:]
        where = " in the middle of a message" if partial else ""
        detail = f"; last output: {' | '.join(tail)}" if tail else ""
        return f"plugin host {how}{where}{detail}"[:600]

    def _kill(self) -> None:
        if self.proc is not None and self.proc.returncode is None:
            with contextlib.suppress(ProcessLookupError):
                self.proc.kill()

    async def _fail(self, reason: str) -> None:
        self._broken = reason
        self._kill()
        if self.proc is not None:
            with contextlib.suppress(Exception):
                await asyncio.wait_for(self.proc.wait(), 2.0)

    async def request(
        self, cmd: str, args: Mapping[str, Any] | None = None, *, timeout_s: float
    ) -> tuple[dict[str, Any], list[NDArray[Any]]]:
        """One request/response. Raises RemoteError (typed plugin error) or HostFailure."""
        async with self._lock:
            if self.proc is None or self.proc.stdin is None:
                raise HostExited("plugin host not started")
            if self._broken is not None:
                raise HostExited(f"plugin host stopped earlier: {self._broken}")
            if self.proc.returncode is not None:
                raise HostExited(self._exit_message(self.proc.returncode))
            await self._drain_pending()
            self._id += 1
            rid = self._id
            try:
                self.proc.stdin.write(
                    ipc.encode_message({"id": rid, "cmd": cmd, "args": dict(args or {})})
                )
                await self.proc.stdin.drain()
            except (BrokenPipeError, ConnectionResetError) as exc:
                code = await self._wait_exit()
                raise HostExited(self._exit_message(code)) from exc
            try:
                header, arrays = await asyncio.wait_for(self._read_message(), timeout_s)
            except TimeoutError:
                await self._fail(f"{cmd} timed out")
                raise HostTimeout(
                    f"plugin did not answer '{cmd}' within {timeout_s:g} s; host stopped"
                ) from None
            except asyncio.CancelledError:
                if self._in_message:
                    # a half-read response would desynchronise the stream: stop the host
                    await asyncio.shield(self._fail(f"{cmd} cancelled mid-message"))
                else:  # nothing consumed yet: drain the answer before the next request
                    self._pending = rid
                raise
            if header.get("id") != rid:
                await self._fail("response id mismatch")
                raise HostProtocolError(f"response id {header.get('id')!r} != request id {rid}")
            if not header.get("ok"):
                e = header.get("error") if isinstance(header.get("error"), dict) else {}
                assert isinstance(e, dict)
                problems = e.get("problems") if isinstance(e.get("problems"), list) else []
                tb = e.get("traceback")
                raise RemoteError(
                    str(e.get("type", "Unknown"))[:64],
                    str(e.get("message", ""))[:1000],
                    tb if isinstance(tb, str) else None,
                    [p for p in (problems or []) if isinstance(p, dict)][:50],
                )
            result = header.get("result")
            return (result if isinstance(result, dict) else {}), arrays

    async def _drain_pending(self) -> None:
        rid, self._pending = self._pending, None
        if rid is None:
            return
        try:
            header, _ = await asyncio.wait_for(self._read_message(), self.pending_timeout_s)
        except asyncio.CancelledError:
            if not self._in_message:
                self._pending = rid  # still unread: try again next time
            else:
                await asyncio.shield(self._fail("cancelled while draining"))
            raise
        except TimeoutError:
            await self._fail("cancelled request never answered")
            raise HostTimeout(
                f"plugin did not finish a cancelled request within {self.pending_timeout_s:g} s"
            ) from None
        if header.get("id") != rid:
            await self._fail("response id mismatch")
            raise HostProtocolError(f"response id {header.get('id')!r} != request id {rid}")

    def kill_now(self) -> None:
        """Synchronous emergency stop (e.g. when an open() is cancelled)."""
        self._broken = self._broken or "killed"
        self._kill()

    async def close(self, timeout_s: float = 1.0) -> int | None:
        """Ask the host to shut down; kill it if it does not exit promptly."""
        proc = self.proc
        if proc is None:
            return None
        if proc.returncode is None and self._broken is None:
            with contextlib.suppress(HostFailure, RemoteError, OSError):
                await self.request("shutdown", timeout_s=timeout_s)
        if proc.returncode is None:
            try:
                await asyncio.wait_for(proc.wait(), timeout_s)
            except TimeoutError:
                self._kill()
                await proc.wait()
        if proc.stdin is not None:
            proc.stdin.close()
        if self._stderr_task is not None:
            try:
                await asyncio.wait_for(self._stderr_task, 1.0)
            except (TimeoutError, asyncio.CancelledError):
                self._stderr_task.cancel()
            except Exception as exc:  # pragma: no cover - log reader failure
                log.debug("plugin stderr reader ended with %r", exc)
        return proc.returncode
