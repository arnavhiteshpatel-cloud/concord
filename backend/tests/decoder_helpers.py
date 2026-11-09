"""Helpers for decoder tests: a deterministic feature source, test decoder plugins, models.

``FeatureSource`` is a test adapter (declared SYNTHETIC) that emits per bin: one or more
neural feature streams (with channel labels), optionally a behavior sample and optionally a
source decoder's output (for decoded passthrough). It waits for ``release`` before emitting,
so a test can start the pipeline first and then compare every bin.
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

from concord.adapters.base import DeviceAdapter, EndOfStream, EventDraft, NativePacket
from concord.contracts.capabilities import Capability, CapabilityDescriptor, EventType
from concord.contracts.events import Provenance, ProvenanceKind, Quality, QualityFlag
from concord.contracts.protocol import DeviceDescriptor, DeviceKind, Modality

DECODERS_DIR = Path(__file__).parent / "decoders"
ADAPTER = "test.features@0.1.0"
ORIGIN = "test:feature-source"
BIN_MS = 20.0


@dataclass
class Stream:
    event_type: str  # features.binned | features.vector
    feature: str
    values: np.ndarray  # (bins, channels)
    labels: list[str] | None = None
    unit: str | None = None


@dataclass
class SourceDecoder:
    model_id: str
    dims: list[str]
    values: np.ndarray  # (bins, dims)
    quantity: str = "velocity"
    unit: str = "workspace/s"
    model_origin: str | None = "historical"
    y_axis: str | None = None
    scale: list[float] | None = None


@dataclass
class FeatureSource(DeviceAdapter):
    device_id: str = "test-features"
    streams: list[Stream] = field(default_factory=list)
    behavior: np.ndarray | None = None  # (bins, dims)
    behavior_dims: list[str] = field(default_factory=lambda: ["vx", "vy"])
    behavior_params: dict[str, Any] = field(default_factory=dict)
    decoders: list[SourceDecoder] = field(default_factory=list)
    modality: Modality | None = Modality.INTRACORTICAL
    origin: str = ORIGIN
    replayed: bool = False
    bins_per_read: int = 5
    drop: set[tuple[int, int]] = field(default_factory=set)  # (stream index, bin) not sent
    release: asyncio.Event = field(default_factory=asyncio.Event)
    end: bool = False  # True: EndOfStream after the last bin (the runtime then stops the pipeline)

    def __post_init__(self) -> None:
        self.i = 0
        caps: list[CapabilityDescriptor] = [
            CapabilityDescriptor(capability=Capability.DEVICE_STATUS)
        ]
        if self.streams:
            s0 = self.streams[0]
            params: dict[str, Any] = {
                "feature": s0.feature,
                "bin_ms": BIN_MS,
                "channel_count": s0.values.shape[1],
                "rate_hz": 1000.0 / BIN_MS,
            }
            if s0.labels:
                params["channel_labels"] = s0.labels
            if s0.unit:
                params["unit"] = s0.unit
            if len(self.streams) > 1:
                params["streams"] = [
                    {
                        "event_type": s.event_type,
                        "feature": s.feature,
                        "bin_ms": BIN_MS,
                        "channel_count": int(s.values.shape[1]),
                        "channel_labels": s.labels or [],
                        "unit": s.unit or "",
                    }
                    for s in self.streams
                ]
            caps.append(CapabilityDescriptor(capability=Capability.NEURAL_FEATURES, params=params))
        if self.behavior is not None:
            caps.append(
                CapabilityDescriptor(
                    capability=Capability.BEHAVIOR,
                    params={"dims": self.behavior_dims, **self.behavior_params},
                )
            )
        if self.decoders:
            caps.append(
                CapabilityDescriptor(
                    capability=Capability.KINEMATIC_INTENT,
                    params={
                        "decoders": [
                            {
                                k: v
                                for k, v in {
                                    "model_id": d.model_id,
                                    "dims": d.dims,
                                    "quantity": d.quantity,
                                    "unit": d.unit,
                                    "space": "test_space",
                                    "model_origin": d.model_origin,
                                    "y_axis": d.y_axis,
                                    "scale": d.scale,
                                }.items()
                                if v is not None
                            }
                            for d in self.decoders
                        ]
                    },
                )
            )
        self.descriptor = DeviceDescriptor(
            device_id=self.device_id,
            display_name="Test feature source (synthetic)",
            kind=DeviceKind.REPLAY if self.replayed else DeviceKind.SIMULATED,
            adapter=ADAPTER,
            native_format="python arrays",
            capabilities=caps,
            synthetic=not self.replayed,
            modality=self.modality,
        )

    @property
    def n(self) -> int:
        if self.streams:
            return len(self.streams[0].values)
        if self.decoders:
            return len(self.decoders[0].values)
        return len(self.behavior) if self.behavior is not None else 0

    async def open(self) -> None:
        return None

    async def close(self) -> None:
        return None

    def set_paused(self, paused: bool) -> None:
        return None

    async def read(self) -> NativePacket:
        await self.release.wait()
        await asyncio.sleep(0)
        if self.i >= self.n:
            if self.end:
                raise EndOfStream("done")
            await asyncio.sleep(3600)
        start, self.i = self.i, min(self.n, self.i + self.bins_per_read)
        return NativePacket(range(start, self.i))

    def _prov(self, kind: ProvenanceKind, **kw: Any) -> Provenance:
        return Provenance(
            kind=kind,
            adapter=ADAPTER,
            synthetic=not self.replayed,
            origin=self.origin,
            replayed=self.replayed,
            **kw,
        )

    def normalize(self, packet: NativePacket) -> Sequence[EventDraft]:
        flags = [QualityFlag.REPLAYED] if self.replayed else [QualityFlag.SYNTHETIC]
        q = Quality(score=1.0, flags=flags)
        out: list[EventDraft] = []
        for b in packet.data:
            ts = (b + 1) * round(BIN_MS * 1e6)
            for k, s in enumerate(self.streams):
                if (k, b) in self.drop:
                    continue
                row = s.values[b]
                if s.event_type == "features.binned":
                    payload: dict[str, Any] = {
                        "feature": s.feature,
                        "unit": "count",
                        "bin_ms": BIN_MS,
                        "bin_index": b,
                        "channel_count": len(row),
                        "counts": [int(v) for v in row],
                    }
                    et = EventType.FEATURES_BINNED
                else:
                    payload = {
                        "feature": s.feature,
                        "unit": s.unit or "arbitrary",
                        "band_hz": None,
                        "bin_ms": BIN_MS,
                        "bin_index": b,
                        "channel_count": len(row),
                        "values": [float(v) for v in row],
                    }
                    et = EventType.FEATURES_VECTOR
                out.append(
                    EventDraft(et, payload, q, self._prov(ProvenanceKind.PROCESSED_FEATURE), ts)
                )
            if self.behavior is not None:
                out.append(
                    EventDraft(
                        EventType.BEHAVIOR_SAMPLE,
                        {
                            "quantity": "velocity",
                            "dims": self.behavior_dims,
                            "unit": "workspace/s",
                            "values": [float(v) for v in self.behavior[b]],
                            "sample_index": b,
                            "valid": True,
                        },
                        q,
                        self._prov(ProvenanceKind.BEHAVIORAL_LABEL),
                        ts,
                    )
                )
            for d in self.decoders:
                out.append(
                    EventDraft(
                        EventType.INTENT_KINEMATICS,
                        {
                            "quantity": d.quantity,
                            "dims": d.dims,
                            "unit": d.unit,
                            "values": [float(v) for v in d.values[b]],
                            "space": "test_space",
                        },
                        q,
                        self._prov(
                            ProvenanceKind.DECODED_INTENT,
                            model_id=d.model_id,
                            model_origin=d.model_origin,
                        ),
                        ts,
                    )
                )
        return out


def tuned_data(
    n: int, channels: int, seed: int = 0, dims: int = 2
) -> tuple[np.ndarray, np.ndarray]:
    """Synthetic Poisson counts cosine-tuned to a smooth latent velocity (decodable)."""
    rng = np.random.default_rng(seed)
    t = np.arange(n) * BIN_MS / 1000.0
    vel = np.stack([np.sin(2 * np.pi * 0.23 * t + k) for k in range(dims)], axis=1)
    tuning = rng.standard_normal((dims, channels))
    rate = np.exp(1.0 + 0.6 * vel @ tuning)
    counts = rng.poisson(rate).astype(np.float64)
    return counts, vel


def plugin_env(site: Path) -> list[str]:
    """extra sys.path entries for decoder hosts: a fake site with entry points + decoders."""
    return [str(site), str(DECODERS_DIR)]


def make_decoder_dist(
    site: Path, entries: dict[str, str], name: str = "concord-test-decoders"
) -> Path:
    info = site / f"{name.replace('-', '_')}-0.0.1.dist-info"
    info.mkdir(parents=True, exist_ok=True)
    (info / "METADATA").write_text(
        f"Metadata-Version: 2.1\nName: {name}\nVersion: 0.0.1\n", encoding="utf-8"
    )
    lines = ["[concord.decoders]", *(f"{k} = {v}" for k, v in entries.items())]
    (info / "entry_points.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return site


def host_pythonpath() -> str:
    return os.pathsep.join([str(DECODERS_DIR), os.environ.get("PYTHONPATH", "")])
