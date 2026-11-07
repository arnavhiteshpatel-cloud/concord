# BrainOS — 14-Day Roadmap

Each milestone is small, ends with a verification gate, and is not "done"
until its gate passes in CI. Days are working days for one engineer + agents.

| Day | Milestone | Depends on | Verification gate |
| --- | --- | --- | --- |
| 1 | Specs (this set of docs) + repo skeleton, CI, Makefile | — | `make lint test` green in CI |
| 1 | Contracts: capabilities, envelope, provenance rules, JSON Schema export | — | AT-1..AT-4 pass |
| 2 | Adapter contract + Profile A/B simulated adapters + fault injection | contracts | AT-5..AT-8 pass |
| 2 | Runtime: state machine, bus, negotiation, diagnostics, reconnect, switch | adapters | AT-9..AT-16 pass |
| 3 | Server (REST + WS) + Python SDK + example | runtime | AT-18..AT-21 pass; example prints events |
| 3 | Recorder + replay adapter | runtime | AT-17 passes |
| 4 | TS SDK + console + board app | server | AT-22..AT-24 pass; `npm run build` |
| 4 | E2E demo script, benchmarks, LIMITATIONS, PR | all | AT-25 passes locally; numbers in BENCHMARKS.md |
| **— MVP vertical slice ends here (days 1–4 are this PR) —** ||||
| 5 | Run E2E in CI (Playwright job, headless Chromium) | AT-25 | CI job green on PR |
| 5 | Per-app auth tokens + operator-approved grants | server | tests: unauthenticated hello rejected; grant approval flow |
| ~~6~~ | ✅ **Done in Milestone 2:** NWB `ReplaySource` for DANDI 000954 (FALCON H1), schema 1.1 (`features.binned`, `behavior.sample`, `intent.kinematics`), verified downloads | replay | 13 real-data tests in CI; binning bit-identical to the dataset authors' reference |
| ~~7~~ | ✅ **Done in Milestone 2:** leakage-free offline evaluation harness + baseline decoder (`decoded_intent` with `model_id`) | dataset replay | docs/DECODING.md, with mean-predictor and time-shift controls |
| ~~next~~ | ✅ **Done in Milestone 3:** runtime-level pipeline + decoder stage on any source's features, LSL and Open Ephys ZMQ adapters, calibration from recordings, command router, SDK-only reference app, center-out cue task | M2 | protocol tests, FALCON-over-LSL equivalence, docs/BENCHMARKS_LIVE.md |
| **next** | **First hardware session** (level 3, docs/VALIDATION_LEVELS.md): one LSL amplifier and one Open Ephys acquisition board, cross-checked against LabRecorder / Open Ephys recordings | M3 + lab partner | integrity report: counts, values, timestamps match the reference recorder |
| next | Cross-day evaluation on FALCON held-out sessions, raw-voltage NWB reader, adaptive threshold / recalibration | M3 | held-out-day metrics reported |
| 8 | Adapter conformance test kit (`brainos.testing.conformance`) any vendor adapter can run | adapter contract | both simulated adapters + replay pass the kit |
| 9 | Adapter SDK docs + "write your own adapter" tutorial with a third toy adapter (e.g. LSL-style stream bridge) | conformance kit | tutorial adapter passes kit, no runtime changes |
| 10 | Timing: clock-sync model (device↔runtime offset estimation), jitter diagnostics (LSL `time_correction` is used for auxiliary streams since M3) | runtime | tests with injected clock skew; diagnostics show estimated offset |
| 11 | Multi-device sessions (two devices concurrently) design + spike | runtime | design doc; spike behind flag; no regression |
| 12 | Audit log (append-only, who connected what, grants) | auth | tests; log viewable in console |
| 13 | Packaging: `pip install brainos-sdk` wheel, `npm` TS SDK package, versioning policy | SDKs | wheels build in CI; example installs from wheel |
| 14 | Hardening + external review: threat model doc, fuzzing of adapter decoders (Hypothesis) | all | fuzz run in CI with fixed budget; issues triaged |

## Dependency notes

- Anything touching real neural data (day 6+) must keep the provenance rules
  from ARCHITECTURE.md §4.2 unchanged. Behavioral labels never become intents.
- No stimulation/write path is on this roadmap. Adding one requires a
  separate safety design and is out of scope for the company's first year.
