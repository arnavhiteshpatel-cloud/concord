# Concord acquisition verification — openephys

**Result: INCONCLUSIVE**

> INCONCLUSIVE: META-CHAIN: processors between ZMQ Interface and Record Node: ['Bandpass Filter']; ALIGN-CONTENT: the data could not be located by content (signal too uniform or values differ): alignment rests on timestamps/indices alone; VALUES: 1916028 of 1917040 values differ beyond the expected tolerance — not comparable: processors between ZMQ Interface and Record Node: ['Bandpass Filter']; CHANNEL-ORDER: values differ, but not as a channel permutation; SCALE: values differ, but not by a constant factor or offset

## What this result means

- Evidence level of this run: **none**
- The comparison did not pass; this run supports no compatibility claim.
- Hardware verified: **no** (never set by this tool). Human validated: **no**.
- Not a hardware-validation run because: the comparison result is inconclusive, not pass; the operator did not declare acquisition hardware as the signal source; no equipment manifest; the reference stream's source processor is 'File Reader' (file playback, not hardware); overlap 3 s < 240 s required for a hardware-validation run.

## Summary

| Quantity | Value |
| --- | --- |
| acquisition protocol | Open Ephys GUI: ZMQ Interface (reference: Record Node, Binary) |
| stream | example_data from File Reader |
| gui version | 1.1.0 |
| channels | 16 |
| channel names | ["CH1", "CH2", "CH3", "CH4", "CH5", "CH6", "CH7", "CH8", "CH9", "CH10", "CH11", "CH12", "CH13", "CH14", "CH15", "CH16"] |
| sample rate hz | 40000 |
| reference samples | 135604 |
| concord samples | 119815 |
| overlap s | 2.99538 |
| samples compared | 119815 |
| missing in concord | 0 |
| estimated loss fraction | 0 |
| duplicated in concord | 0 |
| concord samples without counterpart | 0 |
| values out of tolerance | 1916028 |
| max abs value diff uV | 224.1 |
| concord ingest drift ppm | -144.992 |
| excess delay max s | 0.00233698 |
| reference sample number breaks | 0 |
| result | inconclusive |

## Checks

| Check | Status | Required | Finding |
| --- | --- | --- | --- |
| `REF-FILE` Reference Binary recording is readable and consistent | PASS | yes | 135604 rows x 16 channels |
| `REF-READER` Parser agrees with the official Open Ephys reader | PASS | advisory | identical to open-ephys-python-tools 1.0.1 |
| `CONCORD-FILE` Concord recording file is complete and well-formed | PASS | yes | 129 frames, every line readable, seq contiguous, contract-valid |
| `IDENTITY` Both recordings are of the same Open Ephys stream | PASS | yes | same Open Ephys stream 'example_data' |
| `META-CHAIN` ZMQ Interface and Record Node see the same data | INCONCLUSIVE | yes | processors between ZMQ Interface and Record Node: ['Bandpass Filter'] |
| `META-CHANNELS` Channel count and channel identities agree | PASS | yes | 16 channels, names identical in order |
| `META-RATE` Declared sampling rate agrees | PASS | yes | 40000 Hz on both sides |
| `META-UNITS` Units are interpreted correctly | PASS | yes | Concord 'uV' matches the file's units |
| `OVERLAP` Recordings overlap enough to compare | PASS | yes | 3.00 s of the recordings overlap (119815 samples) |
| `SAMPLE-COUNT` Sample counts agree within the overlap | PASS | yes | reference 119815 vs Concord 119815 samples in the overlap |
| `LOSS` No samples missing in Concord | PASS | yes | no reference sample is missing from Concord |
| `DUPLICATES` No duplicated samples in Concord | PASS | yes | none |
| `EXTRA` No Concord samples without a reference counterpart | PASS | yes | every Concord sample in the reference's range has a counterpart |
| `ORDER` Concord frames are in source order | PASS | yes | frames in source order |
| `ALIGN-CONTENT` Alignment confirmed by signal content (independent of timestamps) | INCONCLUSIVE | yes | the data could not be located by content (signal too uniform or values differ): alignment rests on timestamps/indices alone |
| `VALUES` Signal values agree within the expected numerical tolerance | INCONCLUSIVE | yes | 1916028 of 1917040 values differ beyond the expected tolerance — not comparable: processors between ZMQ Interface and Record Node: ['Bandpass Filter'] |
| `CHANNEL-ORDER` Channels are in the reference order | INCONCLUSIVE | yes | values differ, but not as a channel permutation |
| `SCALE` Scaling and units are correct | INCONCLUSIVE | yes | values differ, but not by a constant factor or offset |
| `LOSS-FLAGGED` Concord reported every loss it suffered | PASS | yes | no loss to report |
| `TS-AGREE` Timestamps agree with the sample clock | PASS | yes | all 129 frame timestamps equal sample_number / rate; reference timestamps.npy minus Concord: median 0 s |
| `EVENTS` TTL events agree | not tested | advisory | no TTL events in either recording (use a pulse generator to test events) |
| `DELAY` Data was not delayed beyond the threshold | PASS | yes | worst excess ingest delay 2.3 ms (median 0.4 ms) vs threshold 1000 ms |
| `REF-CONTINUITY` Reference recording is continuous | PASS | advisory | sample numbers are contiguous |
| `EQUIPMENT` Acquisition hardware and software are documented | not tested | advisory | no equipment manifest given (--equipment); the run is not traceable to hardware |

## Acquisition source

- **protocol**: Open Ephys ZMQ Interface
- **reference software**: Open Ephys GUI 1.1.0 Record Node (Binary format)
- **reference recording**: /tmp/pytest-of-root/pytest-26/test_gui_processor_between_zmq0/ref/2026-11-08_00-57-27/Record Node 103/experiment1/recording1
- **reference stream**: {"folder_name": "File_Reader-100.example_data", "stream_name": "example_data", "sample_rate": 40000.0, "source_processor": "File Reader (100)", "num_channels...
- **concord device**: {"device_id": "openephys:127.0.0.1:49573", "display_name": "Open Ephys (ZMQ) \u00b7 127.0.0.1:49573", "kind": "stream", "adapter": "concord.openephys.zmq@0.1...
- **concord recording params**: {"unit": "uV", "source_unit": "uV", "channel_count": 16, "sample_rate_hz": 40000.0, "channel_names": ["CH1", "CH2", "CH3", "CH4", "CH5", "CH6", "CH7", "CH8",...
- **sync messages**: Software Time (milliseconds since midnight Jan 1st 1970 UTC): 1794099448544
Start Time for File Reader (100) - example_data @ 40000 Hz: 0


## Inputs

| Role | Path | Bytes | SHA-256 |
| --- | --- | --- | --- |
| reference_openephys_recording | `/tmp/pytest-of-root/pytest-26/test_gui_processor_between_zmq0/ref/2026-11-08_00-57-27/Record Node 103/experiment1/recording1` | 6516914 | `aeaeed6b67e8a2b6a19c321ba9eb14cbaa75655882972ca80abe801787e2f272` |
| concord_recording | `/tmp/pytest-of-root/pytest-26/test_gui_processor_between_zmq0/concord.concord.jsonl` | 31212190 | `273bfc79b96cd63f99abbb6864a57a0d31b9dd2f7844054acedbe4429634ca85` |

## Tests performed and evidence

### `REF-FILE` — Reference Binary recording is readable and consistent: PASS

*Method:* structure.oebin parsed; continuous.dat size a multiple of channels x 2 bytes; sample_numbers.npy and timestamps.npy have one entry per row.

*Finding:* 135604 rows x 16 channels

| Evidence | Value |
| --- | --- |
| rows | 135604 |

<details><summary>sample_numbers</summary>

```json
{
 "jumps": 0,
 "regressions": 0,
 "missing_numbers": 0,
 "examples": []
}
```
</details>

<details><summary>official_reader</summary>

```json
{
 "status": "pass",
 "reader": "open-ephys-python-tools 1.0.1",
 "rows_compared": "all sample numbers; scaled values at rows 0, 67802, 135603",
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
| rows_compared | all sample numbers; scaled values at rows 0, 67802, 135603 |

### `CONCORD-FILE` — Concord recording file is complete and well-formed: PASS

*Method:* Parse every line; require the concord.recording/1 header, contiguous envelope seq numbers (the recorder writes every published event), no recorder recovery/active marker next to the file, and — if Concord is installed — validation of every envelope against Concord's contract models.

*Finding:* 129 frames, every line readable, seq contiguous, contract-valid

| Evidence | Value |
| --- | --- |
| frames | 129 |
| malformed_lines | 0 |
| seq_gaps | 0 |
| seq_regressions | 0 |
| recovery_marker | — |
| active_marker | False |

<details><summary>event_counts</summary>

```json
{
 "recording.frame": 129
}
```
</details>

<details><summary>contract</summary>

```json
{
 "validated": true,
 "valid_events": 129,
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
 "samples": 135604,
 "first_sample_number": 0,
 "last_sample_number": 135603,
 "history": [
  "File Reader -> ZMQ Interface -> Bandpass Filter -> Record Node"
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
 "openephys:127.0.0.1:49573/example_data"
]
```
</details>

### `META-CHAIN` — ZMQ Interface and Record Node see the same data: INCONCLUSIVE

*Method:* Each channel's 'history' in structure.oebin must contain the ZMQ Interface with no processor between it and the Record Node; otherwise Concord and the file legitimately carry different values.

*Finding:* processors between ZMQ Interface and Record Node: ['Bandpass Filter']

| Evidence | Value |
| --- | --- |
| source_processor | File Reader |

<details><summary>history</summary>

```json
[
 "File Reader -> ZMQ Interface -> Bandpass Filter -> Record Node"
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

*Finding:* 3.00 s of the recordings overlap (119815 samples)

| Evidence | Value |
| --- | --- |
| overlap_rows | 119815 |
| overlap_s | 2.99538 |
| reference_rows | 135604 |
| concord_samples | 119815 |
| concord_samples_outside_reference | 0 |
| concord_samples_past_reference_end | 0 |
| min_overlap_s | 2 |

<details><summary>reference_row_span</summary>

```json
[
 2786,
 122601
]
```
</details>

### `SAMPLE-COUNT` — Sample counts agree within the overlap: PASS

*Method:* Count reference samples between the first and last Concord sample and the Concord samples mapped onto them (each counted once per frame that claims it).

*Finding:* reference 119815 vs Concord 119815 samples in the overlap

| Evidence | Value |
| --- | --- |
| reference_samples_in_overlap | 119815 |
| concord_samples_mapped_into_overlap | 119815 |
| difference | 0 |
| reference_total | 135604 |
| concord_total | 119815 |

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

### `ALIGN-CONTENT` — Alignment confirmed by signal content (independent of timestamps): INCONCLUSIVE

*Method:* For evenly spaced frames (and every frame the key could not place), search the reference values for the frame's first 16 samples on all channels; compare the row found with the row given by the frame's timestamp / sample number.

*Finding:* the data could not be located by content (signal too uniform or values differ): alignment rests on timestamps/indices alone

| Evidence | Value |
| --- | --- |
| probed | 24 |
| probed_mapped_by_key | 24 |
| probed_unmapped | 0 |
| agree | 0 |
| disagree | 0 |
| not_found | 24 |
| ambiguous | 0 |

### `VALUES` — Signal values agree within the expected numerical tolerance: INCONCLUSIVE

*Method:* Every Concord sample is compared with the reference sample it maps to, channel by channel: |concord - reference| <= tolerance. |diff| <= 0.51 x bit_volts of the channel ([0.0500000007] µV) — the Record Node's int16 rounding; samples clipped at the int16 limits are excluded.

*Finding:* 1916028 of 1917040 values differ beyond the expected tolerance — not comparable: processors between ZMQ Interface and Record Node: ['Bandpass Filter']

| Evidence | Value |
| --- | --- |
| tolerance | |diff| <= 0.51 x bit_volts of the channel ([0.0500000007] µV) — the Record Node's int16 rounding; samples clipped at the int16 limits are excluded. |
| values_compared | 1917040 |
| values_exactly_equal | 0 |
| values_out_of_tolerance | 1916028 |
| max_abs_diff | 224.1 |
| values_excluded_clipped_in_reference | 0 |

<details><summary>per_channel</summary>

```json
[
 {
  "compared": 119815,
  "exact": 0,
  "within_tolerance": 62,
  "within_float32": 62,
  "out_of_tolerance": 119753,
  "excluded_clipped_in_reference": 0,
  "max_abs_diff": 178.20000967047343,
  "rms_diff": 40.509868747901464,
  "channel": "CH1"
 },
 {
  "compared": 119815,
  "exact": 0,
  "within_tolerance": 62,
  "within_float32": 62,
  "out_of_tolerance": 119753,
  "excluded_clipped_in_reference": 0,
  "max_abs_diff": 161.45000625541562,
  "rms_diff": 40.329122767813,
  "channel": "CH2"
 },
 {
  "compared": 119815,
  "exact": 0,
  "within_tolerance": 55,
  "within_float32": 55,
  "out_of_tolerance": 119760,
  "excluded_clipped_in_reference": 0,
  "max_abs_diff": 184.15000363765782,
  "rms_diff": 38.57338991451712,
  "channel": "CH3"
 },
 {
  "compared": 119815,
  "exact": 0,
  "within_tolerance": 66,
  "within_float32": 66,
  "out_of_tolerance": 119749,
  "excluded_clipped_in_reference": 0,
  "max_abs_diff": 183.7000037048578,
  "rms_diff": 39.09491661171953,
  "channel": "CH4"
 },
 {
  "compared": 119815,
  "exact": 0,
  "within_tolerance": 73,
  "within_float32": 73,
  "out_of_tolerance": 119742,
  "excluded_clipped_in_reference": 0,
  "max_abs_diff": 179.2500033275578,
  "rms_diff": 40.16463158932606,
  "channel": "CH5"
 },
 {
  "compared": 119815,
  "exact": 0,
  "within_tolerance": 51,
  "within_float32": 51,
  "out_of_tolerance": 119764,
  "excluded_clipped_in_reference": 0,
  "max_abs_diff": 224.10000931557343,
  "rms_diff": 43.506257760912966,
  "channel": "CH6"
 },
 {
  "compared": 119815,
  "exact": 0,
  "within_tolerance": 63,
  "within_float32": 63,
  "out_of_tolerance": 119752,
  "excluded_clipped_in_reference": 0,
  "max_abs_diff": 158.4500004193,
  "rms_diff": 39.83481656457646,
  "channel": "CH7"
 },
 {
  "compared": 119815,
  "exact": 0,
  "within_tolerance": 62,
  "within_float32": 62,
  "out_of_tolerance": 119753,
  "excluded_clipped_in_reference": 0,
  "max_abs_diff": 168.49999650444218,
  "rms_diff": 39.029617368866994,
  "channel": "CH8"
 },
 {
  "compared": 119815,
  "exact": 0,
  "within_tolerance": 86,
  "within_float32": 86,
  "out_of_tolerance": 119729,
  "excluded_clipped_in_reference": 0,
  "max_abs_diff": 170.90000933027343,
  "rms_diff": 36.70235435890941,
  "channel": "CH9"
 },
 {
  "compared": 119815,
  "exact": 0,
  "within_tolerance": 69,
  "within_float32": 69,
  "out_of_tolerance": 119746,
  "excluded_clipped_in_reference": 0,
  "max_abs_diff": 142.34999707984218,
  "rms_diff": 35.67077370006223,
  "channel": "CH
... (truncated; full evidence in the JSON report)
```
</details>

<details><summary>examples</summary>

```json
[
 {
  "frame_seq": 2,
  "concord_sample_index": 2786,
  "reference_row": 2786,
  "channel": 0,
  "reference_channel": 0,
  "reference_value": -16.6000002324,
  "concord_value": -10.600000381469727
 },
 {
  "frame_seq": 2,
  "concord_sample_index": 2786,
  "reference_row": 2786,
  "channel": 1,
  "reference_channel": 1,
  "reference_value": -12.650000177099999,
  "concord_value": -18.700000762939453
 },
 {
  "frame_seq": 2,
  "concord_sample_index": 2786,
  "reference_row": 2786,
  "channel": 2,
  "reference_channel": 2,
  "reference_value": -3.9500000553,
  "concord_value": -35.20000076293945
 },
 {
  "frame_seq": 2,
  "concord_sample_index": 2786,
  "reference_row": 2786,
  "channel": 3,
  "reference_channel": 3,
  "reference_value": -3.5500000497,
  "concord_value": -48.25
 },
 {
  "frame_seq": 2,
  "concord_sample_index": 2786,
  "reference_row": 2786,
  "channel": 4,
  "reference_channel": 4,
  "reference_value": -10.6500001491,
  "concord_value": -92.45000457763672
 },
 {
  "frame_seq": 2,
  "concord_sample_index": 2786,
  "reference_row": 2786,
  "channel": 5,
  "reference_channel": 5,
  "reference_value": -25.4500003563,
  "concord_value": -171.60000610351562
 },
 {
  "frame_seq": 2,
  "concord_sample_index": 2786,
  "reference_row": 2786,
  "channel": 6,
  "reference_channel": 6,
  "reference_value": -17.8500002499,
  "concord_value": -44.25
 },
 {
  "frame_seq": 2,
  "concord_sample_index": 2786,
  "reference_row": 2786,
  "channel": 7,
  "reference_channel": 7,
  "reference_value": -25.850000361899998,
  "concord_value": -49.25
 },
 {
  "frame_seq": 2,
  "concord_sample_index": 2786,
  "reference_row": 2786,
  "channel": 8,
  "reference_channel": 8,
  "reference_value": -6.6500000931,
  "concord_value": -50.400001525878906
 },
 {
  "frame_seq": 2,
  "concord_sample_index": 2786,
  "reference_row": 2786,
  "channel": 9,
  "reference_channel": 9,
  "reference_value": -18.7000002618,
  "concord_value": -55.75
 }
]
```
</details>

### `CHANNEL-ORDER` — Channels are in the reference order: INCONCLUSIVE

*Method:* Every Concord channel is matched against every reference channel on a thin sample.

*Finding:* values differ, but not as a channel permutation

<details><summary>best_matches</summary>

```json
[
 {
  "channel": 0,
  "expected_ref": 0,
  "best_ref": 0,
  "match_best": 0.000968054211035818,
  "match_expected": 0.000968054211035818
 },
 {
  "channel": 1,
  "expected_ref": 1,
  "best_ref": 11,
  "match_best": 0.0012100677637947724,
  "match_expected": 0.000484027105517909
 },
 {
  "channel": 2,
  "expected_ref": 2,
  "best_ref": 8,
  "match_best": 0.000968054211035818,
  "match_expected": 0.0007260406582768635
 },
 {
  "channel": 3,
  "expected_ref": 3,
  "best_ref": 0,
  "match_best": 0.0007260406582768635,
  "match_expected": 0.0002420135527589545
 },
 {
  "channel": 4,
  "expected_ref": 4,
  "best_ref": 2,
  "match_best": 0.0012100677637947724,
  "match_expected": 0.000484027105517909
 },
 {
  "channel": 5,
  "expected_ref": 5,
  "best_ref": 7,
  "match_best": 0.0012100677637947724,
  "match_expected": 0.0002420135527589545
 },
 {
  "channel": 6,
  "expected_ref": 6,
  "best_ref": 9,
  "match_best": 0.000968054211035818,
  "match_expected": 0.0002420135527589545
 },
 {
  "channel": 7,
  "expected_ref": 7,
  "best_ref": 4,
  "match_best": 0.000968054211035818,
  "match_expected": 0.0002420135527589545
 },
 {
  "channel": 8,
  "expected_ref": 8,
  "best_ref": 3,
  "match_best": 0.0012100677637947724,
  "match_expected": 0.0007260406582768635
 },
 {
  "channel": 9,
  "expected_ref": 9,
  "best_ref": 2,
  "match_best": 0.001452081316553727,
  "match_expected": 0.000968054211035818
 },
 {
  "channel": 10,
  "expected_ref": 10,
  "best_ref": 0,
  "match_best": 0.000968054211035818,
  "match_expected": 0.0002420135527589545
 },
 {
  "channel": 11,
  "expected_ref": 11,
  "best_ref": 9,
  "match_best": 0.0012100677637947724,
  "match_expected": 0.0007260406582768635
 },
 {
  "channel": 12,
  "expected_ref": 12,
  "best_ref": 6,
  "match_best": 0.0012100677637947724,
  "match_expected": 0.0007260406582768635
 },
 {
  "channel": 13,
  "expected_ref": 13,
  "best_ref": 4,
  "match_best": 0.000968054211035818,
  "match_expected": 0.000484027105517909
 },
 {
  "channel": 14,
  "expected_ref": 14,
  "best_ref": 0,
  "match_best": 0.001936108422071636,
  "match_expected": 0.0
 },
 {
  "channel": 15,
  "expected_ref": 15,
  "best_ref": 0,
  "match_best": 0.000968054211035818,
  "match_expected": 0.0007260406582768635
 }
]
```
</details>

### `SCALE` — Scaling and units are correct: INCONCLUSIVE

*Method:* Least-squares factor per channel on a thin sample.

*Finding:* values differ, but not by a constant factor or offset

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

*Finding:* all 129 frame timestamps equal sample_number / rate; reference timestamps.npy minus Concord: median 0 s

| Evidence | Value |
| --- | --- |
| frames | 129 |
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

*Finding:* worst excess ingest delay 2.3 ms (median 0.4 ms) vs threshold 1000 ms

| Evidence | Value |
| --- | --- |
| frames | 129 |
| excess_delay_median_s | 0.0004292 |
| excess_delay_p95_s | 0.00102906 |
| excess_delay_max_s | 0.00233698 |
| drift_ppm | -144.992 |

<details><summary>fit</summary>

```json
{
 "slope": -0.00014499246525594468,
 "intercept": 1794099448.52229,
 "residual_std": 0.00031347397449885806,
 "residual_max_abs": 0.0016472339630126953,
 "n": 129
}
```
</details>

### `REF-CONTINUITY` — Reference recording is continuous: PASS

*Method:* Differences between successive sample_numbers.npy entries must be exactly 1.

*Finding:* sample numbers are contiguous

| Evidence | Value |
| --- | --- |
| jumps | 0 |
| regressions | 0 |
| missing_numbers | 0 |

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
 "created_at": "2026-11-08T00:57:33Z"
}
```
