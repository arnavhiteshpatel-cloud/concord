"""A well-behaved plugin passes every check, through the real plugin host and BrainOS."""

from __future__ import annotations

import json
from typing import Any

import pytest
from certify_helpers import certify, check

from brainos_certify.model import CHECK_IDS
from brainos_certify.report import NOTICE, to_markdown, validate_report
from brainos_certify.runtime_phase import RUNTIME_CHECKS, brainos_available

HAVE_BRAINOS = brainos_available()[0]


def test_every_check_passes_or_is_not_applicable(good_report: dict[str, Any]) -> None:
    by_status = {c["id"]: c["status"] for c in good_report["checks"]}
    assert list(by_status) == list(CHECK_IDS)
    # module:Class reference: entry point / distribution cannot be verified -> warnings
    assert by_status["manifest.entry_point"] == "warn"
    assert by_status["manifest.distribution"] == "warn"
    not_applicable = {"performance.latency"}  # 'source' clock: no relation to a host clock
    for cid, status in by_status.items():
        if cid in ("manifest.entry_point", "manifest.distribution"):
            continue
        if cid in not_applicable or (cid in RUNTIME_CHECKS and not HAVE_BRAINOS):
            assert status == "not_run" and not check(good_report, cid)["applicable"]
            continue
        assert status == "pass", (cid, check(good_report, cid)["reason"])
    assert good_report["summary"]["level"] == "adapter_implementation"
    assert good_report["summary"]["exit_code"] == 0
    assert good_report["levels"]["achieved"] == ["adapter_implementation"]


def test_measured_evidence(good_report: dict[str, Any]) -> None:
    rate = check(good_report, "timing.rate")["evidence"]["streams"]["sig"]
    assert rate["nominal_hz"] == 500.0 and abs(rate["error_percent"]) < 0.5
    thr = check(good_report, "performance.throughput")["evidence"]["streams"]["sig"]
    assert abs(thr["error_percent"]) < 2.0
    jit = check(good_report, "timing.jitter")["evidence"]["streams"]["sig"]
    assert jit["residual_ms"]["max"] < 1e-3  # timestamps exactly on the sample grid
    assert {"p50", "p95", "p99", "max"} <= set(jit["arrival_interval_ms"])
    idx = check(good_report, "integrity.sample_index")["evidence"]
    assert idx["gaps"] == 0 and idx["lost_samples"] == 0 and idx["samples"] > 0
    res = check(good_report, "performance.host_resources")["evidence"]
    assert res["cpu_s"] is not None and res["rss_mib_peak"] > 0
    kill = check(good_report, "reconnect.host_killed")["evidence"]
    assert kill["kill"]["detected_as"] == "HostDied" and kill["kill"]["killed"]
    assert kill["kill"]["detect_s"] < 2.0
    assert kill["identity_unchanged"] and kill["fresh_host_exit_code"] == 0
    assert kill["first_data_after_host_start_s"] > 0
    ident = check(good_report, "metadata.channel_identity")["evidence"]
    opens = ["open_1", "reopen_same_host", "fresh_host_after_kill"]
    assert ident["opens_compared"] == opens + (["brainos_runtime"] if HAVE_BRAINOS else [])


@pytest.mark.skipif(not HAVE_BRAINOS, reason="BrainOS not installed: runtime phase not run")
def test_runtime_phase(good_report: dict[str, Any]) -> None:
    from brainos.contracts import SCHEMA_VERSION

    env = check(good_report, "runtime.envelopes")["evidence"]
    assert env["schema_version"] == SCHEMA_VERSION
    assert env["event_schema_versions"] == {SCHEMA_VERSION: env["events_validated"]}
    assert env["events_validated"] > 0 and not env["invalid"]
    assert env["event_types"].get("recording.frame", 0) > 0
    assert env["event_types"].get("recording.annotation", 0) > 0
    neg = check(good_report, "runtime.negotiation")["evidence"]
    assert neg["expected_granted"] == ["device_status", "recording"]
    assert neg["negotiations"]["command_required"]["status"] == "suspended"
    desc = check(good_report, "runtime.descriptor")["evidence"]["brainos"]
    assert desc["kind"] == "simulated" and desc["modality"] == "ecog" and desc["invasive"] is True
    assert desc["integration"]["kind"] == "plugin" and desc["integration"]["isolated"] is True


def test_report_schema_and_notice(good_report: dict[str, Any]) -> None:
    assert validate_report(good_report) == []
    assert "not hardware certification" in good_report["notice"]
    first = next(iter(good_report))
    assert first == "notice"  # the disclaimer is the first key of the JSON report
    md = to_markdown(good_report)
    head = md.splitlines()[:4]
    assert head[0].startswith("# BrainOS integration certification")
    assert NOTICE in head[2]
    assert "| `timing.rate` | PASS |" in md
    assert "human_participant_validated" in md


def test_secret_options_are_redacted(good_report: dict[str, Any]) -> None:
    text = json.dumps(good_report)
    assert "s3cr3t-value" not in text
    assert good_report["options"]["plugin_options_requested"]["api_token"] == "<redacted>"
    assert good_report["options"]["plugin_options_resolved"]["api_token"] == "<redacted>"
    assert "s3cr3t-value" not in to_markdown(good_report)


def test_identity_hashes_the_plugin_files(good_report: dict[str, Any]) -> None:
    mod = good_report["plugin"]["identity"]["module"]
    assert mod["name"] == "certify_test_plugins"
    assert len(mod["tree_sha256"]) == 64
    assert all(len(f["sha256"]) == 64 for f in mod["files"])


def test_unix_clock_latency_measured() -> None:
    r = certify(options={"clock": "unix"})
    lat = check(r, "performance.latency")
    assert lat["status"] == "pass"
    ms = lat["evidence"]["newest_sample_latency_ms"]
    assert ms["n"] > 10 and ms["p50"] is not None
    clock = check(r, "timing.clock_domain")
    assert clock["status"] == "pass" and clock["evidence"]["reference_clock"].startswith("wall")
