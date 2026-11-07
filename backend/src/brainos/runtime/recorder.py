"""Session recorder: writes published envelopes to a BrainOS recording file."""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import IO

from pydantic import BaseModel

from brainos.adapters.replay.format import (
    RECORDING_FORMAT,
    RECORDING_SUFFIX,
    RecordingFormatError,
    RecordingHeader,
    read_header,
    recording_path,
)
from brainos.contracts.events import SCHEMA_VERSION, EventEnvelope
from brainos.contracts.protocol import DeviceDescriptor

log = logging.getLogger(__name__)

MAX_DURATION_S = 300.0
MAX_BYTES = 200 * 1024 * 1024


class RecordingInfo(BaseModel):
    name: str
    device_id: str
    device_name: str
    synthetic: bool
    created_at_ns: int
    size_bytes: int
    events: int | None = None
    active: bool = False


class RecorderError(Exception):
    pass


class Recorder:
    def __init__(self, directory: Path) -> None:
        self.directory = directory
        self._fh: IO[str] | None = None
        self._name: str | None = None
        self._started = 0.0
        self._bytes = 0
        self._events = 0
        self._device: DeviceDescriptor | None = None
        self.stop_reason: str | None = None

    @property
    def active_name(self) -> str | None:
        return self._name

    def start(self, device: DeviceDescriptor, name: str | None = None) -> str:
        if self._fh is not None:
            raise RecorderError(f"already recording {self._name!r}")
        if device.kind.value == "replay":
            raise RecorderError("re-recording a replay is not supported")
        self.directory.mkdir(parents=True, exist_ok=True)
        name = name or time.strftime(f"{device.device_id}-%Y%m%d-%H%M%S").lower()
        try:
            path = recording_path(self.directory, name)
        except RecordingFormatError as exc:
            raise RecorderError(str(exc)) from exc
        if path.exists():
            raise RecorderError(f"recording {name!r} already exists")
        header = RecordingHeader(
            format=RECORDING_FORMAT,
            schema_version=SCHEMA_VERSION,
            created_at_ns=time.time_ns(),
            device=device,
            synthetic=device.synthetic,
            note="Synthetic data from a BrainOS simulated profile." if device.synthetic else "",
        )
        self._fh = path.open("w", encoding="utf-8")
        line = header.model_dump_json() + "\n"
        self._fh.write(line)
        self._fh.flush()  # header must be readable while recording (device listing)
        self._name, self._device = name, device
        self._started, self._bytes, self._events = time.monotonic(), len(line), 0
        self.stop_reason = None
        log.info("recording %s started for %s", name, device.device_id)
        return name

    def on_event(self, envelope: EventEnvelope, event_json: str) -> None:
        if self._fh is None:
            return
        self._fh.write(event_json)
        self._fh.write("\n")
        self._bytes += len(event_json) + 1
        self._events += 1
        if time.monotonic() - self._started > MAX_DURATION_S:
            self.stop("max duration reached")
        elif self._bytes > MAX_BYTES:
            self.stop("max size reached")

    def stop(self, reason: str = "stopped") -> RecordingInfo | None:
        if self._fh is None or self._name is None or self._device is None:
            return None
        self._fh.close()
        self._fh = None
        name, self._name = self._name, None
        self.stop_reason = reason
        log.info("recording %s stopped (%s, %d events)", name, reason, self._events)
        path = recording_path(self.directory, name)
        info = self._info(path)
        return info.model_copy(update={"events": self._events}) if info else None

    def _info(self, path: Path) -> RecordingInfo | None:
        try:
            h = read_header(path)
        except (RecordingFormatError, OSError) as exc:
            log.warning("skipping unreadable recording %s: %s", path.name, exc)
            return None
        name = path.name.removesuffix(RECORDING_SUFFIX)
        return RecordingInfo(
            name=name,
            device_id=h.device.device_id,
            device_name=h.device.display_name,
            synthetic=h.synthetic,
            created_at_ns=h.created_at_ns,
            size_bytes=path.stat().st_size,
            active=name == self._name,
        )

    def list(self) -> list[RecordingInfo]:
        if not self.directory.exists():
            return []
        infos = [self._info(p) for p in sorted(self.directory.glob(f"*{RECORDING_SUFFIX}"))]
        return sorted((i for i in infos if i), key=lambda i: i.created_at_ns, reverse=True)
