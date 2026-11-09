# Glossary

Every term you meet in Concord's console, on the communication board and in these documents, in
plain language, A to Z. Each entry links to where the [user guide](USER_GUIDE.md) explains it.
The ideas behind them are explained in [How Concord works](CONCEPTS.md).

Terms written `like this` are shown that way on screen (they are names Concord uses
internally).

[A](#a) · [B](#b) · [C](#c) · [D](#d) · [E](#e) · [F](#f) · [G](#g) · [H](#h) · [I](#i) ·
[K](#k) · [L](#l) · [M](#m) · [N](#n) · [O](#o) · [P](#p) · [Q](#q) · [R](#r) · [S](#s) ·
[T](#t) · [U](#u) · [V](#v) · [W](#w) · [X](#x)

---

## A

**Acquisition details**: the section of **Advanced** that shows everything Concord knows about the
connected source: a dataset's checksum and citation, a live stream's counters, simulated device
health. [Guide 10.3](USER_GUIDE.md#103-acquisition-details)

**Acquisition source** (or *source*): where the data comes from: a simulated profile, a replayed
recording, a live stream (LSL, Open Ephys) or a plugin. One source is connected at a time.
[Guide 3](USER_GUIDE.md#3-acquisition-source)

**Activate**: one of the three discrete actions a source can send (select, activate, cancel). With
direct selection, *activate* chooses the highlighted tile. [Guide 11.8](USER_GUIDE.md#118-input-methods)

**Adapter**: the part of Concord that reads one kind of source and turns its data into standard
events. Adapters only receive. Others can write adapters as plugins.
[Guide 3.9](USER_GUIDE.md#39-plugins)

**Advanced**: the folded part at the bottom of the console with technical sections.
[Guide 10](USER_GUIDE.md#10-advanced)

**AJILE12**: a public dataset of electrocorticography (ECoG) recorded from people (DANDI 000055).
Concord replays two verified extracts, shown as *Session 5* and *Session 6*.
[Guide 3.5](USER_GUIDE.md#35-recorded-human-data-offline-replay)

**Application** (*app*): a program that receives data from Concord, such as the communication
board. Each console tab also counts as one. [Guide 10.7](USER_GUIDE.md#107-connected-applications)

**Arbitrary** (unit): the data has no physical unit, either because the file says so (FALCON
velocities) or because the source did not tell (Open Ephys with **Unknown** sample unit).
[Guide 3.8](USER_GUIDE.md#38-live-streams-open-ephys)

**Authorize / Revoke**: allow one application to receive decoded commands, or withdraw that
permission. Applications are not authorized by default; an authorization lasts until you revoke
it or Concord quits. [Guide 6.5](USER_GUIDE.md#65-authorized-applications)

**Automatic** (input method): the board picks the best input method the source supports.
[Guide 11.8](USER_GUIDE.md#118-input-methods)

## B

**Balanced accuracy**: for a classifier, the average of the share of correct answers in each
class, so that a frequent class cannot inflate the score. Shown next to *chance*.
[Guide 5.5](USER_GUIDE.md#55-the-calibrate-panel)

**Band power**: the strength of a signal within a frequency band (for example 70–150 Hz), on a
log scale, per bin. Also the name of a processing preset. [Guide 5.3](USER_GUIDE.md#53-processing-presets)

**Behavior / behaviour labels** (`behavior`, `behavioral_label`): what the task or the person did
at each moment: cued movement, cursor position, a target, a click attempt. Decoders are trained
to reproduce these labels. They are never commands. [Guide 5.5](USER_GUIDE.md#55-the-calibrate-panel)

**Behavior stream**: a stream that carries behaviour labels next to the neural signal, for
example an LSL stream of cued velocity attached with **Behavior stream (optional)**.
[Guide 3.7](USER_GUIDE.md#37-live-streams-lsl)

**Bin, bin length (ms)**: a short time window (for example 20 ms) over which features are
counted or averaged. [Guide 5.2](USER_GUIDE.md#52-the-start-decoding-panel)

## C

**Calibration** (**Calibrate…**): recording labelled data from a source and fitting a decoder to
it. The report gives held-out scores with controls. [Guide 5.5](USER_GUIDE.md#55-the-calibrate-panel)

**Cancel**: a discrete action that undoes the last change on the board (or cancels a pending
confirmation). [Guide 11.8](USER_GUIDE.md#118-input-methods)

**Capability**: one kind of data a source can provide or an application can ask for, such as
`pointer_intent` (pointer movement) or `behavior`. An application receives only the capabilities
it asked for that the source provides. [Guide 10.6](USER_GUIDE.md#106-capability-contract)

**Capability contract**, **capability matrix**: the **Advanced** section listing every source's
capabilities and their details. [Guide 10.6](USER_GUIDE.md#106-capability-contract)

**Channel**: one recording electrode or signal line. *32 of 32* means all declared channels
arrive. [Guide 4](USER_GUIDE.md#4-signal-integrity)

**Checksum** (**SHA-256**): a fingerprint of a file. If even one byte changes, the fingerprint
changes. Concord compares each dataset file and export with its published fingerprint.
[Guide 10.3](USER_GUIDE.md#103-acquisition-details)

**Classifier** (*LDA classifier*): a decoder that chooses among a few classes (for example rest,
left, right) instead of estimating a movement. [Guide 6.4](USER_GUIDE.md#64-settings-for-classifiers)

**Click** (output): a decoder output that says whether the person is trying to click, as a
probability or a 0/1 decision. Mapped to the board with **Click from**.
[Guide 6.3](USER_GUIDE.md#63-settings-for-movement-decoders)

**Click classifier**: a decoder family that estimates the probability of a click attempt.
[Guide 5.5](USER_GUIDE.md#55-the-calibrate-panel)

**Click pause**, **Click / switch debounce**: minimum times between two clicks, in command output
and on the board respectively, so that one attempt selects once.
[Guide 6.3](USER_GUIDE.md#63-settings-for-movement-decoders), [11.9](USER_GUIDE.md#119-board-settings)

**Closed loop / open loop**: closed loop, a person sees the result of their own brain activity and
adjusts (real BCI use). Open loop, decoding recorded data afterwards, with no feedback to the
person. Everything Concord has decoded is open loop. [Guide 6.7](USER_GUIDE.md#67-example-the-t15-recorded-decoder-on-the-board)

**Command output** (*command router*): the only path from a decoder's output to an application
command. Off unless you click **Start control**; **Stop control** turns it off.
[Guide 6](USER_GUIDE.md#6-command-output)

**Common average reference**: subtracting, at each moment, the average of all channels from each
channel, to remove noise they share. [Guide 5.3](USER_GUIDE.md#53-processing-presets)

**Communication board**: the participant-facing application included with Concord: tiles with
phrases, letters or words, chosen with one of five input methods.
[Guide 11](USER_GUIDE.md#11-the-communication-board)

**Compatibility** (registry): the list of every integration and the validation level its evidence
supports. [Guide 10.11](USER_GUIDE.md#1011-compatibility)

**Compatible**: for a plugin, it follows Concord's plugin rules (its code was not reviewed). For a
decoder model, it accepts what the chosen processing produces.
[Guide 3.9](USER_GUIDE.md#39-plugins), [5.4](USER_GUIDE.md#54-decoder-models)

**`concord` command**: the terminal command to start, stop, check and configure Concord, download
datasets, verify exports and publish test streams. [Guide 14](USER_GUIDE.md#14-the-concord-command)

**`concord publish`**: test streams over LSL or the Open Ephys protocol, for rehearsing without
hardware. [Guide 14.2](USER_GUIDE.md#142-test-streams-concord-publish)

**`concord reproduce`**: checks an export bundle and re-fits its decoders.
[Guide 7.5](USER_GUIDE.md#75-concord-reproduce)

**`concord-hwval`**: a separate toolkit that compares a Concord recording with the recording the
acquisition software made at the same time ([HARDWARE_VALIDATION.md](HARDWARE_VALIDATION.md)).

**Confirmation**: a board setting: a tile is chosen only when selected twice in a row.
[Guide 11.9](USER_GUIDE.md#119-board-settings)

**Console**: the operator's screen, in a web browser at http://127.0.0.1:8000.
[Guide 1](USER_GUIDE.md#1-the-console-at-a-glance)

**Contract violation**: data a source sent that breaks Concord's rules (unreadable, malformed, or
of a kind it did not declare). It is refused and counted. [Guide 10.4](USER_GUIDE.md#104-diagnostics)

**`control_status`, `control.state`**: Concord's notices to an application that command output
for it started or stopped, so that it can stop safely. The board's footer shows the latest one.
[Guide 11.2](USER_GUIDE.md#112-the-parts-of-the-board)

**Cross-source model**: a decoder trained on a different source or session, run only with **Allow
a model trained on a different source**; its output is marked reduced quality.
[Guide 5.2](USER_GUIDE.md#52-the-start-decoding-panel)

## D

**DANDI**: a public archive of neurophysiology data (dandiarchive.org). Source of FALCON H1 and
AJILE12. [Guide 3.5](USER_GUIDE.md#35-recorded-human-data-offline-replay)

**Data folder** (*data directory*): where Concord keeps datasets, recordings, models, sessions,
exports and logs. Its path is in **Advanced → Stored data**.
[Guide 16](USER_GUIDE.md#16-data-folders-ports-and-network)

**Data kind**: see *Provenance*.

**Data received (%)**: the share of data that arrived, measured for LSL and Open Ephys only.
[Guide 4](USER_GUIDE.md#4-signal-integrity)

**Data Use Agreement**: the terms of a dataset (FALCON H1: no re-identification, no contact with
participants, no redistribution). Downloading means accepting them ([Datasets](DATASETS.md)).

**Dead-zone**: decoder outputs smaller than this are treated as zero, so that small noise does not
move the cursor. [Guide 6.3](USER_GUIDE.md#63-settings-for-movement-decoders)

**Declared** (prerecorded, synthetic): what an LSL stream's publisher says about itself. Concord
shows it but cannot check it. [Guide 3.7](USER_GUIDE.md#37-live-streams-lsl)

**Decoded intent** (`decoded_intent`): a decoder's estimate of what the person intended, always
labelled with the model and its origin (Concord, external or historical).
[Guide 10.1](USER_GUIDE.md#101-event-stream)

**Decoder**: a model that turns neural features into intended movement, a click or a choice.
[Guide 5](USER_GUIDE.md#5-decoder)

**Decoder family**: the kind of model: ridge regression, Kalman filter, LDA classifier, click
classifier, or an imported format (ONNX, scikit-learn, TorchScript).
[Guide 5.4](USER_GUIDE.md#54-decoder-models)

**Decoder model**: one trained decoder, chosen under **Decoder model**.
[Guide 5.4](USER_GUIDE.md#54-decoder-models)

**Decoder plugin**: an installed package that adds a decoder; it runs in its own process.
[Guide 5.4](USER_GUIDE.md#54-decoder-models)

**Delay to this screen**: the time from Concord receiving an event to this browser tab receiving
it. Not the delay from the brain. [Guide 4](USER_GUIDE.md#4-signal-integrity)

**Delivery gap**: an event an application (the board, or a console tab) never received.
[Guide 11.2](USER_GUIDE.md#112-the-parts-of-the-board)

**`device_report`**: the data kind of reports about a device, such as simulated battery and
temperature. Never a command. [Guide 10.1](USER_GUIDE.md#101-event-stream)

**`device_status`**: connection and streaming changes of a source.
[Guide 10.6](USER_GUIDE.md#106-capability-contract)

**Diagnostics**: measured event rates, latencies, drops and errors.
[Guide 10.4](USER_GUIDE.md#104-diagnostics)

**Direct selection**: a board input method: select moves to the next tile, activate chooses it,
cancel undoes. [Guide 11.8](USER_GUIDE.md#118-input-methods)

**Directional navigation**: a board input method: up, down, left, right (or next, previous) move
the highlight. [Guide 11.8](USER_GUIDE.md#118-input-methods)

**Discrete actions**: the console's name for `selection`: select, activate, cancel.
[Guide 6.5](USER_GUIDE.md#65-authorized-applications)

**Drift monitor**: compares the features arriving now with those a model was trained on, and
recommends recalibration when they differ. [Guide 5.1](USER_GUIDE.md#51-the-row)

**Dryad**: a public data repository (datadryad.org). Source of the T15 cursor + click dataset.
[Guide 3.5](USER_GUIDE.md#35-recorded-human-data-offline-replay)

**Dwell selection**, **dwell time**: choosing a tile by resting the cursor (or highlight) on it for
the dwell time. A board interaction, never a neural click. [Guide 11.8](USER_GUIDE.md#118-input-methods)

## E

**ECoG** (electrocorticography): signals from electrodes on the surface of the brain.
[Guide 5.3](USER_GUIDE.md#53-processing-presets)

**Envelope**: the full form of one event, with its time stamps, quality and provenance.
[Guide 10.1](USER_GUIDE.md#101-event-stream)

**Event**: one piece of data inside Concord (a block of samples, a feature bin, a decoder output, a
status change). [Guide 10.1](USER_GUIDE.md#101-event-stream)

**Event stream**: the **Advanced** section listing the latest events.
[Guide 10.1](USER_GUIDE.md#101-event-stream)

**Export bundle**: a zip of a research session (log, versions, settings, models, optionally
recordings) that `concord reproduce` can check and re-run.
[Guide 7.4](USER_GUIDE.md#74-what-is-in-the-export-and-what-reproducible-means)

**External** (model origin): a decoder that runs in another system and sends its output to Concord.
[Guide 5.1](USER_GUIDE.md#51-the-row)

## F

**FALCON H1**: a public benchmark dataset (DANDI 000954) of multi-unit spiking from intracortical
arrays of one person, with cued seven-dimensional reach-and-grasp velocity.
[Guide 3.5](USER_GUIDE.md#35-recorded-human-data-offline-replay)

**Fault injection**: buttons that make the simulated device fail on purpose (**Link drop**, **Link
failure**, **Malformed packet**, **Clock regression**). [Guide 10.8](USER_GUIDE.md#108-simulator-controls)

**Feature source**: in **Calibrate…**, which features of a recording to train on.
[Guide 5.5](USER_GUIDE.md#55-the-calibrate-panel)

**Features** (`processed_feature`, `neural_features`): numbers computed from the raw signal per
bin, such as threshold crossings or band power, used by decoders. Never commands.
[Guide 5.3](USER_GUIDE.md#53-processing-presets)

**Freeze view**: stops the event stream list from moving; **Resume view** continues.
[Guide 10.1](USER_GUIDE.md#101-event-stream)

## G

**Gain**: how much a decoder output is multiplied to give pointer velocity.
[Guide 6.3](USER_GUIDE.md#63-settings-for-movement-decoders)

**Gap (bins)**: in calibration, bins left out between the training part and the held-out part.
[Guide 5.5](USER_GUIDE.md#55-the-calibrate-panel)

**Gaps detected**: the signal-integrity verdict when something was lost in the last 10 seconds.
[Guide 4](USER_GUIDE.md#4-signal-integrity)

## H

**Held-in / held-out**: held-out data is not used to train a decoder, only to score it. Concord
never scores or shows a decoder on the data it was trained on. *held-in-calib* is FALCON's name
for its calibration files. [Guide 5.5](USER_GUIDE.md#55-the-calibrate-panel)

**High-gamma band power**: power between 70 and 150 Hz, a feature used with ECoG; also a
processing preset. [Guide 5.3](USER_GUIDE.md#53-processing-presets)

**Historical** (model origin): the recorded outputs of the original research system's decoders,
replayed from a dataset (T15). Never presented as Concord's output.
[Guide 6.7](USER_GUIDE.md#67-example-the-t15-recorded-decoder-on-the-board)

## I

**Imported model file**: a decoder saved in a standard format (ONNX, scikit-learn, TorchScript,
safetensors) that you copy into the models folder. [Guide 5.4](USER_GUIDE.md#54-decoder-models)

**Input method**: how the board turns input into choices: pointer and click, pointer with dwell
selection, directional navigation, direct selection, scanning.
[Guide 11.8](USER_GUIDE.md#118-input-methods)

**Intracortical / intracranial**: intracortical, recorded by microelectrode arrays inside the
cortex. Intracranial, inside the skull (a wider term, used in the FALCON source name).
[Guide 3.1](USER_GUIDE.md#31-the-row)

**Invert y**: flips the vertical direction, for decoders whose "up" is positive while the screen's
"down" is positive. [Guide 6.3](USER_GUIDE.md#63-settings-for-movement-decoders)

**Isolated**: running in its own separate process, as plugins and imported decoders do. It
limits damage from a crash; it is not a security sandbox. [Guide 3.9](USER_GUIDE.md#39-plugins)

## K

**Kalman filter**: a decoder family for continuous movement that combines the features with a
model of how movement evolves. [Guide 5.5](USER_GUIDE.md#55-the-calibrate-panel)

**`kinematic_intent`**: a movement estimate with several dimensions from a decoder (simulated or
model-decoded). Reaches applications only through command output.
[Guide 10.6](USER_GUIDE.md#106-capability-contract)

## L

**Lab Streaming Layer (LSL)**: a widely used way of streaming time series between programs on a
lab network. [Guide 3.7](USER_GUIDE.md#37-live-streams-lsl)

**LabRecorder**: the standard recorder of the Lab Streaming Layer ecosystem; writes XDF files.
Used as a reference by `concord-hwval`.

**Latency, p50 / p95 / p99**: how long something takes; p50 is the median, p95 and p99 the values
95 % and 99 % of measurements stay under. [Guide 10.2](USER_GUIDE.md#102-pipeline-details)

**LDA classifier**: a decoder family that chooses among classes; also used for clicks.
[Guide 5.5](USER_GUIDE.md#55-the-calibrate-panel)

**Link drop, link failure**: a source connection lost once (Concord reconnects) or for good (the
source stops with an error). [Guide 10.8](USER_GUIDE.md#108-simulator-controls)

**Live stream, origin unverified**: a stream from your network that does not say what it is.
Concord cannot tell hardware from a file player or a simulator.
[Guide 2.2](USER_GUIDE.md#22-every-state-the-title-bar-can-show)

## M

**Map channels by label**: feeds a model the source channels whose names match the model's
channel names. [Guide 5.2](USER_GUIDE.md#52-the-start-decoding-panel)

**Marker stream**: a stream of event markers (for example trial start), attached to an LSL signal
with **Marker stream (optional)**. [Guide 3.7](USER_GUIDE.md#37-live-streams-lsl)

**Max speed**: the fastest the pointer may move on each axis, in workspaces per second.
[Guide 6.3](USER_GUIDE.md#63-settings-for-movement-decoders)

**Metadata notes**: Concord's notes on a dataset file: corrections it applied and what the file
does not provide. [Guide 10.3](USER_GUIDE.md#103-acquisition-details)

**Modality**: the kind of recording (intracortical, ECoG, EEG, …) and whether it is implanted, as
the source declares it. [Guide 3.1](USER_GUIDE.md#31-the-row)

## N

**Native format**: how a source's data arrives before Concord converts it.
[Guide 10.6](USER_GUIDE.md#106-capability-contract)

**`navigation`**: commands that move a highlight (up, down, left, right, next, previous).
[Guide 6.4](USER_GUIDE.md#64-settings-for-classifiers)

**Negotiation**: when an application connects, Concord gives it the capabilities it asked for that
the source provides (**Granted**), and lists the others (**Not granted**).
[Guide 10.7](USER_GUIDE.md#107-connected-applications)

**NWB** (Neurodata Without Borders): a standard file format for neurophysiology data. FALCON and
AJILE12 files are NWB.

## O

**Offline held-out score**: how well a model reconstructs recorded labels on held-out data (R² for
movement, balanced accuracy for classes, precision and recall for clicks). It does not show how
well a person could control anything with it. [Guide 5.5](USER_GUIDE.md#55-the-calibrate-panel)

**Offline Replay**: playing back recorded data from a file, labelled as such. Never live.
[Guide 3.5](USER_GUIDE.md#35-recorded-human-data-offline-replay)

**Open Ephys GUI**, **ZMQ Interface**: open-source acquisition software, and the plugin of it that
Concord reads. [Guide 3.8](USER_GUIDE.md#38-live-streams-open-ephys)

**Operator**: the person running the console. [Guide 7.2](USER_GUIDE.md#72-new-research-session)

## P

**Participant screen**: the communication board in its own window, for a second screen facing the
participant. [Guide 11.1](USER_GUIDE.md#111-opening-the-board)

**Passthrough**: using what the source already provides without processing: **Source features
(passthrough)** for features, **Source decoder outputs (passthrough)** for a decoder's output.
[Guide 5.3](USER_GUIDE.md#53-processing-presets)

**Pause / Resume**: stops and continues a source; pausing turns command output off.
[Guide 3.1](USER_GUIDE.md#31-the-row)

**Pipeline**: signal processing (filters, feature extraction) followed by an optional decoder, run
continuously on the connected source. [Guide 10.2](USER_GUIDE.md#102-pipeline-details)

**Playback**: the replay controls of a file: position, **Pause**, speed.
[Guide 3.1](USER_GUIDE.md#31-the-row)

**Plugin**: third-party code that adds a source or a decoder; it runs in its own process.
[Guide 3.9](USER_GUIDE.md#39-plugins)

**`pointer_intent`** (*pointer movement*): a command to move a cursor, as a 2-D velocity.
[Guide 6.5](USER_GUIDE.md#65-authorized-applications)

**Processing preset**: one of the ways **Start decoding** turns a source into features (spike-band
threshold crossings, high-gamma band power, band power, the two passthroughs).
[Guide 5.3](USER_GUIDE.md#53-processing-presets)

**Provenance** (*data kind*): what an event is and where it came from: `raw_signal`,
`processed_feature`, `behavioral_label`, `simulated_intent`, `decoded_intent`, `device_report`,
`runtime`, and whether it was replayed. Only intents can become commands.
[Guide 10.1](USER_GUIDE.md#101-event-stream)

## Q

**Quality**: a score from 0 to 1 on each event, and flags such as `synthetic`, `replayed` or
`timestamp_regression`. [Guide 10.1](USER_GUIDE.md#101-event-stream)

## R

**R²** (coefficient of determination): how much of the variation in recorded movement a decoder
reproduces; 1 is perfect, 0 is no better than always guessing the average, and it can be negative.
[Guide 5.5](USER_GUIDE.md#55-the-calibrate-panel)

**Radial-8**: a calibration task with eight targets around a centre (T15 blocks 0–2).
[Guide 3.5](USER_GUIDE.md#35-recorded-human-data-offline-replay)

**Raw signal** (`raw_signal`): samples as acquired (for example microvolts per channel), as opposed
to features. [Guide 4](USER_GUIDE.md#4-signal-integrity)

**Recording** (file): a file of events Concord wrote while a source was connected; it can be
replayed and used for calibration. [Guide 10.5](USER_GUIDE.md#105-recording)

**`recording`** (capability): a source provides raw sample blocks (and time-aligned markers). Not
the same as the **Recording** feature: a dataset can declare it and still not be recordable.
[Guide 10.6](USER_GUIDE.md#106-capability-contract)

**Reference recording**: the recording the acquisition system's own software makes at the same
time as Concord's, for verification ([HARDWARE_VALIDATION.md](HARDWARE_VALIDATION.md)).

**Replayed** (**↺**): played back from a recording, not happening now.
[Guide 10.1](USER_GUIDE.md#101-event-stream)

**Research session**: a named folder that groups recordings, decoders and a log, and can be
exported. Not the same as a FALCON *Session …* file or a `ses_…` connection id.
[Guide 7](USER_GUIDE.md#7-research-sessions-and-export-the-session-strip)

**Reset**: clears a source that stopped with an error, so you can connect again.
[Guide 2.3](USER_GUIDE.md#23-source-stopped-with-an-error-and-reset)

**Ridge regression**: a simple linear decoder family for continuous movement (Concord's default).
[Guide 5.5](USER_GUIDE.md#55-the-calibrate-panel)

**RMS**, **Threshold (× RMS)**: RMS is a channel's typical noise level; a spike is counted when the
signal crosses a multiple of it (−4.5 by default). [Guide 5.2](USER_GUIDE.md#52-the-start-decoding-panel)

**Router stall** (*input stalled*): command output turned off because the decoder received no
input for too long. [Guide 6.6](USER_GUIDE.md#66-why-command-output-turned-off-last-stopped)

**`runtime`** (data kind): notices from Concord itself, such as "command output stopped".
[Guide 10.1](USER_GUIDE.md#101-event-stream)

## S

**Safe stop**: **Safe stop & disconnect**: command output off, recording closed, decoding stopped,
source disconnected, in that order. Quitting does the same.
[Guide 9](USER_GUIDE.md#9-stopping-safely)

**Scanning**: a board input method: tiles are highlighted in turn and one switch chooses.
[Guide 11.8](USER_GUIDE.md#118-input-methods)

**Schema**: the formal description of Concord's event format (version 1.4), at
*/api/v1/schema/event*. [Guide 10.6](USER_GUIDE.md#106-capability-contract)

**Select**: the basic discrete action; on the board it chooses a tile (or moves, with direct
selection). [Guide 11.8](USER_GUIDE.md#118-input-methods)

**`selection`** (*discrete actions*): commands select, activate and cancel.
[Guide 6.5](USER_GUIDE.md#65-authorized-applications)

**Session**: has several meanings in Concord. A *research session* is yours
([Guide 7](USER_GUIDE.md#7-research-sessions-and-export-the-session-strip)). *Session
19250108T111022* is a FALCON file's own name. `ses_…` in an event is one source connection. The
**Session log** is the console's activity list.

**Session log**: the console's list of what happened, newest first.
[Guide 8](USER_GUIDE.md#8-the-session-log)

**Session recording**: a recording you made, offered for replay under **Session recordings
(replay)**. [Guide 3.6](USER_GUIDE.md#36-session-recordings-replay-and-other-sources)

**SHA-256**: see *Checksum*.

**Signal integrity**: whether data arrives complete and on time.
[Guide 4](USER_GUIDE.md#4-signal-integrity)

**Simulated data**, **synthetic**: generated by software, not recorded from a person.
[Guide 3.4](USER_GUIDE.md#34-simulated-profiles)

**Simulated intent** (`simulated_intent`): input from the simulator controls: an operator standing
in for a participant. Reaches applications without command output, labelled simulated.
[Guide 6.1](USER_GUIDE.md#61-when-commands-reach-an-application)

**Simulated profile**: one of two built-in simulated devices (Profile A, Profile B). Never brain
data, and not a model of any real device. [Guide 3.4](USER_GUIDE.md#34-simulated-profiles)

**Simulator controls**: the pad, **Select**, text and fault buttons for a simulated profile.
[Guide 10.8](USER_GUIDE.md#108-simulator-controls)

**`source_id`**: an LSL stream's identifier, set by its publisher; it tells apart streams with the
same name. [Guide 3.7](USER_GUIDE.md#37-live-streams-lsl)

**Spike band power**: power in the frequency band of spikes, per bin (a T15 feature stream).
[Guide 10.6](USER_GUIDE.md#106-capability-contract)

**Spike-band threshold crossings** (*threshold crossings*): counts of how often a band-passed signal
crosses a threshold below its noise level, per bin; a standard intracortical feature.
[Guide 5.3](USER_GUIDE.md#53-processing-presets)

**Stop control**: the title-bar button that turns command output off immediately.
[Guide 2.1](USER_GUIDE.md#21-controls-in-the-title-bar)

**Subscriber drops**: events an application or console tab could not take in time and lost.
[Guide 10.4](USER_GUIDE.md#104-diagnostics)

**Support report**: a report about your installation without neural or personal data, for
whoever helps you. [Guide 10.13](USER_GUIDE.md#1013-support-report)

**Switch**: the **Connect** button's name while another source is connected; changes source.
[Guide 3.3](USER_GUIDE.md#33-the-connect-a-source-panel)

## T

**T15**: the participant of a published cursor-and-click study whose recordings (Dryad) Concord
replays: four blocks of one day, with the original decoders' outputs.
[Guide 3.5](USER_GUIDE.md#35-recorded-human-data-offline-replay)

**Task grid**: a board layout of N × N word tiles, for grid tasks.
[Guide 11.6](USER_GUIDE.md#116-the-task-grid)

**Telemetry** (`telemetry`): device health numbers. The simulated profiles' values are simulated.
[Guide 10.3](USER_GUIDE.md#103-acquisition-details)

**Test stream**: a stream from `concord publish` for rehearsing without hardware.
[Guide 14.2](USER_GUIDE.md#142-test-streams-concord-publish)

**`text_intent`** (*text*): text sent a character or a word at a time.
[Guide 6.5](USER_GUIDE.md#65-authorized-applications)

**Time correction**: the offset LSL measures between a publisher's clock and this computer's, used
to line up streams. [Guide 10.3](USER_GUIDE.md#103-acquisition-details)

**Train fraction**: the share of calibration data (from the start) used for fitting.
[Guide 5.5](USER_GUIDE.md#55-the-calibrate-panel)

**Trust** (model file): your decision to allow a pickle or joblib model file, which runs code when
loaded. [Guide 5.2](USER_GUIDE.md#52-the-start-decoding-panel)

## U

**Undeclared capability**: data a source sent of a kind it did not declare; refused and counted.
[Guide 10.4](USER_GUIDE.md#104-diagnostics)

**uV, µV**: microvolts, the unit of raw voltage Concord uses. [Guide 3.8](USER_GUIDE.md#38-live-streams-open-ephys)

## V

**Validation level**: how far a component has been validated: software, protocol, hardware, human
participant ([VALIDATION_LEVELS.md](VALIDATION_LEVELS.md)). [Guide 10.11](USER_GUIDE.md#1011-compatibility)

**Velocity dimension**: the selector in **Acquisition details** that chooses which behaviour
dimension the plot shows. [Guide 10.3](USER_GUIDE.md#103-acquisition-details)

## W

**Word list**, **word prediction**: the words of the task grid, and up to three completions of the
word being typed on the letters page. [Guide 11.5](USER_GUIDE.md#115-the-letters-page-and-word-prediction)

**Workspace**: the board's tile area, counted as 1 wide and 1 high; pointer speeds are in
workspaces per second. [Guide 6.3](USER_GUIDE.md#63-settings-for-movement-decoders)

## X

**XDF**: the file format LabRecorder writes.
