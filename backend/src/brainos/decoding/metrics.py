"""Held-out metrics for the calibration workflow, chosen by output capability.

* continuous movement: variance-weighted R² (ridge.py), per-dimension R², and velocity
  error — RMSE and MAE per dimension, mean error-vector length in the label unit, and that
  length relative to the mean target speed;
* discrete classes: balanced accuracy, per-class recall, confusion (lda.py);
* click (binary events): per-bin balanced accuracy / precision / recall / ROC AUC, and
  event-level precision / recall / F1 / false positives per minute, where an event is a
  label onset (0 -> 1) and a detection is a crossing of the probability threshold; a
  detection within ``tolerance_ms`` of an unmatched true onset is a hit.

Nothing here is a closed-loop measure: these score how well a model reproduces recorded
labels offline.
"""

from __future__ import annotations

from typing import Any

import numpy as np
from numpy.typing import NDArray

FloatArray = NDArray[np.float64]


def velocity_error(y: FloatArray, p: FloatArray, dims: list[str]) -> dict[str, Any]:
    err = p - y
    rmse = np.sqrt(np.mean(err**2, axis=0))
    mae = np.mean(np.abs(err), axis=0)
    vec = np.linalg.norm(err, axis=1)
    speed = np.linalg.norm(y, axis=1)
    mean_speed = float(np.mean(speed)) if len(speed) else float("nan")
    return {
        "rmse_per_dim": dict(zip(dims, (float(v) for v in rmse), strict=True)),
        "mae_per_dim": dict(zip(dims, (float(v) for v in mae), strict=True)),
        "mean_vector_error": float(np.mean(vec)) if len(vec) else float("nan"),
        "mean_target_speed": mean_speed,
        "relative_vector_error": float(np.mean(vec)) / mean_speed if mean_speed > 0 else None,
    }


def roc_auc(scores: FloatArray, labels: NDArray[np.int64]) -> float | None:
    """Area under the ROC curve (Mann-Whitney U with average ranks for ties)."""
    pos = labels == 1
    n_pos, n_neg = int(pos.sum()), int((~pos).sum())
    if n_pos == 0 or n_neg == 0:
        return None
    order = np.argsort(scores, kind="mergesort")
    ranks = np.empty(len(scores), dtype=np.float64)
    sorted_scores = scores[order]
    i = 0
    while i < len(scores):
        j = i
        while j + 1 < len(scores) and sorted_scores[j + 1] == sorted_scores[i]:
            j += 1
        ranks[order[i : j + 1]] = (i + j) / 2.0 + 1.0
        i = j + 1
    u = float(ranks[pos].sum()) - n_pos * (n_pos + 1) / 2.0
    return u / (n_pos * n_neg)


def _onsets(x: NDArray[np.bool_]) -> NDArray[np.int64]:
    prev = np.concatenate([[False], x[:-1]])
    out: NDArray[np.int64] = np.flatnonzero(x & ~prev)
    return out


def event_metrics(
    prob: FloatArray,
    label: FloatArray,
    valid: NDArray[np.bool_],
    *,
    bin_ms: float,
    tolerance_ms: float = 300.0,
    threshold: float = 0.5,
) -> dict[str, Any]:
    """Per-bin and event-level detection metrics for one binary event (e.g. click)."""
    true = (label > 0.5) & valid
    pred = (prob >= threshold) & valid
    yt = true[valid].astype(np.int64)
    yp = pred[valid].astype(np.int64)
    tp_b = int(np.sum((yt == 1) & (yp == 1)))
    fp_b = int(np.sum((yt == 0) & (yp == 1)))
    fn_b = int(np.sum((yt == 1) & (yp == 0)))
    tn_b = int(np.sum((yt == 0) & (yp == 0)))
    rec1 = tp_b / (tp_b + fn_b) if tp_b + fn_b else float("nan")
    rec0 = tn_b / (tn_b + fp_b) if tn_b + fp_b else float("nan")
    true_on, pred_on = _onsets(true), _onsets(pred)
    tol = max(1, round(tolerance_ms / bin_ms))
    matched: set[int] = set()
    hits = 0
    for po in pred_on:
        cands = [int(t) for t in true_on if abs(int(t) - int(po)) <= tol and int(t) not in matched]
        if cands:
            matched.add(min(cands, key=lambda t: abs(t - int(po))))
            hits += 1
    fp = len(pred_on) - hits
    fn = len(true_on) - len(matched)
    precision = hits / len(pred_on) if len(pred_on) else float("nan")
    recall = len(matched) / len(true_on) if len(true_on) else float("nan")
    f1 = (
        2 * precision * recall / (precision + recall)
        if len(pred_on) and len(true_on) and precision + recall > 0
        else float("nan")
    )
    minutes = valid.sum() * bin_ms / 60_000.0
    return {
        "threshold": threshold,
        "tolerance_ms": tolerance_ms,
        "bin_balanced_accuracy": float(np.nanmean([rec0, rec1])),
        "bin_precision": tp_b / (tp_b + fp_b) if tp_b + fp_b else float("nan"),
        "bin_recall": rec1,
        "roc_auc": roc_auc(prob[valid], yt),
        "true_events": len(true_on),
        "detected_events": len(pred_on),
        "event_hits": hits,
        "event_false_positives": fp,
        "event_misses": fn,
        "event_precision": precision,
        "event_recall": recall,
        "event_f1": f1,
        "false_positives_per_min": fp / minutes if minutes > 0 else float("nan"),
        "positive_bin_rate": float(np.mean(yt)) if len(yt) else float("nan"),
    }
