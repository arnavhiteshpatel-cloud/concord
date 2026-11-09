# Getting started with Concord

This guide takes you from downloading Concord to driving a communication board with a real
person's recorded brain activity. Follow it in order; every step says what to click, what you
should see, and what it means. Nothing is assumed: if you have never used Concord, start at
the top.

> **Before you start.** Concord is research software:
>
> - It *receives* data from acquisition systems and recordings and never sends anything to a
>   device.
> - It has been tested in software and with test sources only, **never with acquisition
>   hardware or a participant**.
> - It is **not a medical device**.
>
> See [what has been validated](VALIDATION_LEVELS.md).

**New to the ideas?** Read [How Concord works](CONCEPTS.md) first (10 minutes). It explains
sources, data kinds, capabilities, decoders and command output in plain language. Look up any
unfamiliar word in the [glossary](GLOSSARY.md).

| Part | What you do | Time | Terminal needed? |
| --- | --- | --- | --- |
| [1. Install and open Concord](#1-install-and-open-concord) | Download, install, start | 5 min | No (Mac); one command on some Linux desktops |
| [2. A tour of the console](#2-a-tour-of-the-console) | Learn what is on the screen | 5 min | No |
| [3. A simulated device and the communication board](#3-a-simulated-device-and-the-communication-board) | Move a cursor and choose words yourself | 10 min | No |
| [4. Replay a real human recording](#4-replay-a-real-human-recording-falcon-h1) | Replay intracortical recordings | 10 min | No |
| [5. Let a recorded decoder drive the board](#5-let-a-recorded-decoder-drive-the-board-t15-cursor--click) | Cursor and clicks from a recording | 15 min | No (needs a free Dryad account) |
| [6. Human ECoG](#6-human-ecog-ajile12-optional) (optional) | Replay a cortical-surface recording | 5 min | Yes, one command |
| [7. A research session: record and export](#7-a-research-session-record-and-export) | Keep a reproducible record | 10 min | No (one optional command) |
| [8. Stored data, support report and quitting](#8-stored-data-support-report-and-quitting) | Tidy up and quit | 5 min | No |
| [9. Where to go next](#9-where-to-go-next) | Your own equipment, every button | | |

**What you need:**
- a Mac with Apple Silicon (M1 or later) and macOS 14 or later, or a Linux PC (x86_64, e.g.
  Ubuntu 22.04 or later);
- a current web browser (Chrome, Firefox, Safari or Edge);
- about 700 MB of free disk space: Concord itself takes about 350 MB, the demo recordings about
  300 MB.

Windows is not supported yet.

---

## 1. Install and open Concord

### On a Mac

1. Download **[Concord-macos-arm64.dmg](https://github.com/arnavhiteshpatel-cloud/concord/releases/latest/download/Concord-macos-arm64.dmg)**
   (all files are on the [Releases page](https://github.com/arnavhiteshpatel-cloud/concord/releases/latest)).
2. Double-click the downloaded `.dmg`. A window opens: drag **Concord** onto **Applications**.
   Then eject the disk image: in Finder's sidebar, click the eject button next to it.
   Always start Concord from **Applications**, not from the disk-image window.
3. Open Concord from **Applications**. The first time, macOS refuses to open it, because the app
   is not signed with an Apple developer certificate. Allow it once:
   - **macOS 15 Sequoia or later:**
     1. Click **Done** in the message.
     2. Open **System Settings → Privacy & Security** and scroll down to *Security*.
     3. Click **Open Anyway** next to "Concord was blocked…" and confirm with your password.
     4. Open Concord again, and click **Open Anyway** (or **Open**) in the dialog that follows.
   - **macOS 14 Sonoma:** in **Applications**, hold **Control** and click Concord (or
     right-click it) → **Open** → **Open**.

   You only do this once. Later, open Concord like any other app.

Intel Macs and macOS 13 or older: use the Python installation in [INSTALL_MAC.md](INSTALL_MAC.md).

### On Linux

1. Download **[Concord-linux-x86_64.tar.gz](https://github.com/arnavhiteshpatel-cloud/concord/releases/latest/download/Concord-linux-x86_64.tar.gz)**
   into your **Downloads** folder.
2. Extract it there (right-click → *Extract Here* in most file managers). This creates a folder
   named `Concord` inside **Downloads**.
3. Start it. Double-click `Concord/Concord`. If nothing happens (many file managers do not start
   programs this way), open a terminal and run these two commands. The first goes to the folder
   where you extracted Concord; the second starts it:

   ```bash
   cd ~/Downloads
   ./Concord/Concord
   ```

   Keep that terminal open while you use Concord. Next time, start it the same way.

### What you should see

A small window titled **Concord** opens, with your browser behind it:

```
┌──────────────────────────────────────────────┐
│ Concord is running                           │
│ http://127.0.0.1:8000                        │
│ Research use only · not a medical device ·   │
│ read-only. Quitting stops command output,    │
│ closes any recording and disconnects the     │
│ source.                                      │
│ [ Open console ]  [ Stop and quit ]          │
└──────────────────────────────────────────────┘
```

- Your web browser opens the **console** at `http://127.0.0.1:8000`. If it does not, click
  **Open console**.
- **Keep this small window open**: Concord runs for as long as it is open. **Stop and quit**
  ends Concord safely (section 8).
- `127.0.0.1` means "this computer". Concord runs entirely on your machine and sends nothing to
  the internet.

> **No small window on Linux, and the terminal says `running headless`?** Concord is running
> anyway; only its small window could not be shown (for example over a remote connection).
> Open `http://127.0.0.1:8000` in your browser yourself. To quit, press **Ctrl-C** in that
> terminal.

> **No small window, or the console looks different from this guide?** Another copy of Concord
> is probably already running: an older version, or one started from a terminal (`make run`,
> `concord start`). The new app then only opens that copy's console, which uses that copy's
> data folder.
>
> **Check:** the top-left of the console shows **Concord** and its version. It must match the
> version on the Releases page you downloaded from (this guide was written for **0.3.1**). An
> older number means you are looking at another copy.
>
> **Fix:**
> 1. Quit the other copy: its window → **Stop and quit**, or Ctrl-C in its terminal.
> 2. If you can't find it, see which program holds the console's address. On a Mac, run
>    `lsof -nP -iTCP:8000 -sTCP:LISTEN` in Terminal. On Linux, run `ss -ltnp 'sport = :8000'`.
> 3. Open Concord again.

### Commands in this guide

You need no commands for most of this guide. The few optional ones are typed in a terminal
(Mac: the **Terminal** app), always the same way:

- **Mac:** `/Applications/Concord.app/Contents/MacOS/Concord` followed by the command, for
  example `/Applications/Concord.app/Contents/MacOS/Concord dataset ajile12`.
- **Linux:** first `cd ~/Downloads`, then `./Concord/Concord` followed by the command, for
  example `./Concord/Concord dataset ajile12`.

Each command in this guide is written out for both. (If you installed Concord with Python
instead, as in [INSTALL_MAC.md](INSTALL_MAC.md), type `concord` followed by the command.)

---

## 2. A tour of the console

The console is the operator's screen: everything in this guide happens there. It is one page,
top to bottom:

![The console on first launch, with its parts numbered](images/01-console-first-launch.png)

| # | Part | What it is for |
| --- | --- | --- |
| 1 | **Title bar** | **Concord** and its version; the connected source and its state (for example *Streaming · Simulated data*, *Paused*, *Recording*). On the right, **Stop control** stops decoded commands at once; it is grey until command output is running. |
| 2 | **Session strip** | **New session** starts a *research session* that groups your recordings, decoders and a log for export (section 7). **Safe stop & disconnect** stops everything in a safe order. |
| 3 | **Acquisition source** | Where the data comes from. **Connect a source** opens the list of sources. Once something is connected, the buttons become **Change source** and **Disconnect**. |
| 4 | **Signal integrity** | Whether data is arriving complete and on time: a verdict (*Good*, *Gaps detected*, *No signal*…), live traces, the number of channels, data received and the delay. |
| 5 | **Decoder** | Turns brain activity into intended movement or choices. **Start decoding** and **Calibrate…** appear once a source is connected. |
| 6 | **Command output** | The gate between a decoder and applications: off until you click **Start control**, and only for applications you **Authorize**. **Open participant screen** opens the communication board in its own window. |
| 7 | **Session log** | What happened, newest first. |
| 8 | **Advanced** | At the very bottom of the page, closed until you click it. It holds the details: event stream, pipeline, acquisition details, diagnostics, recording, simulator, stored data, support report and more. |

**One thing that surprises everyone:** before you have opened anything, **Command output**
already lists a **Communication Board** with an **Authorize** button, and says
"1 application connected · Communication Board waiting for: a source". That board is the
preview built into **Advanced → Communication board**. **Do not click Authorize yet**:
section 5 explains when you need it. Once you open the participant screen (section 3.2), it
says **2 applications connected** and lists the board twice: the preview and the board window.
That is normal.

Every control is explained in the [user guide](USER_GUIDE.md).

---

## 3. A simulated device and the communication board

Simulated devices generate synthetic data inside Concord, for learning and testing. They are
never brain data, and Concord labels them *simulated* everywhere. Here you play the role of a
participant and choose words on the communication board yourself.

### 3.1 Connect a simulated device

1. In **Acquisition source**, click **Connect a source**. A panel lists every kind of source:

   ![The Connect a source panel on a fresh installation](images/02-connect-a-source.png)

   *Recorded human data* says "No recorded datasets yet" until you add recordings in
   section 4. That is expected. The *Live streams* and *Plugins* parts are for your own
   equipment; you don't need them in this guide (see section 9).
2. Under **Simulated profiles**, click **Connect** next to **Simulated Profile A** (32 channels at
   1,000 Hz, with a simulated pointer and click).

**What you should see:**
- The title bar says **Streaming · Simulated data**.
- **Signal integrity** shows moving traces, the verdict **Good** and **Channels 32 of 32**.
- The session log says the source connected.

![Simulated Profile A streaming](images/03-simulated-profile-streaming.png)

What the figures mean:
- **Channels**: how many channels arrived in the latest block, out of how many the source
  declares.
- **Data received (%)**: measured only for live LSL and Open Ephys streams; for simulated and
  recorded sources it shows **—**.
- **Delay to this screen (ms)**: how long data takes from Concord to this page; a few
  milliseconds is normal.

### 3.2 Open the participant screen (the communication board)

In **Command output**, click **Open participant screen**. A second window opens with the
**communication board**, the screen a participant would use to compose messages. Put it next
to the console and make it large enough to see every tile. If nothing opens, your browser
blocked the pop-up: allow pop-ups for `127.0.0.1:8000`.

![The communication board](images/05-participant-screen.png)

*(The picture shows the board after one word was chosen in 3.3; yours starts with an empty
message bar.)*

What is on the board:
- **Header:** *Communication board*, *Research use only*, the input method in use (here
  *Pointer and click*), and **Settings**.
- **Input line:** where the input comes from, here *Input: simulated input · synthetic data*.
- **Message bar:** the message being composed. Once a word is chosen, a label under it says
  where the words came from: *simulated input — no participant*.
- **Tiles:** phrases (*Yes*, *No*, *Hello*, *Thank you*, *Help*…), **Letters** (a keyboard page
  with word prediction), **Delete word**, **Undo**, **Clear** and **Speak** (reads the message
  aloud with ordinary computer speech, not neural speech decoding).
- **History:** spoken messages (shown when the window is wide enough).

**You cannot click the tiles with the mouse.** The board reacts only to input from Concord,
because that is how a participant would use it. In this section the input comes from you,
through the simulator. (The board's hint *click to choose it* means the participant's click:
here, **Select** in the simulator.)

### 3.3 Move the cursor and choose a word

1. In the console, scroll to the bottom, click **Advanced** to open it, then click **Simulator
   controls**. This section is listed only while a simulated profile is connected.

   ![Simulator controls](images/04-simulator-controls.png)

2. The square pad works like a **joystick**: drag the dot away from the centre and the board's
   cursor *keeps moving* in that direction, faster the further you drag; let go and the dot
   springs back and the cursor almost stops. (Profile A adds a little random jitter, like a real
   decoder, so the cursor keeps drifting slowly.) Use small, short movements.

   With the keyboard: click once on an empty part of the console page, then press and hold an
   arrow key (or W, A, S, D) **briefly**: about a quarter of a second moves the cursor about one
   tile, and a one-second hold crosses the whole board. The keys work only while the console
   window is in front.
3. When the cursor (a ring) is on a tile, click **Select** (or press Space).

**What you should see:** the tile's word appears in the board's message bar, labelled
*simulated input — no participant*, so nobody can mistake it for a person's message. "N sent"
under the pad counts your selections.

Simulated input reaches the board directly because no brain data is involved. Decoded brain
data never does: it needs **Start control** and **Authorize** (section 5).

### 3.4 Try a fault (optional)

Under **Fault injection**, each button makes the simulated device misbehave, so you can see how
Concord reacts. Each fault is also counted in **Advanced → Diagnostics → Counters** (*link
errors*, *decode errors*, *timestamp regressions*).

| Button | What it simulates | What you should see |
| --- | --- | --- |
| **Link drop** | A brief loss of connection | The session log shows *Link lost, reconnecting*, then *Streaming (reconnected after 1 attempt(s))*. It takes a fraction of a second, so the title bar barely changes. The counts are in **Advanced → Diagnostics** (*Reconnects ok / tried*). |
| **Link failure** | A connection that cannot be restored | The title bar says *Source stopped with an error*; the source row shows the error and a **Reset** button. Click **Reset**, then **Connect a source → Connect** next to **Simulated Profile A**, and reopen **Advanced → Simulator controls** to try the next fault. |
| **Malformed packet** | A corrupted data packet | The session log shows *Decode error: CRC mismatch*; the bad packet is dropped and counted. |
| **Clock regression** | A timestamp that goes backwards | The session log shows *Timestamp regression*; the event is flagged in its quality. |

### 3.5 Finish

1. On the board, the message stays until you clear it, so the next words don't mix with these:
   press **Clear** by moving the cursor onto it and selecting, or close the board window.
2. In the console, click **Disconnect** in **Acquisition source**. The board says
   *Paused — device disconnected (operator disconnect)*.

---

## 4. Replay a real human recording (FALCON H1)

Concord can replay public recordings from people with implanted electrodes:
- They are always labelled **Offline Replay**: they are files, not a live implant.
- Concord checks every file against a pinned SHA-256 checksum, a fingerprint published with the
  dataset, and refuses a file that does not match.

**FALCON H1** (about 9 MB, no account needed): two recording blocks from one participant with
two 96-channel arrays in motor cortex. They contain spike counts in 176 channels every 20 ms
(the dataset provides 176 of the 192 electrodes; it does not list which were left out), plus
the cued reach-and-grasp movements the participant attempted.
([Dataset page on DANDI](https://dandiarchive.org/dandiset/000954/draft), license CC-BY-4.0.)

> **Downloading means agreeing to the dataset's Data Use Agreement** (on the DANDI page): no
> attempt to re-identify or contact the participant, and no redistribution of the files.

### 4.1 Download the two files

Click each link; your browser downloads one file directly from the DANDI archive:
- [sub-HumanPitt-held-in-calib_ses-19250108T110520.nwb](https://api.dandiarchive.org/api/assets/e40a2eca-883d-4c80-81e3-4203a49506b5/download/) (5.8 MB)
- [sub-HumanPitt-held-in-calib_ses-19250108T111022.nwb](https://api.dandiarchive.org/api/assets/98f1e471-ad68-4006-b090-9a3e347852e6/download/) (3.3 MB)

If your browser saves a second copy with a name like `… (1).nwb`, delete the extra copy.

### 4.2 Put them in Concord's datasets folder

Concord keeps everything in one **data folder**. Recordings you download go in a folder named
`datasets` inside it.

1. **Find the folder.** The quickest way: click **Connect a source**. Under *Recorded human
   data*, Concord shows the exact folder to put recordings in: *Put downloaded dataset files in
   …/data/datasets …*. Select and copy that path, then close the panel.

   The same data folder is also the first line (**Data directory**) of **Advanced → Stored
   data**, at the bottom of the console. It is normally:

   | You installed | Data folder |
   | --- | --- |
   | Mac app | `~/Library/Application Support/Concord/data` |
   | Linux bundle | `~/.local/share/concord/data` |
   | Python install (`concord start`) | Mac: `~/Library/Application Support/Concord/data`; Linux: `~/.local/share/concord/data` |
   | From the source code (`make setup`) | `data/` inside the repository |

   (`~` is your home folder.) If **Stored data** shows a different folder, or this folder does not
   exist, another copy of Concord is running: see the note at the end of section 1.
2. **Open it:**
   - **Mac:** in Finder choose **Go → Go to Folder…**, paste the path, press Return.
   - **Linux:** in your file manager press Ctrl+L, paste the path, press Enter. The path
     contains `.local`; a name starting with a dot is hidden, but typing the path opens it anyway.

   On a new installation the `datasets` folder does not exist yet, so this fails. Then paste the
   path without its last part, `/datasets` (that is the data folder; it contains only `logs` and
   `concord.pid`, leave those alone), and create a folder named `datasets` in it.
3. **Move both `.nwb` files into `datasets`.**

> **With a terminal instead:** one command downloads, verifies and places both files
> (see [Commands in this guide](#commands-in-this-guide)):
> - Mac: `/Applications/Concord.app/Contents/MacOS/Concord dataset`
> - Linux: `cd ~/Downloads`, then `./Concord/Concord dataset`
>
> It puts them in `datasets/dandi-000954/`; any subfolder of `datasets` works.

### 4.3 Connect a recording

1. Reload the console page (⌘R or Ctrl+R), then click **Connect a source**. (Reloading clears
   the on-screen Session log; what happened is still in Concord's log files and, during a
   research session, in the session's log.)
2. Under **Recorded human data (offline replay)** you now see **Session 19250108T110520** and
   **Session 19250108T111022**, each with "DANDI 000954 · held-in-calib · 176 channels · 20 ms
   bins". They are two blocks from the same day; either works. The numbers are the recording's
   date and time, which the dataset shifted to 1925 to protect the participant's identity, and
   *held-in-calib* is the name the FALCON benchmark gives this part of its data.
3. Click **Connect** next to one of them.

**What you should see:**
- The title bar says **Streaming · Recorded human data, offline replay**.
- The source row shows the source type *Recorded Human Intracranial Data — Offline Replay* and,
  on the next line, which session is playing.
- **Signal integrity** shows the spike counts of the most active channels.

![A recorded human session replaying](images/09-recorded-human-data.png)

*(In this image the live traces are blanked: the dataset's terms do not allow its data to be
redistributed, so the documentation shows none of it. On your screen you see the traces.)*

### 4.4 Control the replay

Open **Playback** in the source row:
- **Pause** / **Resume**;
- speed **0.5×, 1×, 2×, 4×, 8×**.

The position (for example *0:43.0 of 2:15.7*) is shown in the line above. The bar shows
progress but cannot be dragged. At the end, the replay starts again from the beginning.

### 4.5 See exactly what you are replaying

Open **Advanced → Acquisition details**:

![Dataset details with checksum verification](images/10-dataset-details.png)

- **Dataset** (with a link), **File**, and a green **SHA-256 matches DANDI 000954 asset …**: the
  file is exactly the published one.
- **Recording**, **Signal**, **Behavior** and **Session**: what was recorded and how.
- **Decoder**: *None attached (no held-out evaluation for this file)*: no decoder has been
  tested on this file ("held-out" means tested on data it was not trained on). Concord does not
  ship a decoder for it; developers who build Concord from its source code can train one
  ([DECODING.md](DECODING.md)).
- **Citation**: how to cite the dataset if you use it.
- **Metadata notes**: corrections Concord applied and what the file does not provide.
- Below these, **Recorded neural activity** plots the replayed spike counts of all 176 channels
  and the participant's cued movement. Choose the movement dimension in **Velocity dimension**:
  *tx, ty, tz* are translation, *rx* rotation, *g1–g3* grasp.

When you are done, click **Disconnect**.

---

## 5. Let a recorded decoder drive the board (T15 cursor + click)

This is the full chain a real system would use: brain activity → decoder → command output →
communication board. The **T15** recordings come from a participant with electrodes in speech
motor cortex (256 electrodes) who controlled a computer cursor and clicked with them. The files
also contain the outputs of the original research system's decoder, so you can replay exactly
what that decoder did. (Singer-Clark et al. 2025,
[dataset on Dryad](https://datadryad.org/dataset/doi:10.5061/dryad.prr4xgxzq), license CC0.)

### 5.1 Download the four files

On the Dryad page, sign in (a free account) and download these four files one at a time from
the file list (click a file's name to download it). The list is long: use your browser's Find
(Ctrl+F or ⌘F) for `day00468_block0`. Don't use the button that downloads the whole dataset;
it is much larger.

| File | Size | What it is |
| --- | --- | --- |
| `t15_day00468_block00_radial8_calibration_task.mat` | 28.4 MB | calibration block 0: cursor to 8 targets around a circle |
| `t15_day00468_block01_radial8_calibration_task.mat` | 11.0 MB | calibration block 1 |
| `t15_day00468_block02_radial8_calibration_task.mat` | 28.5 MB | calibration block 2 |
| `t15_day00468_block03_grid_evaluation_task.mat` | 28.5 MB | **the grid block**: choosing targets on a 14 × 14 grid, fully under neural control. This is the one you will replay. |

Move them into the same `datasets` folder as in section 4.2. Delete any `… (1).mat` duplicate
your browser makes. Concord skips duplicates, because the same block cannot be listed twice.

### 5.2 Connect the grid block

1. Reload the console, click **Connect a source** (or **Change source** if something is
   connected).
2. Under **Recorded human data (offline replay)** the four blocks are listed by day, block and
   task:
   - **Cursor + click · Day 468 · block 0 · radial-8 calibration** (and blocks 1 and 2);
   - **Cursor + click · Day 468 · block 3 · grid evaluation**.

   Each has "Dryad T15 · 256 channels · 10 ms bins".

   ![The T15 blocks in the source list](images/13-t15-sources.png)
3. Click **Connect** (or **Switch**) next to **block 3 · grid evaluation**.


**What you should see:**
- The title bar says **Streaming · Recorded human data, offline replay**.
- The Decoder row says the recording carries the replayed output of a decoder and that *it is
  not used for control*. That is the starting state: in 5.4 you choose to pass this recorded
  output on, and only **Start control** in 5.5 lets it move the board. (The row names only
  *t15-historical-click*; the velocity decoder appears in 5.4.)
- **Signal integrity** shows the threshold crossings of the most active channels.

The file's checksum is verified when you connect; a file that does not match is refused. The
citation is in [DATASETS.md](DATASETS.md).

T15 replays at real speed: block 3 lasts 3 minutes and then starts again. You can **Pause**
under **Options**. (Unlike FALCON, the T15 row shows no position, progress bar or speed
choice.)

### 5.3 Set the board to the task's grid

The participant chose among targets on a 14 × 14 grid, so the board should show the same grid.

1. Click **Open participant screen** (if the board is not open already).
2. On the board, click **Settings** (top right). The **Board settings** panel opens:

   ![Board settings](images/14-board-settings.png)

3. Under **Layout**, choose **Task grid (N × N words)**. **Grid size N** shows **14** (set it to
   14 if not). Then maximise the board window: the 196 tiles are small, and words are cut off
   in a smaller window.
4. Leave **Input method** on **Automatic**. For now it reads *Automatic (nothing available now)*
   and the other methods say *not offered by the current source*. That is expected: no command
   output reaches the board yet. After 5.5 it reads *Automatic (now: Pointer and click)*, as in
   the picture. Click **Close**.

**What you should see:** the board shows 196 word tiles. It says *Paused — no command output
for this application*, because no decoded data may reach it yet. Settings are saved in this
browser, so the board keeps them next time.

### 5.4 Turn on the recorded decoder

1. In the **Decoder** row, click **Start decoding**.
2. Under **Processing**, choose **Source decoder outputs (passthrough)**. This option exists only
   for sources that carry a decoder's output. It forwards that output unchanged, labelled
   *historical*. No model of yours is involved.
3. Click the **Start decoding** button under *Processing* in this panel (not the one in the
   Decoder row).

**What you should see:** the Decoder row says *Running* and lists two decoders:
- **t15-historical-velocity**, with outputs **vx, vy**: the cursor velocity;
- **t15-historical-click**, with output **click**: the click decision.

A note says the velocity has "no declared output scale"; the next step sets the scale.

### 5.5 Set up command output

1. In **Command output**, open **Settings**:

   ![Command output settings for the T15 replay](images/15-command-output-settings.png)

2. **Change three fields** (they start at 1, 0.3 and 2; the picture shows them already
   changed):
   - **Gain**: `1.09`. The recorded velocity is in screen heights per second, and the task's
     targets filled a square 0.92 screen heights wide. Multiplying by 1 / 0.92 = 1.09 makes the
     board's square match that grid.
   - **Dead-zone**: `0` (don't ignore small movements).
   - **Max speed**: `10` (don't cap the recorded movements).

   **Leave the others as they are**: **Horizontal (x) from** `vx`, **Vertical (y) from** `vy`,
   **Invert y** ticked (ticked for you, because the decoder counts "up" as positive y while the
   screen counts "down"), **Click from** `click` (selected for you), **Click threshold** `0.5`,
   **Minimum confidence** `0`, **Click pause (ms)** `300`.
3. Click **Start control**.
4. Under **Authorized applications**, click **Authorize** next to **Communication Board**.

If you change a value later, click **Apply settings** under the fields.

**What you should see:**
- **Command output** says *On · x ← vx, y ← vy (inverted), gain 1.09; click ← click*.
- The title bar's **Stop control** button turns red.
- On the board:
  - the input line reads *historical decoder replay (original research system) · recorded data
    replay*;
  - the cursor moves, and each click selects the word under the cursor;
  - the message is labelled *demonstration — not the participant's message*.

![The board driven by the replayed decoder](images/16-board-t15.png)

**What to expect:** the cursor moves the way the original decoder moved it during the
recording. The replay is [open loop](GLOSSARY.md#closed-loop-open-loop): the recording cannot react to the
board, so the cursor can drift where the original screen differed. Still, the board's
selections land on the cued word roughly half of the time: 39 of 70 clicks in the published
comparison. The board does not show which word was cued, so you cannot check this on screen;
the comparison is described in [NEURAL_COMMUNICATION.md](NEURAL_COMMUNICATION.md).

### 5.6 Stop and tidy up

1. Click **Stop control** (top right). Decoded commands stop at once; the board says it is
   paused.
2. Under **Authorized applications**, click **Revoke**. Authorization lasts until you revoke it,
   even if you change source or session.
3. Click **Stop decoding** in the **Decoder** row, then **Disconnect** in **Acquisition
   source**. The board says *Paused — device disconnected (operator disconnect)*.
4. On the board, open **Settings → Layout → Phrases and letters** to get the normal board back
   (the setting is saved in this browser). Then close the board window: that removes the
   message. (You cannot select **Clear** now: nothing moves the cursor after **Disconnect**,
   and the board ignores mouse clicks.)

Want Concord's *own* decoders on this recording? A [Kalman](GLOSSARY.md#kalman-filter) cursor
decoder and a click decoder fitted on blocks 0–2 are evaluated in
[CURSOR_CLICK.md](CURSOR_CLICK.md). Fitting them needs Concord installed from its source code,
which is meant for developers ([DEVELOPERS.md](DEVELOPERS.md)).

---

## 6. Human ECoG (AJILE12, optional)

AJILE12 contains ECoG recorded from the cortical surface (a 64-electrode grid at 500 Hz) during
everyday arm movements (DANDI 000055, license CC-BY-4.0). The files are very large, so Concord
cuts and verifies two short slices itself. That needs one command in a terminal. Concord may be
running while you run it.

- **Mac** (open the **Terminal** app):

  ```bash
  /Applications/Concord.app/Contents/MacOS/Concord dataset ajile12
  ```

- **Linux** (open a terminal):

  ```bash
  cd ~/Downloads
  ./Concord/Concord dataset ajile12
  ```

(Python installation: `concord dataset ajile12`; see [Commands in this guide](#commands-in-this-guide).)

**What you should see:**
- The command takes about a minute and downloads about 157 MB.
- It prints *verified* twice and ends with *2 extract(s) ready in …/datasets/dandi-000055*.

Then:
1. Reload the console and click **Connect a source**.
2. **Recorded human data** now also lists **Session 5** and **Session 6** ("DANDI 000055 ·
   64 channels · 500 Hz"). Connect one: the source row says *Recorded Human ECoG — Offline
   Replay* and the title bar *Streaming · Recorded human data, offline replay*.
3. When you are done, click **Disconnect**.

Background and decoding results: [ECOG.md](ECOG.md).

---

## 7. A research session: record and export

A **research session** keeps a reproducible record of what you do: recordings, decoders,
settings and a log, in one folder you can export as a zip file.

1. In the session strip, click **New session**. Enter a **Session name** (required; **Start
   session** stays grey until you do), optionally the **Operator** and **Notes**. **Never enter
   participant identifiers.** Click **Start session**.

   ![Starting a research session](images/06-new-session.png)

   The strip now shows the session's name, the operator, the start time and how many recordings
   and models it holds.
2. Connect **Simulated Profile A** (**Connect a source**, or **Change source → Switch** if
   something is connected). Source changes are written to the session's log.
3. Record: open **Advanced → Recording** and click **Start recording**. The title bar adds
   **· Recording**.
   - Leave **Features and labels only** unticked for this exercise. A recording with raw samples
     stops by itself after 5 minutes or 200 MB. Simulated Profile A writes about 12 MB a minute,
     so a one-minute recording is fine. (The panel's warning that raw frames "reach the size cap
     in seconds" applies to high-channel-count live sources.)
   - With **Features and labels only (for calibration)** ticked, the raw samples are left out
     and a recording can run for an hour.
   - The size shown in the list of recordings updates when the recording stops.
   - Both limits can be changed in the [configuration file](USER_GUIDE.md#15-configuration-file).
   - Recorded datasets (sections 4–6) cannot be recorded: they already are recordings.

   ![A session with a recording in progress](images/07-session-recording.png)

4. After a minute, click **Safe stop & disconnect**. It stops command output, closes the
   recording, stops decoding and disconnects the source, in that order. The session stays open.
5. Click **Session and export…** in the session strip:
   1. For this exercise, tick **Include the session's recordings** (the data needed to re-run an
      evaluation). Leave **Include the operator name and notes** unticked unless the people you
      share the zip with should see them.
   2. Click **Create export bundle**.
   3. **Download the zip from the link that appears now** (the same file is also listed just
      below it), before you end the session. Your browser saves it in your Downloads folder.

   ![Session details and export](images/08-session-export.png)

   The zip contains:
   - `session.json` and `session-log.jsonl`: what happened;
   - `environment.json`: software versions;
   - `devices/`: the sources;
   - `recordings/` (if included);
   - decoder models and their calibration reports (if you calibrated);
   - `manifest.json` (checksums) and `REPRODUCE.md`.
6. At the bottom of the same panel, click **End session…** and then **End session now**.

   **What you should see:** the session strip returns to *No research session…*. The session's
   folder stays in **Advanced → Stored data**.

**Reproducing an export (optional, needs a terminal).** Give the `reproduce` command the zip's
full path. Its name is long: type the start, `~/Downloads/concord-session-`, then press **Tab**
to complete it (or drag the zip from your file manager into the terminal).

- **Mac:** `/Applications/Concord.app/Contents/MacOS/Concord reproduce ~/Downloads/concord-session-….zip`
- **Linux:** `cd ~/Downloads`, then `./Concord/Concord reproduce ~/Downloads/concord-session-….zip`

(Python installation: `concord reproduce …`.)

It checks every file against `manifest.json` and re-runs the session's decoder evaluation. For
this session, which has no decoder, it prints `[OK  ] integrity: 6 files verified against
manifest.json` and `result: nothing_to_reproduce`. That is the expected result.

---

## 8. Stored data, support report and quitting

**Advanced → Stored data** shows the data folder, your recordings, decoder models and research
sessions with their sizes, and deletes what you no longer need (it asks for confirmation).
Downloaded datasets are not listed there: delete them from the `datasets` folder yourself.

**Advanced → Support report → Create support report** checks the installation: versions,
optional parts, ports, folder permissions, disk space and recent problems. It contains **no
neural or personal data**. If you tried the faults in section 3.4, the report lists them under *Recent log problems* as
warnings and errors; that is expected. Download it as JSON or Markdown and attach it when you
[report a problem](https://github.com/arnavhiteshpatel-cloud/concord/issues/new/choose).

![Stored data and support report](images/12-stored-data-and-support.png)

**Quitting:**
- **Mac:** click **Stop and quit** in the small Concord window, or press ⌘Q.
- **Linux:** click **Stop and quit**; or, if you started Concord in a terminal, press Ctrl-C there
  (or run `./Concord/Concord stop` from `~/Downloads` in another terminal).

Quitting performs a safe stop first, so recordings are closed properly. Afterwards the console
says *Connection to Concord lost, reconnecting* and the board says *Reconnecting*: Concord has
stopped, so close both tabs. If Concord ever stops unexpectedly,
the next start keeps the complete part of an interrupted recording and marks it *incomplete*.

---

## 9. Where to go next

| You want to… | Read |
| --- | --- |
| Understand the ideas: sources, data kinds, capabilities, decoders, command output | [How Concord works](CONCEPTS.md) |
| Know what every button, field and message does | [User guide](USER_GUIDE.md) |
| Connect your own equipment: LSL, Open Ephys, BrainFlow, BCI2000, your own device | [Connect your equipment](CONNECT_YOUR_EQUIPMENT.md) |
| Calibrate a decoder from your own recordings | [User guide: Calibrate](USER_GUIDE.md#65-the-calibrate-panel) |
| See every demo dataset, its license and how to cite it | [DATASETS.md](DATASETS.md) |
| Fix a problem | [TROUBLESHOOTING.md](TROUBLESHOOTING.md), [FAQ.md](FAQ.md) |
| Know what has been validated, and what has not | [VALIDATION_LEVELS.md](VALIDATION_LEVELS.md), [LIMITATIONS.md](../LIMITATIONS.md) |
| Look up a term | [Glossary](GLOSSARY.md) |
