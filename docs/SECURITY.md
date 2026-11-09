# Security: what is and is not protected

Concord is **research software** that runs on one computer, for one operator, without
accounts or passwords. It is **not a medical device**, it makes **no claim of HIPAA, GDPR,
FDA, CE or any other regulatory or clinical compliance**, and it has not had an independent
security review. The measures below reduce accidental exposure of neural data on the
operator's own computer; they do not make Concord safe to expose to a network or to share a
computer with people you do not trust.

Handle recordings under your institution's research data policy. Do not enter participant
identifiers anywhere in Concord (session names, notes, recording names).

## Protected

| Measure | What it does | Where |
| --- | --- | --- |
| **Read-only** | No adapter, API endpoint or SDK can write to, configure or stimulate a device. The only outbound message to acquisition software is the documented Open Ephys heartbeat. | ARCHITECTURE.md §8 |
| **Loopback only** | The server listens on `127.0.0.1` by default. Any other address is **refused at startup** unless `allow_remote = true` (config file), `CONCORD_ALLOW_REMOTE=1` or `--allow-remote` is given, and then a warning is logged and printed. | `concord/security.py` `check_bind` |
| **Other web sites** | A page open in your browser cannot use the API: requests whose `Origin` is another site, cross-site requests, `null` origins, and browser requests addressed to a non-loopback host name (DNS rebinding) are refused with 403; WebSocket handshakes from other sites are refused. | `server/origin.py` |
| **Private files** | The server runs with umask 077. The data directory and every directory in it are 0700, every file 0600 (recordings, models, sessions, exports, logs, support reports, the pid file). Existing files with wider permissions are tightened at startup. Downloaded public datasets (`data/datasets`) and symlinked directories are left as they are. **Windows** has no mode bits: Concord does not change permissions there. The default data folder (`%LOCALAPPDATA%\Concord\data`) is inside the user profile, which other standard users cannot open (administrators can); a `data_dir` elsewhere (e.g. `C:\data`) keeps the permissions Windows gives it, often readable by every user of the PC. Keep neural data inside your profile. | `security.py`, `server/app.py` |
| **Config file** | One TOML file, validated (unknown keys and wrong types are refused). A config file that other users can write to, or that belongs to another user, is refused (it decides where data goes and which interface the server listens on); POSIX only, on Windows the file is in the user profile (`%LOCALAPPDATA%\Concord\config.toml`). It holds no secrets. | `concord/config.py` |
| **Logs** | Every log line passes a redacting formatter: no secrets (`token=`, `password:`, `Authorization`, …) and no numeric arrays (sample data, feature vectors, weights: replaced by "[N values redacted]"); lines are capped at 4000 characters. Session names, operator names and notes are never logged (only session ids). Logs rotate (3 × 5 MB) in `<data>/logs/`. | `security.py` |
| **Support reports** | `concord doctor` and Advanced → Support report contain installation facts only. Every string is redacted again: the home directory becomes `~`, other users' home paths, e-mail and non-loopback IP addresses and the host name are replaced. The report lists what it leaves out. | `concord/doctor.py` |
| **Session exports** | Operator name and notes are excluded unless you tick the option; recordings are excluded unless you tick the option (then listed by SHA-256 only); public datasets are never included (referenced by SHA-256). Every file is listed with its SHA-256 in `manifest.json`; `concord reproduce` detects any modification. | `runtime/export.py`, `concord/reproduce.py` |
| **Retention and deletion** | `[retention]` in the config file deletes recordings, sessions, exports and models older than N days at startup. Recordings, models and sessions can be deleted in Advanced → Stored data or by REST; the server requires the name as confirmation and refuses anything in use. | `runtime/retention.py` |
| **Crash recovery** | A recording interrupted by a crash, kill or power loss keeps every complete event (the writer flushes at least every 0.25 s), is marked *incomplete* with counts and hashes, and anything after the last complete event is kept byte-for-byte in `<name>.discarded.bin`. Never silently truncated. | `runtime/recorder.py` |
| **Single instance** | Two servers cannot use the same data directory (an OS lock on `<data>/concord.pid`). | `server/serve.py` |
| **Plugins and models** | The console states where plugins are listed that they run with your user's permissions and that "compatible" is not a code review; models are refused for a different source unless you override (and the override is shown). | console, `decoding/model.py` |

## Not protected

- **No authentication.** Any program running on this computer — including programs of
  *other users* of the same computer — can connect to `127.0.0.1:8000`, control the runtime
  (connect sources, start control, authorize applications) and read the event stream,
  recordings and exports through the API. File permissions do not help against the API. Use
  Concord on a computer whose other users you trust, or a computer only you use.
- **No TLS.** Traffic on the loopback interface is not encrypted. If you set
  `allow_remote`, traffic on the network is not encrypted either and anyone who can reach the
  port has full control. Prefer an SSH tunnel (`ssh -L 8000:127.0.0.1:8000 concord-host`)
  over `allow_remote`.
- **No encryption at rest.** Recordings and exports are plain files. Use full-disk
  encryption (FileVault on macOS, LUKS on Linux).
- **Deletion is not secure erasure.** Deleting unlinks files. Copies may remain on SSDs (wear
  levelling), in backups and Time Machine snapshots, in exports you shared, and in the
  acquisition software's own recordings.
- **Not protected against your own user account, an administrator/root, or malware** running
  as you. Plugins are fault-isolated processes, not a sandbox: they can read your files and
  use the network (docs/ADAPTER_SDK.md §5). Install only plugins you trust.
- **No audit log in the security sense.** The research session log records operator
  actions for reproducibility; it is not tamper-proof and does not identify who acted.
- **LSL is unauthenticated.** Any computer on the local network can publish a stream that
  Concord will list; what a stream declares about itself (synthetic, prerecorded, units) is
  shown as declared (LIMITATIONS.md).
- **Authorizations for decoded commands** are keyed by the application id an app declares;
  they prevent mistakes, not a malicious local process that claims another app's id
  (docs/CONTROL_BRIDGE.md).
- **The desktop app is unsigned** (macOS: ad-hoc signature, not notarized; Windows: no
  Authenticode signature, so SmartScreen warns). The operating system cannot verify who built
  it; obtain it only from this repository's releases or your lab's own build
  (docs/INSTALL_MAC.md, docs/INSTALL_WINDOWS.md).

## Reporting a problem

Run `concord doctor`, check that the report contains nothing you would not share (it should
not; its last section lists what is excluded), and send it with a description to whoever
maintains your installation.
