"""Fault injection: kill the plugin host process while a session is streaming."""

from __future__ import annotations

import os
import signal
import threading
import time
from dataclasses import dataclass

from concord_adapter_sdk.client import HostDied, HostError, SyncHostClient


@dataclass
class KillOutcome:
    pid: int
    killed: bool
    reads_before_kill: int
    detected: str  # "HostDied" | "HostError:<type>" | "hang" | "none"
    message: str
    detect_s: float | None  # from SIGKILL to the error reaching the certifier
    exit_code: int | None

    def to_dict(self) -> dict[str, object]:
        return {
            "pid": self.pid,
            "signal": "SIGKILL",
            "killed": self.killed,
            "reads_before_kill": self.reads_before_kill,
            "detected_as": self.detected,
            "message": self.message[:300],
            "detect_s": round(self.detect_s, 4) if self.detect_s is not None else None,
            "host_exit_code": self.exit_code,
        }


def kill_mid_stream(
    client: SyncHostClient,
    *,
    stream_s: float = 0.5,
    read_timeout_s: float = 0.1,
    grace_s: float = 5.0,
) -> KillOutcome:
    """Read continuously in a thread, SIGKILL the host after ``stream_s``, and measure how
    the failure surfaces. A ``HostDied`` within the read deadline is what Concord treats as
    a link loss (``DeviceLinkError`` -> reconnect); anything else is reported as found."""
    pid = client.proc.pid
    state: dict[str, object] = {"reads": 0}
    done = threading.Event()

    def reader() -> None:
        try:
            while True:
                client.request(
                    "read", {"timeout_s": read_timeout_s}, timeout_s=read_timeout_s + grace_s
                )
                state["reads"] = int(state["reads"]) + 1  # type: ignore[call-overload]
        except HostDied as exc:
            state["error"] = ("HostDied", str(exc))
        except HostError as exc:
            state["error"] = (f"HostError:{exc.type}", exc.message)
        except Exception as exc:  # anything else is reported verbatim
            state["error"] = (type(exc).__name__, str(exc))
        state["t_error"] = time.monotonic()
        done.set()

    th = threading.Thread(target=reader, daemon=True)
    th.start()
    time.sleep(stream_s)
    reads_before = int(state["reads"])  # type: ignore[call-overload]
    if done.is_set():  # the session failed before the kill
        err = state.get("error", ("none", ""))
        assert isinstance(err, tuple)
        return KillOutcome(
            pid,
            False,
            reads_before,
            f"before kill: {err[0]}",
            str(err[1]),
            None,
            client.proc.poll(),
        )
    t_kill = time.monotonic()
    killed = True
    try:
        os.kill(pid, signal.SIGKILL)
    except ProcessLookupError:
        killed = False
    finished = done.wait(read_timeout_s + grace_s + 5.0)
    exit_code = client.proc.poll()
    if not finished:
        client.kill()
        return KillOutcome(
            pid,
            killed,
            reads_before,
            "hang",
            "no error within the read deadline after the host was killed",
            None,
            exit_code,
        )
    err = state.get("error", ("none", ""))
    assert isinstance(err, tuple)
    t_err = state.get("t_error")
    detect = float(t_err) - t_kill if isinstance(t_err, float) else None
    return KillOutcome(pid, killed, reads_before, str(err[0]), str(err[1]), detect, exit_code)
