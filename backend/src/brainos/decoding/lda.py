"""Streaming linear discriminant analysis (LDA) classifier for discrete decoding.

Features (e.g. log band power per channel per bin) -> class posteriors per bin:

  1. optional causal exponential smoothing of the features (``tau_ms``; 0 = off),
  2. z-score with *training* statistics only,
  3. LDA with a shared, shrinkage-regularized covariance (Ledoit-Wolf shrinkage towards a
     scaled identity, computed in closed form from the training data only),
  4. posteriors = softmax of the linear discriminants (class priors from training).

numpy only; models are JSON (``brainos.model/1``) with ``outputs: {"type": "classes"}``.
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

from brainos.decoding.ridge import causal_filter, exponential_kernel, filter_step

FloatArray = NDArray[np.float64]
DEFAULT_TAU_MS = 500.0
MIN_PER_CLASS = 10


def ledoit_wolf_shrinkage(x: FloatArray) -> float:
    """Ledoit-Wolf (2004) shrinkage intensity for the covariance of centered data ``x``.

    Target: ``mu * I`` with ``mu = trace(S) / p``. Same estimator as scikit-learn's
    ``ledoit_wolf_shrinkage`` (no block splitting needed at these sizes).
    """
    n, p = x.shape
    if n < 2 or p < 1:
        return 1.0
    x2 = x**2
    emp_cov_trace = x2.sum(axis=0) / n
    mu = float(emp_cov_trace.sum()) / p
    beta_ = float(np.sum(x2.T @ x2))
    delta_ = float(np.sum((x.T @ x) ** 2)) / n**2
    beta = (beta_ / n - delta_) / (p * n)
    delta = (delta_ - 2.0 * mu * float(emp_cov_trace.sum()) + p * mu**2) / p
    beta = min(beta, delta)
    return 0.0 if beta <= 0 or delta <= 0 else float(beta / delta)


def _softmax(z: FloatArray) -> FloatArray:
    z = z - z.max(axis=-1, keepdims=True)
    e = np.exp(z)
    out: FloatArray = e / e.sum(axis=-1, keepdims=True)
    return out


@dataclass
class LDAClassifier:
    model_id: str
    space: str
    classes: list[str]  # class names, in output order
    class_values: list[float]  # label value in the behavior stream for each class
    bin_ms: float
    tau_ms: float
    kernel: list[float]
    x_mean: list[float]
    x_std: list[float]
    coef: list[list[float]]  # classes x channels (on z-scored features)
    intercept: list[float]
    priors: list[float]
    shrinkage: float
    training: dict[str, Any]
    evaluations: list[dict[str, Any]] = field(default_factory=list)
    created_at: str = ""
    method: str = (
        "LDA classifier: causal exponential smoothing, z-score (train stats), shared covariance "
        "with Ledoit-Wolf shrinkage, softmax posteriors"
    )
    schema: str = "brainos.model/1"
    version: int = 1
    kind: str = "lda"
    input: dict[str, Any] = field(default_factory=dict)
    source: dict[str, Any] = field(default_factory=dict)
    outputs: dict[str, Any] = field(default_factory=dict)
    # ---- Milestone 5 (optional; older files lack them)
    inputs: list[dict[str, Any]] = field(default_factory=list)
    manifest: dict[str, Any] = field(default_factory=dict)

    # ---- the decoder interface shared with RidgeDecoder (pipeline, model registry)
    @property
    def quantity(self) -> str:
        return "class_posterior"

    @property
    def dims(self) -> list[str]:
        return list(self.classes)

    @property
    def unit(self) -> str:
        return "probability"

    @property
    def channel_count(self) -> int:
        return len(self.x_mean)

    def _arrays(self) -> tuple[FloatArray, FloatArray, FloatArray, FloatArray]:
        return (
            np.asarray(self.x_mean),
            np.asarray(self.x_std),
            np.asarray(self.coef),
            np.asarray(self.intercept),
        )

    def predict_proba(self, features: FloatArray) -> FloatArray:
        """Offline posteriors for a whole sequence (the smoothing filter starts at zero).

        Computed row by row with the streaming arithmetic: bit-identical to stepping
        :class:`StreamingLDA` through the same sequence."""
        mean, std, w, b = self._arrays()
        x = causal_filter(np.asarray(features, dtype=np.float64), np.asarray(self.kernel))
        z = (x - mean) / std
        wt = np.ascontiguousarray(w.T)
        if z.shape[0] == 0:
            return np.zeros((0, len(self.classes)))
        return np.stack([_softmax(row @ wt + b) for row in z])

    def predict(self, features: FloatArray) -> NDArray[np.int64]:
        out: NDArray[np.int64] = np.argmax(self.predict_proba(features), axis=1)
        return out

    def streaming(self) -> StreamingLDA:
        return StreamingLDA(self)

    def save(self, path: Path) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(asdict(self), indent=1))
        return path

    @classmethod
    def from_dict(cls, data: dict[str, Any], name: str = "model") -> LDAClassifier:
        model = cls(**data)
        if model.kind != "lda":
            raise ValueError(f"{name}: not an LDA model (kind {model.kind!r})")
        k, c = len(model.classes), model.channel_count
        if (
            k < 2
            or len(model.coef) != k
            or any(len(r) != c for r in model.coef)
            or len(model.intercept) != k
            or len(model.class_values) != k
            or len(model.x_std) != c
        ):
            raise ValueError(f"{name}: LDA parameter shapes do not match classes/channels")
        return model

    @classmethod
    def load(cls, path: Path) -> LDAClassifier:
        return cls.from_dict(json.loads(path.read_text()), path.name)


class StreamingLDA:
    """Causal, bin-by-bin posteriors: bit-identical to ``predict_proba``."""

    def __init__(self, model: LDAClassifier) -> None:
        self.model = model
        self._mean, self._std, w, self._b = model._arrays()
        self._wt = np.ascontiguousarray(w.T)
        self._kernel = np.asarray(model.kernel)
        self._history = np.zeros((len(self._kernel), model.channel_count))

    def reset(self) -> None:
        self._history[:] = 0.0

    def step(self, features: FloatArray | list[float]) -> FloatArray:
        self._history = np.roll(self._history, 1, axis=0)
        self._history[0] = np.asarray(features, dtype=np.float64)
        x = filter_step(self._history, self._kernel)
        return _softmax(((x - self._mean) / self._std) @ self._wt + self._b)


def fit_lda(
    features: FloatArray,
    labels: FloatArray,
    valid: NDArray[np.bool_],
    *,
    class_values: list[float],
    class_names: list[str],
    bin_ms: float,
    tau_ms: float = DEFAULT_TAU_MS,
    space: str,
    training: dict[str, Any],
    input_spec: dict[str, Any],
    source: dict[str, Any] | None = None,
) -> LDAClassifier:
    """Fit on one training sequence. Caller guarantees it contains no evaluation data."""
    if len(class_values) != len(class_names) or len(class_values) < 2:
        raise ValueError("need at least two classes, one name per class value")
    kernel = exponential_kernel(bin_ms, tau_ms) if tau_ms > 0 else np.ones(1)
    x = causal_filter(np.asarray(features, dtype=np.float64), kernel)
    rows = valid & np.isin(labels, class_values)
    counts = [int(np.sum(rows & (labels == v))) for v in class_values]
    if min(counts) < MIN_PER_CLASS:
        detail = ", ".join(f"{n}={c}" for n, c in zip(class_names, counts, strict=True))
        raise ValueError(f"too few training bins per class ({detail}; need {MIN_PER_CLASS})")
    xr, yr = x[rows], labels[rows]
    mean = xr.mean(axis=0)
    std = xr.std(axis=0)
    std[std == 0] = 1.0
    z = (xr - mean) / std
    means = np.vstack([z[yr == v].mean(axis=0) for v in class_values])
    centered = np.vstack([z[yr == v] - means[i] for i, v in enumerate(class_values)])
    n, p = centered.shape
    s_emp = centered.T @ centered / n
    shrink = ledoit_wolf_shrinkage(centered)
    mu = float(np.trace(s_emp)) / p
    cov = (1.0 - shrink) * s_emp + shrink * mu * np.eye(p)
    cov_inv_means = np.linalg.solve(cov, means.T).T  # classes x p
    priors = np.asarray(counts, dtype=np.float64) / sum(counts)
    intercept = -0.5 * np.sum(cov_inv_means * means, axis=1) + np.log(priors)
    digest = hashlib.sha256(cov_inv_means.tobytes() + intercept.tobytes()).hexdigest()[:10]
    prefix = "".join(ch if ch.isalnum() else "-" for ch in space.lower()).strip("-")[:32]
    return LDAClassifier(
        model_id=f"{prefix}-lda-{digest}",
        space=space,
        classes=list(class_names),
        class_values=[float(v) for v in class_values],
        bin_ms=bin_ms,
        tau_ms=tau_ms,
        kernel=[float(v) for v in kernel],
        x_mean=mean.tolist(),
        x_std=std.tolist(),
        coef=cov_inv_means.tolist(),
        intercept=intercept.tolist(),
        priors=priors.tolist(),
        shrinkage=shrink,
        training={
            **training,
            "samples_used": int(rows.sum()),
            "class_counts": counts,
            # raw input-feature statistics over all training bins (drift monitoring)
            "feature_stats": {
                "mean": np.asarray(features, dtype=np.float64).mean(axis=0).tolist(),
                "std": np.asarray(features, dtype=np.float64).std(axis=0).tolist(),
                "bins": int(features.shape[0]),
            },
        },
        created_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        input=input_spec,
        source=source or {},
        outputs={"type": "classes", "classes": list(class_names)},
    )


def confusion(true: NDArray[np.int64], pred: NDArray[np.int64], k: int) -> list[list[int]]:
    m = np.zeros((k, k), dtype=np.int64)
    for t, p in zip(true, pred, strict=True):
        m[int(t), int(p)] += 1
    return [[int(v) for v in row] for row in m]


def class_metrics(true: NDArray[np.int64], pred: NDArray[np.int64], k: int) -> dict[str, Any]:
    cm = np.asarray(confusion(true, pred, k))
    support = cm.sum(axis=1)
    recall = [float(cm[i, i] / support[i]) if support[i] else float("nan") for i in range(k)]
    present = [r for r, s in zip(recall, support, strict=True) if s]
    return {
        "accuracy": float(np.trace(cm) / cm.sum()) if cm.sum() else float("nan"),
        "balanced_accuracy": float(np.mean(present)) if present else float("nan"),
        "per_class_recall": recall,
        "support": [int(s) for s in support],
        "confusion": cm.tolist(),
    }


SHIFTS = 20


def evaluate_lda(
    model: LDAClassifier,
    features: FloatArray,
    labels: FloatArray,
    valid: NDArray[np.bool_],
    *,
    skip_first: int = 0,
    shift_control: bool = True,
) -> dict[str, Any]:
    """Score on held-out data. Chance levels and a circular time-shift control included."""
    k = len(model.classes)
    index = {v: i for i, v in enumerate(model.class_values)}
    rows = valid & np.isin(labels, model.class_values)
    rows[:skip_first] = False
    true = np.array([index[float(v)] for v in labels[rows]], dtype=np.int64)
    pred = model.predict(features)[rows]
    m = class_metrics(true, pred, k)
    support = np.asarray(m["support"], dtype=np.float64)
    out: dict[str, Any] = {
        "samples": int(rows.sum()),
        "classes": list(model.classes),
        **m,
        "per_class_accuracy": dict(zip(model.classes, m["per_class_recall"], strict=True)),
        "chance_balanced_accuracy": 1.0 / k,
        "chance_majority_accuracy": float(support.max() / support.sum()) if support.sum() else 0.0,
    }
    if shift_control:
        n = features.shape[0]
        null = []
        for s in range(1, SHIFTS + 1):
            shifted = np.roll(features, (s * n) // (SHIFTS + 1), axis=0)
            pr = model.predict(shifted)[rows]
            null.append(class_metrics(true, pr, k)["balanced_accuracy"])
        out["control_time_shift_balanced_accuracy"] = float(np.mean(null))
        out["control_time_shift_max_balanced_accuracy"] = float(np.max(null))
        out["control_time_shift_n"] = SHIFTS
        out["beats_all_shifts"] = bool(out["balanced_accuracy"] > max(null))
    return out
