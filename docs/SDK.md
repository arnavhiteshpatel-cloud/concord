# BrainOS SDK guide

Two SDKs speak the same protocol (`brainos.stream/1`) and the same envelope (schema `1.0`):

- **Python** — `brainos.sdk` (async; `httpx` + `websockets`). Installed by `make setup`.
- **TypeScript** — `frontend/src/sdk` (browser `WebSocket` + `fetch`, zero dependencies).

Both validate every incoming envelope against the contract (including provenance rules)
and never hand an application an event that violates it.

## Core ideas

1. **Declare capabilities, don't assume devices.** In `hello`, list `required` and
   `optional` capabilities from the closed vocabulary: `recording`, `pointer_intent`,
   `selection`, `text_intent`, `telemetry`, `device_status`.
2. **Negotiation is explicit.** Each request is `granted` or `rejected` with a reason
   (`unsupported_by_device`, `no_device`). Unknown names are a hard error
   (`unknown_capability`). If a required capability is missing, your app is
   `suspended` and receives no events.
3. **Renegotiation happens.** When the operator connects, switches, or loses a device,
   you receive a new negotiation. Adapt to `granted` — that is how one app runs on
   devices with different capabilities.
4. **Check provenance.** `provenance.kind` tells you whether an event is a raw signal,
   a behavioral label, a *simulated* intent, or a *model-decoded* intent. In v1 every
   intent is `simulated_intent`.
5. **Read-only.** There is no API to send anything to a device. Any client message
   other than `ping` gets `read_only_runtime`.

## Python

```python
import asyncio
from brainos.sdk import (
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

Errors from the REST client raise `BrainOSError(code, message, status)`; codes are
stable strings (`device_not_found`, `invalid_state`, `capability_unsupported`, …).

Runnable example: `python backend/examples/print_events.py --connect sim-a`.

## TypeScript

```ts
import { BrainOSStream } from "./sdk";

const stream = new BrainOSStream({
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

See [ARCHITECTURE.md §4](../ARCHITECTURE.md#4-event-envelope-schema-10) and the JSON Schema
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
