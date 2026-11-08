"""Each crafted defect is caught by a specific check with the expected status."""

from __future__ import annotations

from pathlib import Path

import pytest
from certify_helpers import certify, check

# defect -> (check that must catch it, expected status, level still achieved?)
CASES: dict[str, tuple[str, str, bool]] = {
    "unknown_units": ("metadata.units", "warn", True),
    "no_modality": ("metadata.modality", "warn", True),
    "shuffle_labels": ("metadata.channel_identity", "fail", False),
    "wrong_rate": ("timing.rate", "fail", False),
    "gaps": ("integrity.sample_index", "warn", True),
    "overlap": ("integrity.sample_index", "fail", False),
    "decreasing": ("timing.monotonic", "fail", False),
    "marker_disorder": ("integrity.markers", "fail", False),
    "markers_off_clock": ("integrity.markers", "warn", True),
    "nan": ("integrity.chunk_validation", "fail", False),
    "hang_read": ("integrity.read", "fail", False),
    "unix_offset": ("timing.clock_domain", "fail", False),
    "jitter": ("timing.jitter", "warn", True),
    "invalid_stats": ("integrity.plugin_stats", "warn", True),
    "lossy_stats": ("integrity.plugin_stats", "warn", True),
}


@pytest.mark.parametrize("defect", sorted(CASES))
def test_defect_is_caught(defect: str) -> None:
    check_id, status, level = CASES[defect]
    r = certify(options={"defect": defect})
    c = check(r, check_id)
    assert c["status"] == status, (defect, c["reason"])
    assert c["reason"]
    assert (r["summary"]["level"] == "adapter_implementation") is level, r["summary"]["blocking"]
    assert r["summary"]["exit_code"] == (0 if level else 1)
    if not level:
        assert any(check_id in b for b in r["summary"]["blocking"]) or any(
            b.startswith("integrity.read") for b in r["summary"]["blocking"]
        )


def test_wrong_rate_also_fails_throughput() -> None:
    r = certify(options={"defect": "wrong_rate"})
    t = check(r, "performance.throughput")
    assert t["status"] == "fail" and "falls behind" in t["reason"]
    rate = check(r, "timing.rate")["evidence"]["streams"]["sig"]
    assert -11.0 < rate["error_percent"] < -9.0  # 450 Hz delivered, 500 Hz declared


def test_gaps_are_counted() -> None:
    r = certify(options={"defect": "gaps"})
    ev = check(r, "integrity.sample_index")["evidence"]
    main = ev["streams"]["main.sig"]
    assert main["gaps"] >= 5 and main["lost_samples"] == 5 * main["gaps"]
    assert main["overlaps"] == 0


def test_invalid_data_names_its_cause() -> None:
    r = certify(options={"defect": "nan"})
    read = check(r, "integrity.read")
    assert read["status"] == "fail" and "integrity.chunk_validation" in read["reason"]
    # the measurement checks do not run on a session the host stopped
    assert check(r, "timing.rate")["status"] == "not_run"
    assert check(r, "reconnect.host_killed")["status"] == "not_run"


def test_stale_lock_breaks_reopen_after_kill(tmp_path: Path) -> None:
    lock = tmp_path / "device.lock"
    r = certify(options={"defect": "stale_lock", "lock_file": str(lock)})
    assert check(r, "reconnect.clean_reopen")["status"] == "pass"  # close() released it
    killed = check(r, "reconnect.host_killed")
    assert killed["status"] == "fail" and "device busy" in killed["reason"]
    assert killed["evidence"]["kill"]["detected_as"] == "HostDied"
    assert r["summary"]["exit_code"] == 1


def test_shuffled_labels_fail_clean_reopen_too() -> None:
    r = certify(options={"defect": "shuffle_labels"})
    reopen = check(r, "reconnect.clean_reopen")
    assert reopen["status"] == "fail" and "identity changed" in reopen["reason"]
    diffs = check(r, "metadata.channel_identity")["evidence"]["differences"]
    assert "sig.labels" in diffs["reopen_same_host"][0]


@pytest.mark.parametrize(
    ("cls", "check_id"),
    [
        ("Api2Plugin", "manifest.api_compat"),
        ("EmptyDescriptionPlugin", "manifest.valid"),
        ("NoDevicesPlugin", "manifest.discover"),
        ("RATE", "manifest.load"),  # not a SourcePlugin class
    ],
)
def test_plugin_level_defects(cls: str, check_id: str) -> None:
    r = certify(cls)
    c = check(r, check_id)
    assert c["status"] == "fail", c["reason"]
    assert r["summary"]["exit_code"] == 1 and r["summary"]["level"] is None
    # nothing after the failure ran, and that is recorded rather than passed
    assert check(r, "integrity.read")["status"] == "not_run"


def test_missing_module_fails_to_load() -> None:
    r = certify("Nope", plugin="no_such_module_for_certify:Plugin")
    c = check(r, "manifest.load")
    assert c["status"] == "fail" and "No module named" in c["reason"]


def test_unknown_device_key_fails_open() -> None:
    r = certify(device="dev9")
    assert check(r, "manifest.discover")["status"] == "warn"
    c = check(r, "metadata.session_valid")
    assert c["status"] == "fail" and "OpenFailed" in c["reason"]


def test_invalid_option_fails_open() -> None:
    r = certify(options={"defect": "no_such_defect"})
    c = check(r, "metadata.session_valid")
    assert c["status"] == "fail" and "InvalidOptions" in c["reason"]
