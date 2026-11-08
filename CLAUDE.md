# CLAUDE.md — Instructions for agents working on Concord

Concord is a hardware-agnostic, **read-only** runtime + SDK for
implanted brain-computer interfaces. The import package and command are `concord`; the
main Python distribution is `concordos` (`concord` is taken on PyPI); companion packages
are `concord-*`. Read these first; they are the source of truth, in this order:

1. `PRODUCT.md` — what and for whom, explicit non-goals.
2. `ARCHITECTURE.md` — contracts (normative).
3. `MVP_SPEC.md` — requirements and acceptance tests (`AT-*`).
4. `ROADMAP.md` — what comes next.
5. `LIMITATIONS.md` — what does not work / is not real. Keep it current.

## Hard rules (do not violate)

- **Never imply real device compatibility.** No Neuralink, Synchron, Blackrock,
  Paradromics, Precision, or any vendor name in device IDs, profiles, UI copy
  or docs as a supported device. Simulated profiles are "Simulated Profile A/B".
- **Never fabricate neural decoding or benchmark numbers.** Simulated-device intents are
  `simulated_intent`. Decoding results must come from `make model` /
  `make decoding-report` on real files; performance numbers from `make bench`.
- **Real data rules.** Datasets are pinned by SHA-256 in `concord/datasets/*.json` and
  downloaded, never committed (`data/` is git-ignored; DANDI terms forbid
  redistribution). Recorded neural activity is `processed_feature`/`raw_signal`, never an
  intent. Offline sources are labelled "Offline Replay", never live.
- **No leakage.** A decoder must never be scored or replayed on its training session.
  FALCON `held-in-minival` files are subsets of `held-in-calib`; never use one to evaluate
  a model trained on the other. Keep `DecoderLeakageError` checks intact.
- **Read-only.** No write/stimulate/command path to devices: not in the adapter
  contract, not in the API, not in the SDKs. Live adapters only receive (the Open Ephys
  heartbeat is the single, documented exception: a liveness message to the plugin).
- **Validation levels.** Never describe protocol tests or prerecorded-data streaming as
  hardware or human validation. Keep docs/VALIDATION_LEVELS.md current.
- **Commands need the router.** Decoded or raw neural data must never reach apps as
  `pointer_intent`/`selection`/`text_intent` unless the operator enabled the command router.
- Never vendor the GPL Open Ephys client; the conformance test downloads it pinned by SHA-256.
- **Provenance rules** (ARCHITECTURE.md §4.2) are enforced in
  `contracts/events.py`. Do not relax them to make something work.
- **Apps are device-agnostic.** `frontend/src/apps/**` may import only from
  `frontend/src/sdk/**` (enforced by `boundary.test.ts`). No device IDs in app
  code. Apps adapt via negotiated capabilities.
- No secrets, private datasets, or recordings in git (`data/` is ignored).
- No placeholder UI presented as functional. If something is not implemented,
  don't render a button for it.

## Layout

```
backend/src/concord/
  contracts/   capability vocabulary, envelope, provenance, stream protocol (no I/O)
  adapters/    base.py (contract), simulated/ (profiles A/B), replay/, nwb/ (real recordings),
               lsl/ (LSL inlets), openephys/ (ZMQ Interface plugin protocol) — receive-only
  datasets/    pinned dataset manifests + verified downloader
  decoding/    ridge decoder (numpy, JSON models), model.py (input spec + compatibility),
               calibrate.py (fit from recordings)
  processing/  causal, chunk-invariant streaming stages + presets (scipy)
  testing/     LSL / Open Ephys protocol publishers (declared synthetic or prerecorded)
  runtime/     runtime.py (orchestrator), bus.py, negotiation.py, diagnostics.py, recorder.py,
               registry.py, catalog.py (offline dataset devices), live_sources.py (LSL / OE),
               pipeline.py (features -> decoder -> command router)
  server/      FastAPI app, REST routes, WebSocket, test-report reader
  sdk/         Python client SDK
backend/examples/ print_events.py, reference_app/ (SDK-only, test-enforced), center_out_task.py
backend/tests/ pytest suite (AT-* ids in docstrings)
frontend/src/
  sdk/         TS client SDK (types mirror the JSON Schema)
  console/     operator console (index.html)
  apps/board/  communication board demo app (board.html)
e2e/           Playwright demo script (AT-25)
scripts/       bench.py, dev helpers
```

## Commands

```bash
make setup        # create .venv (Python 3.12 via uv), install backend + frontend deps
make dev          # backend :8000 (reload) + Vite :5173 (proxy to backend)
make run          # build frontend, serve everything from :8000
make test         # pytest + vitest, writes reports/ (shown in console Tests tab)
make lint         # ruff + mypy (strict) + tsc
make e2e          # Playwright demo against a fresh server (needs playwright + chromium)
make bench        # measured throughput/latency
make bench-live   # LSL / Open Ephys -> pipeline measurements -> docs/BENCHMARKS_LIVE.md
make schema       # regenerate contracts JSON Schema after changing models
make dataset      # download + verify demo recordings (DANDI 000954) -> data/datasets/
make model        # baseline decoder on downloaded blocks -> data/models/, reports/decoding.json
make decoding-report  # all 13 blocks -> docs/DECODING.md
make test-hwval   # concord-hwval incl. real LabRecorder + Open Ephys GUI (docs/HARDWARE_VALIDATION.md)
```

Backend only: `cd backend && ../.venv/bin/pytest -q`.
Frontend only: `cd frontend && npm test`.

## Coding standards

- Python 3.12, full type hints, `mypy --strict` clean, `ruff` clean.
- Pydantic v2 models for every boundary object; `extra="forbid"` on contracts.
- asyncio only in runtime/server; contracts and `normalize()` are pure.
- Log with `logging.getLogger(__name__)`; include device/session context.
  Never swallow exceptions without logging *and* counting in diagnostics.
- TypeScript `strict`, no `any` in `src/sdk`. React function components.
- Keep modules small and single-purpose. No new dependency without a reason
  written in the PR description.

## Testing rules

- Every bug fix gets a regression test. Every new contract rule gets a
  malformed-input test.
- Tests must not sleep for long; prefer events/conditions with timeouts
  (`backend/tests/helpers.py: wait_for`).
- Rate tests measure real intervals with generous tolerance; never assert on
  machine-dependent absolute latency.
- Real-data tests (`test_nwb_real.py`) must run, not skip, in CI. Synthetic NWB
  fixtures are only for error paths real files cannot exercise.
- Run `make lint test` before every commit. Do not claim something works
  unless it was executed.

## Changing contracts

1. Edit `contracts/events.py` (or `capabilities.py`).
2. Bump `SCHEMA_VERSION` minor (additive) or major (breaking).
3. `make schema`, update `frontend/src/sdk/types.ts`, update ARCHITECTURE.md §4.
4. Add valid + malformed tests.
