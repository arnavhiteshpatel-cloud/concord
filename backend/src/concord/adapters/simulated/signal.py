"""Synthetic multichannel signal generator.

The output is Gaussian noise plus per-channel sinusoids. It is NOT a
physiological model and is NOT coupled to any intent. It exists to exercise
the recording path (framing, rates, shape validation, visualization).
"""

from __future__ import annotations

import math
import random


class SyntheticSignal:
    def __init__(
        self,
        channel_count: int,
        sample_rate_hz: float,
        *,
        noise_uv: float = 8.0,
        seed: int | None = None,
    ) -> None:
        self.channel_count = channel_count
        self.sample_rate_hz = sample_rate_hz
        self.noise_uv = noise_uv
        self._rng = random.Random(seed)
        self._freqs = [self._rng.uniform(4.0, 30.0) for _ in range(channel_count)]
        self._amps = [self._rng.uniform(10.0, 40.0) for _ in range(channel_count)]
        self._phases = [self._rng.uniform(0, 2 * math.pi) for _ in range(channel_count)]
        self.next_sample_index = 0

    def frame(self, n_samples: int) -> tuple[int, list[list[float]]]:
        """Return (first_sample_index, samples[channel][sample]) in microvolts."""
        start = self.next_sample_index
        dt = 1.0 / self.sample_rate_hz
        gauss = self._rng.gauss
        out: list[list[float]] = []
        for ch in range(self.channel_count):
            w = 2 * math.pi * self._freqs[ch]
            a = self._amps[ch]
            ph = self._phases[ch]
            nz = self.noise_uv
            out.append(
                [a * math.sin(w * (start + i) * dt + ph) + gauss(0.0, nz) for i in range(n_samples)]
            )
        self.next_sample_index += n_samples
        return start, out
