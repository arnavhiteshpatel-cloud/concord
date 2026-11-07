"""Adapter contract and simulated profiles (AT-5..AT-8)."""

from __future__ import annotations

import asyncio
import inspect
import json
import struct
import time
import zlib
from collections import Counter

import pytest

from brainos.adapters.base import DeviceAdapter, DeviceLinkError, NativePacket, PacketDecodeError
from brainos.adapters.replay import ReplayAdapter
from brainos.adapters.simulated import (
    Fault,
    OperatorIntentSource,
    ProfileAAdapter,
    ProfileBAdapter,
)
from brainos.adapters.simulated import profile_a as pa
from brainos.contracts.capabilities import EVENT_CAPABILITY, Capability, EventType
from brainos.contracts.events import ProvenanceKind, QualityFlag


def _frame(ptype: int, payload: bytes, clock: int = 1234) -> bytes:
    return pa._frame(ptype, clock, payload)


# ------------------------------------------------------------------ Profile A (AT-5)


def test_profile_a_decodes_binary_frames(intents: OperatorIntentSource) -> None:
    """AT-5: well-formed binary frames decode to standard drafts."""
    a = ProfileAAdapter(intents, seed=1)
    (ptr,) = a.normalize(NativePacket(_frame(pa.T_PTR, struct.pack("<hh", 32767, -16384))))
    assert ptr.event_type is EventType.INTENT_POINTER
    assert ptr.payload == {"vx": 2.0, "vy": pytest.approx(-1.00003, abs=1e-4)}
    assert ptr.device_timestamp_ns == 1234 * 1000
    assert ptr.provenance.kind is ProvenanceKind.SIMULATED_INTENT
    assert QualityFlag.SYNTHETIC in ptr.quality.flags

    counts = list(range(2 * 3))
    rec_payload = struct.pack("<IHH", 40, 2, 3) + struct.pack("<6h", *counts)
    (rec,) = a.normalize(NativePacket(_frame(pa.T_REC, rec_payload)))
    assert rec.event_type is EventType.RECORDING_FRAME
    assert rec.payload["samples"] == [[0.0, 0.5, 1.0], [1.5, 2.0, 2.5]]
    assert rec.payload["first_sample_index"] == 40
    assert rec.provenance.kind is ProvenanceKind.RAW_SIGNAL

    (sel,) = a.normalize(NativePacket(_frame(pa.T_SEL, b"\xff")))
    assert sel.payload == {"action": "primary", "confidence": 1.0}


@pytest.mark.parametrize(
    ("case", "mutate"),
    [
        ("bad magic", lambda b: b"\x00\x00" + b[2:]),
        ("bad crc", lambda b: b[:-1] + bytes([b[-1] ^ 1])),
        ("truncated", lambda b: b[:10]),
        ("length mismatch", lambda b: b + b"\x00"),
        ("not bytes", lambda b: "string"),
        (
            "unknown type",
            lambda b: (lambda body: body + struct.pack("<I", zlib.crc32(body)))(
                pa.HEADER.pack(pa.MAGIC, 99, 0, 1, 0) + b"\x00"
            ),
        ),
        (
            "short payload with valid crc",
            lambda b: (lambda body: body + struct.pack("<I", zlib.crc32(body)))(
                pa.HEADER.pack(pa.MAGIC, pa.T_PTR, 0, 1, 0) + b"\x00"
            ),
        ),
    ],
)
def test_profile_a_rejects_corrupt_frames(intents: OperatorIntentSource, case: str, mutate) -> None:  # type: ignore[no-untyped-def]
    """AT-5: corrupt magic/length/CRC/payload raise PacketDecodeError."""
    a = ProfileAAdapter(intents, seed=1)
    good = _frame(pa.T_SEL, b"\x80")
    with pytest.raises(PacketDecodeError):
        a.normalize(NativePacket(mutate(good)))


# ------------------------------------------------------------------ Profile B (AT-6)


def test_profile_b_decodes_json_lines(intents: OperatorIntentSource) -> None:
    """AT-6: JSON-line packets decode to standard drafts."""
    b = ProfileBAdapter(intents, seed=1)
    (txt,) = b.normalize(NativePacket(b'{"ts_ms":5,"k":"txt","d":{"c":"h","p":80}}\n'))
    assert txt.event_type is EventType.INTENT_TEXT
    assert txt.payload == {"text": "h", "mode": "character", "confidence": 0.8}
    assert txt.device_timestamp_ns == 5_000_000
    (tel,) = b.normalize(
        NativePacket(b'{"ts_ms":5,"k":"tel","d":{"bat":50.5,"tmp":37.0,"rssi":-95}}')
    )
    names = {m["name"]: m["value"] for m in tel.payload["metrics"]}
    assert names["link_quality"] == 0.0
    assert QualityFlag.LOW_LINK_QUALITY in tel.quality.flags


@pytest.mark.parametrize(
    "raw",
    [
        b'{"ts_ms":1,"k":"sel","d":{"p":',  # truncated
        b"not json",
        b'{"k":"sel","d":{"p":50}}',  # missing ts
        b'{"ts_ms":-1,"k":"sel","d":{"p":50}}',  # negative clock
        b'{"ts_ms":1,"k":"sel","d":[]}',  # wrong d type
        b'{"ts_ms":1,"k":"sel","d":{}}',  # missing p
        b'{"ts_ms":1,"k":"zap","d":{}}',  # unknown kind
        b'{"ts_ms":1,"k":"eeg","d":{"i":0,"x":"nope"}}',
    ],
)
def test_profile_b_rejects_malformed_lines(intents: OperatorIntentSource, raw: bytes) -> None:
    """AT-6: malformed JSON lines raise PacketDecodeError."""
    with pytest.raises(PacketDecodeError):
        ProfileBAdapter(intents, seed=1).normalize(NativePacket(raw))


# ------------------------------------------------------------- rates & caps (AT-7)


async def _collect(adapter: DeviceAdapter, seconds: float) -> Counter[EventType]:
    await adapter.open()
    counts: Counter[EventType] = Counter()
    deadline = time.monotonic() + seconds
    try:
        while time.monotonic() < deadline:
            pkt = await asyncio.wait_for(adapter.read(), 2.0)
            for d in adapter.normalize(pkt):
                counts[d.event_type] += 1
    finally:
        await adapter.close()
    return counts


@pytest.mark.parametrize(
    ("cls", "expected_rates", "absent"),
    [
        (
            ProfileAAdapter,
            {EventType.RECORDING_FRAME: 25.0, EventType.INTENT_POINTER: 50.0},
            {EventType.INTENT_TEXT},
        ),
        (
            ProfileBAdapter,
            {EventType.RECORDING_FRAME: 10.0},
            {EventType.INTENT_POINTER},
        ),
    ],
)
async def test_profiles_emit_declared_capabilities_at_declared_rates(
    intents: OperatorIntentSource,
    cls: type[ProfileAAdapter] | type[ProfileBAdapter],
    expected_rates: dict[EventType, float],
    absent: set[EventType],
) -> None:
    """AT-7: only declared capabilities, at approximately declared rates (±30%)."""
    adapter = cls(intents, seed=1)
    window = 1.2
    counts = await _collect(adapter, window)
    declared = adapter.descriptor.capability_set
    for et in counts:
        assert EVENT_CAPABILITY[et] in declared, f"{et} emitted but not declared"
    for et, hz in expected_rates.items():
        measured = counts[et] / window
        assert 0.7 * hz <= measured <= 1.3 * hz, f"{et}: {measured:.1f} Hz vs {hz} Hz"
    for et in absent:
        assert counts[et] == 0


def test_profiles_differ_meaningfully(intents: OperatorIntentSource) -> None:
    a = ProfileAAdapter(intents).descriptor
    b = ProfileBAdapter(intents).descriptor
    assert a.supports(Capability.POINTER_INTENT) and not b.supports(Capability.POINTER_INTENT)
    assert b.supports(Capability.TEXT_INTENT) and not a.supports(Capability.TEXT_INTENT)
    assert a.synthetic and b.synthetic
    assert "commercial" in a.description and "commercial" in b.description


async def test_operator_intents_flow_through_profiles(intents: OperatorIntentSource) -> None:
    a = ProfileAAdapter(intents, seed=1)
    await a.open()
    intents.set_pointer(1.0, 0.0)
    intents.submit_select()
    seen: list[EventType] = []
    vx: list[float] = []
    for _ in range(40):
        for d in a.normalize(await asyncio.wait_for(a.read(), 1.0)):
            seen.append(d.event_type)
            if d.event_type is EventType.INTENT_POINTER:
                vx.append(d.payload["vx"])
    await a.close()
    assert EventType.INTENT_SELECTION in seen
    assert vx and sum(vx) / len(vx) > 1.5  # ~2.0 units/s minus noise


async def test_unsupported_intent_is_dropped_by_device(intents: OperatorIntentSource) -> None:
    a = ProfileAAdapter(intents, seed=1)
    assert a.encode_discrete(type("D", (), {"kind": "text", "text": "x"})(), 0) is None  # type: ignore[arg-type]


# --------------------------------------------------------------------- faults


async def test_link_drop_fault_is_recoverable(intents: OperatorIntentSource) -> None:
    b = ProfileBAdapter(intents, seed=1)
    await b.open()
    b.inject_fault(Fault.LINK_DROP)
    with pytest.raises(DeviceLinkError):
        await b.read()
    await b.open()
    assert await asyncio.wait_for(b.read(), 1.0)


async def test_link_fail_fault_is_not_recoverable(intents: OperatorIntentSource) -> None:
    b = ProfileBAdapter(intents, seed=1)
    await b.open()
    b.inject_fault(Fault.LINK_FAIL)
    with pytest.raises(DeviceLinkError):
        await b.read()
    with pytest.raises(DeviceLinkError):
        await b.open()


async def test_malformed_fault_produces_undecodable_packet(intents: OperatorIntentSource) -> None:
    for cls in (ProfileAAdapter, ProfileBAdapter):
        adapter = cls(intents, seed=1)
        await adapter.open()
        adapter.inject_fault(Fault.MALFORMED_PACKET)
        with pytest.raises(PacketDecodeError):
            adapter.normalize(await adapter.read())
        await adapter.close()


def test_profile_b_wire_format_is_json_lines(intents: OperatorIntentSource) -> None:
    b = ProfileBAdapter(intents, seed=1)
    (line,) = b.produce("tel", 2_000_000)
    assert line.endswith(b"\n")
    msg = json.loads(line)
    assert msg["ts_ms"] == 2000 and msg["k"] == "tel"


# ----------------------------------------------------------------- read-only (AT-8)

WRITE_WORDS = ("write", "send", "stim", "command", "transmit", "set_param", "configure")


@pytest.mark.parametrize("cls", [DeviceAdapter, ProfileAAdapter, ProfileBAdapter, ReplayAdapter])
def test_adapter_contract_has_no_write_path(cls: type) -> None:
    """AT-8: no adapter exposes a write/send/stimulate/command method."""
    names = [n for n, _ in inspect.getmembers(cls, callable) if not n.startswith("__")]
    offenders = [n for n in names if any(w in n.lower() for w in WRITE_WORDS)]
    assert offenders == []
    abstract = set(getattr(DeviceAdapter, "__abstractmethods__", set()))
    assert abstract == {"open", "close", "set_paused", "read", "normalize"}
