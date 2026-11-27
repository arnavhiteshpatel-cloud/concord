"""Session-level and continuous-control metrics (tracking, scrolling, session summaries)."""
from __future__ import annotations

from typing import Iterable, Optional

import numpy as np

from ..events.model import EventKind, InputEvent


def tracking_metrics(t_ms: np.ndarray, cursor: np.ndarray, target: np.ndarray,
                     radius: float) -> dict[str, float]:
    """Continuous tracking: RMS error, time on target, and lag by cross-correlation."""
    err = np.hypot(*(cursor - target).T)
    ok = ~np.isnan(err)
    err = err[ok]
    dt = float(np.median(np.diff(t_ms))) if len(t_ms) > 1 else np.nan
    lag = np.nan
    if ok.sum() > 20:
        c = cursor[ok, 0] - np.nanmean(cursor[ok, 0])
        g = target[ok, 0] - np.nanmean(target[ok, 0])
        maxlag = min(len(c) // 2, int(2000 / dt)) if dt and dt > 0 else 0
        if maxlag > 0 and np.std(c) > 0 and np.std(g) > 0:
            xc = [np.dot(c[k:], g[: len(g) - k]) for k in range(maxlag)]
            lag = float(np.argmax(xc) * dt)
    return {"rms_error_px": float(np.sqrt(np.mean(err ** 2))) if err.size else np.nan,
            "time_on_target": float(np.mean(err <= radius)) if err.size else np.nan,
            "lag_ms": lag}


def scroll_metrics(t_ms: np.ndarray, offset: np.ndarray, target_lo: float, target_hi: float,
                   sel_t: Optional[float]) -> dict[str, float]:
    """Scroll-to-target: time to target, number of times the band was passed, reversals."""
    ok = ~np.isnan(offset)
    o = offset[ok]
    inside = (o >= target_lo) & (o <= target_hi)
    entries = int(np.sum(np.diff(inside.astype(int)) == 1) + (inside[0] if o.size else 0))
    d = np.sign(np.diff(o))
    d = d[d != 0]
    rev = int(np.count_nonzero(np.diff(d))) if d.size > 1 else 0
    return {"time_to_select_ms": float(sel_t) if sel_t is not None else np.nan,
            "band_passes": float(max(entries - 1, 0)), "reversals": float(rev),
            "success": float(sel_t is not None and inside[-1] if o.size else 0)}


def performance_trend(values: np.ndarray) -> dict[str, float]:
    """Within-session variability and linear trend (per trial). A trend cannot distinguish
    fatigue from learning or device change; it is reported, never interpreted automatically."""
    v = np.asarray(values, float)
    v = v[~np.isnan(v)]
    if v.size < 3:
        return {"cv": np.nan, "slope_per_trial": np.nan, "n": float(v.size)}
    x = np.arange(v.size)
    slope = float(np.polyfit(x, v, 1)[0])
    return {"cv": float(np.std(v, ddof=1) / np.mean(v)) if np.mean(v) else np.nan,
            "slope_per_trial": slope, "n": float(v.size)}


def session_summary(events: Iterable[InputEvent], n_tasks_planned: int,
                    n_tasks_completed: int) -> dict[str, float]:
    """Summary of a session's process measures from canonical events."""
    evs = list(events)
    if not evs:
        return {"duration_min": 0.0, "completion_rate": 0.0}
    t0, t1 = evs[0].t_ms, evs[-1].t_ms
    pauses = [e for e in evs if e.kind == EventKind.PAUSE]
    resumes = [e for e in evs if e.kind == EventKind.RESUME]
    rest_ms = 0.0
    for p in pauses:
        r = next((r for r in resumes if r.t_ms >= p.t_ms), None)
        rest_ms += ((r.t_ms if r else t1) - p.t_ms)
    assists = [e for e in evs if e.kind == EventKind.ASSIST]
    dur_min = (t1 - t0) / 60000.0
    by_type: dict[str, int] = {}
    for a in assists:
        by_type[a.meta.get("assist_type", "?")] = by_type.get(a.meta.get("assist_type", "?"), 0) + 1
    out = {"duration_min": dur_min, "active_min": max(dur_min - rest_ms / 60000.0, 0.0),
           "rest_min": rest_ms / 60000.0, "interruptions": float(len(pauses)),
           "assist_events": float(len(assists)),
           "assist_per_hour": len(assists) / (dur_min / 60.0) if dur_min > 0 else np.nan,
           "completion_rate": n_tasks_completed / n_tasks_planned if n_tasks_planned else np.nan}
    for k, v in by_type.items():
        out[f"assist_{k}"] = float(v)
    return out
