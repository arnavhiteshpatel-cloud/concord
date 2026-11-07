"""Open Ephys ZMQ Interface adapter (M3-AT-5, M3-AT-6).

Protocol facts are from the plugin source ``open-ephys-plugins/zmq-interface@38513917``.
Adapter tests run over real ZMQ sockets against :class:`OpenEphysTestPublisher` (a
protocol-faithful stand-in, *not* Open Ephys). The conformance test runs the plugin's
official Python client (downloaded at test time, never committed: it is GPL-3) against
the same publisher.
"""

from __future__ import annotations

import asyncio
import hashlib
import importlib.util
import json
import re
import socket
import sys
import time
import types
from collections.abc import AsyncIterator, Iterator, Sequence
from pathlib import Path
from typing import Any

import httpx
import numpy as np
import pytest

from brainos.adapters.base import DeviceLinkError, EventDraft, NativePacket, PacketDecodeError
from brainos.adapters.openephys import (
    ADAPTER,
    ConfigurationChangedError,
    OpenEphysAdapter,
    OpenEphysConfig,
)
from brainos.adapters.openephys.assembly import (
    BinSpec,
    BlockAssembler,
    Counters,
    FrameChunk,
    StreamLayout,
)
from brainos.adapters.openephys.protocol import (
    BAD_JSON_REPLY,
    ENVELOPE_DATA,
    ENVELOPE_EVENT,
    EVENT_REPLY,
    HEARTBEAT_REPLY,
    DataMessage,
    EventMessage,
    SpikeMessage,
    encode_data,
    encode_event,
    encode_spike,
    encode_ttl_payload,
    heartbeat_reply,
    juce_json,
    parse_message,
)
from brainos.adapters.openephys.publisher import OpenEphysTestPublisher, ramp_signal
from brainos.contracts.capabilities import Capability, capability_for
from brainos.contracts.events import SCHEMA_VERSION, parse_envelope
from brainos.contracts.protocol import DeviceKind

RATE = 30_000.0
BLOCK = 300  # 10 ms blocks keep the tests fast
CHANNELS = (0, 2, 5)  # a non-contiguous user selection


# ---------------------------------------------------------------------------- helpers


def _bindable(port: int) -> bool:
    with socket.socket() as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            s.bind(("127.0.0.1", port))
        except OSError:
            return False
        return True


def free_port_pair() -> int:
    """A free port p with p+1 also free (data + heartbeat); never the default 5556."""
    for _ in range(100):
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            p: int = s.getsockname()[1]
        if p < 65534 and p not in (5555, 5556, 5557) and _bindable(p) and _bindable(p + 1):
            return p
    raise RuntimeError("no free port pair")


def config(port: int, **kw: Any) -> OpenEphysConfig:
    base: dict[str, Any] = {
        "data_port": port,
        "open_timeout_s": 3.0,
        "learn_s": 0.05,
        "stall_timeout_s": 1.0,
        "heartbeat_interval_s": 0.2,
        "heartbeat_timeout_s": 0.3,
    }
    base.update(kw)
    return OpenEphysConfig(**base)


def envelope(draft: EventDraft, device_id: str) -> dict[str, Any]:
    """Validate a draft exactly like the runtime does; returns the JSON-mode envelope."""
    env = parse_envelope(
        {
            "schema_version": SCHEMA_VERSION,
            "session_id": "ses_abcdef12",
            "device_id": device_id,
            "seq": 0,
            "timestamp_ns": time.time_ns(),
            "device_timestamp_ns": draft.device_timestamp_ns,
            "event_type": draft.event_type,
            "capability": capability_for(draft.event_type),
            "payload": draft.payload,
            "quality": draft.quality,
            "provenance": draft.provenance,
        }
    )
    out: dict[str, Any] = env.model_dump(mode="json")
    return out


async def collect(
    adapter: OpenEphysAdapter, *, frames: int, timeout: float = 5.0
) -> list[dict[str, Any]]:
    """Read until ``frames`` recording.frame events were produced; returns envelopes."""
    out: list[dict[str, Any]] = []
    n = 0
    deadline = time.monotonic() + timeout
    while n < frames:
        assert time.monotonic() < deadline, "timed out collecting frames"
        packet = await adapter.read()
        for d in adapter.normalize(packet):
            ev = envelope(d, adapter.device_id)
            out.append(ev)
            n += ev["event_type"] == "recording.frame"
    return out


def of(events: list[dict[str, Any]], et: str) -> list[dict[str, Any]]:
    return [e for e in events if e["event_type"] == et]


@pytest.fixture
def port() -> int:
    return free_port_pair()


@pytest.fixture
def publisher(port: int) -> Iterator[OpenEphysTestPublisher]:
    pub = OpenEphysTestPublisher(
        data_port=port, sample_rate=RATE, channels=CHANNELS, block_size=BLOCK
    ).start()
    yield pub
    pub.stop()
    assert pub.error is None


@pytest.fixture
async def adapter(port: int, publisher: OpenEphysTestPublisher) -> AsyncIterator[OpenEphysAdapter]:
    a = OpenEphysAdapter(config(port))
    await a.open()
    yield a
    await a.close()


# --------------------------------------------------------------------------- protocol


def test_encode_data_is_byte_exact_juce_format() -> None:
    """M3-AT-5: header bytes as JUCE JSON::toString writes the plugin's DynamicObject."""
    frames = encode_data(
        message_num=7,
        stream="example_data",
        channel_num=2,
        channel_name="CH3",
        sample_num=1024,
        sample_rate=30000.0,
        samples=np.array([1.5, -2.25], dtype=np.float32),
        timestamp_ms=1700000000123,
    )
    expected_header = (
        b"{\r\n"
        b'  "message_num": 7,\r\n'
        b'  "type": "data",\r\n'
        b'  "content": {\r\n'
        b'    "stream": "example_data",\r\n'
        b'    "channel_num": 2,\r\n'
        b'    "channel_name": "CH3",\r\n'
        b'    "num_samples": 2,\r\n'
        b'    "sample_num": 1024,\r\n'
        b'    "sample_rate": 30000.0\r\n'
        b"  },\r\n"
        b'  "data_size": 8,\r\n'
        b'  "timestamp": 1700000000123\r\n'
        b"}"
    )
    assert frames == [b"DATA\x00", expected_header, np.array([1.5, -2.25], "<f4").tobytes()]


def test_juce_json_numbers_and_arrays() -> None:
    assert juce_json(-50.0) == "-50.0"
    assert juce_json(float(np.float32(-48.7))) == "-48.700000762939453"
    assert juce_json([]) == "[]"
    assert juce_json([1.0, 2]) == "[\r\n  1.0,\r\n  2\r\n]"
    assert juce_json({"a": 'x"\n'}) == '{\r\n  "a": "x\\"\\n"\r\n}'


def test_parse_round_trip_data() -> None:
    samples = np.arange(5, dtype=np.float32) * 0.5 - 1
    msg = parse_message(
        encode_data(
            message_num=1,
            stream="s",
            channel_num=9,
            channel_name="AP10",
            sample_num=2**40,
            sample_rate=2500.0,
            samples=samples,
            timestamp_ms=5,
        )
    )
    assert isinstance(msg, DataMessage)
    assert (msg.message_num, msg.stream, msg.channel_num, msg.channel_name) == (1, "s", 9, "AP10")
    assert (msg.num_samples, msg.sample_num, msg.sample_rate, msg.timestamp_ms) == (
        5,
        2**40,
        2500.0,
        5,
    )
    assert np.array_equal(msg.samples(), samples)


def test_parse_round_trip_ttl_and_payloadless_event() -> None:
    ttl = parse_message(
        encode_event(
            message_num=3,
            stream="s",
            source_node=104,
            event_type=3,
            sample_num=77,
            payload=encode_ttl_payload(4, 1, 2**63 + 5),
            timestamp_ms=1,
        )
    )
    assert isinstance(ttl, EventMessage) and ttl.is_ttl
    assert ttl.ttl is not None
    assert (ttl.ttl.line, ttl.ttl.state, ttl.ttl.word) == (4, 1, 2**63 + 5)
    assert (ttl.source_node, ttl.sample_num) == (104, 77)
    frames = encode_event(
        message_num=4,
        stream="s",
        source_node=1,
        event_type=5,
        sample_num=0,
        payload=b"",
        timestamp_ms=1,
    )
    assert len(frames) == 2  # data_size 0: header only, like the plugin
    ev = parse_message(frames)
    assert isinstance(ev, EventMessage) and not ev.is_ttl and ev.ttl is None


def test_parse_round_trip_spike() -> None:
    wf = np.arange(8, dtype=np.float32).reshape(2, 4)
    frames = encode_spike(
        message_num=9,
        stream="s",
        source_node=105,
        electrode="Stereotrode 1",
        sample_num=1234,
        sorted_id=2,
        threshold=[-40.0, -41.5],
        waveform=wf,
        timestamp_ms=1,
    )
    header = json.loads(frames[1])
    assert "spike" in header and "content" not in header and "data_size" not in header
    msg = parse_message(frames)
    assert isinstance(msg, SpikeMessage)
    assert (msg.electrode, msg.sample_num, msg.num_channels, msg.num_samples) == (
        "Stereotrode 1",
        1234,
        2,
        4,
    )
    assert msg.threshold == (-40.0, -41.5) and msg.sorted_id == 2
    assert np.array_equal(msg.waveform(), wf)


def _data(**overrides: Any) -> list[bytes]:
    frames = encode_data(
        message_num=1,
        stream="s",
        channel_num=0,
        channel_name="CH1",
        sample_num=0,
        sample_rate=1000.0,
        samples=np.zeros(4, np.float32),
        timestamp_ms=1,
    )
    header = json.loads(frames[1])
    for key, value in overrides.items():
        target = header["content"] if key in header["content"] else header
        if value is _DELETE:
            del target[key]
        else:
            target[key] = value
    return [frames[0], json.dumps(header).encode(), frames[2]]


_DELETE = object()
_GOOD_SPIKE = encode_spike(
    message_num=1,
    stream="s",
    source_node=1,
    electrode="E",
    sample_num=1,
    sorted_id=0,
    threshold=[-1.0],
    waveform=np.zeros((1, 3)),
    timestamp_ms=1,
)
_GOOD_TTL = encode_event(
    message_num=1,
    stream="s",
    source_node=1,
    event_type=3,
    sample_num=1,
    payload=encode_ttl_payload(1, 1, 1),
    timestamp_ms=1,
)


def _spike_header(**overrides: Any) -> list[bytes]:
    h = json.loads(_GOOD_SPIKE[1])
    h["spike"].update(overrides)
    return [_GOOD_SPIKE[0], json.dumps(h).encode(), _GOOD_SPIKE[2]]


MALFORMED: dict[str, tuple[list[bytes], str]] = {
    "one frame": ([ENVELOPE_DATA], "expected 2 or 3 frames"),
    "four frames": ([*_data(), b""], "expected 2 or 3 frames"),
    "envelope without NUL": ([b"DATA", *_data()[1:]], "missing its NUL"),
    "unknown envelope": ([b"FOO\x00", *_data()[1:]], "unknown envelope"),
    "non-utf8 header": ([ENVELOPE_DATA, b"\xff\xfe{", b""], "not valid UTF-8"),
    "invalid json": ([ENVELOPE_DATA, b"{not json", b""], "not valid JSON"),
    "header not object": ([ENVELOPE_DATA, b"[1]", b""], "must be a JSON object"),
    "missing message_num": (_data(message_num=_DELETE), "missing field 'message_num'"),
    "message_num string": (_data(message_num="1"), "'message_num' must be an integer"),
    "message_num bool": (_data(message_num=True), "'message_num' must be an integer"),
    "missing timestamp": (_data(timestamp=_DELETE), "missing field 'timestamp'"),
    "missing content": (_data(content=_DELETE), "missing field 'content'"),
    "negative num_samples": (_data(num_samples=-4, data_size=-16), "'num_samples' must be >= 0"),
    "negative sample_num": (_data(sample_num=-1), "'sample_num' must be >= 0"),
    "sample_rate string": (_data(sample_rate="1000"), "must be a number"),
    "sample_rate zero": (_data(sample_rate=0), "must be > 0"),
    "data_size vs num_samples": (_data(data_size=12), "data_size 12 != num_samples*4"),
    "binary length": (_data(num_samples=5, data_size=20), "payload has 16 bytes"),
    "data with two frames": (_data()[:2], "must have 3 frames"),
    "DATA envelope, event type": (_data(type="event"), "expected 'data'"),
    "EVENT envelope, data type": ([ENVELOPE_EVENT, *_data()[1:]], "unknown type 'data'"),
    "TTL payload too short": (
        [_GOOD_TTL[0], _GOOD_TTL[1].replace(b'"data_size": 10', b'"data_size": 3'), b"abc"],
        "TTL payload has 3 bytes",
    ),
    "event data_size>0 but two frames": (_GOOD_TTL[:2], "must have 3 frames"),
    "event data_size mismatch": ([*_GOOD_TTL[:2], b"x" * 11], "event payload has 11 bytes"),
    "event data_size 0 with payload": (
        [_GOOD_TTL[0], _GOOD_TTL[1].replace(b'"data_size": 10', b'"data_size": 0'), b"x"],
        "must have 2 frames",
    ),
    "spike waveform length": ([*_GOOD_SPIKE[:2], b"\x00" * 8], "spike waveform has 8 bytes"),
    "spike thresholds": (_spike_header(threshold=[-1.0, -2.0]), "2 thresholds for num_channels=1"),
    "spike negative channels": (_spike_header(num_channels=-1), "'num_channels' must be >= 0"),
    "spike under content": (
        [
            _GOOD_SPIKE[0],
            _GOOD_SPIKE[1].replace(b'"spike":', b'"content":'),
            _GOOD_SPIKE[2],
        ],
        "uses 'content'",
    ),
}


@pytest.mark.parametrize("case", sorted(MALFORMED))
def test_malformed_messages_rejected(case: str) -> None:
    """M3-AT-6: every malformed shape raises PacketDecodeError with a specific reason."""
    frames, reason = MALFORMED[case]
    with pytest.raises(PacketDecodeError, match=re.escape(reason)):
        parse_message(frames)


def test_heartbeat_replies_match_plugin() -> None:
    hb = json.dumps({"application": "x", "uuid": "u", "type": "heartbeat"}).encode()
    assert heartbeat_reply(hb) == HEARTBEAT_REPLY == b"heartbeat received"
    assert heartbeat_reply(b'{"type": "event", "event": {}}') == EVENT_REPLY
    assert heartbeat_reply(b"nope") == BAD_JSON_REPLY == b"JSON message could not be read"


# -------------------------------------------------------------------------- assembler


def _msg(ch: int, sample: int, n: int = 4, num: int = 1) -> DataMessage:
    data = (np.arange(n, dtype=np.float32) + sample + ch * 100).tobytes()
    return DataMessage(num, 0, "s", ch, f"CH{ch + 1}", n, sample, 1000.0, data)


def test_assembler_never_fabricates_missing_channel() -> None:
    counters = Counters()
    layout = StreamLayout("s", 1000.0, ((0, "CH1"), (1, "CH2")), 4)
    asm = BlockAssembler(layout, counters, max_frame_samples=10_000)
    out = asm.on_data(_msg(0, 0)) + asm.on_data(_msg(1, 0))
    assert [type(i) for i in out] == [FrameChunk]
    assert asm.on_data(_msg(0, 4)) == []  # channel 1 of block 4 is lost
    out = asm.on_data(_msg(0, 8)) + asm.on_data(_msg(1, 8))
    frames = [i for i in out if isinstance(i, FrameChunk)]
    assert len(frames) == 1 and frames[0].first_sample_index == 8 and frames[0].dropped_before
    assert counters.incomplete_blocks == 1
    assert counters.discarded_samples == 4  # channel 0's samples of the incomplete block
    assert counters.missing_samples == 4  # channel 1: 4..8 never arrived
    with pytest.raises(ConfigurationChangedError, match="missing from 3 consecutive"):
        for s in (12, 16, 20, 24):
            asm.on_data(_msg(0, s))


def test_bin_spec_is_exact_on_the_sample_clock() -> None:
    b = BinSpec.create(20.0, 30_000.0)
    assert (b.num, b.den) == (600, 1)
    assert b.index(599) == 0 and b.index(600) == 1
    assert b.first_starting_at_or_after(1) == 1 and b.first_starting_at_or_after(600) == 1
    odd = BinSpec.create(20.0, 44_100.0)  # 882 samples
    assert odd.index(881) == 0 and odd.index(882) == 1


# ------------------------------------------------------------------- adapter + publisher


async def test_learns_layout_and_descriptor(adapter: OpenEphysAdapter, port: int) -> None:
    d = adapter.descriptor
    assert d.device_id == f"openephys:127.0.0.1:{port}"
    assert d.kind is DeviceKind.STREAM and d.synthetic is False and d.adapter == ADAPTER
    assert "cannot verify" in d.description
    rec = next(c for c in d.capabilities if c.capability is Capability.RECORDING)
    assert rec.params["channel_count"] == 3
    assert rec.params["sample_rate_hz"] == RATE
    assert rec.params["channel_names"] == ["CH1", "CH3", "CH6"]
    assert rec.params["stream"] == "example_data"
    assert rec.params["frame_samples"] == BLOCK
    assert rec.params["unit"] == "arbitrary"
    assert not d.supports(Capability.NEURAL_FEATURES)
    meta = adapter.source_metadata()
    json.dumps(meta)
    assert meta["channels"] == [
        {"index": 0, "channel_num": 0, "name": "CH1"},
        {"index": 1, "channel_num": 2, "name": "CH3"},
        {"index": 2, "channel_num": 5, "name": "CH6"},
    ]
    assert meta["unit_note"] == "units not transmitted by the protocol"
    assert meta["plugin_protocol_reference"] == "zmq-interface@38513917"
    assert adapter.origin == f"openephys:127.0.0.1:{port}/example_data"


async def test_frames_unknown_unit_are_unscaled_and_continuous(
    adapter: OpenEphysAdapter, port: int
) -> None:
    events = await collect(adapter, frames=6)
    frames = of(events, "recording.frame")
    first = frames[0]["payload"]["first_sample_index"]
    for k, ev in enumerate(frames):
        p = ev["payload"]
        assert p["unit"] == "arbitrary" and p["channel_count"] == 3
        assert p["first_sample_index"] == first + k * BLOCK  # sample_num continuity
        expected = np.asarray(ramp_signal(p["first_sample_index"], BLOCK, CHANNELS))
        assert p["samples"] == expected.astype(np.float64).tolist()  # bit-exact float32 values
        assert ev["device_timestamp_ns"] == round(p["first_sample_index"] * 1e9 / RATE)
        assert ev["quality"] == {"score": 1.0, "flags": []}
        assert ev["provenance"]["kind"] == "raw_signal"
        assert ev["provenance"]["synthetic"] is False
        assert ev["provenance"]["origin"] == f"openephys:127.0.0.1:{port}/example_data"
    assert adapter.counters.missed_messages == 0
    assert adapter.counters.incomplete_blocks == 0


@pytest.mark.parametrize(("unit", "scale"), [("uV", 1.0), ("mV", 1e3), ("V", 1e6)])
async def test_known_units_are_converted_exactly(
    port: int, publisher: OpenEphysTestPublisher, unit: str, scale: float
) -> None:
    a = OpenEphysAdapter(config(port, unit=unit))
    await a.open()
    try:
        rec = next(c for c in a.descriptor.capabilities if c.capability is Capability.RECORDING)
        assert rec.params["unit"] == "uV" and rec.params["source_unit"] == unit
        frames = of(await collect(a, frames=2), "recording.frame")
        for ev in frames:
            p = ev["payload"]
            assert p["unit"] == "uV"
            raw = np.asarray(ramp_signal(p["first_sample_index"], BLOCK, CHANNELS))
            assert p["samples"] == (raw.astype(np.float64) * scale).tolist()
    finally:
        await a.close()


async def test_message_num_gap_and_lost_block_are_counted(
    adapter: OpenEphysAdapter, publisher: OpenEphysTestPublisher
) -> None:
    before = of(await collect(adapter, frames=2), "recording.frame")
    publisher.drop_messages(len(CHANNELS))  # one whole block lost in transit
    frames = before + of(await collect(adapter, frames=4), "recording.frame")
    assert adapter.counters.missed_messages == len(CHANNELS)
    assert adapter.counters.missing_samples == len(CHANNELS) * BLOCK
    flagged = [f for f in frames if f["quality"]["flags"] == ["dropped_samples"]]
    assert len(flagged) == 1
    idx = frames.index(flagged[0])
    assert idx > 0
    gap = (
        flagged[0]["payload"]["first_sample_index"]
        - frames[idx - 1]["payload"]["first_sample_index"]
    )
    assert gap == 2 * BLOCK  # the lost block is absent, never fabricated


async def test_dropped_channel_block_is_discarded_counted_and_flagged(
    adapter: OpenEphysAdapter, publisher: OpenEphysTestPublisher
) -> None:
    await collect(adapter, frames=2)
    publisher.drop_channel_blocks(2, 1)
    frames = of(await collect(adapter, frames=4), "recording.frame")
    c = adapter.counters
    assert c.missed_messages == 1
    assert c.incomplete_blocks == 1
    assert c.discarded_samples == 2 * BLOCK  # the two channels that did arrive
    assert c.missing_samples == BLOCK  # channel 2's samples
    flagged = [f for f in frames if "dropped_samples" in f["quality"]["flags"]]
    assert len(flagged) == 1 and flagged[0]["quality"]["score"] < 1.0
    for f in frames:
        assert f["payload"]["channel_count"] == 3


async def test_ttl_events_become_annotations(
    adapter: OpenEphysAdapter, publisher: OpenEphysTestPublisher
) -> None:
    await collect(adapter, frames=1)
    publisher.send_ttl(3, 1, 0xDEADBEEF, offset=17)
    publisher.send_ttl(3, 0, 0, offset=BLOCK - 1)
    events = await collect(adapter, frames=4)
    anns = of(events, "recording.annotation")
    sent = [s for s in publisher.sent_log if s[0] == "ttl"]
    assert len(anns) == 2
    for ann, (_, sample, detail) in zip(anns, sent, strict=True):
        assert ann["payload"] == {"label": "ttl", "value": detail, "duration_ms": None}
        assert ann["device_timestamp_ns"] == round(sample * 1e9 / RATE)
        assert ann["provenance"]["kind"] == "behavioral_label"
    assert anns[0]["payload"]["value"] == f"line=3 state=1 word={0xDEADBEEF}"
    ts = [e["device_timestamp_ns"] for e in events]
    assert ts == sorted(ts)  # never a timestamp regression


async def test_spikes_are_binned_on_the_sample_clock(
    port: int, publisher: OpenEphysTestPublisher
) -> None:
    a = OpenEphysAdapter(config(port, spike_electrodes=["E1", "E2"]))
    await a.open()
    try:
        feat = next(
            c for c in a.descriptor.capabilities if c.capability is Capability.NEURAL_FEATURES
        )
        assert feat.params["channel_names"] == ["E1", "E2"]
        await collect(a, frames=1)
        for e, off in [("E1", 3), ("E2", 4), ("E1", 250), ("E1", 299), ("E2", 0)]:
            publisher.send_spike(e, offset=off)
        await asyncio.sleep(0.05)
        publisher.send_spike("E2", offset=150)
        events = await collect(a, frames=12)
        bins = of(events, "features.binned")
        assert bins
        expected: dict[int, list[int]] = {}
        for kind, sample, electrode in publisher.sent_log:
            assert kind == "spike"
            expected.setdefault(sample // 600, [0, 0])[["E1", "E2"].index(electrode)] += 1
        got = {b["payload"]["bin_index"]: b["payload"]["counts"] for b in bins}
        indices = sorted(got)
        assert indices == list(range(indices[0], indices[0] + len(indices)))  # contiguous
        assert set(expected) <= set(got)
        for i, counts in got.items():
            assert counts == expected.get(i, [0, 0])
        for b in bins:
            p = b["payload"]
            assert p["feature"] == "spike_count" and p["bin_ms"] == 20.0
            assert b["device_timestamp_ns"] == (p["bin_index"] + 1) * 20_000_000
            assert b["provenance"]["kind"] == "processed_feature"
        assert a.counters.spikes_binned == 6
        ts = [e["device_timestamp_ns"] for e in events]
        assert ts == sorted(ts)
    finally:
        await a.close()


async def test_learned_electrodes_and_new_electrode_reconnect(
    port: int, publisher: OpenEphysTestPublisher
) -> None:
    async def spikes() -> None:
        while True:
            publisher.send_spike("tetrode A", offset=10)
            await asyncio.sleep(0.01)

    task = asyncio.create_task(spikes())
    a = OpenEphysAdapter(config(port, learn_s=0.2))
    try:
        await a.open()
        feat = next(
            c for c in a.descriptor.capabilities if c.capability is Capability.NEURAL_FEATURES
        )
        assert feat.params["channel_names"] == ["tetrode A"]
        await collect(a, frames=2)
        publisher.send_spike("tetrode B", offset=5)
        with pytest.raises(ConfigurationChangedError, match="new spike electrode 'tetrode B'"):
            await collect(a, frames=50)
        await a.close()
        await a.open()  # what the runtime does on DeviceLinkError
        feat = next(
            c for c in a.descriptor.capabilities if c.capability is Capability.NEURAL_FEATURES
        )
        assert feat.params["channel_names"] == ["tetrode A", "tetrode B"]
    finally:
        task.cancel()
        await a.close()


@pytest.mark.parametrize("change", ["channels", "sample_rate", "restart"])
async def test_configuration_change_raises_link_error(
    adapter: OpenEphysAdapter, publisher: OpenEphysTestPublisher, change: str
) -> None:
    await collect(adapter, frames=2)
    if change == "channels":
        publisher.set_channels([0, 2, 6])
        match = "channel 6"
    elif change == "sample_rate":
        publisher.set_sample_rate(20_000.0)
        match = "sample rate"
    else:
        publisher.start_acquisition(reset=True)
        match = "acquisition restarted"
    with pytest.raises(DeviceLinkError, match=f"configuration changed: .*{match}"):
        await collect(adapter, frames=50)
    assert adapter.counters.config_changes == 1


async def test_deselected_channel_raises_after_three_blocks(
    adapter: OpenEphysAdapter, publisher: OpenEphysTestPublisher
) -> None:
    await collect(adapter, frames=1)
    publisher.set_channels([0, 2])
    with pytest.raises(ConfigurationChangedError, match=r"channel 5 .*missing from 3"):
        await collect(adapter, frames=50)


async def test_stall_raises_link_error(port: int, publisher: OpenEphysTestPublisher) -> None:
    a = OpenEphysAdapter(config(port, stall_timeout_s=0.3))
    await a.open()
    try:
        await collect(a, frames=1)
        publisher.stop_acquisition()
        t0 = time.monotonic()
        with pytest.raises(DeviceLinkError, match="no message from Open Ephys"):
            await collect(a, frames=10_000, timeout=10)
        assert time.monotonic() - t0 < 3
        assert a.counters.stalls == 1
    finally:
        await a.close()


async def test_open_timeout_without_plugin(port: int) -> None:
    a = OpenEphysAdapter(config(port, open_timeout_s=0.6, heartbeat_timeout_s=0.2))
    t0 = time.monotonic()
    with pytest.raises(DeviceLinkError, match="no reply from an Open Ephys ZMQ Interface"):
        await a.open()
    assert time.monotonic() - t0 < 2
    await a.close()


async def test_open_timeout_plugin_reachable_but_not_acquiring(port: int) -> None:
    pub = OpenEphysTestPublisher(data_port=port, acquiring=False).start()
    try:
        a = OpenEphysAdapter(config(port, open_timeout_s=0.8))
        with pytest.raises(
            DeviceLinkError, match=r"answered heartbeats.*acquisition is not running"
        ):
            await a.open()
        b = OpenEphysAdapter(config(port, open_timeout_s=0.4, heartbeat=False))
        with pytest.raises(DeviceLinkError, match="heartbeats disabled"):
            await b.open()
    finally:
        pub.stop()


async def test_heartbeat_registers_brainos_with_the_plugin(
    adapter: OpenEphysAdapter, publisher: OpenEphysTestPublisher
) -> None:
    deadline = time.monotonic() + 3
    while adapter.client_uuid not in publisher.clients:
        assert time.monotonic() < deadline
        await asyncio.sleep(0.02)
    rec = publisher.clients[adapter.client_uuid]
    assert rec.application == "BrainOS" and rec.heartbeats >= 1
    req = json.loads(publisher.requests[0])
    assert req == {"application": "BrainOS", "uuid": adapter.client_uuid, "type": "heartbeat"}
    while adapter.counters.heartbeat_replies < 1:
        assert time.monotonic() < deadline
        await asyncio.sleep(0.02)
    assert adapter.source_metadata()["heartbeat"]["status"] == "ok"
    assert adapter.source_metadata()["heartbeat"]["last_reply"] == "heartbeat received"


async def test_malformed_wire_message_is_rejected_and_counted(
    adapter: OpenEphysAdapter, publisher: OpenEphysTestPublisher
) -> None:
    await collect(adapter, frames=1)
    publisher.send_raw([b"DATA", b"{}", b""])
    deadline = time.monotonic() + 3
    while True:
        assert time.monotonic() < deadline
        packet = await adapter.read()
        try:
            adapter.normalize(packet)
        except PacketDecodeError as exc:
            assert "missing its NUL" in str(exc)
            break
    assert adapter.counters.malformed == 1
    await collect(adapter, frames=2)  # the stream continues


async def test_pause_drains_and_resumes_without_false_drops(adapter: OpenEphysAdapter) -> None:
    await collect(adapter, frames=1)
    adapter.set_paused(True)
    pending = asyncio.create_task(adapter.read())
    await asyncio.sleep(0.15)
    assert not pending.done()
    adapter.set_paused(False)
    packet = await asyncio.wait_for(pending, 3)
    assert adapter.counters.discarded_while_paused > 0
    frames = [d for d in adapter.normalize(packet) if d.event_type == "recording.frame"]
    assert frames and frames[0].quality.flags == []
    assert adapter.counters.incomplete_blocks == 0


def _plain(drafts: Any) -> list[Any]:
    return [
        (
            d.event_type,
            {k: v.tolist() if isinstance(v, np.ndarray) else v for k, v in d.payload.items()},
            d.quality,
            d.provenance,
            d.device_timestamp_ns,
        )
        for d in drafts
    ]


async def test_long_blocks_are_split_and_normalize_is_pure(
    port: int, publisher: OpenEphysTestPublisher
) -> None:
    a = OpenEphysAdapter(config(port, max_frame_samples=128))
    await a.open()
    try:
        packet: NativePacket = await a.read()
        drafts = a.normalize(packet)
        # pure: same packet, same drafts (frame samples are numpy arrays since M5-E)
        assert _plain(a.normalize(packet)) == _plain(drafts)
        frames = [d for d in drafts if d.event_type == "recording.frame"]
        assert [len(f.payload["samples"][0]) for f in frames] == [128, 128, 44]
        firsts = [f.payload["first_sample_index"] for f in frames]
        assert firsts == [firsts[0], firsts[0] + 128, firsts[0] + 256]
    finally:
        await a.close()


async def test_close_is_idempotent_and_reopen_works(adapter: OpenEphysAdapter) -> None:
    await collect(adapter, frames=1)
    await adapter.close()
    await adapter.close()
    with pytest.raises(DeviceLinkError, match="not open"):
        await adapter.read()
    await adapter.open()
    await collect(adapter, frames=1)
    assert adapter.counters.opens == 2


def test_config_rejects_bad_hosts() -> None:
    with pytest.raises(ValueError):
        OpenEphysConfig(host="tcp://evil:1")
    assert OpenEphysConfig(host="Rig-PC.local").host == "rig-pc.local"
    assert OpenEphysConfig().data_port == 5556


# ------------------------------------------------------- official client conformance

CLIENT_URL = (
    "https://raw.githubusercontent.com/open-ephys-plugins/zmq-interface/"
    "38513917d6a7ee5791a47029d624a1b6110b01ee/Resources/python_client/plot_process_zmq.py"
)
CLIENT_SHA256 = "136f21295f4e417e1eea9abd5514032041d5a063c3ea82b018cb48691f8a00a8"


def _load_official_client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> types.ModuleType:
    try:
        r = httpx.get(CLIENT_URL, timeout=20, follow_redirects=True)
        r.raise_for_status()
    except httpx.HTTPError as exc:
        pytest.skip(f"cannot download the official Open Ephys ZMQ client (no network?): {exc}")
    digest = hashlib.sha256(r.content).hexdigest()
    assert digest == CLIENT_SHA256, "downloaded client does not match the pinned commit"
    # GPL-3 file: lives only in tmp_path for this test, never in the repository.
    path = tmp_path / "plot_process_zmq.py"
    path.write_bytes(r.content)
    mpl = types.ModuleType("matplotlib")
    plt = types.ModuleType("matplotlib.pyplot")
    plt.close = lambda *a, **k: None  # type: ignore[attr-defined]
    mpl.pyplot = plt  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "matplotlib", mpl)
    monkeypatch.setitem(sys.modules, "matplotlib.pyplot", plt)
    spec = importlib.util.spec_from_file_location("oe_official_client", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _blocks_match(arrays: Sequence[np.ndarray], upto: int) -> int:
    """Index of the block start s0 such that arrays[k] == ramp(s0 + k*BLOCK) for channel 1."""
    for s0 in range(0, upto, BLOCK):
        if np.array_equal(arrays[0], np.asarray(ramp_signal(s0, BLOCK, (1,)))[0]):
            return s0
    raise AssertionError("first captured array matches no published block")


def test_official_client_parses_publisher(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """M3-AT-5: the plugin's own reference client parses our publisher identically."""
    if not (_bindable(5556) and _bindable(5557)):
        pytest.skip("the official client hard-codes ports 5556/5557, which are in use")
    client_mod = _load_official_client(tmp_path, monkeypatch)

    class Capture(client_mod.PlotProcess):  # type: ignore[name-defined,misc]
        def __init__(self) -> None:
            super().__init__()
            self.isTesting = False  # no random event requests
            self.arrays: list[np.ndarray] = []
            self.events: list[Any] = []
            self.spikes: list[Any] = []

        def update_plot(self, n_arr: np.ndarray) -> None:
            self.arrays.append(np.array(n_arr))

        def update_plot_event(self, event: Any) -> None:
            self.events.append(event)

        def update_plot_spike(self, spike: Any) -> None:
            self.spikes.append(spike)

    pub = OpenEphysTestPublisher(
        data_port=5556, sample_rate=RATE, channels=(0, 1, 2, 3), block_size=BLOCK
    ).start()
    client = Capture()
    try:
        deadline = time.monotonic() + 1.0
        while time.monotonic() < deadline:  # connect, let the subscription settle
            client.callback()
        wf = np.arange(80, dtype=np.float32).reshape(2, 40) - 40
        pub.send_ttl(5, 1, 2**40 + 7, offset=11)
        pub.send_spike("Stereotrode 1", offset=21, waveform=wf, threshold=[-30.0, -31.5])
        deadline = time.monotonic() + 1.0
        while time.monotonic() < deadline:
            client.callback()
    finally:
        client.context.destroy(linger=0)
        pub.stop()
    assert pub.error is None
    out = capsys.readouterr().out
    assert "missing a message" not in out
    assert "ValueError" not in out

    assert len(client.arrays) >= 20
    s0 = _blocks_match(client.arrays, pub.sample_num)
    for k, arr in enumerate(client.arrays):
        assert arr.dtype == np.float32
        assert np.array_equal(arr, np.asarray(ramp_signal(s0 + k * BLOCK, BLOCK, (1,)))[0])

    sent = {kind: (s, detail) for kind, s, detail in pub.sent_log}
    assert len(client.events) == 1
    ev = client.events[0]
    assert ev.type == "TTL" and ev.stream == "example_data"
    assert (int(ev.event_line), int(ev.event_state), int(ev.event_word)) == (5, 1, 2**40 + 7)
    assert ev.sample_num == sent["ttl"][0]
    assert len(client.spikes) == 1
    sp = client.spikes[0]
    assert (sp.electrode, sp.sample_num, sp.num_channels, sp.num_samples) == (
        "Stereotrode 1",
        sent["spike"][0],
        2,
        40,
    )
    assert sp.threshold == [-30.0, -31.5]
    assert np.array_equal(np.frombuffer(sp.data, np.float32).reshape(2, 40), wf)
    assert any(c.application == "Plot Process" for c in pub.clients.values())
    assert HEARTBEAT_REPLY in pub.replies
