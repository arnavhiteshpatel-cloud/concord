# Integration certification (`brainos-certify`)

Milestone 4, workstream D. `packages/brainos-certify` is an independently installable
toolkit for people who write BrainOS source plugins (adapter SDK API 1.x). It runs a plugin
**exactly as BrainOS runs it** — `python -m brainos_adapter_sdk.host` in a separate process,
binary IPC, host-side validation — checks and measures what the plugin declares and delivers,
and writes a machine-readable JSON report plus a Markdown report with an explicit validation
level. It works without BrainOS installed; when BrainOS is importable an optional runtime
phase also runs the plugin through BrainOS's own `PluginAdapter` and `Runtime`.

> **What a report is not.** Software checks only. A passing report is **not hardware
> certification**, not human-participant validation, not a safety or clinical statement and not
> a decoding-performance figure. It shows that the plugin satisfied the BrainOS adapter SDK
> contract, through the real plugin host, with the data source used in the run, on the machine
> named in the report. Both report formats begin with this statement.

Results for the plugins in this repository: [COMPATIBILITY.md](COMPATIBILITY.md).
Project-wide evidence levels: [VALIDATION_LEVELS.md](VALIDATION_LEVELS.md).

## 1. Validation levels

Exactly four. A report lists every level as achieved or not, with the reason and what is
missing; `summary.level` is the highest achieved.

| Level | Granted when | Reported as | What it does not show |
| --- | --- | --- | --- |
| `adapter_implementation` | Every required automated check passed or warned, and no check failed (§3). **The only level the toolkit grants by itself.** | "adapter implementation: every required automated check passed" | That anything other than the source used in the run (often a simulator or a replay) works |
| `protocol_tested` | `adapter_implementation`, **and** the operator names the external reference software that produced the data (`--protocol-reference "BrainFlow 5.23 BoardShim SYNTHETIC_BOARD"`), **and** that statement is consistent with the session: the manifest declares an `ecosystem`; the reference names it; the session `origin` starts with `<ecosystem>:`; if the reference contains a version and a Python distribution named like the ecosystem is installed in the plugin's environment, its version matches (otherwise "not checkable", which does not block) | "protocol-tested against &lt;reference&gt; (operator statement)" | The toolkit cannot observe which program produced the data: the level rests on the operator's statement. Nothing about hardware |
| `hardware_tested` | `adapter_implementation`, **and** an operator attestation (`--attestation`) that matches the attestation schema, is signed (Ed25519, detached) by the holder of the public key the operator supplies, names this plugin and version (and, if given, its file-tree hash) and is not dated in the future | "hardware-tested: operator-attested by … with &lt;make&gt; &lt;model&gt; serial …; not verified by this toolkit" | The toolkit verifies the signature and the plugin identity only. The hardware, the setup and the observations are the operator's claims. **Never set without an attestation** |
| `human_participant_validated` | Never | "never set by this toolkit" — out of scope for software: it requires an approved human-research protocol run by qualified investigators | — |

Mapping to the project's evidence levels (docs/VALIDATION_LEVELS.md): `adapter_implementation`
is level 1 evidence for a plugin, obtained through the real plugin host; `protocol_tested` is
the certification-report form of level 2 (the project records level 2 only where the reference
software was genuinely run, see COMPATIBILITY.md); an accepted attestation is an operator's
claim and is **not** by itself level 3 ("hardware-verified" requires an integrity and timing
comparison against an independent reference, which the attestation would have to document);
level 4 is never a software result.

The exit code is **0 only if `adapter_implementation` was achieved** (1 otherwise, 2 for
usage errors), so CI can gate on it.

## 2. How a run proceeds

Every step goes through the plugin host; plugin code never runs in the certifier's process.

1. **Host #1** starts (`hello`), `manifest`, plugin identity, `discover`.
2. **Open #1**: session metadata. **Main acquisition** for `--duration` seconds (default 20):
   every `read` answer is recorded (stream, first index, sample count, first/last timestamp,
   arrival time on the host's monotonic and wall clocks; numeric timestamps kept up to 2 M
   per stream), re-validated locally with the SDK's `ChunkValidator`, then the samples are
   dropped. The host process's CPU time and RSS are sampled from `/proc`. Then `stats`, 30 IPC
   pings.
3. **Clean close + open #2** in the same host; read `--reopen-seconds` (default 2).
4. **Fault injection**: a reader thread reads continuously; after 0.5 s the host process is
   killed with `SIGKILL`. The failure must surface as `HostDied` (what BrainOS's
   `PluginAdapter` turns into a link loss and reconnects) within `--kill-detect-limit`
   (default 2 s) — not as a hang and not as another error. **Host #2** starts, **open #3**,
   read, `close`, `shutdown` (exit code recorded).
5. **Runtime phase** (optional, §3.7): BrainOS opens the plugin twice more (probe + connect).
6. Checks are evaluated, levels decided, the report is validated against its own schema and
   written.

If a step fails, later steps that depend on it are reported as `not_run` with the reason
(e.g. "main acquisition stopped after 0.04 s (InvalidData); see integrity.read") — never as
passed. A run on a well-behaved plugin with the defaults takes about 35 s.

## 3. Checks

Status: `pass`, `fail`, `warn` (allowed, worth knowing), `not_run` (with `applicable: false`
when the check does not apply to this plugin, e.g. no markers stream). Ids are stable.

### 3.1 Manifest & compatibility

| Id | Checks | Fails when |
| --- | --- | --- |
| `manifest.load` | The host starts and imports / instantiates the plugin | Import error, not a `SourcePlugin`, host does not start |
| `manifest.valid` | `validate_manifest`, by the host and again locally | Any error (warnings → `warn`) |
| `manifest.api_compat` | Plugin `api_version` vs the host's and the certifier's SDK API (`major` equal, `minor` ≤) | Incompatible; `warn` if the host's SDK version differs from the certifier's |
| `manifest.entry_point` | The `brainos.sources` entry point exists once and its name is valid | Missing / duplicated / invalid name; `warn` when certifying a `module:Class` reference (entry point not verified) |
| `manifest.distribution` | Installed distribution name/version vs the manifest; **every file hash in its `RECORD`** re-computed; the plugin package's files hashed individually (`tree_sha256`); git commit and cleanliness of the source tree | `warn` on name/version mismatch, modified or missing `RECORD` files, or no installed distribution. Editable installs: `RECORD` covers only the `.pth`, so the source files' hashes identify what was tested |
| `manifest.discover` | `discover()` returns valid devices (`validate_devices`) including the one tested | Error, hang (`discover timeout + 10 s`), invalid devices, nothing to open; `warn` if `--device` is not among the discovered |

### 3.2 Metadata

| Id | Checks | Fails when |
| --- | --- | --- |
| `metadata.session_valid` | `open()` succeeds; `validate_session_info` (host + local) | `OpenFailed`, `InvalidOptions`, plugin exception, invalid session; warnings → `warn` |
| `metadata.units` | Units per channel; signal units BrainOS converts to µV (same table as LSL) | **Never fails.** `warn` for channels without a unit (shown as "arbitrary" — correct when the source does not state units) or non-voltage signal units |
| `metadata.modality` | `modality` / `invasive` on signal and spike-count streams, and their consistency (EEG/MEG/EMG noninvasive; ECoG/sEEG/intracortical implanted) | Inconsistent declaration; `warn` when not declared |
| `metadata.channel_identity` | Stream ids, roles, channel labels and order, units, types, nominal rates, clock domains, modality, flags and origin are **identical** on every open: #1, #2 (same host), #3 (fresh host after the kill) and BrainOS's own open | Any difference (listed field by field) |

### 3.3 Timestamps (main acquisition)

| Id | Checks | Threshold |
| --- | --- | --- |
| `timing.monotonic` | Timestamps never decrease, within and across chunks, in every session (host `chunk.timestamps.decreasing` errors land here) | Any decrease fails |
| `timing.rate` | Rate implied by the source's own timestamps (index span / time span, so lost samples are accounted for; least-squares estimate also reported) vs the nominal rate, per regular stream | \|measured / nominal − 1\| > `--rate-tolerance` (default **±2 %**) fails; a regular stream that delivers nothing fails. `sample_counter` clocks: equal by construction (see `performance.throughput`). Irregular-only sessions: not applicable |
| `timing.jitter` | p50/p95/p99/max of: timestamp residuals from a linear fit against the sample index (offset and drift removed), inter-sample interval error vs 1/nominal, inter-chunk arrival intervals, samples per chunk | `warn` when the p99 residual exceeds **one sample period** (not for `sample_counter`) |
| `timing.clock_domain` | Plausibility for the declared domain, from the newest sample of each chunk vs its arrival: `unix` vs `time.time()`; `lsl` vs liblsl `local_clock()` (if `pylsl` is importable; otherwise only monotonic offset/drift are reported); `source`: offset to the host's monotonic clock (origin unknown by declaration); `sample_counter`: timestamps must equal t0 + index / nominal. Drift of the source clock against the host's monotonic clock (ppm, least squares over the run) | `unix`/`lsl`: fail if the median offset exceeds **60 s** (not that clock); `warn` if samples are stamped > 0.5 s in the future or arrive > 5 s late. `sample_counter`: fail beyond 1 µs. Any domain: `warn` above **1000 ppm** drift |

### 3.4 Packet ordering, loss, data validity

| Id | Checks | Fails when |
| --- | --- | --- |
| `integrity.read` | The session streams for the whole run: no host death, hang (read timeout + `--read-grace`), plugin exception, `LinkLost` / `ConfigurationChanged` during a normal run, invalid data | Any of these; the reason names the cause check for invalid data |
| `integrity.chunk_validation` | Every chunk of every session validated by the host and again by the certifier (`ChunkValidator`: stream, kind, dtype, shape, channel count, size, finiteness, spike-count integrality, labels) | Any validation error (the host stops the session); warnings (empty chunks) → `warn` |
| `integrity.sample_index` | `first_index` continuity per stream and session | Overlap (index goes back) fails; gaps → `warn` with gap count, lost samples and loss fraction |
| `integrity.markers` | Marker timestamps never decrease and lie within the primary stream's time span (± 1 s) | Decrease fails; markers outside the span (clock mismatch) or no markers during the run → `warn`; not applicable without a markers stream |
| `integrity.plugin_stats` | `stats()` returns valid counters | `stats()` raises; `warn` for invalid entries or counters reporting loss (`drop`, `lost`, `overflow`, `malformed`, `missed`) |

### 3.5 Reconnection & fault injection

| Id | Checks | Fails when |
| --- | --- | --- |
| `reconnect.clean_reopen` | `close` (latency), `open` again in the same host, time to first data, data valid, identity unchanged | Close/reopen error, no data within `--reopen-seconds`, invalid data, identity changed |
| `reconnect.host_killed` | `SIGKILL` of the host mid-stream → surfaces as `HostDied` (link loss), detection latency; a fresh host opens the device; time to first data after host start and after `open`; identity unchanged; clean `shutdown` | Hang or a different error, detection slower than `--kill-detect-limit`, fresh open fails (e.g. a device lock left behind by the killed process), no data, identity changed |

### 3.6 Performance (main acquisition; machine-dependent, never asserted as absolute latency)

| Id | Measures | Fails when |
| --- | --- | --- |
| `performance.throughput` | Delivered samples per second of the host's monotonic clock (least squares of the cumulative count against arrival time) vs nominal, per regular stream; IPC bytes/s | Outside `--rate-tolerance`: "falls behind" (e.g. a slow `read`) or "runs ahead of real time" (an unpaced source) |
| `performance.latency` | `unix` / `lsl` clocks only: arrival time minus the newest sample's timestamp, p50/p95/p99/max; oldest-sample offset | Informational; not applicable to `source` / `sample_counter` clocks |
| `performance.host_resources` | Host process CPU (`utime + stime` from `/proc/<pid>/stat`, % of one core) and RSS (median, max sampled every 0.25 s, peak `VmHWM`) | `warn` above 80 % of one core; not applicable without `/proc` |
| `performance.ipc` | Host byte / read / chunk counters, reads/s, empty-read fraction, ping round trip | Informational |

### 3.7 BrainOS runtime phase (optional checks)

Runs when `brainos` is importable and `--no-runtime` is not given: the plugin is registered
(`PluginRegistry.register`, which probes it) and connected in an in-process `Runtime` (no
server) for `--runtime-seconds` (default 5). Expectations are derived from the plugin's own
`SessionInfo` and manifest, not from BrainOS, so a BrainOS mapping bug would also show.
When BrainOS is not installed the four checks are `not_run` (not applicable) and the report
notes that contract compliance was not verified; a failing runtime check still blocks the
level.

| Id | Checks |
| --- | --- |
| `runtime.descriptor` | `kind` (simulated / replay / stream from the synthetic / prerecorded flags), `synthetic`, `modality` and `invasive` (from the primary neural stream; invasiveness from the declaration, else the modality's category), `integration` (`plugin`, package, version, API version, `isolated: true`, ecosystem), capabilities = the roles' capabilities + `device_status`, no command capability |
| `runtime.negotiation` | Three test apps: every capability optional → exactly the roles' capabilities granted, every other one rejected `unsupported_by_device`; the roles' capabilities required → `active`; `pointer_intent` required → `suspended`, nothing granted, nothing delivered |
| `runtime.envelopes` | Every published event (up to 5000) validates with BrainOS's pydantic contract (`parse_envelope`) **and** the published JSON Schema (`envelope_json_schema`); schema version recorded; BrainOS diagnostics show 0 validation errors, 0 undeclared capabilities, 0 decode errors; runtime still `streaming`; data events were published |
| `runtime.provenance` | Per event: provenance kind per role (`raw_signal`, `processed_feature`, `behavioral_label`, `decoded_intent`), `synthetic` and `replayed` as declared, origin as declared, decoder output carries `model_id = <package>:<model_id>`, quality flags `synthetic` / `replayed`; no `intent.pointer` / `intent.selection` / `intent.text` event; `warn` if a regular stream published nothing |

## 4. Reports

`<out>/<name>.certify.json` and `<out>/<name>.certify.md` (`--out`, `--name`).

**JSON** (schema: `brainos_certify/schemas/report.schema.json`, `brainos-certify
--print-schema`; every report is validated against it before it is written):

| Key | Content |
| --- | --- |
| `notice` | The "not hardware certification" statement (first key) |
| `report_version`, `tool`, `generated_at`, `started_at`, `elapsed_s` | `"1.0"`, `brainos-certify` version, UTC times |
| `environment` | OS, kernel, architecture, CPU model and count, memory, Python, adapter SDK version and API, BrainOS version (or `null`), the host's Python / SDK. No host or user name |
| `plugin` | Reference, entry point, device key, manifest summary, identity (entry point, distribution, requirements with installed versions, `RECORD` verification, per-file SHA-256 and `tree_sha256` of the plugin package, git commit / dirty), session (origin, flags, streams) |
| `options` | Plugin options as requested and as resolved by the host, and the run options. Values of options whose name contains `secret`, `token`, `password` or `passwd` are replaced by `<redacted>` |
| `summary` | Status counts, highest level and its statement, exit code, blocking results |
| `levels` | `achieved`, `highest`, and per level `achieved` / `statement` / `why` / `missing` (plus `consistency` rules for `protocol_tested`, notes for `adapter_implementation`) |
| `protocol_reference`, `attestation` | The operator statement and its consistency rules; the attestation verdict, file SHA-256, public-key fingerprint, the attested fields |
| `checks` | All 29 checks in a fixed order: `id`, `group`, `title`, `required`, `status`, `applicable`, `reason` (≤ 300 characters), `evidence` (measured values) |
| `host_log_tail` | Last lines the plugin hosts wrote to stderr |

**Markdown**: the notice, level and counts first, then a summary table (check / status /
reason), the levels, plugin identity and streams, options, per-check details with the
evidence, and the environment.

## 5. Hardware attestation

An attestation is the operator's signed statement; the toolkit records it and never
produces one. Format (`brainos_certify/schemas/attestation.schema.json`, no extra keys):

```json
{
  "attestation_version": "1.0",
  "statement": "I attest that the plugin identified below was run with the physical acquisition hardware described here, and that the setup and observations recorded here are accurate. This is my own statement; the BrainOS certification toolkit does not verify it.",
  "attested_by": {"name": "…", "organization": "…", "role": "…", "email": "…"},
  "date": "2026-11-07T10:00:00Z",
  "plugin": {"name": "<manifest name>", "version": "<manifest version>", "tree_sha256": "<optional, from a report>"},
  "hardware": {"make": "…", "model": "…", "serial_number": "…", "firmware_version": "…"},
  "acquisition_software": "…",
  "setup": "… (≥ 20 characters)",
  "observations": "… (≥ 20 characters)",
  "duration_s": 1800
}
```

Signing (OpenSSL 3, Ed25519, detached, over the exact file bytes):

```bash
openssl genpkey -algorithm ed25519 -out operator.key
openssl pkey -in operator.key -pubout -out operator.pub
openssl pkeyutl -sign -rawin -inkey operator.key -in attestation.json -out attestation.json.sig
brainos-certify my-device --attestation attestation.json --attestation-public-key operator.pub
```

Rejected (and `hardware_tested` not granted) when: unreadable / not JSON, schema violation
(missing hardware fields, a different statement, extra keys such as a self-declared level),
unsigned, signature does not verify with the supplied key (e.g. the file was edited after
signing, or another key signed it), `openssl` missing, a different plugin name or version, a
different `tree_sha256`, a date in the future. An accepted attestation proves only that the
holder of the supplied key signed this statement about this plugin version.

## 6. Limitations

* Certifies **plugins** (adapter SDK). Built-in adapters (simulated, NWB, LSL, Open Ephys) are
  not plugins; their evidence is their own test suites (COMPATIBILITY.md).
* What a plugin declares (synthetic / prerecorded, origin, units, modality) is checked for
  consistency, never for truth: a plugin can lie within the contract. `protocol_tested` rests
  on the operator's statement and `hardware_tested` on the operator's signature.
* Timing figures are machine- and load-dependent and come from the certifier's own clock
  readings after IPC; latency is only measured for `unix` / `lsl` clocks.
* Linux `/proc` is needed for CPU / RSS; elsewhere `performance.host_resources` is not run.
* Loss that a source cannot express in `first_index` (e.g. whole BCI2000 blocks) is invisible.
* The kill test detects a dead host; it does not test a device physically disappearing (that
  is the plugin's `LinkLost`, exercised only by the plugin's own tests).
* Thresholds (±2 %, one sample period, 1000 ppm, 60 s, 80 % CPU) are engineering choices for
  catching defects, not standards.
