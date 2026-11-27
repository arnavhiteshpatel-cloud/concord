# Input abstraction: from any input device to canonical events

Status: implemented in the browser (`web/src/input/`) and in Python (`src/neurometric/events/model.py`).
Python is the reference and the validator of record (DECISIONS D-003). Prepared 2026-11-27.
Evidence labels follow `docs/research/CONVENTIONS.md`.

NeuroMetric measures *what a person accomplishes*, not how the input was produced. Every input
source is normalised into one event representation, the canonical `InputEvent`. Sources include a
mouse, a touch screen, one or two switches, eye gaze or a head pointer driving the operating-system
pointer, a BCI exposed by the OS as a pointer or switch, a gamepad, a simulator, or a replayed log.
Tasks are scored from these events alone (D-006, observable-only).

## 1. The canonical event

The field names and enum values are identical in Python (`InputEvent`) and TypeScript
(`web/src/input/types.ts`). Serialisation matches `InputEvent.to_dict()`: `None` and `{}` are
omitted, and `schema_version` = `"1.0"` is added.

| Field | Meaning |
|---|---|
| `t_ms` | **Monotonic session clock** in ms. `performance.now()` based, origin = task start. Never wall-clock time; wall-clock is kept once per session (`time_origin_epoch_ms`, `started_at_epoch_ms`). |
| `kind` | `pointer_move, pointer_down, pointer_up, click, drag_start, drag_end, scroll, text_input, key, dwell_select, switch, select, cancel, pause, resume, assist, marker` |
| `session_id`, `stream_id`, `seq` | One task run = one session. Each stream (input source) has its own `seq` counter starting at 0. |
| `modality` | `mouse, trackpad, touch, pen, keyboard, switch, eye_gaze, head_pointer, joystick, gamepad, bci_cursor, bci_select, simulated, replay, other` |
| `x`, `y` | Task-space CSS px of the 1280 x 800 task canvas (origin top-left, y down), whatever the screen size. |
| `dx`, `dy` | Scroll amounts (task px). |
| `button`, `key`, `switch_id` | Button number; key **name** (never text, except in copy typing); switch identifier (`switch1`, `switch2`). |
| `text` | Only in E1 copy typing, and only predefined phrase characters. |
| `confidence` | Only if the **source itself** reports one, with `meta.confidence_source`. The browser never fabricates it. No current browser source reports one, so it is always absent. |
| `synthetic` | `true` for simulated streams. |
| `meta` | Task metadata (markers, trial index, target geometry), scan action, dwell time, `t_clamped_ms`. |

Validation rules are identical in both languages. Positional kinds need finite `x`/`y`. `scroll`
needs `dx` or `dy`. `text_input` needs `text`. `switch` needs `switch_id`. `assist` needs
`meta.assist_type` in {setup, physical, verbal, troubleshooting, calibration, task_completion}.
`confidence` must lie in [0, 1] and carry `meta.confidence_source`. The browser validates every
event as it is created. `tests/web` re-validates every exported event with
`neurometric.events.model.validate_event`.

## 2. Clock, streams and ordering

* **Timestamps.** DOM input events are stamped from `Event.timeStamp`, not from the handler time.
  Coalesced pointer samples use their own `timeStamp`. Gamepad and simulated samples use the poll
  or scheduled time. Why: in headless Chromium the handler for a CDP-injected mouse move ran a
  median of 15.2 ms after the event's `timeStamp`, because continuous input is aligned to animation
  frames. Handler-time stamping would add up to one frame of bias (Experiment S,
  `experiments/results/S_event_latency/browser_summary.json`). [INF from measurement]
* **Resolution.** The app is served with `Cross-Origin-Opener-Policy: same-origin` and
  `Cross-Origin-Embedder-Policy: require-corp` by `vite preview`/`vite dev`, so it is
  cross-origin isolated. The observed `performance.now()` resolution was 0.005 ms. The backend
  currently sends COOP but not COEP. When the backend serves `web/dist`, the page is therefore not
  isolated, and resolution falls back to about 0.1 ms in Chrome and 1 ms in Safari or Firefox
  (`browser_timing.md`). Recommendation to the API owners: add `Cross-Origin-Embedder-Policy:
  require-corp` to static responses.
* **Per-stream monotonic clamp.** If a sample's time is earlier than the previous sample of the same
  stream, it is set to the previous time, and `meta.t_clamped_ms` records the correction. The
  problem therefore stays visible in the data and is never hidden. In Experiment A, no clamps
  occurred across 35,377 events (latest run).
* **Stream naming.** Input streams are `in:<source>`: `in:pointer:mouse|pen|touch`, `in:keyboard`,
  `in:switch`, `in:dwell`, `in:gamepad`, `in:text`, `in:scroll-buttons`, `in:sim:<id>`,
  `in:replay:<orig>`. The task engine's marker stream is `task`, and session control
  (pause / resume / assist) is `ctl`.
* **Merge order.** The merged session timeline is sorted by `(t_ms, stream_id, seq)`, which is the
  same as `merge_streams` in Python. The sort is stable. Because `"ctl" < "in:…" < "task"` in
  code-unit order, a selection always sorts *before* the `trial_end` / `stimulus_on` markers that
  the task emits at the same `t_ms`. ISO sequences rely on this, because the next trial's onset
  *is* the previous selection.
* Several streams can be active at once, for example a mouse plus a synthetic 1000 Hz pen stream
  in Experiment A, or a pointer plus switch scanning controls. Each stream keeps its own order.

## 3. Adapters (`web/src/input/`)

| Adapter | Source | Notes |
|---|---|---|
| `pointer.ts` | Pointer Events (mouse, pen, touch). Any AT that drives the OS pointer: eye-gaze OS control, head pointers, a BCI exposed as a HID mouse. | Uses `getCoalescedEvents()` where available. Records the primary pointer only. Calls `setPointerCapture` on press. Listeners attach to the **task canvas element only**. The modality is **declared in setup** (`auto` = from `pointerType`). The observed `pointerType`s are stored in session metadata. |
| `keyboard.ts` | Keyboard | Named keys (arrows, Enter, Space, Tab, Escape, Backspace...) are recorded by name. Character keys are never recorded, except by E1, which records predefined-phrase keystrokes because text is allowed only there (`EventRecorder.allowText`, which throws otherwise). |
| `switch.ts` | Switch interfaces presenting as keys (default Space = switch 1, Enter = switch 2; configurable) | Scanner modes: one-switch auto-scan, two-switch step-scan (switch 1 moves, switch 2 selects), two-switch auto-scan. Optional row-column scanning. Configurable scan interval, restart (first item / continue), stop after N empty cycles, first-item extra delay. Dwell-free: no hold or acceptance time is needed. Recording: **only the press that selects a task item is a `switch` event** (a selection kind, with `x,y` = item centre, `meta.scan_action = "select"`). Start, step, row and control presses are `key` events with `switch_id` and `meta.scan_action`, so they never count as selections. |
| `dwell.ts` | Any pointer, typically eye gaze or a head pointer | Configurable threshold and a visible progress ring. The timer resets when the pointer leaves the item, and the item must be left before it can be dwell-selected again. `dwell_select` is stamped at *entry + threshold*, not at the frame on which it was detected, and carries `meta.dwell_ms`. |
| `gamepad.ts` | Gamepad API (polled on rAF) | Joystick → cursor velocity: dead zone 0.15, power-law response (exponent 2), 600 task-px/s at full deflection. Button 0 → `select` at the cursor. Pads are hidden until a gamepad gesture. |
| `simulated.ts` | Simulated streams; replay | `SimulatedPointerStream` emits samples from a path function at a fixed rate, in real time or pumped (fast-forward); events are `synthetic: true`, `modality: "simulated"`. `replayEvents` re-emits a log with `modality: "replay"`, keeping `meta.original_modality`, `original_session_id` and `original_seq`, and preserving relative timing (optionally time-scaled). |
| keyboard cursor (in `TaskRunner`) | Keyboard users in pointing tasks | The arrow keys move a virtual cursor by 10 px, or 40 px with Shift, emitting `pointer_move` with modality `keyboard`. Enter or Space selects at the cursor. |

**What the browser cannot know.** It cannot tell a mouse from eye-gaze OS control, a head pointer
or a BCI cursor exposed as a HID mouse. It cannot tell a keyboard from a switch interface, an EMG
wristband sending arrow keys or a BCI exposed as a switch (`bci_hid_and_input_standards.md`
§1.4, §1.7). The participant or staff therefore **declare** the modality in setup. NeuroMetric
never infers it from timing. Measured times for AT modalities are *selection times*. They include
scan intervals, dwell thresholds and decoder latency, which the page cannot see
(`browser_timing.md` §1.3).

**Global listeners.** Input listeners are attached only to the task canvas. The switch-scanning
listener is attached to the app's root element, never to `window` or `document`. The only
`window` listener is `hashchange`, which handles navigation and receives no input. There is no
focus or visibility tracking outside the canvas (see the known gaps below).

## 4. Task-engine event protocol (consumed by `neurometric.study.scoring`)

* `marker` events on stream `task` (`meta.marker`): `task_start`, `block_start` (D, W),
  `sequence_start` (the unscored first ISO selection), `trial_start`, `stimulus_on`, `trial_end`,
  `phrase_start` / `phrase_end` (E1, `meta.phrase` = index into the stimulus phrases),
  `movement_start` (B1), `task_end` / `task_stopped`, and `scan_stopped`.
* `stimulus_on` carries `trial`, `block`, `target {x,y,w[,h]}`, `start {x,y}`, `D`, `W` and
  `n_items`. It is emitted in the `requestAnimationFrame` callback of the frame that first shows
  the stimulus, with `meta.raf_ts_ms`; a 200 ms timer fallback covers background tabs. In ISO
  sequences (A2/A3) the onset is set exactly to the previous selection's `t_ms`.
* `trial_end` carries `outcome` ∈ {hit, miss, timeout, completed, abandoned} plus task details:
  `wrong_item`, `tunnel_exits`, `placement_error_px`, `band_passes` and `wrong_selections`.
* Selection events (`click`, `dwell_select`, `switch`, `select`) carry `meta.item`. Empty-space
  selections that do not end a trial carry `meta.empty = true`. In the F tasks and C1 they carry
  `meta.correct` (`false` = wrong selection).
* **Pause.** `pause` and `resume` events go on stream `ctl`. While paused, input adapters record
  nothing. The current trial ends with `outcome: "abandoned", reason: "paused"` and is presented
  again on resume. An ISO sequence restarts with a new unscored start selection.
* **Assistance.** `assist` events go on stream `ctl`, with `meta.assist_type`, `meta.by` (staff,
  care partner or participant) and `meta.in_trial`. They are recorded from a native `<dialog>`
  that can be operated with keyboard, pointer or one switch.
* Python's scorer currently treats an `abandoned` trial (no selection) like a timeout, so it counts
  towards `n_trials` and `timeout_rate`. Throughput is unaffected, because timeouts are excluded.
  This is noted for the scoring owners.

## 5. Session metadata (per task run)

`user_agent`, `ua_brands`, `platform`, `device_pixel_ratio`, `viewport_css_px`, `screen_css_px`,
`canvas_scale`, `cross_origin_isolated`, `time_origin_epoch_ms`, `timer_resolution_ms`
(smallest non-zero `performance.now()` step), the display refresh estimate (median and p95 of 120
rAF intervals, frames > 1.5× median), Pointer/coalesced/Gamepad API availability, user
preferences (reduced motion, contrast, colour scheme) and `observed_pointer_types`. Settings
(declared modality, selection method, dwell, switch configuration, timing, theme, text size) are
also stored, and with them the `stimulus_hash` of the Python-exported stimuli (D-004).

## 6. Upload

The upload follows the backend contract in `src/neurometric/api`. The browser calls
`POST /api/auth/login` and then `POST /api/participants/{pid}/sessions` with `task_id`, `events`,
`stimulus_seed`, `stimulus_hash`, `battery_version`, `provenance`, `modality` and
`performed_at`. The server re-validates every event, checks the stimulus hash and computes the
authoritative scores. The browser's numbers are labelled "provisional — authoritative scoring is
server-side".

Without a server, runs are kept in `localStorage` (best effort) and can be downloaded as JSON. The
upload path was exercised end to end against the real backend with a seeded **synthetic** demo
study (`tests/web/upload.spec.ts`).

## 7. Cross-language parity

`web/scripts/make_golden.py` writes Python golden fixtures, and `web/test/parity.test.ts` (Vitest)
must reproduce them:

* **Deterministic DegradedChannel.** Covered: gain, bias, asymmetry, smoothing, quantisation,
  direction bins, update rate, latency, gain decay, dims and selection latency. Each runs in
  velocity and position mode over 240 ticks; 34 cases must match within 1e-9 relative, and the
  selection output exactly. Python's banker's rounding (`np.round`, `round`) is mirrored by
  `roundHalfEven`.
* **Metrics.** Covered: per-trial path efficiency, endpoint error, endpoint dx, amplitude, MT,
  onset, overshoot, re-entries and outcome flags on simulator trajectories plus hand-made edge
  cases; Fitts effective throughput (We, De, IDe, TP, validity); achieved bitrate; Wolpaw bits;
  MSD; and text entry (WPM, CCPM, MSD error rate, KSPC, corrected, uncorrected and total error
  rate). All are within 1e-9 relative, and integers match exactly.
* **Randomised parts.** These use a different PRNG (xoshiro128**), so they are compared by
  statistics: white-noise SD and whiteness, AR(1) lag-1 autocorrelation = exp(−dt/τ),
  false-activation rate, dropout occupancy, miss rate, and mean latency with jitter plus
  monotonic output.

In the browser e2e runs, the provisional TypeScript scores were identical to the Python scores
computed from the same exported events (A2 throughput 17.14 bit/s, A4 achieved bitrate 74.30 bit/s
and E1 WPM 19.16 in both; these values come from synthetic input). The TypeScript metrics for the
Python-simulated virtual-user traces in the demo also match Python's own numbers (for example
mouse_sim 3.74 bit/s, bci_good 0.67 bit/s and grid bitrates 6.20 / 2.16 / 0.93 / 0.67 bit/s).

## 8. Measured behaviour in headless Chromium (not physical latency)

Results are in `experiments/results/A_input_timing/browser_*` and
`experiments/results/S_event_latency/browser_*`. **These figures are for headless Chromium with
injected events. They exclude HID polling, the OS input stack, the compositor and the display, and
are not device latency.** The bench protocol is in `browser_timing.md` §5.

* **Experiment A.** 2000 CDP mouse moves: 2000 recorded, 0 missing, 0 duplicated, 0 order
  violations, 0 non-monotonic. A 1000 Hz in-page pen stream ran over the same period: 33,377
  dispatched, 33,377 recorded, 0 dropped, seq contiguous, median interval 1.00 ms (p99 4.2 ms,
  from main-thread contention with the CDP stream). The merged
  two-stream timeline had 0 order violations, and Python `check_stream` reported 0 non-monotonic,
  0 duplicates and 0 gaps. CDP moves arrive at about 60 Hz (median 16.7 ms), because Playwright
  waits for the renderer, which aligns moves to frames.
* **Experiment S.** From dispatch to canonical event: median 0.055 ms, p99 0.12 ms. From canonical
  event to the next frame callback: median 8.5 ms, p95 16.1 ms, which is the expected uniform wait
  over a 16.7 ms frame. A 10-minute session at 60 Hz, fast-forwarded (36,000 DOM events): 0
  dropped, heap growth about 106 bytes per retained event, and about 9.5 MB of serialised JSON for
  42k events. The recorder keeps the full session log in memory by design.

## 9. Known gaps

* No focus or visibility (`visibilitychange`) tracking. It would need a document-level listener,
  which the current privacy rule excludes. Trials interrupted by tab switches are therefore not
  flagged automatically.
* `pointerrawupdate` is not used (not Baseline), and the Event Timing API is not yet recorded.
* The Gamepad adapter and the replay stream are unit-tested but have not been run with physical
  pads.
* Multi-touch is not recorded: only the primary pointer is.
* The backend does not send COEP, so the page is not cross-origin isolated when the backend serves
  it (see §2).

## 10. Commands

```
cd web && npm install && npm run build && npm test     # build to web/dist (served by the backend if present) + Vitest parity/unit tests
cd tests/web && npm install && npx playwright test     # e2e, axe, timing experiments, backend upload (uses vite preview on :4173)
python web/scripts/export_battery.py                   # re-export stimuli from Python (seed 0)
python web/scripts/export_demo_traces.py               # re-export virtual-user traces for the demo
python web/scripts/make_golden.py                      # re-generate parity golden fixtures
```

