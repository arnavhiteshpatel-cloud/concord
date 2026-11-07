"""Software LSL publishers for hardware-free testing (official liblsl via pylsl).

These are TEST PUBLISHERS, not acquisition systems. Every stream they create declares
itself in ``<desc><brainos>`` as ``synthetic`` (generated) or ``prerecorded`` (replayed from
a file), so BrainOS never presents their output as live human data.

* ``SyntheticEphysPublisher`` — broadband "intracortical-like" signal: Gaussian noise plus
  biphasic spikes at known sample indices, optionally with firing rates cosine-tuned to a
  latent 2-D velocity (also published as a behavior stream). For DSP/pipeline tests.
* ``FalconLSLPublisher`` — replays a FALCON H1 NWB block (real human recording) as three LSL
  streams: binned spike counts (type ``SpikeCounts``), cued kinematics (type ``Behavior``)
  and trial markers (type ``Markers``), all declared prerecorded with the DANDI origin.
"""

from __future__ import annotations

import math
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
from numpy.typing import NDArray


def _pylsl() -> Any:
    import pylsl

    return pylsl


def _declare(desc: Any, *, synthetic: bool, prerecorded: bool, origin: str, **extra: str) -> None:
    b = desc.append_child("brainos")
    b.append_child_value("synthetic", "true" if synthetic else "false")
    b.append_child_value("prerecorded", "true" if prerecorded else "false")
    b.append_child_value("origin", origin)
    for k, v in extra.items():
        b.append_child_value(k, v)


def _channels(desc: Any, labels: list[str], unit: str | None, ctype: str) -> None:
    chs = desc.append_child("channels")
    for label in labels:
        c = chs.append_child("channel")
        c.append_child_value("label", label)
        if unit is not None:
            c.append_child_value("unit", unit)
        c.append_child_value("type", ctype)


# ------------------------------------------------------------------ synthetic broadband


SPIKE_WAVEFORM_MS = 1.2


def spike_waveform(fs: float, amplitude_uv: float = -80.0) -> NDArray[np.float64]:
    """Biphasic extracellular-like waveform (negative trough then positive repolarization)."""
    n = max(4, int(fs * SPIKE_WAVEFORM_MS / 1000))
    t = np.linspace(0, 1, n)
    w = -np.exp(-((t - 0.25) ** 2) / 0.006) + 0.35 * np.exp(-((t - 0.55) ** 2) / 0.02)
    return amplitude_uv * w / abs(w.min())


@dataclass
class SyntheticEphys:
    """Deterministic generator of broadband data with known spike times."""

    channels: int = 16
    fs: float = 30_000.0
    noise_uv: float = 10.0
    base_rate_hz: float = 15.0
    tuning_depth_hz: float = 12.0
    seed: int = 0
    amplitude_uv: float = -80.0
    rng: np.random.Generator = field(init=False)
    pref_dirs: NDArray[np.float64] = field(init=False)
    sample: int = 0
    spike_log: list[tuple[int, int]] = field(
        default_factory=list
    )  # (channel, sample index of trough)
    _tail: NDArray[np.float64] = field(init=False)

    def __post_init__(self) -> None:
        self.rng = np.random.default_rng(self.seed)
        self.pref_dirs = self.rng.uniform(0, 2 * np.pi, self.channels)
        self.wave = spike_waveform(self.fs, self.amplitude_uv)
        self._tail = np.zeros((len(self.wave), self.channels))

    def rates(self, vx: float, vy: float) -> NDArray[np.float64]:
        speed = math.hypot(vx, vy)
        ang = math.atan2(vy, vx)
        r = self.base_rate_hz + self.tuning_depth_hz * speed * np.cos(ang - self.pref_dirs)
        return np.clip(r, 0.5, None)

    def chunk(self, n: int, vx: float = 0.0, vy: float = 0.0) -> NDArray[np.float64]:
        out = self.rng.normal(0.0, self.noise_uv, size=(n, self.channels))
        w = len(self.wave)
        carry = self._tail
        k = min(w, n)
        out[:k] += carry[:k]
        new_tail = np.zeros_like(carry)
        new_tail[: w - k] = carry[k:]
        rates = self.rates(vx, vy)
        for c in range(self.channels):
            count = self.rng.poisson(rates[c] * n / self.fs)
            for pos in np.sort(self.rng.integers(0, n, count)):
                trough = int(np.argmin(self.wave))
                self.spike_log.append((c, self.sample + int(pos) + trough))
                end = pos + w
                if end <= n:
                    out[pos:end, c] += self.wave
                else:
                    out[pos:, c] += self.wave[: n - pos]
                    new_tail[: end - n, c] += self.wave[n - pos :]
        self._tail = new_tail
        self.sample += n
        return out


class _Thread:
    def __init__(self) -> None:
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self.error: BaseException | None = None

    def start(self) -> None:
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._safe_run, daemon=True, name=type(self).__name__
        )
        self._thread.start()

    def _safe_run(self) -> None:
        try:
            self.run()
        except BaseException as exc:  # surfaced to tests via .error
            self.error = exc

    def run(self) -> None:  # pragma: no cover - overridden
        raise NotImplementedError

    def stop(self, timeout: float = 5.0) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout)


class SyntheticEphysPublisher(_Thread):
    """Real-time LSL publisher of ``SyntheticEphys`` (declared synthetic)."""

    def __init__(
        self,
        *,
        name: str = "BrainOS synthetic ephys",
        source_id: str = "brainos-synthetic-ephys",
        channels: int = 16,
        fs: float = 30_000.0,
        chunk_ms: float = 10.0,
        unit: str | None = "microvolts",
        stream_type: str = "EEG",
        latent: bool = True,
        seed: int = 0,
        channel_format: str = "float32",
    ) -> None:
        super().__init__()
        self.gen = SyntheticEphys(channels=channels, fs=fs, seed=seed)
        self.name, self.source_id, self.unit, self.stream_type = name, source_id, unit, stream_type
        self.chunk = max(1, int(fs * chunk_ms / 1000))
        self.latent = latent
        self.channel_format = channel_format
        self.skip_next_samples = 0  # fault injection: drop N samples (timestamp gap)
        self.pushed = 0
        self.push_log: list[tuple[float, int]] = []  # (local_clock at push, samples so far)

    def latent_velocity(self, t: float) -> tuple[float, float]:
        """Smooth 2-D trajectory used as hidden 'intended velocity' (for tuning + labels)."""
        return math.cos(2 * math.pi * 0.25 * t), math.sin(2 * math.pi * 0.17 * t)

    def run(self) -> None:
        pylsl = _pylsl()
        fmt = {"float32": pylsl.cf_float32, "double64": pylsl.cf_double64, "int16": pylsl.cf_int16}[
            self.channel_format
        ]
        info = pylsl.StreamInfo(
            self.name, self.stream_type, self.gen.channels, self.gen.fs, fmt, self.source_id
        )
        desc = info.desc()
        _channels(desc, [f"ch{i:03d}" for i in range(self.gen.channels)], self.unit, "EEG")
        _declare(desc, synthetic=True, prerecorded=False, origin="brainos:synthetic-ephys")
        out = pylsl.StreamOutlet(info, chunk_size=self.chunk, max_buffered=60)
        beh_out = None
        if self.latent:
            binfo = pylsl.StreamInfo(
                f"{self.name} latent velocity",
                "Behavior",
                2,
                self.gen.fs / self.chunk,
                pylsl.cf_float32,
                self.source_id + "-behavior",
            )
            _channels(binfo.desc(), ["vx", "vy"], "arbitrary", "Velocity")
            _declare(
                binfo.desc(),
                synthetic=True,
                prerecorded=False,
                origin="brainos:synthetic-ephys",
                quantity="velocity",
            )
            beh_out = pylsl.StreamOutlet(binfo)
        dt = self.chunk / self.gen.fs
        t0 = pylsl.local_clock()
        k = 0
        while not self._stop.is_set():
            target = t0 + (k + 1) * dt
            now = pylsl.local_clock()
            if target > now:
                time.sleep(target - now)
            t_chunk = k * dt
            vx, vy = self.latent_velocity(t_chunk) if self.latent else (0.0, 0.0)
            data = self.gen.chunk(self.chunk, vx, vy)
            stamp = t0 + (k + 1) * dt  # timestamp of the last sample in the chunk
            if self.skip_next_samples > 0:
                self.skip_next_samples -= self.chunk
            else:
                out.push_chunk(
                    data.astype(np.float32 if self.channel_format == "float32" else np.float64),
                    stamp,
                )
                self.pushed += self.chunk
                self.push_log.append((pylsl.local_clock(), self.pushed))
                if beh_out is not None:
                    beh_out.push_sample([vx, vy], stamp)
            k += 1
        del out
        del beh_out


# ------------------------------------------------------------------ FALCON H1 over LSL


class FalconLSLPublisher(_Thread):
    """Replays a FALCON H1 block (real recording) as LSL streams, declared prerecorded.

    Spike counts are published at the bin end time, with the behavior sample and any
    trial-start marker for the same bin carrying the same timestamp (one local clock).
    """

    def __init__(
        self,
        path: Path,
        *,
        speed: float = 1.0,
        source_prefix: str | None = None,
        loop: bool = False,
        hold: threading.Event | None = None,
    ) -> None:
        """``hold``: if given, outlets are created but data starts only once it is set."""
        super().__init__()
        from brainos.adapters.nwb.reader import load
        from brainos.datasets import verify_file

        self.path = Path(path)
        self.rec = load(self.path)
        v = verify_file(self.path)
        self.origin = (
            f"dandi:{v.manifest.dandiset}/{v.asset.path}"
            if v.manifest and v.asset
            else f"file:{self.path.name}"
        )
        self.speed = speed
        self.loop = loop
        self.hold = hold
        self.finished = threading.Event()
        self.prefix = source_prefix or f"falcon-h1-{self.path.stem.split('_ses-')[-1].lower()}"
        self.bins_published = 0
        self.push_log: list[tuple[float, int, float]] = []  # (local_clock at push, bin, ts)

    def run(self) -> None:
        pylsl = _pylsl()
        rec = self.rec
        fs = 1.0 / rec.bin_s
        n_ch = rec.channel_count
        labels = [f"unit{c.unit_id}" for c in rec.channels]

        info = pylsl.StreamInfo(
            f"FALCON H1 {self.prefix} spike counts",
            "SpikeCounts",
            n_ch,
            fs,
            pylsl.cf_int16,
            self.prefix + "-counts",
        )
        _channels(info.desc(), labels, "count", "SpikeCount")
        _declare(
            info.desc(),
            synthetic=False,
            prerecorded=True,
            origin=self.origin,
            feature="spike_count",
        )
        counts_out = pylsl.StreamOutlet(info, chunk_size=1, max_buffered=60)

        assert rec.behavior is not None
        b = rec.behavior
        binfo = pylsl.StreamInfo(
            f"FALCON H1 {self.prefix} kinematics",
            "Behavior",
            len(b.dims),
            fs,
            pylsl.cf_float32,
            self.prefix + "-behavior",
        )
        _channels(binfo.desc(), b.dims, b.unit, "Velocity")
        _declare(
            binfo.desc(), synthetic=False, prerecorded=True, origin=self.origin, quantity=b.quantity
        )
        beh_out = pylsl.StreamOutlet(binfo, chunk_size=1)

        minfo = pylsl.StreamInfo(
            f"FALCON H1 {self.prefix} trials",
            "Markers",
            1,
            0.0,
            pylsl.cf_string,
            self.prefix + "-markers",
        )
        _declare(minfo.desc(), synthetic=False, prerecorded=True, origin=self.origin)
        mk_out = pylsl.StreamOutlet(minfo)

        time.sleep(0.5)  # let consumers discover and connect before data starts
        if self.hold is not None:
            while not self.hold.wait(0.05):
                if self._stop.is_set():
                    return
        while not self._stop.is_set():
            t0 = pylsl.local_clock() + 0.05
            last_trial = None
            for start, chunk in rec.iter_counts():
                for j in range(chunk.shape[0]):
                    if self._stop.is_set():
                        return
                    i = start + j
                    rel = rec.bin_end_s(i) - rec.bin_end_s(0)
                    stamp = t0 + rel / self.speed
                    now = pylsl.local_clock()
                    if stamp > now:
                        time.sleep(stamp - now)
                    row = b.values[i] if b.valid[i] else np.full(len(b.dims), np.nan)
                    counts_out.push_sample(chunk[j].astype(np.int16).tolist(), stamp)
                    beh_out.push_sample([float(v) for v in row], stamp)
                    if b.trial is not None and b.trial[i] != last_trial:
                        last_trial = b.trial[i]
                        mk_out.push_sample([f"trial {int(last_trial)}"], stamp)
                    self.bins_published += 1
                    self.push_log.append((pylsl.local_clock(), i, stamp))
            if not self.loop:
                break
        self.finished.set()
        time.sleep(0.5)
