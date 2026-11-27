"""One-call psychometric report for NeuroMetric task scores.

:func:`psychometric_report` runs every analysis that is applicable to a long-format table of
repeated task scores and returns a JSON-serialisable dict; :func:`render_markdown` turns it into
a human-readable Markdown document. Each analysis section carries ``method``, ``n``,
``assumptions`` and ``warnings``; a failing analysis yields a section with ``error`` instead of
aborting the report.
"""
from __future__ import annotations

import json
from typing import Sequence

import numpy as np
import pandas as pd

from ._util import jsonable
from .agreement import bland_altman, lin_ccc
from .effects import benjamini_hochberg, holm
from .invariance import INVARIANCE_SCOPE_NOTE, compare_icc_across_groups, tost
from .mixed import fit_repeated_measures_lmm, missing_data_summary
from .reliability import INTERNAL_CONSISTENCY_WARNING, icc, icc_mixed, sem_mdc, to_wide
from .validity import (distribution_based_change_estimates, floor_ceiling, known_groups,
                       mcid_note)

__all__ = ["psychometric_report", "render_markdown", "REPORT_SCHEMA"]

REPORT_SCHEMA = "neurometric.psychometric_report/1"


def _section(fn, *args, n_key: str | None = None, **kw) -> dict:
    """Run one analysis; normalise the required fields; capture failures."""
    try:
        r = fn(*args, **kw)
    except Exception as e:  # noqa: BLE001 - report must not abort on one analysis
        return {"error": f"{type(e).__name__}: {e}", "method": getattr(fn, "__name__", "?"),
                "n": None, "assumptions": [], "warnings": [f"analysis failed: {e}"]}
    r = dict(r)
    if "n" not in r:
        r["n"] = r.get(n_key) if n_key else None
    r.setdefault("method", getattr(fn, "__name__", "?"))
    r.setdefault("assumptions", [])
    r.setdefault("warnings", [])
    return r


def _descriptives(d: pd.DataFrame, score: str, session_col: str, sessions) -> dict:
    rows = []
    for s in sessions:
        x = d.loc[d[session_col] == s, score].dropna().to_numpy(float)
        rows.append({"session": str(s), "n": int(len(x)),
                     "mean": float(x.mean()) if len(x) else None,
                     "sd": float(x.std(ddof=1)) if len(x) > 1 else None,
                     "median": float(np.median(x)) if len(x) else None,
                     "min": float(x.min()) if len(x) else None,
                     "max": float(x.max()) if len(x) else None})
    return {"per_session": rows, "n": int(d[score].notna().sum()),
            "method": "per-session descriptive statistics (SD with ddof=1)",
            "assumptions": [], "warnings": []}


def psychometric_report(df: pd.DataFrame, score_cols: Sequence[str], subject_col: str,
                        session_col: str, group_col: str | None = None, *,
                        alpha: float = 0.05, icc_form: str = "2,1",
                        bounds: dict | None = None, equivalence_margins: dict | None = None,
                        icc_equivalence_margin: float | None = None, n_boot: int = 1000,
                        seed: int = 0, include_markdown: bool = True) -> dict:
    """Run all applicable psychometric analyses for repeated task scores.

    Parameters
    ----------
    df : long DataFrame, one row per subject x session (x group constant within subject)
    score_cols : task-score columns to analyse (each analysed separately; internal consistency
        across them is deliberately NOT computed — see ``internal_consistency`` in the output)
    subject_col, session_col : identifiers; sessions are ordered by sorting their values
    group_col : optional between-subject grouping (e.g. input modality, clinical group)
    icc_form : primary ICC form for SEM and group comparisons (default ``"2,1"``, absolute
        agreement single measure — the test–retest default, Koo & Li 2016)
    bounds : optional ``{score: (min_possible, max_possible)}`` for floor/ceiling
    equivalence_margins : optional ``{score: margin}`` -> TOST of group means at baseline
    icc_equivalence_margin : optional margin for equivalence of ICCs between groups
    n_boot, seed : bootstrap settings (ICC-difference CIs)

    Analyses per score: descriptives; missing-data summary (+ Little's MCAR test); ICC (all six
    forms, complete-case, F-based CIs) and, if any session is missing, a REML mixed-model ICC;
    SEM/MDC; Bland–Altman and Lin's CCC between the first two sessions; floor/ceiling at the
    first session; a random-intercept LMM of score over session (+ group); with ``group_col``:
    known-groups comparison at the first session (2 groups; pairwise if more), ICC comparison
    across groups and optional TOST; distribution-based change estimates (labelled, not MCID).
    Across scores: Holm and Benjamini–Hochberg adjustment of the known-groups Welch p-values.
    """
    bounds = bounds or {}
    equivalence_margins = equivalence_margins or {}
    d = df.copy()
    sessions = sorted(d[session_col].dropna().unique())
    time_index = {s: i for i, s in enumerate(sessions)}
    tcol = f"{session_col}_index"
    d[tcol] = d[session_col].map(time_index)
    groups = sorted(d[group_col].dropna().unique(), key=str) if group_col else []
    out: dict = {
        "schema": REPORT_SCHEMA,
        "parameters": {"score_cols": list(score_cols), "subject_col": subject_col,
                       "session_col": session_col, "group_col": group_col, "alpha": alpha,
                       "icc_form": icc_form, "n_boot": n_boot, "seed": seed,
                       "bounds": bounds, "equivalence_margins": equivalence_margins,
                       "icc_equivalence_margin": icc_equivalence_margin},
        "n_subjects": int(d[subject_col].nunique()), "n_rows": int(len(d)),
        "sessions": [str(s) for s in sessions], "groups": [str(g) for g in groups],
        "scores": {}, "warnings": [],
    }
    if len(sessions) < 2:
        out["warnings"].append("fewer than 2 sessions: test-retest analyses not possible")
    kg_p: list[tuple[str, str, float]] = []
    for sc in score_cols:
        res: dict = {}
        res["descriptives"] = _descriptives(d, sc, session_col, sessions)
        res["missing_data"] = _section(missing_data_summary, d, subject_col, session_col, [sc],
                                       expected_sessions=sessions, n_key="n_subjects")
        if len(sessions) >= 2:
            w = to_wide(d, subject_col, session_col, sc)
            rel = {"icc": _section(icc, w, alpha=alpha)}
            if w.isna().any().any():
                rel["icc_mixed"] = _section(icc_mixed, w, form=icc_form, n_key="n_subjects")
            rel["sem_mdc"] = _section(sem_mdc, w, icc_form=icc_form)
            res["reliability"] = rel
            s1, s2 = sessions[0], sessions[1]
            res["agreement"] = {
                "sessions": [str(s1), str(s2)],
                "bland_altman": _section(bland_altman, w[s2], w[s1], alpha=alpha),
                "lin_ccc": _section(lin_ccc, w[s2], w[s1], alpha=alpha),
                "note": "differences are session2 - session1 (positive = higher at retest)"}
            res["change_over_sessions"] = _section(
                fit_repeated_measures_lmm, d, sc, subject_col, tcol,
                covariates=[group_col] if group_col else [], n_key="n_subjects")
        base = d.loc[d[session_col] == sessions[0], sc]
        lo, hi = bounds.get(sc, (None, None))
        res["floor_ceiling"] = _section(floor_ceiling, base, min_possible=lo, max_possible=hi)
        sem_val = res.get("reliability", {}).get("sem_mdc", {}).get("sem")
        base_sd = float(base.dropna().std(ddof=1)) if base.notna().sum() > 1 else float("nan")
        res["change_thresholds"] = distribution_based_change_estimates(base_sd, sem_val)
        if group_col and len(groups) >= 2:
            bdf = d.loc[d[session_col] == sessions[0]]
            kg = []
            for i in range(len(groups)):
                for j in range(i + 1, len(groups)):
                    a = bdf.loc[bdf[group_col] == groups[i], sc]
                    b = bdf.loc[bdf[group_col] == groups[j], sc]
                    r = _section(known_groups, a, b, alpha=alpha)
                    if "error" not in r:
                        r["n"] = r["n1"] + r["n2"]
                        kg_p.append((sc, f"{groups[i]} vs {groups[j]}", r["welch_t"]["p"]))
                    kg.append({"group_a": str(groups[i]), "group_b": str(groups[j]), **r})
            res["known_groups"] = {"session": str(sessions[0]), "comparisons": kg}
            if len(sessions) >= 2:
                ci = _section(compare_icc_across_groups, d, sc, subject_col, session_col,
                              group_col, form=icc_form, margin=icc_equivalence_margin,
                              n_boot=n_boot, alpha=alpha, seed=seed)
                if "error" not in ci:
                    ci["n"] = int(sum(v["n_subjects_used"] for v in ci["per_group"].values()))
                res["invariance_reliability"] = ci
            if sc in equivalence_margins and len(groups) == 2:
                a = bdf.loc[bdf[group_col] == groups[0], sc]
                b = bdf.loc[bdf[group_col] == groups[1], sc]
                t = _section(tost, a, b, low=equivalence_margins[sc], alpha=alpha)
                t["n"] = int(a.notna().sum() + b.notna().sum())
                res["invariance_means_tost"] = t
        out["scores"][sc] = res
    if kg_p:
        ps = [p for *_, p in kg_p]
        out["multiplicity"] = {
            "family": "known-groups Welch t-tests across all scores and group pairs",
            "tests": [{"score": s, "comparison": c, "p": p} for s, c, p in kg_p],
            "holm": holm(ps, alpha), "benjamini_hochberg": benjamini_hochberg(ps, alpha),
            "n": len(ps), "method": "Holm (FWER) and Benjamini-Hochberg (FDR)",
            "assumptions": ["BH: independence or positive dependence of tests"], "warnings": []}
    out["internal_consistency"] = {
        "computed": False, "reason": INTERNAL_CONSISTENCY_WARNING,
        "method": "not applicable", "n": None, "assumptions": [], "warnings": []}
    out["invariance_scope"] = INVARIANCE_SCOPE_NOTE
    out["mcid_note"] = mcid_note()
    out = jsonable(out)
    if include_markdown:
        out["markdown"] = render_markdown(out)
    json.dumps(out)  # guarantee serialisable
    return out


# ------------------------------------------------------------------------------- markdown
def _f(v, nd=3):
    if v is None:
        return "–"
    if isinstance(v, (int, np.integer)):
        return str(v)
    try:
        return f"{float(v):.{nd}f}"
    except (TypeError, ValueError):
        return str(v)


def _p(v):
    if v is None:
        return "–"
    return "<0.001" if v < 0.001 else f"{v:.3f}"


def _warn_lines(sec: dict) -> list[str]:
    return [f"> ⚠ {w}" for w in sec.get("warnings", []) if w]


def render_markdown(report: dict) -> str:
    """Render a :func:`psychometric_report` dict as Markdown."""
    L = ["# Psychometric report", "",
         f"Subjects: {report['n_subjects']} · sessions: {', '.join(report['sessions'])}"
         + (f" · groups: {', '.join(report['groups'])}" if report.get("groups") else ""), ""]
    for sc, r in report["scores"].items():
        L += [f"## {sc}", "", "### Descriptives", "",
              "| session | n | mean | SD | median | min | max |", "|---|---|---|---|---|---|---|"]
        for row in r["descriptives"]["per_session"]:
            L.append(f"| {row['session']} | {row['n']} | {_f(row['mean'])} | {_f(row['sd'])} | "
                     f"{_f(row['median'])} | {_f(row['min'])} | {_f(row['max'])} |")
        md = r.get("missing_data", {})
        pv = md.get("per_variable", {}).get(sc)
        if pv:
            L += ["", f"Missing cells: {pv['n_missing']}/{pv['n_cells']} "
                      f"({100 * pv['prop_missing']:.1f}%); monotone {pv['subjects_monotone']}, "
                      f"intermittent {pv['subjects_intermittent']} subjects."]
            lm = md.get("little_mcar", {}).get(sc)
            if lm and lm.get("statistic") is not None:
                L.append(f"Little's MCAR test: χ²={_f(lm['statistic'], 2)}, df={lm['df']}, "
                         f"p={_p(lm['p'])}.")
        rel = r.get("reliability")
        if rel:
            ic = rel["icc"]
            L += ["", "### Reliability (ICC)", ""]
            if "error" in ic:
                L.append(f"ICC failed: {ic['error']}")
            else:
                L += [f"{ic['method']}. n = {ic['n_subjects_used']} complete subjects "
                      f"({ic['n_subjects_dropped']} dropped), k = {ic['k']}.", "",
                      "| form | M&W | type | ICC | 95% CI | F | p |",
                      "|---|---|---|---|---|---|---|"]
                for t in ic["table"]:
                    L.append(f"| {t['form']} | {t['mw_label']} | {t['type']}, {t['unit']} | "
                             f"{_f(t['icc'])} | [{_f(t['ci_low'])}, {_f(t['ci_high'])}] | "
                             f"{_f(t['F'], 2)} | {_p(t['p'])} |")
                L += _warn_lines(ic)
            if "icc_mixed" in rel and "error" not in rel["icc_mixed"]:
                m = rel["icc_mixed"]
                L += ["", f"Mixed-model {m['form']} using all observations: {_f(m['icc'])} "
                          f"({m['n_observations']} observations, {m['n_missing_cells']} missing "
                          "cells)."]
            s = rel["sem_mdc"]
            if "error" not in s:
                L += ["", "### SEM and MDC", "", "| SEM definition | SEM | MDC95 | MDC90 |",
                      "|---|---|---|---|"]
                for k, v in s["by_definition"].items():
                    star = " (primary)" if k == s["primary"] else ""
                    L.append(f"| {k}{star} | {_f(v['sem'])} | {_f(v['mdc95'])} | "
                             f"{_f(v['mdc90'])} |")
                L.append("")
                L.append("MDC = statistically detectable change for an individual, not a "
                         "clinically important change.")
        ag = r.get("agreement")
        if ag:
            ba, cc = ag["bland_altman"], ag["lin_ccc"]
            L += ["", f"### Agreement (session {ag['sessions'][1]} − {ag['sessions'][0]})", ""]
            if "error" not in ba:
                L.append(f"Bland–Altman: bias {_f(ba['bias'])} [{_f(ba['bias_ci'][0])}, "
                         f"{_f(ba['bias_ci'][1])}], LoA {_f(ba['loa_low'])} "
                         f"[{_f(ba['loa_low_ci'][0])}, {_f(ba['loa_low_ci'][1])}] to "
                         f"{_f(ba['loa_high'])} [{_f(ba['loa_high_ci'][0])}, "
                         f"{_f(ba['loa_high_ci'][1])}]; proportional-bias slope "
                         f"{_f(ba['proportional_bias']['slope'])} "
                         f"(p={_p(ba['proportional_bias']['p'])}); n={ba['n']}.")
                L += _warn_lines(ba)
            if "error" not in cc:
                L.append(f"Lin's CCC: {_f(cc['ccc'])} [{_f(cc['ci_low'])}, {_f(cc['ci_high'])}]"
                         f" (precision r={_f(cc['pearson_r'])}, accuracy "
                         f"C_b={_f(cc['accuracy_cb'])}).")
        fc = r.get("floor_ceiling", {})
        if "error" not in fc:
            L += ["", "### Floor / ceiling (first session)", "",
                  f"Floor {100 * fc['prop_floor']:.1f}% at {_f(fc['floor_value'])}"
                  f"{' ⚑' if fc['floor_flag'] else ''}; ceiling "
                  f"{100 * fc['prop_ceiling']:.1f}% at {_f(fc['ceiling_value'])}"
                  f"{' ⚑' if fc['ceiling_flag'] else ''} (flag > 15%)."]
            L += _warn_lines(fc)
        ch = r.get("change_over_sessions")
        if ch and "error" not in ch:
            L += ["", "### Change over sessions (linear mixed model)", "",
                  f"`{ch['formula']}`, random {ch['random_effects']}; n = {ch['n_subjects']} "
                  f"subjects, {ch['n_observations']} observations; variance-component ICC "
                  f"{_f(ch['icc'])}.", "", "| term | estimate | 95% CI | p |",
                  "|---|---|---|---|"]
            for fe in ch["fixed_effects"]:
                L.append(f"| {fe['term']} | {_f(fe['estimate'])} | [{_f(fe['ci_low'])}, "
                         f"{_f(fe['ci_high'])}] | {_p(fe['p'])} |")
            L += _warn_lines(ch)
        kg = r.get("known_groups")
        if kg:
            L += ["", f"### Known groups (session {kg['session']})", "",
                  "| comparison | mean diff | Welch p | Hedges g [95% CI] | AUC [95% CI] |",
                  "|---|---|---|---|---|"]
            for c in kg["comparisons"]:
                if "error" in c:
                    L.append(f"| {c['group_a']} vs {c['group_b']} | failed: {c['error']} ||||")
                    continue
                g, a = c["hedges_g"], c["auc"]
                L.append(f"| {c['group_a']} vs {c['group_b']} | "
                         f"{_f(c['welch_t']['mean_diff'])} | {_p(c['welch_t']['p'])} | "
                         f"{_f(g['g'])} [{_f(g['ci_low'])}, {_f(g['ci_high'])}] | "
                         f"{_f(a['auc'])} [{_f(a['ci_low'])}, {_f(a['ci_high'])}] |")
        iv = r.get("invariance_reliability")
        if iv and "error" not in iv:
            L += ["", f"### Reliability across groups ({iv['form']})", ""]
            for g, v in iv["per_group"].items():
                L.append(f"- {g}: {_f(v['icc'])} [{_f(v['ci_low'])}, {_f(v['ci_high'])}], "
                         f"n={v['n_subjects_used']}")
            for c in iv["comparisons"]:
                eq = "" if c["equivalent"] is None else \
                    f"; equivalent within ±{c['margin']}: {c['equivalent']}"
                L.append(f"- {c['group_a']} − {c['group_b']}: {_f(c['icc_diff'])} "
                         f"[{_f(c['ci_low'])}, {_f(c['ci_high'])}] (bootstrap){eq}")
        tt = r.get("invariance_means_tost")
        if tt and "error" not in tt:
            L += ["", f"TOST of means: diff {_f(tt['diff'])}, margin ±{_f(tt['high'])}, "
                      f"p={_p(tt['p'])}, equivalent: {tt['equivalent']}."]
        cth = r.get("change_thresholds", {})
        if cth:
            L += ["", "### Change thresholds (" + cth["label"] + ")", ""]
            for k, v in cth["estimates"].items():
                L.append(f"- {k}: {_f(v['value'])}")
        L.append("")
    if "multiplicity" in report:
        m = report["multiplicity"]
        L += ["## Multiplicity (known-groups tests)", "",
              "| score | comparison | p | Holm p | BH p |", "|---|---|---|---|---|"]
        for t, h, b in zip(m["tests"], m["holm"]["p_adjusted"],
                           m["benjamini_hochberg"]["p_adjusted"]):
            L.append(f"| {t['score']} | {t['comparison']} | {_p(t['p'])} | {_p(h)} | {_p(b)} |")
        L.append("")
    L += ["## Notes", "", "**Internal consistency:** " + report["internal_consistency"]["reason"],
          "", "**Measurement invariance scope:** " + report["invariance_scope"], "",
          "**MCID:** " + report["mcid_note"], ""]
    return "\n".join(L)
