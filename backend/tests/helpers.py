"""Shared test helpers."""

from __future__ import annotations

import asyncio
import json
import time
from collections.abc import Callable, Sequence
from typing import Any

from concord.adapters.base import (
    DeviceAdapter,
    DeviceLinkError,
    EventDraft,
    NativePacket,
    PacketDecodeError,
)
from concord.contracts.capabilities import Capability, CapabilityDescriptor, EventType
from concord.contracts.events import Provenance, ProvenanceKind, Quality, QualityFlag
from concord.contracts.protocol import DeviceDescriptor, DeviceKind
from concord.runtime.bus import Subscriber

SIM_PROV = Provenance(
    kind=ProvenanceKind.SIMULATED_INTENT,
    adapter="test.adapter@0.0.1",
    synthetic=True,
    origin="test",
)
DEV_PROV = Provenance(
    kind=ProvenanceKind.DEVICE_REPORT, adapter="test.adapter@0.0.1", synthetic=True, origin="test"
)
Q = Quality(score=1.0, flags=[QualityFlag.SYNTHETIC])


async def wait_for(cond: Callable[[], bool], timeout: float = 3.0, interval: float = 0.01) -> None:
    deadline = time.monotonic() + timeout
    while not cond():
        if time.monotonic() > deadline:
            raise AssertionError("condition not met within timeout")
        await asyncio.sleep(interval)


def drain(sub: Subscriber) -> list[dict[str, Any]]:
    """Synchronously drain all queued messages from a subscriber (control + events)."""
    out: list[dict[str, Any]] = []
    while sub._control:
        out.append(json.loads(sub._control.popleft()))
    while sub._events:
        dseq, ev, *_ = sub._events.popleft()
        out.append({"type": "event", "delivery_seq": dseq, "event": json.loads(ev.text)})
    return out


def events(msgs: list[dict[str, Any]], event_type: str | None = None) -> list[dict[str, Any]]:
    evs = [m["event"] for m in msgs if m["type"] == "event"]
    return [e for e in evs if event_type is None or e["event_type"] == event_type]


def valid_event(event_type: str = "intent.pointer", **overrides: Any) -> dict[str, Any]:
    payloads: dict[str, tuple[str, dict[str, Any], str]] = {
        "recording.frame": (
            "recording",
            {
                "sample_rate_hz": 1000.0,
                "channel_count": 2,
                "first_sample_index": 0,
                "unit": "uV",
                "samples": [[1.0, 2.0], [3.0, 4.0]],
            },
            "raw_signal",
        ),
        "recording.annotation": (
            "recording",
            {"label": "cue", "value": "left", "duration_ms": 500},
            "behavioral_label",
        ),
        "intent.pointer": ("pointer_intent", {"vx": 0.1, "vy": -0.2}, "simulated_intent"),
        "intent.selection": (
            "selection",
            {"action": "primary", "confidence": 0.9},
            "simulated_intent",
        ),
        "intent.text": (
            "text_intent",
            {"text": "a", "mode": "character", "confidence": 0.9},
            "simulated_intent",
        ),
        "telemetry.sample": (
            "telemetry",
            {"metrics": [{"name": "battery_pct", "value": 90.0, "unit": "%"}]},
            "device_report",
        ),
        "device.status": ("device_status", {"state": "streaming", "detail": ""}, "runtime"),
        "features.binned": (
            "neural_features",
            {
                "feature": "threshold_crossing_count",
                "unit": "count",
                "bin_ms": 20.0,
                "bin_index": 3,
                "channel_count": 3,
                "counts": [0, 2, 1],
            },
            "processed_feature",
        ),
        "features.vector": (
            "neural_features",
            {
                "feature": "log_band_power",
                "unit": "log10(uV^2)",
                "band_hz": [70.0, 150.0],
                "bin_ms": 50.0,
                "bin_index": 1,
                "channel_count": 2,
                "values": [1.5, 2.25],
            },
            "processed_feature",
        ),
        "behavior.sample": (
            "behavior",
            {
                "quantity": "velocity",
                "dims": ["tx", "ty"],
                "unit": "arbitrary",
                "values": [0.1, -0.2],
                "sample_index": 3,
                "valid": True,
            },
            "behavioral_label",
        ),
        "intent.kinematics": (
            "kinematic_intent",
            {
                "quantity": "velocity",
                "dims": ["tx", "ty"],
                "unit": "arbitrary",
                "values": [0.1, -0.2],
                "space": "falcon_h1_7dof",
            },
            "simulated_intent",
        ),
    }
    payloads["intent.navigate"] = (
        "navigation",
        {"direction": "next", "confidence": 0.7},
        "simulated_intent",
    )
    payloads["control.state"] = (
        "control_status",
        {"active": True, "capabilities": ["pointer_intent"], "reason": "operator started control"},
        "runtime",
    )
    cap, payload, kind = payloads[event_type]
    ev: dict[str, Any] = {
        "schema_version": "1.0",
        "session_id": "ses_abcdef12",
        "device_id": "sim-a",
        "seq": 0,
        "timestamp_ns": 1_700_000_000_000_000_000,
        "device_timestamp_ns": 1000,
        "event_type": event_type,
        "capability": cap,
        "payload": payload,
        "quality": {"score": 0.9, "flags": ["synthetic"]},
        "provenance": {
            "kind": kind,
            "adapter": "concord.sim.profile_a@0.1.0",
            "synthetic": True,
            "model_id": None,
            "origin": "test",
            "replayed": False,
        },
    }
    ev.update(overrides)
    return ev


# --------------------------------------------------------------------------- adapter

Script = list[Any]  # items: EventDraft list, Exception, or ("raw", data)


def scripted_descriptor(
    device_id: str = "test-dev", caps: Sequence[Capability] = ()
) -> DeviceDescriptor:
    caps = caps or [Capability.SELECTION, Capability.TELEMETRY, Capability.DEVICE_STATUS]
    return DeviceDescriptor(
        device_id=device_id,
        display_name="Scripted test device",
        kind=DeviceKind.SIMULATED,
        adapter="test.adapter@0.0.1",
        native_format="python objects",
        capabilities=[CapabilityDescriptor(capability=c) for c in caps],
        synthetic=True,
    )


class ScriptedAdapter(DeviceAdapter):
    """Adapter that plays a fixed script; then idles. For deterministic runtime tests."""

    def __init__(self, descriptor: DeviceDescriptor, script: Script, *, fail_open: int = 0) -> None:
        self.descriptor = descriptor
        self.script = list(script)
        self.fail_open = fail_open
        self.open_calls = 0
        self.opened = False
        self.paused = False

    async def open(self) -> None:
        self.open_calls += 1
        if self.fail_open > 0:
            self.fail_open -= 1
            raise DeviceLinkError("scripted open failure")
        self.opened = True

    async def close(self) -> None:
        self.opened = False

    def set_paused(self, paused: bool) -> None:
        self.paused = paused

    async def read(self) -> NativePacket:
        await asyncio.sleep(0.001)
        while not self.script:
            await asyncio.sleep(0.01)
        item = self.script.pop(0)
        if isinstance(item, BaseException):
            raise item
        return NativePacket(item)

    def normalize(self, packet: NativePacket) -> Sequence[EventDraft]:
        if packet.data == "corrupt":
            raise PacketDecodeError("corrupt")
        if packet.data == "crash":
            raise ZeroDivisionError("bug in normalize")
        result: list[EventDraft] = packet.data
        return result


def sel_draft(ts: int | None = None, conf: float = 0.9) -> EventDraft:
    return EventDraft(
        EventType.INTENT_SELECTION, {"action": "primary", "confidence": conf}, Q, SIM_PROV, ts
    )


def tel_draft(ts: int | None = None) -> EventDraft:
    return EventDraft(
        EventType.TELEMETRY_SAMPLE,
        {"metrics": [{"name": "battery_pct", "value": 50.0, "unit": "%"}]},
        Q,
        DEV_PROV,
        ts,
    )
