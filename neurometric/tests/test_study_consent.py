"""Consent, withdrawal (stop collection; retain or delete per protocol), retention purge,
data-subject export / deletion and purpose limitation for sponsor roles."""
from __future__ import annotations

import json
from datetime import timedelta

import pytest

from neurometric.study import (ConsentRequired, InvalidTransition, PermissionDenied,
                               ReasonRequired, StudyService, ValidationFailed)
from neurometric.study.consent import CONSENT_SCOPES
from neurometric.study.testing import (ALL_SCOPES, FakeClock, build_world, ensure_test_key,
                                       telemetry_payload, upload_a1)

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


def _collect(svc, w, clock):
    upload_a1(svc, w.co, w.pid)
    svc.submit_response(w.part, w.pid, "NM-SESSION", {"fatigue": 3, "effort": 4,
                                                      "frustration": 2, "satisfaction": 7,
                                                      "device_problem": False})
    svc.ingest_telemetry(w.part, telemetry_payload(w.pid, clock.now - timedelta(hours=2)))


def test_consent_record_scopes_versioned(svc, w):
    c = svc.get_consent(w.co, w.pid)
    assert c["active"]["consent_document_id"] == "ICF-1"
    assert set(c["active"]["scopes"]) == set(CONSENT_SCOPES)
    assert c["active"]["scopes"]["audio_none"] is True
    svc.record_consent(w.co, w.pid, "ICF-2", "2.0", {**ALL_SCOPES, "free_text": True})
    c = svc.get_consent(w.co, w.pid)
    assert c["active"]["consent_version"] == "2.0"
    assert [h["status"] for h in c["history"]] == ["superseded", "active"]
    with pytest.raises(ValidationFailed):
        svc.record_consent(w.co, w.pid, "ICF-2", "2.0", {"telepathy": True})
    with pytest.raises(ValidationFailed):
        svc.record_consent(w.co, w.pid, "ICF-2", "2.0", {"telemetry_app_categories": True})
    with pytest.raises(PermissionDenied):
        svc.record_consent(w.sa, w.pid, "ICF-2", "2.0", {})


def test_full_withdrawal_retain_stops_collection(svc, w, clock):
    svc.generate_visits(w.co, w.pid, w.schedule["id"], "2026-03-02")
    _collect(svc, w, clock)
    with pytest.raises(ReasonRequired):
        svc.withdraw_consent(w.part, w.pid, "")
    out = svc.withdraw_consent(w.part, w.pid, "participant choice", action="retain")
    assert out["full_withdrawal"] and out["action"] == "retain" and out["deleted_counts"] == {}
    assert svc.get_participant(w.co, w.pid)["enrollment_state"] == "withdrawn"
    assert svc.telemetry_state(w.co, w.pid)["state"] == "stopped"
    # collection stops immediately for every channel
    with pytest.raises((ValidationFailed, ConsentRequired)):
        upload_a1(svc, w.co, w.pid, seed=1)
    with pytest.raises((ValidationFailed, ConsentRequired)):
        svc.submit_response(w.part, w.pid, "NM-SESSION", {"fatigue": 1})
    with pytest.raises(ConsentRequired):
        svc.ingest_telemetry(w.part, telemetry_payload(w.pid, clock.now - timedelta(hours=5)))
    # visits cancelled, data retained
    assert {v["status"] for v in svc.list_visits(w.co, w.pid)} == {"cancelled"}
    assert len(svc.list_sessions(w.co, w.pid)) == 1
    rec = svc.get_consent(w.co, w.pid)
    assert rec["withdrawals"][0]["action"] == "retain"
    assert rec["active"] is None
    with pytest.raises(InvalidTransition):
        svc.withdraw_consent(w.co, w.pid, "again")


def test_full_withdrawal_delete_per_protocol(svc, w, clock):
    _collect(svc, w, clock)
    out = svc.withdraw_consent(w.co, w.pid, "participant requested deletion", action="delete")
    # free_text was never granted, so only the three granted data scopes are deleted
    assert out["deleted_counts"] == {"functional_sessions": 1, "questionnaire_responses": 1,
                                     "telemetry_batches": 1}
    for t in ("functional_sessions", "questionnaire_responses", "telemetry_batches"):
        assert svc.db.scalar(f"SELECT COUNT(*) FROM {t}") == 0
    w_rec = svc.get_consent(w.co, w.pid)["withdrawals"][0]
    assert w_rec["action"] == "delete" and w_rec["deleted_counts"]["functional_sessions"] == 1
    assert svc.audit.verify_chain()["ok"]
    deletes = svc.db.query("SELECT * FROM audit_log WHERE action='delete'")
    assert len(deletes) == 3 and all(d["reason"] for d in deletes)


def test_study_default_withdrawal_action(svc, w, clock):
    svc.update_study(w.inv, w.study["id"], {"withdrawal_action_default": "delete"},
                     "protocol amendment 2")
    _collect(svc, w, clock)
    out = svc.withdraw_consent(w.part, w.pid, "participant choice")
    assert out["action"] == "delete"


def test_partial_withdrawal_of_telemetry(svc, w, clock):
    _collect(svc, w, clock)
    out = svc.withdraw_consent(w.part, w.pid, "no more home tracking", scopes=["home_telemetry"],
                               action="delete")
    assert not out["full_withdrawal"] and out["deleted_counts"] == {"telemetry_batches": 1}
    assert svc.get_participant(w.co, w.pid)["enrollment_state"] in ("enrolled", "active")
    c = svc.get_consent(w.co, w.pid)["active"]["scopes"]
    assert c["home_telemetry"] is False and c["telemetry_app_categories"] is False
    assert c["task_battery"] is True
    assert svc.telemetry_state(w.co, w.pid)["state"] == "stopped"
    with pytest.raises(ConsentRequired):
        svc.ingest_telemetry(w.part, telemetry_payload(w.pid, clock.now - timedelta(hours=5)))
    upload_a1(svc, w.co, w.pid, seed=2)  # task battery collection continues


def test_withdrawal_deletes_free_text(svc, w):
    svc.record_consent(w.co, w.pid, "ICF-1", "1.1", {**ALL_SCOPES, "free_text": True})
    r = svc.submit_response(w.part, w.pid, "NM-SESSION", {
        "fatigue": 3, "effort": 4, "frustration": 2, "satisfaction": 7, "device_problem": False,
        "comment": "my hand was tired"})
    assert r["has_free_text"]
    out = svc.withdraw_consent(w.part, w.pid, "remove my comments", scopes=["free_text"],
                               action="delete")
    assert out["deleted_counts"] == {"free_text_answers": 1}
    assert svc.db.scalar("SELECT free_text_json FROM questionnaire_responses") is None
    assert not svc.db.one("SELECT 1 FROM audit_log WHERE old_json LIKE '%hand was tired%' "
                          "OR new_json LIKE '%hand was tired%'")


def test_free_text_rejected_without_consent(svc, w):
    with pytest.raises(ValidationFailed) as e:
        svc.submit_response(w.part, w.pid, "NM-SESSION", {"fatigue": 3, "comment": "hello"})
    assert "free_text" in json.dumps(e.value.detail)


# --------------------------------------------------------------------------- retention
def test_retention_purge(svc, w, clock):
    upload_a1(svc, w.co, w.pid)
    svc.submit_response(w.part, w.pid, "NM-SESSION", {"fatigue": 3, "effort": 4,
                                                      "frustration": 2, "satisfaction": 7,
                                                      "device_problem": False})
    svc.ingest_telemetry(w.part, telemetry_payload(w.pid, clock.now - timedelta(hours=2)))
    with pytest.raises(ValidationFailed):
        svc.set_retention_policy(w.inv, w.study["id"], "everything", 1)
    with pytest.raises(PermissionDenied):
        svc.set_retention_policy(w.sa, w.study["id"], "telemetry", 1)
    svc.set_retention_policy(w.inv, w.study["id"], "raw_events", 30)
    svc.set_retention_policy(w.inv, w.study["id"], "telemetry", 90)
    svc.set_retention_policy(w.inv, w.study["id"], "questionnaire_responses", 365)
    with pytest.raises(PermissionDenied):
        svc.run_retention_purge(w.inv)
    clock.advance(days=10)
    assert all(p["n_affected"] == 0 for p in svc.run_retention_purge(w.admin))
    clock.advance(days=25)  # 35 days: raw events expire, metrics kept
    res = {p["data_category"]: p["n_affected"] for p in svc.run_retention_purge(w.admin)}
    assert res == {"raw_events": 1, "telemetry": 0, "questionnaire_responses": 0}
    s = svc.db.one("SELECT * FROM functional_sessions")
    assert s["events_blob"] is None and s["raw_purged"] == 1 and json.loads(s["metrics_json"])
    assert svc.integrity_check(w.admin)["ok"]  # purged raw is not an integrity failure
    clock.advance(days=60)
    res = {p["data_category"]: p["n_affected"] for p in svc.run_retention_purge(w.admin)}
    assert res["telemetry"] == 1 and svc.db.scalar("SELECT COUNT(*) FROM telemetry_batches") == 0
    clock.advance(days=300)
    res = {p["data_category"]: p["n_affected"] for p in svc.run_retention_purge(w.admin)}
    assert res["questionnaire_responses"] == 1
    assert svc.db.scalar("SELECT COUNT(*) FROM purge_log") == 12  # 4 runs x 3 policies
    assert svc.audit.verify_chain()["ok"]
    svc.set_retention_policy(w.inv, w.study["id"], "telemetry", 10)  # update is audited
    assert any(h["action"] == "update" for h in svc.audit.history(
        w.org["id"], "retention_policies",
        svc.db.scalar("SELECT id FROM retention_policies WHERE data_category='telemetry'")))


# --------------------------------------------------------------------------- data subject rights
def test_subject_export_and_deletion(svc, w, clock):
    _collect(svc, w, clock)
    exp = svc.export_subject(w.part, w.pid)
    assert exp["participant"]["id"] == w.pid
    assert len(exp["functional_sessions"]) == 1 and exp["functional_sessions"][0]["events"]
    assert len(exp["questionnaire_responses"]) == 1 and len(exp["telemetry_batches"]) == 1
    assert exp["re_identification_key_on_file"] is True
    assert "MRN-A-0001" not in json.dumps(exp)  # identity is never exported
    json.dumps(exp)  # JSON-serialisable
    with pytest.raises(PermissionDenied):
        svc.export_subject(w.sa, w.pid)
    with pytest.raises(ReasonRequired):
        svc.delete_subject(w.inv, w.pid, "")
    with pytest.raises(PermissionDenied):
        svc.delete_subject(w.co, w.pid, "request")
    counts = svc.delete_subject(w.inv, w.pid, "data subject erasure request #12")
    assert counts["participants"] == 1 and counts["functional_sessions"] == 1
    assert counts["reidentification_keys"] == 1
    for t in ("participants", "functional_sessions", "questionnaire_responses",
              "telemetry_batches", "consent_records", "reidentification_keys", "visits"):
        assert svc.db.scalar(f"SELECT COUNT(*) FROM {t} WHERE "
                             f"{'id' if t == 'participants' else 'participant_id'}=?",
                             (w.pid,)) == 0
    assert svc.db.one("SELECT active FROM users WHERE id=?", (w.part.user_id,))["active"] == 0
    assert svc.audit.verify_chain()["ok"]


# --------------------------------------------------------------------------- purpose limitation
def test_sponsor_dashboard_is_aggregate_and_consent_filtered(svc, w):
    p2 = svc.create_participant(w.co, w.study["id"], w.site["id"])
    svc.record_consent(w.co, p2["id"], "ICF-1", "1.0",
                       {**ALL_SCOPES, "sharing_with_sponsor": False})
    svc.transition(w.co, p2["id"], "consented")
    svc.transition(w.co, p2["id"], "enrolled")
    upload_a1(svc, w.co, w.pid)
    upload_a1(svc, w.co, p2["id"], seed=3)
    d = svc.dashboard(w.sa, w.study["id"])
    assert d["n_participants"] == 1  # p2 did not consent to sponsor sharing
    blob = json.dumps(d)
    assert w.pid not in blob and p2["id"] not in blob  # no participant identifiers at all
    assert d["audience"] == "sponsor"
    full = svc.dashboard(w.inv, w.study["id"])
    assert full["n_participants"] == 2


def test_small_cells_suppressed(svc, w):
    svc.update_study(w.inv, w.study["id"], {"min_cell_size": 3}, "disclosure control")
    upload_a1(svc, w.co, w.pid)
    d = svc.dashboard(w.sa, w.study["id"])
    t = [x for x in d["task_trends"] if x["task_id"] == "A1"][0]
    assert t["n"] == 1 and t["suppressed"] and t["mean"] is None
