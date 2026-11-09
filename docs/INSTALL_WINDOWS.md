# Installing Concord on Windows

For a researcher who wants to run Concord on a Windows PC, with or without Python experience.
Concord is research software: **not a medical device**, read-only towards devices, and
validated only in software and with protocol-level test sources — never with acquisition
hardware or a participant ([VALIDATION_LEVELS.md](VALIDATION_LEVELS.md)).

Windows support is new in 0.3.1. It is built and smoke-tested on GitHub's Windows runners for
every change, but **it has not yet been tried on a physical Windows PC** (see
[What has been tested](#what-has-been-tested)). Please [report](https://github.com/arnavhiteshpatel-cloud/concord/issues/new/choose)
anything that does not work as described here.

Two ways to install; both give the same Concord:

| | Desktop app (`.zip`) | Python package (`pip`) |
| --- | --- | --- |
| For | Using Concord | Using Concord, and adding plugins or writing apps |
| Needs | Windows 10 or 11, 64-bit (x86_64) | Python 3.12 for Windows (64-bit) |
| Includes | Concord, the console, simulated sources, recordings, NWB datasets, LSL, Open Ephys, the BCI2000 plugin | the same, plus any plugin you `pip install` (e.g. BrainFlow) |

Windows on ARM is not built or tested.

## A. The desktop app

### Get it

Download **[Concord-windows-x86_64.zip](https://github.com/arnavhiteshpatel-cloud/concord/releases/latest/download/Concord-windows-x86_64.zip)**
from the [Releases page](https://github.com/arnavhiteshpatel-cloud/concord/releases/latest). It
is built and smoke-tested by this repository's release workflow (`.github/workflows/release.yml`);
`SHA256SUMS.txt` on the release page lists its checksum. To check it in PowerShell:

```powershell
Get-FileHash $HOME\Downloads\Concord-windows-x86_64.zip -Algorithm SHA256
```

`Get-FileHash` prints the hash in capitals and `SHA256SUMS.txt` lists it in lower case: compare
the letters, not their case.

The app is unsigned (no Authenticode certificate), so Windows cannot tell you who made it: use
only a release from this repository or a build you made yourself.

**Building it yourself** needs a Windows PC with a checkout of this repository (`git clone`, as
in *From a checkout* below), Python 3.12 (64-bit) and Node 20+. In PowerShell, in the checkout,
with a Python 3.12 environment active, install Concord and the pinned build tools, then build
(`--build-console` also builds the console with npm):

```powershell
python -m pip install -e packages/concord-adapter-sdk -e packages/concord-decoder-sdk -e "backend[lab]" -e packages/concord-bci2000
```

```powershell
python -m pip install -r packaging/requirements.txt
```

```powershell
python packaging/build_app.py --build-console --zip
```

The output is `packaging\dist\Concord-<version>-windows-x86_64.zip`.

### Install

1. Open your **Downloads** folder, right-click `Concord-windows-x86_64.zip` → **Extract All…** →
   **Extract**. Windows can show a zip like a folder, but Concord cannot run from inside it:
   always extract it first.
2. The extracted folder `Concord-windows-x86_64` contains a folder **`Concord`** with:
   - **`Concord.exe`**: the desktop app (double-click it);
   - **`concord-cli.exe`**: the `concord` command for PowerShell or Command Prompt;
   - `_internal`: everything they need (Python, Concord, the console). Leave it next to them.

   You can move the whole `Concord` folder anywhere you like, for example to
   `C:\Users\you\Programs\Concord`. Keep the three items together.

### First launch (SmartScreen)

Double-click **Concord.exe**. Because the app is not signed, Microsoft Defender SmartScreen
shows **Windows protected your PC** the first time:

1. Click **More info**.
2. Check that *App* says **Concord.exe** and *Publisher* says *Unknown publisher*.
3. Click **Run anyway**.

You do this once per extracted copy. Some antivirus programs distrust programs built with
PyInstaller (which Concord's app is); if yours quarantines `Concord.exe`, restore it only if you
downloaded it from this repository's release page.

If Windows says *Smart App Control blocked…*, there is no override for unsigned apps: use the
Python installation ([B](#b-with-python-pip)).

Concord's window and console use only `127.0.0.1` (this computer), which does not make the
Windows firewall ask anything. Windows may ask whether Concord may communicate on networks when
an LSL source looks for streams, or when a BCI2000 source receives on a network address (by
default it receives on `127.0.0.1`, which does not make it ask). Allow **Private networks** only
if your acquisition system runs on another computer of your lab network
([LAB_SETUP.md](LAB_SETUP.md)); otherwise click **Cancel** (sources on this computer keep
working). The prompt may name `Concord.exe` or `concord-cli.exe`; both are Concord.

### Use

When Concord starts:

- a small **Concord** window shows *Concord is running* and, below it,
  `http://127.0.0.1:8000` (with the Concord icon in the taskbar);
- the console opens in your default browser (if it does not, click **Open console**).

To **quit**: **Stop and quit**, or close the Concord window (the **X**). Quitting first performs
a *safe stop*: command output off, any recording closed, decoding stopped, the source
disconnected. Opening Concord again while it runs just opens the console.

Your data stays on this PC, inside your user profile:

| | Location |
| --- | --- |
| Data (recordings, models, sessions, exports, logs) | `%LOCALAPPDATA%\Concord\data` (e.g. `C:\Users\you\AppData\Local\Concord\data`) |
| Optional config file | `%LOCALAPPDATA%\Concord\config.toml` |

To open the data folder: in File Explorer click the address bar, type
`%LOCALAPPDATA%\Concord\data` and press Enter.

**Commands.** `concord-cli.exe` answers the `concord` commands. In PowerShell (Start menu → type
*PowerShell*), go to the `Concord` folder first (or the folder you moved it to):

```powershell
cd $HOME\Downloads\Concord-windows-x86_64\Concord
```

```powershell
.\concord-cli.exe doctor
```

```powershell
.\concord-cli.exe config init
```

```powershell
.\concord-cli.exe dataset
```

```powershell
.\concord-cli.exe stop
```

`doctor` writes a support report (no neural or personal data) to `<data>\support\`;
`config init` writes a commented config file you can edit (port, data folder, retention);
`dataset` downloads the two public demo recordings (DANDI 000954, 8.7 MiB, verified by
SHA-256) so *Recorded human data* appears in the console; `stop` quits a running Concord (the
app or `concord-cli.exe start`) with the same safe stop as its window. In Command Prompt, type
`concord-cli.exe` without the `.\`.

Why two programs: a Windows program either has a window and no terminal output (the app you
double-click) or prints to a terminal (and opens a black console window when double-clicked).
`Concord.exe` given a command still runs it, but its output appears after the prompt has
already returned; use `concord-cli.exe` for commands. Concord also runs its helper processes
(source-plugin and decoder hosts) with `concord-cli.exe`, without showing a window.

### Uninstall

Quit Concord and delete the extracted folder. Your data is not removed: delete
`%LOCALAPPDATA%\Concord` yourself if you no longer need it (it may contain neural recordings;
see [SECURITY.md](SECURITY.md) on deletion).

## B. With Python (`pip`)

Packages are not on PyPI yet.

1. Install **Python 3.12 (64-bit)** from [python.org](https://www.python.org/downloads/windows/)
   (tick *Add python.exe to PATH*), or with `winget install Python.Python.3.12`. Not the
   Microsoft Store version: it can redirect files written under `%LOCALAPPDATA%` into its own
   package folder, so Concord's data folder would not be where this guide says.
2. Download the wheels (`.whl` files) from the
   [Releases page](https://github.com/arnavhiteshpatel-cloud/concord/releases/latest) into one
   folder, for example `$HOME\Downloads\concord-wheels`.
3. In PowerShell, create an environment and install:

   ```powershell
   py -3.12 -m venv $HOME\concord-env
   ```

   ```powershell
   & $HOME\concord-env\Scripts\python.exe -m pip install --find-links $HOME\Downloads\concord-wheels "concordos[lab]"
   ```

4. Start Concord:

   ```powershell
   & $HOME\concord-env\Scripts\concord.exe start
   ```

`concord start` starts Concord in the background on http://127.0.0.1:8000 (no window; it keeps
running after you close PowerShell), waits until it answers, prints the URL and opens the
console. Then:

```powershell
& $HOME\concord-env\Scripts\concord.exe status
```

```powershell
& $HOME\concord-env\Scripts\concord.exe stop
```

(`stop` performs the same safe stop as quitting the app.) If you activate the environment
(`& $HOME\concord-env\Scripts\Activate.ps1`; PowerShell may first need
`Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`), plain `concord start` works too.

`concordos[lab]` is the server with signal processing, NWB datasets, LSL and Open Ephys support
(on Windows it also installs `tornado`, which pyzmq needs for Open Ephys there). Plugins go into
the same environment, from the same folder of release wheels, for example
`pip install --find-links $HOME\Downloads\concord-wheels concord-brainflow`
([Connect your equipment](CONNECT_YOUR_EQUIPMENT.md)).

**From a checkout** (developers): the `Makefile` assumes macOS or Linux (bash, and a virtualenv
with `bin/`; Windows virtualenvs have `Scripts\`). On Windows, with
[uv](https://docs.astral.sh/uv/) and Node 20+:

```powershell
git clone https://github.com/arnavhiteshpatel-cloud/concord.git
```

```powershell
cd concord
```

```powershell
uv venv --python 3.12 .venv
```

```powershell
uv pip install --python .venv\Scripts\python.exe -e packages/concord-adapter-sdk -e packages/concord-decoder-sdk -e "backend[server,dev,nwb,dsp,live]"
```

```powershell
npm --prefix frontend ci
```

```powershell
npm --prefix frontend run build
```

```powershell
.venv\Scripts\concord.exe start
```

## Configuration

Every setting has a safe default; the config file is optional:

```powershell
.\concord-cli.exe config init
```

```powershell
.\concord-cli.exe config show
```

(Python install: `concord config init`.) `init` writes a commented file listing every key, as on
macOS and Linux ([INSTALL_MAC.md](INSTALL_MAC.md#configuration)). Windows paths in it are written
with doubled backslashes (`"C:\\data\\concord"`), as TOML requires; forward slashes
(`"C:/data/concord"`) work too. Environment variables (`CONCORD_PORT`, `CONCORD_DATA_DIR`, …)
override the file; in PowerShell: `$env:CONCORD_PORT = "8010"`.

**File permissions on Windows.** On macOS and Linux, Concord makes its data folder private
(folders 0700, files 0600) and refuses a config file other users can change. Windows has no
such mode bits: Concord relies on Windows' own permissions, under which the default folder,
inside your user profile (`%LOCALAPPDATA%`), cannot be opened by other standard users of the
PC. If you set `data_dir` to a folder outside your profile (e.g. `C:\data`, or the shared
`C:\Users\Public`), other users of the PC may be able to read it; keep neural data inside your
profile ([SECURITY.md](SECURITY.md)). **Advanced → Stored data** says which: it counts a folder
under `C:\Users\<name>\` as inside a user profile, and `C:\Users\Public` (and `Default`,
`All Users`) as outside.

## Troubleshooting

See [TROUBLESHOOTING.md](TROUBLESHOOTING.md). The first step is always:

```powershell
.\concord-cli.exe doctor
```

To see which program uses port 8000:

```powershell
netstat -ano | findstr :8000
```

The last number of the *LISTENING* line is the process ID; **Task Manager → Details** shows the
program with that PID.

## What has been tested

The app is built and smoke-tested automatically on GitHub Actions `windows-latest` (Windows
Server, x86_64) by the **package-windows** CI job and the release workflow: the zip is extracted
to a fresh folder and, from there, `concord-cli.exe --version`, the isolated decoder host and
`concord-cli.exe doctor` run; `Concord.exe --headless` starts with a fresh data folder, Simulated
Profile A streams, the BCI2000 plugin is discovered by the plugin host inside the app, a research
session and a recording are made, and `concord-cli.exe stop` quits it with the recording closed
cleanly; after `Concord.exe` is killed mid-recording (TerminateProcess) the next start keeps the
recording and marks it incomplete; `concord-cli.exe start`, `status` and `stop` run a background
server; and `Concord.exe` opens its Tk status window on the runner's desktop and quits cleanly.
The **backend-windows** job runs the whole backend test suite (with the real FALCON H1 and
AJILE12 data), the plugin and SDK suites, and the clean-room wheel installation
(`scripts/dist_check.py`) on Windows.

Not tested: the app on a physical Windows 10 or 11 PC (SmartScreen, a real display and
browser, Windows Defender's reaction to an unsigned PyInstaller program), Windows on ARM, and
any acquisition equipment on Windows; see [LIMITATIONS.md](../LIMITATIONS.md).
