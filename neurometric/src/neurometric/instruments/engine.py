"""Questionnaire engine: instrument definitions, response validation and scoring.

Definitions are JSON files in ``instruments/defs/`` (one file per instrument version). An
instrument definition has:

``id``, ``version``, ``title``, ``respondent_type`` (PRO / ObsRO / ClinRO), ``status``
(e.g. 'original, unvalidated research questionnaire'), ``license`` {status, holder, citation,
notes}, ``recall_period``, ``languages`` {code: 'source' | 'authorized translation required'},
``accessibility`` metadata, ``schedule`` (default administration rule), ``items`` and
``scoring``.

Item response types: ``likert`` (options), ``numeric`` (min/max), ``minutes`` (0..max),
``yes_no``, ``choice`` (options), ``multi_choice`` (options), ``free_text`` (always flagged
``sensitive``; stored only with the participant's ``free_text`` consent).

Scoring scales: ``method`` in ``sum`` | ``mean`` | ``sus`` | ``nasa_tlx_raw`` |
``nasa_tlx_weighted``; ``items``; ``reverse_items`` (reverse = min + max - value);
``min_answered`` (count) - below it the scale score is not computed (``insufficient``);
``prorate`` (sum scales: sum * n_items / n_answered when min_answered <= answered < n_items).

Licensed instruments (``license.status == 'license_required'``) are metadata-only stubs: no
copyrighted item text is reproduced. A licensed sponsor can load items at run time with
:func:`load_licensed_items`.
"""
from __future__ import annotations

import copy
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

DEFS_DIR = Path(__file__).resolve().parent / "defs"
RESPONSE_TYPES = {"likert", "numeric", "minutes", "yes_no", "choice", "multi_choice",
                  "free_text"}
RESPONDENT_TYPES = {"PRO", "ObsRO", "ClinRO", "PerfO"}
LICENSE_STATUSES = {"original", "public_domain", "free_with_attribution", "license_required"}
SCORING_METHODS = {"sum", "mean", "sus", "nasa_tlx_raw", "nasa_tlx_weighted", "none"}
TLX_SUBSCALES = ("mental", "physical", "temporal", "performance", "effort", "frustration")


class InstrumentError(ValueError):
    pass


class ResponseError(ValueError):
    def __init__(self, message: str, errors: list[str]):
        super().__init__(message)
        self.errors = errors


@dataclass
class Instrument:
    definition: dict[str, Any]

    @property
    def id(self) -> str:
        return self.definition["id"]

    @property
    def version(self) -> str:
        return self.definition["version"]

    @property
    def items(self) -> list[dict]:
        return self.definition.get("items", [])

    @property
    def license_status(self) -> str:
        return self.definition["license"]["status"]

    @property
    def items_loaded(self) -> bool:
        return bool(self.items)

    def item(self, item_id: str) -> Optional[dict]:
        return next((i for i in self.items if i["id"] == item_id), None)

    def public(self) -> dict[str, Any]:
        return copy.deepcopy(self.definition)


def validate_definition(d: dict[str, Any]) -> None:
    errs = []
    for k in ("id", "version", "title", "respondent_type", "status", "license", "items",
              "scoring", "languages"):
        if k not in d:
            errs.append(f"missing '{k}'")
    if errs:
        raise InstrumentError(f"{d.get('id', '?')}: " + "; ".join(errs))
    if d["respondent_type"] not in RESPONDENT_TYPES:
        errs.append(f"respondent_type {d['respondent_type']!r}")
    lic = d["license"].get("status")
    if lic not in LICENSE_STATUSES:
        errs.append(f"license.status {lic!r}")
    if lic == "license_required" and d["items"]:
        errs.append("license_required stubs must not ship item content")
    for code, status in d["languages"].items():
        if status not in ("source", "authorized translation required"):
            errs.append(f"language {code}: status must be 'source' or 'authorized translation required'")
    ids = set()
    for it in d["items"]:
        if it.get("id") in ids:
            errs.append(f"duplicate item id {it.get('id')}")
        ids.add(it.get("id"))
        t = it.get("type")
        if t not in RESPONSE_TYPES:
            errs.append(f"item {it.get('id')}: type {t!r}")
        if t in ("likert", "choice", "multi_choice") and not it.get("options"):
            errs.append(f"item {it['id']}: options required")
        if t == "numeric" and ("min" not in it or "max" not in it):
            errs.append(f"item {it['id']}: numeric requires min and max")
        if t == "free_text" and not it.get("sensitive"):
            errs.append(f"item {it['id']}: free_text items must be flagged sensitive")
    for sc in d["scoring"].get("scales", []):
        if sc.get("method") not in SCORING_METHODS:
            errs.append(f"scale {sc.get('id')}: method {sc.get('method')!r}")
        if d["items"]:
            for iid in sc.get("items", []) + sc.get("reverse_items", []):
                if iid not in ids:
                    errs.append(f"scale {sc.get('id')}: unknown item {iid}")
    if errs:
        raise InstrumentError(f"{d['id']}: " + "; ".join(errs))


class Registry:
    """All instrument versions, keyed by (id, version)."""

    def __init__(self, defs_dir: Path = DEFS_DIR):
        self._by_key: dict[tuple[str, str], Instrument] = {}
        for p in sorted(Path(defs_dir).glob("*.json")):
            d = json.loads(p.read_text(encoding="utf-8"))
            validate_definition(d)
            self._by_key[(d["id"], d["version"])] = Instrument(d)

    def add(self, d: dict[str, Any]) -> Instrument:
        validate_definition(d)
        inst = Instrument(copy.deepcopy(d))
        self._by_key[(inst.id, inst.version)] = inst
        return inst

    def get(self, instrument_id: str, version: Optional[str] = None) -> Instrument:
        if version is None:
            cands = [v for (i, v) in self._by_key if i == instrument_id]
            if not cands:
                raise KeyError(instrument_id)
            version = max(cands, key=_vkey)
        try:
            return self._by_key[(instrument_id, version)]
        except KeyError:
            raise KeyError(f"{instrument_id}@{version}") from None

    def list(self) -> list[dict[str, Any]]:
        out = []
        for (iid, ver), inst in sorted(self._by_key.items()):
            d = inst.definition
            out.append({"id": iid, "version": ver, "title": d["title"],
                        "respondent_type": d["respondent_type"], "status": d["status"],
                        "license_status": d["license"]["status"],
                        "items_loaded": inst.items_loaded, "n_items": len(inst.items) or
                        d.get("item_count")})
        return out

    def versions(self) -> dict[str, list[str]]:
        out: dict[str, list[str]] = {}
        for (iid, ver) in self._by_key:
            out.setdefault(iid, []).append(ver)
        return {k: sorted(v, key=_vkey) for k, v in sorted(out.items())}


def _vkey(v: str):
    return tuple(int(x) if x.isdigit() else x for x in v.replace("-", ".").split("."))


def load_licensed_items(registry: Registry, instrument_id: str, version: str,
                        items: list[dict], scoring: dict, attestation: str) -> Instrument:
    """Attach licensed item content supplied at run time by a licensee (never shipped)."""
    base = registry.get(instrument_id, version)
    if base.license_status != "license_required":
        raise InstrumentError("only license_required stubs take externally loaded items")
    if not attestation or len(attestation.strip()) < 10:
        raise InstrumentError("a license attestation (licence reference) is required")
    d = copy.deepcopy(base.definition)
    d["items"] = items
    d["scoring"] = scoring
    d["license"] = {**d["license"], "status": "license_required",
                    "loaded_under_license": attestation}
    # validate as a loaded instrument (bypass the 'stubs ship no content' rule)
    tmp = {**d, "license": {**d["license"], "status": "original"}}
    validate_definition(tmp)
    inst = Instrument(d)
    registry._by_key[(inst.id, inst.version)] = inst
    return inst


# --------------------------------------------------------------------------- responses
def validate_response(inst: Instrument, answers: dict[str, Any], *,
                      allow_free_text: bool) -> tuple[dict[str, Any], dict[str, str], list[str]]:
    """Validate answers. Returns (structured_answers, free_text_answers, missing_item_ids).

    Unknown items, out-of-range values and wrong types are errors. Free-text answers are
    separated so they can be stored (encrypted at rest by the deployment, never exported to
    sponsors) only when consented; without consent a non-empty free-text answer is an error.
    """
    if not inst.items_loaded:
        raise ResponseError("license_required: item content not loaded", ["license_required"])
    if not isinstance(answers, dict):
        raise ResponseError("answers must be an object", ["answers_not_object"])
    errs: list[str] = []
    out: dict[str, Any] = {}
    free: dict[str, str] = {}
    for k in answers:
        if inst.item(k) is None:
            errs.append(f"unknown item '{k}'")
    for it in inst.items:
        iid, t = it["id"], it["type"]
        if iid not in answers or answers[iid] is None or answers[iid] == "":
            continue
        v = answers[iid]
        if t == "free_text":
            if not isinstance(v, str):
                errs.append(f"{iid}: free text must be a string")
            elif not allow_free_text:
                errs.append(f"{iid}: free text not permitted without free_text consent")
            elif len(v) > int(it.get("max_length", 1000)):
                errs.append(f"{iid}: free text too long")
            else:
                free[iid] = v
            continue
        if t in ("likert", "choice"):
            allowed = [o["value"] for o in it["options"]]
            if v not in allowed or isinstance(v, bool):
                errs.append(f"{iid}: {v!r} not in {allowed}")
                continue
        elif t == "multi_choice":
            allowed = [o["value"] for o in it["options"]]
            if not isinstance(v, list) or any(x not in allowed for x in v) or len(set(map(str, v))) != len(v):
                errs.append(f"{iid}: values must be a list of distinct options from {allowed}")
                continue
        elif t == "yes_no":
            if not isinstance(v, bool):
                errs.append(f"{iid}: must be true or false")
                continue
        elif t in ("numeric", "minutes"):
            if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v):
                errs.append(f"{iid}: must be a number")
                continue
            lo = it.get("min", 0)
            hi = it.get("max", 1440 if t == "minutes" else None)
            if v < lo or (hi is not None and v > hi):
                errs.append(f"{iid}: {v} outside [{lo}, {hi}]")
                continue
            step = it.get("step")
            if step and abs((v - lo) / step - round((v - lo) / step)) > 1e-9:
                errs.append(f"{iid}: {v} not a multiple of step {step}")
                continue
        out[iid] = v
    if errs:
        raise ResponseError("invalid response", errs)
    missing = [it["id"] for it in inst.items
               if it["id"] not in out and it["id"] not in free and it.get("required", True)
               and it["type"] != "free_text"]
    return out, free, missing


def _item_range(it: dict) -> tuple[float, float]:
    if it["type"] in ("likert", "choice"):
        vals = [o["value"] for o in it["options"] if isinstance(o["value"], (int, float))]
        return float(min(vals)), float(max(vals))
    return float(it.get("min", 0)), float(it.get("max", 0))


def score(inst: Instrument, answers: dict[str, Any]) -> dict[str, Any]:
    """Score a (validated) response. Returns {scale_id: {score, n_answered, status, ...}}."""
    scales = {}
    for sc in inst.definition["scoring"].get("scales", []):
        method = sc["method"]
        if method == "sus":
            scales[sc["id"]] = _score_sus(sc, answers)
            continue
        if method in ("nasa_tlx_raw", "nasa_tlx_weighted"):
            scales[sc["id"]] = _score_tlx(sc, answers, weighted=method == "nasa_tlx_weighted")
            continue
        if method == "none":
            continue
        items = sc["items"]
        rev = set(sc.get("reverse_items", []))
        vals = []
        for iid in items:
            if iid in answers and isinstance(answers[iid], (int, float)) and not isinstance(answers[iid], bool):
                v = float(answers[iid])
                if iid in rev:
                    lo, hi = _item_range(inst.item(iid))
                    v = lo + hi - v
                vals.append(v)
            elif iid in answers and isinstance(answers[iid], bool):
                vals.append(1.0 if answers[iid] else 0.0)
        n = len(vals)
        need = int(sc.get("min_answered", len(items)))
        res: dict[str, Any] = {"n_items": len(items), "n_answered": n, "min_answered": need,
                               "method": method}
        if n < need or n == 0:
            res.update(score=None, status="insufficient")
        elif method == "sum":
            s = sum(vals)
            if n < len(items) and sc.get("prorate", False):
                s = s * len(items) / n
                res["prorated"] = True
            elif n < len(items):
                res["prorated"] = False
            res.update(score=s, status="scored" if n == len(items) else "scored_with_missing")
        else:
            res.update(score=sum(vals) / n, status="scored" if n == len(items) else "scored_with_missing")
        scales[sc["id"]] = res
    return scales


def _score_sus(sc: dict, answers: dict) -> dict[str, Any]:
    """SUS (Brooke 1996) [PK]: odd items contribute (score - 1), even items (5 - score);
    the sum (0-40) times 2.5 gives 0-100. All 10 items are required (no proration)."""
    items = sc["items"]
    vals = [answers.get(i) for i in items]
    n = sum(v is not None for v in vals)
    if n < len(items):
        return {"score": None, "status": "insufficient", "n_answered": n, "n_items": len(items),
                "method": "sus"}
    contrib = [(v - 1) if k % 2 == 0 else (5 - v) for k, v in enumerate(vals)]
    return {"score": sum(contrib) * 2.5, "status": "scored", "n_answered": n,
            "n_items": len(items), "method": "sus"}


def _score_tlx(sc: dict, answers: dict, weighted: bool) -> dict[str, Any]:
    """NASA-TLX (Hart & Staveland 1988) [PK]. Ratings 0-100 per subscale.

    Raw TLX = mean of the six subscale ratings. Weighted TLX = sum(rating * weight) / 15, where
    weights (0-5) are the tallies from the 15 pairwise comparisons and must sum to 15.
    """
    items = sc["items"]  # the six rating items, in TLX_SUBSCALES order
    ratings = [answers.get(i) for i in items]
    n = sum(r is not None for r in ratings)
    base = {"n_answered": n, "n_items": len(items), "method": sc["method"]}
    if n < len(items):
        return {**base, "score": None, "status": "insufficient"}
    if not weighted:
        return {**base, "score": sum(ratings) / len(items), "status": "scored"}
    wids = sc["weight_items"]
    weights = [answers.get(w) for w in wids]
    if any(w is None for w in weights):
        return {**base, "score": None, "status": "insufficient_weights"}
    if sum(weights) != 15:
        return {**base, "score": None, "status": "invalid_weights",
                "detail": f"weights sum to {sum(weights)}, expected 15"}
    return {**base, "score": sum(r * w for r, w in zip(ratings, weights)) / 15.0,
            "status": "scored", "weights": dict(zip(TLX_SUBSCALES, weights))}


def tlx_weights_from_pairs(choices: dict[str, str]) -> dict[str, int]:
    """Tally the 15 pairwise comparisons: choices maps 'a|b' -> chosen subscale name."""
    w = {s: 0 for s in TLX_SUBSCALES}
    pairs = {f"{a}|{b}" for i, a in enumerate(TLX_SUBSCALES) for b in TLX_SUBSCALES[i + 1:]}
    if set(choices) != pairs:
        raise ValueError("exactly the 15 TLX subscale pairs are required")
    for pair, chosen in choices.items():
        a, b = pair.split("|")
        if chosen not in (a, b):
            raise ValueError(f"choice {chosen!r} not in pair {pair}")
        w[chosen] += 1
    return w


_REGISTRY: Optional[Registry] = None


def registry() -> Registry:
    global _REGISTRY
    if _REGISTRY is None:
        _REGISTRY = Registry()
    return _REGISTRY
