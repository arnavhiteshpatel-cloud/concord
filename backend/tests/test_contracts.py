"""Contracts: envelope validation, provenance rules, schema drift (AT-1..AT-4)."""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from concord.contracts import (
    Capability,
    EventType,
    UnknownCapabilityError,
    envelope_json_schema,
    parse_capabilities,
    parse_envelope,
    parse_envelope_json,
)
from concord.contracts.capabilities import EVENT_CAPABILITY

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
        valid_event(
            "features.vector",
            payload={**valid_event("features.vector")["payload"], "values": [1.0]},
        ),
    ),
    (
        "feature vector NaN",
        valid_event(
            "features.vector",
            payload={**valid_event("features.vector")["payload"], "values": [math.nan, 1.0]},
        ),
    ),
    (
        "feature vector inverted band",
        valid_event(
            "features.vector",
            payload={**valid_event("features.vector")["payload"], "band_hz": [150.0, 70.0]},
        ),
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
    committed = json.loads(SCHEMA_FILE.read_text(encoding="utf-8"))
    assert committed == envelope_json_schema(), "schema drift: run `make schema`"


def test_parse_capabilities_rejects_unknown_names() -> None:
    assert parse_capabilities(["selection", "selection", "recording"]) == [
        Capability.SELECTION,
        Capability.RECORDING,
    ]
    with pytest.raises(UnknownCapabilityError) as info:
        parse_capabilities(["selection", "mind_reading"])
    assert info.value.names == ["mind_reading"]


# ------------------------------------------------------------------ schema 1.3


@pytest.mark.parametrize("action", ["primary", "activate", "cancel"])
def test_selection_actions_1_3(action: str) -> None:
    env = parse_envelope(
        valid_event("intent.selection", payload={"action": action, "confidence": 0.8})
    )
    assert env.payload.action == action  # type: ignore[union-attr]


@pytest.mark.parametrize("action", ["stimulate", "", "PRIMARY", None])
def test_unknown_selection_actions_rejected(action: Any) -> None:
    with pytest.raises(ValidationError):
        parse_envelope(
            valid_event("intent.selection", payload={"action": action, "confidence": 0.8})
        )


def test_descriptor_modality_and_integration_1_3() -> None:
    from concord.contracts.protocol import (
        INVASIVE_MODALITIES,
        NONINVASIVE_MODALITIES,
        DeviceDescriptor,
        Modality,
        RejectionReason,
    )

    base = {
        "device_id": "plugin:bf-synthetic",
        "display_name": "x",
        "kind": "stream",
        "adapter": "x@1.0.0",
        "native_format": "x",
        "capabilities": [],
        "synthetic": True,
    }
    d = DeviceDescriptor.model_validate(base)
    assert d.modality is None and d.invasive is None and d.integration is None  # never guessed
    d = DeviceDescriptor.model_validate(
        {
            **base,
            "modality": "eeg",
            "invasive": False,
            "integration": {"kind": "plugin", "package": "concord-brainflow", "isolated": True},
        }
    )
    assert d.modality is Modality.EEG and d.integration is not None and d.integration.isolated
    assert Modality.EEG in NONINVASIVE_MODALITIES and Modality.INTRACORTICAL in INVASIVE_MODALITIES
    assert not NONINVASIVE_MODALITIES & INVASIVE_MODALITIES
    with pytest.raises(ValidationError):
        DeviceDescriptor.model_validate({**base, "modality": "implant"})
    with pytest.raises(ValidationError):
        DeviceDescriptor.model_validate({**base, "integration": {"kind": "vendor"}})
    assert RejectionReason("not_authorized") is RejectionReason.NOT_AUTHORIZED


# ------------------------------------------------------------------ schema 1.4


def _decoded(event_type: str, payload: dict[str, Any], **prov: Any) -> dict[str, Any]:
    ev = valid_event(event_type, payload=payload)
    ev["provenance"] = {
        **ev["provenance"],
        "kind": "decoded_intent",
        "synthetic": False,
        "model_id": "m1",
        **prov,
    }
    ev["quality"] = {"score": 1.0, "flags": []}
    return ev


def _nav(**prov: Any) -> dict[str, Any]:
    ev = _decoded("intent.pointer", {"direction": "next", "confidence": 0.8}, **prov)
    ev["event_type"], ev["capability"], ev["schema_version"] = (
        "intent.navigate",
        "navigation",
        "1.4",
    )
    return ev


@pytest.mark.parametrize("direction", ["up", "down", "left", "right", "next", "previous"])
def test_navigate_directions_1_4(direction: str) -> None:
    ev = _nav()
    ev["payload"]["direction"] = direction
    assert parse_envelope(ev).payload.direction == direction  # type: ignore[union-attr]


@pytest.mark.parametrize(
    ("change", "match"),
    [
        ({"payload": {"direction": "jump", "confidence": 0.5}}, "direction"),
        ({"payload": {"direction": "up", "confidence": 1.5}}, "confidence"),
        ({"capability": "selection"}, "capability"),
    ],
)
def test_malformed_navigate_rejected(change: dict[str, Any], match: str) -> None:
    with pytest.raises(ValidationError, match=match):
        parse_envelope({**_nav(), **change})


def test_model_origin_rules_1_4() -> None:
    assert parse_envelope(_nav(model_origin="concord")).provenance.model_origin == "concord"
    # recorded outputs of an original research decoder are replayed data by definition
    with pytest.raises(ValidationError, match="replayed must be true"):
        parse_envelope(_nav(model_origin="historical"))
    assert parse_envelope(_nav(model_origin="historical", replayed=True)).provenance.replayed
    with pytest.raises(ValidationError):
        parse_envelope(_nav(model_origin="mine"))
    raw = valid_event("recording.frame")
    raw["provenance"]["model_origin"] = "concord"
    with pytest.raises(ValidationError, match="model_origin is only valid"):
        parse_envelope(raw)


def test_control_state_1_4() -> None:
    ev = valid_event(
        "intent.pointer",
        payload={"active": False, "capabilities": ["pointer_intent"], "reason": "operator stop"},
    )
    ev.update(event_type="control.state", capability="control_status", schema_version="1.4")
    ev["provenance"] = {**ev["provenance"], "kind": "runtime", "synthetic": False}
    assert parse_envelope(ev).payload.active is False  # type: ignore[union-attr]
    bad = {**ev, "provenance": {**ev["provenance"], "kind": "decoded_intent", "model_id": "m"}}
    with pytest.raises(ValidationError, match="not allowed"):
        parse_envelope(bad)
    with pytest.raises(ValidationError):
        parse_envelope({**ev, "payload": {"active": "no", "capabilities": [], "reason": ""}})


def test_spike_band_power_feature_1_4() -> None:
    ev = valid_event("features.vector")
    ev["payload"] = {**ev["payload"], "feature": "spike_band_power", "band_hz": None}
    assert parse_envelope(ev).payload.feature == "spike_band_power"  # type: ignore[union-attr]
    ev["payload"]["feature"] = "spike_power"
    with pytest.raises(ValidationError, match="feature"):
        parse_envelope(ev)
