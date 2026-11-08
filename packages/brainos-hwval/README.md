# brainos-hwval — acquisition verification for BrainOS

`brainos-hwval` checks whether BrainOS received **exactly** the neural data that established
reference software recorded from the same source at the same time:

| Protocol | Reference recording | Read with |
| --- | --- | --- |
| Lab Streaming Layer | XDF file from **LabRecorder** | `pyxdf` (raw source timestamps; clock offsets analysed separately) |
| Open Ephys GUI (ZMQ Interface) | **Record Node** recording in Binary format | this package's parser, cross-checked against the official `open-ephys-python-tools` reader |

It reports, per check, **pass / fail / inconclusive / not tested** with the method and the
evidence, writes a JSON report (schema: `src/brainos_hwval/schemas/report.schema.json`) and a
Markdown report, and exits 0 / 1 / 3 for PASS / FAIL / INCONCLUSIVE (2 for bad input). There
is no score.

**What it does not do.** It never marks anything hardware-verified or human-validated. A PASS
says: over this run, BrainOS received what the reference received, within the stated
tolerances. Whether that is evidence about *hardware* depends on what the source was; the
laboratory protocol in [`docs/HARDWARE_VALIDATION.md`](../../docs/HARDWARE_VALIDATION.md)
defines how runs with real hardware are made, documented and judged.

## Install

```bash
pip install -e packages/brainos-hwval              # compare (no BrainOS needed)
pip install -e "packages/brainos-hwval[openephys]" # + official Open Ephys reader cross-check
pip install -e "backend[live]" -e "packages/brainos-hwval[capture]"  # + record through BrainOS
```

Python ≥ 3.11. The comparison needs only `numpy` and `pyxdf`.

## Use

```bash
# 1. record with the reference software and BrainOS at the same time (see the protocol), e.g.
brainos-hwval capture lsl --stream "MyAmp EEG" --duration 240 --out runs/ --name run1
#    (or record in the BrainOS console: Recordings -> Start; the sidecar is then absent)

# 2. compare
brainos-hwval lsl --reference runs/run1.xdf --brainos runs/run1.brainos.jsonl \
    --equipment equipment.json --out reports/
brainos-hwval openephys --reference "~/OE/2026-11-08_10-00-00/Record Node 102" \
    --brainos runs/run2.brainos.jsonl --equipment equipment.json --out reports/

# inspect any input before comparing
brainos-hwval inspect runs/run1.xdf
brainos-hwval inspect runs/run1.brainos.jsonl

# rehearse without hardware: a declared-synthetic LSL stream
brainos-hwval test-signal --name hwval-dry-run --duration 300

# document the setup
brainos-hwval equipment-template > equipment.json
```

Options: `--stream` (pick the reference stream), `--max-loss-fraction` (default 0),
`--min-overlap` (default 5 s), `--max-excess-delay` (default 1 s), `--value-rtol` (LSL,
default 2.5e-7; 0 demands bit-exact values), `--quantisation-steps` (Open Ephys, default 0.51
of `bit_volts`), `--json` (print the JSON report).

## What is checked

| Check | Question | Decides |
| --- | --- | --- |
| `REF-FILE`, `BOS-FILE` | Are both files complete and well-formed? (BrainOS envelopes are validated against BrainOS's contract models if BrainOS is installed) | required |
| `REF-READER` | Does the Open Ephys parser agree with the official reader? | advisory (required if it disagrees) |
| `IDENTITY` | Same LSL outlet (uid / name / source_id / host) or same Open Ephys stream? | required |
| `META-CHANNELS`, `META-RATE`, `META-FORMAT`, `META-UNITS`, `PROVENANCE`, `META-CHAIN` | Channel identities and order, declared rate, format, units (µV vs `arbitrary`), synthetic/prerecorded declarations, Open Ephys signal chain | required |
| `OVERLAP`, `SAMPLE-COUNT` | Enough common data; same number of samples in the overlap | required |
| `LOSS`, `DUPLICATES`, `EXTRA`, `ORDER` | Samples missing in BrainOS, duplicated, without a reference counterpart, out of order | required |
| `ALIGN-CONTENT` | Do the data sit where their timestamps / sample numbers say? (found by content, independently of timestamps) | required |
| `VALUES`, `CHANNEL-ORDER`, `SCALE` | Values within the expected tolerance; channel swaps; unit/scale/offset errors | required |
| `LOSS-FLAGGED` | Did BrainOS report each loss (frame flag `dropped_samples` or a `device.status` event)? | required |
| `TS-AGREE` | BrainOS frame timestamps = source timestamps (LSL) / sample_number ÷ rate (Open Ephys) | required |
| `DELAY` | Ingest delay above the best case ≤ threshold (absolute latency with the capture sidecar) | required |
| `EVENTS` | Open Ephys TTL events (sample, line, state) | required when either side has events |
| `RATE-EFFECTIVE`, `REF-CONTINUITY`, `CLOCKS` | Source clock vs nominal rate, discontinuities in the reference, LabRecorder clock offsets and drift, BrainOS wall-clock drift | advisory: properties of the source / reference |
| `EQUIPMENT` | Is the setup documented (equipment manifest)? | advisory; needed for a hardware run |

**Expected tolerances vs integrity failures.** LSL: BrainOS converts declared voltage units to
µV in float64, so values are normally bit-exact (counted as `exact`); differences at
single-precision level are an expected numerical tolerance. Open Ephys: the Record Node stores
`round(µV / bit_volts)` as int16 (GUI v1.1.0 `SIMDConverter`), so values agree to half a
quantisation step; samples clipped at the int16 limits are excluded and, if more than 1 %,
make `VALUES` inconclusive. Anything beyond is a failure, and `CHANNEL-ORDER` / `SCALE` say
whether it is a permutation, a unit error, an offset or corruption.

**Clock domains.** LSL: XDF raw timestamps and BrainOS `device_timestamp_ns` are both the
source's `lsl_local_clock` and must agree to the nanosecond; LabRecorder's ClockOffsets
(recorder − source) are fitted for offset and drift; implausible offset entries (e.g. the
zero-filled one LabRecorder writes when a time-correction query times out) are discarded and
counted. BrainOS's `timestamp_ns` is wall clock: only its drift and spread are meaningful,
unless the capture sidecar provides a measured wall-clock / `lsl_local_clock` pair (then
absolute latency is reported). Open Ephys: the sample clock (`sample_number / rate`); the
delay analysis uses Record Node rows, which keep counting through sample-number resets.

## Reference software actually exercised (tests)

| Software | Version | How |
| --- | --- | --- |
| LabRecorder (`LabRecorderCLI`) | 1.16.4 (release .deb), liblsl 1.16.2 | records the test stream to XDF while BrainOS records it |
| pyxdf | 1.18.0 | reads every XDF file (real and synthetic) |
| Open Ephys GUI | 1.1.0 Linux (official build) | headless (Xvfb + PulseAudio null sink), File Reader → ZMQ Interface → Record Node, driven over its HTTP API |
| ZMQ Interface plugin | 1.0.0 (plugin API 10, official build) | the stream BrainOS's adapter receives |
| open-ephys-python-tools | 1.0.1 | cross-checks this parser on the GUI's Binary output |
| BrainOS runtime | this repository | LSL / Open Ephys adapters, Runtime, Recorder (unchanged) via `brainos-hwval capture` |

The binaries are downloaded at test time from the official release locations, pinned by
SHA-256 (`tests/refsoft.py`), and never committed (Open Ephys is GPL-3).

## Tests

```bash
cd packages/brainos-hwval && pytest -q -rs
```

* `test_lsl_synthetic.py`, `test_oe_synthetic.py` — injected defects (loss, silent loss,
  duplicates, value corruption, float32 rounding, channel swaps, unit errors, timestamp shifts
  and offsets, clock drift, reordered frames, source and reference gaps, corrupt metadata,
  wrong stream, truncated files, clipping, TTL events, sample-number resets, legacy 0.5
  format, flat signals, no overlap) on fixtures that pyxdf, BrainOS's contract models and the
  official Open Ephys reader read back.
* `test_labrecorder.py` — real LabRecorder + BrainOS round trips (clean; a source gap), and
  defects injected into the real BrainOS recording, detected against the real XDF file.
* `test_openephys_gui.py` — real Open Ephys GUI + BrainOS round trips (µV; unit not declared;
  a filter between ZMQ Interface and Record Node; the File Reader looping), defects injected
  into the real BrainOS recording, and this parser's legacy (0.4.5) reader against the GUI's
  own File Reader.
* `test_cli.py`, `test_examples.py` — exit codes, input validation, report schema, evidence
  scope rules, committed example reports.

Reference-software tests skip (with the reason) when the software cannot run; with
`HWVAL_REQUIRE_REFERENCE_SOFTWARE=1` (CI) they fail instead. System packages they need on
Ubuntu: `libpugixml1v5` (LabRecorderCLI), `xvfb pulseaudio libasound2-plugins` (GUI).

`examples/sample-reports/` holds reports from real runs (regenerate with
`HWVAL_EXAMPLES_DIR=examples/sample-reports pytest tests/test_labrecorder.py tests/test_openephys_gui.py`).
Their input files are not committed; their SHA-256 sums are in the reports.

## Findings from the real-software runs

* **BrainOS loses ~0.7 s at an Open Ephys sample-number reset.** When the GUI's File Reader
  loops, sample numbers restart; BrainOS's Open Ephys adapter treats this as an acquisition
  restart, reconnects and re-learns the stream, and the samples in between are missing
  (28 793 samples at 40 kHz in `examples/sample-reports/openephys-gui-file-reader-loop.hwval.md`).
  BrainOS reports it (device.status `reconnecting`), so it is not silent, but it is loss.
* LabRecorder writes a ClockOffset entry with time ≈ 0 and value 0 when a time-correction
  query times out after the source has gone, and its stream-footer `sample_count` can be one
  lower than the samples stored; both are handled and reported, not treated as data errors.
* open-ephys-python-tools 1.0.1 cannot read GUI < 0.6 Binary recordings (it looks up a
  misspelled key, `source_processor_sub_dx`); `REF-READER` then reports "not tested".
* Open Ephys GUI 1.1.0 aborts when a ZMQ Interface 1.0.0 processor is deleted through the
  HTTP API; restart the GUI instead of reconfiguring the chain.

## Limitations

See the `limitations` list in every report, and docs/HARDWARE_VALIDATION.md. In short: both
LSL recordings receive the stream through liblsl; BrainOS keeps one timestamp per frame;
Open Ephys values are verified to the Record Node's quantisation; TTL comparison was tested
only on synthetic Binary files (the GUI sample data has no events); no physical acquisition
hardware has been used with this toolkit.
