# Protocol paper (draft outline): staged validation of an input-agnostic digital function battery in able-bodied adults and assistive-technology users

> **PROTOCOL DRAFT — NO RESULTS. Not submitted; no IRB approval; no participants; no site or PI
> agreement.** Prepared 2026-11-27 from `CLINICAL_VALIDATION_PLAN.md`, `docs/clinical/` and
> `docs/science/PSYCHOMETRICS.md`. A protocol paper should be submitted only after IRB approval
> and OSF registration, with the faculty PI as corresponding author. Placeholders: `[PI]`,
> `[SITE]`, `[IRB #]`, `[OSF DOI]`, `[FUNDER]`. Reporting frame: COSMIN study-design checklist for
> measurement-property studies (Mokkink et al. 2020, 10.1186/s12874-020-01179-5 [V-DOI]); SPIRIT
> items used where relevant to an observational measurement protocol [PK].

---

## Title options
1. "Reliability, validity and home-use feasibility of an input-agnostic digital function battery for
   people using brain-computer interfaces and assistive technology: protocol for a staged
   measurement study"
2. Shorter: "The NeuroMetric validation programme: study protocol"

## Structured abstract (≈ 300 words; protocol only)
- **Introduction.** Gap: no validated, input-agnostic performance outcome for digital function of
  BCI and AT users; FDA iBCI guidance and the iBCI-CC consensus [V].
- **Methods and analysis.** Five stages (below). Primary scores P1–P4. Confirmatory hypotheses
  H2.1, H3.1, H4.1–H4.3 with pre-registered decision rules; GCI for ICC(A,1).
- **Ethics and dissemination.** `[IRB #]`; consent adaptations for limited speech/hand function;
  controlled-access data sharing; open analysis code.
- **Registration.** `[OSF DOI]`; ClinicalTrials.gov for Stage 4 if registered.

## Strengths and limitations (BMJ Open-style bullets)
- Pre-registered, staged design separating practice, fatigue, modality and occasion variance.
- Inferential intervals chosen from a verified simulation study (GCI for ICC(A,1)).
- Founder COI managed by an independent PI, data custody at the university and SAP locking.
- Small AT cohorts (≈ 15 per diagnosis) limit precision of correlations and per-diagnosis ICCs.
- Able-bodied emulation in Stage 2 does not represent experienced AT users.
- No implanted-BCI users in Stages 1–5; no MCID will be estimated unless anchor criteria are met.

## 1. Introduction
1.1 Clinical and regulatory context (FDA 2021 iBCI guidance; DHT guidance; MDDT; iBCI-CC 2026;
Dohle et al. 2025) — cite `NIH_STTR_PHASE1.md` §2 sources.
1.2 Existing measures and their limits (ITR, BPS, Fitts throughput, typing rate, Digital IADL,
SRAlab DAI) — complementary positioning.
1.3 The NeuroMetric battery v1.0.0 (18 original tasks; core battery A1, A2, A4, C1, D1, E1 ×3, F2,
F3, F5) and the event model; not an implementation of any licensed instrument.
1.4 What simulation was used for (design choices only), with citation to the computational
papers P1/P2 once published; simulation is not evidence of measurement properties in people.
1.5 Objectives (one per stage).

## 2. Methods and analysis
### 2.1 Design overview (table)
| Stage | Question | Population | n enrolled (completers) | Primary rule | Confirmatory |
|---|---|---|---|---|---|
| 1 | Instrument mechanics, feasibility, floor/ceiling, timing, order/fatigue | Able-bodied adults | 42 (≥ 40) | Valid-trial Wilson lower bound ≥ 0.90; median Fitts R² ≥ 0.80 | No |
| 2 | Modality ordering and offsets | Able-bodied adults, 4 modalities | 24 | Five Holm-adjusted one-sided contrasts on log P2 | Yes (H2.1) |
| 3 | Test–retest reliability and measurement error | Able-bodied adults, mouse | 60 (50) | ICC(A,1) decision rule (see §2.8) for P1–P4 | Yes (H3.1) |
| 4 | Reliability, known groups, convergent/divergent validity, floor; responsiveness sub-study | Adults with ALS, SCI or stroke using AT | 45 (36) | KG2 AUC ≥ 0.70 (lower bound > 0.50); ≥ 75% hypotheses; ≤ 15% floor | Yes (H4.1–H4.3) |
| 5 | Home-use feasibility with aggregate telemetry and care-partner diary | 5 AT-user/care-partner dyads | 5 (≥ 4) | F1–F7 | No |
Source: `CLINICAL_VALIDATION_PLAN.md` §1.

### 2.2 Setting and timeline
`[SITE]`; lab and home sessions; indicative timeline from PI agreement (plan §9).

### 2.3 Participants and eligibility (per stage; plan §3–7)
Include the consent pathway for limited speech or hand function (AAC, eye gaze, partner-assisted
scanning; teach-back ≥ 4/5; witness signature; no LAR consent) (plan §6.4).

### 2.4 The instrument
Task specifications (`docs/science/TASK_BATTERY.md`); metric definitions (`docs/science/METRICS.md`);
primary scores P1 effective throughput (A2), P2 achieved bitrate (A4), P3 CCPM (E1, 3 phrases), P4
dADL time index (F2, F3, F5; assisted/incomplete = cap); secondary scores; accessibility profiles;
timing configuration and bench validation (`docs/research/browser_timing.md`); version locking
(battery v1.0.0; stimulus seeds by session).

### 2.5 Procedures
Session flow per stage; fatigue and rest rules (≥ 5 min per 15 min for AT users; stop at NRS ≥ 7 or
rise ≥ 3); safety (autonomic dysreflexia, respiratory fatigue, eye/neck strain); assistance
recording (ASSIST events; assisted ≠ failed); Williams designs (Stage 1 task families 6 × 6; Stage 2
modalities ABDC, BCAD, CDBA, DACB); fixed time of day ± 2 h; same device and administrator.

### 2.6 Comparator measures and licences
NASA-TLX, SUS, IRF-PAI Section GG self-care (free); PROMIS/Neuro-QoL, QUEST 2.0, PIADS (licences
required; hypotheses dropped before lock if not licensed); original unvalidated items labelled as
such (fatigue NRS, assistance diary, global rating of change) (`docs/research/instruments.md`).

### 2.7 Sample size (show the calculations)
- Stage 1: 42 = 7 per Williams sequence; Wilson CI example (38/40 → 0.835–0.986).
- Stage 2: n = 24; one-sided paired power at α = 0.01: 0.91 (d_z = 0.8), 0.67 (0.6).
- Stage 3: Walter–Eliasziw–Donner and Bonett precision formulas, plus a Monte-Carlo with the
  project's `psychometrics.icc` including session variance (plan §5 table); 50 completers, k = 3.
- Stage 4: KG2 power 0.71–0.86 depending on group split and d; correlation precision at n = 36
  (r = 0.5: 95% CI ≈ 0.21–0.71); reliability Monte-Carlo.
- Stage 5: feasibility only (4/5: Wilson 95% CI ≈ 0.38–0.96).
All values from `CLINICAL_VALIDATION_PLAN.md` §3–7 (design calculations, not results).

### 2.8 Statistical analysis
- Reliability: ICC(A,1) two-way random, absolute agreement, single measure, with a **generalized
  confidence interval** as the inferential interval; McGraw–Wong interval and ICC(C,1) reported.
  Justification: in verified simulations the McGraw–Wong interval covered 78.0–92.9% of true values
  when sessions differed systematically, the GCI 94.85–96.05%
  (`experiments/results/R_statistical_verification/coverage_results.json`). **Open item before
  lock:** the plan currently uses the McGraw–Wong lower bound ≥ 0.75 as the H3.1 rule; the grant
  draft proposes point ≥ 0.75 with GCI lower bound ≥ 0.60. The PI and statistician choose one rule
  and simulate its false-pass rate and power before the SAP lock.
- Measurement error: SEM from variance components; MDC95; Bland–Altman on log scale with
  proportional bias.
- Construct validity: known groups (Welch, Hedges g, AUC with DeLong CI); convergent/divergent
  (Pearson/Spearman with Fisher-z CIs) against the locked hypothesis table; Holm in the
  confirmatory family; COSMIN ≥ 75% rule.
- Floor/ceiling: > 15% at bound or cap.
- Responsiveness (exploratory): SRM, Guyatt RI, AUC of change, anchor correlations; MIC only if
  anchor correlation ≥ 0.30 and ≥ 30 changed participants; MDC labelled "distribution-based
  estimate, not an MCID".
- Mixed models for practice, fatigue, modality and occasion (plan §2.1 model).
- Missing data: complete-case primary for ICC; REML and MI (m = 50) sensitivity; delta-adjusted
  tipping-point analysis for MNAR.
- Software: Python (NeuroMetric psychometrics, statsmodels) with cross-checks in R (lme4) [INF];
  code frozen at a git commit recorded in the SAP.

### 2.9 Data management
Pseudonymous IDs; no audio, video, gaze coordinates or text content; university hosting;
controlled-access sharing (ICPSR or equivalent); see `docs/grants/DATA_MANAGEMENT_AND_SHARING_PLAN.md`.

### 2.10 Patient and public involvement
Lived-experience advisory input on task accessibility and burden (e.g. through a disability
resources service or a user advocacy group) — **only if such people agree**; describe the role
honestly (advisory, outside the research protocol) [to be completed].

## 3. Ethics and dissemination
IRB `[IRB #]`; COI management (independent PI; founder excluded from consent and confirmatory
analysis; no company publication veto); OSF registration of each stage's SAP with SHA-256;
dissemination plan (open-access papers, data and code release, plain-language summaries for
participants).

## 4. Discussion (protocol-level)
Anticipated challenges: recruitment of switch-scanning users; practice effects; floor effects in
severe impairment (pre-specified adaptive variant); licences; generalisability (English-speaking
adults at one or two sites).

## 5. What this protocol will not show
Clinical benefit of any device; an MCID; equivalence with the SRAlab DAI or any licensed
instrument; diagnostic accuracy; causal effects; generalisation beyond the sites (plan §10).

## 6. Target journals [PK requirements]
*BMJ Open* (protocols accepted; requires registration and ethics approval before submission
[PK]); *JMIR Research Protocols* (often accepts protocols with peer-reviewed funding [PK]); *Journal of
NeuroEngineering and Rehabilitation* (study protocols [PK]). See `VENUES.md`.
