"""Replay adapter: re-emits a recorded session through the standard pipeline.

Replayed events keep their original provenance kind (a replayed simulated
intent is still a simulated intent; a replayed raw signal is still raw signal),
and are marked ``provenance.replayed = true`` with a ``replayed`` quality flag.
Runtime-originated status events from the original session are not replayed.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Iterator, Sequence

from pydantic import ValidationError

from brainos.adapters.base import (
    DeviceAdapter,
    DeviceLinkError,
    EndOfStream,
    EventDraft,
    NativePacket,
    PacketDecodeError,
)
from brainos.adapters.replay.format import RecordingFormatError, ReplayRecord, ReplaySource
from brainos.contracts.capabilities import EventType
from brainos.contracts.events import Provenance, ProvenanceKind, Quality, QualityFlag
from brainos.contracts.protocol import DeviceDescriptor, DeviceKind

ADAPTER_ID = "brainos.replay@0.1.0"
LOOP_GAP_NS = 500_000_000  # pause between loops


def replay_device_id(name: str) -> str:
    return f"replay:{name}"


def replay_descriptor(source: ReplaySource) -> DeviceDescriptor:
    header = source.header()
    return DeviceDescriptor(
        device_id=replay_device_id(source.name),
        display_name=f"Replay · {source.name}",
        kind=DeviceKind.REPLAY,
        adapter=ADAPTER_ID,
        description=f"Replay of a recording from {header.device.display_name} "
        f"({header.device.device_id}). Events are marked replayed.",
        native_format="BrainOS recording (JSONL envelopes)",
        capabilities=header.device.capabilities,
        synthetic=header.synthetic,
    )


class ReplayAdapter(DeviceAdapter):
    def __init__(self, source: ReplaySource, *, speed: float = 1.0, loop: bool = True) -> None:
        if speed <= 0:
            raise ValueError("speed must be > 0")
        self._source = source
        self.descriptor = replay_descriptor(source)
        self._speed = speed
        self._loop = loop
        self._it: Iterator[ReplayRecord] | None = None
        self._t0_rec: int | None = None
        self._t0_wall = 0.0
        self._paused_at: float | None = None
        self._running = asyncio.Event()
        self._running.set()
        self._dev_ts_offset = 0
        self._first_dev_ts: int | None = None
        self._last_dev_ts: int | None = None
        self.loops = 0

    async def open(self) -> None:
        try:
            self._it = self._source.records()
        except OSError as exc:
            raise DeviceLinkError(f"cannot open recording: {exc}") from exc
        self._t0_rec = None

    async def close(self) -> None:
        self._it = None

    def set_paused(self, paused: bool) -> None:
        now = time.monotonic()
        if paused and self._paused_at is None:
            self._paused_at = now
            self._running.clear()
        elif not paused and self._paused_at is not None:
            self._t0_wall += now - self._paused_at  # shift timeline by paused duration
            self._paused_at = None
            self._running.set()

    def _next_record(self) -> ReplayRecord:
        assert self._it is not None
        while True:
            try:
                rec = next(self._it)
            except StopIteration:
                if not self._loop:
                    raise EndOfStream(f"{self.device_id}: end of recording") from None
                if self._first_dev_ts is not None and self._last_dev_ts is not None:
                    self._dev_ts_offset += self._last_dev_ts - self._first_dev_ts + LOOP_GAP_NS
                self._first_dev_ts = None
                self.loops += 1
                self._it = self._source.records()
                self._t0_rec = None
                continue
            except (OSError, RecordingFormatError) as exc:
                raise DeviceLinkError(f"{self.device_id}: read failed: {exc}") from exc
            prov = rec.envelope.get("provenance")
            if isinstance(prov, dict) and prov.get("kind") == ProvenanceKind.RUNTIME.value:
                continue
            return rec

    async def read(self) -> NativePacket:
        if self._it is None:
            raise DeviceLinkError(f"{self.device_id}: not open")
        await self._running.wait()
        rec = self._next_record()
        if self._t0_rec is None:
            self._t0_rec = rec.t_ns
            self._t0_wall = time.monotonic() + (LOOP_GAP_NS / 1e9 if self.loops else 0.0)
        due = self._t0_wall + (rec.t_ns - self._t0_rec) / 1e9 / self._speed
        delay = due - time.monotonic()
        if delay > 0:
            await asyncio.sleep(delay)
        dev_ts = rec.envelope.get("device_timestamp_ns")
        if isinstance(dev_ts, int):
            if self._first_dev_ts is None:
                self._first_dev_ts = dev_ts
            self._last_dev_ts = dev_ts
        return NativePacket({"record": rec.envelope, "dev_ts_offset": self._dev_ts_offset})

    def normalize(self, packet: NativePacket) -> Sequence[EventDraft]:
        data = packet.data
        try:
            env = data["record"]
            event_type = EventType(env["event_type"])
            prov = Provenance.model_validate(env["provenance"])
            q = Quality.model_validate(env["quality"])
            dev_ts = env.get("device_timestamp_ns")
            if dev_ts is not None:
                dev_ts = int(dev_ts) + int(data["dev_ts_offset"])
            payload = env["payload"]
            if not isinstance(payload, dict):
                raise TypeError("payload must be an object")
        except (KeyError, TypeError, ValueError, ValidationError) as exc:
            raise PacketDecodeError(f"invalid recorded event: {exc}") from exc
        flags = list(q.flags)
        if QualityFlag.REPLAYED not in flags:
            flags.append(QualityFlag.REPLAYED)
        return [
            EventDraft(
                event_type=event_type,
                payload=payload,
                quality=Quality(score=q.score, flags=flags),
                provenance=prov.model_copy(
                    update={"replayed": True, "origin": f"replay:{self._source.name}"}
                ),
                device_timestamp_ns=dev_ts,
            )
        ]
