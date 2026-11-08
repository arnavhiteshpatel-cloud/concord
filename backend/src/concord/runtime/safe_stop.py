"""Safe stop & disconnect: one operator action that leaves nothing running.

Order matters: command output first (nothing decoded may reach an application after the
operator asked to stop), then the recording (closed cleanly, before the source goes away),
then decoding, then acquisition. Every step is attempted even if an earlier one fails, and
each is reported with what it did.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable

from pydantic import BaseModel

from concord.runtime.runtime import Runtime, RuntimeCommandError

log = logging.getLogger(__name__)


class SafeStopStep(BaseModel):
    step: str  # command_output | recording | decoding | source
    done: bool  # something was running and was stopped
    detail: str
    error: str | None = None
    ms: float


class SafeStopReport(BaseModel):
    at_ns: int
    reason: str
    steps: list[SafeStopStep]
    state: str  # runtime state afterwards
    ok: bool  # every step succeeded (nothing left running)


async def safe_stop(runtime: Runtime, reason: str = "safe stop by operator") -> SafeStopReport:
    steps: list[SafeStopStep] = []

    def run(step: str, fn: Callable[[], tuple[bool, str]]) -> None:  # synchronous steps
        t0 = time.perf_counter()
        try:
            done, detail = fn()
            steps.append(
                SafeStopStep(step=step, done=done, detail=detail, ms=_ms(t0)),
            )
        except Exception as exc:
            log.exception("safe stop: %s failed", step)
            steps.append(
                SafeStopStep(step=step, done=False, detail="failed", error=str(exc), ms=_ms(t0))
            )

    def control() -> tuple[bool, str]:
        on = runtime.stop_control(reason)
        return on, "command output turned off" if on else "command output was already off"

    def recording() -> tuple[bool, str]:
        name = runtime.recorder.active_name
        if name is None:
            return False, "no recording in progress"
        info = runtime.stop_recording()
        return True, f"recording {info.name} closed"

    def decoding() -> tuple[bool, str]:
        if not runtime.pipeline.running:
            return False, "decoding was not running"
        runtime.stop_pipeline()
        return True, "decoding stopped"

    run("command_output", control)
    run("recording", recording)
    run("decoding", decoding)
    t0 = time.perf_counter()
    connected = runtime.adapter is not None or runtime.device is not None
    try:
        await runtime.disconnect()
        steps.append(
            SafeStopStep(
                step="source",
                done=connected,
                detail="source disconnected" if connected else "no source connected",
                ms=_ms(t0),
            )
        )
    except RuntimeCommandError as exc:
        steps.append(
            SafeStopStep(step="source", done=False, detail="failed", error=exc.message, ms=_ms(t0))
        )
    report = SafeStopReport(
        at_ns=time.time_ns(),
        reason=reason,
        steps=steps,
        state=runtime.state.value,
        ok=all(s.error is None for s in steps),
    )
    log.info(
        "safe stop (%s): %s",
        reason,
        ", ".join(f"{s.step}={'stopped' if s.done else 'idle'}" for s in steps),
    )
    return report


def _ms(t0: float) -> float:
    return round((time.perf_counter() - t0) * 1000, 3)
