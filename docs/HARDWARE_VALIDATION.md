# Hardware validation protocol — verifying BrainOS against a lab's acquisition system

This is a step-by-step laboratory procedure for testing whether BrainOS receives, without loss
or alteration, the neural data that an established acquisition system produces. It uses the
`brainos-hwval` toolkit (`packages/brainos-hwval`) to compare a BrainOS recording with a
recording made **at the same time** by the acquisition system's own reference software:

* **Lab Streaming Layer (LSL)** sources → **LabRecorder** (XDF file);
* **Open Ephys GUI** sources → the GUI's **Record Node** in **Binary** format.

A researcher should be able to follow it without a BrainOS developer present. Sections 1–8
describe one run; section 9 defines when a set of runs confirms hardware compatibility;
section 10 lists what human-participant validation would additionally need.

> **Scope.** This protocol can at most produce *level 3 (hardware-verified)* evidence as
> defined in [VALIDATION_LEVELS.md](VALIDATION_LEVELS.md), for one acquisition system in one
> configuration, and only when a person reviews and signs the complete set of runs (§9). The
> toolkit itself never marks anything hardware-verified. Nothing here involves a person or an
> animal: the inputs are a signal generator, a test board, a phantom or shorted inputs. Use
> with a human participant is level 4 and is outside this protocol (§10).

**Status (November 2026).** The toolkit and this procedure have been exercised end to end with
real reference *software* (LabRecorder 1.16.4; Open Ephys GUI 1.1.0 with the ZMQ Interface
1.0.0 and the GUI's File Reader) but **not yet with physical acquisition hardware**. No
BrainOS component has reached level 3. See "Evidence so far" at the end.

---

## 1. Required acquisition software and equipment

### 1.1 Software

| Item | Version used to develop this protocol | Notes |
| --- | --- | --- |
| BrainOS | this repository, commit recorded in the manifest | `pip install -e "backend[live]"` (LSL: `pylsl`; Open Ephys: `pyzmq`) |
| brainos-hwval | 0.1.0 | `pip install -e "packages/brainos-hwval[capture,openephys]"` |
| pyxdf | 1.18.0 | installed with brainos-hwval; reads XDF |
| LabRecorder | 1.16.4 (GUI or `LabRecorderCLI`) | LSL runs. Any version that writes XDF 1.0 with ClockOffset chunks |
| liblsl | 1.16.2 (LabRecorder), 1.18 (pylsl in BrainOS) | record `lslver` output |
| Vendor LSL app | as installed | the amplifier's LSL streaming application, if the source is LSL |
| Open Ephys GUI | ≥ 0.6 (1.1.0 tested) | Open Ephys runs. GUI 0.5.x Binary files are read, but the official Python reader cannot read them (see §7) |
| ZMQ Interface plugin | 1.0.0 for GUI 1.x (plugin API 10) | installed from the GUI's Plugin Installer |
| open-ephys-python-tools | 1.0.1 | optional; cross-checks the Binary parser (`REF-READER`) |

### 1.2 Equipment

| Item | Purpose |
| --- | --- |
| The acquisition system under test (amplifier / acquisition board, headstage, cables, its host software) | the hardware being validated |
| A function generator with documented amplitude and frequency accuracy (or the amplifier's built-in test-signal mode) | a known input signal through the real hardware |
| The manufacturer's test board / input adapter, a saline phantom, or shorted inputs | a safe, defined electrical input; **never a person or animal** |
| A TTL pulse source (pulse generator or a microcontroller) wired to the acquisition system's digital input | event timing (Open Ephys `EVENTS`; LSL marker streams are not yet compared) |
| One or two host computers (acquisition host; BrainOS host, may be the same) | record their OS, CPU and clock synchronisation (NTP/PTP/none) |
| A wired network between hosts (if two) | Wi-Fi adds jitter and loss; if used, record it |

### 1.3 Documentation before the first run

Create the equipment manifest and fill in **every** field (it is attached to each report):

```bash
brainos-hwval equipment-template > equipment.json
```

`signal_source.kind` must be one of `acquisition_hardware`, `signal_generator_through_hardware`,
`file_playback`, `software_simulator`. Only the first two can ever produce a hardware run.

### 1.4 Dry run (recommended, no hardware)

Rehearse the whole procedure with a declared-synthetic software stream before involving the
hardware:

```bash
brainos-hwval test-signal --name hwval-dry-run --duration 400    # terminal 1
# terminal 2: LabRecorder records "hwval-dry-run" (section 3), terminal 3: BrainOS capture
```

The resulting report must be PASS at level `software_acquisition_comparison`, never a
hardware run (the stream declares itself synthetic).

---

## 2. Connecting a supported LSL or Open Ephys source

### 2.1 LSL source

1. Start the acquisition system and its LSL application; start streaming.
2. Check that the stream describes its channels (XDF meta-data convention:
   `<desc><channels><channel><label/><unit/><type/></channel>…`). BrainOS converts to µV only if
   **every** channel declares a voltage unit (`microvolts`, `millivolts`, `volts`, `nanovolts`
   or abbreviations); otherwise it reports `arbitrary` and does not guess. Note what the vendor
   app declares.
3. Check that BrainOS sees the stream (`brainos-hwval capture` discovers it; in the operator
   console, use LSL discovery in the acquisition-source panel; REST:
   `POST /api/v1/sources/lsl/discover`). If several streams share a name, note the `source_id`
   and host.
4. Do not run other LSL streams with the same name on the network during the run.

### 2.2 Open Ephys source

1. Build the signal chain so that the **ZMQ Interface and the Record Node see the same data**:
   `Acquisition source → (optional processing) → ZMQ Interface → Record Node`. Put **no
   processor between the ZMQ Interface and the Record Node**; otherwise the file legitimately
   differs from what BrainOS receives (the toolkit then reports `META-CHAIN` inconclusive).
2. In the ZMQ Interface: choose the stream, set the Data Port (default 5556; BrainOS also uses
   port + 1 for heartbeats), select the channels to send (all, for validation).
3. In the Record Node: record format **Binary**, record the same stream, events on.
4. In BrainOS, declare the unit configured in the GUI (`uV` for ephys channels): the ZMQ
   protocol does not transmit units; without it BrainOS reports `arbitrary`, which is honest
   but untestable for unit errors.
5. Do not use the File Reader for a hardware run: it is playback (the toolkit detects it from
   `structure.oebin` and excludes the run from hardware evidence). It is useful for a dry run;
   keep runs shorter than the file, because looping restarts the sample numbers (§7).

---

## 3. Recording reference and BrainOS streams simultaneously

The reference must cover the whole BrainOS recording. Order matters:

1. **Start the source** (acquisition running, signal generator on, TTL pulses running).
2. **Start the reference recording.**
   * LSL: LabRecorder → select the stream → *Start* (or
     `LabRecorderCLI run.xdf 'name="<stream>"'`, stop with Enter).
   * Open Ephys: press *Record* (acquisition already running).
3. **Start the BrainOS recording** (raw frames included):
   ```bash
   brainos-hwval capture lsl --stream "<stream name>" [--source-id ID] [--host HOST] \
       --duration 260 --out runs/ --name run01
   brainos-hwval capture openephys --host <gui host> --port 5556 --unit uV \
       --duration 260 --out runs/ --name run02
   ```
   This drives BrainOS's own runtime (the same adapters, runtime and recorder as the console)
   and writes `run01.brainos.jsonl` plus `run01.capture.json` (source metadata, LSL
   time-correction, a measured wall-clock/`lsl_local_clock` pair, diagnostics). Recording from
   the operator console's recording control (REST `POST /api/v1/recordings/start` and
   `/stop`; files in `data/recordings/`, raw frames included) also works; the sidecar is then
   absent and absolute latency is not reported.
4. Let the run last **≥ 240 s** of overlap. BrainOS's recorder stops raw recordings at 300 s
   (`runtime/recorder.py`), so `--duration` is limited to 290 s.
5. **Stop BrainOS first**, then stop the reference a few seconds later.
6. Copy the reference file(s) and the BrainOS files into one run folder. **Do not edit,
   re-save, convert or post-process them.** The reports record SHA-256 sums of every input.

BrainOS does not emit the first ~0.5–1 s after connecting (it learns the stream layout), and
LabRecorder starts with a delay; samples outside the overlap are not compared and are not
counted as loss.

---

## 4. Preserving accurate timing information

* **LSL timestamps.** LabRecorder stores the source's raw timestamps plus ClockOffset
  measurements; BrainOS opens its inlet without clock post-processing, so both carry the same
  source timestamps. Never load the XDF with clock synchronisation or dejittering for this
  comparison (the toolkit loads it with both off and analyses the offsets separately).
* **The vendor app's timestamps** should come from the device's sample clock if it offers that
  option; push-time timestamps make the effective rate deviate from the nominal rate
  (`RATE-EFFECTIVE`, advisory).
* **Open Ephys timing** is the acquisition sample clock: BrainOS frame timestamps are
  `sample_number / sample_rate`, and the Record Node stores the same sample numbers. Do not
  restart acquisition during a run.
* **Host clocks.** Record whether each host runs NTP/PTP; do not change system time, suspend,
  or let power saving throttle the hosts during a run. BrainOS's ingest timestamps are wall
  clock (`timestamp_ns`); only their drift and spread are interpreted unless a measured clock
  pair is available (capture sidecar).
* **Load.** Keep the BrainOS host free of unrelated heavy work; note CPU and network load.
* **TTL timing** (Open Ephys): drive a known pulse train (e.g. 1 Hz, 10 ms) into a digital
  input; events are compared at sample resolution.

---

## 5. Running the comparison tools

```bash
brainos-hwval lsl --reference runs/run01.xdf --brainos runs/run01.brainos.jsonl \
    --equipment equipment.json --out reports/
brainos-hwval openephys --reference "runs/2026-11-08_10-00-00/Record Node 102" \
    --brainos runs/run02.brainos.jsonl --equipment equipment.json --out reports/
```

* `--reference` for Open Ephys may be the session, Record Node, experiment or recording
  folder; if it contains several recordings, the tool lists them and asks for one.
* The capture sidecar is picked up automatically if it sits next to the BrainOS recording.
* `brainos-hwval inspect <file or folder>` summarises any input first.
* Default thresholds: no loss allowed, ≥ 5 s overlap for a conclusive comparison (240 s for a
  hardware run), excess delay ≤ 1 s, LSL values within single precision, Open Ephys values
  within 0.51 × `bit_volts`. Every threshold used is written into the report. Change them
  only with a written justification in the run log.
* Output: `reports/<name>.hwval.json` (machine-readable; schema in the package) and
  `reports/<name>.hwval.md` (human-readable). Exit code 0 PASS, 1 FAIL, 3 INCONCLUSIVE,
  2 input error.

---

## 6. Interpreting the results

The overall result is:

* **FAIL** — at least one required check observed an integrity problem. Nothing averages it
  away.
* **INCONCLUSIVE** — no failure was observed, but a required check could not decide (too
  little overlap, a flat signal, clipped reference values, a processor between ZMQ Interface
  and Record Node, samples present in BrainOS but missing in the reference …). Fix the cause
  and repeat; an inconclusive run is not evidence either way.
* **PASS** — every required check passed.

Advisory checks (`RATE-EFFECTIVE`, `REF-CONTINUITY`, `CLOCKS`, `EQUIPMENT`, `REF-READER` when
it passes or cannot run, `EVENTS` when nobody sent events) describe the source and the
reference, not BrainOS, and never change the result. Read them anyway: a source whose
effective rate is 1 % off nominal, or a reference with gaps, is a finding about the lab's setup.

| Check | A failure means |
| --- | --- |
| `REF-FILE` / `BOS-FILE` | a file is truncated, inconsistent, or (BrainOS) an event violates the contract or event numbers are missing from the file |
| `IDENTITY` | the two recordings are not of the same stream (wrong stream selected, renamed outlet, different GUI stream) |
| `META-CHANNELS` / `META-RATE` / `META-FORMAT` | BrainOS misreports channel count, names or order, the sampling rate, or the sample format |
| `META-UNITS` | BrainOS claims µV without a basis, or ignores declared voltage units, or the declared Open Ephys unit contradicts the file |
| `PROVENANCE` | synthetic / prerecorded declarations are lost or invented |
| `SAMPLE-COUNT`, `LOSS` | BrainOS is missing samples the reference has (the report lists each missing run with its position and duration) |
| `DUPLICATES`, `EXTRA`, `ORDER` | BrainOS duplicated samples, has samples that do not exist in the source, or delivered them out of order |
| `ALIGN-CONTENT`, `TS-AGREE` | data carry the wrong timestamps / sample numbers (the offset is reported) |
| `VALUES` | sample values differ beyond the expected tolerance; `CHANNEL-ORDER` and `SCALE` then say whether it is a channel swap, a unit/scale error, an offset, or corruption |
| `LOSS-FLAGGED` | BrainOS lost data **without reporting it** — the most serious finding |
| `DELAY` | some data arrived much later than the rest (stall, buffering) |
| `EVENTS` | TTL events missing, extra or misplaced |

The section *What this result means* states the evidence level of the run:
`none` (did not pass), `software_acquisition_comparison`, or `hardware_run_candidate` (all of
§9.1 holds). `hardware_verified` is always `false`.

---

## 7. Investigating failures

1. Re-run `brainos-hwval inspect` on both inputs; confirm stream, channel count, rate, units.
2. Open the failing check's evidence in the Markdown report: it lists the first mismatching
   samples (frame, sample index, reference row, channel, both values) and, for loss, each
   missing run with its position.
3. By symptom:
   * **Loss, reported** (`LOSS` fail, `LOSS-FLAGGED` pass): check the BrainOS `device.status`
     events in the evidence (reconnects), CPU load, network, LSL buffer length, the Open Ephys
     ZMQ high-water mark (`rcvhwm`). Known case: an Open Ephys **sample-number reset** (GUI
     File Reader looping, acquisition restart) makes BrainOS reconnect and lose ~0.7 s.
   * **Loss, unreported** (`LOSS-FLAGGED` fail): a BrainOS defect. File it with the bug bundle
     below.
   * **Gaps in both recordings** (`REF-CONTINUITY` advisory): the source dropped them; BrainOS
     is not at fault. Investigate the acquisition system / vendor app.
   * **`SCALE` with a unit factor 10³ / 10⁶**: the unit declared to BrainOS (Open Ephys) or by
     the vendor app (LSL) is wrong.
   * **`CHANNEL-ORDER`**: a channel map, selection or vendor channel ordering differs; the
     report says whether the labels follow the data.
   * **`TS-AGREE` / `ALIGN-CONTENT`**: timestamps were transformed somewhere (vendor app
     settings, LabRecorder version, a BrainOS change); the reported offset tells by how much.
   * **`META-CHAIN` inconclusive**: move the Record Node directly after the ZMQ Interface.
   * **`VALUES` inconclusive with clipped samples**: reduce the generator amplitude or gain.
   * **`REF-READER` not tested** with "source_processor_sub_dx": open-ephys-python-tools 1.0.1
     cannot read GUI < 0.6 recordings; this is a limitation of that reader, not of the data.
4. Known operational issue: Open Ephys GUI 1.1.0 aborted when a ZMQ Interface 1.0.0 processor
   was deleted through the GUI's HTTP API. Restart the GUI rather than removing the plugin
   during a session.
5. **Bug bundle** for the BrainOS developers: both reports (JSON + Markdown), the equipment
   manifest, the capture sidecar, BrainOS logs, and — if data-protection rules allow — the two
   recordings (they contain no participant data in this protocol).

---

## 8. Documenting the acquisition hardware and software versions

Fill the equipment manifest (§1.3) for every session, and keep with every run:

| What | How to obtain |
| --- | --- |
| Acquisition hardware: manufacturer, model, serial number, firmware, headstage/amplifier | device label, vendor software "About" / device info |
| Acquisition software and plugins | vendor app "About"; Open Ephys: Help → About and the Plugin Installer list; `GUI version` in `structure.oebin` |
| Reference recorder | LabRecorder "About" or release file name; Open Ephys Record Node (GUI version) |
| liblsl | `lslver`, or `python -c "import pylsl; print(pylsl.library_info())"` |
| BrainOS | `git rev-parse HEAD` and `git status --porcelain` (must be clean) in the BrainOS checkout; `brainos_version` in the capture sidecar |
| brainos-hwval, pyxdf, numpy, Python | recorded automatically in each report (`environment`) |
| Hosts | OS version, CPU, RAM, NTP/PTP status (`timedatectl`, `chronyc tracking`), network |
| Input signal | generator model, settings (waveform, frequency, amplitude), wiring, which channels |
| Files | SHA-256 of every input (recorded automatically in each report) |

Archive the raw files read-only. A run that cannot be traced to its files and versions does not
count towards §9.

---

## 9. Objective criteria for confirming physical hardware compatibility

### 9.1 A single hardware-validation run

The toolkit reports `evidence_scope.level = hardware_run_candidate` only if **all** hold:

1. Overall result **PASS** (every required check passed with the default thresholds, in
   particular zero samples lost, duplicated or extra; values within tolerance; timestamps
   exact; no unreported loss).
2. The equipment manifest is complete and declares `acquisition_hardware` or
   `signal_generator_through_hardware`.
3. Nothing declares the data synthetic or prerecorded, and the Open Ephys reference does not
   come from the File Reader.
4. At least 240 s of overlap.

### 9.2 The protocol for one acquisition system and configuration

Hardware compatibility (level 3 in VALIDATION_LEVELS.md) is confirmed for **one** acquisition
system, **one** configuration (protocol, channel count, sampling rate, units) and the BrainOS
commit tested, when a reviewer other than the operator confirms that:

| # | Run | Criterion |
| --- | --- | --- |
| H1 | 3 runs of ≥ 240 s overlap, on ≥ 2 different days, with a known generator signal through the hardware | each run is a `hardware_run_candidate` |
| H2 | 1 run with the highest channel count × sampling rate the lab will use | `hardware_run_candidate` |
| H3 | Signal identity: in one H1 run, the generator frequency measured in the BrainOS data (spectral peak) and amplitude (RMS, in µV after the stated gain) match the generator settings within the acquisition system's specified accuracy | documented analysis attached (not computed by the toolkit) |
| H4 | Event timing (Open Ephys, or any source with TTL): a pulse train of ≥ 100 pulses | `EVENTS` pass; no event missing, extra or shifted |
| H5 | Failure injection: during a run, (a) unplug/replug the data cable or stop/restart the vendor app, (b) interrupt the network for ~5 s (two-host setups) | report FAILs on `LOSS` (expected) **and passes `LOSS-FLAGGED`**: every loss is reported by BrainOS; BrainOS resumes without restart; no `DUPLICATES`, `EXTRA`, `ORDER`, `VALUES` failures |
| H6 | Reproducibility: a second person repeats one H1 run from this document alone | `hardware_run_candidate` |
| H7 | Traceability | every report, manifest and SHA-256-identified file archived; BrainOS commit clean |

Any FAIL in H1, H2, H4 or H6, or any **unreported** loss in H5, means the configuration is not
compatible until the cause is fixed and the affected runs are repeated. INCONCLUSIVE runs are
repeated, not counted. The signed review (names, date, BrainOS commit, systems, the list of
reports) is what the BrainOS maintainers need to record level 3 for that integration in
`docs/VALIDATION_LEVELS.md` and the compatibility registry; that change is made by them, not by
the toolkit.

What level 3 still does **not** show: anything about decoding, closed-loop control, or use
with a person; other configurations or firmware versions of the same device.

---

## 10. Additional evidence needed for human-participant validation

Level 4 (VALIDATION_LEVELS.md) is outside this protocol and outside what BrainOS can establish
on its own. It would need, at least:

* an approved research protocol (ethics committee / IRB) run by qualified investigators, with
  informed consent, and compliance with the regulatory status of the implanted or external
  device (BrainOS is not a medical device and provides no clinical function);
* completed level-3 evidence (§9) for the exact acquisition system, configuration and BrainOS
  version used with the participant, plus a documented change-control process;
* safety analysis of the read-only data path and of any decoded-command path (the command
  router must remain operator-authorised; stop paths tested), with monitoring and adverse-event
  reporting procedures;
* pre-registered closed-loop performance metrics (e.g. task success, information transfer rate,
  false-activation rate) and analysis plan, measured with the participant, with appropriate
  controls;
* data-protection measures for participant recordings (never committed to the repository);
* independent review of the results.

---

## Evidence so far (software reference, no hardware)

Executed in `packages/brainos-hwval/tests` (and in `.github/workflows/hwval.yml`); the reports
are in `packages/brainos-hwval/examples/sample-reports/`:

| Run | Reference software | Result |
| --- | --- | --- |
| LSL test signal, 8 ch × 1 kHz, ~10 s | LabRecorder 1.16.4 (`LabRecorderCLI`), pyxdf 1.18.0 | PASS: every value bit-exact, timestamps identical (< 1 µs), absolute latency median ≈ 4 ms ([`labrecorder-pass`](../packages/brainos-hwval/examples/sample-reports/labrecorder-pass.hwval.md)) |
| Same, with 150 samples withheld at the source | LabRecorder 1.16.4 | PASS: gap present in both recordings, attributed to the source; BrainOS flagged it ([`labrecorder-source-gap`](../packages/brainos-hwval/examples/sample-reports/labrecorder-source-gap.hwval.md)) |
| Open Ephys GUI File Reader (GUI sample data, 16 ch × 40 kHz), ~3 s | Open Ephys GUI 1.1.0 Record Node (Binary), ZMQ Interface 1.0.0, open-ephys-python-tools 1.0.1 | PASS: every value within half a quantisation step, sample numbers exact ([`openephys-gui-pass`](../packages/brainos-hwval/examples/sample-reports/openephys-gui-pass.hwval.md)) |
| Same, Bandpass Filter between ZMQ Interface and Record Node | as above | INCONCLUSIVE: values legitimately differ ([`openephys-gui-filter-between`](../packages/brainos-hwval/examples/sample-reports/openephys-gui-filter-between.hwval.md)) |
| Same, 7 s (File Reader loops at 5 s) | as above | Before the fix: FAIL, BrainOS reconnected at the sample-number reset and missed 28 793 samples (0.72 s), reported via `device.status` ([`…-before-fix`](../packages/brainos-hwval/examples/sample-reports/openephys-gui-file-reader-loop-before-fix.hwval.md)). After the adapter fix (Milestone 5 release): PASS, no sample missing; the reference's own discontinuity is reported as advisory ([`openephys-gui-file-reader-loop`](../packages/brainos-hwval/examples/sample-reports/openephys-gui-file-reader-loop.hwval.md)) |
| Injected defects in real BrainOS recordings (loss, duplicate, channel swap, unit error, value corruption, timestamp shift, delay, metadata) | against the real LabRecorder / Record Node files | each detected by the specific check |

These are level-2 (protocol-tested / software) results. No physical acquisition hardware has
been used. Requirements still open for the first hardware run: access to an acquisition system
with an LSL app or the Open Ephys GUI with an acquisition board, a signal generator and a
TTL source; the BrainOS recorder's 300 s raw-recording cap limits each run to < 300 s.
