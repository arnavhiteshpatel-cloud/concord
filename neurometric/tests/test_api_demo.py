"""Demo seed command (synthetic, clearly labelled, isolated) and the operator CLI."""
from __future__ import annotations

import base64
import json
import zlib

import pytest
from fastapi.testclient import TestClient

from neurometric.api.__main__ import main
from neurometric.api.app import create_app
from neurometric.study import StudyService
from neurometric.study.demo import DEMO_TITLE
from neurometric.study.testing import ensure_test_key

ensure_test_key()
DEMO_PW = "demo-password-for-tests-1"


@pytest.fixture(scope="module")
def demo_db(tmp_path_factory):
    import os
    os.environ["NEUROMETRIC_DEMO_PASSWORD"] = DEMO_PW
    db = tmp_path_factory.mktemp("demo") / "demo.sqlite"
    assert main(["seed-demo", "--db", str(db)]) == 0
    os.environ.pop("NEUROMETRIC_DEMO_PASSWORD")
    return db


def test_demo_is_labelled_and_synthetic(demo_db):
    svc = StudyService(demo_db)
    st = svc.db.one("SELECT * FROM studies")
    assert st["title"] == DEMO_TITLE and "synthetic data, not patients" in st["title"]
    assert st["is_demo"] == 1
    assert svc.db.scalar("SELECT is_demo FROM organizations") == 1
    for t in ("participants", "functional_sessions", "questionnaire_responses",
              "telemetry_batches", "visits", "consent_records"):
        n = svc.db.scalar(f"SELECT COUNT(*) FROM {t}")
        assert n > 0, t
        assert svc.db.scalar(f"SELECT COUNT(*) FROM {t} WHERE is_demo=0") == 0, t
    rows = svc.db.query("SELECT provenance, events_blob FROM functional_sessions")
    assert {r["provenance"] for r in rows} == {"simulated"}
    for r in rows[:10]:
        evs = json.loads(zlib.decompress(r["events_blob"]))
        assert all(e["synthetic"] for e in evs)
    assert svc.audit.verify_chain()["ok"]
    assert svc.db.scalar("SELECT COUNT(*) FROM reidentification_keys") == 0
    mods = {r["modality"] for r in svc.db.query("SELECT DISTINCT modality FROM functional_sessions")}
    assert {"mouse_sim", "bci_cursor_good_sim", "eye_gaze_sim", "switch_scan_sim"} <= mods
    svc.db.close()


def test_demo_dashboard_via_api(demo_db):
    app = create_app(demo_db)
    c = TestClient(app)
    svc = app.state.svc
    user = svc.db.scalar("SELECT username FROM users WHERE role='sponsor_analyst'")
    tok = c.post("/api/auth/login", json={"username": user, "password": DEMO_PW}).json()["token"]
    H = {"Authorization": f"Bearer {tok}"}
    sid = svc.db.scalar("SELECT id FROM studies")
    d = c.get(f"/api/studies/{sid}/dashboard", headers=H).json()
    assert d["banner"] == "DEMO - synthetic data, not patients" and d["study"]["is_demo"]
    assert d["n_participants"] >= 7
    comp = {x["visit_code"]: x for x in d["completeness_by_visit"]}
    assert comp["baseline"]["completeness"] == 1.0
    modal = {(m["task_id"], m["modality"]): m for m in d["modality_comparison"]}
    # simulated mouse users are faster than simulated BCI cursor users on the ISO task
    assert modal[("A2", "mouse_sim")]["mean"] > modal[("A2", "bci_cursor_good_sim")]["mean"]
    assert d["telemetry"]["participants_reporting"] >= 7
    assert d["questionnaire_scores"] and d["queries"] and d["deviations"]
    r = c.post(f"/api/studies/{sid}/exports", headers=H)
    assert r.status_code == 200
    import io
    import zipfile
    m = json.loads(zipfile.ZipFile(io.BytesIO(r.content)).read("manifest.json"))
    assert m["study"]["is_demo"] and m["banner"].startswith("DEMO")
    c.close()
    svc.db.close()


def test_demo_data_cannot_enter_real_study(demo_db):
    from neurometric.study.errors import DemoMixError
    svc = StudyService(demo_db)
    inv = svc.actor_for_user(svc.db.one("SELECT * FROM users WHERE role='investigator'"))
    with pytest.raises(DemoMixError):
        svc.create_study(inv, "REAL-1", "real study", is_demo=False)
    demo_pid = svc.db.scalar("SELECT id FROM participants LIMIT 1")
    with pytest.raises(Exception):
        svc.db.execute("UPDATE participants SET is_demo=0 WHERE id=?", (demo_pid,))
    svc.db.close()


def test_cli_operator_commands(tmp_path, monkeypatch, capsys):
    assert main(["gen-key"]) == 0
    k = capsys.readouterr().out.strip()
    assert len(base64.urlsafe_b64decode(k)) == 32
    db = tmp_path / "ops.sqlite"
    monkeypatch.setenv("NEUROMETRIC_ADMIN_PASSWORD", "operator-password-123")
    assert main(["create-admin", "--db", str(db), "--org", "Lab", "--username", "root"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["organization_id"].startswith("org_")
    assert main(["verify-audit", "--db", str(db)]) == 0
    capsys.readouterr()
    assert main(["backup", "--db", str(db), "--out", str(tmp_path / "b.sqlite")]) == 0
    capsys.readouterr()
    assert main(["verify-backup", str(tmp_path / "b.sqlite")]) == 0
    assert json.loads(capsys.readouterr().out)["ok"]
    assert main(["restore", str(tmp_path / "b.sqlite"), str(tmp_path / "r.sqlite")]) == 0
    assert json.loads(capsys.readouterr().out)["audit_chain_ok"]
