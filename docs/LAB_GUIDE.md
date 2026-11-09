# Lab guide: connecting Concord to LSL and Open Ephys

For researchers trying Concord with their own acquisition setup. Read
[VALIDATION_LEVELS.md](VALIDATION_LEVELS.md) first: Concord has been **protocol-tested** with
software publishers and real recorded data, **not** verified with acquisition hardware, and
never used with a participant. It is a research tool, not a medical device; it never sends
anything to acquisition devices.

The step-by-step guide for researchers, with every console click, what you should see and
troubleshooting for LSL, Open Ephys, BrainFlow and BCI2000, is
**[Connect your equipment](CONNECT_YOUR_EQUIPMENT.md)**. This page adds the details behind it:
outlet metadata, the Python API, processing presets and the calibration task.

## 0. What you need

| | |
| --- | --- |
| A computer on the acquisition network | macOS (Apple Silicon) or Linux, with Concord 0.3.1: the desktop app, or the Python installation from the release wheels ([Connect your equipment §2.1](CONNECT_YOUR_EQUIPMENT.md#21-what-you-need)). From a source checkout: Python 3.12 via `uv`, Node 20+ (README). |
| For LSL | Your acquisition software's LSL outlet (an amplifier vendor's LSL app, OpenBCI GUI, BCI2000/OpenViBE LSL output, …) visible on the same network/subnet. liblsl is included in every installation (pylsl wheel). |
| For Open Ephys | Open Ephys GUI ≥ 0.6 with the **ZMQ Interface** plugin in the signal chain, reachable over TCP from this computer |
| For calibration | A behavior / cue stream on LSL (e.g. the included center-out task, or your task software's LSL output) and trial markers |

Start Concord (the app, `concord start`, or `make run` in a checkout) and open
http://127.0.0.1:8000. The server listens on `127.0.0.1` only; keep it that way (no
authentication).

## 1. Rehearse without hardware (10 minutes)

`concord publish` starts test streams that speak the real protocols. The LSL streams declare
themselves synthetic or prerecorded; the Open Ephys protocol cannot carry that declaration, so
its test stream is shown as *Live stream, origin unverified* ([OPEN_EPHYS.md](OPEN_EPHYS.md#limitations)).
Run each in its own terminal (desktop app: `/Applications/Concord.app/Contents/MacOS/Concord
publish …`, Linux bundle `./Concord/Concord publish …`; source checkout `.venv/bin/concord
publish …`):

```bash
concord publish lsl-ephys --channels 32 --rate 30000
```

```bash
concord publish openephys --port 5560 --channels 32
```

```bash
concord publish falcon "<data folder>/datasets/sub-HumanPitt-held-in-calib_ses-19250108T111022.nwb" --loop
```

`<data folder>` is shown in **Advanced → Stored data** (*Data directory*); files downloaded with
`concord dataset` (or `make dataset`) are in its `datasets/dandi-000954/` subfolder. Use a data
port other than 5556 if the Open Ephys GUI runs on this computer. Stop each with Ctrl-C.

Then follow sections 2–5 against these instead of your hardware. The FALCON stream is real
human data, labelled *prerecorded* everywhere (device kind `replay`). For calibration (§5),
record a single pass of the file: with `--loop` the recording's held-out tail repeats data the
decoder was trained on.

## 2. Connect an LSL source

Requirements on the outlet (all standard LSL metadata):

- numeric channel format and a **regular** nominal rate (irregular/string streams can only be
  used as markers);
- `<desc><channels><channel><label/unit/type>` — units are converted to µV only if **every**
  channel declares a voltage unit (`microvolts`, `µV`, `uV`, `mV`, `V`, `nV`); otherwise data
  is shown and recorded as `arbitrary` units, never guessed;
- a stable `source_id` — required for automatic reconnection after the outlet restarts;
- for binned counts rather than voltages: stream type `SpikeCounts` (or `BinnedSpikes`), or
  `<desc><concord><feature>spike_count` in the description (a Concord convention).

Console: **Acquisition source** → **Connect a source** (or **Change source**) → *Live streams*
→ **Find LSL streams** → **Search the network**. Two things happen at once:

- the results table lists every stream found, with **Use** next to each stream that can be a
  signal (text streams and irregular-rate streams show the reason instead);
- every stream that can be a signal is also added to the *Live streams* list as an entry of its
  own (*LSL · `<name>` (`<type>`)*, with **Remove** and **Connect**): the stream alone, without
  attachments. Connecting such an entry needs no further step.

To attach a behavior stream and a marker stream (mapped onto the signal stream's clock with
liblsl `time_correction`): **Use** the signal stream → **Behavior stream (optional)** / **Marker
stream (optional)** → **Add source**. *Add source* adds no new line: it updates the signal
stream's existing entry (the session log says *Registered LSL · …*). Then **Connect** that
entry. The attachments are listed after connecting, in the *Role* table of **Advanced →
Acquisition details**.

The **Signal integrity** row gives the verdict (*Good*, *Gaps detected*, *No signal*,
*Interrupted — reconnecting*), the channel count, the percentage of samples received (samples
vs estimated missing) and the delay to the console; **Advanced → Acquisition details** lists
every counter: samples, gaps, estimated missing samples, stalls and clock corrections.
Registered entries stay listed after their stream stops (**Remove** clears them) and are
forgotten when Concord restarts.

Python (same endpoints the console uses):

```python
import asyncio
from concord.sdk import RuntimeClient

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

Default reconnect policy: 3 attempts, after 0.2 / 0.5 / 1.0 s, each waiting up to 5 s for the
stream: about 17 s in all. If your acquisition app takes longer to restart, the source ends in
*Source stopped with an error*: click **Reset**, then connect again once it is back.

## 3. Connect Open Ephys

In the GUI: add **ZMQ Interface** after your source (and filters/spike detector), choose the
stream, set *Data Port* (default 5556; heartbeat uses port + 1), select channels, start
acquisition. Details: [OPEN_EPHYS.md](OPEN_EPHYS.md).

Console: **Connect a source** → *Live streams* → **Add Open Ephys source** → **Host** (the GUI
machine; `127.0.0.1` if local), **Data port**, and **Sample unit**: the plugin does not
transmit units, so choose the unit your signal chain outputs (**uV**, **mV** or **V**;
electrode/headstage channels are usually µV in the GUI, ADC/AUX channels are not — check your
source's channel settings, and send one kind per ZMQ Interface); choose **Unknown (pass through
unscaled)** if unsure, and the data is labelled `arbitrary`. **Add source** (it registers the
entry *Open Ephys (ZMQ) · host:port* but does not connect) → **Connect**. Connection failures
say whether the plugin answered the heartbeat but sent no data (acquisition stopped / no
channels selected) or did not answer (`no reply from an Open Ephys ZMQ Interface at … within
4 s`: host/port/firewall). An Open Ephys source is always shown as *Live stream, origin
unverified*: the protocol cannot tell an acquisition board from the File Reader.

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

1. On the participant display machine (same network), start the cue task (source checkout):
   `.venv/bin/python backend/examples/center_out_task.py --trials 40`
   (headless: `--headless`). It publishes `concord-center-out-behavior` (cue velocity) and
   `concord-center-out-markers`. Your own task software works the same way if it publishes the
   cues over LSL.
2. Register the neural stream with those two streams attached (section 2), connect, start
   decoding without a model (section 4).
3. **Decoder** → **Calibrate…** → *1. Record a calibration session* → **Start recording**: it
   records **features and labels only** (`exclude_raw`; raw 30 kHz frames would hit the default
   200 MiB recording limit within seconds). Run all trials, then **Stop recording**. (Concord
   0.3.0 refused this for LSL, Open Ephys and plugin sources with *invalid recording name*;
   0.3.1 records them.)
4. In the same panel, under *2. Train*, tick that recording, choose **What the decoder should
   output** (**Continuous movement** for cue velocity), click **Check labels**, then **Train
   decoder**. With features from the pipeline, **Feature source** *Features computed by the
   Concord pipeline* (`feature_source = concord.pipeline`) selects them explicitly. The report
   shows held-out R² per dimension and two controls (mean predictor, time shift). Offline
   held-out R² does not establish closed-loop performance.
5. **Stop decoding**, then **Start decoding** again with the new model. It is refused if the input does not match
   (feature, bin, channel count/labels) or if the source differs from the calibration source.

CLI equivalent of step 4: `.venv/bin/python -m concord.decoding.calibrate data/recordings/<name>.concord.jsonl --feature-source concord.pipeline`.

## 6. Route commands to an application

Decoded output (`intent.kinematics`) is never a command. To drive an app, use **Command
output** → **Start control** (the command router). It is offered while a decoder model runs, and
also while **Source decoder outputs (passthrough)** runs (a source's own decoder outputs, e.g.
BCI2000's control signal or the T15 recordings' historical decoders). Its **Settings** choose
the two decoded dimensions for x/y (**Horizontal (x) from**, **Vertical (y) from**), **Gain**,
**Dead-zone**, **Max speed**, **Invert y** (ticked automatically when the decoder declares +y
up) and **Click from**, which lists the outputs of every running decoder and preselects a click
output when there is one.
With a classifier (LDA, calibrated with *A class per moment*), **Settings** instead list one
action per class (select, activate, cancel or type text) with threshold, hold and pause.
Commands then reach only the applications you **Authorize** under *Authorized applications*
(each says what it would receive); **Revoke** withdraws it at once. Authorizations last until
revoked or Concord restarts; control itself is off after any source change, pause, link loss
or decoder change, and stops by itself if the decoder gets no input for 1 s (at least three
feature bins)
(docs/CONTROL_BRIDGE.md). Run the reference app in another terminal:

```bash
.venv/bin/python backend/examples/reference_app/cursor_app.py --seconds 60
```

It prints whether it is suspended, waiting for your authorization, or active, and where
commands come from (model id, prerecorded/synthetic). For discrete actions use
`backend/examples/reference_app/menu_app.py`. The **Stop control** button in the title bar
(always shown; grey and disabled while command output is off, red while it is on) stops
commands; **Stop decoding** stops the pipeline; **Disconnect** stops acquisition.

The communication board is the reference participant display: **Open participant screen** in the
*Command output* row opens it in its own window, to put on a second monitor facing the
participant; **Authorize** it under *Authorized applications*. With a decoder that has a click
output (selected in **Click from**), it uses *Pointer and click*. With a movement-only decoder
it switches to **Pointer with dwell selection**: a tile is chosen by resting the cursor on it.
With a simulated profile it works end to end.

## 7. Troubleshooting

| Symptom | Likely cause |
| --- | --- |
| LSL stream not discovered | Different subnet / multicast blocked; firewall; outlet not started. Use a longer discovery wait, or test on the same machine first. |
| `arbitrary` units | At least one channel lacks a voltage unit in its LSL metadata, or Open Ephys unit left *unknown*. |
| Gaps counted continuously | Outlet rate lower than declared, CPU starvation on the sender, or network loss. Compare timestamps in a LabRecorder XDF. |
| `incompatible_decoder` | Channel count/labels, bin size or feature differ from the model; or the stream is from the model's training session; or a different source without override. |
| Reconnect exhausted → *Source stopped with an error* | The source took longer than about 17 s to return (3 attempts). Click **Reset**, then connect again. |
| `recording_error: invalid recording name 'lsl:…'` | A bug in 0.3.0 (also `openephys:`, `plugin:`); update to 0.3.1. |

More symptoms, per route (including BrainFlow and BCI2000):
[Connect your equipment §6](CONNECT_YOUR_EQUIPMENT.md#6-troubleshooting).

## 8. (M5-D) Installation, research sessions, export and safe stop

Installation without `make` (`concord start`, the macOS app), network topology with a
separate acquisition computer, research sessions, the reproducibility export and **Safe stop &
disconnect**: [LAB_SETUP.md](LAB_SETUP.md). The first session with real equipment:
[FIRST_LAB_SESSION.md](FIRST_LAB_SESSION.md). Problems: [TROUBLESHOOTING.md](TROUBLESHOOTING.md).
