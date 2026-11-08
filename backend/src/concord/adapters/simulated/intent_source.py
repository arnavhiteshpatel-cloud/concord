"""Operator-driven intention source for simulated devices.

In a real system intent comes from a participant's neural activity via a
decoder. In this simulation the *operator* (console panel or ``/api/v1/sim``)
states the intended action directly; simulated adapters then apply
profile-specific rate, latency, noise and quantization, and every resulting
event is labelled ``provenance.kind = simulated_intent``.

This object lives for the life of the server so it survives device switches.
"""

from __future__ import annotations

import asyncio
import contextlib
import math
import time
from collections import deque
from dataclasses import dataclass
from typing import Literal

POINTER_DEADMAN_S = 0.5  # pointer intent decays to zero if not refreshed
MAX_DISCRETE_QUEUE = 64


@dataclass(frozen=True, slots=True)
class DiscreteIntent:
    kind: Literal["select", "text"]
    text: str = ""
    submitted_monotonic_ns: int = 0


class OperatorIntentSource:
    def __init__(self) -> None:
        self._vx = 0.0
        self._vy = 0.0
        self._pointer_updated = 0.0
        self._discrete: deque[DiscreteIntent] = deque(maxlen=MAX_DISCRETE_QUEUE)
        self._changed = asyncio.Event()
        self.submitted_total = 0

    # --------------------------------------------------------------- operator side
    def set_pointer(self, vx: float, vy: float) -> None:
        if not (math.isfinite(vx) and math.isfinite(vy)):
            raise ValueError("pointer velocity must be finite")
        self._vx = max(-1.0, min(1.0, vx))
        self._vy = max(-1.0, min(1.0, vy))
        self._pointer_updated = time.monotonic()
        self.submitted_total += 1

    def submit_select(self) -> None:
        self._discrete.append(DiscreteIntent("select", "", time.monotonic_ns()))
        self.submitted_total += 1
        self._changed.set()

    def submit_text(self, text: str) -> None:
        if not text:
            raise ValueError("text must be non-empty")
        self._discrete.append(DiscreteIntent("text", text, time.monotonic_ns()))
        self.submitted_total += 1
        self._changed.set()

    # ---------------------------------------------------------------- device side
    def pointer(self) -> tuple[float, float]:
        """Normalized intended velocity in [-1, 1]² (zero if stale)."""
        if time.monotonic() - self._pointer_updated > POINTER_DEADMAN_S:
            return (0.0, 0.0)
        return (self._vx, self._vy)

    def drain_discrete(self) -> list[DiscreteIntent]:
        items = list(self._discrete)
        self._discrete.clear()
        self._changed.clear()
        return items

    def clear(self) -> None:
        self._discrete.clear()
        self._vx = self._vy = 0.0
        self._changed.clear()

    async def wait_changed(self, max_wait_s: float) -> None:
        if self._discrete:
            return
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(self._changed.wait(), timeout=max(0.0, max_wait_s))
