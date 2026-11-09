# Frequently asked questions

**About Concord**

- [What is Concord?](#what-is-concord)
- [Is Concord a medical device? Has anyone used it?](#is-concord-a-medical-device-has-anyone-used-it)
- [Does it work with my implant or my company's device?](#does-it-work-with-my-implant-or-my-companys-device)
- [Does Concord send anything to my amplifier or device?](#does-concord-send-anything-to-my-amplifier-or-device)
- [What do "validation levels" and "protocol-tested" mean?](#what-do-validation-levels-and-protocol-tested-mean)

**Installing and running**

- [Do I need to use the terminal?](#do-i-need-to-use-the-terminal)
- [macOS says the app cannot be opened or verified. Is it safe?](#macos-says-the-app-cannot-be-opened-or-verified-is-it-safe)
- [Does Concord run on Windows or on an Intel Mac?](#does-concord-run-on-windows-or-on-an-intel-mac)
- [Can I use the console from another computer?](#can-i-use-the-console-from-another-computer)
- [How do I uninstall it?](#how-do-i-uninstall-it)

**Data**

- [Where is my data stored, and is any of it sent anywhere?](#where-is-my-data-stored-and-is-any-of-it-sent-anywhere)
- [How do I get the test datasets?](#how-do-i-get-the-test-datasets)
- [How do I know a dataset file is genuine?](#how-do-i-know-a-dataset-file-is-genuine)
- [What does "Offline Replay" mean?](#what-does-offline-replay-mean)
- [Why did my recording stop by itself?](#why-did-my-recording-stop-by-itself)

**Decoding and control**

- [Why can I not start control, or why does the board not react?](#why-can-i-not-start-control-or-why-does-the-board-not-react)
- [Can I use my own decoder?](#can-i-use-my-own-decoder)
- [How good are the decoders?](#how-good-are-the-decoders)

**Getting help**

- [How do I report a problem?](#how-do-i-report-a-problem)
- [How do I cite Concord?](#how-do-i-cite-concord)

---

## About Concord

### What is Concord?

Software that sits between neural acquisition (an amplifier's software, a recording file, a
simulator) and the applications that use the data. It receives the data, labels every event
with where it came from ("provenance"), checks that data arrives complete and on time, runs
signal processing and decoders, and forwards decoded commands only to applications an operator
has authorized. Applications are written once, against a standard set of capabilities, and do
not need to change when the source changes. See [PRODUCT.md](../PRODUCT.md).

### Is Concord a medical device? Has anyone used it?

No, and no. Concord is research software. It has been tested in software and with
protocol-level test sources (software that speaks the same protocols as real acquisition
systems). It has **never been used with acquisition hardware or with a participant**, and
nobody has controlled anything or communicated through it. Decoding results in this repository
are offline analyses of public recordings. See [VALIDATION_LEVELS.md](VALIDATION_LEVELS.md).

### Does it work with my implant or my company's device?

No implant manufacturer's device is supported, and none should be assumed to work. Concord
connects to acquisition *software*: anything that publishes a Lab Streaming Layer stream, the
Open Ephys GUI, boards supported by BrainFlow, and BCI2000. Other systems can be connected with
a source plugin ([ADAPTER_SDK.md](ADAPTER_SDK.md)). Before relying on any connection, verify it
with the [hardware validation protocol](HARDWARE_VALIDATION.md).

### Does Concord send anything to my amplifier or device?

No. Concord only receives. It has no way to send commands, configuration or stimulation to a
device; this is by design and enforced in the code. The single exception is a small "heartbeat"
message to the Open Ephys GUI's ZMQ Interface plugin so the plugin knows a client is listening
([OPEN_EPHYS.md](OPEN_EPHYS.md)).

### What do "validation levels" and "protocol-tested" mean?

Four levels of evidence, from weakest to strongest:

1. **Software-implemented**: the code exists and passes tests on inputs we constructed.
2. **Protocol-tested**: exercised over the real protocol stack (real LSL libraries, real ZMQ
   sockets), against official reference software where it exists, e.g. the real LabRecorder
   and the real Open Ephys GUI.
3. **Hardware-verified**: run with real acquisition hardware and checked against an independent
   reference recording. **Nothing has reached this level yet.**
4. **Human-participant validated**: closed-loop use with a participant under an approved
   research protocol. **Nothing has reached this level.**

Every component's level and evidence: [VALIDATION_LEVELS.md](VALIDATION_LEVELS.md).

## Installing and running

### Do I need to use the terminal?

Not to install, use the console, replay the FALCON and T15 recordings, run research sessions or
export them: see [GETTING_STARTED.md](GETTING_STARTED.md). A terminal is needed for: the ECoG
demo download, the `concord` command (status, configuration file, reproduction of an export),
connecting test publishers, and anything from a source installation (training the demo
decoders, tests, benchmarks).

### macOS says the app cannot be opened or verified. Is it safe?

The app is not signed with an Apple developer certificate or notarized by Apple, so macOS cannot
tell who built it. Download it only from this repository's
[Releases page](https://github.com/arnavhiteshpatel-cloud/concord/releases), where it was built
and smoke-tested by the repository's own release workflow; `SHA256SUMS.txt` on that page lists
its checksum. Then allow it once:
**System Settings → Privacy & Security → Open Anyway** (macOS 15+) or Control-click →
**Open** (macOS 14). [INSTALL_MAC.md](INSTALL_MAC.md) has the details.

### Does Concord run on Windows or on an Intel Mac?

Not as a desktop app. The Mac app needs Apple Silicon and macOS 14 or later. On an Intel Mac or
older macOS, install with Python ([INSTALL_MAC.md](INSTALL_MAC.md#b-with-python-pip)). Windows is
not supported.

### Can I use the console from another computer?

Concord listens only on the computer it runs on (127.0.0.1) because it has no user accounts or
encryption. To see the console from another computer, use an SSH tunnel
(`ssh -L 8000:127.0.0.1:8000 user@concord-computer`) rather than opening it to the network.
[SECURITY.md](SECURITY.md) explains why.

### How do I uninstall it?

Quit Concord and move it from Applications to the Bin (on Linux, delete the extracted folder).
Your data is kept: delete the data folder yourself if you no longer need it (it may contain
neural recordings; see [SECURITY.md](SECURITY.md) on deletion).

## Data

### Where is my data stored, and is any of it sent anywhere?

On your computer only, in a folder readable only by your user account:

| Installation | Data folder |
| --- | --- |
| Mac app or Python install on a Mac | `~/Library/Application Support/Concord/data` |
| Linux bundle or Python install on Linux | `~/.local/share/concord/data` |
| Source checkout | `data/` in the repository |

**Advanced → Stored data** in the console shows the exact folder. Concord sends nothing to the
internet on its own. It contacts other computers only when you ask: downloading a public
dataset, discovering LSL streams on your local network, or connecting to an Open Ephys GUI.
Recordings are not encrypted; put the data folder on an encrypted disk if your protocol
requires it.

### How do I get the test datasets?

See the [dataset table in the README](../README.md#test-datasets) and
[GETTING_STARTED.md §4](GETTING_STARTED.md#4-replay-a-real-human-recording-falcon-h1). The
FALCON and T15 recordings can be downloaded in a browser and dropped into the data folder's
`datasets` subfolder; the ECoG slices need one command. The files are never redistributed in this
repository: the archives' terms apply.

### How do I know a dataset file is genuine?

Concord computes the SHA-256 checksum of every dataset file and compares it with the checksum
pinned from the archive. **Advanced → Acquisition details** shows "SHA-256 matches DANDI …" only
on an exact match; any other file is still playable but labelled **unverified**.

### What does "Offline Replay" mean?

The data comes from a file, played back at its original timing (or faster), not from a live
recording. Replays are labelled as such everywhere, and recorded neural activity is never
presented to applications as a person's live intention.

### Why did my recording stop by itself?

A recording stops cleanly when it reaches a limit: by default 5 minutes or 200 MiB with the raw
signal (1 hour with *Features and labels only*), or when less than 256 MiB of disk space is left.
The file is complete. Raise the limits in the `[recording]` section of the configuration file
(up to 24 hours / 100 GiB), see [USER_GUIDE.md](USER_GUIDE.md#configuration-file).

## Decoding and control

### Why can I not start control, or why does the board not react?

Decoded commands reach an application only when **all** of these hold: a decoder is running
(**Decoder → Start decoding** with a model), command output is on (**Command output → Start
control**), and you have **authorized** that application under *Authorized applications*.
**Stop control** in the title bar turns command output off at once. Simulated profiles drive the
board directly (as simulated input) so you can try the board without a decoder.
[CONTROL_BRIDGE.md](CONTROL_BRIDGE.md) explains every rule.

### Can I use my own decoder?

Yes: as a model file (ONNX, scikit-learn via skops, TorchScript / safetensors) or as a decoder
plugin, run in a separate process and checked against the source before it starts
([DECODER_SDK.md](DECODER_SDK.md)). Concord can also calibrate its own decoders from your
recordings (**Decoder → Calibrate…**).

### How good are the decoders?

Only offline, open-loop results exist, on public recordings, each with controls:
[DECODING.md](DECODING.md) (intracortical reach), [ECOG_DECODING.md](ECOG_DECODING.md) (ECoG
movement vs rest), [CURSOR_CLICK.md](CURSOR_CLICK.md) (cursor and click). How well a person could
control anything with them can only be measured closed loop, under an approved research
protocol; that has not been done.

## Getting help

### How do I report a problem?

Create a support report (**Advanced → Support report → Create support report**; it contains no
neural or personal data) and attach it to a
[bug report](https://github.com/arnavhiteshpatel-cloud/concord/issues/new/choose). Security
problems: see [SECURITY.md](../SECURITY.md) and do not open a public issue.

### How do I cite Concord?

Use **Cite this repository** on the GitHub page (from [CITATION.cff](../CITATION.cff)), and cite
each dataset you use; the console shows each dataset's citation under **Advanced → Acquisition
details**.
