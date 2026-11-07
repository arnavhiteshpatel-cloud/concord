# Milestone 2 — Genuine human intracortical data: plan and acceptance criteria

## Audit of `main` (b10eb41) before starting

| Claim | Verified? |
| --- | --- |
| Runtime: validation, sequencing, negotiation, backpressure, diagnostics, recovery | Yes — 119 backend tests pass on `main` |
| Versioned contract separating raw / label / simulated / decoded | Yes — `contracts/events.py`, schema 1.0 |
| Two simulated profiles | Yes — `sim-a`, `sim-b` |
| Python + TypeScript SDKs | Yes |
| Console + communication board | Yes — 42 frontend tests pass (incl. PR #2 stale-state fix) |
| Recording + replay | Yes — `ReplayAdapter` over a `ReplaySource` protocol |
| macOS desktop packaging | **Not in the repository** (no Tauri files on any branch). Nothing here touches packaging. |

Gaps found during the audit that this milestone must address:

1. The contract has no type for **processed neural features** (e.g. binned threshold
   crossings) or for **continuous behavioral ground truth**; `recording.annotation` holds a
   single scalar label.
2. Replay **speed** exists in `ReplayAdapter` but is not exposed; there is no playback
   position/status API.
3. Fast replay never yields to the event loop when behind schedule (would starve
   WebSocket senders at high speed).
4. The console header always says "SIMULATED DATA".

## Dataset (verified 2026-11-07 against the DANDI API)

DANDI **000954** — *FALCON Benchmark H1: Human 7DoF Reach and Grasp Motor BCI*
(CC-BY-4.0, open access, *Homo sapiens*, two 96-channel intracortical arrays in the hand
knob of motor cortex; 176 channels released). Details and verification in
[DATASETS.md](DATASETS.md).

## Smallest architectural extension

- **Contract 1.1 (additive):** capabilities `neural_features`, `behavior`,
  `kinematic_intent`; event types `features.binned`, `behavior.sample`,
  `intent.kinematics`; provenance kind `processed_feature`. Existing types and rules are
  unchanged; 1.0 apps never receive the new types unless they request the new capabilities.
- **Reuse replay:** a new `ReplaySource` (`NWBUnitsSource`) feeds the *existing*
  `ReplayAdapter`, which already provides timing, pause/resume, looping, end-of-stream and
  the `replayed` provenance marking. No second replay system.
- **Playback control** added to `ReplayAdapter` (speed, position) and exposed through a
  generic runtime/REST endpoint that returns `unsupported_operation` for live/simulated
  devices.
- **Decoder:** FALCON-style baseline (causal exponential filter, z-score, ridge) trained
  on a session's calibration file, evaluated on that session's held-out minival file.
  Model stored as JSON (no pickle). During replay of the held-out file only, it emits
  `intent.kinematics` with `provenance.kind = decoded_intent` and a `model_id`. Never
  mapped to `pointer_intent`/`selection`, so the communication board cannot react to it.

## Acceptance criteria (M2-AT-*)

| ID | Criterion |
| --- | --- |
| M2-AT-1 | A real FALCON H1 NWB file downloaded from DANDI with SHA-256 matching DANDI's digest |
| M2-AT-2 | Loader extracts channel count, unit ids, bin width, units, duration, kinematic dim names; reports missing metadata (no electrode table) instead of inventing it |
| M2-AT-3 | Detected `rate`-holds-period inconsistency is corrected **and recorded** in metadata |
| M2-AT-4 | Binned counts match the FALCON reference binning definition (bin *i* = spikes in [tᵢ−20 ms, tᵢ)) |
| M2-AT-5 | Invalid/unsupported files fail with clear errors (not NWB, no units, unsupported modality, inconsistent lengths) |
| M2-AT-6 | Real data flows through the unchanged runtime: valid envelopes, strictly increasing seq, `synthetic=false`, `replayed=true`, origin identifies DANDI file |
| M2-AT-7 | Provenance separation: features=`processed_feature`, kinematics=`behavioral_label`, decoder output=`decoded_intent`+`model_id`; none delivered as pointer/selection |
| M2-AT-8 | Playback: start (connect), pause, resume, stop (disconnect), speed change, position/duration status |
| M2-AT-9 | Switch NWB → simulated → NWB works; board suspended on NWB (no selection), active again on sim |
| M2-AT-10 | Python SDK and TS SDK receive and validate the new event types; 1.0 apps unaffected |
| M2-AT-11 | Decoder: no train/test leakage (refuses in-sample replay), real metrics reported with mean-predictor and time-shift controls |
| M2-AT-12 | Console shows real-data label, source metadata, feature raster, behavior trace, playback status/controls |
| M2-AT-13 | Measured replay throughput and timing accuracy recorded in BENCHMARKS.md |
| M2-AT-14 | All pre-existing tests still pass |
