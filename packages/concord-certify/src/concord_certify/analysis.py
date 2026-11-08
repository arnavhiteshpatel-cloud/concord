"""Pure numerical analysis of what a session delivered (no I/O)."""

from __future__ import annotations

from typing import Any

import numpy as np
from numpy.typing import NDArray

from concord_certify.acquire import StreamTrack


def _r(x: float, nd: int = 4) -> float:
    return float(round(x, nd))


def distribution(values: NDArray[np.float64] | list[float], scale: float = 1.0) -> dict[str, Any]:
    """p50 / p95 / p99 / max (and min, mean, n) of ``values * scale``."""
    a = np.asarray(values, dtype=np.float64) * scale
    if a.size == 0:
        return {"n": 0}
    p50, p95, p99 = np.percentile(a, [50, 95, 99])
    return {
        "n": int(a.size),
        "min": _r(float(a.min())),
        "p50": _r(float(p50)),
        "p95": _r(float(p95)),
        "p99": _r(float(p99)),
        "max": _r(float(a.max())),
        "mean": _r(float(a.mean())),
    }


def linear_fit(x: NDArray[np.float64], y: NDArray[np.float64]) -> tuple[float, float] | None:
    """Least-squares ``y = slope * x + intercept`` (centred for numerical stability)."""
    if x.size < 2 or float(np.ptp(x)) == 0.0:
        return None
    xm, ym = float(x.mean()), float(y.mean())
    dx = x - xm
    slope = float(np.dot(dx, y - ym) / np.dot(dx, dx))
    return slope, ym - slope * xm


def timestamp_rate(track: StreamTrack) -> dict[str, Any] | None:
    """Rate implied by the source's own timestamps: index span / time span (counts lost
    samples correctly because indices jump over them). Also a least-squares estimate."""
    ts, idx = track.timestamps(), track.indices()
    if ts.size < 2:
        return None
    span_t = float(ts[-1] - ts[0])
    span_i = int(idx[-1] - idx[0])
    if span_t <= 0 or span_i <= 0:
        return {"samples": int(ts.size), "time_span_s": _r(span_t, 6), "rate_hz": None}
    fit = linear_fit(idx.astype(np.float64), ts)
    return {
        "samples": int(ts.size),
        "time_span_s": _r(span_t, 6),
        "rate_hz": _r(span_i / span_t, 6),
        "rate_hz_lsq": _r(1.0 / fit[0], 6) if fit and fit[0] > 0 else None,
    }


def delivery_rate(track: StreamTrack) -> dict[str, Any] | None:
    """Samples per second of the host's monotonic clock, from a least-squares fit of the
    cumulative sample count against arrival time (robust to chunking and start-up)."""
    arr = track.arrivals
    if len(arr) < 3:
        return None
    t = np.array([a.t_mono for a in arr])
    c = np.array([a.cumulative for a in arr], dtype=np.float64)
    fit = linear_fit(t, c)
    span = float(t[-1] - t[0])
    return {
        "chunks": len(arr),
        "arrival_span_s": _r(span, 3),
        "rate_hz": _r(fit[0], 4) if fit else None,
        "rate_hz_endpoints": _r((c[-1] - c[0]) / span, 4) if span > 0 else None,
    }


def jitter(track: StreamTrack, nominal_hz: float) -> dict[str, Any]:
    """Per-sample timestamp deviations and inter-chunk arrival intervals (milliseconds).

    * ``residual_ms``: |timestamp - linear fit of timestamp vs sample index| (offset and
      drift removed; what is left is jitter).
    * ``interval_error_ms``: |difference of consecutive timestamps - 1 / nominal rate|
      (consecutive indices only, i.e. not across a gap).
    * ``arrival_interval_ms``: time between successive chunks of this stream on the host's
      monotonic clock.
    """
    out: dict[str, Any] = {}
    ts, idx = track.timestamps(), track.indices()
    if ts.size >= 3:
        fit = linear_fit(idx.astype(np.float64), ts)
        if fit is not None:
            res = np.abs(ts - (fit[0] * idx + fit[1]))
            out["residual_ms"] = distribution(res, 1e3)
        if nominal_hz > 0:
            consecutive = np.diff(idx) == 1
            err = np.abs(np.diff(ts)[consecutive] - 1.0 / nominal_hz)
            out["interval_error_ms"] = distribution(err, 1e3)
    t = np.array([a.t_mono for a in track.arrivals])
    if t.size >= 2:
        out["arrival_interval_ms"] = distribution(np.diff(t), 1e3)
        out["samples_per_chunk"] = distribution([float(a.n) for a in track.arrivals])
    out["truncated_to_samples"] = track.stored if track.truncated else None
    return out


def offsets(track: StreamTrack, domain: str) -> dict[str, Any] | None:
    """Arrival time minus the newest sample's timestamp, per chunk, on the clock that the
    declared domain should match (wall clock for ``unix``, liblsl ``local_clock`` for ``lsl``
    when available, else the host's monotonic clock), plus the drift of the source clock
    against the host's monotonic clock (ppm; positive = source clock runs slow)."""
    arr = track.arrivals
    if not arr:
        return None
    t_mono = np.array([a.t_mono for a in arr])
    last = np.array([a.ts_last for a in arr])
    first = np.array([a.ts_first for a in arr])
    if domain == "unix":
        ref_name, ref = "wall clock (time.time)", np.array([a.t_wall for a in arr])
    elif domain == "lsl" and all(a.t_lsl is not None for a in arr):
        ref_name = "liblsl local_clock"
        ref = np.array([a.t_lsl if a.t_lsl is not None else 0.0 for a in arr])
    else:
        ref_name, ref = "host monotonic clock", t_mono
    off_new = ref - last
    off_old = ref - first
    out: dict[str, Any] = {
        "reference_clock": ref_name,
        "offset_newest_s": distribution(off_new),
        "offset_oldest_s": distribution(off_old),
    }
    fit = linear_fit(t_mono, t_mono - last)
    if fit is not None and float(t_mono[-1] - t_mono[0]) >= 1.0:
        out["drift_ppm"] = _r(fit[0] * 1e6, 1)
        out["drift_span_s"] = _r(float(t_mono[-1] - t_mono[0]), 2)
    else:
        out["drift_ppm"] = None
    return out


def sample_counter_residual(track: StreamTrack, nominal_hz: float) -> float | None:
    """Max |timestamp - (t0 + (index - index0) / nominal)| in seconds."""
    ts, idx = track.timestamps(), track.indices()
    if ts.size < 2 or nominal_hz <= 0:
        return None
    ideal = ts[0] + (idx - idx[0]) / nominal_hz
    return float(np.max(np.abs(ts - ideal)))
