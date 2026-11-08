# Concord acquisition verification — openephys

**Result: PASS**

> PASS: all 20 required checks passed.

## What this result means

- Evidence level of this run: **software_acquisition_comparison**
- Concord received, over the Open Ephys ZMQ Interface, exactly the data the reference software recorded from the same source, within the stated tolerances. This is software-level evidence about the acquisition path; it says nothing about hardware unless the source was real hardware and the hardware criteria below are met.
- Hardware verified: **no** (never set by this tool). Human validated: **no**.
- Not a hardware-validation run because: the operator did not declare acquisition hardware as the signal source; no equipment manifest; the reference stream's source processor is 'File Reader' (file playback, not hardware); overlap 7 s < 240 s required for a hardware-validation run.

## Summary

| Quantity | Value |
| --- | --- |
| acquisition protocol | Open Ephys GUI: ZMQ Interface (reference: Record Node, Binary) |
| stream | example_data from File Reader |
| gui version | 1.1.0 |
| channels | 16 |
| channel names | ["CH1", "CH2", "CH3", "CH4", "CH5", "CH6", "CH7", "CH8", "CH9", "CH10", "CH11", "CH12", "CH13", "CH14", "CH15", "CH16"] |
| sample rate hz | 40000 |
| reference samples | 297215 |
| concord samples | 279568 |
| overlap s | 6.9892 |
| samples compared | 279568 |
| missing in concord | 0 |
| estimated loss fraction | 0 |
| duplicated in concord | 0 |
| concord samples without counterpart | 0 |
| values out of tolerance | 0 |
| max abs value diff uV | 1.456e-05 |
| concord ingest drift ppm | -44.0247 |
| excess delay max s | 0.00228357 |
| reference sample number breaks | 1 |
| result | pass |

## Checks

| Check | Status | Required | Finding |
| --- | --- | --- | --- |
| `REF-FILE` Reference Binary recording is readable and consistent | PASS | yes | 297215 rows x 16 channels |
| `REF-READER` Parser agrees with the official Open Ephys reader | PASS | advisory | identical to open-ephys-python-tools 1.0.1 |
| `CONCORD-FILE` Concord recording file is complete and well-formed | PASS | yes | 301 frames, every line readable, seq contiguous, contract-valid |
| `IDENTITY` Both recordings are of the same Open Ephys stream | PASS | yes | same Open Ephys stream 'example_data' |
| `META-CHAIN` ZMQ Interface and Record Node see the same data | PASS | yes | signal chain 'File Reader -> ZMQ Interface -> Record Node' |
| `META-CHANNELS` Channel count and channel identities agree | PASS | yes | 16 channels, names identical in order |
| `META-RATE` Declared sampling rate agrees | PASS | yes | 40000 Hz on both sides |
| `META-UNITS` Units are interpreted correctly | PASS | yes | Concord 'uV' matches the file's units |
| `OVERLAP` Recordings overlap enough to compare | PASS | yes | 6.99 s of the recordings overlap (279568 samples) |
| `SAMPLE-COUNT` Sample counts agree within the overlap | PASS | yes | reference 279568 vs Concord 279568 samples in the overlap |
| `LOSS` No samples missing in Concord | PASS | yes | no reference sample is missing from Concord |
| `DUPLICATES` No duplicated samples in Concord | PASS | yes | none |
| `EXTRA` No Concord samples without a reference counterpart | PASS | yes | every Concord sample in the reference's range has a counterpart |
| `ORDER` Concord frames are in source order | PASS | yes | frames in source order |
| `ALIGN-CONTENT` Alignment confirmed by signal content (independent of timestamps) | PASS | yes | 24 probed frame(s) found by content exactly where their timestamps/indices place them; 15 ambiguous |
| `VALUES` Signal values agree within the expected numerical tolerance | PASS | yes | all 4473088 values agree (1029 bit-exact, 4472059 within single precision) |
| `CHANNEL-ORDER` Channels are in the reference order | PASS | yes | every channel matches its reference channel |
| `SCALE` Scaling and units are correct | PASS | yes | values equal the reference in the stated unit (factor 1) |
| `LOSS-FLAGGED` Concord reported every loss it suffered | PASS | yes | no loss to report |
| `TS-AGREE` Timestamps agree with the sample clock | PASS | yes | all 301 frame timestamps equal sample_number / rate; reference timestamps.npy minus Concord: median 0 s |
| `EVENTS` TTL events agree | not tested | advisory | no TTL events in either recording (use a pulse generator to test events) |
| `DELAY` Data was not delayed beyond the threshold | PASS | yes | worst excess ingest delay 2.3 ms (median 0.6 ms) vs threshold 1000 ms |
| `REF-CONTINUITY` Reference recording is continuous | INCONCLUSIVE | advisory | the reference has 0 sample-number jump(s) (0 numbers absent) and 1 reset(s)/regression(s): a discontinuity in the acquisition or recording (e.g. the File Reader looping, a restart) |
| `EQUIPMENT` Acquisition hardware and software are documented | not tested | advisory | no equipment manifest given (--equipment); the run is not traceable to hardware |

## Acquisition source

- **protocol**: Open Ephys ZMQ Interface
- **reference software**: Open Ephys GUI 1.1.0 Record Node (Binary format)
- **reference recording**: /tmp/pytest-of-root/pytest-321/test_gui_file_reader_loop_rese0/ref/2026-11-08_04-34-48/Record Node 102/experiment1/recording1
- **reference stream**: {"folder_name": "File_Reader-100.example_data", "stream_name": "example_data", "sample_rate": 40000.0, "source_processor": "File Reader (100)", "num_channels...
- **concord device**: {"device_id": "openephys:127.0.0.1:57779", "display_name": "Open Ephys (ZMQ) \u00b7 127.0.0.1:57779", "kind": "stream", "adapter": "concord.openephys.zmq@0.1...
- **concord recording params**: {"unit": "uV", "source_unit": "uV", "channel_count": 16, "sample_rate_hz": 40000.0, "channel_names": ["CH1", "CH2", "CH3", "CH4", "CH5", "CH6", "CH7", "CH8",...
- **sync messages**: Software Time (milliseconds since midnight Jan 1st 1970 UTC): 1794112489440
Start Time for File Reader (100) - example_data @ 40000 Hz: 0


## Inputs

| Role | Path | Bytes | SHA-256 |
| --- | --- | --- | --- |
| reference_openephys_recording | `/tmp/pytest-of-root/pytest-321/test_gui_file_reader_loop_rese0/ref/2026-11-08_04-34-48/Record Node 102/experiment1/recording1` | 14273938 | `26e3476d659d7d886e2e32951c5090ad98a6738278946c41a88a8489d0a6138a` |
| concord_recording | `/tmp/pytest-of-root/pytest-321/test_gui_file_reader_loop_rese0/concord.concord.jsonl` | 72824239 | `f4f04e3ff8df6a5d1158e76836f186d8ec5f13e963d24b1222a3eef5cdec0276` |

## Tests performed and evidence

### `REF-FILE` — Reference Binary recording is readable and consistent: PASS

*Method:* structure.oebin parsed; continuous.dat size a multiple of channels x 2 bytes; sample_numbers.npy and timestamps.npy have one entry per row.

*Finding:* 297215 rows x 16 channels

| Evidence | Value |
| --- | --- |
| rows | 297215 |

<details><summary>sample_numbers</summary>

```json
{
 "jumps": 0,
 "regressions": 1,
 "missing_numbers": 0,
 "examples": [
  {
   "after_row": 200619,
   "sample_number": 200619,
   "next": 646
  }
 ]
}
```
</details>

<details><summary>official_reader</summary>

```json
{
 "status": "pass",
 "reader": "open-ephys-python-tools 1.0.1",
 "rows_compared": "all sample numbers; scaled values at rows 0, 148607, 297214",
 "problems": []
}
```
</details>

### `REF-READER` — Parser agrees with the official Open Ephys reader: PASS

*Method:* Load the same recording with open-ephys-python-tools (BinaryRecording) and compare channel names, bit_volts, sample rate, every sample number, scaled values at three rows and the TTL event count. Required only if it fails.

*Finding:* identical to open-ephys-python-tools 1.0.1

| Evidence | Value |
| --- | --- |
| status | pass |
| reader | open-ephys-python-tools 1.0.1 |
| rows_compared | all sample numbers; scaled values at rows 0, 148607, 297214 |

### `CONCORD-FILE` — Concord recording file is complete and well-formed: PASS

*Method:* Parse every line; require the concord.recording/1 header, contiguous envelope seq numbers (the recorder writes every published event), no recorder recovery/active marker next to the file, and — if Concord is installed — validation of every envelope against Concord's contract models.

*Finding:* 301 frames, every line readable, seq contiguous, contract-valid

| Evidence | Value |
| --- | --- |
| frames | 301 |
| malformed_lines | 0 |
| seq_gaps | 0 |
| seq_regressions | 0 |
| recovery_marker | — |
| active_marker | False |

<details><summary>event_counts</summary>

```json
{
 "recording.frame": 301
}
```
</details>

<details><summary>contract</summary>

```json
{
 "validated": true,
 "valid_events": 301,
 "invalid_events": 0
}
```
</details>

### `IDENTITY` — Both recordings are of the same Open Ephys stream: PASS

*Method:* Concord descriptor 'stream' equals the structure.oebin stream_name; every Concord channel name exists in the reference; the Concord adapter is the Open Ephys ZMQ adapter.

*Finding:* same Open Ephys stream 'example_data'

| Evidence | Value |
| --- | --- |
| concord_stream | example_data |
| concord_adapter | concord.openephys.zmq@0.1.0 |
| gui_version | 1.1.0 |

<details><summary>reference_stream</summary>

```json
{
 "folder_name": "File_Reader-100.example_data",
 "stream_name": "example_data",
 "sample_rate": 40000.0,
 "source_processor": "File Reader (100)",
 "num_channels": 16,
 "channel_names": [
  "CH1",
  "CH2",
  "CH3",
  "CH4",
  "CH5",
  "CH6",
  "CH7",
  "CH8",
  "CH9",
  "CH10",
  "CH11",
  "CH12",
  "CH13",
  "CH14",
  "CH15",
  "CH16"
 ],
 "units": [
  "uV"
 ],
 "bit_volts": [
  0.0500000007
 ],
 "samples": 297215,
 "first_sample_number": 0,
 "last_sample_number": 97240,
 "history": [
  "File Reader -> ZMQ Interface -> Record Node"
 ],
 "problems": []
}
```
</details>

<details><summary>reference_streams</summary>

```json
[
 "example_data"
]
```
</details>

<details><summary>concord_origin</summary>

```json
[
 "openephys:127.0.0.1:57779/example_data"
]
```
</details>

### `META-CHAIN` — ZMQ Interface and Record Node see the same data: PASS

*Method:* Each channel's 'history' in structure.oebin must contain the ZMQ Interface with no processor between it and the Record Node; otherwise Concord and the file legitimately carry different values.

*Finding:* signal chain 'File Reader -> ZMQ Interface -> Record Node'

| Evidence | Value |
| --- | --- |
| source_processor | File Reader |

<details><summary>history</summary>

```json
[
 "File Reader -> ZMQ Interface -> Record Node"
]
```
</details>

### `META-CHANNELS` — Channel count and channel identities agree: PASS

*Method:* Concord channel_names (sent by the ZMQ Interface) must each be a reference channel_name, in reference order; the ZMQ Interface may send a selection.

*Finding:* 16 channels, names identical in order

<details><summary>concord_channels</summary>

```json
[
 "CH1",
 "CH2",
 "CH3",
 "CH4",
 "CH5",
 "CH6",
 "CH7",
 "CH8",
 "CH9",
 "CH10",
 "CH11",
 "CH12",
 "CH13",
 "CH14",
 "CH15",
 "CH16"
]
```
</details>

<details><summary>reference_channels</summary>

```json
[
 "CH1",
 "CH2",
 "CH3",
 "CH4",
 "CH5",
 "CH6",
 "CH7",
 "CH8",
 "CH9",
 "CH10",
 "CH11",
 "CH12",
 "CH13",
 "CH14",
 "CH15",
 "CH16"
]
```
</details>

<details><summary>mapping</summary>

```json
[
 0,
 1,
 2,
 3,
 4,
 5,
 6,
 7,
 8,
 9,
 10,
 11,
 12,
 13,
 14,
 15
]
```
</details>

### `META-RATE` — Declared sampling rate agrees: PASS

*Method:* sample_rate_hz of every frame and of the descriptor equals the structure.oebin sample_rate.

*Finding:* 40000 Hz on both sides

| Evidence | Value |
| --- | --- |
| reference | 40000 |
| concord_descriptor | 40000 |

<details><summary>concord_frames</summary>

```json
[
 40000.0
]
```
</details>

### `META-UNITS` — Units are interpreted correctly: PASS

*Method:* If Concord reports µV, the operator-declared unit must equal the structure.oebin channel units; 'arbitrary' is always a correct label for this protocol.

*Finding:* Concord 'uV' matches the file's units

| Evidence | Value |
| --- | --- |
| concord_source_unit | uV |

<details><summary>concord_units</summary>

```json
[
 "uV"
]
```
</details>

<details><summary>reference_units</summary>

```json
[
 "uV"
]
```
</details>

### `OVERLAP` — Recordings overlap enough to compare: PASS

*Method:* Span from the first to the last reference sample that a Concord frame maps to. Concord samples before the reference started or after it stopped are not compared and not counted as errors.

*Finding:* 6.99 s of the recordings overlap (279568 samples)

| Evidence | Value |
| --- | --- |
| overlap_rows | 279568 |
| overlap_s | 6.9892 |
| reference_rows | 297215 |
| concord_samples | 279568 |
| concord_samples_outside_reference | 0 |
| concord_samples_past_reference_end | 0 |
| min_overlap_s | 2 |

<details><summary>reference_row_span</summary>

```json
[
 2786,
 282354
]
```
</details>

### `SAMPLE-COUNT` — Sample counts agree within the overlap: PASS

*Method:* Count reference samples between the first and last Concord sample and the Concord samples mapped onto them (each counted once per frame that claims it).

*Finding:* reference 279568 vs Concord 279568 samples in the overlap

| Evidence | Value |
| --- | --- |
| reference_samples_in_overlap | 279568 |
| concord_samples_mapped_into_overlap | 279568 |
| difference | 0 |
| reference_total | 297215 |
| concord_total | 279568 |

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

*Finding:* 24 probed frame(s) found by content exactly where their timestamps/indices place them; 15 ambiguous

| Evidence | Value |
| --- | --- |
| probed | 24 |
| probed_mapped_by_key | 24 |
| probed_unmapped | 0 |
| agree | 24 |
| disagree | 0 |
| not_found | 0 |
| ambiguous | 15 |

### `VALUES` — Signal values agree within the expected numerical tolerance: PASS

*Method:* Every Concord sample is compared with the reference sample it maps to, channel by channel: |concord - reference| <= tolerance. |diff| <= 0.51 x bit_volts of the channel ([0.0500000007] µV) — the Record Node's int16 rounding; samples clipped at the int16 limits are excluded.

*Finding:* all 4473088 values agree (1029 bit-exact, 4472059 within single precision)

| Evidence | Value |
| --- | --- |
| tolerance | |diff| <= 0.51 x bit_volts of the channel ([0.0500000007] µV) — the Record Node's int16 rounding; samples clipped at the int16 limits are excluded. |
| values_compared | 4473088 |
| values_exactly_equal | 1029 |
| values_out_of_tolerance | 0 |
| max_abs_diff | 1.456e-05 |
| values_excluded_clipped_in_reference | 0 |

<details><summary>per_channel</summary>

```json
[
 {
  "compared": 279568,
  "exact": 76,
  "within_tolerance": 279568,
  "within_float32": 279568,
  "out_of_tolerance": 0,
  "excluded_clipped_in_reference": 0,
  "max_abs_diff": 7.361173430808776e-06,
  "rms_diff": 1.0659732203351007e-06,
  "channel": "CH1"
 },
 {
  "compared": 279568,
  "exact": 62,
  "within_tolerance": 279568,
  "within_float32": 279568,
  "out_of_tolerance": 0,
  "excluded_clipped_in_reference": 0,
  "max_abs_diff": 7.361173430808776e-06,
  "rms_diff": 1.0817128729128248e-06,
  "channel": "CH2"
 },
 {
  "compared": 279568,
  "exact": 81,
  "within_tolerance": 279568,
  "within_float32": 279568,
  "out_of_tolerance": 0,
  "excluded_clipped_in_reference": 0,
  "max_abs_diff": 9.871615588963323e-06,
  "rms_diff": 1.0518803148822917e-06,
  "channel": "CH3"
 },
 {
  "compared": 279568,
  "exact": 69,
  "within_tolerance": 279568,
  "within_float32": 279568,
  "out_of_tolerance": 0,
  "excluded_clipped_in_reference": 0,
  "max_abs_diff": 1.4557846895968396e-05,
  "rms_diff": 1.04002111975479e-06,
  "channel": "CH4"
 },
 {
  "compared": 279568,
  "exact": 62,
  "within_tolerance": 279568,
  "within_float32": 279568,
  "out_of_tolerance": 0,
  "excluded_clipped_in_reference": 0,
  "max_abs_diff": 7.361173430808776e-06,
  "rms_diff": 1.0829444209218063e-06,
  "channel": "CH5"
 },
 {
  "compared": 279568,
  "exact": 58,
  "within_tolerance": 279568,
  "within_float32": 279568,
  "out_of_tolerance": 0,
  "excluded_clipped_in_reference": 0,
  "max_abs_diff": 7.361173430808776e-06,
  "rms_diff": 1.150424922722431e-06,
  "channel": "CH6"
 },
 {
  "compared": 279568,
  "exact": 53,
  "within_tolerance": 279568,
  "within_float32": 279568,
  "out_of_tolerance": 0,
  "excluded_clipped_in_reference": 0,
  "max_abs_diff": 7.361173430808776e-06,
  "rms_diff": 1.0304743690275394e-06,
  "channel": "CH7"
 },
 {
  "compared": 279568,
  "exact": 61,
  "within_tolerance": 279568,
  "within_float32": 279568,
  "out_of_tolerance": 0,
  "excluded_clipped_in_reference": 0,
  "max_abs_diff": 7.361173430808776e-06,
  "rms_diff": 1.0177601351140968e-06,
  "channel": "CH8"
 },
 {
  "compared": 279568,
  "exact": 64,
  "within_tolerance": 279568,
  "within_float32": 279568,
  "out_of_tolerance": 0,
  "excluded_clipped_in_reference": 0,
  "max_abs_diff": 7.361173430808776e-06,
  "rms_diff": 1.0006209973585254e-06,
  "channel": "CH9"
 },
 {
  "compared": 279568,
  "exact": 85,
  "within_tolerance": 279568,
  "within_float32": 279568,
  "out_of_tolerance": 0,
  "exclude
... (truncated; full evidence in the JSON report)
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
 },
 {
  "channel": 8,
  "expected_ref": 8,
  "best_ref": 8,
  "match_best": 1.0,
  "match_expected": 1.0
 },
 {
  "channel": 9,
  "expected_ref": 9,
  "best_ref": 9,
  "match_best": 1.0,
  "match_expected": 1.0
 },
 {
  "channel": 10,
  "expected_ref": 10,
  "best_ref": 10,
  "match_best": 1.0,
  "match_expected": 1.0
 },
 {
  "channel": 11,
  "expected_ref": 11,
  "best_ref": 11,
  "match_best": 1.0,
  "match_expected": 1.0
 },
 {
  "channel": 12,
  "expected_ref": 12,
  "best_ref": 12,
  "match_best": 1.0,
  "match_expected": 1.0
 },
 {
  "channel": 13,
  "expected_ref": 13,
  "best_ref": 13,
  "match_best": 1.0,
  "match_expected": 1.0
 },
 {
  "channel": 14,
  "expected_ref": 14,
  "best_ref": 14,
  "match_best": 1.0,
  "match_expected": 1.0
 },
 {
  "channel": 15,
  "expected_ref": 15,
  "best_ref": 15,
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
| unit_interpretation | Concord converted from the operator-declared unit 'uV' to µV; reference ['uV'] x bit_volts -> µV x 1 |

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

### `TS-AGREE` — Timestamps agree with the sample clock: PASS

*Method:* Concord device_timestamp_ns must equal round(sample_number / sample_rate x 1e9) (docs/OPEN_EPHYS.md); the Record Node's timestamps.npy (synchronised seconds) is compared as an offset/drift (it may be synchronised to another stream).

*Finding:* all 301 frame timestamps equal sample_number / rate; reference timestamps.npy minus Concord: median 0 s

| Evidence | Value |
| --- | --- |
| frames | 301 |
| mismatches | 0 |

<details><summary>reference_timestamps_npy_vs_concord</summary>

```json
{
 "reference_minus_concord_median_s": 0.0,
 "max_abs_s": 0.0,
 "drift_ppm": 0.0
}
```
</details>

### `EVENTS` — TTL events agree: not tested

*Method:* Reference TTL events (events/<stream>/TTL: sample_numbers, states = ±(line+1), full_words) within the sample range Concord covered are matched with Concord 'ttl' annotations (sample = device_timestamp x rate) on (sample, line, state).

*Finding:* no TTL events in either recording (use a pulse generator to test events)

### `DELAY` — Data was not delayed beyond the threshold: PASS

*Method:* Concord ingest wall clock minus the source time of each frame's last sample; the excess over the smallest observed value is the variable delay (buffering, transport, stalls). Without a measured clock pair, absolute latency is unknown.

*Finding:* worst excess ingest delay 2.3 ms (median 0.6 ms) vs threshold 1000 ms

| Evidence | Value |
| --- | --- |
| frames | 301 |
| excess_delay_median_s | 0.0006256 |
| excess_delay_p95_s | 0.00128269 |
| excess_delay_max_s | 0.00228357 |
| drift_ppm | -44.0247 |

<details><summary>fit</summary>

```json
{
 "slope": -4.4024735650814256e-05,
 "intercept": 1794112489.4186018,
 "residual_std": 0.00030673199009772313,
 "residual_max_abs": 0.0014982223510742188,
 "n": 301
}
```
</details>

### `REF-CONTINUITY` — Reference recording is continuous: INCONCLUSIVE

*Method:* Differences between successive sample_numbers.npy entries must be exactly 1.

*Finding:* the reference has 0 sample-number jump(s) (0 numbers absent) and 1 reset(s)/regression(s): a discontinuity in the acquisition or recording (e.g. the File Reader looping, a restart)

| Evidence | Value |
| --- | --- |
| jumps | 0 |
| regressions | 1 |
| missing_numbers | 0 |

<details><summary>examples</summary>

```json
[
 {
  "after_row": 200619,
  "sample_number": 200619,
  "next": 646
 }
]
```
</details>

### `EQUIPMENT` — Acquisition hardware and software are documented: not tested

*Method:* Required fields of the concord-hwval.equipment/1 manifest must be filled in.

*Finding:* no equipment manifest given (--equipment); the run is not traceable to hardware

## Limitations

- The Record Node stores 16-bit integers: values are verified to half a quantisation step (bit_volts / 2), not bit for bit. Samples at the int16 limits (clipped in the file) are excluded from the value comparison.
- Values are comparable only if no processor that changes data sits between the ZMQ Interface and the Record Node; the channel 'history' in structure.oebin is used to check this.
- The ZMQ Interface does not transmit units; unless the Concord operator declared the unit, Concord labels values 'arbitrary' and they are compared unscaled against the file's µV.
- Concord does not emit data received while it learns the stream layout on connect (docs/OPEN_EPHYS.md); that start-up interval is outside the overlap and is not loss.
- Data from the GUI's File Reader is file playback, not hardware, even though it passes through the real GUI and plugin.

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
  "min_overlap_s": 2.0,
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
 "created_at": "2026-11-08T04:35:00Z"
}
```
