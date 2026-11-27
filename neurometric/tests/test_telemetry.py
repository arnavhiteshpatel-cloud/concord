"""Telemetry: aggregate-only allowlist (forbidden content rejected and never stored), consent and
visible recording state, and Experiment O integrity cases (duplicates, out-of-order batches,
overlapping periods, clock skew, hashing) with verification of the stored aggregates."""
from __future__ import annotations

import hashlib
import json
from datetime import timedelta

import pytest

from neurometric.study import ConsentRequired, PermissionDenied, StudyService, ValidationFailed
from neurometric.study.db import canonical_json
from neurometric.study.telemetry import batch_digest, validate_payload
from neurometric.study.testing import (ALL_SCOPES, FakeClock, build_world, ensure_test_key,
                                       telemetry_payload)

ensure_test_key()


@pytest.fixture
def clock():
    return FakeClock()


@pytest.fixture
def svc(tmp_path, clock):
    s = StudyService(tmp_path / "nm.sqlite", clock)
    yield s
    s.db.close()


@pytest.fixture
def w(svc):
    return build_world(svc, "A")


def day(clock, d, hour=8):
    return (clock.now - timedelta(days=d)).replace(hour=hour, minute=0, second=0, microsecond=0)


def reasons(exc):
    return exc.value.detail.get("reasons", [])


# --------------------------------------------------------------------------- allowlist
def test_valid_payload_passes_validator(w, clock):
    assert validate_payload(telemetry_payload(w.pid, day(clock, 1))) == []


FORBIDDEN = [
    ("text", {"text": "hello mum"}),
    ("keystrokes", {"keystrokes": ["h", "e", "l", "l", "o"]}),
    ("url", {"url": "https://example.org/private"}),
    ("window_title", {"window_title": "Inbox - private mail"}),
    ("screenshot", {"screenshot": "iVBORw0KGgoAAAANSUhEUg=="}),
    ("clipboard", {"clipboard": "account 1234"}),
    ("notes", {"notes": "free text from the app"}),
    ("nested_meta", {"meta": {"page": "bank"}}),
    ("counts_text", {"interaction_counts": {"pointer": 1, "text": "abc"}}),
    ("counts_keys", {"interaction_counts": {"pointer": 1, "keys": ["a", "b"]}}),
    ("counts_string", {"interaction_counts": {"pointer": "lots"}}),
    ("app_name", {"app_category_minutes": {"com.whatsapp": 10}}),
    ("app_url", {"app_category_minutes": {"https://facebook.com": 10}}),
    ("client_hostname", {"client": {"app_version": "0.1.0", "hostname": "jane-laptop"}}),
    ("assist_note", {"self_reported_assistance": [{"type": "setup", "minutes": 5,
                                                   "note": "my son helped"}]}),
    ("assist_type_free", {"self_reported_assistance": [{"type": "my son", "minutes": 5}]}),
    ("fatigue_text", {"self_reported_fatigue": "very tired"}),
    ("fatigue_range", {"self_reported_fatigue": 11}),
    ("pseudonym_format", {"participant": "Jane Doe"}),
    ("device_session_url", {"device_session_id": "http://x"}),
]


@pytest.mark.parametrize("name,extra", FORBIDDEN, ids=[f[0] for f in FORBIDDEN])
def test_forbidden_content_rejected_and_never_stored(svc, w, clock, name, extra):
    p = telemetry_payload(w.pid, day(clock, 1))
    p.update(extra)  # adds a forbidden key or replaces an allowed field with forbidden content
    with pytest.raises(ValidationFailed) as e:
        svc.ingest_telemetry(w.part, p)
    assert e.value.code == "telemetry_rejected" and reasons(e)
    assert svc.db.scalar("SELECT COUNT(*) FROM telemetry_batches") == 0
    # the content never reaches the database (not in receipts, not in the audit trail)
    dump = "\n".join(str(r) for t in ("telemetry_receipts", "audit_log")
                     for r in svc.db.query(f"SELECT * FROM {t}"))
    for v in extra.values():
        for needle in ([v] if isinstance(v, str) else []):
            assert needle not in dump


def test_content_keys_are_labelled_forbidden(w, clock):
    p = telemetry_payload(w.pid, day(clock, 1), url="https://x.org", window_title="Bank",
                          keystrokes=["a"], foo=1)
    r = validate_payload(p)
    assert "forbidden_field:url" in r and "forbidden_field:window_title" in r
    assert "forbidden_field:keystrokes" in r and "array_not_allowed:keystrokes" in r
    assert "url_like_value:url" in r and "unknown_field:foo" in r
    assert validate_payload([1, 2]) == ["payload_not_object"]
    assert "missing_field:interaction_counts" in validate_payload(
        {k: v for k, v in telemetry_payload(w.pid, day(clock, 1)).items()
         if k != "interaction_counts"})


# --------------------------------------------------------------------------- consent & state
def test_consent_and_visible_recording_state(svc, w, clock):
    svc.ingest_telemetry(w.part, telemetry_payload(w.pid, day(clock, 3)))
    st = svc.set_telemetry_state(w.part, w.pid, "paused", "taking a break")
    assert st["state"] == "paused"
    with pytest.raises(ValidationFailed) as e:
        svc.ingest_telemetry(w.part, telemetry_payload(w.pid, day(clock, 2)))
    assert reasons(e) == ["telemetry_paused"]
    svc.set_telemetry_state(w.part, w.pid, "active", "resume")
    svc.ingest_telemetry(w.part, telemetry_payload(w.pid, day(clock, 2)))
    svc.set_telemetry_state(w.cp, w.pid, "stopped", "care partner stopped recording")
    with pytest.raises(ValidationFailed) as e:
        svc.ingest_telemetry(w.part, telemetry_payload(w.pid, day(clock, 1)))
    assert reasons(e) == ["telemetry_stopped"]
    with pytest.raises(PermissionDenied):
        svc.set_telemetry_state(w.sa, w.pid, "active")
    with pytest.raises(PermissionDenied):
        svc.ingest_telemetry(w.co, telemetry_payload(w.pid, day(clock, 1)))
    svc.record_consent(w.co, w.pid, "ICF-1", "1.2", {**ALL_SCOPES, "home_telemetry": False,
                                                    "telemetry_app_categories": False})
    with pytest.raises(ConsentRequired):
        svc.set_telemetry_state(w.part, w.pid, "active")
    with pytest.raises(ConsentRequired):
        svc.ingest_telemetry(w.part, telemetry_payload(w.pid, day(clock, 1)))
    assert svc.db.scalar("SELECT COUNT(*) FROM telemetry_batches") == 2


def test_app_categories_require_their_own_scope(svc, w, clock):
    svc.record_consent(w.co, w.pid, "ICF-1", "1.2", {**ALL_SCOPES,
                                                    "telemetry_app_categories": False})
    p = telemetry_payload(w.pid, day(clock, 1), app_category_minutes={"communication": 10})
    with pytest.raises(ValidationFailed) as e:
        svc.ingest_telemetry(w.part, p)
    assert reasons(e) == ["app_categories_not_consented"]
    p.pop("app_category_minutes")
    assert svc.ingest_telemetry(w.part, p)["status"] == "accepted"


def test_participant_mismatch_and_care_partner(svc, w, clock):
    other = svc.create_participant(w.co, w.study["id"], w.site["id"])
    with pytest.raises(ValidationFailed) as e:
        svc.ingest_telemetry(w.part, telemetry_payload(other["id"], day(clock, 1)))
    assert reasons(e) == ["participant_mismatch"]
    assert svc.ingest_telemetry(w.cp, telemetry_payload(w.pid, day(clock, 1)))["status"] == "accepted"


def test_local_review_shows_exactly_what_was_sent(svc, w, clock):
    p = telemetry_payload(w.pid, day(clock, 1), app_category_minutes={"web": 12.5})
    r = svc.ingest_telemetry(w.part, p)
    with pytest.raises(ValidationFailed):
        svc.ingest_telemetry(w.part, {**p, "url": "https://x.org"})
    rev = svc.review_own_telemetry(w.part, w.pid)
    assert rev["batches"][0]["payload"] == p
    assert canonical_json(rev["batches"][0]["payload"]) == canonical_json(p)
    assert rev["batches"][0]["payload_sha256"] == r["payload_sha256"] == batch_digest(p)
    assert hashlib.sha256(canonical_json(p).encode()).hexdigest() == r["payload_sha256"]
    outcomes = [x["outcome"] for x in rev["receipts"]]
    assert outcomes == ["accepted", "rejected"]
    assert "forbidden_field:url" in rev["receipts"][1]["reasons"]
    assert "https://x.org" not in json.dumps(rev)
    with pytest.raises(PermissionDenied):
        svc.review_own_telemetry(w.co, w.pid)


# --------------------------------------------------------------------------- Experiment O
def test_duplicates_are_idempotent(svc, w, clock):
    p = telemetry_payload(w.pid, day(clock, 1))
    a = svc.ingest_telemetry(w.part, p)
    b = svc.ingest_telemetry(w.part, dict(p))
    assert a["status"] == "accepted" and b["status"] == "duplicate"
    assert a["batch_id"] == b["batch_id"]
    assert svc.db.scalar("SELECT COUNT(*) FROM telemetry_batches") == 1
    with pytest.raises(ValidationFailed) as e:
        svc.ingest_telemetry(w.part, {**p, "active_minutes": 45})
    assert reasons(e) == ["conflicting_duplicate"]
    assert svc.telemetry_summary(w.co, w.pid)["active_minutes"] == 30


def test_out_of_order_batches_accepted_and_flagged(svc, w, clock):
    r3 = svc.ingest_telemetry(w.part, telemetry_payload(w.pid, day(clock, 1), active_minutes=10))
    r1 = svc.ingest_telemetry(w.part, telemetry_payload(w.pid, day(clock, 3), active_minutes=20))
    r2 = svc.ingest_telemetry(w.part, telemetry_payload(w.pid, day(clock, 2), active_minutes=40))
    assert r3["flags"] == [] and "out_of_order" in r1["flags"] and "out_of_order" in r2["flags"]
    s = svc.telemetry_summary(w.co, w.pid)
    assert s["active_minutes"] == 70 and s["n_batches"] == 3
    assert list(s["days"]) == sorted(s["days"])  # aggregated by period, not arrival


def test_overlapping_periods(svc, w, clock):
    t0 = day(clock, 1)
    svc.ingest_telemetry(w.part, telemetry_payload(w.pid, t0, hours=2))
    with pytest.raises(ValidationFailed) as e:
        svc.ingest_telemetry(w.part, telemetry_payload(w.pid, t0 + timedelta(hours=1), hours=2))
    assert reasons(e) == ["overlapping_period"]
    # adjacent (touching) periods are not overlaps
    assert svc.ingest_telemetry(w.part, telemetry_payload(
        w.pid, t0 + timedelta(hours=2), hours=1))["status"] == "accepted"
    # a second device may overlap in time: accepted but flagged
    r = svc.ingest_telemetry(w.part, telemetry_payload(w.pid, t0, hours=1,
                                                       device_session_id="tablet-session-02"))
    assert "overlaps_other_device_session" in r["flags"]


def test_clock_skew_and_period_sanity(svc, w, clock):
    now = clock.now
    with pytest.raises(ValidationFailed) as e:
        svc.ingest_telemetry(w.part, telemetry_payload(w.pid, now, hours=1))
    assert reasons(e) == ["future_period"]
    r = svc.ingest_telemetry(w.part, telemetry_payload(w.pid, now - timedelta(minutes=58),
                                                       hours=1))
    assert "clock_skew_tolerated" in r["flags"]
    bad = [
        (telemetry_payload(w.pid, now - timedelta(days=3), hours=25), "period_too_long"),
        (telemetry_payload(w.pid, now - timedelta(days=4), hours=1, active_minutes=61),
         "active_minutes_exceed_period"),
        (telemetry_payload(w.pid, now - timedelta(days=5), hours=1,
                           self_reported_assistance=[{"type": "physical", "minutes": 90}]),
         "assistance_minutes_exceed_period"),
        (telemetry_payload(w.pid, now - timedelta(days=6), hours=1,
                           app_category_minutes={"web": 50}), "app_minutes_exceed_active_minutes"),
    ]
    for p, code in bad:
        with pytest.raises(ValidationFailed) as e:
            svc.ingest_telemetry(w.part, p)
        assert code in reasons(e)
    p = telemetry_payload(w.pid, now - timedelta(days=2))
    p["period_end"], p["period_start"] = p["period_start"], p["period_end"]
    with pytest.raises(ValidationFailed) as e:
        svc.ingest_telemetry(w.part, p)
    assert "period_end_not_after_start" in reasons(e)
    p = telemetry_payload(w.pid, now - timedelta(days=2))
    p["period_start"] = "2026-03-01T08:00:00"  # naive time stamps rejected
    assert "invalid_value:period_start" in validate_payload(p)


def test_batch_hash_integrity(svc, w, clock):
    p = telemetry_payload(w.pid, day(clock, 1))
    good = {**p, "batch_sha256": batch_digest(p)}
    assert svc.ingest_telemetry(w.part, good)["payload_sha256"] == good["batch_sha256"]
    p2 = telemetry_payload(w.pid, day(clock, 2))
    with pytest.raises(ValidationFailed) as e:
        svc.ingest_telemetry(w.part, {**p2, "batch_sha256": "0" * 64})
    assert reasons(e) == ["hash_mismatch"]
    assert svc.verify_telemetry_integrity()["ok"]
    svc.db.execute("UPDATE telemetry_batches SET payload_json=replace(payload_json, "
                   "'\"active_minutes\":30', '\"active_minutes\":300')")
    assert not svc.verify_telemetry_integrity()["ok"]


def test_experiment_o_stored_aggregates_are_correct(svc, w, clock):
    """Inject a noisy stream (duplicates, out-of-order, overlap, skew, forbidden fields,
    conflicts) and check the stored aggregates equal the sum over the valid unique batches."""
    expected_minutes, expected_pointer, expected_chars = 0, 0, 0
    sent = []
    for d in (5, 3, 4, 1, 2):  # out of order arrival
        p = telemetry_payload(w.pid, day(clock, d), active_minutes=10 * d,
                              interaction_counts={"pointer": 100 * d, "select": d,
                                                  "text_chars_count": 7 * d})
        sent.append(p)
        expected_minutes += 10 * d
        expected_pointer += 100 * d
        expected_chars += 7 * d
    noise = [
        sent[0], sent[2], dict(sent[3]),  # exact re-sends (retries)
        {**sent[1], "active_minutes": 99},  # conflicting duplicate
        telemetry_payload(w.pid, day(clock, 3) + timedelta(minutes=30)),  # overlap
        telemetry_payload(w.pid, clock.now + timedelta(hours=2)),  # future (skew)
        {**telemetry_payload(w.pid, day(clock, 6)), "window_title": "Bank"},  # forbidden
        {**telemetry_payload(w.pid, day(clock, 7)),
         "interaction_counts": {"pointer": 1, "keys": ["p", "w"]}},  # keystroke array
    ]
    outcomes = []
    for p in sent[:2] + [noise[0]] + sent[2:] + noise[1:]:
        try:
            outcomes.append(svc.ingest_telemetry(w.part, p)["status"])
        except ValidationFailed:
            outcomes.append("rejected")
    assert outcomes.count("accepted") == 5
    assert outcomes.count("duplicate") == 3
    assert outcomes.count("rejected") == 5
    s = svc.telemetry_summary(w.co, w.pid)
    assert s["n_batches"] == 5
    assert s["active_minutes"] == expected_minutes
    assert s["interaction_counts"]["pointer"] == expected_pointer
    assert s["interaction_counts"]["text_chars_count"] == expected_chars
    assert s["assistance_minutes"] == {"setup": 25}
    assert svc.verify_telemetry_integrity()["ok"]
    rec = svc.db.query("SELECT outcome, COUNT(*) n FROM telemetry_receipts GROUP BY outcome")
    assert {r["outcome"]: r["n"] for r in rec} == {"accepted": 5, "duplicate": 3, "rejected": 5}
    assert svc.audit.verify_chain()["ok"]
