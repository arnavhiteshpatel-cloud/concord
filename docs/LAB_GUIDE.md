# Lab guide: connecting BrainOS to LSL and Open Ephys

For researchers trying BrainOS with their own acquisition setup. Read
[VALIDATION_LEVELS.md](VALIDATION_LEVELS.md) first: BrainOS has been **protocol-tested** with
software publishers and real recorded data, **not** verified with acquisition hardware, and
never used with a participant. It is a research tool, not a medical device; it never sends
anything to acquisition devices.

## 0. What you need

| | |
| --- | --- |
| A computer on the acquisition network | macOS (Apple Silicon) or Linux; Python 3.12 via `uv`, Node 20+ (see README Quick start) |
| For LSL | Your acquisition software's LSL outlet (an amplifier vendor's LSL app, OpenBCI GUI, BCI2000/OpenViBE LSL output, …) visible on the same network/subnet. liblsl is installed with `make setup` (pylsl wheel). |
| For Open Ephys | Open Ephys GUI ≥ 0.6 with the **ZMQ Interface** plugin in the signal chain, reachable over TCP from this computer |
| For calibration | A behavior / cue stream on LSL (e.g. the included center-out task, or your task software's LSL output) and trial markers |

Install and start (once): `make setup`, then `make run` and open http://127.0.0.1:8000.
The server listens on `127.0.0.1` only; keep it that way (no authentication).

## 1. Rehearse without hardware (10 minutes)

Each publisher speaks the real protocol and declares itself synthetic or prerecorded. Run
each in its own terminal from the repository root:

```bash
.venv/bin/python -m brainos.testing.publish lsl-ephys --channels 32 --rate 30000
```

```bash
.venv/bin/python -m brainos.testing.publish openephys --port 5556 --channels 32
```

```bash
make dataset
```

```bash
.venv/bin/python -m brainos.testing.publish falcon data/datasets/dandi-000954/sub-HumanPitt-held-in-calib_ses-19250108T111022.nwb --speed 1 --loop
```

Then follow sections 2–5 against these instead of your hardware. The FALCON stream is real
human data, labelled *prerecorded* everywhere (device kind `replay`).

## 2. Connect an LSL source

Requirements on the outlet (all standard LSL metadata):

- numeric channel format and a **regular** nominal rate (irregular/string streams can only be
  used as markers);
- `<desc><channels><channel><label/unit/type>` — units are converted to µV only if **every**
  channel declares a voltage unit (`microvolts`, `µV`, `uV`, `mV`, `V`, `nV`); otherwise data
  is shown and recorded as `arbitrary` units, never guessed;
- a stable `source_id` — required for automatic reconnection after the outlet restarts;
- stream type `SpikeCounts` (or `BinnedSpikes`) if it carries binned counts rather than
  voltages (a BrainOS convention; set `<desc><brainos><feature>spike_count`).

Console: **Acquisition source** → **Connect a source** (or **Change source**) → *Live streams*
→ **Find LSL streams** → *Search the network* → **Use** the signal stream → optionally attach
a behavior stream and a marker stream (they are mapped onto the signal stream's clock with
liblsl `time_correction`) → **Add source** → **Connect**. The **Signal integrity** row gives
the verdict (*Good*, *Gaps detected*, *No signal*, *Interrupted — reconnecting*), the channel
count, the percentage of samples received (samples vs estimated missing) and the delay to the
console; **Advanced → Acquisition details** lists every counter: samples, gaps, estimated
missing samples, stalls and clock corrections.

Python (same endpoints the console uses):

```python
import asyncio
from brainos.sdk import RuntimeClient

async def main() -> None:
    async with RuntimeClient("http://127.0.0.1:8000") as op:
        found = await op.discover_lsl(2.0)
        for s in found["streams"]:
            print(s["key"], s["name"], s["type"], s["channel_count"], s["nominal_srate"],
                  s["usable_as_signal"], s["reason"])
        dev = await op.configure_lsl("<signal key>", behavior="<behavior key>", markers="<marker key>")
        await op.connect(dev.device_id)

asyncio.run(main())
```

Default reconnect policy: 3 attempts (0.2 / 0.5 / 1.0 s). If your acquisition app takes
longer to restart, reconnect manually once it is back.

## 3. Connect Open Ephys

In the GUI: add **ZMQ Interface** after your source (and filters/spike detector), choose the
stream, set *Data Port* (default 5556; heartbeat uses port + 1), select channels, start
acquisition. Details: [OPEN_EPHYS.md](OPEN_EPHYS.md).

Console: **Connect a source** → *Live streams* → **Add Open Ephys source** → host (the GUI
machine; `127.0.0.1` if local), data port, and **unit**: the plugin does not transmit units, so enter the unit your signal chain
outputs (electrode/headstage channels are usually µV in the GUI, ADC/AUX channels are
not — check your source's channel settings, and send one kind per ZMQ Interface); leave *unknown* if unsure and data is labelled `arbitrary`. **Add source** →
**Connect**. Connection failures say whether the plugin answered the heartbeat but sent no data
(acquisition stopped / no channels selected) or did not answer (host/port/firewall).

Python: `await op.configure_openephys(host="192.168.1.20", data_port=5556, unit="uV")`.

## 4. Run a processing pipeline

Console: **Decoder** → **Start decoding**. The processing preset is preselected from the
source (passthrough if it already sends features, spike band at ≥ 10 kHz, high gamma at
≥ 400 Hz, band power otherwise); a decoder model is optional (without one, the pipeline only
computes features). Stages, counters and latency percentiles are under **Advanced → Pipeline
details**.

| Your signal | Preset | Output |
| --- | --- | --- |
| Broadband intracortical / single-unit, ≥ 10 kHz | `spikeband_threshold` (250–5000 Hz, CAR if ≥ 8 ch, −4.5 × RMS crossings, 1 ms refractory) | `features.binned` threshold-crossing counts |
| ECoG / sEEG, ≥ 400 Hz | `ecog_high_gamma` (60 Hz notch, 70–150 Hz log power) | `features.vector` |
| Any rate, custom band | `band_power` (`band_low_hz`, `band_high_hz`) | `features.vector` |
| Source already sends features (e.g. LSL `SpikeCounts`) | `features_passthrough` | — |

Set `line_hz` to 50 in 50 Hz countries. The threshold is estimated from the first second
(`rms_window_s`); the status shows the remaining warm-up. Watch `dropped_inputs` (pipeline
queue overflow) and the processing-time percentiles; on an M-series laptop 96 channels at
30 kHz should use well under one core (measure yours: `make bench-live`).

## 5. Calibrate a decoder

1. On the participant display machine (same network), start the cue task:
   `.venv/bin/python backend/examples/center_out_task.py --trials 40`
   (headless: `--headless`). It publishes `brainos-center-out-behavior` (cue velocity) and
   `brainos-center-out-markers`.
2. Register the neural stream with those two streams attached (section 2), connect, start
   decoding without a model (section 4).
3. **Decoder** → **Calibrate…** → *Start recording*: it records **features and labels only**
   (`exclude_raw`; raw 30 kHz frames would hit the default 200 MiB recording limit within
   seconds).
   Run all trials, then *Stop recording*.
4. In the same panel, select that recording and **Train decoder** (`feature_source = brainos.pipeline` when features came
   from the pipeline). The report shows held-out R² per dimension and a mean-predictor
   control. Offline held-out R² does not establish closed-loop performance.
5. **Stop decoding**, then **Start decoding** again with the new model. It is refused if the input does not match
   (feature, bin, channel count/labels) or if the source differs from the calibration source.

CLI equivalent of step 4: `.venv/bin/python -m brainos.decoding.calibrate data/recordings/<name>.brainos.jsonl --feature-source brainos.pipeline`.

## 6. Route commands to an application

Decoded output (`intent.kinematics`) is never a command. To drive an app, use **Command
output** → **Start control** (the command router; it is offered only while a decoder model
runs). Its **Settings** choose the two decoded dimensions for x/y, gain, dead-zone, max speed.
With a classifier (LDA, calibrated with *A class per moment*), **Settings** instead list one
action per class (select, activate, cancel or type text) with threshold, hold and pause.
Commands then reach only the applications you **Authorize** under *Authorized applications*
(each says what it would receive); **Revoke** withdraws it at once. Authorizations last until
revoked or BrainOS restarts; control itself is off after any source change, pause, link loss
or decoder change, and stops by itself if the decoder gets no input for 1 s (at least three
feature bins)
(docs/CONTROL_BRIDGE.md). Run the reference app in another terminal:

```bash
.venv/bin/python backend/examples/reference_app/cursor_app.py --seconds 60
```

It prints whether it is suspended, waiting for your authorization, or active, and where
commands come from (model id, prerecorded/synthetic). For discrete actions use
`backend/examples/reference_app/menu_app.py`. The red **Stop control** button in the title bar (always visible)
stops commands; **Stop decoding** stops the pipeline; **Disconnect** stops acquisition.

The communication board is the reference participant display: **Open participant screen** in the
*Command output* row opens it in its own window, to put on a second monitor facing the
participant. It needs pointer movement **and** a selection, so with a movement-only decoder it
stays in "Waiting"; with a simulated profile it works end to end.

## 7. Troubleshooting

| Symptom | Likely cause |
| --- | --- |
| LSL stream not discovered | Different subnet / multicast blocked; firewall; outlet not started. Use a longer discovery wait, or test on the same machine first. |
| `arbitrary` units | At least one channel lacks a voltage unit in its LSL metadata, or Open Ephys unit left *unknown*. |
| Gaps counted continuously | Outlet rate lower than declared, CPU starvation on the sender, or network loss. Compare timestamps in a LabRecorder XDF. |
| `incompatible_decoder` | Channel count/labels, bin size or feature differ from the model; or the stream is from the model's training session; or a different source without override. |
| Reconnect exhausted → `error` | The source took longer than ~2 s to return; reconnect manually. |

## 8. (M5-D) Installation, research sessions, export and safe stop

Installation without `make` (`brainos start`, the macOS app), network topology with a
separate acquisition computer, research sessions, the reproducibility export and **Safe stop &
disconnect**: [LAB_SETUP.md](LAB_SETUP.md). The first session with real equipment:
[FIRST_LAB_SESSION.md](FIRST_LAB_SESSION.md). Problems: [TROUBLESHOOTING.md](TROUBLESHOOTING.md).
