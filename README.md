# BrainOS

**Internal project name.** A hardware-agnostic, read-only runtime and SDK for implanted
brain-computer interfaces. Applications declare the capabilities they need, receive
standardized, provenance-labelled events, and keep working when the underlying device
changes.

> **Status: MVP vertical slice.** All devices are **simulated or replayed**. There is no
> real implant integration, no neural decoding, and no write/stimulation path. This is not
> a medical device. See [LIMITATIONS.md](LIMITATIONS.md).

| Document | Purpose |
| --- | --- |
| [PRODUCT.md](PRODUCT.md) | Users, problem, value proposition, non-goals |
| [ARCHITECTURE.md](ARCHITECTURE.md) | Contracts: adapters, capabilities, envelope, provenance, runtime, API, security |
| [MVP_SPEC.md](MVP_SPEC.md) | Requirements, acceptance tests (`AT-*`), demo script |
| [ROADMAP.md](ROADMAP.md) | Next 14 days |
| [LIMITATIONS.md](LIMITATIONS.md) | What is not real / not done |
| [docs/SDK.md](docs/SDK.md) | Python + TypeScript SDK guide |
| [docs/BENCHMARKS.md](docs/BENCHMARKS.md) | Measured performance (with machine info) |
| [CLAUDE.md](CLAUDE.md) | Rules for agents/engineers working in this repo |

## Quick start (macOS, Apple Silicon)

Prerequisites: [Homebrew](https://brew.sh), then

```bash
brew install uv node
```

`uv` downloads Python 3.12 automatically if it is not installed. Node 20+ is required.

```bash
git clone https://github.com/arnavhiteshpatel-cloud/brainos.git
```

```bash
cd brainos
```

```bash
make setup
```

```bash
make run
```

Open **http://127.0.0.1:8000**. (`make run` builds the frontend and serves the API,
console, and board app from one process. Stop with Ctrl-C.)

For development with hot reload instead: `make dev` and open http://127.0.0.1:5173.

## The 5-minute demo

1. **Console loads** — runtime `IDLE`; the Communication Board app is already connected
   (see *Connected applications*) with status `no_device`.
2. **Connect Simulated Profile A.** The event stream fills with `intent.pointer`,
   `recording.frame`, `telemetry.sample`; the 32-channel synthetic signal renders; the board
   switches to **pointer mode**.
3. **Control the board.** Drag inside the *Simulated intention source* pad (or hold arrow
   keys / WASD) to move the board's cursor; press **Select** (or Space) to activate a tile.
   Click any event row to inspect its envelope — note `provenance.kind = simulated_intent`.
4. **Inject a link drop** (Fault injection). Runtime goes `RECONNECTING` → `STREAMING`;
   Diagnostics shows the reconnect.
5. **Switch to Simulated Profile B.** The runtime renegotiates: no `pointer_intent`, but
   `text_intent`. The board — unchanged code — switches to **scan mode**; Select picks the
   highlighted tile; *Send text* types into the message.
6. **Record** a few seconds, stop, then click the new `Replay · …` device. Replayed events
   are marked `↺` / `replayed: true` and still drive the board.
7. **Diagnostics** tab: measured rates, pipeline/delivery/client latency percentiles,
   drops, contract violations, switch durations, errors. **Contract** tab: capability
   matrix and provenance rules. **Tests** tab: results of the last `make test` / `make e2e`.

## Commands

```bash
make test     # pytest (backend) + vitest (frontend); writes reports/ for the Tests tab
make lint     # ruff, mypy --strict, tsc
make e2e      # real-browser demo (AT-25); needs Playwright: npm i -g playwright && npx playwright install chromium
make bench    # measured throughput/latency on this machine -> docs/BENCHMARKS.md
```

## Repository layout

```
backend/src/brainos/   contracts · adapters (simulated, replay) · runtime · server · sdk
backend/tests/         pytest suite (AT-1..AT-21)
frontend/src/sdk/      TypeScript SDK
frontend/src/console/  operator console
frontend/src/apps/     communication board (imports only src/sdk)
contracts/             committed JSON Schema for the event envelope
e2e/                   Playwright demo script (AT-25)
scripts/               benchmarks, schema export
```

## Writing an application

```python
from brainos.sdk import EventStream, NegotiationUpdate, is_event

async with await EventStream.connect(
    app_id="my-app", app_name="My App",
    required=["selection"], optional=["pointer_intent", "text_intent"],
) as stream:
    async for item in stream:
        if isinstance(item, NegotiationUpdate):
            ...  # adapt to item.negotiation.granted
        elif is_event(item):
            ...  # item.event_type, item.payload, item.provenance.kind
```

See [docs/SDK.md](docs/SDK.md) and `backend/examples/print_events.py`.
