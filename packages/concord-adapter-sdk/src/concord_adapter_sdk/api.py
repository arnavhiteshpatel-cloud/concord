"""Concord adapter SDK — public API, version 1.0.

This is the ONLY interface a third-party source plugin uses. It does not import Concord.
A plugin is a normal Python distribution that exposes a :class:`SourcePlugin` subclass via
the ``concord.sources`` entry-point group::

    [project.entry-points."concord.sources"]
    my-device = "my_package.plugin:MyDevicePlugin"

Concord runs plugin code in a separate process (the plugin host), validates everything the
plugin declares and emits, and converts it to standard Concord events. Plugins are
**read-only**: there is no method to send anything to a device, and plugins cannot emit
application commands (pointer movement, selection, text). Commands only ever come from
the operator-controlled command router in Concord.

Design rules a plugin must follow (the host and the certification toolkit check them):

* Declare what you know; leave unknowns as ``None``. Never invent units, modality or
  clock information. Unknown units are shown to users as "arbitrary".
* Timestamps are the source's own, in seconds, in the clock domain you declare.
* ``first_index`` counts samples since ``open()`` per stream; gaps in it are data loss.
* Raise :class:`LinkLost` when the device link drops (Concord may reopen the session);
  raise :class:`OpenFailed` with an operator-readable message when opening fails.
"""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, ClassVar, Literal

import numpy as np
from numpy.typing import NDArray

API_VERSION = "1.0"
ENTRY_POINT_GROUP = "concord.sources"
KEY_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_.\-]{0,39}$")


class Modality(StrEnum):
    """Recording modality (same values as the Concord contract)."""

    EEG = "eeg"
    MEG = "meg"
    EMG = "emg"
    ECOG = "ecog"
    SEEG = "seeg"
    INTRACORTICAL = "intracortical"
    OTHER = "other"


class StreamRole(StrEnum):
    """What a stream carries. Each maps to one Concord event type."""

    SIGNAL = "signal"  # continuous samples, e.g. voltages -> recording.frame (raw_signal)
    SPIKE_COUNTS = "spike_counts"  # non-negative counts per channel per bin -> features.binned
    BEHAVIOR = "behavior"  # behavioral labels / task variables -> behavior.sample
    MARKERS = "markers"  # text event markers -> recording.annotation
    # The output of an EXTERNAL decoder (e.g. a BCI2000 control signal). Becomes
    # intent.kinematics with provenance decoded_intent and the declared model_id. It never
    # reaches applications as a command unless the operator enables the command router.
    DECODER_OUTPUT = "decoder_output"


PRIMARY_ROLES = frozenset({StreamRole.SIGNAL, StreamRole.SPIKE_COUNTS, StreamRole.DECODER_OUTPUT})


@dataclass(frozen=True, slots=True)
class Channel:
    label: str
    unit: str | None = None  # e.g. "microvolts"; None = unknown (shown as "arbitrary")
    type: str | None = None  # e.g. "EEG", "EMG", "ACCEL", "AUX", "SpikeCount"


@dataclass(frozen=True, slots=True)
class ClockInfo:
    """Which clock a stream's timestamps are on.

    ``source``: the device's or software's own clock (monotonic seconds, arbitrary origin);
    ``unix``: seconds since 1970-01-01 UTC (wall clock); ``lsl``: liblsl local_clock;
    ``sample_counter``: timestamps derived from sample index / nominal rate.
    """

    domain: Literal["source", "unix", "lsl", "sample_counter"]
    description: str = ""


@dataclass(frozen=True, slots=True)
class StreamSpec:
    stream_id: str
    role: StreamRole
    channels: tuple[Channel, ...]
    nominal_rate_hz: float  # 0.0 = irregular (markers, event-driven streams)
    clock: ClockInfo
    modality: Modality | None = None  # SIGNAL / SPIKE_COUNTS only; None = unknown
    invasive: bool | None = None  # None = unknown; must agree with modality if both given
    # SPIKE_COUNTS only (required there). A spike-count sample's timestamp is the END of
    # its bin (the bin spans ``bin_ms`` before it), as in Concord ``features.binned``.
    bin_ms: float | None = None
    quantity: str | None = None  # BEHAVIOR / DECODER_OUTPUT, e.g. "velocity", "target_code"
    model_id: str | None = None  # DECODER_OUTPUT only (required there): the external decoder


@dataclass(frozen=True, slots=True)
class DeviceInfo:
    """A device or source found by :meth:`SourcePlugin.discover`."""

    device_key: str  # stable, matches KEY_PATTERN; becomes part of the Concord device id
    display_name: str
    description: str = ""
    details: Mapping[str, str] = field(default_factory=dict)  # e.g. serial number, host


@dataclass(frozen=True, slots=True)
class SessionInfo:
    """What an open session will deliver. Must not change while the session is open
    (raise :class:`ConfigurationChanged` instead)."""

    streams: tuple[StreamSpec, ...]
    primary_stream: str  # a stream with a role in PRIMARY_ROLES; defines the device clock
    synthetic: bool  # the data is generated (a simulator, a synthetic board)
    prerecorded: bool  # the data was recorded earlier and is being played back
    origin: str  # where the data comes from, e.g. "brainflow:SYNTHETIC_BOARD", "bci2000:host:20320"


@dataclass(frozen=True, slots=True)
class Chunk:
    """Consecutive samples of one numeric stream."""

    stream_id: str
    data: NDArray[np.floating[Any] | np.integer[Any]]  # shape (n_samples, n_channels)
    # shape (n_samples,), seconds (>= 0) on the stream's clock, non-decreasing across calls
    timestamps: NDArray[np.float64]
    first_index: int  # index of data[0] counted from 0 at open(); a jump means lost samples


@dataclass(frozen=True, slots=True)
class MarkerChunk:
    """Text markers of one MARKERS stream."""

    stream_id: str
    labels: tuple[str, ...]
    timestamps: NDArray[np.float64]  # one per label, seconds, the stream's clock


@dataclass(frozen=True, slots=True)
class OptionSpec:
    """An operator-configurable option for :meth:`SourcePlugin.open` (e.g. a serial port)."""

    type: Literal["str", "int", "float", "bool", "choice"]
    description: str
    default: Any = None
    required: bool = False
    choices: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class PluginManifest:
    name: str  # distribution name, e.g. "concord-brainflow"
    version: str  # the plugin's own semantic version, e.g. "0.1.0"
    api_version: str  # the adapter SDK API version it was written for, e.g. "1.0"
    display_name: str
    description: str
    author: str
    license: str
    roles: frozenset[StreamRole]  # every role the plugin may emit
    homepage: str = ""
    ecosystem: str | None = None  # external software it integrates, e.g. "brainflow", "bci2000"
    network: bool = False  # True if the plugin opens network sockets (shown to the operator)
    options: Mapping[str, OptionSpec] = field(default_factory=dict)


# ----------------------------------------------------------------------------- errors


class PluginError(Exception):
    """Base class; the message is shown to the operator, so make it actionable."""


class OpenFailed(PluginError):
    """The session could not be opened (device absent, port busy, wrong options...)."""


class InvalidOptions(OpenFailed):
    """The options passed to open() are invalid."""


class LinkLost(PluginError):
    """The link to the device dropped. Concord may call open() again to reconnect."""


class ConfigurationChanged(LinkLost):
    """The device's channels, rate or format changed; the session must be reopened."""


# ----------------------------------------------------------------------------- plugin


class SourceSession(ABC):
    """One open connection to a device. Called from a single thread."""

    @property
    @abstractmethod
    def info(self) -> SessionInfo:
        """Streams this session delivers. Constant for the session's lifetime."""

    @abstractmethod
    def read(self, timeout_s: float) -> Sequence[Chunk | MarkerChunk]:
        """Return available data, blocking for at most ``timeout_s`` seconds.

        Return an empty sequence when nothing arrived. Raise :class:`LinkLost` when the
        link dropped. Never return data from before ``open()``.
        """

    @abstractmethod
    def close(self) -> None:
        """Release the device. Idempotent; must not raise."""

    def stats(self) -> Mapping[str, int | float]:
        """Optional integrity counters shown to the operator (e.g. ``dropped_packets``)."""
        return {}


class SourcePlugin(ABC):
    """Entry point of a plugin. Instantiated without arguments by the plugin host."""

    manifest: ClassVar[PluginManifest]

    def discover(self, timeout_s: float) -> Sequence[DeviceInfo]:
        """List devices this plugin can open right now (may scan for up to ``timeout_s``).

        Plugins whose devices cannot be enumerated return a single configurable entry.
        """
        return []

    @abstractmethod
    def open(self, device_key: str, options: Mapping[str, Any]) -> SourceSession:
        """Open a session. Raise :class:`OpenFailed` (or :class:`InvalidOptions`)."""
