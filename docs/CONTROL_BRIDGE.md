# Control bridge (Milestone 4, workstream C)

How decoded brain-signal output becomes a command an application may act on — and every way
that path is closed. BrainOS is a read-only research runtime: nothing here sends anything to
a device, and nothing here has been used with a participant (see LIMITATIONS.md).

```
 decoder output (intent.kinematics, decoded_intent + model_id)
        │  only this is accepted (provenance asserted; anything else raises)
        ▼
 command router (operator-enabled, explicit mapping)            ── off on every stop path
        │  intent.pointer / intent.selection / intent.text (decoded_intent + model_id)
        ▼
 negotiation: not_authorized unless the operator authorized the app id for that capability
 bus:         decoded commands never delivered to an unauthorized subscriber (defense in depth)
        ▼
 application + SDK CommandGuard: acts only while usable; drops stale; dead-man; stop callback
```

## 1. Authorization model (default deny)

- A **decoded command** is an `intent.pointer`, `intent.selection` or `intent.text` event with
  provenance `decoded_intent`. Only the command router produces them, only from the running
  decoder's output.
- It reaches an application only if the operator has **authorized that application id for
  that capability** (`pointer_intent`, `selection`, `text_intent`). Nothing else needs
  authorization (features, decoded kinematics, labels, status …).
- **Negotiation**: while the router provides a command capability and the app is not
  authorized for it, the capability is rejected with reason `not_authorized` (schema 1.3). If
  the app requires it, the app is `suspended`. A capability the router does not provide at
  all is `unsupported_by_device`, as before.
- **Bus (defense in depth)**: even if negotiation granted the capability (e.g. the source
  also provides it natively), the bus does not deliver a decoded command to a subscriber
  whose app id is not authorized for it (counted as `refused_commands`).
- **Revocation and stop take effect before the REST call returns**: authorization is
  removed, the app is renegotiated (it receives a `negotiation` message with
  `not_authorized`), and decoded commands still waiting in its send queue are withdrawn
  (the queue is renumbered so `delivery_seq` stays contiguous — no stale command is sent).
- **Lifetime**: authorizations live in memory only. They are empty after every runtime start,
  survive source switches and reconnects (they belong to the app id, not the source), and
  change only through the operator API below. The router, in contrast, is **always off
  after any source change**.
- **Simulated profiles are not gated.** Simulated Profile A/B emit `simulated_intent`
  natively (from the operator's simulator controls), not decoded commands; they negotiate as
  before so the existing demos and the communication board keep working. Authorization
  applies to `decoded_intent` only.
- The operator console is an ordinary subscriber here: it does not receive decoded commands
  unless authorized (it shows decoded output as `intent.kinematics`).
- Application ids are self-declared by clients. On a localhost-only research runtime this
  protects against mistakes (an app receiving commands nobody meant for it), not against a
  malicious local process (LIMITATIONS.md).

### REST (operator only; applications never call these)

| Endpoint | Effect |
| --- | --- |
| `GET /api/v1/control` | router state (`router_on`, `model_id`, `provides`, `router`, `stall_limit_ms`, `last_stop`), every app id that asks for command capabilities (`requested`, `required`, `authorized`, `receiving`, `waiting` with reasons, `connections`, `refused_commands`) and authorized-but-offline app ids, plus a history of authorizations and router on/off with reasons |
| `POST /api/v1/control/apps/{app_id}/authorize` `{"capabilities": ["selection", …]}` | adds the authorization; only command capabilities (400 otherwise, 422 for unknown names) |
| `POST /api/v1/control/apps/{app_id}/revoke` `{"capabilities": [...]}` (body optional = all) | removes it; immediate renegotiation + queued commands withdrawn |
| `POST /api/v1/control/stop` `{"reason": "..."}` (body optional) | router off now, reason recorded, queued decoded commands withdrawn; idempotent |
| `POST /api/v1/negotiate` `{"required": [...], "app_id": "..."}` | dry run as that app id (shows `not_authorized`) |

Python operator methods: `RuntimeClient.control()`, `authorize_app(app_id, caps)`,
`revoke_app(app_id, caps=None)`, `stop_control(reason=None)`, `negotiate(..., app_id=...)`.

## 2. Standardized action set

| Action | Event (capability) | Payload | Produced from |
| --- | --- | --- | --- |
| continuous 2-D movement | `intent.pointer` (`pointer_intent`) | `vx`, `vy` (workspace/s) | two dimensions of a **continuous** decoder (ridge): value / training-behavior std, dead-zone, × gain, clamp ±max speed, optional y inversion |
| select | `intent.selection` (`selection`) | `action: "primary"`, `confidence` | a **classifier** class posterior, by a discrete rule |
| activate | `intent.selection` | `action: "activate"`, `confidence` | idem |
| cancel | `intent.selection` | `action: "cancel"`, `confidence` | idem |
| text | `intent.text` (`text_intent`) | `text` (rule's text), `mode` (`character` if 1 char else `word`), `confidence` | idem |
| navigate (1.4) | `intent.navigate` (`navigation`) | `direction` (`up`/`down`/`left`/`right`/`next`/`previous`), `confidence` | a classifier class posterior, by a discrete rule with action `navigate:<direction>` |
| click (1.4 router feature) | `intent.selection` | `action: "primary"` (or `activate`), `confidence` | one decoder output that is a click probability or a 0/1 decision (§7) |

`confidence` is the class posterior at the moment the rule fired. All carry provenance
`decoded_intent`, the model id, and the source's `synthetic` / `replayed` flags.

The router (`runtime/router.py`) accepts nothing but the running decoder's output draft:
`intent.kinematics` + `decoded_intent` + that model's id. A `behavior.sample`,
`recording.frame`, `features.*`, simulated intent or another model's output raises
`CommandProvenanceError` (tested). Raw-only sources and label-only sources therefore never
yield commands, whatever the operator configures (tested end to end).

**Capabilities are advertised only for what is configured**: `pointer_intent` only with a
pointer mapping on a continuous decoder; `selection` only with at least one
select/activate/cancel rule (params list the `actions`); `text_intent` only with a text rule
(params `text_modes`). Refusals: a pointer mapping on a classifier or discrete rules on a
continuous decoder → 409 `incompatible_decoder`; a rule on a class the decoder does not have
→ 409 `incompatible_decoder`; an enabled router with nothing to emit → 409
`capability_unsupported`; a router without a decoder → 400; malformed rules → 422.

## 3. Discrete decoding

### LDA classifier (`decoding/lda.py`)

Per feature bin: optional causal exponential smoothing (`tau_ms`, default 500 ms; kernel
length `tau / bin`), z-score with training statistics, linear discriminant analysis with a
shared covariance shrunk towards `mu·I` by the closed-form **Ledoit-Wolf** intensity (same
estimator as scikit-learn's, tested against the formula), class priors from training
frequencies, softmax posteriors. Streaming output equals offline output bin for bin
(tested). numpy only; the model is JSON `brainos.model/1` with `kind: "lda"`, `input`
(event type, feature, bin, channel count and labels), `source.identity`, `training`
(recordings + SHA-256, sessions, class counts), `evaluations` and
`outputs: {"type": "classes", "classes": [...]}`. The same compatibility checks as for ridge
models apply (input spec, source identity / cross-source override, training-session leakage).

In the pipeline the posteriors are emitted as **`intent.kinematics`** with
`quantity: "class_posterior"`, `dims` = class names, `unit: "probability"`, `decoded_intent` +
`model_id`. No contract change was needed: `intent.kinematics` is already "decoder output in a
decoder-defined space", and it is not a command capability.

### Calibration from recordings

`calibrate_classifier()` (`POST /calibration/train` with `"kind": "classifier"`, CLI
`python -m brainos.decoding.calibrate --classes`) uses recordings whose behavior stream
carries a class label per sample (e.g. `cue_class` 0/1/2). Alignment, chronological split at
a trial marker after `train_fraction`, then `gap_bins`, then held-out scoring — exactly as
for ridge. Labels must be small non-negative integers; class names come from the request
(`class_names[i]` names value `i`), else from the source's `behavior` capability parameter
`class_names`, else `class_<i>`. Only training bins are used for every statistic. The report
gives accuracy, **balanced accuracy**, per-class accuracy (recall), the **confusion matrix**,
**chance levels** (1/k balanced, majority-class rate) and a circular **time-shift control**
(20 shifts), plus `beats_all_shifts`. A Markdown report is written to `reports/calibration/`.

### Discrete rules (hysteresis)

`{output, action, threshold=0.8, release=threshold−0.15, hold_ms=300, refractory_ms=1000, text?}`;
one rule per class. A rule fires when the class posterior is ≥ `threshold` continuously for
`hold_ms` (on the source's device clock; the runtime's monotonic clock if the source has
none) and at least `refractory_ms` after its previous firing. After firing it is disarmed
until the posterior falls below `release` — so a posterior hovering around the threshold
fires once, not repeatedly (tested). Rule state resets whenever the router is (re)configured.

### Result on the synthetic test source (SYNTHETIC data — not human, not hardware)

`backend/tests/mi_source.py` generates scalp-EEG-like data (8 channels around C3/Cz/C4,
250 Hz) with cues rest/left/right (3 s each) and a contralateral mu-band (8–13 Hz) amplitude
decrease during imagery, put there on purpose. Recorded through the runtime (band power
8–13 Hz, 200 ms bins, pipeline features) for 300 s of data and calibrated with the defaults
(`test_classifier_calibrated_from_a_recording_runs_in_the_pipeline`, seed 21):

| | |
| --- | --- |
| bins | 1500 (all labelled): train 1214, gap 12, held-out 274 (271 scored) |
| held-out balanced accuracy | **0.659** (chance 0.333) |
| accuracy | 0.649 (majority-class rate 0.387) |
| per class | rest 0.67 · left 0.80 · right 0.50 |
| time-shift control | 0.313 mean, 0.504 max over 20 shifts |
| Ledoit-Wolf shrinkage | 0.098 |

Confusion (rows true, columns predicted; rest/left/right): `[[51, 18, 7], [11, 72, 7], [36, 16, 53]]`.

This only shows that the implementation recovers a structure that was deliberately put into
synthetic data. It says nothing about decoding motor imagery from a person.

## 4. Stale-command prevention

### Server side — command output (the router) turns off

| Trigger | Recorded reason |
| --- | --- |
| operator Stop (`POST /control/stop`, the console's title-bar Stop control) | the given reason, default `stopped by operator` |
| operator disables the router (`POST /pipeline/router` with `enabled: false`) | `disabled by operator` |
| source paused | `source paused` |
| source link lost (reconnecting) | `source link lost` |
| pipeline stopped, restarted, decoder changed (any `POST /pipeline/start`) | `stopped by operator` / `pipeline restarted` |
| source switched or disconnected | `device disconnected (…)` |
| source error / end of a finite source | `runtime error: …` / `source ended` |
| **decoder input stall**: no decoder input for longer than `max(stall_ms, 3 × bin)` | `input stalled: no decoder input for N ms (limit L)` |

- `stall_ms` is a router setting (default **1000 ms**, 100–10000). The watchdog is armed by
  the first decoder input after the router is enabled (before that nothing was emitted) and
  is checked after every input and every **50 ms** while the queue is empty. With 200 ms bins
  the limit is 1000 ms; with 20 ms bins, 1000 ms.
- A (re)start never inherits the previous router state: the router is on after a start only
  if that start request itself enables it.
- When the router turns off for any reason, decoded commands already queued for any
  subscriber are withdrawn and the router's capabilities disappear, so apps are renegotiated
  in the same step. No command is emitted after a stop: the router check and event emission
  run synchronously on the runtime's event loop (tested for every trigger above).

### SDK side — `CommandGuard`

| Behaviour | Default |
| --- | --- |
| act only while the capability is granted, the source is `streaming` and the stream is open | — |
| drop a command older than `max_age_ms` by its runtime `timestamp_ns` vs the local wall clock (`compare_wall_clock`, turn off when the runtime is on another machine) | **500 ms** |
| drop a command delivered more than `max_age_ms` later than the fastest delivery seen this session (arrival − timestamp; no clock agreement needed; catches bursts after a stall) | **500 ms** |
| dead-man: no pointer command for `deadman_ms` ⇒ reported velocity is zero (`on_deadman` once per idle period) | **500 ms** |
| `on_stop(reason)` immediately when a usable capability stops being usable: `authorization revoked`, `command output stopped`, `source disconnected`, `application suspended`, `source paused` / `source <state>`, `stream closed` (TS also `connection lost`) | — |

## 5. Writing an application that acts on commands

1. Declare what you need: `required=["selection"]`, `optional=["text_intent"]` (or
   `pointer_intent`). Never ask the operator API for anything.
2. Feed every stream item through a guard and act only on what it returns:

```python
from brainos.sdk import CommandGuard, EventStream

guard = CommandGuard(["selection", "text_intent"], on_stop=lambda why: print("stopped:", why))
async with await EventStream.connect(app_id="my-menu", app_name="My menu",
                                     required=["selection"], optional=["text_intent"]) as stream:
    # (start a task that calls guard.tick() every ~20-50 ms if you use pointer_intent)
    async for item in stream:
        env = guard.handle(item)            # None: control item, or a command not to act on
        if guard.waiting_for_authorization:
            show("waiting for the operator to authorize this app")
        if env is not None and env.event_type == "intent.selection":
            act(env.payload.action, env.payload.confidence)
```

`ControlChannel(stream, guard)` does the same and runs the dead-man timer for you
(`async for item in ControlChannel(stream, guard)`).

```ts
import { BrainOSStream, CommandGuard, attachGuard } from "./sdk";

const stream = new BrainOSStream({ app: { id: "my-cursor", name: "My cursor" }, required: ["pointer_intent"] });
const guard = new CommandGuard({ capabilities: ["pointer_intent"], onStop: (why) => showStopped(why) });
const detach = attachGuard(stream, guard, (e) => { /* fresh, usable commands only */ });
stream.connect();
// guard.velocity → last fresh [vx, vy], or [0, 0] after 500 ms without a command or after a stop
```

3. Show the user where commands come from (`provenance.kind`, `model_id`, `synthetic`,
   `replayed`), and that the app is waiting when `waiting_for_authorization` is non-empty.
4. Adapt to what is granted: the same app must work with simulated intents, decoded commands,
   or nothing.

### Reference applications (SDK + stdlib only, test-enforced)

- `backend/examples/reference_app/cursor_app.py` — continuous pointer (center-out task).
  `python backend/examples/reference_app/cursor_app.py --url http://127.0.0.1:8000`
- `backend/examples/reference_app/menu_app.py` — discrete menu / speller: select moves the
  highlight, activate opens/chooses, cancel goes back (a "Back" entry where cancel is not
  offered), text is appended to the message line.
  `python backend/examples/reference_app/menu_app.py --url http://127.0.0.1:8000`

Both print their state, say when they wait for operator authorization, and record every stop
reason. Tests: `test_reference_app.py` (imports, no operator API, state machines, cursor app
across simulator / FALCON-over-LSL / Open Ephys) and `test_control_e2e.py` (real server:
unauthorized app gets `not_authorized` and nothing; authorized app receives decoded actions;
revoke / stop / disconnect reach the app within 1 s and nothing arrives afterwards; raw-only
and label-only sources never yield commands; the unchanged menu app on Simulated Profile B
and on the decoded synthetic source).

### Operator walk-through (console)

1. Connect a source with a class-label behavior stream; start decoding (e.g. band power
   8–13 Hz) without a model; record; Decoder → Calibrate with "A class per moment … LDA
   classifier" (optionally class names).
2. Start decoding with the new classifier. Command output → Settings shows one action per
   class (rest: none; others select / activate / cancel by default; thresholds, hold, pause,
   or "Type text").
3. Start control. Under "Authorized applications" each app that asks for commands says what it
   would receive; Authorize the one you mean. Revoke or the title-bar Stop control end it.

## 7. Milestone 5 (workstream C): control.state, navigation, click

Application side: [APPLICATIONS.md](APPLICATIONS.md).

### control.state — the explicit safe-state signal (schema 1.4)

An application that asks for `control_status` (granted whenever a device is connected)
receives `control.state {active, capabilities, reason}` addressed to it alone:

- when a session starts (`connecting to …`, then e.g. `source streaming (…)`) and when the
  app connects during a session;
- whenever the set of command capabilities whose events can reach it changes — granted by
  negotiation, the source `streaming`, and for decoded commands the router on and the app id
  authorized (the same conditions the bus applies);
- while inactive, when the reason it stays inactive changes (e.g. connecting → suspended →
  waiting for operator authorization).

| Trigger | `reason` |
| --- | --- |
| operator Stop / router disabled / pipeline restarted or stopped | `command output stopped: <router stop reason>` |
| input stall | `command output stopped: input stalled: no decoder input for N ms (limit L)` |
| source paused | `command output stopped: source paused`, then `source paused by operator` |
| link lost / reconnected | `command output stopped: source link lost`, `source link lost: …` / `source reconnected after N attempt(s)` |
| switch / disconnect | `command output stopped: device disconnected (…)` / `device disconnected (…)` |
| error / end of source | `runtime error: …` / `source ended: …` |
| authorize / revoke | `operator authorized this application (…)` / `authorization revoked by operator (…)` |
| router on, app authorized | `decoded command output active (…; decoder <model>, authorized)` |
| simulated source | `command input active (…; from <device>)` |

Ordering: the notice is computed and enqueued in the same synchronous step as the change,
after decoded commands still queued for the app were withdrawn, so an app never receives a
command after `active: false` until a later `active: true` (tested for every trigger above in
`test_control_state.py`, over the WebSocket in `test_apps_e2e.py`). It is pinned in the
subscriber queue: overflow drops the oldest *other* event. Negotiation messages are control
messages (delivered ahead of queued events), so an app usually sees the negotiation change
first; the SDK `CommandGuard` stops on whichever comes first and, when `control_status` is
granted, requires an active `control.state` before any command is usable.

### Navigation rules

Discrete rules accept `action: "navigate:<direction>"`; the router then advertises
`navigation` (`params.directions`) and emits `intent.navigate`. `selection` is advertised only
if a select/activate/cancel rule (or a click) exists. Decoded navigation needs the operator's
authorization (`POST /control/apps/{id}/authorize {"capabilities": ["navigation"]}`). The
console's rule editor offers "Move to next / previous / up / down / left / right".

### Click rule (cursor + click)

`RouterSpec.click = {output, action="primary"|"activate", threshold=0.5, release?,
min_confidence=0, confidence_dim?, debounce_ms=0, refractory_ms=300}` on any decoder output
(typically next to a pointer mapping on a continuous decoder, e.g. dims `vx, vy, click`):
fires when `output ≥ threshold` for `debounce_ms` (decoder clock), at most once per
`refractory_ms`, then waits until `output < release` (default `threshold − 0.15`) — one click,
one selection. At the moment it would fire, the confidence (`confidence_dim`, default the
output, clipped to [0, 1]) must be ≥ `min_confidence`; otherwise the click is rejected and
counted (`counters.clicks_gated`). The click output cannot also drive the pointer; a missing
output is refused with 409 `incompatible_decoder`. The console offers "Click from" for
continuous decoders.

### Native pointer scale

`pointer_scale: "native"` treats the two pointer dims as a velocity already in workspace units
per second (no division by the training behavior std, so no `behavior_std` needed);
`deadzone` is then in those units (set it to 0 to pass every movement). Example: a research
system's original cursor decoder in screen heights / s with targets in a square of side
0.92 centred at the origin, +y up → `gain = 1 / 0.92`, `invert_y: true` maps it onto the
board's unit-square workspace (y down).

### Historical and external decoder outputs

The router accepts the configured model's `intent.kinematics` + `decoded_intent` whatever its
`model_origin` and copies the provenance (incl. `model_origin` and `replayed`) to every
command, so apps can say "historical decoder replay (original research system)". Feeding a
*source's* recorded decoder output (rather than the pipeline's decoder) into the router is not
wired in this workstream (LIMITATIONS.md).

### Desktop control bridge

`backend/examples/desktop_bridge/` maps authorized decoded pointer / selection commands to OS
pointer events in a separate, opt-in process; see its
[SAFETY.md](../backend/examples/desktop_bridge/SAFETY.md).
