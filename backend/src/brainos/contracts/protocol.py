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
    DEVICE_ERROR = "device_error"
    SIMULATION_DISABLED = "simulation_disabled"
    RECORDING_ERROR = "recording_error"


# ---------------------------------------------------------------------------- devices


class DeviceKind(StrEnum):
    SIMULATED = "simulated"
    REPLAY = "replay"
    HARDWARE = "hardware"  # reserved; no hardware adapters exist in v1


class DeviceDescriptor(_Wire):
    device_id: str = Field(pattern=DEVICE_ID_PATTERN)
    display_name: str
    kind: DeviceKind
    adapter: str = Field(description="adapter name@semver")
    description: str = ""
    native_format: str = Field(description="Human-readable description of the wire format")
    capabilities: list[CapabilityDescriptor]
    synthetic: bool

    def supports(self, capability: Capability) -> bool:
        return any(c.capability is capability for c in self.capabilities)

    @property
    def capability_set(self) -> frozenset[Capability]:
        return frozenset(c.capability for c in self.capabilities)


# ------------------------------------------------------------------------ negotiation


class RejectionReason(StrEnum):
    UNSUPPORTED_BY_DEVICE = "unsupported_by_device"
    NO_DEVICE = "no_device"


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


class RuntimeSnapshot(_Wire):
    state: RuntimeState
    device: DeviceDescriptor | None
    session_id: str | None
    state_since_ns: int
    last_error: str | None
    recording: str | None = Field(description="Name of the active recording, if any")
    apps: list[ConnectedApp]
