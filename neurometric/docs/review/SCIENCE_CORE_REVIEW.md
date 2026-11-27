# Science-core review: metrics, simulator, experiment analysis

Scope: `metrics/{pointing,text,session}.py`, `simulator/{decoder,engine,scanning,modalities,tasks}.py`,
`users/models.py`, `experiments/{analysis,core,registry}.py`, `docs/science/{METRICS,SIMULATOR}.md`,
and three test files. This is an independent, adversarial review. No source files were changed.
The demonstration scripts are in
`/tmp/claude-0/-home-user-concord/e99cb831-573d-524c-a881-af97df967193/scratchpad/review/` (d1–d16). Each run took under 2 minutes with a small n.

Severity: **critical** = puts wrong or misleading numbers into experiment outputs.
**important** = a definitional or design error that can mislead, or a robustness bug.
**minor** = small bias, documentation, or test gap.

---

## Critical

### C1. The latent "ability" is not monotone for velocity (BCI-like) users
`simulator/modalities.py:95` scales `kp` (feedback gain) up with ability (`speed = e^{σz}`). It also
scales the feedback delay down by `e^{-σz/2}`, so the loop gain × delay rises with z. Combined with the channel delay (latency, smoothing, hold), high-z users drive the closed loop towards oscillation, and they perform *worse*.
Demo d11 uses experiment M's exact design (ability −1/0/+1, bci_good, n=30):

| ability | ISO TP | ISO MT | grid time | grid bitrate |
|---|---|---|---|---|
| low | 0.92 | 3044 | 2246 | 2.02 |
| mid | 1.05 | 2836 | 2031 | 2.26 |
| **high** | **0.86** | **3754** | **2930** | **1.76** |

d12 shows the mechanism. With `kp` held at 3.0, the ordering becomes monotone: TP 0.81 / 1.07 / 1.25. d2 shows that within a normal population (σ=0.3), Spearman(z, grid_time) ≈ +0.03. Grid time is instead driven by kp·delay (ρ=0.62).
**Consequences:** experiment M's `eta2_ability` does not measure "person" variance. Experiment H's
`within_level_rho_with_latent_ability` uses a non-monotone ground truth. Any known-groups or latent-validity claim for BCI users is unsupported.
**Fix:** do not scale `kp` with ability (or bound kp·(fb+channel delay) below the stability margin). Add a precondition test that E[score | z] is monotone for every modality and profile before running M, H or I.

### C2. ISO throughput and MT summaries include invalid values and are censored by selection
`experiments/core.py:57` averages `tp_bps` regardless of `tp_valid`, so TP from 2 selections or with >50% errors is included. `core.py:63–71` takes means of MT, path efficiency, dial-in and similar metrics over *selected* trials only (timeouts are NaN), with timeouts censored at `step_max_ms=10 s`.
Demo d6 (B_noise sweep, bci_good, n=40):

| noise × | TP valid | mean TP reported | timeouts | MT (selected only) | MT (timeouts at 10 s) |
|---|---|---|---|---|---|
| 1 | 1.00 | 0.88 | 0.00 | 3217 | 3232 |
| 3 | **0.00** | 0.48 | 0.71 | 5318 | 8664 |
| 6 | **0.00** | 0.25 | 0.95 | **5179** | 9779 |

The TP values reported for noise ≥3 are entirely invalid estimates, some from n=0–2 selections. MT *decreases* as degradation increases because slow trials drop out. Both effects feed `sweep_properties` (rho, monotone_frac, AUC) and the G ranking.
**Fix:** set TP to NaN when `!tp_valid` (or carry `iso_tp_valid_frac` and exclude it in the property analysis). Report MT as a censored outcome (restricted mean with timeouts at the cap, or a survival/Kaplan–Meier median). Always pair MT with the timeout rate.

### C3. E_drift: tracking starts at session minute 0, and every task restarts the session clock
`simulator/tasks.py:236` builds `DegradedChannel` without `session_minutes`, and `core.py:103` does not pass it. So in E_drift (`session_minutes_start=10`) tracking runs at t≈0–0.25 min while all other tasks run at 10 min.
Demo d10 (k=4): tracking RMS is **85 px as run vs 349 px** if started at 10 min like the other tasks. Grid accuracy at 10 min is 0.00.
Tracking metrics will therefore look insensitive to calibration deterioration, purely because of this plumbing gap. In addition, `battery_scores` creates a new `Simulation` per task, each starting at the same `session_minutes` (`core.py:50,73,84,94`). "Deterioration over session time" therefore acts only within each task, and the drift direction is re-randomised per task.
**Fix:** thread `session_minutes` into `run_tracking`. Carry one session clock (and decoder state) across the battery, or document per-task resets.

### C4. Scanning modalities ignore the virtual population
`rt_scale` is never passed by `battery_scores` (`core.py:73,84,94`), and `run_grid`, `run_typing` and `run_adl` default it to 1.0 (`tasks.py:109,201,355`). Every scanning "participant" is therefore identical.
Demo d1 (switch_scan_sim, n=40): test–retest ICC(A,1) = **0.10** (grid time) and **0.005** (bitrate). Correlation with latent z is about 0. For bci_good on the same machinery the ICC is 0.98.
The L `retest_icc` values for scanning are artefacts. The claim of the "same virtual population across modalities" does not hold for scanning.
**Fix:** derive `rt_scale` (and miss probability) from the sampled person (for example `rt_scale = users.reaction_ms / base.reaction_ms`) and pass it through `battery_scores`.

### C5. Simulated WPM and CCPM start the clock at phrase onset, not at the first keystroke
`tasks.py:206` accumulates the first key's acquisition time into `t`, and then `text_entry_metrics` applies `(|T|−1)/S`. METRICS.md §2 says "S from first keystroke", and recorded sessions do exactly that (`study/scoring.py:284`).
Demo d4 (16-character phrase): mouse_sim WPM is 14.93 vs 15.73 (**−5.1%**), and bci_good is −3.6%. Simulated and recorded WPM are not comparable, and the "~15 WPM" calibration claim is affected.
**Fix:** record the time of the first keystroke and pass `t_last − t_first` (CCPM needs the same change).

## Important

**I1. Tracking-lag estimator is biased towards 0** (`metrics/session.py:120`). It uses an unnormalised dot product over a shrinking overlap on non-stationary windows. Demo d7, with a noiseless pure delay over a 12 s window: true 200 ms gives a mean of 137 (5–95%: 30–200). True 500 ms gives 432. True 1000 ms gives 926. Using `np.corrcoef` per lag (d7b) recovers 200 and 500 exactly. Fix: use a normalised per-lag correlation, and fit both axes.

**I2. `run_typing` can loop forever** (`tasks.py:174–189`). The only abort is `len(stream) > 3·|P|`, and keystrokes never accumulate if no selection is produced. Demo d16: with all selections blocked, 4589 key attempts (918 s simulated) for "hi" and still running. Near-zero selection rates (E_drift k=4, noise ×6) make runs extremely long. Aborted phrases are also scored without a flag. Fix: cap attempts or simulated time per phrase, and add an `aborted` column.

**I3. Experiment H compares designs under different task rules.** `adaptive_grid` uses `end_on_empty=True` (`registry.py:480`), while fixed grids use `False` (`tasks.py:123`). Demo d5 (40 px items, noise ×2): accuracy 0.344 vs 0.285 for the same people. In addition, with 30 trials and a ×1.25 step from 100 px, at noise 0 **78%** of participants have fewer than 2 reversals. For them, `thr` falls back to the final clipped size of 16 px (`registry.py:496`), so the adaptive ceiling is a truncation artefact (d13). Fix: use the same empty-click rule in both designs, run more trials or use a larger initial step, use an even number of reversals, and flag participants with fewer than 4 reversals.

**I4. `latency_jitter_ms` does not do what its docstring and SIMULATOR.md say.** They describe "Exp(mean) extra latency", but the code takes the per-tick draw combined with the monotone `read = max(read, last_read)` (`decoder.py:236–242`), which is effectively a running minimum. Demo d3 (fixed delay 50 ms): nominal +20/+50/+100/+200 ms gives a realised mean extra of +13/+23/+35/+51 ms. No current experiment uses it, but any future sweep would be mislabelled. Fix: draw the jitter per packet (renewal process), or document the realised distribution and test its mean.

**I5. Cross-modality comparisons (L) are not like-for-like:**
- Dwell (800/1000 ms) is inside MT, TP, grid time and WPM, and the `dwell` TP flag is dropped in aggregation (`core.py:57–58` keeps only `tp_valid_frac`).
- Selection-channel degradations (false or missed selections) do not exist for dwell modalities.
- The scanning typing layout pads every row to 10 columns (`tasks.py:165`), so late activations land on empty cells (no keystroke, time spent).
- Scanning `false_activations` is the injected **ground-truth** count `r["false"]` (`tasks.py:114`). For pointers it is the observable empty-space count. This breaks the observable-only rule; it is currently 0 only because `false_per_min=0`.
- Mouse, gaze and head users never make an ISO error (d15: error rate 0.000), so the speed–accuracy trade-off is not modelled.
- With 8 modality means, Kendall τ rank concordance is fragile.

**I6. Both default ISO conditions have the same ID.** 256/48 and 512/96 both give ID = log2(6.33) = 2.66 (`core.py:39`). "TP = mean over conditions" is therefore TP at a single ID, which is not comparable to literature ISO TP averaged over a range of IDs (the calibration claims in SIMULATOR.md:51–58). Fix: use conditions that span IDs of about 2–5.

**I7. The retest and responsiveness design gives upper bounds that could be over-read.** rep 0 and rep 1 differ only in the noise stream: same person parameters, same decoder, no day-level variance. ICC (sweeps, I, L), MDC (I, K) and "frac_stable_exceeding_mdc" are therefore optimistic. Paired d_z (`analysis.py:72–80`) with a threshold of 0.5 ("min_detect") is inflated by the same pairing, and it is not on Cohen's d scale. G's "sensitivity" (pooled Spearman across participants) mixes between-person spread with responsiveness. State these caveats in the summaries.

**I8. SIMULATOR.md over-claims test coverage.** SIMULATOR.md:44–47 says "Each parameter is verified by a unit test". There are no tests for `smoothing_tau_ms`, `quantization`, `direction_bins`, `loss_of_control*` and `recovery_ms`, `gain_decay_per_min`, `noise_growth_per_min`, `dims`, the position-mode transforms, the mask/inactive invariance, or the magnitude of the jitter. `test_latency_jitter_never_reorders` would also pass with zero jitter. SIMULATOR.md:72 mentions simulated "learning", which is not implemented. `GazeUser` ignores `fatigue_per_min`.

## Minor

- M1. `adapters/sessions.py:88–89` appends the click as an extra trajectory sample. Recorded-path MV/ME/MO then differ from direct scoring by up to 0.13 px (d14). `tests/test_events_adapters.py:158` omits these keys, so the test hides this. `trial_end.meta.selected_item` is documented as used but is ignored.
- M2. Dwell fires after `dwell_ms + dt`, because the counter starts at 0 on the entry tick (`engine.py:169–172`).
- M3. The C_latency axis says "added latency", but `latency_ms=L` replaces the base 60 ms (`registry.py:36`). The G comment says the heatmap shows d_first, but it plots rho (`registry.py:120`). `mean_monotone_frac` includes B4_gain while the sensitivity means exclude it.
- M4. The AR(1) noise starts at 0 in every new Simulation (`decoder.py:105`), so each task's first ~τ is under-noised. Initialise from the stationary distribution.
- M5. The ISO ring step k→k+7 of 13 gives an inter-target distance of D·sin(7π/13) = 0.993·D (`tasks/battery.py:244`). This varies with `n_targets` in experiment I (0.951·D at 5 targets), which slightly confounds the length effect.
- M6. TAC, MDC and ODC count raw 10 ms sign changes, so they depend on noise and sampling rate. METRICS.md notes this only for submovements.
- M7. IF counts correct-but-erased characters (original S&M 2003 definition). Note the Wobbrock & Myers 2006 refinement in METRICS.md.
- M8. `session_summary` (`metrics/session.py:165–167`) can pair two PAUSEs with one RESUME, which double-counts rest time.
- M9. `run_adl` does not count wrong selections during "back" recovery, and pressing "back" on step >0 does not navigate (`tasks.py:362–368`).
- M10. There is no spatial-outlier rule for We. False selections near the start (dx ≈ −D) inflate We; consider the MacKenzie & Isokoski outlier criterion, or at least a flag.
- M11. In `test_metrics_analytic.py:127` the comment says "<bs><bs>" but the stream has one backspace. Missing tests: TRE, TAC and MDC with known counts; exclusion of timeouts from TP; a non-collinear start for dx; collateral IF.

## Checked and found correct

- We = √(2πe)·SD = 4.133·SD. De is the mean projected amplitude from the actual start (the previous selection). IDe = log2(De/We+1). TP = IDe/MT. Hits and misses are included and timeouts excluded and flagged.
- Wolpaw bits (with 0 for P ≤ 1/N) and achieved bitrate log2(N−1)·max(Sc−Si,0)/t.
- MSD (Levenshtein). C = max(|P|,|T|) − MSD. INF = MSD. IF = |IS| − F − |T| (exact, even with backspace on an empty buffer). Corrected, uncorrected and total ER. KSPC. WPM formula (the formula itself; see C5 for the clock).
- TRE = entries − 1. TAC as sign changes of the perpendicular offset. MDC and ODC as sign changes of perpendicular and parallel velocity (the common FittsStudy reading of MacKenzie et al. 2001). MO/ME/MV. Overshoot uses the box support function, consistent with the square hit test.
- NaN padding and masking up to selection, timeouts (efficiency NaN), and the zero-path guard.
- ICC(A,1) matches pingouin ICC(A,1) to 1e-15. AUC orientation (`1−auc(a,b)` = P(lower degradation better)). Paired d_z sign and the zero-SD branch. Spearman–Brown alignment in exp_I (verified that the SB prediction equals the ICC at L0). SEM/MDC95 formulas. Guyatt RI and SRM. 2-down/1-up update and reversal logic (converges near 0.71: observed 0.74).
- Decoder: identity is exact. AR(1) is stationary with SD as specified. Gain, bias and asymmetry order. Sample-and-hold. Fixed latency. Selection latency (exactly sl ticks). Miss, block and false-selection accounting. Dropout and LOC Markov episodes. Recovery ramp. Inactive elements do not move, select, or advance `t_min`. Ground-truth `gt_*` fields are never consumed by pointer, typing or ADL metrics (scanning is the exception, I5).
- ISO ordering (k → k+⌈n/2⌉ mod n), end-on-any-selection, and TP per participant pooled over 12 selections. The typing correction logic (notice → backspace, accepted unnoticed errors, retyping after an unintended backspace). Row-column scanning timing and late-reaction landing (tests pass analytically).
- Calibration: mouse TP 4.05, gaze 2.38 (includes dwell) and mouse WPM ~15 match SIMULATOR.md. bci_good TP is 1.06 vs the stated ≈1.2.
