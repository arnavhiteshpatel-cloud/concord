# BrainOS user guide

Every part of BrainOS, in the order you meet it: the desktop app, the console (the operator's
screen in your browser), the communication board (the participant's screen), the configuration
file and the `brainos` command. New to BrainOS? Start with
[Getting started](GETTING_STARTED.md); terms are explained in the [glossary](GLOSSARY.md).

> BrainOS is research software and only *receives* data. It has never been used with acquisition
> hardware or a participant and is not a medical device ([validation levels](VALIDATION_LEVELS.md)).

**Contents**

1. [The desktop app](#the-desktop-app)
2. [The console at a glance](#the-console-at-a-glance)
3. [Connecting a source](#connecting-a-source)
4. [Signal integrity](#signal-integrity)
5. [Decoding](#decoding)
6. [Command output and applications](#command-output-and-applications)
7. [The communication board](#the-communication-board)
8. [Recording and replay](#recording-and-replay)
9. [Research sessions, export and reproduction](#research-sessions-export-and-reproduction)
10. [Stopping safely](#stopping-safely)
11. [Advanced sections](#advanced-sections)
12. [Configuration file](#configuration-file)
13. [The `brainos` command](#the-brainos-command)
14. [Network, ports and data folders](#network-ports-and-data-folders)

---

## The desktop app

Starting BrainOS (the Mac app or the Linux bundle) opens a small window titled **BrainOS**:
**BrainOS is running**, its address (http://127.0.0.1:8000) and *Research use only · not a
medical device · read-only*, with two buttons:

| Button | What it does |
| --- | --- |
| **Open console** | Opens the console in your default browser (it also opens by itself at start). |
| **Stop and quit** | Performs a [safe stop](#stopping-safely), then ends BrainOS. ⌘Q, Quit in the Dock and closing the window do the same. |

Opening BrainOS again while it runs only opens the console. If BrainOS ends unexpectedly
(crash, power loss), the next start keeps every complete part of an interrupted recording and
marks it *incomplete* (details in [TROUBLESHOOTING.md](TROUBLESHOOTING.md)).

---

## The console at a glance

![The console](images/01-console-first-launch.png)

| Part | Contents |
| --- | --- |
| **Title bar** | *BrainOS*, a **Research use only** badge (hover: "Not a medical device. Read-only: BrainOS never writes to or stimulates a device."), the connected source, its state (e.g. *Streaming · Simulated data*, *Streaming · Recorded human data, offline replay*), **· Recording** while recording, and **Stop control** (turns decoded commands off at once). |
| **Session strip** | The research session (or "No research session…"), **New session** / **Session and export…**, and **Safe stop & disconnect**. |
| **Acquisition source** | The connected source, **Connect a source** / **Change source** / **Disconnect**, and *Options* (live sources) or *Playback* (replays). |
| **Signal integrity** | The verdict, live traces and three measured numbers. |
| **Decoder** | The decoder's state, **Start decoding** / **Stop decoding**, **Calibrate…** |
| **Command output** | Whether decoded commands are sent, their settings, the **Authorized applications**, **Open participant screen**. |
| **Session log** | What happened, newest first: connections, state changes, recordings, decoding, control, refusals. |
| **Advanced** | Thirteen sections of details and tools ([below](#advanced-sections)). |

Buttons that cannot be used right now are disabled, and the reason is shown in the row (for
example "Connect a source first." or "Start decoding with a model first.").

---

## Connecting a source

**Connect a source** (or **Change source** while connected) opens a panel with every source
BrainOS can use, grouped by kind. **Connect** next to a source starts it; while another source
runs, the button reads **Switch** and BrainOS changes source without restarting. Applications
keep running and are told what the new source can provide.

![The Connect a source panel](images/02-connect-a-source.png)

### Simulated profiles

Synthetic data generated inside BrainOS, for demonstrations and testing. Never brain data; every
event they produce is labelled `simulated_intent` or synthetic.

| Profile | Signal | What it provides to applications |
| --- | --- | --- |
| **Simulated Profile A** | 32 channels at 1,000 Hz | Continuous pointer movement and a select action (the board uses *Pointer and click*) |
| **Simulated Profile B** | 8 channels at 250 Hz | A select action and text, no pointer (the board switches to *Scanning*) |

You stand in for the participant with **Advanced → Simulator controls** ([below](#simulator-controls)).

### Recorded human data (offline replay)

Verified files from public datasets ([Datasets](DATASETS.md)), listed by session
(e.g. *Session 19250108T111022 · DANDI 000954 · held-in-calib · 176 channels · 20 ms bins*).
The first four files are shown; **Show all N files** lists the rest. Files appear here as soon as
they are in the data folder's `datasets` subfolder ([how to get them](GETTING_STARTED.md#4-replay-real-human-recordings-10-minutes)).

While a replay runs, the source panel shows the position (*0:02.0 of 2:15.7*) and **Playback**:
**Pause** / **Resume** and the speed **0.5× 1× 2× 4× 8×**. **Advanced → Acquisition details**
shows the dataset, license, whether the file's SHA-256 matches the archive, what was recorded,
the citation, and (when one is installed) the decoder evaluated on this file. A decoder is shown
only on data it was *not* trained on.

### Session recordings (replay)

Recordings you made with BrainOS ([Recording and replay](#recording-and-replay)). They replay
through the same pipeline; every replayed event is marked `replayed`.

### Other sources

Other offline sources, such as the T15 cursor + click blocks (*Recorded Human Intracortical Data
(cursor + click) — Offline Replay*), which include the original research system's decoder
outputs, labelled *historical*.

### Live streams

BrainOS only receives; nothing is sent to the acquisition system.

**Find LSL streams** — Lab Streaming Layer outlets on your network:

1. **Search the network** lists the streams found (*Stream, Channels, Rate, Units, Declared*).
   Streams whose publisher declares them prerecorded or synthetic are labelled so; any other
   stream is shown as live with unverified origin, because LSL cannot tell hardware from playback.
2. **Use** next to the neural stream makes it the *Signal*.
3. Optionally attach a **Behavior stream** (calibration labels, e.g. cued movement) and a
   **Marker stream** (events), mapped onto the signal's clock with LSL time correction.
4. **Add source** registers it; it then appears in the list with **Connect** (and **Remove**).

**Add Open Ephys source** — the Open Ephys GUI's ZMQ Interface plugin:

| Field | Meaning |
| --- | --- |
| **Host** | The computer running the Open Ephys GUI (default 127.0.0.1) |
| **Data port** | The plugin's data port (default 5556); BrainOS sends heartbeats to port + 1 |
| **Sample unit** | **Unknown** (samples passed through, labelled *arbitrary*), or the unit configured in the GUI (µV, mV, V), which BrainOS converts to µV |

**Add source** registers it; adding does not connect it. Setup in the GUI: [OPEN_EPHYS.md](OPEN_EPHYS.md).

### Plugins

Sources from installed adapter packages (BCI2000 is included in the app; BrainFlow with the
Python installation; or [your own](ADAPTER_SDK.md)). Each plugin shows its version, whether it is
**compatible** with this BrainOS, its kind and whether it uses the network; each device it
offers has **Connect** and, where needed, **Options**. **Search again** looks for newly installed
plugins. Plugins are third-party code: each runs in its own process, with your user's
permissions; "compatible" means it follows the adapter contract, not that its code was reviewed.

---

## Signal integrity

Whether data is arriving complete and on time, like a patient monitor: four live traces on the
left (*Showing 4 of 32 channels · raw samples, last 2 s, each scaled to fit*), the verdict and
three numbers on the right.

| Verdict | When |
| --- | --- |
| **Good** | None of the conditions below |
| **Gaps detected** | A loss counter increased in the last 10 s (stream gaps, estimated missing samples, missed messages, incomplete blocks, pipeline dropped inputs, dropped deliveries) |
| **No signal** | No raw-signal or feature event arrived in the last 2 s |
| **Paused** | The operator paused the source |
| **Interrupted — reconnecting** | BrainOS is reconnecting to the source |

| Number | Meaning |
| --- | --- |
| **Channels** | Channels in the latest data block, of the channels the source declares |
| **Data received (%)** | Share of the data that arrived, where the source reports both sides: LSL (samples received vs estimated missing) and Open Ephys (messages received vs missed); — otherwise |
| **Delay to this screen (ms)** | Median time from BrainOS receiving an event to this browser receiving it (last 1,000 events) |

Per-stream counters (received, gaps, estimated missing samples, time correction, last
timestamp) are under **Advanced → Acquisition details**. BrainOS counts every loss and
reconnect; it never fills gaps silently.

---

## Decoding

### Start decoding

**Decoder → Start decoding** opens the decoding settings:

| Setting | Options |
| --- | --- |
| **Processing** | *Spike-band threshold crossings* (raw broadband signals), *High-gamma band power* (ECoG), *Band power*, *Source features (passthrough)* (the source already sends features), *Source decoder outputs (passthrough)* (the source's own decoder outputs go to command output unchanged, keeping their model and origin) |
| Processing parameters | **Bin (ms)**, **Threshold (× RMS)**, **Band low (Hz)**, **Band high (Hz)**, depending on the preset |
| **Decoder model** | **None (features only)**, or one of the installed models and decoder plugins. Each shows its family (ridge regression, Kalman filter, LDA classifier, click classifier, ONNX, scikit-learn, TorchScript), what it was trained on, what it expects and outputs, its offline held-out score, and whether it is **compatible with this source**. Incompatible models are refused with the reason. |
| **Map channels by label** | Feeds the model the source channels that carry the model's channel labels, in the model's order. Only if the labels name the same electrodes; the mapping is logged and shown. |
| **Allow a model trained on a different source** | For deliberate cross-source tests only; the decoded output is marked as reduced quality. |

Pickle and joblib model files can run arbitrary code, so they are refused until you click
**Mark this file trusted** for that exact file (**Withdraw trust** undoes it). While running,
the row shows *Running · <processing>* with the model, and **Stop decoding** stops it. Bring your
own models and decoders: [DECODER_SDK.md](DECODER_SDK.md).

### Calibrate…

Train a decoder from your own recordings:

1. **Record a calibration session**: records features and behaviour labels only (not raw
   samples), for up to an hour. With a raw source, start decoding without a model first so that
   the pipeline computes the features.
2. **Train**:

| Setting | Meaning |
| --- | --- |
| **What the decoder should output** | **Continuous movement** (needs a behaviour stream with continuous targets, e.g. cued cursor velocity), **Discrete classes** (a class code per bin, e.g. a cue), **Click** (a dimension that is 1 while a click is attempted) |
| **Decoder family** | The default for that output, or another family that supports it |
| **Label dimension**, **Class names** | Which behaviour dimension holds the label; names for classes 0, 1, … (optional) |
| **Train fraction**, **Gap (bins)** | The first part trains; the chronological tail, after a gap, is held out for scoring |
| **Feature source**, **Use every feature stream…** | Which feature stream to use, or all of them joined per bin |

**Check labels** verifies that the recordings carry the labels the output needs. The report
gives the offline held-out score with controls: R² per dimension and velocity error (continuous),
balanced accuracy, per-class results and the confusion matrix (classes), click detection,
precision and false clicks per minute (click). The saved model is then selectable under **Start
decoding**. An offline held-out score measures how well the model reconstructs recorded labels,
not how well a person can control anything with it. Step by step: [LAB_GUIDE.md §5](LAB_GUIDE.md#5-calibrate-a-decoder).

---

## Command output and applications

Decoded output never becomes an application command by itself. Commands reach an application
only while **all** of these hold: a decoder runs with a model, the operator has clicked **Start
control**, and the operator has **authorized** that application.

### Command settings

For decoders with continuous output (movement):

| Setting | Meaning |
| --- | --- |
| **Horizontal (x) from**, **Vertical (y) from** | Which decoder dimensions drive the pointer |
| **Gain** | Workspace per second per training-standard-deviation unit (0 < gain ≤ 10) |
| **Dead-zone** | Outputs below this (in training-standard-deviation units) are ignored |
| **Max speed** | Upper limit of pointer speed |
| **Invert y** | For decoders whose +y points up when the application's +y points down |
| **Click from** / **No click** | A decoder output that is a click probability or decision, if any |
| **Click threshold**, **Minimum confidence**, **Click pause (ms)** | When a click is sent, and the minimum time between two clicks |

**Apply settings** applies changes while running. For classifiers (discrete output), each class
maps to an action (**No action, Select, Activate, Cancel, Move to next / previous / up / down /
left / right, Type text**) with a **Threshold**, a **Hold (ms)** time above it, and a **Pause
(ms)** before it can repeat.

### Authorized applications

Every connected application is listed with what it asks for. **Authorize** lets it receive
decoded commands until you **Revoke** it. Applications are not authorized by default.
Simulated profiles drive applications directly (as simulated input, labelled so), so you can try
the board without a decoder. **Open participant screen** opens the communication board in its own
window, for a second screen facing the participant. Every rule and stop path:
[CONTROL_BRIDGE.md](CONTROL_BRIDGE.md).

---

## The communication board

The participant-facing application included with BrainOS. It uses only the public SDK, so it
works with any source that provides the capabilities it asks for.

![The communication board](images/05-participant-screen.png)

| Part | Contents |
| --- | --- |
| Header | *Communication board*, *Research use only*, the active input method, the connection state, **Settings** |
| Input bar | **Input active** and where the input comes from (*simulated input · synthetic data*, *decoded by <model> (BrainOS)*, *historical decoder replay*) |
| Message | The composed text, with a label when it is not a participant's own message: *simulated input — no participant* or *demonstration — not the participant's message* |
| Tiles | Phrases (Yes, No, Hello, Thank you, Please, Help, Water, Wait, I'm tired, Pain, Too hot), **Letters** (keyboard page), **Delete word**, **Undo**, **Clear**, **Speak** (computer speech of the message; not neural speech decoding) |
| History | Spoken or saved messages |
| Footer | What the runtime is delivering, selections, events and delivery gaps |

### Input methods

The board picks the first method the source supports, in this order (or the one chosen in
Settings):

| Method | Needs | How it works |
| --- | --- | --- |
| **Pointer and click** | pointer + selection | Move the cursor to a tile, click to choose it |
| **Pointer with dwell selection** | pointer | Rest the cursor on a tile to choose it (a board interaction, never a neural click) |
| **Directional navigation** | navigation | Move the highlight; select chooses (or dwell, without selection) |
| **Direct selection** | selection with several actions | Select = next tile, Activate = choose, Cancel = undo |
| **Scanning** | selection | The board highlights tiles in turn; one switch chooses |

### Board settings

| Setting | Options |
| --- | --- |
| **Input method** | Automatic or a specific method ("— not offered by the current source" when unavailable) |
| **Layout** | **Phrases and letters**, or **Task grid (N × N words)** with an optional **Word list URL** |
| **Tile size (phrase page)** | Large (3 × 3), Standard (4 × 4), Small (5 × 5) |
| **Text size** | 0.75× to 2× |
| **Timing** | Dwell time (0.3–5 s), scan interval (0.4–5 s), click debounce (0–3 s) |
| **Scan pattern** | Tile by tile, or Row, then column |
| **Confirmation** | None (choose at once), or select the same tile twice |
| **Feedback and speech** | Audio tick on every selection; speech and its rate |
| **Clear history** | Removes the message history |

Cursor speed and smoothing are not board settings: the operator sets them in
[Command output](#command-settings). For evaluation harnesses, every setting can also be given
in the board's URL (e.g. `board.html?layout=grid&n=7&method=cursor_click`); the parameter names
are listed in [APPLICATIONS.md](APPLICATIONS.md).

---

## Recording and replay

**Advanced → Recording → Start recording** writes the standardized events of the connected
source to the data folder's `recordings/` subfolder, including pipeline features and decoder
output while decoding runs; **Stop recording** ends it. **Features and labels only (for
calibration)** records everything except raw signal frames (raw frames at high rates are large).

| Limit (default) | With raw frames | Features and labels only |
| --- | --- | --- |
| Duration | 5 minutes | 1 hour |
| Size | 200 MiB | 200 MiB |
| Free disk space | stops below 256 MiB | stops below 256 MiB |

Limits can be raised in the [configuration file](#configuration-file) (up to 24 hours / 100 GiB).
A recording that reaches a limit stops cleanly and is complete. Recordings appear under
**Session recordings (replay)** in the source panel and can be used for calibration. Local file
replays cannot be re-recorded. For raw archival, use your acquisition software.

---

## Research sessions, export and reproduction

**New session** creates a session folder; while it is active, BrainOS logs source changes,
decoding and control settings, recordings and calibrations into it.

| Field | Note |
| --- | --- |
| **Session name** | No participant identifiers |
| **Operator (optional)**, **Notes (optional)** | Kept only in the session folder: never written to logs or support reports, and in an export only if you choose so |

**Start session** begins it; the strip then shows the session, the operator, the start time and
how many recordings and models it has. **Session and export…** shows the session id, start,
operator, notes, recordings, decoder models and its log, and **Export for reproduction**:

- **Include the session's recordings** (neural data; needed to re-run the evaluation);
- **Include the operator name and notes**;
- **Create export bundle** writes a zip (shown with its SHA-256) with the session log, versions
  and package fingerprints, sources, pipeline settings, decoder models with their calibration
  reports, and a `REPRODUCE.md`.

`brainos reproduce <bundle>.zip` (in any BrainOS installation) checks that no file was changed
and re-runs the evaluation. **End session…** → **End session now** turns command output off,
closes any recording, stops decoding, disconnects the source and closes the session.

![Session details and export](images/08-session-export.png)

---

## Stopping safely

| Control | Effect |
| --- | --- |
| **Stop control** (title bar) | Command output off immediately; nothing else changes |
| **Safe stop & disconnect** (session strip) | Command output off, recording closed, decoding stopped, source disconnected, in that order |
| **Revoke** (an application) | That application stops receiving decoded commands |
| **Pause** (source *Options* / *Playback*) | The source pauses and command output turns off; **Resume** continues |
| **Disconnect** (source) | The source stops; decoding and command output stop and any recording closes |
| Quitting the app / `brainos stop` | A safe stop, then BrainOS ends |

---

## Advanced sections

![Advanced](images/11-advanced.png)

| Section | What it shows or does |
| --- | --- |
| **Event stream** | Live events (*Seq, Type, Device, Provenance, Quality, Payload*), filterable by type; click a row to see the full event |
| **Pipeline details** | Processing stages, decoder, command router, input/output counters and measured latency per stage |
| **Acquisition details** | For datasets: the dataset panel (source, license, checksum, citation, channels) and the replayed neural activity; for live sources: per-stream counters and the source's metadata |
| **Diagnostics** | Events published, latency percentiles (runtime and browser), contract violations, drops, reconnects, uptime, per-type rates, device switches and recent errors, all measured live |
| **Recording** | [Recording](#recording-and-replay) |
| **Capability contract** | Which capabilities each device declares, the capability vocabulary and how provenance kinds are kept apart; links to the event schema and API documentation |
| **Connected applications** | The applications connected over the SDK and what they were granted |
| **Simulator controls** | Only with a simulated profile ([below](#simulator-controls)) |
| **Communication board** | The board embedded in the console |
| **Tests** | Results of the most recent test runs (read from the reports folder; it does not run tests) |
| **Compatibility** | Every integration and the validation level its evidence supports ([COMPATIBILITY.md](COMPATIBILITY.md)) |
| **Stored data** | The data folder, its recordings, models and research sessions with their sizes, and **Delete** (asks for confirmation; refuses anything in use) |
| **Support report** | **Create support report**: versions, components, ports, permissions, disk space and recent log problems, without neural or personal data; **Download JSON** / **Download Markdown** |

![Stored data and support report](images/12-stored-data-and-support.png)

### Simulator controls

![Simulator controls](images/04-simulator-controls.png)

You stand in for the participant's intent; no neural decoding is involved. Drag the dot in the
pad (or hold the arrow keys / W A S D) to move; **Select** (or Space) selects; with Simulated
Profile B, type text and **Send text**. **Fault injection** tests how BrainOS and applications
react:

| Fault | What happens |
| --- | --- |
| **Link drop** | The link drops once; BrainOS reconnects on its own |
| **Link failure** | The link drops and every reconnect fails; after its retries BrainOS reports an error and you reconnect manually |
| **Malformed packet** | The next packet is corrupt; it is rejected and counted |
| **Clock regression** | The next packet's device clock jumps back; the event is flagged and counted |

---

## Configuration file

Every setting has a safe default, so the file is optional. Create it with
`brainos config init` (a commented file readable only by you), see where it is with
`brainos config path`, and see the settings in effect with `brainos config show`. It is
refused if other users can modify it.

| Section and key | Default | Meaning |
| --- | --- | --- |
| `[server] host` | `127.0.0.1` | Interface to listen on; keep 127.0.0.1 (BrainOS has no authentication) |
| `[server] port` | `8000` | Port of the console and API |
| `[server] allow_remote` | `false` | Required for any other host (not recommended; use an SSH tunnel) |
| `[server] open_browser` | `true` | Open the console when BrainOS starts |
| `[server] log_level` | `INFO` | DEBUG, INFO, WARNING or ERROR |
| `[storage] data_dir` | see [below](#network-ports-and-data-folders) | Recordings, models, sessions, exports and logs |
| `[storage] reports_dir` | | Test and calibration reports |
| `[retention] recordings_days`, `sessions_days`, `exports_days`, `models_days` | `0` (keep) | Delete items older than this many days when BrainOS starts; items in use are never deleted |
| `[recording] max_duration_s` | `300` | A recording with raw frames stops after this many seconds (at most 86400) |
| `[recording] max_duration_no_raw_s` | `3600` | A features-and-labels-only recording stops after this many seconds |
| `[recording] max_size_mb` | `200` | A recording stops at this size (at most 102400 MiB) |
| `[recording] min_free_mb` | `256` | A recording does not start, or stops cleanly, below this much free disk space |
| `[simulation] enabled` | `true` | Offer the simulated profiles and simulator controls |
| `[plugins] discover` | `true` | Look for installed source plugins at start |

Environment variables override the file: `BRAINOS_HOST`, `BRAINOS_PORT`, `BRAINOS_ALLOW_REMOTE`,
`BRAINOS_OPEN_BROWSER`, `BRAINOS_LOG_LEVEL`, `BRAINOS_DATA_DIR`, `BRAINOS_REPORTS_DIR`,
`BRAINOS_ENABLE_SIM`, `BRAINOS_PLUGINS`, `BRAINOS_RECORDING_MAX_S`,
`BRAINOS_RECORDING_MAX_NO_RAW_S`, `BRAINOS_RECORDING_MAX_MB`, `BRAINOS_RECORDING_MIN_FREE_MB`,
and `BRAINOS_CONFIG` (which config file to read). For plugins and development:
`BRAINOS_PLUGIN_PYTHON`, `BRAINOS_PLUGIN_PATH`, `BRAINOS_STATIC_DIR`, `BRAINOS_COMPAT_REGISTRY`.

---

## The `brainos` command

Installed with the Python package; in the Mac app the same commands are run as
`/Applications/BrainOS.app/Contents/MacOS/BrainOS <command>`.

| Command | What it does | Main options |
| --- | --- | --- |
| `brainos start` | Starts BrainOS in the background, waits until it answers, opens the console | `--port`, `--data-dir`, `--config`, `--no-browser`, `--foreground`, `--host` with `--allow-remote` |
| `brainos stop` | Safe stop, then ends BrainOS | `--port` |
| `brainos status` | Whether BrainOS runs, where, and what it is doing | `--json` |
| `brainos doctor` | Checks the installation and writes a support report (no neural or personal data) | `--json FILE`, `--markdown FILE`, `--print json/markdown`, `--no-plugins` |
| `brainos version` | Versions of BrainOS and its packages | `--json` |
| `brainos config` | `path`, `show` (settings in effect), `init` (create the file), `template` | `--config` |
| `brainos dataset` | Downloads and verifies a demo dataset: `falcon-h1` (default) or `ajile12` | `--all-calib` (all 13 FALCON calibration blocks), `--list`, `--data-dir` |
| `brainos reproduce BUNDLE.zip` | Verifies a session export and re-runs its evaluation | `--json FILE` |
| `brainos serve` | Runs BrainOS in the foreground (what `start` runs) | as `start` |

---

## Network, ports and data folders

BrainOS listens only on this computer, at http://127.0.0.1:8000, and refuses requests from
other web sites and other host names. It contacts other computers only when you ask: LSL
discovery (multicast on your local network), an Open Ephys GUI (its data port and port + 1),
BCI2000 (UDP 20321 by default), and dataset downloads. Ports and topology for a lab:
[LAB_SETUP.md §2](LAB_SETUP.md#2-network-topology).

| Installation | Data folder | Configuration file |
| --- | --- | --- |
| Mac app or Python on a Mac | `~/Library/Application Support/BrainOS/data` | `~/Library/Application Support/BrainOS/config.toml` |
| Linux bundle or Python on Linux | `~/.local/share/brainos/data` | `~/.config/brainos/config.toml` |
| Source checkout | `data/` in the repository | as above for the platform |

The data folder holds `datasets/`, `recordings/`, `models/`, `sessions/` (with their logs and
exports), `logs/` and `support/`; it is readable only by your user account (folders 0700, files
0600). Nothing is encrypted by BrainOS. What is and is not protected: [SECURITY.md](SECURITY.md).
