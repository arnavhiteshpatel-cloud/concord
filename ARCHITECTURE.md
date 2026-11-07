# BrainOS — Architecture

Status: v1 + Milestone 2 (schema 1.1: recorded human data, offline decoding) + Milestone 3
(schema 1.2: live LSL / Open Ephys acquisition, streaming pipeline, calibration, command router; §11). This document is normative: if code and this
document disagree, one of them is a bug.

## 1. System overview

```
 ┌──────────────── device side (untrusted, device-specific) ───────────────┐
 │  Simulated Profile A/B    Replay (BrainOS rec.,    LSL inlets      Open Ephys │
 │  (binary / JSON lines)    NWB datasets)            (liblsl)        ZMQ (SUB)  │
 └──────────┬───────────────────────┬────────────────────────┬─────────────┘
            │ NativePacket          │ NativePacket           │ NativePacket
            ▼                       ▼                        ▼
 ┌──────────────────────── DeviceAdapter contract ─────────────────────────┐
 │   open() / close() / set_paused() / read() -> NativePacket               │
 │   normalize(NativePacket) -> [EventDraft]   (pure, device-specific)      │
 └──────────────────────────────────┬──────────────────────────────────────┘
                                    │ EventDraft (no seq / session / ts)
                                    ▼
 ┌──────────────────────────────── Runtime ────────────────────────────────┐
 │  state machine · capability check · envelope stamping (seq, ts, ids)     │
 │  schema validation · reconnect policy · pause/resume · device switching  │
 │  diagnostics · recorder                                                  │
 │                    │                                                     │
 │                    ▼  EventEnvelope v1 (validated)                       │
 │               EventBus  ── per-subscriber bounded queue, filtered by     │
 │                            negotiated capability grants                  │
 └────────┬───────────────────────────────┬────────────────────────────────┘
          │ WebSocket  /api/v1/stream     │ REST /api/v1/*
          ▼                               ▼
   Python SDK · TS SDK            Console (operator UI)
          │
          ▼
   Applications (e.g. Communication Board) — device-agnostic
```

Everything above the `DeviceAdapter` line is device-specific. Everything below
it only sees `EventDraft` and then `EventEnvelope`. **Applications never see a
native packet, a device-specific field, or a device-specific code path.**

## 2. Components and code layout

| Component | Path | Responsibility |
| --- | --- | --- |
| Contracts | `backend/src/brainos/contracts/` | Capability vocabulary, event envelope + payload models, provenance rules, stream protocol messages, error codes. No I/O. |
| Adapter contract | `backend/src/brainos/adapters/base.py` | `DeviceAdapter` ABC, `NativePacket`, `EventDraft`, `DeviceDescriptor`, adapter errors. |
| Simulated adapters | `backend/src/brainos/adapters/simulated/` | Two synthetic profiles with distinct native wire formats, rates and capabilities; operator-driven intent source; fault injection. |
| Replay adapter | `backend/src/brainos/adapters/replay/` | Reads BrainOS recordings (and, later, external datasets) through the same contract. |
| Runtime | `backend/src/brainos/runtime/` | Orchestration, negotiation, event bus, diagnostics, recorder, device registry. |
| Server | `backend/src/brainos/server/` | FastAPI app: REST + WebSocket transport, static console hosting, test-report endpoint. |
| Python SDK | `backend/src/brainos/sdk/` | Async client for third-party developers. |
| TS SDK | `frontend/src/sdk/` | Browser client used by the console and the board app. |
| Console | `frontend/src/console/` | Operator UI: devices, runtime controls, events, signals, diagnostics, apps, tests. |
| Board app | `frontend/src/apps/board/` | Demo application. Imports **only** `src/sdk`. Enforced by a test. |
| LSL adapter (M3) | `backend/src/brainos/adapters/lsl/` | Discovery, metadata, composite signal + behavior + marker inlets, timestamps, gap detection, reconnect. Receive-only. |
| Open Ephys adapter (M3) | `backend/src/brainos/adapters/openephys/` | ZMQ Interface plugin wire format (data, TTL, spikes), heartbeat, block assembly, loss accounting. Receive-only. |
| Processing (M3) | `backend/src/brainos/processing/` | Causal, chunk-invariant streaming stages and presets. |
| Pipeline (M3) | `backend/src/brainos/runtime/pipeline.py` | Features → decoder → (optional) command router, as derived events in the device's session. |
| Live sources (M3) | `backend/src/brainos/runtime/live_sources.py` | Operator-configured LSL / Open Ephys sources exposed as devices. |
| Decoding (M2/M3) | `backend/src/brainos/decoding/` | Ridge decoder, model metadata + compatibility rules, calibration from recordings. |
| Reference app (M3) | `backend/examples/reference_app/` | Cursor app using only `brainos.sdk`; test-enforced. |
| Test publishers (M3) | `backend/src/brainos/testing/` | LSL and Open Ephys protocol publishers (synthetic or prerecorded, declared). |
| Adapter SDK (M4) | `packages/brainos-adapter-sdk/` | Public plugin API (`api.py`), validation (`validate.py`), IPC (`ipc.py`), plugin host process (`host.py`), sync host client. No BrainOS import. §12. |
| Plugin adapter (M4) | `backend/src/brainos/adapters/plugin/`, `runtime/plugins.py`, `server/plugin_routes.py` | Runs installed source plugins out of process; discovery, configuration, role → event mapping. §12. |
| Example plugin (M4) | `examples/adapters/brainos-example-adapter/` | Separately installable third-party-style plugin (declared-synthetic motor-imagery EEG). |

## 3. Capability model

### 3.1 Vocabulary (closed set; 1.1 added the last three; 1.2 added `features.vector`)

| Capability | Event types | Description |
| --- | --- | --- |
| `recording` | `recording.frame`, `recording.annotation` | Multichannel sample frames (raw signal) and time-aligned behavioral labels. |
| `pointer_intent` | `intent.pointer` | Continuous 2-D velocity intent in normalized workspace units. |
| `selection` | `intent.selection` | Discrete "select / activate" intent. |
| `text_intent` | `intent.text` | Discrete text (character or word) intent. |
| `telemetry` | `telemetry.sample` | Device health metrics (battery, temperature, link quality …). |
| `device_status` | `device.status` | Connection / streaming state changes. |
| `neural_features` (1.1) | `features.binned`, `features.vector` (1.2) | Processed neural features: counts per channel per time bin, or real-valued per-channel features (e.g. log band power). |
| `behavior` (1.1) | `behavior.sample` | Recorded behavioral ground truth (e.g. cued kinematics). |
| `kinematic_intent` (1.1) | `intent.kinematics` | Multi-dimensional movement intent in a source-defined space (simulated or decoded). |

Every event type maps to exactly one capability; the envelope carries that
capability explicitly and validation rejects mismatches.

### 3.2 Capability descriptors

A device declares a `CapabilityDescriptor` per capability it supports, with
parameters (e.g. `rate_hz`, `channel_count`, `sample_rate_hz`, `dims`,
`text_modes`). Descriptors are informational for apps and binding for the
adapter: **an adapter emitting an event for an undeclared capability is a
contract violation; the runtime drops the event and counts it**
(`undeclared_capability`).

### 3.3 Negotiation

An application's `hello` lists `required` and `optional` capabilities.

- Unknown capability name → protocol error `unknown_capability`, connection
  closed (code 1008). Never silently ignored.
- Each requested capability is either `granted` or `rejected` with a reason:
  `unsupported_by_device` or `no_device`.
- If any **required** capability is rejected, the app status is `suspended`:
  it stays connected, receives runtime/negotiation notices, but **no events**.
- On every device change (connect, switch, disconnect) the runtime
  re-negotiates for every connected app and sends a `negotiation` message.
  Apps adapt to the new grant set; this is how one unchanged app runs on
  devices with different capabilities.
- Events are delivered only for granted capabilities (enforced server-side,
  not by client filtering).

`POST /api/v1/negotiate` offers the same algorithm as a dry run against any
registered device.

## 4. Event envelope (schema `1.2`; 1.1 and 1.2 are additive over 1.0)

```jsonc
{
  "schema_version": "1.2",           // major.minor; consumers accept same major
  "session_id": "ses_8f3a…",        // one per device connection
  "device_id": "sim-a",
  "seq": 1042,                       // runtime-assigned, strictly increasing per session
  "timestamp_ns": 1730950000000000000,        // runtime wall clock at ingest (UTC ns)
  "device_timestamp_ns": 52340000000,         // device clock from native packet, nullable
  "event_type": "intent.pointer",
  "capability": "pointer_intent",
  "payload": { "vx": 0.12, "vy": -0.40 },
  "quality": { "score": 0.94, "flags": ["synthetic"] },
  "provenance": {
    "kind": "simulated_intent",
    "adapter": "brainos.sim.profile_a@0.1.0",
    "synthetic": true,
    "model_id": null,
    "origin": "operator",
    "replayed": false
  }
}
```

The authoritative definition is the Pydantic model in
`contracts/events.py`; the exported JSON Schema is committed at
`contracts/event-envelope.v1.schema.json` and a test fails if they drift.

### 4.1 Payloads

| Event type | Payload |
| --- | --- |
| `recording.frame` | `sample_rate_hz`, `channel_count`, `first_sample_index`, `unit` (`uV`, or `arbitrary` (1.2) when the source does not declare a convertible unit for every channel), `samples[channel][sample]` (shape validated) |
| `recording.annotation` | `label`, `value` (number/string/null), `duration_ms` |
| `intent.pointer` | `vx`, `vy` — velocity in workspace units/s; workspace = unit square, x → right, y → down; `|v| ≤ 10` |
| `intent.selection` | `action` (`primary`), `confidence` ∈ [0,1] |
| `intent.text` | `text` (1–64 chars), `mode` (`character`/`word`), `confidence` |
| `telemetry.sample` | `metrics: [{name, value, unit}]` |
| `device.status` | `state` (`connected`/`streaming`/`paused`/`reconnecting`/`disconnected`/`error`/`ended`), `detail` |
| `features.vector` (1.2) | `feature` (`band_power`/`log_band_power`), `unit`, `band_hz` [lo, hi] or null, `bin_ms`, `bin_index`, `channel_count`, `values[channel]` (finite). The bin ends at `device_timestamp_ns`. |
| `features.binned` | `feature` (`spike_count`/`threshold_crossing_count`), `unit` (`count`), `bin_ms`, `bin_index`, `channel_count`, `counts[channel]` (non-negative ints). The bin ends at `device_timestamp_ns`. |
| `behavior.sample` | `quantity`, `dims[]`, `unit`, `values[dim]`, `sample_index`, `valid` (false where the dataset excludes the sample) |
| `intent.kinematics` | `quantity`, `dims[]`, `unit`, `values[dim]`, `space` (e.g. `falcon_h1_7dof`) |

All numbers reject NaN/Infinity.

### 4.2 Provenance — the separation rule

`provenance.kind` is one of:

| Kind | Meaning | Allowed event types | Extra rule |
| --- | --- | --- | --- |
| `raw_signal` | Samples as acquired (or synthesized) | `recording.frame` | — |
| `behavioral_label` | Prerecorded behavioral / task labels (e.g. cue, cursor kinematics in a dataset) | `recording.annotation` | — |
| `simulated_intent` | Intent produced by a simulator | `intent.*` | `synthetic` must be `true` |
| `decoded_intent` | Intent produced by a decoding model | `intent.*` | `model_id` required |
| `device_report` | Device self-report | `telemetry.sample`, `device.status` | — |
| `runtime` | Runtime-originated status | `device.status` | — |
| `processed_feature` (1.1) | Features computed from neural data (e.g. binned spike counts, band power) | `features.binned`, `features.vector` | — |

`behavior.sample` uses `behavioral_label`; `intent.kinematics` uses `simulated_intent` or
`decoded_intent` (with `model_id`).

These rules are enforced by the envelope validator. Consequences:

- A behavioral label can never be delivered as an intent. Replay of a dataset
  does **not** turn labels into intents; only a decoder (with a `model_id`)
  may emit `decoded_intent`.
- Recorded neural activity is never an intent: `features.*` can only carry
  `processed_feature`. `decoded_intent` is emitted only by a decoder with a `model_id`:
  `intent.kinematics` by the M2 offline source or the M3 pipeline, and `intent.pointer`
  **only** when the operator has explicitly enabled the M3 command router (§11.4).
  Without the router no application that requires a command capability is activated.
- Replayed events keep their original `kind`, and set `replayed: true` plus a
  `replayed` quality flag.

### 4.3 Ordering and timing

- `seq` is assigned by the runtime from a single pump task per session, so it
  is strictly increasing. Envelope `seq` is **not** contiguous for a given
  subscriber (it only sees granted capabilities).
- Each WebSocket frame carries a per-connection `delivery_seq` that **is**
  contiguous; a gap means the server dropped events for that subscriber
  (bounded queue overflow). SDKs report gaps.
- `device_timestamp_ns` regressions are flagged (`timestamp_regression`
  quality flag) and counted, never silently reordered. Monotonicity is checked **per
  stream** — per (event type, producing adapter) — because a composite source (signal +
  behavior + markers) or the pipeline legitimately interleaves streams (M3).

## 5. Adapter contract

```python
class DeviceAdapter(ABC):
    descriptor: DeviceDescriptor               # id, kind, version, capabilities
    async def open(self) -> None               # raises DeviceLinkError
    async def close(self) -> None
    def set_paused(self, paused: bool) -> None # best-effort acquisition pause
    async def read(self) -> NativePacket       # next packet; DeviceLinkError / EndOfStream
    def normalize(self, packet) -> Sequence[EventDraft]   # pure; PacketDecodeError
```

- `read()` is device-specific I/O. `normalize()` is device-specific decoding
  and must be pure, so it is unit-testable with captured packets.
- An `EventDraft` has `event_type`, `payload`, `quality`, `provenance`,
  `device_timestamp_ns`. It has no `seq`, `session_id`, or runtime timestamp —
  the adapter cannot forge those.
- **There is no write path.** No method sends data or commands to the device.
  This is the v1 read-only guarantee at the type level.

### 5.1 Simulated profiles (synthetic, not commercial devices)

| | Profile A `sim-a` | Profile B `sim-b` |
| --- | --- | --- |
| Concept | High-bandwidth cortical array | Low-bandwidth discrete interface |
| Native format | Binary frames: magic, type, length, µs clock, payload, CRC32 | JSON lines: `ts_ms`, `k`, `d` |
| `recording` | 32 ch @ 1000 Hz, 40-sample frames (25 frames/s), int16 counts | 8 ch @ 250 Hz, 25-sample frames (10 frames/s) |
| `pointer_intent` | 50 Hz | **not supported** |
| `selection` | yes | yes |
| `text_intent` | **not supported** | yes (character) |
| `telemetry` | 1 Hz | 0.2 Hz |
| `device_status` | yes | yes |

Intent source: the operator (console "Simulated intention source" panel or
the `/api/v1/sim/*` endpoints). The simulator adds profile-specific
quantization, noise, and latency. The synthetic raw signal is noise plus
oscillations; it is **not** physiologically modeled and is **not** coupled to
intents — no decoding is implied.

Fault injection (`/api/v1/sim/faults`): `link_drop` (recoverable),
`link_fail` (unrecoverable until reconnect), `malformed_packet`,
`timestamp_regression`.

### 5.2 Replay

`ReplayAdapter` is the single replay engine. It pulls `ReplayRecord`s from a
`ReplaySource` (`name`, `origin`, `descriptor()`, `records()`, `duration_ns()`)
and re-emits them with their original relative timing. It supports pause/resume,
looping, end-of-stream, and **speed control** (`set_speed`, 0.1–64×, re-anchored so
position never jumps). It reports `playback_status()` (position, duration, speed,
loops) through the optional `PlaybackControl` interface. When behind schedule it
yields to the event loop every 64 records. Every replayed event gets
`provenance.replayed = true`, `origin = source.origin`, and a `replayed` quality flag.

Sources:

| Source | Device ids | Emits |
| --- | --- | --- |
| `BrainOSRecordingSource` | `replay:<name>` | the recorded envelopes (runtime status events excluded) |
| `NWBUnitsSource` (M2) | `nwb:<file-slug>` | per bin: `features.binned` (`processed_feature`), `behavior.sample` (`behavioral_label`) if the file has kinematics, `intent.kinematics` (`decoded_intent`) only if a held-out decoder is attached |

`NWBUnitsSource` reads NWB `units.spike_times` with PyNWB, bins them on demand in
chunks (bit-identical to the dataset authors' reference binning), validates the
timebase against the spike times, and returns `SourceMetadata` (dataset, license,
SHA-256 verification, channels, notes). Files without a units table (e.g. raw
`ElectricalSeries` only) are rejected as an unsupported modality. Offline sources
are `kind = replay`, `synthetic = false`, and are labelled "Recorded Human
Intracranial Data — Offline Replay", never as a live device.

### 5.3 Decoders (M2)

`brainos.decoding.ridge.RidgeDecoder` is a JSON-serialized linear model with a
causal streaming implementation identical to its offline prediction. The
`NWBCatalog` attaches a model to a dataset file only if the model's
`evaluations` include that file's SHA-256. `NWBUnitsSource` refuses (with
`DecoderLeakageError`) any model trained on the same session as the file.

## 6. Runtime

### 6.1 State machine

```
idle ──connect──▶ connecting ──ok──▶ streaming ◀──resume── paused
  ▲                   │ fail            │  ▲  └──pause──▶ ┘
  │                   ▼                 │  │
  └──disconnect── error ◀──retries──  reconnecting
                            exhausted   (link error)
```

`switch(device)` = disconnect current (if any) + connect new, under one lock;
the measured switch duration is recorded in diagnostics.

### 6.2 Data path per packet

`adapter.read()` → `adapter.normalize()` → capability declared? →
stamp (`schema_version`, `session_id`, `device_id`, `seq`, `timestamp_ns`) →
Pydantic validation → timestamp-regression check → diagnostics → bus fan-out
(filtered by grants) → recorder (if active).

Failures at any step are logged with context, counted
(`decode_errors`, `validation_errors`, `undeclared_capability`), and the
packet is dropped. The pump never dies on a bad packet. If the pump task
nevertheless dies from an unexpected exception, a watchdog moves the runtime
to `error` (it never keeps claiming `streaming`). Any active recording is
stopped whenever its device stops delivering (disconnect, switch, error, end).

### 6.3 Reconnect policy

On `DeviceLinkError`: state `reconnecting`, `device.status` emitted, then up
to 3 attempts with backoff 0.2 s / 0.5 s / 1.0 s. Success → `streaming`
(same session, `seq` continues). Exhausted → `error`.

### 6.4 Backpressure

Each subscriber has a bounded event queue (default 2048). On overflow the
oldest event is dropped and counted per subscriber. Control messages
(negotiation, runtime state, pongs) use a separate queue and are never dropped; it is
bounded at 256 messages, and a client that falls that far behind is disconnected (close
code 1008, `control_queue_overflow`) rather than allowed to grow server memory.

## 7. Transport & API

REST under `/api/v1`: `health`, `capabilities`, `devices`, `devices/{id}`,
`devices/{id}/source` (offline metadata, or live counters for an LSL / Open Ephys
source), `datasets`, `runtime`,
`runtime/{connect,switch,disconnect,pause,resume}`, `runtime/playback`
(GET status / POST `{speed}`; `unsupported_operation` for live devices),
`diagnostics`, `negotiate`, `schema/event`, `recordings`,
`recordings/{start,stop}`, `system/tests`; simulation-only:
`sim/{pointer,select,text,faults}`. Milestone 3 (operator controls, `live_routes.py`):
`sources/lsl` (GET), `sources/lsl/discover`, `sources/lsl` (POST: signal + optional
behavior/markers keys), `sources/openephys`, `DELETE sources/{id}`, `pipeline`,
`pipeline/{start,stop,router}`, `pipeline/presets`, `models`, `calibration/train`. Milestone 4
(`plugin_routes.py`, §12): `plugins` (GET), `plugins/discover`, `plugins/{name}/configure`;
`DELETE sources/{id}` also removes configured plugin devices.

WebSocket `/api/v1/stream`, protocol `brainos.stream/1`:

| Direction | Message |
| --- | --- |
| C→S | `hello {protocol, app{id,name,kind}, capabilities{required[],optional[]}}` (must be first) |
| C→S | `ping {nonce}` |
| S→C | `welcome {connection_id, negotiation, runtime}` |
| S→C | `event {delivery_seq, event}` |
| S→C | `negotiation {negotiation}` |
| S→C | `runtime {runtime}` |
| S→C | `error {code, message}` / `pong {nonce}` |

Any other client message → `error{code: "read_only_runtime"}`. Clients cannot
send data toward devices.

## 8. Security boundaries (v1)

| Boundary | v1 stance |
| --- | --- |
| Device → runtime | Native packets are untrusted. Binary frames are length/CRC checked; every draft is schema-validated; undeclared capabilities are dropped. |
| App → runtime | Apps are untrusted. Hello is validated; unknown capabilities rejected; apps receive only granted capabilities; no write path exists. |
| Network exposure | Server binds `127.0.0.1` by default. **No authentication in v1** — local single-user demo only. Do not expose to a network. |
| Simulation endpoints | `/api/v1/sim/*` exist only for simulated devices and are disabled by `BRAINOS_ENABLE_SIM=0`. They are an operator tool, not an app API. |
| Data at rest | Recordings are written to `data/recordings/` (gitignored). With M3 live sources they may contain real neural data: treat the directory as research data under your protocol. No encryption. |
| Acquisition networks (M3) | LSL inlets and the Open Ephys SUB socket only *receive*. The Open Ephys heartbeat REQ sends only `{application, uuid, type: "heartbeat"}` (the plugin's event-injection request is not implemented). BrainOS opens no listening socket other than its HTTP server (default `127.0.0.1`). LSL discovery uses liblsl's multicast/broadcast on the local network. |

| Source plugins (M4) | Third-party plugin code runs in a separate process (fault isolation) and everything it sends is validated twice; it is **not sandboxed** — same user, files and network as BrainOS (§12, docs/ADAPTER_SDK.md §5). |

Planned (not implemented): per-app auth tokens, capability grants requiring
operator approval, signed adapters, audit log, TLS.

## 9. Extension points

1. **New device**: preferably a **source plugin** against the public adapter SDK (§12):
   `pip install` it and BrainOS discovers, validates and runs it out of process — no change
   to BrainOS. Built-in alternative: implement `DeviceAdapter`, register a factory in
   `runtime/registry.py`.
2. **New dataset format**: implement `ReplaySource` (see `NWBUnitsSource`), and
   pin verified files in a `brainos/datasets/*.json` manifest.
3. **Decoder**: the M3 pipeline (§11) runs a model on `features.*` from any device whose
   features match the model's declared input. New model types implement the same
   `streaming()` / `predict_counts()` behaviour and metadata (`brainos.model/1`).
4. **New capability**: requires a schema minor version bump, a payload model,
   provenance rules, and SDK type updates — deliberately not a plugin.

## 10. Diagnostics definitions

All values are measured in-process; nothing is estimated.

| Metric | Definition |
| --- | --- |
| pipeline latency | adapter produced/read the native packet → validated envelope enqueued to all subscriber queues (includes waiting behind packets read in the same tick) |
| delivery latency | envelope enqueued for a subscriber → written to its WebSocket |
| client latency (console) | envelope `timestamp_ns` → received in the browser tab (same-machine clocks, ms resolution) |
| rate | events in the last 5 s ÷ min(5 s, max(time since connect, 1 s)) |
| switch duration | wall time of `switch()` (disconnect + connect + renegotiation) |

## 11. Live acquisition and the real-time pipeline (Milestone 3)

```
 LSL outlet(s) ─┐                                   ┌─ features.binned / features.vector (processed_feature)
 Open Ephys ZMQ ┼─▶ adapter ─▶ runtime ─▶ bus ─tap─▶│  pipeline: preprocessing ─▶ features ─▶ decoder ─▶ router
 (receive-only) ┘   (normalize) (validate)          └─ intent.kinematics, intent.pointer (decoded_intent + model_id)
                                                        └─ re-ingested by the runtime, same session, validated
```

### 11.1 Device kinds and labelling

An external stream cannot prove where it comes from. LSL / Open Ephys sources are
`kind = stream` ("live stream · origin unverified") unless the stream itself declares
otherwise in BrainOS metadata (`<desc><brainos><prerecorded>` / `<synthetic>`): a declared
prerecorded stream is `kind = replay` and its events carry `replayed: true` (e.g. FALCON H1
streamed over LSL); a declared synthetic one is `kind = simulated`, `synthetic: true`. The
declaration travels with the data into recordings, decoders and calibration reports.

### 11.2 LSL adapter (`adapters/lsl/`)

- Discovery (`resolve_streams`) lists every outlet with its metadata. Usable signal
  streams: numeric, regular-rate; types ending in `SpikeCounts`/`BinnedSpikes` (BrainOS
  convention) map to `features.binned`, others to `recording.frame`. String or irregular
  streams can only be attached as markers.
- Units are taken from `<channels><channel><unit>`: converted exactly to µV if **every**
  channel has a known voltage unit, else frames are `unit = arbitrary` and a note says why.
- Timestamps: the signal stream's own LSL timestamps are `device_timestamp_ns`. Behavior and
  marker streams are mapped onto the signal clock with liblsl `time_correction`
  (refreshed periodically). Gaps (> 1.5 sample periods) are counted, frames are split at
  gaps and the frame after a gap is flagged `dropped_samples`.
- Loss (`LostError`) or a stall raises `DeviceLinkError` → runtime reconnect policy; a
  stream with the same `source_id` (new uid) is re-resolved. A changed channel count/format
  is refused rather than silently remapped.

### 11.3 Open Ephys adapter (`adapters/openephys/`)

Implements the Open Ephys GUI "ZMQ Interface" plugin wire protocol (details, sources and
deviations: docs/OPEN_EPHYS.md). SUB on `data_port`, REQ heartbeat on `data_port + 1`.
Per-channel messages are assembled into whole blocks; a block missing a channel is dropped
and counted, never padded. TTL events → `recording.annotation`; spikes → binned counts on
the sample clock. The plugin does not transmit units: the operator states them, otherwise
frames are `arbitrary`. Device timestamps are `sample_num / sample_rate` (the acquisition
clock), not wall clock.

### 11.4 Pipeline, decoders and the command router (`runtime/pipeline.py`)

- The pipeline taps the bus for its input event type in the current session into a bounded
  queue (4096; overflow drops the oldest and counts `dropped_inputs`) and runs in its own
  asyncio task. Derived events are re-ingested and validated like any adapter event, with
  `adapter = brainos.pipeline@…`, the source's `origin`, `synthetic` and `replayed`.
- Presets (`processing/chain.py`): `spikeband_threshold` (≥ 10 kHz: 250–5000 Hz band-pass,
  optional CAR, −4.5 × RMS threshold crossings, 1 ms refractory → `features.binned`),
  `ecog_high_gamma` / `band_power` (notch + band-pass → log band power →
  `features.vector`), `features_passthrough` (decode features the source already provides).
  Stages are causal and chunk-invariant (tested: streamed output == batch output).
- Models declare their input (`event_type`, `feature`, `bin_ms`, `channel_count`,
  `channel_labels`) and source identity (e.g. `dandi:000954:HumanPitt`). Loading is refused
  (`incompatible_decoder`, HTTP 409) on any mismatch, on a stream from the model's training
  session (leakage), and on a different source unless `allow_cross_source` is set — which is
  then shown in status and lowers event quality to 0.5.
- The **command router** is off by default. When the operator enables it, two decoded
  dimensions are mapped to `intent.pointer` (`decoded_intent`, `model_id`), z-scored by the
  training behavior std, with gain, dead-zone and clamp. Only then is `pointer_intent`
  negotiable; apps requiring it are otherwise suspended.
- Status reports per-input processing time, ingest → derived latency (p50/p95/p99/max),
  counters (inputs, dropped_inputs, features_out, decoded_out, commands_out, errors) and
  RMS warm-up remaining.

### 11.5 Calibration (`decoding/calibrate.py`)

Input: closed BrainOS recordings with neural features and `behavior.sample` labels (e.g. a
cue task's LSL Behavior stream, or a dataset's kinematics). Each feature bin is labelled
with the behavior sample nearest its end within half a bin (labels only; features are never
shifted). Chronological split at a trial marker after `train_fraction`, then `gap_bins`,
then held-out evaluation; only training data is used for z-scoring and alpha selection. The
saved model records recordings + SHA-256, sessions, input spec and source identity; a
markdown report is written to `reports/calibration/`.


## 12. Source plugins (Milestone 4)

A third party integrates a source by writing a plugin against `brainos_adapter_sdk` only
(`SourcePlugin` / `SourceSession`, API 1.0, read-only), exposing it in the `brainos.sources`
entry-point group and installing it into BrainOS's environment. Guide: docs/ADAPTER_SDK.md.

```
 runtime process (never imports plugin code)            plugin host process (one per plugin connection)
 ┌───────────────────────────────────────────┐          ┌──────────────────────────────────────────┐
 │ PluginRegistry ── host --list ────────────┼─spawn──▶ │ entry points (metadata only) → one probe │
 │                                           │          │ process per plugin: manifest, discover() │
 │ PluginAdapter.open() ── spawn ────────────┼─────────▶│ python -m brainos_adapter_sdk.host <ep>  │
 │   AsyncHostClient  ◀═ brainos.plugin-ipc/1 ═════════▶│   fd 1 → stderr, fd 0 → /dev/null        │
 │   re-validate (validate.py)               │  frames: │   validate.py: manifest, options,        │
 │   mapping.normalize → EventDraft          │  4-byte  │   session, every chunk                   │
 │   → runtime ingest (§6.2)                 │  len +   │   plugin.open() / session.read()         │
 └───────────────────────────────────────────┘  JSON +  └──────────────────────────────────────────┘
                                                raw LE buffers
```

### 12.1 Discovery, configuration, device ids

* Discovery (startup, in the background, and `POST /plugins/discover`) runs
  `python -m brainos_adapter_sdk.host --list`, which reads entry points from package metadata
  and probes each plugin in its own process (manifest + `discover()`). The runtime re-validates
  every manifest and device list. Each plugin is listed as `compatible`, `rejected` (with the
  validation problems, e.g. API version) or `load_error` (import / instantiation failure).
* Device ids: `plugin:<entry-point name>:<device key>` (≤ 64 characters; entry-point names
  ≤ 24). `configure` validates options against the plugin's `OptionSpec`s, then opens the device
  once in a host so the descriptor states real streams, units and modality.

### 12.2 Mapping (normative)

| Plugin role | Event | Provenance |
| --- | --- | --- |
| `signal` | `recording.frame` (µV only if every channel's unit is a known voltage unit, else `arbitrary`; split at sample-index gaps — the first frame after a gap is flagged `dropped_samples` — and at 2000 samples) | `raw_signal` |
| `spike_counts` | `features.binned` (`spike_count`; timestamp = bin end) | `processed_feature` |
| `behavior` | `behavior.sample` | `behavioral_label` |
| `markers` | `recording.annotation` | `behavioral_label` |
| `decoder_output` | `intent.kinematics`, `model_id = <plugin name>:<model id>` | `decoded_intent` |

One stream per role is delivered (primary first). Descriptor: `kind` = `simulated` (declared
synthetic) / `replay` (declared prerecorded; events `replayed: true`) / `stream`; `modality`,
`invasive` (declared, or by the contract's modality category), `integration = {kind: plugin,
package, version, api_version, isolated: true, ecosystem}`; adapter `<package>@<version>`.
**Clocks:** all streams of a session must be on the primary stream's clock domain
(`session.clock.mixed` otherwise); timestamps go to `device_timestamp_ns` unchanged. API 1.0
carries no clock offsets, so different clocks are refused, never merged.

### 12.3 Failure containment

| Event | Effect |
| --- | --- |
| Host exits / is killed, hangs past `read timeout + grace`, breaks the protocol | Host killed; `DeviceLinkError` → reconnect policy (§6.3) with a fresh host |
| Plugin raises `LinkLost` / `ConfigurationChanged` | `DeviceLinkError` → reconnect; a changed session updates the descriptor and renegotiates |
| `OpenFailed` / `InvalidOptions` | connect / reconnect attempt fails with the plugin's message |
| Invalid data, undeclared stream or role, invalid session or manifest, malformed IPC content, unexpected exception in plugin code, 3 sessions in a row failing before any data | Plugin **stopped**: every further open is refused with the reason, the runtime ends in `error` |

The runtime never imports plugin code; its pump only awaits the host client. Isolation is
fault isolation, not a security boundary (§8).
