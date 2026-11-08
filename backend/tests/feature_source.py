"""In-test synthetic binned-feature source (SYNTHETIC — not neural data).

Emits ``features.binned`` spike counts whose Poisson rates are cosine-tuned to a smooth latent
2-D velocity, plus that velocity as ``behavior.sample`` on the same device clock, faster than
real time (``speed``). Enough to calibrate a ridge decoder end to end in a test, and to run
the passthrough pipeline with a model so recordings contain real pipeline decoder output.
"""

from __future__ import annotations

import asyncio
import math
from collections.abc import Sequence
from typing import Any

import numpy as np

from brainos.adapters.base import DeviceAdapter, EventDraft, NativePacket
from brainos.contracts.capabilities import Capability, CapabilityDescriptor, EventType
from brainos.contracts.events import Provenance, ProvenanceKind, Quality, QualityFlag
from brainos.contracts.protocol import DeviceDescriptor, DeviceKind

ADAPTER = "test.features@0.1.0"
ORIGIN = "brainos:test-features"
CHANNELS = 12
BIN_MS = 20.0
BINS_PER_READ = 10


def feature_descriptor(device_id: str = "test-features") -> DeviceDescriptor:
    return DeviceDescriptor(
        device_id=device_id,
        display_name="Test binned features (synthetic)",
        kind=DeviceKind.SIMULATED,
        adapter=ADAPTER,
        native_format="python arrays (test generator)",
        capabilities=[
            CapabilityDescriptor(capability=Capability.DEVICE_STATUS),
            CapabilityDescriptor(
                capability=Capability.NEURAL_FEATURES,
                params={"feature": "spike_count", "bin_ms": BIN_MS, "channel_count": CHANNELS},
            ),
            CapabilityDescriptor(
                capability=Capability.BEHAVIOR,
                params={"dims": ["vx", "vy"], "quantity": "velocity", "unit": "arbitrary"},
            ),
        ],
        synthetic=True,
    )


class FeatureSourceAdapter(DeviceAdapter):
    def __init__(self, device_id: str = "test-features", *, speed: float = 50.0, seed: int = 5):
        self.descriptor = feature_descriptor(device_id)
        self.origin = ORIGIN  # stream identity: models calibrated on it are compatible
        self.speed = speed
        self.rng = np.random.default_rng(seed)
        self.prefs = self.rng.uniform(0, 2 * math.pi, CHANNELS)
        self.bin = 0
        self.v = np.zeros(2)
        self.paused = False

    async def open(self) -> None:
        return None

    async def close(self) -> None:
        return None

    def set_paused(self, paused: bool) -> None:
        self.paused = paused

    async def read(self) -> NativePacket:
        await asyncio.sleep(BINS_PER_READ * BIN_MS / 1000 / self.speed)
        out: list[tuple[int, list[int], list[float]]] = []
        for _ in range(BINS_PER_READ):
            self.v = 0.95 * self.v + self.rng.normal(0, 0.3, 2)
            speed = float(np.hypot(*self.v))
            angle = math.atan2(self.v[1], self.v[0])
            rates = np.exp(0.5 + 0.8 * speed * np.cos(angle - self.prefs) / 2.0)
            counts = self.rng.poisson(rates).astype(int).tolist()
            out.append((self.bin, counts, [float(self.v[0]), float(self.v[1])]))
            self.bin += 1
        return NativePacket(out)

    def normalize(self, packet: NativePacket) -> Sequence[EventDraft]:
        q = Quality(score=1.0, flags=[QualityFlag.SYNTHETIC])
        drafts: list[EventDraft] = []
        data: list[tuple[int, list[int], list[float]]] = packet.data
        for i, counts, v in data:
            ts = int(i * BIN_MS * 1e6)
            feat: dict[str, Any] = {
                "feature": "spike_count",
                "unit": "count",
                "bin_ms": BIN_MS,
                "bin_index": i,
                "channel_count": CHANNELS,
                "counts": counts,
            }
            beh: dict[str, Any] = {
                "quantity": "velocity",
                "dims": ["vx", "vy"],
                "unit": "arbitrary",
                "values": v,
                "sample_index": i,
                "valid": True,
            }
            drafts.append(
                EventDraft(
                    EventType.FEATURES_BINNED,
                    feat,
                    q,
                    self._prov(ProvenanceKind.PROCESSED_FEATURE),
                    ts,
                )
            )
            drafts.append(
                EventDraft(
                    EventType.BEHAVIOR_SAMPLE,
                    beh,
                    q,
                    self._prov(ProvenanceKind.BEHAVIORAL_LABEL),
                    ts,
                )
            )
        return drafts

    @staticmethod
    def _prov(kind: ProvenanceKind) -> Provenance:
        return Provenance(kind=kind, adapter=ADAPTER, synthetic=True, origin=ORIGIN)
