# NIH STTR Phase I: research plan draft

**Development and initial validation of an input-agnostic digital functional outcome assessment
system for brain-computer interfaces and assistive technologies**

> **DRAFT. Not submitted. Not reviewed by any faculty member, institution or program officer.**
> Prepared 2026-11-27 for the NeuroMetric founder and a prospective faculty PD/PI.
>
> - NeuroMetric is not yet incorporated. No partner research institution, PD/PI, clinical site,
>   collaborator or sponsor has agreed to anything. Every name below is a **candidate**. The
>   brackets `[PARTNER RI]`, `[PD/PI]` and `[CLINICAL SITE]` mark text the real team must
>   supply.
> - There are **no human data**. Every NeuroMetric result cited here is either a **computational
>   preliminary study** (simulated virtual users and simulated input degradation, labelled
>   *synthetic* in every output file) or the analysis of **one public, non-human dataset** (the
>   macaque hand-controlled cursor dataset NLB MC_RTT, DANDI:000129). Neither is clinical
>   evidence, and neither is called "preliminary data" in the NIH sense.
> - Each number is followed by the file it comes from. `[RESULT PENDING: …]` marks a result that
>   the running simulation study had not written when this draft was finished.
> - Evidence labels follow `docs/research/CONVENTIONS.md`: [V] verified from a primary source on
>   2026-11-27, [RF] peer-reviewed, [CC] company claim, [AE] third-party, [INF] inference,
>   [HYP] hypothesis, [PK] prior knowledge not re-verified, [UNR] unresolved.

---

## 0. Application frame

| Item | Proposal | Source / status |
|---|---|---|
| Notice of funding opportunity | **PA-27-102**, NIH omnibus STTR (Phase I) | [V] `docs/research/funding.md` §1–2 |
| Remaining standard due dates | **5 Jan 2027** and **5 Apr 2027**; the NOFO expires 6 Apr 2027 | [V] funding.md §1. 5 Jan 2027 is not realistic: the company does not exist and registrations take ≥ 6 weeks [V warning, INF conclusion]. **Target 5 Apr 2027**; fallback is the reissued NOFO's September 2027 date [UNR number/date] |
| Preferred awarding IC | **NINDS** (Phase I up to $700k; Phase II up to $3.0M) | [V] funding.md §1 (NOFO budget table) |
| Alternative ICs | NICHD/NCMRR ($400k / $2.5M); NIDCD ($400k / $3.0M); NIBIB (SBA guideline) | [V] funding.md §1 |
| Applicant | NeuroMetric, Inc. (to be incorporated) | Not yet incorporated |
| Partnering research institution (≥ 30% of work) | `[PARTNER RI]`; candidate: University of Illinois Urbana-Champaign (UIUC), with Carle Foundation Hospital for clinical recruitment | Candidate only; no contact made (`docs/research/collaborators.md`) |
| PD/PI | `[PD/PI]`, a faculty member of the partner RI. Under NIH STTR the PD/PI may be employed by the research institution if they have a formal appointment with or commitment to the small business, with ≥ 10% effort | [V] funding.md §3.1. Candidate named in collaborators.md: Yuan Yang (UIUC Bioengineering / Carle Illinois / JNERL). **Not contacted.** |
| Student founder's role | Key personnel (technical lead, software); not PD/PI, not IRB PI, does not obtain consent or run confirmatory analyses | UIUC RP-19 [V] (`CLINICAL_VALIDATION_PLAN.md` §0); `STTR_STRUCTURE.md` |
| Project period | 24 months (Phase I normally up to 1 year for STTR; NIH accepts up to 2 years with justification [PK, confirm in PA-27-102 §II]) | `BUDGET.md` |
| Total costs requested | ≈ $700k cap for NINDS; a reduced $400k version is defined for NICHD/NIDCD | `BUDGET.md` |
| Clinical trial status | Expected **not** an NIH-defined clinical trial: the studies validate a measurement instrument and do not test an intervention's effect on a health-related outcome [INF]. Confirm with the NIH four-question tool and the program officer; check whether PA-27-102 is "clinical trial optional" [UNR] | §5.6 |
| Page limits | Specific Aims 1 page; Phase I Research Strategy 6 pages [PK, confirm in the current SF424 instructions]. This draft is longer and must be cut; the extra material moves to the Human Subjects and Resource Sharing attachments | — |

---

## 1. Specific Aims (target: 1 page)

People with paralysis from ALS, spinal cord injury (SCI) or stroke use brain-computer
interfaces (BCIs), eye-gaze trackers, head pointers and switches to operate computers, to
communicate and to carry out daily digital activities. Whether a new device actually improves
what they can do, and how independently, is hard to show. FDA's iBCI guidance asks pivotal
studies for a validated effectiveness endpoint with a minimal clinically important difference,
for home-use data and for measures of the caregiver's ability to assist [V, FDA 2021 guidance,
`docs/research/regulatory_landscape.md` §1]. No BCI clinical outcome assessment has been
qualified through FDA's MDDT program [V]. A 2025 systematic review found that only 17.9% of
implanted-BCI studies (20 of 112) assessed clinical outcomes [V/RF, Dohle et al. 2025]. In
October 2026 the iBCI Collaborative Community concluded that a single existing measure is
unlikely to be sufficient and called for a "shared measurement chain" from device performance to
function to health outcome or care burden [V]. Today's performance metrics (information transfer
rate, grid "bits per second", typing rate) are device- and task-specific, capture peak rather
than typical performance, and have not been validated against function.

**NeuroMetric** is research software that measures digital function the same way whatever the
input. Any input (BCI cursor or click, eye gaze, head pointer, switch scanning, mouse) is
recorded as one canonical, hashed event stream. An 18-task battery (pointing, steering,
scrolling, dragging, text entry, phrase selection and seven simulated digital activities of
daily living) is scored from those events alone. Assistance from care partners is recorded as
events, not treated as failure, and home use is summarised as consented aggregate counts. In
**computational preliminary studies** we built a closed-loop simulated-decoder harness with
virtual users. In a 52,920-trial noise sweep, effective throughput, achieved bitrate and
correct characters per minute fell monotonically as decoder noise rose (Spearman ρ −0.89,
−0.90 and −0.92), while a digital-ADL completion score sat at ceiling in 90.7% of
virtual-participant sessions (`experiments/results/B_noise/summary.json`). We also verified our
psychometric library against published examples and 86 known-truth simulations
(`experiments/results/R_statistical_verification/coverage_results.json`). One finding changed
our design: the usual McGraw–Wong interval for absolute-agreement ICCs covered the truth in only
78.0–92.9% of simulated studies when sessions differ systematically, while a generalized
confidence interval kept 94.85–96.05% coverage.

The **objective** of this Phase I is to establish the technical performance, test–retest
reliability and initial construct validity of a short core battery, in able-bodied adults and in
assistive-technology (AT) users, and the feasibility of home use with care-partner assistance
capture. The **central hypothesis** is that a 20–25-minute input-agnostic core battery yields
scores that are reliable across days, separate groups that should differ, and can be collected
at home at acceptable burden.

**Aim 1. Technical validation of the battery and measurement harness, and able-bodied
reliability.** (1a) Bench-validate end-to-end timing for each input class and verify scoring
parity between the browser and the reference pipeline. (1b) Confirm the battery's mechanics,
speed–accuracy structure and floor/ceiling in 42 adults (single visit). (1c) Show that scores
order four input modalities as expected (24 adults, Williams crossover). (1d) Estimate
reliability and measurement error over three test sessions after familiarisation in 50
completers. *Go criterion:* ICC(A,1) ≥ 0.75 with a generalized-CI lower bound ≥ 0.60 for at
least 3 of the 4 primary scores.

**Aim 2. Reliability, known-groups and convergent validity in AT users.** In 45 adults with ALS,
SCI or stroke who use their own AT, test pre-registered known-groups hypotheses (direct-selection
vs switch-scanning users; AUC ≥ 0.70), ≥ 75% of pre-registered convergent/divergent hypotheses,
floor effects (≤ 15% at floor per cohort) and test–retest reliability with the participant's own
device.

**Aim 3. Home-use feasibility and care-partner assistance capture.** In 5 AT-user/care-partner
dyads over 14 days, test whether the home battery, aggregate telemetry and a 2-minute daily
assistance diary yield usable data (≥ 4 of 5 dyads; ≥ 80% of participant-days) with acceptable
burden and **zero** accepted payloads containing disallowed content.

**Expected outcomes.** A version-locked core battery with published reliability, measurement
error and initial validity across input modalities; a verified, open analysis pipeline; and a
feasibility-tested home protocol. These are the prerequisites for Phase II: multi-site validation
in neural-interface users, anchor-based meaningful-change estimates, a Part 11-ready evidence
package, and exploration of FDA MDDT qualification.

---

## 2. Significance

### 2.1 The measurement gap is recognised by regulators, payers and the field
- **Regulatory expectation.** The 2021 FDA guidance on implanted BCIs asks sponsors to describe
  how the primary effectiveness endpoint was validated and its minimal clinically important
  difference (MCID), to study devices "in realistic, home use environments", and to assess
  "caregiver safety and their ability to assist the user (i.e., time, attention and physical
  ability)". It also allows feasibility studies to validate metrics rather than requiring
  validated endpoints a priori [V] (`regulatory_landscape.md` §1). The caregiver language is about
  safety and ability to assist, not burden as a benefit outcome [V, correction recorded in
  `EVIDENCE_LEDGER.md` row 4].
- **No qualified tool.** No BCI clinical outcome assessment (COA) is qualified under MDDT [V].
  FDA's Digital Health Technology guidance (Dec 2023) requires verification and validation of
  a data-collection technology "regardless of whether the DHT meets the definition of a device"
  [V] (`regulatory_landscape.md` §3).
- **The field's own consensus.** The iBCI-CC consensus statement (1 Oct 2026) says a single
  existing measure is unlikely to suffice, asks for a shared measurement chain respecting distinct
  FDA and CMS standards, and names care-partner burden, functional communication and
  participation as key outcomes "particularly for payor decision-making" [V]
  (`published_bci_functional_measures.md` §5.2). The 2026 *J Neural Eng* workshop report
  (Sawyer et al., DOI 10.1088/1741-2552/ae9eee) names "the lack of widely validated and
  fit-for-purpose COAs" and home measurement as open challenges [V].
- **Under-reporting of function.** Dohle et al. (2025) reviewed 112 implanted-BCI studies:
  decoding and task performance were reported prospectively in 69.6% and 62.5%, clinical outcomes
  in 17.9%, communication speed in 16.1% and ITR in 8% [V/RF].
- **Payers.** Coverage decisions depend on improved health outcomes and real-world use, which
  device-performance metrics do not show [V/INF] (`regulatory_landscape.md` §7, §9).

### 2.2 Existing measures do not travel across inputs or into the home
| Measure family | Strength | Limitation for this problem | Source |
|---|---|---|---|
| Wolpaw ITR; achieved bitrate; Neuralink webgrid BPS | Simple throughput summaries | ITR assumptions (equiprobable targets, uniform errors, fixed trial time) rarely hold; BPS is a 60-s peak score with a grid- and click-type-dependent formula; no clinical validation, no MCID | `methods_references.md` §C; `published_bci_functional_measures.md` §3 |
| Fitts throughput (ISO 9241-411) | Device-independent pointing metric with a canonical recipe | Pointing only; undefined for scanning; lab task | Soukoreff & MacKenzie 2004 [PK formula; V-DOI] |
| Typing rate (WPM/CCPM) | Communication-relevant | Protocol-dependent (copy vs free, language model, correction time) | `published_bci_functional_measures.md` §3.6 |
| Digital IADL scale (Sawyer et al. 2025) | Patient-derived content (9 domains, 37 items) | Content-validity stage only; no reliability or responsiveness yet | [V/RF] §4.1 |
| SRAlab Digital Assessment Interface (NCT07407725) | Closest effort: click, scroll, type, drag within simulated dADLs + NASA-TLX, SUS, modified COPM, PIADS; 60 participants; Neuralink collaborator | In development; clinic-based; no home-logging outcome in the registry | [V] `clinical_trials.md` §1 |
| Home-use hours (Utrecht; Cognixion NCT07871071 primary) | Behavioural, real-world | Exposure, not function; context-dependent; no MCID | [V] §3.8 |

**Our position.** NeuroMetric is complementary to, not a rival of, the SRAlab DAI and the Digital
IADL scale. It contributes three things none of them provides today: (1) one event model and
scoring pipeline for *any* input, so the same score can be computed for a BCI user, an eye-gaze
user and a switch user; (2) explicit capture of assistance, so independence is not inferred
from device activity; and (3) privacy-bounded home measurement. The battery's tasks are
original; they are not an implementation of the DAI or any licensed instrument
(`docs/science/TASK_BATTERY.md`).

### 2.3 Why now
Only three companies run active US motor/communication implant studies [V], and about 5–8 are
plausible by 2028 [INF] (`EVIDENCE_LEDGER.md` §B). A neutral, validated, input-agnostic
measurement system is needed **before** pivotal studies lock their endpoints. The same tool is
useful immediately for the much larger non-invasive BCI, AAC and AT population, which is where
Phase I validation happens.

### 2.4 Commercial significance (summary)
See §8 and `COMMERCIALIZATION.md`. The recommended entry niche is neutral home-use evidence of
digital independence for communication and computer-access devices [INF]; an iBCI-only business
is judged not viable because the sponsor universe is too small [INF/HYP].

---

## 3. Innovation

1. **Input-agnostic canonical event model with observable-only scoring.** Every metric is
   computed from events a real deployment can record; simulation ground truth (intended
   selections, injected false activations) is kept separately and used only to validate metrics
   (`DECISIONS.md` D-006). Events are stored verbatim with SHA-256 hashes; stimuli are generated
   once from seeds and are byte-identical in browser and simulator (D-004).
2. **A closed-loop simulated-decoder harness for measurement science.** Virtual users perceive
   the *degraded* cursor after a feedback delay and correct for it (D-005; feedback-control
   framing after Willett et al. 2017, *J Neural Eng* 14:016001 [V-DOI]). Thirteen degradation
   parameters (noise, latency, dropout, drift, gain, bias, false and missed selections, update
   rate and others) are each unit-tested against analytic expectations
   (`docs/science/SIMULATOR.md`). This lets us ask, before any human study, which metrics are
   sensitive to which failure mode, where they saturate, and how many trials they need. We know
   of no published outcome-measure framework for BCIs that does this [INF; literature search
   incomplete, see P1 manuscript].
3. **Assistance as data.** Assistance events (setup, physical, verbal, troubleshooting,
   calibration, task completion) by participant, care partner or staff are first-class events;
   "assisted ≠ failed" (`docs/science/METRICS.md` §4; `INDEPENDENCE_AND_CHAIN.md`).
4. **Verified psychometrics with honest intervals.** A psychometric library verified against
   published worked examples, independent implementations and 86 known-truth Monte-Carlo
   scenarios (all pass), which reproduced and fixed the under-coverage of the standard
   absolute-agreement ICC interval (§4.2.5).
5. **Privacy by construction for home measurement.** An allowlist validator accepts only
   aggregate counts and minutes; content-like keys and values are rejected and only a receipt is
   kept (`src/neurometric/study/telemetry.py`; DECISIONS D-008).

---

## 4. Approach

### 4.1 Overview and team roles
| Work package | Lead organisation | Aims |
|---|---|---|
| Software, harness, bench timing, analysis code, simulation, data pipeline, home agent | NeuroMetric (small business) | 1a, 3 (software) |
| Human-subjects recruitment, consent, data collection, independent confirmatory analysis, data custody | `[PARTNER RI]` under the `[PD/PI]` | 1b–1d, 2, 3 |
| Clinical recruitment and AT-clinic advice | `[CLINICAL SITE]` (candidate: Carle; Carle research route [V] in `CLINICAL_VALIDATION_PLAN.md` §2.10) | 2, 3 |

The founder does not obtain consent, does not hold the randomisation list and does not run
confirmatory analyses (COI plan, `CLINICAL_VALIDATION_PLAN.md` §0). Work split and IP:
`STTR_STRUCTURE.md`.

### 4.2 Computational preliminary studies

All studies in this section are **synthetic** (simulation) except §4.2.6 (public macaque data)
and §4.2.7 (software performance on a synthetic session). They show how the measurement system
behaves under controlled, modelled conditions. **They do not show reliability, validity or
benefit in humans** (`docs/science/SIMULATOR.md`, "Known limitations").

#### 4.2.1 Harness and virtual users
- **Degradation model.** `DegradationConfig` applies gain and gain decay, directional bias,
  asymmetry, white and AR(1)-correlated noise, noise growth, constant and growing drift,
  smoothing, quantisation, sample-and-hold update rate, latency with exponential jitter,
  two-state Markov dropout, loss-of-control episodes, and a selection channel with misses,
  delay and Poisson false activations. Each parameter has an analytic unit test
  (`tests/test_simulator.py`).
- **Virtual users.** A velocity-control feedback user (proportional control on the perceived
  error, speed limit, signal-dependent and constant motor noise, reaction delay, settle-to-click
  rule), a position-control submovement user (minimum-jerk submovements, Flash & Hogan 1985;
  stochastic optimised submovements, Meyer et al. 1988), a dwell gaze user, and row-column /
  linear switch-scanning users (`users/models.py`, `simulator/scanning.py`). Populations share
  one latent ability z ~ N(0, 1) that scales speed and noise, plus log-normal idiosyncratic
  variation.
- **Calibration targets** (ranges, not individuals): `bci_good` ≈ 1.2 bit/s ISO throughput and
  ≈ 2.4 bit/s grid achieved bitrate; mouse-like ≈ 4.1 bit/s; dwell-gaze-like ≈ 2.3 bit/s
  (`docs/science/SIMULATOR.md`; ranges [PK]).
- **Simulated battery per virtual session** (used in all sweeps): ISO ring at two D × W
  conditions (256/48 and 512/96 px, 13 targets each), a 12-trial 4 × 6 grid, one copy-typing
  phrase, the F2 compose-message digital ADL, and 15 s of tracking
  (`src/neurometric/experiments/core.py`). Each virtual participant is run twice per condition
  with independent seeds (simulated test–retest). Seeds are derived by hashing the experiment,
  condition and replicate, so any condition can be re-run alone.

#### 4.2.2 Study B: sensitivity of each metric to injected decoder noise
Design: 60 virtual participants × 7 noise levels (0–6 × a base of 30 px/s white plus 40 px/s
AR(1) noise on the `bci_good` profile) × 2 replicates; 52,920 simulated trials
(`experiments/results/B_noise/summary.json`). For each metric, scores are oriented so that
higher is better; sensitivity is Spearman ρ between score and degradation level (negative =
appropriate), plus monotonicity of level means, paired effect size at the first degraded level,
and floor/ceiling fractions (`src/neurometric/experiments/analysis.py`).

| Metric | Spearman ρ with noise | Monotone fraction of adjacent steps | Floor / ceiling (pooled) | Median simulated retest ICC(A,1) across levels |
|---|---|---|---|---|
| Effective Fitts throughput (A2) | −0.892 | 1.00 | — | 0.571 |
| Movement variability (A2) | −0.985 | 1.00 | — | 0.795 |
| Grid achieved bitrate (A4) | −0.901 | 1.00 | floor 5.5% | 0.666 |
| Correct characters per minute (E1) | −0.917 | 1.00 | floor 0% | 0.763 |
| Digital-ADL time (F2) | −0.843 | 1.00 | — | 0.434 |
| Digital-ADL completion (F2) | −0.459 | 1.00 | **ceiling 90.7%** | 0.115 |
| Grid accuracy (A4) | −0.843 | 0.83 | **ceiling 58.6%** | 0.098 |
| Selection-process onset (A2) | +0.102 | 0.33 | — | 0.883 |
| Tracking lag (B2) | −0.008 | 0.50 | — | 0.761 |

Source for every value: `experiments/results/B_noise/summary.json` (fields `properties` and
`median_retest_icc_by_metric`). Figure: `experiments/results/B_noise/sweep.png` (16 metrics,
mean ± 95% CI over virtual participants).

Interpretation (bounded by the simulation's assumptions):
- Kinematic and rate metrics (throughput, movement variability, achieved bitrate, CCPM) track
  noise monotonically and are candidates for **degradation-sensitive** scores.
- Process outcomes that matter to users (did the digital activity get done?) are
  **ceiling-prone**: ADL completion stayed at ceiling in 90.7% of sessions. Completion alone
  would hide moderate device degradation; time-to-complete and assistance must accompany it.
  This is the rationale for the P4 time index (§4.3.4).
- Onset and tracking lag did not respond to noise (ρ = +0.102 and −0.008). They are not
  noise-sensitive by construction; whether they respond to latency is tested in Study C
  [RESULT PENDING: experiments/results/C_latency/summary.json — Spearman ρ of track_lag_ms and iso_onset_ms with added latency].
- The simulated retest ICCs depend entirely on the assumed between-person spread (latent ability
  SD 0.25). They show which metrics are *structurally* unreliable (e.g. bounded proportions at
  ceiling: grid accuracy median 0.098, ADL completion 0.115), not what reliability humans will
  show.

#### 4.2.3 Studies C–F, B2–B4: other degradation types; Study G: metric comparison
Same design, one degradation at a time: added latency (0–700 ms) for velocity-control (C) and
position-control (C2) users; dropout episodes (D); calibration drift (E); false selections (F);
missed selections (F2); directional bias (B2); decoder update interval (B3); decoder gain
(B4, non-monotone by design). Study G ranks each metric by mean sensitivity across sweeps, its
worst-case sensitivity, floor/ceiling and simulated retest ICC
(`src/neurometric/experiments/registry.py`).

- Latency: [RESULT PENDING: experiments/results/C_latency/summary.json — Spearman ρ of iso_tp_bps, grid_bitrate_bps, type_ccpm and track_lag_ms with latency].
- False activations: [RESULT PENDING: experiments/results/F_false_activation/summary.json — Spearman ρ of false_activations_per_min, grid_bitrate_bps and adl_time_s with false-selection rate].
- Dropout, drift, missed selections, bias, update rate, gain: [RESULT PENDING: experiments/results/{D_dropout,E_drift,F2_missed_selection,B2_bias,B3_update_rate,B4_gain}/summary.json — per-metric Spearman ρ].
- Cross-sweep ranking: [RESULT PENDING: experiments/results/G_metric_comparison/ranking.csv — top metrics by mean_sensitivity and their min_sensitivity, max_ceiling_frac, median_retest_icc]. Figure: [RESULT PENDING: experiments/results/G_metric_comparison/sensitivity_heatmap.png].

#### 4.2.4 Studies I, K, L, M, N, H: reliability vs length, responsiveness, modality, variance, missing data, adaptive difficulty
- **I (test length).** Simulated ICC(A,1) for 4, 8, 16 and 32 trials per task in three simulated
  modalities, compared with the Spearman–Brown prophecy from the shortest length
  [RESULT PENDING: experiments/results/I_test_retest/reliability.csv — ICC(A,1) of iso_tp_bps and grid_bitrate_bps at 4/8/16/32 trials, and the Spearman–Brown prediction].
- **K (responsiveness).** Half of the virtual participants receive a known decoder improvement
  between sessions [RESULT PENDING: experiments/results/K_responsiveness/responsiveness.csv — AUC improved-vs-stable and SRM for the top metrics].
- **L (modalities).** The same battery across eight simulated modalities, including two scanning
  configurations [RESULT PENDING: experiments/results/L_cross_modality/summary.json — modality means for grid_bitrate_bps and type_ccpm; Kendall τ rank concordance].
- **M (person vs device).** A 3 × 3 crossed design of simulated ability × decoder profile
  [RESULT PENDING: experiments/results/M_user_variability/variance_decomposition.csv — η² for device vs ability per metric].
- **N (missing data).** Complete-case bias under MCAR, abandon-after-failure (MNAR) and
  fatigue-like (MAR) trial loss [RESULT PENDING: experiments/results/N_missing_data/results.csv — mt_bias_ms and success_bias at ~25% missing by mechanism].
- **H (adaptive difficulty).** A 2-down/1-up item-size staircase vs fixed 100 px and 40 px grids
  across six noise levels [RESULT PENDING: experiments/results/H_adaptive/comparison.csv — floor/ceiling fractions and mean adjacent-level AUC per design].
- **P (reproducibility).** Bit-identical re-run in-process vs in a process pool
  [RESULT PENDING: experiments/results/P_reproducibility/summary.json — identical flag].

#### 4.2.5 Study R: verification of the statistical implementation
`neurometric.psychometrics` was checked three ways (`docs/science/PSYCHOMETRICS.md` §9):
(a) published worked examples (Shrout & Fleiss 1979 ICC example reproduced to two decimals;
Bland & Altman 1986; naniar `mcar_test(airquality)`; pingouin documentation); (b) independent
implementations (pingouin, scipy, statsmodels); (c) known-truth Monte-Carlo, 2000 replications
per scenario, seed 20261127. **86 of 86 scenarios met the pre-set pass rule**
(`experiments/results/R_statistical_verification/coverage_results.json`, fields `n_rows`,
`n_pass`).

Key finding for this proposal (same file):

| Scenario (n subjects, k sessions, session variance) | McGraw–Wong 95% CI coverage, ICC(A,1) | Generalized CI coverage | Mean width M&W / GCI |
|---|---|---|---|
| n = 20, k = 2, no session effect | 0.950 | 0.961 | 0.671 / 0.689 |
| n = 30, k = 3, session var 0.1 (of 1.0) | 0.929 | 0.958 | 0.386 / 0.590 |
| n = 20, k = 2, session var 0.2 | **0.907** | 0.958 | 0.644 / 0.764 |
| n = 50, k = 3, session var 0.05 | **0.868** | 0.955 | 0.258 / 0.528 |
| n = 200, k = 3, session var 0.05 | **0.780** | 0.950 | 0.234 / 0.510 |
| n = 50, k = 6, session var 0.05 | **0.922** | 0.949 | 0.155 / 0.223 |

The McGraw–Wong interval, which most software reports, under-covers when sessions differ
systematically (practice, fatigue, recalibration), and it gets *worse* as n grows because the
session variance is estimated from k − 1 degrees of freedom. The generalized confidence interval
(GCI; generalized pivotal quantities, Weerahandi 1993 [PK]) kept 0.9485–0.9605 coverage in every
scenario. **Design consequences:** the GCI is our inferential interval for ICC(A,1); we plan
three test sessions after a familiarisation session, because more participants cannot repair
uncertainty about session shifts. Other checks in the same file: the MDC95 false-positive rate
in truly stable simulated people was 0.058 with SEM estimated from 40 subjects (nominal 0.05),
and Little's MCAR test had type-I error 0.047.

#### 4.2.6 Study X1: the pipeline on real public behavioural data (non-human, non-clinical)
To test the event model and scoring on real movement data, we converted the public Neural
Latents Benchmark **MC_RTT** dataset (DANDI:000129, CC-BY-4.0; file SHA-256 verified against
DANDI) into canonical events and scored it. MC_RTT is **one session of a macaque monkey
controlling a cursor with its hand** in a self-paced random-target task; it is not BCI control and
not a clinical population (`docs/research/datasets.md` §1). Results
(`experiments/results/X1_external_mc_rtt/summary.json`):
- 66,639 events; stream integrity checks found 0 non-monotonic timestamps, 0 duplicate sequence
  numbers and 0 gaps;
- 541 reaches; median reach time 1110 ms; median path efficiency 0.866;
- effective-width throughput by distance quintile 1.32, 1.72, 1.97, 2.39 and 2.37 bit/s, mean
  of bins 1.95 bit/s; mean reach time rose with effective index of difficulty from 1046 ms
  (IDe 1.38 bits) to 1345 ms (IDe 3.18 bits)
  (`experiments/results/X1_external_mc_rtt/throughput_by_distance.csv`;
  figure `experiments/results/X1_external_mc_rtt/mc_rtt_metrics.png`).
- Caveats recorded in the file: acquisition time is inferred from target changes and includes
  any hold time; target width is not in the dataset, so only effective-width throughput is
  computed and target re-entries are not computable; data were decimated to 100 Hz.

This shows the pipeline runs end-to-end on real recorded behaviour and yields a Fitts-like
speed–difficulty relation. It says nothing about human or AT-user performance.

#### 4.2.7 Study S: server-side processing cost
On a synthetic 60-trial session of 14,643 events, event validation ran at a median of about
2.14 million events/s, segmentation and scoring took a median 87.5 ms, and every JSON round trip
reproduced an identical hash (`experiments/results/S_event_latency/summary.json`). Browser-side
timing is a separate bench study (Aim 1a).

#### 4.2.8 Study Q: automated accessibility and end-to-end checks of the browser battery
An automated axe-core 4.10.3 scan (WCAG 2.0/2.1/2.2 A and AA rule sets plus best practice) of 58
screens in light and dark themes found **0 violations** and 0 serious or critical issues
(`experiments/results/Q_accessibility/axe_summary.json`). Automated end-to-end runs in headless
Chromium with synthetic input (scripted mouse; keyboard acting as a switch) completed A2, A4 and E1
and reached the task list through single-switch scanning setup; in each run the browser's
provisional scores equalled the reference scores (e.g. A4 achieved bitrate 64.37 bit/s in both)
(`experiments/results/Q_accessibility/e2e_tasks_summary.json`). These synthetic-input values are
not human performance. As the result file states, automated rules find only part of WCAG issues and
the manual protocol with screen readers, switch hardware and eye trackers has **not** been carried
out; it is budgeted in Aim 1a (`BUDGET.md` §3.2).

### 4.3 Aim 1: technical validation of the battery and harness; able-bodied reliability

Corresponds to Stages 1–3 of `CLINICAL_VALIDATION_PLAN.md`; protocols in
`docs/clinical/stage1_protocol.md`, `stage2_protocol.md`, `stage3_protocol.md`; SAP draft
`docs/clinical/sap_stage1_3.md`.

#### 4.3.1 Aim 1a: harness technical validation (no participants)
- **Bench timing.** For each supported input class (mouse, head pointer with dwell, eye-gaze OS
  pointer with dwell, USB switch interface), measure end-to-end lag and its SD from physical
  input to recorded timestamp with a photodiode/actuator rig, on the pinned laptop, OS and
  browser configuration (`docs/research/browser_timing.md` §5). Published browser studies found
  constant lags of tens of milliseconds with SDs up to about 28 ms [RF], so we claim
  within-setup comparisons, not millisecond-accurate absolute times.
- **Scoring parity.** The TypeScript subset of metrics must match the Python reference on golden
  fixtures (DECISIONS D-003); stimulus hashes must be identical in browser and simulator (D-004).
- **Simulated dry run.** The frozen analysis code is run on a simulated dataset before each SAP
  lock; simulated output is never reported as a finding (`CLINICAL_VALIDATION_PLAN.md` §2.9).

#### 4.3.2 Aim 1b: instrument mechanics (Stage 1)
42 able-bodied adults, one visit, full 18-task battery, task-family order by a 6 × 6 Williams
design. Criteria: valid-trial rate with lower 95% Wilson bound ≥ 0.90; Fitts structure (median
per-person R² of MT on IDe ≥ 0.80); floor/ceiling per Terwee et al. (2007) 15% rule; in-session
timing self-check pass rate ≥ 95%; a position-in-battery effect that excludes > 10% slowing per
family position. Outputs: the final core-battery order and the P4 time caps.

#### 4.3.3 Aim 1c: modality ordering (Stage 2)
24 able-bodied adults use mouse (A), camera head pointer with dwell (B), eye-gaze OS pointer with
dwell (C) and single-switch scanning (D) in a Williams crossover over two visits. Confirmatory
hypothesis H2.1: on achieved bitrate, A > B, A > C, A > D, B > D, C > D (five one-sided paired
contrasts on log P2 from a mixed model, Holm-adjusted). Power for one contrast at Holm's
strictest level (α = 0.01) is 0.91 for d_z = 0.8 (computed in `CLINICAL_VALIDATION_PLAN.md` §4).
Limitation stated in every report: able-bodied novices with emulated AT do not represent
experienced AT users.

#### 4.3.4 Aim 1d: reliability and measurement error (Stage 3)
- **Design.** 60 enrolled, 50 completers; S0 familiarisation (not analysed) then S1–S3 at 2–7-day
  intervals, same time of day ± 2 h, same device and administrator where possible; different
  stimulus seeds with identical parameters each session.
- **Primary scores** (`CLINICAL_VALIDATION_PLAN.md` §1.1): P1 effective throughput (A2,
  pointing modalities only); P2 achieved bitrate (A4); P3 correct characters per minute (E1,
  3 phrases); P4 dADL time index, the mean log10 time over F2, F3 and F5 with assisted or
  incomplete trials set to the task cap. P4 uses time rather than completion because completion
  saturated in the computational studies (§4.2.2).
- **Primary analysis.** ICC(A,1) (two-way random, absolute agreement, single measurement) over
  S1–S3 with the **generalized 95% CI** as the inferential interval; the McGraw–Wong interval and
  ICC(C,1) are reported for comparability. SEM from variance components (de Vet et al. 2006),
  MDC95 = 1.96·√2·SEM, Bland–Altman on the log scale with proportional-bias check, a mixed model
  for the session trend (practice), TOST for S1→S3 stability.
- **Go criterion (M2, §4.8).** For at least 3 of P1–P4: ICC(A,1) point estimate ≥ 0.75 **and**
  GCI lower 95% bound ≥ 0.60. Rationale: the GCI is honest but wide (mean width 0.37 at n = 30,
  k = 3, true ICC 0.70 with no session effect; 0.59 with session variance 0.1;
  `experiments/results/R_statistical_verification/coverage_results.json`), so a 0.75 GCI lower
  bound would fail most truly good scores at n = 50. **Before the SAP lock** the PD/PI and
  biostatistician must simulate this rule's false-pass rate (true ICC 0.60) and power (true ICC
  0.85) with `psychometrics.icc`. *Reconciliation note:* `CLINICAL_VALIDATION_PLAN.md` §5
  currently uses the McGraw–Wong lower bound ≥ 0.75 as the decision rule and the GCI as a
  sensitivity analysis; this proposal reverses that ordering because of Study R.

### 4.4 Aim 2: AT-user reliability, known-groups and convergent validity (Stage 4)

Protocol: `docs/clinical/stage4_protocol.md`; plan §6.

- **Participants.** 45 adults (about 15 ALS, 15 cervical/high-thoracic SCI ≥ 12 months
  post-injury, 15 chronic stroke ≥ 6 months) who use AT or adapted access at least weekly (eye
  gaze, head pointer, joystick including mouth joystick, trackball, switch scanning, voice with
  pointer grid, adapted mouse). Personal consent only (no legally authorised representative);
  consent through the participant's usual communication method with teach-back
  (`CLINICAL_VALIDATION_PLAN.md` §6.4). People with implanted BCIs are **not** recruited in
  Phase I.
- **Sessions.** S0 familiarisation with the participant's own AT and settings recorded; S1, S2
  and S3 at 3–7-day intervals in a fixed setting (lab or home). S3 was optional in the clinical
  plan; we make it planned because Study R shows two sessions leave the absolute-agreement
  interval very wide. Participants who miss S3 stay in the analysis through the REML mixed-model
  ICC (`icc_mixed`).
- **H4.1 (confirmatory, known groups).** Direct-selection vs switch-scanning users on P2:
  AUC ≥ 0.70 with DeLong lower 95% bound > 0.50 in the predicted direction. Power at d = 1.0 with
  27 vs 9 users is 0.71; with 24 vs 12 it is 0.79 (plan §6); recruitment targets ≥ 10 scanning
  users. KG1 (AT users vs able-bodied) and KG3 (needs help most days vs independent, using the
  original unvalidated assistance diary) are supportive.
- **H4.2 (confirmatory, construct).** ≥ 75% of the locked convergent/divergent hypotheses
  confirmed (COSMIN criterion [PK]). The hypothesis table (C1–C10) is in plan §6 and includes
  P3 vs P2 (r ≥ 0.60), P4 vs P2 (r ≤ −0.50), P2 vs NASA-TLX (−0.30 to −0.60), and divergent
  predictions against Section GG self-care and age. Hypotheses needing licensed instruments
  (Neuro-QoL/PROMIS, QUEST 2.0, PIADS) are dropped **before** the SAP lock if the licence is not
  granted (`docs/research/instruments.md` §3b).
- **H4.3 (confirmatory, floor).** In each diagnostic cohort ≤ 15% of participants are at the floor
  of P2 and P4. Failure is informative: it triggers the lower-demand adaptive version (§4.9).
- **H4.4 (secondary-confirmatory).** ICC(A,1) with GCI for each applicable primary score, own AT.
- **Exploratory.** Reliability by diagnosis (`compare_icc_across_groups`); responsiveness
  sub-study in consenting ALS participants at 3 and 6 months and in stroke participants before
  and after a partner's rehabilitation programme, with anchor-based change only if the
  anchor–change correlation is ≥ 0.30 (Revicki et al. 2008). **No MCID is computed from
  distributions**; MDC is labelled "distribution-based estimate, not an MCID".

### 4.5 Aim 3: home-use feasibility and care-partner assistance capture (Stage 5)

Protocol: `docs/clinical/HOME_USE_FEASIBILITY.md`, `docs/clinical/stage5_protocol.md`.

- **Participants.** 5 AT-user/care-partner dyads (ALS, SCI or stroke), 14 days. Windows or
  Android for opt-in Tier 1 activity telemetry; other platforms take part with in-battery data
  only (`docs/research/platform_matrix.md`).
- **Collected.** Tier 0 home battery on days 1, 8 and 14; opt-in Tier 1 daily totals (active
  minutes, device-assisted-session flags, counts of pointer/select/scroll/switch/dwell events,
  the *number* of characters typed); optional coarse app-category minutes under a separate
  consent scope; a daily 2-minute care-partner diary (help minutes by type, burden 0–10).
  **Never collected:** keystroke content, text, URLs, window titles, screenshots, audio, video,
  gaze coordinates, location, contacts or app names.
- **Success criteria (all must hold):** F1 ≥ 4 of 5 dyads with usable logs; F2 ≥ 80% of the 70
  participant-days complete; F3 median participant burden ≤ 5/10 and none > 8/10; F4 median diary
  time ≤ 3 min/day and burden ≤ 4/10; **F5 zero accepted batches with a disallowed field**
  (validator receipts audited); F6 ≤ 2 unscheduled support contacts per dyad; F7 ≥ 4 of 5
  complete day 14. With n = 5, 4/5 has a Wilson 95% CI of about 0.38–0.96; the study can detect
  gross infeasibility only.
- **Assistance capture.** ASSIST events recorded during home batteries are compared descriptively
  with diary help minutes, per dyad; no correlation is reported as evidence at n = 5.
- **Software deliverable.** Telemetry integrity rules (idempotent batches, duplicate and
  conflict detection, rejection of overlapping or future periods, SHA-256 per stored batch) are
  implemented in `src/neurometric/study/telemetry.py`
  [RESULT PENDING: experiments/results/O_*/summary.json — Experiment O telemetry integrity results; no O_* directory existed at drafting].

### 4.6 Psychometric methods (summary; full specification in `docs/science/PSYCHOMETRICS.md`)
| Property (COSMIN term) | Method | Notes |
|---|---|---|
| Reliability | ICC(A,1) two-way random, absolute agreement, single measure; **GCI** inferential interval; McGraw–Wong and ICC(C,1) reported | Study R; ≥ 3 test sessions |
| Measurement error | SEM_agreement from variance components; MDC95 = 1.96·√2·SEM; Bland–Altman (log scale), LoA CIs (Bland & Altman 1999 or exact) | MDC is about individuals; group change uses the mixed model |
| Hypotheses testing (construct validity) | Known groups: Welch t, Hedges g with non-central-t CI, AUC with DeLong CI; convergent/divergent: Pearson/Spearman with Fisher-z CI against pre-registered magnitudes; Holm within the confirmatory family | ≥ 75% hypotheses confirmed |
| Floor/ceiling | Proportion at the theoretical bound or task cap; > 15% flagged | Terwee et al. 2007 [PK] |
| Responsiveness (exploratory) | SRM, Guyatt RI with a stable group, AUC of change scores, correlation with anchor change | MIC only with an adequate anchor; Devji et al. 2020 credibility criteria |
| Longitudinal / missing | REML mixed models; Little's MCAR test (descriptive); multiple imputation (m = 50) and a delta-adjusted tipping-point analysis for MNAR | Dropout in ALS is plausibly MNAR |
| Comparability across modalities | Per-modality ICC with bootstrap CI of the difference; TOST only where equal means are expected | Multi-group CFA/DIF out of scope (single observed metrics, not reflective items) |
| Internal consistency | **Not computed across task metrics** (formative, speed–accuracy trade-offs) | Alpha/omega only for questionnaires |

### 4.7 Research design and rigor
- **Pre-registration and locking.** One SAP per stage, analysis code frozen at a git commit,
  SHA-256 of the SAP recorded, registered on OSF before the first participant of that stage;
  post-lock changes demote a hypothesis to exploratory (`CLINICAL_VALIDATION_PLAN.md` §2.9).
- **Independence.** The founder does not consent participants, hold allocation lists or run
  confirmatory analyses; the partner RI holds the data.
- **Sources of variance separated by design and model** (plan §2.1): person, practice
  (S0 + fixed intervals), within-session learning (practice blocks), fatigue (rest rules,
  position term), modality (Williams square), difficulty (Fitts design), occasion (fixed time and
  setup; occasion variance enters SEM_agreement), carry-over, timing hardware.
- **Sex as a biological variable and other factors.** Sex, age band, handedness, diagnosis, AT
  type and computer-use frequency are recorded; analyses by sex are descriptive (no powered sex
  comparison) [INF].
- **Authentication of key resources.** Pinned software versions recorded in every result file;
  stimulus hashes; the public dataset's SHA-256; device bench profiles applied as
  `validation_profile_id`.

### 4.8 Milestones and quantitative go/no-go criteria
| # | Month (from award) | Milestone | Quantitative criterion | If not met |
|---|---|---|---|---|
| M0 | 3 | IRB approval; SAP (Stages 1–2) locked on OSF; bench timing done | All four input classes have a lag/SD profile; parity tests pass on 100% of golden fixtures | Delay Stage 1; no change to aims |
| M1 | 7 | Stage 1 complete | Valid-trial rate Wilson lower bound ≥ 0.90; median Fitts R² ≥ 0.80; timing self-check ≥ 95% of sessions | Fix and re-pilot the failing tasks (≤ 10 extra participants) before Stage 3 lock |
| M2 | 13 | Stages 2 and 3 complete | **H2.1:** all 5 Holm-adjusted contrasts significant in the predicted direction. **H3:** ≥ 3 of P1–P4 with ICC(A,1) ≥ 0.75 and GCI lower bound ≥ 0.60 | Demote failing scores to secondary; lengthen the affected task using the Study I relation; Aim 2 proceeds only with passing scores (documented decision) |
| M3 | 21 | Stage 4 complete | **H4.1** AUC ≥ 0.70, lower bound > 0.50; **H4.2** ≥ 75% hypotheses confirmed; **H4.3** ≤ 15% at floor per cohort on P2 and P4 | Floor failure → adaptive lower-demand version in Phase II; validity failure → revise construct definitions before Phase II |
| M4 | 22 | Stage 5 complete | F1–F7 all met; F5 is absolute | F5 breach stops the study and is reported to the IRB; F1/F2 failure → redesign home workflow |
| Go to Phase II | 24 | — | M2 met, H4.1 and H4.2 met, F1 and F5 met | Seek a second Phase I or restrict Phase II to the passing components |

### 4.9 Risks and alternative strategies
| Risk | Likelihood [INF] | Mitigation / alternative |
|---|---|---|
| No faculty PD/PI or partner RI agrees by Feb 2027 | High at present (no one contacted) | Approach several candidates in parallel (`collaborators.md`); fallback September 2027 submission |
| Practice effects persist after S0 (ICC(A,1) penalised) | Medium | Plan includes TOST and a session-trend model; add a second familiarisation session; report ICC(C,1) alongside |
| Floor effects in severe ALS or high SCI | Medium–high | Adaptive item-size staircase (Study H) as a pre-specified lower-demand variant; larger targets via the accessibility profile; switch scanning path |
| Slow AT-user recruitment | High | Three diagnostic cohorts; home sessions allowed; travel support; Carle and other clinics as candidate sites; extend Stage 4 into a no-cost extension if needed |
| Licences for comparator instruments not granted | Medium | Drop those hypotheses before lock; free comparators (NASA-TLX, SUS, Section GG) retained (`instruments.md`) |
| Browser timing variability across devices | Medium | Within-setup design; pinned configuration; bench profiles; absolute times reported with device-class bands |
| Telemetry perceived as surveillance; platform restrictions | Medium | Tier 1 opt-in and separate; visible indicator; aggregates only; Windows/Android only; sponsor-export route for BCI devices in Phase II |
| Simulation conclusions do not transfer to humans | Certain to some degree | Simulation used only to choose designs and metrics, never as evidence; Aim 1–2 data decide |
| SRAlab DAI or Digital IADL becomes the reference instrument | Medium | Stay complementary: map NeuroMetric primitives to their constructs where licensable; emphasise home and input-agnostic capture |
| Founder conflict of interest | Certain | COI management plan; independent PD/PI; data custody at RI; no publication veto |

### 4.10 Timeline (months from award)
| Months | 1–3 | 4–7 | 8–13 | 14–21 | 18–22 | 22–24 |
|---|---|---|---|---|---|---|
| Activity | IRB, CITI, COI plan, SAP lock (S1–2), bench timing | Stage 1 | Stages 2 and 3; Stage 4 SAP lock and amendment; licences | Stage 4 (3 cohorts) | Stage 5 (5 dyads) | Analysis, reports, manuscripts, Phase II application |

---

## 5. Protection of human subjects (summary for the Human Subjects attachment)

### 5.1 Risks
Computer tasks; physical risk is low [INF]. Foreseeable risks: fatigue; frustration; eye strain
and dry eye (gaze dwell); neck/shoulder strain (head pointer, joystick); skin pressure; in SCI at
T6 and above, autonomic dysreflexia triggers; in ALS, respiratory fatigue; privacy breach of
pseudonymised performance data (`CLINICAL_VALIDATION_PLAN.md` §2.4).

### 5.2 Protections
Mandatory breaks (≥ 5 min per 15 min of task time for AT users), stop rules (fatigue NRS ≥ 7 or a
rise ≥ 3), hard session caps (90 min AT users), staff trained to recognise autonomic dysreflexia
and follow the participant's own plan, no flashing stimuli, reduced-motion option. Data:
pseudonymous IDs, aggregates only at home, university-hosted storage, TLS, least-privilege
access, no audio/video/gaze coordinates (`DATA_MANAGEMENT_AND_SHARING_PLAN.md`). Only OPRS and
the IRB decide exemption and risk level [V].

### 5.3 Consent
Written consent for able-bodied adults; for AT users, consent through the participant's usual
communication method, teach-back (≥ 4/5), electronic signature, mark or witness signature; no
LAR consent (`CLINICAL_VALIDATION_PLAN.md` §6.4). Care partners consent separately. Data-sharing
consent language: `DATA_MANAGEMENT_AND_SHARING_PLAN.md` §6.

### 5.4 Inclusion
Adults ≥ 18. Children are excluded because the battery and its norms are designed for adults and
the target device studies enrol adults [INF]; this must be justified under NIH's inclusion
across the lifespan policy. Women and racial and ethnic minority groups are recruited in
proportion to the local AT-user population; planned enrolment tables to be completed with the
partner RI.

### 5.5 Conflict of interest
The founder is studying their own product. COI management plan: independent faculty PI,
founder excluded from consent and confirmatory analysis, SAP lock before data, university data
custody, no company publication veto (`CLINICAL_VALIDATION_PLAN.md` §0; `STTR_STRUCTURE.md` §5).

### 5.6 Data and safety monitoring; clinical-trial status
Minimal risk is expected [INF]; the PD/PI monitors adverse events and reports per IRB policy.
Whether any stage meets the NIH clinical-trial definition must be checked with the NIH decision
tool: Stage 2 prospectively assigns input modalities, but the outcome is task performance with a
measurement instrument, not a health-related outcome of an intervention [INF]. If NIH or the
program officer classifies a stage as a clinical trial, ClinicalTrials.gov registration and
the clinical-trial forms apply. Registration of Stage 4 is recommended for transparency anyway
(plan §2.10).

---

## 6. Rigor and reproducibility (summary)
- Every simulation result records software versions, seeds and a `synthetic: true` flag
  (`src/neurometric/experiments/core.py`). The reproducibility check (Study P) re-runs a condition
  in-process and in a pool [RESULT PENDING: experiments/results/P_reproducibility/summary.json — identical flag].
- Statistical code is verified (Study R: 86/86 scenarios pass).
- Confirmatory analyses are pre-registered and run by someone other than the founder.
- Scoring source of truth is Python; browser scoring is checked against golden fixtures.
- Public release of code and de-identified data per the DMS plan.

---

## 7. Vertebrate animals, select agents, resource sharing
No vertebrate animals are used. The X1 analysis uses an existing public dataset of macaque
behaviour; no animal work is performed [INF: confirm that secondary use of public animal data
needs no Vertebrate Animals section]. Resource sharing: `DATA_MANAGEMENT_AND_SHARING_PLAN.md`.

---

## 8. Commercialization potential (Phase I narrative; full plan in `COMMERCIALIZATION.md`)
- **Product.** Research software plus services that produce neutral, input-agnostic evidence of
  digital function and independence: clinic and home battery, consented aggregate home
  telemetry, assistance capture, and an evidence package oriented to Part 11 expectations.
- **First users and buyers [HYP].** Academic BCI and rehabilitation programmes (grant-funded
  deployments), non-invasive BCI and AAC makers, home neuro-rehabilitation device makers, and,
  later, implant sponsors preparing pivotal studies.
- **Why the iBCI market alone is not enough [INF/HYP].** About 3 US industry sponsors have active
  motor/communication IDE studies; excluding the largest, the addressable iBCI universe is about
  3 organisations in 2027 rising to about 7 by 2031, worth roughly $0.38–0.88M per year at full
  penetration under a $125K/study-year price hypothesis (`COMMERCIALIZATION.md` §0). The
  business must be input-agnostic.
- **Competition.** SRAlab DAI (with Neuralink), Mount Sinai Digital IADL, sponsor in-house tools,
  eCOA incumbents (e.g. Signant, which acquired Ametris in May 2026 [V]) (`docs/research/competitors.md`).
- **Regulatory position.** Measuring task performance for trial endpoints without diagnostic or
  treatment claims is most likely not a device, but must be fit-for-purpose and Part 11-ready
  [V guidance / INF application] (`regulatory_landscape.md` §10).
- **Status.** No customers, pilots or letters of intent exist.

---

## 9. Phase II outlook
If the go criteria are met, a Phase II (NINDS up to $3.0M [V]) would:
1. validate the locked core battery in neural-interface users through partner-run studies
   (Stage 6, under partners' protocols and IRBs; no partner has agreed);
2. run a home test–retest study and a longitudinal measurement-chain study linking device
   performance, task performance, home activity, assistance and participation, with
   within-/between-person decomposition (`docs/clinical/MEASUREMENT_CHAIN_STUDY.md`);
3. estimate anchor-based meaningful within-person change in AT users;
4. complete Part 11 computer-system validation and security certification of the hosted
   service;
5. prepare an MDDT qualification plan for a defined context of use, if the evidence supports it.

---

## 10. Institute fit (to discuss with program officers before submission)
| IC | Fit | Caveat |
|---|---|---|
| **NINDS** | Neurological disorders (ALS, SCI, stroke) and neurotechnology outcome measures; highest Phase I/II caps ($700k / $3.0M) [V] | Compete with device-development applications; frame as enabling infrastructure for neurological device trials |
| **NICHD / NCMRR** | Rehabilitation outcomes, assistive technology, functional independence; topical fit is strongest for Aims 2–3 | Phase I cap $400k [V] → use the reduced budget (`BUDGET.md` §4) |
| **NIBIB** | Technology development (measurement harness, simulation framework) | SBA guideline cap [V; reported $323,090 [AE]]; less natural home for the clinical aims |
| **NIDCD** | Communication (AAC, text entry, speech BCIs) | Phase I $400k [V]; would need a stronger communication focus |
Recommendation [INF]: request NINDS as primary and NICHD as secondary assignment; contact both
program officers with the one-page aims before writing the full application (NIH strongly
encourages this [V]).

---

## 11. Items to verify before submission
1. PA-27-102 current text: due date, page limits, Phase I duration and budget rules, clinical-trial
   option, allowable fee and small-business F&A rules [V for dates/caps; others PK].
2. Partner RI agreement, PD/PI commitment letter, subaward budget, F&A rate (`BUDGET.md`).
3. Company registrations: EIN, SAM.gov UEI, Grants.gov, eRA Commons, SBA company registry
   (≥ 6 weeks) [V warning].
4. Allocation-of-rights (IP) agreement with the partner RI, signed before award [PK]
   (`STTR_STRUCTURE.md`).
5. Instrument licences (`instruments.md` §3b).
6. Final numbers from the computational studies (all `[RESULT PENDING]` markers above).

---

## 12. References (DOIs verified via Crossref in `docs/research/methods_references.md` unless noted)
- Bland JM, Altman DG. Lancet 1986;327:307–310. 10.1016/S0140-6736(86)90837-8.
- Bland JM, Altman DG. Stat Methods Med Res 1999;8:135–160. 10.1177/096228029900800204.
- de Vet HCW et al. J Clin Epidemiol 2006;59:1033–1039. 10.1016/j.jclinepi.2005.10.015.
- Devji T et al. BMJ 2020;369:m1714. 10.1136/bmj.m1714.
- Dohle E et al. Adv Sci 2025;12(32):e01912. 10.1002/advs.202501912 [V].
- FDA. Implanted BCI devices for patients with paralysis or amputation. Final guidance, 20 May 2021 [V].
- FDA. Digital health technologies for remote data acquisition in clinical investigations. Dec 2023 [V].
- Flash T, Hogan N. J Neurosci 1985;5:1688–1703. 10.1523/JNEUROSCI.05-07-01688.1985.
- Fry A et al. J Neural Eng 2022. 10.1088/1741-2552/ac60ca [V].
- Guyatt G, Walter S, Norman G. J Chronic Dis 1987;40:171–178. 10.1016/0021-9681(87)90069-5.
- Koo TK, Li MY. J Chiropr Med 2016;15:155–163. 10.1016/j.jcm.2016.02.012.
- MacKenzie IS, Kauppinen T, Silfverberg M. CHI 2001:9–16. 10.1145/365024.365028.
- McGraw KO, Wong SP. Psychol Methods 1996;1:30–46. 10.1037/1082-989X.1.1.30.
- Meyer DE et al. Psychol Rev 1988;95:340–370. 10.1037/0033-295X.95.3.340.
- Mokkink LB et al. BMC Med Res Methodol 2020. 10.1186/s12874-020-01179-5.
- Nuyujukian P et al. IEEE TBME 2015;62:21–29. 10.1109/TBME.2014.2354697.
- Revicki D et al. J Clin Epidemiol 2008;61:102–109. 10.1016/j.jclinepi.2007.03.012.
- Sawyer A et al. EBioMedicine 2025;116:105732. 10.1016/j.ebiom.2025.105732 [V].
- Sawyer A et al. J Neural Eng 2026;23(5). 10.1088/1741-2552/ae9eee [V].
- Shrout PE, Fleiss JL. Psychol Bull 1979;86:420–428. 10.1037/0033-2909.86.2.420.
- Soukoreff RW, MacKenzie IS. Int J Hum-Comput Stud 2004;61:751–789. 10.1016/j.ijhcs.2004.09.001.
- Soukoreff RW, MacKenzie IS. CHI 2003:113–120. 10.1145/642611.642632.
- Terwee CB et al. J Clin Epidemiol 2007;60:34–42. 10.1016/j.jclinepi.2006.03.012.
- Weerahandi S. JASA 1993;88:899–905 [PK].
- Willett FR et al. J Neural Eng 2017;14:016001. 10.1088/1741-2560/14/1/016001.
- Wolpaw JR et al. IEEE Trans Rehabil Eng 1998;6:326–333. 10.1109/86.712231.
- iBCI-CC. Assessment of the iBCI endpoints for clinical utility (consensus statement), 1 Oct 2026 [V].
- ClinicalTrials.gov NCT07407725 (SRAlab DAI) [V]; NCT07871071 (Cognixion) [V].
- Public dataset: Neural Latents Benchmark MC_RTT, DANDI:000129 (CC-BY-4.0) [V]; cite per the
  dataset README in `experiments/external_data/nlb_mc_rtt_dandi000129/`.
