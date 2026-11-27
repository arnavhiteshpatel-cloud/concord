"""Canonical input events.

Every input source (mouse, switch, eye gaze through an OS pointer, a BCI cursor exposed as a
pointer, a simulator, a replay) is normalised into this one representation, so a functional task
can be scored without knowing how the input was produced.

Design rules (see docs/science/INPUT_ABSTRACTION.md):

* ``t_ms`` is a *monotonic session clock* in milliseconds (browser ``performance.now()`` style),
  never wall-clock time. Wall-clock time, when known, is kept separately for provenance.
* Coordinates are task-space CSS pixels of the task canvas (origin top-left, y down).
* ``confidence`` is ``None`` unless the *source itself* reported a value. NeuroMetric never
  fabricates a decoder confidence.
* Measurement never controls the device: these events flow one way, from the input to the task.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Iterable, Optional

SCHEMA_VERSION = "1.0"


class EventKind(str, Enum):
    POINTER_MOVE = "pointer_move"
    POINTER_DOWN = "pointer_down"
    POINTER_UP = "pointer_up"
    CLICK = "click"
    DRAG_START = "drag_start"
    DRAG_END = "drag_end"
    SCROLL = "scroll"
    TEXT_INPUT = "text_input"
    KEY = "key"
    DWELL_SELECT = "dwell_select"
    SWITCH = "switch"
    SELECT = "select"  # generic discrete selection from a non-pointer source (e.g. BCI "click")
    CANCEL = "cancel"
    PAUSE = "pause"
    RESUME = "resume"
    ASSIST = "assist"  # someone else helped: setup, physical, verbal, troubleshooting, calibration
    MARKER = "marker"  # task engine markers: trial_start, stimulus_on, trial_end, block_start ...


class Modality(str, Enum):
    MOUSE = "mouse"
    TRACKPAD = "trackpad"
    TOUCH = "touch"
    PEN = "pen"
    KEYBOARD = "keyboard"
    SWITCH = "switch"
    EYE_GAZE = "eye_gaze"
    HEAD_POINTER = "head_pointer"
    JOYSTICK = "joystick"
    GAMEPAD = "gamepad"
    BCI_CURSOR = "bci_cursor"
    BCI_SELECT = "bci_select"
    SIMULATED = "simulated"
    REPLAY = "replay"
    OTHER = "other"


#: Kinds that represent a discrete user selection for scoring purposes.
SELECTION_KINDS = frozenset(
    {EventKind.CLICK, EventKind.DWELL_SELECT, EventKind.SELECT, EventKind.SWITCH}
)

ASSIST_TYPES = (
    "setup",
    "physical",
    "verbal",
    "troubleshooting",
    "calibration",
    "task_completion",
)


@dataclass(frozen=True)
class InputEvent:
    t_ms: float
    kind: EventKind
    session_id: str
    stream_id: str
    modality: Modality
    seq: int = 0
    x: Optional[float] = None
    y: Optional[float] = None
    dx: Optional[float] = None
    dy: Optional[float] = None
    button: Optional[int] = None
    key: Optional[str] = None
    text: Optional[str] = None
    switch_id: Optional[str] = None
    confidence: Optional[float] = None
    calibration_state: Optional[str] = None
    synthetic: bool = False
    meta: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["kind"] = self.kind.value
        d["modality"] = self.modality.value
        d["schema_version"] = SCHEMA_VERSION
        return {k: v for k, v in d.items() if v is not None and v != {}}

    @staticmethod
    def from_dict(d: dict[str, Any]) -> "InputEvent":
        d = dict(d)
        d.pop("schema_version", None)
        d["kind"] = EventKind(d["kind"])
        d["modality"] = Modality(d["modality"])
        d.setdefault("meta", {})
        return InputEvent(**d)

    @property
    def is_selection(self) -> bool:
        return self.kind in SELECTION_KINDS


class EventValidationError(ValueError):
    pass


def validate_event(ev: InputEvent) -> None:
    """Raise :class:`EventValidationError` if an event violates the canonical contract."""
    import math

    if not isinstance(ev.t_ms, (int, float)) or not math.isfinite(ev.t_ms) or ev.t_ms < 0:
        raise EventValidationError(f"t_ms must be a finite non-negative number, got {ev.t_ms!r}")
    if ev.kind in (EventKind.POINTER_MOVE, EventKind.POINTER_DOWN, EventKind.POINTER_UP,
                   EventKind.CLICK, EventKind.DWELL_SELECT, EventKind.DRAG_START,
                   EventKind.DRAG_END):
        if ev.x is None or ev.y is None:
            raise EventValidationError(f"{ev.kind.value} requires x and y")
        if not (math.isfinite(ev.x) and math.isfinite(ev.y)):
            raise EventValidationError("x/y must be finite")
    if ev.kind == EventKind.SCROLL and ev.dx is None and ev.dy is None:
        raise EventValidationError("scroll requires dx or dy")
    if ev.kind == EventKind.TEXT_INPUT and ev.text is None:
        raise EventValidationError("text_input requires text")
    if ev.kind == EventKind.SWITCH and not ev.switch_id:
        raise EventValidationError("switch requires switch_id")
    if ev.kind == EventKind.ASSIST:
        at = ev.meta.get("assist_type")
        if at not in ASSIST_TYPES:
            raise EventValidationError(f"assist requires meta.assist_type in {ASSIST_TYPES}")
    if ev.confidence is not None:
        if not (0.0 <= ev.confidence <= 1.0):
            raise EventValidationError("confidence must be within [0, 1]")
        if not ev.meta.get("confidence_source"):
            raise EventValidationError(
                "confidence present without meta.confidence_source: NeuroMetric only stores "
                "confidence values reported by the input source itself"
            )
    if not ev.session_id or not ev.stream_id:
        raise EventValidationError("session_id and stream_id are required")


def check_stream(events: Iterable[InputEvent]) -> dict[str, Any]:
    """Check ordering and integrity of an event stream.

    Returns a report with counts of non-monotonic timestamps (per stream), duplicate sequence
    numbers and sequence gaps (dropped events). Does not mutate input.
    """
    last_t: dict[str, float] = {}
    last_seq: dict[str, int] = {}
    seen: set[tuple[str, int]] = set()
    report = {"n": 0, "non_monotonic": 0, "duplicate_seq": 0, "seq_gaps": 0, "gap_events": 0,
              "streams": set()}
    for ev in events:
        report["n"] += 1
        s = ev.stream_id
        report["streams"].add(s)
        if s in last_t and ev.t_ms < last_t[s]:
            report["non_monotonic"] += 1
        last_t[s] = max(ev.t_ms, last_t.get(s, ev.t_ms))
        key = (s, ev.seq)
        if key in seen:
            report["duplicate_seq"] += 1
        seen.add(key)
        if s in last_seq and ev.seq > last_seq[s] + 1:
            report["seq_gaps"] += 1
            report["gap_events"] += ev.seq - last_seq[s] - 1
        last_seq[s] = max(ev.seq, last_seq.get(s, ev.seq))
    report["streams"] = sorted(report["streams"])
    return report


def merge_streams(*streams: Iterable[InputEvent]) -> list[InputEvent]:
    """Merge several per-device streams into one session timeline.

    Stable ordering key: (t_ms, stream_id, seq) so that simultaneous events from different
    devices are ordered deterministically and each device keeps its own order.
    """
    out: list[InputEvent] = []
    for s in streams:
        out.extend(s)
    out.sort(key=lambda e: (e.t_ms, e.stream_id, e.seq))
    return out
