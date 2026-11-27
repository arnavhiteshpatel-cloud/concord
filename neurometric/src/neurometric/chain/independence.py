"""Functional independence measurement model (EXPERIMENTAL, unvalidated).

Device activity does not imply independent function. Each task attempt is classified into one
state of an explicit hierarchy, using only recorded events and reports:

    device_unavailable < device_not_connected < not_used < abandoned
    < completed_other_input < completed_with_assistance < completed_independently

Assistance is recorded as ASSIST events (participant, care partner or staff report) with a type.
The derived score is labelled EXPERIMENTAL until validated against external anchors (see
CLINICAL_VALIDATION_PLAN.md). Weights are configurable and versioned; defaults are a priori
judgements, not estimates.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Optional

import numpy as np

from ..events.model import ASSIST_TYPES, EventKind, InputEvent

STATES = ["device_unavailable", "device_not_connected", "not_used", "abandoned",
          "completed_other_input", "completed_with_assistance", "completed_independently"]

#: a-priori assistance severity weights (0 = no help, 1 = someone else did it). VERSIONED.
ASSIST_SEVERITY_V1 = {"setup": 0.2, "verbal": 0.3, "troubleshooting": 0.4, "calibration": 0.4,
                      "physical": 0.7, "task_completion": 1.0}
MODEL_VERSION = "independence-model-0.1-experimental"


@dataclass
class AttemptContext:
    device_available: bool = True
    device_connected: bool = True
    planned_stream: Optional[str] = None  # the device stream under study
    completed: bool = False
    abandoned: bool = False


@dataclass
class AttemptResult:
    state: str
    assists: dict = field(default_factory=dict)
    assist_severity: float = 0.0
    used_planned_device: bool = False
    used_other_input: bool = False
    model_version: str = MODEL_VERSION
    label: str = "EXPERIMENTAL - not a validated measure of independence"


def classify_attempt(events: Iterable[InputEvent], ctx: AttemptContext,
                     weights: dict = ASSIST_SEVERITY_V1) -> AttemptResult:
    evs = list(events)
    assists: dict[str, int] = {}
    for e in evs:
        if e.kind == EventKind.ASSIST:
            t = e.meta.get("assist_type")
            assists[t] = assists.get(t, 0) + 1
    action = [e for e in evs if e.kind not in (EventKind.MARKER, EventKind.ASSIST,
                                               EventKind.PAUSE, EventKind.RESUME)]
    streams = {e.stream_id for e in action}
    used_planned = ctx.planned_stream in streams if ctx.planned_stream else bool(action)
    other = bool(ctx.planned_stream) and bool(streams - {ctx.planned_stream})
    sev = max((weights.get(k, 1.0) for k in assists), default=0.0)
    if not ctx.device_available:
        st = "device_unavailable"
    elif not ctx.device_connected:
        st = "device_not_connected"
    elif not action:
        st = "not_used"
    elif not ctx.completed:
        st = "abandoned"
    elif other and not used_planned:
        st = "completed_other_input"
    elif assists:
        st = "completed_with_assistance"
    else:
        st = "completed_independently"
    return AttemptResult(st, assists, sev, used_planned, other)


def independence_summary(results: list[AttemptResult]) -> dict:
    """Experimental summary over attempts: state counts, proportion completed independently,
    and an assistance-weighted completion score in [0, 1]."""
    n = len(results)
    counts = {s: sum(r.state == s for r in results) for s in STATES}
    if n == 0:
        return {"n_attempts": 0, **counts}
    weighted = np.mean([(1 - r.assist_severity) if r.state in ("completed_independently",
                                                                "completed_with_assistance")
                        else 0.0 for r in results])
    return {"n_attempts": n, **counts,
            "prop_completed_independently": counts["completed_independently"] / n,
            "prop_completed_any": (counts["completed_independently"] + counts["completed_with_assistance"]
                                   + counts["completed_other_input"]) / n,
            "assistance_weighted_completion": float(weighted),
            "model_version": MODEL_VERSION,
            "label": "EXPERIMENTAL - weights are a-priori judgements, not validated"}
