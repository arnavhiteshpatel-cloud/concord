# Glossary

Every term you meet in Concord's console, on the communication board and in these documents, in
plain language, A to Z. Most entries link to where the [user guide](USER_GUIDE.md) explains them.
The ideas behind them are explained in [How Concord works](CONCEPTS.md).

Terms written `like this` are shown that way on screen (they are names Concord uses
internally).

[A](#a) · [B](#b) · [C](#c) · [D](#d) · [E](#e) · [F](#f) · [G](#g) · [H](#h) · [I](#i) ·
[K](#k) · [L](#l) · [M](#m) · [N](#n) · [O](#o) · [P](#p) · [Q](#q) · [R](#r) · [S](#s) ·
[T](#t) · [U](#u) · [V](#v) · [W](#w) · [X](#x) · [Z](#z)

---

## A

### Acquisition details

The section of **Advanced** that shows everything Concord knows about the connected source: a
dataset's checksum and citation, a live stream's counters, simulated device health.
[Guide 10.3](USER_GUIDE.md#103-acquisition-details)

### Acquisition source

Also just *source*. Where the data comes from: a simulated profile, a replayed recording, a live
stream (LSL, Open Ephys) or a plugin. One source is connected at a time.
[Guide 4](USER_GUIDE.md#4-acquisition-source)

### Activate

One of the three discrete actions a source can send (select, activate, cancel). With direct
selection, *activate* chooses the highlighted tile. [Guide 11.8](USER_GUIDE.md#118-input-methods)

### Adapter

The part of Concord that reads one kind of source and turns its data into standard events.
Adapters only receive. Others can write adapters as plugins. [Guide 4.9](USER_GUIDE.md#49-plugins)

### Advanced

The folded part at the bottom of the console with technical sections.
[Guide 10](USER_GUIDE.md#10-advanced)

### AJILE12

A public dataset of electrocorticography (ECoG) recorded from people (DANDI 000055). Concord
replays two verified extracts, shown as *Session 5* and *Session 6*.
[Guide 4.5](USER_GUIDE.md#45-recorded-human-data-offline-replay)

### Application

Also *app*. A program that receives data from Concord, such as the communication board. The
board embedded in each console tab counts as one application. The console tab itself is listed
under **Connected applications** (as `console`) but is not counted in *N applications
connected*. [Guide 10.7](USER_GUIDE.md#107-connected-applications)

### Arbitrary (unit)

The data has no physical unit, either because the file says so (FALCON velocities) or because
the source did not tell (Open Ephys with **Unknown** sample unit).
[Guide 4.8](USER_GUIDE.md#48-live-streams-open-ephys)

### Authorize, Revoke

Allow one application to receive decoded commands, or withdraw that permission. Applications are
not authorized by default; an authorization lasts until you revoke it or Concord quits.
[Guide 7.5](USER_GUIDE.md#75-authorized-applications)

### Automatic (input method)

The board uses the first input method the source supports, in the order listed in the guide.
[Guide 11.8](USER_GUIDE.md#118-input-methods)

## B

### Balanced accuracy

A score for a classifier: the share of correct answers is computed for each class separately, and
these shares are averaged. A class that occurs often therefore cannot inflate the score. Shown
next to [chance](#chance). [Guide 6.5](USER_GUIDE.md#65-the-calibrate-panel)

### Band power

The strength of a signal within a frequency band (for example 70–150 Hz), on a log scale, per
bin. Also the name of a processing preset. [Guide 6.3](USER_GUIDE.md#63-processing-presets)

### Behavior labels

On screen also `behavior` or `behavioral_label`. What the task or the person did at each moment:
cued movement, cursor position, a target, a click attempt. Decoders are trained to reproduce
these labels. They are never commands. [Guide 6.5](USER_GUIDE.md#65-the-calibrate-panel)

### Behavior stream

A stream that carries behavior labels next to the neural signal, for example an LSL stream of
cued velocity attached with **Behavior stream (optional)**.
[Guide 4.7](USER_GUIDE.md#47-live-streams-lsl)

### Bin

Also *bin length (ms)*. A short time window (for example 20 ms) over which features are counted
or averaged. [Guide 6.2](USER_GUIDE.md#62-the-start-decoding-panel)

## C

### Calibration

**Calibrate…** in the console. Recording labelled data from a source and fitting a decoder to it.
The report gives [held-out](#held-out) scores with controls.
[Guide 6.5](USER_GUIDE.md#65-the-calibrate-panel)

### Cancel

A discrete action that undoes the last change on the board (or cancels a pending confirmation).
[Guide 11.8](USER_GUIDE.md#118-input-methods)

### Capability

One kind of data a source can provide or an application can ask for, such as `pointer_intent`
(pointer movement) or `behavior`. An application receives only the capabilities it asked for
that the source provides. [Guide 10.6](USER_GUIDE.md#106-capability-contract)

### Capability contract

The **Advanced** section that lists every source's capabilities (the **Capability matrix**),
what each capability means (**Capability vocabulary**), and which data kinds can reach an
application (**Provenance separation**). [Guide 10.6](USER_GUIDE.md#106-capability-contract)

### Chance

The score a classifier would get by guessing. For [balanced accuracy](#balanced-accuracy) it is
1 divided by the number of classes (0.333 for three classes). A useful classifier scores clearly
above chance. [Guide 6.5](USER_GUIDE.md#65-the-calibrate-panel)

### Channel

One recording electrode or signal line. *32 of 32* means all declared channels arrive.
[Guide 5](USER_GUIDE.md#5-signal-integrity)

### Checksum

A fingerprint of a file, made with [SHA-256](#sha-256). If even one byte changes, the fingerprint
changes. Concord compares each dataset file and export with its published fingerprint.
[Guide 10.3](USER_GUIDE.md#103-acquisition-details)

### Classifier

Also *LDA classifier*. A decoder that chooses among a few classes (for example rest, left, right)
instead of estimating a movement. [Guide 7.4](USER_GUIDE.md#74-settings-for-classifiers)

### Click (output)

A decoder output that says whether the person is trying to click, as a probability or a 0/1
decision. Mapped to the board with **Click from**.
[Guide 7.3](USER_GUIDE.md#73-settings-for-movement-decoders)

### Click classifier

A decoder family that estimates the probability of a click attempt.
[Guide 6.5](USER_GUIDE.md#65-the-calibrate-panel)

### Click pause and debounce

**Click pause** (in command output) and **Click / switch debounce** (on the board): minimum times
between two clicks, so that one attempt selects once.
[Guide 7.3](USER_GUIDE.md#73-settings-for-movement-decoders),
[11.9](USER_GUIDE.md#119-board-settings)

### Closed loop, open loop

Closed loop: a person sees the result of their own brain activity and adjusts (real BCI use).
Open loop: decoding recorded data afterwards, with no feedback to the person. Everything Concord
has decoded is open loop.
[Guide 7.7](USER_GUIDE.md#77-example-the-t15-recorded-decoder-on-the-board)

### Command output

Also *command router*. The only path from a decoder's output to an application command. Off
unless you click **Start control**; **Stop control** turns it off.
[Guide 7](USER_GUIDE.md#7-command-output)

### Common average reference

Subtracting, at each moment, the average of all channels from each channel, to remove noise they
share. [Guide 6.3](USER_GUIDE.md#63-processing-presets)

### Communication board

The participant-facing application included with Concord: tiles with phrases, letters or words,
chosen with one of five input methods. [Guide 11](USER_GUIDE.md#11-the-communication-board)

### Compatibility (registry)

The list of every integration and the validation level its evidence supports.
[Guide 10.11](USER_GUIDE.md#1011-compatibility)

### Compatible

For a plugin: it follows Concord's plugin rules (its code was not reviewed). For a decoder model:
it accepts what the chosen processing produces. [Guide 4.9](USER_GUIDE.md#49-plugins),
[6.4](USER_GUIDE.md#64-decoder-models)

### `concord` command

The terminal command to start, stop, check and configure Concord, download datasets, verify
exports and publish test streams. [Guide 14](USER_GUIDE.md#14-the-concord-command)

### `concord publish`

Test streams over LSL or the Open Ephys protocol, for rehearsing without hardware.
[Guide 14.2](USER_GUIDE.md#142-test-streams-concord-publish)

### `concord reproduce`

Checks an export bundle, re-fits its decoders and recomputes the decoded output recorded in the
session. [Guide 3.5](USER_GUIDE.md#35-concord-reproduce)

### `concord-hwval`

A separate toolkit that compares a Concord recording with the recording the acquisition software
made at the same time ([HARDWARE_VALIDATION.md](HARDWARE_VALIDATION.md)).

### Confirmation

A board setting: a tile is chosen only when selected twice in a row.
[Guide 11.9](USER_GUIDE.md#119-board-settings)

### Console

The operator's screen, in a web browser at http://127.0.0.1:8000.
[Guide 1](USER_GUIDE.md#1-the-console-at-a-glance)

### Contract violation

Data a source sent that breaks Concord's rules (unreadable, malformed, or of a kind it did not
declare). It is refused and counted. [Guide 10.4](USER_GUIDE.md#104-diagnostics)

### `control_status`, `control.state`

Concord's notices to an application that command output for it started or stopped, so that it can
stop safely. The board's footer shows the latest one.
[Guide 11.2](USER_GUIDE.md#112-the-parts-of-the-board)

### CORS

Cross-origin resource sharing: the rule by which a web server says whether pages from other web
sites may read its files. A board word list on another web server loads only if that server
allows it. [Guide 11.6](USER_GUIDE.md#116-the-task-grid)

### CRC

Cyclic redundancy check: a short checksum inside each data packet, so that a damaged packet can be
recognized and dropped. Simulated Profile A's packets carry one (CRC32); the simulator's
**Malformed packet** fault produces a *CRC mismatch*.
[Guide 10.4](USER_GUIDE.md#104-diagnostics)

### Cross-source model

A decoder trained on a different source or session, run only with **Allow a model trained on a
different source**; its output is marked reduced quality.
[Guide 6.2](USER_GUIDE.md#62-the-start-decoding-panel)

## D

### DANDI

A public archive of neurophysiology data (dandiarchive.org). Source of FALCON H1 and AJILE12.
[Guide 4.5](USER_GUIDE.md#45-recorded-human-data-offline-replay)

### Data folder

Also *data directory*. Where Concord keeps datasets, recordings, models, sessions, exports and
logs. Its path is in **Advanced → Stored data**.
[Guide 16](USER_GUIDE.md#16-data-folders-ports-and-network)

### Data kind

See [provenance](#provenance).

### Data received (%)

The share of data that arrived, measured for LSL and Open Ephys only.
[Guide 5](USER_GUIDE.md#5-signal-integrity)

### Data Use Agreement

The terms of a dataset (FALCON H1: no re-identification, no contact with participants, no
redistribution). Downloading means accepting them ([Datasets](DATASETS.md)).

### Dead-zone

Decoder outputs smaller than this are treated as zero, so that small noise does not move the
cursor. [Guide 7.3](USER_GUIDE.md#73-settings-for-movement-decoders)

### Declared

Prerecorded, synthetic: what an LSL stream's publisher says about itself. Concord shows it but
cannot check it. [Guide 4.7](USER_GUIDE.md#47-live-streams-lsl)

### Decoded intent

On screen `decoded_intent`. A decoder's estimate of what the person intended, always labelled
with the model and its origin (Concord, external or historical).
[Guide 10.1](USER_GUIDE.md#101-event-stream)

### Decoder

A model that turns neural features into intended movement, a click or a choice.
[Guide 6](USER_GUIDE.md#6-decoder)

### Decoder family

The kind of model: ridge regression, Kalman filter, LDA classifier, click classifier, or an
imported format (ONNX, scikit-learn, TorchScript). [Guide 6.4](USER_GUIDE.md#64-decoder-models)

### Decoder model

One trained decoder, chosen under **Decoder model**. [Guide 6.4](USER_GUIDE.md#64-decoder-models)

### Decoder plugin

An installed package that adds a decoder; it runs in its own process.
[Guide 6.4](USER_GUIDE.md#64-decoder-models)

### Delay to this screen

The time from Concord receiving an event to this browser tab receiving it. Not the delay from the
brain. [Guide 5](USER_GUIDE.md#5-signal-integrity)

### Delivery gap

An event an application (the board, or a console tab) never received.
[Guide 11.2](USER_GUIDE.md#112-the-parts-of-the-board)

### `device_report`

The data kind of reports about a device, such as simulated battery and temperature. Never a
command. [Guide 10.1](USER_GUIDE.md#101-event-stream)

### `device_status`

Connection and streaming changes of a source. [Guide 10.6](USER_GUIDE.md#106-capability-contract)

### Diagnostics

Measured event rates, latencies, drops and errors. [Guide 10.4](USER_GUIDE.md#104-diagnostics)

### Direct selection

A board input method: select moves to the next tile, activate chooses it, cancel undoes.
[Guide 11.8](USER_GUIDE.md#118-input-methods)

### Directional navigation

A board input method: up, down, left, right (or next, previous) move the highlight.
[Guide 11.8](USER_GUIDE.md#118-input-methods)

### Discrete actions

The console's name for `selection`: select, activate, cancel.
[Guide 7.5](USER_GUIDE.md#75-authorized-applications)

### DNS rebinding

An attack in which a web site makes its own name point to your computer (127.0.0.1), so that a
page from that site could talk to programs running on your computer. Concord refuses browser
requests that address it by such a name.
[Guide 16](USER_GUIDE.md#16-data-folders-ports-and-network)

### Drift monitor

Compares the features arriving now with those a model was trained on, and recommends
recalibration when they differ. [Guide 6.1](USER_GUIDE.md#61-the-row)

### Dryad

A public data repository (datadryad.org). Source of the T15 cursor + click dataset.
[Guide 4.5](USER_GUIDE.md#45-recorded-human-data-offline-replay)

### Dwell selection

Also *dwell time*. Choosing a tile by resting the cursor (or highlight) on it for the dwell time.
A board interaction, never a neural click. [Guide 11.8](USER_GUIDE.md#118-input-methods)

## E

### ECoG

Electrocorticography: signals from electrodes on the surface of the brain.
[Guide 6.3](USER_GUIDE.md#63-processing-presets)

### Envelope

The full form of one event, with its time stamps, quality and provenance.
[Guide 10.1](USER_GUIDE.md#101-event-stream)

### Event

One piece of data inside Concord (a block of samples, a feature bin, a decoder output, a status
change). [Guide 10.1](USER_GUIDE.md#101-event-stream)

### Event stream

The **Advanced** section listing the latest events. [Guide 10.1](USER_GUIDE.md#101-event-stream)

### Export bundle

A zip of a research session (log, versions, settings, models, optionally recordings) that
`concord reproduce` can check and re-run.
[Guide 3.4](USER_GUIDE.md#34-what-is-in-the-export-and-what-reproducible-means)

### External (model origin)

A decoder that runs in another system and sends its output to Concord.
[Guide 6.1](USER_GUIDE.md#61-the-row)

## F

### F1

A score for a click decoder that combines [precision and recall](#precision-and-recall) into one
number (their harmonic mean). 1 is perfect; it is low if either precision or recall is low.
[Guide 6.5](USER_GUIDE.md#65-the-calibrate-panel)

### FALCON H1

A public benchmark dataset (DANDI 000954) of multi-unit spiking from intracortical arrays of one
person, with cued seven-dimensional reach-and-grasp velocity.
[Guide 4.5](USER_GUIDE.md#45-recorded-human-data-offline-replay)

### Fault injection

Buttons that make the simulated device fail on purpose (**Link drop**, **Link failure**,
**Malformed packet**, **Clock regression**). [Guide 10.8](USER_GUIDE.md#108-simulator-controls)

### Feature source

In **Calibrate…**, which features of a recording to train on.
[Guide 6.5](USER_GUIDE.md#65-the-calibrate-panel)

### Features

On screen also `processed_feature` or `neural_features`. Numbers computed from the raw signal per
bin, such as threshold crossings or band power, used by decoders. Never commands.
[Guide 6.3](USER_GUIDE.md#63-processing-presets)

### Freeze view

Stops the event stream list from moving; **Resume view** continues.
[Guide 10.1](USER_GUIDE.md#101-event-stream)

## G

### Gain

How much a decoder output is multiplied to give pointer velocity.
[Guide 7.3](USER_GUIDE.md#73-settings-for-movement-decoders)

### Gap (bins)

In calibration, bins left out between the training part and the held-out part.
[Guide 6.5](USER_GUIDE.md#65-the-calibrate-panel)

### Gaps detected

The signal-integrity verdict when something was lost in the last 10 seconds.
[Guide 5](USER_GUIDE.md#5-signal-integrity)

## H

### Heartbeat

A short "still listening" message that Concord sends to the Open Ephys GUI's ZMQ Interface
plugin, on the port after the data port. It is the only message Concord ever sends to
acquisition software. [Guide 4.8](USER_GUIDE.md#48-live-streams-open-ephys)

### Held-out

Held-out data is kept apart: it is not used to train a decoder, only to score it. Concord never
scores or shows a decoder on the data it was trained on. *Held-in* is the opposite: the data a
decoder may be trained on; *held-in-calib* is FALCON's name for its calibration files.
[Guide 6.5](USER_GUIDE.md#65-the-calibrate-panel)

### High-gamma band power

Power between 70 and 150 Hz, a feature used with ECoG; also a processing preset.
[Guide 6.3](USER_GUIDE.md#63-processing-presets)

### Historical (model origin)

The recorded outputs of the original research system's decoders, replayed from a dataset (T15).
Never presented as Concord's output.
[Guide 7.7](USER_GUIDE.md#77-example-the-t15-recorded-decoder-on-the-board)

## I

### Imported model file

A decoder saved in a standard format ([ONNX](#onnx), scikit-learn via [skops](#skops),
[TorchScript](#torchscript), [safetensors](#safetensors)) that you copy into the models folder.
[Guide 6.4](USER_GUIDE.md#64-decoder-models)

### Input method

How the board turns input into choices: pointer and click, pointer with dwell selection,
directional navigation, direct selection, scanning. [Guide 11.8](USER_GUIDE.md#118-input-methods)

### Intracortical, intracranial

Intracortical: recorded by microelectrode arrays inside the cortex. Intracranial: inside the
skull (a wider term, used in the FALCON source name). [Guide 4.1](USER_GUIDE.md#41-the-row)

### Invert y

Flips the vertical direction, for decoders whose "up" is positive while the screen's "down" is
positive. [Guide 7.3](USER_GUIDE.md#73-settings-for-movement-decoders)

### Isolated

Running in its own separate process, as plugins and imported decoders do. It limits damage from a
crash; it is not a security sandbox. [Guide 4.9](USER_GUIDE.md#49-plugins)

## K

### Kalman filter

A decoder family for continuous movement that combines the features with a model of how movement
evolves. [Guide 6.5](USER_GUIDE.md#65-the-calibrate-panel)

### `kinematic_intent`

A movement estimate with several dimensions from a decoder (simulated or model-decoded). Reaches
applications only through command output. [Guide 10.6](USER_GUIDE.md#106-capability-contract)

## L

### LabRecorder

The standard recorder of the Lab Streaming Layer ecosystem; writes XDF files. Used as a
reference by `concord-hwval`.

### Latency, p50, p95, p99

Latency is how long something takes. p50 is the median: half of the measurements were shorter.
p95 and p99 are the values that 95 % and 99 % of the measurements stayed under; they show the
slow cases. [Guide 10.2](USER_GUIDE.md#102-pipeline-details)

### LDA classifier

Linear discriminant analysis: a decoder family that chooses among classes; also used for clicks.
[Guide 6.5](USER_GUIDE.md#65-the-calibrate-panel)

### LFP

Local field potential: the slower part of the voltage that electrodes in the brain record (below a
few hundred hertz), the summed activity of many neurons near the electrode.
[Guide 6.3](USER_GUIDE.md#63-processing-presets)

### Link drop, link failure

A source connection lost once (Concord reconnects) or for good (the source stops with an error).
[Guide 10.8](USER_GUIDE.md#108-simulator-controls)

### Live stream, origin unverified

A stream from your network that does not say what it is. Concord cannot tell hardware from a file
player or a simulator. [Guide 2.2](USER_GUIDE.md#22-every-state-the-title-bar-can-show)

### LSL (Lab Streaming Layer)

A widely used way of streaming time series between programs on a lab network.
[Guide 4.7](USER_GUIDE.md#47-live-streams-lsl)

## M

### Map channels by label

Feeds a model the source channels whose names match the model's channel names.
[Guide 6.2](USER_GUIDE.md#62-the-start-decoding-panel)

### Marker stream

A stream of event markers (for example trial start), attached to an LSL signal with **Marker
stream (optional)**. [Guide 4.7](USER_GUIDE.md#47-live-streams-lsl)

### Max speed

The fastest the pointer may move on each axis, in workspaces per second.
[Guide 7.3](USER_GUIDE.md#73-settings-for-movement-decoders)

### Mean-predictor control

The [R²](#r-squared) of a "decoder" that always outputs the average of the training labels. It is
about 0 or below. A decoder that does not score clearly above it has learned nothing useful.
[Guide 6.5](USER_GUIDE.md#65-the-calibrate-panel)

### Metadata notes

Concord's notes on a dataset file: corrections it applied and what the file does not provide.
[Guide 10.3](USER_GUIDE.md#103-acquisition-details)

### Modality

The kind of recording (intracortical, ECoG, EEG, …) and whether it is implanted, as the source
declares it. [Guide 4.1](USER_GUIDE.md#41-the-row)

### Multicast

A way of sending one network message to every computer on the local network that listens for it.
LSL uses it to find streams. Some networks (for example some Wi-Fi networks) block it.
[Guide 4.7](USER_GUIDE.md#47-live-streams-lsl)

## N

### Native format

How a source's data arrives before Concord converts it.
[Guide 10.6](USER_GUIDE.md#106-capability-contract)

### `navigation`

Commands that move a highlight (up, down, left, right, next, previous).
[Guide 7.4](USER_GUIDE.md#74-settings-for-classifiers)

### Negotiation

When an application connects, Concord gives it the capabilities it asked for that the source
provides (**Granted**), and lists the others (**Not granted**).
[Guide 10.7](USER_GUIDE.md#107-connected-applications)

### Notch filter

A filter that removes one narrow frequency, such as the 50 or 60 Hz hum of mains electricity, and
its multiples (harmonics). [Guide 6.3](USER_GUIDE.md#63-processing-presets)

### NWB

Neurodata Without Borders: a standard file format for neurophysiology data. FALCON and AJILE12
files are NWB.

## O

### Offline held-out score

How well a model reconstructs recorded labels on [held-out](#held-out) data (R² for movement,
balanced accuracy for classes, precision and recall for clicks). It does not show how well a
person could control anything with it. [Guide 6.5](USER_GUIDE.md#65-the-calibrate-panel)

### Offline Replay

Playing back recorded data from a file, labelled as such. Never live.
[Guide 4.5](USER_GUIDE.md#45-recorded-human-data-offline-replay)

### ONNX

An open file format for trained models that many tools can read. Concord runs ONNX models in an
isolated process. [Guide 6.4](USER_GUIDE.md#64-decoder-models)

### Open Ephys GUI, ZMQ Interface

Open-source acquisition software, and the plugin of it that Concord reads (it publishes data over
[ZMQ](#zmq)). [Guide 4.8](USER_GUIDE.md#48-live-streams-open-ephys)

### Operator

The person running the console. [Guide 3.2](USER_GUIDE.md#32-new-research-session)

## P

### p50, p95, p99

See [latency, p50, p95, p99](#latency-p50-p95-p99).

### Participant screen

The communication board in its own window, for a second screen facing the participant.
[Guide 11.1](USER_GUIDE.md#111-opening-the-board)

### Passthrough

Using what the source already provides without processing: **Source features (passthrough)** for
features, **Source decoder outputs (passthrough)** for a decoder's output.
[Guide 6.3](USER_GUIDE.md#63-processing-presets)

### Pause, Resume

Stops and continues a source; pausing turns command output off.
[Guide 4.1](USER_GUIDE.md#41-the-row)

### Pickle, joblib

Python file formats that can hold a trained model. Loading such a file runs code stored in it,
so Concord loads one only after you click **Mark this file trusted**.
[Guide 6.2](USER_GUIDE.md#62-the-start-decoding-panel)

### Pipeline

Signal processing (filters, feature extraction) followed by an optional decoder, run
continuously on the connected source. [Guide 10.2](USER_GUIDE.md#102-pipeline-details)

### Playback

The replay controls of a file: position, **Pause**, speed. [Guide 4.1](USER_GUIDE.md#41-the-row)

### Plugin

Third-party code that adds a source or a decoder; it runs in its own process.
[Guide 4.9](USER_GUIDE.md#49-plugins)

### `pointer_intent`

Shown as *pointer movement*. A command to move a cursor, as a 2-D velocity.
[Guide 7.5](USER_GUIDE.md#75-authorized-applications)

### Precision and recall

Scores for a click decoder. Precision: of the clicks the decoder made, the share that were real
click attempts. Recall: of the real click attempts, the share the decoder caught. [F1](#f1)
combines both. [Guide 6.5](USER_GUIDE.md#65-the-calibrate-panel)

### Processing preset

One of the ways **Start decoding** turns a source into features (spike-band threshold crossings,
high-gamma band power, band power, the two passthroughs).
[Guide 6.3](USER_GUIDE.md#63-processing-presets)

### Provenance

Also *data kind*. What an event is and where it came from: `raw_signal`, `processed_feature`,
`behavioral_label`, `simulated_intent`, `decoded_intent`, `device_report`, `runtime`, and
whether it was replayed. Only intents can become commands.
[Guide 10.1](USER_GUIDE.md#101-event-stream)

## Q

### Quality

A score from 0 to 1 on each event, and flags such as `synthetic`, `replayed` or
`timestamp_regression`. [Guide 10.1](USER_GUIDE.md#101-event-stream)

## R

### R-squared

Written **R²**; also called the coefficient of determination. How much of the variation in
recorded movement a decoder reproduces: 1 is perfect, 0 is no better than always guessing the
average ([mean-predictor control](#mean-predictor-control)), and it can be negative.
[Guide 6.5](USER_GUIDE.md#65-the-calibrate-panel)

### Radial-8

A calibration task with eight targets around a centre (T15 blocks 0–2).
[Guide 4.5](USER_GUIDE.md#45-recorded-human-data-offline-replay)

### Raw signal

On screen `raw_signal`. Samples as acquired (for example microvolts per channel), as opposed to
features. [Guide 5](USER_GUIDE.md#5-signal-integrity)

### Recording (file)

A file of events Concord wrote while a source was connected; it can be replayed and used for
calibration. [Guide 10.5](USER_GUIDE.md#105-recording)

### `recording` (capability)

A source provides raw sample blocks (and time-aligned markers). Not the same as the **Recording**
feature: a dataset can declare it and still not be recordable.
[Guide 10.6](USER_GUIDE.md#106-capability-contract)

### Reference recording

The recording the acquisition system's own software makes at the same time as Concord's, for
verification ([HARDWARE_VALIDATION.md](HARDWARE_VALIDATION.md)).

### Replayed

Shown as **↺**. Played back from a recording, not happening now.
[Guide 10.1](USER_GUIDE.md#101-event-stream)

### Research session

A named folder that groups recordings, decoders and a log, and can be exported. Not the same as a
FALCON *Session …* file or a `ses_…` connection id.
[Guide 3](USER_GUIDE.md#3-research-sessions-and-export-the-session-strip)

### Reset

Clears a source that stopped with an error, so you can connect again.
[Guide 2.3](USER_GUIDE.md#23-source-stopped-with-an-error-and-reset)

### Ridge regression

A simple linear decoder family for continuous movement (Concord's default).
[Guide 6.5](USER_GUIDE.md#65-the-calibrate-panel)

### RMS

Root mean square: a channel's typical noise level. With **Threshold (× RMS)**, a spike is counted
when the signal crosses a multiple of it (−4.5 by default).
[Guide 6.2](USER_GUIDE.md#62-the-start-decoding-panel)

### ROC AUC

A score for a click decoder, computed per bin: the chance that a bin with a click attempt gets a
higher click score than a bin without one. 0.5 is guessing, 1 is perfect.
[Guide 6.5](USER_GUIDE.md#65-the-calibrate-panel)

### Router stall

On screen *input stalled*. Command output turned off because the decoder received no input for
too long. [Guide 7.6](USER_GUIDE.md#76-why-command-output-turned-off-last-stopped)

### `runtime`

The data kind of notices from Concord itself, such as "command output stopped".
[Guide 10.1](USER_GUIDE.md#101-event-stream)

## S

### Safe stop

**Safe stop & disconnect**: command output off, recording closed, decoding stopped, source
disconnected, in that order. Quitting does the same. [Guide 9](USER_GUIDE.md#9-stopping-safely)

### safetensors

A file format that stores only a model's numbers (its weights), without any code, so loading it
runs nothing. [Guide 6.4](USER_GUIDE.md#64-decoder-models)

### Scanning

A board input method: tiles are highlighted in turn and one switch chooses.
[Guide 11.8](USER_GUIDE.md#118-input-methods)

### Schema

The formal description of Concord's event format (version 1.4), at */api/v1/schema/event*.
[Guide 10.6](USER_GUIDE.md#106-capability-contract)

### sEEG

Stereo-electroencephalography: recordings from thin depth electrodes placed inside the brain,
usually for epilepsy monitoring. [Guide 6.3](USER_GUIDE.md#63-processing-presets)

### Select

The basic discrete action; on the board it chooses a tile (or moves, with direct selection).
[Guide 11.8](USER_GUIDE.md#118-input-methods)

### `selection`

Shown as *discrete actions*. The commands select, activate and cancel.
[Guide 7.5](USER_GUIDE.md#75-authorized-applications)

### Session

Has several meanings in Concord. A *research session* is yours
([Guide 3](USER_GUIDE.md#3-research-sessions-and-export-the-session-strip)). *Session
19250108T111022* is a FALCON file's own name. `ses_…` in an event is one source connection. The
**Session log** is the console's activity list.

### Session log

The console's list of what happened, newest first. [Guide 8](USER_GUIDE.md#8-the-session-log)

### Session recording

A recording you made, offered for replay under **Session recordings (replay)**.
[Guide 4.6](USER_GUIDE.md#46-session-recordings-replay-and-other-sources)

### SHA-256

The method Concord uses to make a file's fingerprint ([checksum](#checksum)): a 64-character code
that changes completely if even one byte of the file changes.
[Guide 4.5](USER_GUIDE.md#45-recorded-human-data-offline-replay)

### Sheet

A panel that slides in from the right of the console, for example **Connect a source** or **Start
decoding**. Close it with **Close**, the Escape key, or a click on the grey area beside it.
[Guide 1](USER_GUIDE.md#1-the-console-at-a-glance)

### Signal integrity

Whether data arrives complete and on time. [Guide 5](USER_GUIDE.md#5-signal-integrity)

### Simulated data, synthetic

Generated by software, not recorded from a person.
[Guide 4.4](USER_GUIDE.md#44-simulated-profiles)

### Simulated intent

On screen `simulated_intent`. Input from the simulator controls: an operator standing in for a
participant. Reaches applications without command output, labelled simulated.
[Guide 7.1](USER_GUIDE.md#71-when-commands-reach-an-application)

### Simulated profile

One of two built-in simulated devices (Profile A, Profile B). Never brain data, and not a model
of any real device. [Guide 4.4](USER_GUIDE.md#44-simulated-profiles)

### Simulator controls

The pad, **Select**, text and fault buttons for Simulated Profile A or B. Not shown for other
synthetic sources. [Guide 10.8](USER_GUIDE.md#108-simulator-controls)

### skops

A file format for scikit-learn models that can be loaded without running code from the file.
[Guide 6.4](USER_GUIDE.md#64-decoder-models)

### `source_id`

An LSL stream's identifier, set by its publisher; it tells apart streams with the same name.
[Guide 4.7](USER_GUIDE.md#47-live-streams-lsl)

### Spike band power

Power in the frequency band of spikes, per bin (a T15 feature stream).
[Guide 10.6](USER_GUIDE.md#106-capability-contract)

### Spike-band threshold crossings

Also *threshold crossings*. Counts of how often a band-passed signal crosses a threshold below its
noise level, per bin; a standard intracortical feature.
[Guide 6.3](USER_GUIDE.md#63-processing-presets)

### Stop control

The title-bar button that turns command output off immediately.
[Guide 2.1](USER_GUIDE.md#21-controls-in-the-title-bar)

### Subscriber drops

Events an application or console tab could not take in time and lost.
[Guide 10.4](USER_GUIDE.md#104-diagnostics)

### Support report

A report about your installation without neural or personal data, for whoever helps you.
[Guide 10.13](USER_GUIDE.md#1013-support-report)

### Switch

The **Connect** button's name while another source is connected; changes source.
[Guide 4.3](USER_GUIDE.md#43-the-connect-a-source-panel)

## T

### T15

The participant of a published cursor-and-click study whose recordings (Dryad) Concord replays:
four blocks of one day, with the original decoders' outputs.
[Guide 4.5](USER_GUIDE.md#45-recorded-human-data-offline-replay)

### Task grid

A board layout of N × N word tiles, for grid tasks. [Guide 11.6](USER_GUIDE.md#116-the-task-grid)

### Telemetry

On screen `telemetry`. Device health numbers. The simulated profiles' values are simulated.
[Guide 10.3](USER_GUIDE.md#103-acquisition-details)

### Test stream

A stream from `concord publish` for rehearsing without hardware.
[Guide 14.2](USER_GUIDE.md#142-test-streams-concord-publish)

### `text_intent`

Shown as *text*. Text sent a character or a word at a time.
[Guide 7.5](USER_GUIDE.md#75-authorized-applications)

### Time correction

The offset LSL measures between a publisher's clock and this computer's, used to line up streams.
[Guide 10.3](USER_GUIDE.md#103-acquisition-details)

### Time-shift control

The score of the same trained decoder when the held-out features are shifted in time against the
labels, so that they no longer belong together (averaged over several shifts). A decoder that
does not score clearly above it may be following slow trends rather than the neural signal.
[Guide 6.5](USER_GUIDE.md#65-the-calibrate-panel)

### TorchScript

A file format for models built with PyTorch. [Guide 6.4](USER_GUIDE.md#64-decoder-models)

### Train fraction

The share of calibration data (from the start) used for fitting.
[Guide 6.5](USER_GUIDE.md#65-the-calibrate-panel)

### Trust (model file)

Your decision to allow a [pickle or joblib](#pickle-joblib) model file, which runs code when
loaded. [Guide 6.2](USER_GUIDE.md#62-the-start-decoding-panel)

## U

### Undeclared capability

Data a source sent of a kind it did not declare; refused and counted.
[Guide 10.4](USER_GUIDE.md#104-diagnostics)

### uV, µV

Microvolts, the unit of raw voltage Concord uses.
[Guide 4.8](USER_GUIDE.md#48-live-streams-open-ephys)

## V

### Validation level

How far a component has been validated: software, protocol, hardware, human participant
([VALIDATION_LEVELS.md](VALIDATION_LEVELS.md)). [Guide 10.11](USER_GUIDE.md#1011-compatibility)

### Velocity dimension

The selector in **Acquisition details** that chooses which behavior dimension the plot shows.
[Guide 10.3](USER_GUIDE.md#103-acquisition-details)

## W

### Word list, word prediction

The words of the task grid, and up to three completions of the word being typed on the letters
page. [Guide 11.5](USER_GUIDE.md#115-the-letters-page-and-word-prediction)

### Workspace

The board's tile area, counted as 1 wide and 1 high; pointer speeds are in workspaces per second.
[Guide 7.3](USER_GUIDE.md#73-settings-for-movement-decoders)

## X

### XDF

The file format LabRecorder writes.

## Z

### ZMQ

ZeroMQ: a messaging library that programs use to send data to each other over a network. The
Open Ephys GUI's ZMQ Interface plugin uses it to publish data, and Concord receives it that way.
[Guide 4.8](USER_GUIDE.md#48-live-streams-open-ephys)
