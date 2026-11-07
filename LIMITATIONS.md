# Known limitations and incomplete functionality

Kept current with every change. If something here is fixed, move it to the changelog in
the PR description and delete it here.

## What is not real

- **No hardware has ever been connected.** Milestone 3 adds live-protocol adapters (LSL,
  Open Ephys ZMQ Interface). They are **protocol-tested** with software publishers and with
  real recorded data streamed as *prerecorded*; none has been run against acquisition
  hardware or the real Open Ephys GUI. See docs/VALIDATION_LEVELS.md. Nothing implies
  compatibility with any company's implant; there is no vendor adapter.
- **No human has used it.** Decoding, calibration, the command router and the reference app
  have never been used with a participant, live or closed-loop. Real-time decoding has been
  exercised only on FALCON H1 blocks streamed as prerecorded data, where it reproduces the
  offline decoder exactly. That shows the software path, not BCI performance.
- **Decoders are linear baselines.** Ridge regression on causally filtered features
  (held-out R² ≈ 0.08–0.14 within-day on FALCON H1, docs/DECODING.md). No cross-day,
  cross-participant or cross-modality transfer is claimed; a model from another source is
  refused unless the operator overrides, and the override is shown.
- **Synthetic signals.** Simulated Profile A/B frames are noise + sinusoids. The LSL/Open
  Ephys test publishers emit noise plus biphasic spikes whose rates are cosine-tuned to a
  latent velocity — enough to exercise the pipeline, not physiological. Do not draw
  scientific conclusions from them.
- **Real-data scope.** The NWB reader supports spike-time `units` tables, plus the FALCON H1
  behavior layout. Raw voltage (`ElectricalSeries`), LFP/ECoG, imaging and processed-only
  files are rejected with an explicit "unsupported modality" error. Behavior is read only from
  the FALCON H1 layout; other datasets replay neural features without behavior.
- **One dataset, one participant.** FALCON H1 is one person, one cued task, within-day
  blocks. Kinematics are cued, in arbitrary units. No electrode geometry is available.
  See docs/DATASETS.md.
- **Dataset is a DANDI draft.** 000954 has no published version; BrainOS pins every file by
  SHA-256, so a changed upstream file fails verification instead of silently changing results.

## Security (local demo only)

- **No authentication or authorization.** Any local process can connect, control the
  runtime (including configuring sources, pipelines and the command router), and inject
  simulated intents. The server binds `127.0.0.1` by default and warns
  if bound elsewhere. Do not expose it to a network.
- No TLS, no audit log, no per-app grant approval, no signed adapters.
- Recordings are written unencrypted to `data/recordings/`. With live sources they can
  contain real neural data: handle the directory under your research data policy.
- LSL discovery uses liblsl's multicast/broadcast on the local network, and any host on that
  network can publish a stream BrainOS will list. A stream's self-declared metadata
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
- **Recording limits**: 300 s or 200 MB per recording, then auto-stop; with
  `exclude_raw` (features + labels only) 3600 s. Raw 30 kHz × 96 ch frames as JSON reach
  200 MB in seconds — use LabRecorder/Open Ephys for raw archival. Re-recording a local file
  replay is not supported. Recordings cannot be deleted from the UI.
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
    same user with the same file, network and process permissions as BrainOS; there are no
    CPU/memory limits. `manifest.network` is a declaration, not enforced. Installing a plugin
    means trusting its code like any Python package in BrainOS's environment.
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
    installed while BrainOS runs is not seen until then. Configured plugin devices and options
    are in memory only (lost on restart).
  - If the runtime process is killed hard, a plugin blocked inside `read()` exits only when that
    call returns; processes a plugin itself starts are not tracked.
  - The example adapter generates synthetic EEG at 250 Hz; the pipeline's default 50 ms bin is
    not a whole number of samples at 250 Hz, so the operator must set e.g. 40 or 100 ms.
- **Pipeline (M3)**: one pipeline at a time, in the runtime process (Python, single asyncio
  task). Measured headroom on a 4-vCPU container: 96 ch × 30 kHz at ≈ 50 % of one core
  (docs/BENCHMARKS_LIVE.md); larger arrays need measuring. Threshold RMS is estimated once
  (first second) and not adapted. Only ridge models; the router maps two decoded dimensions
  to `intent.pointer` only (no decoded selection/text).
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
- No packaging/publishing of the SDKs yet (installed from the repo). `brainos` now depends on
  `brainos-adapter-sdk`, which must be installed from `packages/` first (`make setup` does).
- Diagnostics are in-memory only and reset on restart.

## Ecosystem plugins (Milestone 4, `brainos-brainflow`, `brainos-bci2000`)

See docs/ECOSYSTEMS.md for details and evidence.

- Neither plugin has been run with acquisition hardware. BrainFlow was exercised only with
  its synthetic, playback-file and streaming boards (and a real driver's failure path);
  BCI2000 only with a locally built SignalGenerator + DummySignalProcessing +
  DummyApplication from a public source fork (bci2000.org was not reachable).
- Not yet wired through the plugin host / runtime (built in parallel); tested directly
  through the public adapter API.
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
