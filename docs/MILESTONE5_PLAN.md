# Milestone 5 — plan

Universal platform, genuine neural communication, research-ready release.

## What exists (verified on main @ 658a592)

Contracts 1.3 (now 1.4), runtime, Python/TS SDKs, simulated profiles, FALCON H1 (DANDI
000954) replay + ridge decoder, LSL and Open Ephys adapters, causal processing pipeline,
regression + LDA calibration, command router with operator authorization, `CommandGuard`,
adapter SDK + isolated plugin host, BrainFlow and BCI2000 plugins, `brainos-certify`,
cursor/menu reference apps, communication board + participant window, single-screen console,
CI (backend, distribution, frontend, e2e). **Not present:** any desktop packaging (verified in
M2/M3/M4 plans: no Tauri/packaging files ever existed), a decoder plugin interface, Kalman
decoders, a cursor-and-click dataset, ECoG support.

## Contract 1.4 (done, additive)

- `navigation` / `intent.navigate {direction: up|down|left|right|next|previous, confidence}`.
- `control_status` / `control.state {active, capabilities, reason}` (runtime → one app).
- `provenance.model_origin`: `brainos` (a model BrainOS trained or loaded), `external` (a live
  external decoder, e.g. BCI2000 or a device's own), `historical` (recorded outputs of a
  research system's original online decoder; must be `replayed`). Only for `decoded_intent`.

## Workstreams and ownership

| ID | Priority | Scope | Owns (others avoid) |
| --- | --- | --- | --- |
| P0 | P0 | Singer-Clark et al. cursor+click dataset (Dryad doi:10.5061/dryad.prr4xgxzq, CC0): pinned subset download, importer, Kalman/ridge cursor decoders, click decoder, three modes (historical replay / BrainOS inference / live), neural-to-communication evaluation | `datasets/` manifests for it, `adapters/cursorclick/`, `decoding/kalman.py`, `decoding/click.py`, `evaluation/` |
| A | P1 | Decoder plugin SDK + model families (builtin, Kalman, sklearn via skops, ONNX, TorchScript), compatibility, calibration workflow, recalibration monitoring | `packages/brainos-decoder-sdk/`, `decoding/{model,registry,…}`, decoder use in `runtime/pipeline.py`, console Decoder/Calibration components |
| B | P3 | A genuinely different modality: human ECoG with behavior (DANDI NWB, streamed), modality-correct preprocessing, decoding if labels permit, modality guards | ECoG importer/manifests, ECoG processing stages |
| C | P0/P3 | Communication board v2 (cursor+click, cursor+dwell, scanning, directional, direct), settings, undo/history, TTS; `control.state` emission; `intent.navigate` routing; three SDK-only apps; opt-in desktop control bridge | `frontend/src/apps/board/`, `frontend/src/sdk/`, `runtime/router.py`, `runtime/control.py`, `examples/reference_app/`, `examples/desktop_bridge/` |
| D | P2/P6 | Installation: macOS app (built and smoke-tested on macOS CI), launcher, session workflow + export, `brainos doctor` support report, security (permissions, retention/deletion, redaction, crash recovery), clean-room lab acceptance test, first-lab-session protocol | `packaging/`, launcher, session export, doctor, recorder recovery, retention |
| E | P4 | Benchmarks at scale (64–4096 ch, multi-stream, long sessions, end-to-end), bottleneck profiling, native acceleration only where measured | `scripts/bench_*`, `packages/brainos-native/` (if justified), hot paths in `processing/` |
| F | P5 | Compatibility registry (machine-readable, from integration metadata + certify evidence), REST + console view | `compat/` registry, docs/COMPATIBILITY.md |

Shared files (Makefile, CI, README, LIMITATIONS, ARCHITECTURE, `e2e/demo.cjs`): append only,
in a section named after the workstream; the lead resolves conflicts.

## Rules that apply to every workstream

- CLAUDE.md hard rules. Never fabricate results; failed experiments are reported as such.
- Validation levels never auto-promote (software → protocol → hardware → human).
- Historical decoder outputs are `model_origin: historical`, never attributed to BrainOS.
- No behavioral ground truth or raw signal ever becomes an application command.
- No silent channel reordering, unit rescaling, or cross-participant decoder use.
- Untrusted serialized models are never deserialized with pickle without an explicit trust
  decision; prefer safe formats (skops, ONNX, safetensors, JSON).

## Workstream A notes (decoder SDK and model ecosystem)

- Delivered:
  - `packages/brainos-decoder-sdk` (API 1.0);
  - `decoding/{families,model,registry,engine,monitor,metrics,calibrate}.py`;
  - pipeline integration (one decoder interface, several decoders, multi-input join,
    `decoded_passthrough`, `model_origin`);
  - `server/decoder_routes.py`;
  - console Decoder row / start sheet / Calibration panel;
  - `examples/decoders/brainos-example-decoder`;
  - guide docs/DECODER_SDK.md, ARCHITECTURE §14.
- P0 integration (agreed with the lead):
  - `kalman.py` and `click.py` register through `families.register_family` (stable API);
  - T15 decoder outputs go through `decoded_passthrough` with `model_origin: historical`;
  - click events are `intent.kinematics` dims `["click"]`, quantity `click_decision` /
    `click_probability`;
  - a declared `y_axis: up` requires `invert_y`.
- Not done:
  - routing an external decoder's continuous output with automatic scaling (it needs a
    declared `scale`);
  - per-app decoder selection;
  - GPU execution;
  - decoder-host IPC benchmarks (E).
