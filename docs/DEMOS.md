# Guided demos (source installation)

These demos use the terminal and a source installation (`make setup`; see the
[README](../README.md#developers-install-from-source)). For the same things without a
terminal, start with [GETTING_STARTED.md](GETTING_STARTED.md). Every command runs from the
repository root. Real-data demos download public datasets, verified by SHA-256, into
`data/datasets/` (never committed).

**Contents**

- [Recorded human intracortical data with its offline decoder (FALCON H1)](#recorded-human-intracortical-data-with-its-offline-decoder-falcon-h1)
- [Cursor + click data driving the communication board (T15)](#cursor--click-data-driving-the-communication-board-t15)
- [Human ECoG (AJILE12)](#human-ecog-ajile12)
- [Live acquisition without hardware (LSL, Open Ephys test publishers)](#live-acquisition-without-hardware-lsl-open-ephys-test-publishers)
- [The 5-minute simulated demo, step by step](#the-5-minute-simulated-demo-step-by-step)
- [Bring your own decoder](#bring-your-own-decoder)
- [Writing an application](#writing-an-application)
- [Compatibility registry](#compatibility-registry)
- [Acquisition verification with concord-hwval](#acquisition-verification-with-concord-hwval)

## Recorded human intracortical data with its offline decoder (FALCON H1)

After `make setup`, run these once. They download two recording blocks (~8.7 MiB) from the
DANDI archive, check each file's SHA-256, and train the baseline decoder (~10 s):

```bash
make dataset
```

```bash
make model
```

Then start Concord as usual:

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
[docs/DECODING.md](DECODING.md).

## Cursor + click data driving the communication board (T15)

Recorded intracortical data from a person with paralysis controlling a cursor and clicking
(participant T15, Singer-Clark et al., Dryad doi:10.5061/dryad.prr4xgxzq, CC0) replays as
"Recorded Human Intracortical Data (cursor + click) — Offline Replay" (`t15:*` devices): threshold
crossings and spike band power, task state, and the original online decoders' outputs
(labelled historical, never Concord). Concord's own Kalman cursor decoder and click decoder,
trained only on earlier calibration blocks, recover the movement intention on held-out blocks
(angle error 28.0° vs 27.3° for the original online decoder; docs/CURSOR_CLICK.md), and drive
the participant board end to end in a browser (docs/NEURAL_COMMUNICATION.md). Open loop only:
nobody has communicated through Concord.

```bash
make dataset-t15            # day 468 blocks 0-3 (~90 MiB; Dryad API token: see --help)
make e2e-communication      # the board selects words from the replayed block (historical + Concord)
make cursorclick-report     # all 18 blocks: decoders, clicks, word selection -> docs/CURSOR_CLICK.md
```

## Human ECoG (AJILE12)

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

## Live acquisition without hardware (LSL, Open Ephys test publishers)

Protocol-level publishers stand in for acquisition software (each declares itself synthetic or
prerecorded). With Concord running (`make run`), in a second terminal:

```bash
.venv/bin/python -m concord.testing.publish falcon data/datasets/dandi-000954/sub-HumanPitt-held-in-calib_ses-19250108T111022.nwb --loop
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
[docs/LAB_GUIDE.md](LAB_GUIDE.md).

## The 5-minute simulated demo, step by step

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

## Bring your own decoder

Decoders are pluggable. Each one is checked against the source before it runs (modality,
features, bin size, channel identities and order, units, participant). Third-party code runs
in an isolated decoder process, and every output is validated:

```bash
concord-decoder new my-decoder && pip install -e concord-my-decoder   # a decoder plugin
concord-decoder check my-decoder                                       # run it as Concord does
concord-decoder check --model data/models/<id>.manifest.json           # an ONNX / skops / TorchScript file
```

In the console, **Start decoding** lists every decoder:

- Concord-trained models, imported model files and decoder plugins;
- each decoder's compatibility verdict for the chosen processing;
- the explicit channel mapping by label, offered only when it applies.

**Calibrate…** starts from the output you need (continuous movement, discrete classes, click).
Pickle / joblib files are refused unless you mark the exact file trusted. Guide:
[docs/DECODER_SDK.md](DECODER_SDK.md). Example plugin:
[examples/decoders/concord-example-decoder](../examples/decoders/concord-example-decoder/README.md).

## Writing an application

```python
from concord.sdk import EventStream, NegotiationUpdate, is_event

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

See [docs/SDK.md](SDK.md) and `backend/examples/print_events.py`.

## Compatibility registry

`compat/registry.json` lists every integration (built-in adapters, offline datasets, source
plugins), the validation level its evidence supports and that evidence. Levels are derived by
fixed rules, never typed in; nothing is at level 3 (hardware-verified) or 4 (human-participant
validated). `make compat` regenerates it, `make compat-check` (run in CI) fails when it is
stale; `GET /api/v1/compatibility` serves it with this installation's status, and the console
shows it under Advanced → Compatibility. See
[docs/COMPATIBILITY.md](COMPATIBILITY.md#registry-m5-f).

## Acquisition verification with concord-hwval

`packages/concord-hwval` checks that Concord received exactly what an acquisition system
produced: it compares a Concord recording with the recording the system's own reference
software made at the same time (LabRecorder XDF for LSL sources, the Open Ephys GUI's Record
Node in Binary format) and writes a JSON + Markdown report (PASS / FAIL / INCONCLUSIVE, per
check: identity, channels, units, loss, duplicates, values, timestamps, delay). The comparison
needs only `numpy` and `pyxdf`, not Concord. The laboratory procedure is
[docs/HARDWARE_VALIDATION.md](HARDWARE_VALIDATION.md). So far it has been run against the
real LabRecorder and the real Open Ephys GUI with software sources only: **no acquisition
hardware has been verified** (docs/VALIDATION_LEVELS.md).

```bash
concord-hwval capture lsl --stream "MyAmp EEG" --duration 240 --out runs/ --name run1
```
```bash
concord-hwval lsl --reference runs/run1.xdf --concord runs/run1.concord.jsonl --out reports/
```
```bash
make test-hwval   # also runs real LabRecorderCLI + Open Ephys GUI (Linux x86_64; see the Makefile)
```

