# Concord acquisition verification — lsl

**Result: PASS**

> PASS: all 21 required checks passed.

## What this result means

- Evidence level of this run: **software_acquisition_comparison**
- Concord received, over Lab Streaming Layer, exactly the data the reference software recorded from the same source, within the stated tolerances. This is software-level evidence about the acquisition path; it says nothing about hardware unless the source was real hardware and the hardware criteria below are met.
- Hardware verified: **no** (never set by this tool). Human validated: **no**.
- Not a hardware-validation run because: the operator did not declare acquisition hardware as the signal source; no equipment manifest; the data is declared synthetic; overlap 11 s < 240 s required for a hardware-validation run.

## Summary

| Quantity | Value |
| --- | --- |
| acquisition protocol | Lab Streaming Layer (reference: XDF) |
| stream | hwval-clean-5491 (EEG) on vm |
| channels | 8 |
| channel labels | ["T1", "T2", "T3", "T4", "T5", "T6", "T7", "T8"] |
| nominal rate hz | 1000 |
| effective rate reference hz | 1000 |
| effective rate concord hz | 1000 |
| reference samples | 14020 |
| concord samples | 10640 |
| overlap s | 10.64 |
| samples compared | 10640 |
| missing in concord | 0 |
| estimated loss fraction | 0 |
| duplicated in concord | 0 |
| concord samples without counterpart | 0 |
| values out of tolerance | 0 |
| max abs value diff | 0 |
| max timestamp discrepancy s | 4.547e-13 |
| reference clock drift ppm | 1.8364 |
| concord ingest drift ppm | -12.1967 |
| latency median s | 0.00441599 |
| excess delay max s | 0.00911498 |
| reference discontinuities | 0 |
| result | pass |

## Checks

| Check | Status | Required | Finding |
| --- | --- | --- | --- |
| `REF-FILE` Reference XDF stream is readable and consistent | PASS | yes | 14020 samples read by pyxdf (footer sample_count 14019 vs 14020 samples read (LabRecorder footer count; the samples themselves are authoritative)) |
| `CONCORD-FILE` Concord recording file is complete and well-formed | PASS | yes | 501 frames, every line readable, seq contiguous, contract-valid |
| `IDENTITY` Both recordings are of the same LSL stream | PASS | yes | same LSL outlet (uid 22b95506-c162-407f-8bf2-45b67384afb3) |
| `META-CHANNELS` Channel count and channel identities agree | PASS | yes | 8 channels, labels identical in order |
| `META-RATE` Declared sampling rate agrees | PASS | yes | 1000 Hz on both sides |
| `META-FORMAT` Stream type and sample format agree | PASS | yes | EEG / float32 |
| `META-UNITS` Units are interpreted correctly | PASS | yes | reference declares voltage units; Concord reports µV |
| `PROVENANCE` Synthetic / prerecorded declarations are carried through | PASS | yes | declarations consistent (the data is declared synthetic) |
| `OVERLAP` Recordings overlap enough to compare | PASS | yes | 10.64 s of the recordings overlap (10640 samples) |
| `SAMPLE-COUNT` Sample counts agree within the overlap | PASS | yes | reference 10640 vs Concord 10640 samples in the overlap |
| `LOSS` No samples missing in Concord | PASS | yes | no reference sample is missing from Concord |
| `DUPLICATES` No duplicated samples in Concord | PASS | yes | none |
| `EXTRA` No Concord samples without a reference counterpart | PASS | yes | every Concord sample in the reference's range has a counterpart |
| `ORDER` Concord frames are in source order | PASS | yes | frames in source order |
| `ALIGN-CONTENT` Alignment confirmed by signal content (independent of timestamps) | PASS | yes | 24 probed frame(s) found by content exactly where their timestamps/indices place them |
| `VALUES` Signal values agree within the expected numerical tolerance | PASS | yes | all 85120 values agree (85120 bit-exact) |
| `CHANNEL-ORDER` Channels are in the reference order | PASS | yes | every channel matches its reference channel |
| `SCALE` Scaling and units are correct | PASS | yes | values equal the reference in the stated unit (factor 1) |
| `LOSS-FLAGGED` Concord reported every loss it suffered | PASS | yes | no loss to report |
| `TS-AGREE` Timestamps agree with the reference | PASS | yes | first-sample timestamps of 501 frames equal the source timestamps (max \|diff\| 4.5e-13 s) |
| `DELAY` Data was not delayed beyond the threshold | PASS | yes | worst excess ingest delay 9.1 ms (median 2.7 ms) vs threshold 1000 ms; absolute latency median 4.4 ms |
| `RATE-EFFECTIVE` Effective sampling rate matches the nominal rate | PASS | advisory | effective rate 1000.0000 Hz (+0.0 ppm from nominal) |
| `REF-CONTINUITY` Reference stream is continuous | PASS | advisory | the reference stream is continuous |
| `CLOCKS` Clock offset and drift characterised | PASS | advisory | recorder-source offset median -0.011 ms, drift +1.84 ppm; Concord wall clock vs source drift -12.20 ppm |
| `EQUIPMENT` Acquisition hardware and software are documented | not tested | advisory | no equipment manifest given (--equipment); the run is not traceable to hardware |

## Acquisition source

- **protocol**: Lab Streaming Layer
- **reference software**: XDF file (LabRecorder or compatible), read with pyxdf
- **xdf stream**: {"stream_id": 1, "name": "hwval-clean-5491", "type": "EEG", "source_id": "hwval-clean-5491-sid", "hostname": "vm", "uid": "22b95506-c162-407f-8bf2-45b67384af...
- **xdf file header**: {"version": "1.0", "datetime": "2026-11-08T00:56:27+0000"}
- **concord device**: {"device_id": "lsl:hwval-clean-5491-sid", "display_name": "LSL \u00b7 hwval-clean-5491 (EEG) \u2014 declared synthetic", "kind": "simulated", "adapter": "bra...
- **concord recording note**: Synthetic data (declared by the source).
- **concord schema version**: 1.4
- **capture sidecar**: {"concord_version": "0.3.0", "started_utc": "2026-11-08T00:56:30Z", "duration_s": 10.692358173, "stop_reason": "duration reached", "host": {"hostname": "vm",...
- **reference software version**: LabRecorder 1.16.4 (LabRecorderCLI) with liblsl 1.16.2

## Inputs

| Role | Path | Bytes | SHA-256 |
| --- | --- | --- | --- |
| reference_xdf | `/tmp/pytest-of-root/pytest-26/lr-clean0/labrecorder.xdf` | 527333 | `2e6e994a8accb2f4b35524ce4ca3faed476e7b3e3abcf1f93678500d44cf573d` |
| concord_recording | `/tmp/pytest-of-root/pytest-26/lr-clean0/concord.concord.jsonl` | 1825119 | `baf5f67182cb05b21421e7b107682f6fb818fe1d10551b812a9769c489c60096` |
| capture_sidecar | `/tmp/pytest-of-root/pytest-26/lr-clean0/concord.capture.json` | 3904 | `7407b5c04cff88e81ecb2b62b25913b2133a70dc590aee119d8cd4456eae2690` |

## Tests performed and evidence

### `REF-FILE` — Reference XDF stream is readable and consistent: PASS

*Method:* pyxdf loads the file (synchronize_clocks=False, dejitter_timestamps=False); sample and timestamp counts must agree.

*Finding:* 14020 samples read by pyxdf (footer sample_count 14019 vs 14020 samples read (LabRecorder footer count; the samples themselves are authoritative))

| Evidence | Value |
| --- | --- |
| samples | 14020 |
| pyxdf_effective_srate | 1000 |

<details><summary>footer</summary>

```json
{
 "first_timestamp": "3929.429074409",
 "last_timestamp": "3943.448074409",
 "sample_count": "14019"
}
```
</details>

<details><summary>notes</summary>

```json
[
 "footer sample_count 14019 vs 14020 samples read (LabRecorder footer count; the samples themselves are authoritative)"
]
```
</details>

### `CONCORD-FILE` — Concord recording file is complete and well-formed: PASS

*Method:* Parse every line; require the concord.recording/1 header, contiguous envelope seq numbers (the recorder writes every published event), no recorder recovery/active marker next to the file, and — if Concord is installed — validation of every envelope against Concord's contract models.

*Finding:* 501 frames, every line readable, seq contiguous, contract-valid

| Evidence | Value |
| --- | --- |
| frames | 501 |
| malformed_lines | 0 |
| seq_gaps | 0 |
| seq_regressions | 0 |
| recovery_marker | — |
| active_marker | False |

<details><summary>event_counts</summary>

```json
{
 "recording.frame": 501
}
```
</details>

<details><summary>contract</summary>

```json
{
 "validated": true,
 "valid_events": 501,
 "invalid_events": 0
}
```
</details>

### `IDENTITY` — Both recordings are of the same LSL stream: PASS

*Method:* XDF stream chosen by the capture sidecar's uid, else the stream name/source_id/host in the Concord device descriptor, else a unique channel count + rate; then every identity field available on both sides must agree.

*Finding:* same LSL outlet (uid 22b95506-c162-407f-8bf2-45b67384afb3)

| Evidence | Value |
| --- | --- |
| selected_by | same LSL stream uid (capture sidecar) |

<details><summary>xdf_stream</summary>

```json
{
 "stream_id": 1,
 "name": "hwval-clean-5491",
 "type": "EEG",
 "source_id": "hwval-clean-5491-sid",
 "hostname": "vm",
 "uid": "22b95506-c162-407f-8bf2-45b67384afb3",
 "channel_count": 8,
 "nominal_srate": 1000.0,
 "channel_format": "float32",
 "samples": 14020,
 "channels_described": true,
 "manufacturer": "concord-hwval test signal (synthetic)",
 "declaration": {
  "prerecorded": "false",
  "synthetic": "true"
 }
}
```
</details>

<details><summary>concord_descriptor_identity</summary>

```json
{
 "name": "hwval-clean-5491",
 "hostname": "vm",
 "source_id": "hwval-clean-5491-sid",
 "type": "EEG"
}
```
</details>

<details><summary>sidecar_identity</summary>

```json
{
 "name": "hwval-clean-5491",
 "type": "EEG",
 "source_id": "hwval-clean-5491-sid",
 "hostname": "vm",
 "uid": "22b95506-c162-407f-8bf2-45b67384afb3"
}
```
</details>

<details><summary>streams_in_file</summary>

```json
[
 {
  "stream_id": 1,
  "name": "hwval-clean-5491",
  "type": "EEG",
  "source_id": "hwval-clean-5491-sid",
  "channel_count": 8,
  "nominal_srate": 1000.0,
  "samples": 14020
 }
]
```
</details>

### `META-CHANNELS` — Channel count and channel identities agree: PASS

*Method:* Channel count of every Concord frame and of the descriptor equals the XDF channel_count; the descriptor's channel_labels equal the XDF <channel><label> list in order (Concord names an unlabelled channel 'ch<i>').

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

<details><summary>concord_labels</summary>

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

*Method:* sample_rate_hz of every Concord frame and of the descriptor equals the XDF nominal_srate.

*Finding:* 1000 Hz on both sides

| Evidence | Value |
| --- | --- |
| reference_nominal_srate | 1000 |
| concord_descriptor_rate | 1000 |

<details><summary>concord_frame_rates</summary>

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

<details><summary>concord</summary>

```json
{
 "type": "EEG",
 "channel_format": "float32"
}
```
</details>

### `META-UNITS` — Units are interpreted correctly: PASS

*Method:* If every XDF channel declares a known voltage unit (microvolts, millivolts, volts, nanovolts and abbreviations), Concord must label frames 'uV' (values converted); otherwise it must label them 'arbitrary' (values unscaled).

*Finding:* reference declares voltage units; Concord reports µV

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

<details><summary>concord_units</summary>

```json
[
 "uV"
]
```
</details>

### `PROVENANCE` — Synthetic / prerecorded declarations are carried through: PASS

*Method:* The publisher's optional <desc><concord><synthetic>/<prerecorded> declarations must appear as provenance synthetic / replayed on every Concord frame, and Concord must not add them on its own.

*Finding:* declarations consistent (the data is declared synthetic)

<details><summary>reference_declaration</summary>

```json
{
 "prerecorded": "false",
 "synthetic": "true"
}
```
</details>

<details><summary>concord</summary>

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
  "lsl:hwval-clean-5491@vm"
 ],
 "adapters": [
  "concord.lsl@0.1.0"
 ]
}
```
</details>

### `OVERLAP` — Recordings overlap enough to compare: PASS

*Method:* Span from the first to the last reference sample that a Concord frame maps to. Concord samples before the reference started or after it stopped are not compared and not counted as errors.

*Finding:* 10.64 s of the recordings overlap (10640 samples)

| Evidence | Value |
| --- | --- |
| overlap_rows | 10640 |
| overlap_s | 10.64 |
| reference_rows | 14020 |
| concord_samples | 10640 |
| concord_samples_outside_reference | 0 |
| concord_samples_past_reference_end | 0 |
| min_overlap_s | 5 |

<details><summary>reference_row_span</summary>

```json
[
 3120,
 13760
]
```
</details>

### `SAMPLE-COUNT` — Sample counts agree within the overlap: PASS

*Method:* Count reference samples between the first and last Concord sample and the Concord samples mapped onto them (each counted once per frame that claims it).

*Finding:* reference 10640 vs Concord 10640 samples in the overlap

| Evidence | Value |
| --- | --- |
| reference_samples_in_overlap | 10640 |
| concord_samples_mapped_into_overlap | 10640 |
| difference | 0 |
| reference_total | 14020 |
| concord_total | 10640 |

### `LOSS` — No samples missing in Concord: PASS

*Method:* Reference samples inside the overlap that no Concord frame maps to.

*Finding:* no reference sample is missing from Concord

| Evidence | Value |
| --- | --- |
| missing_samples | 0 |
| missing_fraction | 0 |
| missing_runs | 0 |
| max_loss_fraction | 0 |
| estimated_lost_duration_s | 0 |

### `DUPLICATES` — No duplicated samples in Concord: PASS

*Method:* Reference samples claimed by more than one Concord frame.

*Finding:* none

| Evidence | Value |
| --- | --- |
| duplicated_samples | 0 |

### `EXTRA` — No Concord samples without a reference counterpart: PASS

*Method:* Concord frames whose first-sample key lies within the reference's range but matches no reference sample.

*Finding:* every Concord sample in the reference's range has a counterpart

| Evidence | Value |
| --- | --- |
| concord_samples_without_counterpart | 0 |
| frames | 0 |
| frames_inside_a_reference_gap | 0 |
| content_found_elsewhere | 0 |

### `ORDER` — Concord frames are in source order: PASS

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

*Method:* Every Concord sample is compared with the reference sample it maps to, channel by channel: |concord - reference| <= tolerance. |diff| <= 0 + 2.5e-07 x |reference| (reference converted to Concord's unit in float64). Bit-exact values are counted separately ('exact'); a difference at single-precision level is an expected numerical tolerance.

*Finding:* all 85120 values agree (85120 bit-exact)

| Evidence | Value |
| --- | --- |
| tolerance | |diff| <= 0 + 2.5e-07 x |reference| (reference converted to Concord's unit in float64). Bit-exact values are counted separately ('exact'); a difference at single-precision level is an expected numerical tolerance. |
| values_compared | 85120 |
| values_exactly_equal | 85120 |
| values_out_of_tolerance | 0 |
| max_abs_diff | 0 |
| values_excluded_clipped_in_reference | 0 |

<details><summary>per_channel</summary>

```json
[
 {
  "compared": 10640,
  "exact": 10640,
  "within_tolerance": 10640,
  "within_float32": 10640,
  "out_of_tolerance": 0,
  "excluded_clipped_in_reference": 0,
  "max_abs_diff": 0.0,
  "rms_diff": 0.0,
  "channel": "T1"
 },
 {
  "compared": 10640,
  "exact": 10640,
  "within_tolerance": 10640,
  "within_float32": 10640,
  "out_of_tolerance": 0,
  "excluded_clipped_in_reference": 0,
  "max_abs_diff": 0.0,
  "rms_diff": 0.0,
  "channel": "T2"
 },
 {
  "compared": 10640,
  "exact": 10640,
  "within_tolerance": 10640,
  "within_float32": 10640,
  "out_of_tolerance": 0,
  "excluded_clipped_in_reference": 0,
  "max_abs_diff": 0.0,
  "rms_diff": 0.0,
  "channel": "T3"
 },
 {
  "compared": 10640,
  "exact": 10640,
  "within_tolerance": 10640,
  "within_float32": 10640,
  "out_of_tolerance": 0,
  "excluded_clipped_in_reference": 0,
  "max_abs_diff": 0.0,
  "rms_diff": 0.0,
  "channel": "T4"
 },
 {
  "compared": 10640,
  "exact": 10640,
  "within_tolerance": 10640,
  "within_float32": 10640,
  "out_of_tolerance": 0,
  "excluded_clipped_in_reference": 0,
  "max_abs_diff": 0.0,
  "rms_diff": 0.0,
  "channel": "T5"
 },
 {
  "compared": 10640,
  "exact": 10640,
  "within_tolerance": 10640,
  "within_float32": 10640,
  "out_of_tolerance": 0,
  "excluded_clipped_in_reference": 0,
  "max_abs_diff": 0.0,
  "rms_diff": 0.0,
  "channel": "T6"
 },
 {
  "compared": 10640,
  "exact": 10640,
  "within_tolerance": 10640,
  "within_float32": 10640,
  "out_of_tolerance": 0,
  "excluded_clipped_in_reference": 0,
  "max_abs_diff": 0.0,
  "rms_diff": 0.0,
  "channel": "T7"
 },
 {
  "compared": 10640,
  "exact": 10640,
  "within_tolerance": 10640,
  "within_float32": 10640,
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

*Method:* Every Concord channel is matched against every reference channel on a thin sample.

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

### `LOSS-FLAGGED` — Concord reported every loss it suffered: PASS

*Method:* For each run of samples missing in Concord, the next Concord frame must carry the quality flag dropped_samples, or a device.status event (reconnecting, ...) must lie between the frames around the gap.

*Finding:* no loss to report

| Evidence | Value |
| --- | --- |
| loss_runs | 0 |
| reported_by_frame_flag | 0 |
| reported_by_device_status | 0 |
| unreported_runs | 0 |
| frames_flagged_dropped_samples | 0 |

### `TS-AGREE` — Timestamps agree with the reference: PASS

*Method:* Each Concord frame's device_timestamp_ns (source clock) is compared with the XDF raw timestamp of the sample it maps to; both are copies of the source's timestamps, so any difference above 2e-06 s is an error. Frames located by content at another sample are timestamp errors.

*Finding:* first-sample timestamps of 501 frames equal the source timestamps (max |diff| 4.5e-13 s)

| Evidence | Value |
| --- | --- |
| frames_with_timestamp_match | 501 |
| max_abs_diff_s | 4.547e-13 |
| median_diff_s | 0 |
| exact_tolerance_s | 2e-06 |
| frames_whose_timestamp_contradicts_content | 0 |
| intra_frame_reconstruction_max_error_s | 4.547e-13 |

### `DELAY` — Data was not delayed beyond the threshold: PASS

*Method:* Concord ingest wall clock minus the source time of each frame's last sample; the excess over the smallest observed value is the variable delay (buffering, transport, stalls). Absolute latency uses the clock pair measured by `concord-hwval capture`.

*Finding:* worst excess ingest delay 9.1 ms (median 2.7 ms) vs threshold 1000 ms; absolute latency median 4.4 ms

| Evidence | Value |
| --- | --- |
| frames | 501 |
| excess_delay_median_s | 0.00270247 |
| excess_delay_p95_s | 0.00520921 |
| excess_delay_max_s | 0.00911498 |
| drift_ppm | -12.1967 |
| latency_median_s | 0.00441599 |
| latency_p95_s | 0.00692272 |
| latency_max_s | 0.0108285 |
| latency_min_s | 0.00171351 |

<details><summary>fit</summary>

```json
{
 "slope": -1.2196694109325543e-05,
 "intercept": 1794095457.8386068,
 "residual_std": 0.0015802422321954323,
 "residual_max_abs": 0.0063326358795166016,
 "n": 501
}
```
</details>

### `RATE-EFFECTIVE` — Effective sampling rate matches the nominal rate: PASS

*Method:* Linear fit of the reference's raw timestamps against sample number over the longest gap-free segment; the same fit over Concord frame timestamps vs first_sample_index. Advisory: this measures the source, not Concord.

*Finding:* effective rate 1000.0000 Hz (+0.0 ppm from nominal)

| Evidence | Value |
| --- | --- |
| nominal_hz | 1000 |
| reference_rate_hz | 1000 |
| reference_ppm | 0 |
| concord_rate_hz | 1000 |
| concord_ppm | -2.22e-10 |
| advisory_threshold_ppm | 500 |

<details><summary>reference_segment</summary>

```json
{
 "rate_hz": 1000.0,
 "segment_rows": [
  0,
  14020
 ],
 "segment_s": 14.018999999999778,
 "timestamp_jitter_std_s": 0.0,
 "timestamp_jitter_max_s": 4.547473508864641e-13
}
```
</details>

### `REF-CONTINUITY` — Reference stream is continuous: PASS

*Method:* Per-sample XDF timestamps: an interval > 1.5 periods (and > 2 ms beyond one period) is a gap; a non-increasing timestamp is a regression. Advisory: a discontinuity here is in the source or in LabRecorder, not in Concord.

*Finding:* the reference stream is continuous

| Evidence | Value |
| --- | --- |
| concord_frames_flagged_dropped_samples | 0 |

<details><summary>reference</summary>

```json
{
 "gaps": 0,
 "regressions": 0,
 "est_missing": 0,
 "examples": []
}
```
</details>

### `CLOCKS` — Clock offset and drift characterised: PASS

*Method:* Linear fit of LabRecorder's ClockOffset chunks (recorder minus source clock) against time; separately, Concord ingest wall clock minus source time against source time. Advisory: these characterise the clocks involved; offsets between clock domains are expected and are not errors.

*Finding:* recorder-source offset median -0.011 ms, drift +1.84 ppm; Concord wall clock vs source drift -12.20 ppm

<details><summary>labrecorder_clock_offsets</summary>

```json
{
 "measurements": 3,
 "usable": 3,
 "discarded": 0,
 "offset_median_s": -1.0747000260380446e-05,
 "offset_min_s": -2.7745500119635835e-05,
 "offset_max_s": -9.380999927088851e-06,
 "drift_ppm": 1.8364000297446728,
 "fit": {
  "slope": 1.8364000297446727e-06,
  "intercept": -0.007251538952694455,
  "residual_std": 3.6846397899943024e-06,
  "residual_max_abs": 5.210867563442377e-06,
  "n": 3
 },
 "span_s": 10.000256274499861
}
```
</details>

<details><summary>concord_ingest_vs_source</summary>

```json
{
 "frames": 501,
 "excess_delay_median_s": 0.002702474594116211,
 "excess_delay_p95_s": 0.005209207534790039,
 "excess_delay_max_s": 0.009114980697631836,
 "drift_ppm": -12.196694109325543,
 "fit": {
  "slope": -1.2196694109325543e-05,
  "intercept": 1794095457.8386068,
  "residual_std": 0.0015802422321954323,
  "residual_max_abs": 0.0063326358795166016,
  "n": 501
 },
 "latency_median_s": 0.004415988922119141,
 "latency_p95_s": 0.006922721862792969,
 "latency_max_s": 0.010828495025634766,
 "latency_min_s": 0.0017135143280029297
}
```
</details>

### `EQUIPMENT` — Acquisition hardware and software are documented: not tested

*Method:* Required fields of the concord-hwval.equipment/1 manifest must be filled in.

*Finding:* no equipment manifest given (--equipment); the run is not traceable to hardware

## Limitations

- Both recordings receive the stream through liblsl. A defect that liblsl itself introduced before either inlet (e.g. in the outlet's buffer) would be invisible to this comparison; comparing against the acquisition device's own file format closes that gap.
- Concord stores one source timestamp per frame (its first sample); per-sample timestamps inside a frame are reconstructed as first + k / nominal rate. The reconstruction error is reported but Concord cannot be checked for per-sample timestamp fidelity.
- LSL carries no sequence numbers: a sample lost before both inlets (at the source) appears as the same gap in both recordings and is reported as a source discontinuity, not as Concord loss.
- Absolute ingest latency needs the clock pair measured by `concord-hwval capture`; otherwise only delay variation (excess over the best case) and drift are measured.
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
  "concord_hwval": "0.1.0",
  "python": "3.12.3",
  "platform": "Linux-6.18.44-fc-v310-x86_64-with-glibc2.39",
  "numpy": "2.5.4",
  "pyxdf": "1.18.0",
  "open_ephys_python_tools": "1.0.1",
  "concord": "0.3.0"
 },
 "command": null,
 "tool": "concord-hwval 0.1.0",
 "created_at": "2026-11-08T00:56:44Z"
}
```
