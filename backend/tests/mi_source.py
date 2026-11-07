"""In-test synthetic motor-imagery EEG source (SYNTHETIC — not human data).

Same structure as the third-party example adapter used for the Milestone 4 demo: scalp-EEG-like
channels at 250 Hz, a cue sequence rest / left / right, a contralateral mu-band (8-13 Hz)
power decrease during imagery (left-hand cue -> C4 side, right-hand cue -> C3 side), a
behavior stream ``cue_class`` (0 rest, 1 left, 2 right) and cue-onset markers.

Variants for negative tests: ``signal=False`` (behavior labels + markers only) and
``behavior=False`` (raw signal only).
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
from numpy.typing import NDArray

from brainos.adapters.base import DeviceAdapter, DeviceLinkError, EventDraft, NativePacket
from brainos.contracts.capabilities import Capability, CapabilityDescriptor, EventType
from brainos.contracts.events import Provenance, ProvenanceKind, Quality, QualityFlag
from brainos.contracts.protocol import DeviceDescriptor, DeviceKind

CHANNELS = ("FC3", "C3", "CP3", "Cz", "FC4", "C4", "CP4", "Pz")
CLASS_NAMES = ["rest", "left", "right"]
LEFT_SIDE = {"FC3": 0.6, "C3": 1.0, "CP3": 0.6}  # attenuated by right-hand imagery
RIGHT_SIDE = {"FC4": 0.6, "C4": 1.0, "CP4": 0.6}  # attenuated by left-hand imagery
ADAPTER = "test.motor-imagery@0.1.0"
ORIGIN = "brainos:test-motor-imagery"


@dataclass
class MotorImageryGenerator:
    """Deterministic multichannel generator; ``chunk(n)`` returns samples, labels, onsets."""

    fs: float = 250.0
    seed: int = 0
    cue_s: float = 3.0
    mu_hz: float = 10.5
    mu_uv: float = 6.0
    erd: float = 0.45  # amplitude retained at the most affected channel during imagery
    noise_uv: float = 5.0
    sample: int = 0
    rng: np.random.Generator = field(init=False)
    _ar: NDArray[np.float64] = field(init=False)
    _gain: NDArray[np.float64] = field(init=False)
    _phase: NDArray[np.float64] = field(init=False)
    _cues: list[int] = field(default_factory=list)
    _env: NDArray[np.float64] = field(init=False)

    def __post_init__(self) -> None:
        self.rng = np.random.default_rng(self.seed)
        n = len(CHANNELS)
        self._ar = np.zeros(n)
        self._gain = np.ones(n)
        self._phase = self.rng.uniform(0, 2 * np.pi, n)
        self._env = np.ones(n)

    def cue_at(self, sample: int) -> int:
        k = int(sample // round(self.cue_s * self.fs))
        while len(self._cues) <= k:
            self._cues.extend(int(c) for c in self.rng.permutation(3))
        return self._cues[k]

    def _target_env(self, cue: int) -> NDArray[np.float64]:
        env = np.ones(len(CHANNELS))
        side = RIGHT_SIDE if cue == 1 else LEFT_SIDE if cue == 2 else {}
        for name, w in side.items():
            env[CHANNELS.index(name)] = 1.0 - (1.0 - self.erd) * w
        return env

    def chunk(self, n: int) -> tuple[NDArray[np.float64], list[int], list[tuple[int, int]]]:
        nch = len(CHANNELS)
        out = np.zeros((n, nch))
        labels: list[int] = []
        onsets: list[tuple[int, int]] = []
        cue_len = round(self.cue_s * self.fs)
        alpha_env = 1.0 - np.exp(-1.0 / (0.3 * self.fs))  # ~300 ms ERD onset / recovery
        alpha_gain = 1.0 - np.exp(-1.0 / (1.5 * self.fs))  # slow amplitude wander
        w = 2 * np.pi * self.mu_hz / self.fs
        white = self.rng.normal(0.0, 1.0, (n, nch))
        drive = self.rng.normal(0.0, 1.0, (n, nch))
        wander = self.rng.normal(0.0, 1.0, (n, nch))
        for i in range(n):
            s = self.sample + i
            cue = self.cue_at(s)
            if s % cue_len == 0:
                onsets.append((i, cue))
            labels.append(cue)
            self._env += alpha_env * (self._target_env(cue) - self._env)
            self._gain += alpha_gain * (1.0 - self._gain) + 0.02 * wander[i]
            self._gain = np.clip(self._gain, 0.4, 1.8)
            self._ar = 0.97 * self._ar + drive[i]
            self._phase += w + 0.05 * self.rng.normal(0.0, 1.0, nch)
            mu = self.mu_uv * self._gain * self._env * np.sin(self._phase)
            out[i] = mu + 0.6 * self._ar + self.noise_uv * white[i]
        self.sample += n
        return out, labels, onsets


def mi_descriptor(
    device_id: str = "test-mi", *, signal: bool = True, behavior: bool = True, fs: float = 250.0
) -> DeviceDescriptor:
    caps = [CapabilityDescriptor(capability=Capability.DEVICE_STATUS)]
    if signal or behavior:  # markers are recording.annotation (recording capability)
        params: dict[str, int | float | str | bool | list[str]] = {}
        if signal:
            params = {
                "sample_rate_hz": fs,
                "channel_count": len(CHANNELS),
                "unit": "uV",
                "channel_labels": list(CHANNELS),
            }
        caps.append(CapabilityDescriptor(capability=Capability.RECORDING, params=params))
    if behavior:
        caps.append(
            CapabilityDescriptor(
                capability=Capability.BEHAVIOR,
                params={
                    "dims": ["cue_class"],
                    "quantity": "cue_class",
                    "class_names": CLASS_NAMES,
                },
            )
        )
    return DeviceDescriptor(
        device_id=device_id,
        display_name="Test motor-imagery EEG (synthetic)",
        kind=DeviceKind.SIMULATED,
        adapter=ADAPTER,
        native_format="python arrays (test generator)",
        capabilities=caps,
        synthetic=True,
    )


class MotorImageryAdapter(DeviceAdapter):
    """Paced in real time x ``speed``. Receive-only like every adapter."""

    origin = ORIGIN

    def __init__(
        self,
        *,
        device_id: str = "test-mi",
        speed: float = 10.0,
        chunk: int = 25,
        seed: int = 0,
        signal: bool = True,
        behavior: bool = True,
    ) -> None:
        self.descriptor = mi_descriptor(device_id, signal=signal, behavior=behavior)
        self.gen = MotorImageryGenerator(seed=seed)
        self.speed, self.n = speed, chunk
        self.signal, self.behavior = signal, behavior
        self._t0: float | None = None
        self._k = 0
        self.paused = False
        self.stalled = False  # test hook: stop producing data (link stays up)
        self.fail_reads = 0  # test hook: the next N reads lose the link

    async def open(self) -> None:
        self._t0 = time.monotonic()
        self._k = 0

    async def close(self) -> None:
        self._t0 = None

    def set_paused(self, paused: bool) -> None:
        self.paused = paused

    async def read(self) -> NativePacket:
        assert self._t0 is not None
        if self.fail_reads > 0:
            self.fail_reads -= 1
            raise DeviceLinkError("test: link lost")
        while self.stalled:
            await asyncio.sleep(0.01)
            self._t0 = time.monotonic() - self._k * self.n / self.gen.fs / self.speed
        due = self._t0 + (self._k + 1) * self.n / self.gen.fs / self.speed
        delay = due - time.monotonic()
        await asyncio.sleep(max(0.0, delay))
        start = self.gen.sample
        data, labels, onsets = self.gen.chunk(self.n)
        self._k += 1
        return NativePacket((start, data, labels, onsets))

    def normalize(self, packet: NativePacket) -> Sequence[EventDraft]:
        start, data, labels, onsets = packet.data
        fs = self.gen.fs
        q = Quality(score=1.0, flags=[QualityFlag.SYNTHETIC])

        def prov(kind: ProvenanceKind) -> Provenance:
            return Provenance(kind=kind, adapter=ADAPTER, synthetic=True, origin=ORIGIN)

        def ts(sample: int) -> int:
            return round(sample / fs * 1e9)

        out: list[EventDraft] = []
        if self.signal:
            out.append(
                EventDraft(
                    EventType.RECORDING_FRAME,
                    {
                        "sample_rate_hz": fs,
                        "channel_count": data.shape[1],
                        "first_sample_index": start,
                        "unit": "uV",
                        "samples": data.T.tolist(),
                    },
                    q,
                    prov(ProvenanceKind.RAW_SIGNAL),
                    ts(start),
                )
            )
        if self.behavior:
            for j in (self.n // 2 - 1, self.n - 1):  # two labels per 100 ms chunk
                out.append(
                    EventDraft(
                        EventType.BEHAVIOR_SAMPLE,
                        {
                            "quantity": "cue_class",
                            "dims": ["cue_class"],
                            "unit": "class",
                            "values": [float(labels[j])],
                            "sample_index": start + j,
                            "valid": True,
                        },
                        q,
                        prov(ProvenanceKind.BEHAVIORAL_LABEL),
                        ts(start + j),
                    )
                )
        for j, cue in onsets:
            out.append(
                EventDraft(
                    EventType.RECORDING_ANNOTATION,
                    {"label": f"cue {CLASS_NAMES[cue]}", "value": cue, "duration_ms": None},
                    q,
                    prov(ProvenanceKind.BEHAVIORAL_LABEL),
                    ts(start + j),
                )
            )
        return out


def offline_features(
    seconds: float, *, seed: int = 0, bin_ms: float = 200.0
) -> tuple[NDArray[np.float64], NDArray[np.float64]]:
    """Log mu-band power per bin (the pipeline's band_power preset) + the cue per bin end."""
    from brainos.processing import ProcessingSpec, SignalChain

    gen = MotorImageryGenerator(seed=seed)
    chain = SignalChain(
        ProcessingSpec(preset="band_power", band_low_hz=8, band_high_hz=13, bin_ms=bin_ms),
        gen.fs,
        len(CHANNELS),
        "uV",
    )
    feats: list[NDArray[np.float64]] = []
    labels: list[float] = []
    lab_all: list[int] = []
    total = int(seconds * gen.fs)
    while gen.sample < total:
        p0 = chain.processed
        data, lab, _ = gen.chunk(25)
        lab_all.extend(lab)
        for f in chain.push(data):
            feats.append(f.values)
            labels.append(float(lab_all[f.end_sample - 1]))
        del p0
    return np.vstack(feats), np.asarray(labels)


def train_offline_lda(models_dir: Path, *, seconds: float = 240.0, seed: int = 11) -> Any:
    """An LDA on separately generated synthetic data, saved to ``models_dir`` (test helper)."""
    from brainos.decoding.lda import fit_lda

    x, y = offline_features(seconds, seed=seed)
    m = fit_lda(
        x,
        y,
        np.ones(len(y), dtype=bool),
        class_values=[0.0, 1.0, 2.0],
        class_names=CLASS_NAMES,
        bin_ms=200.0,
        tau_ms=500.0,
        space="classes_cue_class",
        training={"note": "synthetic test data (tests/mi_source.py)"},
        input_spec={
            "event_type": "features.vector",
            "feature": "log_band_power",
            "bin_ms": 200.0,
            "channel_count": len(CHANNELS),
            "channel_labels": list(CHANNELS),
        },
        source={"identity": ORIGIN},
    )
    m.save(models_dir / f"{m.model_id}.json")
    return m
