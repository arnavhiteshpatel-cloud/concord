# Simulated decoder harness and virtual users

**What it is:** an experimental model of input degradation plus synthetic closed-loop control
policies, used to test whether the *measurement system* behaves sensibly (monotone, sensitive,
reliable, not saturated) under controlled input conditions.

**What it is not:** a model of the physiology of any implanted or non-invasive BCI, a model of any
patient population, or evidence of clinical effectiveness. Virtual users are never described as
patients; every simulated row carries `synthetic=True`.

## Loop

```
virtual user --intent (velocity or position) + select intent--> DegradedChannel
     ^                                                               |
     |                                                     output velocity/position + selections
     +---- perceives the cursor with a feedback delay <---- cursor (integrated / set) ---+
```
The user perceives the **degraded** cursor and corrects for it (closed loop). This matters: an
open-loop noise model overstates the harm of bias and drift (which users partly compensate) and
understates the harm of latency (which destabilises feedback control). Basis: feedback-control
models of BCI users used for decoder design (Willett et al. 2019, Sci Rep) [PK].

## Degradation parameters (`DegradationConfig`, defaults = identity)

| Parameter | Model | Velocity mode | Position mode |
|---|---|---|---|
| gain, gain_decay_per_min | multiplicative; decays with session time | scales velocity | scales displacements (CD-gain mismatch) |
| bias_deg | rotation of decoded direction | yes | displacements |
| asymmetry | +x components ×(1+a), −x ×(1−a) | yes | displacements |
| white_noise | i.i.d. Gaussian per tick, per axis | px/s | px jitter |
| correlated_noise, correlated_tau_ms | AR(1), ρ = exp(−dt/τ), stationary SD as given | px/s | px |
| noise_growth_per_min | SD × (1 + g·t_min) | | |
| drift, drift_rate_per_min | constant + growing additive bias in a random fixed direction | px/s | px offset |
| smoothing_tau_ms | exponential smoothing (decoder smoothing) | | |
| quantization, direction_bins | rounding of magnitude / direction | | |
| update_hz | sample-and-hold output updates | | |
| latency_ms, latency_jitter_ms | delay line; jitter ~ Exp(mean); output never goes back in time | | |
| dropout_enter_per_s, dropout_mean_ms | two-state Markov (Gilbert–Elliott) episodes: zero velocity / frozen position, selections blocked | | |
| loss_of_control_per_min, _mean_ms, recovery_ms | intent not passed through (noise only), then gain ramps 0→1 | | |
| select_miss_prob, select_latency_ms, false_select_per_min | selection channel: misses, delay, Poisson false activations when not intending | | |
| dims | active axes (scrolling uses y only) | | |

Each parameter is verified by a unit test against its analytic expectation
(`tests/test_simulator.py`: latency shift, jitter never reorders, white/AR noise SD and lag-1
autocorrelation, gain and bias geometry, asymmetry, sample-and-hold rate, Markov dropout duty
cycle, false-selection rate, miss probability, selection latency, drift growth, determinism).

## Profiles (illustrative stress conditions)

`identity`, `bci_good`, `bci_moderate`, `bci_poor` in `simulator/decoder.py`. Calibration: with
the default BCI-like feedback user, `bci_good` gives ISO effective throughput ≈ 1.2 bit/s and
grid achieved bitrate ≈ 2.4 bit/s; mouse-like users give ≈ 4.1 bit/s and ~15 WPM on the on-screen
keyboard; dwell-gaze-like users ≈ 2.3 bit/s and ~9 WPM. These were tuned to sit inside broad,
published ranges (mouse Fitts TP ≈ 3.7–4.9 bit/s, Soukoreff & MacKenzie 2004; intracortical BCI
cursor throughput on the order of 1–2 bit/s in 2015–2017 BrainGate reports; dwell gaze typing in
single-digit WPM) [PK — ranges from memory; verify against methods_references.md before any
publication]. Calibration targets ranges, not individuals; no parameter is claimed to be a
measured property of a device.

## Virtual users (`users/models.py`)

| Model | Control | Mechanism | Parameters |
|---|---|---|---|
| FeedbackUser | velocity | proportional controller on perceived error, speed limit, signal-dependent + constant noise, reaction delay; clicks when the perceived cursor has been inside the target for `settle_ms` and is slow | feedback_delay, reaction, kp, vmax, motor_noise, const_noise, aim_sd_frac, select_margin, select_speed, select_rt, settle |
| SubmovementUser | position | minimum-jerk submovements (Flash & Hogan 1985) with endpoint SD ∝ D/T (stochastic optimised submovements, Meyer et al. 1988); corrective submovement after a feedback delay if outside the target | sub_tmin, sub_c, sub_k, aim_sd_frac |
| GazeUser | position | saccade latency + saccade, fixational jitter, partial compensation of a visible offset by looking beside the target | saccade_ms, fixation_jitter, offset_compensation |
| Scanning (simulator/scanning.py) | discrete | row-column or linear scanning; activation after a log-normal reaction time; late reactions land on the next item; misses wrap the cycle; Poisson false activations | scan_ms, rt_ms, rt_sigma, miss_prob, switch_latency_ms, false_per_min |

Populations (`sample_population`): one latent ability z ~ N(0,1) scales speed (×e^{σz}) and
noise (×e^{−σz}) plus idiosyncratic log-normal variation — the ground truth for reliability and
known-groups experiments. Fatigue (`fatigue_per_min`) and learning are *simulated* state changes,
labelled as such.

Text-entry users notice an error with probability 0.9 and correct it with backspace; unnoticed
errors remain. ADL users press "back" after a wrong selection and retry.

## Known limitations (read before interpreting any result)
1. No physiology: noise is not derived from neural tuning, spike counts or electrode properties.
2. One control law per modality; real users switch strategies (e.g., slowing down near targets
   more under noise, learning decoder quirks). Adaptation across sessions is not modelled except
   by explicit parameter changes.
3. Selection is a separate binary channel; real click decoders may couple click and movement.
4. The latent-ability structure that makes reliability non-trivial is an assumption; real
   between-person variance in BCI users may be larger or differently structured.
5. Eye-gaze model ignores blinks, head movement and calibration grids.
6. Scanning model ignores anticipation strategies used by experienced switch users.
Therefore: simulation can establish that metrics respond appropriately under these defined
conditions. It cannot establish reliability, validity or effectiveness in human users.
