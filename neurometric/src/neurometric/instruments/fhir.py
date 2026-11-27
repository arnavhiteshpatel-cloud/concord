"""FHIR R4 QuestionnaireResponse export (structure only).

The output follows the shape of the FHIR R4 ``QuestionnaireResponse`` resource and a
``collection`` Bundle. It has NOT been validated against FHIR profiles and makes no
conformance claim. Free-text answers are never included. Subjects are identified only by the
NeuroMetric pseudonym.
"""
from __future__ import annotations

from typing import Any

from .engine import Instrument

PSEUDONYM_SYSTEM = "urn:neurometric:pseudonym"
SCORE_EXT = "urn:neurometric:fhir:extension:scale-score"


def questionnaire_url(inst_id: str, version: str) -> str:
    return f"urn:neurometric:instrument:{inst_id}|{version}"


def _answer(item: dict[str, Any], value: Any) -> list[dict[str, Any]]:
    t = item["type"]
    if t == "yes_no":
        return [{"valueBoolean": bool(value)}]
    if t in ("likert", "choice", "multi_choice"):
        labels = {o["value"]: o["label"] for o in item["options"]}
        vals = value if isinstance(value, list) else [value]
        return [{"valueCoding": {"system": f"urn:neurometric:item:{item['id']}",
                                 "code": str(v), "display": labels.get(v, str(v))}} for v in vals]
    if t == "minutes":
        return [{"valueQuantity": {"value": value, "unit": "min",
                                   "system": "http://unitsofmeasure.org", "code": "min"}}]
    if t == "numeric":
        if isinstance(value, int) or float(value).is_integer():
            return [{"valueInteger": int(value)}]
        return [{"valueDecimal": float(value)}]
    return []


def to_questionnaire_response(response: dict[str, Any], inst: Instrument) -> dict[str, Any]:
    items = []
    for it in inst.items:
        if it["type"] == "free_text" or it["id"] not in response["answers"]:
            continue
        items.append({"linkId": it["id"], "text": it.get("text", ""),
                      "answer": _answer(it, response["answers"][it["id"]])})
    ext = []
    for sid, sc in (response.get("scores") or {}).items():
        if sc.get("score") is not None:
            ext.append({"url": SCORE_EXT, "extension": [
                {"url": "scale", "valueString": sid},
                {"url": "score", "valueDecimal": float(sc["score"])},
                {"url": "status", "valueString": sc.get("status", "")}]})
    res = {"resourceType": "QuestionnaireResponse", "id": response["id"],
           "questionnaire": questionnaire_url(response["instrument_id"],
                                              response["instrument_version"]),
           "status": "completed",
           "subject": {"identifier": {"system": PSEUDONYM_SYSTEM,
                                      "value": response["participant_id"]}},
           "authored": response["submitted_at"],
           "author": {"display": response.get("respondent_role", "")},
           "item": items}
    if ext:
        res["extension"] = ext
    if response.get("completion") == "partial":
        res.setdefault("extension", []).append(
            {"url": "urn:neurometric:fhir:extension:completion", "valueString": "partial"})
    return res


def bundle(resources: list[dict[str, Any]], bundle_id: str, timestamp: str) -> dict[str, Any]:
    return {"resourceType": "Bundle", "id": bundle_id, "type": "collection",
            "timestamp": timestamp,
            "meta": {"tag": [{"system": "urn:neurometric:conformance",
                              "code": "structure-only-no-conformance-claim"}]},
            "entry": [{"fullUrl": f"urn:neurometric:{r['resourceType']}:{r['id']}", "resource": r}
                      for r in resources]}
