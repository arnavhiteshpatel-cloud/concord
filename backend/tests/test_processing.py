"""Streaming signal processing: causality, chunk invariance, numerical correctness (M3-AT-7/8)."""

from __future__ import annotations

import numpy as np
import pytest

pytest.importorskip("scipy")

from scipy import signal as sps

from concord.processing import ProcessingSpec, SignalChain, StageConfigError
from concord.processing.stages import (
    BandPower,
    ThresholdCrossings,
    bandpass,
    common_average_reference,
    notch,
)
from concord.testing.lsl_publishers import SyntheticEphys


def _chunks(x: np.ndarray, seed: int = 0) -> list[np.ndarray]:
    rng = np.random.default_rng(seed)
    out, i = [], 0
    while i < len(x):
        n = int(rng.integers(1, 2500))
        out.append(x[i : i + n])
        i += n
    return out


@pytest.mark.parametrize("preset", ["spikeband_threshold", "ecog_high_gamma"])
def test_chain_is_chunk_invariant(preset: str) -> None:
    """M3-AT-7: identical output whether data arrives in one block or random small chunks."""
    fs = 30_000.0 if preset == "spikeband_threshold" else 2_000.0
    gen = SyntheticEphys(channels=12, fs=fs, seed=1)
    x = gen.chunk(int(fs * 4), 0.4, -0.3)
    spec = ProcessingSpec(preset=preset)  # type: ignore[arg-type]
    whole = SignalChain(spec, fs, 12, "uV").push(x)
    streamed = []
    c = SignalChain(spec, fs, 12, "uV")
    for part in _chunks(x):
        streamed += c.push(part)
    assert len(whole) == len(streamed) > 10
    for a, b in zip(whole, streamed, strict=True):
        assert a.bin_index == b.bin_index and a.end_sample == b.end_sample
        assert np.allclose(a.values, b.values, rtol=1e-9, atol=1e-12)


def test_filters_are_causal() -> None:
    """An impulse at sample t produces no output before t."""
    f = bandpass(30_000.0, 250.0, 5000.0, 1)
    x = np.zeros((2000, 1))
    x[1000, 0] = 1.0
    y = f.process(x)
    assert np.all(y[:1000] == 0) and np.any(y[1000:] != 0)


def test_bandpass_and_notch_frequency_response() -> None:
    fs = 2000.0
    t = np.arange(int(fs * 4)) / fs
    for freq, expect_pass in [(10.0, False), (100.0, True), (600.0, False)]:
        x = np.sin(2 * np.pi * freq * t)[:, None]
        y = bandpass(fs, 70.0, 150.0, 1).process(x)
        gain = y[int(fs) :].std() / x[int(fs) :].std()
        assert (gain > 0.8) if expect_pass else (gain < 0.1), (freq, gain)
    x = np.sin(2 * np.pi * 60.0 * t)[:, None]
    y = notch(fs, 60.0, 1).process(x)
    assert y[int(fs * 2) :].std() / x.std() < 0.05


def test_common_average_reference_removes_shared_signal() -> None:
    shared = np.sin(np.linspace(0, 20, 500))[:, None] * np.ones((1, 8))
    private = np.random.default_rng(0).normal(size=(500, 8))
    y = common_average_reference(shared + private)
    assert np.allclose(y.mean(axis=1), 0) and np.abs(np.corrcoef(y[:, 0], shared[:, 0])[0, 1]) < 0.2


def test_threshold_crossings_recover_injected_spikes() -> None:
    """M3-AT-8: >= 95% of injected spikes after RMS warm-up are detected, few false positives."""
    fs = 30_000.0
    gen = SyntheticEphys(channels=8, fs=fs, seed=2, base_rate_hz=20, tuning_depth_hz=0)
    x = gen.chunk(int(fs * 6))
    bp = bandpass(fs, 250.0, 5000.0, 8)
    tc = ThresholdCrossings(fs, 8, bin_ms=20.0)
    bins = []
    for part in _chunks(x, seed=3):
        bins += tc.process(bp.process(part))
    detected = float(np.sum(bins))
    warm = tc.warmup_samples
    injected = sum(1 for _, s in gen.spike_log if s >= warm + 300 and s < len(x) - 300)
    assert 0.95 * injected <= detected <= 1.05 * injected


def test_threshold_crossings_refractory_across_chunks() -> None:
    """A crossing exactly at a chunk boundary is not double counted."""
    fs = 10_000.0
    tc = ThresholdCrossings(fs, 1, bin_ms=10.0, rms_window_s=0.1)
    calm = np.random.default_rng(0).normal(size=(1000, 1))
    tc.process(calm)  # RMS ~1, threshold ~ -4.5
    x = np.zeros((200, 1))
    x[100:105, 0] = -20.0  # one 5-sample spike
    whole = ThresholdCrossings(fs, 1, bin_ms=10.0, rms_window_s=0.1)
    whole.process(calm)
    a = whole.process(x)
    b = tc.process(x[:102]) + tc.process(x[102:])
    assert float(np.sum(a)) == float(np.sum(b)) == 1.0


def test_band_power_matches_analytic_power() -> None:
    """M3-AT-8: log10 mean power of a 100 Hz tone of amplitude A is log10(A^2 / 2)."""
    fs, a = 2000.0, 50.0
    t = np.arange(int(fs * 3)) / fs
    x = (a * np.sin(2 * np.pi * 100 * t))[:, None]
    bp = BandPower(fs, 1, 70.0, 150.0, bin_ms=50.0)
    vals = np.array([v[0] for v in bp.process(x)])
    steady = vals[10:]  # after filter settling
    assert np.allclose(steady, np.log10(a**2 / 2), atol=0.02)


@pytest.mark.parametrize(
    ("spec", "fs", "msg"),
    [
        (ProcessingSpec(preset="spikeband_threshold"), 1000.0, "10 kHz"),
        (ProcessingSpec(preset="ecog_high_gamma"), 250.0, "400 Hz"),
        (ProcessingSpec(preset="band_power"), 1000.0, "band_low_hz"),
        (ProcessingSpec(preset="spikeband_threshold", bin_ms=0.01), 30_000.0, "whole number"),
    ],
)
def test_invalid_configurations_are_refused(spec: ProcessingSpec, fs: float, msg: str) -> None:
    with pytest.raises(StageConfigError, match=msg):
        SignalChain(spec, fs, 4, "uV")


def test_scipy_reference_equivalence() -> None:
    """Our streaming bandpass equals scipy's one-shot sosfilt with the same design."""
    fs = 30_000.0
    x = np.random.default_rng(5).normal(size=(30_000, 3))
    f = bandpass(fs, 250.0, 5000.0, 3)
    streamed = np.vstack([f.process(p) for p in _chunks(x, 9)])
    ref = sps.sosfilt(sps.butter(4, [250, 5000], btype="bandpass", fs=fs, output="sos"), x, axis=0)
    assert np.allclose(streamed, ref, atol=1e-10)
