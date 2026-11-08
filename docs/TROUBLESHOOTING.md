# Troubleshooting

Start with the support report; it checks most of what follows and contains no neural or
personal data:

```bash
concord doctor
```

(Desktop app: `/Applications/Concord.app/Contents/MacOS/Concord doctor`, or **Advanced →
Support report** in the console.) Logs are in `<data directory>/logs/`: `concord.log`
(rotating, redacted) and `console.log` (startup output of `concord start`).

## Installing and starting

| Symptom | Cause and fix |
| --- | --- |
| `The Concord server is not installed` | The base `concord` package is the application SDK only. `pip install "concordos[lab]"` (or `concordos[server]`). |
| `concord: refusing to listen on '0.0.0.0'` | Non-loopback addresses are refused (no authentication). Remove `host` from the config file / `CONCORD_HOST`. To use the console from another computer, use an SSH tunnel (docs/SECURITY.md). |
| `port 8000 is in use by another program` | `concord start --port 8010`, or `[server] port` in the config file. `concord doctor` shows who answers on the port. |
| `another Concord server … uses this data directory` | One server per data directory. `concord status`, then `concord stop`. |
| `refusing to use the config file: … can be changed by other users` | `chmod 600 <file>` (`concord config path` prints it). |
| `unknown key [server] prot` | A typo in the config file; `concord config template` lists every key. |
| `concord start` says the server exited during startup | The last lines of `<data>/logs/console.log` are printed; `concord doctor` for missing components. |
| The console page is blank or "Not Found", the API works | The console was not built into this installation: from a checkout `make build` (or `python packaging/stage_console.py --build` before building wheels). |
| `concord stop` says it killed the server | It did not exit within 30 s of SIGTERM. An active recording is recovered and marked incomplete at the next start. Check `concord.log`. |

## Desktop app (macOS)

| Symptom | Cause and fix |
| --- | --- |
| "Concord cannot be opened because Apple cannot check it for malicious software" | The app is unsigned and not notarized. See INSTALL_MAC.md "First launch". |
| "Concord is damaged and can't be opened" | The quarantine flag on a copy downloaded from a browser; for a build you trust: `xattr -dr com.apple.quarantine /Applications/Concord.app`. |
| The console does not open | Click **Open console** in the Concord window, or open http://127.0.0.1:8000. If Concord was already running, the second launch only opens the console. |
| No Concord window appears but the console works | The app runs without its window if none can be created (logged as "no window could be created"). Quit with `/Applications/Concord.app/Contents/MacOS/Concord stop`. |
| BrainFlow or another plugin is missing | The app includes only the BCI2000 plugin. Use the pip installation for other plugins. |
| First start is slow (tens of seconds) | macOS verifies the bundle on first launch. Later starts are faster. |

## Sources

| Symptom | Cause and fix |
| --- | --- |
| LSL stream not discovered | Different subnet or multicast blocked; firewall (UDP 16571, TCP/UDP 16572–16603); outlet not started. Test on one computer first. LAB_SETUP.md §2. |
| `arbitrary` units | A channel lacks a voltage unit in the LSL metadata, or the Open Ephys unit was left *unknown*. Concord never guesses units. |
| Open Ephys: "answered the heartbeat but sent no data" | Acquisition not running, or no channels selected in the ZMQ Interface. |
| Open Ephys: "did not answer" | Host/port/firewall (TCP 5556 and 5557 on the GUI computer). |
| BCI2000: no data | BCI2000's `ConnectorOutputAddress` must point to this computer and port (default 20321); inbound UDP allowed; `concord doctor` shows whether the port is free. |
| *Recorded human data* is empty | `concord dataset` downloads the demo files (needs network access to DANDI). |
| `incompatible_decoder` | Channel count/labels, bin size or feature differ from the model, or the stream is the model's training session, or a different source without override (LAB_GUIDE.md §7). |

## Sessions, recordings, export

| Symptom | Cause and fix |
| --- | --- |
| A recording is marked *incomplete* | Concord stopped while writing it (crash, kill, power loss). Every complete event was kept; see `<name>.recovery.json` next to it; bytes after the last complete event are in `<name>.discarded.bin`. |
| A research session is *interrupted* | Concord stopped unexpectedly while it was active. Start a new session; the old one can still be exported. |
| Recording stopped by itself | A recording limit was reached: by default 300 s / 200 MiB with raw frames (3600 s with *Features and labels only*), or free disk space fell below 256 MiB. The file is complete. Raise the limits in `[recording]` of the config file (`concord config show`; up to 24 h / 100 GiB) or use your acquisition software for raw archival. |
| Delete is refused | The item is in use (recording being written, active session, model of the running pipeline). Stop it first. |
| `concord reproduce` says `nothing_to_reproduce` | The bundle was exported without recordings; export again with *Include the session's recordings*. |
| `concord reproduce` reports a different model id | Different numerical libraries can change the last digits of the weights; the report shows the differences and the metrics. Install the versions listed in the bundle's `environment.json`. |
| `concord reproduce` fails integrity | A file in the bundle was modified or added after export. |
| Requests are refused with `forbidden_origin` | The request came from a web page on another site (or a host name other than 127.0.0.1/localhost). Open the console at http://127.0.0.1:8000. |
