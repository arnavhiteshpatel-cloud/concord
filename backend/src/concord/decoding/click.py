"""Click decoder: neural features -> P(click attempt) per bin (L2 logistic regression).

Labels come from the task, never from a command path: in calibration the participant was
instructed to attempt a click while the cursor touched the target, so (by default) bins with
the cursor on the target are positive and others negative (``labels.py`` in ``evaluation``
documents the variants). The model outputs a probability only (dims ``["click"]``, quantity
``click_probability``, unit ``probability``). Turning probabilities into clicks is the command
router's job (threshold + hold + refractory, under operator control); the decision rule the
model was tuned with on its training data is recorded in ``decision`` as advice.

Features are transformed per input (``identity`` / ``log1p``), causally smoothed and z-scored
with training statistics. numpy only; JSON models.
"""

from __future__ import annotations

import hashlib
import json
import time
from collections.abc import Sequence
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
from numpy.typing import NDArray

from concord.decoding.kalman import (
    TRANSFORMS,
    apply_transforms,
    exp_smooth,
    smoothing_coefficient,
)

FloatArray = NDArray[np.float64]
KIND = "click_logistic"


def _sigmoid(x: FloatArray) -> FloatArray:
    out: FloatArray = 1.0 / (1.0 + np.exp(-np.clip(x, -30.0, 30.0)))
    return out


@dataclass
class ClickDecoder:
    model_id: str
    space: str
    bin_ms: float
    inputs: list[dict[str, Any]]
    transforms: list[str]
    smoothing_tau_ms: float
    x_mean: list[float]
    x_std: list[float]
    weights: list[float]
    intercept: float
    l2: float
    training: dict[str, Any]
    decision: dict[str, Any] = field(default_factory=dict)
    kind: str = KIND
    dims: list[str] = field(default_factory=lambda: ["click"])
    quantity: str = "click_probability"
    unit: str = "probability"
    evaluations: list[dict[str, Any]] = field(default_factory=list)
    created_at: str = ""
    method: str = (
        "Click probability: causal exponential smoothing, z-score (training statistics), "
        "L2-regularized logistic regression on task-defined click-attempt labels"
    )
    schema: str = "concord.model/1"
    version: int = 1
    source: dict[str, Any] = field(default_factory=dict)
    manifest: dict[str, Any] | None = None

    @property
    def channel_count(self) -> int:
        return len(self.x_mean)

    @property
    def widths(self) -> list[int]:
        return [int(i["channel_count"]) for i in self.inputs]

    @property
    def input(self) -> dict[str, Any]:
        return self.inputs[0] if self.inputs else {}

    def validate(self, name: str = "model") -> None:
        n = self.channel_count
        if self.kind != KIND:
            raise ValueError(f"{name}: kind {self.kind!r} is not {KIND!r}")
        if self.dims != ["click"] or self.quantity != "click_probability":
            raise ValueError(f"{name}: a click model outputs dims ['click'] / click_probability")
        if not self.inputs or sum(self.widths) != n:
            raise ValueError(f"{name}: inputs declare {sum(self.widths)} features, model has {n}")
        if len(self.transforms) != len(self.inputs) or any(
            t not in TRANSFORMS for t in self.transforms
        ):
            raise ValueError(f"{name}: transforms must be one of {TRANSFORMS} per input")
        if len(self.x_std) != n or len(self.weights) != n:
            raise ValueError(f"{name}: x_std/weights must have {n} entries")
        arrays = [self.x_mean, self.x_std, self.weights, [self.intercept]]
        if not all(np.all(np.isfinite(np.asarray(a, dtype=np.float64))) for a in arrays):
            raise ValueError(f"{name}: non-finite parameters")
        if np.any(np.asarray(self.x_std) <= 0):
            raise ValueError(f"{name}: x_std must be positive")

    def preprocess(self, x: FloatArray) -> FloatArray:
        z = apply_transforms(np.asarray(x, dtype=np.float64), self.widths, self.transforms)
        z = exp_smooth(z, smoothing_coefficient(self.smoothing_tau_ms, self.bin_ms))
        out: FloatArray = (z - np.asarray(self.x_mean)) / np.asarray(self.x_std)
        return out

    def predict(self, x: FloatArray) -> FloatArray:
        """P(click) for a whole sequence, shape (bins, 1); identical to ``streaming().step``."""
        p = _sigmoid(self.preprocess(x) @ np.asarray(self.weights) + self.intercept)
        return p[:, None]

    def streaming(self) -> StreamingClick:
        return StreamingClick(self)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def save(self, path: Path) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_dict(), indent=1))
        return path

    @classmethod
    def from_dict(cls, data: dict[str, Any], name: str = "model") -> ClickDecoder:
        if not isinstance(data, dict):
            raise ValueError(f"{name}: not a model object")
        d = dict(data)
        if "inputs" not in d and isinstance(d.get("input"), dict):
            d["inputs"] = [d.pop("input")]
        d.pop("input", None)
        try:
            model = cls(**d)
        except TypeError as exc:
            raise ValueError(f"{name}: {exc}") from exc
        model.validate(name)
        return model

    @classmethod
    def load(cls, path: Path) -> ClickDecoder:
        return cls.from_dict(json.loads(path.read_text()), path.name)


class StreamingClick:
    def __init__(self, model: ClickDecoder) -> None:
        self.model = model
        self._mean = np.asarray(model.x_mean)
        self._std = np.asarray(model.x_std)
        self._w = np.asarray(model.weights)
        self._a = smoothing_coefficient(model.smoothing_tau_ms, model.bin_ms)
        self._widths = model.widths
        self._transforms = model.transforms
        self.reset()

    def reset(self) -> None:
        self._s = np.zeros(self.model.channel_count)

    def step(self, features: FloatArray | Sequence[float]) -> FloatArray:
        x = np.asarray(features, dtype=np.float64)
        if x.shape != self._mean.shape:
            raise ValueError(f"expected {self._mean.shape[0]} features, got {x.shape}")
        x = apply_transforms(x, self._widths, self._transforms)
        self._s = self._a * self._s + (1.0 - self._a) * x
        z = (self._s - self._mean) / self._std
        return _sigmoid(np.asarray([z @ self._w + self.model.intercept]))


# ---------------------------------------------------------------------------- fitting
def logistic_regression(
    z: FloatArray, y: FloatArray, l2: float, iters: int = 50
) -> tuple[FloatArray, float]:
    """Newton/IRLS with an L2 penalty on the weights (not the intercept)."""
    n, p = z.shape
    zz = np.hstack([z, np.ones((n, 1))])
    w = np.zeros(p + 1)
    pen = np.full(p + 1, l2)
    pen[-1] = 0.0
    for _ in range(iters):
        prob = _sigmoid(zz @ w)
        grad = zz.T @ (prob - y) + pen * w
        hess = (zz * (prob * (1.0 - prob))[:, None]).T @ zz + np.diag(pen)
        step = np.linalg.solve(hess, grad)
        w -= step
        if np.max(np.abs(step)) < 1e-7:
            break
    return w[:-1], float(w[-1])


RELEASE_GAP = 0.15  # the command router's default hysteresis (release = threshold - 0.15)


def decision_events(
    p: FloatArray,
    threshold: float,
    hold_bins: int,
    refractory_bins: int,
    release: float | None = None,
) -> NDArray[np.int64]:
    """The command router's click rule, bin by bin (``runtime/router.py: _step``).

    Fires when P >= ``threshold`` for ``hold_bins`` consecutive bins (router ``debounce_ms`` =
    (hold_bins - 1) x bin), at least ``refractory_bins`` after the previous click, and then
    waits until P falls below ``release`` (default threshold - 0.15) before it can fire again.
    The evaluation uses this so offline numbers mean what the live chain does.
    """
    rel = max(0.0, threshold - RELEASE_GAP) if release is None else release
    out: list[int] = []
    armed = True
    above: int | None = None
    last: int | None = None
    for t, v in enumerate(np.ravel(p)):
        if not armed:
            if v < rel:
                armed = True
            above = None
            continue
        if v < threshold:
            above = None
            continue
        if above is None:
            above = t
        held = t - above >= hold_bins - 1
        rested = last is None or t - last >= refractory_bins
        if held and rested:
            out.append(t)
            last = t
            armed = False
            above = None
    return np.asarray(out, dtype=np.int64)


def router_click_rule(decision: dict[str, Any], output: str = "click") -> dict[str, Any]:
    """The router ``ClickRule`` equivalent to a model's recorded ``decision`` advice."""
    bin_ms = float(decision.get("bin_ms", 10.0))
    return {
        "output": output,
        "threshold": float(decision["threshold"]),
        "debounce_ms": (int(decision["hold_bins"]) - 1) * bin_ms,
        "refractory_ms": float(decision["refractory_ms"]),
    }


def fit(
    features: Sequence[FloatArray],
    labels: Sequence[FloatArray],
    weights: Sequence[FloatArray] | None = None,
    *,
    inputs: list[dict[str, Any]],
    transforms: list[str],
    smoothing_tau_ms: float,
    l2: float,
    space: str,
    training: dict[str, Any] | None = None,
    source: dict[str, Any] | None = None,
    model_id_prefix: str | None = None,
) -> ClickDecoder:
    """Fit on training segments. ``weights`` 0 excludes a bin (ambiguous label)."""
    bin_ms = float(inputs[0]["bin_ms"])
    widths = [int(i["channel_count"]) for i in inputs]
    a_s = smoothing_coefficient(smoothing_tau_ms, bin_ms)
    xs = [
        exp_smooth(apply_transforms(np.asarray(f, dtype=np.float64), widths, transforms), a_s)
        for f in features
    ]
    ys = [np.asarray(y, dtype=np.float64).ravel() for y in labels]
    ws = [np.asarray(w, dtype=np.float64).ravel() for w in weights] if weights else None
    x = np.vstack(xs)
    y = np.concatenate(ys)
    keep = np.concatenate(ws) > 0 if ws else np.ones(len(y), dtype=bool)
    if x.shape[0] != y.shape[0] or x.shape[1] != sum(widths):
        raise ValueError("feature/label shapes do not match the declared inputs")
    if not set(np.unique(y[keep])) <= {0.0, 1.0} or len(np.unique(y[keep])) < 2:
        raise ValueError("labels must contain both 0 and 1")
    mean = x[keep].mean(axis=0)
    std = x[keep].std(axis=0)
    std[std == 0] = 1.0
    w, b = logistic_regression((x[keep] - mean) / std, y[keep], l2)
    digest = hashlib.sha256(w.tobytes() + np.float64(b).tobytes()).hexdigest()[:10]
    prefix = model_id_prefix or "".join(ch if ch.isalnum() else "-" for ch in space.lower())[:32]
    model = ClickDecoder(
        model_id=f"{prefix}-click-{digest}",
        space=space,
        bin_ms=bin_ms,
        inputs=[dict(i) for i in inputs],
        transforms=list(transforms),
        smoothing_tau_ms=float(smoothing_tau_ms),
        x_mean=mean.tolist(),
        x_std=std.tolist(),
        weights=w.tolist(),
        intercept=b,
        l2=float(l2),
        training={
            **(training or {}),
            "bins": int(keep.sum()),
            "positive_fraction": float(y[keep].mean()),
            "feature_stats": {"mean": mean.tolist(), "std": std.tolist()},
            "behavior_std": [float(y[keep].std())],
        },
        created_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        source=source or {},
    )
    model.validate()
    return model


def fit_calibration(data: Any) -> ClickDecoder:
    """Calibration-workflow entry point (``families.CalibrationData``, target ``click``)."""
    opts = dict(getattr(data, "options", {}) or {})
    positive = opts.get("positive_value", 1)
    sl = data.train
    valid = np.asarray(data.valid, dtype=bool)[sl]
    targ = np.asarray(data.targets, dtype=np.float64)[sl].reshape(-1)
    return fit(
        [np.asarray(data.features, dtype=np.float64)[sl]],
        [(targ == float(positive)).astype(np.float64)],
        [valid.astype(np.float64)],
        inputs=list(data.inputs),
        transforms=list(opts.get("transforms") or ["identity"] * len(data.inputs)),
        smoothing_tau_ms=float(opts.get("smoothing_tau_ms", 100.0)),
        l2=float(opts.get("l2", 1000.0)),
        space=str(data.space),
        training=dict(data.training),
        source=dict(data.source),
    )


def _register_family() -> None:
    """Register with the decoder families registry (Milestone 5, workstream A), if present."""
    import importlib

    try:
        families = importlib.import_module("concord.decoding.families")
    except ImportError:  # only before the families module exists
        return
    families.register_family(
        families.BuiltinFamily(
            name="click",
            kinds=frozenset({KIND}),
            output="event",
            from_dict=ClickDecoder.from_dict,
            description="Click probability (logistic regression); router applies the decision",
            confidence="posterior",
            capabilities=frozenset({"click"}),
            fit=fit_calibration,
        )
    )


_register_family()
