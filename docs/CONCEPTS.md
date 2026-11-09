# How Concord works

This page explains the ideas behind Concord in plain language: where data comes from, what
Concord does with it, what the labels on the screen mean, and what *capabilities* are. Read it
once and the console will make sense. To try things step by step, use
[Getting started](GETTING_STARTED.md). To look up a specific button, use the
[user guide](USER_GUIDE.md). Single terms are in the [glossary](GLOSSARY.md).

**Contents**

1. [The big picture](#1-the-big-picture)
2. [Sources: where the data comes from](#2-sources-where-the-data-comes-from)
3. [Data kinds: what each piece of data is](#3-data-kinds-what-each-piece-of-data-is)
4. [Capabilities: what a source can provide and an app can ask for](#4-capabilities-what-a-source-can-provide-and-an-app-can-ask-for)
5. [Decoders: from brain activity to intended movement](#5-decoders-from-brain-activity-to-intended-movement)
6. [Command output: the only way decoded data reaches an app](#6-command-output-the-only-way-decoded-data-reaches-an-app)
7. [Applications and the communication board](#7-applications-and-the-communication-board)
8. [Recordings, research sessions and export](#8-recordings-research-sessions-and-export)
9. [Stopping safely](#9-stopping-safely)
10. [What has and has not been validated](#10-what-has-and-has-not-been-validated)
11. [What Concord never does](#11-what-concord-never-does)

---

## 1. The big picture

```
  SOURCE                      CONCORD (on your computer)                         APPLICATIONS
  ──────                      ──────────────────────────                         ────────────
  simulated device  ─┐
  recorded file      ├──►  receive, check, label  ──►  processing ──► decoder ──► command output ──►  communication
  live lab stream    │     (every piece of data          (features)    (model)    OFF by default     board, your
  plugin            ─┘      gets a "data kind")                                   + authorization    own app
                                    │
                                    └──►  recording, session log, export (for your records)
```

1. A **source** sends data to Concord: a simulated device, a recorded file, a live stream from
   your acquisition software, or a plugin.
2. Concord **checks** every piece of data (complete? in order? on time?) and **labels** it with
   what it is (its *data kind*) and where it came from.
3. Optionally, **processing** turns raw signals into features (for example spike counts per 20 ms)
   and a **decoder** turns features into intended movement or choices.
4. **Command output** is the gate between decoded brain activity and applications. It is off until
   the operator turns it on, and it then reaches only the applications the operator has
   **authorized**.
5. Applications, such as the **communication board** (a screen a participant could use to
   choose words), react to the commands they receive.

Everything runs on your own computer. The console is a web page served by Concord at
`http://127.0.0.1:8000`; nothing is sent to the internet.

---

## 2. Sources: where the data comes from

A **source** is anything Concord receives data from. You choose one with **Connect a source** in
the console; one source is connected at a time.

| Kind of source | What it is | How the console labels it |
| --- | --- | --- |
| **Simulated profiles** (A and B) | Two built-in imaginary devices that generate synthetic signals, plus a pad you use to stand in for a participant. For learning and testing. | *Simulated data*. Every event is marked synthetic. |
| **Recorded human data** | Public recordings from people with implanted electrodes (FALCON H1, T15 cursor + click, AJILE12 ECoG), replayed from files you download. | *Recorded human data, offline replay*. Never "live". |
| **Session recordings** | Recordings you made yourself with Concord, replayed. | *Replay* plus the recording's name. |
| **Live streams** | Data from your lab's acquisition software over Lab Streaming Layer (LSL) or the Open Ephys GUI. | *Live stream, origin unverified*: Concord cannot know whether a stream comes from real hardware. A stream that declares itself prerecorded or synthetic is labelled so. |
| **Plugins** | Small add-on packages that connect other systems: BrainFlow boards, BCI2000, or your own device. Each runs in its own process. | *Plugin*, with its package name and version. |

How to connect your own equipment: [CONNECT_YOUR_EQUIPMENT.md](CONNECT_YOUR_EQUIPMENT.md).

---

## 3. Data kinds: what each piece of data is

Every piece of data in Concord (an *event*) carries a **data kind**, also called its
**provenance**. The data kind decides what Concord may do with it. The most important rule:
**recorded brain activity is never a command**. Only a decoder's output can become a command,
and only through command output (section 6).

| Data kind | Plain meaning | Examples | Can it ever reach an app as a command? |
| --- | --- | --- | --- |
| `raw_signal` | Samples as the source sent them | voltages from an amplifier, a simulated signal | No |
| `processed_feature` | Numbers computed from a signal | spike counts per 20 ms bin, band power | No |
| `behavioral_label` | What the task or the participant did | cursor position, cued movement direction, target | No |
| `simulated_intent` | An operator standing in for a participant on a simulated device | the simulator pad and its **Select** button | Yes, and always labelled *simulated* |
| `decoded_intent` | A decoder's estimate of what the person intended | cursor velocity, a click, a chosen class | Only while command output is on, and only to authorized apps |
| `device_report` / `runtime` | Reports about the device and Concord itself | battery and temperature of a simulated device, connection changes, "command output stopped" | Not a command |

Labels you will see next to the data kind:

- **synthetic**: generated by software, not recorded from a person (simulated profiles, test
  streams).
- **replayed** (shown as **↺** in the event stream): played back from a recording, not
  happening now.
- **model id and origin** on decoded data. The origin is one of:
  - **Concord**: a model running in Concord;
  - **external**: a decoder running in another system, for example BCI2000;
  - **historical**: the recorded output of the original research system's decoder, replayed
    from a dataset.
- **quality**: a score and flags on each event, for example a gap before it or a timestamp
  that went backwards.

The communication board turns these labels into words, for example *simulated input — no
participant* or *demonstration — not the participant's message* for text composed from a
replayed recording.

---

## 4. Capabilities: what a source can provide and an app can ask for

A **capability** is one kind of thing a source can provide, for example "pointer movement" or
"behavior". Capabilities are how Concord stays device-agnostic:

- every **source declares** the capabilities it provides (and details such as the sample
  rate or the number of channels);
- every **application asks** for the capabilities it can use;
- when an application connects, Concord **negotiates**: the app receives the capabilities it
  asked for *and* the source provides. Nothing else reaches it.

This is why the communication board works with any source: it never knows which device is
connected, it only knows which capabilities it was granted. With a source that provides pointer
movement and selection it shows a cursor and clicks; with a source that provides only selection
it scans tiles one by one.

You can see every source's declared capabilities in the console under **Advanced → Capability
contract**, a table with one column per source. The twelve capabilities:

| Capability (as written in the console) | What it means in plain words | Provided by (examples) |
| --- | --- | --- |
| `recording` | Raw multichannel samples (and time-aligned labels) | Simulated profiles, LSL signal streams, Open Ephys; some recorded datasets declare it too |
| `neural_features` | Processed neural features, e.g. spike counts per bin | FALCON H1 and T15 files, LSL streams of binned counts, the processing pipeline |
| `behavior` | What the task or participant did (cursor position, cued movement) | FALCON H1, T15, an LSL behavior stream you attach |
| `kinematic_intent` | A continuous movement estimate with several dimensions (simulated, or decoded by a model) | Decoders; shown in the console, and reaches apps only as pointer movement through command output |
| `pointer_intent` | A command to move a cursor (2-D velocity) | Simulated Profile A; decoded output through command output |
| `selection` | A discrete choice: select, activate, cancel | Simulated profiles A and B; a click or classifier decoder through command output |
| `navigation` | Move a highlight: up, down, left, right, next, previous | A classifier decoder through command output |
| `text_intent` | Text, a character or a word at a time | Simulated Profile B |
| `telemetry` | Device health numbers (battery, temperature, link quality) | Simulated profiles (the numbers are simulated) |
| `device_status` | Connection and streaming changes | Every source |
| `control_status` | Notices that command output for an app started or stopped, so the app can stop safely | Concord itself |

The console uses plainer names for the four command capabilities: **pointer movement**
(`pointer_intent`), **discrete actions** (`selection`), **navigation** and **text**
(`text_intent`). You see these names under **Command output → Authorized applications**.

Common details in the capability table:

- `rate_hz`: how many times per second;
- `dims`: the dimensions, e.g. `x, y`;
- `bin_ms`: the length of one feature bin in milliseconds;
- `unit`: for example `uV` (microvolts), `count`, or `arbitrary` when the source does not say;
- `max_speed`: the fastest pointer velocity;
- `text_modes`: character and/or word;
- `streams`: the separate feature streams a source carries.

---

## 5. Decoders: from brain activity to intended movement

A **decoder** turns neural features into an estimate of what the person intended: a cursor
velocity, a click, or one of a few choices (for example rest, left, right).

- **Processing (presets)** come first and turn raw samples into features. For example:
  - *Spike-band threshold crossings* for 30 kHz intracortical signals;
  - *High-gamma band power* for ECoG;
  - *Band power* for EEG rhythms.

  Recorded datasets usually carry features already (*Source features (passthrough)*).
- **Decoder families** built in:
  - *ridge regression* and *Kalman filter* for continuous movement;
  - *LDA classifier* for a few discrete classes;
  - *click classifier* for a click.

  Other model files and decoder plugins can be installed ([DECODER_SDK.md](DECODER_SDK.md)).
- **Calibration** fits a decoder from a recording that contains both neural features and
  behavior labels. Concord trains on the first part and scores on a later, held-out part. The
  score (e.g. *offline held-out R²*) says how well the model reconstructs recorded labels. It
  does **not** say how well a person could control anything with it.
- **Compatibility checks** refuse a model whose expected input does not match the connected
  source (number of channels, bin size, feature type). They also refuse a model on the same
  session it was trained on (that would be leakage). Running a model on a different source is
  allowed only if you explicitly override, and the output is then marked as reduced quality.
- **A source's own decoder outputs.** Some recordings (T15) carry the output of the original
  research system's decoder; external systems such as BCI2000 send their own decoded output.
  **Source decoder outputs (passthrough)** forwards these unchanged, labelled with their
  origin (*historical* or *external*).

---

## 6. Command output: the only way decoded data reaches an app

**Command output** (the fourth row of the console) is the gate between a decoder and
applications.

1. It is **off** until you click **Start control**. While it is off, decoded output is shown
   in the console but never reaches an application.
2. Its **settings** map decoder outputs to commands:
   - two dimensions become pointer velocity (with **Gain**, **Dead-zone**, **Max speed** and
     **Invert y**);
   - an output can become a click;
   - for classifiers, rules turn a class into an action (select, move left, type a word…).
3. It reaches only applications you **Authorize**, and only for the kinds of command you
   authorized. **Revoke** takes that back; authorization lasts until you revoke it, even
   across sources and sessions.
4. **Stop control** (top right of the console) turns it off at once. Disconnecting the source,
   a stall in the decoder's input, or a safe stop also turn it off. The app is told (the
   `control_status` capability) and enters a safe state: the cursor freezes, nothing is
   selected.

Simulated profiles are the exception: their input is *simulated intent*, labelled as such, and
reaches the board without command output, because no brain data is involved.

---

## 7. Applications and the communication board

An **application** is any program that connects to Concord to receive data or commands. It uses
only the SDK (the documented interface), so it works with any source. Concord ships:

- **the communication board**, a participant screen for composing messages. It has five input
  methods, and Concord chooses one from the capabilities granted:

  | Input method | Needs | How a choice is made |
  | --- | --- | --- |
  | Pointer and click | pointer movement + discrete actions | the cursor moves; a click chooses the tile under it |
  | Pointer with dwell selection | pointer movement | resting the cursor on a tile for a set time chooses it |
  | Directional navigation | navigation | a highlight moves; a selection (or resting) chooses |
  | Direct selection | discrete actions with several kinds | select moves, activate chooses, cancel undoes |
  | Scanning | discrete actions | tiles light up in turn; any selection chooses the lit one |

- two reference apps for developers (`backend/examples/reference_app/`).

Text composed from replayed recordings is labelled *demonstration — not the participant's
message*. The board's **Speak** uses ordinary computer speech; it is not neural speech
decoding.

---

## 8. Recordings, research sessions and export

- A **recording** saves the standardized events of the connected source to a file in your data
  folder. It replays later as a source (*Session recordings*). It can also train a decoder.
  - Simulated and live sources can be recorded; recorded files cannot (they already are
    recordings).
  - A recording stops by itself at a time or size limit, which you can change in the
    configuration file.
- A **research session** groups everything you do into one folder: the recordings, the decoders
  you calibrate, the settings you use, and a log of what happened.
- An **export** packs a session into one zip file with the session log, versions, sources,
  settings, models and (if you choose) recordings, plus instructions. `concord reproduce <zip>`
  checks the files and re-runs the decoder evaluation. A session without a decoder has nothing
  to re-run, and `reproduce` then only checks the files.

---

## 9. Stopping safely

There are three levels of stop:

- **Stop control** turns command output off; the source keeps streaming.
- **Safe stop & disconnect** stops everything in order: command output, recording, decoding,
  and the source.
- **Quitting Concord** performs a safe stop first, so recordings are closed properly.

If Concord or the computer stops abruptly, a recording that was being written is kept and
marked *incomplete* at the next start.

---

## 10. What has and has not been validated

Concord is research software at an early stage:

- it has been tested in software, with protocol test sources and real recorded data;
- it has **never been tested with acquisition hardware or with a participant**;
- it is **not a medical device**.

[VALIDATION_LEVELS.md](VALIDATION_LEVELS.md) lists, for every part, what has been tested and how.
The console's **Advanced → Compatibility** shows the level of every integration. The levels are
derived from evidence; nothing has reached hardware-verified or human-validated.

---

## 11. What Concord never does

- **It never sends anything to a device.** It only receives. The single documented exception is
  a liveness "heartbeat" message the Open Ephys plugin expects.
- **It never treats recorded brain activity as a command.**
- **It never labels a replay as live**, or simulated data as brain data.
- **It never claims compatibility with an implant.** No implant vendor is supported.
- **It accepts no connections from other computers.** It listens only on your own computer
  (`127.0.0.1`), because it has no user accounts or encryption.
