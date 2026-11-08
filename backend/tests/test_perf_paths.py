"""Milestone 5 (E) performance paths: correctness against the pre-M5 implementation.

* ``recording.frame`` samples may be a numpy array in-process: identical accept/reject
  decisions, errors, JSON text and JSON Schema as the ``list[list[float]]`` path.
* Envelope JSON is produced lazily and once (``bus.EventJson``), byte-identical to
  ``model_dump_json()`` with orjson and with the pure-Python fallback.
* Adapters emitting arrays produce the same events as the old ``tolist()`` drafts.
* Queues are bounded in memory, and the pump yields under backlog.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from pydantic import ValidationError

from brainos.adapters.base import DeviceAdapter, EndOfStream, EventDraft, NativePacket
from brainos.contracts.capabilities import Capability, EventType
from brainos.contracts.events import (
    SCHEMA_VERSION,
    Provenance,
    ProvenanceKind,
    Quality,
    QualityFlag,
    RecordingFramePayload,
    envelope_json_schema,
    parse_envelope,
)
from brainos.contracts.protocol import AppInfo
from brainos.runtime import DeviceRegistry, Recorder, Runtime, fastjson
from brainos.runtime.bus import EventBus, EventJson
from brainos.runtime.pipeline import QUEUE_MAX_VALUES, PipelineStartRequest

from .conftest import subscribe
from .helpers import drain, scripted_descriptor, wait_for

REPO = Path(__file__).resolve().parents[2]
RAW = Provenance(kind=ProvenanceKind.RAW_SIGNAL, adapter="t@0.0.1", synthetic=True, origin="t")
SYN = Quality(score=1.0, flags=[QualityFlag.SYNTHETIC])
EDGE = [0.1, 1e-5, 1e-7, 2.5e-5, 1e15, 1e16, 1e20, -0.0, 0.0, 100.0, 5e-324, 1.7976931348623157e308]


def frame(samples: Any, channels: int | None = None, **kw: Any) -> dict[str, Any]:
    n = channels if channels is not None else len(samples)
    return {
        "sample_rate_hz": 30000.0,
        "channel_count": n,
        "first_sample_index": 0,
        "unit": "uV",
        "samples": samples,
        **kw,
    }


def envelope(samples: Any, channels: int | None = None) -> Any:
    return parse_envelope(
        {
            "schema_version": SCHEMA_VERSION,
            "session_id": "ses_perftest1",
            "device_id": "perf",
            "seq": 7,
            "timestamp_ns": 1_700_000_000_000_000_000,
            "device_timestamp_ns": 42,
            "event_type": "recording.frame",
            "capability": "recording",
            "payload": frame(samples, channels),
            "quality": SYN,
            "provenance": RAW,
        }
    )


def rand(ch: int, n: int, dtype: Any = np.float32, seed: int = 0) -> np.ndarray[Any, Any]:
    return (np.random.default_rng(seed).standard_normal((ch, n)) * 50).astype(dtype)


# --------------------------------------------------------------------------- contract


@pytest.mark.parametrize("dtype", [np.float32, np.float64, np.int16, np.uint8, np.bool_])
def test_array_samples_equal_list_samples(dtype: Any) -> None:
    a = rand(4, 25, dtype)
    from_array = RecordingFramePayload.model_validate(frame(a))
    from_list = RecordingFramePayload.model_validate(frame(a.tolist()))
    assert isinstance(from_array.samples, np.ndarray)
    assert from_array.samples.dtype == np.float64 and from_array.samples.flags.c_contiguous
    assert from_array.model_dump_json() == from_list.model_dump_json()
    assert from_array.model_dump() == from_list.model_dump()
    assert from_array.model_dump(mode="json") == from_list.model_dump(mode="json")


def test_array_samples_are_an_owned_read_only_copy() -> None:
    a = rand(2, 5, np.float64)
    p = RecordingFramePayload.model_validate(frame(a))
    before = p.model_dump_json()
    a[:] = 0.0  # the producer reuses its buffer
    assert p.model_dump_json() == before
    with pytest.raises(ValueError):
        p.samples[0][0] = 1.0  # type: ignore[index]


@pytest.mark.parametrize(
    ("bad", "channels"),
    [
        (np.array([[1.0, np.nan]]), 1),
        (np.array([[1.0], [np.inf]]), 2),
        (np.array([[-np.inf]], dtype=np.float32), 1),
        (np.zeros((2, 3)), 1),  # channel count mismatch
        (np.zeros((1, 0)), 1),  # no samples
        (np.zeros((1, 10_001)), 1),  # too many samples
        (np.zeros(3), 3),  # 1-D
        (np.zeros((1, 2, 2)), 1),  # 3-D
        (np.array([[1 + 1j]]), 1),  # complex
        (np.array([["a"]]), 1),  # strings
        (np.array([[object()]], dtype=object), 1),
    ],
)
def test_malformed_arrays_are_rejected_exactly_like_lists(bad: Any, channels: int) -> None:
    with pytest.raises(ValidationError) as from_array:
        RecordingFramePayload.model_validate(frame(bad, channels))
    with pytest.raises(ValidationError) as from_list:
        RecordingFramePayload.model_validate(frame(bad.tolist(), channels))
    strip = [{k: e[k] for k in ("type", "loc", "msg")} for e in from_array.value.errors()]
    assert strip == [{k: e[k] for k in ("type", "loc", "msg")} for e in from_list.value.errors()]


def test_channel_count_limit_still_applies_to_arrays() -> None:
    with pytest.raises(ValidationError, match="less than or equal to 1024"):
        RecordingFramePayload.model_validate(frame(np.zeros((1025, 1))))


def test_json_schema_is_unchanged_by_the_array_path() -> None:
    committed = json.loads((REPO / "contracts" / "event-envelope.v1.schema.json").read_text())
    assert envelope_json_schema() == committed


# --------------------------------------------------------------------------- JSON


def _encoders() -> list[str]:
    return ["pydantic"] + (["orjson"] if fastjson._orjson_samples is not None else [])


@pytest.mark.parametrize("encoder", _encoders())
@pytest.mark.parametrize("dtype", [np.float32, np.float64, np.int16])
def test_envelope_json_is_byte_identical(
    encoder: str, dtype: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    if encoder == "pydantic":
        monkeypatch.setattr(fastjson, "_orjson_samples", None)
    a = rand(8, 40, dtype, seed=3)
    if dtype is np.float64:
        a[0, : len(EDGE)] = EDGE
    env_array, env_list = envelope(a), envelope(a.tolist())
    assert fastjson.envelope_json(env_array) == env_list.model_dump_json()
    assert env_array.model_dump_json() == env_list.model_dump_json()


@pytest.mark.parametrize("encoder", _encoders())
def test_edge_case_floats_serialize_identically(
    encoder: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    if encoder == "pydantic":
        monkeypatch.setattr(fastjson, "_orjson_samples", None)
    rng = np.random.default_rng(5)
    scales = 10.0 ** rng.integers(-300, 300, size=2000)
    values = np.concatenate([EDGE, rng.standard_normal(2000) * scales, -np.asarray(EDGE)])
    a = values.reshape(2, -1)
    assert fastjson.envelope_json(envelope(a)) == envelope(a.tolist()).model_dump_json()


def test_non_frame_envelopes_use_the_generic_serializer() -> None:
    env = parse_envelope(
        {
            "schema_version": SCHEMA_VERSION,
            "session_id": "ses_perftest1",
            "device_id": "perf",
            "seq": 1,
            "timestamp_ns": 5,
            "event_type": "telemetry.sample",
            "capability": "telemetry",
            "payload": {"metrics": [{"name": "x", "value": 0.1, "unit": ""}]},
            "quality": SYN,
            "provenance": Provenance(
                kind=ProvenanceKind.DEVICE_REPORT, adapter="t@0.0.1", synthetic=True, origin="t"
            ),
        }
    )
    assert fastjson.envelope_json(env) == env.model_dump_json()


# --------------------------------------------------------------------------- bus


def _bus_with(subs: int) -> tuple[EventBus, list[Any]]:
    from brainos.contracts.protocol import AppStatus, NegotiationResult
    from brainos.runtime.bus import Subscriber

    bus = EventBus()
    out = []
    for i in range(subs):
        neg = NegotiationResult(
            device_id="perf", status=AppStatus.ACTIVE, granted=[Capability.RECORDING], rejected=[]
        )
        s = Subscriber(f"c{i}", AppInfo(id=f"a{i}", name="a"), [], [Capability.RECORDING], neg)
        bus.add(s)
        out.append(s)
    return bus, out


async def test_json_is_lazy_shared_and_identical() -> None:
    bus, (s1, s2) = _bus_with(2)
    seen: list[str] = []
    blind: list[str] = []
    bus.add_tap(lambda _e, j: blind.append(j), json=False)
    env = envelope(rand(4, 10))
    bus.publish(env, Capability.RECORDING)
    item = s1._events[0][1]
    assert item is s2._events[0][1]  # one shared holder per envelope
    assert item._text is None  # nobody needed the text yet
    assert blind == [""]
    text1, _ = await s1.next_message()
    text2, _ = await s2.next_message()
    assert text1 == text2 == f'{{"type":"event","delivery_seq":0,"event":{env.model_dump_json()}}}'
    bus.add_tap(lambda _e, j: seen.append(j), when=lambda e: e.seq == 7)
    bus.publish(env, Capability.RECORDING)
    assert seen == [env.model_dump_json()]


async def test_subscriber_queue_is_bounded_in_bytes() -> None:
    bus, (s,) = _bus_with(1)
    s.max_queue_bytes = 3 * 8 * 64 * 100  # room for three 64 x 100 float64 frames
    for _ in range(10):
        bus.publish(envelope(rand(64, 100)), Capability.RECORDING)
    assert len(s._events) == 3 and s.dropped == 7
    assert [e[0] for e in s._events] == [7, 8, 9]  # oldest dropped; gap visible to the client
    msgs = [json.loads((await s.next_message())[0]) for _ in range(3)]
    assert [m["delivery_seq"] for m in msgs] == [7, 8, 9]
    assert s._queued_bytes == 0


async def test_count_bound_unchanged_for_small_events() -> None:
    bus, (s,) = _bus_with(1)
    s.max_queue = 5
    for _ in range(8):
        bus.publish(envelope(rand(1, 1)), Capability.RECORDING)
    assert len(s._events) == 5 and s.dropped == 3


async def test_prebuilt_json_strings_are_still_accepted() -> None:
    bus, (s,) = _bus_with(1)
    env = envelope(rand(2, 3))
    bus.publish(env, Capability.RECORDING, "{}")
    assert (await s.next_message())[0].endswith('"event":{}}')
    s.offer_event('{"a":1}')
    assert (await s.next_message())[0].endswith('"event":{"a":1}}')


# --------------------------------------------------------------------------- adapters


def _lsl_adapter(channels: int) -> Any:
    from brainos.adapters.lsl import LSLAdapter, LSLSourceSpec
    from brainos.adapters.lsl.metadata import ChannelMeta, Declaration, StreamMeta

    meta = StreamMeta(
        name="t",
        type="EEG",
        source_id="t",
        hostname="h",
        uid="u",
        channel_count=channels,
        nominal_srate=30000.0,
        channel_format="float32",
        created_at=0.0,
        channels=tuple(
            ChannelMeta(index=i, label=f"c{i}", unit="millivolts", type="EEG")
            for i in range(channels)
        ),
        declaration=Declaration(synthetic=True, origin="test"),
    )
    return LSLAdapter(LSLSourceSpec(device_id="lsl:t", signal=meta))


def _as_list_drafts(drafts: Sequence[EventDraft]) -> list[EventDraft]:
    """The same drafts as the pre-M5 adapters built them (``tolist()`` samples)."""
    out = []
    for d in drafts:
        p = dict(d.payload)
        if isinstance(p.get("samples"), np.ndarray):
            p["samples"] = p["samples"].tolist()
        out.append(EventDraft(d.event_type, p, d.quality, d.provenance, d.device_timestamp_ns))
    return out


def _json_of(draft: EventDraft) -> str:
    return fastjson.envelope_json(
        parse_envelope(
            {
                "schema_version": SCHEMA_VERSION,
                "session_id": "ses_perftest1",
                "device_id": "perf",
                "seq": 0,
                "timestamp_ns": 1,
                "device_timestamp_ns": draft.device_timestamp_ns,
                "event_type": draft.event_type,
                "capability": "recording",
                "payload": draft.payload,
                "quality": draft.quality,
                "provenance": draft.provenance,
            }
        )
    )


def test_lsl_array_frames_equal_list_frames() -> None:
    a = _lsl_adapter(6)
    data = (np.random.default_rng(1).standard_normal((4500, 6)) * 0.05).astype(np.float32)
    part = {
        "data": data,
        "ts": [1.0 + i / 30000 for i in range(4500)],
        "first_index": 10,
        "gap_starts": [100],
    }
    drafts = a._signal_drafts(part)
    # split at the gap and every MAX_FRAME_SAMPLES (2000) from the chunk start, as before
    assert [d.payload["samples"].shape for d in drafts] == [
        (6, 100),
        (6, 1900),
        (6, 2000),
        (6, 500),
    ]
    for new, old in zip(drafts, _as_list_drafts(drafts), strict=True):
        assert _json_of(new) == _json_of(old)
    # millivolts -> microvolts is applied before the frame is built (exact, float64)
    assert drafts[0].payload["samples"][0][0] == float(data[0, 0]) * 1e3


def test_openephys_array_frames_equal_list_frames() -> None:
    from brainos.adapters.openephys.adapter import OpenEphysPacket, normalize_packet
    from brainos.adapters.openephys.assembly import FrameChunk

    raw = rand(5, 64, np.float32)
    pkt = OpenEphysPacket("oe:t", 30000.0, 0.195, 20.0, (FrameChunk(30, raw, False),))
    (d,) = normalize_packet(pkt)
    assert isinstance(d.payload["samples"], np.ndarray)
    assert _json_of(d) == _json_of(_as_list_drafts([d])[0])
    expected = (raw.astype(np.float64) * 0.195).tolist()
    assert json.loads(_json_of(d))["payload"]["samples"] == expected


# --------------------------------------------------------------------------- runtime


BACKLOG_LIMIT = 5000


class _Backlog(DeviceAdapter):
    """read() never suspends: a source with a permanent backlog."""

    def __init__(self) -> None:
        self.descriptor = scripted_descriptor("backlog", [Capability.RECORDING])
        self.reads = 0

    async def open(self) -> None:
        pass

    async def close(self) -> None:
        pass

    def set_paused(self, paused: bool) -> None:
        pass

    async def read(self) -> NativePacket:
        self.reads += 1
        if self.reads > BACKLOG_LIMIT:  # frees a starved loop so a regression fails, not hangs
            raise EndOfStream("backlog test limit")
        return NativePacket(self.reads)

    def normalize(self, packet: NativePacket) -> Sequence[EventDraft]:
        return []


async def test_pump_yields_to_other_tasks_under_backlog(
    registry: DeviceRegistry, tmp_path: Path
) -> None:
    """Pre-M5, a source that always had data starved the event loop (REST, WebSocket and
    the pipeline task never ran). Regression test for the pump's per-packet yield."""
    adapter = _Backlog()
    registry.register(adapter.descriptor, lambda: adapter)
    rt = Runtime(registry, Recorder(tmp_path))
    await rt.connect("backlog")
    for _ in range(20):
        await asyncio.sleep(0)
    # with the yield, pump and test interleave; without it the pump ran to the limit first
    assert 0 < adapter.reads < BACKLOG_LIMIT
    await asyncio.wait_for(rt.disconnect(), 2)


def _frame_draft(ch: int, n: int, first: int) -> EventDraft:
    return EventDraft(
        EventType.RECORDING_FRAME,
        frame(rand(ch, n, np.float32, seed=first), first_sample_index=first),
        SYN,
        RAW,
        first * 1000,
    )


async def test_runtime_delivers_identical_events_for_array_and_list_drafts(
    runtime: Runtime, registry: DeviceRegistry
) -> None:
    from .helpers import ScriptedAdapter

    desc = scripted_descriptor("framer", [Capability.RECORDING, Capability.DEVICE_STATUS])
    adapter = ScriptedAdapter(desc, [])
    registry.register(desc, lambda: adapter)
    sub = subscribe(runtime, optional=[Capability.RECORDING])
    await runtime.connect("framer")
    d = _frame_draft(3, 50, 0)
    adapter.script.append([d, *_as_list_drafts([d])])
    await wait_for(lambda: runtime.diagnostics.totals["recording.frame"] >= 2)
    frames = [
        m["event"] for m in drain(sub) if m.get("event", {}).get("event_type") == "recording.frame"
    ]
    assert len(frames) == 2
    for f in frames:
        f.pop("seq"), f.pop("timestamp_ns")
    assert frames[0] == frames[1]
    assert runtime.diagnostics.validation_errors == 0


async def test_recorder_lines_are_identical_and_raw_exclusion_skips_serialization(
    runtime: Runtime, registry: DeviceRegistry
) -> None:
    from .helpers import ScriptedAdapter

    desc = scripted_descriptor("rec-framer", [Capability.RECORDING, Capability.DEVICE_STATUS])
    adapter = ScriptedAdapter(desc, [])
    registry.register(desc, lambda: adapter)
    await runtime.connect("rec-framer")
    runtime.start_recording("arrays")
    d = _frame_draft(2, 20, 5)
    adapter.script.append([d])
    await wait_for(lambda: runtime.diagnostics.totals["recording.frame"] >= 1)
    runtime.stop_recording()
    lines = (runtime.recorder.directory / "arrays.brainos.jsonl").read_text().splitlines()
    rec = [json.loads(x) for x in lines[1:] if '"recording.frame"' in x]
    assert rec[0]["payload"]["samples"] == d.payload["samples"].astype(np.float64).tolist()
    # exclude_raw: the recorder does not want frames, so they are never serialized for it
    runtime.start_recording("noraw", exclude_raw=True)
    env = envelope(rand(2, 2))
    assert not runtime.recorder.wants(env)
    runtime.stop_recording()


async def test_pipeline_input_queue_is_bounded_in_memory(
    registry: DeviceRegistry, tmp_path: Path
) -> None:
    """A pipeline that falls behind drops its oldest inputs before they exceed the memory
    budget (pre-M5 only the count was bounded: 4096 large frames could hold gigabytes)."""
    from .helpers import ScriptedAdapter

    desc = scripted_descriptor("q-framer", [Capability.RECORDING, Capability.DEVICE_STATUS])
    rec = next(c for c in desc.capabilities if c.capability is Capability.RECORDING)
    rec.params.update({"sample_rate_hz": 30000.0, "channel_count": 1024})
    adapter = ScriptedAdapter(desc, [])
    registry.register(desc, lambda: adapter)
    rt = Runtime(registry, Recorder(tmp_path))
    await rt.connect("q-framer")
    rt.start_pipeline(PipelineStartRequest(processing={"preset": "spikeband_threshold"}))
    big = rt.pipeline
    env = envelope(np.zeros((1024, 2000), dtype=np.float32))
    env = env.model_copy(update={"session_id": rt._session_id})
    n = QUEUE_MAX_VALUES // (1024 * 2000) + 5
    for _ in range(n):  # synchronous: the pipeline task gets no chance to run
        big.tap(env, "")
    assert big._queued_values <= QUEUE_MAX_VALUES
    assert big.counters["dropped_inputs"] == n - len(big._queue) > 0
    await rt.shutdown()


def test_event_json_size_estimate() -> None:
    env = envelope(rand(16, 100, np.float64))
    assert EventJson(env).nbytes == 16 * 100 * 8
    assert EventJson(None, "x" * 50).nbytes == 50


# --------------------------------------------------------------------------- benchmark smoke


def _bench() -> Any:
    import importlib.util
    import sys

    path = REPO / "scripts" / "bench_scale.py"
    spec = importlib.util.spec_from_file_location("bench_scale", path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules["bench_scale"] = mod
    spec.loader.exec_module(mod)
    return mod


async def test_bench_scale_smoke() -> None:
    """The scale benchmark's in-process sections run at tiny sizes (no timing asserts)."""
    bench = _bench()
    micro = await bench._micro_one(8, 30, 1)
    assert micro["ingest_us"] > 0 and micro["json_bytes"] > 0
    rng = np.random.default_rng(0)
    rows = bench._alt_json(8, 1, rng)
    assert rows and all(r["byte_identical"] for r in rows)
    validate = bench._alt_validate(8, 1, rng)
    assert any("shipped" in r["method"] for r in validate)
    sos = bench._alt_sos(8, 1, rng, None, None)
    assert all(r["max_abs_err_uV"] < 1e-9 for r in sos)
    text = bench.render(
        {"started": "now", "command": "x", "machine": {}, "load_start": "0", "micro": [micro]}
    )
    assert "per 10 ms chunk" in text


# --------------------------------------------------------------------------- transport limits


def test_frames_stay_under_the_sdk_message_limit_at_high_channel_counts() -> None:
    """Pre-M5, a 2000-sample frame at 256+ channels exceeded the Python SDK's 8 MiB WebSocket
    message limit and disconnected every raw-signal client (measured: 1009 message too big)."""
    from brainos.adapters.base import MAX_FRAME_VALUES, frame_samples_limit

    assert frame_samples_limit(64, 2000) == 2000
    assert frame_samples_limit(1024, 2000) == MAX_FRAME_VALUES // 1024 == 256
    assert frame_samples_limit(10**6, 2000) == 1
    a = _lsl_adapter(1024)
    data = (np.random.default_rng(2).standard_normal((2000, 1024)) * 1e-5).astype(np.float32)
    drafts = a._signal_drafts({"data": data, "ts": [1.0] * 2000, "first_index": 0})
    assert {d.payload["samples"].shape[1] for d in drafts} == {256, 2000 - 7 * 256}
    assert max(len(_json_of(d)) for d in drafts) < 8 * 1024 * 1024
    joined = np.concatenate([d.payload["samples"] for d in drafts], axis=1)
    assert np.array_equal(joined, data.T.astype(np.float64) * 1e3)  # nothing lost or reordered


def test_server_entry_point_disables_websocket_compression(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """permessage-deflate cost ~13 ms of CPU per 180 KB raw frame (M5-E measurement)."""
    import uvicorn

    import brainos.server.__main__ as entry

    seen: dict[str, Any] = {}
    monkeypatch.setattr(uvicorn, "run", lambda app, **kw: seen.update(kw))
    monkeypatch.setenv("BRAINOS_PLUGINS", "0")
    entry.main()
    assert seen["ws_per_message_deflate"] is False
