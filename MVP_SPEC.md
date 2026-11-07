# BrainOS — MVP Specification

Scope: the first vertical slice. Every requirement has an acceptance test ID;
`AT-*` IDs appear in test docstrings so coverage is greppable
(`grep -rn "AT-" backend/tests frontend/src e2e`).

## Functional requirements

| ID | Requirement |
| --- | --- |
| FR-1 | Device-adapter contract separates device-native packets from application events (`read()` vs `normalize()`), with no write path. |
| FR-2 | Capability registry with the six v1 capabilities; unsupported capabilities are explicitly rejected; unknown capability names are protocol errors. |
| FR-3 | Two simulated profiles (A, B) with different capabilities, rates, and native wire formats. Labelled synthetic everywhere. |
| FR-4 | Versioned, validated event envelope with schema version, device ID, timestamps, seq, type, capability, payload, quality, provenance. |
| FR-5 | Runtime: connect, disconnect, switch, stream, pause/resume, reconnect on link error, error state, diagnostics. |
| FR-6 | Python SDK with docs and a runnable example. |
| FR-7 | React console: runtime state, devices & capabilities, live events, signal view, telemetry, diagnostics, connected apps, test results. |
| FR-8 | Interactive communication board controlled only via the runtime API. |
| FR-9 | Device switch A→B keeps the board working with no code change (adapts via negotiation). |
| FR-10 | Record a live session and replay it through the same pipeline, marked `replayed`. |
| FR-11 | Provenance kinds enforced by the schema (raw / label / simulated / decoded). |
| FR-12 | Read-only: no endpoint, SDK call, or adapter method writes to a device. |

## Acceptance tests

### Contracts
- **AT-1** Valid envelopes of every event type round-trip through JSON.
- **AT-2** Malformed envelopes are rejected: wrong schema major, unknown event
  type, payload/type mismatch, capability/type mismatch, NaN/Inf, negative
  seq, recording shape mismatch, missing fields.
- **AT-3** Provenance rules: label-as-intent rejected; `decoded_intent`
  without `model_id` rejected; `simulated_intent` with `synthetic=false`
  rejected; raw signal only on `recording.frame`.
- **AT-4** Committed JSON Schema equals the schema generated from the models.

### Adapters
- **AT-5** Profile A binary frames decode; corrupt magic/length/CRC raise
  `PacketDecodeError`.
- **AT-6** Profile B JSON lines decode; malformed lines raise
  `PacketDecodeError`.
- **AT-7** Each profile emits only declared capabilities at approximately
  its declared rates (measured over a real interval, ±30%).
- **AT-8** `DeviceAdapter` exposes no write/send/stimulate method.

### Runtime
- **AT-9** connect → streaming; events stamped with session, strictly
  increasing seq.
- **AT-10** pause stops delivery; resume restarts it.
- **AT-11** Recoverable link drop → `reconnecting` → `streaming`, same session,
  seq still increasing; status events emitted.
- **AT-12** Unrecoverable link failure → `error` state with last error.
- **AT-13** Malformed packets and undeclared capabilities are dropped and
  counted; stream continues.
- **AT-14** Switch A→B: new session, re-negotiation pushed to subscribers,
  switch duration recorded.
- **AT-15** Subscriber receives only granted capabilities; required-but-
  unsupported → `suspended`, no events.
- **AT-16** Slow subscriber overflow drops oldest and counts drops; other
  subscribers unaffected.
- **AT-17** Record + replay: replayed events keep provenance kind, have
  `replayed=true`, and preserve order.

### Server / SDK
- **AT-18** REST endpoints: devices, connect, switch, pause/resume,
  disconnect, diagnostics, negotiate (dry run), schema.
- **AT-19** WebSocket: hello required first; unknown capability → error +
  close; non-hello client messages → `read_only_runtime`.
- **AT-20** Python SDK end-to-end against a live server: negotiates, receives
  ordered events, reports delivery gaps, survives a device switch.
- **AT-21** Sim endpoints reject intents a profile does not support (409
  `capability_unsupported`).

### Frontend
- **AT-22** Board model: pointer integration, hit-testing, selection, scan
  mode, text intent, mode change on negotiation.
- **AT-23** Board imports nothing outside `src/sdk` (device-agnostic
  boundary).
- **AT-24** TS SDK validates envelopes and detects delivery gaps.
- **AT-25** End-to-end demo script (Playwright) performs the full demo
  sequence in a real browser against a real server.

## Demo sequence (≈5 minutes)

1. `make setup && make run` → open http://127.0.0.1:8000.
2. Console shows runtime `idle`, two simulated profiles with a capability
   matrix, and the board app listed as a connected app (status `no_device`).
3. Connect **Profile A**. Live event stream, 32-channel synthetic signal
   view, telemetry, and rates appear. Board switches to *pointer mode*.
4. Drag in the *Simulated intention source* pad (or arrow keys) — the board
   cursor moves. Press **Select** (or Space) — the hovered phrase is added to
   the message.
5. Show an `intent.pointer` event: `provenance.kind = simulated_intent`.
6. Inject a `link_drop` fault → `reconnecting` → `streaming`; diagnostics
   show the reconnect.
7. **Switch to Profile B.** Board receives a new negotiation (no
   `pointer_intent`, has `text_intent`) and switches to *scan mode*; Select
   picks the highlighted tile; text typed in the intention source appears via
   `intent.text`. Board code unchanged.
8. Record 10 s, then connect the recording as a replay device; events show
   `replayed`.
9. Open **Diagnostics** (measured rates, pipeline latency percentiles, drops,
   errors) and **Tests** (latest pytest and vitest results).

## Performance measurement

Only measured numbers are reported. `make bench` runs `scripts/bench.py`
which measures, against a live server, event throughput and
runtime-ingest → SDK-receive latency, and prints machine info. Results are
recorded in `docs/BENCHMARKS.md` with the machine they were measured on.

## Known limitations

Maintained in [LIMITATIONS.md](LIMITATIONS.md).
