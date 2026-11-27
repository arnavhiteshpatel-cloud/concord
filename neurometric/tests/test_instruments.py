"""Questionnaire engine: definitions, validation, scoring (SUS / NASA-TLX known answers,
reverse items, proration, minimum-answered rule), licensing stubs, versioning, translations,
schedules/completion tracking through the study service."""
from __future__ import annotations

import copy
import json

import pytest

from neurometric.instruments.engine import (DEFS_DIR, InstrumentError, Registry, ResponseError,
                                            load_licensed_items, score, tlx_weights_from_pairs,
                                            validate_definition, validate_response)
from neurometric.study import StudyService, ValidationFailed
from neurometric.study.testing import FakeClock, build_world, ensure_test_key

ensure_test_key()
REG = Registry()


def S(iid, answers, version=None):
    inst = REG.get(iid, version)
    clean, _, _ = validate_response(inst, answers, allow_free_text=False)
    return score(inst, clean)


# --------------------------------------------------------------------------- catalogue
def test_catalogue_and_labels():
    ids = {i["id"]: i for i in REG.list()}
    for nm in ("NM-DAU", "NM-CPB", "NM-SESSION", "NM-DEV"):
        assert ids[nm]["status"] == "original, unvalidated research questionnaire"
        assert ids[nm]["license_status"] == "original"
    assert ids["SUS"]["license_status"] == "free_with_attribution"
    assert ids["NASA-TLX"]["license_status"] == "public_domain"
    for lic in ("ZBI", "QUEST-2.0", "PIADS"):
        assert ids[lic]["license_status"] == "license_required"
        assert ids[lic]["items_loaded"] is False and ids[lic]["n_items"] > 0
    assert "not the Zarit" in REG.get("NM-CPB").definition["title"]


def test_definitions_files_valid_and_no_licensed_text():
    for p in DEFS_DIR.glob("*.json"):
        d = json.loads(p.read_text())
        validate_definition(d)
        assert d["respondent_type"] in ("PRO", "ObsRO", "ClinRO")
        if d["license"]["status"] == "license_required":
            assert d["items"] == [] and d["scoring"]["scales"] == []
        for code, status in d["languages"].items():
            assert status in ("source", "authorized translation required")
        for it in d["items"]:
            if it["type"] == "free_text":
                assert it["sensitive"] is True
        assert "accessibility" in d


def test_invalid_definitions_rejected():
    base = copy.deepcopy(REG.get("NM-SESSION").definition)
    bad = copy.deepcopy(base)
    bad["items"].append({"id": "x", "type": "free_text", "text": "?"})  # not flagged sensitive
    with pytest.raises(InstrumentError):
        validate_definition(bad)
    bad = copy.deepcopy(base)
    bad["languages"]["de"] = "machine translated"
    with pytest.raises(InstrumentError):
        validate_definition(bad)
    stub = copy.deepcopy(REG.get("ZBI").definition)
    stub["items"] = [{"id": "q1", "type": "numeric", "min": 0, "max": 4, "text": "x"}]
    with pytest.raises(InstrumentError, match="must not ship item content"):
        validate_definition(stub)


# --------------------------------------------------------------------------- SUS
@pytest.mark.parametrize("answers,expected", [
    ([5, 1, 5, 1, 5, 1, 5, 1, 5, 1], 100.0),
    ([1, 5, 1, 5, 1, 5, 1, 5, 1, 5], 0.0),
    ([3] * 10, 50.0),
    ([4, 2, 4, 2, 4, 2, 4, 2, 4, 2], 75.0),
    ([4, 1, 5, 2, 4, 2, 5, 1, 4, 3], 82.5),  # (3+4+4+3+3+3+4+4+3+2) * 2.5
])
def test_sus_known_answers(answers, expected):
    r = S("SUS", {f"sus{i + 1}": v for i, v in enumerate(answers)})
    assert r["sus_score"]["score"] == pytest.approx(expected)


def test_sus_requires_all_items():
    r = S("SUS", {f"sus{i}": 3 for i in range(1, 10)})
    assert r["sus_score"]["score"] is None and r["sus_score"]["status"] == "insufficient"


# --------------------------------------------------------------------------- NASA-TLX
TLX = {"mental": 70, "physical": 20, "temporal": 50, "performance": 30, "effort": 60,
       "frustration": 40}


def test_tlx_raw_and_weighted_known_answers():
    w = {"w_mental": 4, "w_physical": 0, "w_temporal": 3, "w_performance": 2, "w_effort": 4,
         "w_frustration": 2}
    r = S("NASA-TLX", {**TLX, **w})
    assert r["tlx_raw"]["score"] == pytest.approx(270 / 6)
    expected = (70 * 4 + 20 * 0 + 50 * 3 + 30 * 2 + 60 * 4 + 40 * 2) / 15
    assert r["tlx_weighted"]["score"] == pytest.approx(expected)
    r2 = S("NASA-TLX", TLX)
    assert r2["tlx_raw"]["score"] == pytest.approx(45.0)
    assert r2["tlx_weighted"]["status"] == "insufficient_weights"
    r3 = S("NASA-TLX", {**TLX, **{**w, "w_mental": 5}})
    assert r3["tlx_weighted"]["status"] == "invalid_weights"


def test_tlx_weights_from_pairwise_comparisons():
    subs = ["mental", "physical", "temporal", "performance", "effort", "frustration"]
    pref = {s: i for i, s in enumerate(["mental", "effort", "temporal", "performance",
                                        "frustration", "physical"])}
    choices = {f"{a}|{b}": (a if pref[a] < pref[b] else b)
               for i, a in enumerate(subs) for b in subs[i + 1:]}
    wts = tlx_weights_from_pairs(choices)
    assert sum(wts.values()) == 15
    assert wts == {"mental": 5, "effort": 4, "temporal": 3, "performance": 2,
                   "frustration": 1, "physical": 0}
    with pytest.raises(ValueError):
        tlx_weights_from_pairs({"mental|physical": "mental"})


def test_tlx_step_and_range_validation():
    with pytest.raises(ResponseError):
        S("NASA-TLX", {**TLX, "mental": 72})  # not a multiple of 5
    with pytest.raises(ResponseError):
        S("NASA-TLX", {**TLX, "mental": 105})


# --------------------------------------------------------------------------- NM instruments
def test_reverse_scoring_and_proration_nm_cpb():
    full = {"cp_minutes_setup_per_day": 20, "cp_minutes_help_per_day": 40, "cp_calls_per_day": 3,
            "s1": 2, "s2": 3, "s3": 4, "s4": 1, "s5": 4, "s6": 2}
    r = S("NM-CPB", full)
    # s5 (confidence) is reverse-scored on 0..4: 4 -> 0
    assert r["cp_strain"]["score"] == 2 + 3 + 4 + 1 + 0 + 2
    assert r["cp_minutes_per_day"]["score"] == 60
    part = {k: v for k, v in full.items() if k != "s6"}
    r = S("NM-CPB", part)
    assert r["cp_strain"]["prorated"] is True
    assert r["cp_strain"]["score"] == pytest.approx((2 + 3 + 4 + 1 + 0) * 6 / 5)
    assert r["cp_strain"]["status"] == "scored_with_missing"
    few = {k: v for k, v in full.items() if k not in ("s5", "s6")}
    r = S("NM-CPB", few)
    assert r["cp_strain"]["score"] is None and r["cp_strain"]["status"] == "insufficient"


def test_nm_session_mean_with_reverse_item():
    r = S("NM-SESSION", {"fatigue": 6, "effort": 8, "frustration": 2, "satisfaction": 9,
                         "device_problem": True})
    assert r["session_burden"]["score"] == pytest.approx((6 + 8 + 2 + 1) / 4)
    r = S("NM-SESSION", {"fatigue": 6, "effort": 8, "satisfaction": 9, "device_problem": True})
    assert r["session_burden"]["score"] == pytest.approx((6 + 8 + 1) / 3)
    r = S("NM-SESSION", {"fatigue": 6, "device_problem": True})
    assert r["session_burden"]["score"] is None


def test_response_validation_errors():
    inst = REG.get("NM-DAU")
    with pytest.raises(ResponseError) as e:
        validate_response(inst, {"minutes_digital_total": 2000, "activities": ["web", "web"],
                                 "main_access_method": "telepathy", "unmet_activity": "no",
                                 "bogus": 1}, allow_free_text=False)
    errs = " ".join(e.value.errors)
    for frag in ("unknown item 'bogus'", "minutes_digital_total", "activities",
                 "main_access_method", "unmet_activity"):
        assert frag in errs
    clean, free, missing = validate_response(inst, {"independence_rating": 5,
                                                    "notes": "private"}, allow_free_text=True)
    assert free == {"notes": "private"} and "notes" not in clean
    assert "activities" in missing and "minutes_care_partner_help" not in missing


def test_licensed_stub_cannot_be_answered_until_loaded():
    reg = Registry()
    with pytest.raises(ResponseError) as e:
        validate_response(reg.get("ZBI"), {"q1": 1}, allow_free_text=False)
    assert e.value.errors == ["license_required"]
    with pytest.raises(InstrumentError):
        load_licensed_items(reg, "ZBI", "license-stub-1", [], {"scales": []}, "")
    items = [{"id": f"q{i}", "type": "numeric", "min": 0, "max": 4,
              "text": "[licensed item text loaded at run time]"} for i in range(1, 4)]
    inst = load_licensed_items(reg, "ZBI", "license-stub-1", items,
                               {"scales": [{"id": "total", "method": "sum",
                                            "items": ["q1", "q2", "q3"]}]},
                               "Licence agreement #TEST-0001 with the licensor")
    assert inst.items_loaded and inst.license_status == "license_required"
    clean, _, _ = validate_response(inst, {"q1": 1, "q2": 2, "q3": 3}, allow_free_text=False)
    assert score(inst, clean)["total"]["score"] == 6
    assert not REG.get("ZBI").items_loaded  # shipped registry untouched


def test_versioning_responses_keep_version():
    reg = Registry()
    d = copy.deepcopy(reg.get("NM-SESSION").definition)
    d["version"] = "1.1.0"
    d["items"][0]["max"] = 10
    reg.add(d)
    assert reg.get("NM-SESSION").version == "1.1.0"
    assert reg.get("NM-SESSION", "1.0.0").version == "1.0.0"
    assert reg.versions()["NM-SESSION"] == ["1.0.0", "1.1.0"]


# --------------------------------------------------------------------------- via the service
@pytest.fixture
def svc(tmp_path):
    s = StudyService(tmp_path / "nm.sqlite", FakeClock())
    yield s
    s.db.close()


def test_service_respondent_types_translations_and_completion(svc):
    w = build_world(svc, "A")
    svc.generate_visits(w.co, w.pid, w.schedule["id"], "2026-03-02")
    base = svc.list_visits(w.co, w.pid)[0]
    # PRO by participant, ObsRO by care partner, ClinRO only by staff
    r = svc.submit_response(w.part, w.pid, "NM-SESSION", {"fatigue": 2, "effort": 3,
                                                          "frustration": 1, "satisfaction": 8,
                                                          "device_problem": False},
                            visit_id=base["id"])
    assert r["instrument_version"] == "1.0.0" and r["completion"] == "complete"
    svc.submit_response(w.cp, w.pid, "NM-CPB", {"s1": 1, "s2": 1, "s3": 1, "s4": 1, "s5": 3,
                                                "s6": 0, "cp_minutes_setup_per_day": 10,
                                                "cp_minutes_help_per_day": 15,
                                                "cp_calls_per_day": 2})
    with pytest.raises(ValidationFailed) as e:
        svc.submit_response(w.part, w.pid, "NM-DEV", {"setting": "home"})
    assert e.value.code == "respondent_type"
    with pytest.raises(ValidationFailed) as e:
        svc.submit_response(w.cp, w.pid, "NM-SESSION", {"fatigue": 1})
    assert e.value.code == "respondent_type"
    p = svc.submit_response(w.co, w.pid, "NM-DEV", {"setting": "clinic"})
    assert p["completion"] == "partial" and "position" in p["missing_items"]
    with pytest.raises(ValidationFailed) as e:
        svc.submit_response(w.part, w.pid, "NM-SESSION", {"fatigue": 1}, language="es")
    assert e.value.code == "translation_unavailable"
    with pytest.raises(ValidationFailed) as e:
        svc.submit_response(w.part, w.pid, "ZBI", {"q1": 1})
    assert e.value.code in ("license_required", "respondent_type")
    asg = {a["instrument_id"]: a for a in svc.list_assignments(w.co, w.pid)
           if a["visit_id"] == base["id"]}
    assert asg["NM-SESSION"]["status"] == "completed"
    assert asg["NM-SESSION"]["response_id"] == r["id"]
    assert all(x["status"] == "cancelled" for x in asg["NM-SESSION"]["reminders"])
    resp = svc.list_responses(w.co, w.pid)
    assert {x["instrument_id"] for x in resp} == {"NM-SESSION", "NM-CPB", "NM-DEV"}
