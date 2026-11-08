"""Deterministic, SYNTHETIC motor-imagery EEG (numpy only; no Concord, no plugin API).

What it generates (per 250 Hz sample, standard 10-20 labels, microvolts):

* background: 1/f-like ("pink") noise per channel - a sum of three first-order low-pass
  branches plus white noise - and a small common-mode component;
* rhythms: three narrow-band sources (second-order resonators driven by white noise):
  a left-hemisphere mu rhythm (strongest at C3), a right-hemisphere mu rhythm (C4) and a
  posterior alpha rhythm (O1/Oz/O2), mixed into the channels with fixed spatial weights;
* a cue schedule ``rest, <left|right>, rest, <left|right>, ...`` (each ``cue_duration_s``);
  imagined LEFT-hand movement reduces the RIGHT mu source (C4) and imagined RIGHT-hand
  movement the LEFT one (C3) by ``effect_size`` (event-related desynchronisation), with a
  0.3 s time constant.

This is a teaching / demo signal: plausible in shape, NOT physiologically validated, and it
must never be presented as brain data. Output depends only on the configuration (seed),
never on timing, so tests can regenerate it bit-exactly.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np
from numpy.typing import NDArray

FS_HZ = 250.0
BLOCK = 25  # samples per generated block (100 ms)
BEHAVIOR_DECIMATION = 5  # cue class sampled at 50 Hz
CLASSES = ("rest", "left", "right")  # cue_class codes 0, 1, 2

MONTAGES: dict[str, tuple[str, ...]] = {
    "8": ("F3", "Fz", "F4", "C3", "Cz", "C4", "P3", "P4"),
    "16": (
        "Fp1", "Fp2", "F3", "Fz", "F4", "T7", "C3", "Cz",
        "C4", "T8", "P3", "Pz", "P4", "O1", "Oz", "O2",
    ),
}  # fmt: skip

# Spatial weights of the three sources (left mu, right mu, posterior alpha) per electrode.
WEIGHTS: dict[str, tuple[float, float, float]] = {
    "Fp1": (0.05, 0.02, 0.05), "Fp2": (0.02, 0.05, 0.05),
    "F3": (0.35, 0.08, 0.10), "Fz": (0.25, 0.25, 0.10), "F4": (0.08, 0.35, 0.10),
    "T7": (0.30, 0.03, 0.15), "C3": (1.00, 0.10, 0.20), "Cz": (0.45, 0.45, 0.20),
    "C4": (0.10, 1.00, 0.20), "T8": (0.03, 0.30, 0.15),
    "P3": (0.35, 0.08, 0.60), "Pz": (0.20, 0.20, 0.80), "P4": (0.08, 0.35, 0.60),
    "O1": (0.03, 0.01, 1.00), "Oz": (0.02, 0.02, 1.00), "O2": (0.01, 0.03, 1.00),
}  # fmt: skip

PINK_POLES = (0.997, 0.963, 0.57)  # corners ~0.1, ~1.5 and ~17 Hz at 250 Hz
PINK_GAINS = (0.099046, 0.2965164, 1.0526913)
PINK_DIRECT = 0.1848
PINK_RMS_UV = 6.0
COMMON_RMS_UV = 2.0
MU_RMS_UV = 8.0
ALPHA_RMS_UV = 10.0
RESONATOR_R = 0.985  # pole radius: ~1.2 Hz bandwidth
ERD_TAU_S = 0.3


@dataclass(frozen=True, slots=True)
class GeneratorConfig:
    seed: int = 1
    montage: str = "8"
    cue_duration_s: float = 4.0
    effect_size: float = 0.5  # fractional amplitude reduction of the contralateral mu source

    def __post_init__(self) -> None:
        if self.montage not in MONTAGES:
            raise ValueError(f"montage must be one of {sorted(MONTAGES)}")
        if not 1.0 <= self.cue_duration_s <= 30.0:
            raise ValueError("cue_duration_s must be in [1, 30]")
        if not 0.0 <= self.effect_size <= 0.95:
            raise ValueError("effect_size must be in [0, 0.95]")
        if self.seed < 0:
            raise ValueError("seed must be >= 0")


@dataclass(slots=True)
class Block:
    first_index: int  # sample index of eeg[0]
    eeg: NDArray[np.float32]  # (BLOCK, n_channels), microvolts
    cue: NDArray[np.int8]  # (BLOCK,) class code per sample
    markers: list[tuple[int, str]] = field(default_factory=list)  # (sample index, label)


def _pink_rms_unit() -> float:
    """Exact output std of the pink filter for unit-variance white input."""
    p, c, d = PINK_POLES, PINK_GAINS, PINK_DIRECT
    var = sum(c[i] * c[j] / (1 - p[i] * p[j]) for i in range(3) for j in range(3))
    return math.sqrt(var + 2 * d * sum(c) + d * d)


def _resonator(freq_hz: float) -> tuple[float, float, float]:
    """(a1, a2, input gain) of a unit-variance AR(2) resonator at ``freq_hz``."""
    w = 2 * math.pi * freq_hz / FS_HZ
    a1, a2 = 2 * RESONATOR_R * math.cos(w), -(RESONATOR_R**2)
    var = (1 - a2) / ((1 + a2) * ((1 - a2) ** 2 - a1 * a1))
    return a1, a2, 1.0 / math.sqrt(var)


class MotorImageryGenerator:
    """Call :meth:`next_block` repeatedly; blocks are contiguous from sample 0."""

    def __init__(self, config: GeneratorConfig) -> None:
        self.config = config
        self.labels = MONTAGES[config.montage]
        self._rng = np.random.default_rng([config.seed, 1])
        self._schedule_rng = np.random.default_rng([config.seed, 2])
        n = len(self.labels)
        self._mix = np.array([WEIGHTS[x] for x in self.labels], dtype=np.float64)  # (n, 3)
        freqs = 10.0 + self._rng.uniform(-0.6, 0.6, size=3)
        self._res = [_resonator(f) for f in freqs]
        self._src_state = np.zeros((3, 2))  # x[t-1], x[t-2] per source
        self._src_rms = np.array([MU_RMS_UV, MU_RMS_UV, ALPHA_RMS_UV])
        self._pink = np.zeros((3, n))
        self._pink_scale = PINK_RMS_UV / _pink_rms_unit()
        self._gain = np.ones(2)  # ERD gain of the left / right mu source
        self._lag = math.exp(-1.0 / (ERD_TAU_S * FS_HZ))
        self._cue_len = round(config.cue_duration_s * FS_HZ)
        self._trials: list[int] = []  # class code of trial k (k even = rest)
        self.index = 0

    @property
    def n_channels(self) -> int:
        return len(self.labels)

    def cue_at(self, sample_index: int) -> int:
        k = sample_index // self._cue_len
        while len(self._trials) <= k:
            t = len(self._trials)
            self._trials.append(0 if t % 2 == 0 else 1 + int(self._schedule_rng.integers(2)))
        return self._trials[k]

    def next_block(self) -> Block:
        n = self.n_channels
        start = self.index
        white = self._rng.standard_normal((BLOCK, n))
        common = self._rng.standard_normal(BLOCK) * COMMON_RMS_UV
        drive = self._rng.standard_normal((BLOCK, 3))
        eeg = np.empty((BLOCK, n), dtype=np.float64)
        cue = np.empty(BLOCK, dtype=np.int8)
        markers: list[tuple[int, str]] = []
        effect = self.config.effect_size
        p, c, d = PINK_POLES, PINK_GAINS, PINK_DIRECT
        for i in range(BLOCK):
            idx = start + i
            k = self.cue_at(idx)
            cue[i] = k
            if idx % self._cue_len == 0:
                markers.append((idx, f"cue {CLASSES[k]}"))
            # event-related desynchronisation: left imagery -> right mu source, and vice versa
            target = np.array([1.0 - effect if k == 2 else 1.0, 1.0 - effect if k == 1 else 1.0])
            self._gain = target + (self._gain - target) * self._lag
            # sources
            src = np.empty(3)
            for s, (a1, a2, g) in enumerate(self._res):
                x = a1 * self._src_state[s, 0] + a2 * self._src_state[s, 1] + g * drive[i, s]
                self._src_state[s, 1] = self._src_state[s, 0]
                self._src_state[s, 0] = x
                src[s] = x * self._src_rms[s]
            src[:2] *= self._gain
            # pink background
            w = white[i]
            for b in range(3):
                self._pink[b] = p[b] * self._pink[b] + c[b] * w
            pink = (self._pink.sum(axis=0) + d * w) * self._pink_scale
            eeg[i] = pink + self._mix @ src + common[i]
        self.index += BLOCK
        return Block(start, eeg.astype(np.float32), cue, markers)
