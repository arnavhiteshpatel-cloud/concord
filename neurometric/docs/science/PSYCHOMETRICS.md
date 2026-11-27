# NeuroMetric psychometrics: methods, applicability and verification

Module: `neurometric.psychometrics` (`src/neurometric/psychometrics/`). Tests:
`tests/test_psychometrics.py`. Monte-Carlo verification script:
`python -m neurometric.psychometrics.verify_coverage` → `experiments/results/R_statistical_verification/`.

References marked **[PK]** are cited from prior knowledge and were not re-verified against the
source for this document. Every formula is also written out in the function docstrings.

---

## 1. What we are measuring, and what that implies for the statistics

NeuroMetric task scores (pointing throughput, Wolpaw ITR / achieved bitrate, movement time,
path efficiency, endpoint error, false activations per minute, text-entry WPM, MSD error rate,
…) are **single observed performance metrics** computed from many trials within a session. They
are not items of a questionnaire and they are not interchangeable indicators of one latent trait.
The psychometric questions for such metrics are:

| Question | Property | NeuroMetric method |
|---|---|---|
| Does a person get the same score on a repeat session? | Test–retest reliability (relative) | `icc` – ICC(2,1) absolute agreement (primary) |
| How large is measurement error in score units? | Agreement / measurement error | `sem_mdc` (SEM, MDC95/90), `bland_altman` |
| Is an observed individual change larger than noise? | Statistically detectable change | MDC95 = 1.96·√2·SEM |
| Is a change important to the user? | Clinically important change (MCID) | **Not computable here** – `mcid_note()` |
| Do two measurement routes give the same numbers? | Method agreement | `bland_altman`, `lin_ccc` |
| Does the score separate groups that should differ? | Known-groups validity | `known_groups` |
| Does it correlate with what it should (and not with what it shouldn't)? | Convergent / divergent validity | `correlation_ci`, `convergent_divergent` |
| Are many users at the scale limit? | Floor / ceiling effects | `floor_ceiling` |
| Does it detect true change? | Responsiveness | `responsiveness` |
| Is it equally reliable / comparable across input modalities? | Pragmatic invariance | `compare_icc_across_groups`, `tost` |
| How do scores evolve over sessions with missing visits? | Longitudinal model | `fit_repeated_measures_lmm`, `missing_data_summary` |

## 2. Reliability

### 2.1 Which ICC form

Notation: n subjects, k sessions; ANOVA mean squares MS_R (subjects), MS_C (sessions), MS_E
(residual), MS_W (within-subject, one-way). `icc()` returns all six forms with McGraw & Wong
(1996) F-based 95 % CIs; the docstring lists every formula.

| S&F form | M&W | Use in NeuroMetric |
|---|---|---|
| **ICC(2,1)** | ICC(A,1) | **Primary for test–retest of task scores.** Sessions are a random sample of occasions; systematic session shifts (practice, fatigue, device recalibration) count as error because a clinician comparing a user's score to a norm or to their own earlier score experiences them as error (Koo & Li 2016 [PK]; de Vet et al. 2006 [PK]). |
| ICC(3,1) | ICC(C,1) | Report alongside ICC(2,1). Consistency: ignores session mean shifts. Appropriate when only rank-ordering matters, or when a practice effect is modelled explicitly. A large gap ICC(3,1) − ICC(2,1) is itself a finding (systematic learning effect → add familiarisation sessions). |
| ICC(1,1) | ICC(1) | Only when sessions are not crossed with subjects (each subject measured on different, unaligned occasions; no common "session 1/2"). |
| ICC(·,k) | ICC(A,k), ICC(C,k), ICC(k) | Only when the score used in practice is the **mean of k sessions**. Never report an average-measure ICC for a single-session score. |

Reporting checklist (Koo & Li 2016 [PK]): software, model (one-way / two-way random / mixed),
type (agreement / consistency), unit (single / average), point estimate **and 95 % CI**,
interpretation based on the CI (<0.5 poor, 0.5–0.75 moderate, 0.75–0.9 good, >0.9 excellent —
conventions, not laws).

**Absolute-agreement CIs: use the generalized CI when sessions differ systematically.**
Experiment R (§8) found that the McGraw & Wong Satterthwaite interval for ICC(A,·) — which is
also what pingouin and most software compute — under-covers when the session variance is
comparable to the error variance: 78 % (n = 200, k = 3), 87 % (n = 50, k = 3), 91 % (n = 20,
k = 2), 92 % (n = 50, k = 6) nominal 95 %. It gets *worse* with more subjects, because the
information about session variance is limited by k − 1, not n. `icc()` therefore also reports a
seeded generalized confidence interval (`gci_low`, `gci_high`; generalized pivotal quantities,
Weerahandi 1993 [PK]; Ionan et al. 2014 [PK]) for the agreement forms, which kept 94.9–96.1 %
coverage in every scenario. Report the M&W interval for comparability and the GCI as the
inferential interval whenever ICC(3,1) − ICC(2,1) is non-trivial.

**Design consequence:** with only 2 sessions the population session variance is estimated with
1 df, so an honest CI for ICC(A,1) is wide however many participants are enrolled (simulated
mean GCI width at true ICC 0.8: 0.46 for n = 100, k = 2 vs 0.15 for n = 100, k = 3). Plan
**≥ 3 sessions** for test–retest of absolute agreement.

Expected 95 % CI width of ICC(2,1) (M&W / GCI; 300 simulated studies each, no session effect):

| true ICC | n | k = 2 (M&W / GCI) | k = 3 (M&W / GCI) |
|---|---|---|---|
| 0.7 | 30 | 0.39 / 0.65 | 0.31 / 0.38 |
| 0.8 | 15 | 0.44 / 0.74 | 0.33 / 0.43 |
| 0.8 | 30 | 0.29 / 0.63 | 0.23 / 0.30 |
| 0.8 | 50 | 0.21 / 0.56 | 0.17 / 0.22 |
| 0.9 | 30 | 0.16 / 0.54 | 0.13 / 0.18 |
| 0.9 | 50 | 0.11 / 0.48 | 0.10 / 0.13 |

### 2.2 Missing sessions

`icc(..., missing="complete_case")` (default) drops subjects with any missing session and
reports the count (`n_subjects_dropped`, plus a warning). `missing="mixed"` / `icc_mixed()`
estimate variance components by REML with statsmodels `MixedLM` from all observations
(crossed random subject and session effects for the agreement form; fixed sessions + random
subject for consistency; random subject only for one-way). For balanced complete data with
positive components REML equals the ANOVA estimator (tested to 2e-3). Under 15 % MCAR missing
cells both estimators were essentially unbiased (|bias| ≤ 0.006); REML uses more data and remains valid
under MAR, complete-case does not. No F-based CI exists for the mixed-model ICC; `n_boot > 0`
gives a subject-cluster percentile bootstrap (slow: one model fit per resample).

### 2.3 SEM and MDC

`sem_mdc()` reports three labelled SEMs; the headline (`primary`, default `sqrt_mse`) is stated
in the output:

* `sd_icc`: SEM = SD_pooled·√(1 − ICC), SD_pooled = √(mean of per-session variances). Depends on
  sample heterogeneity — a homogeneous sample gives a lower ICC but a similar SEM.
* `sqrt_mse`: SEM = √MS_E (Weir 2005 [PK]) — consistency SEM, excludes systematic session shifts.
* `agreement`: SEM = √(σ²_session + MS_E), σ²_session = max(0, (MS_C − MS_E)/n) (de Vet 2006 [PK]).

MDC95 = 1.96·√2·SEM; MDC90 = 1.645·√2·SEM. The √2 is because a change score carries error from
both occasions. In Experiment R, with SEM estimated from 40 calibration subjects, 5.8 % of truly
stable people exceeded MDC95 (nominal 5 %; the excess is the estimation error of SEM).

Interpretation:

* **MDC is about individuals.** A group mean change is detectable at a much smaller value
  (approximately MDC/√n for the mean of n independent changes [PK]; better: test it with the
  mixed model).
* **Statistically detectable ≠ clinically important.** MDC answers "is this bigger than the
  noise of the measurement?", not "does it matter to the user?". An MCID requires anchor-based
  evidence (global rating of change, goal attainment, caregiver/clinician judgement) from real
  participants and cannot be derived from simulation or from the score distribution. No
  function computes an MCID; `distribution_based_change_estimates()` labels every value
  "distribution-based estimate, not an MCID", and `mcid_note()` returns the explanation for
  reports.
* SEM assumes homoscedastic error. For metrics whose error grows with level (movement time,
  WPM), check Bland–Altman proportional bias; consider log transformation, and then MDC is a
  ratio.

### 2.4 Test length: Spearman–Brown

`spearman_brown(rho, m)` = mρ/(1 + (m − 1)ρ); `spearman_brown_length(rho, target)` =
ρ*(1 − ρ)/(ρ(1 − ρ*)). Use to decide how many trials/blocks per session (or how many sessions to
average) are needed for a target reliability, assuming added trials are parallel. Verified in
simulation: the reliability of the mean of 4 parallel trials matched the prophecy within 0.02,
and ICC(1,k)/ICC(3,k) equal the step-up of ICC(1,1)/ICC(3,1) exactly. Note the A,k form is not
an exact step-up (session term), but its CI bounds are.

### 2.5 Internal consistency — why not for task metrics

`cronbach_alpha()` (Feldt CI) and `mcdonald_omega()` (one-factor ML model; loadings match
statsmodels' ML factor analysis to 1e-4) exist for questionnaires that NeuroMetric may
administer (e.g. a usability or workload scale whose items are meant to measure one construct).
**They must not be computed across task metrics.** Throughput, error rate, latency and path
efficiency are different constructs (formative, partly trading off against each other — the
speed–accuracy trade-off makes some correlations negative by design). Alpha over them is neither
the reliability of any single metric nor of their sum; it mostly reflects how many metrics were
included and how correlated they happen to be. Alpha also assumes tau-equivalence; with
congeneric items it underestimates reliability (demonstrated in the tests: omega recovers the
true value, alpha falls below it). The report sets `internal_consistency.computed = false` with
this reason.

## 3. Agreement

* **Bland–Altman** (`bland_altman`): bias with t-CI, LoA = bias ± 1.96·SD_d, CIs of the LoA by
  the Bland & Altman (1999) approximation (default), the 1986 √(3s²/n) shortcut, or the exact
  non-central-t tolerance factor (Carkeet 2015 [PK]); OLS regression of d on the mean for
  proportional bias (with warning); Shapiro–Wilk on differences. Use for: session 2 − session 1
  in metric units; browser vs Python scoring parity (D-003); two devices on the same people.
  One pair per subject (the repeated-pairs variant is not implemented).
* **Lin's CCC** (`lin_ccc`): ρ_c = r·C_b (precision × accuracy), Fisher-z CI with Lin's
  asymptotic variance. CCC penalises location and scale shifts that Pearson r ignores.

## 4. Validity

* **Known groups** (`known_groups`): Welch t (unequal variances; default — never pooled t for
  groups of unequal size/variance), Mann–Whitney U, Hedges g with non-central-t CI, AUC with
  DeLong (or seeded bootstrap) CI, and a pre-specified expected direction. Typical NeuroMetric
  hypotheses: experienced vs novice users of the same interface; able-bodied reference vs users
  with motor impairment; dwell vs switch input for pointing throughput.
* **Convergent / divergent** (`convergent_divergent`): Pearson or Spearman with Fisher-z CIs
  (Spearman SE √(1.06/(n−3)), Fieller 1957 [PK]) against pre-registered thresholds (default
  |r| ≥ 0.5 convergent, |r| < 0.3 divergent — set per hypothesis).
* **Floor / ceiling** (`floor_ceiling`): proportion at the theoretical min/max (or observed,
  flagged), > 15 % flagged (Terwee 2007 [PK]). Expect floor effects for error-rate and
  false-activation metrics in skilled users (many zeros) — such metrics have poor ICC because of
  low between-subject variance, and a count model may be more appropriate.
* **Responsiveness** (`responsiveness`): SRM, Kazis ES, d_z with CI, Guyatt RI (only with a
  stable group's change SD — otherwise not computed, with warning), AUC of change scores
  changed vs stable, proportion exceeding the MDC in each group.

## 5. Effect sizes and multiplicity

`cohens_d`, `hedges_g` (exact J by default; `correction="approx"` = 1 − 3/(4df − 1) as in
pingouin), `cohens_dz` (paired, = t/√n), `cliffs_delta` (= 2·AUC − 1), `bootstrap_ci`
(seeded; percentile or BCa; independent or paired resampling), `holm`, `benjamini_hochberg`.
Use Holm for a small confirmatory family (e.g. the primary hypotheses of a validation study);
BH for exploratory screens over many metrics.

## 6. Longitudinal models and missing data

`fit_repeated_measures_lmm`: random intercept per participant (optional random slope for
session), fixed session trend (numeric) or session factor, optional covariates (e.g. modality),
REML, Wald CIs, variance components, variance-component ICC (at time 0 if a random slope is
used; flagged). Uses all observations — valid under MAR given the model.

`missing_data_summary`: per-variable missingness over the full subject × session grid (an
absent session row counts as missing), per-subject classification complete / monotone
(dropout) / intermittent, pattern counts, and **Little's (1988) MCAR test** (EM ML estimates;
reproduces naniar's `mcar_test(airquality)`: χ² = 35.1, df = 14, p = 0.00142). Non-rejection
does not prove MCAR (low power; cannot separate MAR from MNAR). Dropout in assistive-technology
studies is plausibly related to performance or health (MNAR); plan sensitivity analyses.

## 7. Pragmatic invariance across input modalities

`compare_icc_across_groups`: per-group ICC with M&W CI; ICC difference with a stratified
subject bootstrap CI; equivalence if the 90 % (1 − 2α) CI lies within ±margin. `tost`: two
one-sided tests (Welch by default) for mean equivalence within a pre-specified margin (e.g. less
than the MDC or a pre-registered fraction of the between-subject SD).

**Out of scope for v1:** multi-group CFA invariance (configural/metric/scalar/strict) and DIF.
Task scores are single observed metrics, not multiple reflective indicators of one factor, so a
per-group factor model is not identified or not meaningful; MG-CFA needs hundreds of
participants per group; and no CFA engine is among the vetted dependencies. Equal reliability and
equivalent means do not show that a score measures the same construct in each modality — that
needs construct-validity evidence within each group.

## 8. Analysis-plan templates for participant studies

These templates are starting points for pre-registration; all numbers are to be justified per
study.

**A. Test–retest reliability and measurement error (per task metric)**
1. Design: ≥ 30 participants (Koo & Li 2016 [PK]; see CI-width table §2.1), ≥ 3 sessions on
   separate days, fixed protocol, familiarisation session excluded and stated.
2. Primary: ICC(2,1) absolute agreement with GCI and M&W 95 % CI; secondary ICC(3,1).
3. SEM (state definition), MDC95; Bland–Altman session 2 − 1 with LoA CIs and proportional-bias
   check; LMM of session trend (practice effect).
4. Missing data: report patterns + Little's test; primary complete-case ICC, sensitivity
   mixed-model ICC.
5. Floor/ceiling per metric. No alpha across metrics.

**B. Construct validity**
1. Pre-register hypotheses with direction and magnitude (known groups: expected AUC/g; convergent
   and divergent measures with thresholds). Report the % of hypotheses supported (COSMIN [PK]).
2. Welch t + Hedges g (CI) + AUC (DeLong) per known-groups hypothesis; Holm across the family.

**C. Responsiveness and important change**
1. External anchor collected at follow-up (global rating of change, goal attainment).
2. SRM, Guyatt RI (stable group defined by the anchor), AUC of change scores for
   changed vs stable; proportion beyond MDC.
3. MCID: anchor-based (mean change in the "minimally improved" anchor category, ROC-based cut
   point), triangulated with distribution-based values that are labelled as such.

**D. Comparability across input modalities**
1. Per-modality ICC(2,1) with CI; ICC difference with bootstrap CI and a pre-specified
   equivalence margin (e.g. 0.1).
2. TOST on means only where equal means are expected; otherwise report modality as a covariate
   in the LMM.

## 9. Verification (Experiment R: statistical implementation verification)

Run: `cd neurometric && python -m pytest tests/test_psychometrics*.py -q` (50 tests, ~11 s;
the full coverage study is `-m slow`, ~25 s at 500 replications) and
`python -m neurometric.psychometrics.verify_coverage --reps 2000` (86 s; results in
`experiments/results/R_statistical_verification/coverage_results.{csv,json}`; seed 20261127;
numpy 2.5.3, scipy 1.18.1, statsmodels 0.15.0, pingouin 0.7.0).

### 9.1 (a) Published worked examples

| Source | Quantity | Published | NeuroMetric |
|---|---|---|---|
| Shrout & Fleiss 1979, 6 × 4 example | ICC(1,1), (2,1), (3,1), (1,4), (2,4), (3,4) | .17, .29, .71, .44, .62, .91 | .166, .290, .715, .443, .620, .909 (all equal at 2 dp) |
| Shrout & Fleiss 1979 | BMS, WMS, JMS, EMS | 11.24, 6.26, 32.49, 1.02 | identical at 2 dp |
| Bland & Altman 1986 PEFR (Wright vs mini Wright) [PK data] | mean diff, SD, r, LoA (± 2 SD) | −2.1, 38.8, 0.94, −79.7 / 75.5 | −2.1, 38.8, 0.94; LoA from rounded values identical; unrounded −79.65 / 75.41 |
| naniar `mcar_test(airquality)` [PK] | χ², df, p, patterns | 35.1, 14, 0.00142, 4 | 35.106, 14, 0.001418, 4 |
| pingouin docs, `tost` | p (Student; paired 0.5) | 0.965097; 0.954854 | identical (1e-6) |
| pingouin docs, wine ICC | ICC(1,1); ICC(C,k) | 0.728; 0.915 | identical (3 dp) |
| Spearman–Brown | ρ = .5 doubled; length for .5 → .8 | .667; 4 | identical |

### 9.2 (b) Independent implementations

| Our function | Reference | Result |
|---|---|---|
| `icc` (all six forms, 5 random datasets incl. missing → complete case) | `pingouin.intraclass_corr` | ICC to 1e-10, F/p/df identical; CIs within 0.005 — **discrepancy: pingouin rounds CI95 to 2 dp**; full-precision CIs checked against an independent re-derivation (1e-12) |
| `icc_mixed` (REML) | ANOVA ICC, balanced data | within 2e-3 (optimiser tolerance) |
| `cronbach_alpha` | `pingouin.cronbach_alpha` | alpha 1e-12; CI within 5e-4 (pingouin rounds to 3 dp) |
| `mcdonald_omega` | `statsmodels` `Factor(method="ml")` | standardized loadings within 1e-4 |
| `cohens_d`, `hedges_g(correction="approx")`, `cohens_dz` | `pingouin.compute_effsize` | identical (1e-12). Exact J (our default) differs from pingouin's approximation by < 0.2 % |
| `hedges_g(ci="normal")` | `pingouin.compute_esci` | **discrepancy: pingouin multiplies the Hedges–Olkin SE by a t quantile (df = n1+n2−2); Hedges & Olkin and we use z.** Reconstructing pingouin's interval from our SE matches to 1e-8. Our default CI is the exact non-central t. |
| `cliffs_delta` | brute force; 2·pingouin CLES − 1 | identical |
| `auc_delong` | scipy Mann–Whitney U/(n1n2); brute-force structural components | identical (1e-12) |
| `known_groups` Welch t / Mann–Whitney | `pingouin.ttest(correction=True)`, scipy | identical |
| `correlation_ci` | `scipy.stats.pearsonr(...).confidence_interval`; `pingouin.corr` | 1e-10; pingouin to its 2-dp rounding |
| `holm`, `benjamini_hochberg` | `statsmodels multipletests`, `scipy.stats.false_discovery_control` | identical (1e-14) |
| `bootstrap_ci(method="bca")` | `scipy.stats.bootstrap(method="BCa")` | within 0.03 (different resampling streams); seeded output reproducible |
| `tost` (Welch) | `pingouin.tost(correction=True)` | identical (1e-8) |
| `fit_repeated_measures_lmm` | OLS slope (balanced); ANOVA ICC(3,1) for categorical sessions | 1e-6; 1e-3 |
| `em_mvn` | ML moments of complete data | 1e-12 |
| scipy `nct.cdf` | — | **found: returns NaN far in the tail (t < 0, large non-centrality)**; the CI inversion uses the reflection identity and a bracket search; regression test added |

### 9.3 (c) Known-truth simulations (2000 replications per row unless stated)

Pass rule: |coverage − 0.95| ≤ 3·MCSE (+0.02 for large-sample approximations); tests: rejection
rate ≤ α + tolerance; bias rows: |bias| ≤ 0.03. Rows marked *known limitation* document the
McGraw & Wong agreement-interval under-coverage (§2.1) and pass when they under-cover, i.e. the
finding is reproduced. Result: **86/86 rows pass.** The fast test-suite repeats the key checks
at 150–500 replications.

| Analysis | Scenario | Truth | Bias | Checked value | Nominal | Pass |
|---|---|---|---|---|---|---|
| ICC(2,1) 95% CI (McGraw & Wong) | n=20, k=2, var_s=1.0, var_session=0.0, var_e=1.0 | 0.500 | -0.0218 | coverage 0.9495 | 0.95 | yes |
| ICC(2,k) 95% CI (McGraw & Wong) | n=20, k=2, var_s=1.0, var_session=0.0, var_e=1.0 | 0.667 | -0.0414 | coverage 0.9495 | 0.95 | yes |
| ICC(3,1) 95% CI (McGraw & Wong) | n=20, k=2, var_s=1.0, var_session=0.0, var_e=1.0 | 0.500 | -0.0211 | coverage 0.9480 | 0.95 | yes |
| ICC(3,k) 95% CI (McGraw & Wong) | n=20, k=2, var_s=1.0, var_session=0.0, var_e=1.0 | 0.667 | -0.0410 | coverage 0.9480 | 0.95 | yes |
| ICC(1,1) 95% CI (McGraw & Wong) | n=20, k=2, var_s=1.0, var_session=0.0, var_e=1.0 | 0.500 | -0.0215 | coverage 0.9460 | 0.95 | yes |
| ICC(1,k) 95% CI (McGraw & Wong) | n=20, k=2, var_s=1.0, var_session=0.0, var_e=1.0 | 0.667 | -0.0408 | coverage 0.9460 | 0.95 | yes |
| ICC(2,1) 95% CI (generalized CI) | n=20, k=2, var_s=1.0, var_session=0.0, var_e=1.0 | 0.500 | -0.0218 | coverage 0.9605 | 0.95 | yes |
| ICC(2,k) 95% CI (generalized CI) | n=20, k=2, var_s=1.0, var_session=0.0, var_e=1.0 | 0.667 | -0.0414 | coverage 0.9605 | 0.95 | yes |
| ICC(2,1) 95% CI (McGraw & Wong) | n=30, k=3, var_s=0.7, var_session=0.0, var_e=0.3 | 0.700 | -0.0120 | coverage 0.9525 | 0.95 | yes |
| ICC(2,k) 95% CI (McGraw & Wong) | n=30, k=3, var_s=0.7, var_session=0.0, var_e=0.3 | 0.875 | -0.0094 | coverage 0.9525 | 0.95 | yes |
| ICC(3,1) 95% CI (McGraw & Wong) | n=30, k=3, var_s=0.7, var_session=0.0, var_e=0.3 | 0.700 | -0.0121 | coverage 0.9495 | 0.95 | yes |
| ICC(3,k) 95% CI (McGraw & Wong) | n=30, k=3, var_s=0.7, var_session=0.0, var_e=0.3 | 0.875 | -0.0095 | coverage 0.9495 | 0.95 | yes |
| ICC(1,1) 95% CI (McGraw & Wong) | n=30, k=3, var_s=0.7, var_session=0.0, var_e=0.3 | 0.700 | -0.0120 | coverage 0.9520 | 0.95 | yes |
| ICC(1,k) 95% CI (McGraw & Wong) | n=30, k=3, var_s=0.7, var_session=0.0, var_e=0.3 | 0.875 | -0.0093 | coverage 0.9520 | 0.95 | yes |
| ICC(2,1) 95% CI (generalized CI) | n=30, k=3, var_s=0.7, var_session=0.0, var_e=0.3 | 0.700 | -0.0120 | coverage 0.9600 | 0.95 | yes |
| ICC(2,k) 95% CI (generalized CI) | n=30, k=3, var_s=0.7, var_session=0.0, var_e=0.3 | 0.875 | -0.0094 | coverage 0.9600 | 0.95 | yes |
| ICC(2,1) 95% CI (McGraw & Wong) | n=15, k=4, var_s=0.8, var_session=0.0, var_e=0.2 | 0.800 | -0.0186 | coverage 0.9485 | 0.95 | yes |
| ICC(2,k) 95% CI (McGraw & Wong) | n=15, k=4, var_s=0.8, var_session=0.0, var_e=0.2 | 0.941 | -0.0091 | coverage 0.9485 | 0.95 | yes |
| ICC(3,1) 95% CI (McGraw & Wong) | n=15, k=4, var_s=0.8, var_session=0.0, var_e=0.2 | 0.800 | -0.0189 | coverage 0.9445 | 0.95 | yes |
| ICC(3,k) 95% CI (McGraw & Wong) | n=15, k=4, var_s=0.8, var_session=0.0, var_e=0.2 | 0.941 | -0.0092 | coverage 0.9445 | 0.95 | yes |
| ICC(1,1) 95% CI (McGraw & Wong) | n=15, k=4, var_s=0.8, var_session=0.0, var_e=0.2 | 0.800 | -0.0186 | coverage 0.9465 | 0.95 | yes |
| ICC(1,k) 95% CI (McGraw & Wong) | n=15, k=4, var_s=0.8, var_session=0.0, var_e=0.2 | 0.941 | -0.0091 | coverage 0.9465 | 0.95 | yes |
| ICC(2,1) 95% CI (generalized CI) | n=15, k=4, var_s=0.8, var_session=0.0, var_e=0.2 | 0.800 | -0.0186 | coverage 0.9565 | 0.95 | yes |
| ICC(2,k) 95% CI (generalized CI) | n=15, k=4, var_s=0.8, var_session=0.0, var_e=0.2 | 0.941 | -0.0091 | coverage 0.9565 | 0.95 | yes |
| ICC(2,1) 95% CI (McGraw & Wong) | n=30, k=3, var_s=0.7, var_session=0.1, var_e=0.2 | 0.700 | -0.0024 | coverage 0.9290 | 0.95 | yes |
| ICC(2,k) 95% CI (McGraw & Wong) | n=30, k=3, var_s=0.7, var_session=0.1, var_e=0.2 | 0.875 | -0.0057 | coverage 0.9290 | 0.95 | yes |
| ICC(3,1) 95% CI (McGraw & Wong) | n=30, k=3, var_s=0.7, var_session=0.1, var_e=0.2 | 0.778 | -0.0099 | coverage 0.9465 | 0.95 | yes |
| ICC(3,k) 95% CI (McGraw & Wong) | n=30, k=3, var_s=0.7, var_session=0.1, var_e=0.2 | 0.913 | -0.0063 | coverage 0.9465 | 0.95 | yes |
| ICC(2,1) 95% CI (generalized CI) | n=30, k=3, var_s=0.7, var_session=0.1, var_e=0.2 | 0.700 | -0.0024 | coverage 0.9580 | 0.95 | yes |
| ICC(2,k) 95% CI (generalized CI) | n=30, k=3, var_s=0.7, var_session=0.1, var_e=0.2 | 0.875 | -0.0057 | coverage 0.9580 | 0.95 | yes |
| ICC(2,1) 95% CI (McGraw & Wong) | n=20, k=2, var_s=0.6, var_session=0.2, var_e=0.2 | 0.600 | +0.0213 | coverage 0.9070 | 0.95 | known limitation (under-covers) |
| ICC(2,k) 95% CI (McGraw & Wong) | n=20, k=2, var_s=0.6, var_session=0.2, var_e=0.2 | 0.750 | +0.0027 | coverage 0.9070 | 0.95 | known limitation (under-covers) |
| ICC(3,1) 95% CI (McGraw & Wong) | n=20, k=2, var_s=0.6, var_session=0.2, var_e=0.2 | 0.750 | -0.0167 | coverage 0.9385 | 0.95 | yes |
| ICC(3,k) 95% CI (McGraw & Wong) | n=20, k=2, var_s=0.6, var_session=0.2, var_e=0.2 | 0.857 | -0.0163 | coverage 0.9385 | 0.95 | yes |
| ICC(2,1) 95% CI (generalized CI) | n=20, k=2, var_s=0.6, var_session=0.2, var_e=0.2 | 0.600 | +0.0213 | coverage 0.9580 | 0.95 | yes |
| ICC(2,k) 95% CI (generalized CI) | n=20, k=2, var_s=0.6, var_session=0.2, var_e=0.2 | 0.750 | +0.0027 | coverage 0.9580 | 0.95 | yes |
| ICC(2,1) 95% CI (McGraw & Wong) | n=50, k=3, var_s=0.9, var_session=0.05, var_e=0.05 | 0.900 | -0.0008 | coverage 0.8680 | 0.95 | known limitation (under-covers) |
| ICC(2,k) 95% CI (McGraw & Wong) | n=50, k=3, var_s=0.9, var_session=0.05, var_e=0.05 | 0.964 | -0.0009 | coverage 0.8680 | 0.95 | known limitation (under-covers) |
| ICC(3,1) 95% CI (McGraw & Wong) | n=50, k=3, var_s=0.9, var_session=0.05, var_e=0.05 | 0.947 | -0.0018 | coverage 0.9535 | 0.95 | yes |
| ICC(3,k) 95% CI (McGraw & Wong) | n=50, k=3, var_s=0.9, var_session=0.05, var_e=0.05 | 0.982 | -0.0007 | coverage 0.9535 | 0.95 | yes |
| ICC(2,1) 95% CI (generalized CI) | n=50, k=3, var_s=0.9, var_session=0.05, var_e=0.05 | 0.900 | -0.0008 | coverage 0.9550 | 0.95 | yes |
| ICC(2,k) 95% CI (generalized CI) | n=50, k=3, var_s=0.9, var_session=0.05, var_e=0.05 | 0.964 | -0.0009 | coverage 0.9550 | 0.95 | yes |
| ICC(2,1) 95% CI (McGraw & Wong) | n=200, k=3, var_s=0.9, var_session=0.05, var_e=0.05 | 0.900 | +0.0011 | coverage 0.7800 | 0.95 | known limitation (under-covers) |
| ICC(2,k) 95% CI (McGraw & Wong) | n=200, k=3, var_s=0.9, var_session=0.05, var_e=0.05 | 0.964 | -0.0001 | coverage 0.7800 | 0.95 | known limitation (under-covers) |
| ICC(3,1) 95% CI (McGraw & Wong) | n=200, k=3, var_s=0.9, var_session=0.05, var_e=0.05 | 0.947 | -0.0005 | coverage 0.9490 | 0.95 | yes |
| ICC(3,k) 95% CI (McGraw & Wong) | n=200, k=3, var_s=0.9, var_session=0.05, var_e=0.05 | 0.982 | -0.0002 | coverage 0.9490 | 0.95 | yes |
| ICC(2,1) 95% CI (generalized CI) | n=200, k=3, var_s=0.9, var_session=0.05, var_e=0.05 | 0.900 | +0.0011 | coverage 0.9500 | 0.95 | yes |
| ICC(2,k) 95% CI (generalized CI) | n=200, k=3, var_s=0.9, var_session=0.05, var_e=0.05 | 0.964 | -0.0001 | coverage 0.9500 | 0.95 | yes |
| ICC(2,1) 95% CI (McGraw & Wong) | n=50, k=6, var_s=0.9, var_session=0.05, var_e=0.05 | 0.900 | -0.0036 | coverage 0.9220 | 0.95 | known limitation (under-covers) |
| ICC(2,k) 95% CI (McGraw & Wong) | n=50, k=6, var_s=0.9, var_session=0.05, var_e=0.05 | 0.982 | -0.0009 | coverage 0.9220 | 0.95 | known limitation (under-covers) |
| ICC(3,1) 95% CI (McGraw & Wong) | n=50, k=6, var_s=0.9, var_session=0.05, var_e=0.05 | 0.947 | -0.0024 | coverage 0.9545 | 0.95 | yes |
| ICC(3,k) 95% CI (McGraw & Wong) | n=50, k=6, var_s=0.9, var_session=0.05, var_e=0.05 | 0.991 | -0.0005 | coverage 0.9545 | 0.95 | yes |
| ICC(2,1) 95% CI (generalized CI) | n=50, k=6, var_s=0.9, var_session=0.05, var_e=0.05 | 0.900 | -0.0036 | coverage 0.9485 | 0.95 | yes |
| ICC(2,k) 95% CI (generalized CI) | n=50, k=6, var_s=0.9, var_session=0.05, var_e=0.05 | 0.982 | -0.0009 | coverage 0.9485 | 0.95 | yes |
| Bland-Altman lower LoA 95% CI (ba1999) | n=20, bias=0.5, sd_diff=1.0 | -1.460 | +0.0258 | coverage 0.9535 | 0.95 | yes |
| Bland-Altman upper LoA 95% CI (ba1999) | n=20, bias=0.5, sd_diff=1.0 | 2.460 | -0.0311 | coverage 0.9420 | 0.95 | yes |
| Bland-Altman lower LoA 95% CI (exact) | n=20, bias=0.5, sd_diff=1.0 | -1.460 | +0.0566 | coverage 0.9440 | 0.95 | yes |
| Bland-Altman upper LoA 95% CI (exact) | n=20, bias=0.5, sd_diff=1.0 | 2.460 | -0.0318 | coverage 0.9470 | 0.95 | yes |
| Bland-Altman bias 95% CI (t) | n=20, bias=0.5, sd_diff=1.0 | 0.500 | +0.0124 | coverage 0.9540 | 0.95 | yes |
| Bland-Altman lower LoA 95% CI (ba1999) | n=60, bias=-1.0, sd_diff=2.0 | -4.920 | +0.0121 | coverage 0.9420 | 0.95 | yes |
| Bland-Altman upper LoA 95% CI (ba1999) | n=60, bias=-1.0, sd_diff=2.0 | 2.920 | -0.0225 | coverage 0.9475 | 0.95 | yes |
| Bland-Altman lower LoA 95% CI (exact) | n=60, bias=-1.0, sd_diff=2.0 | -4.920 | +0.0119 | coverage 0.9550 | 0.95 | yes |
| Bland-Altman upper LoA 95% CI (exact) | n=60, bias=-1.0, sd_diff=2.0 | 2.920 | -0.0206 | coverage 0.9440 | 0.95 | yes |
| Bland-Altman bias 95% CI (t) | n=60, bias=-1.0, sd_diff=2.0 | -1.000 | -0.0043 | coverage 0.9425 | 0.95 | yes |
| Lin CCC 95% CI (Fisher z) | n=30, shift=0.3, sd_ratio=1.0, rho=0.8 | 0.766 | -0.0138 | coverage 0.9350 | 0.95 | yes |
| Lin CCC 95% CI (Fisher z) | n=100, shift=0.0, sd_ratio=1.2, rho=0.9 | 0.885 | -0.0020 | coverage 0.9540 | 0.95 | yes |
| Hedges g 95% CI (noncentral_t) | n1=10, n2=12, delta=0.8 | 0.800 | -0.0056 | coverage 0.9460 | 0.95 | yes |
| Hedges g 95% CI (normal) | n1=10, n2=12, delta=0.8 | 0.800 | +0.0236 | coverage 0.9530 | 0.95 | yes |
| Hedges g 95% CI (noncentral_t) | n1=30, n2=30, delta=0.3 | 0.300 | -0.0015 | coverage 0.9460 | 0.95 | yes |
| Hedges g 95% CI (normal) | n1=30, n2=30, delta=0.3 | 0.300 | -0.0019 | coverage 0.9550 | 0.95 | yes |
| Cohen d_z 95% CI (noncentral t) | n=15, dz=0.5 | 0.500 | +0.0450 | coverage 0.9555 | 0.95 | yes |
| AUC 95% CI (DeLong) | n1=20, n2=25, shift=1.0 | 0.760 | +0.0006 | coverage 0.9275 | 0.95 | yes |
| AUC 95% CI (DeLong) | n1=50, n2=50, shift=0.5 | 0.638 | -0.0001 | coverage 0.9510 | 0.95 | yes |
| pearson r 95% CI (Fisher z) | n=25, rho=0.5 | 0.500 | -0.0047 | coverage 0.9475 | 0.95 | yes |
| spearman r 95% CI (Fisher z) | n=25, rho=0.5 | 0.483 | -0.0163 | coverage 0.9470 | 0.95 | yes |
| pearson r 95% CI (Fisher z) | n=80, rho=0.8 | 0.800 | -0.0014 | coverage 0.9580 | 0.95 | yes |
| spearman r 95% CI (Fisher z) | n=80, rho=0.8 | 0.786 | -0.0068 | coverage 0.9405 | 0.95 | yes |
| Cronbach alpha 95% CI (Feldt) | n=40, k=5, parallel items | 0.769 | -0.0097 | coverage 0.9530 | 0.95 | yes |
| TOST type-I error at margin (Welch) | n=20/group,  true diff = margin = 0.5 |  |  | rate 0.0010 | 0.05 | yes |
| TOST type-I error at margin (Welch) | n=60/group,  true diff = margin = 0.5 |  |  | rate 0.0465 | 0.05 | yes |
| Little MCAR type-I error under MCAR | n=150, p=3, 15% MCAR |  |  | rate 0.0470 | 0.05 | yes |
| MDC95 false-positive rate in stable subjects (estimated SEM) | n=40 calibration,  var_e=0.25 |  |  | rate 0.0578 | 0.05 | yes |
| ICC(3,1) point estimate, mixed-model REML, 15% MCAR | n=40, k=3, var_s=0.7, var_session=0.1, var_e=0.2 | 0.778 | -0.0019 | bias -0.0019 | 0.0 | yes |
| ICC(3,1) point estimate, complete-case ANOVA, 15% MCAR | n=40, k=3, var_s=0.7, var_session=0.1, var_e=0.2 | 0.778 | -0.0015 | bias -0.0015 | 0.0 | yes |
| ICC(2,1) point estimate, mixed-model REML, 15% MCAR | n=40, k=3, var_s=0.7, var_session=0.1, var_e=0.2 | 0.700 | -0.0020 | bias -0.0020 | 0.0 | yes |
| ICC(2,1) point estimate, complete-case ANOVA, 15% MCAR | n=40, k=3, var_s=0.7, var_session=0.1, var_e=0.2 | 0.700 | -0.0052 | bias -0.0052 | 0.0 | yes |

Notes: TOST is conservative at the margin when the standard error is large relative to the
margin (n = 20: 0.1 % rejections; n = 60: 4.7 %), as expected. Hedges g normal-approximation
intervals were adequate here, but the default is the exact non-central-t interval.

## 10. References

* Bland JM, Altman DG (1986) Lancet 327:307–310. · (1999) Stat Methods Med Res 8:135–160 [PK].
* Bonett DG, Wright TA (2000) Psychometrika 65:23–28 [PK].
* Carkeet A (2015) Optom Vis Sci 92:e71–e80 [PK].
* Cronbach LJ (1951) Psychometrika 16:297–334 [PK]. · Feldt LS et al. (1987) Appl Psychol Meas
  11:93–103 [PK].
* DeLong ER et al. (1988) Biometrics 44:837–845 [PK].
* de Vet HCW et al. (2006) J Clin Epidemiol 59:1033–1039 [PK]. · de Vet & Terwee (2010) J Clin
  Epidemiol 63:804–805 [PK].
* Fieller EC et al. (1957) Biometrika 44:470–481 [PK].
* Guyatt G et al. (1987) J Chronic Dis 40:171–178 [PK]. · Husted JA et al. (2000) J Clin
  Epidemiol 53:459–468 [PK]. · Kazis LE et al. (1989) Med Care 27:S178–S189 [PK]. · Liang MH
  (2000) Med Care 38:II84–II90 [PK].
* Hedges LV, Olkin I (1985) Statistical Methods for Meta-Analysis [PK].
* Holm S (1979) Scand J Stat 6:65–70. · Benjamini Y, Hochberg Y (1995) JRSS-B 57:289–300.
* Ionan AC et al. (2014) BMC Med Res Methodol 14:121 (CI methods for the ICC) [PK].
* Koo TK, Li MY (2016) J Chiropr Med 15:155–163 [PK].
* Lin LI (1989) Biometrics 45:255–268; correction (2000) 56:324–325 [PK].
* Little RJA (1988) JASA 83:1198–1202 [PK].
* McDonald RP (1999) Test Theory: A Unified Treatment [PK].
* McGraw KO, Wong SP (1996) Psychol Methods 1:30–46 [PK].
* Meredith W (1993) Psychometrika 58:525–543 [PK]. · Vandenberg RJ, Lance CE (2000) Organ Res
  Methods 3:4–70 [PK].
* Revicki D et al. (2008) J Clin Epidemiol 61:102–109 [PK].
* Schuirmann DJ (1987) J Pharmacokinet Biopharm 15:657–680 [PK]. · Lakens D (2017) Soc Psychol
  Personal Sci 8:355–362 [PK].
* Shrout PE, Fleiss JL (1979) Psychol Bull 86:420–428.
* Terwee CB et al. (2007) J Clin Epidemiol 60:34–42 [PK].
* Weerahandi S (1993) JASA 88:899–905 (generalized confidence intervals) [PK].
* Weir JP (2005) J Strength Cond Res 19:231–240 [PK].

## Design note: number of test–retest sessions (checked 2026-11-27)
With absolute-agreement ICC(A,1), the session (rater) variance is estimated with k−1 degrees of
freedom. With k = 2 sessions it has 1 df, so the generalized CI — which accounts for that
uncertainty and keeps nominal coverage when sessions differ systematically — is much wider than
the McGraw–Wong F-based CI. Example (30 simulated subjects, true ICC ≈ 0.8, small session shift):
k=2: F-CI lower 0.52 vs GCI lower 0.30; k=3: 0.67 vs 0.63; k=4: 0.77 vs 0.71. **Implication for
the validation plan:** use ≥3 sessions per participant in Stage 3 when absolute agreement is the
target, or pre-specify consistency ICC(C,1) as primary with a separate test of systematic session
effects (practice) if only 2 sessions are feasible.
