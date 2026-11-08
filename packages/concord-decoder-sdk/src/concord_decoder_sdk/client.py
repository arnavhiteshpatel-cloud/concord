"""Synchronous client for one decoder-host process.

Used by ``host --list`` / ``host --check``, ``concord-decoder check`` and decoder authors'
own tests: it runs the decoder exactly as Concord does (separate process, binary IPC,
host-side output validation). Concord's runtime uses an asyncio client over the same
protocol.
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
from pathlib import Path
from typing import IO, Any

import numpy as np
from numpy.typing import NDArray

from concord_decoder_sdk import ipc


class DecoderHostError(Exception):
    """The host answered with a typed error (``type`` is one of the ``ipc`` constants)."""

    def __init__(
        self,
        type_: str,
        message: str,
        traceback: str | None = None,
        problems: Sequence[Mapping[str, Any]] = (),
    ) -> None:
        self.type, self.message, self.traceback = type_, message, traceback
        self.problems = list(problems)
        super().__init__(f"{type_}: {message}")


class DecoderHostDied(Exception):
    """The host process exited, hung past a timeout, or broke the protocol."""


_EOF = object()


def host_args(
    ref: str | None = None, model_path: Path | None = None, trusted_sha256: str | None = None
) -> list[str]:
    """Arguments after ``python -m concord_decoder_sdk.host``."""
    if (ref is None) == (model_path is None):
        raise ValueError("give exactly one of ref or model_path")
    args = [ref] if ref is not None else ["--model", str(model_path)]
    if trusted_sha256:
        args += ["--trusted-sha256", trusted_sha256]
    return [a for a in args if a is not None]


class SyncDecoderHost:
    def __init__(
        self,
        *,
        ref: str | None = None,
        model_path: Path | None = None,
        trusted_sha256: str | None = None,
        python: str | None = None,
        env: Mapping[str, str] | None = None,
        hello_timeout_s: float = 30.0,
        command: Sequence[str] | None = None,
    ) -> None:
        cmd = (
            list(command)
            if command
            else [
                python or sys.executable,
                "-m",
                "concord_decoder_sdk.host",
                *host_args(ref, model_path, trusted_sha256),
            ]
        )
        self.proc = subprocess.Popen(
            cmd,
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
            raise DecoderHostDied(f"unexpected first message from host: {self.hello!r}"[:300])

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
            raise DecoderHostDied(
                f"decoder host did not answer within {timeout_s:g} s (killed)"
            ) from None
        if item is _EOF:
            code = self.proc.wait(timeout=5)
            tail = " | ".join(list(self.stderr_tail)[-5:])
            raise DecoderHostDied(f"decoder host exited (code {code}){': ' + tail if tail else ''}")
        if isinstance(item, Exception):
            self.kill()
            raise DecoderHostDied(f"protocol error from decoder host: {item}")
        return item  # type: ignore[return-value]

    def request(
        self,
        cmd: str,
        args: Mapping[str, Any] | None = None,
        buffers: Sequence[NDArray[Any]] = (),
        *,
        timeout_s: float = 30.0,
    ) -> tuple[dict[str, Any], list[NDArray[Any]]]:
        self._id += 1
        assert self.proc.stdin is not None
        try:
            ipc.write_message(
                self.proc.stdin, {"id": self._id, "cmd": cmd, "args": dict(args or {})}, buffers
            )
        except (BrokenPipeError, OSError) as exc:
            raise DecoderHostDied(f"decoder host is gone: {exc}") from None
        header, arrays = self._next(timeout_s)
        if header.get("id") != self._id:
            self.kill()
            raise DecoderHostDied(f"response id {header.get('id')!r} != request id {self._id}")
        if not header.get("ok"):
            e = header.get("error") or {}
            raise DecoderHostError(
                str(e.get("type", "Unknown")),
                str(e.get("message", "")),
                e.get("traceback"),
                e.get("problems") or [],
            )
        result = header.get("result")
        return (result if isinstance(result, dict) else {}), arrays

    def manifest(self, timeout_s: float = 30.0) -> dict[str, Any]:
        return self.request("manifest", timeout_s=timeout_s)[0]

    def load(self, timeout_s: float = 60.0) -> dict[str, Any]:
        return self.request("load", timeout_s=timeout_s)[0]

    def reset(self) -> None:
        self.request("reset")

    def step(
        self,
        features: NDArray[Any],
        timestamps_s: Sequence[float] | None,
        timeout_s: float = 10.0,
    ) -> tuple[NDArray[np.float64], NDArray[np.float64] | None]:
        x = np.ascontiguousarray(np.atleast_2d(np.asarray(features, dtype=np.float64)))
        args = {"timestamps_s": list(timestamps_s)} if timestamps_s is not None else {}
        _, arrays = self.request("step", args, [x], timeout_s=timeout_s)
        if not arrays:
            raise DecoderHostDied("step answered without values")
        return arrays[0], arrays[1] if len(arrays) > 1 else None

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
            except (DecoderHostDied, DecoderHostError, subprocess.TimeoutExpired):
                pass
        self.kill()
        for f in (self.proc.stdin, self.proc.stdout, self.proc.stderr):
            if f is not None:
                with contextlib.suppress(OSError):
                    f.close()

    def __enter__(self) -> SyncDecoderHost:
        return self

    def __exit__(self, *exc: object) -> None:
        self.shutdown()
