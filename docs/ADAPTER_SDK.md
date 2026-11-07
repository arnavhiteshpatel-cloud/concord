# BrainOS adapter SDK (API 1.0) — source plugins

The adapter SDK (`packages/brainos-adapter-sdk`, import name `brainos_adapter_sdk`) lets a third
party connect a neural-data source to BrainOS **without changing BrainOS**: write a plugin against
the SDK only, `pip install` it into BrainOS's Python environment, and BrainOS discovers it,
validates it and runs it in a separate process. Plugins are **read-only**: the API has no way to
send anything to a device, and a plugin cannot produce application commands.

* Tutorial: [`examples/adapters/brainos-example-adapter/README.md`](../examples/adapters/brainos-example-adapter/README.md)
  ("write your own adapter in 15 minutes").
* Normative API: `brainos_adapter_sdk/api.py`. Validation: `brainos_adapter_sdk/validate.py`.
* Runtime side: `backend/src/brainos/adapters/plugin/`, `backend/src/brainos/runtime/plugins.py`,
  ARCHITECTURE.md §12.

Validation level of this mechanism (docs/VALIDATION_LEVELS.md): software only. The example
plugin is a declared-synthetic generator; no plugin has been run against hardware.

## 1. Concepts

| Concept | API | Meaning |
| --- | --- | --- |
| Plugin | `SourcePlugin` subclass with a class attribute `manifest: PluginManifest` | One installable integration (e.g. "BrainFlow boards"). Instantiated without arguments by the plugin host. |
| Device | `DeviceInfo` from `discover(timeout_s)` | Something the plugin can open now. `device_key` (matches `KEY_PATTERN`) becomes part of the BrainOS device id `plugin:<entry point>:<device key>`. Plugins that cannot enumerate return one configurable entry. |
| Options | `manifest.options: {name: OptionSpec}` | Operator settings for `open()` (`str`, `int`, `float`, `bool`, `choice`). BrainOS generates the form, validates the values, fills in defaults. Range checks are the plugin's job (raise `InvalidOptions`). |
| Session | `open(device_key, options) -> SourceSession` | One connection. `info: SessionInfo` must not change while open (raise `ConfigurationChanged`). |
| Stream | `StreamSpec` | Role, channels (label, unit, type), nominal rate (0 = irregular), clock, and role-specific fields (modality / invasive, bin_ms, quantity, model_id). |
| Chunk | `Chunk(stream_id, data[n, ch], timestamps[n], first_index)` / `MarkerChunk(stream_id, labels, timestamps)` | Data returned by `read(timeout_s)`. `first_index` counts samples per stream since `open()`; a jump = lost samples. |
| Errors | `OpenFailed`, `InvalidOptions`, `LinkLost`, `ConfigurationChanged`, `PluginError` | Messages are shown to the operator. |

**Declare what you know; leave unknowns as `None`.** BrainOS never guesses: a channel without a
unit is shown as "arbitrary", a stream without modality as "modality not declared".

## 2. Lifecycle and how BrainOS uses a plugin

```
pip install my-plugin  ──▶  entry point  [project.entry-points."brainos.sources"]  name = "pkg.mod:Class"
                                │
BrainOS startup / "Search again" │  python -m brainos_adapter_sdk.host --list
                                ▼  (one host process per plugin: manifest + discover())
                        GET /api/v1/plugins  (compatible / rejected + reason / failed to load)
                                │
operator: options form, Connect │  POST /api/v1/plugins/{name}/configure  {device_key, options}
                                ▼  (options validated; device opened once in a host to learn its streams)
                        DeviceDescriptor  plugin:<name>:<key>   (in /devices, the console picker)
                                │
                                ▼  runtime connect: a fresh host process per connection / reconnect
       host: open() → read(timeout) … → close()   ══binary IPC══▶   PluginAdapter → standard events
```

## 3. Roles → BrainOS events

| Role | Event | Provenance | Notes |
| --- | --- | --- | --- |
| `SIGNAL` | `recording.frame` | `raw_signal` | µV only if **every** channel states a known voltage unit (microvolts / millivolts / volts / nanovolts, exact factors; same table as LSL), else `unit = "arbitrary"`, values unscaled. Frames ≤ 2000 samples; the first frame after a sample-index gap is flagged `dropped_samples`. |
| `SPIKE_COUNTS` | `features.binned` | `processed_feature` | `feature = spike_count`, `bin_ms` required; the sample timestamp is the **end** of the bin. Values must be non-negative integers. |
| `BEHAVIOR` | `behavior.sample` | `behavioral_label` | `quantity` (default `behavior`), `dims` = channel labels, unit = the channels' common unit / `mixed` / `unspecified`. |
| `MARKERS` | `recording.annotation` | `behavioral_label` | One annotation per label. |
| `DECODER_OUTPUT` | `intent.kinematics` | `decoded_intent`, `model_id = "<plugin name>:<spec.model_id>"` | The output of an *external* decoder. Never reaches applications as `pointer_intent` / `selection` / `text_intent`; only the operator-enabled command router produces commands. |

* One stream per role is delivered (the primary for its role, else the first declared). Further
  streams of the same role are listed in the source metadata as "not delivered" with the reason.
* Descriptor: `kind = simulated` if the session declares `synthetic`, `replay` if `prerecorded`
  (events then carry `replayed: true`), else `stream` ("origin unverified"). Contract-1.3 fields:
  `modality` / `invasive` from the delivered neural stream (invasiveness follows the declaration,
  or the contract's category for a declared modality — EEG/MEG/EMG noninvasive, ECoG/sEEG/
  intracortical implanted), `integration = {kind: "plugin", package, version, api_version,
  isolated: true, ecosystem}`. Capability params state channel labels, units, rate and modality.
* `device_timestamp_ns` = the plugin's source timestamps (seconds × 1e9). **Clock rule:** every
  stream must use the primary stream's clock domain (`session.clock.mixed` otherwise). Streams
  on different clocks cannot be aligned without a measured offset, which API 1.0 does not carry,
  so they are rejected rather than silently mixed; convert in the plugin.

## 4. Validation rules

Everything is checked by the host before it leaves the plugin process **and again by the
runtime** on receipt (the host process runs third-party code and is not trusted). Codes are
stable; `severity` is `error` (rejected / stopped), `warning` or `info`.

**Manifest** (`validate_manifest`; errors make the plugin "rejected" — listed, cannot connect)

| Code | Rule |
| --- | --- |
| `manifest.name` | distribution-style name (`[A-Za-z0-9._-]`, ≤ 64) |
| `manifest.version` | semantic version (`0.1.0`, pre-release/build allowed) |
| `manifest.api_version.format` / `.incompatible` | `major.minor`; **same major as the host and minor ≤ host minor** |
| `manifest.display_name` / `description` / `author` / `license` | non-empty, bounded |
| `manifest.ecosystem` | `None` or `[a-z0-9][a-z0-9_.-]{0,63}` |
| `manifest.roles.empty` / `.unknown` / `.no_primary` | non-empty subset of `StreamRole`, including a primary role (`signal`, `spike_counts`, `decoder_output`) |
| `option.name` / `.type` / `.description` / `.choices` / `.default` | key matches `KEY_PATTERN`; known type; `choice` needs unique non-empty choices (others none); default of the right type / in choices. `option.required_with_default` is a warning. |
| `entry_point.name` / `entry_point.duplicate` | entry-point name `[a-z0-9][a-z0-9_.-]{0,23}` (it is part of device ids); one distribution per name |
| `manifest.name.dist_mismatch` / `manifest.version.dist_mismatch` | warnings: manifest differs from the installed distribution |

**Options** (`validate_options`): unknown names (`options.unknown`), missing required
(`options.missing`), values not coercible to the type / not a choice (`options.invalid`; form
strings such as `"7"` or `"true"` are accepted, `bool` is never an `int`).

**Devices** (`validate_devices`): sequence of `DeviceInfo` (≤ 64), unique `device_key` matching
`KEY_PATTERN`, non-empty `display_name`, `details` maps short strings to strings.

**Session** (`validate_session_info`; errors refuse the session)

| Code | Rule |
| --- | --- |
| `session.streams.empty` / `.count` / `.duplicate`, `stream.id` | 1–16 streams, unique ids matching `KEY_PATTERN` |
| `stream.role.unknown` / `stream.role.undeclared` | role is a `StreamRole` **and in `manifest.roles`** |
| `stream.channels.empty` / `.count` / `.duplicate`, `channel.label.empty` / `.length`, `channel.unit` / `channel.type` | ≥ 1 channel (≤ 1024 signal, 4096 spike counts, 64 behavior/decoder, 1 markers); unique non-empty labels (≤ 32 chars for behavior/decoder dims); unit/type `None` or short text |
| `stream.rate`, `stream.rate.irregular` | finite, ≥ 0, ≤ 100 kHz for signals; 0 (irregular) only for markers / behavior / decoder output |
| `stream.clock` | `ClockInfo` with domain `source` / `unix` / `lsl` / `sample_counter` |
| `stream.modality`, `.modality.not_applicable`, `stream.invasive.*` | known modality, only on signal / spike-count streams; EEG/MEG/EMG cannot be `invasive=True`, ECoG/sEEG/intracortical cannot be `invasive=False` |
| `stream.bin_ms.missing` / `.not_applicable` (`.rate_mismatch` warning) | spike counts require `0 < bin_ms ≤ 10000`; other roles must not set it |
| `stream.model_id.missing` / `.not_applicable` | decoder output requires `model_id`; others must not set it |
| `stream.quantity.not_applicable` | `quantity` only for behavior / decoder output |
| `session.primary.missing` / `.role` | the primary stream exists and has a primary role |
| `session.clock.mixed` | all streams on the primary's clock domain |
| `session.origin`, `session.synthetic`, `session.prerecorded` | non-empty origin ≤ 128; booleans. Both flags set → warning, treated as synthetic |

**Chunks** (`ChunkValidator`, stateful per session; an error **stops the session**)

| Code | Rule |
| --- | --- |
| `read.type`, `chunk.type` | `read()` returns a sequence of `Chunk` / `MarkerChunk` |
| `chunk.stream.unknown`, `chunk.kind_mismatch` | the stream was declared; markers ↔ `MarkerChunk` |
| `chunk.data.type` / `.dtype` / `.shape` / `.channels` | numpy array, real numeric dtype (≤ 8 bytes), 2-D, columns = declared channels |
| `chunk.too_large` | ≤ 1 000 000 samples and ≤ 64 MiB per chunk |
| `chunk.timestamps.type` / `.length` / `.finite` / `.negative` / `.decreasing` | 1-D numeric, one per sample, finite, ≥ 0, non-decreasing within the chunk **and across calls** |
| `chunk.data.finite` | no NaN / ±inf |
| `chunk.counts.invalid` | spike counts are non-negative integers |
| `chunk.index`, `chunk.index.overlap`, `chunk.index.gap` (warning) | `first_index` int ≥ 0; going back = overlap (error); jumping ahead = lost samples (reported, counted, flagged) |
| `chunk.labels.type` / `.empty` / `.length` | marker labels: non-empty text ≤ 128 chars |
| `chunk.empty` (warning) | empty chunks are ignored |

## 5. Isolation model — and its limits

**A subprocess is not a security sandbox.** The plugin host isolates *faults*, not *intent*.

What **is** isolated / guaranteed:

* Plugin code (import, `discover`, `open`, `read`, `close`) never runs in the BrainOS process.
  Discovery runs `host --list`, which enumerates entry points from package metadata without
  importing them and probes each plugin in its **own** process; one plugin that fails to
  import, hangs or exits cannot affect the listing of the others.
* A plugin exception becomes a typed error; a crash (`os._exit`, segfault, `SIGKILL`) or a hang
  (no answer within `read timeout + grace`, default 0.1 + 5 s) ends that host process and becomes a
  `DeviceLinkError` → the runtime's reconnect policy starts a **fresh** process. The runtime
  never crashes and its pump never blocks on plugin code.
* Plugin output to stdout (Python `print`, or a C library writing to fd 1) cannot corrupt the
  IPC channel: before plugin code is imported the host moves the channel to private file
  descriptors, points fd 1 at stderr and fd 0 at `/dev/null`. Plugin output goes to the plugin
  log (shown in source metadata, last lines kept).
* Everything is validated twice (host, then runtime). Frame lengths are bounded (header 4 MiB,
  buffer 128 MiB); malformed frames end the host.
* Contract violations **stop** the plugin (host killed; every reopen refused with the reason),
  so the runtime ends in `error` with a clear message instead of looping: invalid data, an
  undeclared stream or role, an invalid session or manifest, an unexpected exception in plugin
  code, malformed IPC content, or 3 consecutive sessions that fail before delivering any data.
  `LinkLost` / `ConfigurationChanged`, host exits and hangs are reconnected.
* A plugin cannot emit an event type outside the role mapping, cannot claim command
  capabilities, and its decoder output is `intent.kinematics` only.

What is **not** isolated:

* Same OS user, same permissions: a plugin can read and write every file BrainOS can
  (recordings, models, datasets), open network connections, start processes and read
  environment variables. `manifest.network` is a declaration shown to the operator, not enforced.
* No CPU / memory / disk limits; a plugin can starve the machine.
* A malicious plugin can bypass its own host's checks (it shares the process); the runtime's
  re-validation still enforces the contract on what arrives, but a plugin can **lie** within it:
  `synthetic`, `prerecorded`, units, modality and origin are self-declared and are shown as
  declared ("declared synthetic", "origin unverified"), never verified.
* Installing a plugin is installing a Python package into BrainOS's environment: it can
  modify BrainOS's own files, and its dependencies can conflict with BrainOS's. Treat a plugin
  like any code you run. (`BRAINOS_PLUGIN_PYTHON` runs hosts with another interpreter /
  virtualenv that has `brainos-adapter-sdk` installed, which separates dependencies but not
  privileges.)
* Child processes a plugin starts are not tracked. If the runtime itself is killed hard, a
  plugin blocked inside `read()` lives until that call returns (then its next write fails and it
  exits); hosts run in their own process group, so a terminal Ctrl-C reaches only the runtime.

## 6. IPC protocol (`brainos.plugin-ipc/1`)

* Transport: the host process's original stdin (runtime → host) and stdout (host → runtime).
* Frame: 4-byte big-endian length + payload. Message: one UTF-8 JSON header frame, then one raw
  binary frame per entry of `header.buffers = [{dtype: "<f4", shape: [n, ch]}, …]` (little-endian,
  C order; dtypes f4 f8 i1 i2 i4 i8 u1 u2 u4 u8). **Sample data and timestamps never go
  through JSON**, so values and dtypes arrive bit-exact (tested).
* The host speaks first: `{type: "hello", protocol, api_version, sdk_version, pid, loaded,
  load_error}`. Then strictly request/response: `{id, cmd, args}` →
  `{id, ok: true, result}` or `{id, ok: false, error: {type, message, traceback, problems}}`.
* Commands: `ping`, `manifest`, `discover {timeout_s}`, `open {device_key, options}` →
  `{info, problems, options}`, `read {timeout_s}` → `{chunks: [{kind, stream_id, first_index |
  labels}], notices}` + buffers (data then timestamps per numeric chunk, timestamps per marker
  chunk), `stats`, `close`, `shutdown`. There is no command that writes to a device.
* Error types: `LoadFailed`, `IncompatiblePlugin`, `InvalidOptions`, `OpenFailed`, `LinkLost`,
  `ConfigurationChanged`, `PluginError`, `InvalidSession`, `InvalidData`, `InvalidDevices`,
  `InternalError` (with a traceback summary), `NotOpen`, `BadRequest`.

Measured on the dev container (`python scripts/bench_plugins.py`; unpaced test plugin, 64 ch ×
30 kHz float32 = 7.68 MB/s real time; machine-dependent, not asserted):

| samples per read | host IPC throughput | read round trip p50 / p95 (ms) | bit-exact | adapter (IPC + runtime validation) | adapter + normalize to events |
| --- | --- | --- | --- | --- | --- |
| 300 (10 ms) | 215 MB/s · 28.0x | 0.29 / 0.62 | yes | 24.1x | 10.0x |
| 1500 (50 ms) | 334 MB/s · 43.5x | 1.00 / 1.79 | yes | 46.2x | 13.7x |
| 6000 (200 ms) | 557 MB/s · 72.5x | 2.47 / 3.01 | yes | 70.3x | 17.4x |

The IPC is not the bottleneck; converting 30 kHz frames to JSON events is (as for every source).

## 7. Operating plugins

* REST: `GET /api/v1/plugins` (each plugin: manifest fields, options, status `compatible` /
  `rejected` / `load_error`, `reason`, `problems`, devices with their BrainOS device ids, log
  tail), `POST /api/v1/plugins/discover`, `POST /api/v1/plugins/{name}/configure`
  `{device_key, options}` → `DeviceDescriptor` (400 invalid options, 404 unknown plugin, 409
  rejected plugin, 502 open failed). Configured devices appear in `/devices`;
  `/devices/{id}/source` returns plugin, streams, counters, plugin stats and log tail;
  `DELETE /sources/{id}` removes one. Python SDK: `RuntimeClient.plugins()`,
  `discover_plugins()`, `configure_plugin(name, device_key, options)`.
* Console: source picker → **Plugins**: each installed plugin with its status or the reason it
  was rejected, its devices, an options form generated from its option specs, Connect. The
  Acquisition row then shows e.g. `Plugin · brainos-example-adapter@0.1.0 · isolated · EEG,
  noninvasive`.
* Environment: `BRAINOS_PLUGINS=0` disables discovery at startup; `BRAINOS_PLUGIN_PYTHON`
  (interpreter for hosts), `BRAINOS_PLUGIN_PATH` (extra `sys.path` entries for hosts, `:`
  separated), `BRAINOS_PLUGIN_LOG_LEVEL` (host log level, default INFO).

## 8. Step by step: create → install → see in BrainOS → test

1. **Create** a package that depends only on `brainos-adapter-sdk` (+ your libraries). Implement
   `SourcePlugin` (`manifest`, `discover`, `open`) and `SourceSession` (`info`, `read`, `close`,
   optional `stats`). Register it:
   ```toml
   [project.entry-points."brainos.sources"]
   my-device = "my_package.plugin:MyDevicePlugin"
   ```
2. **Install** into BrainOS's environment: `.venv/bin/pip install -e path/to/my-plugin`.
3. **Check** it exactly as BrainOS will run it:
   `.venv/bin/python -m brainos_adapter_sdk.host --check my-device [--device KEY] [--option k=v]`
   prints the manifest problems, devices, streams, per-stream sample rates and "OK" or the first
   violation. `--list` shows what discovery sees.
4. **See it in BrainOS**: start BrainOS (`make run`), open *Connect a source* → *Plugins* (or
   *Search again* if BrainOS was already running), set options, *Connect*.
5. **Test** in CI with `brainos_adapter_sdk.client.SyncHostClient` (runs your plugin through
   a real host with BrainOS's validation; see the example's `tests/`).
6. **Certify** with `brainos-certify my-device [--device KEY] [--option k=v]`
   (`packages/brainos-certify`, docs/CERTIFICATION.md): 29 checks — metadata, channel identity
   across reopens, timestamps, rate, jitter, loss, a killed host, throughput, CPU/RSS and, with
   BrainOS installed, negotiation and event-contract compliance — in a JSON + Markdown report
   with an explicit validation level; exit code 0 only for `adapter_implementation`. A pass is
   a software result, never hardware certification.

## 9. Compatibility

API versions are `major.minor`. A plugin declaring `api_version = "1.0"` runs on any BrainOS
whose SDK API is `1.x`; a plugin for `1.2` is refused by a `1.1` host ("update BrainOS"); a
plugin for `2.0` is refused by every `1.x` host. Additive changes bump the minor version;
anything a 1.0 plugin could observe as different bumps the major version.
