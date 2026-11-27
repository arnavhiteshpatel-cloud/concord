# SAP draft: Stages 1–3 (able-bodied functional testing, modality comparison, test–retest)

> **DRAFT. Not locked. Not submitted. No participants, no data.** Filled from
> `STATISTICAL_ANALYSIS_PLAN_TEMPLATE.md`. Thresholds are pre-specification proposals for faculty
> PI and statistician review. Numbers marked "computed" were calculated on 2026-11-27 with
> scipy/statsmodels and with the project's own `neurometric.psychometrics.icc` (Monte Carlo).

## 0. Version control and lock
| Field | Value |
|---|---|
| SAP title | NeuroMetric battery v1.0.0: Stages 1–3 |
| Protocols | `stage1_protocol.md`, `stage2_protocol.md`, `stage3_protocol.md` |
| IRB protocol number | *(pending; not submitted)* |
| Faculty PI | *[FACULTY PI NAME, DEPARTMENT]* |
| Independent statistician | *[NAME; must have no NeuroMetric financial interest]* |
| SAP version | 0.1 (draft) |
| Status | DRAFT |
| SHA-256 (Markdown) | *(computed at lock)* |
| Code commit | *(frozen at lock)* |
| OSF registration | *(at lock)* |
| Lock order | Part A (Stage 1) and Part B (Stage 2) lock before Stage 1 enrolment. Part C (Stage 3) locks **after** Stage 1 analysis and **before** Stage 3 enrolment, because P4 caps and task order come from Stage 1. Stage 1 data are never used to re-tune Stage 3 thresholds. |

## 1. Objectives and hypotheses
| ID | Hypothesis | Status | Decision rule |
|---|---|---|---|
| H1.1 | Valid-trial rate is adequate | Feasibility (pre-specified) | Proportion of participants with ≥ 95% valid trials: lower 95% Wilson bound ≥ 0.90 (at participant level; trial-level rate also reported) |
| H1.2 | A2 follows Fitts' law | Feasibility | Median per-participant R² (MT ~ IDe) ≥ 0.80; group R² on 6 condition means ≥ 0.90 |
| H1.3 | No excessive floor/ceiling on P1–P4 | Feasibility | ≤ 15% at the best or worst possible value |
| H1.4 | Timing self-checks pass | Feasibility | ≥ 95% of sessions pass |
| H1.5 | Position (fatigue/order) effect bounded | Estimation | 95% CI of per-position change in log MT excludes > +10% per family position (+0.0414 log10 units) |
| **H2.1** | P2 orders modalities A > B, A > C, A > D, B > D, C > D | **Confirmatory** | 5 one-sided contrasts from the mixed model on log10 P2, Holm, FWER 0.05; all 5 must reject |
| H2.2 | Same ordering for P3, P4 | Secondary | Holm within each score |
| H2.3 | NASA-TLX raw higher for B, C, D than A | Secondary | Holm, 3 contrasts |
| H2.4 | Modality offsets | Estimation | Ratios (back-transformed) with 95% CI; Bland–Altman log-scale LoA (descriptive) |
| **H3.1** | ICC(A,1) for P1, P2, P3, P4 | **Confirmatory, co-primary** | Each **generalized-CI (GCI) lower 95% bound** ≥ 0.75 (S1–S4, k = 4). Battery claim needs all 4 (intersection–union). The McGraw–Wong bound is a sensitivity analysis only, because it under-covers with systematic session effects (Experiment R; `docs/science/PSYCHOMETRICS.md` design note) |
| H3.2 | SEM, MDC95 precision | Secondary | SEM 95% CI within the chi-square multiplier interval [0.90, 1.13] (df = 147); reported regardless |
| H3.3 | No residual systematic session (practice) effect after S0 | Secondary | TOST on mean(S4 − S1), margin ±1.0 × SEM, 90% CI; plus the mixed-model session trend over S1–S4 |
| H3.4 | MW lower bound for ICC(A,1); ICC(C,1) with MW exact CI | Sensitivity | Reported; discordance with H3.1 is discussed (§9) |

## 2. Design summary
- **Stage 1.** Single visit; full battery, 18 tasks; Williams 6 × 6 over task families A–F;
  n = 42.
- **Stage 2.** 2 visits; 4 modalities (A mouse, B head pointer + dwell, C eye-gaze OS pointer +
  dwell, D single-switch scanning); Williams 4 × 4 (ABDC, BCAD, CDBA, DACB); periods 1–2 at
  visit 1, periods 3–4 at visit 2; n = 24.
- **Stage 3.** S0 familiarization (core battery run twice), then S1, S2, S3, S4 at 2–7-day intervals; fixed task order; mouse;
  n = 60 enrolled, 50 completers.
- **Randomization.** `scripts/allocation_<stage>.py` (to be written), seeded with a value drawn
  publicly at lock (e.g. a date-stamped value recorded in the SAP). Permuted blocks of the
  sequence count. The list is held by the study coordinator, not the founder.
- **Stimulus seeds.** Session s for participant i uses seed = hash(study, i, s) via
  `battery.stimuli`. Parameters are identical across sessions.

## 3. Estimands
| Objective | Population | Variable | Intercurrent events → strategy | Summary |
|---|---|---|---|---|
| H3.1 | Able-bodied adults, mouse, after familiarization | P1–P4 per test session (S1–S4) | Hardware or browser change between sessions → per-protocol exclusion of that session (hypothetical: same setup); session stopped for fatigue → scores from completed tasks kept, uncompleted tasks missing (MAR) | ICC(A,1), 95% CI |
| H2.1 | Able-bodied novices | log10 P2 per modality block | Calibration failure (C) → recorded as "modality not usable" and P2 set to floor (0 bps) in the primary analysis (treatment-policy). Sensitivity: exclude (hypothetical) | Ratio of geometric means, one-sided Holm-adjusted tests |
| H1.x | Able-bodied adults | Trial validity; R²; floor/ceiling | none expected | Proportions, medians |

## 4. Endpoints
- **P1**, A2 effective throughput, bits/s.
  - Per (participant, D, W) condition: We = 4.133 × SDx of endpoint deviations projected on the
    task axis; De = mean movement amplitude; IDe = log2(De/We + 1); TP = IDe/MT(s). P1 is the
    mean over administered conditions.
  - Excluded selections: first selection of each sequence (not timed); misfires (selection
    > 2W from target centre **and** MT < 150 ms [HYP rule]).
  - At least 4 of 6 conditions are needed, otherwise P1 is missing.
  - Univariate We is primary; bivariate We is reported (Wobbrock et al. 2011).
- **P2**, A4 achieved bitrate = log2(N − 1) × max(Sc − Si, 0)/t, with N = 24 items and t the
  total task time from first cue to last selection, including errors. Analysed as log10(P2 + 0.01).
  The 0.01 offset handles zero; sensitivity uses a Tobit model.
- **P3**, E1 ccpm. Correct characters = |P| − MSD(P,T), summed over 3 phrases, divided by total
  entry time (first keystroke to Done, per phrase) in minutes. Phrases not finished by the
  3-min cap contribute their transcribed text and 3 min.
- **P4**, dADL time index = mean over F2, F3 (4 trials) and F5 (6 trials) of
  log10(time_to_complete_s).
  - Trials with any ASSIST event of type physical or task_completion, or that are not completed,
    get cap_t.
  - cap_t = 3 × (99th percentile of the Stage 1 completed time for that task), frozen before
    Part C is locked.
- **Secondary:** A2 error rate; A2 path efficiency; A1 MT; C1 time; D1 time; E1 total error rate
  (Soukoreff & MacKenzie 2003); NASA-TLX raw (mean of 6 subscales 0–100); fatigue NRS change;
  ASSIST counts.
- **Trial validity.** A trial is invalid if `visibility_or_focus_lost` is true, if there is a
  technical fault flag, or if `frames_dropped_during_trial` exceeds 10% of the trial's frames.
  Invalid trials are excluded from scoring and counted for H1.1.

## 5. Populations
As in the template. For H3.1 the **reliability set** is participants with valid S1, S2, S3 and S4
for that score (complete case). Mixed-model sensitivity uses all with ≥ 1 valid test session.

## 6. Models
**6.1 Stage 1 position/fatigue (H1.5).**
log10 MT_{itq} = β0 + β_task + β_pos · position_q + β_ID · ID_t + β_trial · trialindex + u_i + e,
for A-family trials.
- β_pos is the per-family-position change.
- `MixedLM` with a random intercept; a random slope on position if it converges.
- **Fitts:** OLS per participant; group OLS on condition means.

**6.2 Stage 2 (H2.1).**
log10 P2_{im} = β0 + β_modality[m] + β_period[p] + β_sequence[g] + u_i + e_{im}.
- REML, Kenward–Roger df if available; otherwise Satterthwaite or a z approximation, with the
  choice documented.
- Contrasts: A−B, A−C, A−D, B−D, C−D, one-sided, Holm (`psychometrics.effects.holm`).
- **Carry-over sensitivity:** add a first-order carry-over term (previous modality). The Williams
  design makes it estimable, but power is low, so it is not a gate.
- Paired dz per contrast (`cohens_dz`) is reported.

**6.3 Stage 3 reliability (H3.1–H3.4).**
- Wide matrix n × 4 (S1–S4) per score.
- `psychometrics.icc(Y, forms=("2,1","3,1"), alpha=0.05)` gives the GCI (`gci_low`, `gci_high`;
  **decision**; seeded, `gci_draws = 10000`) and the McGraw–Wong CI (sensitivity).
- `psychometrics.sem_mdc(..., icc_form="2,1")`: SEM_agreement = √(σ²_session + σ²_residual)
  from ANOVA variance components; MDC95 = 1.96 × √2 × SEM. Labelled with `DISTRIBUTION_LABEL`.
- `psychometrics.bland_altman` on log10 scores for S1 vs S4 and for adjacent pairs: bias, LoA,
  proportional-bias regression. Back-transformed to ratio LoA.
- Practice: `fit_repeated_measures_lmm(df, outcome, "pid", "session", time_as="categorical")`
  over S0–S4, plus a numeric-trend model over S1–S4.
- TOST: `psychometrics.tost(S4, S1, low=-1.0*SEM, paired=True)`.
- Floor/ceiling: `floor_ceiling(x, min_possible, max_possible)`. For P2 the floor is 0 bps; for
  P4 the ceiling is all trials at cap.

**6.4 Assumption checks.** Q–Q plots of residuals and random effects. If the log transform does
not stabilize the variance (Bland–Altman proportional bias with p < 0.05 and slope CI excluding
0), report it and add a rank-based ICC sensitivity analysis.

**6.5 Convergence.** Simplify in this order: drop the random slope → drop the carry-over term →
z approximation. Every simplification is logged.

## 7. Multiplicity
- **H2.1:** Holm over 5 one-sided contrasts, FWER 0.05.
- **H3.1:** intersection–union over P1–P4. Each is tested at a one-sided 0.025 level (the lower
  bound of a two-sided 95% CI); the battery claim requires all four, so FWER ≤ 0.025 and no
  adjustment is needed. Per-score claims also show Bonferroni 98.75% lower bounds.
- Everything else is secondary or exploratory and unadjusted, with labels.

## 8. Missing data
- Reason codes: participant choice, fatigue, illness, technical fault, scheduling, withdrawal.
  These use `missing_data_summary` and `little_mcar_test` (descriptive).
- **Primary assumption:** MAR given S1 score, age band, session and fatigue NRS.
- **H3.1 primary** is complete case. **Sensitivity 1:** `icc(..., missing="mixed")`.
  **Sensitivity 2:** MI (R `mice`, PMM, m = 50, predictors: other primary scores at all sessions,
  age band, fatigue NRS); ICC per imputation; Fisher z; Rubin's rules.
  There is no standard way to combine GCIs across imputations, so the MI sensitivity reports
  the Rubin-pooled Fisher-z ICC(A,1) with its approximate CI. It is labelled approximate and is
  not a decision rule.
- **Tipping point:** add −δ × SD(observed S1) to imputed values for P1–P3 and +δ × SD for P4
  (unfavourable direction), δ ∈ {0, 0.1, …, 1.0}. Report the smallest δ at which the lower bound
  falls below 0.75.
- **Stage 2:** the mixed model uses all available data (MAR). A dropout is replaced by a new
  participant on the same sequence, to keep the Williams balance; the replacement is reported.

## 9. Sensitivity analyses
1. McGraw–Wong lower bound vs the GCI decision bound. If MW passes but GCI does not, report
   "not met by the pre-specified GCI criterion". MW is known to under-cover when sessions
   differ systematically, so an MW pass is not a substitute.
2. ICC(C,1), consistency, to separate ranking stability from systematic shift.
3. Per-protocol set.
4. Without the misfire/outlier rule.
5. S2–S4 only (k = 3, GCI), in case S1 still carries practice. Exploratory, because it is
   chosen after S1 is seen.
6. MI and tipping point (§8).
7. Stage 2: calibration failures excluded rather than floored.
8. Stage 2: carry-over model.

## 10. Subgroups (exploratory)
Age band (18–30, 31–45, 46–65); daily computer hours (≤ 4, > 4); handedness. Interaction terms
in the mixed model; no claims.

## 11. Interim
None. Recruitment and attrition are monitored without outcome data.

## 12. Reporting shells
- T1: demographics per stage.
- T2: valid-trial rates per task.
- T3: Fitts parameters (a, b, R²; univariate/bivariate TP).
- T4: Stage 2 modality geometric means, ratios and Holm-adjusted p-values.
- T5: Stage 3 ICC(A,1) and ICC(C,1) with MW and GCI CIs, SEM, MDC95, and Bland–Altman ratio LoA.
- F1: Bland–Altman plots.
- F2: session-mean trajectories S0–S4.
- F3: modality forest plot.

## 13. Sample-size record (computed 2026-11-27)
- **Walter et al. 1998** (one-sided α = 0.025, power 0.80; ρ0 = 0.75):
  - ρ1 = 0.88, k = 2: n = 49.4; k = 3: n = 34.9
  - ρ1 = 0.90, k = 2: n = 32.5
- **Bonett 2002:** ρ = 0.85, k = 2, w = 0.20: n = 30.6.
- These analytic formulas ignore session-variance uncertainty, so they understate n and k for
  an absolute-agreement GCI rule.
- **Monte Carlo of the actual decision rule** (`psychometrics.icc` GCI lower bound ≥ 0.75; 300
  replicates per cell; 2,000 GCI draws; 2026-11-27). P(pass) at true ICC 0.88 with 0% / 1% / 3%
  systematic session variance:
  - k = 3, n = 50: 0.69 / 0.28 / 0.15
  - **k = 4, n = 50: 0.93 / 0.53 / 0.27** (true 0.90: 0.99 / 0.66 / 0.34)
  - k = 4, n = 60: 0.94 / 0.63 / 0.30
  - k = 5, n = 50: 0.96 / 0.74 / 0.44
  - false-pass at true 0.75: ≤ 0.013 in every k ≥ 3 cell
- k = 2 (earlier runs): ≤ 0.31 even with no session variance.
- **Choice: k = 4, 50 completers (enrol 60).** The scripts (`mc2.py`, `mc4.py`, `mc5.py` in the
  session scratchpad) are to be committed under `experiments/` by the statistician at lock
  [INF].
- **Stage 2** (one-sided paired t, α = 0.01, n = 24): power 0.91 for dz = 0.8.
- **Stage 1:** Wilson 95% CI for 38/40 = 0.835–0.986.

## 14. Deviations log
| # | Date | Section | Change | Reason | Data seen? | Effect | Approved |
|---|---|---|---|---|---|---|---|
| — | — | — | (none; draft) | — | — | — | — |

## 15. Sign-off
Pending: faculty PI, independent statistician, student investigator attestation.
