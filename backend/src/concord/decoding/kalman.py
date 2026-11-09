"""Velocity Kalman filter decoder (Wu et al. 2006; Gilja et al. 2012, velocity-only state).

State ``v_t`` (the output dims, e.g. ``[vx, vy]``); observation ``z_t`` = the decoder's input
features, causally smoothed and z-scored with **training** statistics only:

    v_t = A v_{t-1} + w,       w ~ N(0, W)
    z_t = C v_t + c0 + q,      q ~ N(0, Q)       (Q shrunk toward its diagonal)

A, W from consecutive training labels (within blocks only); C, c0, Q by least squares. The
filter runs with its steady-state gain K (Riccati iteration at fit time), so a step is
``v_t = M v_{t-1} + K (z_t - c0)`` with ``M = A - K C A``; ``covariance()`` returns the
steady-state posterior covariance of the output dims.

Inputs may be several feature streams (e.g. threshold crossings + spike band power), joined
per bin in the order of ``inputs``. Per-input transforms are declared in the model
(``identity`` or ``log1p``) so the same maths runs offline and in the pipeline.

numpy only; models are JSON (no pickle).
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

FloatArray = NDArray[np.float64]
TRANSFORMS = ("identity", "log1p")
KIND = "kalman"


def apply_transforms(x: FloatArray, widths: Sequence[int], transforms: Sequence[str]) -> FloatArray:
    """Per-input feature transform on (bins, sum(widths)) or (sum(widths),) arrays."""
    if all(t == "identity" for t in transforms):
        return x
    out = np.array(x, dtype=np.float64, copy=True)
    start = 0
    for w, t in zip(widths, transforms, strict=True):
        sl = (..., slice(start, start + w))
        if t == "log1p":
            out[sl] = np.log1p(np.maximum(out[sl], 0.0))
        elif t != "identity":
            raise ValueError(f"unknown transform {t!r}")
        start += w
    return out


def smoothing_coefficient(tau_ms: float, bin_ms: float) -> float:
    """y_t = a*y_{t-1} + (1-a)*x_t; a = exp(-bin/tau); tau 0 = no smoothing."""
    return float(np.exp(-bin_ms / tau_ms)) if tau_ms > 0 else 0.0


def exp_smooth(x: FloatArray, a: float) -> FloatArray:
    if a == 0.0:
        return np.asarray(x, dtype=np.float64)
    from scipy.signal import lfilter

    out: FloatArray = lfilter([1.0 - a], [1.0, -a], np.asarray(x, dtype=np.float64), axis=0)
    return out


@dataclass
class KalmanDecoder:
    model_id: str
    space: str
    quantity: str
    dims: list[str]
    unit: str
    bin_ms: float
    inputs: list[dict[str, Any]]
    transforms: list[str]
    smoothing_tau_ms: float
    x_mean: list[float]
    x_std: list[float]
    A: list[list[float]]
    W: list[list[float]]
    C: list[list[float]]  # features x dims
    c0: list[float]
    K: list[list[float]]  # dims x features (steady-state gain)
    M: list[list[float]]  # dims x dims
    P: list[list[float]]  # steady-state posterior covariance (dims x dims)
    shrinkage: float
    training: dict[str, Any]
    kind: str = KIND
    evaluations: list[dict[str, Any]] = field(default_factory=list)
    created_at: str = ""
    method: str = (
        "Velocity Kalman filter (Wu 2006 / Gilja 2012): causal exponential smoothing, z-score "
        "(training statistics), linear-Gaussian observation model with diagonal-shrunk noise "
        "covariance, steady-state gain"
    )
    schema: str = "concord.model/1"
    version: int = 1
    source: dict[str, Any] = field(default_factory=dict)
    manifest: dict[str, Any] | None = None
    # direction of +y in the output space ("up" for screen coordinates with +y up, e.g. the T15
    # dataset); the router refuses to drive a +y-down pointer from it unless invert_y is set
    y_axis: str | None = None

    # -------------------------------------------------------------- properties
    @property
    def channel_count(self) -> int:
        return len(self.x_mean)

    @property
    def widths(self) -> list[int]:
        return [int(i["channel_count"]) for i in self.inputs]

    @property
    def input(self) -> dict[str, Any]:
        """Legacy single-input view (first input)."""
        return self.inputs[0] if self.inputs else {}

    def validate(self, name: str = "model") -> None:
        n, d = self.channel_count, len(self.dims)
        if self.kind != KIND:
            raise ValueError(f"{name}: kind {self.kind!r} is not {KIND!r}")
        if not self.inputs or sum(self.widths) != n:
            raise ValueError(f"{name}: inputs declare {sum(self.widths)} features, model has {n}")
        if len(self.transforms) != len(self.inputs) or any(
            t not in TRANSFORMS for t in self.transforms
        ):
            raise ValueError(f"{name}: transforms must be one of {TRANSFORMS} per input")
        shapes = {
            "x_std": (np.shape(self.x_std), (n,)),
            "c0": (np.shape(self.c0), (n,)),
            "C": (np.shape(self.C), (n, d)),
            "K": (np.shape(self.K), (d, n)),
            "A": (np.shape(self.A), (d, d)),
            "W": (np.shape(self.W), (d, d)),
            "M": (np.shape(self.M), (d, d)),
            "P": (np.shape(self.P), (d, d)),
        }
        for k, (got, want) in shapes.items():
            if got != want:
                raise ValueError(f"{name}: {k} has shape {got}, expected {want}")
        arrays = [self.x_mean, self.x_std, self.C, self.c0, self.K, self.M, self.P, self.A, self.W]
        if not all(np.all(np.isfinite(np.asarray(a, dtype=np.float64))) for a in arrays):
            raise ValueError(f"{name}: non-finite parameters")
        if np.any(np.asarray(self.x_std) <= 0):
            raise ValueError(f"{name}: x_std must be positive")
        p = np.asarray(self.P)
        if not np.allclose(p, p.T, atol=1e-9) or np.any(np.diag(p) < 0):
            raise ValueError(f"{name}: P must be symmetric with a non-negative diagonal")
        if self.y_axis not in (None, "up", "down"):
            raise ValueError(f"{name}: y_axis must be 'up', 'down' or null")
        if np.max(np.abs(np.linalg.eigvals(np.asarray(self.M)))) >= 1.0:
            raise ValueError(f"{name}: filter dynamics are unstable (|eig(M)| >= 1)")

    # ----------------------------------------------------------------- inference
    def preprocess(self, x: FloatArray) -> FloatArray:
        """Transform + smooth + z-score a whole (bins, features) sequence (filter starts at 0)."""
        z = apply_transforms(np.asarray(x, dtype=np.float64), self.widths, self.transforms)
        z = exp_smooth(z, smoothing_coefficient(self.smoothing_tau_ms, self.bin_ms))
        out: FloatArray = (z - np.asarray(self.x_mean)) / np.asarray(self.x_std)
        return out

    def predict(self, x: FloatArray) -> FloatArray:
        """Offline decoding of a whole sequence; identical maths to ``streaming().step``."""
        u = (self.preprocess(x) - np.asarray(self.c0)) @ np.asarray(self.K).T
        m = np.asarray(self.M)
        out = np.empty((len(u), len(self.dims)))
        v = np.zeros(len(self.dims))
        for t in range(len(u)):
            v = m @ v + u[t]
            out[t] = v
        return out

    def streaming(self) -> StreamingKalman:
        return StreamingKalman(self)

    # ------------------------------------------------------------- persistence
    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def save(self, path: Path) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_dict(), indent=1), encoding="utf-8")
        return path

    @classmethod
    def from_dict(cls, data: dict[str, Any], name: str = "model") -> KalmanDecoder:
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
    def load(cls, path: Path) -> KalmanDecoder:
        return cls.from_dict(json.loads(path.read_text(encoding="utf-8")), path.name)


class StreamingKalman:
    """Bin-by-bin decoding with the model's steady-state gain."""

    def __init__(self, model: KalmanDecoder) -> None:
        self.model = model
        self._mean = np.asarray(model.x_mean)
        self._std = np.asarray(model.x_std)
        self._c0 = np.asarray(model.c0)
        self._k = np.asarray(model.K)
        self._m = np.asarray(model.M)
        self._p = np.asarray(model.P)
        self._a = smoothing_coefficient(model.smoothing_tau_ms, model.bin_ms)
        self._widths = model.widths
        self._transforms = model.transforms
        self.reset()

    def reset(self) -> None:
        self._s = np.zeros(self.model.channel_count)
        self._v = np.zeros(len(self.model.dims))

    def step(self, features: FloatArray | Sequence[float]) -> FloatArray:
        x = np.asarray(features, dtype=np.float64)
        if x.shape != self._mean.shape:
            raise ValueError(f"expected {self._mean.shape[0]} features, got {x.shape}")
        x = apply_transforms(x, self._widths, self._transforms)
        self._s = self._a * self._s + (1.0 - self._a) * x
        z = (self._s - self._mean) / self._std
        self._v = self._m @ self._v + self._k @ (z - self._c0)
        return self._v.copy()

    def covariance(self) -> FloatArray:
        out: FloatArray = self._p.copy()
        return out


# ---------------------------------------------------------------------------- fitting
def _steady_state(
    a: FloatArray, w: FloatArray, c: FloatArray, q: FloatArray, iters: int = 10_000
) -> tuple[FloatArray, FloatArray]:
    """Steady-state gain K and posterior covariance P (information form; Q is features^2)."""
    qi = np.linalg.inv(q)
    cqc = c.T @ qi @ c
    p = w.copy()
    for _ in range(iters):
        pp = a @ p @ a.T + w
        pn = np.linalg.inv(np.linalg.inv(pp) + cqc)
        if np.max(np.abs(pn - p)) < 1e-14:
            p = pn
            break
        p = pn
    pp = a @ p @ a.T + w
    post = np.linalg.inv(np.linalg.inv(pp) + cqc)
    k = post @ c.T @ qi
    post = (post + post.T) / 2
    return k, post


def fit(
    features: Sequence[FloatArray],
    targets: Sequence[FloatArray],
    *,
    inputs: list[dict[str, Any]],
    transforms: list[str],
    smoothing_tau_ms: float,
    shrinkage: float,
    dims: list[str],
    unit: str,
    space: str,
    quantity: str = "velocity",
    training: dict[str, Any] | None = None,
    source: dict[str, Any] | None = None,
    model_id_prefix: str | None = None,
    y_axis: str | None = None,
) -> KalmanDecoder:
    """Fit on a list of contiguous training segments (blocks); transitions never cross segments.

    The caller guarantees the segments contain no evaluation data.
    """
    if not features or len(features) != len(targets):
        raise ValueError("need one target array per feature segment")
    bin_ms = float(inputs[0]["bin_ms"])
    widths = [int(i["channel_count"]) for i in inputs]
    a_s = smoothing_coefficient(smoothing_tau_ms, bin_ms)
    zs = [
        exp_smooth(apply_transforms(np.asarray(f, dtype=np.float64), widths, transforms), a_s)
        for f in features
    ]
    ys = [np.asarray(t, dtype=np.float64) for t in targets]
    for z, y in zip(zs, ys, strict=True):
        if z.shape[0] != y.shape[0] or z.shape[1] != sum(widths) or y.shape[1] != len(dims):
            raise ValueError("feature/target shapes do not match the declared inputs/dims")
    x = np.vstack(zs)
    y = np.vstack(ys)
    if len(x) < 100:
        raise ValueError(f"too few training bins ({len(x)})")
    mean = x.mean(axis=0)
    std = x.std(axis=0)
    std[std == 0] = 1.0
    z = (x - mean) / std
    prev = np.vstack([s[:-1] for s in ys])
    nxt = np.vstack([s[1:] for s in ys])
    a = np.linalg.lstsq(prev, nxt, rcond=None)[0].T
    w = np.atleast_2d(np.cov((nxt - prev @ a.T).T))
    yt = np.hstack([y, np.ones((len(y), 1))])
    ct = np.linalg.lstsq(yt, z, rcond=None)[0].T
    c, c0 = ct[:, : len(dims)], ct[:, len(dims)]
    q = np.cov((z - yt @ ct.T).T)
    q = (1.0 - shrinkage) * q + shrinkage * np.diag(np.diag(q))
    k, p = _steady_state(a, w, c, q)
    m = a - k @ c @ a
    digest = hashlib.sha256(k.tobytes() + m.tobytes()).hexdigest()[:10]
    prefix = model_id_prefix or "".join(ch if ch.isalnum() else "-" for ch in space.lower())[:32]
    feature_stats = {"mean": mean.tolist(), "std": std.tolist()}
    model = KalmanDecoder(
        model_id=f"{prefix}-kalman-{digest}",
        space=space,
        quantity=quantity,
        dims=list(dims),
        unit=unit,
        bin_ms=bin_ms,
        inputs=[dict(i) for i in inputs],
        transforms=list(transforms),
        smoothing_tau_ms=float(smoothing_tau_ms),
        x_mean=mean.tolist(),
        x_std=std.tolist(),
        A=a.tolist(),
        W=w.tolist(),
        C=c.tolist(),
        c0=c0.tolist(),
        K=k.tolist(),
        M=m.tolist(),
        P=p.tolist(),
        shrinkage=float(shrinkage),
        training={
            **(training or {}),
            "bins": len(x),
            "segments": len(zs),
            "feature_stats": feature_stats,
            "behavior_mean": y.mean(axis=0).tolist(),
            "behavior_std": y.std(axis=0).tolist(),
            "output_stats": {"mean": y.mean(axis=0).tolist(), "std": y.std(axis=0).tolist()},
        },
        created_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        source=source or {},
        y_axis=y_axis,
    )
    model.validate()
    return model


def fit_calibration(data: Any) -> KalmanDecoder:
    """Calibration-workflow entry point (``families.CalibrationData``): continuous targets."""
    opts = dict(getattr(data, "options", {}) or {})
    sl = data.train
    valid = np.asarray(data.valid, dtype=bool)[sl]
    feats = np.asarray(data.features, dtype=np.float64)[sl]
    targ = np.asarray(data.targets, dtype=np.float64)[sl]
    # contiguous valid runs become segments, so no dynamics are fitted across gaps
    segments_f: list[FloatArray] = []
    segments_y: list[FloatArray] = []
    edges = np.flatnonzero(np.diff(np.concatenate([[0], valid.astype(np.int8), [0]])))
    for s, e in zip(edges[::2], edges[1::2], strict=True):
        if e - s >= 10:
            segments_f.append(feats[s:e])
            segments_y.append(targ[s:e])
    return fit(
        segments_f,
        segments_y,
        inputs=list(data.inputs),
        transforms=list(opts.get("transforms") or ["identity"] * len(data.inputs)),
        smoothing_tau_ms=float(opts.get("smoothing_tau_ms", 0.0)),
        shrinkage=float(opts.get("shrinkage", 0.9)),
        dims=list(data.target_dims),
        unit=str(data.target_unit),
        space=str(data.space),
        quantity=str(getattr(data, "target_quantity", "velocity")),
        training=dict(data.training),
        source=dict(data.source),
        y_axis=opts.get("y_axis"),
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
            name="kalman",
            kinds=frozenset({KIND}),
            output="continuous",
            from_dict=KalmanDecoder.from_dict,
            description="Velocity Kalman filter (Wu/Gilja), steady-state gain",
            confidence="covariance",
            capabilities=frozenset({"continuous"}),
            fit=fit_calibration,
        )
    )


_register_family()
