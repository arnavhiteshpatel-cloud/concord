"""Runtime behaviour (AT-9..AT-17)."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from brainos.adapters.base import DeviceLinkError, EndOfStream, EventDraft
from brainos.adapters.simulated import Fault, OperatorIntentSource
from brainos.contracts.capabilities import Capability, EventType
from brainos.contracts.events import SCHEMA_VERSION, Quality
from brainos.contracts.protocol import AppStatus, ErrorCode, RejectionReason, RuntimeState
from brainos.runtime import DeviceRegistry, Recorder, Runtime, RuntimeCommandError

from .conftest import FAST_BACKOFF, subscribe
from .helpers import (
    SIM_PROV,
    ScriptedAdapter,
    drain,
    events,
    scripted_descriptor,
    sel_draft,
    tel_draft,
    wait_for,
)


async def test_connect_stamps_session_and_strictly_increasing_seq(runtime: Runtime) -> None:
    """AT-9: connect -> streaming; events carry session + strictly increasing seq."""
    sub = subscribe(runtime)
    snap = await runtime.connect("sim-a")
    assert snap.state is RuntimeState.STREAMING
    assert snap.session_id and snap.device and snap.device.device_id == "sim-a"
    await wait_for(lambda: sub.queue_depth > 60)
    evs = events(drain(sub))
    assert {e["session_id"] for e in evs} == {snap.session_id}
    seqs = [e["seq"] for e in evs]
    assert seqs == sorted(seqs) and len(set(seqs)) == len(seqs)
    assert seqs[0] == 0  # app subscribed before connect and sees the session from the start
    statuses = [e["payload"]["state"] for e in evs if e["event_type"] == "device.status"]
    assert statuses[:2] == ["connected", "streaming"]
    assert all(e["schema_version"] == SCHEMA_VERSION for e in evs)


async def test_connect_twice_is_invalid_state(runtime: Runtime) -> None:
    await runtime.connect("sim-a")
    with pytest.raises(RuntimeCommandError) as info:
        await runtime.connect("sim-b")
    assert info.value.code is ErrorCode.INVALID_STATE


async def test_unknown_device(runtime: Runtime) -> None:
    with pytest.raises(RuntimeCommandError) as info:
        await runtime.connect("neuralink-n1")
    assert info.value.code is ErrorCode.DEVICE_NOT_FOUND
    assert runtime.state is RuntimeState.IDLE


async def test_pause_stops_delivery_and_resume_restarts(runtime: Runtime) -> None:
    """AT-10: pause stops delivery; resume restarts it."""
    sub = subscribe(runtime)
    await runtime.connect("sim-a")
    await wait_for(lambda: sub.queue_depth > 10)
    await runtime.pause()
    assert runtime.state is RuntimeState.PAUSED
    drain(sub)
    await asyncio.sleep(0.3)
    paused_evs = events(drain(sub))
    assert all(e["event_type"] == "device.status" for e in paused_evs)
    with pytest.raises(RuntimeCommandError):
        await runtime.pause()
    await runtime.resume()
    assert runtime.state is RuntimeState.STREAMING
    await wait_for(lambda: sub.queue_depth > 10)
    resumed = events(drain(sub))
    assert resumed[0]["payload"]["state"] == "streaming"
    assert any(e["event_type"] == "intent.pointer" for e in resumed)


async def test_recoverable_link_drop_reconnects_same_session(runtime: Runtime) -> None:
    """AT-11: link drop -> reconnecting -> streaming; same session; seq increasing."""
    sub = subscribe(runtime)
    snap = await runtime.connect("sim-b")
    await wait_for(lambda: sub.queue_depth > 3)
    adapter = runtime.adapter
    assert adapter is not None
    adapter.inject_fault(Fault.LINK_DROP)  # type: ignore[attr-defined]
    await wait_for(lambda: runtime.diagnostics.reconnect_successes == 1)
    await wait_for(lambda: sub.queue_depth > 8)
    evs = events(drain(sub))
    states = [e["payload"]["state"] for e in evs if e["event_type"] == "device.status"]
    assert "reconnecting" in states
    assert states[-1] == "streaming"
    assert runtime.state is RuntimeState.STREAMING
    assert runtime.snapshot().session_id == snap.session_id
    seqs = [e["seq"] for e in evs]
    assert seqs == sorted(seqs)
    assert runtime.diagnostics.link_errors == 1


async def test_unrecoverable_link_failure_enters_error(runtime: Runtime) -> None:
    """AT-12: unrecoverable link failure -> error with last error; reconnect via connect."""
    sub = subscribe(runtime)
    await runtime.connect("sim-a")
    runtime.adapter.inject_fault(Fault.LINK_FAIL)  # type: ignore[union-attr]
    await wait_for(lambda: runtime.state is RuntimeState.ERROR)
    snap = runtime.snapshot()
    assert snap.last_error and "reconnect attempts failed" in snap.last_error
    assert runtime.diagnostics.reconnect_attempts == len(FAST_BACKOFF)
    assert sub.negotiation.status is AppStatus.NO_DEVICE
    statuses = [e["payload"]["state"] for e in events(drain(sub), "device.status")]
    assert statuses[-1] == "error"
    # operator can recover by connecting again (fresh adapter instance)
    await runtime.connect("sim-a")
    assert runtime.state is RuntimeState.STREAMING


async def test_connect_failure_reports_device_error(
    registry: DeviceRegistry, tmp_path: Path
) -> None:
    desc = scripted_descriptor("flaky")
    registry.register(desc, lambda: ScriptedAdapter(desc, [], fail_open=1))
    rt = Runtime(registry, Recorder(tmp_path), reconnect_backoff_s=FAST_BACKOFF)
    with pytest.raises(RuntimeCommandError) as info:
        await rt.connect("flaky")
    assert info.value.code is ErrorCode.DEVICE_ERROR
    assert rt.state is RuntimeState.ERROR
    await rt.disconnect()
    assert rt.state is RuntimeState.IDLE


async def test_bad_packets_dropped_and_counted_stream_continues(
    registry: DeviceRegistry, tmp_path: Path
) -> None:
    """AT-13: malformed packets, invalid drafts, undeclared capabilities are dropped + counted."""
    desc = scripted_descriptor("scripted", [Capability.SELECTION, Capability.DEVICE_STATUS])
    invalid = EventDraft(
        EventType.INTENT_SELECTION,
        {"action": "primary", "confidence": 7.0},
        Quality(score=1),
        SIM_PROV,
    )
    script = [
        [sel_draft(ts=10)],
        "corrupt",
        "crash",
        [invalid],
        [tel_draft(ts=20)],  # telemetry not declared by this device
        [sel_draft(ts=30)],
    ]
    registry.register(desc, lambda: ScriptedAdapter(desc, script))
    rt = Runtime(registry, Recorder(tmp_path))
    sub = subscribe(rt)
    await rt.connect("scripted")
    await wait_for(lambda: rt.diagnostics.totals["intent.selection"] == 2)
    d = rt.diagnostics
    assert (d.decode_errors, d.validation_errors, d.undeclared_capability) == (2, 1, 1)
    sels = events(drain(sub), "intent.selection")
    assert [e["device_timestamp_ns"] for e in sels] == [10, 30]
    assert rt.state is RuntimeState.STREAMING
    kinds = {e.kind for e in rt.diagnostics_snapshot().recent_errors}
    assert {"decode_error", "validation_error", "undeclared_capability"} <= kinds
    await rt.shutdown()


async def test_timestamp_regression_flagged_not_reordered(
    registry: DeviceRegistry, tmp_path: Path
) -> None:
    desc = scripted_descriptor("clock", [Capability.SELECTION])
    script = [[sel_draft(ts=100)], [sel_draft(ts=50)], [sel_draft(ts=150)]]
    registry.register(desc, lambda: ScriptedAdapter(desc, script))
    rt = Runtime(registry, Recorder(tmp_path))
    sub = subscribe(rt)
    await rt.connect("clock")
    await wait_for(lambda: rt.diagnostics.totals["intent.selection"] == 3)
    sels = events(drain(sub), "intent.selection")
    assert [e["device_timestamp_ns"] for e in sels] == [100, 50, 150]  # delivery order preserved
    assert [("timestamp_regression" in e["quality"]["flags"]) for e in sels] == [False, True, False]
    assert rt.diagnostics.timestamp_regressions == 1
    await rt.shutdown()


async def test_adapter_crash_in_read_treated_as_link_error(
    registry: DeviceRegistry, tmp_path: Path
) -> None:
    desc = scripted_descriptor("buggy", [Capability.SELECTION])
    registry.register(desc, lambda: ScriptedAdapter(desc, [KeyError("bug"), [sel_draft()]]))
    rt = Runtime(registry, Recorder(tmp_path), reconnect_backoff_s=FAST_BACKOFF)
    await rt.connect("buggy")
    await wait_for(lambda: rt.diagnostics.totals["intent.selection"] == 1)
    assert rt.diagnostics.link_errors == 1 and rt.state is RuntimeState.STREAMING
    await rt.shutdown()


async def test_end_of_stream(registry: DeviceRegistry, tmp_path: Path) -> None:
    desc = scripted_descriptor("finite", [Capability.SELECTION])
    registry.register(desc, lambda: ScriptedAdapter(desc, [[sel_draft()], EndOfStream("done")]))
    rt = Runtime(registry, Recorder(tmp_path))
    sub = subscribe(rt, required=[Capability.SELECTION], optional=[])
    await rt.connect("finite")
    await wait_for(lambda: rt.state is RuntimeState.ENDED)
    assert sub.negotiation.status is AppStatus.NO_DEVICE
    await rt.disconnect()
    assert rt.state is RuntimeState.IDLE


async def test_switch_renegotiates_and_records_duration(runtime: Runtime) -> None:
    """AT-14: switch A->B: new session, re-negotiation pushed, duration recorded."""
    board = subscribe(
        runtime,
        required=[Capability.SELECTION],
        optional=[Capability.POINTER_INTENT, Capability.TEXT_INTENT],
        app_id="board",
    )
    a = await runtime.connect("sim-a")
    assert set(board.negotiation.granted) == {Capability.SELECTION, Capability.POINTER_INTENT}
    drain(board)
    b = await runtime.switch("sim-b")
    assert b.session_id != a.session_id and b.device and b.device.device_id == "sim-b"
    msgs = drain(board)
    neg = [m["negotiation"] for m in msgs if m["type"] == "negotiation"]
    assert neg and set(neg[-1]["granted"]) == {"selection", "text_intent"}
    assert neg[-1]["rejected"] == [
        {"capability": "pointer_intent", "reason": "unsupported_by_device", "required": False}
    ]
    sw = runtime.diagnostics_snapshot().switches
    assert sw[-1].from_device == "sim-a" and sw[-1].to_device == "sim-b" and sw[-1].duration_ms > 0


async def test_switch_to_unknown_device_keeps_current(runtime: Runtime) -> None:
    await runtime.connect("sim-a")
    with pytest.raises(RuntimeCommandError):
        await runtime.switch("does-not-exist")
    assert runtime.state is RuntimeState.STREAMING and runtime.device
    assert runtime.device.device_id == "sim-a"


async def test_events_filtered_by_grant_and_suspension(
    runtime: Runtime, intents: OperatorIntentSource
) -> None:
    """AT-15: only granted capabilities delivered; required-but-unsupported => suspended."""
    sel_only = subscribe(runtime, required=[Capability.SELECTION], optional=[], app_id="sel")
    needs_ptr = subscribe(runtime, required=[Capability.POINTER_INTENT], optional=[], app_id="ptr")
    await runtime.connect("sim-b")
    assert needs_ptr.negotiation.status is AppStatus.SUSPENDED
    assert needs_ptr.negotiation.rejected[0].reason is RejectionReason.UNSUPPORTED_BY_DEVICE
    intents.submit_select()
    await wait_for(lambda: sel_only.queue_depth >= 1, timeout=2)
    await asyncio.sleep(0.2)
    assert {e["event_type"] for e in events(drain(sel_only))} == {"intent.selection"}
    assert events(drain(needs_ptr)) == []


async def test_slow_subscriber_drops_oldest_others_unaffected(
    registry: DeviceRegistry, tmp_path: Path
) -> None:
    """AT-16: overflow drops oldest, counted per subscriber; delivery_seq shows the gap."""
    rt = Runtime(registry, Recorder(tmp_path), queue_size=20)
    slow = subscribe(rt, app_id="slow")
    fast = subscribe(rt, app_id="fast")
    fast.max_queue = 100_000
    await rt.connect("sim-a")
    await wait_for(lambda: slow.dropped > 0)
    assert slow.queue_depth == 20 and fast.dropped == 0
    # control.state notices (1.4, the app asked for control_status) are pinned: never dropped
    pinned = [e for e in slow._events if e[4]]
    assert pinned and {json.loads(e[1].text)["event_type"] for e in pinned} == {"control.state"}
    kept = [e[0] for e in slow._events]
    # the oldest event of all (the first notice) is still queued; how many unpinned events sit
    # between the pinned ones depends on how many drops happened by now (>= 1)
    assert kept[0] == pinned[0][0] == 0
    # every other gap in delivery_seq is a dropped event, and the dropped ones are the oldest
    missing = set(range(slow._next_delivery_seq)) - set(kept)
    assert len(missing) == slow.dropped
    assert max(missing) < min(e[0] for e in slow._events if not e[4])
    assert rt.diagnostics_snapshot().counters.subscriber_drops == slow.dropped
    await rt.shutdown()


async def test_rates_not_inflated_right_after_connect(runtime: Runtime) -> None:
    """Regression: rolling rate window has a 1 s floor (was ~100 Hz for 2 status events)."""
    await runtime.connect("sim-b")
    rates = {t.event_type: t.rate_hz for t in runtime.diagnostics_snapshot().event_types}
    assert rates["device.status"] <= 2.0


async def test_disconnect_notifies_apps(runtime: Runtime) -> None:
    sub = subscribe(runtime, required=[Capability.SELECTION], optional=[])
    await runtime.connect("sim-a")
    drain(sub)
    snap = await runtime.disconnect()
    assert snap.state is RuntimeState.IDLE and snap.device is None
    msgs = drain(sub)
    assert [e["payload"]["state"] for e in events(msgs)] == []  # status not granted to this app
    assert sub.negotiation.status is AppStatus.NO_DEVICE


async def test_record_and_replay_preserves_provenance_and_order(
    tmp_path: Path, intents: OperatorIntentSource
) -> None:
    """AT-17: record live -> replay; same provenance kinds, replayed=true, order preserved."""
    rec_dir = tmp_path / "rec"
    registry = DeviceRegistry(intents, rec_dir, seed=1, replay_loop=False)
    rt = Runtime(registry, Recorder(rec_dir))
    await rt.connect("sim-b")
    name = rt.start_recording("unit-test")
    # header is flushed immediately, so the in-progress recording is listable without errors
    assert any(r.name == "unit-test" for r in rt.recorder.list())
    intents.submit_select()
    intents.submit_text("hi")
    await wait_for(lambda: rt.diagnostics.totals["intent.text"] == 1)
    await asyncio.sleep(0.2)
    info = rt.stop_recording()
    assert info.name == name and info.events and info.events > 3
    lines = (rec_dir / f"{name}.brainos.jsonl").read_text().splitlines()
    header = json.loads(lines[0])
    assert header["format"] == "brainos.recording/1" and header["synthetic"] is True
    original = [json.loads(line) for line in lines[1:]]

    replay_id = f"replay:{name}"
    assert replay_id in [d.device_id for d in registry.list()]
    sub = subscribe(rt)
    await rt.switch(replay_id)
    await wait_for(lambda: rt.state is RuntimeState.ENDED, timeout=5)
    replayed = [e for e in events(drain(sub)) if e["provenance"]["kind"] != "runtime"]
    expected = [e for e in original if e["provenance"]["kind"] != "runtime"]
    assert [e["event_type"] for e in replayed] == [e["event_type"] for e in expected]
    assert [e["payload"] for e in replayed] == [e["payload"] for e in expected]
    for r, o in zip(replayed, expected, strict=True):
        assert r["provenance"]["kind"] == o["provenance"]["kind"]
        assert r["provenance"]["replayed"] is True
        assert "replayed" in r["quality"]["flags"]
        assert r["device_id"] == replay_id
    assert [e["seq"] for e in replayed] == sorted(e["seq"] for e in replayed)
    await rt.shutdown()


async def test_recording_requires_device_and_stops_on_disconnect(runtime: Runtime) -> None:
    with pytest.raises(RuntimeCommandError):
        runtime.start_recording()
    await runtime.connect("sim-a")
    runtime.start_recording("r1")
    with pytest.raises(RuntimeCommandError):
        runtime.start_recording("r2")
    await runtime.disconnect()
    assert runtime.recorder.active_name is None
    assert [r.name for r in runtime.recorder.list()] == ["r1"]


async def test_preview_negotiation(runtime: Runtime) -> None:
    res = runtime.preview_negotiation("sim-b", [Capability.POINTER_INTENT], [])
    assert res.status is AppStatus.SUSPENDED
    res = runtime.preview_negotiation(None, [Capability.SELECTION], [])
    assert res.status is AppStatus.NO_DEVICE


async def test_link_error_during_pause_resumes_paused(
    registry: DeviceRegistry, tmp_path: Path
) -> None:
    desc = scripted_descriptor("p", [Capability.SELECTION])
    adapter = ScriptedAdapter(desc, [])
    registry.register(desc, lambda: adapter)
    rt = Runtime(registry, Recorder(tmp_path), reconnect_backoff_s=FAST_BACKOFF)
    await rt.connect("p")
    await rt.pause()
    adapter.script.append(DeviceLinkError("drop"))
    await wait_for(lambda: rt.diagnostics.reconnect_successes == 1)
    assert rt.state is RuntimeState.PAUSED and adapter.paused
    await rt.shutdown()


# --------------------------------------------------------------------------------------
# Regression tests from the independent review (one per finding).


async def test_recording_stops_when_reconnect_gives_up(runtime: Runtime) -> None:
    """Review #1: a recording must not outlive the device that produced it."""
    await runtime.connect("sim-a")
    runtime.start_recording("leak")
    runtime.adapter.inject_fault(Fault.LINK_FAIL)  # type: ignore[union-attr]
    await wait_for(lambda: runtime.state is RuntimeState.ERROR)
    assert runtime.recorder.active_name is None
    await runtime.connect("sim-b")
    lines = (runtime.recorder.directory / "leak.brainos.jsonl").read_text().splitlines()
    assert {json.loads(line)["device_id"] for line in lines[1:]} == {"sim-a"}


async def test_replay_of_empty_recording_ends_instead_of_spinning(
    tmp_path: Path, intents: OperatorIntentSource
) -> None:
    """Review #2: a recording with no replayable events must end, not busy-loop the server."""
    rec_dir = tmp_path / "rec"
    registry = DeviceRegistry(intents, rec_dir, seed=1)  # looping replay (the default)
    rt = Runtime(registry, Recorder(rec_dir))
    await rt.connect("sim-a")
    await rt.pause()
    rt.start_recording("empty")
    rt.stop_recording()
    ticks = 0

    async def ticker() -> None:
        nonlocal ticks
        while True:
            ticks += 1
            await asyncio.sleep(0.01)

    t = asyncio.create_task(ticker())
    await rt.switch("replay:empty")
    await wait_for(lambda: rt.state is RuntimeState.ENDED, timeout=3)
    t.cancel()
    assert ticks > 0  # the event loop was never starved
    await rt.shutdown()


async def test_pump_crash_moves_runtime_to_error(registry: DeviceRegistry, tmp_path: Path) -> None:
    """Review #6: an unexpected exception in the pump must not leave state 'streaming'."""
    desc = scripted_descriptor("crashy", [Capability.SELECTION])
    adapter = ScriptedAdapter(desc, [])
    registry.register(desc, lambda: adapter)
    rt = Runtime(registry, Recorder(tmp_path))

    def bad_tap(*_: object) -> None:
        raise ZeroDivisionError("tap bug")

    await rt.connect("crashy")
    rt.bus.add_tap(bad_tap)
    adapter.script.append([sel_draft()])
    await wait_for(lambda: rt.state is RuntimeState.ERROR)
    assert rt.snapshot().last_error and "pump" in rt.snapshot().last_error
    await rt.disconnect()
    assert rt.state is RuntimeState.IDLE


async def test_recorder_write_failure_stops_recording_not_stream(runtime: Runtime) -> None:
    """Review #6: disk errors stop the recording; streaming continues."""
    sub = subscribe(runtime)
    await runtime.connect("sim-a")
    runtime.start_recording("diskfull")

    class Broken:
        def write(self, _: str) -> int:
            raise OSError(28, "No space left on device")

        def close(self) -> None:
            raise OSError(28, "No space left on device")

    runtime.recorder._fh = Broken()  # type: ignore[assignment]
    await wait_for(lambda: runtime.recorder.active_name is None)
    drain(sub)
    await wait_for(lambda: sub.queue_depth > 5)
    assert runtime.state is RuntimeState.STREAMING
    assert (await runtime.disconnect()).state is RuntimeState.IDLE


def test_control_queue_is_bounded() -> None:
    """Review #4: a client that never reads cannot grow server memory without bound."""
    from brainos.contracts.protocol import AppInfo, AppStatus, NegotiationResult
    from brainos.runtime.bus import MAX_CONTROL_QUEUE, Subscriber, SubscriberOverflowError

    sub = Subscriber(
        "c",
        AppInfo(id="x", name="x"),
        [],
        [],
        NegotiationResult(device_id=None, status=AppStatus.NO_DEVICE, granted=[], rejected=[]),
    )
    for _ in range(MAX_CONTROL_QUEUE * 4):
        sub.offer_control("{}")
    assert len(sub._control) == MAX_CONTROL_QUEUE and sub.control_overflow
    with pytest.raises(SubscriberOverflowError):
        asyncio.run(sub.next_message())


async def test_replay_skips_truncated_last_line(
    tmp_path: Path, intents: OperatorIntentSource
) -> None:
    """Review (minor): a line truncated by a crash is skipped; replay still ends cleanly."""
    rec_dir = tmp_path / "rec"
    registry = DeviceRegistry(intents, rec_dir, seed=1, replay_loop=False)
    rt = Runtime(registry, Recorder(rec_dir))
    await rt.connect("sim-b")
    rt.start_recording("trunc")
    await wait_for(lambda: rt.diagnostics.totals["recording.frame"] >= 3)
    rt.stop_recording()
    path = rec_dir / "trunc.brainos.jsonl"
    path.write_text(path.read_text() + '{"schema_version": "1.0", "seq": 9')
    await rt.switch("replay:trunc")
    await wait_for(lambda: rt.state is RuntimeState.ENDED, timeout=5)
    assert rt.diagnostics.link_errors == 0
    await rt.shutdown()
