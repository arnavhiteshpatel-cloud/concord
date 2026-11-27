"""Evidence exports and sponsor dashboards.

Exports are study data packages (CSV + JSON) with a versioned schema, a data dictionary
generated from the live schema and the data inventory, an analysis dataset (one row per
participant x visit x task x metric), SDTM-*inspired* layouts (a QS-like questionnaire table
and a custom functional-task domain "XF"), and a FHIR QuestionnaireResponse bundle (structure
only). Every package has a ``manifest.json`` with the SHA-256 of every file, software,
battery, scorer and instrument versions, and the audit-chain head hash.

NO conformance is claimed: not CDISC SDTM conformant, not FHIR-profile validated.

Audiences:
* ``sponsor`` (sponsor analysts, investigators): pseudonymous data of participants whose
  latest consent record allows ``sharing_with_sponsor``; no free text, no deviation
  descriptions, no device free-text fields, no re-identification data, no raw events.
* ``full`` (investigators): all participants at the investigator's sites; still no
  re-identification data, free text or raw events (those leave only via subject export).
"""
from __future__ import annotations

import csv
import io
import json
import statistics
import zipfile
from collections import defaultdict
from pathlib import Path
from typing import Any, Optional

from ..instruments.fhir import bundle as fhir_bundle, to_questionnaire_response
from ..tasks.battery import BATTERY_VERSION
from .core import StudyServiceBase, jload, new_id
from .db import canonical_json, sha256_hex
from .errors import PermissionDenied, ValidationFailed
from .inventory import INVENTORY, describe
from .permissions import Actor, require
from .scoring import PRIMARY_METRICS, SCORER_VERSION, flat_metrics
from .telemetry import summarize_batches

EXPORT_SCHEMA_VERSION = "1.0.0"
DISCLAIMERS = [
    "Research data from NeuroMetric (research software; not a medical device).",
    "SDTM-inspired layouts only: NOT CDISC SDTM conformant.",
    "FHIR QuestionnaireResponse structure only: no FHIR conformance or profile validation claimed.",
    "Functional tasks and NeuroMetric questionnaires are experimental / unvalidated measures.",
]
DEMO_BANNER = "DEMO - synthetic data, not patients"


def software_version() -> str:
    try:
        from importlib.metadata import version
        return version("neurometric")
    except Exception:  # pragma: no cover
        return "unknown"


def _unit(metric: str) -> str:
    if metric.endswith("_ms") or "_ms_" in metric:
        return "ms"
    if metric.endswith("_px") or "_px_" in metric:
        return "px"
    if metric.endswith("_bps"):
        return "bit/s"
    if metric.startswith("wpm"):
        return "words/min"
    if metric.startswith("ccpm"):
        return "chars/min"
    if "rate" in metric:
        return "fraction"
    if metric.endswith("_min"):
        return "min"
    return ""


def _write_csv(path: Path, rows: list[dict[str, Any]], columns: Optional[list[str]] = None) -> int:
    cols = columns or (sorted({k for r in rows for k in r}) if rows else [])
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore", lineterminator="\n")
        w.writeheader()
        for r in rows:
            w.writerow({k: ("" if r.get(k) is None else r.get(k)) for k in cols})
    return len(rows)


def file_sha256(path: Path) -> str:
    return sha256_hex(path.read_bytes())


def verify_export(out_dir: str | Path) -> dict[str, Any]:
    out_dir = Path(out_dir)
    m = json.loads((out_dir / "manifest.json").read_text("utf-8"))
    bad = [f["path"] for f in m["files"]
           if not (out_dir / f["path"]).exists() or file_sha256(out_dir / f["path"]) != f["sha256"]]
    listed = {f["path"] for f in m["files"]} | {"manifest.json"}
    extra = sorted(p.name for p in out_dir.iterdir() if p.name not in listed)
    return {"ok": not bad and not extra, "mismatched": bad, "unlisted_files": extra,
            "audit_chain_head": m["audit_chain_head"]}


def zip_dir(out_dir: str | Path) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for p in sorted(Path(out_dir).iterdir()):
            z.write(p, p.name)
    return buf.getvalue()


class ExportMixin(StudyServiceBase):
    # ------------------------------------------------------------------ participant selection
    def _sponsor_shareable(self, pid: str) -> bool:
        c = self.db.one("SELECT scopes_json FROM consent_records WHERE participant_id=? "
                        "ORDER BY given_at DESC, rowid DESC LIMIT 1", (pid,))
        return bool(c and jload(c["scopes_json"], {}).get("sharing_with_sponsor"))

    def _participants_for(self, actor: Actor, study_id: str, audience: str) -> list[dict]:
        rows = self.db.query("SELECT p.*, s.code AS site_code FROM participants p JOIN sites s "
                             "ON s.id=p.site_id WHERE p.study_id=? AND p.org_id=? ORDER BY p.id",
                             (study_id, actor.org_id))
        if audience == "sponsor":
            return [r for r in rows if self._sponsor_shareable(r["id"])]
        if actor.role in ("coordinator", "investigator"):
            return [r for r in rows if r["site_id"] in actor.site_ids]
        return []

    # ------------------------------------------------------------------ dashboard
    def dashboard(self, actor: Actor, study_id: str) -> dict[str, Any]:
        """Aggregates only (no participant ids). Groups smaller than the study's
        ``min_cell_size`` are suppressed."""
        require(actor, "dashboard.read")
        s = self._study(actor, study_id)
        audience = "sponsor" if actor.role == "sponsor_analyst" else "full"
        parts = self._participants_for(actor, study_id, audience)
        pids = {p["id"] for p in parts}
        k = max(1, int(s["min_cell_size"]))

        def cell(values: list[float]) -> dict[str, Any]:
            n = len(values)
            if n < k:
                return {"n": n, "suppressed": True, "mean": None, "sd": None}
            return {"n": n, "suppressed": False, "mean": statistics.fmean(values),
                    "sd": statistics.stdev(values) if n > 1 else None}

        enroll: dict[str, int] = defaultdict(int)
        for p in parts:
            enroll[p["enrollment_state"]] += 1
        visits = [v for v in self.db.query("SELECT * FROM visits WHERE study_id=? AND org_id=?",
                                           (study_id, actor.org_id)) if v["participant_id"] in pids]
        comp: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
        for v in visits:
            if v["status"] == "cancelled":
                continue
            c = comp[v["visit_code"]]
            c["expected"] += 1
            c[v["status"]] += 1
        completeness = []
        for code, c in sorted(comp.items()):
            done = c.get("completed", 0) + c.get("completed_out_of_window", 0)
            completeness.append({"visit_code": code, "expected": c["expected"], "completed": done,
                                 "out_of_window": c.get("completed_out_of_window", 0),
                                 "missed": c.get("missed", 0),
                                 "completeness": done / c["expected"] if c["expected"] else None})
        vcode = {v["id"]: v["visit_code"] for v in visits}
        sessions = [r for r in self.db.query(
            "SELECT participant_id, visit_id, task_id, modality, metrics_json FROM "
            "functional_sessions WHERE study_id=? AND org_id=? AND status='valid'",
            (study_id, actor.org_id)) if r["participant_id"] in pids]
        trend: dict[tuple, list[float]] = defaultdict(list)
        modal: dict[tuple, list[float]] = defaultdict(list)
        for r in sessions:
            metric = PRIMARY_METRICS.get(r["task_id"])
            val = jload(r["metrics_json"], {}).get(metric) if metric else None
            if val is None:
                continue
            trend[(r["task_id"], metric, vcode.get(r["visit_id"], "unscheduled"))].append(val)
            modal[(r["task_id"], metric, r["modality"])].append(val)
        trends = [{"task_id": t, "metric": m, "visit_code": vc, **cell(v)}
                  for (t, m, vc), v in sorted(trend.items())]
        modality = [{"task_id": t, "metric": m, "modality": mo, **cell(v)}
                    for (t, m, mo), v in sorted(modal.items())]
        miss: dict[tuple, int] = defaultdict(int)
        for r in self.db.query("SELECT participant_id, item_type, reason_code FROM missing_data "
                               "WHERE study_id=? AND org_id=?", (study_id, actor.org_id)):
            if r["participant_id"] in pids:
                miss[(r["item_type"], r["reason_code"])] += 1
        devs: dict[tuple, int] = defaultdict(int)
        for r in self.db.query("SELECT participant_id, category, severity, status FROM "
                               "protocol_deviations WHERE study_id=? AND org_id=?",
                               (study_id, actor.org_id)):
            if r["participant_id"] is None or r["participant_id"] in pids:
                devs[(r["category"], r["severity"], r["status"])] += 1
        qs: dict[str, int] = defaultdict(int)
        for r in self.db.query("SELECT participant_id, status FROM data_queries WHERE study_id=? "
                               "AND org_id=?", (study_id, actor.org_id)):
            if r["participant_id"] is None or r["participant_id"] in pids:
                qs[r["status"]] += 1
        inst: dict[tuple, list[float]] = defaultdict(list)
        for r in self.db.query("SELECT participant_id, visit_id, instrument_id, score_json FROM "
                               "questionnaire_responses WHERE study_id=? AND org_id=?",
                               (study_id, actor.org_id)):
            if r["participant_id"] not in pids:
                continue
            for sid, sc in jload(r["score_json"], {}).get("scales", {}).items():
                if sc.get("score") is not None:
                    inst[(r["instrument_id"], sid, vcode.get(r["visit_id"], "unscheduled"))].append(
                        float(sc["score"]))
        tel = defaultdict(list)
        for r in self.db.query("SELECT * FROM telemetry_batches WHERE study_id=? AND org_id=?",
                               (study_id, actor.org_id)):
            if r["participant_id"] in pids:
                tel[r["participant_id"]].append(r)
        per_day = []
        for pid, rows in tel.items():
            sm = summarize_batches(rows)
            if sm["days"]:
                per_day.append(sm["active_minutes"] / len(sm["days"]))
        return {
            "study": {"id": s["id"], "code": s["code"], "title": s["title"],
                      "is_demo": bool(s["is_demo"])},
            "banner": DEMO_BANNER if s["is_demo"] else None,
            "audience": audience, "min_cell_size": k, "n_participants": len(parts),
            "enrollment": dict(enroll), "completeness_by_visit": completeness,
            "task_trends": trends, "modality_comparison": modality,
            "missing_data": [{"item_type": a, "reason_code": b, "count": n}
                             for (a, b), n in sorted(miss.items())],
            "deviations": [{"category": a, "severity": b, "status": c, "count": n}
                           for (a, b, c), n in sorted(devs.items())],
            "queries": dict(qs),
            "questionnaire_scores": [{"instrument_id": i, "scale": sc, "visit_code": vc, **cell(v)}
                                     for (i, sc, vc), v in sorted(inst.items())],
            "telemetry": {"participants_reporting": len(per_day),
                          "active_minutes_per_day": cell(per_day)},
        }

    # ------------------------------------------------------------------ exports
    def data_dictionary(self) -> list[dict[str, Any]]:
        out = []
        for t in self.db.tables():
            inv = INVENTORY.get(t, {})
            for c in self.db.columns(t):
                out.append({"table": t, "column": c["name"], "type": c["type"],
                            "nullable": not c["notnull"], "description": describe(t, c["name"]),
                            "purpose": inv.get("purpose", ""), "category": inv.get("category", ""),
                            "sensitivity": inv.get("sensitivity", ""),
                            "retention": inv.get("retention", ""),
                            "visible_to": inv.get("visible_to", "")})
        return out

    def export_study(self, actor: Actor, study_id: str, out_dir: str | Path,
                     audience: str = "sponsor") -> dict[str, Any]:
        if audience == "sponsor":
            require(actor, "export.sponsor")
        elif audience == "full":
            require(actor, "export.full")
        else:
            raise ValidationFailed("audience must be sponsor or full")
        s = self._study(actor, study_id)
        out = Path(out_dir)
        out.mkdir(parents=True, exist_ok=True)
        if any(out.iterdir()):
            raise ValidationFailed("export directory must be empty")
        parts = self._participants_for(actor, study_id, audience)
        pids = {p["id"] for p in parts}
        usubj = lambda pid: f"{s['code']}-{pid}"  # noqa: E731
        files: dict[str, int] = {}

        # data dictionary
        dd = self.data_dictionary()
        files["data_dictionary.csv"] = _write_csv(out / "data_dictionary.csv", dd, list(dd[0]))
        (out / "data_dictionary.json").write_text(json.dumps(
            {"export_schema_version": EXPORT_SCHEMA_VERSION, "fields": dd}, indent=1), "utf-8")
        files["data_dictionary.json"] = len(dd)

        pcols = ["participant_id", "site_code", "enrollment_state", "cohort", "primary_modality",
                 "enrolled_on", "is_demo"]
        files["participants.csv"] = _write_csv(out / "participants.csv", [
            {**p, "participant_id": p["id"]} for p in parts], pcols)

        visits = [v for v in self.db.query("SELECT * FROM visits WHERE study_id=? AND org_id=? "
                                           "ORDER BY participant_id, target_date",
                                           (study_id, actor.org_id)) if v["participant_id"] in pids]
        vmap = {v["id"]: v for v in visits}
        vcols = ["id", "participant_id", "visit_code", "visit_type", "target_date",
                 "window_start", "window_end", "status", "completed_at", "is_demo"]
        files["visits.csv"] = _write_csv(out / "visits.csv", visits, vcols)

        sessions = [r for r in self.db.query(
            "SELECT * FROM functional_sessions WHERE study_id=? AND org_id=? ORDER BY uploaded_at",
            (study_id, actor.org_id)) if r["participant_id"] in pids]
        scols = ["id", "participant_id", "visit_id", "task_id", "battery_version",
                 "performed_at", "stimulus_seed", "stimulus_hash", "modality", "provenance", "events_sha256",
                 "n_events", "raw_purged", "scorer_version", "status", "uploaded_at", "is_demo"]
        files["functional_sessions.csv"] = _write_csv(out / "functional_sessions.csv", sessions,
                                                      scols)
        analysis, xf = [], []
        for r in sessions:
            v = vmap.get(r["visit_id"]) or {}
            fm = flat_metrics(jload(r["metrics_json"], {}))
            for seq, (m, val) in enumerate(sorted(fm.items()), 1):
                analysis.append({"study_code": s["code"], "participant_id": r["participant_id"],
                                 "visit_code": v.get("visit_code", "unscheduled"),
                                 "visit_target_date": v.get("target_date", ""),
                                 "task_id": r["task_id"], "battery_version": r["battery_version"],
                                 "modality": r["modality"], "session_id": r["id"],
                                 "session_status": r["status"], "metric": m, "value": val,
                                 "unit": _unit(m), "is_primary": int(PRIMARY_METRICS.get(r["task_id"]) == m),
                                 "is_demo": r["is_demo"]})
                xf.append({"STUDYID": s["code"], "DOMAIN": "XF", "USUBJID": usubj(r["participant_id"]),
                           "XFSPID": r["id"], "XFTESTCD": m[:8].upper(), "XFTEST": m,
                           "XFCAT": r["task_id"], "XFORRES": val, "XFSTRESN": val,
                           "XFSTRESU": _unit(m), "XFMETHOD": r["modality"],
                           "XFGRPID": f"battery-{r['battery_version']}",
                           "VISIT": v.get("visit_code", "unscheduled"),
                           "XFDTC": r["performed_at"], "XFSTAT": "" if r["status"] == "valid" else "NOT DONE"})
        acols = ["study_code", "participant_id", "visit_code", "visit_target_date", "task_id",
                 "battery_version", "modality", "session_id", "session_status", "metric", "value",
                 "unit", "is_primary", "is_demo"]
        files["analysis_dataset.csv"] = _write_csv(out / "analysis_dataset.csv", analysis, acols)
        for i, row in enumerate(xf, 1):
            row["XFSEQ"] = i
        xcols = ["STUDYID", "DOMAIN", "USUBJID", "XFSEQ", "XFSPID", "XFTESTCD", "XFTEST", "XFCAT",
                 "XFORRES", "XFSTRESN", "XFSTRESU", "XFMETHOD", "XFGRPID", "VISIT", "XFDTC", "XFSTAT"]
        files["sdtm_like_xf_functional.csv"] = _write_csv(out / "sdtm_like_xf_functional.csv", xf,
                                                         xcols)

        responses = [self._response_view(r) for r in self.db.query(
            "SELECT * FROM questionnaire_responses WHERE study_id=? AND org_id=? ORDER BY "
            "submitted_at", (study_id, actor.org_id)) if r["participant_id"] in pids]
        qs, fhir, inst_versions = [], [], defaultdict(set)
        for r in responses:
            inst = self.instruments.get(r["instrument_id"], r["instrument_version"])
            inst_versions[r["instrument_id"]].add(r["instrument_version"])
            visit = (vmap.get(r["visit_id"]) or {}).get("visit_code", "unscheduled")
            base = {"STUDYID": s["code"], "DOMAIN": "QS", "USUBJID": usubj(r["participant_id"]),
                    "QSCAT": r["instrument_id"], "QSSCAT": r["instrument_version"],
                    "QSEVAL": r["respondent_type"], "VISIT": visit, "QSDTC": r["submitted_at"]}
            for it in inst.items:
                if it["type"] == "free_text":
                    continue
                if it["id"] in r["answers"]:
                    val = r["answers"][it["id"]]
                    num = val if isinstance(val, (int, float)) and not isinstance(val, bool) else (
                        int(val) if isinstance(val, bool) else None)
                    qs.append({**base, "QSTESTCD": it["id"][:8].upper(), "QSTEST": it.get("text", "")[:40],
                               "QSORRES": json.dumps(val) if isinstance(val, list) else val,
                               "QSSTRESC": json.dumps(val) if isinstance(val, list) else val,
                               "QSSTRESN": num, "QSSTAT": "", "QSDRVFL": ""})
                elif it.get("required", True):
                    qs.append({**base, "QSTESTCD": it["id"][:8].upper(),
                               "QSTEST": it.get("text", "")[:40], "QSORRES": "", "QSSTRESC": "",
                               "QSSTRESN": None, "QSSTAT": "NOT DONE", "QSDRVFL": ""})
            for sid, sc in r["scores"].items():
                qs.append({**base, "QSTESTCD": sid[:8].upper(), "QSTEST": f"{sid} (derived score)",
                           "QSORRES": sc.get("score"), "QSSTRESC": sc.get("score"),
                           "QSSTRESN": sc.get("score"), "QSSTAT": "" if sc.get("score") is not None
                           else "NOT DONE", "QSDRVFL": "Y"})
            fhir.append(to_questionnaire_response(r, inst))
        for i, row in enumerate(qs, 1):
            row["QSSEQ"] = i
        qcols = ["STUDYID", "DOMAIN", "USUBJID", "QSSEQ", "QSTESTCD", "QSTEST", "QSCAT", "QSSCAT",
                 "QSEVAL", "QSORRES", "QSSTRESC", "QSSTRESN", "QSSTAT", "QSDRVFL", "VISIT", "QSDTC"]
        files["sdtm_like_qs_questionnaires.csv"] = _write_csv(
            out / "sdtm_like_qs_questionnaires.csv", qs, qcols)
        (out / "fhir_questionnaire_responses.json").write_text(json.dumps(
            fhir_bundle(fhir, new_id("bundle"), self.db.now_iso()), indent=1), "utf-8")
        files["fhir_questionnaire_responses.json"] = len(fhir)

        tel_rows = []
        by_p = defaultdict(list)
        for r in self.db.query("SELECT * FROM telemetry_batches WHERE study_id=? AND org_id=?",
                               (study_id, actor.org_id)):
            if r["participant_id"] in pids:
                by_p[r["participant_id"]].append(r)
        for pid, rows in sorted(by_p.items()):
            daily = defaultdict(list)
            for r in rows:
                daily[r["period_start"][:10]].append(r)
            for day, drows in sorted(daily.items()):
                sm = summarize_batches(drows)
                tel_rows.append({"participant_id": pid, "date": day, "n_batches": sm["n_batches"],
                                 "active_minutes": sm["active_minutes"],
                                 "device_assisted_sessions": sm["device_assisted_sessions"],
                                 "interruptions": sm["interruptions"],
                                 **{f"count_{k}": v for k, v in sm["interaction_counts"].items()},
                                 "assistance_minutes": sum(sm["assistance_minutes"].values()),
                                 "fatigue_mean": sm["fatigue_mean"], "burden_mean": sm["burden_mean"],
                                 "flagged_batches": sm["flagged_batches"]})
        files["telemetry_daily.csv"] = _write_csv(out / "telemetry_daily.csv", tel_rows)

        dev = [d for d in self.db.query("SELECT * FROM protocol_deviations WHERE study_id=? AND "
                                        "org_id=?", (study_id, actor.org_id))
               if d["participant_id"] is None or d["participant_id"] in pids]
        dcols = ["id", "participant_id", "visit_id", "category", "severity", "status",
                 "reported_at"] + (["description"] if audience == "full" else [])
        files["protocol_deviations.csv"] = _write_csv(out / "protocol_deviations.csv", dev, dcols)
        miss = [m for m in self.db.query("SELECT * FROM missing_data WHERE study_id=? AND org_id=?",
                                         (study_id, actor.org_id)) if m["participant_id"] in pids]
        files["missing_data.csv"] = _write_csv(out / "missing_data.csv", miss, [
            "id", "participant_id", "visit_id", "item_type", "item_ref", "reason_code",
            "recorded_at"])
        qry = [q for q in self.db.query("SELECT * FROM data_queries WHERE study_id=? AND org_id=?",
                                        (study_id, actor.org_id))
               if q["participant_id"] is None or q["participant_id"] in pids]
        files["data_queries.csv"] = _write_csv(out / "data_queries.csv", qry, [
            "id", "participant_id", "record_table", "record_id", "field", "question", "status",
            "answer", "raised_at", "answered_at", "closed_at"])
        (out / "MAPPING_NOTES.md").write_text(MAPPING_NOTES, "utf-8")
        files["MAPPING_NOTES.md"] = 0

        manifest = {
            "format": "neurometric.export/1", "export_schema_version": EXPORT_SCHEMA_VERSION,
            "study": {"id": s["id"], "code": s["code"], "title": s["title"],
                      "is_demo": bool(s["is_demo"])},
            "banner": DEMO_BANNER if s["is_demo"] else None,
            "audience": audience, "generated_at": self.db.now_iso(),
            "generated_by": {"user_id": actor.user_id, "role": actor.role},
            "software_version": software_version(), "battery_version": BATTERY_VERSION,
            "scorer_version": SCORER_VERSION, "database_schema_version": self.db.schema_version(),
            "instrument_versions": {k: sorted(v) for k, v in sorted(inst_versions.items())},
            "instrument_registry": self.instruments.versions(),
            "n_participants": len(parts),
            "disclaimers": DISCLAIMERS,
            "files": [{"path": name, "sha256": file_sha256(out / name),
                       "bytes": (out / name).stat().st_size, "records": n}
                      for name, n in sorted(files.items())],
        }
        # record the export in the audit trail first, then anchor the manifest on the new head
        self.audit.append(actor, "export", "studies", study_id, reason=f"export ({audience})",
                          new={"files": {f["path"]: f["sha256"] for f in manifest["files"]}})
        manifest["audit_chain_head"] = self.audit.head()
        manifest["audit_entries"] = self.audit.count()
        (out / "manifest.json").write_text(json.dumps(manifest, indent=2), "utf-8")
        return manifest


MAPPING_NOTES = """# NeuroMetric export mapping notes

**No conformance claim.** These layouts are *inspired by* CDISC SDTM conventions to make
downstream conversion easier. They are NOT CDISC SDTM conformant (no define.xml, no controlled
terminology validation, no trial design domains, custom test codes). The FHIR file follows the
*structure* of the R4 QuestionnaireResponse resource; it has not been validated against any FHIR
profile.

## sdtm_like_qs_questionnaires.csv (QS-like)
* One row per answered item (QSORRES/QSSTRESC/QSSTRESN), one row per required unanswered item
  (QSSTAT = NOT DONE) and one row per derived scale score (QSDRVFL = Y).
* QSCAT = instrument id, QSSCAT = instrument version (responses keep the version answered).
* QSEVAL = respondent type (PRO / ObsRO / ClinRO). USUBJID = study code + pseudonym.
* Free-text items are never exported.

## sdtm_like_xf_functional.csv (custom domain XF: functional tasks)
* Custom domain code "XF" (sponsor-defined domains use X/Y/Z prefixes by SDTM convention).
* One row per session x metric. XFCAT = battery task id, XFGRPID = battery version,
  XFMETHOD = input modality, XFSPID = session id, XFSTRESU = unit.
* XFTESTCD is an 8-character truncation of the metric name; XFTEST holds the full name.

## analysis_dataset.csv
* Long format: one row per participant x visit x task x metric, with units and an is_primary
  flag (primary metric per task as used in dashboards).

## telemetry_daily.csv
* Daily sums of aggregate telemetry batches (no content was ever collected).

## Provenance
* manifest.json lists the SHA-256 of every file, software / battery / scorer / instrument
  versions and the audit-chain head hash at export time; compare the head hash with
  `GET /api/audit/verify` to confirm the export was produced from an intact trail.
"""
