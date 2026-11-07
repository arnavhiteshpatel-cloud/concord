# Troubleshooting

Start with the support report; it checks most of what follows and contains no neural or
personal data:

```bash
brainos doctor
```

(Desktop app: `/Applications/BrainOS.app/Contents/MacOS/BrainOS doctor`, or **Advanced →
Support report** in the console.) Logs are in `<data directory>/logs/`: `brainos.log`
(rotating, redacted) and `console.log` (startup output of `brainos start`).

## Installing and starting

| Symptom | Cause and fix |
| --- | --- |
| `The BrainOS server is not installed` | The base `brainos` package is the application SDK only. `pip install "brainos[lab]"` (or `brainos[server]`). |
| `brainos: refusing to listen on '0.0.0.0'` | Non-loopback addresses are refused (no authentication). Remove `host` from the config file / `BRAINOS_HOST`. To use the console from another computer, use an SSH tunnel (docs/SECURITY.md). |
| `port 8000 is in use by another program` | `brainos start --port 8010`, or `[server] port` in the config file. `brainos doctor` shows who answers on the port. |
| `another BrainOS server … uses this data directory` | One server per data directory. `brainos status`, then `brainos stop`. |
| `refusing to use the config file: … can be changed by other users` | `chmod 600 <file>` (`brainos config path` prints it). |
| `unknown key [server] prot` | A typo in the config file; `brainos config template` lists every key. |
| `brainos start` says the server exited during startup | The last lines of `<data>/logs/console.log` are printed; `brainos doctor` for missing components. |
| The console page is blank or "Not Found", the API works | The console was not built into this installation: from a checkout `make build` (or `python packaging/stage_console.py --build` before building wheels). |
| `brainos stop` says it killed the server | It did not exit within 30 s of SIGTERM. An active recording is recovered and marked incomplete at the next start. Check `brainos.log`. |

## Desktop app (macOS)

| Symptom | Cause and fix |
| --- | --- |
| "BrainOS cannot be opened because Apple cannot check it for malicious software" | The app is unsigned and not notarized. See INSTALL_MAC.md "First launch". |
| "BrainOS is damaged and can't be opened" | The quarantine flag on a copy downloaded from a browser; for a build you trust: `xattr -dr com.apple.quarantine /Applications/BrainOS.app`. |
| The console does not open | Click **Open console** in the BrainOS window, or open http://127.0.0.1:8000. If BrainOS was already running, the second launch only opens the console. |
| No BrainOS window appears but the console works | The app runs without its window if none can be created (logged as "no window could be created"). Quit with `/Applications/BrainOS.app/Contents/MacOS/BrainOS stop`. |
| BrainFlow or another plugin is missing | The app includes only the BCI2000 plugin. Use the pip installation for other plugins. |
| First start is slow (tens of seconds) | macOS verifies the bundle on first launch. Later starts are faster. |

## Sources

| Symptom | Cause and fix |
| --- | --- |
| LSL stream not discovered | Different subnet or multicast blocked; firewall (UDP 16571, TCP/UDP 16572–16603); outlet not started. Test on one computer first. LAB_SETUP.md §2. |
| `arbitrary` units | A channel lacks a voltage unit in the LSL metadata, or the Open Ephys unit was left *unknown*. BrainOS never guesses units. |
| Open Ephys: "answered the heartbeat but sent no data" | Acquisition not running, or no channels selected in the ZMQ Interface. |
| Open Ephys: "did not answer" | Host/port/firewall (TCP 5556 and 5557 on the GUI computer). |
| BCI2000: no data | BCI2000's `ConnectorOutputAddress` must point to this computer and port (default 20321); inbound UDP allowed; `brainos doctor` shows whether the port is free. |
| *Recorded human data* is empty | `brainos dataset` downloads the demo files (needs network access to DANDI). |
| `incompatible_decoder` | Channel count/labels, bin size or feature differ from the model, or the stream is the model's training session, or a different source without override (LAB_GUIDE.md §7). |

## Sessions, recordings, export

| Symptom | Cause and fix |
| --- | --- |
| A recording is marked *incomplete* | BrainOS stopped while writing it (crash, kill, power loss). Every complete event was kept; see `<name>.recovery.json` next to it; bytes after the last complete event are in `<name>.discarded.bin`. |
| A research session is *interrupted* | BrainOS stopped unexpectedly while it was active. Start a new session; the old one can still be exported. |
| Recording stopped by itself | 300 s / 200 MB limit with raw frames (3600 s with *Features and labels only*). Use your acquisition software for raw archival. |
| Delete is refused | The item is in use (recording being written, active session, model of the running pipeline). Stop it first. |
| `brainos reproduce` says `nothing_to_reproduce` | The bundle was exported without recordings; export again with *Include the session's recordings*. |
| `brainos reproduce` reports a different model id | Different numerical libraries can change the last digits of the weights; the report shows the differences and the metrics. Install the versions listed in the bundle's `environment.json`. |
| `brainos reproduce` fails integrity | A file in the bundle was modified or added after export. |
| Requests are refused with `forbidden_origin` | The request came from a web page on another site (or a host name other than 127.0.0.1/localhost). Open the console at http://127.0.0.1:8000. |
