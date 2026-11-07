# Known limitations and incomplete functionality

Kept current with every change. If something here is fixed, move it to the changelog in
the PR description and delete it here.

## What is not real

- **No real devices.** Simulated Profile A and B are synthetic and do not model any
  commercial implant. There is no hardware adapter. Nothing implies compatibility with
  any company's device.
- **No neural decoding.** All intents are `simulated_intent`, produced from operator input
  (console pad / `/api/v1/sim/*`). The contract supports `decoded_intent` (requires a
  `model_id`), but no decoder exists.
- **Synthetic signal.** `recording.frame` data is Gaussian noise + sinusoids. Not
  physiological, not coupled to intents. Do not draw conclusions from it.
- **No real datasets.** Replay works only for BrainOS recordings made by this runtime.
  A public-dataset reader (e.g. NWB) is designed for (`ReplaySource`) but not implemented.

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

- **E2E test is not in CI yet.** `make e2e` (Playwright, AT-25) passes locally but CI runs
  only unit/integration tests, typecheck, and build.
- The TypeScript wire types are hand-maintained mirrors of the JSON Schema (drift is guarded
  only by review and the SDK tests, not by code generation).
- Benchmarks in `docs/BENCHMARKS.md` were measured in a 4-vCPU Linux cloud container,
  **not on an M4 MacBook**. Run `make bench` locally for your numbers.
- npm uses `legacy-peer-deps` (frontend/.npmrc) to work around an npm 10 resolver bug with
  Vitest 4's optional peer dependencies; peers we need are pinned explicitly.
- No packaging/publishing of the SDKs yet (installed from the repo).
- Diagnostics are in-memory only and reset on restart.
