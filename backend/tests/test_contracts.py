"""Contracts: envelope validation, provenance rules, schema drift (AT-1..AT-4)."""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from brainos.contracts import (
    Capability,
    EventType,
    UnknownCapabilityError,
    envelope_json_schema,
    parse_capabilities,
    parse_envelope,
    parse_envelope_json,
)
from brainos.contracts.capabilities import EVENT_CAPABILITY

from .helpers import valid_event

SCHEMA_FILE = Path(__file__).resolve().parents[2] / "contracts" / "event-envelope.v1.schema.json"


@pytest.mark.parametrize("event_type", [e.value for e in EventType])
def test_valid_envelopes_round_trip(event_type: str) -> None:
    """AT-1: every event type validates and round-trips through JSON."""
    env = parse_envelope(valid_event(event_type))
    again = parse_envelope_json(env.model_dump_json())
    assert again == env
    assert again.capability is EVENT_CAPABILITY[EventType(event_type)]


def test_every_event_type_maps_to_one_capability() -> None:
    assert set(EVENT_CAPABILITY) == set(EventType)
    assert set(EVENT_CAPABILITY.values()) == set(Capability)


MALFORMED: list[tuple[str, dict[str, Any]]] = [
    ("wrong schema major", valid_event(schema_version="2.0")),
    ("garbage schema version", valid_event(schema_version="one")),
    ("unknown event type", {**valid_event(), "event_type": "intent.telepathy"}),
    ("capability/type mismatch", valid_event(capability="selection")),
    ("payload/type mismatch", valid_event(payload={"action": "primary", "confidence": 0.5})),
    ("NaN velocity", valid_event(payload={"vx": math.nan, "vy": 0.0})),
    ("infinite velocity", valid_event(payload={"vx": math.inf, "vy": 0.0})),
    ("velocity out of range", valid_event(payload={"vx": 11.0, "vy": 0.0})),
    ("negative seq", valid_event(seq=-1)),
    ("bad session id", valid_event(session_id="nope")),
    ("bad device id", valid_event(device_id="Has Spaces")),
    ("extra field", {**valid_event(), "extra": 1}),
    ("missing provenance", {k: v for k, v in valid_event().items() if k != "provenance"}),
    ("quality score > 1", valid_event(quality={"score": 1.5, "flags": []})),
    ("unknown quality flag", valid_event(quality={"score": 1.0, "flags": ["vibes"]})),
    (
        "recording channel_count mismatch",
        valid_event(
            "recording.frame",
            payload={
                "sample_rate_hz": 1000.0,
                "channel_count": 3,
                "first_sample_index": 0,
                "samples": [[1.0], [2.0]],
            },
        ),
    ),
    (
        "recording ragged channels",
        valid_event(
            "recording.frame",
            payload={
                "sample_rate_hz": 1000.0,
                "channel_count": 2,
                "first_sample_index": 0,
                "samples": [[1.0, 2.0], [3.0]],
            },
        ),
    ),
    (
        "empty text intent",
        valid_event("intent.text", payload={"text": "", "mode": "character", "confidence": 1}),
    ),
    ("unknown device state", valid_event("device.status", payload={"state": "asleep"})),
    # schema 1.1 types
    (
        "features count/channel mismatch",
        valid_event(
            "features.binned",
            payload={**valid_event("features.binned")["payload"], "counts": [1, 2]},
        ),
    ),
    (
        "negative feature count",
        valid_event(
            "features.binned",
            payload={**valid_event("features.binned")["payload"], "counts": [0, -1, 1]},
        ),
    ),
    (
        "non-integer feature count",
        valid_event(
            "features.binned",
            payload={**valid_event("features.binned")["payload"], "counts": [0, 1.5, 1]},
        ),
    ),
    (
        "unknown feature kind",
        valid_event(
            "features.binned",
            payload={**valid_event("features.binned")["payload"], "feature": "vibes"},
        ),
    ),
    (
        "feature vector count mismatch",
        valid_event("features.vector", payload={**valid_event("features.vector")["payload"], "values": [1.0]}),
    ),
    (
        "feature vector NaN",
        valid_event("features.vector", payload={**valid_event("features.vector")["payload"], "values": [math.nan, 1.0]}),
    ),
    (
        "feature vector inverted band",
        valid_event("features.vector", payload={**valid_event("features.vector")["payload"], "band_hz": [150.0, 70.0]}),
    ),
    (
        "recording frame with an unknown unit",
        valid_event(
            "recording.frame",
            payload={**valid_event("recording.frame")["payload"], "unit": "volts"},
        ),
    ),
    (
        "behavior dims/values mismatch",
        valid_event(
            "behavior.sample",
            payload={**valid_event("behavior.sample")["payload"], "values": [1.0]},
        ),
    ),
    (
        "behavior NaN",
        valid_event(
            "behavior.sample",
            payload={**valid_event("behavior.sample")["payload"], "values": [math.nan, 0.0]},
        ),
    ),
    (
        "kinematic intent without space",
        valid_event(
            "intent.kinematics",
            payload={
                k: v for k, v in valid_event("intent.kinematics")["payload"].items() if k != "space"
            },
        ),
    ),
]


@pytest.mark.parametrize(("case", "data"), MALFORMED, ids=[c for c, _ in MALFORMED])
def test_malformed_envelopes_rejected(case: str, data: dict[str, Any]) -> None:
    """AT-2: malformed envelopes are rejected."""
    with pytest.raises(ValidationError):
        parse_envelope(data)


def test_malformed_json_rejected() -> None:
    """AT-2: non-JSON and truncated JSON are rejected."""
    with pytest.raises(ValidationError):
        parse_envelope_json(b'{"schema_version": "1.0", ')
    with pytest.raises(ValidationError):
        parse_envelope_json(json.dumps([valid_event()]))


def test_recording_frame_arbitrary_unit_is_valid() -> None:
    """1.2: sources that state no known unit pass values through as 'arbitrary'."""
    p = {**valid_event("recording.frame")["payload"], "unit": "arbitrary"}
    assert parse_envelope(valid_event("recording.frame", payload=p)).payload.unit == "arbitrary"  # type: ignore[union-attr]


def test_future_minor_version_accepted() -> None:
    """Consumers accept the same major version."""
    assert parse_envelope(valid_event(schema_version="1.7")).schema_version == "1.7"


def _prov(**kw: Any) -> dict[str, Any]:
    base = {
        "kind": "simulated_intent",
        "adapter": "x.y@1.0.0",
        "synthetic": True,
        "model_id": None,
        "origin": "test",
        "replayed": False,
    }
    base.update(kw)
    return base


PROVENANCE_VIOLATIONS: list[tuple[str, dict[str, Any]]] = [
    (
        "feature vector labelled as raw signal",
        valid_event("features.vector", provenance=_prov(kind="raw_signal")),
    ),
    (
        "feature vector labelled as an intent",
        valid_event("features.vector", provenance=_prov()),
    ),
    (
        "processed features delivered as an intent",
        valid_event("intent.kinematics", provenance=_prov(kind="processed_feature")),
    ),
    (
        "recorded behavior delivered as a kinematic intent",
        valid_event("intent.kinematics", provenance=_prov(kind="behavioral_label")),
    ),
    (
        "features labelled as raw signal",
        valid_event("features.binned", provenance=_prov(kind="raw_signal")),
    ),
    (
        "features labelled as decoded intent",
        valid_event("features.binned", provenance=_prov(kind="decoded_intent", model_id="m")),
    ),
    (
        "behavior labelled as simulated intent",
        valid_event("behavior.sample", provenance=_prov()),
    ),
    (
        "processed_feature on a raw recording frame",
        valid_event("recording.frame", provenance=_prov(kind="processed_feature")),
    ),
    (
        "decoded kinematics without model_id",
        valid_event("intent.kinematics", provenance=_prov(kind="decoded_intent", synthetic=False)),
    ),
    (
        "behavioral label delivered as an intent",
        valid_event("intent.pointer", provenance=_prov(kind="behavioral_label")),
    ),
    (
        "raw signal delivered as an intent",
        valid_event("intent.selection", provenance=_prov(kind="raw_signal")),
    ),
    (
        "decoded intent without model_id",
        valid_event("intent.pointer", provenance=_prov(kind="decoded_intent", synthetic=False)),
    ),
    (
        "simulated intent claiming to be non-synthetic",
        valid_event("intent.pointer", provenance=_prov(synthetic=False)),
    ),
    (
        "model_id on a simulated intent",
        valid_event("intent.pointer", provenance=_prov(model_id="m1")),
    ),
    (
        "intent kind on a raw recording frame",
        valid_event("recording.frame", provenance=_prov()),
    ),
    (
        "raw_signal on an annotation",
        valid_event("recording.annotation", provenance=_prov(kind="raw_signal")),
    ),
    (
        "behavioral_label on telemetry",
        valid_event("telemetry.sample", provenance=_prov(kind="behavioral_label")),
    ),
]


@pytest.mark.parametrize(
    ("case", "data"), PROVENANCE_VIOLATIONS, ids=[c for c, _ in PROVENANCE_VIOLATIONS]
)
def test_provenance_separation_enforced(case: str, data: dict[str, Any]) -> None:
    """AT-3: raw / label / simulated / decoded provenance cannot be mixed up."""
    with pytest.raises(ValidationError):
        parse_envelope(data)


def test_decoded_intent_with_model_id_is_valid() -> None:
    """AT-3: the contract already supports future decoders, if they identify the model."""
    env = parse_envelope(
        valid_event(
            "intent.pointer",
            provenance=_prov(kind="decoded_intent", synthetic=False, model_id="decoder-v0"),
        )
    )
    assert env.provenance.model_id == "decoder-v0"


def test_committed_schema_matches_models() -> None:
    """AT-4: committed JSON Schema equals the schema generated from the models."""
    assert SCHEMA_FILE.exists(), "run `make schema`"
    committed = json.loads(SCHEMA_FILE.read_text())
    assert committed == envelope_json_schema(), "schema drift: run `make schema`"


def test_parse_capabilities_rejects_unknown_names() -> None:
    assert parse_capabilities(["selection", "selection", "recording"]) == [
        Capability.SELECTION,
        Capability.RECORDING,
    ]
    with pytest.raises(UnknownCapabilityError) as info:
        parse_capabilities(["selection", "mind_reading"])
    assert info.value.names == ["mind_reading"]
