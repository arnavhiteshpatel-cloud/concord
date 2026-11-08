"""Timing analysis: sampling rate, discontinuities, clock offsets, drift and ingest delay.

Clock domains (never mixed without an explicit measured mapping):

* **source clock** - LSL: the publisher's ``lsl_local_clock`` (XDF raw timestamps and
  BrainOS ``device_timestamp_ns``); Open Ephys: the acquisition sample clock
  (``sample_number / sample_rate``).
* **recorder clock** - LabRecorder's host ``lsl_local_clock``; related to the source clock by
  the ClockOffset chunks LabRecorder writes (``recorder - source``).
* **BrainOS wall clock** - ``timestamp_ns`` (UTC ns at ingest). Related to the source clock only
  through a measured pair (``brainos-hwval capture`` sidecar) or not at all; without the pair,
  only *drift* and *spread* (not absolute latency) are meaningful.
"""

from __future__ import annotations

import itertools
import math
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

import numpy as np
from numpy.typing import NDArray

from brainos_hwval.brainos_rec import Frame


@dataclass
class LineFit:
    slope: float
    intercept: float
    residual_std: float
    residual_max: float
    n: int

    def to_json(self) -> dict[str, Any]:
        return {
            "slope": self.slope,
            "intercept": self.intercept,
            "residual_std": self.residual_std,
            "residual_max_abs": self.residual_max,
            "n": self.n,
        }


def fit_line(x: NDArray[np.float64], y: NDArray[np.float64]) -> LineFit | None:
    if len(x) < 2 or np.ptp(x) == 0:
        return None
    xm, ym = float(np.mean(x)), float(np.mean(y))
    dx = x - xm
    slope = float(np.dot(dx, y - ym) / np.dot(dx, dx))
    intercept = ym - slope * xm
    resid = y - (slope * x + intercept)
    return LineFit(slope, intercept, float(np.std(resid)), float(np.max(np.abs(resid))), len(x))


def gaps(ts: NDArray[np.float64], rate: float, jitter_s: float = 0.002) -> dict[str, Any]:
    """Discontinuities in per-sample timestamps (LSL / XDF)."""
    if len(ts) < 2 or rate <= 0:
        return {"gaps": 0, "regressions": 0, "est_missing": 0, "examples": []}
    period = 1.0 / rate
    dt = np.diff(ts)
    gap_idx = np.flatnonzero((dt > 1.5 * period) & (dt - period > jitter_s))
    reg_idx = np.flatnonzero(dt <= 0)
    est = int(np.sum(np.maximum(np.round(dt[gap_idx] / period) - 1, 1))) if gap_idx.size else 0
    ex = [
        {"after_row": int(i), "t_s": float(ts[i]), "dt_s": float(dt[i])}
        for i in np.concatenate([gap_idx, reg_idx])[:10]
    ]
    return {
        "gaps": int(gap_idx.size),
        "regressions": int(reg_idx.size),
        "est_missing": est,
        "examples": ex,
        "rows": [int(i) for i in gap_idx[:1000]],
    }


def sample_number_breaks(sn: NDArray[np.int64]) -> dict[str, Any]:
    """Discontinuities in Open Ephys sample numbers (jumps and resets)."""
    if len(sn) < 2:
        return {"jumps": 0, "regressions": 0, "missing_numbers": 0, "examples": []}
    d = np.diff(sn)
    jumps = np.flatnonzero(d > 1)
    regs = np.flatnonzero(d <= 0)
    ex = [
        {"after_row": int(i), "sample_number": int(sn[i]), "next": int(sn[i + 1])}
        for i in np.sort(np.concatenate([jumps, regs]))[:10]
    ]
    return {
        "jumps": int(jumps.size),
        "regressions": int(regs.size),
        "missing_numbers": int(np.sum(d[jumps] - 1)) if jumps.size else 0,
        "examples": ex,
    }


def effective_rate(ts: NDArray[np.float64], gap_rows: Sequence[int]) -> dict[str, Any]:
    """Sampling rate measured from timestamps over the longest gap-free segment."""
    if len(ts) < 3:
        return {"rate_hz": None}
    bounds = [0, *[r + 1 for r in gap_rows], len(ts)]
    seg = max(itertools.pairwise(bounds), key=lambda ab: ab[1] - ab[0])
    a, b = seg
    if b - a < 3:
        return {"rate_hz": None}
    idx = np.arange(a, b, dtype=np.float64)
    fit = fit_line(idx, ts[a:b])
    if fit is None or fit.slope <= 0:
        return {"rate_hz": None}
    return {
        "rate_hz": 1.0 / fit.slope,
        "segment_rows": [a, b],
        "segment_s": float(ts[b - 1] - ts[a]),
        "timestamp_jitter_std_s": fit.residual_std,
        "timestamp_jitter_max_s": fit.residual_max,
    }


def ppm(measured: float | None, nominal: float) -> float | None:
    if measured is None or nominal <= 0:
        return None
    return (measured / nominal - 1.0) * 1e6


def clock_offsets(
    times: NDArray[np.float64], values: NDArray[np.float64], t_lo: float, t_hi: float
) -> dict[str, Any]:
    """LabRecorder ClockOffset measurements (recorder clock minus source clock).

    Measurements that cannot be real are discarded and counted: non-finite values, and
    measurement times outside the recording (e.g. the zero-filled entry LabRecorder writes
    when a time-correction query times out after the source has gone).
    """
    n = len(times)
    out: dict[str, Any] = {"measurements": n}
    if n == 0:
        out["usable"] = 0
        return out
    margin = max(60.0, 0.1 * (t_hi - t_lo))
    finite = np.isfinite(times) & np.isfinite(values)
    # times are on the recorder clock; with an offset of value, source time = time - value
    src_t = times - values
    in_range = finite & (src_t >= t_lo - margin) & (src_t <= t_hi + margin)
    discarded = [
        {"time": float(t), "value": float(v)}
        for t, v in zip(times[~in_range][:5], values[~in_range][:5], strict=True)
    ]
    t = times[in_range]
    v = values[in_range]
    out.update(usable=int(in_range.sum()), discarded=int(n - in_range.sum()))
    if discarded:
        out["discarded_examples"] = discarded
    if len(v):
        out.update(
            offset_median_s=float(np.median(v)),
            offset_min_s=float(np.min(v)),
            offset_max_s=float(np.max(v)),
        )
    fit = fit_line(t, v) if len(t) >= 3 else None
    if fit is not None:
        out.update(
            drift_ppm=fit.slope * 1e6,
            fit=fit.to_json(),
            span_s=float(t.max() - t.min()),
        )
    return out


def ingest_relation(
    frames: Sequence[Frame], device_s: Sequence[float | None], wall_to_source: float | None
) -> dict[str, Any]:
    """BrainOS ingest wall clock against the source clock of each frame's first sample.

    ``lag = wall - source`` contains an unknown constant unless ``wall_to_source`` (a measured
    offset that maps the BrainOS wall clock onto the source clock, in seconds) is given.
    The slope of ``lag`` over source time is the relative drift of the two clocks; the spread
    of ``lag`` above its minimum is the variable part of the delay (transport, buffering).
    """
    xs: list[float] = []
    ys: list[float] = []
    for f, d in zip(frames, device_s, strict=True):
        if d is None:
            continue
        # the frame is emitted once its LAST sample arrived: compare that sample's time
        last = d + (f.n - 1) / f.rate if f.rate > 0 else d
        xs.append(last)
        ys.append(f.t_wall_ns / 1e9 - last)
    if len(xs) < 3:
        return {"frames": len(xs)}
    x = np.asarray(xs)
    y = np.asarray(ys)
    fit = fit_line(x, y)
    excess = y - float(np.min(y))
    out: dict[str, Any] = {
        "frames": len(xs),
        "excess_delay_median_s": float(np.median(excess)),
        "excess_delay_p95_s": float(np.percentile(excess, 95)),
        "excess_delay_max_s": float(np.max(excess)),
    }
    if fit is not None:
        out["drift_ppm"] = fit.slope * 1e6
        out["fit"] = fit.to_json()
    if wall_to_source is not None:
        lat = y - wall_to_source
        out.update(
            latency_median_s=float(np.median(lat)),
            latency_p95_s=float(np.percentile(lat, 95)),
            latency_max_s=float(np.max(lat)),
            latency_min_s=float(np.min(lat)),
        )
    return out


def finite_or_none(x: float | None) -> float | None:
    return x if x is not None and math.isfinite(x) else None
