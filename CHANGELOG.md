# Changelog

Concord is research software in active development. Versions follow
[semantic versioning](https://semver.org/) while below 1.0: a minor version may change
interfaces. Each entry links to the documents that describe the change in depth.
Every release is software- and protocol-tested only: **no version has been used with
acquisition hardware or with a participant** ([validation levels](docs/VALIDATION_LEVELS.md)).

## 0.3.1 — fixes found by a first-time walkthrough, and the guides rewritten

Two independent reviews followed the documentation as a first-time researcher would. They found
documented workflows that did not work in the app, and steps the guides never explained. This
release fixes both. Nothing about how data is received, processed or decoded changed.

**Fixed in the app**

- **Recording a live source works.** Recording or calibrating from LSL, Open Ephys or a plugin
  failed with "invalid recording name", because the default name was built from the source's
  id (which contains ":"). Default names are now always valid. Recorded files (session
  recordings, NWB datasets, T15 blocks) are refused with a plain reason: they already are
  recordings.
- **A decoder's click can reach the board.** In Command output → Settings, **Click from** offered
  only the first running decoder's outputs. A cursor + click chain runs two decoders (movement
  and click), so the click could never be routed from the console. It now lists every running
  decoder's outputs and pre-selects a click output when there is one.
- **Invert y** is ticked automatically when the decoder declares +y up (the only valid choice).
  The error message names the checkbox.
- **The four T15 cursor + click blocks have their own names**
  ("Cursor + click · Day 468 · block 3 · grid evaluation") and are listed with the recorded human
  data. Before, all four had the same title and only a hover tooltip told them apart.
- **The source card says which file or session is playing.**
- **The empty source list names your real datasets folder**, instead of a developer command
  (`make dataset`).
- **The communication board's "Input: …" label** is cleared when the source changes, so it no
  longer says "simulated input" after you switch to recorded human data.
- **The console shows its version** next to "Concord", so you can tell at a glance that an older
  copy is not the one running.
- **Advanced → Compatibility** works in installed copies: the registry now ships with the app
  and the wheel. **Advanced → Tests** explains why an installed copy has no test results.
- **Delay to this screen** no longer shows negative values. The provenance table in
  **Capability contract** and a caption in **Acquisition details** were out of date and are
  rewritten.
- **Advanced → Simulator controls** is shown only for Simulated Profile A and B. A plugin's
  synthetic board (for example BrainFlow's) offered buttons that did nothing for it.
- **A source that could not be reconnected names the reason** even when the last error had no
  message (for example *TimeoutError*); before, the message ended in an empty reason.
- **The export's `REPRODUCE.md`** said to `pip install concordos` from PyPI, where Concord is not
  published. It now says to install from the release wheels, or to use the desktop app's own
  program.

**New**

- **Windows 10 and 11 (x86_64).** A third desktop download, `Concord-windows-x86_64.zip`:
  extract it and double-click `Concord.exe` (windowed, with the same status window); commands go
  to `concord-cli.exe` next to it. The Python installation works on Windows too
  ([INSTALL_WINDOWS.md](docs/INSTALL_WINDOWS.md)). Data and the config file are in
  `%LOCALAPPDATA%\Concord`. CI builds the app on `windows-latest`, extracts the zip and
  smoke-tests it (headless start, plugin host, recording, crash recovery, `start`/`status`/
  `stop`, the Tk window), and runs the backend and package test suites and the clean-room wheel
  installation on Windows. Unsigned, and **not yet tested on a physical Windows PC**
  ([LIMITATIONS.md](LIMITATIONS.md)). What Windows needed:
  - process liveness without `os.kill(pid, 0)` (on Windows that *ends* the process); file locks
    for the pid file and recording markers that Windows releases when a process dies (a byte
    lock beyond the end of the file, so the content stays readable); `concord stop` asks the app
    or server to quit through a stop request in the data folder (Windows has no SIGTERM to
    catch), with TerminateProcess only as the last resort;
  - files opened in binary mode (`os.open` defaults to text mode on Windows, which turned every
    `\n` into `\r\n`, corrupting export zips) and recordings and session logs written with `\n`
    line endings on every platform; UTF-8 for every text file Concord reads or writes; console
    output that never fails on a character the Windows code page lacks;
  - helper processes (source-plugin and decoder hosts, `concord start`'s server) without console
    windows, in their own process group, run with `concord-cli.exe` from the windowed app;
  - Windows-specific checks: a busy port looked free to `concord doctor` (`SO_REUSEADDR` means
    something else on Windows); the config template's Windows paths were invalid TOML; a
    session bundle member such as `..\x` or `C:x` could escape the extraction folder in
    `concord reproduce`; deleting a file another program holds open now says so (409) instead
    of failing; support reports redact `C:\Users\<name>`;
  - recording names that Windows reserves (`con`, `nul`, `com1`…) are refused on every platform,
    so recordings can move between computers;
  - `tornado` is installed with the `live` extra on Windows only: pyzmq needs it there for Open
    Ephys on the Proactor event loop, which Concord needs for its plugin subprocesses.
- **`concord publish lsl-ephys | falcon <file> | openephys`**: hardware-free test streams for
  rehearsing a lab setup. They are also available from the desktop app's own program
  (`/Applications/Concord.app/Contents/MacOS/Concord publish …`, `./Concord/Concord publish …`,
  on Windows `.\concord-cli.exe publish …`).
- **The release ships the BrainFlow, BCI2000 and certification plugins as wheels**, next to the
  others. None of Concord's packages is on PyPI; install from the release files.

**Documentation**

- [Getting started](docs/GETTING_STARTED.md) is rewritten from the walkthrough's findings.
  Every step says what to click and what you should see, and it now ends with a recorded
  decoder driving the communication board (T15). All screenshots were retaken on a fresh
  installation.
- New: [How Concord works](docs/CONCEPTS.md) explains sources, data kinds, capabilities,
  decoders and command output in plain language.
- New: [Connect your equipment](docs/CONNECT_YOUR_EQUIPMENT.md) covers LSL, Open Ephys, BrainFlow,
  BCI2000 and your own device, including rehearsal without hardware.
- The [user guide](docs/USER_GUIDE.md) is now a complete reference of every control, state and
  message in the console and on the board, in the order they appear on screen, with an A–Z
  index of every control. The [glossary](docs/GLOSSARY.md) is completed; every term can be
  linked directly.

## 0.3.0 — renamed to Concord

**The project is now called Concord.** Every name changed with it; nothing else did.

- Python import package `concord`, command `concord`; the main distribution is
  `concordos` (`pip install "concordos[lab]"`), because `concord` is taken on PyPI.
- Companion packages: `concord-adapter-sdk`, `concord-decoder-sdk`, `concord-certify`,
  `concord-hwval`, `concord-brainflow`, `concord-bci2000` and the two examples.
- Plugin entry-point groups are `concord.sources` and `concord.decoders`: an existing
  third-party plugin must re-declare its entry point under the new group to be found.
- Environment variables start with `CONCORD_`; config and data live under `concord`
  directories; recordings use the `.concord.jsonl` extension; built-in adapter IDs start
  with `concord.`; `provenance.model_origin` for a model the runtime trained is `"concord"`.
- Desktop downloads are `Concord-macos-arm64.dmg` and `Concord-linux-x86_64.tar.gz`.
- Certification reports for the three bundled plugins were re-run on the renamed sources
  (same results and levels).

**Desktop app: another running copy is explained.** If another copy of Concord already
answers on the app's address (an older version, another installation, or one started from a
terminal with its own data folder), the app no longer opens that copy's console without a
word. A window says that another copy is running, with its version, process ID and what
differs, and asks to quit it and open Concord again; without a window the same message goes
to stderr and `concord.log` (exit status 3). A second launch while this data folder's own
server runs still only opens its console ([TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md)).

## 0.3.0 — Milestone 5 (research preview) — first downloadable release

The first release with a desktop app download ([release notes](docs/releases/v0.3.0.md)).

**Human data, decoding and communication**

- Recorded intracortical data from a participant controlling a cursor and clicking (T15,
  Dryad, CC0) replays through Concord; Concord's own Kalman cursor decoder and click
  decoder, trained only on earlier blocks, drive the communication board end to end in a
  browser test. Open loop only ([CURSOR_CLICK.md](docs/CURSOR_CLICK.md),
  [NEURAL_COMMUNICATION.md](docs/NEURAL_COMMUNICATION.md)).
- Human ECoG (AJILE12, DANDI 000055) as verified slices, with a raw-voltage importer, ECoG
  preprocessing and a movement-vs-rest decoder evaluated on held-out sessions ([ECOG.md](docs/ECOG.md)).
- Decoder SDK: bring your own decoder (ONNX, scikit-learn via skops, TorchScript /
  safetensors, or a plugin) run in an isolated process, with compatibility rules
  ([DECODER_SDK.md](docs/DECODER_SDK.md)).

**Using it in a lab**

- Desktop app for macOS (`.dmg`) and a Linux bundle; the `concord` command (start, stop,
  status, doctor, config, dataset, reproduce) ([INSTALL_MAC.md](docs/INSTALL_MAC.md),
  [LAB_SETUP.md](docs/LAB_SETUP.md)).
- Research sessions with a session log, export bundles and `concord reproduce`; safe stop;
  crash-safe recordings; retention and deletion; a support report without neural or
  personal data ([SECURITY.md](docs/SECURITY.md)).
- Communication board v2: five input methods (pointer and click, pointer with dwell
  selection, directional navigation, direct selection, scanning) chosen from what the source
  provides, and an opt-in desktop control bridge
  ([APPLICATIONS.md](docs/APPLICATIONS.md)).
- Compatibility registry: what each integration has been validated to, derived from the
  evidence ([COMPATIBILITY.md](docs/COMPATIBILITY.md)).
- Performance: 1024 channels at 30 kHz sustained for 10 minutes without loss on the test
  machine ([PERFORMANCE.md](docs/PERFORMANCE.md)).

**Verifying acquisition: `concord-hwval`**

- A toolkit that compares a Concord recording with the recording the acquisition system's
  own software made at the same time (LabRecorder XDF, Open Ephys Record Node) and writes a
  PASS / FAIL / INCONCLUSIVE report, plus the laboratory protocol for a hardware
  verification ([HARDWARE_VALIDATION.md](docs/HARDWARE_VALIDATION.md)). Exercised against
  the real LabRecorder and Open Ephys GUI with software sources.

**Fixes and changes found by that toolkit**

- Open Ephys: a sample-number reset while acquisition continues (the GUI's File Reader
  looping) no longer reconnects and loses about 0.7 s of data; the discontinuity stays
  visible ([OPEN_EPHYS.md](docs/OPEN_EPHYS.md)).
- Recording limits are configurable (default 300 s / 200 MiB with raw frames, up to 24 h /
  100 GiB); a recording stops cleanly when free disk space runs low.
- Recording headers keep the source's metadata at the start of a recording and state what
  their timestamps can reconstruct. Recordings with these fields need Concord 0.3.0 or later
  to open.

**Contract 1.4** (additive): navigation intents, `control.state`, `provenance.model_origin`,
the `spike_band_power` feature ([ARCHITECTURE.md](ARCHITECTURE.md)).

## Milestone 4 — integration ecosystem

- Source plugins through a public adapter SDK, each run in its own process
  ([ADAPTER_SDK.md](docs/ADAPTER_SDK.md)); BrainFlow and BCI2000 plugins
  ([ECOSYSTEMS.md](docs/ECOSYSTEMS.md)).
- Control bridge: decoded pointer / select / activate / cancel / text commands reach only
  the applications the operator authorizes, with stop paths
  ([CONTROL_BRIDGE.md](docs/CONTROL_BRIDGE.md)).
- Certification toolkit `concord-certify` ([CERTIFICATION.md](docs/CERTIFICATION.md)).
- Console redesigned as one session screen; the communication board opens as its own
  participant screen.

## Milestone 3 — live acquisition

- Live sources over Lab Streaming Layer and the Open Ephys ZMQ Interface
  ([LAB_GUIDE.md](docs/LAB_GUIDE.md), [OPEN_EPHYS.md](docs/OPEN_EPHYS.md)).
- Streaming processing pipeline, calibration of decoders from recordings, the command
  router, a center-out cue task ([BENCHMARKS_LIVE.md](docs/BENCHMARKS_LIVE.md)).

## Milestone 2 — genuine human intracortical data

- Recorded human intracortical data (FALCON H1, DANDI 000954) replayed through the
  unchanged runtime, every file verified by SHA-256 ([DATASETS.md](docs/DATASETS.md)).
- A baseline decoder evaluated without leakage, with controls
  ([DECODING.md](docs/DECODING.md)).

## Milestone 1 — MVP vertical slice

- Contracts (capabilities, event envelope, provenance), simulated devices (Simulated
  Profile A/B), the runtime, REST + WebSocket API, Python and TypeScript SDKs, the operator
  console and the communication board ([PRODUCT.md](PRODUCT.md),
  [ARCHITECTURE.md](ARCHITECTURE.md), [MVP_SPEC.md](MVP_SPEC.md)).
