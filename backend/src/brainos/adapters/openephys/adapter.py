"""Read-only adapter for the Open Ephys GUI "ZMQ Interface" plugin.

BrainOS connects *outward* to the plugin's PUB socket (``tcp://host:data_port``) and,
optionally, sends the plugin's heartbeat on its REP socket (``data_port + 1``) so the GUI
lists BrainOS as a client. Nothing else is ever sent: the heartbeat carries only the
application name and a random uuid; the plugin's "event" request type (which would inject
events into the GUI) is deliberately not implemented.

What BrainOS can and cannot know from this protocol:

* channels, names, sample rate and the sample clock come from the stream itself and are
  learned during :meth:`OpenEphysAdapter.open`;
* **physical units are not transmitted.** Frames are labelled ``arbitrary`` unless the
  operator states the unit in :class:`OpenEphysConfig` (then converted exactly to µV);
* whether the GUI is reading hardware, a file or a simulator is not visible.

See ``docs/OPEN_EPHYS.md``.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import re
import time
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Literal

import zmq
import zmq.asyncio
from pydantic import BaseModel, ConfigDict, Field, field_validator

from brainos.adapters.base import (
    DeviceAdapter,
    DeviceLinkError,
    EventDraft,
    NativePacket,
    PacketDecodeError,
)
from brainos.adapters.openephys.assembly import (
    BinSpec,
    BlockAssembler,
    ConfigurationChangedError,
    Counters,
    FrameChunk,
    Item,
    StreamLayout,
    TTLItem,
)
from brainos.adapters.openephys.protocol import (
    EVENT_TYPES,
    PLUGIN_REFERENCE,
    DataMessage,
    EventMessage,
    Message,
    SpikeMessage,
    heartbeat_request,
    parse_message,
)
from brainos.contracts.capabilities import Capability, CapabilityDescriptor, EventType
from brainos.contracts.events import Provenance, ProvenanceKind, Quality, QualityFlag
from brainos.contracts.protocol import DeviceDescriptor, DeviceKind

log = logging.getLogger(__name__)

ADAPTER_NAME = "brainos.openephys.zmq"
ADAPTER_VERSION = "0.1.0"
ADAPTER = f"{ADAPTER_NAME}@{ADAPTER_VERSION}"
APP_NAME = "BrainOS"
MAX_CONTRACT_CHANNELS = 1024
MAX_CONTRACT_RATE_HZ = 100_000.0
UNIT_TO_UV: dict[str, float] = {"uV": 1.0, "mV": 1e3, "V": 1e6}
NATIVE_FORMAT = (
    "Open Ephys ZMQ Interface: ZMQ PUB multipart [b'DATA\\0'|b'EVENT\\0', JSON header, "
    "float32 payload]; one message per channel per block"
)
LIVENESS_NOTE = (
    "Live stream from the Open Ephys GUI ZMQ Interface. BrainOS cannot verify whether the GUI "
    "is reading hardware, a file or a simulator."
)
UNITS_NOTE = "units not transmitted by the protocol"
_HOST_RE = re.compile(
    r"^[a-z0-9]([a-z0-9\-]{0,61}[a-z0-9])?(\.[a-z0-9]([a-z0-9\-]{0,61}[a-z0-9])?)*$"
)


class OpenEphysConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    host: str = Field(default="127.0.0.1", description="hostname or IPv4 address of the GUI")
    data_port: int = Field(default=5556, ge=1, le=65534, description="heartbeats use port+1")
    unit: Literal["unknown", "uV", "mV", "V"] = Field(
        default="unknown",
        description="Unit of the samples as configured in the GUI; the protocol does not say",
    )
    open_timeout_s: float = Field(default=4.0, gt=0, le=60)
    learn_s: float = Field(
        default=0.5, ge=0, le=30, description="minimum listening time in open() (spike electrodes)"
    )
    stall_timeout_s: float = Field(default=2.0, gt=0, le=600)
    heartbeat: bool = True
    heartbeat_interval_s: float = Field(default=2.0, gt=0, le=4.5)
    heartbeat_timeout_s: float = Field(default=1.0, gt=0, le=10)
    spike_bin_ms: float = Field(default=20.0, gt=0, le=10_000)
    spike_electrodes: list[str] | None = Field(
        default=None,
        description="Declare spike electrode names; if None they are learned from the stream",
    )
    max_frame_samples: int = Field(default=10_000, ge=1, le=10_000)
    rcvhwm: int = Field(default=20_000, ge=100, le=1_000_000, description="SUB queue (messages)")

    @field_validator("host")
    @classmethod
    def _host(cls, v: str) -> str:
        v = v.strip().lower()
        if not _HOST_RE.match(v) or len(v) > 40:
            raise ValueError("host must be a hostname or IPv4 address (max 40 chars)")
        return v


@dataclass(frozen=True, slots=True)
class OpenEphysPacket:
    """Everything :func:`normalize_packet` needs (normalization is pure)."""

    origin: str
    sample_rate: float
    uv_scale: float | None  # None -> unit "arbitrary", values unscaled
    bin_ms: float
    items: tuple[Item, ...]


@dataclass(frozen=True, slots=True)
class MalformedPacket:
    reason: str
    frame_sizes: tuple[int, ...]


def _ts_ns(sample: int, rate: float) -> int:
    return round(sample * 1_000_000_000 / rate)


def normalize_packet(pkt: OpenEphysPacket) -> list[EventDraft]:
    """Pure conversion of assembled items to drafts, ordered by device timestamp."""
    raw = Provenance(
        kind=ProvenanceKind.RAW_SIGNAL, adapter=ADAPTER, synthetic=False, origin=pkt.origin
    )
    label = Provenance(
        kind=ProvenanceKind.BEHAVIORAL_LABEL, adapter=ADAPTER, synthetic=False, origin=pkt.origin
    )
    feat = Provenance(
        kind=ProvenanceKind.PROCESSED_FEATURE, adapter=ADAPTER, synthetic=False, origin=pkt.origin
    )
    ok = Quality(score=1.0)
    dropped = Quality(score=0.5, flags=[QualityFlag.DROPPED_SAMPLES])
    unit = "arbitrary" if pkt.uv_scale is None else "uV"
    keyed: list[tuple[int, int, EventDraft]] = []
    for item in pkt.items:
        if isinstance(item, FrameChunk):
            data = item.samples.astype("float64")
            if pkt.uv_scale is not None and pkt.uv_scale != 1.0:
                data = data * pkt.uv_scale
            ts = _ts_ns(item.first_sample_index, pkt.sample_rate)
            draft = EventDraft(
                EventType.RECORDING_FRAME,
                {
                    "sample_rate_hz": pkt.sample_rate,
                    "channel_count": int(data.shape[0]),
                    "first_sample_index": item.first_sample_index,
                    "unit": unit,
                    "samples": data.tolist(),
                },
                dropped if item.dropped_before else ok,
                raw,
                ts,
            )
            keyed.append((ts, 0, draft))
        elif isinstance(item, TTLItem):
            ts = _ts_ns(item.sample_num, pkt.sample_rate)
            t = item.ttl
            value = None if t is None else f"line={t.line} state={t.state} word={t.word}"
            payload: dict[str, Any] = {"label": "ttl", "value": value}
            keyed.append(
                (ts, 1, EventDraft(EventType.RECORDING_ANNOTATION, payload, ok, label, ts))
            )
        else:
            ts = round((item.bin_index + 1) * pkt.bin_ms * 1_000_000)
            draft = EventDraft(
                EventType.FEATURES_BINNED,
                {
                    "feature": "spike_count",
                    "unit": "count",
                    "bin_ms": pkt.bin_ms,
                    "bin_index": item.bin_index,
                    "channel_count": len(item.counts),
                    "counts": list(item.counts),
                },
                dropped if item.incomplete else ok,
                feat,
                ts,
            )
            keyed.append((ts, 2, draft))
    keyed.sort(key=lambda k: (k[0], k[1]))
    return [d for _, _, d in keyed]


class OpenEphysAdapter(DeviceAdapter):
    """Live, read-only Open Ephys ZMQ Interface client."""

    def __init__(self, config: OpenEphysConfig | None = None) -> None:
        self.config = config or OpenEphysConfig()
        cfg = self.config
        self.endpoint = f"tcp://{cfg.host}:{cfg.data_port}"
        self.heartbeat_endpoint = f"tcp://{cfg.host}:{cfg.data_port + 1}"
        self.client_uuid = str(uuid.uuid4())
        self.counters = Counters()
        self.descriptor = self._descriptor(None, [])
        self.layout: StreamLayout | None = None
        self.electrodes: list[str] = []
        self._ctx: zmq.asyncio.Context | None = None
        self._sub: zmq.asyncio.Socket | None = None
        self._hb_task: asyncio.Task[None] | None = None
        self._assembler: BlockAssembler | None = None
        self._paused = False
        self._resync_on_resume = False
        self._last_message_num: int | None = None
        self._last_sender_ms: int | None = None
        self._offset_last_ms: float | None = None
        self._offset_min_ms: float | None = None
        self._hb_replies_this_open = 0
        self._hb_last_reply: str | None = None
        self._hb_last_reply_monotonic: float | None = None
        self._last_error: str | None = None

    # ------------------------------------------------------------- descriptor
    @property
    def _uv_scale(self) -> float | None:
        return UNIT_TO_UV.get(self.config.unit)

    @property
    def origin(self) -> str:
        """Provenance origin: ``openephys:<host>:<port>/<stream>`` (stream once learned)."""
        base = f"openephys:{self.config.host}:{self.config.data_port}"
        return (f"{base}/{self.layout.stream}" if self.layout else base)[:128]

    def _descriptor(self, layout: StreamLayout | None, electrodes: list[str]) -> DeviceDescriptor:
        cfg = self.config
        unit = "arbitrary" if self._uv_scale is None else "uV"
        rec: dict[str, Any] = {"unit": unit, "source_unit": cfg.unit}
        rec_desc = f"Continuous data; {UNITS_NOTE}"
        if cfg.unit == "unknown":
            rec_desc += "; values passed through unscaled (unit 'arbitrary')"
        else:
            rec_desc += f"; operator-declared unit {cfg.unit}, converted to µV"
        rec_desc += ". TTL events arrive as recording.annotation label 'ttl'."
        if layout is not None:
            rec.update(
                channel_count=layout.channel_count,
                sample_rate_hz=layout.sample_rate,
                channel_names=[name for _, name in layout.channels],
                stream=layout.stream,
                frame_samples=min(layout.block_samples, cfg.max_frame_samples),
            )
        caps = [
            CapabilityDescriptor(capability=Capability.RECORDING, params=rec, description=rec_desc)
        ]
        if electrodes:
            caps.append(
                CapabilityDescriptor(
                    capability=Capability.NEURAL_FEATURES,
                    params={
                        "feature": "spike_count",
                        "unit": "count",
                        "bin_ms": cfg.spike_bin_ms,
                        "channel_count": len(electrodes),
                        "channel_names": list(electrodes),
                    },
                    description=(
                        "Spike counts per electrode; spike detection by Open Ephys, binning on "
                        "the sample clock by BrainOS."
                    ),
                )
            )
        caps.append(CapabilityDescriptor(capability=Capability.DEVICE_STATUS))
        where = f"{cfg.host}:{cfg.data_port}"
        return DeviceDescriptor(
            device_id=f"openephys:{where}",
            display_name=f"Open Ephys (ZMQ) · {where}",
            kind=DeviceKind.STREAM,
            adapter=ADAPTER,
            description=LIVENESS_NOTE,
            native_format=NATIVE_FORMAT,
            capabilities=caps,
            synthetic=False,
        )

    # --------------------------------------------------------------- contract
    async def open(self) -> None:
        await self.close()
        cfg = self.config
        self.counters.opens += 1
        self._ctx = zmq.asyncio.Context()
        try:
            sub = self._ctx.socket(zmq.SUB)
            sub.setsockopt(zmq.LINGER, 0)
            sub.setsockopt(zmq.RCVHWM, cfg.rcvhwm)
            sub.setsockopt(zmq.SUBSCRIBE, b"")
            sub.connect(self.endpoint)
            self._sub = sub
            self._last_message_num = None
            self._hb_replies_this_open = 0
            self._offset_min_ms = None
            if cfg.heartbeat:
                self._hb_task = asyncio.create_task(self._heartbeat_loop(), name="oe-heartbeat")
            layout, seen = await self._learn()
            self._adopt(layout, seen)
        except BaseException as exc:
            self._last_error = str(exc)
            await self.close()
            raise
        self._last_error = None
        log.info(
            "openephys %s: stream '%s', %d ch @ %s Hz, unit %s, %d spike electrodes",
            self.endpoint,
            layout.stream,
            layout.channel_count,
            layout.sample_rate,
            cfg.unit,
            len(self.electrodes),
        )

    async def close(self) -> None:
        task, self._hb_task = self._hb_task, None
        if task is not None:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await task
        sub, self._sub = self._sub, None
        if sub is not None:
            sub.close(linger=0)
        ctx, self._ctx = self._ctx, None
        if ctx is not None:
            ctx.destroy(linger=0)
        self._assembler = None

    def set_paused(self, paused: bool) -> None:
        if self._paused and not paused:
            self._resync_on_resume = True
        self._paused = paused

    async def read(self) -> NativePacket:
        if self._sub is None or self._assembler is None or self.layout is None:
            raise DeviceLinkError(f"Open Ephys {self.endpoint}: not open")
        await asyncio.sleep(0)  # never starve the event loop when messages keep arriving
        stall = self.config.stall_timeout_s
        while True:
            frames = await self._recv(stall)
            if frames is None:
                self.counters.stalls += 1
                raise DeviceLinkError(
                    f"no message from Open Ephys at {self.endpoint} for {stall:g} s "
                    "(acquisition stopped, plugin removed, or network down)"
                )
            try:
                msg = parse_message(frames)
            except PacketDecodeError as exc:
                self.counters.malformed += 1
                return NativePacket(MalformedPacket(str(exc), tuple(len(f) for f in frames)))
            try:
                gap = self._track(msg)
                if self._paused:
                    self.counters.discarded_while_paused += 1
                    continue
                if self._resync_on_resume:
                    self._resync_on_resume = False
                    self._assembler.resync()
                if gap:
                    self._assembler.note_message_gap()
                items = self._dispatch(msg)
            except ConfigurationChangedError as exc:
                self.counters.config_changes += 1
                if exc.new_electrode and exc.new_electrode not in self.electrodes:
                    self.electrodes.append(exc.new_electrode)
                log.warning("openephys %s: %s", self.endpoint, exc)
                raise
            if items:
                return NativePacket(
                    OpenEphysPacket(
                        origin=self.origin,
                        sample_rate=self.layout.sample_rate,
                        uv_scale=self._uv_scale,
                        bin_ms=self.config.spike_bin_ms,
                        items=tuple(items),
                    )
                )

    def normalize(self, packet: NativePacket) -> Sequence[EventDraft]:
        data = packet.data
        if isinstance(data, MalformedPacket):
            raise PacketDecodeError(data.reason)
        if not isinstance(data, OpenEphysPacket):
            raise PacketDecodeError(f"unexpected packet type {type(data).__name__}")
        return normalize_packet(data)

    # -------------------------------------------------------------- internals
    async def _recv(self, timeout_s: float) -> list[bytes] | None:
        sub = self._sub
        if sub is None:
            raise DeviceLinkError(f"Open Ephys {self.endpoint}: socket closed")
        try:
            try:
                frames = await sub.recv_multipart(flags=zmq.NOBLOCK)
            except zmq.Again:
                if not await sub.poll(timeout=max(1, round(timeout_s * 1000))):
                    return None
                frames = await sub.recv_multipart(flags=zmq.NOBLOCK)
        except zmq.ZMQError as exc:
            raise DeviceLinkError(f"Open Ephys {self.endpoint}: socket error: {exc}") from exc
        self.counters.bytes += sum(len(f) for f in frames)
        return frames

    def _track(self, msg: Message) -> int:
        """Message accounting; returns the number of messages missed before ``msg``."""
        c = self.counters
        c.messages += 1
        now_ms = time.time() * 1000
        self._last_sender_ms = msg.timestamp_ms
        off = now_ms - msg.timestamp_ms
        self._offset_last_ms = off
        if self._offset_min_ms is None or off < self._offset_min_ms:
            self._offset_min_ms = off
        last, self._last_message_num = self._last_message_num, msg.message_num
        if last is None:
            return 0
        if msg.message_num <= last:
            raise ConfigurationChangedError(
                f"message_num went from {last} to {msg.message_num} (acquisition restarted)"
            )
        gap = msg.message_num - last - 1
        c.missed_messages += gap
        return gap

    def _dispatch(self, msg: Message) -> list[Item]:
        asm = self._assembler
        assert asm is not None
        if isinstance(msg, DataMessage):
            self.counters.data_messages += 1
            return asm.on_data(msg)
        if isinstance(msg, EventMessage):
            return asm.on_event(msg)
        asm.on_spike(msg)
        return []

    async def _learn(self) -> tuple[StreamLayout, list[str]]:
        """Listen until a complete block was seen (and at least ``learn_s``)."""
        cfg = self.config
        start = time.monotonic()
        deadline = start + cfg.open_timeout_s
        learn_until = start + min(cfg.learn_s, cfg.open_timeout_s)
        layout: StreamLayout | None = None
        block_sample: int | None = None
        block: list[tuple[int, str, int, str, float]] = []
        first_block = True
        seen = {"data": 0, "event": 0, "spike": 0, "malformed": 0}
        electrodes: dict[str, None] = {}
        while True:
            now = time.monotonic()
            if layout is not None and now >= learn_until:
                break
            if now >= deadline:
                break
            until = deadline if layout is None else learn_until
            frames = await self._recv(until - now)
            if frames is None:
                continue
            try:
                msg = parse_message(frames)
            except PacketDecodeError as exc:
                self.counters.malformed += 1
                seen["malformed"] += 1
                log.debug("openephys %s: malformed message during open: %s", self.endpoint, exc)
                continue
            try:
                self._track(msg)
            except ConfigurationChangedError:
                # acquisition restarted while we were learning: start over
                layout, block_sample, block, first_block = None, None, [], True
                self._last_message_num = msg.message_num
            if isinstance(msg, DataMessage):
                seen["data"] += 1
                if block_sample is not None and msg.sample_num != block_sample:
                    if not first_block and block:
                        layout = self._layout_from(block)
                    first_block = False
                    block = []
                block_sample = msg.sample_num
                block.append(
                    (
                        msg.channel_num,
                        msg.channel_name,
                        msg.num_samples,
                        msg.stream,
                        msg.sample_rate,
                    )
                )
            elif isinstance(msg, SpikeMessage):
                seen["spike"] += 1
                electrodes[msg.electrode] = None
            else:
                seen["event"] += 1
        if layout is None:
            raise DeviceLinkError(self._open_failure(seen))
        return layout, list(electrodes)

    def _layout_from(self, block: list[tuple[int, str, int, str, float]]) -> StreamLayout:
        streams = {b[3] for b in block}
        rates = {b[4] for b in block}
        lengths = {b[2] for b in block}
        nums = [b[0] for b in block]
        where = f"Open Ephys {self.endpoint}"
        if len(streams) != 1 or len(rates) != 1:
            raise DeviceLinkError(f"{where}: one block mixes streams or sample rates")
        if len(set(nums)) != len(nums):
            raise DeviceLinkError(f"{where}: a block repeats a channel; cannot learn the layout")
        if len(lengths) != 1:
            raise DeviceLinkError(f"{where}: channels of one block differ in length")
        rate = rates.pop()
        if rate > MAX_CONTRACT_RATE_HZ:
            raise DeviceLinkError(
                f"{where}: sample rate {rate} Hz exceeds the 100 kHz contract limit"
            )
        if len(nums) > MAX_CONTRACT_CHANNELS:
            raise DeviceLinkError(
                f"{where}: {len(nums)} channels selected; the contract allows at most "
                f"{MAX_CONTRACT_CHANNELS}. Select fewer channels in the ZMQ Interface."
            )
        return StreamLayout(
            stream=streams.pop(),
            sample_rate=rate,
            channels=tuple((b[0], b[1]) for b in block),
            block_samples=lengths.pop(),
        )

    def _open_failure(self, seen: dict[str, int]) -> str:
        cfg = self.config
        t = f"{cfg.open_timeout_s:g} s"
        if seen["data"]:
            return (
                f"Open Ephys {self.endpoint}: received {seen['data']} data messages but no "
                f"complete block within {t} (blocks longer than the timeout?)"
            )
        if seen["event"] or seen["spike"]:
            return (
                f"Open Ephys {self.endpoint}: received events/spikes but no continuous data within "
                f"{t}: select at least one channel in the ZMQ Interface"
            )
        if seen["malformed"]:
            return (
                f"{self.endpoint}: {seen['malformed']} messages received but none parsed as the "
                f"Open Ephys ZMQ Interface protocol ({PLUGIN_REFERENCE}); is this the right port?"
            )
        if not cfg.heartbeat:
            return (
                f"no messages from {self.endpoint} within {t} (heartbeats disabled, so it is "
                "unknown whether the plugin is reachable): is acquisition running?"
            )
        if self._hb_replies_this_open:
            return (
                f"the Open Ephys ZMQ Interface answered heartbeats on {self.heartbeat_endpoint}, "
                f"but no data arrived on {self.endpoint} within {t}: acquisition is not running, "
                "or no channels are selected in the ZMQ Interface"
            )
        return (
            f"no reply from an Open Ephys ZMQ Interface at {cfg.host} (data port "
            f"{cfg.data_port}, heartbeat port {cfg.data_port + 1}) within {t}: check the host and "
            "data port, that the ZMQ Interface is in the signal chain, and firewall settings"
        )

    def _adopt(self, layout: StreamLayout, seen_electrodes: list[str]) -> None:
        cfg = self.config
        prev = self.layout
        if prev is None or (prev.stream, prev.sample_rate) != (layout.stream, layout.sample_rate):
            self.electrodes = []
        if cfg.spike_electrodes is not None:
            self.electrodes = list(dict.fromkeys(cfg.spike_electrodes))
        else:
            for e in seen_electrodes:
                if e not in self.electrodes:
                    self.electrodes.append(e)
        self.layout = layout
        bins = BinSpec.create(cfg.spike_bin_ms, layout.sample_rate) if self.electrodes else None
        self._assembler = BlockAssembler(
            layout,
            self.counters,
            max_frame_samples=cfg.max_frame_samples,
            electrodes=self.electrodes,
            bin_spec=bins,
            fixed_electrodes=cfg.spike_electrodes is not None,
        )
        self._resync_on_resume = False
        self.descriptor = self._descriptor(layout, self.electrodes)

    async def _heartbeat_loop(self) -> None:
        """Lazy-pirate REQ heartbeats, as the official client does."""
        cfg = self.config
        ctx = self._ctx
        assert ctx is not None
        request = heartbeat_request(APP_NAME, self.client_uuid)
        req: zmq.asyncio.Socket | None = None
        try:
            while True:
                if req is None:
                    req = ctx.socket(zmq.REQ)
                    req.setsockopt(zmq.LINGER, 0)
                    req.connect(self.heartbeat_endpoint)
                try:
                    await req.send(request)
                    self.counters.heartbeats_sent += 1
                    timeout_ms = max(1, round(cfg.heartbeat_timeout_s * 1000))
                    if await req.poll(timeout=timeout_ms):
                        reply = await req.recv()
                        self.counters.heartbeat_replies += 1
                        self._hb_replies_this_open += 1
                        self._hb_last_reply = reply.decode("utf-8", "replace")[:64]
                        self._hb_last_reply_monotonic = time.monotonic()
                    else:
                        self.counters.heartbeat_timeouts += 1
                        req.close(linger=0)  # REQ is stuck awaiting a reply: recreate it
                        req = None
                except zmq.ZMQError as exc:
                    self.counters.heartbeat_errors += 1
                    log.warning("openephys %s: heartbeat error: %s", self.heartbeat_endpoint, exc)
                    if req is not None:
                        req.close(linger=0)
                    req = None
                await asyncio.sleep(cfg.heartbeat_interval_s)
        finally:
            if req is not None:
                req.close(linger=0)

    # ---------------------------------------------------------------- metadata
    def heartbeat_status(self) -> str:
        if not self.config.heartbeat:
            return "disabled"
        t = self._hb_last_reply_monotonic
        if t is None:
            return "no_reply" if self.counters.heartbeat_timeouts else "pending"
        return "ok" if time.monotonic() - t <= 5.0 else "stale"

    def source_metadata(self) -> dict[str, Any]:
        cfg = self.config
        lay = self.layout
        return {
            "protocol": "openephys-zmq",
            "plugin_protocol_reference": PLUGIN_REFERENCE,
            "adapter": ADAPTER,
            "host": cfg.host,
            "data_port": cfg.data_port,
            "heartbeat_port": cfg.data_port + 1,
            "client_uuid": self.client_uuid,
            "stream": lay.stream if lay else None,
            "sample_rate_hz": lay.sample_rate if lay else None,
            "block_samples": lay.block_samples if lay else None,
            "channels": [
                {"index": i, "channel_num": num, "name": name}
                for i, (num, name) in enumerate(lay.channels if lay else ())
            ],
            "spike_electrodes": list(self.electrodes),
            "spike_electrodes_source": "configured"
            if cfg.spike_electrodes is not None
            else "learned",
            "spike_bin_ms": cfg.spike_bin_ms,
            "unit_configured": cfg.unit,
            "unit_emitted": "arbitrary" if self._uv_scale is None else "uV",
            "unit_note": UNITS_NOTE,
            "liveness_note": LIVENESS_NOTE,
            "event_types": {str(k): v for k, v in EVENT_TYPES.items()},
            "heartbeat": {
                "status": self.heartbeat_status(),
                "last_reply": self._hb_last_reply,
                "application": APP_NAME,
            },
            "counters": self.counters.as_dict(),
            "last_message_num": self._last_message_num,
            "last_sender_timestamp_ms": self._last_sender_ms,
            "sender_to_local_offset_ms": {
                "last": None if self._offset_last_ms is None else round(self._offset_last_ms, 3),
                "min": None if self._offset_min_ms is None else round(self._offset_min_ms, 3),
                "note": "local wall clock minus sender timestamp, including transport latency; "
                "'min' is the best estimate of the clock offset",
            },
            "assembler": self._assembler.state() if self._assembler else None,
            "last_error": self._last_error,
        }
