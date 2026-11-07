"""Simulated Profile A — high-bandwidth cortical array (synthetic).

Not a model of any commercial device. Native format is a little-endian binary
frame:

    offset size field
    0      2    magic   0xB7A5
    2      1    type    1=REC 2=PTR 3=SEL 4=TEL
    3      1    flags   bit0 = low link quality
    4      2    length  payload length in bytes
    6      8    clock   device clock, microseconds since power-on
    14     n    payload (type-specific, below)
    14+n   4    crc32   over bytes [0, 14+n)

    REC: u32 first_sample_index, u16 channels, u16 samples, i16[channels*samples]
         channel-major, 0.5 uV/count
    PTR: i16 vx, i16 vy   (±32767 = ±2.0 workspace units/s)
    SEL: u8 confidence    (0..255)
    TEL: u16 battery (0.1 %), i16 temperature (0.01 °C), u8 link quality (0..255),
         u32 packets sent
"""

from __future__ import annotations

import struct
import zlib
from array import array
from collections.abc import Sequence
from typing import Any

from brainos.adapters.base import EventDraft, NativePacket, PacketDecodeError
from brainos.adapters.simulated.base import SimulatedAdapter
from brainos.adapters.simulated.intent_source import DiscreteIntent, OperatorIntentSource
from brainos.adapters.simulated.signal import SyntheticSignal
from brainos.contracts.capabilities import Capability, CapabilityDescriptor, EventType
from brainos.contracts.events import Provenance, ProvenanceKind, Quality, QualityFlag
from brainos.contracts.protocol import DeviceDescriptor, DeviceKind

DEVICE_ID = "sim-a"
ADAPTER_NAME = "brainos.sim.profile_a"

MAGIC = 0xB7A5
HEADER = struct.Struct("<HBBHQ")  # magic, type, flags, length, clock_us
CRC = struct.Struct("<I")
T_REC, T_PTR, T_SEL, T_TEL = 1, 2, 3, 4
FLAG_LOW_LINK = 0x01

CHANNELS = 32
SAMPLE_RATE_HZ = 1000.0
FRAME_SAMPLES = 40  # -> 25 frames/s
UV_PER_COUNT = 0.5
POINTER_RATE_HZ = 50.0
POINTER_MAX_SPEED = 2.0
POINTER_NOISE = 0.01  # std of additive velocity noise, normalized units
TELEMETRY_RATE_HZ = 1.0

_REC_HEAD = struct.Struct("<IHH")
_PTR = struct.Struct("<hh")
_SEL = struct.Struct("<B")
_TEL = struct.Struct("<HhBI")


def _frame(ptype: int, clock_us: int, payload: bytes, flags: int = 0) -> bytes:
    head = HEADER.pack(MAGIC, ptype, flags, len(payload), clock_us)
    body = head + payload
    return body + CRC.pack(zlib.crc32(body))


def descriptor() -> DeviceDescriptor:
    return DeviceDescriptor(
        device_id=DEVICE_ID,
        display_name="Simulated Profile A",
        kind=DeviceKind.SIMULATED,
        adapter=f"{ADAPTER_NAME}@{SimulatedAdapter.ADAPTER_VERSION}",
        description=(
            "Synthetic high-bandwidth cortical-array-style interface: dense recording, "
            "continuous pointer intent, discrete selection. Not a model of any commercial device."
        ),
        native_format="binary frames (magic, type, flags, length, u64 µs clock, payload, CRC32)",
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
            CapabilityDescriptor(
                capability=Capability.POINTER_INTENT,
                params={"rate_hz": POINTER_RATE_HZ, "dims": 2, "max_speed": POINTER_MAX_SPEED},
                description="2-D velocity, int16-quantized, additive noise.",
            ),
            CapabilityDescriptor(
                capability=Capability.SELECTION,
                params={"latency_ms": 30},
            ),
            CapabilityDescriptor(
                capability=Capability.TELEMETRY,
                params={"rate_hz": TELEMETRY_RATE_HZ},
            ),
            CapabilityDescriptor(capability=Capability.DEVICE_STATUS),
        ],
    )


class ProfileAAdapter(SimulatedAdapter):
    DISCRETE_LATENCY_S = 0.03

    def __init__(self, intents: OperatorIntentSource, *, seed: int | None = None) -> None:
        self.descriptor = descriptor()
        self._signal = SyntheticSignal(CHANNELS, SAMPLE_RATE_HZ, seed=seed)
        self._battery = 98.0
        self._packets = 0
        super().__init__(intents, seed=seed)
        self._provenance_sig = self._prov(ProvenanceKind.RAW_SIGNAL, "synthetic_signal")
        self._provenance_int = self._prov(ProvenanceKind.SIMULATED_INTENT, "operator")
        self._provenance_dev = self._prov(ProvenanceKind.DEVICE_REPORT, "device")

    def _prov(self, kind: ProvenanceKind, origin: str) -> Provenance:
        return Provenance(kind=kind, adapter=self.descriptor.adapter, synthetic=True, origin=origin)

    # ---------------------------------------------------------- device side (wire)
    def stream_periods(self) -> dict[str, float]:
        return {
            "rec": FRAME_SAMPLES / SAMPLE_RATE_HZ,
            "ptr": 1.0 / POINTER_RATE_HZ,
            "tel": 1.0 / TELEMETRY_RATE_HZ,
        }

    def _flags(self) -> int:
        return FLAG_LOW_LINK if self._rng.random() < 0.02 else 0

    def produce(self, stream: str, clock_us: int) -> list[Any]:
        self._packets += 1
        if stream == "rec":
            first, samples = self._signal.frame(FRAME_SAMPLES)
            counts = array("h", (round(v / UV_PER_COUNT) for ch in samples for v in ch))
            payload = _REC_HEAD.pack(first, CHANNELS, FRAME_SAMPLES) + counts.tobytes()
            return [_frame(T_REC, clock_us, payload, self._flags())]
        if stream == "ptr":
            vx, vy = self._intents.pointer()
            q = []
            for v in (vx, vy):
                noisy = max(-1.0, min(1.0, v + self._rng.gauss(0.0, POINTER_NOISE)))
                q.append(round(noisy * 32767))
            return [_frame(T_PTR, clock_us, _PTR.pack(*q), self._flags())]
        if stream == "tel":
            self._battery = max(0.0, self._battery - 0.01)
            temp = 37.0 + self._rng.gauss(0.0, 0.05)
            link = int(self._rng.uniform(0.88, 1.0) * 255)
            payload = _TEL.pack(int(self._battery * 10), int(temp * 100), link, self._packets)
            return [_frame(T_TEL, clock_us, payload)]
        raise ValueError(f"unknown stream {stream}")

    def encode_discrete(self, intent: DiscreteIntent, clock_us: int) -> Any | None:
        if intent.kind != "select":
            return None  # Profile A has no text intent
        conf = int(self._rng.uniform(0.85, 0.99) * 255)
        return _frame(T_SEL, clock_us, _SEL.pack(conf))

    def malformed(self, clock_us: int) -> Any:
        good = bytearray(_frame(T_SEL, clock_us, _SEL.pack(200)))
        good[-1] ^= 0xFF  # corrupt CRC
        return bytes(good)

    # ------------------------------------------------------ normalization (pure)
    def normalize(self, packet: NativePacket) -> Sequence[EventDraft]:
        raw = packet.data
        if not isinstance(raw, bytes | bytearray):
            raise PacketDecodeError(f"expected bytes, got {type(raw).__name__}")
        if len(raw) < HEADER.size + CRC.size:
            raise PacketDecodeError(f"short frame ({len(raw)} bytes)")
        magic, ptype, flags, length, clock_us = HEADER.unpack_from(raw, 0)
        if magic != MAGIC:
            raise PacketDecodeError(f"bad magic 0x{magic:04X}")
        if len(raw) != HEADER.size + length + CRC.size:
            raise PacketDecodeError(f"length mismatch: header says {length}, frame is {len(raw)}")
        (crc,) = CRC.unpack_from(raw, HEADER.size + length)
        if zlib.crc32(raw[: HEADER.size + length]) != crc:
            raise PacketDecodeError("CRC mismatch")
        payload = bytes(raw[HEADER.size : HEADER.size + length])
        ts_ns = clock_us * 1000
        q_flags = [QualityFlag.SYNTHETIC]
        score = 0.97
        if flags & FLAG_LOW_LINK:
            q_flags.append(QualityFlag.LOW_LINK_QUALITY)
            score = 0.6
        quality = Quality(score=score, flags=q_flags)
        try:
            return [self._decode(ptype, payload, quality, ts_ns)]
        except struct.error as exc:
            raise PacketDecodeError(f"payload decode failed for type {ptype}: {exc}") from exc

    def _decode(self, ptype: int, payload: bytes, quality: Quality, ts_ns: int) -> EventDraft:
        if ptype == T_REC:
            first, nch, ns = _REC_HEAD.unpack_from(payload, 0)
            body = payload[_REC_HEAD.size :]
            if len(body) != nch * ns * 2:
                raise PacketDecodeError("REC sample block size mismatch")
            counts = array("h")
            counts.frombytes(body)
            samples = [
                [c * UV_PER_COUNT for c in counts[ch * ns : (ch + 1) * ns]] for ch in range(nch)
            ]
            return EventDraft(
                EventType.RECORDING_FRAME,
                {
                    "sample_rate_hz": SAMPLE_RATE_HZ,
                    "channel_count": nch,
                    "first_sample_index": first,
                    "unit": "uV",
                    "samples": samples,
                },
                quality,
                self._provenance_sig,
                ts_ns,
            )
        if ptype == T_PTR:
            qx, qy = _PTR.unpack(payload)
            return EventDraft(
                EventType.INTENT_POINTER,
                {
                    "vx": round(qx / 32767 * POINTER_MAX_SPEED, 5),
                    "vy": round(qy / 32767 * POINTER_MAX_SPEED, 5),
                },
                quality,
                self._provenance_int,
                ts_ns,
            )
        if ptype == T_SEL:
            (conf,) = _SEL.unpack(payload)
            return EventDraft(
                EventType.INTENT_SELECTION,
                {"action": "primary", "confidence": round(conf / 255, 3)},
                quality,
                self._provenance_int,
                ts_ns,
            )
        if ptype == T_TEL:
            bat, temp, link, sent = _TEL.unpack(payload)
            return EventDraft(
                EventType.TELEMETRY_SAMPLE,
                {
                    "metrics": [
                        {"name": "battery_pct", "value": bat / 10, "unit": "%"},
                        {"name": "temperature_c", "value": temp / 100, "unit": "C"},
                        {"name": "link_quality", "value": round(link / 255, 3), "unit": ""},
                        {"name": "packets_sent", "value": float(sent), "unit": ""},
                    ]
                },
                quality,
                self._provenance_dev,
                ts_ns,
            )
        raise PacketDecodeError(f"unknown packet type {ptype}")
