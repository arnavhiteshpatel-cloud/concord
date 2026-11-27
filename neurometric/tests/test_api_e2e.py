"""API end to end: login -> create study -> enroll -> upload a session -> scores -> dashboard ->
export, plus HTTP hardening (security headers, CORS off, size limits, rate limiting, token
expiry), tenant isolation over HTTP and static file serving."""
from __future__ import annotations

import hashlib
import io
import json
import zipfile
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from neurometric.api.app import create_app
from neurometric.api.middleware import LoginRateLimiter
from neurometric.study.audit import SYSTEM
from neurometric.study.testing import (TEST_PASSWORD, FakeClock, a1_events, ensure_test_key,
                                       telemetry_payload)
from neurometric.tasks.battery import stimuli

ensure_test_key()


@pytest.fixture
def clock():
    return FakeClock()


@pytest.fixture
def env(tmp_path, clock):
    app = create_app(tmp_path / "api.sqlite", clock=clock, web_dist=tmp_path / "no-dist",
                     backup_dir=tmp_path / "backups")
    svc = app.state.svc
    org = svc.create_organization("Org API")
    svc.create_user(SYSTEM, org_id=org["id"], username="admin-a", password=TEST_PASSWORD,
                    role="admin", display_name="Admin A")
    c = TestClient(app)
    yield c, app, org
    c.close()
    svc.db.close()


def login(c, user, pw=TEST_PASSWORD):
    r = c.post("/api/auth/login", json={"username": user, "password": pw})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


def ok(r, code=200):
    assert r.status_code == code, f"{r.status_code}: {r.text}"
    return r.json()


def setup_study(c):
    A = login(c, "admin-a")
    site = ok(c.post("/api/sites", json={"code": "S1", "name": "Site 1"}, headers=A), 201)
    for u, role in (("coord-a", "coordinator"), ("inv-a", "investigator")):
        ok(c.post("/api/users", json={"username": u, "password": TEST_PASSWORD, "role": role,
                                      "display_name": u, "site_ids": [site["id"]]}, headers=A), 201)
    ok(c.post("/api/users", json={"username": "sponsor-a", "password": TEST_PASSWORD,
                                  "role": "sponsor_analyst"}, headers=A), 201)
    INV, CO = login(c, "inv-a"), login(c, "coord-a")
    st = ok(c.post("/api/studies", json={"code": "API-1", "title": "API study",
                                         "min_cell_size": 1}, headers=INV), 201)
    ok(c.post(f"/api/studies/{st['id']}/sites/{site['id']}", headers=INV), 201)
    pv = ok(c.post(f"/api/studies/{st['id']}/protocol-versions",
                   json={"version": "1.0", "effective_date": "2026-01-01"}, headers=INV), 201)
    sch = ok(c.post(f"/api/studies/{st['id']}/schedules", json={
        "name": "s", "protocol_version_id": pv["id"], "definition": {
            "visits": [{"code": "baseline", "day": 0, "window_after": 7, "tasks": ["A1"],
                        "instruments": ["NM-SESSION"]}]}}, headers=INV), 201)
    p = ok(c.post(f"/api/studies/{st['id']}/participants",
                  json={"site_id": site["id"], "identifier": "MRN-API-1"}, headers=CO), 201)
    return A, INV, CO, site, st, sch, p


def test_end_to_end_workflow(env, tmp_path):
    c, app, org = env
    A, INV, CO, site, st, sch, p = setup_study(c)
    pid = p["id"]
    ok(c.post(f"/api/participants/{pid}/consent", json={
        "consent_document_id": "ICF-1", "consent_version": "1.0", "scopes": {
            "task_battery": True, "questionnaires": True, "home_telemetry": True,
            "sharing_with_sponsor": True}}, headers=CO), 201)
    for s in ("consented", "enrolled"):
        ok(c.post(f"/api/participants/{pid}/transition", json={"to_state": s}, headers=CO))
    bad = c.post(f"/api/participants/{pid}/transition", json={"to_state": "screening"}, headers=CO)
    assert bad.status_code == 409 and bad.json()["error"] == "invalid_transition"
    visits = ok(c.post(f"/api/participants/{pid}/visits/generate",
                       json={"schedule_id": sch["id"], "anchor_date": "2026-03-02"},
                       headers=CO), 201)
    # battery + stimuli are what the browser uses to run the task
    bat = ok(c.get("/api/battery"))
    assert bat["battery_version"] == "1.0.0" and len(bat["tasks"]) >= 10
    stim = ok(c.get("/api/battery/A1/stimuli?seed=0"))
    assert stim["stimulus_hash"] == stimuli("A1", 0)["stimulus_hash"]
    assert c.get("/api/battery/ZZ/stimuli").status_code == 404
    ses = ok(c.post(f"/api/participants/{pid}/sessions", json={
        "task_id": "A1", "events": a1_events(0), "stimulus_seed": 0,
        "stimulus_hash": stim["stimulus_hash"], "visit_id": visits[0]["id"]}, headers=CO), 201)
    assert ses["metrics"]["success_rate"] == 1.0
    assert ses["metrics"]["movement_time_ms_mean"] == pytest.approx(1000.0)
    got = ok(c.get(f"/api/sessions/{ses['id']}?include_events=true", headers=CO))
    assert len(got["events"]) == ses["n_events"]
    assert ok(c.get(f"/api/participants/{pid}/visits", headers=CO))[0]["status"] == "completed"
    q = ok(c.post(f"/api/participants/{pid}/questionnaires", json={
        "instrument_id": "NM-SESSION", "answers": {"fatigue": 4, "effort": 5, "frustration": 3,
                                                   "satisfaction": 6, "device_problem": False},
        "visit_id": visits[0]["id"]}, headers=CO), 201)
    assert q["scores"]["session_burden"]["score"] == pytest.approx(4.0)
    preview = ok(c.post("/api/instruments/SUS/score", json={"answers": {
        f"sus{i}": 5 if i % 2 else 1 for i in range(1, 11)}}, headers=CO))
    assert preview["scores"]["sus_score"]["score"] == 100.0
    insts = ok(c.get("/api/instruments", headers=CO))
    assert {"NM-DAU", "SUS", "NASA-TLX", "ZBI"} <= {i["id"] for i in insts}
    # participant account, telemetry and local review
    ok(c.post("/api/users", json={"username": "part-a", "password": TEST_PASSWORD,
                                  "role": "participant", "participant_id": pid}, headers=A), 201)
    P = login(c, "part-a")
    me = ok(c.get("/api/auth/me", headers=P))
    assert me["participant_id"] == pid and me["role"] == "participant"
    now = app.state.svc.db.now()
    tp = telemetry_payload(pid, now - timedelta(hours=3))
    t1 = ok(c.post("/api/telemetry/ingest", json=tp, headers=P), 201)
    assert t1["status"] == "accepted"
    assert ok(c.post("/api/telemetry/ingest", json=tp, headers=P), 201)["status"] == "duplicate"
    bad = c.post("/api/telemetry/ingest", json={**tp, "window_title": "Inbox"}, headers=P)
    assert bad.status_code == 422 and "forbidden_field:window_title" in bad.json()["detail"]["reasons"]
    mine = ok(c.get("/api/telemetry/mine", headers=P))
    assert mine["batches"][0]["payload"] == tp
    ok(c.put(f"/api/participants/{pid}/telemetry/state", json={"state": "paused"}, headers=P))
    # participants cannot see other endpoints' data
    assert c.get(f"/api/studies/{st['id']}/dashboard", headers=P).status_code == 403
    # sponsor dashboard: aggregates only
    SA = login(c, "sponsor-a")
    d = ok(c.get(f"/api/studies/{st['id']}/dashboard", headers=SA))
    assert d["n_participants"] == 1 and pid not in json.dumps(d)
    assert d["completeness_by_visit"][0]["completeness"] == 1.0
    assert any(t["task_id"] == "A1" for t in d["task_trends"])
    assert c.get(f"/api/participants/{pid}", headers=SA).status_code == 403
    assert c.post(f"/api/participants/{pid}/reid/reveal", json={"reason": "x"},
                  headers=SA).status_code == 403
    assert ok(c.post(f"/api/participants/{pid}/reid/reveal", json={"reason": "AE follow-up"},
                     headers=CO))["identifier"] == "MRN-API-1"
    # data management: query, correction with reason, signature with re-auth
    qq = ok(c.post(f"/api/studies/{st['id']}/queries", json={
        "record_table": "functional_sessions", "record_id": ses["id"],
        "question": "Confirm device?"}, headers=SA), 201)
    ok(c.post(f"/api/queries/{qq['id']}/answer", json={"answer": "Confirmed"}, headers=CO))
    ok(c.post(f"/api/queries/{qq['id']}/close", json={"reason": ""}, headers=SA))
    r = c.patch(f"/api/records/questionnaire_responses/{q['id']}",
                json={"changes": {"answers": {"fatigue": 2}}, "reason": ""}, headers=CO)
    assert r.status_code == 422
    fixed = ok(c.patch(f"/api/records/questionnaire_responses/{q['id']}", json={
        "changes": {"answers": {"fatigue": 2, "effort": 5, "frustration": 3, "satisfaction": 6,
                                "device_problem": False}},
        "reason": "transcription error"}, headers=CO))
    assert fixed["scores"]["session_burden"]["score"] == pytest.approx(3.5)
    hist = ok(c.get(f"/api/records/questionnaire_responses/{q['id']}/history", headers=CO))
    assert hist[-1]["reason"] == "transcription error"
    assert c.post("/api/signatures", json={"record_table": "casebook", "record_id": pid,
                                           "meaning": "approved", "password": "wrong-password"},
                  headers=INV).status_code == 401
    sig = ok(c.post("/api/signatures", json={"record_table": "casebook", "record_id": pid,
                                             "meaning": "approved", "password": TEST_PASSWORD},
                    headers=INV), 201)
    assert ok(c.get(f"/api/signatures/{sig['id']}/verify", headers=INV))["status"] == "valid"
    # audit trail
    v = ok(c.get("/api/audit/verify", headers=INV))
    assert v["ok"] and v["entries"] > 20
    assert c.get("/api/audit/verify", headers=SA).status_code == 403
    assert len(ok(c.get("/api/audit?limit=5", headers=A))) == 5
    # export (zip) with manifest hashes
    r = c.post(f"/api/studies/{st['id']}/exports?audience=sponsor", headers=SA)
    assert r.status_code == 200 and r.headers["content-type"] == "application/zip"
    z = zipfile.ZipFile(io.BytesIO(r.content))
    manifest = json.loads(z.read("manifest.json"))
    for f in manifest["files"]:
        assert hashlib.sha256(z.read(f["path"])).hexdigest() == f["sha256"]
    assert manifest["audit_chain_head"] == r.headers["X-NeuroMetric-Audit-Head"]
    assert manifest["instrument_versions"] == {"NM-SESSION": ["1.0.0"]}
    assert b"MRN-API-1" not in r.content
    # the export's anchor is an entry of the (intact) chain
    assert app.state.svc.db.one("SELECT id FROM audit_log WHERE entry_hash=?",
                                (manifest["audit_chain_head"],))
    assert ok(c.get(f"/api/audit/verify?expected_head={manifest['audit_chain_head']}",
                    headers=INV))["ok"]  # nothing was written after the export yet
    assert c.post(f"/api/studies/{st['id']}/exports?audience=full",
                  headers=SA).status_code == 403
    # admin operations
    b = ok(c.post("/api/admin/backup", headers=A), 201)
    name = b["file"]
    assert ok(c.post("/api/admin/backup/verify", json={"name": name}, headers=A))["ok"]
    assert c.post("/api/admin/backup/verify", json={"name": "../x.sqlite"},
                  headers=A).status_code == 422
    assert ok(c.get("/api/admin/integrity", headers=A))["ok"]
    ok(c.put(f"/api/studies/{st['id']}/retention", json={"data_category": "raw_events",
                                                          "retain_days": 365}, headers=INV))
    assert ok(c.post("/api/admin/retention/run", headers=A))["purges"][0]["n_affected"] == 0
    # data subject export by the participant
    exp = ok(c.get(f"/api/participants/{pid}/export", headers=P))
    assert exp["participant"]["id"] == pid and "MRN-API-1" not in json.dumps(exp)
    ok(c.post("/api/auth/logout", headers=P))
    assert c.get("/api/auth/me", headers=P).status_code == 401


def test_security_headers_cors_off_and_docs_off(env):
    c, app, org = env
    r = c.get("/api/health", headers={"Origin": "https://evil.example"})
    h = r.headers
    assert h["x-content-type-options"] == "nosniff" and h["x-frame-options"] == "DENY"
    assert "default-src 'self'" in h["content-security-policy"]
    assert h["referrer-policy"] == "no-referrer" and h["cache-control"] == "no-store"
    assert "access-control-allow-origin" not in h
    pre = c.options("/api/health", headers={"Origin": "https://evil.example",
                                            "Access-Control-Request-Method": "GET"})
    assert "access-control-allow-origin" not in pre.headers
    assert c.get("/api/docs").status_code == 404
    assert c.get("/api/openapi.json").status_code == 404


def test_auth_required_and_token_expiry(env, clock, monkeypatch):
    c, app, org = env
    assert c.get("/api/studies").status_code == 401
    assert c.get("/api/studies", headers={"Authorization": "Bearer nope"}).status_code == 401
    monkeypatch.setenv("NEUROMETRIC_TOKEN_TTL_MIN", "10")
    A = login(c, "admin-a")
    assert c.get("/api/users", headers=A).status_code == 200
    clock.advance(minutes=11)
    r = c.get("/api/users", headers=A)
    assert r.status_code == 401 and r.json()["error"] == "token_expired"


def test_login_rate_limiting(tmp_path, clock):
    app = create_app(tmp_path / "rl.sqlite", clock=clock, web_dist=tmp_path / "none",
                     rate_limiter=LoginRateLimiter(max_failures=3, window_s=300))
    svc = app.state.svc
    org = svc.create_organization("O")
    svc.create_user(SYSTEM, org_id=org["id"], username="victim", password=TEST_PASSWORD,
                    role="admin")
    c = TestClient(app)
    for _ in range(3):
        assert c.post("/api/auth/login", json={"username": "victim",
                                               "password": "guess-guess-1"}).status_code == 401
    r = c.post("/api/auth/login", json={"username": "victim", "password": TEST_PASSWORD})
    assert r.status_code == 429 and "Retry-After" in r.headers
    c.close()
    svc.db.close()


def test_request_size_limits(tmp_path, clock):
    app = create_app(tmp_path / "sz.sqlite", clock=clock, web_dist=tmp_path / "none",
                     max_body_bytes=50_000)
    c = TestClient(app)
    big = {"username": "x" * 20_000, "password": "y"}
    assert c.post("/api/auth/login", json=big).status_code == 413  # auth limit 8 KiB
    r = c.post("/api/telemetry/ingest", content=b"{" + b" " * 70_000 + b"}",
               headers={"Content-Type": "application/json"})
    assert r.status_code == 413
    r = c.post("/api/studies", content=b"x" * 60_000, headers={"Content-Type": "application/json"})
    assert r.status_code == 413
    c.close()
    app.state.svc.db.close()


def test_tenant_isolation_over_http(env):
    c, app, org = env
    A, INV, CO, site, st, sch, p = setup_study(c)
    svc = app.state.svc
    org_b = svc.create_organization("Org B")
    svc.create_user(SYSTEM, org_id=org_b["id"], username="admin-b", password=TEST_PASSWORD,
                    role="admin")
    B = login(c, "admin-b")
    ok(c.post("/api/users", json={"username": "inv-b", "password": TEST_PASSWORD,
                                  "role": "investigator"}, headers=B), 201)
    ok(c.post("/api/users", json={"username": "sa-b", "password": TEST_PASSWORD,
                                  "role": "sponsor_analyst"}, headers=B), 201)
    IB, SB = login(c, "inv-b"), login(c, "sa-b")
    assert c.get(f"/api/studies/{st['id']}", headers=IB).status_code == 404
    assert c.get(f"/api/studies/{st['id']}/dashboard", headers=SB).status_code == 404
    assert c.post(f"/api/studies/{st['id']}/exports", headers=SB).status_code == 404
    assert c.get(f"/api/participants/{p['id']}", headers=IB).status_code == 404
    assert ok(c.get("/api/studies", headers=IB)) == []
    assert all(u["org_id"] == org_b["id"] for u in ok(c.get("/api/users", headers=B)))
    assert all(e["org_id"] == org_b["id"] for e in ok(c.get("/api/audit?limit=1000", headers=B)))


def test_static_web_dist_served(tmp_path):
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("<!doctype html><title>NeuroMetric</title>")
    app = create_app(tmp_path / "w.sqlite", web_dist=dist)
    c = TestClient(app)
    r = c.get("/")
    assert r.status_code == 200 and "NeuroMetric" in r.text
    assert r.headers["x-frame-options"] == "DENY"
    assert c.get("/api/health").json()["status"] == "ok"
    c.close()
    app.state.svc.db.close()


def test_unknown_fields_rejected(env):
    c, app, org = env
    A = login(c, "admin-a")
    r = c.post("/api/sites", json={"code": "S", "name": "n", "evil": 1}, headers=A)
    assert r.status_code == 422
