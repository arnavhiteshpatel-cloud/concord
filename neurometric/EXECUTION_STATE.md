# EXECUTION STATE (resume file)

Last updated: 2026-11-27 (session in progress). Branch: `claude/neurometric-platform-vvzijh`.

## How to resume
1. `cd neurometric && pip install -e '.[dev]'`
2. `python -m pytest` (fast suite; `-m slow` for coverage studies)
3. Experiments: `python -m neurometric.experiments.registry` (all) or with IDs; log in
   `experiments/logs/`; results in `experiments/results/<ID>/`.
4. Rebuild deliverables: `python tools/build_workbook.py`, `python tools/build_report.py`,
   `neurometric report demo deliverables/demo_reports`.

## Workstream status
| Workstream | Owner (agent / main) | State |
|---|---|---|
| Research dossiers (7) | agents | complete |
| Core: events, simulator, users, tasks, metrics, adapters, chain, neuromod, reports, CLI | main | complete, tested |
| Psychometrics + Exp R | agent | complete (50 tests + slow coverage study) |
| Study management / API / telemetry / questionnaires / quality docs | agent | in progress |
| Web battery, demo, accessibility, Exp A/Q/S-browser | agent | in progress |
| Clinical validation + IRB package | agent | in progress |
| Commercialization + economics + outreach | agent | in progress |
| Founder knowledge base | agent | in progress |
| Website | agent | in progress |
| Grants + manuscripts | agent | in progress |
| Adversarial review (science core) | agent | in progress |
| Full simulation study | background process | running |
| Sponsor portal UI, final integration, PDF report, handoff | main | pending |
