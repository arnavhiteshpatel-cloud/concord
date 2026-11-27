# NeuroMetric

**Input-agnostic functional outcome measurement and real-world evidence infrastructure for
brain-computer interfaces, assistive technology and neurorehabilitation devices.**

> Research software. Not a medical device. It never decodes neural signals, controls a device or
> changes stimulation. Not validated as a clinical outcome assessment. No Part 11, HIPAA or SOC 2
> compliance is claimed. All experimental results here are simulations unless labelled real data.

Start with **[FOUNDER_HANDOFF.md](FOUNDER_HANDOFF.md)** and the report
**[deliverables/NeuroMetric_Report.pdf](deliverables/NeuroMetric_Report.pdf)**.

## Quick start
```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e '.[dev]'
python -m pytest                                        # Python test suite
python -m neurometric.api seed-demo --db nm.sqlite      # SYNTHETIC demo study; prints logins
(cd web && npm install && npm run build)                # participant battery + live demo
python -m neurometric.api serve --db nm.sqlite          # battery at /, sponsor portal at /portal
```
Other entry points: `neurometric --help` (battery export, scoring, Concord import, experiments,
demo reports), `python -m neurometric.experiments.registry` (computational study),
`python tools/build_workbook.py`, `python tools/build_registry.py`, `python tools/build_report.py`,
`python -m http.server -d site` (website).

## Map
| Path | What |
|---|---|
| `src/neurometric/events` | canonical input events, validation, ordering |
| `src/neurometric/adapters` | simulated/replay/Concord adapters; telemetry probe contract |
| `src/neurometric/tasks` | task battery v1 specs + seeded stimuli |
| `src/neurometric/metrics` | pointing, text-entry, tracking, session metrics |
| `src/neurometric/simulator`, `users` | decoder-degradation harness, virtual users, scanning |
| `src/neurometric/experiments` | experiment framework, registry, analyses |
| `src/neurometric/psychometrics` | reliability, agreement, validity, responsiveness, mixed models |
| `src/neurometric/study`, `instruments`, `api` | study management, consent, audit, telemetry, questionnaires, exports, REST API |
| `src/neurometric/chain`, `neuromod`, `economics`, `reports` | measurement chain, adherence records, scenarios, evidence reports |
| `web/`, `portal/`, `site/` | participant battery & demo, sponsor portal, company website |
| `platform_agents/` | untested Windows/macOS/Android usage-probe sketches |
| `experiments/results/` | all experiment outputs (CSV, JSON, figures) |
| `docs/` | research, science, clinical, IRB, grants, manuscripts, commercial, founder, quality, security, review |
| top-level `*.md` | plan, state, decisions, blockers, evidence ledger, experiment registry, governance, validation plan, commercialization, handoff |

## Repository note
NeuroMetric lives in `neurometric/` of the Concord repository on branch
`claude/neurometric-platform-vvzijh` (DECISIONS D-001). Extract with
`git subtree split -P neurometric -b neurometric-main`. Licence: proprietary pending the founder's
IP decision (see FOUNDER_HANDOFF §13).
