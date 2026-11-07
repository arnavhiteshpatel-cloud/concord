# BrainOS

**Internal project name.** A hardware-agnostic, read-only runtime and SDK for implanted
brain-computer interfaces. Applications declare the capabilities they need, receive
standardized, provenance-labelled events, and keep working when the underlying device
changes.

> **Status: Milestone 4 — an integration platform, not yet lab-verified.** Device makers and
> labs integrate sources as **isolated plugins** through a public adapter SDK, with a
> certification toolkit; **BrainFlow** (official `BoardShim` API) and **BCI2000** (App
> Connector: processed control information) are integrated as plugins; applications receive
> decoded **pointer / select / activate / cancel / text** commands only after the operator
> **authorizes** them. Built-in: LSL, Open Ephys ZMQ, recorded human data (DANDI 000954),
> streaming processing, calibration (regression and LDA classification). Everything is
> **software- or protocol-tested** — **never with acquisition hardware or a participant**
> ([docs/VALIDATION_LEVELS.md](docs/VALIDATION_LEVELS.md),
> [docs/COMPATIBILITY.md](docs/COMPATIBILITY.md)). No implant vendor is supported, and there
> is no write/stimulation path. Not a medical device. See [LIMITATIONS.md](LIMITATIONS.md).

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
| [docs/DEVELOPERS.md](docs/DEVELOPERS.md) | **Developers:** install and use the adapter SDK, certify toolkit, server and app SDK |
| [docs/ADAPTER_SDK.md](docs/ADAPTER_SDK.md) | Source-plugin API, validation rules, isolation model, step-by-step |
| [docs/CERTIFICATION.md](docs/CERTIFICATION.md) | `brainos-certify`: checks, reports, validation levels |
| [docs/COMPATIBILITY.md](docs/COMPATIBILITY.md) | Compatibility matrix: every source × level reached × evidence |
| [docs/ECOSYSTEMS.md](docs/ECOSYSTEMS.md) | BrainFlow and BCI2000: what each interface exposes, mapping, tests |
| [docs/CONTROL_BRIDGE.md](docs/CONTROL_BRIDGE.md) | App authorization, action set, discrete decoding, stop/stale-command safety |
| [docs/MILESTONE4_PLAN.md](docs/MILESTONE4_PLAN.md) | Milestone 4 extension points, workstreams, validation levels |
| [CLAUDE.md](CLAUDE.md) | Rules for agents/engineers working in this repo |

## M5-D: install, start, and run a research session

**Desktop app (macOS, Apple Silicon):** open `BrainOS-<version>-macos-arm64.dmg` (CI job
`package-macos`, or `make app` on a Mac), drag BrainOS to Applications, open it (it is
unsigned: see [docs/INSTALL_MAC.md](docs/INSTALL_MAC.md) for the one-time Gatekeeper step).
The console opens in your browser; quitting stops everything safely.

**From a checkout (macOS or Linux):** after `make setup` and `make build` (below),

```bash
.venv/bin/brainos start
```

starts BrainOS in the background on http://127.0.0.1:8000 and opens the console;
`brainos status`, `brainos stop` (safe stop, then exit), `brainos doctor` (support report
without neural or personal data), `brainos config init` (an optional config file with safe
defaults), `brainos dataset` (the demo recordings), `brainos reproduce <bundle>.zip`.

In the console, the strip above the rows holds **New session** (name, operator, notes),
**Session and export…** (a reproducibility bundle) and **Safe stop & disconnect**;
**Advanced → Stored data** deletes recordings, models and sessions; **Advanced → Support
report**.

| Document | Purpose |
| --- | --- |
| [docs/INSTALL_MAC.md](docs/INSTALL_MAC.md) | Mac users: the app or pip, first launch, configuration |
| [docs/LAB_SETUP.md](docs/LAB_SETUP.md) | Labs with their own acquisition system: adapters, network topology, step by step |
| [docs/FIRST_LAB_SESSION.md](docs/FIRST_LAB_SESSION.md) | Validation protocol for the first session with real equipment (a protocol, not a result) |
| [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md) | Symptoms and fixes |
| [docs/SECURITY.md](docs/SECURITY.md) | What is and is not protected (no authentication; not a medical device) |

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

The console is one session screen: a title bar with the status line and the red **Stop
control** button, four rows (*Acquisition source*, *Signal integrity*, *Decoder*, *Command
output*), the *Session log* on the right, and a collapsed **Advanced** section at the bottom.

1. In **Acquisition source**, click **Connect a source**. Under *Recorded human data (offline
   replay)*, click **Connect** on *Session 19250108T111022* (show all files if it is not listed).
2. The status line now reads **Streaming · Recorded human data, offline replay**. *Signal
   integrity* shows the verdict, 176 of 176 channels, the measured delay, and four of the 176
   channels' spike counts as live traces.
3. Open **Advanced → Acquisition details**: the dataset (DANDI 000954, CC-BY-4.0), the
   "SHA-256 matches DANDI" check, 176 channels at 20 ms bins, the attached decoder's offline
   held-out R², the raster of all channels and the recorded velocity (solid) against the
   offline decoder's output (dashed).
4. In *Acquisition source*, open **Playback**: **Pause / Resume** and the speed buttons
   (**0.5× … 8×**). **Disconnect** stops the replay.
5. In **Advanced → Event stream**, click a `features.binned` row: `provenance.kind` is
   `processed_feature`, `synthetic` is `false`, and `origin` names the exact DANDI file.
6. *Command output* lists the Communication Board as *waiting for: selection*. It does not
   react to neural data, because recorded activity is never presented as intent.
7. **Change source** → *Simulated Profile A*. Everything returns to the simulated demo below,
   and you can switch back at any time.

Want the full evaluation over 13 blocks (~66 MiB)? Run `make decoding-report`; it regenerates
[docs/DECODING.md](docs/DECODING.md).

## Demo: live acquisition without hardware (Milestone 3)

Protocol-level publishers stand in for acquisition software (each declares itself synthetic or
prerecorded). With BrainOS running (`make run`), in a second terminal:

```bash
.venv/bin/python -m brainos.testing.publish falcon data/datasets/dandi-000954/sub-HumanPitt-held-in-calib_ses-19250108T111022.nwb --loop
```

In the console: **Connect a source** → *Live streams* → **Find LSL streams** → *Search the
network*; **Use** the FALCON spike-count stream, attach its behavior and marker streams, **Add
source**, then **Connect** it (the status line reads *Recorded data, streamed replay
(declared)*). In **Decoder**, **Start decoding**: *Source features (passthrough)* is preselected;
choose the trained model. In **Command output**, **Start control**, then **Authorize** the
application under *Authorized applications* (decoded commands reach only authorized apps); the
red **Stop control** in the title bar stops it at any time.
In a third terminal, the reference app (SDK only) waits while no commands exist or while it is not
authorized, and moves once the router is on and you have authorized it:

```bash
.venv/bin/python backend/examples/reference_app/cursor_app.py --seconds 60
```

Broadband synthetic ephys over LSL (`... publish lsl-ephys`) or an Open Ephys ZMQ stream
(`... publish openephys --port 5556`) work the same way with the `spikeband_threshold`
preset. Full researcher steps, including calibration with the center-out cue task:
[docs/LAB_GUIDE.md](docs/LAB_GUIDE.md).

## The 5-minute demo (simulated devices)

1. **Console loads** — status line *No source connected*; *Command output* shows the
   Communication Board connected and *waiting for: selection*.
2. **Connect a source → Simulated Profile A.** *Signal integrity* shows *Good* and four of
   the 32 synthetic channels; the session log records the connection. Click **Open participant
   screen** (in *Command output*): the communication board opens in its own window, for a
   second screen facing the participant, and switches to **pointer mode**. (It is also under
   **Advanced → Communication board**.)
3. **Control the board.** Open **Advanced → Simulator controls**; drag inside the pad (or
   hold arrow keys / WASD) to move the board's cursor; press **Select** (or Space) to activate
   a tile. In **Advanced → Event stream**, click any row to inspect its envelope — note
   `provenance.kind = simulated_intent`.
4. **Inject a link drop** (Simulator controls). The status line shows *Source link lost,
   reconnecting*, then *Streaming*; the session log records both.
5. **Change source → Simulated Profile B.** The runtime renegotiates: no `pointer_intent`,
   but `text_intent`. The board — unchanged code — switches to **scan mode**; Select picks the
   highlighted tile; *Send text* types into the message.
6. **Advanced → Recording**: record a few seconds, stop, then **Change source** → the new
   recording under *Session recordings*. Replayed events are marked `↺` / `replayed: true`
   and still drive the board.
7. **Advanced → Diagnostics**: measured rates, pipeline/delivery/client latency percentiles,
   drops, contract violations, switch durations, errors. **Capability contract**: capability
   matrix and provenance rules. **Tests**: results of the last `make test` / `make e2e`.

## Commands

```bash
make test     # pytest (backend) + vitest (frontend); writes reports/ for Advanced → Tests
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

## Milestone 5, workstream B: human ECoG (offline replay)

A second neural modality: raw-voltage ECoG from AJILE12 (DANDI 000055, CC-BY-4.0), streamed as
pinned, digest-verified slices (the source files are ~10 GB each) and replayed as
"Recorded Human ECoG — Offline Replay" (`modality: ecog`). The `ecog_high_gamma` pipeline uses
the source's 60 Hz mains and leaves bad electrodes out of the common average; a move-vs-rest
LDA trained on one day is scored on two held-out days (docs/ECOG_DECODING.md), and the unchanged
SDK-only menu app receives its decoded selections only after operator authorization. Models are
refused on a different recording modality. Details, results and limitations: docs/ECOG.md.

```bash
make dataset-ecog       # 2 demo slices (~157 MiB) -> data/datasets/dandi-000055/
make ecog-report        # all 6 slices; model -> data/models/; docs/ECOG_DECODING.md
```

## Compatibility registry (Milestone 5, workstream F)

`compat/registry.json` lists every integration (built-in adapters, offline datasets, source
plugins), the validation level its evidence supports and that evidence. Levels are derived by
fixed rules, never typed in; nothing is at level 3 (hardware-verified) or 4 (human-participant
validated). `make compat` regenerates it, `make compat-check` (run in CI) fails when it is
stale; `GET /api/v1/compatibility` serves it with this installation's status, and the console
shows it under Advanced → Compatibility. See
[docs/COMPATIBILITY.md](docs/COMPATIBILITY.md#registry-m5-f).

## Decoders: bring your own (Milestone 5, workstream A)

Decoders are pluggable. Each one is checked against the source before it runs (modality,
features, bin size, channel identities and order, units, participant). Third-party code runs
in an isolated decoder process, and every output is validated:

```bash
brainos-decoder new my-decoder && pip install -e brainos-my-decoder   # a decoder plugin
brainos-decoder check my-decoder                                       # run it as BrainOS does
brainos-decoder check --model data/models/<id>.manifest.json           # an ONNX / skops / TorchScript file
```

In the console, **Start decoding** lists every decoder:

- BrainOS-trained models, imported model files and decoder plugins;
- each decoder's compatibility verdict for the chosen processing;
- the explicit channel mapping by label, offered only when it applies.

**Calibrate…** starts from the output you need (continuous movement, discrete classes, click).
Pickle / joblib files are refused unless you mark the exact file trusted. Guide:
[docs/DECODER_SDK.md](docs/DECODER_SDK.md). Example plugin:
[examples/decoders/brainos-example-decoder](examples/decoders/brainos-example-decoder/README.md).
