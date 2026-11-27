"""Evidence exports: manifest hashes, data dictionary from the model, analysis dataset,
SDTM-inspired layouts, FHIR structure, audience filtering (purpose limitation)."""
from __future__ import annotations

import csv
import json

import pytest

from neurometric.study import PermissionDenied, StudyService, ValidationFailed
from neurometric.study.exports import verify_export
from neurometric.study.inventory import INVENTORY, describe
from neurometric.study.testing import (ALL_SCOPES, FakeClock, build_world, ensure_test_key,
                                       upload_a1)

ensure_test_key()


@pytest.fixture
def svc(tmp_path):
    s = StudyService(tmp_path / "nm.sqlite", FakeClock())
    yield s
    s.db.close()


@pytest.fixture
def w(svc):
    w = build_world(svc, "A")
    svc.record_consent(w.co, w.pid, "ICF-1", "1.1", {**ALL_SCOPES, "free_text": True})
    visits = svc.generate_visits(w.co, w.pid, w.schedule["id"], "2026-03-02")
    upload_a1(svc, w.co, w.pid, visit_id=visits[0]["id"])
    svc.submit_response(w.part, w.pid, "NM-SESSION", {
        "fatigue": 3, "effort": 4, "frustration": 2, "satisfaction": 7, "device_problem": False,
        "comment": "SECRET-FREE-TEXT"}, visit_id=visits[0]["id"])
    svc.submit_response(w.part, w.pid, "SUS", {f"sus{i}": 3 for i in range(1, 11)})
    w.p2 = svc.create_participant(w.co, w.study["id"], w.site["id"], identifier="MRN-NOSHARE")
    svc.record_consent(w.co, w.p2["id"], "ICF-1", "1.0",
                       {**ALL_SCOPES, "sharing_with_sponsor": False})
    svc.transition(w.co, w.p2["id"], "consented")
    svc.transition(w.co, w.p2["id"], "enrolled")
    upload_a1(svc, w.co, w.p2["id"], seed=9)
    return w


def _read(path):
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def test_every_schema_column_is_documented(svc):
    for t in svc.db.tables():
        assert t in INVENTORY, f"table {t} missing from data inventory"
        for c in svc.db.columns(t):
            assert describe(t, c["name"]), f"{t}.{c['name']} undocumented"
        inv = INVENTORY[t]
        for k in ("purpose", "category", "sensitivity", "retention", "visible_to"):
            assert inv[k]


def test_sponsor_export_manifest_and_contents(svc, w, tmp_path):
    out = tmp_path / "exp"
    m = svc.export_study(w.sa, w.study["id"], out, "sponsor")
    assert m["audience"] == "sponsor" and m["n_participants"] == 1
    assert m["battery_version"] == "1.0.0" and m["software_version"]
    assert m["instrument_versions"] == {"NM-SESSION": ["1.0.0"], "SUS": ["1.0.0"]}
    assert m["audit_chain_head"] == svc.audit.head()
    assert svc.audit.verify_chain(expected_head=m["audit_chain_head"])["ok"]
    assert any("NOT CDISC" in d for d in m["disclaimers"])
    names = {f["path"] for f in m["files"]}
    assert {"data_dictionary.csv", "data_dictionary.json", "participants.csv",
            "analysis_dataset.csv", "sdtm_like_qs_questionnaires.csv",
            "sdtm_like_xf_functional.csv", "fhir_questionnaire_responses.json",
            "MAPPING_NOTES.md", "telemetry_daily.csv"} <= names
    v = verify_export(out)
    assert v["ok"], v
    # purpose limitation: no non-sharing participant, no identifiers, no free text, no raw events
    blob = "".join(p.read_text("utf-8") for p in out.iterdir())
    assert w.p2["id"] not in blob
    assert "MRN-" not in blob and "SECRET-FREE-TEXT" not in blob
    assert "events_blob" not in _read(out / "functional_sessions.csv")[0]
    header = (out / "protocol_deviations.csv").read_text("utf-8").splitlines()[0].split(",")
    assert "category" in header and "description" not in header
    # tampering any file breaks verification
    (out / "analysis_dataset.csv").write_text("forged\n", "utf-8")
    assert not verify_export(out)["ok"]
    (out / "extra.csv").write_text("x", "utf-8")
    assert "extra.csv" in verify_export(out)["unlisted_files"]


def test_full_export_includes_all_site_participants(svc, w, tmp_path):
    m = svc.export_study(w.inv, w.study["id"], tmp_path / "f", "full")
    assert m["n_participants"] == 2
    ids = {r["participant_id"] for r in _read(tmp_path / "f" / "participants.csv")}
    assert ids == {w.pid, w.p2["id"]}
    blob = "".join(p.read_text("utf-8") for p in (tmp_path / "f").iterdir())
    assert "MRN-" not in blob and "SECRET-FREE-TEXT" not in blob


def test_export_permissions(svc, w, tmp_path):
    for a in (w.co, w.admin, w.part):
        with pytest.raises(PermissionDenied):
            svc.export_study(a, w.study["id"], tmp_path / a.role, "sponsor")
    with pytest.raises(PermissionDenied):
        svc.export_study(w.sa, w.study["id"], tmp_path / "x", "full")
    with pytest.raises(ValidationFailed):
        svc.export_study(w.inv, w.study["id"], tmp_path / "y", "everyone")
    (tmp_path / "nonempty").mkdir()
    (tmp_path / "nonempty" / "f").write_text("x")
    with pytest.raises(ValidationFailed):
        svc.export_study(w.inv, w.study["id"], tmp_path / "nonempty", "full")


def test_analysis_dataset_and_sdtm_like_layouts(svc, w, tmp_path):
    svc.export_study(w.inv, w.study["id"], tmp_path / "e", "full")
    rows = _read(tmp_path / "e" / "analysis_dataset.csv")
    mine = [r for r in rows if r["participant_id"] == w.pid]
    assert {r["visit_code"] for r in mine} == {"baseline"}
    assert {r["task_id"] for r in mine} == {"A1"}
    metrics = [r["metric"] for r in mine]
    assert len(metrics) == len(set(metrics))  # one row per participant x visit x task x metric
    sr = next(r for r in mine if r["metric"] == "success_rate")
    assert float(sr["value"]) == 1.0 and sr["unit"] == "fraction"
    assert any(r["is_primary"] == "1" for r in mine)
    qs = _read(tmp_path / "e" / "sdtm_like_qs_questionnaires.csv")
    assert {r["DOMAIN"] for r in qs} == {"QS"}
    sus = [r for r in qs if r["QSCAT"] == "SUS" and r["QSDRVFL"] == "Y"]
    assert sus and float(sus[0]["QSSTRESN"]) == 50.0
    assert [int(r["QSSEQ"]) for r in qs] == list(range(1, len(qs) + 1))
    assert all(r["USUBJID"].startswith("ST-A-") for r in qs)
    xf = _read(tmp_path / "e" / "sdtm_like_xf_functional.csv")
    assert {r["DOMAIN"] for r in xf} == {"XF"} and {r["XFCAT"] for r in xf} == {"A1"}
    dd = json.loads((tmp_path / "e" / "data_dictionary.json").read_text())
    cols = {(f["table"], f["column"]) for f in dd["fields"]}
    assert ("functional_sessions", "events_sha256") in cols and dd["export_schema_version"]


def test_fhir_questionnaire_response_structure(svc, w, tmp_path):
    svc.export_study(w.inv, w.study["id"], tmp_path / "e", "full")
    b = json.loads((tmp_path / "e" / "fhir_questionnaire_responses.json").read_text())
    assert b["resourceType"] == "Bundle" and b["type"] == "collection"
    assert b["meta"]["tag"][0]["code"] == "structure-only-no-conformance-claim"
    qrs = [e["resource"] for e in b["entry"]]
    assert {q["resourceType"] for q in qrs} == {"QuestionnaireResponse"}
    ses = next(q for q in qrs if "NM-SESSION" in q["questionnaire"])
    assert ses["questionnaire"] == "urn:neurometric:instrument:NM-SESSION|1.0.0"
    assert ses["subject"]["identifier"]["value"] == w.pid
    items = {i["linkId"]: i["answer"][0] for i in ses["item"]}
    assert items["fatigue"] == {"valueInteger": 3}
    assert items["device_problem"] == {"valueBoolean": False}
    assert "comment" not in items  # free text never exported
    sus = next(q for q in qrs if "SUS" in q["questionnaire"])
    assert sus["item"][0]["answer"][0]["valueCoding"]["code"] == "3"
    assert any(x["extension"][1]["valueDecimal"] == 50.0 for x in sus["extension"])
