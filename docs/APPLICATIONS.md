# Applications (Milestone 5, workstream C)

How applications use Concord: the capability contract they program against (schema 1.4), the
input methods of the communication board and when each is available, the safe-state rules,
and how to write an application. Research software: nothing here has been used with a
participant (LIMITATIONS.md, docs/VALIDATION_LEVELS.md).

## 1. Three applications, one contract

| App | Kind | Code | Asks for |
| --- | --- | --- | --- |
| Reference cursor | continuous pointer (center-out task) | `backend/examples/reference_app/cursor_app.py` | requires `pointer_intent`; optional `control_status` |
| Reference menu | discrete menu / speller | `backend/examples/reference_app/menu_app.py` | requires `selection`; optional `text_intent`, `navigation`, `control_status` |
| Communication board | text communication | `frontend/src/apps/board/` (`/board.html`) | nothing required; optional `pointer_intent`, `selection`, `navigation`, `text_intent`, `control_status` |

All three import only the public SDK (Python `concord.sdk` + stdlib; TS `frontend/src/sdk`),
contain no device ids, never call the operator API, and act on commands only through the SDK
`CommandGuard` — enforced by `backend/tests/test_reference_app.py` and
`frontend/src/apps/board/boundary.test.ts`. The opt-in desktop control bridge
(`backend/examples/desktop_bridge/`, [SAFETY.md](../backend/examples/desktop_bridge/SAFETY.md))
is a separate process, not one of these apps.

## 2. Capability contract for apps (schema 1.4)

| Capability | Event | Payload | Command? |
| --- | --- | --- | --- |
| `pointer_intent` | `intent.pointer` | `vx`, `vy` (workspace units / s) | yes |
| `selection` | `intent.selection` | `action`: `primary` (select) / `activate` / `cancel`, `confidence` | yes |
| `text_intent` | `intent.text` | `text`, `mode` (`character` / `word`), `confidence` | yes |
| `navigation` (1.4) | `intent.navigate` | `direction`: `up` / `down` / `left` / `right` / `next` / `previous`, `confidence` | yes |
| `control_status` (1.4) | `control.state` | `active` (strict bool), `capabilities` (command capabilities now delivered to this app), `reason` | no — a runtime notice to one app |

- **Commands** with provenance `decoded_intent` come only from the operator-enabled command
  router and reach an app only after the operator authorized that app id for that capability
  (default deny; [CONTROL_BRIDGE.md](CONTROL_BRIDGE.md)). `simulated_intent` from Simulated
  Profiles is not gated. Raw signals, features and behavior labels never become commands.
- **`provenance.model_origin`** (1.4) on decoded commands: `concord` (a model Concord trained
  or loaded), `external` (a live external decoder), `historical` (recorded outputs of a
  research system's original decoder; always `replayed`). The router copies it from the
  decoder output to every command. Pipeline decoder output without an origin is Concord's.
- **`control_status`** is provided by the runtime whenever a device is connected (granted in
  negotiation like any capability). See §4.

## 3. Communication board v2

### 3.1 Input methods and when each is available

Availability comes only from negotiation; the automatic choice is the first available in
this order, and the operator / caregiver can override it in the board's settings (an
unavailable method cannot be chosen; an override that becomes unavailable falls back to auto).

| Method | Available when granted | Behaviour |
| --- | --- | --- |
| Pointer and click | `pointer_intent` + `selection` | the cursor follows `intent.pointer`; `primary` / `activate` chooses the tile under the cursor; `cancel` undoes |
| Pointer with dwell selection | `pointer_intent` | resting on a tile for the dwell time chooses it. A board interaction, labelled "dwell selection", never presented as a neural click. Arms only after the cursor moved since input became active; leaving the tile cancels; staying does not repeat |
| Directional navigation | `navigation` | `up/down/left/right` move the highlight in the grid (stop at edges), `next/previous` move linearly (wrap); `primary`/`activate` choose, `cancel` undoes. Without `selection`: resting on the highlighted tile for the dwell time chooses it |
| Direct selection | `selection` (auto: only after the source sent an `activate` or `cancel`) | `primary` moves the highlight to the next tile, `activate` chooses, `cancel` undoes |
| Scanning | `selection` | the board highlights tiles in turn (interval setting), tile by tile or row then column; any `primary` / `activate` is the switch; in row/column scanning `cancel` returns from the row to row scanning |

`text_intent`, when granted and usable, is appended directly in every method (characters as
they come, words separated like phrases). With none of the above the board says "Waiting".

### 3.2 Pointer integration and geometry (stable; used by evaluation harnesses)

- Workspace: the unit square, x to the right, **y down**, origin at the top-left. The current
  page's `cols × rows` tiles fill it; **tile index = row × cols + col**. The cursor starts at
  (0.5, 0.5) and is clamped to [0, 1]².
- Integration: `x += vx · dt`, `y += vy · dt`, with `dt` the difference of consecutive pointer
  events' `device_timestamp_ns` (fallback: `timestamp_ns` when the event has none), clamped
  to [0, 0.1] s. The first pointer event after the board (re)starts only sets the clock. A
  replay at 4× or 8× therefore reproduces the 1× trajectory. Gain, dead-zone, axis inversion
  and clamping belong to the command router (operator); the board applies none.
- Layouts: *phrases* (3×3, 4×4 or 5×5 targets: phrases, then Letters, Delete word, Undo,
  Clear, Speak/Save), *letters* (6×6: three word predictions, Space, Delete, Phrases, A–Z, ".",
  Undo, Clear, Speak/Save), and the **task grid**: N×N word tiles (N = 2…20, default 14) over a
  square workspace, labelled from a word list (one word or phrase per line, `#` comments; the
  built-in list is 200 common words). For a research task whose targets are an N×N grid in a
  square of side S centred at the origin with +y up (e.g. the T15 grid task: N = 14,
  S = 0.92 screen heights), set the router to `pointer_scale: "native"`, `gain = 1 / S`,
  `invert_y: true`; a click then lands on tile (row, col) exactly when the original cursor was
  inside task cell (row, col), up to the first bin and clamping.

### 3.3 Settings (all with operational effect)

Board settings panel (for the caregiver / experimenter; the participant view needs no input)
or URL parameters (they override this browser's saved settings):

| URL parameter | Setting | Range / default |
| --- | --- | --- |
| `method` | input method | `auto` (default), `cursor_click`, `cursor_dwell`, `navigate`, `direct`, `scan` |
| `layout`, `n`, `words` | layout, task-grid N, word-list URL | `communication` / `grid`; 2–20 (14); any URL the page can fetch |
| `tile_size`, `text_scale` | phrase-page targets, text size | `large` / `standard` / `small`; 0.75–2 |
| `dwell_ms` | dwell time | 300–5000 ms (1000) |
| `scan_interval_ms`, `scan_pattern` | scanning | 400–5000 ms (1100); `linear` / `row_column` |
| `click_refractory_ms` | board-side click / switch debounce, on the event clock (device timestamps): one click selects once at any replay speed | 0–3000 ms (300) |
| `confirm`, `confirm_ms` | `repeat`: the same tile must be selected twice | `none` / `repeat`; 1000–10000 ms |
| `audio_tick` | short tick on every selection | 0 / 1 |
| `speech`, `speech_rate` | conventional text-to-speech (Web Speech API) of the message on Speak, labelled **"computer speech (not neural speech decoding)"**; the tile says Save when off or unavailable | 0 / 1; 0.5–2 |

Not offered, on purpose: cursor gain or smoothing (the router's job).

### 3.4 Text, feedback, provenance

- Text: phrase tiles, letters with three word predictions, Space, Delete (character / word),
  Undo (up to 50 steps, including Clear and text intents), Clear, Speak/Save → communication
  history (last 50, with where the input came from).
- Feedback: the chosen tile flashes (static in reduced motion), an `aria-live` announcement,
  optional audio tick, dwell progress bar, a dashed outline for a selection awaiting
  confirmation. High contrast (`prefers-contrast: more`) and reduced motion are respected.
- Input provenance is shown plainly: "simulated input", "decoded by <model> (Concord)",
  "decoded by <model> (external decoder)", "historical decoder replay (original research
  system)", plus "recorded data replay" / "synthetic data".
- **Scientific limitation in the UI:** text composed from replayed recordings (`replayed`, or
  `model_origin: historical`) is labelled **"demonstration — not the participant's message"**:
  the person recorded did a different task (e.g. a cursor task), so the text is never theirs.
  Simulated or synthetic input is labelled "simulated input — no participant".

### 3.5 Evaluation snapshot (`window.__concordBoard`, version 1)

A read-only getter returning a fresh copy of the board state on every read; writing to it
changes nothing (tested). It is not a control path: the board is driven only by runtime
events. Fields: `version`, `connection`, `status`, `granted`, `usable`,
`waitingForAuthorization`, `method`, `methodLabel`, `active`, `stopReason`, `control` (latest
control.state), `layout {kind, page, cols, rows, tiles[], geometry}`, `cursor {x, y}`,
`highlighted`, `pending`, `text`, `textLabel`, `input {label, qualifiers}`, `selections[]`
(`n, page, tile, label, via` = click/dwell/scan/navigate/direct, `atMs` (page clock),
`cursor`, `event {seq, sessionId, timestampNs, deviceTimestampNs, eventType, input}`),
`history[]`, `counters` (selections, debounced, pendingConfirmations, ignoredInactive,
texts), `guard` (SDK guard stats), `settings`. The last 5000 selections are kept.

## 4. Safe-state rules

1. **Declare, then wait.** Ask for capabilities; never call the operator API; show "waiting
   for operator authorization" while `waiting_for_authorization` is non-empty.
2. **Gate every command through the SDK `CommandGuard`.** It acts only while the capability is
   granted, the source is `streaming`, the stream is open and — when `control_status` is
   granted — the runtime's latest `control.state` for this session lists the capability as
   active. It drops commands older than 500 ms, zeroes pointer velocity 500 ms after the last
   pointer command, and calls `on_stop(reason)` at once on any loss.
3. **`control.state` is the explicit safe-state signal.** The runtime sends it to each app
   that asked for `control_status`: at the start of each session, when the app connects, and
   whenever the set of command capabilities that can reach the app changes (router on/off,
   operator Stop, authorize/revoke, input stall, pause/resume, link loss/reconnect, source
   switch/disconnect/error/end, suspension), with the triggering reason (e.g.
   `command output stopped: input stalled: no decoder input for 1004 ms (limit 1000)`,
   `authorization revoked by operator (navigation)`, `source paused by operator`). It is
   enqueued in the same synchronous step as the change, after queued decoded commands were
   withdrawn, so **no command follows an `active: false` notice** until an `active: true` one;
   it is never dropped on queue overflow. Negotiation changes (a control message, delivered
   ahead of queued events) usually reach the app first; either stops the guard.
4. **On a stop, enter a safe state immediately**: the board freezes the cursor (shown dashed),
   cancels dwell progress, pending confirmations and a picked scan row, and stops scanning;
   after a resume the first pointer event only sets the clock and dwell needs movement again.
   Measured end to end (Playwright, real server): both boards paused within the 2 s check
   after the operator's Stop and made no selection and no cursor motion in the next 2.5 s
   (`reports/e2e.json`, step M5-C-3); over the WebSocket the inactive notice arrived within
   1 s of the Stop request and nothing after it (`backend/tests/test_apps_e2e.py`).
5. **Never act on raw signals, features or labels**, and never attribute composed text to a
   participant whose recording came from another task.

## 5. Writing an application

```ts
import { ConcordStream, CommandGuard, attachGuard } from "../../sdk";

const stream = new ConcordStream({
  app: { id: "my-app", name: "My app" },
  required: [],
  optional: ["pointer_intent", "selection", "navigation", "control_status"],
});
const guard = new CommandGuard({
  capabilities: ["pointer_intent", "selection", "navigation"],
  onStop: (why) => enterSafeState(why),          // freeze, cancel anything pending
  onControlState: (c) => showStatus(c.active, c.reason),
});
attachGuard(stream, guard, (e) => {               // fresh, usable commands only
  if (e.event_type === "intent.navigate") moveHighlight(e.payload.direction);
  if (e.event_type === "intent.selection") choose(e.payload.action);
});
stream.connect();
```

```python
from concord.sdk import CommandGuard, ControlChannel, EventStream, is_event

guard = CommandGuard(["selection", "navigation"], on_stop=lambda why: safe_state(why))
async with await EventStream.connect(app_id="my-menu", app_name="My menu",
                                     optional=["selection", "navigation", "control_status"]) as s:
    async for item in ControlChannel(s, guard):
        if is_event(item) and item.event_type.value == "control.state":
            show(item.payload.active, item.payload.reason)
        elif is_event(item) and item.event_type.value == "intent.navigate":
            move(item.payload.direction)
```

Adapt to what is granted (the same app must work with simulated intents, decoded commands, or
nothing), show provenance (§3.4), and keep device ids out of the code.

## 6. Tests

- Board (vitest): `model.test.ts` — every input method (click on the tile under the cursor;
  dwell selects after the dwell time, cancels on leave, needs movement; linear and row/column
  scanning; navigation; direct selection), device-clock integration at 1× vs 8×, debounce,
  undo/history/prediction, Speak/Save, safe stop (dwell, confirmation, scan row), provenance
  and demonstration labels, task-grid geometry, settings parsing; `Board.test.tsx` — the real
  SDK client + guard over a mock socket: nothing acts before `control.state` active, stop
  freezes the cursor with the runtime's reason, labels, computer-speech label and call,
  snapshot is a copy; `boundary.test.ts` — SDK-only, no operator REST, guard required.
- Runtime / SDK (pytest): `test_control_state.py`, `test_sdk_guard.py`,
  `test_reference_app.py`, `test_apps_e2e.py`, `test_desktop_bridge.py`; vitest
  `guard.test.ts`.
- Browser (Playwright, `make e2e`, section M5-C): a second server with the scripted decoder
  test source + identity test decoder; two participant boards (click, dwell) select "Hello"
  then "Water" from authorized decoded commands only, compose "Hello Water", show "decoded by
  test-scripted-identity (Concord)" and "simulated input — no participant"; operator Stop,
  re-enable and revoke behave as in §4.
