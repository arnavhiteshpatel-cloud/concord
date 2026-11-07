"""Online performance monitoring of a running decoder: drift and "recalibration recommended".

Three families of statistics over a rolling window of the most recent bins (default 500):

1. **Input-feature shift** against the model's training statistics (``training.feature_stats``
   ``{mean, std}``, raw input features in input order): per channel, the window mean's
   distance from the training mean in training standard deviations, ``z_c = (m_w - m_t) /
   s_t``; summarised as the RMS over channels and the fraction of channels with ``|z_c| > 1``,
   plus the RMS of ``log(s_w / s_t)`` (gain / variance changes).
2. **Output statistics**: continuous outputs' window mean in training-output standard
   deviations (``training.output_stats``) when the model records them; class / event
   occupancy (fraction of bins each class wins, or each event's probability > 0.5).
3. **Label-based rolling metrics**, only when the source delivers behavioral labels in the
   same session (a cue task, a dataset's kinematics): each decoded bin is paired with the
   label nearest its end within half a bin (as in calibration); rolling R² for continuous
   outputs (dims matched by name), rolling balanced accuracy for classes and events,
   compared with the model's held-out calibration result.

Labels are used for these numbers only; they never reach the decoder or the router.

"Recalibration recommended" is raised when (with at least ``min_bins`` in the window):
the feature shift RMS exceeds ``SHIFT_Z`` or more than ``SHIFTED_FRACTION`` of channels moved
by more than one training SD, or the scale RMS exceeds ``SCALE_LOG``; or the rolling labelled
metric fell below half of its held-out margin over chance (R² below half the held-out R²).
These thresholds are heuristics, documented in docs/DECODER_SDK.md; they are not validated
against closed-loop performance.
"""

from __future__ import annotations

import math
from collections import deque
from typing import Any

import numpy as np
from numpy.typing import NDArray

FloatArray = NDArray[np.float64]
WINDOW_BINS = 500
MIN_BINS = 200
SHIFT_Z = 0.5
SHIFTED_FRACTION = 0.25
SCALE_LOG = math.log(1.5)
MIN_LABEL_PAIRS = 200
EPS = 1e-9


class _Rolling:
    """Mean / variance of the last ``n`` vectors (exact; sums re-based periodically)."""

    def __init__(self, n: int) -> None:
        self.n = n
        self.buf: deque[FloatArray] = deque()
        self.s: FloatArray | None = None
        self.s2: FloatArray | None = None
        self._since_rebase = 0

    def add(self, x: FloatArray) -> None:
        if self.s is None or self.s2 is None or self.s.shape != x.shape:
            self.buf.clear()
            self.s, self.s2 = np.zeros_like(x), np.zeros_like(x)
        self.buf.append(x)
        self.s += x
        self.s2 += x * x
        if len(self.buf) > self.n:
            old = self.buf.popleft()
            self.s -= old
            self.s2 -= old * old
        self._since_rebase += 1
        if self._since_rebase >= 10 * self.n:  # bound floating-point drift of the sums
            arr = np.array(self.buf)
            self.s, self.s2 = arr.sum(axis=0), (arr * arr).sum(axis=0)
            self._since_rebase = 0

    def __len__(self) -> int:
        return len(self.buf)

    def stats(self) -> tuple[FloatArray, FloatArray]:
        assert self.s is not None and self.s2 is not None
        k = len(self.buf)
        mean = self.s / k
        var = np.maximum(self.s2 / k - mean * mean, 0.0)
        return mean, np.sqrt(var)


class DriftMonitor:
    def __init__(
        self,
        *,
        model_id: str,
        dims: list[str],
        output_kind: str,
        bin_ms: float,
        feature_stats: dict[str, Any] | None,
        output_stats: dict[str, Any] | None = None,
        reference: dict[str, Any] | None = None,
        class_values: list[float] | None = None,
        window_bins: int = WINDOW_BINS,
        min_bins: int = MIN_BINS,
    ) -> None:
        self.model_id, self.dims, self.kind = model_id, list(dims), output_kind
        self.bin_ns = round(bin_ms * 1e6)
        self.window, self.min_bins = window_bins, min(min_bins, window_bins)
        self.f_mean = self.f_std = None
        self.feature_reason: str | None = None
        if feature_stats and isinstance(feature_stats.get("mean"), list):
            m = np.asarray(feature_stats["mean"], dtype=np.float64)
            s = np.asarray(feature_stats.get("std") or [], dtype=np.float64)
            if s.shape == m.shape and np.all(np.isfinite(m)) and np.all(np.isfinite(s)):
                self.f_mean, self.f_std = m, s
        if self.f_mean is None:
            self.feature_reason = (
                "the model records no training feature statistics (calibrate it with this "
                "BrainOS version to enable drift detection)"
            )
        self.o_mean = self.o_std = None
        if output_stats and isinstance(output_stats.get("mean"), list):
            self.o_mean = np.asarray(output_stats["mean"], dtype=np.float64)
            self.o_std = np.asarray(output_stats.get("std") or [], dtype=np.float64)
        self.reference = reference or {}
        self.class_values = class_values
        self.features = _Rolling(window_bins)
        self.outputs = _Rolling(window_bins)
        self.bins = 0
        self._pending: deque[tuple[int, FloatArray]] = deque(maxlen=64)  # recent predictions
        self._labels_pending: deque[tuple[int, list[float], list[str]]] = deque(maxlen=64)
        self.pairs: deque[tuple[FloatArray, FloatArray]] = deque(maxlen=window_bins)
        self.label_dims: list[str] | None = None
        self.labels_seen = 0
        self.label_note: str | None = None

    # ------------------------------------------------------------------ input
    def add(self, ts_ns: int, features: FloatArray, values: FloatArray) -> None:
        self.bins += 1
        if self.f_mean is not None and features.shape == self.f_mean.shape:
            self.features.add(np.asarray(features, dtype=np.float64))
        elif self.f_mean is not None and self.feature_reason is None:
            self.feature_reason = (
                f"feature width {features.shape[0]} differs from the training statistics "
                f"({self.f_mean.shape[0]})"
            )
        self.outputs.add(np.asarray(values, dtype=np.float64))
        self._pending.append((ts_ns, np.asarray(values, dtype=np.float64)))
        self._match()

    def add_label(self, ts_ns: int, values: list[float], valid: bool, dims: list[str]) -> None:
        """A behavior sample (for metrics only)."""
        self.labels_seen += 1
        if not valid or not all(math.isfinite(v) for v in values):
            return
        self._labels_pending.append((ts_ns, list(values), list(dims)))
        self._match()

    def _match(self) -> None:
        half = self.bin_ns // 2
        while self._labels_pending and self._pending:
            lts, lvals, ldims = self._labels_pending[0]
            best = min(self._pending, key=lambda p: abs(p[0] - lts))
            if abs(best[0] - lts) <= half:
                self._labels_pending.popleft()
                self._pair(best[1], lvals, ldims)
                continue
            # the label is older than every pending prediction: no prediction will match it
            if lts < self._pending[0][0] - half:
                self._labels_pending.popleft()
                continue
            # the label is newer than every prediction: wait for later predictions
            break

    def _pair(self, pred: FloatArray, lvals: list[float], ldims: list[str]) -> None:
        if self.kind == "continuous":
            common = [d for d in self.dims if d in ldims]
            if not common:
                self.label_note = (
                    f"labels have dims {ldims}; the decoder outputs {self.dims}: no common "
                    "dimension to score"
                )
                return
            self.label_dims = common
            p = np.array([pred[self.dims.index(d)] for d in common])
            y = np.array([lvals[ldims.index(d)] for d in common])
        else:
            if len(lvals) != 1:
                self.label_note = "a class / event label stream must have one dimension"
                return
            self.label_dims = ldims
            p, y = pred, np.array([lvals[0]])
        self.pairs.append((p, y))

    # ------------------------------------------------------------------ status
    def _feature_block(self, reasons: list[str]) -> dict[str, Any]:
        if self.f_mean is None or self.f_std is None or len(self.features) == 0:
            return {"available": False, "reason": self.feature_reason or "no bins yet"}
        mean, std = self.features.stats()
        s_t = np.where(self.f_std > EPS, self.f_std, np.nan)
        z = (mean - self.f_mean) / s_t
        usable = np.isfinite(z)
        if not usable.any():
            return {"available": False, "reason": "every training channel was constant"}
        z = z[usable]
        ratio = np.log(np.maximum(std[usable], EPS) / s_t[usable])
        shift = float(np.sqrt(np.mean(z * z)))
        frac = float(np.mean(np.abs(z) > 1.0))
        scale = float(np.sqrt(np.mean(ratio * ratio)))
        enough = len(self.features) >= self.min_bins
        if enough and shift > SHIFT_Z:
            reasons.append(
                f"input features moved {shift:.2f} training SD (RMS over channels; threshold "
                f"{SHIFT_Z})"
            )
        if enough and frac > SHIFTED_FRACTION:
            reasons.append(f"{frac:.0%} of channels moved more than 1 training SD")
        if enough and scale > SCALE_LOG:
            reasons.append(f"feature variability changed by a factor of ~{math.exp(scale):.2f}")
        worst = np.argsort(-np.abs(z))[:5]
        return {
            "available": True,
            "bins": len(self.features),
            "shift_z_rms": round(shift, 4),
            "channels_shifted_fraction": round(frac, 4),
            "scale_log_ratio_rms": round(scale, 4),
            "most_shifted_channels": [int(np.flatnonzero(usable)[i]) for i in worst],
            "constant_training_channels": int((~usable).sum()),
        }

    def _output_block(self) -> dict[str, Any]:
        if len(self.outputs) == 0:
            return {}
        mean, std = self.outputs.stats()
        out: dict[str, Any] = {"mean": [round(float(v), 5) for v in mean]}
        if self.kind == "classes":
            arr = np.array(self.outputs.buf)
            wins = np.bincount(np.argmax(arr, axis=1), minlength=len(self.dims)) / len(arr)
            out["class_occupancy"] = dict(
                zip(self.dims, (round(float(v), 4) for v in wins), strict=True)
            )
        elif self.kind == "event":
            arr = np.array(self.outputs.buf)
            out["event_rate"] = dict(
                zip(self.dims, (round(float(v), 4) for v in (arr > 0.5).mean(axis=0)), strict=True)
            )
        elif self.o_mean is not None and self.o_std is not None and self.o_mean.shape == mean.shape:
            s = np.where(self.o_std > EPS, self.o_std, np.nan)
            z = (mean - self.o_mean) / s
            out["shift_z"] = [None if not math.isfinite(v) else round(float(v), 4) for v in z]
        out["std"] = [round(float(v), 5) for v in std]
        return out

    def _label_block(self, reasons: list[str]) -> dict[str, Any] | None:
        if self.labels_seen == 0:
            return None
        n = len(self.pairs)
        block: dict[str, Any] = {
            "pairs": n,
            "labels_seen": self.labels_seen,
            "note": self.label_note,
        }
        if n < 10:
            return block
        P = np.array([p for p, _ in self.pairs])
        Y = np.array([y for _, y in self.pairs])
        if self.kind == "continuous":
            sst = float(np.sum((Y - Y.mean(axis=0)) ** 2))
            value = 1.0 - float(np.sum((Y - P) ** 2)) / sst if sst > 0 else float("nan")
            ref = self.reference.get("r2")
            block.update(metric="r2", dims=self.label_dims, value=_r(value), reference=_r(ref))
            if (
                n >= MIN_LABEL_PAIRS
                and isinstance(ref, int | float)
                and ref > 0.05
                and math.isfinite(value)
                and value < 0.5 * ref
            ):
                reasons.append(
                    f"rolling R² {value:.2f} over the last {n} labelled bins is below half the "
                    f"held-out R² ({ref:.2f})"
                )
        else:
            if self.kind == "classes":
                pred = np.argmax(P, axis=1)
                values = self.class_values or [float(i) for i in range(len(self.dims))]
                index = {float(v): i for i, v in enumerate(values)}
                true = np.array([index.get(float(y[0]), -1) for y in Y])
                k = len(self.dims)
            else:
                pred = (P[:, 0] > 0.5).astype(int)
                true = (Y[:, 0] > 0.5).astype(int)
                k = 2
            keep = true >= 0
            recalls = [
                float(np.mean(pred[keep][true[keep] == c] == c))
                for c in range(k)
                if np.any(true[keep] == c)
            ]
            value = float(np.mean(recalls)) if recalls else float("nan")
            ref = self.reference.get("balanced_accuracy")
            chance = self.reference.get("chance_balanced_accuracy") or 1.0 / k
            block.update(
                metric="balanced_accuracy", value=_r(value), reference=_r(ref), chance=_r(chance)
            )
            if (
                n >= MIN_LABEL_PAIRS
                and isinstance(ref, int | float)
                and ref > chance
                and math.isfinite(value)
                and value < chance + 0.5 * (ref - chance)
            ):
                reasons.append(
                    f"rolling balanced accuracy {value:.2f} over the last {n} labelled bins lost "
                    f"more than half of the held-out margin over chance ({ref:.2f} vs {chance:.2f})"
                )
        return block

    def status(self) -> dict[str, Any]:
        reasons: list[str] = []
        feature = self._feature_block(reasons)
        labels = self._label_block(reasons)
        return {
            "model_id": self.model_id,
            "method": "rolling window vs training statistics (decoding/monitor.py)",
            "window_bins": self.window,
            "min_bins": self.min_bins,
            "bins": self.bins,
            "features": feature,
            "outputs": self._output_block(),
            "labels": labels,
            "recalibration_recommended": bool(reasons),
            "reasons": reasons,
        }


def _r(v: object) -> float | None:
    if isinstance(v, int | float) and math.isfinite(v):
        return round(float(v), 4)
    return None
