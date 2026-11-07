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
- **Pipeline (M3)**: one pipeline at a time, in the runtime process (Python, single asyncio
  task). Measured headroom on a 4-vCPU container: 96 ch × 30 kHz at ≈ 50 % of one core
  (docs/BENCHMARKS_LIVE.md); larger arrays need measuring. Threshold RMS is estimated once
  (first second) and not adapted. Only ridge models; the router maps two decoded dimensions
  to `intent.pointer` only (no decoded selection/text).
- **Calibration (M3)**: offline fit from closed recordings (no adaptive/online
  recalibration). Labels are the nearest behavior sample within half a bin. The center-out
  task's display latency is not measured, so cue timing on screen vs. on the LSL clock may
  differ by a monitor frame or more.
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
- No packaging/publishing of the SDKs yet (installed from the repo).
- Diagnostics are in-memory only and reset on restart.
