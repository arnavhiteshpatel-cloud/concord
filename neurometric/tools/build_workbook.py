"""Build the NeuroMetric workbook (deliverables/NeuroMetric_workbook.xlsx).

Sheets: README, Experiments, Benchmark_* (results), Competitors, Prospects, Funding,
Collaborators, Instruments, Datasets, Trials, Platforms, Evidence_Ledger, Financial_Model
(driver-based, live formulas). Re-run after experiments: python tools/build_workbook.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd
from openpyxl import Workbook
from openpyxl.comments import Comment
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

ROOT = Path(__file__).resolve().parents[1]
RES = ROOT / "experiments" / "results"
RS = ROOT / "docs" / "research"
OUT = ROOT / "deliverables" / "NeuroMetric_workbook.xlsx"
FONT = "Arial"
HEAD = PatternFill("solid", start_color="DCE6F1")
INPUT_BLUE = Font(name=FONT, color="0000FF", size=9)
BLACK = Font(name=FONT, size=9)
BOLD = Font(name=FONT, size=9, bold=True)
KEY = PatternFill("solid", start_color="FFFF00")


def write_df(wb, name, df: pd.DataFrame, note: str = "", maxw=60):
    ws = wb.create_sheet(name[:31])
    r0 = 1
    if note:
        ws.cell(1, 1, note).font = Font(name=FONT, size=9, italic=True)
        r0 = 3
    for j, c in enumerate(df.columns, 1):
        cell = ws.cell(r0, j, str(c))
        cell.font = BOLD
        cell.fill = HEAD
        cell.alignment = Alignment(wrap_text=True, vertical="top")
    for i, row in enumerate(df.itertuples(index=False), r0 + 1):
        for j, v in enumerate(row, 1):
            if isinstance(v, float) and pd.isna(v):
                v = None
            elif not isinstance(v, (int, float, str, type(None), bool)):
                v = str(v)
            cell = ws.cell(i, j, v)
            cell.font = BLACK
            cell.alignment = Alignment(wrap_text=isinstance(v, str) and len(v) > 40, vertical="top")
            if isinstance(v, float):
                cell.number_format = "0.000"
    for j, c in enumerate(df.columns, 1):
        lens = [len(str(c))] + [len(str(x)) for x in df.iloc[:200, j - 1]]
        ws.column_dimensions[get_column_letter(j)].width = min(max(10, max(lens) * 0.9), maxw)
    ws.freeze_panes = ws.cell(r0 + 1, 1)
    return ws


def read_csv(p):
    try:
        return pd.read_csv(p)
    except Exception:
        return pd.DataFrame({"note": [f"could not read {p.name}"]})


def financial_sheet(wb):
    """Driver-based model with live formulas. Blue = inputs (hypotheses), black = formulas."""
    ws = wb.create_sheet("Financial_Model")
    ws["A1"] = "NeuroMetric driver-based model — ALL INPUTS ARE HYPOTHESES [HYP] until tested with customers"
    ws["A1"].font = BOLD
    ws["A2"] = "Edit blue cells (yellow = key assumptions). Formulas recalculate. Sources: docs/research/comparable_pricing.md, founder Playbook B, docs/commercial/."
    ws["A2"].font = Font(name=FONT, size=9, italic=True)
    years = ["2027", "2028", "2029", "2030", "2031"]
    ws["A4"] = "Driver"
    for j, y in enumerate(years, 2):
        ws.cell(4, j, y).font = BOLD
        ws.cell(4, j).fill = HEAD
    ws["A4"].font = BOLD
    ws["A4"].fill = HEAD
    ws.cell(4, 8, "Source / note").font = BOLD
    inputs = [
        ("iBCI / BCI sponsor studies (count)", [0, 1, 2, 3, 4], "≈3 active US motor/communication iBCI sponsors now, 5–8 plausible by 2028 [V/INF]; competitors.md"),
        ("Avg contract per sponsor study-year ($)", [60000, 120000, 150000, 175000, 200000], "Playbook $100–400K [HYP]; comparables suggest lower for 2–15 participant studies"),
        ("Neuromod / rehab maker contracts (count)", [0, 1, 2, 4, 6], "Tier-1 prospects: ONWARD, Kandu, Bioness, Mobia, Cognixion [V]; prospects.md"),
        ("Avg maker contract per year ($)", [50000, 100000, 125000, 150000, 175000], "Playbook $100–300K/yr [HYP]"),
        ("Academic / AT program licences (count)", [1, 3, 6, 10, 14], "academic iBCI programs, AT clinics [INF]"),
        ("Avg academic licence ($/yr)", [10000, 15000, 20000, 25000, 25000], "OpenClinica ~$36–45K/yr/study as ceiling [V]; comparable_pricing.md"),
        ("Grant revenue ($)", [150000, 400000, 700000, 600000, 300000], "NIH STTR Phase I/II (NINDS caps $700k/$3.0M) [V], timing uncertain"),
        ("Delivery cost as % of contract revenue", [0.55, 0.45, 0.40, 0.35, 0.32], "deployment, support, psychometrics [HYP]"),
        ("Headcount (FTE)", [2, 4, 7, 10, 13], "[HYP]"),
        ("Loaded cost per FTE ($)", [90000, 120000, 135000, 145000, 150000], "[HYP]"),
        ("Hosting, security, QA/validation ($)", [20000, 60000, 110000, 150000, 180000], "Part 11 CSV, SOC 2 readiness, E&O/cyber insurance [HYP]"),
        ("Other opex ($)", [30000, 60000, 90000, 120000, 150000], "[HYP]"),
    ]
    r = 5
    rowof = {}
    for label, vals, src in inputs:
        ws.cell(r, 1, label).font = BLACK
        for j, v in enumerate(vals, 2):
            c = ws.cell(r, j, v)
            c.font = INPUT_BLUE
            c.number_format = "0.0%" if isinstance(v, float) and v < 1 else ("$#,##0" if "$" in label else "0")
            if "Avg contract" in label or "maker contracts (count)" in label or "studies (count)" in label:
                c.fill = KEY
        ws.cell(r, 8, src).font = Font(name=FONT, size=8, italic=True)
        rowof[label] = r
        r += 1
    r += 1
    calc = [
        ("Sponsor revenue ($)", "={c}{a}*{c}{b}", ("iBCI / BCI sponsor studies (count)", "Avg contract per sponsor study-year ($)")),
        ("Maker revenue ($)", "={c}{a}*{c}{b}", ("Neuromod / rehab maker contracts (count)", "Avg maker contract per year ($)")),
        ("Academic revenue ($)", "={c}{a}*{c}{b}", ("Academic / AT program licences (count)", "Avg academic licence ($/yr)")),
    ]
    for label, f, (a, b) in calc:
        ws.cell(r, 1, label).font = BLACK
        for j in range(2, 7):
            c = get_column_letter(j)
            cell = ws.cell(r, j, f.format(c=c, a=rowof[a], b=rowof[b]))
            cell.number_format = "$#,##0;($#,##0);-"
            cell.font = BLACK
        rowof[label] = r
        r += 1

    def row_formula(label, expr, fmt="$#,##0;($#,##0);-", bold=False):
        nonlocal r
        ws.cell(r, 1, label).font = BOLD if bold else BLACK
        for j in range(2, 7):
            c = get_column_letter(j)
            cell = ws.cell(r, j, expr(c))
            cell.number_format = fmt
            cell.font = BOLD if bold else BLACK
        rowof[label] = r
        r += 1

    row_formula("Contract revenue ($)", lambda c: f"={c}{rowof['Sponsor revenue ($)']}+{c}{rowof['Maker revenue ($)']}+{c}{rowof['Academic revenue ($)']}", bold=True)
    row_formula("Total revenue incl. grants ($)", lambda c: f"={c}{rowof['Contract revenue ($)']}+{c}{rowof['Grant revenue ($)']}", bold=True)
    row_formula("Delivery cost ($)", lambda c: f"={c}{rowof['Contract revenue ($)']}*{c}{rowof['Delivery cost as % of contract revenue']}")
    row_formula("Gross margin on contracts", lambda c: f"=IF({c}{rowof['Contract revenue ($)']}=0,0,1-{c}{rowof['Delivery cost ($)']}/{c}{rowof['Contract revenue ($)']})", fmt="0.0%")
    row_formula("People cost ($)", lambda c: f"={c}{rowof['Headcount (FTE)']}*{c}{rowof['Loaded cost per FTE ($)']}")
    row_formula("Total costs ($)", lambda c: f"={c}{rowof['Delivery cost ($)']}+{c}{rowof['People cost ($)']}+{c}{rowof['Hosting, security, QA/validation ($)']}+{c}{rowof['Other opex ($)']}")
    row_formula("Net income ($)", lambda c: f"={c}{rowof['Total revenue incl. grants ($)']}-{c}{rowof['Total costs ($)']}", bold=True)
    ws.cell(r, 1, "Cumulative net income ($) (negative = funding need)").font = BOLD
    for j in range(2, 7):
        c = get_column_letter(j)
        prev = f"+{get_column_letter(j - 1)}{r}" if j > 2 else ""
        cell = ws.cell(r, j, f"={c}{rowof['Net income ($)']}" if j == 2 else f"={get_column_letter(j-1)}{r}+{c}{rowof['Net income ($)']}")
        cell.number_format = "$#,##0;($#,##0);-"
        cell.font = BOLD
    r += 2
    ws.cell(r, 1, "Notes: counts are customers (organisations), never patients. Revenue double counting is avoided by "
                  "treating each sponsor study-year as one contract. No line is a forecast; it is a structure for testing "
                  "hypotheses with customer interviews (decision rules E1–E9, docs/commercial/CUSTOMER_DISCOVERY_PLAN.md).").font = Font(name=FONT, size=8, italic=True)
    ws.column_dimensions["A"].width = 44
    for j in range(2, 7):
        ws.column_dimensions[get_column_letter(j)].width = 14
    ws.column_dimensions["H"].width = 80
    ws.freeze_panes = "B5"


def main():
    OUT.parent.mkdir(parents=True, exist_ok=True)
    wb = Workbook()
    ws = wb.active
    ws.title = "README"
    lines = [
        "NeuroMetric workbook — generated by tools/build_workbook.py",
        "All experiment results are SIMULATION results (virtual participants, simulated input degradation) unless the sheet says 'real data' (X1: public macaque cursor data).",
        "Research sheets carry evidence labels: [V] verified, [CC] company claim, [RF] research finding, [AE] analyst estimate, [INF] inference, [HYP] hypothesis, [PK] prior knowledge, [UNR] unresolved.",
        "Prices, market sizes and financial inputs are hypotheses until tested with customers.",
        "Sheets: Experiments; Bench_* (benchmark results); Competitors; Prospects; Funding; Collaborators; Instruments; Datasets; Trials; Platforms; Evidence_Ledger; Financial_Model.",
    ]
    for i, l in enumerate(lines, 1):
        ws.cell(i, 1, l).font = BOLD if i == 1 else BLACK
    ws.column_dimensions["A"].width = 160
    # experiments index
    rows = []
    for d in sorted(RES.glob("*")):
        sj = d / "summary.json"
        if sj.exists():
            s = json.loads(sj.read_text())
            rows.append({"experiment": d.name, "synthetic": s.get("synthetic", True),
                         "design": s.get("design", s.get("x", "")), "generated_utc": s.get("generated_utc", ""),
                         "files": ", ".join(sorted(p.name for p in d.iterdir()))})
    write_df(wb, "Experiments", pd.DataFrame(rows), "Index of executed experiments (experiments/results/<id>/summary.json)")
    bench = [("Bench_metric_ranking", RES / "G_metric_comparison" / "ranking.csv", "Experiment G: per-metric sensitivity, monotonicity, floor/ceiling, retest ICC across all sweeps (simulation)"),
             ("Bench_all_properties", RES / "G_metric_comparison" / "all_properties.csv", "Properties of every metric in every degradation sweep (simulation)"),
             ("Bench_reliability", RES / "I_test_retest" / "reliability.csv", "Experiment I: test-retest ICC vs test length (simulation)"),
             ("Bench_responsiveness", RES / "K_responsiveness" / "responsiveness.csv", "Experiment K (simulation)"),
             ("Bench_modalities", RES / "L_cross_modality" / "means.csv", "Experiment L: mean scores by simulated modality"),
             ("Bench_variance", RES / "M_user_variability" / "variance_decomposition.csv", "Experiment M"),
             ("Bench_missing", RES / "N_missing_data" / "results.csv", "Experiment N"),
             ("Bench_adaptive", RES / "H_adaptive" / "comparison.csv", "Experiment H"),
             ("Bench_stat_verification", next(iter(sorted((RES / "R_statistical_verification").glob("*.csv"))), RES / "none.csv"), "Experiment R"),
             ("Bench_real_data_X1", RES / "X1_external_mc_rtt" / "throughput_by_distance.csv", "X1 REAL public data (macaque hand cursor, NLB MC_RTT)"),
             ("Bench_python_perf", RES / "S_event_latency" / "python_pipeline.csv", "Experiment S (server side)")]
    for name, p, note in bench:
        if p.exists():
            write_df(wb, name, read_csv(p), note)
    research = [("Competitors", "competitors.csv"), ("Prospects", "prospects.csv"), ("Funding", "funding.csv"),
                ("Collaborators", "collaborators.csv"), ("Instruments", "instruments.csv"),
                ("Datasets", "datasets.csv"), ("Trials", "trials.csv"), ("Platforms", "platform_matrix.csv"),
                ("Evidence_Ledger", "ledger_regulatory.csv")]
    for name, f in research:
        p = RS / f
        if p.exists():
            write_df(wb, name, read_csv(p), f"Source: docs/research/{f} (labels per CONVENTIONS.md; accessed 2026-11-27)")
    financial_sheet(wb)
    wb.save(OUT)
    print(OUT)


if __name__ == "__main__":
    main()
