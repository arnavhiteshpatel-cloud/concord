# BrainOS

**Internal project name.** A hardware-agnostic, read-only runtime and SDK for implanted
brain-computer interfaces. Applications declare the capabilities they need, receive
standardized, provenance-labelled events, and keep working when the underlying device
changes.

> **Status: Milestone 3 — lab-ready software, not yet lab-verified.** BrainOS now acquires
> live streams over **Lab Streaming Layer** and the **Open Ephys ZMQ Interface**, runs a
> streaming processing → decoding pipeline, calibrates decoders from recorded sessions, and
> routes decoded commands to applications only when an operator enables it. These paths are
> **protocol-tested** with software publishers and with genuine recorded human data streamed
> as *prerecorded* (DANDI 000954) — **never with acquisition hardware or a participant**
> ([docs/VALIDATION_LEVELS.md](docs/VALIDATION_LEVELS.md)). No implant vendor is supported,
> and there is no write/stimulation path. Not a medical device. See
> [LIMITATIONS.md](LIMITATIONS.md).

| Document | Purpose |
| --- | --- |
| [PRODUCT.md](PRODUCT.md) | Users, problem, value proposition, non-goals |
| [ARCHITECTURE.md](ARCHITECTURE.md) | Contracts: adapters, capabilities, envelope, provenance, runtime, API, security |
| [MVP_SPEC.md](MVP_SPEC.md) | Requirements, acceptance tests (`AT-*`), demo script |
| [ROADMAP.md](ROADMAP.md) | Next 14 days |
| [LIMITATIONS.md](LIMITATIONS.md) | What is not real / not done |
| [docs/SDK.md](docs/SDK.md) | Python + TypeScript SDK guide |
| [docs/BENCHMARKS.md](docs/BENCHMARKS.md) | Measured performance (with machine info) |
| [docs/DATASETS.md](docs/DATASETS.md) | The real dataset: provenance, license, verification, pitfalls |
| [docs/DECODING.md](docs/DECODING.md) | Offline decoding results with controls (generated) |
| [docs/MILESTONE2_PLAN.md](docs/MILESTONE2_PLAN.md) | Milestone 2 audit, plan, acceptance criteria |
| [docs/LAB_GUIDE.md](docs/LAB_GUIDE.md) | **Researchers:** exact steps for LSL / Open Ephys, pipeline, calibration, routing |
| [docs/VALIDATION_LEVELS.md](docs/VALIDATION_LEVELS.md) | Software-implemented vs protocol-tested vs hardware-verified vs human-validated, per component |
| [docs/OPEN_EPHYS.md](docs/OPEN_EPHYS.md) | Open Ephys ZMQ Interface protocol facts, sources, setup |
| [docs/BENCHMARKS_LIVE.md](docs/BENCHMARKS_LIVE.md) | Measured live-protocol throughput, loss, latency, soak |
| [docs/MILESTONE3_PLAN.md](docs/MILESTONE3_PLAN.md) | Milestone 3 audit, design, acceptance criteria |
| [DEVELOPMENT.md](DEVELOPMENT.md) | Rules for engineers working in this repo |

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

## Demo: genuine human neural data (Milestone 2)

After `make setup`, run these once. They download two recording blocks (~8.7 MiB) from the
DANDI archive, check each file's SHA-256, and train the baseline decoder (~10 s):

```bash
make dataset
```

```bash
make model
```

Then start BrainOS as usual:

```bash
make run
```

Open **http://127.0.0.1:8000** and:

1. In **Devices & sources**, under *Recorded human intracranial data · offline replay*, click
   **Connect** on `held-in-calib · 19250108T111022` (the row marked *held-out decoder*).
2. The header now reads **RECORDED HUMAN DATA · OFFLINE REPLAY**. The **Data source** panel
   shows the dataset (DANDI 000954, CC-BY-4.0), a green "SHA-256 matches DANDI" check,
   176 channels, 20 ms bins, the playback position, and the decoder's held-out R².
3. Scroll down to **Recorded neural activity**: the raster shows real spike counts from 176
   channels. The trace below compares the recorded velocity (solid) with the offline decoder's
   output (dashed); pick a dimension (tx, ty, tz, …).
4. Use **Pause / Resume**, the speed buttons (**0.5× … 8×**) and **Stop**.
5. In **Live event stream**, click a `features.binned` row: `provenance.kind` is
   `processed_feature`, `synthetic` is `false`, and `origin` names the exact DANDI file.
6. The Communication Board shows *suspended*. It does not react to neural data, because recorded
   activity is never presented as intent.
7. Click **Switch** on *Simulated Profile A*. Everything returns to the simulated demo below,
   and you can switch back at any time.

Want the full evaluation over 13 blocks (~66 MiB)? Run `make decoding-report`; it regenerates
[docs/DECODING.md](docs/DECODING.md).

## Demo: live acquisition without hardware (Milestone 3)

Protocol-level publishers stand in for acquisition software (each declares itself synthetic or
prerecorded). With BrainOS running (`make run`), in a second terminal:

```bash
.venv/bin/python -m brainos.testing.publish falcon data/datasets/dandi-000954/sub-HumanPitt-held-in-calib_ses-19250108T111022.nwb --loop
```

In the console's acquisition controls: discover LSL streams, register the FALCON spike-count
stream with its behavior and marker streams attached, connect (labelled prerecorded), start
the `features_passthrough` pipeline with the trained model, then enable the command router.
In a third terminal, the reference app (SDK only) waits while no commands exist and moves once
the router is on:

```bash
.venv/bin/python backend/examples/reference_app/cursor_app.py --seconds 60
```

Broadband synthetic ephys over LSL (`... publish lsl-ephys`) or an Open Ephys ZMQ stream
(`... publish openephys --port 5556`) work the same way with the `spikeband_threshold`
preset. Full researcher steps, including calibration with the center-out cue task:
[docs/LAB_GUIDE.md](docs/LAB_GUIDE.md).

## The 5-minute demo (simulated devices)

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
make e2e      # real-browser demo (AT-25); run `make e2e-setup` once first
make bench    # measured throughput/latency on this machine -> docs/BENCHMARKS.md
make bench-live  # LSL / Open Ephys -> pipeline -> decoder, measured here -> docs/BENCHMARKS_LIVE.md
make dataset  # download + verify the demo recordings (DANDI 000954) into data/datasets/
make model    # train/evaluate the baseline decoder on downloaded blocks -> data/models/
```

## Repository layout

```
backend/src/brainos/   contracts · adapters (simulated, replay, nwb, lsl, openephys) · processing
                       · decoding · runtime (incl. pipeline) · server · sdk · testing (publishers)
backend/examples/      print_events.py · reference_app/ (SDK-only) · center_out_task.py
backend/tests/         pytest suite (AT-*, M2-AT-*, M3-AT-*)
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
