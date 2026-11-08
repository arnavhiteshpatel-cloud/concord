# Desktop control bridge — safety model

`bridge.py` turns **authorized, decoded** BrainOS pointer and selection commands into
operating-system pointer events: relative pointer moves and a primary-button click. Anything
that moves a real pointer on a real desktop can click the wrong thing, so the bridge is
**opt-in, off by default, and separate** from everything else in BrainOS. It is research
software. It has not been used with any participant and is not an accessibility product.

## What it will never do

- Start on its own. Nothing in BrainOS launches it; it refuses to run without `--enable`
  (exit code 2, before any network or pointer access).
- Accept raw signals, features, behavior labels or simulated intents. It asks the runtime only
  for `pointer_intent`, `selection` and `control_status`, and it acts only on `intent.pointer`
  / `intent.selection` events whose provenance is `decoded_intent`. Simulated-profile intents
  are not gated by operator authorization, so the bridge refuses them (counted as
  `refused_provenance`).
- Authorize itself. Decoded commands reach the app id `desktop-bridge` only after the operator
  authorized it in the BrainOS console (Command output → Authorized applications) and started
  command output. Until then it prints that it is waiting.
- Type text, press keys, scroll, drag or hold a button down. `cancel` has no OS meaning and
  is ignored. A click is a press and release in one backend call.

## Limits on what it does

| Limit | Default | Flag |
| --- | --- | --- |
| commands older than this are dropped (SDK `CommandGuard`, wall clock and relative delay) | 500 ms | — |
| dead-man: pointer velocity is zero this long after the last pointer command | 500 ms | — |
| pointer moves per second (one per tick at most; sub-pixel motion carries over) | 60 | `--rate-hz` (1–240) |
| pointer speed (vector magnitude, workspace units / s) | 1.0 | `--max-speed` (≤ 5) |
| pixels per workspace unit | 800 | `--pixels-per-unit` |
| minimum time between two clicks | 500 ms | `--click-interval-ms` (100–10000) |
| minimum selection confidence for a click | 0 | `--min-confidence` |
| act only while the focused window's title contains TEXT | off | `--focus TEXT` |

The time step of a move is clamped to 0.1 s, so a delayed tick never produces a jump.

## Focus restriction

With `--focus TEXT` every move and click first asks the backend for the focused window's
title; if the backend cannot tell, or the title does not contain TEXT, the action is withheld
(`refused_focus`). A backend that cannot report focus at all (`pynput`) makes the bridge
**refuse to start** when `--focus` is given. Only the `xdotool` backend (X11) reports focus.
There is no integration with any platform accessibility API (UI Automation, AX, AT-SPI): the
bridge does not know what is under the pointer or what a click will do.

## Stopping

| Event | Effect | Timing |
| --- | --- | --- |
| the runtime's `control.state` says inactive (operator Stop, router off, input stall, pause, link lost, source switch/disconnect, revocation) | no OS event until the runtime says active again | the notice is processed when it arrives; no command is delivered after it (runtime guarantee) |
| negotiation withdraws pointer/selection (revocation, suspension, disconnect) | same | immediate (control message, delivered before queued events) |
| stream closed / runtime unreachable | latched stop, the process exits | immediate |
| Ctrl-C / SIGTERM in the bridge's terminal | latched stop, exits | immediate |
| stop hotkey (`pynput` backend: Ctrl+Alt+B) | latched stop, exits | immediate |

Measured in `tests/test_desktop_bridge.py` against a real server: after the operator's
Stop, the bridge learns it within 1 s (the test bound) and emits no OS event in the following
second. The `xdotool` backend has no global hotkey; use Ctrl-C.

## Backends

| Backend | Platforms | Focus | Hotkey | Notes |
| --- | --- | --- | --- | --- |
| `dry-run` (default) | any | configurable (tests) | test hook | records actions, touches nothing |
| `xdotool` | X11 | yes | no | needs the `xdotool` command; tested under Xvfb |
| `pynput` | Windows, macOS, X11 | no | Ctrl+Alt+B | optional `pip install pynput`; not tested here |

## Tests

`backend/tests/test_desktop_bridge.py`: off by default (CLI exit 2), refusals, SDK-only
imports and no operator calls, speed/rate/click limits, stale and simulated commands refused,
dead-man, focus restriction, stop on `control.state` inactive and on the hotkey, an end-to-end
run against a real server (decoded commands from the scripted test decoder; nothing before the
operator authorizes; nothing after the operator stops), and — when `Xvfb` and `xdotool` are
installed — the real X11 pointer moving by the expected number of pixels and focus restriction
against a real (`xterm`) window.
