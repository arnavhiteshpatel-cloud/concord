"""Evaluation protocol for cursor + click decoding on the T15 dataset (offline, open loop).

Everything here is *offline analysis of recorded closed-loop sessions*. The participant was
controlling the ORIGINAL decoder's cursor; their neural activity reflects corrections to that
cursor, not to Concord's. Metrics below therefore measure how well Concord recovers the
recorded intention, never how well a person would control Concord in closed loop.

Definitions (all from the dataset README and the authors' scoring code):

* ``intention_labels``: ReFIT-style intended velocity -- the original decoder's speed, pointed
  from the cursor to the cued target; zero while the cursor touches the target.
* angle error: mean absolute angle between decoded velocity and the cursor->target direction,
  over bins where the cursor is not on the target (chance = 90 deg).
* trials: a grid trial runs from ``trial_start_bin[k]`` to the click that ends it, which is
  the bin before ``trial_start_bin[k+1]``.
* anchored open-loop endpoint: start at the recorded cursor position at the trial start (where
  the participant saw the cursor), integrate decoded velocity (10 ms bins), read the position
  at the trial's click. This is an analysis only; the command path never uses recorded positions.
* board accuracy (n x n board over the task grid): the endpoint's cell == the cued target's
  cell. The 14 x 14 board is the task's own grid; coarser boards group task cells.
* bitrate (authors' grid formula): (correct - wrong) * log2(N - 1) / seconds, floored at 0.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
from numpy.typing import NDArray

from concord.adapters.cursorclick.reader import BIN_S, T15Block
from concord.decoding.click import decision_events

FloatArray = NDArray[np.float64]
IntArray = NDArray[np.int64]


def intention_labels(b: T15Block) -> FloatArray:
    to = b.target - b.cursor
    n = np.linalg.norm(to, axis=1, keepdims=True)
    unit = np.divide(to, n, out=np.zeros_like(to), where=n > 0)
    speed = np.linalg.norm(b.cursor_decoder, axis=1, keepdims=True)
    y: FloatArray = unit * speed
    y[b.on_target()] = 0.0
    return y


def angle_error_deg(pred: FloatArray, b: T15Block) -> float:
    to = b.target - b.cursor
    m = (~b.on_target()) & (np.linalg.norm(pred, axis=1) > 1e-9)
    a = np.arctan2(pred[m, 1], pred[m, 0]) - np.arctan2(to[m, 1], to[m, 0])
    return float(np.degrees(np.abs((a + np.pi) % (2 * np.pi) - np.pi)).mean())


def r2(pred: FloatArray, y: FloatArray) -> float:
    sst = float(((y - y.mean(axis=0)) ** 2).sum())
    return 1.0 - float(((pred - y) ** 2).sum()) / sst if sst > 0 else float("nan")


def trials(b: T15Block) -> list[tuple[int, int]]:
    s = b.trial_start_bin
    return [(int(s[k]), int(s[k + 1] - 1)) for k in range(len(s) - 1)]


def _integral(vel: FloatArray) -> FloatArray:
    out: FloatArray = np.vstack([np.zeros((1, vel.shape[1])), np.cumsum(vel, axis=0) * BIN_S])
    return out


def anchored_endpoints(vel: FloatArray, b: T15Block) -> tuple[FloatArray, FloatArray, FloatArray]:
    """(endpoints, cued targets, start positions) per trial; endpoint at the trial's click."""
    integ = _integral(vel)
    ends, tgts, starts = [], [], []
    for s, e in trials(b):
        starts.append(b.cursor[s])
        ends.append(b.cursor[s] + integ[e + 1] - integ[s + 1])
        tgts.append(b.target[e])
    return np.array(ends), np.array(tgts), np.array(starts)


def whole_block_positions(vel: FloatArray, b: T15Block) -> FloatArray:
    """Integrated from the recorded start position only (what an app integrating the
    velocity stream would show over the whole block)."""
    integ = _integral(vel)
    out: FloatArray = b.cursor[0] + integ[1:] - integ[1]
    return out


def board_cells(pos: FloatArray, b: T15Block, n: int) -> IntArray:
    if b.grid_height is None:
        raise ValueError("board cells need the grid task's geometry")
    half = b.grid_height / 2
    eps = 1e-9
    out: IntArray = np.floor((np.clip(pos, -half + eps, half - eps) + half) / (b.grid_height / n))
    return out.astype(np.int64)


def board_accuracy(ends: FloatArray, tgts: FloatArray, b: T15Block, n: int) -> float:
    return float(np.mean(np.all(board_cells(ends, b, n) == board_cells(tgts, b, n), axis=1)))


def endpoint_summary(vel: FloatArray, b: T15Block, boards: tuple[int, ...]) -> dict[str, Any]:
    ends, tgts, starts = anchored_endpoints(vel, b)
    travel = np.linalg.norm(tgts - starts, axis=1)
    progress = np.sum((ends - starts) * (tgts - starts), axis=1) / np.maximum(travel**2, 1e-12)
    return {
        "trials": len(ends),
        "endpoint_error_median": float(np.median(np.linalg.norm(ends - tgts, axis=1))),
        "progress_median": float(np.median(progress)),
        "board_accuracy": {f"{n}x{n}": board_accuracy(ends, tgts, b, n) for n in boards},
    }


# ----------------------------------------------------------------------------- clicks
TOLERANCE_BINS = 25  # +-250 ms when matching clicks to the original decoder's clicks
REFRACTORY_BINS = 100  # 1 s: the original clicks are never closer than this


def match_events(ev: IntArray, ref: IntArray, tol: int = TOLERANCE_BINS) -> list[int]:
    """Greedy one-to-one matching within +-tol bins; returns the lags (ev - ref) of matches."""
    used: set[int] = set()
    lags: list[int] = []
    for e in ev.tolist():
        cands = [r for r in ref.tolist() if abs(r - e) <= tol and r not in used]
        if cands:
            r = min(cands, key=lambda r: abs(r - e))
            used.add(r)
            lags.append(e - r)
    return lags


def click_metrics(ev: IntArray, b: T15Block) -> dict[str, Any]:
    """Clicks vs the original decoder's clicks and vs the task (recorded cursor on target)."""
    ref = b.click_bins()
    lags = match_events(ev, ref)
    on = b.on_target()
    correct = int(on[ev].sum()) if len(ev) else 0
    minutes = b.duration_s / 60
    completed = 0
    for s, e in trials(b):
        completed += any(s <= t <= e + TOLERANCE_BINS and on[min(t, b.n_bins - 1)] for t in ev)
    return {
        "clicks": len(ev),
        "reference_clicks": len(ref),
        "matched": len(lags),
        "lags_bins": lags,
        "task_correct": correct,
        "minutes": minutes,
        "trials": len(trials(b)),
        "trials_completed": completed,
    }


def summarize_clicks(per_block: list[dict[str, Any]]) -> dict[str, Any]:
    n = sum(m["clicks"] for m in per_block)
    nr = sum(m["reference_clicks"] for m in per_block)
    tp = sum(m["matched"] for m in per_block)
    lags = [x for m in per_block for x in m["lags_bins"]]
    corr = sum(m["task_correct"] for m in per_block)
    mins = sum(m["minutes"] for m in per_block)
    tr = sum(m["trials"] for m in per_block)
    done = sum(m["trials_completed"] for m in per_block)
    prec = tp / n if n else float("nan")
    rec = tp / nr if nr else float("nan")
    return {
        "clicks": n,
        "clicks_per_min": n / mins,
        "precision_vs_original": prec,
        "recall_vs_original": rec,
        "lag_median_ms": float(np.median(lags)) * BIN_S * 1000 if lags else None,
        "lag_iqr_ms": [float(np.percentile(lags, q)) * BIN_S * 1000 for q in (25, 75)]
        if lags
        else None,
        "task_correct_fraction": corr / n if n else float("nan"),
        "false_activations_per_min": (n - corr) / mins,
        "trials_completed_fraction": done / tr if tr else float("nan"),
    }


def click_events(p: FloatArray, threshold: float, hold_bins: int) -> IntArray:
    return decision_events(p, threshold, hold_bins, REFRACTORY_BINS)


# ------------------------------------------------------------------ communication
@dataclass(frozen=True)
class Selection:
    trial: int
    click_bin: int | None
    selected: tuple[int, int] | None
    cued: tuple[int, int]

    @property
    def correct(self) -> bool:
        return self.selected is not None and self.selected == self.cued


def board_chain_positions(vel: FloatArray, b: T15Block) -> FloatArray:
    """Exactly what the communication board does with a velocity stream over the task grid:
    the cursor starts at the centre, the first event only starts the clock, then
    ``pos += v * dt`` per 10 ms event, clamped to the grid square (the board's workspace)."""
    if b.grid_height is None:
        raise ValueError("needs the grid task's geometry")
    half = b.grid_height / 2
    out = np.empty_like(vel)
    pos = np.zeros(2)
    for t in range(len(vel)):
        if t > 0:
            pos = np.clip(pos + vel[t] * BIN_S, -half, half)
        out[t] = pos
    return out


def board_tile(pos: FloatArray, b: T15Block, n: int) -> int:
    """Board tile index (row-major, row 0 at the TOP, as the board numbers tiles)."""
    col, row_up = board_cells(np.asarray(pos)[None, :], b, n)[0]
    return int((n - 1 - row_up) * n + col)


MODES = ("anchored", "whole_block", "board")


def select_words(
    vel: FloatArray, clicks: IntArray, b: T15Block, n: int, *, mode: str
) -> list[Selection]:
    """Per trial: the first click inside the trial window (start .. original click + 250 ms)
    selects the board cell under the integrated cursor.

    ``mode``: ``anchored`` -- the cursor restarts each trial at the recorded position
    (analysis only); ``whole_block`` -- integrated from the block's first recorded position;
    ``board`` -- exactly the communication board's integration (centre start, clamped)."""
    if mode not in MODES:
        raise ValueError(f"mode must be one of {MODES}")
    integ = _integral(vel)
    chain = board_chain_positions(vel, b) if mode == "board" else None
    out: list[Selection] = []
    for k, (s, e) in enumerate(trials(b)):
        cued = board_cells(b.target[e][None, :], b, n)[0]
        hit = [int(t) for t in clicks.tolist() if s <= t <= e + TOLERANCE_BINS]
        if not hit:
            out.append(Selection(k, None, None, (int(cued[0]), int(cued[1]))))
            continue
        t = hit[0]
        if chain is not None:
            pos = chain[t]
        elif mode == "anchored":
            pos = b.cursor[s] + integ[t + 1] - integ[s + 1]
        else:
            pos = b.cursor[0] + integ[t + 1] - integ[1]
        cell = board_cells(pos[None, :], b, n)[0]
        out.append(Selection(k, t, (int(cell[0]), int(cell[1])), (int(cued[0]), int(cued[1]))))
    return out


def bitrate(correct: int, wrong: int, n_cells: int, seconds: float) -> float:
    """Authors' grid-task formula (Singer-Clark et al.), bits/s, floored at zero."""
    if seconds <= 0 or n_cells < 3:
        return 0.0
    return max(0.0, (correct - wrong) * float(np.log2(n_cells - 1)) / seconds)


def selection_summary(sel: list[Selection], n: int, seconds: float) -> dict[str, Any]:
    made = [x for x in sel if x.selected is not None]
    correct = sum(x.correct for x in sel)
    wrong = len(made) - correct
    return {
        "board": f"{n}x{n}",
        "trials": len(sel),
        "selections": len(made),
        "correct": correct,
        "accuracy_per_trial": correct / len(sel) if sel else float("nan"),
        "accuracy_per_selection": correct / len(made) if made else float("nan"),
        "chance": 1.0 / (n * n),
        "bitrate_bps": bitrate(correct, wrong, n * n, seconds),
    }
