# Measurement properties of input-agnostic digital function metrics in simulation: reliability versus test length, responsiveness, floor and ceiling effects, adaptive difficulty, cross-modality comparability, person-versus-device variance and missing data

> **MANUSCRIPT DRAFT v0.1 (2026-11-27). Not submitted.** Companion to
> `P1_simulated_decoder_framework.md` (framework and sweeps). All NeuroMetric results are
> **synthetic**: simulated virtual participants under simulated input conditions. They describe how
> the metrics and statistics behave under stated assumptions; they are not estimates of human
> reliability, validity or responsiveness. Numbers carry their source file; `[RESULT PENDING: …]`
> marks results not yet written by the running study when this draft was finished. Authors and
> competing interests: `[AUTHORS]` (the founder's company interest must be declared).

---

## Abstract (to finalise when results are complete)

**Background.** Before a digital function battery for brain-computer interface (BCI) and
assistive-technology (AT) users is validated in people, design choices must be made: how many
trials per task, whether difficulty should adapt, how to compare scores across input modalities,
how to handle incomplete sessions, and which confidence intervals to trust. **Methods.** Using a
closed-loop simulator with virtual participants whose latent ability is known, we estimated (I)
test–retest ICC(A,1) at 4–32 trials per task against the Spearman–Brown prophecy; (K)
responsiveness to a known decoder improvement; (H) floor/ceiling and discrimination of fixed versus
adaptive (2-down/1-up staircase) difficulty; (L) the same battery across eight simulated
modalities; (M) the share of score variance due to device versus user ability; and (N) bias from
incomplete sessions under three missingness mechanisms. We also verified the statistical
implementation in 86 known-truth Monte-Carlo scenarios (R). **Results.** All 86 verification
scenarios passed the pre-set rule; the McGraw–Wong interval for absolute-agreement ICCs
under-covered (78.0% at n = 200, k = 3 with a small session effect) while a generalized
confidence interval held 95.0% (`experiments/results/R_statistical_verification/coverage_results.json`).
[RESULT PENDING: experiments/results/{I_test_retest,K_responsiveness,H_adaptive,L_cross_modality,M_user_variability,N_missing_data}/ — one sentence each]. **Conclusions.** [to write from results].

---

## 1. Introduction

Performance-based outcome measures for BCI and AT users are single observed metrics computed over
many trials (throughput, achieved bitrate, typing rate, time to complete a digital activity). Their
measurement properties — reliability, measurement error, responsiveness, floor and ceiling effects,
comparability across input methods — are defined by COSMIN for outcome measurement instruments,
including performance-based ones (Mokkink et al. 2010, 10.1016/j.jclinepi.2010.02.006; Mokkink et
al. 2020, 10.1186/s12874-020-01179-5 [V-DOI]). In BCI research these properties are rarely
reported: reviews show that studies mostly report decoding and task performance, not validated
clinical outcomes (Dohle et al. 2025) [V], and the newest functional instruments are still at the
content-validity stage (Sawyer et al. 2025) [V].

Human validation studies with AT users are small (often 15–45 participants per site), slow and
burdensome, so design errors are costly. Typical mistakes are predictable: too few trials for a
reliable score, tasks that are too easy for some users and too hard for others, ICC intervals that
are too narrow, and complete-case summaries of sessions that ended early for reasons related to
performance. A simulator in which the truth is known can show the size of these problems before
any participant is enrolled. This paper reports those simulations for the NeuroMetric battery and
the statistical verification of its psychometric library.

---

## 2. Methods

### 2.1 Simulator, virtual participants and battery
As in P1 (§2.1–2.5): 10-ms closed-loop simulation; velocity-control feedback users for BCI-like
cursors, minimum-jerk submovement users for mouse- and head-pointer-like input, gaze users with
dwell, and row-column switch scanning. Each virtual participant has a latent ability z ~ N(0, 1)
that scales speed (× e^{σz}) and noise and delays (× e^{−σz}) with idiosyncratic log-normal
variation (`simulator/modalities.py: sample_population`). All runs used `--n 60` virtual
participants per condition (`experiments/logs/full_run.log` command line); seeds are hashed from
(experiment, condition, replicate).

### 2.2 Study I: reliability versus test length
- **Design** (`experiments/registry.py: exp_I`): three simulated modalities (`bci_cursor_good_sim`,
  `bci_cursor_moderate_sim`, `mouse_sim`) × four test lengths L = 4, 8, 16, 32 trials × two
  sessions; ISO ring with one condition (D = 384 px, W = 64 px; ring geometry fixed at 13 targets, with L
  scored selections continuing around the ring) and a grid with L trials; latent-ability SD σ = 0.3.
- **Note:** the summary's design string says "80 virtual participants"; the run used `--n 60`,
  which overrides the function default. Report n from the data
  [RESULT PENDING: experiments/results/I_test_retest/data.csv — confirm n participants per cell].
- **Analysis**: ICC(A,1) per modality × length × metric (effective throughput, movement time, path
  efficiency, ISO error rate, grid accuracy, grid time, achieved bitrate); Spearman–Brown prediction
  from the shortest length, ρ_k = kρ₁/(1 + (k − 1)ρ₁); SEM = SD·√(1 − ICC); MDC95 = 1.96·√2·SEM.

### 2.3 Study K: responsiveness to a known change
- **Design** (`exp_K`): session 1 with the `bci_moderate` profile; at session 2 the first half of
  the virtual participants (assignment fixed in advance) receive an improved decoder (white and AR
  noise × 0.6, false selections 0.5/min, missed selections 0.05) and the second half are unchanged.
  With n = 60: 30 improved, 30 stable.
- **Analysis** per metric (oriented higher = better): standardised response mean in the improved
  group; Guyatt responsiveness index (mean change improved / SD of change in stable); AUC of change
  scores improved vs stable; ICC(A,1) and MDC95 from the stable group; proportion of improved and
  stable participants whose change exceeds the MDC95. The MDC is labelled a statistically
  detectable change, not a minimal clinically important difference.

### 2.4 Floor/ceiling across sweeps and Study H: adaptive versus fixed difficulty
- **Floor/ceiling** fractions at natural bounds (`METRIC_BOUNDS`) were computed in every sweep of
  P1 and pooled by Study G (maximum across sweeps). There is no separate experiment for this.
- **Study H** (`exp_H`): six noise levels (0, 1, 2, 4, 6, 8 × the P1 base noise) × 60 virtual
  participants × three designs: fixed grid with 100-px items, fixed grid with 40-px items (accuracy score), and a **2-down/1-up staircase on item size** (start 100 px, step
  × 1.4, bounds 6–116 px, 40 trials; the fixed grids also use 40 trials and the same empty-click
  rule after the review fixes; cell spacing fixed so only target size varies; threshold =
  geometric mean of the last 6 reversal sizes; score = −log(threshold), higher = better). A
  2-down/1-up rule converges near 70.7% correct (Levitt 1971 [PK]).
- **Analysis**: floor and ceiling fractions (fixed designs at 0 or 1; adaptive at the size bounds);
  Spearman ρ of score with device noise; mean within-level Spearman ρ with latent ability (does the
  design rank people correctly at a fixed device level?); minimum and mean AUC between adjacent
  noise levels.

### 2.5 Study L: cross-modality comparability
- **Design** (`exp_L`): eight simulated modalities (mouse, head pointer with 1000-ms dwell, eye
  gaze with 800-ms dwell, BCI good/moderate/poor, row-column scanning at 1000 ms and at 600 ms) ×
  60 virtual participants × 2 replicates, full sweep battery.
- **Analysis**: modality means; applicability (fraction of defined scores; ISO throughput and
  tracking are undefined for scanning; tracking is run only for velocity-control users); retest
  ICC(A,1) per modality; Kendall τ between modality rankings for six metrics applicable to all
  modalities (grid accuracy, grid time, achieved bitrate, CCPM, ADL completion, ADL time).

### 2.6 Study M: person versus device variance
- **Design** (`exp_M`): 3 latent-ability levels (z = −1, 0, +1, each with N(0, 0.3²) spread) × 3
  decoder profiles (`bci_good`, `bci_moderate`, `bci_poor`) × 60 virtual participants; ISO, grid,
  typing and ADL tasks.
- **Analysis**: two-way ANOVA (type II sums of squares) per metric; η² for ability, device,
  interaction and residual.

### 2.7 Study N: incomplete sessions
- **Design** (`exp_N`): 60 virtual participants, 24 scored ISO selections (D = 384, W = 64,
  `bci_moderate`, 10-s cap). Target missing fractions 0, 0.1, 0.25, 0.4, 0.6 under three
  mechanisms: **MCAR** (random trials missing); **MNAR, slow-abandon** (after a slow — > 1.5 × the
  person's median MT — or timed-out trial, the participant abandons the rest of the session with a
  probability scaled by the fraction); **MAR, fatigue-late** (later trials missing more often, the
  probability depending on the observed trial index).
- **Analysis**: complete-case per-person mean MT and success rate versus the full-data values: bias,
  RMSE, Spearman correlation with the full-data ranking, and participants retained.

### 2.8 Study R: verification of the statistical implementation
`neurometric.psychometrics` was verified by (a) published worked examples, (b) independent
implementations and (c) known-truth Monte-Carlo simulation, 2000 replications per scenario, seed
20261127, with a pass rule |coverage − 0.95| ≤ 3·MCSE (+0.02 for large-sample approximations),
rejection rates ≤ α + tolerance, |bias| ≤ 0.03 (`docs/science/PSYCHOMETRICS.md` §9). Scenarios
included ICC forms with and without a systematic session variance, Bland–Altman limits of
agreement, Lin's CCC, Hedges g, d_z, AUC (DeLong), Pearson and Spearman CIs, Cronbach's alpha,
TOST, Little's MCAR test, MDC95 false-positive rate, and REML versus complete-case ICC under 15%
MCAR missingness. Generalized confidence intervals (GCI) for ICC(A,·) used generalized pivotal
quantities (Weerahandi 1993 [PK]).

---

## 3. Results (all synthetic)

### 3.1 Study R: statistical verification
**All 86 scenarios met the pre-set rule** (`experiments/results/R_statistical_verification/coverage_results.json`:
`n_rows` 86, `n_pass` 86; versions numpy 2.5.3, scipy 1.18.1, statsmodels 0.15.0; runtime 85.8 s).

Table 1. Coverage of 95% intervals for ICC(A,1) (2000 replications each; same file).

| n | k | Session variance (share of total) | True ICC(A,1) | McGraw–Wong coverage | GCI coverage | Mean width M&W | Mean width GCI |
|---|---|---|---|---|---|---|---|
| 20 | 2 | 0 | 0.50 | 0.9495 | 0.9605 | 0.671 | 0.689 |
| 30 | 3 | 0 | 0.70 | 0.9525 | 0.9600 | 0.305 | 0.370 |
| 15 | 4 | 0 | 0.80 | 0.9485 | 0.9565 | 0.299 | 0.336 |
| 30 | 3 | 0.1 | 0.70 | 0.9290 | 0.9580 | 0.386 | 0.590 |
| 20 | 2 | 0.2 | 0.60 | **0.9070** | 0.9580 | 0.644 | 0.764 |
| 50 | 3 | 0.05 | 0.90 | **0.8680** | 0.9550 | 0.258 | 0.528 |
| 200 | 3 | 0.05 | 0.90 | **0.7800** | 0.9500 | 0.234 | 0.510 |
| 50 | 6 | 0.05 | 0.90 | **0.9220** | 0.9485 | 0.155 | 0.223 |

- When sessions differ, the McGraw–Wong interval misses mostly by lying entirely **above** the true
  value (n = 200, k = 3: `miss_above` 0.215 versus `miss_below` 0.005). Its lower bound is too high,
  so it overstates how reliable a score can be claimed to be. Under-coverage worsens with n because
  the session variance has only k − 1 degrees of freedom; adding sessions (k = 6: coverage 0.922)
  helps more than adding subjects.
- Consistency forms (ICC(C,1), ICC(C,k)) and one-way forms covered nominally in all scenarios
  (0.9385–0.9545).
- Other checks: MDC95 false-positive rate in truly stable simulated people 0.0578 with SEM estimated
  from 40 calibration subjects (nominal 0.05); Little's MCAR test type-I error 0.047; TOST
  type-I error at the margin 0.001 (n = 20 per group, conservative) and 0.0465 (n = 60); ICC(A,1)
  point-estimate bias under 15% MCAR −0.0020 (REML) and −0.0052 (complete case); AUC DeLong
  coverage 0.9275 (n = 20 vs 25) and 0.951 (50 vs 50); Hedges g non-central-t coverage 0.946 in both
  scenarios (all from `coverage_results.csv`).
- Discrepancies with other software found during verification (documented in
  `docs/science/PSYCHOMETRICS.md` §9.2): pingouin rounds ICC CIs to two decimals; pingouin's
  normal-approximation interval for Hedges g uses a t quantile; scipy's non-central t CDF returned
  NaN far in the tail, so the CI inversion uses a reflection identity.

**Implication.** For absolute-agreement reliability, report the GCI as the inferential interval
and plan ≥ 3 test sessions after familiarisation; increasing n alone does not fix coverage.

### 3.2 Study I: reliability versus test length
[RESULT PENDING: experiments/results/I_test_retest/reliability.csv — Table 2: ICC(A,1) at L = 4/8/16/32 for iso_tp_bps, grid_bitrate_bps, iso_mt_ms, grid_accuracy in each modality, with the Spearman–Brown prediction and MDC95; Figure: experiments/results/I_test_retest/reliability_vs_length.png]

Reading rule written in advance: a metric "follows Spearman–Brown" if the observed ICC at L = 32
is within 0.05 of the prediction from L = 4; a metric whose ICC stays low at L = 32 has a
structural problem (ceiling, low between-person variance), not a length problem.

### 3.3 Study K: responsiveness
[RESULT PENDING: experiments/results/K_responsiveness/responsiveness.csv — Table 3: top 8 metrics by auc_improved_vs_stable with srm_improved, guyatt_ri, icc_stable, mdc95, frac_improved_exceeding_mdc, frac_stable_exceeding_mdc; Figure: experiments/results/K_responsiveness/responsiveness_auc.png]

### 3.4 Floor/ceiling and adaptive difficulty
From the noise sweep: pooled over 7 levels (`experiments/results/B_noise/summary.json`, 07:35Z), ceiling fractions were
89.8% for digital-ADL completion, 58.3% for grid accuracy and 27.9% for ISO success rate; floor
fractions were 83.8% for ADL wrong selections, 56.0% for empty-space selections per minute and
53.1% for typing total error rate. Rate metrics had less floor: achieved bitrate 5.2% and CCPM
10.7%. Effective throughput was undefined (validity conditions failed) in 42.4% of sessions. Each is judged against the 15% criterion (Terwee et al. 2007, 10.1016/j.jclinepi.2006.03.012 [V-DOI]). Note that after the review fixes false-activation metrics are NaN (not observable) for switch scanning.
Cross-sweep maxima:
[RESULT PENDING: experiments/results/G_metric_comparison/ranking.csv — max_floor_frac and max_ceiling_frac per metric across all sweeps].

Adaptive staircase versus fixed grids:
[RESULT PENDING: experiments/results/H_adaptive/comparison.csv — Table 4: floor_frac, ceiling_frac, rho_with_device_noise, within_level_rho_with_latent_ability, min_adjacent_auc, mean_adjacent_auc for fixed_large_100px, fixed_small_40px and adaptive_size_threshold; Figure: experiments/results/H_adaptive/fixed_vs_adaptive.png]

### 3.5 Study L: cross-modality comparability
[RESULT PENDING: experiments/results/L_cross_modality/summary.json — modality means for grid_bitrate_bps, type_ccpm, adl_time_s, grid_accuracy; rank_concordance_kendall_tau; per-modality retest ICC from retest_icc.csv; Figure: experiments/results/L_cross_modality/modalities.png]

### 3.6 Study M: person versus device variance
[RESULT PENDING: experiments/results/M_user_variability/variance_decomposition.csv — η² device, ability, interaction, residual for iso_tp_bps, grid_bitrate_bps, type_ccpm, adl_time_s, adl_completion_rate; Figure: experiments/results/M_user_variability/variance_decomposition.png]

### 3.7 Study N: incomplete sessions
[RESULT PENDING: experiments/results/N_missing_data/results.csv — Table 5: actual_missing_frac, mt_bias_ms, mt_rmse_ms, success_bias, mt_rank_corr_with_full by mechanism at target 0.1/0.25/0.4/0.6; Figure: experiments/results/N_missing_data/missing_bias.png]

---

## 4. Discussion (outline; complete with results)

1. **Intervals.** Study R shows that the most widely used absolute-agreement ICC interval is
   anti-conservative exactly when practice or recalibration shifts session means, which is the
   usual situation in BCI and AT studies. Test–retest designs should include familiarisation, ≥ 3
   test sessions and a GCI; ICC(C,1) should be reported beside ICC(A,1) because their gap measures
   systematic change.
2. **Test length** (I): [to write].
3. **Responsiveness** (K): [to write; emphasise that MDC-based "detectable change" is not
   meaningful change].
4. **Saturation and adaptivity** (B, H): completion and accuracy saturate; [H result] — if the
   staircase removes floor and ceiling while preserving device discrimination, it is a candidate
   lower-demand variant for severe impairment (pre-specified fallback in the Phase I plan). Adaptive
   scores are on a different scale; comparability requires a fixed, versioned staircase rule.
5. **Cross-modality** (L): equal reliability and concordant rankings do not show that a score
   measures the same construct in each modality; that needs within-modality construct evidence.
6. **Person vs device** (M): [to write; relevance: a score dominated by device variance is
   suited to device comparison, one dominated by ability to tracking a person].
7. **Missing data** (N): [to write; expected: complete-case summaries are biased when people stop
   after failures; mixed models under MAR plus tipping-point sensitivity analyses].

## 5. Limitations
An independent science-core review found five critical simulator defects (ability scaling of the
feedback gain, averaging of invalid throughput and timeout-censored MT, session clock restarting
per task, scanning ignoring the population, typing timed from phrase onset) and several important
ones (tracking-lag bias, staircase floor, unequal empty-click rules between adaptive and fixed
grids, identical ISO conditions, ring geometry varying with length in Study I, retest sessions
differing only in noise). All were fixed with regression tests and all results regenerated
(`docs/review/RESPONSE_TO_SCIENCE_CORE_REVIEW.md`); results from before the fixes are not used.
Synthetic data only; one latent-ability structure (σ = 0.25–0.3) plus day-to-day within-person variation
(log-normal SD 0.10) generates the variance components, so simulated ICCs are upper bounds, not
predictions for humans; short simulated tasks; simple gaze and scanning
models; no learning across sessions except where explicitly modelled; Study R verifies software
against known truth, not the appropriateness of the models for a given dataset; the founder has a
commercial interest. Internal consistency (alpha/omega) is deliberately not computed across task
metrics because they are formative and partly trade off (speed–accuracy).

## 6. Reproducibility
```bash
python -m neurometric.experiments.registry I_test_retest K_responsiveness L_cross_modality \
    M_user_variability N_missing_data H_adaptive --n 60
python -m neurometric.psychometrics.verify_coverage --reps 2000
python -m pytest tests/test_psychometrics.py -q
```
Outputs in `experiments/results/<ID>/`. Psychometric specification: `docs/science/PSYCHOMETRICS.md`.

## 7. Candidate venues
*Behavior Research Methods* (simulation and psychometric methods; [PK] scope), *Journal of
NeuroEngineering and Rehabilitation* (methodology article), *IEEE TNSRE*, or *Assistive
Technology* (RESNA) for the floor/ceiling and adaptive-testing part. Requirements [PK]; see
`VENUES.md`. Study R alone could be a short statistical note (e.g. *BMC Medical Research
Methodology* [PK]) on ICC(A,1) interval coverage under session effects, after checking that
Ionan et al. 2014 (BMC Med Res Methodol 14:121 [PK]) has not already shown the same result.

## References
Bland JM, Altman DG 1986, 10.1016/S0140-6736(86)90837-8 · de Vet HCW et al. 2006,
10.1016/j.jclinepi.2005.10.015 · Guyatt G et al. 1987, 10.1016/0021-9681(87)90069-5 · Ionan AC et
al. 2014, BMC Med Res Methodol 14:121 [PK] · Koo TK, Li MY 2016, 10.1016/j.jcm.2016.02.012 · Levitt
H 1971, J Acoust Soc Am 49:467–477 [PK] · Little RJA 1988, JASA 83:1198–1202 [PK] · McGraw KO, Wong
SP 1996, 10.1037/1082-989X.1.1.30 · Mokkink LB et al. 2010, 10.1016/j.jclinepi.2010.02.006 ·
Mokkink LB et al. 2020, 10.1186/s12874-020-01179-5 · Shrout PE, Fleiss JL 1979,
10.1037/0033-2909.86.2.420 · Terwee CB et al. 2007, 10.1016/j.jclinepi.2006.03.012 · Weerahandi S
1993, JASA 88:899–905 [PK] · Dohle E et al. 2025, 10.1002/advs.202501912 [V] · Sawyer A et al. 2025,
10.1016/j.ebiom.2025.105732 [V].
