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

## Where each component is today (Milestone 3)

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
