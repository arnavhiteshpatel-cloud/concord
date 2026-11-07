"""Capability vocabulary (closed set for schema 1.x).

A capability is a class of application-facing events a device can provide.
Every event type maps to exactly one capability.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class Capability(StrEnum):
    RECORDING = "recording"
    POINTER_INTENT = "pointer_intent"
    SELECTION = "selection"
    TEXT_INTENT = "text_intent"
    TELEMETRY = "telemetry"
    DEVICE_STATUS = "device_status"


class EventType(StrEnum):
    RECORDING_FRAME = "recording.frame"
    RECORDING_ANNOTATION = "recording.annotation"
    INTENT_POINTER = "intent.pointer"
    INTENT_SELECTION = "intent.selection"
    INTENT_TEXT = "intent.text"
    TELEMETRY_SAMPLE = "telemetry.sample"
    DEVICE_STATUS = "device.status"


EVENT_CAPABILITY: dict[EventType, Capability] = {
    EventType.RECORDING_FRAME: Capability.RECORDING,
    EventType.RECORDING_ANNOTATION: Capability.RECORDING,
    EventType.INTENT_POINTER: Capability.POINTER_INTENT,
    EventType.INTENT_SELECTION: Capability.SELECTION,
    EventType.INTENT_TEXT: Capability.TEXT_INTENT,
    EventType.TELEMETRY_SAMPLE: Capability.TELEMETRY,
    EventType.DEVICE_STATUS: Capability.DEVICE_STATUS,
}

CAPABILITY_DESCRIPTIONS: dict[Capability, str] = {
    Capability.RECORDING: "Multichannel sample frames and time-aligned behavioral labels.",
    Capability.POINTER_INTENT: "Continuous 2-D velocity intent in normalized workspace units.",
    Capability.SELECTION: "Discrete select/activate intent.",
    Capability.TEXT_INTENT: "Discrete text (character or word) intent.",
    Capability.TELEMETRY: "Device health metrics.",
    Capability.DEVICE_STATUS: "Connection and streaming state changes.",
}


def capability_for(event_type: EventType) -> Capability:
    return EVENT_CAPABILITY[event_type]


class UnknownCapabilityError(ValueError):
    """Raised when a name is not part of the capability vocabulary."""

    def __init__(self, names: list[str]) -> None:
        self.names = names
        super().__init__(f"unknown capability name(s): {', '.join(names)}")


def parse_capabilities(names: list[str]) -> list[Capability]:
    """Parse capability names, rejecting unknown names explicitly (never ignored)."""
    unknown = [n for n in names if n not in Capability._value2member_map_]
    if unknown:
        raise UnknownCapabilityError(unknown)
    # preserve order, drop duplicates
    seen: dict[Capability, None] = {}
    for n in names:
        seen[Capability(n)] = None
    return list(seen)


ParamValue = int | float | str | bool | list[str]


class CapabilityDescriptor(BaseModel):
    """What a device declares about one capability it supports.

    ``params`` is informational for apps (e.g. ``rate_hz``, ``channel_count``)
    but binding for adapters: emitting events for an undeclared capability is
    a contract violation.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    capability: Capability
    params: dict[str, ParamValue] = Field(default_factory=dict)
    description: str = ""
