# CLAUDE.md — Instructions for agents working on BrainOS

BrainOS (internal name) is a hardware-agnostic, **read-only** runtime + SDK for
implanted brain-computer interfaces. Read these first; they are the source of
truth, in this order:

1. `PRODUCT.md` — what and for whom, explicit non-goals.
2. `ARCHITECTURE.md` — contracts (normative).
3. `MVP_SPEC.md` — requirements and acceptance tests (`AT-*`).
4. `ROADMAP.md` — what comes next.
5. `LIMITATIONS.md` — what does not work / is not real. Keep it current.

## Hard rules (do not violate)

- **Never imply real device compatibility.** No Neuralink, Synchron, Blackrock,
  Paradromics, Precision, or any vendor name in device IDs, profiles, UI copy
  or docs as a supported device. Simulated profiles are "Simulated Profile A/B".
- **Never fabricate neural decoding or benchmark numbers.** Intents in v1 are
  `simulated_intent`. Performance numbers must come from `make bench` output
  on a named machine.
- **Read-only.** No write/stimulate/command path to devices: not in the adapter
  contract, not in the API, not in the SDKs.
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
backend/src/brainos/
  contracts/   capability vocabulary, envelope, provenance, stream protocol (no I/O)
  adapters/    base.py (contract), simulated/ (profiles A/B), replay/
  runtime/     runtime.py (orchestrator), bus.py, negotiation.py, diagnostics.py, recorder.py, registry.py
  server/      FastAPI app, REST routes, WebSocket, test-report reader
  sdk/         Python client SDK
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
make schema       # regenerate contracts JSON Schema after changing models
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
- Run `make lint test` before every commit. Do not claim something works
  unless it was executed.

## Changing contracts

1. Edit `contracts/events.py` (or `capabilities.py`).
2. Bump `SCHEMA_VERSION` minor (additive) or major (breaking).
3. `make schema`, update `frontend/src/sdk/types.ts`, update ARCHITECTURE.md §4.
4. Add valid + malformed tests.
