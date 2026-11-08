# BrainOS acquisition verification — lsl

**Result: PASS**

> PASS: all 21 required checks passed.

## What this result means

- Evidence level of this run: **software_acquisition_comparison**
- BrainOS received, over Lab Streaming Layer, exactly the data the reference software recorded from the same source, within the stated tolerances. This is software-level evidence about the acquisition path; it says nothing about hardware unless the source was real hardware and the hardware criteria below are met.
- Hardware verified: **no** (never set by this tool). Human validated: **no**.
- Not a hardware-validation run because: the operator did not declare acquisition hardware as the signal source; no equipment manifest; the data is declared synthetic; overlap 10 s < 240 s required for a hardware-validation run.

## Summary

| Quantity | Value |
| --- | --- |
| acquisition protocol | Lab Streaming Layer (reference: XDF) |
| stream | hwval-gap-3583 (EEG) on vm |
| channels | 8 |
| channel labels | ["T1", "T2", "T3", "T4", "T5", "T6", "T7", "T8"] |
| nominal rate hz | 1000 |
| effective rate reference hz | 1000 |
| effective rate brainos hz | 978.148 |
| reference samples | 13870 |
| brainos samples | 10490 |
| overlap s | 10.49 |
| samples compared | 10490 |
| missing in brainos | 0 |
| estimated loss fraction | 0 |
| duplicated in brainos | 0 |
| brainos samples without counterpart | 0 |
| values out of tolerance | 0 |
| max abs value diff | 0 |
| max timestamp discrepancy s | 4.547e-13 |
| reference clock drift ppm | 1.5386 |
| brainos ingest drift ppm | 8.33678 |
| latency median s | 0.00444174 |
| excess delay max s | 0.00984669 |
| reference discontinuities | 1 |
| result | pass |

## Checks

| Check | Status | Required | Finding |
| --- | --- | --- | --- |
| `REF-FILE` Reference XDF stream is readable and consistent | PASS | yes | 13870 samples read by pyxdf (footer sample_count 13869 vs 13870 samples read (LabRecorder footer count; the samples themselves are authoritative)) |
| `BOS-FILE` BrainOS recording file is complete and well-formed | PASS | yes | 494 frames, every line readable, seq contiguous, contract-valid |
| `IDENTITY` Both recordings are of the same LSL stream | PASS | yes | same LSL outlet (uid f6b65d83-d7e5-417f-8adb-2565d7e60348) |
| `META-CHANNELS` Channel count and channel identities agree | PASS | yes | 8 channels, labels identical in order |
| `META-RATE` Declared sampling rate agrees | PASS | yes | 1000 Hz on both sides |
| `META-FORMAT` Stream type and sample format agree | PASS | yes | EEG / float32 |
| `META-UNITS` Units are interpreted correctly | PASS | yes | reference declares voltage units; BrainOS reports µV |
| `PROVENANCE` Synthetic / prerecorded declarations are carried through | PASS | yes | declarations consistent (the data is declared synthetic) |
| `OVERLAP` Recordings overlap enough to compare | PASS | yes | 10.49 s of the recordings overlap (10490 samples) |
| `SAMPLE-COUNT` Sample counts agree within the overlap | PASS | yes | reference 10490 vs BrainOS 10490 samples in the overlap |
| `LOSS` No samples missing in BrainOS | PASS | yes | no reference sample is missing from BrainOS |
| `DUPLICATES` No duplicated samples in BrainOS | PASS | yes | none |
| `EXTRA` No BrainOS samples without a reference counterpart | PASS | yes | every BrainOS sample in the reference's range has a counterpart |
| `ORDER` BrainOS frames are in source order | PASS | yes | frames in source order |
| `ALIGN-CONTENT` Alignment confirmed by signal content (independent of timestamps) | PASS | yes | 24 probed frame(s) found by content exactly where their timestamps/indices place them |
| `VALUES` Signal values agree within the expected numerical tolerance | PASS | yes | all 83920 values agree (83920 bit-exact) |
| `CHANNEL-ORDER` Channels are in the reference order | PASS | yes | every channel matches its reference channel |
| `SCALE` Scaling and units are correct | PASS | yes | values equal the reference in the stated unit (factor 1) |
| `LOSS-FLAGGED` BrainOS reported every loss it suffered | PASS | yes | no loss to report (1 frame(s) flagged anyway) |
| `TS-AGREE` Timestamps agree with the reference | PASS | yes | first-sample timestamps of 494 frames equal the source timestamps (max \|diff\| 4.5e-13 s) |
| `DELAY` Data was not delayed beyond the threshold | PASS | yes | worst excess ingest delay 9.8 ms (median 2.7 ms) vs threshold 1000 ms; absolute latency median 4.4 ms |
| `RATE-EFFECTIVE` Effective sampling rate matches the nominal rate | PASS | advisory | effective rate 1000.0000 Hz (+0.0 ppm from nominal) |
| `REF-CONTINUITY` Reference stream is continuous | INCONCLUSIVE | advisory | the reference itself has 1 gap(s) (~150 samples) and 0 timestamp regression(s): source or recorder discontinuities |
| `CLOCKS` Clock offset and drift characterised | PASS | advisory | recorder-source offset median -0.019 ms, drift +1.54 ppm; BrainOS wall clock vs source drift +8.34 ppm |
| `EQUIPMENT` Acquisition hardware and software are documented | not tested | advisory | no equipment manifest given (--equipment); the run is not traceable to hardware |

## Acquisition source

- **protocol**: Lab Streaming Layer
- **reference software**: XDF file (LabRecorder or compatible), read with pyxdf
- **xdf stream**: {"stream_id": 1, "name": "hwval-gap-3583", "type": "EEG", "source_id": "hwval-gap-3583-sid", "hostname": "vm", "uid": "f6b65d83-d7e5-417f-8adb-2565d7e60348",...
- **xdf file header**: {"version": "1.0", "datetime": "2026-11-08T00:44:00+0000"}
- **brainos device**: {"device_id": "lsl:hwval-gap-3583-sid", "display_name": "LSL \u00b7 hwval-gap-3583 (EEG) \u2014 declared synthetic", "kind": "simulated", "adapter": "brainos...
- **brainos recording note**: Synthetic data (declared by the source).
- **brainos schema version**: 1.4
- **capture sidecar**: {"brainos_version": "0.3.0", "started_utc": "2026-11-08T00:44:03Z", "duration_s": 10.656822835, "stop_reason": "duration reached", "host": {"hostname": "vm",...

## Inputs

| Role | Path | Bytes | SHA-256 |
| --- | --- | --- | --- |
| reference_xdf | `/tmp/pytest-of-root/pytest-20/lr-gap0/labrecorder.xdf` | 521722 | `444bb2fd2edbdac08f88a58b62c8b0db9ef9b8bd9005b587b7422998a74ad10f` |
| brainos_recording | `/tmp/pytest-of-root/pytest-20/lr-gap0/brainos.brainos.jsonl` | 1797446 | `d6025b58b4c740292d198e2648af1375b7074ab2dbac2123d1e0da4a8c9b2a6e` |
| capture_sidecar | `/tmp/pytest-of-root/pytest-20/lr-gap0/brainos.capture.json` | 3897 | `b666b356224ba60c7542a0ba4d2f332b676e7c0b04d23bf984d86a873fb7520c` |

## Tests performed and evidence

### `REF-FILE` — Reference XDF stream is readable and consistent: PASS

*Method:* pyxdf loads the file (synchronize_clocks=False, dejitter_timestamps=False); sample and timestamp counts must agree.

*Finding:* 13870 samples read by pyxdf (footer sample_count 13869 vs 13870 samples read (LabRecorder footer count; the samples themselves are authoritative))

| Evidence | Value |
| --- | --- |
| samples | 13870 |
| pyxdf_effective_srate | 989.3 |

<details><summary>footer</summary>

```json
{
 "first_timestamp": "3182.968893921",
 "last_timestamp": "3196.987893921",
 "sample_count": "13869"
}
```
</details>

<details><summary>notes</summary>

```json
[
 "footer sample_count 13869 vs 13870 samples read (LabRecorder footer count; the samples themselves are authoritative)"
]
```
</details>

### `BOS-FILE` — BrainOS recording file is complete and well-formed: PASS

*Method:* Parse every line; require the brainos.recording/1 header, contiguous envelope seq numbers (the recorder writes every published event), and — if BrainOS is installed — validation of every envelope against BrainOS's contract models.

*Finding:* 494 frames, every line readable, seq contiguous, contract-valid

| Evidence | Value |
| --- | --- |
| frames | 494 |
| malformed_lines | 0 |
| seq_gaps | 0 |
| seq_regressions | 0 |

<details><summary>event_counts</summary>

```json
{
 "recording.frame": 494
}
```
</details>

<details><summary>contract</summary>

```json
{
 "validated": true,
 "valid_events": 494,
 "invalid_events": 0
}
```
</details>

### `IDENTITY` — Both recordings are of the same LSL stream: PASS

*Method:* XDF stream chosen by the capture sidecar's uid, else the stream name/source_id/host in the BrainOS device descriptor, else a unique channel count + rate; then every identity field available on both sides must agree.

*Finding:* same LSL outlet (uid f6b65d83-d7e5-417f-8adb-2565d7e60348)

| Evidence | Value |
| --- | --- |
| selected_by | same LSL stream uid (capture sidecar) |

<details><summary>xdf_stream</summary>

```json
{
 "stream_id": 1,
 "name": "hwval-gap-3583",
 "type": "EEG",
 "source_id": "hwval-gap-3583-sid",
 "hostname": "vm",
 "uid": "f6b65d83-d7e5-417f-8adb-2565d7e60348",
 "channel_count": 8,
 "nominal_srate": 1000.0,
 "channel_format": "float32",
 "samples": 13870,
 "channels_described": true,
 "manufacturer": "brainos-hwval test signal (synthetic)",
 "declaration": {
  "prerecorded": "false",
  "synthetic": "true"
 }
}
```
</details>

<details><summary>brainos_descriptor_identity</summary>

```json
{
 "name": "hwval-gap-3583",
 "hostname": "vm",
 "source_id": "hwval-gap-3583-sid",
 "type": "EEG"
}
```
</details>

<details><summary>sidecar_identity</summary>

```json
{
 "name": "hwval-gap-3583",
 "type": "EEG",
 "source_id": "hwval-gap-3583-sid",
 "hostname": "vm",
 "uid": "f6b65d83-d7e5-417f-8adb-2565d7e60348"
}
```
</details>

<details><summary>streams_in_file</summary>

```json
[
 {
  "stream_id": 1,
  "name": "hwval-gap-3583",
  "type": "EEG",
  "source_id": "hwval-gap-3583-sid",
  "channel_count": 8,
  "nominal_srate": 1000.0,
  "samples": 13870
 }
]
```
</details>

### `META-CHANNELS` — Channel count and channel identities agree: PASS

*Method:* Channel count of every BrainOS frame and of the descriptor equals the XDF channel_count; the descriptor's channel_labels equal the XDF <channel><label> list in order (BrainOS names an unlabelled channel 'ch<i>').

*Finding:* 8 channels, labels identical in order

<details><summary>reference_labels</summary>

```json
[
 "T1",
 "T2",
 "T3",
 "T4",
 "T5",
 "T6",
 "T7",
 "T8"
]
```
</details>

<details><summary>brainos_labels</summary>

```json
[
 "T1",
 "T2",
 "T3",
 "T4",
 "T5",
 "T6",
 "T7",
 "T8"
]
```
</details>

<details><summary>frame_channel_counts</summary>

```json
[
 8
]
```
</details>

### `META-RATE` — Declared sampling rate agrees: PASS

*Method:* sample_rate_hz of every BrainOS frame and of the descriptor equals the XDF nominal_srate.

*Finding:* 1000 Hz on both sides

| Evidence | Value |
| --- | --- |
| reference_nominal_srate | 1000 |
| brainos_descriptor_rate | 1000 |

<details><summary>brainos_frame_rates</summary>

```json
[
 1000.0
]
```
</details>

### `META-FORMAT` — Stream type and sample format agree: PASS

*Method:* Descriptor stream_type and channel_format equal the XDF type and channel_format.

*Finding:* EEG / float32

<details><summary>reference</summary>

```json
{
 "type": "EEG",
 "channel_format": "float32"
}
```
</details>

<details><summary>brainos</summary>

```json
{
 "type": "EEG",
 "channel_format": "float32"
}
```
</details>

### `META-UNITS` — Units are interpreted correctly: PASS

*Method:* If every XDF channel declares a known voltage unit (microvolts, millivolts, volts, nanovolts and abbreviations), BrainOS must label frames 'uV' (values converted); otherwise it must label them 'arbitrary' (values unscaled).

*Finding:* reference declares voltage units; BrainOS reports µV

<details><summary>reference_units</summary>

```json
[
 "microvolts",
 "microvolts",
 "microvolts",
 "microvolts",
 "microvolts",
 "microvolts",
 "microvolts",
 "microvolts"
]
```
</details>

<details><summary>factors_to_uV</summary>

```json
[
 1.0,
 1.0,
 1.0,
 1.0,
 1.0,
 1.0,
 1.0,
 1.0
]
```
</details>

<details><summary>brainos_units</summary>

```json
[
 "uV"
]
```
</details>

### `PROVENANCE` — Synthetic / prerecorded declarations are carried through: PASS

*Method:* The publisher's optional <desc><brainos><synthetic>/<prerecorded> declarations must appear as provenance synthetic / replayed on every BrainOS frame, and BrainOS must not add them on its own.

*Finding:* declarations consistent (the data is declared synthetic)

<details><summary>reference_declaration</summary>

```json
{
 "prerecorded": "false",
 "synthetic": "true"
}
```
</details>

<details><summary>brainos</summary>

```json
{
 "header_synthetic": true,
 "device_kind": "simulated",
 "frames_synthetic": [
  true
 ],
 "frames_replayed": [
  false
 ],
 "origins": [
  "lsl:hwval-gap-3583@vm"
 ],
 "adapters": [
  "brainos.lsl@0.1.0"
 ]
}
```
</details>

### `OVERLAP` — Recordings overlap enough to compare: PASS

*Method:* Span from the first to the last reference sample that a BrainOS frame maps to. BrainOS samples before the reference started or after it stopped are not compared and not counted as errors.

*Finding:* 10.49 s of the recordings overlap (10490 samples)

| Evidence | Value |
| --- | --- |
| overlap_rows | 10490 |
| overlap_s | 10.49 |
| reference_rows | 13870 |
| brainos_samples | 10490 |
| brainos_samples_outside_reference | 0 |
| brainos_samples_past_reference_end | 0 |
| min_overlap_s | 5 |

<details><summary>reference_row_span</summary>

```json
[
 3100,
 13590
]
```
</details>

### `SAMPLE-COUNT` — Sample counts agree within the overlap: PASS

*Method:* Count reference samples between the first and last BrainOS sample and the BrainOS samples mapped onto them (each counted once per frame that claims it).

*Finding:* reference 10490 vs BrainOS 10490 samples in the overlap

| Evidence | Value |
| --- | --- |
| reference_samples_in_overlap | 10490 |
| brainos_samples_mapped_into_overlap | 10490 |
| difference | 0 |
| reference_total | 13870 |
| brainos_total | 10490 |

### `LOSS` — No samples missing in BrainOS: PASS

*Method:* Reference samples inside the overlap that no BrainOS frame maps to.

*Finding:* no reference sample is missing from BrainOS

| Evidence | Value |
| --- | --- |
| missing_samples | 0 |
| missing_fraction | 0 |
| missing_runs | 0 |
| max_loss_fraction | 0 |
| estimated_lost_duration_s | 0 |

### `DUPLICATES` — No duplicated samples in BrainOS: PASS

*Method:* Reference samples claimed by more than one BrainOS frame.

*Finding:* none

| Evidence | Value |
| --- | --- |
| duplicated_samples | 0 |

### `EXTRA` — No BrainOS samples without a reference counterpart: PASS

*Method:* BrainOS frames whose first-sample key lies within the reference's range but matches no reference sample.

*Finding:* every BrainOS sample in the reference's range has a counterpart

| Evidence | Value |
| --- | --- |
| brainos_samples_without_counterpart | 0 |
| frames | 0 |
| frames_inside_a_reference_gap | 0 |
| content_found_elsewhere | 0 |

### `ORDER` — BrainOS frames are in source order: PASS

*Method:* Successive frames (in recording order) must map to increasing reference rows; a frame that cannot be mapped must not have a smaller first_sample_index than its predecessor.

*Finding:* frames in source order

| Evidence | Value |
| --- | --- |
| frames_mapped_before_their_predecessor | 0 |
| frames_overlapping_predecessor | 0 |
| unmapped_frames_with_index_regression | 0 |

### `ALIGN-CONTENT` — Alignment confirmed by signal content (independent of timestamps): PASS

*Method:* For evenly spaced frames (and every frame the key could not place), search the reference values for the frame's first 16 samples on all channels; compare the row found with the row given by the frame's timestamp / sample number.

*Finding:* 24 probed frame(s) found by content exactly where their timestamps/indices place them

| Evidence | Value |
| --- | --- |
| probed | 24 |
| probed_mapped_by_key | 24 |
| probed_unmapped | 0 |
| agree | 24 |
| disagree | 0 |
| not_found | 0 |
| ambiguous | 0 |

### `VALUES` — Signal values agree within the expected numerical tolerance: PASS

*Method:* Every BrainOS sample is compared with the reference sample it maps to, channel by channel: |brainos - reference| <= tolerance. |diff| <= 0 + 2.5e-07 x |reference| (reference converted to BrainOS's unit in float64). Bit-exact values are counted separately ('exact'); a difference at single-precision level is an expected numerical tolerance.

*Finding:* all 83920 values agree (83920 bit-exact)

| Evidence | Value |
| --- | --- |
| tolerance | |diff| <= 0 + 2.5e-07 x |reference| (reference converted to BrainOS's unit in float64). Bit-exact values are counted separately ('exact'); a difference at single-precision level is an expected numerical tolerance. |
| values_compared | 83920 |
| values_exactly_equal | 83920 |
| values_out_of_tolerance | 0 |
| max_abs_diff | 0 |
| values_excluded_clipped_in_reference | 0 |

<details><summary>per_channel</summary>

```json
[
 {
  "compared": 10490,
  "exact": 10490,
  "within_tolerance": 10490,
  "within_float32": 10490,
  "out_of_tolerance": 0,
  "excluded_clipped_in_reference": 0,
  "max_abs_diff": 0.0,
  "rms_diff": 0.0,
  "channel": "T1"
 },
 {
  "compared": 10490,
  "exact": 10490,
  "within_tolerance": 10490,
  "within_float32": 10490,
  "out_of_tolerance": 0,
  "excluded_clipped_in_reference": 0,
  "max_abs_diff": 0.0,
  "rms_diff": 0.0,
  "channel": "T2"
 },
 {
  "compared": 10490,
  "exact": 10490,
  "within_tolerance": 10490,
  "within_float32": 10490,
  "out_of_tolerance": 0,
  "excluded_clipped_in_reference": 0,
  "max_abs_diff": 0.0,
  "rms_diff": 0.0,
  "channel": "T3"
 },
 {
  "compared": 10490,
  "exact": 10490,
  "within_tolerance": 10490,
  "within_float32": 10490,
  "out_of_tolerance": 0,
  "excluded_clipped_in_reference": 0,
  "max_abs_diff": 0.0,
  "rms_diff": 0.0,
  "channel": "T4"
 },
 {
  "compared": 10490,
  "exact": 10490,
  "within_tolerance": 10490,
  "within_float32": 10490,
  "out_of_tolerance": 0,
  "excluded_clipped_in_reference": 0,
  "max_abs_diff": 0.0,
  "rms_diff": 0.0,
  "channel": "T5"
 },
 {
  "compared": 10490,
  "exact": 10490,
  "within_tolerance": 10490,
  "within_float32": 10490,
  "out_of_tolerance": 0,
  "excluded_clipped_in_reference": 0,
  "max_abs_diff": 0.0,
  "rms_diff": 0.0,
  "channel": "T6"
 },
 {
  "compared": 10490,
  "exact": 10490,
  "within_tolerance": 10490,
  "within_float32": 10490,
  "out_of_tolerance": 0,
  "excluded_clipped_in_reference": 0,
  "max_abs_diff": 0.0,
  "rms_diff": 0.0,
  "channel": "T7"
 },
 {
  "compared": 10490,
  "exact": 10490,
  "within_tolerance": 10490,
  "within_float32": 10490,
  "out_of_tolerance": 0,
  "excluded_clipped_in_reference": 0,
  "max_abs_diff": 0.0,
  "rms_diff": 0.0,
  "channel": "T8"
 }
]
```
</details>

### `CHANNEL-ORDER` — Channels are in the reference order: PASS

*Method:* Every BrainOS channel is matched against every reference channel on a thin sample.

*Finding:* every channel matches its reference channel

<details><summary>best_matches</summary>

```json
[
 {
  "channel": 0,
  "expected_ref": 0,
  "best_ref": 0,
  "match_best": 1.0,
  "match_expected": 1.0
 },
 {
  "channel": 1,
  "expected_ref": 1,
  "best_ref": 1,
  "match_best": 1.0,
  "match_expected": 1.0
 },
 {
  "channel": 2,
  "expected_ref": 2,
  "best_ref": 2,
  "match_best": 1.0,
  "match_expected": 1.0
 },
 {
  "channel": 3,
  "expected_ref": 3,
  "best_ref": 3,
  "match_best": 1.0,
  "match_expected": 1.0
 },
 {
  "channel": 4,
  "expected_ref": 4,
  "best_ref": 4,
  "match_best": 1.0,
  "match_expected": 1.0
 },
 {
  "channel": 5,
  "expected_ref": 5,
  "best_ref": 5,
  "match_best": 1.0,
  "match_expected": 1.0
 },
 {
  "channel": 6,
  "expected_ref": 6,
  "best_ref": 6,
  "match_best": 1.0,
  "match_expected": 1.0
 },
 {
  "channel": 7,
  "expected_ref": 7,
  "best_ref": 7,
  "match_best": 1.0,
  "match_expected": 1.0
 }
]
```
</details>

### `SCALE` — Scaling and units are correct: PASS

*Method:* Least-squares factor per channel on a thin sample.

*Finding:* values equal the reference in the stated unit (factor 1)

| Evidence | Value |
| --- | --- |
| unit_interpretation | reference units ['microvolts', 'microvolts', 'microvolts', 'microvolts', 'microvolts', 'microvolts', 'microvolts', 'microvolts'] -> µV factors [1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0] |

### `LOSS-FLAGGED` — BrainOS reported every loss it suffered: PASS

*Method:* For each run of samples missing in BrainOS, the next BrainOS frame must carry the quality flag dropped_samples, or a device.status event (reconnecting, ...) must lie between the frames around the gap.

*Finding:* no loss to report (1 frame(s) flagged anyway)

| Evidence | Value |
| --- | --- |
| loss_runs | 0 |
| reported_by_frame_flag | 0 |
| reported_by_device_status | 0 |
| unreported_runs | 0 |
| frames_flagged_dropped_samples | 1 |

### `TS-AGREE` — Timestamps agree with the reference: PASS

*Method:* Each BrainOS frame's device_timestamp_ns (source clock) is compared with the XDF raw timestamp of the sample it maps to; both are copies of the source's timestamps, so any difference above 2e-06 s is an error. Frames located by content at another sample are timestamp errors.

*Finding:* first-sample timestamps of 494 frames equal the source timestamps (max |diff| 4.5e-13 s)

| Evidence | Value |
| --- | --- |
| frames_with_timestamp_match | 494 |
| max_abs_diff_s | 4.547e-13 |
| median_diff_s | 0 |
| exact_tolerance_s | 2e-06 |
| frames_whose_timestamp_contradicts_content | 0 |
| intra_frame_reconstruction_max_error_s | 4.547e-13 |

### `DELAY` — Data was not delayed beyond the threshold: PASS

*Method:* BrainOS ingest wall clock minus the source time of each frame's last sample; the excess over the smallest observed value is the variable delay (buffering, transport, stalls). Absolute latency uses the clock pair measured by `brainos-hwval capture`.

*Finding:* worst excess ingest delay 9.8 ms (median 2.7 ms) vs threshold 1000 ms; absolute latency median 4.4 ms

| Evidence | Value |
| --- | --- |
| frames | 494 |
| excess_delay_median_s | 0.00265479 |
| excess_delay_p95_s | 0.00512356 |
| excess_delay_max_s | 0.00984669 |
| drift_ppm | 8.33678 |
| latency_median_s | 0.00444174 |
| latency_p95_s | 0.0069105 |
| latency_max_s | 0.0116336 |
| latency_min_s | 0.00178695 |

<details><summary>fit</summary>

```json
{
 "slope": 8.336778322479357e-06,
 "intercept": 1794095457.7640052,
 "residual_std": 0.00158150736710181,
 "residual_max_abs": 0.007131814956665039,
 "n": 494
}
```
</details>

### `RATE-EFFECTIVE` — Effective sampling rate matches the nominal rate: PASS

*Method:* Linear fit of the reference's raw timestamps against sample number over the longest gap-free segment; the same fit over BrainOS frame timestamps vs first_sample_index. Advisory: this measures the source, not BrainOS.

*Finding:* effective rate 1000.0000 Hz (+0.0 ppm from nominal)

| Evidence | Value |
| --- | --- |
| nominal_hz | 1000 |
| reference_rate_hz | 1000 |
| reference_ppm | 4.441e-10 |
| brainos_rate_hz | 978.148 |
| brainos_ppm | -21852.2 |
| advisory_threshold_ppm | 500 |

<details><summary>reference_segment</summary>

```json
{
 "rate_hz": 1000.0000000000005,
 "segment_rows": [
  0,
  7980
 ],
 "segment_s": 7.9789999999998145,
 "timestamp_jitter_std_s": 9.171539384860508e-14,
 "timestamp_jitter_max_s": 4.547473508864641e-13
}
```
</details>

### `REF-CONTINUITY` — Reference stream is continuous: INCONCLUSIVE

*Method:* Per-sample XDF timestamps: an interval > 1.5 periods (and > 2 ms beyond one period) is a gap; a non-increasing timestamp is a regression. Advisory: a discontinuity here is in the source or in LabRecorder, not in BrainOS.

*Finding:* the reference itself has 1 gap(s) (~150 samples) and 0 timestamp regression(s): source or recorder discontinuities

| Evidence | Value |
| --- | --- |
| brainos_frames_flagged_dropped_samples | 1 |

<details><summary>reference</summary>

```json
{
 "gaps": 1,
 "regressions": 0,
 "est_missing": 150,
 "examples": [
  {
   "after_row": 7979,
   "t_s": 3190.947893921,
   "dt_s": 0.15100000000029468
  }
 ]
}
```
</details>

### `CLOCKS` — Clock offset and drift characterised: PASS

*Method:* Linear fit of LabRecorder's ClockOffset chunks (recorder minus source clock) against time; separately, BrainOS ingest wall clock minus source time against source time. Advisory: these characterise the clocks involved; offsets between clock domains are expected and are not errors.

*Finding:* recorder-source offset median -0.019 ms, drift +1.54 ppm; BrainOS wall clock vs source drift +8.34 ppm

<details><summary>labrecorder_clock_offsets</summary>

```json
{
 "measurements": 3,
 "usable": 3,
 "discarded": 0,
 "offset_median_s": -1.8550500044511864e-05,
 "offset_min_s": -2.3576999865326798e-05,
 "offset_max_s": -8.190500011551194e-06,
 "drift_ppm": 1.5386007651047282,
 "fit": {
  "slope": 1.538600765104728e-06,
  "intercept": -0.004930465888012791,
  "residual_std": 1.257127472619447e-06,
  "residual_max_abs": 1.7778467214079469e-06,
  "n": 3
 },
 "span_s": 10.00031690249989
}
```
</details>

<details><summary>brainos_ingest_vs_source</summary>

```json
{
 "frames": 494,
 "excess_delay_median_s": 0.0026547908782958984,
 "excess_delay_p95_s": 0.005123555660247803,
 "excess_delay_max_s": 0.009846687316894531,
 "drift_ppm": 8.336778322479358,
 "fit": {
  "slope": 8.336778322479357e-06,
  "intercept": 1794095457.7640052,
  "residual_std": 0.00158150736710181,
  "residual_max_abs": 0.007131814956665039,
  "n": 494
 },
 "latency_median_s": 0.004441738128662109,
 "latency_p95_s": 0.006910502910614014,
 "latency_max_s": 0.011633634567260742,
 "latency_min_s": 0.001786947250366211
}
```
</details>

### `EQUIPMENT` — Acquisition hardware and software are documented: not tested

*Method:* Required fields of the brainos-hwval.equipment/1 manifest must be filled in.

*Finding:* no equipment manifest given (--equipment); the run is not traceable to hardware

## Limitations

- Both recordings receive the stream through liblsl. A defect that liblsl itself introduced before either inlet (e.g. in the outlet's buffer) would be invisible to this comparison; comparing against the acquisition device's own file format closes that gap.
- BrainOS stores one source timestamp per frame (its first sample); per-sample timestamps inside a frame are reconstructed as first + k / nominal rate. The reconstruction error is reported but BrainOS cannot be checked for per-sample timestamp fidelity.
- LSL carries no sequence numbers: a sample lost before both inlets (at the source) appears as the same gap in both recordings and is reported as a source discontinuity, not as BrainOS loss.
- Absolute ingest latency needs the clock pair measured by `brainos-hwval capture`; otherwise only delay variation (excess over the best case) and drift are measured.
- A software publisher or a file player is not hardware. LSL cannot tell hardware from playback; the source kind is what the operator declares in the equipment manifest.

## Parameters and environment

```json
{
 "thresholds": {
  "match_fraction_of_period": 0.25,
  "timestamp_exact_s": 2e-06,
  "value_rtol": 2.5e-07,
  "value_atol": 0.0,
  "float32_rtol": 2.5e-07,
  "quantisation_steps": 0.51,
  "max_loss_fraction": 0.0,
  "min_overlap_s": 5.0,
  "max_excess_delay_s": 1.0,
  "rate_ppm_advisory": 500.0,
  "content_probe_frames": 24
 },
 "environment": {
  "brainos_hwval": "0.1.0",
  "python": "3.12.3",
  "platform": "Linux-6.18.44-fc-v310-x86_64-with-glibc2.39",
  "numpy": "2.5.4",
  "pyxdf": "1.18.0",
  "open_ephys_python_tools": "1.0.1",
  "brainos": "0.3.0"
 },
 "command": null,
 "tool": "brainos-hwval 0.1.0",
 "created_at": "2026-11-08T00:44:18Z"
}
```
