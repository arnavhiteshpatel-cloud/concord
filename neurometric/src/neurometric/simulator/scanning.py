"""Switch-scanning simulation (row-column and linear scanning).

A highlight advances every ``scan_ms``. The simulated user activates the switch a reaction time
after the desired item (or row) is highlighted. If the reaction is slower than the remaining
highlight time, the activation lands on the *next* item: the classic scanning timing error.
Switch degradations: added switch latency, missed activations, false activations.

Batched over B participants. Simulated only; parameters in docs/science/SIMULATOR_PARAMETERS.md.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class ScanConfig:
    scan_ms: float = 1000.0
    rt_ms: float = 450.0  # median reaction time to a highlight
    rt_sigma: float = 0.25  # lognormal sigma
    miss_prob: float = 0.03  # user fails to activate in time on this pass (cycle continues)
    switch_latency_ms: float = 0.0  # added by the switch/interface
    false_per_min: float = 0.0  # unintended activations per minute
    first_delay_ms: float = 0.0  # extra time before scanning starts (some systems delay item 1)
    max_cycles: int = 3
    mode: str = "row_column"  # or "linear"


def _activate(rng, B, target_pos, n_pos, cfg: ScanConfig, rt_scale):
    """Simulate selecting position ``target_pos`` (0-based) in a scan of ``n_pos`` positions.

    Returns (time_ms, selected_pos, n_false) arrays. Selected position -1 means nothing selected
    after max_cycles (abandon). A false activation selects whatever is highlighted at that moment.
    """
    t = np.full(B, cfg.first_delay_ms, float)
    sel = np.full(B, -1, np.int64)
    nfalse = np.zeros(B, np.int64)
    done = np.zeros(B, bool)
    lam = cfg.false_per_min / 60000.0
    for cycle in range(cfg.max_cycles):
        # false activation before reaching the target on this cycle?
        span = (target_pos + 1) * cfg.scan_ms
        if lam > 0:
            tf = rng.exponential(1 / lam, B)
            fa = (~done) & (tf < span)
            pos = np.minimum((tf // cfg.scan_ms).astype(np.int64), n_pos - 1)
            sel = np.where(fa, pos, sel)
            t = np.where(fa, t + tf, t)
            nfalse += fa
            done |= fa
        rt = np.exp(np.log(cfg.rt_ms * rt_scale) + cfg.rt_sigma * rng.standard_normal(B))
        rt = rt + cfg.switch_latency_ms
        miss = rng.random(B) < cfg.miss_prob
        landed = target_pos + np.floor(rt / cfg.scan_ms).astype(np.int64)
        act = (~done) & ~miss
        landed_ok = act & (landed < n_pos)
        sel = np.where(landed_ok, landed, sel)
        t = np.where(landed_ok, t + target_pos * cfg.scan_ms + rt, t)
        done |= landed_ok
        # missed or fell off the end: scanning wraps to a new cycle
        t = np.where(~done, t + n_pos * cfg.scan_ms, t)
        if done.all():
            break
    return t, sel, nfalse


def scan_select(rng: np.random.Generator, B: int, target_index: np.ndarray, rows: int, cols: int,
                cfg: ScanConfig, rt_scale: np.ndarray | float = 1.0):
    """Select item ``target_index`` (row-major) from a rows x cols layout.

    Returns dict with time_ms, selected index (-1 = abandoned), false activations.
    """
    target_index = np.asarray(target_index)
    rt_scale = np.broadcast_to(np.asarray(rt_scale, float), (B,))
    if cfg.mode == "linear":
        t, pos, nf = _activate(rng, B, target_index, rows * cols, cfg, rt_scale)
        return {"time_ms": t, "selected": pos, "false": nf}
    r = target_index // cols
    c = target_index % cols
    t1 = np.zeros(B)
    rsel = np.full(B, -1)
    nf = np.zeros(B, np.int64)
    # per-element row targets differ: run per unique row value
    for rv in np.unique(r):
        m = r == rv
        tt, pp, ff = _activate(rng, int(m.sum()), int(rv), rows, cfg, rt_scale[m])
        t1[m], rsel[m], nf[m] = tt, pp, ff
    t2 = np.zeros(B)
    csel = np.full(B, -1)
    for cv in np.unique(c):
        m = (c == cv) & (rsel >= 0)
        if m.any():
            tt, pp, ff = _activate(rng, int(m.sum()), int(cv), cols, cfg, rt_scale[m])
            t2[m], csel[m], nf[m] = tt, pp, nf[m] + ff
    selected = np.where((rsel >= 0) & (csel >= 0), rsel * cols + np.clip(csel, 0, cols - 1), -1)
    return {"time_ms": t1 + t2, "selected": selected, "false": nf}
