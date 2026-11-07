"""Modality presets that turn a raw multichannel stream into binned features.

``SignalChain.push(samples)`` consumes raw chunks (samples x channels) in arrival order and
returns completed feature bins. It is causal and chunk-invariant (see stages.py).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

import numpy as np
from numpy.typing import NDArray
from pydantic import BaseModel, ConfigDict, Field

from brainos.processing.stages import (
    BandPower,
    SOSFilter,
    StageConfigError,
    ThresholdCrossings,
    bandpass,
    common_average_reference,
    notch,
)

Preset = Literal["spikeband_threshold", "ecog_high_gamma", "band_power", "features_passthrough"]

PRESET_INFO: dict[str, str] = {
    "spikeband_threshold": (
        "Intracortical broadband (>= 10 kHz): 250-5000 Hz bandpass, common average reference, "
        "negative threshold crossings at k x RMS (RMS from the first second), counts per bin."
    ),
    "ecog_high_gamma": (
        "ECoG/sEEG/LFP (>= 400 Hz): line-noise notch (+ harmonics; the source's declared mains "
        "frequency if it states one), common average reference without the electrodes the "
        "source marks bad, 70-150 Hz bandpass, log10 mean power per bin."
    ),
    "band_power": "Any rate: log10 mean power in one configurable band per bin.",
    "features_passthrough": (
        "Source already delivers binned features (e.g. spike counts over LSL): no processing."
    ),
}


class ProcessingSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    preset: Preset
    bin_ms: float | None = Field(default=None, gt=0, le=1000)
    threshold_k: float = Field(default=-4.5, lt=0, ge=-20)
    rms_window_s: float = Field(default=1.0, gt=0, le=60)
    car: bool | None = None  # default: on when >= 8 channels
    line_hz: Literal[50, 60] | None = 60
    band_low_hz: float | None = Field(default=None, gt=0)
    band_high_hz: float | None = Field(default=None, gt=0)


@dataclass(frozen=True, slots=True)
class FeatureFrame:
    event_type: Literal["features.binned", "features.vector"]
    feature: str
    unit: str
    bin_ms: float
    bin_index: int
    values: NDArray[np.float64]
    band_hz: tuple[float, float] | None
    end_sample: int  # processed-sample index (exclusive) at which this bin ended


@dataclass(frozen=True, slots=True)
class OutputSpec:
    event_type: str
    feature: str
    bin_ms: float
    channel_count: int
    unit: str


class SignalChain:
    def __init__(
        self,
        spec: ProcessingSpec,
        fs: float,
        channels: int,
        unit: str,
        *,
        car_exclude: Sequence[int] = (),
        channel_labels: Sequence[str] | None = None,
    ) -> None:
        """``car_exclude`` (M5): channel indices left out of the common average (e.g. the
        electrodes the source marks bad); they are still referenced and still produce features.
        """
        if spec.preset == "features_passthrough":
            raise StageConfigError("features_passthrough has no signal chain")
        if channels < 1 or fs <= 0:
            raise StageConfigError("invalid channel count / sample rate")
        self.spec, self.fs, self.channels, self.unit = spec, fs, channels, unit
        self.pre: list[SOSFilter] = []
        self.car = spec.car if spec.car is not None else channels >= 8
        excl = sorted({int(i) for i in car_exclude})
        if any(not 0 <= i < channels for i in excl):
            raise StageConfigError(f"CAR exclusion {excl} outside 0..{channels - 1}")
        if len(excl) >= channels:
            raise StageConfigError("CAR would exclude every channel")
        self.car_reference: NDArray[np.bool_] | None = None
        if excl:
            self.car_reference = np.ones(channels, dtype=bool)
            self.car_reference[excl] = False
        self._car_excluded = (
            [channel_labels[i] for i in excl]
            if channel_labels is not None and len(channel_labels) == channels
            else [str(i) for i in excl]
        )
        self.processed = 0
        self._bins = 0
        self.stages: list[str] = []
        p = spec.preset
        if p == "spikeband_threshold":
            if fs < 10_000:
                raise StageConfigError(
                    f"spikeband_threshold needs >= 10 kHz broadband data; source is {fs:g} Hz"
                )
            hi = min(5000.0, 0.45 * fs)
            self.pre.append(bandpass(fs, 250.0, hi, channels))
            self.tc: ThresholdCrossings | None = ThresholdCrossings(
                fs,
                channels,
                bin_ms=spec.bin_ms or 20.0,
                k=spec.threshold_k,
                rms_window_s=spec.rms_window_s,
            )
            self.bp: BandPower | None = None
            self.out = OutputSpec(
                "features.binned", "threshold_crossing_count", self.tc.bin_ms, channels, "count"
            )
        elif p in ("ecog_high_gamma", "band_power"):
            if p == "ecog_high_gamma":
                if fs < 400:
                    raise StageConfigError(f"ecog_high_gamma needs >= 400 Hz; source is {fs:g} Hz")
                low, high = 70.0, min(150.0, 0.45 * fs)
                if spec.line_hz:
                    f = float(spec.line_hz)
                    while f < 0.45 * fs:
                        self.pre.append(notch(fs, f, channels))
                        f += spec.line_hz
            else:
                if spec.band_low_hz is None or spec.band_high_hz is None:
                    raise StageConfigError("band_power needs band_low_hz and band_high_hz")
                low, high = spec.band_low_hz, spec.band_high_hz
            self.tc = None
            self.bp = BandPower(fs, channels, low, high, bin_ms=spec.bin_ms or 50.0)
            unit_out = "log10(uV^2)" if unit == "uV" else "log10(arbitrary^2)"
            self.out = OutputSpec(
                "features.vector", "log_band_power", self.bp.bin_ms, channels, unit_out
            )
            self.band = (low, high)
        else:  # pragma: no cover - Literal guards this
            raise StageConfigError(f"unknown preset {p}")
        self.stages = [f.description for f in self.pre]
        if self.car and self.car_reference is not None:
            n_ref = int(self.car_reference.sum())
            self.stages.append(
                f"common average reference over {n_ref} of {channels} channels "
                f"(excluded as bad: {', '.join(self._car_excluded)})"
            )
        elif self.car:
            self.stages.append("common average reference")
        if self.tc is not None:
            self.stages.append(
                f"threshold crossings at {spec.threshold_k:g} x RMS "
                f"(RMS over first {spec.rms_window_s:g} s), "
                f"refractory 1 ms, {self.tc.bin_ms:g} ms bins"
            )
        if self.bp is not None:
            self.stages.append(
                f"log10 power {self.band[0]:g}-{self.band[1]:g} Hz, {self.bp.bin_ms:g} ms bins"
            )

    @property
    def warmup_samples(self) -> int:
        return self.tc.warmup_samples if self.tc is not None else 0

    def push(self, samples: NDArray[np.float64]) -> list[FeatureFrame]:
        x = np.asarray(samples, dtype=np.float64)
        if x.ndim != 2 or x.shape[1] != self.channels:
            raise ValueError(f"expected (n, {self.channels}) samples, got {x.shape}")
        start = self.processed
        self.processed += x.shape[0]
        for f in self.pre:
            x = f.process(x)
        if self.car:
            x = common_average_reference(x, self.car_reference)
        out: list[FeatureFrame] = []
        if self.tc is not None:
            bins = self.tc.process(x)
            bs = self.tc._binner.bin_samples
            first_end = self.processed - (self.tc._binner._filled) - (len(bins) - 1) * bs
            for j, b in enumerate(bins):
                out.append(
                    FeatureFrame(
                        "features.binned",
                        self.out.feature,
                        "count",
                        self.out.bin_ms,
                        self._bins,
                        b,
                        None,
                        first_end + j * bs,
                    )
                )
                self._bins += 1
        elif self.bp is not None:
            bins = self.bp.process(x)
            bs = self.bp._binner.bin_samples
            first_end = self.processed - self.bp._binner._filled - (len(bins) - 1) * bs
            for j, b in enumerate(bins):
                out.append(
                    FeatureFrame(
                        "features.vector",
                        self.out.feature,
                        self.out.unit,
                        self.out.bin_ms,
                        self._bins,
                        b,
                        self.band,
                        first_end + j * bs,
                    )
                )
                self._bins += 1
        del start
        return out
