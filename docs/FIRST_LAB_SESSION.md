# First lab session with real equipment: validation protocol

**This is a protocol, not a result.** Nobody has run Concord with acquisition hardware yet
(docs/VALIDATION_LEVELS.md: nothing has reached level 3). This document says what to check,
how, and what evidence to keep, so that a lab's first session produces a defensible answer to
one question: *does Concord receive exactly what our acquisition system produces, with known
timing, and can we stop it reliably?* It does not evaluate decoding performance, usability,
or anything clinical.

Run it **without a participant first** (bench test with a signal source), and only then, if
your approved research protocol allows it, during a session with a participant — with Concord
in a passive, recording-only role until every stop procedure has been rehearsed.

## 0. Before the day

Decide and write down, in advance:

- [ ] Which data path is being validated (e.g. "amplifier X → vendor LSL app Y vY.Z → LSL →
      Concord", "Open Ephys GUI 0.6.x + ZMQ Interface → Concord").
- [ ] **Pass/fail criteria** your lab accepts, for example: sample count equal to the
      acquisition software's for the same interval; values equal after unit conversion
      (within quantization); no gaps Concord does not also count; timestamp offset to the
      reference below *N* ms with jitter below *M* ms; every stop procedure effective within
      *T* s. Concord does not prescribe these numbers.
- [ ] Who operates Concord, who operates acquisition, who decides to stop.

## 1. Pre-checks (on the Concord computer)

- [ ] `concord version --json` — save the output.
- [ ] `concord doctor` — save both report files; resolve every *fail*.
- [ ] All computers synchronised to the same NTP server; note the offsets they report.
- [ ] Data directory on an encrypted disk with enough space (≥ 10 GB free);
      `[retention]` off for this session (`concord config show`).
- [ ] Firewall/ports for your protocol (docs/LAB_SETUP.md §2) open; nothing else listens on
      Concord's port.
- [ ] Acquisition software name, version, and settings (sample rate, channel map, filters,
      units, reference) recorded.
- [ ] **New session** in Concord (name without participant identifiers).

## 2. Signal verification against the acquisition software

Use a known signal: a signal generator or the amplifier's test signal into a defined set of
channels (e.g. a 10 Hz sine of known amplitude), other channels shorted or grounded as your
amplifier's manual describes.

1. Connect the source in Concord. In *Signal integrity* and **Advanced → Acquisition
   details**, compare with the acquisition software's own display:
   - [ ] channel count and labels, sample rate, units (Concord shows `arbitrary` if your
         source does not declare a voltage unit for every channel — it never guesses);
   - [ ] the traces show the test signal on the expected channels with the expected shape.
2. Record the **same interval** in both systems: start the acquisition software's own
   recording (e.g. LabRecorder XDF for LSL, Open Ephys binary format), then
   **Advanced → Recording → Start recording** in Concord; run for 60 s; stop Concord first,
   then the acquisition recording. Note wall-clock start/stop times in both.
3. Offline, compare the two files (your lab's analysis tools; a Concord recording is one JSON
   object per line, `recording.frame` events carry `first_sample_index`, `samples`,
   `sample_rate_hz` and `unit`):
   - [ ] **sample counts**: Concord samples between two marker times equal the reference's;
   - [ ] **continuity**: Concord `first_sample_index` has no gaps that the reference does
         not have; Concord's own counters (gaps, estimated missing samples, stalls) agree;
   - [ ] **values**: per channel, Concord values equal the reference after unit conversion
         (report max absolute difference and correlation);
   - [ ] the 10 Hz component appears at 10 Hz with the expected amplitude.
4. Disconnect the cable / stop the acquisition stream for ~5 s and reconnect: Concord shows
   *Interrupted — reconnecting* and counts the gap; note what happened.

## 3. Timing checks

- [ ] **Event alignment**: send a hardware TTL/marker at known times (e.g. a button or a
      pulse generator into a digital input that your acquisition software records and
      publishes as markers). In the Concord recording, compare each `recording.annotation`
      time with the reference's marker time: report mean offset and jitter.
- [ ] **Delay to Concord**: *Signal integrity* "delay" and **Advanced → Diagnostics**
      (pipeline and delivery latency percentiles); for LSL compare Concord's device
      timestamps with LabRecorder's for the same samples.
- [ ] **Display latency** of the participant screen is *not* measured by Concord. If it
      matters for your task, measure it with a photodiode.
- [ ] With the processing pipeline running at your intended settings: `dropped_inputs`
      stays 0 and processing time stays below the bin duration
      (**Advanced → Pipeline details**) over at least 10 minutes.

## 4. Stop procedures (rehearse each; time each)

| Procedure | Expected effect | Check |
| --- | --- | --- |
| **Stop control** (red, title bar) | command output off at once; queued commands withdrawn | apps stop moving; *Command output* reads Off |
| **Safe stop & disconnect** | command output off, recording closed, decoding stopped, source disconnected | session log line "Safe stop: stopped …"; *Acquisition source* empty |
| **Revoke** an application | that app receives no further commands | the app reports *not authorized* |
| Unplug / stop the acquisition stream | Concord reconnects or ends in *error*; control is turned off by any link loss | control Off; session log entry |
| Quit Concord (app: ⌘Q; pip: `concord stop`) | safe stop, then Concord exits; the recording is complete | next start lists the recording as complete |
| Force-quit / kill Concord | nothing is sent to devices (Concord never sends); at the next start the recording is kept and marked *incomplete* | Advanced → Stored data |

Record for each: who triggered it, time to effect, anything unexpected. A participant-facing
application must stop by itself when commands stop (the SDK's `CommandGuard` does).

## 5. Evidence to keep

- [ ] The doctor report and `concord version --json` output (§1).
- [ ] The **session export bundle** (Session and export… → Create export bundle; include
      recordings only if your data policy allows): versions with package fingerprints, the
      session log, device descriptors, pipeline settings, models, calibration reports.
- [ ] The acquisition software's recording and settings, and the hardware description
      (amplifier model, serials if your lab tracks them, montage).
- [ ] The comparison results of §2 and §3 against your pre-registered criteria, with the
      analysis code.
- [ ] Screenshots of Concord and the acquisition software side by side.
- [ ] The stop-procedure table (§4) filled in.
- [ ] Deviations from this protocol and their reasons.

## 6. Reporting the result

State the validation level honestly: matching data and timing against an independent
reference for a named hardware + software chain is what docs/VALIDATION_LEVELS.md calls
**level 3 (hardware-verified)** — for that chain only. For a plugin, record it with
`concord-certify --attestation` (docs/CERTIFICATION.md). Nothing in this protocol establishes
decoding performance, closed-loop control, or suitability for any clinical use.
