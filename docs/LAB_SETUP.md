# Setting up Concord in a lab with its own acquisition system

For a lab that already records neural data with its own amplifier and software and wants to
add Concord next to it. Concord **receives** data from your acquisition software; it never
sends anything to the amplifier or the acquisition software (the single, documented
exception is the Open Ephys heartbeat message). Read
[VALIDATION_LEVELS.md](VALIDATION_LEVELS.md) first: no part of Concord has been run against
acquisition hardware yet. Your first session with equipment is a validation session; follow
[FIRST_LAB_SESSION.md](FIRST_LAB_SESSION.md).

This page covers the lab side: which route, network and ports, installation, a research session
and data handling. The console steps for each route, rehearsal without hardware and
troubleshooting are in **[Connect your equipment](CONNECT_YOUR_EQUIPMENT.md)**.

## 1. Which adapter for which acquisition system

| Your acquisition software / system | Concord adapter | Install | What Concord receives |
| --- | --- | --- | --- |
| Any software with an **LSL outlet** (amplifier vendors' LSL apps, OpenBCI GUI, BCI2000 or OpenViBE LSL output, your own task software) | LSL (built in) | included | the stream as published: raw signal or binned features, plus behavior and marker streams you attach |
| **Open Ephys GUI** ≥ 0.6 with the *ZMQ Interface* plugin | Open Ephys (built in) | included | continuous data, TTL events, spikes from the plugin's ZMQ stream |
| A board supported by **BrainFlow** | `concord-brainflow` plugin | Python installation only (not in the desktop app): the `concord_brainflow` wheel from the GitHub release, [Connect your equipment §2.1](CONNECT_YOUR_EQUIPMENT.md#the-python-installation-needed-for-brainflow-optional-otherwise) | BrainFlow's DEFAULT preset data |
| **BCI2000** | `concord-bci2000` plugin (App Connector) | included in the desktop app; Python installation: the `concord_bci2000` wheel from the release | BCI2000's processed control signal and states (not raw signal) |
| Recorded **NWB** files (spike-time units) | NWB (built in) | included | offline replay, labelled *Offline Replay* |
| Anything else | write a source plugin ([ADAPTER_SDK.md](ADAPTER_SDK.md)) or publish it over LSL | | |

None of Concord's packages is on PyPI: `pip install concord-brainflow` (or any other Concord
package) without `--find-links` fails with "No matching distribution found".

No implant vendor is supported and none should be assumed to work.

## 2. Network topology

Recommended: acquisition stays on its own computer, unchanged; Concord runs on a second
computer on the same lab network; the participant display (the communication board or a task)
is a second screen of the Concord computer.

```
 ┌──────────────────────────┐   LSL (multicast discovery + TCP)    ┌──────────────────────────────┐
 │ Acquisition computer     │   Open Ephys ZMQ (TCP 5556/5557)     │ Concord computer             │
 │ amplifier + vendor app / │ ───────────────────────────────────► │ Concord on 127.0.0.1:8000    │
 │ Open Ephys GUI / BCI2000 │   BCI2000 App Connector (UDP 20321)  │ console (browser, same host) │
 └──────────────────────────┘                                      │ participant screen (2nd mon.)│
                                                                   └──────────────────────────────┘
```

| Protocol | Direction | Ports to allow | Notes |
| --- | --- | --- | --- |
| LSL | acquisition → Concord | UDP 16571 (multicast discovery), TCP/UDP 16572–16603 on the acquisition computer | Both computers on the same subnet with multicast allowed; otherwise configure liblsl's `KnownPeers` (lsl_api.cfg). Timestamps are mapped with liblsl `time_correction`. |
| Open Ephys ZMQ Interface | Concord connects to the GUI computer | TCP data port (default 5556) and heartbeat port + 1 (5557) on the GUI computer | Concord subscribes; it sends only the plugin's heartbeat. |
| BCI2000 App Connector | BCI2000 → Concord | inbound UDP 20321 (default) on the Concord computer | Set BCI2000's `ConnectorOutputAddress` to the Concord computer's address and port, and the plugin's *Local address* option to that same address. |
| Concord console and API | local only | none | Concord listens on 127.0.0.1. To use the console from another computer, use an SSH tunnel (`ssh -L 8000:127.0.0.1:8000 user@concord-computer`), not `allow_remote` (docs/SECURITY.md). |

Clocks: keep all computers on NTP. Concord does not estimate offsets between computers beyond
what liblsl provides; Open Ephys timestamps are sample counts in the GUI's clock.

## 3. Install on the Concord computer

Three ways, all for Concord 0.3.1:

- **Desktop app**: `Concord-macos-arm64.dmg` (Mac with Apple Silicon, [INSTALL_MAC.md](INSTALL_MAC.md)),
  `Concord-windows-x86_64.zip` (Windows 10/11, [INSTALL_WINDOWS.md](INSTALL_WINDOWS.md)) or
  `Concord-linux-x86_64.tar.gz` (Linux bundle). It includes LSL, Open Ephys and the BCI2000
  plugin, not BrainFlow. Its program answers the same commands as `concord`:
  `/Applications/Concord.app/Contents/MacOS/Concord <command>`, `.\concord-cli.exe <command>`
  (Windows, in the `Concord` folder) or `./Concord/Concord <command>`.
- **Python installation** (Python 3.12+; needed for BrainFlow and other plugins): download all
  `.whl` files of the [GitHub release](https://github.com/arnavhiteshpatel-cloud/concord/releases/latest)
  into one folder, then

  ```bash
  pip install --find-links <wheels folder> "concordos[lab]" concord-brainflow concord-bci2000
  ```

  (leave out the plugins you do not need; `brainflow` itself comes from PyPI).
- **From a source checkout**: `make setup && make build`, then `.venv/bin/concord …`.

Then check the installation and save the report with your lab records:

```bash
concord doctor
```

It checks Python, the packages (with build fingerprints), liblsl, pyzmq, BrainFlow, a
BCI2000 reachability hint, the port, the data directory's permissions, disk space and recent
log problems. It contains no neural or personal data.

Configure (optional; safe defaults otherwise):

```bash
concord config init
```

Edit the file `concord config path` prints: put `[storage] data_dir` on an encrypted disk,
set `[retention]` per your data policy (applied at every start). Then:

```bash
concord start
```

```bash
concord status
```

## 4. Connect your source

Follow [Connect your equipment §4](CONNECT_YOUR_EQUIPMENT.md#4-connect-your-equipment-route-by-route):
LSL, Open Ephys, BrainFlow, BCI2000 and your own plugin, with the exact console steps. Plugins
must be installed in the same Python environment as Concord; the desktop app includes only the
BCI2000 plugin. Check the *Signal integrity* row and **Advanced → Acquisition details** against
your acquisition software's own display.

Rehearse without hardware first with `concord publish` (desktop app:
`/Applications/Concord.app/Contents/MacOS/Concord publish …`, `.\concord-cli.exe publish …` or
`./Concord/Concord publish …`).
The LSL test streams declare themselves synthetic or prerecorded; the Open Ephys protocol cannot
carry that declaration, so its test stream is shown as *Live stream, origin unverified*
([OPEN_EPHYS.md](OPEN_EPHYS.md#limitations)).

```bash
concord publish lsl-ephys --channels 32 --rate 30000
```

```bash
concord publish falcon "<data folder>/datasets/sub-HumanPitt-held-in-calib_ses-19250108T111022.nwb" --loop
```

`<data folder>` is shown in **Advanced → Stored data** (*Data directory*); files downloaded with
`concord dataset` are in its `datasets/dandi-000954/` subfolder.

```bash
concord publish openephys --port 5560
```

Details, what you should see and how to stop: [Connect your equipment §3](CONNECT_YOUR_EQUIPMENT.md#3-rehearse-without-hardware).

## 5. A research session, step by step

1. **New session** (strip above the rows): a name (no participant identifiers), the operator,
   notes. Concord creates a private session folder and logs into it from now on.
2. **Connect a source**, check signal integrity.
3. **Decoder → Start decoding** (processing preset), **Decoder → Calibrate…**: record features
   and labels, train; the report gives held-out R² and controls (LAB_GUIDE.md §5).
4. **Stop decoding**, then **Start decoding** with the new model; **Command output → Start
   control**; **Authorize** the application(s) that should receive commands.
5. **Stop control** (title bar; grey and disabled while command output is off, red while it is
   on) stops commands at once; **Safe stop & disconnect** stops everything: command output,
   recording, decoding, the source.
6. **Session and export… → Create export bundle** (tick *Include the session's recordings* to
   make it reproducible): a zip with the session log, versions, sources, pipeline settings,
   models, calibration reports and `REPRODUCE.md`. Verify it anywhere with
   `concord reproduce <bundle>.zip`.
7. **End session…**.

## 6. Documented commands and API used by the acceptance test

`scripts/lab_acceptance.py` runs the steps above from built wheels in fresh virtual
environments, using only these commands and the REST endpoints the console calls (all under
`http://127.0.0.1:8000/api/v1`):

| Purpose | Command / endpoint |
| --- | --- |
| install, check, configure, run | `pip install "concordos[lab]"` from the built wheels, `concord version`, `concord doctor`, `concord config init / show`, `concord start --no-browser`, `concord status`, `concord stop`, `concord dataset` |
| external sources | `python -m concord.testing.publish lsl-ephys …` / `… falcon …` (separate processes; the same publishers as `concord publish …`) |
| research session | `POST /sessions`, `POST /sessions/{id}/export`, `POST /safe-stop` |
| source | `POST /sources/lsl/discover`, `POST /sources/lsl`, `POST /runtime/connect`, `POST /runtime/disconnect`, `GET /devices` |
| pipeline, recording, calibration | `POST /pipeline/start`, `POST /pipeline/stop`, `GET /pipeline`, `POST /recordings/start`, `POST /recordings/stop`, `POST /calibration/train` |
| applications | an SDK-only app (`concord.sdk.EventStream`, `pip install concordos`), `GET /control`, `POST /control/apps/{id}/authorize` |
| reproduction | `concord reproduce <bundle>.zip` in a fresh environment (`pip install "concordos[dsp]"`) |

Run it yourself with `make lab-acceptance` (CI job **lab-acceptance**).

## 7. Data handling

Everything is written under the data directory (0700; files 0600): `recordings/`, `models/`,
`sessions/<id>/` (session.json, log.jsonl, exports/), `logs/`, `support/`. Recordings can
contain neural data. Delete with **Advanced → Stored data** (or `DELETE /api/v1/recordings/{name}?confirm={name}`);
deletion is not secure erasure. A recording interrupted by a crash is kept, marked
*incomplete*. Details: [SECURITY.md](SECURITY.md).
