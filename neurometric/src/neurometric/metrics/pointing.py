"""Pointing / target-acquisition metrics.

All functions are vectorised over trials: trajectories are (N, T, 2) arrays padded with NaN.
Every metric is defined in docs/science/METRICS.md, with its formula, units, assumptions and the
raw fields it needs. Raw measurements (times, positions, counts) are kept separate from derived
metrics (throughput, efficiency, bitrates).

Observable-only rule: these functions use only data a real measurement system can record (cursor
samples, selection events, stimulus geometry). Simulation ground truth is never an input here.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np

# ISO 9241-411 / Soukoreff & MacKenzie (2004): We = sqrt(2*pi*e) * SD = 4.133 * SD
WE_FACTOR = float(np.sqrt(2 * np.pi * np.e))


@dataclass
class PointingTrials:
    """Observable record of N acquisition trials (the canonical scoring input)."""

    traj: np.ndarray  # (N, T, 2) cursor samples, NaN padded
    t_ms: np.ndarray  # (N, T) sample times relative to stimulus onset, NaN padded
    start: np.ndarray  # (N, 2) cursor position at stimulus onset
    target_c: np.ndarray  # (N, 2)
    target_h: np.ndarray  # (N, 2) half sizes (radius for circular targets in both)
    sel_t: np.ndarray  # (N,) time of terminating selection (NaN if none)
    sel_pos: np.ndarray  # (N, 2)
    sel_item: np.ndarray  # (N,) 0 target, >0 other item, -1 empty space, -2 none (timeout)
    n_empty_selects: np.ndarray  # (N,) non-terminating selections on empty space
    n_items: Optional[np.ndarray] = None  # (N,) number of selectable items on screen

    @staticmethod
    def from_step(step, dt_ms: float = 10.0) -> "PointingTrials":
        N, T, _ = step.traj.shape
        t = np.tile(np.arange(T) * dt_ms, (N, 1)).astype(float)
        t[np.isnan(step.traj[:, :, 0])] = np.nan
        return PointingTrials(step.traj, t, step.start, step.target_c, step.target_h,
                              step.sel_t, step.sel_pos, step.sel_item, step.n_empty_selects)

    def __len__(self):
        return self.traj.shape[0]

    def subset(self, idx) -> "PointingTrials":
        return PointingTrials(self.traj[idx], self.t_ms[idx], self.start[idx], self.target_c[idx],
                              self.target_h[idx], self.sel_t[idx], self.sel_pos[idx],
                              self.sel_item[idx], self.n_empty_selects[idx],
                              None if self.n_items is None else self.n_items[idx])


def _axis(tr: PointingTrials):
    d = tr.target_c - tr.start
    D = np.hypot(d[:, 0], d[:, 1])
    u = d / np.maximum(D, 1e-9)[:, None]
    return u, D


def _valid_until_selection(tr: PointingTrials) -> np.ndarray:
    """Mask (N,T) of samples at or before the selection (or end of record)."""
    m = ~np.isnan(tr.traj[:, :, 0])
    sel = np.where(np.isnan(tr.sel_t), np.inf, tr.sel_t)
    return m & (np.nan_to_num(tr.t_ms, nan=np.inf) <= sel[:, None] + 1e-9)


def trial_metrics(tr: PointingTrials, onset_frac: float = 0.1) -> dict[str, np.ndarray]:
    """Per-trial raw and derived metrics. Returns dict of (N,) arrays."""
    N = len(tr)
    u, D = _axis(tr)
    perp = np.stack([-u[:, 1], u[:, 0]], 1)
    m = _valid_until_selection(tr)
    rel = tr.traj - tr.start[:, None, :]
    proj = np.einsum("ntk,nk->nt", rel, u)  # along task axis
    off = np.einsum("ntk,nk->nt", rel, perp)  # perpendicular
    proj_m = np.where(m, proj, np.nan)
    off_m = np.where(m, off, np.nan)
    steps = np.diff(tr.traj, axis=1)
    seg = np.hypot(steps[:, :, 0], steps[:, :, 1])
    seg = np.where(m[:, 1:] & m[:, :-1], seg, 0.0)
    path = seg.sum(1)
    end = tr.sel_pos
    disp = np.hypot(*(end - tr.start).T)
    success = tr.sel_item == 0
    timeout = tr.sel_item == -2
    error = ~success & ~timeout
    mt = tr.sel_t.copy()
    # movement onset: first sample whose projection exceeds onset_frac * D
    crossed = np.nan_to_num(proj_m, nan=-np.inf) >= onset_frac * D[:, None]
    has = crossed.any(1)
    first = np.argmax(crossed, 1)
    onset = np.where(has, tr.t_ms[np.arange(N), first], np.nan)
    eff = np.where(path > 0, disp / np.maximum(path, 1e-9), np.nan)
    eff = np.where(timeout, np.nan, eff)
    endpoint_err = np.hypot(*(end - tr.target_c).T)
    dx = np.einsum("nk,nk->n", end - tr.target_c, u)  # signed endpoint error on task axis
    h_along = np.abs(u[:, 0]) * tr.target_h[:, 0] + np.abs(u[:, 1]) * tr.target_h[:, 1]
    overshoot = np.maximum(0.0, np.nanmax(np.where(m, proj, -np.inf), 1) - (D + h_along))
    # MacKenzie, Kauppinen & Silfverberg (2001) path accuracy measures
    mo = np.nanmean(off_m, 1)
    me = np.nanmean(np.abs(off_m), 1)
    mv = np.nanstd(off_m, 1, ddof=1)
    sgn = np.sign(np.where(np.isnan(off_m), 0, off_m))
    tac = _count_sign_changes(sgn, m)
    tre = _target_reentries(tr, m)
    mdc, odc = _direction_changes(proj_m, off_m, m)
    entry_t = _first_entry_time(tr, m)
    dial_in = np.where(success, tr.sel_t - entry_t, np.nan)
    speed = np.where(m[:, 1:], seg, np.nan) / np.maximum(np.diff(np.nan_to_num(tr.t_ms), axis=1), 1e-9) * 1000
    peak_speed = np.nanmax(np.where(np.isnan(speed), -np.inf, speed), 1)
    nsub = _submovements(speed)
    return {
        "success": success, "error": error, "timeout": timeout,
        "movement_time_ms": mt, "onset_ms": onset,
        "distance_px": D, "path_length_px": path, "path_efficiency": eff,
        "endpoint_error_px": endpoint_err, "endpoint_dx_px": dx,
        "amplitude_px": np.einsum("nk,nk->n", end - tr.start, u),
        "overshoot_px": overshoot, "target_reentries": tre,
        "task_axis_crossings": tac, "movement_direction_changes": mdc,
        "orthogonal_direction_changes": odc, "movement_variability_px": mv,
        "movement_error_px": me, "movement_offset_px": mo,
        "first_entry_ms": entry_t, "dial_in_ms": dial_in, "peak_speed_pxps": peak_speed,
        "submovements": nsub, "empty_selections": tr.n_empty_selects.astype(float),
    }


def _count_sign_changes(sgn, m):
    out = np.zeros(sgn.shape[0])
    for i in range(sgn.shape[0]):
        s = sgn[i][m[i]]
        s = s[s != 0]
        out[i] = np.count_nonzero(np.diff(s)) if s.size > 1 else 0
    return out


def _direction_changes(proj, off, m):
    """MacKenzie et al. (2001): MDC = sign changes of the path's motion perpendicular to the task
    axis; ODC = sign changes of the motion along the task axis."""
    N = proj.shape[0]
    mdc = np.zeros(N)
    odc = np.zeros(N)
    for i in range(N):
        mi = m[i]
        p = proj[i][mi]
        o = off[i][mi]
        if p.size < 3:
            continue
        # MDC: changes of direction of the path relative to the axis (sign of d(off))
        do = np.sign(np.diff(o))
        do = do[do != 0]
        mdc[i] = np.count_nonzero(np.diff(do)) if do.size > 1 else 0
        dp = np.sign(np.diff(p))
        dp = dp[dp != 0]
        odc[i] = np.count_nonzero(np.diff(dp)) if dp.size > 1 else 0
    return mdc, odc


def _inside(tr, m):
    dx = np.abs(tr.traj[:, :, 0] - tr.target_c[:, None, 0]) <= tr.target_h[:, None, 0]
    dy = np.abs(tr.traj[:, :, 1] - tr.target_c[:, None, 1]) <= tr.target_h[:, None, 1]
    return dx & dy & m


def _target_reentries(tr, m):
    ins = _inside(tr, m).astype(np.int8)
    entries = (np.diff(ins, axis=1) == 1).sum(1) + ins[:, 0]
    return np.maximum(entries - 1, 0).astype(float)


def _first_entry_time(tr, m):
    ins = _inside(tr, m)
    has = ins.any(1)
    first = np.argmax(ins, 1)
    return np.where(has, tr.t_ms[np.arange(len(tr)), first], np.nan)


def _submovements(speed, min_peak=50.0):
    """Count speed peaks above min_peak px/s after light smoothing (5-sample moving average)."""
    N = speed.shape[0]
    out = np.zeros(N)
    k = np.ones(5) / 5
    for i in range(N):
        s = speed[i]
        s = s[~np.isnan(s)]
        if s.size < 7:
            continue
        s = np.convolve(s, k, mode="same")
        pk = (s[1:-1] > s[:-2]) & (s[1:-1] >= s[2:]) & (s[1:-1] > min_peak)
        out[i] = pk.sum()
    return out


# --------------------------------------------------------------------------- block level
@dataclass
class ThroughputResult:
    tp_effective_bps: float
    tp_nominal_bps: float
    we_px: float
    de_px: float
    ide_bits: float
    id_bits: float
    mt_ms: float
    error_rate: float
    n: int
    valid: bool
    flags: list


def fitts_throughput(tr: PointingTrials, D: float, W: float, *, dwell: bool = False,
                     min_n: int = 10, max_error_rate: float = 0.5) -> ThroughputResult:
    """ISO 9241-411 effective throughput for ONE condition (fixed nominal D, W).

    Uses all trials that ended with a selection (hits and misses); timeouts are excluded and
    reported. Effective width We = 4.133 * SD of the selection endpoint projected on the task
    axis; effective distance De = mean projected movement amplitude; IDe = log2(De/We + 1);
    TP = IDe / mean MT (s). Validity flags are raised when assumptions are not met.
    """
    flags = []
    sel = tr.sel_item != -2
    n = int(sel.sum())
    tm = trial_metrics(tr.subset(np.nonzero(sel)[0])) if n else None
    ID = float(np.log2(D / W + 1))
    if n < 2:
        return ThroughputResult(np.nan, np.nan, np.nan, np.nan, np.nan, ID, np.nan,
                                np.nan, n, False, ["fewer than 2 selections"])
    dx = tm["endpoint_dx_px"]
    sd = float(np.std(dx, ddof=1))
    We = WE_FACTOR * sd
    De = float(np.mean(tm["amplitude_px"]))
    IDe = float(np.log2(De / We + 1)) if We > 0 else np.nan
    mt = float(np.mean(tm["movement_time_ms"])) / 1000.0
    err = float(np.mean(~tm["success"]))
    timeouts = int((~sel).sum())
    if n < min_n:
        flags.append(f"n={n} < {min_n} selections")
    if err > max_error_rate:
        flags.append(f"error rate {err:.2f} > {max_error_rate}: speed-accuracy assumption violated")
    if timeouts:
        flags.append(f"{timeouts} timeouts excluded (throughput is conditional on selection)")
    if dwell:
        flags.append("dwell selection: MT includes a fixed dwell time; compare TP only within the same dwell setting")
    # spatial outliers (MacKenzie & Isokoski 2008 style criterion [PK]): movement shorter than half
    # the nominal distance, or endpoint more than twice the nominal width from the target centre.
    # Flagged (not excluded) because they inflate We.
    n_out = int(np.sum((tm["amplitude_px"] < D / 2) | (np.abs(dx) > 2 * W)))
    if n_out:
        flags.append(f"{n_out} spatial outlier selection(s) included (inflate We)")
    if We <= 0 or not np.isfinite(IDe):
        flags.append("degenerate endpoint spread")
    valid = n >= min_n and err <= max_error_rate and We > 0 and bool(np.isfinite(IDe))
    return ThroughputResult(IDe / mt if mt > 0 else np.nan, ID / mt if mt > 0 else np.nan, We,
                            De, IDe, ID, mt * 1000, err, n, valid, flags)


def achieved_bitrate(n_correct: int, n_incorrect: int, n_targets: int, seconds: float) -> float:
    """Achieved bitrate for grid selection tasks (Nuyujukian et al. 2015 style) [PK]:
    B = log2(N - 1) * max(Sc - Si, 0) / t. Penalises errors by requiring a correction."""
    if n_targets < 2 or seconds <= 0:
        return float("nan")
    return float(np.log2(n_targets - 1) * max(n_correct - n_incorrect, 0) / seconds)


def wolpaw_itr_bits(p: float, n: int) -> float:
    """Wolpaw bits per selection. Assumes equiprobable targets, errors uniformly distributed
    across the N-1 wrong targets, and a fixed selection time. Use with stated caution."""
    if n < 2:
        return float("nan")
    p = float(np.clip(p, 0.0, 1.0))
    if p <= 1.0 / n:
        return 0.0
    b = np.log2(n) + p * np.log2(p)
    if p < 1:
        b += (1 - p) * np.log2((1 - p) / (n - 1))
    return float(b)


def wolpaw_itr_bpm(p: float, n: int, selections_per_min: float) -> float:
    return wolpaw_itr_bits(p, n) * selections_per_min
