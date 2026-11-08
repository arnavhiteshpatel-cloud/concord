# Concord SDK guide

Two SDKs speak the same protocol (`concord.stream/1`) and the same envelope (schema `1.0`):

- **Python** — `concord.sdk` (async; `httpx` + `websockets`). Installed by `make setup`.
- **TypeScript** — `frontend/src/sdk` (browser `WebSocket` + `fetch`, zero dependencies).

Both validate every incoming envelope against the contract (including provenance rules)
and never hand an application an event that violates it.

## Core ideas

1. **Declare capabilities, don't assume devices.** In `hello`, list `required` and
   `optional` capabilities from the closed vocabulary: `recording`, `pointer_intent`,
   `selection`, `text_intent`, `telemetry`, `device_status`.
2. **Negotiation is explicit.** Each request is `granted` or `rejected` with a reason
   (`unsupported_by_device`, `no_device`, `not_authorized`). Unknown names are a hard error
   (`unknown_capability`). If a required capability is missing, your app is
   `suspended` and receives no events.
3. **Renegotiation happens.** When the operator connects, switches, or loses a device,
   you receive a new negotiation. Adapt to `granted` — that is how one app runs on
   devices with different capabilities.
4. **Check provenance.** `provenance.kind` tells you whether an event is a raw signal,
   a behavioral label, a *simulated* intent, or a *model-decoded* intent
   (`decoded_intent` + `model_id`). `provenance.replayed` / `synthetic` say whether the data
   behind it is prerecorded or synthetic — show it to your users.
5. **Read-only.** There is no API to send anything to a device. Any client message
   other than `ping` gets `read_only_runtime`.

## Python

```python
import asyncio
from concord.sdk import (
    EventStream, RuntimeClient, NegotiationUpdate, RuntimeUpdate, ServerNotice, is_event,
)

async def main() -> None:
    async with RuntimeClient("http://127.0.0.1:8000") as rc:
        print([d.device_id for d in await rc.devices()])
        print(await rc.negotiate(["pointer_intent"], device_id="sim-b"))  # dry run

    async with await EventStream.connect(
        app_id="my-app",
        app_name="My App",
        required=["selection"],
        optional=["pointer_intent", "text_intent"],
    ) as stream:
        print(stream.negotiation.status, stream.negotiation.granted)
        async for item in stream:
            if isinstance(item, NegotiationUpdate):
                print("now granted:", item.negotiation.granted)
            elif isinstance(item, ServerNotice):
                print("server notice:", item.code)
            elif is_event(item):
                if item.event_type == "intent.selection":
                    print("select!", item.payload.confidence, item.provenance.kind)

asyncio.run(main())
```

`stream.stats` exposes `received`, `invalid`, `delivery_gaps` / `missed_events`
(server dropped events for you because you were too slow — the per-connection
`delivery_seq` skipped), and `out_of_order` (envelope `seq` not increasing within a
session; should always be 0).

Errors from the REST client raise `ConcordError(code, message, status)`; codes are
stable strings (`device_not_found`, `invalid_state`, `capability_unsupported`, …).

Runnable example: `python backend/examples/print_events.py --connect sim-a`.

## TypeScript

```ts
import { ConcordStream } from "./sdk";

const stream = new ConcordStream({
  app: { id: "my-app", name: "My App" },
  required: ["selection"],
  optional: ["pointer_intent"],
  // url defaults to ws(s)://<page host>/api/v1/stream
});
stream.on("negotiation", (n) => console.log("granted", n.granted));
stream.on("event", (e) => {
  if (e.event_type === "intent.pointer") console.log(e.payload.vx, e.payload.vy); // typed
});
stream.on("notice", (n) => console.warn(n.code, n.message));
stream.connect();
```

The client reconnects with backoff (250 ms → 4 s) after unexpected disconnects, but not
after a handshake rejection. `stream.stats` mirrors the Python stats.

The Communication Board (`frontend/src/apps/board/`) is the reference application: a pure
reducer (`model.ts`) plus a view that only consumes SDK events.

## Event envelope (schema 1.0)

See [ARCHITECTURE.md §4](../ARCHITECTURE.md#4-event-envelope-schema-14-1114-are-additive-over-10) and the JSON Schema
at `contracts/event-envelope.v1.schema.json` (also served at `/api/v1/schema/event`).

Note for JavaScript: `timestamp_ns` values exceed `Number.MAX_SAFE_INTEGER`; after
`JSON.parse` they are accurate to roughly ±256 ns, which is fine for display and
millisecond latency math but not for nanosecond arithmetic.

## Schema 1.1: recorded neural data (Milestone 2)

Request these capabilities to receive genuine recorded data from offline sources
(e.g. `nwb:` devices). Apps that don't request them never receive them.

| Capability | Event | Provenance | Payload |
| --- | --- | --- | --- |
| `neural_features` | `features.binned` | `processed_feature` | `counts[channel]` for the bin ending at `device_timestamp_ns`; `bin_ms`, `bin_index`, `feature` |
| `behavior` | `behavior.sample` | `behavioral_label` | recorded ground truth `values[dims]`, `valid` |
| `kinematic_intent` | `intent.kinematics` | `decoded_intent` + `model_id` (or `simulated_intent`) | `values[dims]` in `space` (e.g. `falcon_h1_7dof`) |

```python
async with await EventStream.connect(
    app_id="analysis", app_name="Analysis",
    optional=["neural_features", "behavior", "kinematic_intent"],
) as stream:
    async for ev in stream.events():
        if ev.event_type == "features.binned":
            print(ev.payload.bin_index, sum(ev.payload.counts), ev.provenance.origin)
```

REST: `GET /api/v1/devices/{id}/source` (dataset, license, SHA-256 verification, channels,
notes), `GET/POST /api/v1/runtime/playback` (position, duration, speed).

## Units and conventions

| Field | Convention |
| --- | --- |
| `intent.pointer` `vx`, `vy` | workspace units per second; workspace = unit square, x → right, y → down |
| `recording.frame` `samples` | `samples[channel][sample]`, microvolts |
| `timestamp_ns` | runtime wall clock at ingest (UTC, ns) |
| `device_timestamp_ns` | device clock, arbitrary epoch, monotonic per device unless flagged `timestamp_regression` |
| `quality.score` | adapter estimate in [0, 1]; 1 = nominal |

## Milestone 3: live sources, pipeline, commands (schema 1.2)

- New event type `features.vector` (`neural_features` capability): real-valued per-channel
  features, e.g. `log_band_power` with `band_hz`. `recording.frame.unit` may be `arbitrary`
  when the source did not declare convertible units — do not treat those values as µV.
- Device kind `stream`: an external LSL / Open Ephys stream whose origin Concord cannot
  verify. A stream that declares prerecorded content is `replay`; synthetic is `simulated`.
- `intent.pointer` with `decoded_intent` comes **only** from the operator-enabled command
  router, with the decoder's `model_id`. Apps that require `pointer_intent` are suspended
  while the router is off — raw or decoded neural data never becomes a command by itself.
- Reference app: `backend/examples/reference_app/cursor_app.py` (only `concord.sdk` + stdlib;
  a test enforces it). It runs unchanged against the simulator, LSL and Open Ephys sources.

## Milestone 4: authorized commands and the command guard (schema 1.3)

- **Decoded commands need the operator's authorization of your app id.** While the command
  router provides `pointer_intent` / `selection` / `text_intent` and the operator has not
  authorized your app for it, negotiation rejects it with `not_authorized` (your app is
  `suspended` if it is required). Show "waiting for operator authorization"; never try to
  authorize yourself. Simulated profiles' `simulated_intent` is not gated.
- `intent.selection.action` is `primary` (select), `activate` or `cancel`; `intent.text`
  carries the rule's text. Discrete actions come only from a classifier via operator rules.
- Use the **command guard** (Python `concord.sdk.CommandGuard` / `ControlChannel`, TS
  `CommandGuard` / `attachGuard` in `frontend/src/sdk/guard.ts`): it tells you which command
  capabilities are usable now (`is_active`, `waiting_for_authorization`), drops commands
  older than 500 ms (wall clock and relative delivery delay), reports zero pointer velocity
  after 500 ms without a pointer command (dead-man), and calls `on_stop(reason)` at once on
  revocation, command output stopped, suspension, pause, disconnect or stream close.
  Details, timeouts and examples: [CONTROL_BRIDGE.md](CONTROL_BRIDGE.md).
- Reference apps: `cursor_app.py` (continuous pointer) and `menu_app.py` (discrete
  select / activate / cancel + optional text), both SDK + stdlib only.

### Operator methods (Python `RuntimeClient`)

These configure acquisition and processing; applications should not need them.

| Method | Endpoint |
| --- | --- |
| `discover_lsl(wait_s)` | `POST /sources/lsl/discover` |
| `configure_lsl(signal, behavior=None, markers=None)` | `POST /sources/lsl` → `DeviceDescriptor` (`lsl:<key>`) |
| `configure_openephys(host=…, data_port=…, unit=…)` | `POST /sources/openephys` |
| `start_pipeline(preset, model_id=None, allow_cross_source=False, router=None, **params)` | `POST /pipeline/start` |
| `set_router(enabled=…, x_dim=…, y_dim=…, gain=…, deadzone=…, invert_y=…, max_speed=…)` | `POST /pipeline/router` |
| `pipeline()` / `stop_pipeline()` | `GET /pipeline` / `POST /pipeline/stop` |
| `models()` | `GET /models` (with compatibility against the running pipeline) |
| `start_recording(name, exclude_raw=False)` / `stop_recording()` | `POST /recordings/{start,stop}` |
| `calibrate(recordings, train_fraction=…, gap_bins=…, feature_source=…, kind="classifier", class_names=…)` | `POST /calibration/train` (`kind="classifier"`: LDA on a class-label behavior stream) |
| `set_router(enabled=…, discrete=[{output, action, threshold, hold_ms, refractory_ms, text?}], stall_ms=…)` | `POST /pipeline/router` (discrete actions from a classifier) |
| `control()` / `authorize_app(app_id, caps)` / `revoke_app(app_id, caps=None)` / `stop_control(reason=None)` | `GET /control`, `POST /control/apps/{id}/authorize`, `…/revoke`, `POST /control/stop` |
| `negotiate(required, optional, app_id=…)` | `POST /negotiate` dry run as an app id |

Errors raise `ConcordError(code, message, status)`; e.g. `incompatible_decoder` (409) with the
reasons (channel count, bin, feature, training session, source).


## Milestone 5: application layer (schema 1.4)

- New capabilities: `navigation` (`intent.navigate {direction, confidence}`, a command:
  decoded navigation needs the operator's authorization) and `control_status`
  (`control.state {active, capabilities, reason}`, a runtime notice to your app only). Ask
  for `control_status` and show its reason; enter a safe state on `active: false`.
- `CommandGuard` (Python and TS) treats `navigation` as a command capability; when
  `control_status` is granted, a command capability is usable only while the latest
  `control.state` of this session lists it as active (`state()` returns `control_inactive`
  otherwise), and `on_stop` fires with the runtime's reason on `active: false`. TS:
  `onControlState`, `guard.controlState`; Python: `guard.control_state`; control.state events
  pass through `handle()` / `ControlChannel` / `attachGuard` (TS feeds them to the guard).
- Decoded commands may carry `provenance.model_origin` (`concord` / `external` /
  `historical`); show it (historical = recorded outputs of a research system's original
  decoder, always replayed).
- Operator API additions: discrete rule actions `navigate:<direction>`, `click` and
  `pointer_scale` in `set_router(...)` / `start_pipeline(router=...)`; `/control` apps carry
  `control_active` / `control_reason`; authorize/revoke accept up to four command capabilities.
- Applications, input methods, safe-state rules, the board's evaluation snapshot
  (`window.__concordBoard`): [APPLICATIONS.md](APPLICATIONS.md). The opt-in desktop control
  bridge: `backend/examples/desktop_bridge/`
  ([SAFETY.md](../backend/examples/desktop_bridge/SAFETY.md)).
- Test helper: `concord.testing.scripted` — a declared-synthetic scripted feature source and a
  hand-written identity *test* decoder for deterministic decoded cursor + click tests
  (`python -m concord.testing.scripted serve --port P --data-dir D --click-at X,Y ...`).
