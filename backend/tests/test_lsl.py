"""LSL adapter against the REAL liblsl network stack (pylsl outlets/inlets) — M3-AT-1..4.

No mocks: every test publishes with a genuine liblsl StreamOutlet and BrainOS consumes
it through discovery + StreamInlet. Unique source_ids isolate tests from each other.
"""

from __future__ import annotations

import asyncio
import threading
import time
import uuid
from collections.abc import Iterator
from typing import Any

import numpy as np
import pytest

pylsl = pytest.importorskip("pylsl")

from brainos.adapters.base import DeviceLinkError  # noqa: E402
from brainos.adapters.lsl import (  # noqa: E402
    LSLAdapter,
    LSLSourceSpec,
    StreamMeta,
    discovery,
)
from brainos.adapters.simulated import OperatorIntentSource  # noqa: E402
from brainos.contracts import parse_envelope  # noqa: E402
from brainos.contracts.protocol import DeviceKind, RuntimeState  # noqa: E402
from brainos.runtime import DeviceRegistry, Recorder, Runtime  # noqa: E402

from .conftest import subscribe  # noqa: E402
from .helpers import drain, events, wait_for  # noqa: E402


class Outlet:
    """A real liblsl outlet pushing caller-provided chunks at real-time pace."""

    def __init__(
        self,
        *,
        name: str = "test",
        stype: str = "EEG",
        channels: int = 4,
        fs: float = 1000.0,
        fmt: Any = None,
        units: list[str | None] | None = None,
        source_id: str | None = None,
        declare: dict[str, str] | None = None,
    ) -> None:
        self.source_id = source_id or f"brainos-test-{uuid.uuid4().hex[:10]}"
        info = pylsl.StreamInfo(name, stype, channels, fs, fmt or pylsl.cf_float32, self.source_id)
        if units is not None:
            chs = info.desc().append_child("channels")
            for i, u in enumerate(units):
                c = chs.append_child("channel")
                c.append_child_value("label", f"c{i}")
                if u is not None:
                    c.append_child_value("unit", u)
        if declare:
            b = info.desc().append_child("brainos")
            for k, v in declare.items():
                b.append_child_value(k, v)
        self.info = info
        self.fs = fs
        self.outlet = pylsl.StreamOutlet(info, chunk_size=0, max_buffered=60)

    def push(self, data: np.ndarray, stamp: float | None = None) -> None:
        if not hasattr(self, "outlet"):  # closed (a pusher thread may still be winding down)
            return
        if stamp is None:
            self.outlet.push_chunk(data.tolist())
        else:
            self.outlet.push_chunk(data.tolist(), stamp)

    def close(self) -> None:
        del self.outlet


def find(source_id: str, wait: float = 2.0) -> StreamMeta:
    end = time.monotonic() + 8
    while time.monotonic() < end:
        for _info, meta in discovery.discover(wait):
            if meta.source_id == source_id:
                return meta
    raise AssertionError(f"stream {source_id} not discovered")


class Pusher(threading.Thread):
    """Pushes a ramp signal at real-time pace in a background thread."""

    def __init__(self, out: Outlet, chunk: int = 10) -> None:
        super().__init__(daemon=True)
        self.out, self.chunk = out, chunk
        self.stop = threading.Event()
        self.sent = 0

    def run(self) -> None:
        ch = self.out.info.channel_count()
        while not self.stop.is_set():
            block = (
                np.arange(self.sent, self.sent + self.chunk)[:, None] + np.zeros((1, ch))
            ).astype(np.float32)
            self.out.push(block)
            self.sent += self.chunk
            time.sleep(self.chunk / self.out.fs)


@pytest.fixture
def pusher() -> Iterator[list[Pusher]]:
    started: list[Pusher] = []
    yield started
    for p in started:
        p.stop.set()
        p.join(2)


async def collect(adapter: LSLAdapter, until: Any, timeout: float = 8.0) -> list[Any]:
    drafts: list[Any] = []
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        drafts += adapter.normalize(await adapter.read())
        if until(drafts):
            return drafts
    raise AssertionError(f"timed out with {len(drafts)} drafts")


# ------------------------------------------------------------------ metadata (AT-1)


async def test_discovery_reads_real_stream_metadata() -> None:
    """M3-AT-1: labels, units, rate, format and declarations come from the stream itself."""
    out = Outlet(
        channels=3, units=["microvolts", "microvolts", "microvolts"], declare={"synthetic": "true"}
    )
    meta = find(out.source_id)
    assert (
        meta.channel_count == 3
        and meta.nominal_srate == 1000.0
        and meta.channel_format == "float32"
    )
    assert [c.label for c in meta.channels] == ["c0", "c1", "c2"]
    assert {c.unit for c in meta.channels} == {"microvolts"}
    assert meta.declaration.synthetic is True and meta.declaration.prerecorded is None
    out.close()


@pytest.mark.parametrize(
    ("units", "expect_unit", "scale"),
    [
        (["millivolts", "millivolts"], "uV", 1000.0),
        (["V", "volts"], "uV", 1e6),
        (["microvolts", "uV"], "uV", 1.0),
        (["microvolts", "furlongs"], "arbitrary", 1.0),  # one unknown unit -> nothing scaled
        (None, "arbitrary", 1.0),  # no channel metadata at all
    ],
)
async def test_units_converted_exactly_or_marked_arbitrary(
    units: list[str] | None, expect_unit: str, scale: float
) -> None:
    """M3-AT-1/2: known units converted exactly to µV; unknown units never assumed."""
    out = Outlet(channels=2, units=units)  # type: ignore[arg-type]
    adapter = LSLAdapter(LSLSourceSpec(device_id="lsl:t", signal=find(out.source_id)))
    await adapter.open()
    values = np.array([[0.5, -1.25], [2.0, 0.125], [-3.5, 7.75]], dtype=np.float32)
    out.push(values)
    drafts = await collect(adapter, lambda d: sum(len(x.payload["samples"][0]) for x in d) >= 3)
    frame = drafts[0].payload
    assert frame["unit"] == expect_unit
    got = np.array(frame["samples"]).T[:3]
    assert np.array_equal(
        got, values.astype(np.float64) * scale
    )  # exact (powers of two / decimal scale)
    assert adapter.descriptor.capabilities[0].params["unit"] == expect_unit
    await adapter.close()
    out.close()


# ------------------------------------------------------------------ timestamps & gaps (AT-3)


async def test_source_timestamps_preserved_and_gaps_flagged() -> None:
    """M3-AT-3: device timestamps are the LSL source timestamps; dropped samples are flagged."""
    out = Outlet(channels=1, fs=100.0, units=["microvolts"])
    adapter = LSLAdapter(LSLSourceSpec(device_id="lsl:t", signal=find(out.source_id)))
    await adapter.open()
    t0 = pylsl.local_clock()
    a = np.arange(10, dtype=np.float32)[:, None]
    out.push(a, stamp=t0 + 0.09)  # liblsl stamps the LAST sample; earlier ones at 1/fs steps
    out.push(a + 10, stamp=t0 + 0.19)  # contiguous
    out.push(a + 20, stamp=t0 + 0.49)  # 20 samples missing before this chunk
    drafts = await collect(adapter, lambda d: sum(len(x.payload["samples"][0]) for x in d) >= 30)
    assert drafts[0].device_timestamp_ns == pytest.approx(t0 * 1e9, abs=2_000)  # first sample at t0
    flagged = [d for d in drafts if "dropped_samples" in d.quality.flags]
    assert len(flagged) == 1 and flagged[0].payload["samples"][0][0] == 20.0
    assert adapter.stats.gaps == 1 and adapter.stats.est_missing_samples == 20
    await adapter.close()
    out.close()


async def test_composite_source_behavior_and_markers_on_signal_clock() -> None:
    """M3-AT-3: behavior + marker streams arrive with timestamps on the signal stream's clock."""
    sig = Outlet(channels=2, fs=100.0, units=["microvolts", "microvolts"])
    beh = Outlet(
        name="kin", stype="Behavior", channels=2, fs=100.0, units=["arbitrary", "arbitrary"]
    )
    mk = Outlet(name="mk", stype="Markers", channels=1, fs=0.0, fmt=pylsl.cf_string)
    spec = LSLSourceSpec(
        device_id="lsl:t",
        signal=find(sig.source_id),
        behavior=find(beh.source_id),
        markers=find(mk.source_id),
    )
    adapter = LSLAdapter(spec)
    await adapter.open()
    caps = {c.capability.value for c in adapter.descriptor.capabilities}
    assert caps == {"recording", "behavior", "device_status"}
    t0 = pylsl.local_clock()
    sig.push(np.zeros((10, 2), np.float32), stamp=t0 + 0.09)
    beh.push(np.ones((10, 2), np.float32), stamp=t0 + 0.09)
    mk.outlet.push_sample(["trial 1"], t0 + 0.05)
    drafts = await collect(
        adapter,
        lambda d: (
            {x.event_type.value for x in d}
            >= {"recording.frame", "behavior.sample", "recording.annotation"}
        ),
    )
    ann = next(x for x in drafts if x.event_type.value == "recording.annotation")
    assert ann.payload["label"] == "trial 1" and ann.provenance.kind.value == "behavioral_label"
    assert ann.device_timestamp_ns == pytest.approx(
        (t0 + 0.05) * 1e9, abs=1e6
    )  # same host: ~0 offset
    behs = [x for x in drafts if x.event_type.value == "behavior.sample"]
    assert behs[0].payload["dims"] == ["c0", "c1"] and behs[0].payload["unit"] == "arbitrary"
    await adapter.close()
    for o in (sig, beh, mk):
        o.close()


def test_declared_prerecorded_and_synthetic_streams_are_labelled() -> None:
    """Liveness is never assumed: undeclared streams are 'stream' (origin unverified)."""
    base = dict(
        type="EEG",
        hostname="h",
        uid="u",
        channel_count=1,
        nominal_srate=100.0,
        channel_format="float32",
        created_at=0.0,
    )
    from brainos.adapters.lsl import Declaration

    plain = LSLAdapter(
        LSLSourceSpec(device_id="lsl:a", signal=StreamMeta(name="a", source_id="a", **base))
    )
    rec = LSLAdapter(
        LSLSourceSpec(
            device_id="lsl:b",
            signal=StreamMeta(
                name="b",
                source_id="b",
                declaration=Declaration(prerecorded=True, origin="dandi:000954/x"),
                **base,
            ),
        )
    )
    syn = LSLAdapter(
        LSLSourceSpec(
            device_id="lsl:c",
            signal=StreamMeta(
                name="c", source_id="c", declaration=Declaration(synthetic=True), **base
            ),
        )
    )
    assert plain.descriptor.kind is DeviceKind.STREAM and not plain.descriptor.synthetic
    assert "cannot verify" in plain.descriptor.description
    assert (
        rec.descriptor.kind is DeviceKind.REPLAY
        and rec._p_raw.replayed
        and rec.origin == "dandi:000954/x"
    )
    assert syn.descriptor.kind is DeviceKind.SIMULATED and syn.descriptor.synthetic


def test_unsupported_signal_streams_are_refused() -> None:
    base = dict(
        name="x",
        type="Markers",
        source_id="x",
        hostname="h",
        uid="u",
        channel_count=1,
        created_at=0.0,
    )
    with pytest.raises(ValueError, match="strings"):
        LSLAdapter(
            LSLSourceSpec(
                device_id="lsl:x",
                signal=StreamMeta(nominal_srate=0.0, channel_format="string", **base),
            )
        )
    with pytest.raises(ValueError, match="irregular"):
        LSLAdapter(
            LSLSourceSpec(
                device_id="lsl:x",
                signal=StreamMeta(nominal_srate=0.0, channel_format="float32", **base),
            )
        )


async def test_malformed_spike_count_values_rejected() -> None:
    from brainos.adapters.base import NativePacket, PacketDecodeError

    base = dict(
        name="x",
        type="SpikeCounts",
        source_id="x",
        hostname="h",
        uid="u",
        channel_count=2,
        nominal_srate=50.0,
        channel_format="float32",
        created_at=0.0,
    )
    a = LSLAdapter(LSLSourceSpec(device_id="lsl:x", signal=StreamMeta(**base)))
    with pytest.raises(PacketDecodeError, match="non-integer or negative"):
        a.normalize(
            NativePacket(
                {"signal": {"data": np.array([[1.5, 2.0]]), "ts": [1.0], "first_index": 0}}
            )
        )
    with pytest.raises(PacketDecodeError, match="negative"):
        a.normalize(
            NativePacket(
                {"signal": {"data": np.array([[1.0, 2.0]]), "ts": [-1.0], "first_index": 0}}
            )
        )


# ------------------------------------------------------------- loss & reconnect (AT-4)


async def test_stream_loss_reconnects_when_source_returns(
    tmp_path: Any, pusher: list[Pusher]
) -> None:
    """M3-AT-4: outlet disappears -> reconnecting; same source_id returns -> streaming again."""
    out = Outlet(channels=2, fs=500.0, units=["microvolts", "microvolts"])
    p = Pusher(out)
    p.start()
    pusher.append(p)
    reg = DeviceRegistry(OperatorIntentSource(), tmp_path / "rec")
    reg.live._streams.clear()
    meta = find(out.source_id)
    from brainos.runtime.live_sources import DiscoveredStream

    reg.live._streams["k"] = DiscoveredStream("k", meta, True, None)
    reg.live.configure_lsl("k", None, None)
    rt = Runtime(reg, Recorder(tmp_path / "rec"), reconnect_backoff_s=(0.5, 1.0, 2.0, 3.0))
    sub = subscribe(rt)
    await rt.connect("lsl:k")
    await wait_for(lambda: rt.diagnostics.totals["recording.frame"] > 5, timeout=5)
    # publisher dies
    p.stop.set()
    p.join(2)
    out.close()
    await wait_for(lambda: rt.state is RuntimeState.RECONNECTING, timeout=10)
    # ...and comes back with the same source_id (new uid), as after a device restart
    out2 = Outlet(channels=2, fs=500.0, units=["microvolts", "microvolts"], source_id=out.source_id)
    p2 = Pusher(out2)
    p2.start()
    pusher.append(p2)
    await wait_for(lambda: rt.diagnostics.reconnect_successes >= 1, timeout=15)
    n = rt.diagnostics.totals["recording.frame"]
    await wait_for(lambda: rt.diagnostics.totals["recording.frame"] > n + 5, timeout=5)
    assert rt.state is RuntimeState.STREAMING
    states = [e["payload"]["state"] for e in events(drain(sub), "device.status")]
    assert "reconnecting" in states and states[-1] == "streaming"
    await rt.shutdown()
    out2.close()


async def test_stream_loss_without_return_ends_in_error(
    tmp_path: Any, pusher: list[Pusher]
) -> None:
    out = Outlet(channels=1, fs=500.0, units=["microvolts"])
    p = Pusher(out)
    p.start()
    pusher.append(p)
    reg = DeviceRegistry(OperatorIntentSource(), tmp_path / "rec")
    from brainos.runtime.live_sources import DiscoveredStream

    reg.live._streams["k"] = DiscoveredStream("k", find(out.source_id), True, None)
    reg.live.configure_lsl("k", None, None)
    rt = Runtime(reg, Recorder(tmp_path / "rec"), reconnect_backoff_s=(0.1, 0.1))
    await rt.connect("lsl:k")
    await wait_for(lambda: rt.diagnostics.totals["recording.frame"] > 2, timeout=5)
    p.stop.set()
    p.join(2)
    out.close()
    await wait_for(lambda: rt.state is RuntimeState.ERROR, timeout=30)
    assert "not found" in (rt.snapshot().last_error or "") or "lost" in (
        rt.snapshot().last_error or ""
    )
    await rt.shutdown()


async def test_open_fails_cleanly_when_stream_absent() -> None:
    base = dict(
        name="ghost",
        type="EEG",
        source_id=f"ghost-{uuid.uuid4().hex}",
        hostname="h",
        uid="u",
        channel_count=1,
        nominal_srate=100.0,
        channel_format="float32",
        created_at=0.0,
    )
    a = LSLAdapter(LSLSourceSpec(device_id="lsl:g", signal=StreamMeta(**base), open_timeout_s=0.5))
    with pytest.raises(DeviceLinkError, match="not found"):
        await a.open()


async def test_envelopes_validate_end_to_end(tmp_path: Any, pusher: list[Pusher]) -> None:
    """Frames from a real LSL stream become valid schema-1.2 envelopes through the runtime."""
    out = Outlet(channels=3, fs=1000.0, units=["microvolts"] * 3)
    p = Pusher(out)
    p.start()
    pusher.append(p)
    reg = DeviceRegistry(OperatorIntentSource(), tmp_path / "rec")
    from brainos.runtime.live_sources import DiscoveredStream

    reg.live._streams["k"] = DiscoveredStream("k", find(out.source_id), True, None)
    reg.live.configure_lsl("k", None, None)
    rt = Runtime(reg, Recorder(tmp_path / "rec"))
    sub = subscribe(rt)
    await rt.connect("lsl:k")
    await wait_for(lambda: rt.diagnostics.totals["recording.frame"] > 10, timeout=5)
    frames = [parse_envelope(e) for e in events(drain(sub), "recording.frame")]
    assert all(
        f.provenance.kind.value == "raw_signal" and not f.provenance.replayed for f in frames
    )
    idx = [f.payload.first_sample_index for f in frames]  # type: ignore[union-attr]
    assert idx == sorted(idx)
    ramp = np.concatenate([np.array(f.payload.samples[0]) for f in frames])  # type: ignore[union-attr]
    assert np.all(np.diff(ramp) == 1.0)  # every sample, in order, no duplicates or holes
    assert rt.diagnostics.validation_errors == 0
    await rt.shutdown()
    out.close()
    await asyncio.sleep(0)


def test_frames_split_at_gaps_inside_one_pulled_block() -> None:
    """Regression: a gap inside one liblsl pull must split the frame (frames are contiguous)."""
    from brainos.adapters.base import NativePacket

    base = dict(
        name="x",
        type="EEG",
        source_id="x",
        hostname="h",
        uid="u",
        channel_count=1,
        nominal_srate=100.0,
        channel_format="float32",
        created_at=0.0,
    )
    a = LSLAdapter(LSLSourceSpec(device_id="lsl:x", signal=StreamMeta(**base)))
    data = np.arange(30, dtype=np.float32)[:, None]
    ts = [1.0 + i * 0.01 for i in range(10)] + [
        1.5 + i * 0.01 for i in range(20)
    ]  # gap before index 10
    frames = a.normalize(
        NativePacket({"signal": {"data": data, "ts": ts, "first_index": 0, "gap_starts": [10]}})
    )
    assert [len(f.payload["samples"][0]) for f in frames] == [10, 20]
    assert [("dropped_samples" in f.quality.flags) for f in frames] == [False, True]
    assert (
        frames[1].device_timestamp_ns == round(1.5e9)
        and frames[1].payload["first_sample_index"] == 10
    )


def test_lost_stream_raises_link_error_and_is_counted() -> None:
    """Regression: pylsl >= 1.17 has LostError only in pylsl.util; a lost inlet must still
    become a DeviceLinkError (not an AttributeError) and be counted in `lost`."""
    from pylsl import util as pylsl_util

    base = dict(
        name="x",
        type="EEG",
        source_id="x",
        hostname="h",
        uid="u",
        channel_count=1,
        nominal_srate=100.0,
        channel_format="float32",
        created_at=0.0,
    )
    a = LSLAdapter(LSLSourceSpec(device_id="lsl:x", signal=StreamMeta(**base)))

    class LostInlet:
        def pull_chunk(self, **_: Any) -> Any:
            raise pylsl_util.LostError("the stream has been lost.")

    st = a._streams[0]
    st.inlet = LostInlet()
    with pytest.raises(DeviceLinkError, match="lost"):
        a._pull(st)
    assert a.stats.lost == 1
