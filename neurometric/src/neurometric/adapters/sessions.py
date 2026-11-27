"""Conversions between canonical event streams and scoring records.

* ``step_to_events``: a simulated acquisition step -> canonical events (simulated adapter).
* ``events_to_pointing_trials``: a recorded event stream with task markers -> PointingTrials,
  so recorded and simulated data go through the SAME metric code.
* ``replay``: re-emit a stored stream with optional time scaling (replay adapter).
"""
from __future__ import annotations

from typing import Iterable, Optional

import numpy as np

from ..events.model import EventKind, InputEvent, Modality
from ..metrics.pointing import PointingTrials


def step_to_events(step, session_id: str, dt_ms: float = 10.0, t_offset_ms: float = 0.0,
                   trial_offset: int = 0, modality: Modality = Modality.SIMULATED) -> list[list[InputEvent]]:
    """One event list per batch element (participant)."""
    B, T, _ = step.traj.shape
    out = []
    for b in range(B):
        sid = f"{session_id}_{b:04d}"
        evs = []
        s = 0

        def ev(**kw):
            nonlocal s
            e = InputEvent(session_id=sid, stream_id="sim", modality=modality, seq=s,
                           synthetic=True, **kw)
            s += 1
            evs.append(e)

        tc, th = step.target_c[b], step.target_h[b]
        ev(t_ms=t_offset_ms, kind=EventKind.MARKER,
           meta={"marker": "stimulus_on", "trial": trial_offset,
                 "target": [float(tc[0]), float(tc[1]), float(th[0]), float(th[1])],
                 "start": [float(step.start[b, 0]), float(step.start[b, 1])]})
        n = int(np.sum(~np.isnan(step.traj[b, :, 0])))
        for k in range(n):
            ev(t_ms=t_offset_ms + k * dt_ms, kind=EventKind.POINTER_MOVE,
               x=float(step.traj[b, k, 0]), y=float(step.traj[b, k, 1]))
        for _ in range(int(step.n_empty_selects[b])):
            pass  # empty selections are not time-resolved in the step summary
        if step.sel_item[b] != -2:
            ev(t_ms=t_offset_ms + float(step.sel_t[b]), kind=EventKind.CLICK,
               x=float(step.sel_pos[b, 0]), y=float(step.sel_pos[b, 1]))
        ev(t_ms=t_offset_ms + (float(step.sel_t[b]) if step.sel_item[b] != -2 else (n - 1) * dt_ms),
           kind=EventKind.MARKER, meta={"marker": "trial_end", "trial": trial_offset,
                                        "selected_item": int(step.sel_item[b])})
        out.append(evs)
    return out


def events_to_pointing_trials(events: Iterable[InputEvent]) -> PointingTrials:
    """Segment a stream into trials using stimulus_on / trial_end markers.

    stimulus_on.meta: target [cx, cy, hw, hh], start [x, y] (optional; else first sample),
    items (optional list of [cx,cy,hw,hh] with the target first, for item classification).
    trial_end.meta: selected_item (optional; else computed from the selection position).
    The terminating selection is the first CLICK/DWELL_SELECT/SELECT after stimulus_on whose
    item is not empty space (or any selection if meta.end_on_empty is true).
    """
    evs = sorted(events, key=lambda e: (e.t_ms, e.stream_id, e.seq))
    trials = []
    cur = None
    for e in evs:
        if e.kind == EventKind.MARKER and e.meta.get("marker") == "stimulus_on":
            cur = {"t0": e.t_ms, "meta": e.meta, "xy": [], "t": [], "sel": None, "empty": 0}
            continue
        if cur is None:
            continue
        if e.kind == EventKind.POINTER_MOVE:
            cur["xy"].append((e.x, e.y))
            cur["t"].append(e.t_ms - cur["t0"])
        elif e.is_selection and cur["sel"] is None and e.x is not None:
            items = cur["meta"].get("items") or [cur["meta"]["target"]]
            hit = -1
            for i, (cx, cy, hw, hh) in enumerate(items):
                if abs(e.x - cx) <= hw and abs(e.y - cy) <= hh:
                    hit = i
                    break
            if hit == -1 and not cur["meta"].get("end_on_empty", True):
                cur["empty"] += 1
            else:
                cur["sel"] = (e.t_ms - cur["t0"], e.x, e.y, hit)
                cur["xy"].append((e.x, e.y))
                cur["t"].append(e.t_ms - cur["t0"])
        elif e.kind == EventKind.MARKER and e.meta.get("marker") == "trial_end":
            trials.append(cur)
            cur = None
    if not trials:
        raise ValueError("no complete trials (stimulus_on ... trial_end) in stream")
    T = max(len(t["xy"]) for t in trials)
    N = len(trials)
    traj = np.full((N, T, 2), np.nan)
    tt = np.full((N, T), np.nan)
    start = np.zeros((N, 2))
    tc = np.zeros((N, 2))
    th = np.zeros((N, 2))
    sel_t = np.full(N, np.nan)
    sel_pos = np.full((N, 2), np.nan)
    sel_item = np.full(N, -2)
    empty = np.zeros(N, int)
    for i, tr in enumerate(trials):
        xy = np.array(tr["xy"], float) if tr["xy"] else np.zeros((0, 2))
        traj[i, : len(xy)] = xy
        tt[i, : len(xy)] = tr["t"]
        m = tr["meta"]
        start[i] = m.get("start") or (xy[0] if len(xy) else [np.nan, np.nan])
        tc[i] = m["target"][:2]
        th[i] = m["target"][2:4]
        empty[i] = tr["empty"]
        if tr["sel"] is not None:
            sel_t[i], sel_pos[i, 0], sel_pos[i, 1], sel_item[i] = tr["sel"]
        elif len(xy):
            sel_pos[i] = xy[-1]
    return PointingTrials(traj, tt, start, tc, th, sel_t, sel_pos, sel_item, empty)


def replay(events: Iterable[InputEvent], speed: float = 1.0, session_id: Optional[str] = None,
           stream_suffix: str = ":replay") -> list[InputEvent]:
    """Re-emit a stored stream (time-scaled), marked as replayed; never changes geometry."""
    out = []
    for e in events:
        d = e.to_dict()
        d["t_ms"] = e.t_ms / speed
        d["stream_id"] = e.stream_id + stream_suffix
        if session_id:
            d["session_id"] = session_id
        meta = dict(e.meta)
        meta["replayed_from"] = e.session_id
        d["meta"] = meta
        d["modality"] = Modality.REPLAY.value if e.modality not in (Modality.SIMULATED,) else e.modality.value
        out.append(InputEvent.from_dict(d))
    return out
