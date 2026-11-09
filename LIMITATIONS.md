# Known limitations and incomplete functionality

Kept current with every change. If something here is fixed, move it to the changelog in
the PR description and delete it here.

## What is not real

- **No hardware has ever been connected.** Milestone 3 adds live-protocol adapters (LSL,
  Open Ephys ZMQ Interface). They are **protocol-tested** with software publishers and with
  real recorded data streamed as *prerecorded*; none has been run against acquisition
  hardware. Milestone 5's `concord-hwval` compared Concord with the real LabRecorder and the
  real Open Ephys GUI (File Reader input), i.e. reference *software* with software sources;
  the hardware procedure (docs/HARDWARE_VALIDATION.md) has never been carried out. See
  docs/VALIDATION_LEVELS.md. Nothing implies compatibility with any company's implant; there
  is no vendor adapter.
- **No human has used it.** Decoding, calibration, the command router, the board and the
  reference apps have never been used with a participant, live or closed-loop. Real-time
  decoding has been exercised on recorded human data replayed through the runtime (FALCON H1,
  T15 cursor + click, AJILE12 ECoG), where it reproduces the offline decoders exactly. That
  shows the software path, not BCI performance; open-loop numbers are not communication rates
  (docs/NEURAL_COMMUNICATION.md).
- **Decoders are classical.** Built in: ridge, LDA, a velocity Kalman filter and a logistic
  click decoder (M5); other families (ONNX, skops, TorchScript) load through the decoder SDK.
  Measured: held-out R² ≈ 0.08–0.14 within-day on FALCON H1 (docs/DECODING.md); on T15 cursor
  + click, Kalman angle error 28.0° vs 27.3° for the original online decoder
  (docs/CURSOR_CLICK.md). No cross-day, cross-participant or cross-modality transfer is
  claimed; a model from another source is refused unless the operator overrides (never across
  modalities), and the override is shown.
- **Synthetic signals.** Simulated Profile A/B frames are noise + sinusoids. The LSL/Open
  Ephys test publishers emit noise plus biphasic spikes whose rates are cosine-tuned to a
  latent velocity — enough to exercise the pipeline, not physiological. Do not draw
  scientific conclusions from them.
- **Real-data scope.** Readers: NWB spike-time `units` tables (FALCON H1 behavior layout),
  NWB raw-voltage `ElectricalSeries` in the layouts covered (AJILE12 ECoG, M5-B), and the T15
  cursor + click MATLAB blocks (M5-P0). Imaging and other layouts are refused with an explicit
  error.
- **Three datasets, one participant each.** FALCON H1 (intracortical, reach and grasp),
  T15 (intracortical, speech motor cortex, cursor + click; day 468 evaluated), AJILE12 sub-07
  (ECoG, natural reaching). All results are within-participant and offline/open loop.
  See docs/DATASETS.md, docs/CURSOR_CLICK.md, docs/ECOG.md.
- **Dataset is a DANDI draft.** 000954 has no published version; Concord pins every file by
  SHA-256, so a changed upstream file fails verification instead of silently changing results.

## Security (local demo only)

- **No authentication or authorization.** Any local process can connect, control the
  runtime (including configuring sources, pipelines and the command router), and inject
  simulated intents. The server binds `127.0.0.1` by default and refuses any other
  address unless `allow_remote` is set (M5-D). Do not expose it to a network.
- No TLS, no audit log, no signed adapters. Operator authorization of applications for
  decoded commands (M4) is keyed by the application id each client declares itself: it
  prevents mistakes (an app receiving commands nobody meant for it), not a malicious local
  process that claims another app's id. Authorizations are in memory and not persisted.
- Recordings are written unencrypted to `data/recordings/`. With live sources they can
  contain real neural data: handle the directory under your research data policy.
- LSL discovery uses liblsl's multicast/broadcast on the local network, and any host on that
  network can publish a stream Concord will list. A stream's self-declared metadata
  (including "prerecorded"/"synthetic") is trusted as declared; an undeclared stream is
  labelled "origin unverified", not "live hardware".
- The Open Ephys heartbeat sends a small JSON message to the plugin's REP port; no other
  data is sent to acquisition software.

## Functional gaps

- **One device at a time.** No concurrent multi-device sessions.
- **Switching is disconnect + connect.** Apps see a brief `no_device` negotiation during a
  switch (measured switch duration ≈ 10–15 ms on the dev machine; see Diagnostics).
- **Clock model is naive.** Device timestamps are passed through and regressions are
  flagged; there is no device↔runtime clock-offset estimation or drift correction.
- **Pipeline latency includes intra-tick queueing.** Pointer packets produced in the same
  scheduler tick as a 32×40 recording frame wait for it to be processed (p50 ≈ 0.24 ms on
  the dev container). Not optimized.
- **Rolling rates** in Diagnostics use a 5 s window with a 1 s floor; they under-report
  during the first second after a connect.
- **Recording limits**: by default 300 s or 200 MiB per recording, then a clean auto-stop
  (the file is complete and replayable); with `exclude_raw` (features + labels only) 3600 s.
  Configurable in `[recording]` of the config file or `CONCORD_RECORDING_MAX_S` /
  `_MAX_NO_RAW_S` / `_MAX_MB` / `_MIN_FREE_MB`, up to 24 h and 100 GiB per recording; a
  recording refuses to start, or stops cleanly, below 256 MiB free disk space. There is no
  automatic segmentation into several files: one recording is one file. Recordings are JSON
  text, much larger than the binary samples: raw 30 kHz × 96 ch frames reach 200 MiB in
  seconds, so use LabRecorder/Open Ephys for raw archival. Re-recording a local file replay is not
  supported.
- **Timing in recordings**: a `recording.frame` stores the source-clock time of its first
  sample (`device_timestamp_ns`) and the host ingest time; later samples are placed at the
  nominal rate. Per-sample source timestamps inside a frame (LSL per-sample stamps and their
  jitter) are not stored and cannot be reconstructed; Open Ephys frames keep exact sample
  numbers. The header states this (`timing`) and keeps the adapter's source metadata at the
  start of the recording (`source_metadata`: LSL uid, source_id, host, time correction;
  Open Ephys host/ports/stream); integrity counters at the end are in diagnostics, not the
  header. Recordings with these header fields cannot be opened by Concord builds before
  Milestone 5 (the header model forbids unknown keys).
- **Replay** loops by default (no UI toggle). Speed is adjustable 0.1–64× via
  `/api/v1/runtime/playback` (console offers 0.5–8×). Seeking to a position is not supported.
- **Pause** discards packets at the runtime (simulators also stop generating). Discarded
  counts are shown; nothing is buffered for later.
- **Live sources (M3)**:
  - One signal stream per source. Behavior/marker streams can be attached to an LSL signal;
    two signal streams cannot be merged.
  - Reconnect uses the runtime policy (3 attempts, ≈ 1.7 s total). An acquisition app that
    restarts more slowly ends in `error`; reconnect manually.
  - After a reconnect the pipeline continues with its previous filter/threshold state; the
    first frame after a gap is flagged `dropped_samples`, but filters see a discontinuity.
  - Open Ephys: data received while the adapter learns the stream layout (≥ 0.5 s on every
    open/reconnect) is not emitted; a block missing any channel is dropped (counted); a
    spike from a new electrode forces a reconnect unless electrodes are configured. The
    adapter needs the plugin's per-channel format exactly as documented in docs/OPEN_EPHYS.md.
  - LSL timestamps are the source's; behavior/markers are mapped with liblsl
    `time_correction` (accuracy as liblsl's, typically sub-millisecond on a LAN, not
    verified by us across machines).
- **Source plugins (M4)**: see docs/ADAPTER_SDK.md §5 for exactly what is isolated.
  - **Fault isolation, not a security sandbox.** A plugin runs in its own process but as the
    same user with the same file, network and process permissions as Concord; there are no
    CPU/memory limits. `manifest.network` is a declaration, not enforced. Installing a plugin
    means trusting its code like any Python package in Concord's environment.
  - What a plugin declares (synthetic / prerecorded, units, modality, origin, clock) is shown
    as declared, never verified. Undeclared modality is shown as "modality not declared".
  - One stream per role is delivered; additional streams of a role are listed as not
    delivered. All streams of a session must share one clock domain (mixed clocks are
    rejected; API 1.0 has no offset estimation). Non-finite values are rejected (a plugin
    cannot mark individual behavior samples invalid).
  - Every connection and reconnect starts a fresh host process (≈ 0.2 s with numpy). The
    reconnect policy is the runtime's (3 attempts); a plugin that fails 3 sessions in a row
    without delivering data, or violates the contract, is stopped until reconfigured.
  - Request/response IPC (one outstanding `read`, 0.1 s plugin wait): adds ≈ 0.3–2.5 ms per
    read round trip on the dev container; measured ceiling 28–72× real time for 64 ch × 30 kHz
    float32 (docs/ADAPTER_SDK.md §6). Converting frames to JSON events is the slower step.
  - Discovery runs at startup in the background and on demand ("Search again"); a package
    installed while Concord runs is not seen until then. Configured plugin devices and options
    are in memory only (lost on restart).
  - If the runtime process is killed hard, a plugin blocked inside `read()` exits only when that
    call returns; processes a plugin itself starts are not tracked.
  - The example adapter generates synthetic EEG at 250 Hz; the pipeline's default 50 ms bin is
    not a whole number of samples at 250 Hz, so the operator must set e.g. 40 or 100 ms.
- **Pipeline (M3)**: one pipeline at a time, in the runtime process (Python, single asyncio
  task). Measured headroom on a 4-vCPU container: 96 ch × 30 kHz at ≈ 50 % of one core
  (docs/BENCHMARKS_LIVE.md); larger arrays need measuring. Threshold RMS is estimated once
  (first second) and not adapted. Decoders: ridge (continuous) and shrinkage LDA (classes).
- **Control bridge (M4)**: discrete decoding has been exercised only on synthetic
  motor-imagery-like data generated in the tests (a mu-band decrease put there on purpose;
  held-out balanced accuracy 0.66 vs chance 0.33 is a software check, not a result). The
  discrete rules are fixed thresholds on posteriors; no adaptive thresholds, no error
  correction, no "no-control" state detection beyond a class the operator leaves unmapped.
  The pointer and discrete paths cannot be combined from one decoder (a decoder is either
  continuous or a classifier). Simulated Profile A/B intents are not subject to authorization
  (they are `simulated_intent`, driven by the operator's simulator controls). The SDK guard's
  wall-clock staleness check assumes the runtime and the app share a clock (disable it
  across machines; the relative-delay check still applies). The communication board does not
  use the SDK guard yet.
- **Calibration (M3)**: offline fit from closed recordings (no adaptive/online
  recalibration). Labels are the nearest behavior sample within half a bin. The center-out
  task's display latency is not measured, so cue timing on screen vs. on the LSL clock may
  differ by a monitor frame or more.
- **Console**: live-source counters and the pipeline status are polled once per second
  (up to ~1 s old). The signal-integrity verdict uses only what the console can measure: data
  events arriving in this browser tab, the runtime state, and loss counters reported by the
  adapter, pipeline and runtime; "Data received" is shown only for LSL (samples vs estimated
  missing) and Open Ephys (messages vs missed), never estimated for other sources. The four
  live traces show raw samples (first four channels) or binned counts (the four most active
  channels); `features.vector` output (band power, high gamma) appears only in the event
  stream. The status line does not show the reconnect attempt number (the runtime does not
  report it per attempt). Discovery uses a fixed 1.5 s wait. The Playwright demo exercises
  LSL discovery → registration → connect → spikeband pipeline, Open Ephys registration →
  connect, and real data over LSL → passthrough + trained model → Start control → title-bar
  Stop control; calibration is covered by component tests with a mocked server and by
  backend tests, not by the browser demo.
- **Backpressure** drops the oldest events per slow subscriber; there is no per-app QoS or
  priority (e.g. "never drop selections").
- The board's **Speak** tile uses the browser's Web Speech API; it is labelled unavailable
  when the API is missing. Voice quality depends on the OS.
- The board is **not keyboard/mouse operable by design** (it is driven only by runtime
  events). It is not an accessibility-certified AAC product.

## Console rough edges (0.3.1)

These are known and documented in the guides; none affects what Concord receives or decodes.

- **T15 cursor + click blocks have no dataset panel** in Advanced → Acquisition details. Their
  checksum is verified when you connect, but the console shows no checksum line, license or
  citation for them (FALCON and AJILE12 have it). The citation is in docs/DATASETS.md.
- **T15 blocks have no playback speed or position**, only Pause and Resume (under *Options*). They
  replay at real speed.
- **Replays loop** at the end of the file, without a log entry.
- **The board preview in Advanced counts as a connected application.** The console therefore
  lists a *Communication Board* before you open the participant screen, and two once you have.
  Both share one authorization.
- **Stored data does not list downloaded datasets**; delete them from the datasets folder.
- The FALCON source is named *Recorded Human Intracranial Data* while its sub-line says
  *Intracortical*: intracortical recordings are intracranial ones, but the two words are not
  used consistently.

## Engineering gaps

- The Open Ephys conformance test downloads the official GPL client from GitHub at test
  time (SHA-256 pinned) and skips if offline or if ports 5556/5557 are busy.
- **CI downloads ~8.7 MiB from DANDI per run** (cached by manifest hash). If DANDI is
  unreachable, CI fails rather than skipping real-data tests (by design).
- **Old (0.1) SDK clients** parse device descriptors with a closed capability enum, so they
  cannot list or receive runtime snapshots that contain the 1.1 capabilities. Their event
  streams are unaffected (they never receive 1.1 event types). Upgrade SDKs together with
  the server.
- **Opening a dataset file** takes ~0.1–0.3 s (it runs off the event loop), and the spike
  times for one block are held in memory (~5 MB). Very long recordings would need a
  streaming spike reader.
- The TypeScript wire types are hand-maintained mirrors of the JSON Schema (drift is guarded
  only by review and the SDK tests, not by code generation).
- Benchmarks in `docs/BENCHMARKS.md`, `docs/BENCHMARKS_LIVE.md` and decoding results in `docs/DECODING.md` were
  produced in a 4-vCPU Linux cloud container, **not on an M4 MacBook**. Decoding results are
  deterministic (same model id on rerun); timing numbers are machine-dependent, so run
  `make bench` locally for yours.
- npm uses `legacy-peer-deps` (frontend/.npmrc) to work around an npm 10 resolver bug with
  Vitest 4's optional peer dependencies; peers we need are pinned explicitly.
- Nothing is published to PyPI yet: wheels are built from the repo (M5-D: `concordos[lab]`,
  the desktop bundle). `concordos[server]` depends on `concord-adapter-sdk`, which must be
  built or installed from `packages/` first (`make setup` does).
- Diagnostics are in-memory only and reset on restart.

## Ecosystem plugins (Milestone 4, `concord-brainflow`, `concord-bci2000`)

See docs/ECOSYSTEMS.md for details and evidence.

- Neither plugin has been run with acquisition hardware. BrainFlow was exercised only with
  its synthetic, playback-file and streaming boards (and a real driver's failure path);
  BCI2000 only with a locally built SignalGenerator + DummySignalProcessing +
  DummyApplication from a public source fork (bci2000.org was not reachable).
- Run through the plugin host and the runtime by `test_plugin_ecosystems.py` and by
  `concord-certify` (docs/COMPATIBILITY.md): BrainFlow with its synthetic board, BCI2000 with
  a replayed capture of genuine BCI2000 output (not live BCI2000).
- BrainFlow: only the DEFAULT preset is read; board configuration (`config_board`) is not
  offered (it writes to the device); BrainFlow markers cannot reach a read-only consumer
  (BrainFlow overwrites the marker row), so there is no markers stream; units are taken from
  BrainFlow's docs ("uV wherever possible" for EXG) and unknown otherwise; channels BrainFlow
  lists under several types are typed as ambiguous with modality unknown; package-counter
  loss inference assumes a 0-255 counter unless the operator sets `package_num_modulus`.
- BCI2000: only the App Connector output is used — processed control information (control
  signal + states), never raw signal (raw signal would need the FieldTripBuffer route, not
  implemented). Blocks whose datagrams are all lost are undetectable (no block counter on the
  wire). `synthetic`/`prerecorded` are operator declarations (App Connector does not reveal
  BCI2000's source module). The live test against BCI2000 is opt-in (`BCI2000_PROG_DIR`); CI
  replays a capture recorded from that build.

## Certification toolkit (Milestone 4, `concord-certify`)

See docs/CERTIFICATION.md §6.

- Software checks only. It grants `adapter_implementation` by itself; `protocol_tested` rests
  on the operator's statement of which reference software produced the data (checked only for
  consistency with the declared ecosystem, origin and installed version); `hardware_tested` on
  an operator-signed attestation whose signature and plugin identity are verified but whose
  hardware claims are not; `human_participant_validated` is never set.
- Certifies plugins only; built-in adapters are covered by their own test suites.
- A plugin's declarations (synthetic / prerecorded, origin, units, modality) are checked for
  consistency, not truth. Timing numbers are machine-dependent; latency only for `unix` / `lsl`
  clocks; CPU / RSS need Linux `/proc`. Thresholds (±2 % rate, one sample period of jitter,
  1000 ppm drift) are engineering choices, not standards.
- The fault-injection test kills the plugin host; it does not simulate a device disappearing.
- Attestation signatures need the `openssl` command (OpenSSL 3, Ed25519).
- No plugin for real acquisition hardware has been certified; the committed reports
  (docs/compatibility/) are for a synthetic generator, BrainFlow's synthetic board and a
  replayed BCI2000 capture.


## Cursor + click decoding and neural-to-communication (Milestone 5, P0)

See docs/CURSOR_CLICK.md (generated by `make cursorclick-report`) for every number and the
protocol.

- **Open loop only.** All T15 results decode *recorded* closed-loop sessions. The participant
  was correcting the original research decoder's cursor, not Concord's; no person has ever
  controlled anything with a Concord decoder. Open-loop numbers are not communication rates.
- **One participant, one day.** Day 468 of participant T15 (18 blocks). Days 39 and 202
  (no click) are downloadable but not evaluated. Decoders are trained and tested within
  that day (different blocks, test always recorded later), as the original online decoders
  were; no cross-day or cross-participant use is supported or claimed.
- **Labels are inferred.** Cursor intention is the ReFIT-style direction to the cued target
  with the original decoder's speed; click intention is "cursor on the target" (the task
  instruction). Neither is observed directly.
- **Whole-block replay through the board drifts.** Integrating a velocity stream open loop
  accumulates error trial after trial. Even the original decoder's own recorded outputs,
  integrated by the board, select the cued word in only 65 % of trials on the 14 x 14 grid
  (the session itself: 94 %); Concord's decoders through the board are near chance on fine
  boards (14 x 14: 1 %, chance 0.5 %; 2 x 2: 44 %, chance 25 %). Per-trial anchoring to the
  recorded cursor position (which reproduces the session) is an offline analysis and is never
  fed to an application: recorded positions are behavioral labels, never commands.
- **Historical outputs are not Concord.** The original decoders' outputs are replayed as
  `decoded_intent` with `model_origin: historical` and are labelled as the original research
  system's in the board and console.
- **Dryad access.** Downloads need a Dryad API token (free account) or browser download plus
  `--verify`. CI runs the T15 real-data tests only when the repository has the
  `DRYAD_CLIENT_ID` / `DRYAD_CLIENT_SECRET` secrets; without them the tests are skipped with a
  warning annotation.
- **SBP unit unknown.** The dataset does not state the unit of the filtered signal behind spike
  band power; it is declared `arbitrary^2`.

## Human ECoG (Milestone 5, workstream B)

See docs/ECOG.md §9 for details.

- **Offline replay only.** The ECoG source is a recording (AJILE12, DANDI 000055) made during
  clinical epilepsy monitoring; no live ECoG source has been connected to Concord.
- **One participant (sub-07), 78.75 minutes from three days**, chosen as the densest windows of
  curated reach events. Results do not transfer to other participants, implants or tasks.
- **Movement vs rest only.** The classifier detects curated arm reaches against periods with both
  wrists still; it also fires during unlabelled behavior (P(move) > 0.5 in 11–15 % of all
  held-out bins) and yields 3.7–6.1 false onsets per minute of labelled rest at a 0.5 threshold.
  Reach direction and continuous wrist velocity were not attempted.
- **No low-frequency / LMP feature:** the 1.4 contract has no feature name for a signed
  low-pass amplitude; adding one needs a schema minor bump.
- The data was already notch-filtered (60/120/180 Hz) and low-passed (250 Hz) by the dataset
  authors; Concord's notch has not been exercised on un-notched real ECoG.
- The AJILE12 files store no channel names, no anatomical locations and no coordinate space;
  Concord labels channels `<group>/<id>` and reports coordinates as stored. Pose is in video
  pixels (declared `meters` with `conversion` NaN in the file) and is reported as `arbitrary`.
- The source files (~10 GB each) are never downloaded whole: their SHA-256 is DANDI's metadata,
  checked at fetch time; Concord verifies the slices it uses by their own digests.
- Raw-voltage NWB files other than AJILE12 extracts are supported only in the layouts the
  synthetic fixtures cover (one regularly sampled `ElectricalSeries`, an electrodes table,
  optional Position pose and interval tables); explicit timestamps are refused.
- An unverified raw-voltage NWB file has no declared modality (`null`); models with a declared
  modality then load with a warning only (feature, channel, source and session checks still
  apply).

## Compatibility registry (Milestone 5, workstream F)

See docs/COMPATIBILITY.md, "Registry (M5-F)".

- The registry verifies that evidence exists and says what it claims (paths, anchor texts,
  certify-report consistency, plugin versions and source hashes). It does not re-run tests or
  read test results: a counted test is one CI runs (and fails on), or an opt-in test whose
  execution a document records. Dates of curated tests, benchmarks and documents are curated.
- A "protocol-level" test is one whose curated entry names the reference stack and whose file
  contains the given anchor; the anchor ties the claim to the file, it does not prove the test
  exercises that stack.
- The BCI2000 certify report predates a change to the plugin's source (an open-error hint), so
  it is listed and not counted until concord-certify is re-run; BCI2000's level 2 rests on the
  opt-in live test recorded in docs/ECOSYSTEMS.md.
- Plugins outside this repository cannot be hash-checked: their reports count for the version
  they name. Built-in adapters carry the Concord package version, not a per-adapter version.
- Live status (`GET /api/v1/compatibility`) reports installed / different version /
  unavailable for this installation; for plugins it needs a completed plugin discovery.
- The T15 cursor+click adapter is listed as not in this checkout until workstream P0's code is
  merged; its evidence entries (`compat/sources.json`) are read and verified only then.

## Application layer (Milestone 5, workstream C)

See docs/APPLICATIONS.md.

- The communication board, the reference apps and the desktop bridge have been exercised with
  simulated intents, a synthetic motor-imagery source + LDA, and a scripted test source with a
  hand-written identity *test* decoder — never with a participant, and not as assistive
  technology. No usability, accessibility or clinical evaluation was done.
- `control.state` reasons are text for people; apps must not parse them. Notices are per
  connection and are not stored in session recordings.
- Feeding a source's own recorded decoder outputs (`model_origin: historical`) or an external
  live decoder's outputs into the command router is not wired: the router takes only the
  running pipeline decoder's output. Apps already label historical / external provenance.
- The router's click rule needs a decoder output that is a click probability or a 0/1
  decision; Concord does not check that a continuous output really is one.
- Board: word prediction is a fixed 200-word list (no language model); speech is the
  browser's Web Speech API (voices and availability vary; "computer speech, not neural speech
  decoding"); the audio tick needs Web Audio; settings are stored per browser; the
  `window.__concordBoard` snapshot is for tests and evaluation and copies up to 5000
  selections per read. Reproducing an original cursor trajectory on the task grid is exact
  only up to the first pointer event after a (re)start (it sets the clock) and clamping.
- Direct selection is chosen automatically only after a source sent `activate`/`cancel`
  (capability parameters such as the router's `actions` are not visible to apps).
- Desktop bridge: relative pointer moves and a primary click only (no keys, scrolling,
  dragging); focus restriction only with the `xdotool` backend (X11 window titles); no
  accessibility-API integration (UI Automation, AX, AT-SPI), so it cannot know what a click
  will do; the `pynput` backend was not tested here; `xdotool` does not work on Wayland.

## Decoders and model ecosystem (Milestone 5, workstream A)

- **Not a security sandbox.** Decoder plugins and model files run in a separate process
  (fault isolation: crash, hang, garbage and invalid outputs are contained and reported). That
  process has the same user, files and network as Concord. A malicious plugin, or a pickle
  the operator trusted, can do anything that user can.
- Trust decisions are recorded per file (SHA-256, who, when). Concord has no user accounts,
  so "who" is what the operator types or "operator".
- **TorchScript** is deprecated upstream (PyTorch 2.x). It is supported but not recommended;
  ONNX or safetensors are preferred. Torch is an optional extra and is not installed by
  `make setup` (the CPU wheel needs a dedicated index). Without it, the TorchScript /
  safetensors tests skip with a reason. They were run here with torch 2.15 (CPU).
- Only two safetensors architectures exist (`linear`, `gru`). Other PyTorch models must be
  exported to ONNX or TorchScript.
- **The drift thresholds are heuristics** (feature shift 0.5 SD RMS, 25 % of channels > 1 SD,
  variability × 1.5, half the held-out margin). They are tested only on deliberately shifted
  versus unshifted synthetic streams, and are not validated against closed-loop performance
  or real non-stationarity. Models trained before Milestone 5 lack `feature_stats`, so their
  feature drift is reported as unavailable.
- **Calibration records the preset only when known.** Recordings do not carry the pipeline's
  processing parameters. Models calibrated from recordings declare their feature, bin, unit,
  band and channel labels, but not `threshold_k` or the preset. A spike-band model
  calibrated at one threshold is not refused at another.
- **The click calibration metric** uses a plain 0.5 threshold crossing within ±300 ms. The
  router's hold / refractory / hysteresis rules, which decide the actual clicks, are not part
  of the offline score.
- **Decoded passthrough** routes the source's decoder outputs as they are.
  - Without a declared `scale`, the pointer gain applies to raw values.
  - Only `historical` and `external` origins are accepted.
  - Concord cannot verify that a source's declared model origin is true.
- **The example decoder is hand-set** (not trained) and only shown above chance on Concord's
  synthetic motor-imagery generator. It is a teaching example, not an EEG decoder.
- The decoder-host IPC round trip per step is not benchmarked here (workstream E).

## M5-D: installation, desktop app, researcher workflow, security

- **The macOS app has been built and smoke-tested only on GitHub Actions `macos-latest`**
  (Apple Silicon runners; job `package-macos`), never installed by hand on a physical Mac or
  used with equipment. The identical bundle layout is built and smoke-tested on Linux
  (`package-linux`, and locally). Apple Silicon and macOS 14 or later only (the bundled
  numpy/scipy wheels require it); Intel Macs and older macOS use the pip installation.
- **Unsigned and not notarized** (ad-hoc signature only): Gatekeeper blocks the first launch
  until the user allows it (docs/INSTALL_MAC.md). No auto-update.
- The app bundles Concord's built-in sources and the BCI2000 plugin. BrainFlow and other
  plugins need the pip installation (a frozen app cannot install packages); their wheels are on
  the release page. The test publishers are available from the app's own program since 0.3.1
  (`Concord publish …`).
- The status window needs Tk; where no window can be created the app runs without it (quit
  with `Concord stop`). The Apple Event quit is tested on CI only if the runner permits
  sending Apple Events; otherwise the job falls back to SIGTERM and says so.
- **Security**: see docs/SECURITY.md. No authentication or TLS; any local process (including
  other users') can use the API; no encryption at rest; deletion is not secure erasure;
  plugins are not sandboxed. Browser cross-site / DNS-rebinding requests are refused, but a
  local web server on a loopback port is treated like any other local program.
- **Crash recovery** loses at most the last ~0.25 s of a recording (the flush interval) plus
  what the operating system had not written to disk at a power loss (no fsync per event).
- **Session log** records operator actions through the API while a session is active; it is
  not tamper-proof, does not identify who acted, and does not record actions while no
  session is active. Simulated pointer/select/text inputs and free-text stop reasons are not
  recorded.
- **`concord reproduce`** re-fits calibrated decoders from bundled recordings and recomputes
  recorded *linear* decoder output; classifier (LDA) output and command-router output are not
  recomputed, and models trained outside a session (e.g. `make model` on FALCON H1) are
  reproduced only from the dataset, not from the bundle. Identical model ids need the same
  numerical libraries; other builds may differ in the last digits (reported with tolerances).
- Retention runs only at server start; it does not delete while Concord runs.
- The lab acceptance test (`scripts/lab_acceptance.py`) approximates an outside lab on one
  machine with software publishers and the FALCON H1 file; it is not a test with acquisition
  hardware or a participant.

## Performance at scale (Milestone 5, workstream E)

See docs/PERFORMANCE.md and docs/BENCHMARKS_SCALE.md for the measurements.

- **Measured on one shared 4-vCPU Linux cloud VM** while other workloads ran (load averages
  are recorded with every run), with benchmark-generated synthetic streams and random-weight
  decoders. Not measured on macOS or Windows, on real acquisition hardware, or over a network.
- **Raw signal is limited to 1024 channels** by contract 1.4 (`recording.frame`
  `channel_count <= 1024`). A 2048- or 4096-channel raw stream connects, but every frame is
  rejected (validation errors) and nothing reaches the pipeline, while the runtime still
  spends most of a core receiving and rejecting it. Binned features (`features.binned` /
  `features.vector`) are allowed up to 4096 channels and were measured there.
- **One device per runtime process; one core per runtime.** Acquisition, validation, DSP,
  decoder, router and WebSocket share one asyncio loop. More devices means more runtime
  processes (each with its own port and console); nothing coordinates them.
- **Raw-signal viewers are expensive.** Raw frames go to WebSocket clients as JSON
  (~20 ns of CPU per value to encode, plus the client's parse). At 256+ channels a Python
  SDK client cannot keep up with 30 kHz raw and the runtime drops (and counts) frames for it;
  at 1024 channels a raw viewer costs the runtime a large share of its core and delays other
  apps' events. There is no decimated preview stream and no binary encoding yet.
- **The liblsl inlet buffer is time-based (30 s), not byte-based**: a stalled runtime can
  let liblsl hold several GB at 1024 channels x 30 kHz before samples are dropped.
- Queue byte budgets are estimates (sample-array size, or 512 bytes for small events).
- `make dev` and the test servers keep uvicorn's WebSocket permessage-deflate default; only
  `python -m concord.server` (`make run`, packaging) disables it.
- Without orjson (an exotic platform without wheels) raw-frame JSON falls back to pydantic's
  encoder: identical output, about 2.5x slower per value.
- The numba and C SOS-filter prototypes in the benchmark are not shipped; the DSP is scipy.

## Acquisition verification toolkit (`concord-hwval`, Milestone 5)

- Software-level evidence only: LabRecorderCLI 1.16.4 / liblsl 1.16.2 with a declared-synthetic
  LSL publisher, and Open Ephys GUI 1.1.0 + ZMQ Interface 1.0.0 with its File Reader. No
  amplifier, acquisition board, signal generator or TTL source has been used; no report may be
  read as hardware verification (`hardware_verified` is always false; a person signs off
  level 3, §9 of docs/HARDWARE_VALIDATION.md).
- The reference-software tests run on Linux x86_64 only (they download the official Linux
  packages; the GUI runs headless under Xvfb with a PulseAudio null sink). The comparison
  itself (numpy + pyxdf) runs anywhere Python 3.11+ does.
- Thresholds (loss tolerance, value tolerance, delay) are engineering choices, not standards.
- Without the `capture` sidecar the absolute Concord-vs-source latency is not reported (only
  delay relative to the best case); the stream is still identified by the LSL uid kept in the
  recording header.
