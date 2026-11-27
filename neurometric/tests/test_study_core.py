"""Study data model: migrations, permission matrix, tenant isolation, site scoping, enrollment
state machine, schedules / visit windows, reason-for-change, demo isolation, security."""
from __future__ import annotations

import sqlite3
from datetime import date, timedelta

import pytest

from neurometric.study import (AuthenticationFailed, ConsentRequired, DemoMixError,
                               InvalidTransition, NotFound, PermissionDenied, ReasonRequired,
                               StudyService, ValidationFailed)
from neurometric.study.audit import SYSTEM
from neurometric.study.clinical import TRANSITIONS, expand_schedule, validate_schedule
from neurometric.study.db import Database
from neurometric.study.permissions import PERMISSIONS, ROLES, can, matrix
from neurometric.study.schema import MIGRATIONS
from neurometric.study.security import (decrypt_field, encrypt_field, hash_password,
                                        verify_password)
from neurometric.study.testing import (ALL_SCOPES, SCHEDULE, TEST_PASSWORD, FakeClock, actor_of,
                                       build_world, ensure_test_key, upload_a1)

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


# --------------------------------------------------------------------------- storage
def test_database_pragmas_and_migrations(tmp_path):
    db = Database(tmp_path / "x.sqlite")
    assert db.scalar("PRAGMA journal_mode") == "wal"
    assert db.scalar("PRAGMA foreign_keys") == 1
    assert db.schema_version() == max(v for v, _, _ in MIGRATIONS)
    rows = db.query("SELECT * FROM schema_migrations ORDER BY version")
    assert [r["version"] for r in rows] == [v for v, _, _ in MIGRATIONS]
    db.close()
    db2 = Database(tmp_path / "x.sqlite")  # re-open: idempotent
    assert db2.migrate() == []
    db2.close()


def test_changed_applied_migration_is_refused(tmp_path):
    db = Database(tmp_path / "x.sqlite")
    db.execute("UPDATE schema_migrations SET checksum='tampered' WHERE version=1")
    db.close()
    with pytest.raises(RuntimeError, match="changed after it was applied"):
        Database(tmp_path / "x.sqlite")


def test_timestamps_are_utc_server_clock(svc, w, clock):
    p = svc.get_participant(w.co, w.pid)
    assert p["created_at"].endswith("Z")
    assert p["created_at"].startswith(clock.now.date().isoformat())
    e = svc.audit.entries(w.org["id"], limit=1)[0]
    assert e["at"].endswith("Z")


# --------------------------------------------------------------------------- permissions
def test_permission_matrix_is_complete_and_least_privilege():
    m = matrix()
    assert set(m) == set(PERMISSIONS)
    for perm, roles in m.items():
        assert set(roles) == set(ROLES)
    # sponsor analysts never see participant-level data or the re-identification table
    for perm in ("participant.read", "reid.read", "reid.write", "session.read",
                 "questionnaire.read", "subject.export", "audit.read"):
        assert not can("sponsor_analyst", perm), perm
    # administrators run the system but do not read clinical data
    for perm in ("participant.read", "session.read", "reid.read", "questionnaire.read"):
        assert not can("admin", perm), perm
    assert can("investigator", "signature.approve") and not can("coordinator", "signature.approve")
    assert can("participant", "telemetry.ingest") and not can("coordinator", "telemetry.ingest")
    with pytest.raises(KeyError):
        can("admin", "no.such.permission")


ROLE_EXPECT = {
    # action -> roles that may perform it on their own organization's data
    "create_study": {"investigator", "admin"},
    "create_site": {"admin"},
    "create_user": {"admin"},
    "read_participant": {"participant", "care_partner", "coordinator", "investigator"},
    "dashboard": {"sponsor_analyst", "investigator"},
    "verify_audit": {"investigator", "admin"},
}


@pytest.mark.parametrize("role", ROLES)
def test_role_actions_enforced(svc, w, role):
    a = w.users[role]
    actions = {
        "create_study": lambda: svc.create_study(a, f"X-{role}", "t"),
        "create_site": lambda: svc.create_site(a, f"X{role[:3]}", "s"),
        "create_user": lambda: svc.create_user(a, org_id=a.org_id, username=f"n-{role}",
                                               password=TEST_PASSWORD, role="coordinator"),
        "read_participant": lambda: svc.get_participant(a, w.pid),
        "dashboard": lambda: svc.dashboard(a, w.study["id"]),
        "verify_audit": lambda: svc.integrity_check(a),
    }
    for name, fn in actions.items():
        if role in ROLE_EXPECT[name]:
            fn()
        else:
            with pytest.raises((PermissionDenied, NotFound)):
                fn()


def test_site_scoping_for_site_staff(svc, w):
    # coordinator of another site in the same org cannot see the participant
    with pytest.raises(NotFound):
        svc.get_participant(w.co2, w.pid)
    assert svc.list_participants(w.co2, w.study["id"]) == []
    with pytest.raises(PermissionDenied):
        svc.create_participant(w.co2, w.study["id"], w.site["id"])


def test_participant_sees_only_self_and_care_partner_only_linked(svc, w):
    other = svc.create_participant(w.co, w.study["id"], w.site["id"])
    assert svc.get_participant(w.part, w.pid)["id"] == w.pid
    with pytest.raises(NotFound):
        svc.get_participant(w.part, other["id"])
    assert svc.get_participant(w.cp, w.pid)["id"] == w.pid
    with pytest.raises(NotFound):
        svc.get_participant(w.cp, other["id"])


def test_sponsor_gets_aggregate_only_error(svc, w):
    with pytest.raises(PermissionDenied) as e:
        svc._participant(w.sa, w.pid)
    assert e.value.code in ("aggregate_only", "forbidden")


# --------------------------------------------------------------------------- tenant isolation
def test_tenant_isolation(svc, w):
    b = build_world(svc, "B")
    # B's staff cannot read, list, modify or reference A's records
    for a in (b.co, b.inv):
        with pytest.raises(NotFound):
            svc.get_participant(a, w.pid)
        with pytest.raises(NotFound):
            svc.get_study(a, w.study["id"])
        with pytest.raises(NotFound):
            svc.list_participants(a, w.study["id"])
    with pytest.raises(NotFound):
        svc.dashboard(b.sa, w.study["id"])
    with pytest.raises(NotFound):
        svc.transition(b.co, w.pid, "active")
    with pytest.raises(NotFound):
        svc.create_participant(b.co, w.study["id"], b.site["id"])
    with pytest.raises(NotFound):
        svc.create_participant(b.co, b.study["id"], w.site["id"])
    with pytest.raises(NotFound):
        svc.create_user(b.admin, org_id=w.org["id"], username="intruder",
                        password=TEST_PASSWORD, role="admin")
    with pytest.raises(NotFound):
        svc.raise_query(b.sa, b.study["id"], "participants", w.pid, "?")
    with pytest.raises(NotFound):
        svc.correct_record(b.co, "participants", w.pid, {"cohort": "x"}, "r")
    with pytest.raises(NotFound):
        svc.sign(b.inv, TEST_PASSWORD, "participants", w.pid, "approved")
    s = upload_a1(svc, w.co, w.pid)
    with pytest.raises(NotFound):
        svc.get_session(b.co, s["id"])
    # lists only show own tenant's data
    assert {x["id"] for x in svc.list_studies(b.inv)} == {b.study["id"]}
    assert all(u["org_id"] == b.org["id"] for u in svc.list_users(b.admin))
    assert all(e["org_id"] == b.org["id"] for e in svc.audit.entries(b.org["id"], 1000))
    # participant of B cannot ingest telemetry for A's participant
    from neurometric.study.testing import telemetry_payload
    with pytest.raises(ValidationFailed):
        svc.ingest_telemetry(b.part, telemetry_payload(w.pid, svc.db.now() - timedelta(hours=3)))


# --------------------------------------------------------------------------- enrollment
def test_enrollment_state_machine(svc, w):
    p = svc.create_participant(w.co, w.study["id"], w.site["id"])
    pid = p["id"]
    assert p["enrollment_state"] == "screening"
    with pytest.raises(InvalidTransition):
        svc.transition(w.co, pid, "enrolled")  # must consent first
    with pytest.raises(InvalidTransition):
        svc.transition(w.co, pid, "consented")  # no consent record yet
    svc.record_consent(w.co, pid, "ICF-1", "1.0", dict(ALL_SCOPES))
    svc.transition(w.co, pid, "consented")
    svc.transition(w.co, pid, "enrolled")
    svc.transition(w.co, pid, "active")
    with pytest.raises(ReasonRequired):
        svc.transition(w.co, pid, "lost")
    svc.transition(w.co, pid, "lost", "no contact for 60 days")
    svc.transition(w.co, pid, "active", "re-contacted")
    svc.transition(w.co, pid, "completed", "protocol complete")
    for target in ("active", "withdrawn", "screening"):
        with pytest.raises(InvalidTransition):
            svc.transition(w.co, pid, target, "x")
    hist = svc.enrollment_history(w.co, pid)
    assert [h["to_state"] for h in hist] == ["consented", "enrolled", "active", "lost", "active",
                                             "completed"]
    assert TRANSITIONS["completed"] == frozenset() and TRANSITIONS["withdrawn"] == frozenset()


def test_pseudonyms_random_and_not_derived(svc, w):
    ids = {svc.create_participant(w.co, w.study["id"], w.site["id"],
                                  identifier="SAME-IDENTIFIER")["id"] for _ in range(5)}
    assert len(ids) == 5
    assert all(i.startswith("NM-") and len(i) == 13 for i in ids)


# --------------------------------------------------------------------------- schedules
def test_schedule_expansion_with_windows_and_recurrence():
    v = expand_schedule(SCHEDULE, date(2026, 1, 10))
    codes = [x["visit_code"] for x in v]
    assert codes == ["baseline", "home_01", "home_02", "week_02", "home_03"]  # same day: by code
    b = v[0]
    assert (b["target_date"], b["window_start"], b["window_end"]) == (
        date(2026, 1, 10), date(2026, 1, 10), date(2026, 1, 17))
    wk2 = next(x for x in v if x["visit_code"] == "week_02")
    assert (wk2["window_start"], wk2["target_date"], wk2["window_end"]) == (
        date(2026, 1, 21), date(2026, 1, 24), date(2026, 1, 27))
    homes = [x for x in v if x["visit_type"] == "home"]
    assert [h["target_date"] for h in homes] == [date(2026, 1, 17), date(2026, 1, 24),
                                                 date(2026, 1, 31)]
    until = expand_schedule({"recurrences": [{"code_prefix": "h", "start_day": 0,
                                              "every_days": 10, "until_day": 25}]},
                            date(2026, 1, 1))
    assert [x["visit_code"] for x in until] == ["h_01", "h_02", "h_03"]


@pytest.mark.parametrize("bad", [
    {"visits": [{"code": "Bad Code", "day": 0}]},
    {"visits": [{"code": "a", "day": -1}]},
    {"visits": [{"code": "a", "day": 0, "tasks": ["Z9"]}]},
    {"visits": [{"code": "a", "day": 0, "instruments": ["NOPE"]}]},
    {"visits": [{"code": "a", "day": 0}, {"code": "a", "day": 3}]},
    {"recurrences": [{"code_prefix": "h", "start_day": 0, "every_days": 0, "count": 2}]},
    {"recurrences": [{"code_prefix": "h", "start_day": 0, "every_days": 7}]},
    {},
])
def test_invalid_schedules_rejected(bad):
    with pytest.raises(ValidationFailed):
        validate_schedule(bad, {"NM-SESSION"})


def test_visit_generation_assignments_reminders_and_windows(svc, w, clock):
    visits = svc.generate_visits(w.co, w.pid, w.schedule["id"], "2026-03-02")
    assert len(visits) == 5
    assert svc.generate_visits(w.co, w.pid, w.schedule["id"], "2026-03-02") == []  # idempotent
    asg = svc.list_assignments(w.co, w.pid)
    assert {a["instrument_id"] for a in asg} == {"NM-SESSION", "SUS", "NM-DAU"}
    assert all(a["reminders"] and all(r["channel"] == "record_only" for r in a["reminders"])
               for a in asg)
    vs = {v["visit_code"]: v for v in svc.list_visits(w.co, w.pid)}
    # in-window completion
    upload_a1(svc, w.co, w.pid, visit_id=vs["baseline"]["id"])
    assert {v["visit_code"]: v for v in svc.list_visits(w.co, w.pid)}["baseline"]["status"] == "completed"
    # out-of-window completion creates an automatic deviation
    upload_a1(svc, w.co, w.pid, seed=1, visit_id=vs["week_02"]["id"],
              performed_at="2026-03-02T08:00:00Z")  # before the week-2 window
    v2 = {v["visit_code"]: v for v in svc.list_visits(w.co, w.pid)}["week_02"]
    assert v2["status"] == "completed_out_of_window"
    devs = svc.list_deviations(w.co, w.study["id"])
    assert any(d["category"] == "visit_out_of_window" and d["visit_id"] == v2["id"] for d in devs)
    # missed visits once the window closes
    clock.advance(days=40)
    n = svc.mark_missed_visits(w.co, w.study["id"])
    assert n == 3  # three home visits
    missing = svc.db.query("SELECT * FROM missing_data WHERE participant_id=?", (w.pid,))
    assert {m["reason_code"] for m in missing} == {"missed_visit"} and len(missing) == 3
    assert any(a["status"] == "missed" for a in svc.list_assignments(w.co, w.pid))


def test_performed_at_in_future_rejected(svc, w):
    with pytest.raises(ValidationFailed):
        upload_a1(svc, w.co, w.pid, performed_at="2030-01-01T00:00:00Z")


# --------------------------------------------------------------------------- reason for change
def test_updates_require_reason_and_keep_history(svc, w):
    dev = svc.add_device_config(w.co, w.pid, "mouse", "Generic mouse", {"dpi": 800}, "calibrated")
    with pytest.raises(ReasonRequired):
        svc.correct_record(w.co, "device_configs", dev["id"], {"make_model": "X"}, "")
    with pytest.raises(ReasonRequired):
        svc.correct_record(w.co, "device_configs", dev["id"], {"make_model": "X"}, "   ")
    with pytest.raises(ReasonRequired):
        svc._update(w.co, "device_configs", dev["id"], {"make_model": "X"}, "")
    svc.correct_record(w.co, "device_configs", dev["id"], {"make_model": "Trackball T1"},
                       "transcription error")
    svc.correct_record(w.co, "device_configs", dev["id"], {"settings_json": {"dpi": 400}},
                       "settings re-checked")
    hist = svc.record_history(w.co, "device_configs", dev["id"])
    assert [h["action"] for h in hist] == ["create", "correction", "correction"]
    assert hist[1]["old"] == {"make_model": "Generic mouse"}
    assert hist[1]["new"] == {"make_model": "Trackball T1"}
    assert hist[1]["reason"] == "transcription error"
    assert hist[1]["actor_user_id"] == w.co.user_id
    with pytest.raises(ValidationFailed):
        svc.correct_record(w.co, "device_configs", dev["id"], {"id": "x"}, "r")
    with pytest.raises(ValidationFailed):
        svc.correct_record(w.co, "audit_log", "1", {"reason": "x"}, "r")
    with pytest.raises(PermissionDenied):
        svc.correct_record(w.sa, "device_configs", dev["id"], {"make_model": "Y"}, "r")


def test_questionnaire_correction_rescores_and_keeps_version(svc, w):
    r = svc.submit_response(w.part, w.pid, "NM-SESSION", {
        "fatigue": 8, "effort": 6, "frustration": 4, "satisfaction": 2, "device_problem": False})
    assert r["scores"]["session_burden"]["score"] == pytest.approx((8 + 6 + 4 + 8) / 4)
    c = svc.correct_record(w.co, "questionnaire_responses", r["id"], {"answers": {
        "fatigue": 2, "effort": 6, "frustration": 4, "satisfaction": 2, "device_problem": False}},
        "participant clarified the fatigue rating")
    assert c["scores"]["session_burden"]["score"] == pytest.approx((2 + 6 + 4 + 8) / 4)
    assert c["instrument_version"] == "1.0.0"
    h = svc.record_history(w.co, "questionnaire_responses", r["id"])
    assert h[-1]["action"] == "correction" and h[-1]["reason"].startswith("participant clarified")


# --------------------------------------------------------------------------- demo isolation
def test_demo_records_cannot_mix_with_real_studies(svc, w):
    demo = svc.create_study(w.inv, "DEMO-1", "DEMO - synthetic", is_demo=True)
    svc.add_site_to_study(w.inv, demo["id"], w.site["id"])
    dp = svc.create_participant(w.co, demo["id"], w.site["id"])
    assert dp["is_demo"] == 1 and w.p["is_demo"] == 0
    # synthetic events into a non-demo study are refused
    with pytest.raises(ValidationFailed) as e:
        upload_a1(svc, w.co, w.pid, synthetic=True, provenance="simulated")
    assert e.value.code == "demo_mix"
    # database triggers stop any direct attempt (defence in depth)
    with pytest.raises(sqlite3.IntegrityError, match="demo_mix"):
        svc.db.execute("UPDATE participants SET is_demo=1 WHERE id=?", (w.pid,))
    with pytest.raises(sqlite3.IntegrityError, match="demo_mix"):
        svc.db.execute("UPDATE studies SET is_demo=0 WHERE id=?", (demo["id"],))
    with pytest.raises(sqlite3.IntegrityError, match="another study"):
        svc.db.execute(
            "INSERT INTO missing_data VALUES ('m1', ?, ?, ?, NULL, 'task', 'A1', 'other', '', 0, "
            "'2026-01-01T00:00:00Z', 'x')", (w.org["id"], w.study["id"], dp["id"]))
    with pytest.raises(DemoMixError):
        svc._insert(w.co, "missing_data", {
            "id": "m2", "org_id": w.org["id"], "study_id": demo["id"], "participant_id": dp["id"],
            "visit_id": None, "item_type": "task", "item_ref": "A1", "reason_code": "other",
            "note": "", "is_demo": 0, "recorded_at": "2026-01-01T00:00:00Z", "recorded_by": "x"})
    # a demo organization cannot hold non-demo studies
    org = svc.create_organization("Demo org", is_demo=True)
    adm = actor_of(svc, svc.create_user(SYSTEM, org_id=org["id"], username="demoadm",
                                        password=TEST_PASSWORD, role="investigator"))
    with pytest.raises(DemoMixError):
        svc.create_study(adm, "REAL", "real study in demo org", is_demo=False)


# --------------------------------------------------------------------------- security
def test_password_hashing_scrypt():
    h = hash_password("a-long-password-123")
    assert h.startswith("scrypt$16384$8$1$")
    assert verify_password("a-long-password-123", h)
    assert not verify_password("wrong-password-123", h)
    assert hash_password("a-long-password-123") != h  # salted


def test_password_policy(svc, w):
    with pytest.raises(ValueError):
        svc.create_user(w.admin, org_id=w.org["id"], username="short", password="short",
                        role="coordinator")


def test_login_tokens_expire_and_revoke(svc, w, clock, monkeypatch):
    monkeypatch.setenv("NEUROMETRIC_TOKEN_TTL_MIN", "15")
    user = svc.db.one("SELECT username FROM users WHERE id=?", (w.co.user_id,))["username"]
    with pytest.raises(AuthenticationFailed):
        svc.login(user, "wrong-password-xx")
    with pytest.raises(AuthenticationFailed):
        svc.login("nobody-here", "wrong-password-xx")
    tok = svc.login(user, TEST_PASSWORD)
    stored = svc.db.one("SELECT * FROM auth_tokens")
    assert stored["token_hash"] != tok["token"]  # only the hash is stored
    assert svc.actor_from_token(tok["token"]).user_id == w.co.user_id
    clock.advance(minutes=16)
    with pytest.raises(AuthenticationFailed) as e:
        svc.actor_from_token(tok["token"])
    assert e.value.code == "token_expired"
    tok2 = svc.login(user, TEST_PASSWORD)
    svc.logout(tok2["token"])
    with pytest.raises(AuthenticationFailed):
        svc.actor_from_token(tok2["token"])
    tok3 = svc.login(user, TEST_PASSWORD)
    svc.deactivate_user(w.admin, w.co.user_id, "left the study team")
    with pytest.raises(AuthenticationFailed):
        svc.actor_from_token(tok3["token"])
    with pytest.raises(AuthenticationFailed):
        svc.login(user, TEST_PASSWORD)


def test_reidentification_encrypted_site_scoped_and_audited(svc, w):
    raw = svc.db.one("SELECT * FROM reidentification_keys WHERE participant_id=?", (w.pid,))
    assert raw["enc_scheme"] == "aes-256-gcm/v1"
    assert b"MRN-A-0001" not in raw["enc_identifier"]
    with pytest.raises(ReasonRequired):
        svc.get_reidentification(w.co, w.pid, "")
    assert svc.get_reidentification(w.co, w.pid, "adverse event follow-up") == "MRN-A-0001"
    for a in (w.sa, w.admin, w.part, w.cp):
        with pytest.raises((PermissionDenied, NotFound)):
            svc.get_reidentification(a, w.pid, "curious")
    with pytest.raises(NotFound):
        svc.get_reidentification(w.co2, w.pid, "other site")
    assert any(e["action"] == "reidentify" for e in svc.audit.history(
        w.org["id"], "reidentification_keys", w.pid))
    # ciphertext is bound to the pseudonym (AAD): moving it to another row fails
    from cryptography.exceptions import InvalidTag
    with pytest.raises(InvalidTag):
        decrypt_field(raw["enc_scheme"], raw["enc_identifier"], "NM-OTHERPSEUD")
    # never in the audit trail in clear
    assert not svc.db.one("SELECT 1 FROM audit_log WHERE new_json LIKE '%MRN-A-0001%'")


def test_reid_requires_key(svc, w, monkeypatch):
    monkeypatch.delenv("NEUROMETRIC_REID_KEY")
    from neurometric.study.errors import ConfigurationError
    with pytest.raises(ConfigurationError):
        encrypt_field("x", "NM-AAAAAAAAAA")


def test_collection_requires_consent_and_enrollment(svc, w):
    p = svc.create_participant(w.co, w.study["id"], w.site["id"])
    with pytest.raises(ValidationFailed):
        upload_a1(svc, w.co, p["id"])  # screening: not collecting
    svc.record_consent(w.co, p["id"], "ICF-1", "1.0", {"questionnaires": True})
    svc.transition(w.co, p["id"], "consented")
    svc.transition(w.co, p["id"], "enrolled")
    with pytest.raises(ConsentRequired):
        upload_a1(svc, w.co, p["id"])  # no task_battery scope
