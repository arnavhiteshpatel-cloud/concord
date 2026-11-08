"""Replay sources.

``ReplaySource`` is the extension point for offline data. v1 implements
``ConcordRecordingSource`` for files written by the runtime recorder:

    line 1:  {"format": "concord.recording/1", "schema_version": "1.0",
              "created_at_ns": ..., "device": <DeviceDescriptor>, "synthetic": bool}
    line 2+: one EventEnvelope per line, in seq order.

A future reader for public intracranial datasets implements the same protocol
and must map continuous data to ``recording.frame`` (raw_signal) and
trial/behavior tables to ``recording.annotation`` (behavioral_label). It must
never emit intents: behavioral labels are not intents.
"""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict

from concord.contracts.events import SCHEMA_MAJOR
from concord.contracts.protocol import DeviceDescriptor, DeviceKind

log = logging.getLogger(__name__)

RECORDING_FORMAT = "concord.recording/1"
RECORDING_SUFFIX = ".concord.jsonl"
NAME_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_\-]{0,47}$")


class RecordingFormatError(ValueError):
    pass


class RecordingHeader(BaseModel):
    model_config = ConfigDict(extra="forbid")

    format: str
    schema_version: str
    created_at_ns: int
    device: DeviceDescriptor
    synthetic: bool
    note: str = ""
    # Milestone 5 (optional, additive): the adapter's description of the source when the
    # recording started (e.g. LSL uid, source_id, host, time correction), what the
    # timestamps can reconstruct, and the limits the recording ran under.
    source_metadata: dict[str, Any] | None = None
    timing: str | None = None
    limits: dict[str, float] | None = None


@dataclass(frozen=True, slots=True)
class ReplayRecord:
    """One record: original timing plus the standardized fields to re-emit."""

    t_ns: int  # original runtime timestamp (used for relative timing)
    envelope: dict[str, Any]


class ReplaySource(Protocol):
    """A finite, re-iterable source of recorded envelopes for ``ReplayAdapter``.

    Implementations: ``ConcordRecordingSource`` (runtime recordings) and
    ``concord.adapters.nwb.NWBUnitsSource`` (public NWB datasets).
    """

    name: str
    origin: str  # provenance.origin for every replayed event

    def descriptor(self) -> DeviceDescriptor: ...

    def records(self) -> Iterator[ReplayRecord]: ...

    def duration_ns(self) -> int | None: ...


def recording_path(directory: Path, name: str) -> Path:
    if not NAME_PATTERN.match(name):
        raise RecordingFormatError(f"invalid recording name {name!r}")
    return directory / f"{name}{RECORDING_SUFFIX}"


def read_header(path: Path) -> RecordingHeader:
    """Read and validate the header. Any malformed file raises RecordingFormatError."""
    try:
        with path.open("r", encoding="utf-8") as fh:
            first = fh.readline()
        header = RecordingHeader.model_validate_json(first)
        major = int(header.schema_version.split(".")[0])
    except ValueError as exc:  # includes UnicodeDecodeError and pydantic ValidationError
        raise RecordingFormatError(f"{path.name}: invalid header: {exc}") from exc
    if header.format != RECORDING_FORMAT:
        raise RecordingFormatError(f"{path.name}: unsupported format {header.format!r}")
    if major != SCHEMA_MAJOR:
        raise RecordingFormatError(f"{path.name}: unsupported schema {header.schema_version}")
    return header


class ConcordRecordingSource:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.name = path.name.removesuffix(RECORDING_SUFFIX)
        self._header = read_header(path)
        self.skipped_lines = 0
        self.origin = f"replay:{self.name}"

    def header(self) -> RecordingHeader:
        return self._header

    def descriptor(self) -> DeviceDescriptor:
        header = self._header
        return DeviceDescriptor(
            device_id=f"replay:{self.name}",
            display_name=f"Replay · {self.name}",
            kind=DeviceKind.REPLAY,
            adapter="concord.replay@0.1.0",
            description=f"Replay of a recording from {header.device.display_name} "
            f"({header.device.device_id}). Events are marked replayed.",
            native_format="Concord recording (JSONL envelopes)",
            capabilities=header.device.capabilities,
            synthetic=header.synthetic,
        )

    def duration_ns(self) -> int | None:
        return None  # not known without scanning the file

    def records(self) -> Iterator[ReplayRecord]:
        with self.path.open("r", encoding="utf-8") as fh:
            fh.readline()  # header
            for lineno, line in enumerate(fh, start=2):
                if not line.strip():
                    continue
                try:
                    env = json.loads(line)
                    t_ns = int(env["timestamp_ns"])
                except (ValueError, KeyError, TypeError) as exc:
                    # e.g. a last line truncated by a crash mid-write: skip, don't fail the replay
                    self.skipped_lines += 1
                    log.warning(
                        "%s:%d: skipping unreadable record: %s", self.path.name, lineno, exc
                    )
                    continue
                yield ReplayRecord(t_ns=t_ns, envelope=env)
