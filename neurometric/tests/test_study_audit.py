"""Audit trail (hash chain, tamper detection, append-only), electronic signatures with
re-authentication, record integrity, backup / restore / backup verification."""
from __future__ import annotations

import json
import sqlite3
import zlib

import pytest

from neurometric.study import AuthenticationFailed, PermissionDenied, StudyService
from neurometric.study.audit import GENESIS
from neurometric.study.backup import restore_database, verify_backup
from neurometric.study.testing import (TEST_PASSWORD, FakeClock, build_world, ensure_test_key,
                                       upload_a1)

ensure_test_key()


@pytest.fixture
def svc(tmp_path):
    s = StudyService(tmp_path / "nm.sqlite", FakeClock())
    yield s
    s.db.close()


@pytest.fixture
def w(svc):
    return build_world(svc, "A")


def _drop_guards(db):
    """Simulate an attacker with raw file access: remove the append-only triggers."""
    db.execute("DROP TRIGGER audit_log_no_update")
    db.execute("DROP TRIGGER audit_log_no_delete")


def test_chain_valid_and_entries_complete(svc, w):
    v = svc.audit.verify_chain()
    assert v["ok"] and v["entries"] == svc.audit.count() > 20
    first = svc.db.one("SELECT * FROM audit_log ORDER BY id LIMIT 1")
    assert first["prev_hash"] == GENESIS
    rows = svc.db.query("SELECT * FROM audit_log ORDER BY id")
    for a, b in zip(rows, rows[1:]):
        assert b["prev_hash"] == a["entry_hash"]
    e = rows[-1]
    for k in ("at", "actor_user_id", "actor_role", "action", "table_name", "record_id"):
        assert e[k]


def test_audit_is_append_only(svc, w):
    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        svc.db.execute("UPDATE audit_log SET reason='x' WHERE id=1")
    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        svc.db.execute("DELETE FROM audit_log WHERE id=1")


@pytest.mark.parametrize("attack", ["edit_value", "edit_reason", "delete_middle", "reorder",
                                    "rehash_one"])
def test_tampering_is_detected(svc, w, attack):
    _drop_guards(svc.db)
    n = svc.audit.count()
    mid = n // 2
    if attack == "edit_value":
        svc.db.execute("UPDATE audit_log SET new_json='{\"cohort\":\"forged\"}' WHERE id=?", (mid,))
    elif attack == "edit_reason":
        svc.db.execute("UPDATE audit_log SET reason='nothing to see' WHERE id=?", (mid,))
    elif attack == "delete_middle":
        svc.db.execute("DELETE FROM audit_log WHERE id=?", (mid,))
    elif attack == "reorder":
        a = svc.db.one("SELECT * FROM audit_log WHERE id=?", (mid,))
        b = svc.db.one("SELECT * FROM audit_log WHERE id=?", (mid + 1,))
        svc.db.execute("DELETE FROM audit_log WHERE id IN (?,?)", (mid, mid + 1))
        for row, new_id in ((b, mid), (a, mid + 1)):
            row = {**row, "id": new_id}
            svc.db.execute(f"INSERT INTO audit_log ({','.join(row)}) VALUES "
                           f"({','.join('?' * len(row))})", list(row.values()))
    elif attack == "rehash_one":
        # attacker edits an entry AND recomputes its own hash: the next link breaks
        from neurometric.study.audit import _entry_hash
        e = svc.db.one("SELECT * FROM audit_log WHERE id=?", (mid,))
        e["reason"] = "forged"
        svc.db.execute("UPDATE audit_log SET reason=?, entry_hash=? WHERE id=?",
                       ("forged", _entry_hash(e), mid))
    v = svc.audit.verify_chain()
    assert not v["ok"]
    assert v["first_bad_id"] in (mid, mid + 1)


def test_truncation_detected_against_external_anchor(svc, w):
    head = svc.audit.head()
    svc.create_site(w.admin, "S9", "late site")
    anchor = svc.audit.head()
    _drop_guards(svc.db)
    last = svc.db.scalar("SELECT MAX(id) FROM audit_log")
    svc.db.execute("DELETE FROM audit_log WHERE id=?", (last,))
    assert svc.audit.verify_chain()["ok"]  # chain alone cannot see a cut tail ...
    assert svc.audit.head() == head
    assert not svc.audit.verify_chain(expected_head=anchor)["ok"]  # ... the anchor can


def test_sensitive_values_hashed_in_audit(svc, w):
    s = upload_a1(svc, w.co, w.pid)
    e = [x for x in svc.audit.history(w.org["id"], "functional_sessions", s["id"])
         if x["action"] == "create"][0]
    assert "redacted_sha256" in e["new"]["events_blob"]
    pw = [x for x in svc.audit.history(w.org["id"], "users", w.co.user_id)
          if x["action"] == "create"][0]
    assert "redacted_sha256" in pw["new"]["password_hash"]


# --------------------------------------------------------------------------- e-signatures
def test_signature_requires_reauthentication(svc, w):
    with pytest.raises(AuthenticationFailed) as e:
        svc.sign(w.inv, "wrong-password-xx", "casebook", w.pid, "approved")
    assert e.value.code == "reauth_failed"
    assert svc.db.scalar("SELECT COUNT(*) FROM e_signatures") == 0
    assert any(x["action"] == "reauth_failed" for x in svc.audit.entries(w.org["id"], 50))
    sig = svc.sign(w.inv, TEST_PASSWORD, "casebook", w.pid, "approved")
    assert sig["meaning"] == "approved" and sig["reauth_method"] == "password"
    assert sig["signer_display_name"] and sig["signed_at"].endswith("Z")
    assert len(sig["record_hash"]) == 64


def test_signature_meanings_and_roles(svc, w):
    s = upload_a1(svc, w.co, w.pid)
    r = svc.sign(w.co, TEST_PASSWORD, "functional_sessions", s["id"], "reviewed")
    assert r["signer_role"] == "coordinator"
    with pytest.raises(PermissionDenied):
        svc.sign(w.co, TEST_PASSWORD, "functional_sessions", s["id"], "approved")
    with pytest.raises(PermissionDenied):
        svc.sign(w.sa, TEST_PASSWORD, "functional_sessions", s["id"], "reviewed")
    with pytest.raises(Exception):
        svc.sign(w.inv, TEST_PASSWORD, "functional_sessions", s["id"], "liked")


def test_signature_detects_later_changes(svc, w):
    s = upload_a1(svc, w.co, w.pid)
    sig = svc.sign(w.inv, TEST_PASSWORD, "casebook", w.pid, "approved")
    assert svc.verify_signature(w.inv, sig["id"])["status"] == "valid"
    svc.correct_record(w.co, "functional_sessions", s["id"], {"status": "invalidated"},
                       "device malfunction noted after review")
    assert svc.verify_signature(w.inv, sig["id"])["status"] == "record_changed_since_signing"
    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        svc.db.execute("UPDATE e_signatures SET meaning='reviewed'")
    assert svc.integrity_check(w.inv)["signatures"] == {"record_changed_since_signing": 1}


# --------------------------------------------------------------------------- integrity
def test_integrity_check_detects_raw_event_tampering(svc, w):
    s = upload_a1(svc, w.co, w.pid)
    assert svc.integrity_check(w.admin)["ok"]
    evs = json.loads(zlib.decompress(svc.db.one("SELECT events_blob FROM functional_sessions")
                                     ["events_blob"]))
    evs[3]["x"] = 1.0
    svc.db.execute("UPDATE functional_sessions SET events_blob=? WHERE id=?",
                   (zlib.compress(json.dumps(evs).encode()), s["id"]))
    rep = svc.integrity_check(w.admin)
    assert not rep["ok"] and rep["sessions_with_bad_hash"] == [s["id"]]


# --------------------------------------------------------------------------- backup / restore
def test_backup_restore_roundtrip(svc, w, tmp_path):
    upload_a1(svc, w.co, w.pid)
    with pytest.raises(PermissionDenied):
        svc.backup(w.co, tmp_path / "b0.sqlite")
    m = svc.backup(w.admin, tmp_path / "bk" / "b1.sqlite")
    assert len(m["sha256"]) == 64 and m["audit_entries"] > 0
    v = verify_backup(tmp_path / "bk" / "b1.sqlite")
    assert v["ok"], v
    out = restore_database(tmp_path / "bk" / "b1.sqlite", tmp_path / "restored.sqlite")
    assert out["audit_chain_ok"] and out["audit_head"] == m["audit_head"]
    r = StudyService(tmp_path / "restored.sqlite")
    assert r.db.scalar("SELECT COUNT(*) FROM functional_sessions") == 1
    assert r.get_participant(w.co, w.pid)["id"] == w.pid
    assert r.integrity_check(w.admin)["ok"]
    r.db.close()
    with pytest.raises(FileExistsError):
        svc.backup(w.admin, tmp_path / "bk" / "b1.sqlite")
    with pytest.raises(FileExistsError):
        restore_database(tmp_path / "bk" / "b1.sqlite", tmp_path / "restored.sqlite")


def test_backup_verification_detects_corruption(svc, w, tmp_path):
    svc.backup(w.admin, tmp_path / "b.sqlite")
    data = bytearray((tmp_path / "b.sqlite").read_bytes())
    data[-100] ^= 0xFF
    (tmp_path / "b.sqlite").write_bytes(bytes(data))
    v = verify_backup(tmp_path / "b.sqlite")
    assert not v["ok"] and any("SHA-256" in p for p in v["problems"])
    with pytest.raises(ValueError):
        restore_database(tmp_path / "b.sqlite", tmp_path / "r.sqlite")
    (tmp_path / "b.sqlite.manifest.json").unlink()
    assert not verify_backup(tmp_path / "b.sqlite")["ok"]


def test_backup_with_tampered_audit_fails_verification(svc, w, tmp_path):
    svc.backup(w.admin, tmp_path / "b.sqlite")
    con = sqlite3.connect(tmp_path / "b.sqlite")
    con.execute("DROP TRIGGER audit_log_no_update")
    con.execute("UPDATE audit_log SET reason='forged' WHERE id=3")
    con.commit()
    con.close()
    # attacker also rewrites the manifest's file hash: the audit chain still fails
    import hashlib
    mp = tmp_path / "b.sqlite.manifest.json"
    m = json.loads(mp.read_text())
    m["sha256"] = hashlib.sha256((tmp_path / "b.sqlite").read_bytes()).hexdigest()
    mp.write_text(json.dumps(m))
    v = verify_backup(tmp_path / "b.sqlite")
    assert not v["ok"] and "audit chain verification failed" in v["problems"]
