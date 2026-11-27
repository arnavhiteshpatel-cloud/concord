"""Render the comprehensive founder report: docs/report/NeuroMetric_Report.md -> deliverables/NeuroMetric_Report.pdf"""
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from neurometric.reports.pdf import render_markdown_pdf  # noqa: E402

src = ROOT / "docs" / "report" / "NeuroMetric_Report.md"
out = ROOT / "deliverables" / "NeuroMetric_Report.pdf"
md = src.read_text()
render_markdown_pdf(md, out, base_dir=src.parent, title="NeuroMetric — founder report",
                    footer="NeuroMetric founder report, 27 Nov 2026 — simulation results are not clinical evidence; nothing here is a regulatory submission",
                    cover={"kicker": "PROJECT NEUROMETRIC · FOUNDER REPORT · 27 NOVEMBER 2026",
                           "title": "Input-agnostic functional outcome measurement and real-world evidence infrastructure for neural interfaces",
                           "subtitle": "What was built, what the computational research shows, what remains unvalidated, and the path to the first human study, customers and funding",
                           "lines": ["Prepared autonomously for the founder. Evidence labels: [V] verified, [CC] company claim, [RF] research finding, [AE] analyst estimate, [INF] inference, [HYP] hypothesis, [PK] prior knowledge, [UNR] unresolved.",
                                     "All experimental results are from simulation (virtual participants) except X1 (public macaque hand-cursor data). No human-subject data were collected. Nothing was submitted, sent or published."]})
print(out)
