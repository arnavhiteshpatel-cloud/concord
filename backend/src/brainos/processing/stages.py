"""Causal, stateful, chunk-invariant signal-processing stages.

Every stage keeps its state across calls, so processing a recording in one block or in
arbitrary chunks gives the same output (tested). Nothing looks ahead in time.

Arrays are (samples, channels), float64.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from numpy.typing import NDArray
from scipy import signal as sps

F64 = NDArray[np.float64]


class StageConfigError(ValueError):
    """A stage cannot run with the given sample rate / parameters."""


# ------------------------------------------------------------------ filters


@dataclass
class SOSFilter:
    """Butterworth/IIR second-order-sections filter with per-channel state (scipy.sosfilt)."""

    sos: F64
    channels: int
    description: str
    _zi: F64 = field(init=False)

    def __post_init__(self) -> None:
        self._zi = np.zeros((self.sos.shape[0], 2, self.channels))

    def process(self, x: F64) -> F64:
        y, self._zi = sps.sosfilt(self.sos, x, axis=0, zi=self._zi)
        return np.asarray(y, dtype=np.float64)


def bandpass(fs: float, low: float, high: float, channels: int, order: int = 4) -> SOSFilter:
    nyq = fs / 2
    if not 0 < low < high < nyq:
        raise StageConfigError(
            f"bandpass {low:g}-{high:g} Hz needs 0 < low < high < Nyquist ({nyq:g} Hz at fs={fs:g})"
        )
    sos = sps.butter(order, [low, high], btype="bandpass", fs=fs, output="sos")
    return SOSFilter(
        np.asarray(sos), channels, f"butterworth bandpass {low:g}-{high:g} Hz, order {order}"
    )


def notch(fs: float, f0: float, channels: int, q: float = 30.0) -> SOSFilter:
    if not 0 < f0 < fs / 2:
        raise StageConfigError(f"notch at {f0:g} Hz is outside (0, {fs / 2:g}) Hz")
    b, a = sps.iirnotch(f0, q, fs=fs)
    return SOSFilter(np.asarray(sps.tf2sos(b, a)), channels, f"notch {f0:g} Hz (Q={q:g})")


def common_average_reference(x: F64) -> F64:
    """Subtract the across-channel mean at each sample (stateless, causal)."""
    return x - x.mean(axis=1, keepdims=True)


# ------------------------------------------------------------------ binning


@dataclass
class _Binner:
    """Accumulates per-sample quantities into fixed bins on the sample clock."""

    fs: float
    bin_ms: float
    channels: int
    bin_samples: int = field(init=False)
    _acc: F64 = field(init=False)
    _filled: int = 0
    bins_out: int = 0

    def __post_init__(self) -> None:
        self.bin_samples = round(self.fs * self.bin_ms / 1000)
        if (
            self.bin_samples < 1
            or abs(self.bin_samples / self.fs * 1000 - self.bin_ms) > 1e-6 * self.bin_ms + 1e-9
        ):
            raise StageConfigError(
                f"bin of {self.bin_ms:g} ms is not a whole number of samples at {self.fs:g} Hz"
            )
        self._acc = np.zeros(self.channels)

    def add(self, per_sample: F64) -> list[F64]:
        """Add per-sample values (n, ch); return the bins completed by this chunk."""
        out: list[F64] = []
        i = 0
        n = per_sample.shape[0]
        while i < n:
            take = min(self.bin_samples - self._filled, n - i)
            self._acc += per_sample[i : i + take].sum(axis=0)
            self._filled += take
            i += take
            if self._filled == self.bin_samples:
                out.append(self._acc.copy())
                self._acc[:] = 0.0
                self._filled = 0
                self.bins_out += 1
        return out


@dataclass
class ThresholdCrossings:
    """Negative threshold crossings at ``k`` x RMS, counted per bin (spike-band input).

    The RMS of each channel is estimated from the first ``rms_window_s`` of (filtered) data
    and then frozen, as in common iBCI practice; no bins are emitted during estimation. A
    crossing is a sample below threshold whose previous sample was not; a refractory
    period suppresses re-triggering.
    """

    fs: float
    channels: int
    bin_ms: float = 20.0
    k: float = -4.5
    rms_window_s: float = 1.0
    refractory_ms: float = 1.0
    thresholds: F64 | None = None
    _sumsq: F64 = field(init=False)
    _nrms: int = 0
    _prev_below: NDArray[np.bool_] = field(init=False)
    _since: NDArray[np.int64] = field(init=False)
    _binner: _Binner = field(init=False)

    def __post_init__(self) -> None:
        if self.k >= 0:
            raise StageConfigError("threshold multiplier k must be negative (e.g. -4.5)")
        self._sumsq = np.zeros(self.channels)
        self._prev_below = np.zeros(self.channels, dtype=bool)
        self._refr = max(1, round(self.refractory_ms * self.fs / 1000))
        self._since = np.full(self.channels, self._refr, dtype=np.int64)
        self._binner = _Binner(self.fs, self.bin_ms, self.channels)

    @property
    def calibrated(self) -> bool:
        return self.thresholds is not None

    @property
    def warmup_samples(self) -> int:
        return round(self.rms_window_s * self.fs)

    def process(self, x: F64) -> list[F64]:
        if self.thresholds is None:
            need = self.warmup_samples - self._nrms
            head, x = x[:need], x[need:]
            self._sumsq += (head**2).sum(axis=0)
            self._nrms += head.shape[0]
            if self._nrms < self.warmup_samples:
                return []
            rms = np.sqrt(self._sumsq / self._nrms)
            self.thresholds = self.k * rms
            if x.shape[0] == 0:
                return []
        n = x.shape[0]
        below = x < self.thresholds
        shifted = np.vstack([self._prev_below[None, :], below[:-1]])
        onset = below & ~shifted
        events = np.zeros((n, self.channels))
        # Refractory: only actual onsets (few per second) are iterated. Equivalent to the
        # sequential rule "onset at t counts if t - last_event >= refractory".
        for c in np.flatnonzero(onset.any(axis=0)):
            last = -int(self._since[c])  # position of the previous event relative to this chunk
            for i in np.flatnonzero(onset[:, c]):
                if i - last >= self._refr:
                    events[i, c] = 1.0
                    last = int(i)
            self._since[c] = n - last
        quiet = ~onset.any(axis=0)
        self._since[quiet] += n
        self._prev_below = below[-1].copy()
        return self._binner.add(events)


@dataclass
class BandPower:
    """Mean power in one band per bin (bandpass -> square -> bin mean), optionally log10."""

    fs: float
    channels: int
    low: float
    high: float
    bin_ms: float = 50.0
    log: bool = True
    order: int = 4
    _filt: SOSFilter = field(init=False)
    _binner: _Binner = field(init=False)

    EPS = 1e-20  # floor inside log10 to keep silent channels finite (documented)

    def __post_init__(self) -> None:
        self._filt = bandpass(self.fs, self.low, self.high, self.channels, self.order)
        self._binner = _Binner(self.fs, self.bin_ms, self.channels)

    def process(self, x: F64) -> list[F64]:
        y = self._filt.process(x)
        sums = self._binner.add(y * y)
        out = []
        for s in sums:
            mean = s / self._binner.bin_samples
            out.append(np.log10(mean + self.EPS) if self.log else mean)
        return out
