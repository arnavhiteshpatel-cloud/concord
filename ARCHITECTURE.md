# BrainOS — Architecture

Status: v1 (MVP vertical slice). This document is normative: if code and this
document disagree, one of them is a bug.

## 1. System overview

```
 ┌──────────────── device side (untrusted, device-specific) ───────────────┐
 │  Simulated Profile A      Simulated Profile B      Replay source         │
 │  (binary framed packets)  (JSON-line packets)      (BrainOS recording)   │
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

## 3. Capability model

### 3.1 Vocabulary (closed set in v1)

| Capability | Event types | Description |
| --- | --- | --- |
| `recording` | `recording.frame`, `recording.annotation` | Multichannel sample frames (raw signal) and time-aligned behavioral labels. |
| `pointer_intent` | `intent.pointer` | Continuous 2-D velocity intent in normalized workspace units. |
| `selection` | `intent.selection` | Discrete "select / activate" intent. |
| `text_intent` | `intent.text` | Discrete text (character or word) intent. |
| `telemetry` | `telemetry.sample` | Device health metrics (battery, temperature, link quality …). |
| `device_status` | `device.status` | Connection / streaming state changes. |

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

## 4. Event envelope (schema `1.0`)

```jsonc
{
  "schema_version": "1.0",           // major.minor; consumers accept same major
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
| `recording.frame` | `sample_rate_hz`, `channel_count`, `first_sample_index`, `unit` (`uV`), `samples[channel][sample]` (shape validated) |
| `recording.annotation` | `label`, `value` (number/string/null), `duration_ms` |
| `intent.pointer` | `vx`, `vy` — velocity in workspace units/s; workspace = unit square, x → right, y → down; `|v| ≤ 10` |
| `intent.selection` | `action` (`primary`), `confidence` ∈ [0,1] |
| `intent.text` | `text` (1–64 chars), `mode` (`character`/`word`), `confidence` |
| `telemetry.sample` | `metrics: [{name, value, unit}]` |
| `device.status` | `state` (`connected`/`streaming`/`paused`/`reconnecting`/`disconnected`/`error`/`ended`), `detail` |

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

These rules are enforced by the envelope validator. Consequences:

- A behavioral label can never be delivered as an intent. Replay of a dataset
  does **not** turn labels into intents; only a decoder (with a `model_id`)
  may emit `decoded_intent`.
- v1 ships **no decoder**. All intents in v1 are `simulated_intent`.
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
  quality flag) and counted, never silently reordered.

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

`ReplayAdapter` reads a BrainOS recording (`brainos.recording/1`, JSONL:
header line + envelopes) and re-emits drafts with original relative timing
(optional speed factor, looping). Runtime-originated status events are not
replayed. The source abstraction (`ReplaySource`) is designed so a future
reader for public intracranial datasets maps continuous data →
`recording.frame` (`raw_signal`) and trial/behavior tables →
`recording.annotation` (`behavioral_label`) — never to intents.

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

REST under `/api/v1`: `health`, `devices`, `runtime`, `runtime/{connect,
switch,disconnect,pause,resume}`, `diagnostics`, `negotiate`,
`schema/event`, `recordings`, `recordings/{start,stop}`,
`system/tests`; simulation-only: `sim/{pointer,select,text,faults}`.

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
| Data at rest | Recordings are written to `data/recordings/` (gitignored), synthetic only. No PHI. No encryption in v1. |

Planned (not implemented): per-app auth tokens, capability grants requiring
operator approval, signed adapters, audit log, TLS.

## 9. Extension points

1. **New device**: implement `DeviceAdapter`, register a factory in
   `runtime/registry.py`. No changes to runtime, SDKs, or apps.
2. **New dataset format**: implement `ReplaySource`.
3. **Decoder** (future): a component that consumes `raw_signal` events and
   emits `decoded_intent` drafts with a `model_id`. Its place in the pipeline
   is a v2 design item.
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
