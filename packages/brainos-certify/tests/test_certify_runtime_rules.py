"""Runtime-phase rules on crafted descriptors, negotiations and events (pure; no BrainOS)."""

from __future__ import annotations

from typing import Any

from brainos_adapter_sdk import (
    Channel,
    ClockInfo,
    Modality,
    PluginManifest,
    SessionInfo,
    StreamRole,
    StreamSpec,
)

from brainos_certify import runtime_phase as rp

CLOCK = ClockInfo("source")
ALL_CAPS = [
    "recording",
    "pointer_intent",
    "selection",
    "text_intent",
    "telemetry",
    "device_status",
    "neural_features",
    "behavior",
    "kinematic_intent",
]


def manifest() -> PluginManifest:
    return PluginManifest(
        name="brainos-bci2000", version="0.1.0", api_version="1.0", display_name="B",
        description="d", author="a", license="l", ecosystem="bci2000",
        roles=frozenset({StreamRole.DECODER_OUTPUT, StreamRole.BEHAVIOR, StreamRole.MARKERS}),
    )  # fmt: skip


def decoder_info(synthetic: bool = False, prerecorded: bool = False) -> SessionInfo:
    return SessionInfo(
        streams=(
            StreamSpec("ctrl", StreamRole.DECODER_OUTPUT, (Channel("x"),), 32.0, CLOCK,
                       quantity="control_signal", model_id="m1"),
            StreamSpec("states", StreamRole.BEHAVIOR, (Channel("TargetCode"),), 32.0, CLOCK),
            StreamSpec("changes", StreamRole.MARKERS, (Channel("m"),), 0.0, CLOCK),
        ),
        primary_stream="ctrl", synthetic=synthetic, prerecorded=prerecorded,
        origin="bci2000:127.0.0.1:20321",
    )  # fmt: skip


def signal_info(modality: Modality | None, invasive: bool | None) -> SessionInfo:
    s = StreamSpec("sig", StreamRole.SIGNAL, (Channel("a", "microvolts"),), 1000.0, CLOCK,
                   modality=modality, invasive=invasive)  # fmt: skip
    return SessionInfo((s,), "sig", False, False, "lab")


def test_expected_capabilities_follow_roles() -> None:
    assert rp.expected_capabilities(decoder_info()) == {
        "kinematic_intent",
        "behavior",
        "recording",
        "device_status",
    }
    assert rp.expected_capabilities(signal_info(None, None)) == {"recording", "device_status"}


def test_expected_descriptor_invasiveness() -> None:
    m = manifest()
    assert rp.expected_descriptor(signal_info(Modality.ECOG, None), m)["invasive"] is True
    assert rp.expected_descriptor(signal_info(Modality.EEG, None), m)["invasive"] is False
    assert rp.expected_descriptor(signal_info(None, None), m)["invasive"] is None
    assert rp.expected_descriptor(decoder_info(), m)["modality"] is None  # no neural primary
    kinds = [rp.expected_descriptor(decoder_info(*f), m)["kind"]
             for f in ((True, False), (False, True), (False, False), (True, True))]  # fmt: skip
    assert kinds == ["simulated", "replay", "stream", "simulated"]


def _descriptor(**over: Any) -> dict[str, Any]:
    d: dict[str, Any] = {
        "kind": "stream",
        "synthetic": False,
        "modality": None,
        "invasive": None,
        "integration": {"kind": "plugin", "package": "brainos-bci2000", "version": "0.1.0",
                        "api_version": "1.0", "isolated": True, "ecosystem": "bci2000"},
        "capabilities": [{"capability": c} for c in
                         ("recording", "behavior", "kinematic_intent", "device_status")],
    }  # fmt: skip
    d.update(over)
    return d


def test_descriptor_mismatches_are_reported() -> None:
    exp = rp.expected_descriptor(decoder_info(), manifest())
    assert rp.compare_descriptor(exp, _descriptor()) == []
    diffs = rp.compare_descriptor(exp, _descriptor(kind="hardware", modality="eeg"))
    assert any(d.startswith("kind") for d in diffs) and any("modality" in d for d in diffs)
    integ = dict(_descriptor()["integration"], isolated=False)
    assert any("integration.isolated" in d for d in rp.compare_descriptor(
        exp, _descriptor(integration=integ)))  # fmt: skip
    caps = [{"capability": c} for c in ("recording", "behavior", "kinematic_intent",
                                        "device_status", "pointer_intent")]  # fmt: skip
    diffs = rp.compare_descriptor(exp, _descriptor(capabilities=caps))
    assert any("command capabilities" in d for d in diffs)


def _neg(status: str, granted: list[str], rejected: dict[str, str], req: bool = False) -> Any:
    return {
        "status": status,
        "granted": granted,
        "rejected": [{"capability": c, "reason": r, "required": req} for c, r in rejected.items()],
    }


def test_negotiation_rules() -> None:
    exp = {"recording", "device_status"}
    others = {c: "unsupported_by_device" for c in ALL_CAPS if c not in exp}
    good = {
        "all_optional": _neg("active", sorted(exp), others),
        "roles_required": _neg("active", sorted(exp), {}),
        "command_required": _neg(
            "suspended", [], {"pointer_intent": "unsupported_by_device"}, True
        ),
    }
    assert rp.check_negotiations(exp, ALL_CAPS, good) == []
    granted_cmd = dict(good, all_optional=_neg("active", [*sorted(exp), "pointer_intent"],
                       {k: v for k, v in others.items() if k != "pointer_intent"}))  # fmt: skip
    assert rp.check_negotiations(exp, ALL_CAPS, granted_cmd)
    active_cmd = dict(good, command_required=_neg("active", ["pointer_intent"], {}))
    probs = rp.check_negotiations(exp, ALL_CAPS, active_cmd)
    assert any("command app" in p for p in probs)
    wrong_reason = dict(good, all_optional=_neg("active", sorted(exp),
                        dict(others, telemetry="no_device")))  # fmt: skip
    assert rp.check_negotiations(exp, ALL_CAPS, wrong_reason)


def _event(et: str, kind: str, **prov: Any) -> dict[str, Any]:
    p = {"kind": kind, "synthetic": False, "replayed": False, "origin": "bci2000:127.0.0.1:20321",
         "model_id": None}  # fmt: skip
    p.update(prov)
    return {"event_type": et, "provenance": p, "quality": {"flags": []}}


def test_provenance_rules() -> None:
    info, m = decoder_info(), manifest()
    by = {rp.ROLE_EVENT[r]: s for r, s in rp.delivered_streams(info).items()}
    ok = _event("intent.kinematics", "decoded_intent", model_id="brainos-bci2000:m1")
    assert rp.check_event_provenance(ok, info, m, by) == []
    assert (
        rp.check_event_provenance(_event("behavior.sample", "behavioral_label"), info, m, by) == []
    )
    # decoder output without its model id, or presented as raw data
    assert rp.check_event_provenance(_event("intent.kinematics", "decoded_intent"), info, m, by)
    assert rp.check_event_provenance(
        _event("intent.kinematics", "raw_signal", model_id="brainos-bci2000:m1"), info, m, by
    )
    # a command never reaches the bus from a plugin
    assert (
        "command"
        in rp.check_event_provenance(_event("intent.pointer", "decoded_intent"), info, m, by)[0]
    )
    # an event type the roles do not produce
    assert rp.check_event_provenance(_event("recording.frame", "raw_signal"), info, m, by)


def test_synthetic_and_replayed_flags_must_propagate() -> None:
    m = manifest()
    syn = decoder_info(synthetic=True)
    by = {rp.ROLE_EVENT[r]: s for r, s in rp.delivered_streams(syn).items()}
    ev = _event("behavior.sample", "behavioral_label")
    probs = rp.check_event_provenance(ev, syn, m, by)
    assert any("synthetic" in p for p in probs)
    ev_ok = _event("behavior.sample", "behavioral_label", synthetic=True)
    ev_ok["quality"]["flags"] = ["synthetic"]
    assert rp.check_event_provenance(ev_ok, syn, m, by) == []
    rec = decoder_info(prerecorded=True)
    probs = rp.check_event_provenance(_event("behavior.sample", "behavioral_label"), rec, m, by)
    assert any("replayed" in p for p in probs)


def test_negotiation_rules_with_runtime_capabilities() -> None:
    """Schema 1.4: control_status is granted by the runtime with any device (not the plugin)."""
    caps = [*ALL_CAPS, "navigation", "control_status"]
    exp = {"recording", "device_status"}
    others = {c: "unsupported_by_device" for c in caps if c not in exp | {"control_status"}}
    good = {
        "all_optional": _neg("active", sorted(exp | {"control_status"}), others),
        "roles_required": _neg("active", sorted(exp), {}),
        "command_required": _neg(
            "suspended", [], {"pointer_intent": "unsupported_by_device"}, True
        ),
    }
    assert rp.check_negotiations(exp, caps, good) == []
    nav = dict(good, all_optional=_neg("active", sorted(exp | {"control_status", "navigation"}),
               {k: v for k, v in others.items() if k != "navigation"}))  # fmt: skip
    assert rp.check_negotiations(exp, caps, nav)  # a plugin must never grant navigation
    assert "navigation" in rp.COMMAND_CAPABILITIES and "intent.navigate" in rp.COMMAND_EVENTS
