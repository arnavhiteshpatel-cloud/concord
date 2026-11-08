# Installing Concord on a Mac

For a researcher who wants to run Concord on a Mac, with or without Python experience.
Concord is research software: **not a medical device**, read-only towards devices, and
validated only in software and with protocol-level test sources — never with acquisition
hardware or a participant (docs/VALIDATION_LEVELS.md).

Two ways to install; both give the same Concord:

| | Desktop app (`.dmg`) | Python package (`pip`) |
| --- | --- | --- |
| For | Using Concord | Using Concord, and adding plugins or writing apps |
| Needs | macOS 14 (Sonoma) or later, **Apple Silicon** (M1 or later) | Python 3.12 (any macOS Python 3.12 supports) |
| Includes | Concord, the console, simulated sources, recordings, NWB datasets, LSL, Open Ephys, the BCI2000 plugin | the same, plus any plugin you `pip install` (e.g. BrainFlow) |

## A. The desktop app

### Get it

Download **[Concord-macos-arm64.dmg](https://github.com/arnavhiteshpatel-cloud/brainos/releases/latest/download/Concord-macos-arm64.dmg)**
from the [Releases page](https://github.com/arnavhiteshpatel-cloud/brainos/releases/latest). It
is built and smoke-tested by this repository's release workflow (`.github/workflows/release.yml`);
`SHA256SUMS.txt` on the release page lists its checksum. You can also build it yourself on a Mac
from a checkout with `make setup && make app` (output:
`packaging/dist/Concord-<version>-macos-arm64.dmg`). The app requires macOS 14 because the
numerical libraries it bundles (numpy, scipy for Apple Silicon) do; on older macOS use the pip
installation, which picks libraries for your system. The app is unsigned, so macOS cannot tell
you who made it: use only a release from this repository or a build you made yourself.

### Install

1. Open the `.dmg`.
2. Drag **Concord** onto **Applications**.
3. Eject the disk image.

### First launch (Gatekeeper)

Concord.app is **not signed with an Apple Developer ID and not notarized** (it carries only
an ad-hoc signature). macOS therefore refuses to open it the first time:

- **macOS 15 (Sequoia) and later**: double-click Concord; when macOS says it cannot verify
  the app, click **Done**. Open **System Settings → Privacy & Security**, scroll to
  *Security*, click **Open Anyway** next to "Concord was blocked…", and confirm with your
  password. Then double-click Concord again and click **Open**.
- **macOS 14 (Sonoma)**: in Applications, **Control-click** (or right-click) Concord →
  **Open** → **Open**.

You do this once per installed copy. (Command-line alternative, only for a build you trust:
`xattr -dr com.apple.quarantine /Applications/Concord.app`.)

### Use

When Concord starts:

- a small **Concord** window shows "Concord is running at http://127.0.0.1:8000";
- the console opens in your default browser (if it does not, click **Open console**).

To **quit**: Concord → Quit (⌘Q), Dock → Quit, close the Concord window, or **Stop and
quit**. Quitting first performs a *safe stop*: command output off, any recording closed,
decoding stopped, the source disconnected. Opening Concord again while it runs just opens the
console.

Your data stays on this Mac, private to your user account (folders 0700, files 0600):

| | Location |
| --- | --- |
| Data (recordings, models, sessions, exports, logs) | `~/Library/Application Support/Concord/data` |
| Optional config file | `~/Library/Application Support/Concord/config.toml` |

The app's executable also answers the `concord` commands, for example:

```bash
/Applications/Concord.app/Contents/MacOS/Concord doctor
```
```bash
/Applications/Concord.app/Contents/MacOS/Concord config init
```
```bash
/Applications/Concord.app/Contents/MacOS/Concord dataset
```

`doctor` writes a support report (no neural or personal data) to `<data>/support/`;
`config init` writes a commented config file you can edit (port, data folder, retention);
`dataset` downloads the two public demo recordings (DANDI 000954, 8.7 MiB, verified by
SHA-256) so *Recorded human data* appears in the console.

### Uninstall

Quit Concord and move it from Applications to the Bin. Your data is not removed: delete
`~/Library/Application Support/Concord` yourself if you no longer need it (it may contain
neural recordings; see docs/SECURITY.md on deletion).

## B. With Python (`pip`)

Packages are not on PyPI yet. Either download the wheels from the
[Releases page](https://github.com/arnavhiteshpatel-cloud/brainos/releases/latest) into one folder
and run `pip install --find-links <that folder> "concordos[lab]"` in a Python 3.12 environment, or
install from a checkout of this repository. For a checkout, the prerequisites are:
[Homebrew](https://brew.sh), then

```bash
brew install uv node
```

```bash
git clone https://github.com/arnavhiteshpatel-cloud/brainos.git
```

```bash
cd concord
```

```bash
make setup
```

```bash
make build
```

```bash
.venv/bin/concord start
```

`concord start` starts Concord in the background on http://127.0.0.1:8000, waits until it
answers, prints the URL and opens the console. Then:

```bash
.venv/bin/concord status
```

```bash
.venv/bin/concord stop
```

(`stop` performs the same safe stop as quitting the app.) To install into another Python
environment instead, build the wheels (with the console staged into them):

```bash
.venv/bin/python packaging/stage_console.py
```

```bash
uv build --wheel -o dist packages/concord-adapter-sdk
```

```bash
uv build --wheel -o dist backend
```

```bash
pip install --find-links dist "concordos[lab]"
```

`concordos[lab]` is the server with signal processing, NWB datasets, LSL and Open Ephys support.
Plugins go into the same environment (`pip install concord-brainflow …`).

## Configuration

Every setting has a safe default; the config file is optional:

```bash
concord config init
```

```bash
concord config show
```

`init` writes a commented file (mode 600) listing every key: `[server]` host/port (host stays
127.0.0.1: Concord has no authentication), `[storage]` data folder, `[retention]` days to keep
recordings, sessions, exports and models (0 = keep forever; applied at startup), `[recording]`
limits of one recording (default 300 s / 200 MiB with raw frames; up to 24 h / 100 GiB).
Environment variables (`CONCORD_PORT`, `CONCORD_DATA_DIR`, …) override the file.

## Troubleshooting

See [TROUBLESHOOTING.md](TROUBLESHOOTING.md). The first step is always:

```bash
concord doctor
```

## What has been tested

The app bundle is built and smoke-tested automatically on GitHub Actions `macos-latest`
(Apple Silicon) by the **package-macos** job. In the run for commit 3cd64fb (PR #9) every check
passed: the bundled executable's version; the isolated decoder host started from the bundle;
`Concord doctor` (14 ok, 0 fail); a headless launch with Simulated Profile A streaming, the
BCI2000 plugin discovered by the plugin host inside the app, a recording closed cleanly on quit
(SIGTERM) with private file permissions; crash recovery after a SIGKILL mid-recording; the Tk
status window quitting cleanly on SIGTERM; launching with `open` (the double-click
equivalent) and quitting with an Apple Event; and the app run from the mounted, verified
`.dmg`. (The first macOS run found that SIGTERM did not reach the window's event loop; fixed
in 336ecc4.) The build fails if any bundled library needs a newer macOS than the app declares
(14.0); orjson, whose macOS wheels need macOS 15, is therefore left out of the app (Concord
uses its byte-identical pure-Python encoder instead). The identical bundle layout is built and
tested on Linux by **package-linux**.

Not tested: installing the `.dmg` by hand on a physical Mac (Gatekeeper prompts, a real
display, a real browser) and using it with acquisition equipment; see LIMITATIONS.md.
