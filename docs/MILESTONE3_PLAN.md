# Milestone 3 — Lab-ready live acquisition, processing and online decoding

## Audit of `main` (aa1f799)

| Area | State on main | Verified |
| --- | --- | --- |
| Runtime, contract 1.1, SDKs, simulation, console, board | working | 174 backend + 57 frontend tests pass |
| FALCON H1 replay (NWB), offline decoder | working | real-data tests pass with downloaded files |
| macOS desktop packaging | **not in the repository** (no Tauri/packaging files on any branch) | nothing here touches packaging |
| Live acquisition | none | — |
| Streaming DSP / online decoding | none; the decoder runs only inside the NWB replay source | — |

## Primary sources used for the protocols

- **LSL:** the official liblsl 1.18 (bundled in `pylsl` 1.18.6). Tests use real liblsl outlets
  and inlets over the network stack, not mocks.
- **Open Ephys ZMQ Interface:** the plugin source `open-ephys-plugins/zmq-interface` at commit
  `38513917` (2025-07-07), files `Source/ZmqInterface.cpp` and
  `Resources/python_client/plot_process_zmq.py`. Facts taken from it:
  - PUB socket on `data_port` (default 5556); REP heartbeat socket on `data_port + 1`.
  - Envelope frames are `b"DATA\0"` / `b"EVENT\0"` (NUL-terminated).
  - Header JSON:
    - `data`: `content{stream, channel_num, channel_name, num_samples, sample_num, sample_rate}`, `data_size`
    - `event`: `content{stream, source_node, type, sample_num}`, `data_size`
    - `spike`: header key `spike{stream, source_node, electrode, sample_num, num_channels, num_samples, sorted_id, threshold[]}`, no `data_size`
    - every header also has `message_num` and `timestamp` (sender wall clock, ms)
  - Payloads:
    - data: one message per channel per block, float32 samples
    - TTL event (type 3): byte 0 = line, byte 1 = state, bytes 2–9 = uint64 word, per the official client
    - spike: float32 waveform
  - Heartbeat: JSON `{"application", "uuid", "type": "heartbeat"}` on REQ, replied to with
    "heartbeat received"; the plugin marks a client dead after 5 s without one.
  - **Physical units are not transmitted.**

## Design (smallest extension of what exists)

```
LSL inlet / OE SUB socket  ->  DeviceAdapter (read/normalize, unchanged contract)
   -> Runtime (_ingest: validate, seq, provenance)  -> EventBus -> SDK apps
                 |  tap (bounded queue, drop-counted)
                 v
   Pipeline task: preprocessing -> features -> StreamingDecoder -> [CommandRouter]
                 |  derived drafts (processed_feature / decoded_intent + model_id)
                 +--> Runtime._ingest (same seq/session/provenance path)
```

- **Contract 1.2 (additive):**
  - `recording.frame.unit` gains `"arbitrary"` for sources that do not state a known unit.
    Known units are converted exactly to µV; nothing is guessed.
  - New event `features.vector` (capability `neural_features`, provenance
    `processed_feature`) for continuous-valued features such as log band power.
- **Adapters:**
  - `adapters/lsl` (pylsl): discovery, metadata parsing, composite sources
    (signal + markers + behavior on one clock), stall/loss detection, reconnect by `source_id`.
  - `adapters/openephys` (pyzmq): protocol-exact parsing, heartbeats, message/sample gap
    accounting, configuration-change detection.
- **Processing (`brainos/processing`):** causal, chunk-invariant stages:
  - filters: Butterworth bandpass, notch, common average reference
  - threshold-crossing counts (−4.5 × RMS, refractory period)
  - log band power
  - presets per modality, with sample-rate validation
- **Pipeline (`runtime/pipeline.py`):** runs as a separate asyncio task. Derived capabilities
  are merged into negotiation. Latency and drops are measured.
- **Decoders:**
  - The existing `RidgeDecoder` is extended with an explicit input spec (feature, bin, channel
    labels) and a source identity.
  - Mismatches raise `incompatible_decoder`.
  - A model from another source requires an explicit override, which is recorded and shown.
- **Command router:** off by default. The operator explicitly maps decoded dimensions to
  `intent.pointer` (`decoded_intent` + `model_id`). Raw or decoded neural data never becomes
  an actionable command without this step.
- **Calibration:**
  - Record a session (the existing `Recorder`) and align features with behavior on the device
    clock.
  - Chronological split, ridge fit, held-out report, versioned model JSON.
  - Calibration task: `backend/examples/center_out_task.py` publishes cue kinematics and trial
    markers as LSL streams (the standard way task software integrates); the LSL adapter maps
    them onto the neural stream's clock with `time_correction`. (Chosen over an
    app → runtime label channel, which would have added a new write-like API.)
- **Reference app:** `backend/examples/reference_app` uses only `brainos.sdk`. Tests run it against
  simulation, LSL and Open Ephys sources, plus a raw-only source.
- **Console:**
  - discover/connect LSL and Open Ephys sources
  - signal integrity panel
  - pipeline/decoder/calibration/routing controls
  - stop
- **Validation levels** are documented explicitly
  (software-implemented / protocol-tested / hardware-verified / human-validated).

## Acceptance criteria (M3-AT-*)

| ID | Criterion |
| --- | --- |
| M3-AT-1 | LSL: discover real liblsl outlets; channel labels, units, types, rate and format come from stream metadata; unknown units are labelled `arbitrary`, never assumed |
| M3-AT-2 | LSL: known units are converted exactly to µV; sample values are preserved end-to-end |
| M3-AT-3 | LSL: source timestamps preserved; composite streams on one clock; gaps flagged and counted |
| M3-AT-4 | LSL: outlet loss → reconnecting → recovery when a stream with the same source_id returns; error state if it does not |
| M3-AT-5 | OE: messages built byte-for-byte per plugin source are parsed; the official reference client parses our test publisher identically |
| M3-AT-6 | OE: malformed envelopes/headers/sizes are rejected and counted; message_num and sample_num gaps counted; heartbeat protocol works |
| M3-AT-7 | Processing stages are causal and chunk-invariant (streamed output == batch output) |
| M3-AT-8 | Threshold crossings recover injected spikes; band power matches analytic power of test tones |
| M3-AT-9 | Pipeline: features + decoding on live streams; per-stage latency and drops measured; incompatible decoders refused with explicit errors |
| M3-AT-10 | Router off ⇒ no actionable events; router on ⇒ `intent.pointer` with `decoded_intent` + model_id |
| M3-AT-11 | FALCON H1 via LSL (declared prerecorded) → calibration recording → model → held-out metrics consistent with the offline evaluation; still labelled prerecorded |
| M3-AT-12 | Reference app (SDK only) receives commands from simulated, LSL and OE sources unchanged; receives none from raw-only sources |
| M3-AT-13 | Long-running, high-rate soak: measured throughput, latency distributions, loss; reconnect/switch under load |
| M3-AT-14 | Console controls all work (Playwright e2e) |
| M3-AT-15 | All previous tests pass |
