# A closed-loop simulated-decoder framework for evaluating the sensitivity of functional outcome measures for brain-computer interfaces

> **MANUSCRIPT DRAFT v0.1 (2026-11-27). Not submitted. Not peer reviewed.**
> - All NeuroMetric results are **synthetic** (simulated virtual users and simulated input
>   degradation) except the pipeline check on one public, non-human dataset (§2.9, §3.6). No human
>   data are reported. The paper must say this in the title page, abstract, results and
>   limitations.
> - Every number is followed by the file it comes from. `[RESULT PENDING: …]` marks results the
>   running study had not yet written when this draft was finished; they must be filled from the
>   named file before submission, and the text around them revised to match what the numbers show.
> - Author list, affiliations and competing interests: `[AUTHORS]`. The founder's company
>   interest must be declared. A faculty co-author with methods expertise is recommended before
>   submission.
> - Citations marked [PK] are from prior knowledge and must be checked against the source; DOIs
>   marked [V-DOI] were resolved via Crossref in `docs/research/methods_references.md`.

---

## Abstract (structured; ≈ 250 words; complete when results are final)

**Objective.** Functional outcome measures for brain-computer interfaces (BCIs) are increasingly
called for, but there is no standard way to check, before human studies, whether a candidate
measure responds to the device problems it should detect. We describe and evaluate a closed-loop
simulated-decoder framework for this purpose.

**Approach.** Virtual users with feedback-control, submovement, gaze and switch-scanning policies
operated an 18-task digital battery through a parameterised degradation channel (noise, latency,
dropout, drift, gain, bias, update rate, false and missed selections). Users perceived the
degraded cursor after a feedback delay and corrected for it. Metrics were computed only from
observable events. For each degradation type we swept severity over 60 virtual participants with
two independent replicates and estimated each metric's monotonic sensitivity, smallest detectable
level, floor and ceiling fractions and simulated test–retest agreement.

**Main results.** [RESULT PENDING: experiments/results/B_noise/summary.json — Spearman ρ of movement variability, achieved bitrate, CCPM and effective throughput with noise; ceiling fraction of digital-activity completion; ρ of onset and tracking lag]. [RESULT PENDING: experiments/results/G_metric_comparison/ranking.csv — one sentence on which metrics were sensitive across all degradation types and which were blind to latency/false activations]. An independent code review found five critical simulator defects, which were fixed before all results were regenerated. The scoring pipeline produced a speed–difficulty relation on a public macaque hand-cursor dataset (541 reaches; `experiments/results/X1_external_mc_rtt/summary.json`).

**Significance.** Simulation cannot establish reliability or validity in people, but it can
expose measures that are structurally blind, saturated or unstable, and it can guide which
measures and test lengths to carry into human validation.

---

## 1. Introduction

### 1.1 The measurement problem
Implanted and non-invasive BCIs now let people with paralysis control computer cursors, type and
speak through decoders [PK: Hochberg et al. 2006, 10.1038/nature04970; Pandarinath et al. 2017,
10.7554/eLife.18554; Willett et al. 2021, 10.1038/s41586-021-03506-2; Willett et al. 2023,
10.1038/s41586-023-06377-x — V-DOI]. Evidence that they improve what people can do in daily life
is thinner. A systematic review of 112 implanted-BCI studies (2000–2024) found that decoding and
task-performance outcomes dominated (69.6% and 62.5%), while 17.9% assessed clinical outcomes
(Dohle et al. 2025, 10.1002/advs.202501912) [V]. FDA's 2021 guidance for implanted BCIs asks for
a validated effectiveness endpoint with a minimal clinically important difference, home-use
evidence and measures of caregivers' ability to assist [V]. In 2025–2026 the field moved toward
patient-centred frameworks: a Digital Instrumental Activities of Daily Living scale reached the
content-validity stage (Sawyer et al. 2025, 10.1016/j.ebiom.2025.105732) [V]; a BCI Society
workshop report described the path from meaningful aspects of health to concepts of interest to
clinical outcome assessments (Sawyer et al. 2026, 10.1088/1741-2552/ae9eee) [V]; and the iBCI
Collaborative Community concluded that a single existing measure is unlikely to suffice and called
for a "shared measurement chain" from device performance to function to health outcome or care
burden [V].

### 1.2 Existing performance metrics and their assumptions
- **Wolpaw information transfer rate** assumes equiprobable targets, uniform errors and fixed trial
  time (Wolpaw et al. 1998, 10.1109/86.712231) [V-DOI]; these assumptions are routinely violated and
  ITR is often misreported (Yuan et al. 2013, 10.1088/1741-2560/10/2/026014) [V-DOI].
- **Achieved bitrate** penalises errors as if each needs one correction (Nuyujukian et al. 2015,
  10.1109/TBME.2014.2354697) [V-DOI]; industry "bits per second" grid scores are variants with
  grid- and click-type-dependent formulas [CC] (`docs/research/published_bci_functional_measures.md`
  §3.3).
- **Fitts throughput** under ISO 9241-411 is device-independent for pointing and has a canonical
  computation (Soukoreff & MacKenzie 2004, 10.1016/j.ijhcs.2004.09.001) [V-DOI] but depends on the
  index-of-difficulty range and the speed–accuracy instruction (Zhai 2004; Zhai, Kong & Ren 2004)
  [V-DOI].
- **Path accuracy measures** (target re-entries, task-axis crossings, movement variability;
  MacKenzie, Kauppinen & Silfverberg 2001, 10.1145/365024.365028) [V-DOI] describe trajectories but
  depend on sampling rate.
- **Text-entry measures** (WPM, CCPM, MSD and total error rate; Soukoreff & MacKenzie 2003,
  10.1145/642611.642632) [V-DOI] are communication-relevant but protocol-dependent.
- **Task completion and time** in simulated daily activities are face-valid but, as shown below,
  can saturate.
Tutorials recommend reporting at the level the user experiences (Thompson et al. 2014,
10.1088/1741-2560/11/3/035001) [V-DOI]. None of these sources tells a study designer, for a given
population and device, **which measure will move when a specific device property degrades**.

### 1.3 Simulation of BCI users
Closed-loop models treat the BCI user as a feedback controller who perceives the decoded cursor
with delay and corrects it (Willett et al. 2017, 10.1088/1741-2560/14/1/016001) [V-DOI]. Such
models and closed-loop human simulators with able-bodied users have been used to design and
compare decoders [PK: e.g. Cunningham et al. 2011, J Neurophysiol — verify]. Movement-science
models provide position-control policies: minimum-jerk submovements (Flash & Hogan 1985,
10.1523/JNEUROSCI.05-07-01688.1985) and stochastic optimised submovements (Meyer et al. 1988,
10.1037/0033-295X.95.3.340) [V-DOI]. Rate models exist for switch scanning (Damper 1984;
Koester & Levine 1994) and dwell gaze typing (Majaranta & Räihä 2002) [V-DOI]. We are not aware of
work that uses closed-loop simulation to evaluate **outcome measures** (rather than decoders)
across many degradation types and input modalities at once [INF; a systematic search must be
done before submission — see §6].

### 1.4 Aim
We present an open, reproducible framework that (i) injects controlled, unit-tested degradations
between simulated users and a digital task battery, (ii) computes metrics only from observable
events, and (iii) reports, for every metric × degradation pair, sensitivity, detectability,
saturation and simulated retest agreement. We illustrate it with a full sweep study and check the
scoring pipeline on real public movement data.

---

## 2. Methods

### 2.1 Software and determinism
NeuroMetric v0.1.0, Python 3.13.18, numpy 2.5.3, pandas 3.0.5 (versions are written into every
`summary.json`). The simulation runs in 10-ms ticks (`simulator/engine.py`, `DT_MS = 10`). Seeds are
derived as the first 64 bits of SHA-256 over (experiment id, condition, replicate)
(`experiments/core.py: seed_for`), so any single condition can be re-run in isolation and
results do not depend on process count or order. A virtual population is drawn from a separate
seed shared across conditions of an experiment, so the **same virtual people** are measured at
every severity level (paired design).

### 2.2 Canonical events and observable-only metrics
Each simulated step is converted to the same canonical event stream that the browser records
(pointer samples, selections, keystrokes, markers, assistance events). Metric functions take only
observable data; simulation ground truth (intended selection times, injected false activations,
dropout ticks) is stored separately and is used only to validate metrics (`DECISIONS.md` D-006).
Metric definitions: `docs/science/METRICS.md`; analytic unit tests:
`tests/test_metrics_analytic.py`.

### 2.3 Degradation channel
`DegradationConfig` (`simulator/decoder.py`; defaults = identity) transforms the user's intended
velocity (velocity mode) or displacement (position mode) and the selection channel:

| Group | Parameters (units) | Model |
|---|---|---|
| Geometry | gain, gain_decay_per_min; bias_deg; asymmetry | multiplicative gain decaying with session time; rotation of decoded direction; ±x asymmetry |
| Noise | white_noise (px/s or px); correlated_noise with correlated_tau_ms; noise_growth_per_min | i.i.d. Gaussian per tick per axis; stationary AR(1) with ρ = exp(−dt/τ); SD × (1 + g·t_min) |
| Drift | drift, drift_rate_per_min | constant plus growing additive bias in a fixed random direction |
| Temporal | smoothing_tau_ms; update_hz; latency_ms, latency_jitter_ms | exponential smoothing; sample-and-hold; delay line with Exp(mean) jitter that never reverses time |
| Availability | dropout_enter_per_s, dropout_mean_ms; loss_of_control_per_min, _mean_ms, recovery_ms | two-state Markov (Gilbert–Elliott) dropout (zero velocity / frozen position, selections blocked); intent not passed through, then gain ramps back |
| Selection | select_miss_prob; select_latency_ms; false_select_per_min | misses; delay; Poisson false activations when not intending |
| Discretisation | quantization, direction_bins; dims | magnitude/direction rounding; active axes |

Unit tests against analytic expectations exist for identity, latency shift, jitter never
reordering, white/AR noise SD and lag-1 autocorrelation, gain and bias geometry, asymmetry,
sample-and-hold rate, Markov dropout duty cycle, false-selection rate, miss probability,
selection latency, drift growth and determinism (`tests/test_simulator.py`). Smoothing,
quantisation, direction bins, gain decay, noise growth, loss of control and recovery, position-mode
gain and axis masking are **not yet unit-tested** (`docs/science/SIMULATOR.md`). The AR(1) noise
starts from its stationary distribution. Because jittered outputs are never reordered, realised
latency is below the nominal (nominal +200 ms jitter realises about +50 ms); realised latency is
reported.

Reference profiles (illustrative stress conditions, not models of any device):

| Profile | Settings |
|---|---|
| `bci_good` | white 30 px/s; AR(1) 40 px/s, τ 400 ms; smoothing 60 ms; latency 60 ms; update 50 Hz; false selections 0.3/min; miss 0.05; selection latency 60 ms |
| `bci_moderate` | white 60; AR 80, τ 500; smoothing 80; latency 100; 50 Hz; bias 10°; gain 0.85; false 1.0/min; miss 0.10; selection latency 100; dropout 0.02/s, mean 400 ms |
| `bci_poor` | white 100; AR 130, τ 600; smoothing 100; latency 150; 20 Hz; bias 20°; gain 0.7; drift 20; false 3.0/min; miss 0.2; selection latency 150; dropout 0.05/s, mean 800 ms; loss of control 0.5/min, mean 1500 ms, recovery 1000 ms |

### 2.4 Virtual users
| Model | Control | Mechanism | Key defaults (BCI-like user) |
|---|---|---|---|
| FeedbackUser | velocity | proportional control on perceived error (after feedback delay), speed limit, signal-dependent and constant motor noise, reaction delay; clicks when the perceived cursor has been inside the target for `settle_ms` and is slower than `select_speed` | reaction 300 ms; feedback delay 150 ms; kp 3.0 s⁻¹; vmax 700 px/s; motor noise 0.05; constant noise 3.0; settle 300 ms; select speed 200 px/s; select RT 150 ms |
| SubmovementUser | position | minimum-jerk submovements, endpoint SD = k·D/T, corrective submovement after a feedback delay if outside the target | mouse-like: reaction 220 ms, feedback delay 110 ms, sub_tmin 90 ms, sub_c 15, sub_k 0.10, clicks without visual verification with probability 0.6 (head-pointer-like: 0.3), giving realistic ≈ 3% ISO errors |
| GazeUser | position | saccade latency and saccade, fixational jitter, partial compensation of a visible offset; dwell selection | saccade 45 ms; jitter 7 px; offset compensation 0.6; dwell 800 ms |
| Scanning | discrete | row-column scanning on a 4 × 7 frequency-ordered layout without empty cells; log-normal reaction with a per-person scale drawn from the population; late reactions land on the next item; misses wrap the cycle; Poisson false activations (not observable, so false-activation metrics are NaN for scanning and the ground truth is kept separately) | scan period 1000 ms (or 600 ms) |
Source: `users/models.py`, `simulator/modalities.py`, `simulator/scanning.py`. Text-entry users
notice an error with probability 0.9 and correct it with backspace; ADL users press "back" after a
wrong selection and retry.

**Populations.** One latent ability z ~ N(0, 1) per virtual participant scales speed limits by
exp(σz) and noise and delay parameters by exp(−σz) (delays by its square root), plus independent
log-normal idiosyncratic variation per parameter (`sample_population`). The feedback gain is not
scaled with ability, because higher gain with sensorimotor delay destabilises the loop. Default
σ = 0.25 in the sweeps. z is the ground truth for reliability and known-groups analyses.
Repeated sessions add day-to-day within-person variation (log-normal SD 0.10 on speed, reaction,
motor noise and fixation jitter), so simulated retest differences are not only noise streams;
simulated ICCs remain upper bounds. Learning is not modelled.

**Calibration.** After the review fixes (40 virtual participants, battery defaults), mouse-like
users give ≈ 4.5 bit/s ISO throughput with ≈ 3% errors and ≈ 17.5 WPM on the on-screen keyboard;
`bci_good` ≈ 1.0 bit/s, grid achieved bitrate ≈ 2.3 bit/s and ≈ 29 correct characters/min;
row-column switch scanning at 1 s ≈ 3.3 WPM (`docs/science/SIMULATOR.md`). These sit inside broad
published ranges (ranges [PK]). **Calibration targets ranges, not individuals; no parameter is a
measured property of any device.**

### 2.5a Independent code review
Before the study reported here, an independent science-core review of the simulator and
experiment code (`docs/review/SCIENCE_CORE_REVIEW.md`) found five critical defects: (C1) latent
ability made velocity users worse because the feedback gain was scaled with ability; (C2) invalid
throughput values were averaged and timeouts censored movement time; (C3) tracking ran at session
minute 0 and every task restarted the session clock; (C4) switch scanning ignored the population;
(C5) typing rate was timed from phrase onset. Important issues included a tracking-lag estimator
biased toward 0, identical ID in both ISO conditions, unfair cross-modality comparisons (dwell
time in MT, unobservable scanning false activations, empty scan cells, no ISO errors for
position users) and a staircase that hit its floor. All were fixed with regression tests
(`tests/test_review_regressions.py`), and **every result was deleted and regenerated** after the
fixes (`docs/review/RESPONSE_TO_SCIENCE_CORE_REVIEW.md`). We report this because it shows how
easily simulation artefacts can masquerade as measurement findings.

### 2.5 Simulated battery
For every virtual participant and condition the sweep battery comprised
(`experiments/core.py: battery_scores`):
- **A2 ISO multidirectional ring**: two conditions (D = 256 px, W = 64 px; D = 512 px, W = 48 px;
  nominal ID 2.32 and 3.55 bits), 13 targets, 12 scored selections each; max 10 s per selection.
  Effective throughput per condition (We = 4.133·SD of projected endpoints; IDe = log2(De/We + 1);
  TP = IDe/MT), averaged over **valid** conditions only (NaN if none is valid; validity flags in
  `docs/science/METRICS.md`); movement time counts timeouts at the limit, with completed-trial
  MT reported separately; spatial outliers are flagged, not excluded; plus error, timeout and success rates, MT, path
  efficiency, re-entries, overshoot, movement variability, endpoint error, dial-in time,
  submovements and selection-process onset.
- **A4 grid**: 4 × 6 items (120 px cells, 100 px items), 12 cued trials, max 10 s; accuracy, mean
  time, achieved bitrate log2(N − 1)·max(Sc − Si, 0)/t; empty-space selections per minute.
- **E1 copy typing**: one phrase on a 90-px QWERTY keyboard, timed from first to last keystroke,
  with an attempt cap per phrase; WPM, CCPM, total and uncorrected error
  rates, KSPC, correction burden.
- **F2 compose-message digital ADL**: completion, time, wrong selections.
- **B2 tracking** (velocity users only): 15 s of a sum-of-sines target, radius 40 px, first 3 s
  excluded; RMS error, time on target, lag by cross-correlation.
All tasks share one session clock with 30 s of rest between tasks, so time-dependent degradation
(drift, calibration decay) accumulates across the battery. Tasks B1, C1 and D1 run in the browser
only and were not simulated.

### 2.6 Sweep design (Studies B–F)
| Study | Degradation (on `bci_good`, velocity BCI-like user unless stated) | Levels |
|---|---|---|
| B_noise | white × s and AR(1) × s (base 30 and 40 px/s) | s = 0, 0.5, 1, 2, 3, 4, 6 |
| C_latency | total decoder output latency (ms; the base profile has 60) | 0, 60, 120, 200, 300, 450, 700 |
| C2_latency_mouse | latency on an otherwise identity channel, position-control (mouse-like) user | 0, 60, 120, 200, 300, 450, 700 |
| D_dropout | dropout episodes per second (mean 500 ms) | 0, 0.05, 0.1, 0.2, 0.4, 0.8 |
| E_drift | calibration deterioration index k: drift rate 8k px/s/min, gain decay 0.01k/min, noise growth 0.03k/min, session starting at minute 10 | 0, 0.5, 1, 2, 4 |
| F_false_activation | false selections per minute | 0, 1, 2, 4, 8, 16 |
| F2_missed_selection | missed-selection probability | 0, 0.1, 0.2, 0.4, 0.6 |
| B2_bias | directional bias (deg) | 0, 15, 30, 45, 60 |
| B3_update_rate | decoder update interval (ms) | 10, 20, 50, 100, 200 |
| B4_gain | decoder gain (non-monotone; analysed against abs(log gain)) | 0.4, 0.6, 0.8, 1.0, 1.4, 2.0 |
Each: 60 virtual participants × levels × 2 replicates (`experiments/registry.py: SWEEPS`;
command in §7).

### 2.7 Metric properties
For each metric oriented so that higher = better (`METRIC_DIRECTION`), using replicate 0
(`experiments/analysis.py: sweep_properties`):
- **ρ**: Spearman correlation of score with severity (negative = appropriate direction);
- **monotone fraction**: share of adjacent level means moving in the expected direction;
- **d_first**: paired d_z between baseline and the first degraded level; **min_detect_level**: the
  lowest level with d_z ≤ −0.5;
- **auc_adjacent**: mean AUC separating adjacent levels;
- **undefined fraction**, **floor** and **ceiling** fractions at natural bounds
  (`METRIC_BOUNDS`), pooled over levels;
- **simulated retest ICC(A,1)** between replicates 0 and 1 at each level (two-way random,
  absolute agreement, single measure; complete cases).
Study G pools the properties across sweeps (excluding the non-monotone B4 gain sweep from the sensitivity and monotonicity means) into a ranking:
mean and worst-case sensitivity, mean monotone fraction, mean adjacent AUC, maximum undefined,
floor and ceiling fractions, and median and baseline retest ICC
(`experiments/registry.py: exp_G`).

### 2.8 Additional studies (reported in the companion paper P2)
Reliability versus test length (I), responsiveness to a known decoder improvement (K), the same
battery across eight simulated modalities (L), person-versus-device variance (M), missing data
(N), adaptive versus fixed difficulty (H) and reproducibility (P). Only their headline results are
cited here.

### 2.9 Pipeline check on real public data (X1)
NLB MC_RTT (DANDI:000129, CC-BY-4.0; single file SHA-256-verified against DANDI) contains one
session of a rhesus macaque moving a cursor **by hand** to random targets on an 8 × 8 grid, with
cursor, finger and target positions at 1 kHz (`docs/research/datasets.md`). The file was read
read-only; data were decimated to 100 Hz and converted to canonical events. A reach starts when
the target position changes and ends at the next change. Target width and hold rules are not in
the file, so throughput uses effective width only and success/error rates are not computed
(`experiments/external_mc_rtt.py`). Reaches were binned into distance quintiles for an
effective-width throughput per bin. This analysis checks the pipeline on real recorded behaviour;
it is not BCI control, not human and not clinical.

### 2.10 Statistical software verification
The psychometrics used downstream were verified separately (companion paper P2; 86/86 known-truth
scenarios passed, `experiments/results/R_statistical_verification/coverage_results.json`).

---

## 3. Results

All results in §3.1–3.5 are synthetic.

### 3.1 Noise (Study B)
[RESULT PENDING: experiments/results/B_noise/summary.json — n_trials_simulated and runtime_s]

Table 1. Properties of selected metrics under increasing noise.
[RESULT PENDING: experiments/results/B_noise/summary.json — rows (ρ, monotone fraction, d_z at first level, minimum detectable level, adjacent AUC, floor, ceiling, median retest ICC(A,1)) for iso_movement_variability_px, iso_submovements, iso_success_rate, iso_endpoint_error_px, type_ccpm, grid_bitrate_bps, iso_tp_bps, iso_mt_ms, adl_time_s, grid_accuracy, iso_path_efficiency, track_rms_px, false_activations_per_min, adl_completion_rate, iso_onset_ms, track_lag_ms; Figure 1: experiments/results/B_noise/sweep.png]

Pre-specified reading (written before the regenerated results): degradation-sensitive metrics
should have ρ ≤ −0.7 with monotone steps; bounded proportions (completion, accuracy on large
targets) are expected to saturate (> 15% of sessions at a bound) and to show low simulated retest
ICC because of little between-person variance; onset and tracking lag are not expected to respond
to noise but may respond to latency (Study C).

### 3.2 Latency (Studies C, C2)
[RESULT PENDING: experiments/results/C_latency/summary.json — Table 2 rows (ρ, monotone, min_detect_level, ceiling) for track_lag_ms, track_rms_px, iso_tp_bps, iso_dial_in_ms, grid_bitrate_bps, type_ccpm, adl_time_s; figure experiments/results/C_latency/sweep.png]

[RESULT PENDING: experiments/results/C2_latency_mouse/summary.json — same rows for the position-control user; contrast velocity vs position control]

### 3.3 Availability and selection faults (Studies D, F, F2)
[RESULT PENDING: experiments/results/D_dropout/summary.json — ρ for iso_timeout_rate, iso_mt_ms, grid_bitrate_bps, adl_time_s]

[RESULT PENDING: experiments/results/F_false_activation/summary.json — ρ for false_activations_per_min, grid_accuracy, grid_bitrate_bps, type_total_error_rate, adl_wrong_selections]

[RESULT PENDING: experiments/results/F2_missed_selection/summary.json — ρ for iso_mt_ms, iso_dial_in_ms, grid_time_ms, type_ccpm]

### 3.4 Calibration drift, bias, update rate, gain (Studies E, B2, B3, B4)
[RESULT PENDING: experiments/results/E_drift/summary.json — ρ for iso_tp_bps, iso_path_efficiency, grid_bitrate_bps, type_ccpm]

[RESULT PENDING: experiments/results/B2_bias/summary.json — ρ for iso_path_efficiency, iso_movement_variability_px, iso_tp_bps]

[RESULT PENDING: experiments/results/B3_update_rate/summary.json — ρ for track_rms_px, iso_tp_bps, iso_submovements]

[RESULT PENDING: experiments/results/B4_gain/summary.json — ρ against |log gain| for iso_tp_bps, iso_overshoot_px, iso_dial_in_ms]

### 3.5 Cross-degradation comparison (Study G)
[RESULT PENDING: experiments/results/G_metric_comparison/ranking.csv — Table 3: top 10 metrics by mean_sensitivity with min_sensitivity, mean_monotone_frac, max_ceiling_frac, median_retest_icc; Figure 2: experiments/results/G_metric_comparison/sensitivity_heatmap.png]

Pre-specified reading rule for Table 3 (written before the results, from
`docs/science/TASK_BATTERY.md`): a task stays in the core battery if it (a) responds monotonically
to at least one degradation type, (b) adds sensitivity to a degradation type that other tasks miss,
or (c) measures a functional construct (communication, activities) that the primitives do not.

### 3.6 Real public data (X1; not synthetic, not human)
From `experiments/results/X1_external_mc_rtt/summary.json`:
- 66,639 canonical events; 0 non-monotonic timestamps, 0 duplicate sequence numbers, 0 gaps.
- 541 reaches; median reach time 1110 ms; median path efficiency 0.866.
- Effective-width throughput by distance quintile (bins in mm): 1.32 bit/s (9.5–32.4 mm, n = 109),
  1.72 (32.4–47.2, n = 108), 1.97 (47.2–62.5, n = 108), 2.39 (62.5–78.9, n = 108), 2.37
  (78.9–114.5, n = 108); mean over bins 1.95 bit/s. Mean reach time rose from 1046 ms at IDe 1.38
  bits to 1345 ms at IDe 3.18 bits (`throughput_by_distance.csv`).
Figure 3: `experiments/results/X1_external_mc_rtt/mc_rtt_metrics.png` (reach-time and
path-efficiency distributions; reach time against effective ID).

### 3.7 Computational cost and reproducibility
[RESULT PENDING: experiments/results/B_noise/summary.json — runtime_s of the sweep]
[RESULT PENDING: experiments/results/S_event_latency/summary.json — server-side scoring time and JSON round-trip hash identity on a synthetic session; the file present at drafting predates the review fixes and must be regenerated].
[RESULT PENDING: experiments/results/P_reproducibility/summary.json — in-process vs pool hash identical; different seed differs].
In-page event capture (software path only, headless Chromium): 2,000 injected mouse events were
recorded with 0 missing, 0 duplicated and 0 order violations, and a synthetic 1000-Hz stream of
4,000 events with 0 drops (`experiments/results/A_input_timing/browser_summary.json`; this
excludes device, OS and display latency).

---

## 4. Discussion

### 4.1 What the framework shows (to be written from the regenerated results)
Expected structure of the argument, to be kept only if the numbers support it: (i)
**degradation-sensitive** kinematic and rate metrics that move early and monotonically; (ii)
**functional process** outcomes (completion, accuracy on large targets) that matter to users but
may saturate and therefore be blind to moderate degradation; (iii) metrics that are insensitive to
one degradation but specific to another (e.g. tracking lag and latency). If (ii) holds, a
completion score must be paired with time and assistance, or a harder/adaptive variant, before it
can detect change — the rationale for the proposed dADL time index
(`CLINICAL_VALIDATION_PLAN.md` §1.1).
[RESULT PENDING: experiments/results/G_metric_comparison/ranking.csv — rewrite this paragraph with the observed classes].
The review episode (§2.5a) is itself a result for the field: several defects (gain scaled with
ability, timeouts censoring MT, a lag estimator biased to 0) would have produced plausible-looking
but wrong conclusions about metric sensitivity.

### 4.2 Why closed loop matters
Because virtual users perceive the degraded cursor and correct it, constant bias and slow drift
are partly compensated and latency destabilises control, as in real users (`DECISIONS.md` D-005).
An open-loop noise model would misrank metrics for these degradations [INF; the open-loop
comparison was not run and is future work].

### 4.3 Relation to human validation
The framework is a filter, not a substitute: it identifies measures that cannot work (structurally
saturated or blind) and suggests test lengths, but reliability, validity and meaningful change
must come from people (planned in `CLINICAL_VALIDATION_PLAN.md`). Simulated retest ICCs depend on
the assumed between-person spread and are not predictions of human ICCs.

---

## 5. Limitations (prominent; keep in the main text)
1. **No physiology.** Noise is not derived from neural tuning, spike counts, electrode properties or
   any decoder architecture. Results describe responses to the modelled degradations, not to any
   real BCI.
2. **One control policy per modality.** Real users change strategy under degradation (slowing near
   targets, learning decoder quirks); cross-session adaptation is not modelled.
3. **Selection as a separate channel.** Real click decoders can couple click and movement.
4. **Assumed population structure.** A single latent ability with σ = 0.25 creates the
   between-person variance that makes reliability non-trivial; real BCI and AT populations may be
   more heterogeneous or differently structured. All simulated ICCs inherit this assumption.
5. **Calibration to broad ranges**, from prior knowledge, not to individual data; ranges must be
   checked against the cited literature before publication.
6. **Short simulated battery** (one phrase, one ADL, 12 grid trials, 24 scored ISO selections);
   sensitivities are for this length. Study I addresses length.
7. **Gaze and scanning models are simple** (no blinks, head movement, calibration grids or
   anticipation by experienced switch users).
8. **Single real-data check** on non-human, hand-controlled data with missing target width; it
   validates the pipeline, not norms.
9. **Not peer-reviewed software**; the code is research software with a proprietary licence
   pending an IP decision (`pyproject.toml`), which may limit reuse until a release decision is made.
10. **Simulator defects.** Five critical defects were found by independent review and fixed
    (§2.5a); others may remain, especially in the parameters that are not yet unit-tested. A second
    independent review is planned before submission.
11. **Conflict of interest**: the framework was built by the founder of a company that intends to
    commercialise measurement services.

---

## 6. Before submission
- Systematic search (PubMed, IEEE Xplore, ACM DL) for prior simulation-based evaluation of BCI or
  AT outcome measures; revise §1.3 and the novelty claim.
- Fill every `[RESULT PENDING]`; regenerate figures at journal resolution; write Table 3 and the
  final abstract from the numbers.
- Verify all [PK] citations and the calibration ranges.
- Decide the code licence and archive the exact commit on Zenodo.

---

## 7. Reproducibility (commands)
From the repository root (`neurometric/`), with Python ≥ 3.11 and the package installed
(`pip install -e .[dev]`):

```bash
# unit tests for the simulator, metrics and psychometrics
python -m pytest tests/test_simulator.py tests/test_metrics_analytic.py tests/test_psychometrics.py -q

# all sweeps and studies used here (writes experiments/results/<ID>/)
python -m neurometric.experiments.registry B_noise C_latency C2_latency_mouse D_dropout E_drift \
    F_false_activation F2_missed_selection B2_bias B3_update_rate B4_gain I_test_retest \
    K_responsiveness L_cross_modality M_user_variability N_missing_data H_adaptive \
    P_reproducibility G_metric_comparison --n 60
#   (--processes 4 is the default; G must run last because it reads the sweep outputs)

# a single condition / sweep can be re-run alone, e.g.
python -m neurometric.experiments.registry B_noise --n 60

# real public data check (needs the DANDI:000129 file in experiments/external_data/)
python -I -m neurometric.experiments.external_mc_rtt

# statistical verification (companion paper)
python -m neurometric.psychometrics.verify_coverage --reps 2000
```
Expected outputs: `summary.json` (with software versions, `synthetic: true` and a disclaimer),
`data.csv`, `properties.csv`, `retest_icc.csv`, figures. The study run used for this draft is
logged in `experiments/logs/full_run.log`.

**Data availability statement (draft).** Simulation outputs and derived X1 tables will be
deposited on Zenodo with a DOI at submission. The MC_RTT source data are available from DANDI
(DANDI:000129, CC-BY-4.0).

---

## 8. Candidate venues (requirements are [PK] unless verified; check the journal site before submission)
| Venue | Fit | Notes to verify [PK] |
|---|---|---|
| **Journal of Neural Engineering** (IOP) | Strong: BCI methods, endpoint debate (the 2026 COA workshop report appeared here, Sawyer et al. 2026 [V]) | Article type "Paper"; data-availability statement required; preprints permitted; APC only if open access chosen; check length guidance and figure rules |
| **IEEE Transactions on Neural Systems and Rehabilitation Engineering** | Strong: rehabilitation/AT engineering and measurement | Fully open access with an APC; page limits with over-length charges; double-column IEEE template; check current APC and page limit |
| **Journal of NeuroEngineering and Rehabilitation** (BMC) | Good: open methods papers, AT and rehabilitation | Open access APC; "Methodology" article type; reporting checklists; check APC waiver policy |
| Alternative: *PLOS Computational Biology* or *Behavior Research Methods* | If framed as general measurement-simulation methodology | Scope check needed |
Recommendation [INF]: J Neural Eng first (audience is the BCI endpoint community), TNSRE second.
See `VENUES.md`.

---

## References (DOIs [V-DOI] via `docs/research/methods_references.md` unless marked)
Damper RI 1984, Appl Ergon 15:289–296, 10.1016/0003-6870(84)90201-1 · Dohle E et al. 2025, Adv
Sci 12:e01912, 10.1002/advs.202501912 [V] · Flash T, Hogan N 1985, J Neurosci 5:1688–1703,
10.1523/JNEUROSCI.05-07-01688.1985 · Fry A et al. 2022, J Neural Eng, 10.1088/1741-2552/ac60ca [V] ·
Gilja V et al. 2012, Nat Neurosci 15:1752–1757, 10.1038/nn.3265 · Hochberg LR et al. 2006, Nature
442:164–171, 10.1038/nature04970 · Koester HH, Levine SP 1994, Assist Technol 6:42–53,
10.1080/10400435.1994.10132226 · MacKenzie IS, Kauppinen T, Silfverberg M 2001, CHI '01:9–16,
10.1145/365024.365028 · Majaranta P, Räihä K-J 2002, ETRA '02:15–22, 10.1145/507072.507076 · Meyer
DE et al. 1988, Psychol Rev 95:340–370, 10.1037/0033-295X.95.3.340 · Nuyujukian P et al. 2015, IEEE
TBME 62:21–29, 10.1109/TBME.2014.2354697 · Pandarinath C et al. 2017, eLife 6:e18554,
10.7554/eLife.18554 · Sawyer A et al. 2025, EBioMedicine 116:105732, 10.1016/j.ebiom.2025.105732
[V] · Sawyer A et al. 2026, J Neural Eng 23(5), 10.1088/1741-2552/ae9eee [V] · Soukoreff RW,
MacKenzie IS 2003, CHI '03:113–120, 10.1145/642611.642632 · Soukoreff RW, MacKenzie IS 2004, IJHCS
61:751–789, 10.1016/j.ijhcs.2004.09.001 · Thompson DE et al. 2014, J Neural Eng 11:035001,
10.1088/1741-2560/11/3/035001 · Willett FR et al. 2017, J Neural Eng 14:016001,
10.1088/1741-2560/14/1/016001 · Willett FR et al. 2021, Nature 593:249–254,
10.1038/s41586-021-03506-2 · Willett FR et al. 2023, Nature 620:1031–1036,
10.1038/s41586-023-06377-x · Wolpaw JR et al. 1998, IEEE TRE 6:326–333, 10.1109/86.712231 · Yuan P
et al. 2013, J Neural Eng 10:026014, 10.1088/1741-2560/10/2/026014 · Zhai S 2004, IJHCS 61:791–809,
10.1016/j.ijhcs.2004.09.006 · Zhai S, Kong J, Ren X 2004, IJHCS 61:823–856,
10.1016/j.ijhcs.2004.09.007 · iBCI-CC consensus statement, 1 Oct 2026 [V] · O'Doherty JE et al.;
Makin JG et al. 2018, J Neural Eng, 10.1088/1741-2552/aa9e95 (MC_RTT source; cite per DANDI
README) [V link in datasets.md].
