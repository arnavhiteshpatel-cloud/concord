"""Simulated Profile B — low-bandwidth discrete interface (synthetic).

Not a model of any commercial device. Native format is newline-delimited JSON
with terse vendor-style keys:

    {"ts_ms": <device ms since power-on>, "k": <kind>, "d": <data>}

    k="eeg": d = {"i": first_sample_index, "x": [[ch0...], [ch1...], ...]}  (µV, 1 dp)
    k="sel": d = {"p": confidence_percent}
    k="txt": d = {"c": character(s), "p": confidence_percent}
    k="tel": d = {"bat": percent, "tmp": celsius, "rssi": dBm}

No continuous pointer channel exists on this profile.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from typing import Any

from concord.adapters.base import EventDraft, NativePacket, PacketDecodeError
from concord.adapters.simulated.base import SimulatedAdapter
from concord.adapters.simulated.intent_source import DiscreteIntent, OperatorIntentSource
from concord.adapters.simulated.signal import SyntheticSignal
from concord.contracts.capabilities import Capability, CapabilityDescriptor, EventType
from concord.contracts.events import Provenance, ProvenanceKind, Quality, QualityFlag
from concord.contracts.protocol import DeviceDescriptor, DeviceKind

DEVICE_ID = "sim-b"
ADAPTER_NAME = "concord.sim.profile_b"

CHANNELS = 8
SAMPLE_RATE_HZ = 250.0
FRAME_SAMPLES = 25  # -> 10 frames/s
TELEMETRY_PERIOD_S = 5.0
RSSI_MIN, RSSI_MAX = -90.0, -40.0
MAX_TEXT = 64


def descriptor() -> DeviceDescriptor:
    return DeviceDescriptor(
        device_id=DEVICE_ID,
        display_name="Simulated Profile B",
        kind=DeviceKind.SIMULATED,
        adapter=f"{ADAPTER_NAME}@{SimulatedAdapter.ADAPTER_VERSION}",
        description=(
            "Synthetic low-bandwidth interface: sparse recording, discrete selection and "
            "character-level text intent, no continuous pointer. Not a model of any "
            "commercial device."
        ),
        native_format="newline-delimited JSON ({ts_ms, k, d})",
        synthetic=True,
        capabilities=[
            CapabilityDescriptor(
                capability=Capability.RECORDING,
                params={
                    "channel_count": CHANNELS,
                    "sample_rate_hz": SAMPLE_RATE_HZ,
                    "frame_samples": FRAME_SAMPLES,
                    "frame_rate_hz": SAMPLE_RATE_HZ / FRAME_SAMPLES,
                    "unit": "uV",
                },
                description="Synthetic signal (noise + sinusoids); not physiological.",
            ),
            CapabilityDescriptor(capability=Capability.SELECTION, params={"latency_ms": 150}),
            CapabilityDescriptor(
                capability=Capability.TEXT_INTENT,
                params={"text_modes": ["character"], "latency_ms": 150},
            ),
            CapabilityDescriptor(
                capability=Capability.TELEMETRY, params={"rate_hz": 1.0 / TELEMETRY_PERIOD_S}
            ),
            CapabilityDescriptor(capability=Capability.DEVICE_STATUS),
        ],
    )


def _line(ts_ms: int, kind: str, data: dict[str, Any]) -> bytes:
    return (
        json.dumps({"ts_ms": ts_ms, "k": kind, "d": data}, separators=(",", ":")) + "\n"
    ).encode()


class ProfileBAdapter(SimulatedAdapter):
    DISCRETE_LATENCY_S = 0.15

    def __init__(self, intents: OperatorIntentSource, *, seed: int | None = None) -> None:
        self.descriptor = descriptor()
        self._signal = SyntheticSignal(CHANNELS, SAMPLE_RATE_HZ, noise_uv=12.0, seed=seed)
        self._battery = 91.0
        super().__init__(intents, seed=seed)
        adapter = self.descriptor.adapter
        self._prov_sig = Provenance(
            kind=ProvenanceKind.RAW_SIGNAL,
            adapter=adapter,
            synthetic=True,
            origin="synthetic_signal",
        )
        self._prov_int = Provenance(
            kind=ProvenanceKind.SIMULATED_INTENT, adapter=adapter, synthetic=True, origin="operator"
        )
        self._prov_dev = Provenance(
            kind=ProvenanceKind.DEVICE_REPORT, adapter=adapter, synthetic=True, origin="device"
        )

    # ---------------------------------------------------------- device side (wire)
    def stream_periods(self) -> dict[str, float]:
        return {"eeg": FRAME_SAMPLES / SAMPLE_RATE_HZ, "tel": TELEMETRY_PERIOD_S}

    def produce(self, stream: str, clock_us: int) -> list[Any]:
        ts_ms = clock_us // 1000
        if stream == "eeg":
            first, samples = self._signal.frame(FRAME_SAMPLES)
            x = [[round(v, 1) for v in ch] for ch in samples]
            return [_line(ts_ms, "eeg", {"i": first, "x": x})]
        if stream == "tel":
            self._battery = max(0.0, self._battery - 0.05)
            return [
                _line(
                    ts_ms,
                    "tel",
                    {
                        "bat": round(self._battery, 2),
                        "tmp": round(36.9 + self._rng.gauss(0.0, 0.05), 2),
                        "rssi": round(self._rng.uniform(-70.0, -50.0), 1),
                    },
                )
            ]
        raise ValueError(f"unknown stream {stream}")

    def encode_discrete(self, intent: DiscreteIntent, clock_us: int) -> Any | None:
        p = int(self._rng.uniform(70, 95))
        ts_ms = clock_us // 1000
        if intent.kind == "select":
            return _line(ts_ms, "sel", {"p": p})
        return _line(ts_ms, "txt", {"c": intent.text[:MAX_TEXT], "p": p})

    def malformed(self, clock_us: int) -> Any:
        return b'{"ts_ms":' + str(clock_us // 1000).encode() + b',"k":"sel","d":{"p":'

    # ------------------------------------------------------ normalization (pure)
    def normalize(self, packet: NativePacket) -> Sequence[EventDraft]:
        raw = packet.data
        if not isinstance(raw, bytes | bytearray):
            raise PacketDecodeError(f"expected bytes, got {type(raw).__name__}")
        try:
            msg = json.loads(raw)
            ts_ms = msg["ts_ms"]
            kind = msg["k"]
            data = msg["d"]
            if not isinstance(ts_ms, int) or ts_ms < 0 or not isinstance(data, dict):
                raise TypeError("bad ts_ms/d")
            return [self._decode(kind, data, ts_ms * 1_000_000)]
        except PacketDecodeError:
            raise
        except (ValueError, KeyError, TypeError) as exc:
            raise PacketDecodeError(f"malformed JSON line: {exc}") from exc

    def _decode(self, kind: str, d: dict[str, Any], ts_ns: int) -> EventDraft:
        base_q = Quality(score=0.9, flags=[QualityFlag.SYNTHETIC])
        if kind == "eeg":
            x = d["x"]
            if not isinstance(x, list):
                raise TypeError("x must be a list")
            return EventDraft(
                EventType.RECORDING_FRAME,
                {
                    "sample_rate_hz": SAMPLE_RATE_HZ,
                    "channel_count": len(x),
                    "first_sample_index": int(d["i"]),
                    "unit": "uV",
                    "samples": x,
                },
                base_q,
                self._prov_sig,
                ts_ns,
            )
        if kind == "sel":
            return EventDraft(
                EventType.INTENT_SELECTION,
                {"action": "primary", "confidence": float(d["p"]) / 100},
                base_q,
                self._prov_int,
                ts_ns,
            )
        if kind == "txt":
            return EventDraft(
                EventType.INTENT_TEXT,
                {
                    "text": str(d["c"]),
                    "mode": "character" if len(d["c"]) == 1 else "word",
                    "confidence": float(d["p"]) / 100,
                },
                base_q,
                self._prov_int,
                ts_ns,
            )
        if kind == "tel":
            rssi = float(d["rssi"])
            link = (min(max(rssi, RSSI_MIN), RSSI_MAX) - RSSI_MIN) / (RSSI_MAX - RSSI_MIN)
            flags = [QualityFlag.SYNTHETIC]
            if link < 0.3:
                flags.append(QualityFlag.LOW_LINK_QUALITY)
            return EventDraft(
                EventType.TELEMETRY_SAMPLE,
                {
                    "metrics": [
                        {"name": "battery_pct", "value": float(d["bat"]), "unit": "%"},
                        {"name": "temperature_c", "value": float(d["tmp"]), "unit": "C"},
                        {"name": "rssi_dbm", "value": rssi, "unit": "dBm"},
                        {"name": "link_quality", "value": round(link, 3), "unit": ""},
                    ]
                },
                Quality(score=round(0.5 + 0.5 * link, 3), flags=flags),
                self._prov_dev,
                ts_ns,
            )
        raise PacketDecodeError(f"unknown packet kind {kind!r}")
