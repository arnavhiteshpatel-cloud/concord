# Known limitations and incomplete functionality

Kept current with every change. If something here is fixed, move it to the changelog in
the PR description and delete it here.

## What is not real

- **No live implant connection.** Simulated Profile A and B are synthetic and do not model
  any commercial implant. The only genuine neural data is **offline replay** of published
  recordings (DANDI 000954). There is no hardware adapter, and nothing implies compatibility
  with any company's device.
- **Decoding is offline only.** The one decoder is a linear baseline trained and scored on
  recorded blocks (held-out R² ≈ 0.08–0.14, see docs/DECODING.md). It emits
  `intent.kinematics` (`decoded_intent`) only while replaying the block it was evaluated on.
  It is not a real-time BCI, it has never been run closed-loop, and it does not drive any
  application. Intents on the simulated devices remain `simulated_intent`.
- **Synthetic signal.** `recording.frame` data is Gaussian noise + sinusoids. Not
  physiological, not coupled to intents. Do not draw conclusions from it.
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
  runtime, and inject simulated intents. The server binds `127.0.0.1` by default and warns
  if bound elsewhere. Do not expose it to a network.
- No TLS, no audit log, no per-app grant approval, no signed adapters.
- Recordings are written unencrypted to `data/recordings/` (synthetic data only).

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
- **Recording limits**: 300 s or 200 MB per recording, then auto-stop. Re-recording a
  replay is not supported. Recordings cannot be deleted from the UI.
- **Replay** loops by default; speed control exists in the adapter but is not exposed in
  the API/UI.
- **Pause** discards packets at the runtime (simulators also stop generating). Discarded
  counts are shown; nothing is buffered for later.
- **Backpressure** drops the oldest events per slow subscriber; there is no per-app QoS or
  priority (e.g. "never drop selections").
- The board's **Speak** tile uses the browser's Web Speech API; it is labelled unavailable
  when the API is missing. Voice quality depends on the OS.
- The board is **not keyboard/mouse operable by design** (it is driven only by runtime
  events). It is not an accessibility-certified AAC product.

## Engineering gaps

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
- Benchmarks in `docs/BENCHMARKS.md` and decoding results in `docs/DECODING.md` were
  produced in a 4-vCPU Linux cloud container, **not on an M4 MacBook**. Decoding results are
  deterministic (same model id on rerun); timing numbers are machine-dependent, so run
  `make bench` locally for yours.
- npm uses `legacy-peer-deps` (frontend/.npmrc) to work around an npm 10 resolver bug with
  Vitest 4's optional peer dependencies; peers we need are pinned explicitly.
- No packaging/publishing of the SDKs yet (installed from the repo).
- Diagnostics are in-memory only and reset on restart.
