# Validation levels

BrainOS distinguishes four levels of evidence. A component is at the **highest level whose
evidence actually exists**, not the level it was designed for. Every claim in the README,
console and docs must be consistent with this page.

| Level | Meaning | What it does **not** show |
| --- | --- | --- |
| **1. Software-implemented** | Code exists, is type-checked, and passes unit tests on inputs we constructed. | That it interoperates with anything we did not write. |
| **2. Protocol-tested** | Exercised over the real protocol stack — real liblsl outlets/inlets, real ZMQ sockets — by software publishers, in a separate process where relevant, with timing, loss and reconnect measured. Where an official reference implementation exists, it was run against our output. | That a real acquisition program (amplifier software, Open Ephys GUI) produces exactly what our publishers produce; anything about hardware timing, noise or failure modes. |
| **3. Hardware-verified** | Run against real acquisition hardware through its real producer software (e.g. an amplifier's LSL app, the Open Ephys GUI with an acquisition board), with integrity and timing checked against an independent reference. | Anything about decoding or control with a person. |
| **4. Human-participant validated** | Run with a participant, in a closed loop, under an approved research protocol, with performance measured by pre-registered metrics. | — |

**Real-data replay** sits beside level 2: genuine recorded human data (FALCON H1, DANDI
000954) streamed through a live protocol and *declared prerecorded*. It shows the software
path reproduces offline results on real neural statistics. It is not live acquisition and
not closed-loop control.

## Where each component is today (Milestone 4, workstream A)

| Component | Level reached | Evidence (all executed) | Not yet done |
| --- | --- | --- | --- |
| Contracts, schema 1.2, provenance rules | 1 | `test_contracts.py`, JSON Schema drift test, TS SDK tests | — |
| LSL adapter: discovery, metadata, units, timestamps, gaps, composite clocks, reconnect | **2** | `test_lsl.py` (16 tests) against liblsl 1.18 outlets; `bench_live.py` with the publisher in a separate process (30 kHz × 32/96 ch, 0 gaps); reconnect after killing the publisher process | Third-party LSL producers (vendor LSL apps, LabRecorder interop) not tested; no hardware |
| Open Ephys ZMQ adapter: data/TTL/spikes, heartbeat, block assembly, loss counters | **2** | `test_openephys.py` (61 tests); the **official** plugin Python client (`plot_process_zmq.py`, SHA-256 pinned, downloaded at test time) parses our publisher's output bit-exactly; message layout derived line by line from the plugin source | Never run against the Open Ephys GUI or an acquisition board. Our publisher reproduces the plugin's format from source; a mismatch with the real plugin binary is possible (see docs/OPEN_EPHYS.md "Limitations") |
| Signal processing (filters, CAR, threshold crossings, band power) | 1 (+ numerical reference) | Chunk invariance exact; equals SciPy `sosfilt`; analytic band power; ≥ 95 % recall of injected synthetic spikes | Never applied to real broadband neural recordings |
| Pipeline + streaming decoder | 2 + real-data replay | FALCON H1 block streamed over LSL: every bin received exactly once; decoded output equals the offline decoder bin for bin (`test_pipeline_live.py`); measured latency in docs/BENCHMARKS_LIVE.md | No live neural source |
| Decoder compatibility + leakage guards | 1 | Tests refuse wrong channel count / feature / bin, training-session streams, cross-source models without override | — |
| Calibration from recordings | 2 + real-data replay | Recording of FALCON-over-LSL → calibration gives the same held-out R² as fitting the file directly (within float32 tolerance); synthetic tuned units calibrate (R² > 0.3); unrelated signal gives R² < 0.2 | Never calibrated on live neural data or with a participant |
| Center-out cue task | 2 | Cue + marker streams attach to a neural stream on one clock (`test_center_out_task.py`) | Never shown to a participant; display timing (monitor latency) unmeasured |
| Command router + reference app | 1–2 | Same unchanged SDK-only app across simulator, FALCON-over-LSL (suspended until the router is enabled and the operator authorizes the app, then decoded commands), Open Ephys (suspended) | No person has controlled anything with it |
| Control bridge (M4): authorization, discrete actions, LDA, stop paths, SDK guard, menu app | 1 (+ real server and WebSocket in tests) | `test_control.py` (authorization, bus, router provenance, hysteresis, every stop path incl. input stall), `test_lda.py`, `test_sdk_guard.py`, `guard.test.ts`, `test_control_e2e.py` (real server + SDK + both reference apps: default deny, authorize, revoke / stop / disconnect within 1 s, raw-only and label-only sources yield no commands); LDA only on synthetic motor-imagery-like data generated in the tests; e2e demo M3-6 authorizes and revokes the board app | Never run on a real EEG/ECoG/intracortical source, with a participant, or with a third-party application |
| Operator console | 1–2 | Vitest (API helpers and every Acquisition/Pipeline/Router/Calibration control against a mocked server); Playwright `e2e/demo.cjs` steps M3-1…M3-5 against a real server with an LSL synthetic-ephys publisher and an Open Ephys ZMQ test publisher (discover, register, connect, integrity counters, spikeband pipeline counters, stop, remove) | Calibration, model loading and the router are not exercised in the browser demo (component + backend tests only) |
| Source plugins (M4): adapter SDK, validation, plugin host, isolation, `PluginAdapter`, REST, console | 1 | `test_plugin_validate.py` (one malformed-input test per rule), `test_plugin_host.py` (IPC bit-exactness, typed errors, stdout isolation, crash/hang/exit, `--list` with broken plugins), `test_plugin_runtime.py` (every broken test plugin is rejected or stopped and the runtime stays healthy), `test_plugin_example.py` (REST → WebSocket → record → replay → pipeline → host killed → reconnect), Vitest `Plugins.test.tsx`, Playwright step M4-1; IPC throughput measured (`scripts/bench_plugins.py`) | The isolation is fault isolation, not a security sandbox (docs/ADAPTER_SDK.md §5). Only test plugins and a synthetic example exist; no plugin for a real acquisition system has been run here (BrainFlow/BCI2000 plugins are separate work) |
| Example adapter (motor-imagery EEG generator) | 1 | Same seed → bit-identical samples through host, runtime, WebSocket and replay; mu ERD at C3/C4 measured in `test_generator_mu_desynchronisation` | Synthetic, declared so; not physiologically validated; never presented as brain data |
| **Anything** | **3 / 4** | **Nothing in BrainOS has reached level 3 or 4.** | Requires lab hardware, and for level 4 an approved protocol |

## What would move a component up a level

- **LSL → 3:** connect a real amplifier's LSL outlet (e.g. a lab EEG/ECoG system with
  an LSL app) while a reference recorder (LabRecorder → XDF) records the same streams;
  compare sample counts, values and timestamps offline; inject cable pulls and app restarts.
- **Open Ephys → 3:** Open Ephys GUI with an acquisition board (or the GUI's File Reader for
  a first step, which is still level 2 — it is not hardware), ZMQ Interface in the chain;
  compare against the GUI's own Binary-format recording of the same session; check TTL
  alignment with a known pulse generator.
- **Any → 4:** only within an approved human-research protocol run by qualified
  investigators. BrainOS provides no clinical functions and is not a medical device.

## Ecosystem plugins (Milestone 4, workstream B)

| Component | Level reached | Evidence (all executed) | Not yet done |
| --- | --- | --- | --- |
| `brainos-brainflow` plugin | **2** | 41 tests against the official BrainFlow 5.23.0 library: SYNTHETIC_BOARD (rate, timestamps, ordering), PLAYBACK_FILE_BOARD replaying a `DataFilter.write_file` file bit-for-bit, STREAMING_BOARD fed over multicast by a second official session (bit-exact), a real driver's `prepare_session` failure; metadata from every shipped board description; through the plugin host and the runtime in `test_plugin_ecosystems.py` and a 20 s `brainos-certify` run (`protocol_tested`, docs/compatibility/brainflow-synthetic.certify.md) | No hardware board |
| `brainos-bci2000` plugin (App Connector) | **2** | Genuine BCI2000 3.6 build (source fork) — SignalGenerator → DummySignalProcessing → DummyApplication's own ConnectorOutput — received live by the plugin (opt-in test); a capture of it replayed in CI; byte-for-byte reproduction sender for loss/reorder/wrap/malformed cases; the capture through the plugin host and the runtime in `test_plugin_ecosystems.py` and a 20 s `brainos-certify` run (`adapter_implementation`, docs/compatibility/bci2000-app-connector.certify.md) | No amplifier, no real BCI2000 application module; the certification run used the replayed capture, not live BCI2000 |

## Certification toolkit (Milestone 4, workstream D)

`brainos-certify` (docs/CERTIFICATION.md) reports four levels for a plugin. They map onto the
levels above as follows; the toolkit can grant only the first by itself.

| Certification level | Project level | Basis |
| --- | --- | --- |
| `adapter_implementation` | 1 (through the real plugin host) | 25 required automated checks + 4 optional BrainOS-runtime checks |
| `protocol_tested` | 2, if the named reference software really produced the data | operator statement (`--protocol-reference`) + consistency of ecosystem, origin and installed version |
| `hardware_tested` | not 3 by itself | an operator-signed attestation; level 3 additionally needs a documented comparison against an independent reference |
| `human_participant_validated` | 4 | never set by the toolkit |

| Component | Level reached | Evidence (all executed) | Not yet done |
| --- | --- | --- | --- |
| `brainos-certify` toolkit | 1 | `packages/brainos-certify/tests` (every check passes on a good plugin; each check that can fail or warn does so on a crafted defect; installed entry points and RECORD hash verification on a temporary distribution; level logic; signed / tampered / foreign-key / malformed attestations with OpenSSL Ed25519; report schema; CLI exit codes; a run with BrainOS hidden); every broken test plugin in `backend/tests/plugins` caught by a specific check (docs/COMPATIBILITY.md); real runs of the example, BrainFlow and BCI2000 plugins (docs/compatibility/) | Never run against a plugin for real acquisition hardware; thresholds are engineering choices, not standards |


## Cursor + click decoding (Milestone 5, P0)

Real-data replay of the Singer-Clark et al. cursor + click dataset (participant T15, Dryad
doi:10.5061/dryad.prr4xgxzq). Every number: docs/CURSOR_CLICK.md.

| Component | Level reached | Evidence (all executed) | Not yet done |
| --- | --- | --- | --- |
| Dryad manifest + fetcher | 1 + real data | 53 files pinned by SHA-256 from the Dryad API listing; downloads verified; `--verify` | — |
| T15 reader + replay source (`t15:*` devices) | 1 + real-data replay | `test_cursorclick_real.py`: files verified, layout, authors' trial/click structure, per-trial integration of the recorded decoder output reproduces the recorded cursor; every replayed event validates; runtime replay bit-exact for TX and SBP; error paths in `test_cursorclick_format.py` | Not live acquisition |
| Kalman cursor decoder | 1 + real-data replay (open loop) | Held-out grid blocks (trained only on earlier calibration blocks): mean angle error 28.0° (original online decoder 27.3°, shifted-feature control 92.4°); R² vs intention 0.765 (original 0.819, control −0.80) | Never closed loop; one participant, one day |
| Click decoder | 1 + real-data replay (open loop) | 81 % of BrainOS clicks fall while the recorded cursor is on the cued target (original 94 %, control 21 %); 5.0 false activations/min (original 1.5, control 21) | Never closed loop |
| Neural-to-communication (board) | 1 + real-data replay (open loop) | Word selection by BrainOS cursor + click over the task grid: anchored per trial 14 x 14 15 % / 7 x 7 34 % / 2 x 2 83 % (chance 0.5 / 2 / 25 %; shifted control at chance); through the board's whole-block integration 1 % / 4 % / 43 % (the original decoder's own outputs: 65 % / 83 % / 96 %) | No person has communicated through BrainOS; closed loop needed |

## Human ECoG (Milestone 5, workstream B)

Real-data replay of **recorded** human ECoG (AJILE12, DANDI 000055, one participant, clinical
epilepsy monitoring). Offline replay is not live acquisition (not level 2 for a live source),
not hardware (3) and not closed-loop use by a person (4).

| Component | Level reached | Evidence (all executed) | Not yet done |
| --- | --- | --- | --- |
| Slice streaming + verified NWB extracts (`datasets/extract.py`, `ajile12.json`) | 1 + real data | 6 slices fetched from DANDI by HTTP range reads; DANDI SHA-256 / size checked; each slice's stored values hash to the pinned digest; a one-sample change or a shifted timeline makes the extract unverified (`test_ecog_real.py`, `test_ecog.py`) | The full 10 GB source files were never downloaded and hashed here (DANDI's digest is trusted for them) |
| Raw-voltage NWB importer (`adapters/nwb/ecog.py`) | 1 + real-data replay | Frames through the unchanged runtime equal the stored µV bit for bit; electrode table, bad flags, pose, intervals, data-break flags; unit only from the file's declaration (synthetic fixtures for mV, channel_conversion, unusable units) | Only AJILE12-style files and synthetic fixtures; other ECoG/sEEG NWB layouts untested |
| ECoG preprocessing (source mains notch, CAR without bad electrodes, 70–150 Hz log power) | 1 (+ real data) | Chunk invariance and causality with CAR exclusion; live pipeline features equal the offline analysis on the real held-out slice | Never applied to a live ECoG stream; never on un-notched real ECoG |
| Movement-vs-rest LDA on ECoG | real-data replay (offline) | Held-out sessions: balanced accuracy 0.938 / 0.861, AUC 0.992 / 0.939 vs time-shift nulls ≤ 0.55 / 0.60 (docs/ECOG_DECODING.md); online == offline posteriors | No participant was trying to control anything; one participant |
| Modality guards | 1 (+ real streams) | ECoG model refused on FALCON spike counts, FALCON model and EEG-declared model refused on ECoG, even with the cross-source override | — |
| Same SDK-only app on ECoG | 1–2 (real server, real recorded ECoG) | Unchanged `menu_app.py` receives decoded selections from the held-out ECoG replay only after operator authorization; nothing after disconnect | No person used it; offline replay only |
