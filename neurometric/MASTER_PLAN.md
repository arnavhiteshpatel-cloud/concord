# NeuroMetric — MASTER PLAN

**Mission.** Determine whether neural interfaces and assistive technologies produce meaningful
improvements in people's lives, by building neutral measurement and evidence infrastructure that
connects device performance → functional capability → everyday independence → care burden and
participation → clinical and economic evidence.

**What NeuroMetric is not:** a decoder, a device controller, a neural acquisition SDK, a validated
clinical outcome assessment (yet), or a regulatory submission.

## Phases (status as of this session — see EXECUTION_STATE.md)

| # | Workstream | Deliverable | Status |
|---|---|---|---|
| 1 | Scientific, regulatory & competitive investigation | docs/research/* (regulatory, trials, measures, instruments, datasets, competitors, prospects, platforms, funding, collaborators) | done (web-search budget exhausted; [UNR] items listed) |
| 2 | Concord inspection | docs/research/concord_reuse_audit.md; importer `adapters/concord.py` | done |
| 3 | Input abstraction | `events/model.py`, adapters (simulated, replay, Concord, browser), conformance tests | done (browser adapters in web/) |
| 4 | Task battery | `tasks/battery.py` (A1–F7 specs + seeded stimuli), web implementation | done (v1 experimental) |
| 5 | Task scoring | `metrics/` + analytic fixtures | done |
| 6 | Decoder simulator | `simulator/decoder.py`, engine, scanning | done |
| 7 | Virtual participants | `users/models.py`, populations | done |
| 8 | Large-scale experiments | `experiments/registry.py` (B–N, P, G, H, I, K, L, M), X1 real data | done; regenerated after independent review (see EXPERIMENT_REGISTRY.md) |
| 9 | Psychometrics | `psychometrics/` + verification (Exp R) | done |
| 10 | Accessibility | web app, axe tests, docs/accessibility | done (automated only) |
| 11 | Privacy-preserving telemetry | `study/` telemetry with allowlist, consent gating | done (app-scoped) |
| 12–13 | Study management, questionnaires | `study/`, `instruments/`, API | done |
| 14 | Measurement chain | `chain/` | done (analysis infrastructure; no real data) |
| 15–16 | Sponsor portal, reports | web portal, `reports/` | done |
| 17 | Cross-platform adapters | platform matrix, contracts | partial — browser only tested |
| 18–19 | Clinical validation & quality systems | CLINICAL_VALIDATION_PLAN.md, docs/clinical, docs/irb, docs/quality | drafts |
| 20 | Neuromodulation module | `study/` therapy-session + adherence records | done (records only; no device control) |
| 21 | Security & adversarial review | docs/security, docs/review | done |
| 22–26 | Collaborators, prospects, funding, publications, investor materials | docs/commercial, docs/grants, docs/manuscripts | drafts |
| 27 | Integration & handoff | FOUNDER_HANDOFF.md, PDF report, workbook | done |

## Entry niche (current best hypothesis, see COMMERCIALIZATION.md)
Neutral, input-agnostic **home-use evidence of digital independence** for communication and
computer-access devices: (1) a periodic home version of a digital-function battery, (2)
consented aggregate real-world-use logging, (3) care-partner assistance capture, (4) a
Part 11-oriented evidence package. First buyers: smaller implant sponsors, non-invasive BCI and
AAC makers, home neuro-rehab makers (ONWARD, Kandu/IpsiHand, Bioness/PoNS, Mobia/Vivistim,
Cognixion), academic iBCI programs. iBCI-only is too concentrated to be a standalone business.

## Gates (from playbook, kept)
* 30 days: SRAlab DAI conversation (open or not); CUC membership known; ≥10 discovery calls.
* 90 days (25 Feb 2027): ≥2 sponsors/makers say they'd pay, or SRAlab scopes a collaboration;
  IRB pilot under way via a faculty PI; LOI or paid pilot ($25–75K [HYP]).
