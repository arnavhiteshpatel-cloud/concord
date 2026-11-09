"""Validation-level logic: what can and cannot be claimed."""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from typing import Any

import pytest
from certify_helpers import OPENSSL, attestation_doc, keypair, sign
from concord_adapter_sdk import (
    Channel,
    ClockInfo,
    PluginManifest,
    SessionInfo,
    StreamRole,
    StreamSpec,
)

from concord_certify import levels as lv
from concord_certify.model import CHECK_IDS, CheckResult, Status, check_def

needs_openssl = pytest.mark.skipif(OPENSSL is None, reason="openssl not installed")


def results(**over: Status) -> list[CheckResult]:
    out = []
    for cid in CHECK_IDS:
        status = over.get(cid.replace(".", "__"), "pass")
        out.append(CheckResult(cid, status, f"{cid} {status}"))
    return out


def manifest(ecosystem: str | None = "brainflow") -> PluginManifest:
    return PluginManifest(
        name="concord-brainflow", version="0.1.0", api_version="1.0", display_name="BF",
        description="d", author="a", license="l", roles=frozenset({StreamRole.SIGNAL}),
        ecosystem=ecosystem,
    )  # fmt: skip


def info(origin: str = "brainflow:SYNTHETIC_BOARD") -> SessionInfo:
    s = StreamSpec("exg", StreamRole.SIGNAL, (Channel("C3", "microvolts"),), 250.0,
                   ClockInfo("unix"))  # fmt: skip
    return SessionInfo((s,), "exg", True, False, origin)


# ----------------------------------------------------------------------------- level 1


def test_all_pass_grants_adapter_implementation_only() -> None:
    r = lv.evaluate(results(), reference=None, rules=[], attestation=None)
    assert r["achieved"] == ["adapter_implementation"]
    assert r["highest"] == "adapter_implementation"
    assert not r["levels"]["hardware_tested"]["achieved"]
    assert not r["levels"]["human_participant_validated"]["achieved"]


def test_warnings_do_not_block_but_failures_do() -> None:
    ok = lv.adapter_implementation(results(metadata__units="warn", timing__jitter="warn"))
    assert ok["achieved"]
    bad = lv.adapter_implementation(results(timing__rate="fail"))
    assert not bad["achieved"] and bad["missing"][0].startswith("timing.rate failed")


def test_optional_runtime_failure_blocks_but_not_running_it_does_not() -> None:
    assert not check_def("runtime.envelopes").required
    failed = lv.adapter_implementation(results(runtime__envelopes="fail"))
    assert not failed["achieved"]
    skipped = [
        CheckResult(c.id, "not_run", "Concord not installed", applicable=False)
        if c.id.startswith("runtime.")
        else c
        for c in results()
    ]
    r = lv.adapter_implementation(skipped)
    assert r["achieved"] and "runtime phase not run" in r["notes"][0]


def test_required_not_run_blocks_unless_not_applicable() -> None:
    blocked = [
        CheckResult(c.id, "not_run", "prerequisite failed") if c.id == "timing.rate" else c
        for c in results()
    ]
    assert not lv.adapter_implementation(blocked)["achieved"]
    na = [
        CheckResult(c.id, "not_run", "no markers stream", applicable=False)
        if c.id == "integrity.markers"
        else c
        for c in results()
    ]
    assert lv.adapter_implementation(na)["achieved"]


# ----------------------------------------------------------------------------- level 2


def test_protocol_tested_needs_reference_and_consistency() -> None:
    ref = "BrainFlow 5.23 BoardShim SYNTHETIC_BOARD"
    rules = lv.protocol_consistency(ref, manifest(), info(), {"brainflow": "5.23.0"})
    assert all(r["ok"] is True for r in rules), rules
    r = lv.evaluate(results(), reference=ref, rules=rules, attestation=None)
    assert r["highest"] == "protocol_tested"
    st = r["levels"]["protocol_tested"]["statement"]
    assert st == f"protocol-tested against {ref} (operator statement)"
    # without the operator statement, never
    r2 = lv.evaluate(results(), reference=None, rules=[], attestation=None)
    assert not r2["levels"]["protocol_tested"]["achieved"]


@pytest.mark.parametrize(
    ("ref", "man", "inf", "versions", "broken"),
    [
        ("BCI2000 3.6", manifest(), info(), {"brainflow": "5.23.0"}, "reference_names_ecosystem"),
        ("BrainFlow 5.23", manifest(), info("lsl:stream"), {}, "origin_from_ecosystem"),
        ("BrainFlow 5.22", manifest(), info(), {"brainflow": "5.23.0"},
         "reference_version_matches_installed"),
        ("BrainFlow 5.23", manifest(None), info(), {}, "ecosystem_declared"),
    ],
)  # fmt: skip
def test_inconsistent_reference_is_refused(
    ref: str, man: PluginManifest, inf: SessionInfo, versions: dict[str, str | None], broken: str
) -> None:
    rules = lv.protocol_consistency(ref, man, inf, versions)
    assert {r["rule"]: r["ok"] for r in rules}[broken] is False
    r = lv.evaluate(results(), reference=ref, rules=rules, attestation=None)
    assert not r["levels"]["protocol_tested"]["achieved"]
    assert any(broken in m for m in r["levels"]["protocol_tested"]["missing"])


def test_protocol_needs_level1() -> None:
    ref = "BrainFlow 5.23"
    rules = lv.protocol_consistency(ref, manifest(), info(), {"brainflow": "5.23.0"})
    r = lv.evaluate(results(timing__rate="fail"), reference=ref, rules=rules, attestation=None)
    assert r["achieved"] == [] and r["highest"] is None


def test_unverifiable_version_does_not_block() -> None:
    rules = lv.protocol_consistency("BrainFlow synthetic", manifest(), info(), {})
    assert {r["rule"]: r["ok"] for r in rules}["reference_version_matches_installed"] is None
    assert lv.protocol_tested(True, "BrainFlow synthetic", rules)["achieved"]


# ----------------------------------------------------------------------------- level 3


def write(tmp: Path, doc: dict[str, Any], name: str = "att.json") -> Path:
    p = tmp / name
    p.write_text(json.dumps(doc, indent=1), encoding="utf-8")
    return p


def check_att(path: Path, sig: Path | None, pub: Path | None, **over: Any) -> dict[str, Any]:
    kw: dict[str, Any] = {"plugin_name": "concord-brainflow", "plugin_version": "0.1.0",
                          "tree_sha256": None}  # fmt: skip
    kw.update(over)
    return lv.check_attestation(path, sig, pub, **kw)


@needs_openssl
def test_signed_attestation_is_recorded_as_operator_attested(tmp_path: Path) -> None:
    key, pub = keypair(tmp_path)
    p = write(tmp_path, attestation_doc())
    att = check_att(p, sign(p, key), pub)
    assert att["accepted"], att["reason"]
    assert len(att["public_key_sha256"]) == 64 and len(att["file_sha256"]) == 64
    assert "NOT verified" in att["verified_by_toolkit"]
    r = lv.evaluate(results(), reference=None, rules=[], attestation=att)
    hw = r["levels"]["hardware_tested"]
    assert hw["achieved"] and "operator-attested" in hw["statement"]
    assert "not verified by this toolkit" in hw["statement"]
    assert r["highest"] == "hardware_tested"
    assert not r["levels"]["human_participant_validated"]["achieved"]  # never


def test_no_attestation_never_hardware() -> None:
    r = lv.evaluate(results(), reference="BrainFlow 5.23", rules=[], attestation=None)
    assert not r["levels"]["hardware_tested"]["achieved"]
    assert "never inferred" in r["levels"]["hardware_tested"]["missing"][0]


@needs_openssl
def test_tampered_attestation_is_rejected(tmp_path: Path) -> None:
    key, pub = keypair(tmp_path)
    p = write(tmp_path, attestation_doc())
    sig = sign(p, key)
    p.write_text(
        p.read_text(encoding="utf-8").replace("SN-1", "SN-2"), encoding="utf-8"
    )  # edited after signing
    att = check_att(p, sig, pub)
    assert not att["accepted"] and "does not verify" in att["reason"]
    r = lv.evaluate(results(), reference=None, rules=[], attestation=att)
    assert not r["levels"]["hardware_tested"]["achieved"]
    assert "attestation rejected" in r["levels"]["hardware_tested"]["missing"][0]


@needs_openssl
def test_attestation_signed_by_another_key_is_rejected(tmp_path: Path) -> None:
    key, _ = keypair(tmp_path)
    other = tmp_path / "other"
    other.mkdir()
    _, other_pub = keypair(other)
    p = write(tmp_path, attestation_doc())
    assert not check_att(p, sign(p, key), other_pub)["accepted"]


@needs_openssl
@pytest.mark.parametrize(
    ("over", "kw", "fragment"),
    [
        ({"plugin": {"name": "concord-bci2000", "version": "0.1.0"}}, {}, "for plugin"),
        ({"plugin": {"name": "concord-brainflow", "version": "0.0.9"}}, {}, "for version"),
        ({"plugin": {"name": "concord-brainflow", "version": "0.1.0", "tree_sha256": "0" * 64}},
         {"tree_sha256": "1" * 64}, "tree_sha256"),
        ({"date": "2999-01-01T00:00:00Z"}, {}, "in the future"),
    ],
)  # fmt: skip
def test_attestation_for_something_else_is_rejected(
    tmp_path: Path, over: dict[str, Any], kw: dict[str, Any], fragment: str
) -> None:
    key, pub = keypair(tmp_path)
    p = write(tmp_path, attestation_doc(**over))
    att = check_att(p, sign(p, key), pub, **kw)
    assert not att["accepted"] and fragment in att["reason"], att["reason"]


@pytest.mark.parametrize(
    ("mutate", "fragment"),
    [
        (lambda d: d.pop("hardware"), "schema"),
        (lambda d: d.update(statement="I promise it works."), "schema"),
        (lambda d: d["hardware"].pop("serial_number"), "schema"),
        (lambda d: d.update(level="hardware_tested"), "schema"),
        (lambda d: d.update(duration_s=0), "schema"),
    ],
)
def test_malformed_attestation_is_rejected(tmp_path: Path, mutate: Any, fragment: str) -> None:
    doc = attestation_doc()
    mutate(doc)
    p = write(tmp_path, doc)
    att = check_att(p, tmp_path / "missing.sig", tmp_path / "missing.pub")
    assert not att["accepted"] and fragment in att["reason"], att["reason"]


def test_unsigned_attestation_is_rejected(tmp_path: Path) -> None:
    p = write(tmp_path, attestation_doc())
    att = check_att(p, None, None)
    assert not att["accepted"] and "not signed" in att["reason"]
    (tmp_path / "bad.json").write_text("{not json", encoding="utf-8")
    assert "not valid UTF-8 JSON" in check_att(tmp_path / "bad.json", None, None)["reason"]


def test_human_participant_validation_is_never_granted() -> None:
    h = lv.human_participant_validated()
    assert h["achieved"] is False and "out of scope" in h["why"]
    future = dt.datetime(2000, 1, 1, tzinfo=dt.UTC)  # even an "accepted" fake attestation
    fake = {"accepted": True, "attested": {}, "reason": "x", "date": future.isoformat()}
    r = lv.evaluate(results(), reference="x", rules=[], attestation=fake)
    assert not r["levels"]["human_participant_validated"]["achieved"]
    assert "human_participant_validated" not in r["achieved"]
