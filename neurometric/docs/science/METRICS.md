# NeuroMetric metric definitions (v1)

Implementation: `src/neurometric/metrics/{pointing,text,session}.py`. Tests with analytically
known values: `tests/test_metrics_analytic.py`. Cross-language parity (TypeScript subset):
`web/` golden fixtures.

**Raw measurements** are things recorded directly: sample positions and times, selection times
and positions, item hit, keystrokes, markers, assistance events. **Derived metrics** are
computed from raw measurements by the formulas below. Every derived metric can be recomputed from
the stored canonical event stream (events are stored verbatim with a SHA-256).

Observable-only rule: metric functions take only what a real deployment records. Simulation
ground truth (intended selections, injected false activations) is never an input to a metric.

## 1. Target acquisition (tasks A1-A5, E2, F-steps)

| Metric | Definition | Units | Notes / assumptions |
|---|---|---|---|
| success | terminating selection on the target item | bool | |
| error | terminating selection on a non-target item or empty space (ISO sequences end on any selection) | bool | |
| timeout | no terminating selection by max time | bool | excluded from throughput, reported separately |
| movement_time_ms (MT) | stimulus onset (or previous selection in sequential tasks) to terminating selection | ms | includes reaction time in A1/A4; in A2 sequences MT = inter-selection interval as in ISO 9241-411 |
| onset_ms | first sample whose projection on the task axis exceeds 10% of D | ms | "movement onset", not pure reaction time: under a noisy BCI the cursor moves without intent. Call it *selection-process onset*, never "reaction time" for AT users |
| path_length_px | sum of sample-to-sample distances up to the selection | px | depends on sampling rate; compare at equal rates |
| path_efficiency | ‖selection − start‖ / path length | 0-1 | straightness index; undefined for timeouts |
| endpoint_error_px | ‖selection − target centre‖ | px | |
| endpoint_dx_px | signed endpoint error projected on the start→target axis | px | input to effective width |
| overshoot_px | max projection beyond (D + target half-extent along axis), 0 if none | px | |
| target_reentries (TRE) | entries into the target after the first | count | MacKenzie, Kauppinen & Silfverberg 2001 |
| task_axis_crossings (TAC) | sign changes of the perpendicular offset | count | same source |
| movement_direction_changes (MDC) | sign changes of perpendicular velocity | count | same source |
| orthogonal_direction_changes (ODC) | sign changes of velocity along the axis | count | same source |
| movement_variability_px (MV) | SD of perpendicular offset | px | same source |
| movement_error_px (ME), movement_offset_px (MO) | mean absolute / signed perpendicular offset | px | same source |
| dial_in_ms | first target entry to selection (successful trials) | ms | used in BCI literature for the "stopping and clicking" phase |
| submovements | speed peaks > 50 px/s after 5-sample smoothing | count | heuristic; sampling-rate dependent |
| empty_selections | selections on empty space that did not end the trial | count | observable proxy of false activations |

### Fitts throughput (A2, A3)
Per condition (fixed nominal D and W), all selection-terminated trials (hits and misses):
`We = 4.133 × SD(endpoint_dx)`, `De = mean(projected amplitude)`, `IDe = log2(De/We + 1)`,
`TP = IDe / mean(MT)` (Soukoreff & MacKenzie 2004, ISO 9241-411) [PK formula, DOI verified in
docs/research/methods_references.md]. A participant's TP = mean over conditions.

Validity flags (computed, stored with the value):
* n < 10 selections in a condition;
* error rate > 50% — the speed–accuracy assumption behind effective width fails;
* timeouts are excluded, so TP is conditional on selection — report timeout rate beside TP;
* dwell selection — MT contains a fixed dwell; compare TP only at the same dwell setting.
TP is **not** reported for scanning (no continuous aimed movement) and is labelled
"undefined" rather than zero.

### Achieved bitrate (A4, E2)
`B = log2(N − 1) × max(Sc − Si, 0) / t` for N selectable items, Sc correct, Si incorrect selections,
t seconds (Nuyujukian et al. 2015 style) [PK]. Penalises errors as if each needs a correction.

### Wolpaw ITR (reported only with a flag)
`bits = log2 N + P log2 P + (1−P) log2((1−P)/(N−1))`. Assumes equiprobable targets, errors spread
uniformly over the N−1 wrong items, and fixed selection time; these rarely hold for AT/BCI use, so
NeuroMetric never uses ITR as a primary score.

## 2. Text entry (E1)
Presented P, transcribed T, input stream IS (BACKSPACE = editing key), time S from first keystroke.
* `WPM = (|T| − 1) / S × 60 / 5`
* `CCPM = max(|T| − MSD(P,T), 0) / minutes` (correct characters per minute)
* `MSD error rate = MSD(P,T) / max(|P|,|T|)`
* Soukoreff & MacKenzie (2003): C = max(|P|,|T|) − MSD; INF = MSD; IF = non-editing keystrokes
  that were erased; F = editing keystrokes. Corrected ER = IF/(C+INF+IF); uncorrected ER =
  INF/(C+INF+IF); total ER = (INF+IF)/(C+INF+IF).
* `KSPC = |IS| / |T|`; correction burden = F / |T|.
Only predefined phrases are processed. Free text (opt-in) stores character counts and timing,
never content.

## 3. Continuous control
* Tracking (B2): RMS error, time on target (within radius), lag by cross-correlation of x.
* Steering (B1): tunnel exits, RMS deviation from the tunnel centre line, MT.
* Scrolling (C1): time to select, band passes (overshoots), direction reversals.
* Drag (D1): success, unintended drops (release outside zone), placement error.

## 4. Digital ADL (F1-F7)
completed (bool), time to complete, wrong selections, assisted (any ASSIST event during the
task). **Assisted ≠ failed**: assistance is recorded and reported separately.

## 5. Session and process measures
duration, active minutes, rest minutes, interruptions (PAUSE), assistance events by type and per
hour, completion rate (tasks completed / planned), within-session variability (CV) and linear
trend. A trend cannot distinguish fatigue from learning or device change; it is reported and
never interpreted automatically.

## 6. What NeuroMetric does not compute
* MCID / clinically important change (requires anchor-based clinical evidence).
* Any neural-signal or decoder-internal metric unless supplied by an authorised source (and then
  stored as device metadata, not recomputed).
* Composite "independence" or "digital function" indices are **experimental** and labelled so
  until validated (see docs/science/INDEPENDENCE_MODEL.md).

## Notes added after independent review
* TAC, MDC and ODC count sign changes of 10 ms (or device-rate) samples: they depend on noise and
  sampling rate; compare only at equal sampling rates (as for submovements).
* IF follows the original Soukoreff & MacKenzie (2003) definition (all erased non-editing
  keystrokes, including correct ones). Wobbrock & Myers (2006) refine this by aligning the input
  stream; NeuroMetric may add that refinement later [PK].
* Throughput flags spatial outliers (movement < D/2 or |endpoint error| > 2W) but does not exclude
  them; they inflate We.
* `iso_tp_bps` is undefined (NaN) when no condition meets the validity rules; `iso_mt_ms` counts
  timeouts at the time limit (censored), `iso_mt_completed_ms` only selection-terminated trials.
