# FOUNDER HANDOFF — NeuroMetric

Prepared 2026-11-27 at the end of the first autonomous build session. Read this first, then
`EXPERIMENT_REGISTRY.md` (results), `EVIDENCE_LEDGER.md` (what is verified),
`COMMERCIALIZATION.md`, `CLINICAL_VALIDATION_PLAN.md`, and `docs/founder/KNOWLEDGE_BASE.md`.

**Bottom line.** The software, the computational research and the preparation for human studies,
funding and customer discovery are built. Clinical evidence, partnerships, licences, approvals and
revenue do not exist and cannot be created without you. Nothing has been sent, submitted,
published or released.

---

## 1. What was built

| Area | Where | State |
|---|---|---|
| Canonical input events + conformance suite | `src/neurometric/events`, `tests/test_events_adapters.py` | working, tested |
| Input adapters | browser (mouse, pen, touch, keyboard, switch scanning, dwell, gamepad, OS-pointer gaze/head/BCI) in `web/src/input`; simulated, replay, Concord-recording importer in `src/neurometric/adapters` | browser adapters tested in headless Chromium with synthetic input only |
| Task battery v1 (17 tasks, A1–F7) | spec `src/neurometric/tasks/battery.py`, docs `docs/science/TASK_BATTERY.md`, web implementation `web/src/tasks` | experimental; original tasks (not the SRAlab DAI) |
| Metrics engine | `src/neurometric/metrics` (+ TS subset with golden-fixture parity in `web/src/metrics`) | analytic tests; independent review fixes applied |
| Simulated decoder harness + virtual users | `src/neurometric/simulator`, `src/neurometric/users` | closed-loop; calibrated to broad published ranges; limitations in `docs/science/SIMULATOR.md` |
| Computational experiments (A–S, X1) | `src/neurometric/experiments`, results in `experiments/results/` | executed; see EXPERIMENT_REGISTRY.md |
| Psychometrics engine | `src/neurometric/psychometrics` | verified vs Shrout & Fleiss, pingouin, coverage simulation |
| Study management, consent, audit, telemetry, questionnaires, exports, API | `src/neurometric/study`, `instruments`, `api` | 142 tests; demo seeding; not Part 11 validated |
| Sponsor portal | `portal/` (served at `/portal`) | see portal/README.md |
| Participant battery + live degradation demo | `web/` (served at `/`) | see web README and docs/accessibility |
| Measurement chain + independence model | `src/neurometric/chain` | experimental; verified on synthetic data only |
| Neuromodulation companion (records + adherence) | `src/neurometric/neuromod` | records only; refuses stimulation parameters |
| Evidence reports (7 types, PDF + JSON) | `src/neurometric/reports`; demo in `deliverables/demo_reports/` | synthetic demo only |
| Health economics (scenarios with guardrails) + financial model | `src/neurometric/economics`, `docs/commercial/` | hypotheses |
| Platform probes (Windows/macOS/Android) | `platform_agents/` | **untested source sketches** |
| Company website | `site/` | static, axe-clean; contact e-mail is a TODO |
| Research dossiers | `docs/research/` (regulatory, trials, measures, instruments + licensing, datasets, competitors, prospects, neuromodulation, platforms, BCI HID, timing, funding, collaborators, Concord audit) | web-search budget ran out; [UNR] items listed |
| Clinical validation + IRB drafts | `CLINICAL_VALIDATION_PLAN.md`, `docs/clinical/`, `docs/irb/` | drafts, not submitted |
| Grants + manuscripts | `docs/grants/`, `docs/manuscripts/` | drafts, not submitted |
| Quality + security | `docs/quality/`, `docs/security/`, `docs/review/` | technical foundations; no compliance claims |

### How to run (macOS, Linux)
```
cd neurometric
python3 -m venv .venv && source .venv/bin/activate
pip install -e '.[dev]'
python -m pytest                                 # Python suite
python -m neurometric.api seed-demo --db nm.sqlite   # SYNTHETIC demo study (prints logins)
python -m neurometric.api serve --db nm.sqlite        # battery at /, portal at /portal
cd web && npm install && npm run build && npm test     # web app + parity tests
neurometric report demo deliverables/demo_reports      # 7 synthetic evidence reports
python -m neurometric.experiments.registry             # all simulation experiments (~1-2 h, 4 cores)
python tools/build_workbook.py && python tools/build_report.py
```

## 2. What genuinely works vs. what is unvalidated

**Works (verified in this environment):** event validation/ordering; Concord import; simulator
parameters vs analytic expectations; metric formulas vs analytic fixtures; psychometric
statistics vs published examples and pingouin; reproducibility (bit-identical results across
process counts); API permissions, tenant isolation, consent withdrawal, audit-chain tamper
detection, telemetry allowlist and integrity rules; report generation; automated accessibility
scans (axe) of the web app, portal and website; Python dependency audit clean.

**Unvalidated:** every task and score in humans; any psychometric property in humans; the
simulator as a model of any real BCI; all input hardware (no switch, eye tracker, head pointer or
BCI was connected); Windows/macOS/Android telemetry; Part 11/GCP qualification; HIPAA/state
neural-data-law applicability; all prices, market sizes and willingness to pay; whether SRAlab,
the iBCI-CC, any sponsor or any maker wants this.

**Input adapters tested:** browser Pointer Events (synthetic mouse moves via Playwright and
dispatched events), keyboard/switch scanning (synthetic key events), dwell, simulated and replayed
streams, Concord recordings (3 genuine synthetic recordings generated with Concord). No physical
assistive device or BCI.

## 3. Scientific findings (simulation — not human evidence)
See EXPERIMENT_REGISTRY.md for numbers, figures and limitations. Headlines are summarised there
and in `deliverables/NeuroMetric_Report.pdf`.

## 4. Commercial verdict
* The implanted-BCI sponsor market alone is too concentrated for a standalone business (3 active
  US motor/communication iBCI sponsors now, ~5–8 by 2028; Neuralink builds in-house; Synchron
  paused enrollment Nov 2026).
* Most specific defensible entry niche (hypothesis): **neutral, input-agnostic home-use evidence
  of digital independence** — periodic home battery + consented aggregate use logging +
  care-partner assistance capture + Part 11-oriented evidence packaging — sold first to
  non-invasive BCI/AAC makers and home neuro-rehab makers with public evidence gaps (Cognixion,
  Kandu/IpsiHand, ONWARD, Bioness/PoNS, Mobia/Vivistim), then smaller implant sponsors, with
  STTR-funded academic validation.
* **Most threatening:** SRAlab DAI (with Neuralink) — same digital primitives, psychometric
  validation planned; sponsor in-house systems; Mount Sinai Digital IADL / iBCI-CC endpoint work;
  Signant (+Ametris/ActiGraph) and Thermo Fisher (Clario + Evidera) at platform level.
* No financial scenario reaches operating break-even by 2031 at hypothesised prices; grants and
  a lean team are essential. Commercial credibility is **plausible but unproven**; the 90-day
  gate decides.

## 5. Collaborators who matter most
1. SRAlab DAI team (PI Arun Jayaraman per registry) — partner, not rival (docs/clinical/SRALAB_APPROACH.md).
2. Yuan Yang (Illinois–Carle JNERL) — faculty PI candidate for IRB and STTR.
3. iBCI-CC Clinical Study Endpoints workgroup (co-leads Mariska Vansteensel, Vivek Pinto).
4. Mount Sinai Digital IADL team (David Putrino, Abbey Sawyer, Adam Fry).
5. Melanie Fried-Oken (OHSU, BCI/AAC). 6. DRES and Carle Illinois. 7. Catherine Lang (WashU).
8. Leigh Hochberg (BrainGate). Details and drafts: docs/research/collaborators.md, docs/commercial/OUTREACH_DRAFTS.md.

## 6. What you need to learn (priority)
Psychometrics (ICC, SEM/MDC, COSMIN, responsiveness, anchor-based MCID) → FDA iBCI guidance + COA
+ DHT guidance + Part 11 → Fitts/text-entry evaluation → AT/AAC clinical practice → IRB/GCP →
customer discovery. 12-week plan: docs/founder/LEARNING_GUIDE.md.

## 7. Devices to acquire (Stage 1–2 only)
USB switch interface + 2 switches; one eye tracker (check gaze-data licensing); free head-pointer
software (Apple Head Pointer / Camera Mouse); a mouth joystick if borrowable; a Windows laptop and
an Android tablet for the telemetry spike; a photodiode + microcontroller latency bench. Do not
buy an EEG headset for the evidence product. Details: docs/founder/EQUIPMENT.md.

## 8. Approvals needed
* A **faculty PI** (UIUC RP-19: student employees may not be PI) and UIUC OPRS IRB approval before
  any human data; CITI training; COI management plan (you would study your own product).
* Instrument licences before using ZBI, PROMIS/Neuro-QoL (commercial), QUEST, PIADS, COPM, ALSAQ…
* Landuyt IP Clinic + OTM disclosure before incorporation, open-sourcing or publication
  (Concord is "Proprietary (internal preview)").
* Regulatory counsel on device status (FD&C 520(o)) before marketing claims.

## 9. First participant study — how
1. Recruit the faculty PI (Yuan Yang first). 2. Adapt docs/irb drafts to OPRS forms; submit
Stage 1 (42 able-bodied, 4 sessions incl. familiarisation). 3. Pre-register the SAP
(docs/clinical/sap_stage1_3.md; hash-lock it). 4. Buy the Stage 1–2 devices; run the latency bench.
5. Run Stage 1, then Stage 2 (24, four modalities, Latin square), then Stage 3 test–retest (≥3
sessions — two sessions cannot pass the reliability rule). 6. Stage 4 with AT users via Carle/DRES.

## 10. How to approach SRAlab
Use the NCT07407725 registry contact only. Offer implementation, home extension, AT-input
validation and the simulation harness — not a rival index. Ask about licensing, roadmap, home use
and whether an implementation partner exists (playbook E1). Draft: docs/clinical/SRALAB_APPROACH.md.

## 11. How to approach BCI manufacturers
Lead with a research call, not a pitch (docs/research/interview_guides.md). Target clinical,
regulatory and market-access leads at Paradromics, Precision, Cognixion, Synchron (hold until
enrollment resumes), and the neuromod makers. Use playbook E2/E8 rules (≥2 LOIs in 90 days).

## 12. Grants
NIH STTR PA-27-102 (due 5 Jan / 5 Apr 2027) with a UIUC/Carle faculty PI; NIDILRR SBIR
(~Dec 2027); DoD ALSRP clinical outcomes award (watch FY27); Illinois DCEO match; Cozad (needs a
Carle Illinois medical student for healthcare prizes); Illinois I-Corps (due 5 Feb 2027). SBIR/STTR
reauthorized to 2031 (P.L. 119-83). Drafts: docs/grants/.

## 13. Establishing a legitimate company
IP Clinic → OTM disclosure → decide licence for Concord-derived concepts → incorporate (Delaware C
or Illinois LLC per advice) → founder IP assignment → separate company accounts/repo
(`git subtree split -P neurometric`) → E&O/cyber insurance before any pilot → Part 11 validation
package and SOC 2 readiness before sponsor-grade use.

## 14. Remaining actions (prioritised)
### Requires you
1. Read FDA iBCI guidance, iBCI-CC consensus, NCT07407725 record (playbook week-1 list).
2. Landuyt advising + IP Clinic booking; OTM disclosure.
3. Email SRAlab, Yuan Yang, iBCI-CC (drafts ready; review and personalise).
4. 15–20 discovery interviews (guides ready) → decide by the 25 Feb 2027 gate.
5. Faculty PI → IRB Stage 1 submission; CITI training.
6. Acquire Stage 1–2 devices; run the latency bench; run the battery on yourself and 2 friends
   (playbook E4 sanity check — not research data).
7. Licensing inquiries (instruments.md pack).
8. Replace the website contact e-mail; decide whether/when to publish anything.
9. Cozad team (Carle Illinois medical student); I-Corps application.
10. Re-verify [UNR]/[PK] items in the evidence ledger (state neural-data laws, IEEE P2731/P2794).
### Can still be done computationally
1. Unit tests for the untested simulator parameters (smoothing, quantization, LOC/recovery…).
2. Realistic demo trajectories in the seeded demo study (currently straight lines, labelled).
3. Wobbrock–Myers input-stream alignment for corrected errors.
4. Server-side scoring for B/C/D/F tasks beyond completion/time.
5. MFA/SSO, key rotation, external audit-chain anchoring.
6. Larger simulation grids (e.g., interaction of latency × noise), and calibration of the
   simulator against BCI datasets with cursor kinematics if licences allow.
7. Re-run `site/build_results.py`, the workbook and the report after any new experiment.
