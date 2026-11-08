# Getting started with BrainOS

This guide takes you from downloading BrainOS to replaying real human brain recordings, in
about 20 minutes, **without using a terminal**. Every step shows what you should see.

> **Before you start.** BrainOS is research software. It *receives* data from acquisition
> systems and recordings and never sends anything to a device. It has been tested in software
> and with test sources only, **never with acquisition hardware or a participant**, and it is
> **not a medical device** ([validation levels](VALIDATION_LEVELS.md)).

**Contents**

1. [Install](#1-install)
2. [First launch: the console](#2-first-launch-the-console)
3. [Try it with a simulated device](#3-try-it-with-a-simulated-device-5-minutes)
4. [Replay real human recordings](#4-replay-real-human-recordings-10-minutes)
5. [Run a research session and export it](#5-run-a-research-session-and-export-it)
6. [Stored data, support report and quitting](#6-stored-data-support-report-and-quitting)
7. [Where to go next](#7-where-to-go-next)

---

## 1. Install

### On a Mac (Apple Silicon, macOS 14 Sonoma or later)

1. Download **[BrainOS-macos-arm64.dmg](https://github.com/arnavhiteshpatel-cloud/brainos/releases/latest/download/BrainOS-macos-arm64.dmg)**
   (from the [Releases page](https://github.com/arnavhiteshpatel-cloud/brainos/releases/latest)).
2. Double-click the downloaded `.dmg` and drag **BrainOS** onto **Applications**.
3. Open BrainOS from Applications. The first time, macOS blocks it because the app is not
   signed with an Apple developer certificate:
   - **macOS 15 Sequoia or later:** click **Done**, open **System Settings → Privacy &
     Security**, scroll down to *Security* and click **Open Anyway** next to "BrainOS was
     blocked", confirm with your password, then open BrainOS again and click **Open**.
   - **macOS 14 Sonoma:** in Applications, **Control-click** (or right-click) BrainOS →
     **Open** → **Open**.

   You only do this once.

Intel Macs and macOS 13 or older: use the Python installation in
[INSTALL_MAC.md](INSTALL_MAC.md) (it needs the terminal).

### On Linux (x86_64, e.g. Ubuntu 22.04 or later)

1. Download **[BrainOS-linux-x86_64.tar.gz](https://github.com/arnavhiteshpatel-cloud/brainos/releases/latest/download/BrainOS-linux-x86_64.tar.gz)**.
2. Extract it (right-click → *Extract Here* in most file managers).
3. Open the `BrainOS` folder and run the program named **BrainOS** (double-click it if your
   file manager runs programs; otherwise run `./BrainOS/BrainOS` in a terminal once).

### Windows

Not supported yet.

---

## 2. First launch: the console

When BrainOS starts, a small window says **"BrainOS is running at http://127.0.0.1:8000"**
and your web browser opens the **console** (if it does not, click **Open console** in that
window). The console is the operator's screen: everything below happens there. BrainOS runs
only on your computer; nothing is sent to the internet.

![The console on first launch: no source connected](images/01-console-first-launch.png)

The console is one screen, top to bottom:

| Part | What it is for |
| --- | --- |
| **Title bar** | The connected source and its state (*Streaming*, *Recording*…). **Stop control** stops decoded commands immediately. |
| **Session strip** | Start a **research session** (it groups recordings, decoders and a log for export). **Safe stop & disconnect** stops everything. |
| **Acquisition source** | Where the brain data comes from. **Connect a source** opens the list of sources. |
| **Signal integrity** | Whether data is arriving complete and on time: channels, data received, delay. |
| **Decoder** | Turns brain activity into intended movement or choices: **Start decoding**, **Calibrate…** |
| **Command output** | Lets the decoder send commands to applications you **Authorize**; off unless you start it. **Open participant screen** opens the communication board. |
| **Session log** | What happened, newest first. |
| **Advanced** | Details for experts: event stream, pipeline, acquisition details, diagnostics, recording, simulator, stored data, support report and more. |

The [user guide](USER_GUIDE.md) explains every control in depth.

---

## 3. Try it with a simulated device (5 minutes)

Simulated devices generate synthetic data inside BrainOS. They are for learning and testing;
they are never brain data, and BrainOS labels them as simulated everywhere.

1. Click **Connect a source**. A panel lists every kind of source:

   ![The Connect a source panel](images/02-connect-a-source.png)

2. Under **Simulated profiles**, click **Connect** next to **Simulated Profile A** (32
   channels at 1,000 Hz, with a simulated pointer and click).

   The title bar now says **Streaming · Simulated data**, the signal appears under **Signal
   integrity** with the verdict **Good**, and the session log records the connection:

   ![Simulated Profile A streaming](images/03-simulated-profile-streaming.png)

3. Open the **participant screen**: in **Command output**, click **Open participant screen**.
   A second window shows the **communication board**, the screen a participant would use.
   Arrange it next to the console.

4. Act as the participant. In the console, open **Advanced → Simulator controls**:

   ![Simulator controls](images/04-simulator-controls.png)

   Drag the dot in the square pad (or hold the arrow keys / W A S D) to move the board's
   cursor onto a tile, then click **Select** (or press Space). The tile's word appears in the
   board's message bar. The board says *simulated input — no participant*, so nobody can
   mistake it for a person's message.

   ![The communication board on the participant screen](images/05-participant-screen.png)

5. Try a fault: under **Fault injection**, click **Link drop**. The title bar shows the
   connection being restored and the session log records it. BrainOS reconnects on its own
   and counts what was lost.

6. Click **Disconnect** (in **Acquisition source**) when you are done.

---

## 4. Replay real human recordings (10 minutes)

BrainOS can replay public recordings from people with implanted electrode arrays. Replays are
always labelled **Offline Replay**: they are files, not a live implant. BrainOS checks every
file against a pinned SHA-256 checksum and shows whether it matches.

### 4.1 Intracortical spiking: FALCON H1 (about 9 MB, no account needed)

Two recording blocks from one participant with two 96-channel arrays in motor cortex
(176 channels, 20 ms bins) and the cued reach-and-grasp movements
([dataset page on DANDI](https://dandiarchive.org/dandiset/000954/draft), CC-BY-4.0).
**Downloading means agreeing to the dataset's Data Use Agreement**: no attempt to re-identify
or contact the participant, and no redistribution of the files.

1. Download both files in your browser (each link downloads one file directly from the DANDI
   archive):
   - [sub-HumanPitt-held-in-calib_ses-19250108T110520.nwb](https://api.dandiarchive.org/api/assets/e40a2eca-883d-4c80-81e3-4203a49506b5/download/) (5.5 MB)
   - [sub-HumanPitt-held-in-calib_ses-19250108T111022.nwb](https://api.dandiarchive.org/api/assets/98f1e471-ad68-4006-b090-9a3e347852e6/download/) (3.2 MB)
2. Put them in BrainOS's **datasets** folder (create the `datasets` folder if it does not
   exist):

   | You installed | Data folder | Put the files in |
   | --- | --- | --- |
   | Mac app | `~/Library/Application Support/BrainOS/data` | `…/data/datasets/` |
   | Linux bundle | `~/.local/share/brainos/data` | `…/data/datasets/` |
   | From source (`make setup`) | `data/` in the repository | `data/datasets/` |

   On a Mac: in Finder choose **Go → Go to Folder…**, paste
   `~/Library/Application Support/BrainOS/data`, press Return, create a folder named
   `datasets` there and move both `.nwb` files into it. The **Stored data** section of the
   console (Advanced) shows the exact data folder of your installation.
3. Reload the console page. **Connect a source → Recorded human data (offline replay)** now
   lists two sessions (`Session 19250108T110520` and `Session 19250108T111022`).
4. Click **Connect** next to one of them. The title bar says **Streaming · Recorded human data,
   offline replay**:

   ![A recorded human session replaying](images/09-recorded-human-data.png)

   Open **Playback** in the source panel to **Pause** / **Resume** the replay or change its
   speed (0.5×, 1×, 2×, 4×, 8×); the position is shown next to the recording's length.
   **Disconnect** ends the replay.
5. Open **Advanced → Acquisition details** to see exactly what you are replaying: dataset,
   license, whether the file's **SHA-256 matches** the archive, what was recorded and the
   citation to use. Below these details, **Recorded neural activity** shows the replayed spike
   counts of all 176 channels and the participant's recorded movement:

   ![Dataset details with checksum verification](images/10-dataset-details.png)

   The **Decoder** line appears when a decoder trained on the *other* block is installed: a
   decoder is never shown on the data it was trained on. That demo decoder is created by
   `make model` in a source installation ([README](../README.md#developers-install-from-source)).

### 4.2 Cursor control and click: T15 (about 96 MB, free Dryad account)

Recordings from a participant controlling a computer cursor and clicking with signals from
speech motor cortex (256 electrodes; threshold crossings and spike band power), with the
original research system's decoder outputs (Singer-Clark et al. 2025,
[dataset page on Dryad](https://datadryad.org/dataset/doi:10.5061/dryad.prr4xgxzq), CC0).

1. On the dataset page, sign in to Dryad (free) and download these four files:
   `t15_day00468_block00_radial8_calibration_task.mat`,
   `t15_day00468_block01_radial8_calibration_task.mat`,
   `t15_day00468_block02_radial8_calibration_task.mat` and
   `t15_day00468_block03_grid_evaluation_task.mat`.
2. Put them in the `datasets` folder from step 4.1.2 (any subfolder works).
3. Reload the console. **Connect a source → Other sources** lists the blocks as **Recorded
   Human Intracortical Data (cursor + click) — Offline Replay**. Connect the grid block to see
   the task replayed, including the original decoders' outputs (labelled *historical*).

What BrainOS's own decoders achieve on these recordings is described in
[CURSOR_CLICK.md](CURSOR_CLICK.md) and [NEURAL_COMMUNICATION.md](NEURAL_COMMUNICATION.md).

### 4.3 Human ECoG: AJILE12 (about 157 MB)

These recordings are slices of very large files that BrainOS extracts and verifies itself, so
they need one command (the only one in this guide). On a Mac with the app, open the Terminal
app and run:

```bash
/Applications/BrainOS.app/Contents/MacOS/BrainOS dataset ajile12
```

It streams only the two pinned slices from the archive and checks each against its pinned
digest. From a source installation, run `make dataset-ecog` instead (the tested path). Details:
[ECOG.md](ECOG.md).

---

## 5. Run a research session and export it

A research session groups everything you do (recordings, decoders, a log) so it can be
exported and reproduced.

1. In the session strip, click **New session**. Give it a name (**no participant identifiers**),
   the operator and notes, then **Start session**:

   ![Starting a research session](images/06-new-session.png)

2. Connect a source (for example Simulated Profile A).
3. Record: open **Advanced → Recording**, click **Start recording**; the title bar shows
   **Recording**. Recordings stop by themselves after 5 minutes when they include the raw
   signal (or 1 hour for *Features and labels only*); the limits can be changed in the
   [configuration file](USER_GUIDE.md#configuration-file).

   ![A session with a recording in progress](images/07-session-recording.png)

4. Click **Safe stop & disconnect**: it stops command output, closes the recording, stops
   decoding and disconnects the source, in that order.
5. Click **Session and export…**, tick **Include the session's recordings** if you want the
   export to be reproducible, and click **Create export bundle**. Download the zip from the
   link that appears. It contains the session log, software versions, source and pipeline
   settings, decoder models and their calibration reports, and a `REPRODUCE.md`.

   ![Session details and export](images/08-session-export.png)

6. Click **End session…** when you are finished.

---

## 6. Stored data, support report and quitting

**Advanced → Stored data** lists your recordings, decoder models and sessions, their size and
the data folder (readable only by your user account), and deletes what you no longer need
(it asks for confirmation). **Advanced → Support report → Create support report** produces a
report of versions, ports, permissions and recent problems **without any neural or personal
data**; attach it when you [report a problem](https://github.com/arnavhiteshpatel-cloud/brainos/issues/new/choose).

![Stored data and support report](images/12-stored-data-and-support.png)

**Quitting:** quit BrainOS (⌘Q on a Mac, or close the small BrainOS window). Quitting performs
a safe stop first, so recordings are closed properly. If BrainOS ever stops unexpectedly, the
next start keeps every complete part of an interrupted recording and marks it *incomplete*.

---

## 7. Where to go next

| You want to… | Read |
| --- | --- |
| Understand every control in the console | [User guide](USER_GUIDE.md) |
| Connect your lab's acquisition system (LSL, Open Ephys, BrainFlow, BCI2000) | [Lab setup](LAB_SETUP.md), then the [lab guide](LAB_GUIDE.md) |
| Plan the first session with real equipment | [First lab session](FIRST_LAB_SESSION.md) |
| Verify that BrainOS receives exactly what your acquisition software records | [Hardware validation](HARDWARE_VALIDATION.md) |
| Know what the datasets are and how they are verified | [Datasets](DATASETS.md) |
| Know what BrainOS has and has not been validated for | [Validation levels](VALIDATION_LEVELS.md), [limitations](../LIMITATIONS.md) |
| Fix a problem | [Troubleshooting](TROUBLESHOOTING.md), [FAQ](FAQ.md) |
