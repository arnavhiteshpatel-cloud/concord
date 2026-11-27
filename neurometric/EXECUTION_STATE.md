# EXECUTION STATE (resume file)

Last updated: 2026-11-27 (session in progress). Branch: `claude/neurometric-platform-vvzijh`.

## How to resume
1. `cd neurometric && pip install -e '.[dev]'`
2. `python -m pytest` (fast suite; `-m slow` for coverage studies)
3. Experiments: `python -m neurometric.experiments.registry` (all) or with IDs; log in
   `experiments/logs/`; results in `experiments/results/<ID>/`.
4. Rebuild deliverables: `python tools/build_workbook.py`, `python tools/build_report.py`,
   `neurometric report demo deliverables/demo_reports`.

## Workstream status (end of session 1)
All workstreams below are complete for what can be done without participants, hardware,
partners or funding. See FOUNDER_HANDOFF.md §14 for remaining actions.

| Workstream | State |
|---|---|
| Research dossiers, Concord audit | complete ([UNR] items listed in EVIDENCE_LEDGER) |
| Core library (events, adapters, tasks, metrics, simulator, users, chain, neuromod, reports, CLI) | complete, tested |
| Psychometrics + Exp R | complete |
| Study platform / API / telemetry / questionnaires / quality & security docs | complete (technical; not validated) |
| Web battery + demo + accessibility (Exp A, Q, S-browser) | complete (automated testing only) |
| Sponsor portal | see portal/README.md |
| Website | complete (contact e-mail TODO) |
| Computational study (B–N, P, G, H, I, K, L, M, X1, O, S) | complete; regenerated after independent review |
| Clinical validation plan, SAPs, IRB drafts | drafts, not submitted |
| Commercialization, economics, outreach, interview guides | drafts, nothing sent |
| Grants, manuscripts | drafts, not submitted |
| Founder knowledge base | complete |
| Final report (PDF), workbook, handoff | complete |
