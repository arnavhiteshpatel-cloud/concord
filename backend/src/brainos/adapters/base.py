"""Device-adapter contract.

An adapter is the *only* device-specific code in BrainOS. It has two halves:

* ``read()`` — device-specific I/O returning opaque :class:`NativePacket` objects.
* ``normalize()`` — pure, device-specific decoding of one native packet into zero
  or more :class:`EventDraft` objects using the standard payload vocabulary.

The runtime stamps drafts (seq, session, timestamps), validates them against
the envelope schema, and routes them. Adapters cannot forge seq or session.

Read-only guarantee: this contract deliberately has **no** method that sends
data or commands to a device.
"""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from brainos.contracts.capabilities import EventType
from brainos.contracts.events import Provenance, Quality
from brainos.contracts.protocol import DeviceDescriptor, PlaybackStatus


class AdapterError(Exception):
    """Base class for adapter errors."""


class DeviceLinkError(AdapterError):
    """The link to the device failed (may be recoverable by reopening)."""


class PacketDecodeError(AdapterError):
    """A native packet could not be decoded. The packet is dropped."""


class EndOfStream(AdapterError):
    """A finite source (e.g. replay) has no more packets."""


@dataclass(frozen=True, slots=True)
class NativePacket:
    """An opaque device-specific packet plus the monotonic time it was read."""

    data: Any
    read_monotonic_ns: int = field(default_factory=time.monotonic_ns)


@dataclass(frozen=True, slots=True)
class EventDraft:
    """Adapter output: a standardized event without runtime-assigned fields."""

    event_type: EventType
    payload: dict[str, Any]
    quality: Quality
    provenance: Provenance
    device_timestamp_ns: int | None = None


class DeviceAdapter(ABC):
    """Abstract base for every device adapter (simulated, replay, hardware)."""

    descriptor: DeviceDescriptor

    @property
    def device_id(self) -> str:
        return self.descriptor.device_id

    @abstractmethod
    async def open(self) -> None:
        """Open the link. Raises :class:`DeviceLinkError` on failure."""

    @abstractmethod
    async def close(self) -> None:
        """Close the link. Must be idempotent and must not raise."""

    @abstractmethod
    def set_paused(self, paused: bool) -> None:
        """Best-effort acquisition pause. Runtime also gates delivery itself."""

    @abstractmethod
    async def read(self) -> NativePacket:
        """Await the next native packet.

        Raises :class:`DeviceLinkError` if the link fails and
        :class:`EndOfStream` if a finite source is exhausted.
        """

    @abstractmethod
    def normalize(self, packet: NativePacket) -> Sequence[EventDraft]:
        """Decode one native packet. Pure. Raises :class:`PacketDecodeError`."""


@runtime_checkable
class PlaybackControl(Protocol):
    """Optional interface for adapters over finite recordings (speed, position).

    Live devices do not implement it; the runtime then reports ``unsupported_operation``.
    """

    def set_speed(self, speed: float) -> None: ...

    def playback_status(self) -> PlaybackStatus: ...
