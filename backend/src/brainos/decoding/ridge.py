"""Baseline linear decoder for binned spike counts -> continuous kinematics.

Follows the FALCON H1 reference baseline (snel-repo/falcon-challenge, decoder_demos):
  1. causal exponential filter on counts (tau = 240 ms, kernel length = tau / bin),
  2. z-score with *training* statistics only,
  3. ridge regression (closed form, unpenalized intercept),
and the FALCON metric: variance-weighted R^2 over evaluation-mask samples.

Differences from the reference, made to avoid leakage: alpha is chosen by *blocked*
(contiguous, unshuffled) cross-validation inside the training data only, and the
held-out data is never used for any fitting or selection.

numpy only; models are stored as JSON (no pickle).
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
from numpy.typing import NDArray

TAU_MS = 240.0
STILL_THRESHOLD = 0.001  # reference: |v| < 0.001 in all dims = "nothing happening"
ALPHAS: tuple[float, ...] = tuple(float(a) for a in np.logspace(-3, 5, 17))
CV_FOLDS = 5
SHIFTS = 20  # circular-shift null distribution size (beats all 20 => p < 1/21)

FloatArray = NDArray[np.float64]


def exponential_kernel(bin_ms: float, tau_ms: float = TAU_MS) -> FloatArray:
    t = np.arange(0.0, tau_ms, bin_ms)
    k: FloatArray = np.exp(-t / tau_ms)
    return k / float(k.sum())


def causal_filter(x: FloatArray, kernel: FloatArray) -> FloatArray:
    """y[t] = sum_k kernel[k] * x[t-k]; zeros before the first sample (causal)."""
    out = np.zeros_like(x, dtype=np.float64)
    for k, w in enumerate(kernel):
        if k == 0:
            out += w * x
        else:
            out[k:] += w * x[:-k]
    return out


def r2_variance_weighted(y: FloatArray, pred: FloatArray) -> float:
    """sklearn r2_score(multioutput='variance_weighted') == 1 - sum SSE / sum SST."""
    sse = float(np.sum((y - pred) ** 2))
    sst = float(np.sum((y - y.mean(axis=0)) ** 2))
    return 1.0 - sse / sst if sst > 0 else float("nan")


def r2_per_dim(y: FloatArray, pred: FloatArray) -> list[float]:
    sse = np.sum((y - pred) ** 2, axis=0)
    sst = np.sum((y - y.mean(axis=0)) ** 2, axis=0)
    return [float(1 - a / b) if b > 0 else float("nan") for a, b in zip(sse, sst, strict=True)]


def _ridge(x: FloatArray, y: FloatArray, alpha: float) -> tuple[FloatArray, FloatArray]:
    xm, ym = x.mean(axis=0), y.mean(axis=0)
    xc, yc = x - xm, y - ym
    a = xc.T @ xc + alpha * np.eye(x.shape[1])
    w = np.linalg.solve(a, xc.T @ yc)
    return w, ym - xm @ w


def select_alpha(
    x: FloatArray, y: FloatArray, alphas: tuple[float, ...] = ALPHAS
) -> tuple[float, dict[str, float]]:
    """Blocked K-fold CV: contiguous folds in time order, no shuffling."""
    n = x.shape[0]
    bounds = np.linspace(0, n, CV_FOLDS + 1).astype(int)
    scores: dict[str, float] = {}
    for alpha in alphas:
        fold_scores = []
        for i in range(CV_FOLDS):
            test = np.zeros(n, dtype=bool)
            test[bounds[i] : bounds[i + 1]] = True
            if test.sum() < 10 or (~test).sum() < 10:
                continue
            w, b = _ridge(x[~test], y[~test], alpha)
            fold_scores.append(r2_variance_weighted(y[test], x[test] @ w + b))
        scores[f"{alpha:g}"] = float(np.mean(fold_scores))
    best = max(alphas, key=lambda a: scores[f"{a:g}"])
    return best, scores


@dataclass
class RidgeDecoder:
    model_id: str
    space: str
    quantity: str
    dims: list[str]
    unit: str
    bin_ms: float
    tau_ms: float
    kernel: list[float]
    x_mean: list[float]
    x_std: list[float]
    weights: list[list[float]]  # channels x dims
    intercept: list[float]
    alpha: float
    training: dict[str, Any]
    evaluations: list[dict[str, Any]] = field(default_factory=list)
    created_at: str = ""
    method: str = (
        "FALCON H1 baseline: causal exponential filter (tau 240 ms), z-score (train stats), "
        "ridge regression; alpha by blocked 5-fold CV within training data"
    )

    @property
    def channel_count(self) -> int:
        return len(self.x_mean)

    def _arrays(self) -> tuple[FloatArray, FloatArray, FloatArray, FloatArray]:
        return (
            np.asarray(self.x_mean),
            np.asarray(self.x_std),
            np.asarray(self.weights),
            np.asarray(self.intercept),
        )

    def predict_counts(self, counts: FloatArray) -> FloatArray:
        """Offline prediction for a whole sequence of counts (filter starts at zero)."""
        mean, std, w, b = self._arrays()
        filtered = causal_filter(np.asarray(counts, dtype=np.float64), np.asarray(self.kernel))
        return ((filtered - mean) / std) @ w + b

    def streaming(self) -> StreamingDecoder:
        return StreamingDecoder(self)

    def save(self, path: Path) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(asdict(self), indent=1))
        return path

    @classmethod
    def load(cls, path: Path) -> RidgeDecoder:
        data = json.loads(path.read_text())
        model = cls(**data)
        if len(model.weights) != model.channel_count or any(
            len(r) != len(model.dims) for r in model.weights
        ):
            raise ValueError(f"{path.name}: weight matrix shape does not match channels/dims")
        return model


class StreamingDecoder:
    """Causal, bin-by-bin decoding: identical maths to ``predict_counts``."""

    def __init__(self, model: RidgeDecoder) -> None:
        self.model = model
        self._mean, self._std, self._w, self._b = model._arrays()
        self._kernel = np.asarray(model.kernel)
        self._history = np.zeros((len(self._kernel), model.channel_count))
        self._n = 0

    def reset(self) -> None:
        self._history[:] = 0.0
        self._n = 0

    def step(self, counts: FloatArray | list[int]) -> FloatArray:
        self._history = np.roll(self._history, 1, axis=0)
        self._history[0] = np.asarray(counts, dtype=np.float64)
        self._n += 1
        filtered = self._kernel @ self._history
        return ((filtered - self._mean) / self._std) @ self._w + self._b


def fit(
    counts: FloatArray,
    behavior: FloatArray,
    valid: NDArray[np.bool_],
    *,
    dims: list[str],
    unit: str,
    bin_ms: float,
    space: str,
    training: dict[str, Any],
) -> RidgeDecoder:
    """Fit on one training sequence. Caller guarantees it contains no evaluation data."""
    kernel = exponential_kernel(bin_ms)
    filtered = causal_filter(np.asarray(counts, dtype=np.float64), kernel)
    mean = filtered.mean(axis=0)
    std = filtered.std(axis=0)
    std[std == 0] = 1.0
    z = (filtered - mean) / std
    still = np.all(np.abs(behavior) < STILL_THRESHOLD, axis=1)
    rows = valid & ~still
    if rows.sum() < 50:
        raise ValueError(f"too few usable training samples ({int(rows.sum())})")
    alpha, cv = select_alpha(z[rows], behavior[rows])
    w, b = _ridge(z[rows], behavior[rows], alpha)
    digest = hashlib.sha256(w.tobytes() + b.tobytes()).hexdigest()[:10]
    training = {
        **training,
        "samples_used": int(rows.sum()),
        "behavior_mean": behavior[rows].mean(axis=0).tolist(),
        "cv_r2_by_alpha": cv,
    }
    return RidgeDecoder(
        model_id=f"falcon-h1-ridge-{digest}",
        space=space,
        quantity="velocity",
        dims=dims,
        unit=unit,
        bin_ms=bin_ms,
        tau_ms=TAU_MS,
        kernel=kernel.tolist(),
        x_mean=mean.tolist(),
        x_std=std.tolist(),
        weights=w.tolist(),
        intercept=b.tolist(),
        alpha=alpha,
        training=training,
        created_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    )


def evaluate(
    model: RidgeDecoder,
    counts: FloatArray,
    behavior: FloatArray,
    valid: NDArray[np.bool_],
    *,
    skip_first: int = 0,
    shift_control: bool = True,
) -> dict[str, Any]:
    """Score on held-out data with controls. ``skip_first`` bins are excluded from scoring."""
    pred = model.predict_counts(counts)
    rows = valid.copy()
    rows[:skip_first] = False
    y, p = behavior[rows], pred[rows]
    train_mean = np.asarray(model.training.get("behavior_mean", np.zeros(len(model.dims))))
    out: dict[str, Any] = {
        "samples": int(rows.sum()),
        "r2": r2_variance_weighted(y, p),
        "r2_per_dim": dict(zip(model.dims, r2_per_dim(y, p), strict=True)),
        "control_mean_predictor_r2": r2_variance_weighted(y, np.broadcast_to(train_mean, y.shape)),
    }
    if shift_control:
        # Null distribution: the same model on neural data circularly shifted against behavior
        # by SHIFTS evenly spaced offsets (keeps firing statistics, destroys alignment).
        n = counts.shape[0]
        null = []
        for k in range(1, SHIFTS + 1):
            shifted = model.predict_counts(np.roll(counts, (k * n) // (SHIFTS + 1), axis=0))
            null.append(r2_variance_weighted(y, shifted[rows]))
        out["control_time_shift_r2"] = float(np.mean(null))
        out["control_time_shift_max_r2"] = float(np.max(null))
        out["control_time_shift_n"] = SHIFTS
        out["beats_all_shifts"] = bool(out["r2"] > max(null))
    return out
