"""Wire models shared by the server, SDKs and console (no I/O)."""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from brainos.contracts.capabilities import Capability, CapabilityDescriptor
from brainos.contracts.events import DEVICE_ID_PATTERN

STREAM_PROTOCOL = "brainos.stream/1"


class _Wire(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ErrorCode(StrEnum):
    PROTOCOL_ERROR = "protocol_error"
    HELLO_REQUIRED = "hello_required"
    UNSUPPORTED_PROTOCOL = "unsupported_protocol"
    UNKNOWN_CAPABILITY = "unknown_capability"
    CAPABILITY_UNSUPPORTED = "capability_unsupported"
    READ_ONLY_RUNTIME = "read_only_runtime"
    DEVICE_NOT_FOUND = "device_not_found"
    INVALID_STATE = "invalid_state"
    UNSUPPORTED_OPERATION = "unsupported_operation"
    INCOMPATIBLE_DECODER = "incompatible_decoder"
    DEVICE_ERROR = "device_error"
    SIMULATION_DISABLED = "simulation_disabled"
    RECORDING_ERROR = "recording_error"


# ---------------------------------------------------------------------------- devices


class DeviceKind(StrEnum):
    SIMULATED = "simulated"
    REPLAY = "replay"
    HARDWARE = "hardware"  # reserved: a vendor adapter that talks to a known device directly
    # 1.2: an external acquisition stream (LSL, Open Ephys ZMQ). BrainOS cannot verify whether
    # it originates from hardware, a file player or a simulator; it is labelled accordingly.
    STREAM = "stream"


class Modality(StrEnum):
    """Recording modality of a source's neural signal (schema 1.3). None = unknown."""

    EEG = "eeg"  # scalp EEG (noninvasive)
    MEG = "meg"  # noninvasive
    EMG = "emg"  # surface EMG (noninvasive)
    ECOG = "ecog"  # electrocorticography (implanted, cortical surface)
    SEEG = "seeg"  # stereo-EEG depth electrodes (implanted)
    INTRACORTICAL = "intracortical"  # penetrating microelectrodes (implanted)
    OTHER = "other"


NONINVASIVE_MODALITIES = frozenset({Modality.EEG, Modality.MEG, Modality.EMG})
INVASIVE_MODALITIES = frozenset({Modality.ECOG, Modality.SEEG, Modality.INTRACORTICAL})


class IntegrationInfo(_Wire):
    """How BrainOS reaches the source (schema 1.3): a built-in adapter or an external plugin."""

    kind: Literal["builtin", "plugin"]
    package: str | None = Field(
        default=None, max_length=128, description="plugin distribution name"
    )
    version: str | None = Field(default=None, max_length=64)
    api_version: str | None = Field(
        default=None, max_length=16, description="adapter SDK API version"
    )
    isolated: bool = Field(default=False, description="third-party code runs in a separate process")
    ecosystem: str | None = Field(
        default=None, max_length=64, description="external software ecosystem, e.g. 'brainflow'"
    )


class DeviceDescriptor(_Wire):
    device_id: str = Field(pattern=DEVICE_ID_PATTERN)
    display_name: str
    kind: DeviceKind
    adapter: str = Field(description="adapter name@semver")
    description: str = ""
    native_format: str = Field(description="Human-readable description of the wire format")
    capabilities: list[CapabilityDescriptor]
    synthetic: bool
    # schema 1.3 (all optional; None = not declared, never guessed)
    modality: Modality | None = None
    invasive: bool | None = None
    integration: IntegrationInfo | None = None

    def supports(self, capability: Capability) -> bool:
        return any(c.capability is capability for c in self.capabilities)

    @property
    def capability_set(self) -> frozenset[Capability]:
        return frozenset(c.capability for c in self.capabilities)


# ------------------------------------------------------------------------ negotiation


class RejectionReason(StrEnum):
    UNSUPPORTED_BY_DEVICE = "unsupported_by_device"
    NO_DEVICE = "no_device"
    NOT_AUTHORIZED = "not_authorized"  # 1.3: decoded commands need operator authorization


class CapabilityRejection(_Wire):
    capability: Capability
    reason: RejectionReason
    required: bool


class AppStatus(StrEnum):
    ACTIVE = "active"  # all required capabilities granted
    SUSPENDED = "suspended"  # a required capability is unsupported by the device
    NO_DEVICE = "no_device"  # no device connected


class NegotiationResult(_Wire):
    device_id: str | None
    status: AppStatus
    granted: list[Capability]
    rejected: list[CapabilityRejection]


class CapabilityRequest(_Wire):
    # Plain strings so unknown names produce an explicit unknown_capability error
    # instead of a generic validation error.
    required: list[str] = Field(default_factory=list, max_length=16)
    optional: list[str] = Field(default_factory=list, max_length=16)


# ---------------------------------------------------------------------- stream (C->S)


class AppInfo(_Wire):
    id: str = Field(pattern=r"^[a-zA-Z0-9][a-zA-Z0-9_.\-]{0,63}$")
    name: str = Field(min_length=1, max_length=128)
    kind: Literal["application", "console", "sdk"] = "application"


class Hello(_Wire):
    type: Literal["hello"]
    protocol: str
    app: AppInfo
    capabilities: CapabilityRequest


class Ping(_Wire):
    type: Literal["ping"]
    nonce: str | int | None = None


# ------------------------------------------------------------------- runtime snapshot


class RuntimeState(StrEnum):
    IDLE = "idle"
    CONNECTING = "connecting"
    STREAMING = "streaming"
    PAUSED = "paused"
    RECONNECTING = "reconnecting"
    DISCONNECTING = "disconnecting"
    ERROR = "error"
    ENDED = "ended"  # finite source (replay without loop) exhausted


class ConnectedApp(_Wire):
    connection_id: str
    app: AppInfo
    negotiation: NegotiationResult
    connected_at_ns: int
    delivered: int
    dropped: int
    queue_depth: int


class PlaybackStatus(_Wire):
    """Playback state of a replay source (recordings and offline datasets)."""

    device_id: str
    speed: float
    position_s: float = Field(
        description="Recording time of the last emitted record, from the start of this pass"
    )
    duration_s: float | None
    loops: int
    loop: bool
    paused: bool
    records_emitted: int
    origin: str


class DatasetInfo(_Wire):
    id: str
    title: str
    dandiset: str
    version: str
    url: str
    license: str
    access: str
    citation: str
    asset_id: str
    asset_path: str


class SourceFile(_Wire):
    name: str
    size_bytes: int
    sha256: str
    verified: bool
    verification: str


class SourceChannel(_Wire):
    index: int
    unit_id: int
    spike_count: int
    electrode: str | None


class SourceBehavior(_Wire):
    series: str
    quantity: str
    dims: list[str]
    unit: str
    valid_fraction: float


class SourceDecoder(_Wire):
    model_id: str
    method: str
    dims: list[str]
    alpha: float
    trained_on: str
    evaluated_r2: float | None
    evaluated_samples: int | None
    control_mean_predictor_r2: float | None
    control_time_shift_r2: float | None


class SourceElectrode(_Wire):
    """One electrode of a raw-signal source, exactly as the file describes it (M5)."""

    index: int
    id: int
    label: str
    group: str | None
    group_description: str | None
    location: str | None
    x: float | None
    y: float | None
    z: float | None
    bad: bool | None = Field(description="from the file's good/bad column; None = not stated")
    filtering: str | None


class SourceSignal(_Wire):
    """Raw-signal layout of an offline source (M5)."""

    series: str
    sample_rate_hz: float
    unit: Literal["uV", "arbitrary"]
    declared_unit: str
    conversion: float | None
    n_samples: int
    start_s: float = Field(description="time of the first sample, seconds since session start")
    first_sample_index: int = Field(description="index of the first sample in the source series")
    frame_samples: int
    line_hz: float | None
    bad_channels: list[str]


class SourceIntervals(_Wire):
    table: str
    description: str
    rows: int
    emitted_as: str


class SourceSlice(_Wire):
    """Where a verified extract came from: a pinned slice of a larger published asset (M5)."""

    id: str
    asset_path: str
    asset_sha256: str
    series: str
    samples: list[int]
    data_sha256: str
    role: str


class SourceMetadata(_Wire):
    """Everything known (and explicitly not known) about an offline data source."""

    device_id: str
    label: str
    # nwb_units: spike times (M2); nwb_electrical_series: raw voltage, e.g. ECoG (M5)
    source_type: Literal["nwb_units", "nwb_electrical_series"]
    live: Literal[False] = False
    dataset: DatasetInfo | None
    file: SourceFile
    species: str | None
    subject_id: str | None
    identifier: str
    session_description: str
    session_start_time: str
    experiment_description: str
    institution: str
    lab: str
    recording_type: str
    profile: str
    feature: str
    feature_unit: str
    bin_ms: float
    n_bins: int
    duration_s: float
    channel_count: int
    channels: list[SourceChannel]
    behavior: SourceBehavior | None
    decoder: SourceDecoder | None
    notes: list[str]
    # Milestone 5 (additive, optional): declared modality, raw-signal layout, electrode table,
    # interval tables forwarded as annotations, and the pinned slice an extract came from.
    modality: Modality | None = None
    invasive: bool | None = None
    signal: SourceSignal | None = None
    electrodes: list[SourceElectrode] | None = None
    intervals: list[SourceIntervals] = Field(default_factory=list)
    slice: SourceSlice | None = None


class RuntimeSnapshot(_Wire):
    state: RuntimeState
    device: DeviceDescriptor | None
    session_id: str | None
    state_since_ns: int
    last_error: str | None
    recording: str | None = Field(description="Name of the active recording, if any")
    apps: list[ConnectedApp]
