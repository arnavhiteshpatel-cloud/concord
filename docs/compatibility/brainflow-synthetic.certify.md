# Concord integration certification: concord-brainflow 0.1.0

> **SOFTWARE CERTIFICATION ONLY - this report is not hardware certification and not human-participant validation. A pass means the plugin satisfied the Concord adapter SDK contract, through the real plugin host, with the data source used in this run, on this machine. It does not show that any physical device, amplifier or implant works with Concord, and it says nothing about safety, clinical use or decoding performance. 'hardware_tested' appears only as an operator's signed attestation, which this toolkit does not verify; 'human_participant_validated' is never set by this toolkit.**

**Level achieved: `protocol_tested`** - protocol-tested against BrainFlow 5.23 BoardShim SYNTHETIC_BOARD (operator statement)  
Checks: 26 pass, 2 warn, 0 fail, 1 not run. Exit code 0.  
Plugin `brainflow`, device `synthetic`; origin `brainflow:SYNTHETIC_BOARD` (synthetic=True, prerecorded=False).  
Run 2026-11-08T07:21:47Z on Linux x86_64 (Intel(R) Xeon(R) Processor @ 2.10GHz, 4 CPUs), Python 3.12.3, adapter SDK 1.0.0 (API 1.0), Concord 0.3.0, concord-certify 0.1.0.

## Summary

| Check | Status | Reason |
| --- | --- | --- |
| `manifest.load` | PASS | plugin loaded in its own host process (pid 7443) in 0.12 s |
| `manifest.valid` | PASS | manifest valid (host and local validation) |
| `manifest.api_compat` | PASS | plugin API 1.0 runs on SDK API 1.0 (SDK 1.0.0) |
| `manifest.entry_point` | PASS | entry point brainflow = concord_brainflow.plugin:BrainFlowPlugin (concord-brainflow) |
| `manifest.distribution` | PASS | concord-brainflow 0.1.0: 9 of 9 hashed RECORD entries verified; module tree sha256 d86fdf6b946f… (editable install: RECORD covers the .pth only; source files hashed) |
| `manifest.discover` | PASS | 4 device(s) ['synthetic', 'playback', 'streaming', 'board'] in 0.00 s; testing 'synthetic' |
| `metadata.session_valid` | PASS | 2 stream(s), primary 'exg', synthetic=True prerecorded=False, opened in 0.00 s |
| `metadata.units` | WARN | 13 of 29 channel(s) declare no unit (shown as 'arbitrary'; correct when the source does not state units) |
| `metadata.modality` | WARN | modality not declared for ['exg']; invasiveness unknown for ['exg'] (shown as 'not declared'; correct when the source cannot tell) |
| `metadata.channel_identity` | PASS | 4 opens (open_1, reopen_same_host, fresh_host_after_kill, concord_runtime): identical stream ids, labels, order, units, rates (29 channels) |
| `timing.monotonic` | PASS | 12004 timestamps in 3 session(s) never decrease (within or across chunks) |
| `timing.rate` | PASS | primary 249.934453 Hz from timestamps vs nominal 250 Hz (-0.026 %, tolerance ±2 %) |
| `timing.jitter` | PASS | primary timestamp residual p50/p99/max 0.0322/0.1605/1.8446 ms; arrival interval p50/p99 3.305/5.8901 ms |
| `timing.clock_domain` | PASS | unix timestamps within 1.80 ms (median) of the wall clock (time.time); drift +0.3 ppm vs host monotonic |
| `integrity.read` | PASS | 4993 reads over 20.0 s, 10000 samples (all streams), no errors |
| `integrity.chunk_validation` | PASS | 11986 chunks validated by the host and again by the certifier |
| `integrity.sample_index` | PASS | 12004 samples in 3 session(s): 0 gaps, 0 overlaps |
| `integrity.markers` | NOT RUN | not applicable: the session declares no markers stream |
| `integrity.plugin_stats` | PASS | 7 counter(s), none reporting loss |
| `reconnect.clean_reopen` | PASS | closed in 2.8 ms, reopened in 0.002 s, first data 0.003 s after open; identity unchanged |
| `reconnect.host_killed` | PASS | SIGKILL after 124 reads surfaced as a link loss in 3.1 ms; fresh host: first data 0.134 s after start (0.007 s after open); identity unchanged; exit code 0 |
| `performance.throughput` | PASS | primary delivered 249.9363 samples/s over 20.0 s vs nominal 250 Hz (-0.025 %); 61997.4 B/s over IPC |
| `performance.latency` | PASS | newest-sample latency p50/p95/p99/max 1.7705/2.7945/3.1002/11.905 ms |
| `performance.host_resources` | PASS | host process CPU 16.7 % of one core, RSS peak 38.1 MiB (median 37.7 MiB) |
| `performance.ipc` | PASS | 61997.4 B/s, 249.64 reads/s; ping round trip p50/p99 0.1036/0.2775 ms |
| `runtime.descriptor` (optional) | PASS | descriptor kind=simulated modality=None invasive=None integration=plugin matches the declarations |
| `runtime.negotiation` (optional) | PASS | granted ['device_status', 'recording']; every other capability rejected (unsupported_by_device); command app suspended |
| `runtime.envelopes` (optional) | PASS | 1253 of 1253 events validated against contract 1.4 (pydantic + JSON Schema); 0 invalid, 0 undeclared, 0 decode errors |
| `runtime.provenance` (optional) | PASS | provenance kinds, synthetic/replayed flags, origin and model ids as declared; no command events |

## Validation levels

| Level | Achieved | Statement / what is missing |
| --- | --- | --- |
| `adapter_implementation` | yes | adapter implementation: every required automated check passed |
| `protocol_tested` | yes | protocol-tested against BrainFlow 5.23 BoardShim SYNTHETIC_BOARD (operator statement) |
| `hardware_tested` | no | no operator attestation (--attestation): hardware testing cannot be established by software and is never inferred |
| `human_participant_validated` | no | out of scope for software; never granted by concord-certify |


Protocol reference (operator statement): "BrainFlow 5.23 BoardShim SYNTHETIC_BOARD"

- `reference_given`: consistent - BrainFlow 5.23 BoardShim SYNTHETIC_BOARD
- `ecosystem_declared`: consistent - manifest.ecosystem = 'brainflow'
- `reference_names_ecosystem`: consistent - reference mentions the plugin's ecosystem 'brainflow'
- `origin_from_ecosystem`: consistent - session origin 'brainflow:SYNTHETIC_BOARD'
- `reference_version_matches_installed`: consistent - reference version 5.23, installed brainflow 5.23.0

Level definitions: docs/CERTIFICATION.md. `adapter_implementation` is the only level this toolkit grants by itself.

## Plugin identity

| | |
| --- | --- |
| Reference | brainflow |
| Entry point | brainflow |
| Manifest | concord-brainflow 0.1.0, API 1.0, ecosystem brainflow, roles ['signal'] |
| Distribution | concord-brainflow 0.1.0 (editable) |
| RECORD | 9 of 9 hashed entries verified (10 files), sha256 672de55e6644214b71cb6e13364347cf4a86fa30a3d7500c051cba3041527c40 |
| Module files | 6 files under /home/user/concord/packages/concord-brainflow/src/concord_brainflow, tree sha256 d86fdf6b946fbad2d18aabaf9540c3642144545bd84eea838063a627384b40c0 |
| Git | f8b0081d53b3642152810195ed8e2c96c3a56126 (clean) |

| Stream | Role | Channels | Rate (Hz) | Clock | Modality | Invasive | Units |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `exg` | signal | 16 | 250 | unix | None | None | microvolts |
| `aux` | signal | 13 | 250 | unix | other | None | None |

## Options

- Plugin options requested: `{}`
- Plugin options resolved by the host: `{"board": "SYNTHETIC_BOARD", "master_board": "", "serial_port": "", "mac_address": "", "ip_address": "", "ip_port": 0, "ip_protocol": "NO_IP_PROTOCOL", "serial_number": "", "file": "", "other_info": "", "timeout": 0, "stall_timeout_s": 5.0, "package_num_modulus": 256}`
- Run: duration 20.0 s, reopen 2.0 s, rate tolerance ±2 %, runtime phase on (5.0 s)

## Details

### Manifest & compatibility

**`manifest.load` - PASS** - Plugin host starts and the plugin loads  
plugin loaded in its own host process (pid 7443) in 0.12 s

<details><summary>evidence</summary>

```json
{
 "host_api_version": "1.0",
 "host_python": "3.12.3",
 "host_sdk_version": "1.0.0",
 "pid": 7443,
 "protocol": "concord.plugin-ipc/1",
 "startup_s": 0.121
}
```

</details>

**`manifest.valid` - PASS** - Manifest passes validate_manifest (host and local)  
manifest valid (host and local validation)

<details><summary>evidence</summary>

```json
{
 "host_says_compatible": true,
 "manifest": {
  "api_version": "1.0",
  "author": "Concord",
  "display_name": "BrainFlow",
  "ecosystem": "brainflow",
  "homepage": "https://brainflow.org",
  "license": "Proprietary (internal preview)",
  "name": "concord-brainflow",
  "network": true,
  "options": {
   "board": {
    "required": false,
    "type": "choice"
   },
   "file": {
    "required": false,
    "type": "str"
   },
   "ip_address": {
    "required": false,
    "type": "str"
   },
   "ip_port": {
    "required": false,
    "type": "int"
   },
   "ip_protocol": {
    "required": false,
    "type": "choice"
   },
   "mac_address": {
    "required": false,
    "type": "str"
   },
   "master_board": {
    "required": false,
    "type": "str"
   },
   "other_info": {
    "required": false,
    "type": "str"
   },
   "package_num_modulus": {
    "required": false,
    "type": "int"
   },
   "serial_number": {
    "required": false,
    "type": "str"
   },
   "serial_port": {
    "required": false,
    "type": "str"
   },
   "stall_timeout_s": {
    "required": false,
    "type": "float"
   },
   "timeout": {
    "required": false,
    "type": "int"
   }
  },
  "roles": [
   "signal"
  ],
  "version": "0.1.0"
 },
 "problems": []
}
```

</details>

**`manifest.api_compat` - PASS** - Plugin API version is compatible with the installed SDK  
plugin API 1.0 runs on SDK API 1.0 (SDK 1.0.0)

<details><summary>evidence</summary>

```json
{
 "certify_sdk_api_version": "1.0",
 "certify_sdk_version": "1.0.0",
 "host_api_version": "1.0",
 "host_sdk_version": "1.0.0",
 "plugin_api_version": "1.0"
}
```

</details>

**`manifest.entry_point` - PASS** - Registered as a concord.sources entry point  
entry point brainflow = concord_brainflow.plugin:BrainFlowPlugin (concord-brainflow)

<details><summary>evidence</summary>

```json
{
 "entry_point": {
  "count": 1,
  "group": "concord.sources",
  "name": "brainflow",
  "providers": [
   "concord-brainflow"
  ],
  "value": "concord_brainflow.plugin:BrainFlowPlugin"
 }
}
```

</details>

**`manifest.distribution` - PASS** - Installed distribution identified (name, version, hashes)  
concord-brainflow 0.1.0: 9 of 9 hashed RECORD entries verified; module tree sha256 d86fdf6b946f… (editable install: RECORD covers the .pth only; source files hashed)

<details><summary>evidence</summary>

```json
{
 "distribution": {
  "direct_url": "file:///home/user/concord/packages/concord-brainflow",
  "editable": true,
  "name": "concord-brainflow",
  "version": "0.1.0"
 },
 "git": {
  "commit": "f8b0081d53b3642152810195ed8e2c96c3a56126",
  "dirty": false,
  "dirty_files": 0
 },
 "module": {
  "file_count": 6,
  "name": "concord_brainflow.plugin",
  "path": "/home/user/concord/packages/concord-brainflow/src/concord_brainflow",
  "tree_sha256": "d86fdf6b946fbad2d18aabaf9540c3642144545bd84eea838063a627384b40c0"
 },
 "record": {
  "files": 10,
  "mismatched": [],
  "missing": [],
  "sha256": "672de55e6644214b71cb6e13364347cf4a86fa30a3d7500c051cba3041527c40",
  "unhashed": 1,
  "verified": 9
 }
}
```

</details>

**`manifest.discover` - PASS** - discover() returns valid devices, including the one tested  
4 device(s) ['synthetic', 'playback', 'streaming', 'board'] in 0.00 s; testing 'synthetic'

<details><summary>evidence</summary>

```json
{
 "devices": [
  {
   "description": "Generated test signals from BrainFlow's SYNTHETIC_BOARD (not a real device).",
   "details": {
    "board": "SYNTHETIC_BOARD",
    "brainflow": "5.23.0"
   },
   "device_key": "synthetic",
   "display_name": "BrainFlow synthetic board"
  },
  {
   "description": "Replays a file recorded with BrainFlow (PLAYBACK_FILE_BOARD). Needs options 'file' and 'master_board'.",
   "details": {
    "board": "PLAYBACK_FILE_BOARD",
    "brainflow": "5.23.0"
   },
   "device_key": "playback",
   "display_name": "BrainFlow playback file"
  },
  {
   "description": "Receives data another BrainFlow session publishes with add_streamer('streaming_board://<group>:<port>'). Needs options 'ip_address', 'ip_port' and 'master_board'.",
   "details": {
    "board": "STREAMING_BOARD",
    "brainflow": "5.23.0"
   },
   "device_key": "streaming",
   "display_name": "BrainFlow streaming board"
  },
  {
   "description": "Any board supported by BrainFlow: choose 'board' and fill the connection options BrainFlow's documentation lists for it. Not detected automatically.",
   "details": {
    "brainflow": "5.23.0"
   },
   "device_key": "board",
   "display_name": "Configure a BrainFlow board"
  }
 ],
 "discover_s": 0.001,
 "problems": [],
 "tested_device": "synthetic"
}
```

</details>

### Metadata correctness

**`metadata.session_valid` - PASS** - open() succeeds; SessionInfo passes validation  
2 stream(s), primary 'exg', synthetic=True prerecorded=False, opened in 0.00 s

<details><summary>evidence</summary>

```json
{
 "open_s": 0.004,
 "options_resolved": {
  "board": "SYNTHETIC_BOARD",
  "file": "",
  "ip_address": "",
  "ip_port": 0,
  "ip_protocol": "NO_IP_PROTOCOL",
  "mac_address": "",
  "master_board": "",
  "other_info": "",
  "package_num_modulus": 256,
  "serial_number": "",
  "serial_port": "",
  "stall_timeout_s": 5.0,
  "timeout": 0
 },
 "origin": "brainflow:SYNTHETIC_BOARD",
 "prerecorded": false,
 "primary_stream": "exg",
 "problems": [],
 "streams": [
  {
   "bin_ms": null,
   "channels": 16,
   "clock": "unix",
   "clock_description": "BrainFlow timestamp channel: UNIX time in seconds. For some boards BrainFlow stamps packages on the PC when they are received (BrainFlow docs, Data Format Description).",
   "invasive": null,
   "modality": null,
   "model_id": null,
   "nominal_rate_hz": 250.0,
   "quantity": null,
   "role": "signal",
   "stream_id": "exg",
   "units": [
    "microvolts"
   ]
  },
  {
   "bin_ms": null,
   "channels": 13,
   "clock": "unix",
   "clock_description": "BrainFlow timestamp channel: UNIX time in seconds. For some boards BrainFlow stamps packages on the PC when they are received (BrainFlow docs, Data Format Description).",
   "invasive": null,
   "modality": "other",
   "model_id": null,
   "nominal_rate_hz": 250.0,
   "quantity": null,
   "role": "signal",
   "stream_id": "aux",
   "units": [
    "None"
   ]
  }
 ],
 "synthetic": true
}
```

</details>

**`metadata.units` - WARN** - Channel units declared (unknown units are a warning)  
13 of 29 channel(s) declare no unit (shown as 'arbitrary'; correct when the source does not state units)

<details><summary>evidence</summary>

```json
{
 "notes": [],
 "streams": {
  "aux": {
   "channels": 13,
   "concord_unit": "arbitrary",
   "declared": [],
   "role": "signal",
   "unknown": 13
  },
  "exg": {
   "channels": 16,
   "concord_unit": "uV",
   "declared": [
    "microvolts"
   ],
   "role": "signal",
   "unknown": 0
  }
 },
 "unknown_channels": 13
}
```

</details>

**`metadata.modality` - WARN** - Modality / invasiveness declared and consistent  
modality not declared for ['exg']; invasiveness unknown for ['exg'] (shown as 'not declared'; correct when the source cannot tell)

<details><summary>evidence</summary>

```json
{
 "aux": {
  "invasive": null,
  "modality": "other",
  "role": "signal"
 },
 "exg": {
  "invasive": null,
  "modality": null,
  "role": "signal"
 }
}
```

</details>

**`metadata.channel_identity` - PASS** - Identical streams and channels on every open  
4 opens (open_1, reopen_same_host, fresh_host_after_kill, concord_runtime): identical stream ids, labels, order, units, rates (29 channels)

<details><summary>evidence</summary>

```json
{
 "channels": 29,
 "differences": {},
 "opens_compared": [
  "open_1",
  "reopen_same_host",
  "fresh_host_after_kill",
  "concord_runtime"
 ],
 "reference": "open_1"
}
```

</details>

### Timestamps

**`timing.monotonic` - PASS** - Timestamps never decrease  
12004 timestamps in 3 session(s) never decrease (within or across chunks)

<details><summary>evidence</summary>

```json
{
 "streams": {
  "fresh_host.aux": {
   "decreases": 0,
   "samples": 501
  },
  "fresh_host.exg": {
   "decreases": 0,
   "samples": 501
  },
  "main.aux": {
   "decreases": 0,
   "samples": 5000
  },
  "main.exg": {
   "decreases": 0,
   "samples": 5000
  },
  "reopen.aux": {
   "decreases": 0,
   "samples": 501
  },
  "reopen.exg": {
   "decreases": 0,
   "samples": 501
  }
 }
}
```

</details>

**`timing.rate` - PASS** - Rate from source timestamps matches the nominal rate  
primary 249.934453 Hz from timestamps vs nominal 250 Hz (-0.026 %, tolerance ±2 %)

<details><summary>evidence</summary>

```json
{
 "streams": {
  "aux": {
   "clock": "unix",
   "error_percent": -0.026,
   "nominal_hz": 250.0,
   "rate_hz": 249.934453,
   "rate_hz_lsq": 249.936409,
   "samples": 5000,
   "time_span_s": 20.001244
  },
  "exg": {
   "clock": "unix",
   "error_percent": -0.026,
   "nominal_hz": 250.0,
   "rate_hz": 249.934453,
   "rate_hz_lsq": 249.936409,
   "samples": 5000,
   "time_span_s": 20.001244
  }
 },
 "tolerance_percent": 2.0
}
```

</details>

**`timing.jitter` - PASS** - Timestamp and arrival jitter distribution  
primary timestamp residual p50/p99/max 0.0322/0.1605/1.8446 ms; arrival interval p50/p99 3.305/5.8901 ms

<details><summary>evidence</summary>

```json
{
 "streams": {
  "aux": {
   "arrival_interval_ms": {
    "max": 19.003,
    "mean": 4.0063,
    "min": 0.8376,
    "n": 4992,
    "p50": 3.305,
    "p95": 5.5917,
    "p99": 5.8901
   },
   "interval_error_ms": {
    "max": 1.8631,
    "mean": 0.0374,
    "min": 0.0001,
    "n": 4999,
    "p50": 0.021,
    "p95": 0.0909,
    "p99": 0.26
   },
   "residual_ms": {
    "max": 1.8446,
    "mean": 0.043,
    "min": 0.0,
    "n": 5000,
    "p50": 0.0322,
    "p95": 0.0956,
    "p99": 0.1605
   },
   "samples_per_chunk": {
    "max": 3.0,
    "mean": 1.0014,
    "min": 1.0,
    "n": 4993,
    "p50": 1.0,
    "p95": 1.0,
    "p99": 1.0
   },
   "truncated_to_samples": null
  },
  "exg": {
   "arrival_interval_ms": {
    "max": 19.003,
    "mean": 4.0063,
    "min": 0.8376,
    "n": 4992,
    "p50": 3.305,
    "p95": 5.5917,
    "p99": 5.8901
   },
   "interval_error_ms": {
    "max": 1.8631,
    "mean": 0.0374,
    "min": 0.0001,
    "n": 4999,
    "p50": 0.021,
    "p95": 0.0909,
    "p99": 0.26
   },
   "residual_ms": {
    "max": 1.8446,
    "mean": 0.043,
    "min": 0.0,
    "n": 5000,
    "p50": 0.0322,
    "p95": 0.0956,
    "p99": 0.1605
   },
   "samples_per_chunk": {
    "max": 3.0,
    "mean": 1.0014,
    "min": 1.0,
    "n": 4993,
    "p50": 1.0,
    "p95": 1.0,
    "p99": 1.0
   },
   "truncated_to_samples": null
  }
 },
 "warn_threshold_sample_periods": 1.0
}
```

</details>

**`timing.clock_domain` - PASS** - Timestamps are plausible for the declared clock domain  
unix timestamps within 1.80 ms (median) of the wall clock (time.time); drift +0.3 ppm vs host monotonic

<details><summary>evidence</summary>

```json
{
 "description": "BrainFlow timestamp channel: UNIX time in seconds. For some boards BrainFlow stamps packages on the PC when they are received (BrainFlow docs, Data Format Description).",
 "domain": "unix",
 "drift_ppm": 0.3,
 "drift_span_s": 20.0,
 "offset_newest_s": {
  "max": 0.0119,
  "mean": 0.0018,
  "min": 0.0005,
  "n": 4993,
  "p50": 0.0018,
  "p95": 0.0028,
  "p99": 0.0031
 },
 "offset_oldest_s": {
  "max": 0.0158,
  "mean": 0.0018,
  "min": 0.0005,
  "n": 4993,
  "p50": 0.0018,
  "p95": 0.0028,
  "p99": 0.0031
 },
 "reference_clock": "wall clock (time.time)"
}
```

</details>

### Packet ordering, loss & data validity

**`integrity.read` - PASS** - Session streams for the whole run without errors or hangs  
4993 reads over 20.0 s, 10000 samples (all streams), no errors

<details><summary>evidence</summary>

```json
{
 "empty_reads": 0,
 "failure": null,
 "first_data_after_s": 0.001,
 "ran_s": 20.001,
 "reads": 4993,
 "requested_s": 20.0,
 "samples": 10000
}
```

</details>

**`integrity.chunk_validation` - PASS** - Every chunk passes validation (host and local)  
11986 chunks validated by the host and again by the certifier

<details><summary>evidence</summary>

```json
{
 "chunks_validated": 11986,
 "errors": [],
 "host_notices": {},
 "warnings": []
}
```

</details>

**`integrity.sample_index` - PASS** - first_index continuity: gaps counted, no overlaps  
12004 samples in 3 session(s): 0 gaps, 0 overlaps

<details><summary>evidence</summary>

```json
{
 "gaps": 0,
 "lost_samples": 0,
 "samples": 12004,
 "streams": {
  "fresh_host.aux": {
   "first_index": 0,
   "gaps": 0,
   "loss_fraction": 0.0,
   "lost_samples": 0,
   "overlaps": 0,
   "samples": 501
  },
  "fresh_host.exg": {
   "first_index": 0,
   "gaps": 0,
   "loss_fraction": 0.0,
   "lost_samples": 0,
   "overlaps": 0,
   "samples": 501
  },
  "main.aux": {
   "first_index": 0,
   "gaps": 0,
   "loss_fraction": 0.0,
   "lost_samples": 0,
   "overlaps": 0,
   "samples": 5000
  },
  "main.exg": {
   "first_index": 0,
   "gaps": 0,
   "loss_fraction": 0.0,
   "lost_samples": 0,
   "overlaps": 0,
   "samples": 5000
  },
  "reopen.aux": {
   "first_index": 0,
   "gaps": 0,
   "loss_fraction": 0.0,
   "lost_samples": 0,
   "overlaps": 0,
   "samples": 501
  },
  "reopen.exg": {
   "first_index": 0,
   "gaps": 0,
   "loss_fraction": 0.0,
   "lost_samples": 0,
   "overlaps": 0,
   "samples": 501
  }
 }
}
```

</details>

**`integrity.markers` - NOT RUN** - Marker timestamps ordered and on the primary clock  
not applicable: the session declares no markers stream

**`integrity.plugin_stats` - PASS** - stats() returns valid integrity counters  
7 counter(s), none reporting loss

<details><summary>evidence</summary>

```json
{
 "host_counters": {
  "bytes": 1240000,
  "chunks": 9986,
  "reads": 4993,
  "samples": 10000
 },
 "invalid_stats": 0,
 "plugin_stats": {
  "chunks_emitted": 9986,
  "dropped_packets": 0,
  "marker_row_nonzero": 0,
  "package_num_repeats": 0,
  "package_num_unusable": 0,
  "samples_received": 5000,
  "timestamp_regressions": 0
 }
}
```

</details>

### Reconnection & fault injection

**`reconnect.clean_reopen` - PASS** - Clean close, reopen, data again, identity unchanged  
closed in 2.8 ms, reopened in 0.002 s, first data 0.003 s after open; identity unchanged

<details><summary>evidence</summary>

```json
{
 "close_s": 0.003,
 "failure": null,
 "first_data_after_open_s": 0.003,
 "identity_differences": [],
 "identity_unchanged": true,
 "read_s": 2.002,
 "reopen_s": 0.002,
 "samples": 1002
}
```

</details>

**`reconnect.host_killed` - PASS** - Host killed mid-stream: link loss reported, fresh open  
SIGKILL after 124 reads surfaced as a link loss in 3.1 ms; fresh host: first data 0.134 s after start (0.007 s after open); identity unchanged; exit code 0

<details><summary>evidence</summary>

```json
{
 "failure": null,
 "first_data_after_host_start_s": 0.134,
 "first_data_after_open_s": 0.007,
 "fresh_host_exit_code": 0,
 "fresh_host_start_s": 0.127,
 "identity_differences": [],
 "identity_unchanged": true,
 "kill": {
  "detect_s": 0.0031,
  "detected_as": "HostDied",
  "host_exit_code": -9,
  "killed": true,
  "message": "plugin host exited (code -9):     \"serial_number\": \"\", |     \"serial_port\": \"\", |     \"timeout\": 0 | } | [plugin brainflow pid 7443] INFO concord_brainflow.plugin: opened BrainFlow SYNTHETIC_BOARD (format SYNTHETIC_BOARD, brainflow 5.23.0)",
  "pid": 7443,
  "reads_before_kill": 124,
  "signal": "SIGKILL"
 },
 "open_s": 0.004,
 "samples": 1002
}
```

</details>

### Performance

**`performance.throughput` - PASS** - Sustained delivery rate keeps up with the nominal rate  
primary delivered 249.9363 samples/s over 20.0 s vs nominal 250 Hz (-0.025 %); 61997.4 B/s over IPC

<details><summary>evidence</summary>

```json
{
 "duration_s": 20.001,
 "ipc_bytes_per_s": 61997.4,
 "ipc_bytes_received": 1240000,
 "streams": {
  "aux": {
   "arrival_span_s": 19.999,
   "chunks": 4993,
   "error_percent": -0.025,
   "nominal_hz": 250.0,
   "rate_hz": 249.9363,
   "rate_hz_endpoints": 249.9565,
   "samples": 5000,
   "samples_per_s_overall": 249.989
  },
  "exg": {
   "arrival_span_s": 19.999,
   "chunks": 4993,
   "error_percent": -0.025,
   "nominal_hz": 250.0,
   "rate_hz": 249.9363,
   "rate_hz_endpoints": 249.9565,
   "samples": 5000,
   "samples_per_s_overall": 249.989
  }
 },
 "tolerance_percent": 2.0
}
```

</details>

**`performance.latency` - PASS** - Read latency (now - sample timestamp)  
newest-sample latency p50/p95/p99/max 1.7705/2.7945/3.1002/11.905 ms

<details><summary>evidence</summary>

```json
{
 "newest_sample_latency_ms": {
  "max": 11.905,
  "mean": 1.7836,
  "min": 0.4814,
  "n": 4993,
  "p50": 1.7705,
  "p95": 2.7945,
  "p99": 3.1002
 },
 "note": "read latency = arrival time at the certifier minus the sample's own timestamp; machine-dependent, includes the source's buffering and the plugin's read timeout",
 "oldest_sample_latency_s": {
  "max": 0.0158,
  "mean": 0.0018,
  "min": 0.0005,
  "n": 4993,
  "p50": 0.0018,
  "p95": 0.0028,
  "p99": 0.0031
 },
 "reference_clock": "wall clock (time.time)"
}
```

</details>

**`performance.host_resources` - PASS** - Plugin host process CPU and memory  
host process CPU 16.7 % of one core, RSS peak 38.1 MiB (median 37.7 MiB)

<details><summary>evidence</summary>

```json
{
 "clock_ticks_per_s": 100,
 "cpu_percent_of_one_core": 16.7,
 "cpu_s": 3.35,
 "pid": 7443,
 "rss_mib_max_sampled": 38.1,
 "rss_mib_median": 37.7,
 "rss_mib_peak": 38.1,
 "rss_samples": 80,
 "wall_s": 20.001
}
```

</details>

**`performance.ipc` - PASS** - IPC volume and round-trip time  
61997.4 B/s, 249.64 reads/s; ping round trip p50/p99 0.1036/0.2775 ms

<details><summary>evidence</summary>

```json
{
 "empty_read_fraction": 0.0,
 "host_bytes_per_s": 61997.4,
 "host_counters": {
  "bytes": 1240000,
  "chunks": 9986,
  "reads": 4993,
  "samples": 10000
 },
 "ping_round_trip_ms": {
  "max": 0.299,
  "mean": 0.1305,
  "min": 0.0996,
  "n": 30,
  "p50": 0.1036,
  "p95": 0.2132,
  "p99": 0.2775
 },
 "reads_per_s": 249.64
}
```

</details>

### Concord runtime: negotiation & event contract

**`runtime.descriptor` - PASS** - Concord device descriptor matches the declarations  
descriptor kind=simulated modality=None invasive=None integration=plugin matches the declarations

<details><summary>evidence</summary>

```json
{
 "concord": {
  "adapter": "concord-brainflow@0.1.0",
  "integration": {
   "api_version": "1.0",
   "ecosystem": "brainflow",
   "isolated": true,
   "kind": "plugin",
   "package": "concord-brainflow",
   "version": "0.1.0"
  },
  "invasive": null,
  "kind": "simulated",
  "modality": null,
  "synthetic": true
 },
 "concord_capabilities": [
  "recording",
  "device_status"
 ],
 "device_id": "plugin:brainflow:synthetic",
 "expected": {
  "capabilities": [
   "device_status",
   "recording"
  ],
  "integration": {
   "api_version": "1.0",
   "ecosystem": "brainflow",
   "isolated": true,
   "kind": "plugin",
   "package": "concord-brainflow",
   "version": "0.1.0"
  },
  "invasive": null,
  "kind": "simulated",
  "modality": null,
  "synthetic": true
 }
}
```

</details>

**`runtime.negotiation` - PASS** - Capability grants and rejections match the roles  
granted ['device_status', 'recording']; every other capability rejected (unsupported_by_device); command app suspended

<details><summary>evidence</summary>

```json
{
 "expected_granted": [
  "device_status",
  "recording"
 ],
 "negotiations": {
  "all_optional": {
   "device_id": "plugin:brainflow:synthetic",
   "granted": [
    "recording",
    "device_status",
    "control_status"
   ],
   "rejected": [
    {
     "capability": "pointer_intent",
     "reason": "unsupported_by_device",
     "required": false
    },
    {
     "capability": "selection",
     "reason": "unsupported_by_device",
     "required": false
    },
    {
     "capability": "text_intent",
     "reason": "unsupported_by_device",
     "required": false
    },
    {
     "capability": "telemetry",
     "reason": "unsupported_by_device",
     "required": false
    },
    {
     "capability": "neural_features",
     "reason": "unsupported_by_device",
     "required": false
    },
    {
     "capability": "behavior",
     "reason": "unsupported_by_device",
     "required": false
    },
    {
     "capability": "kinematic_intent",
     "reason": "unsupported_by_device",
     "required": false
    },
    {
     "capability": "navigation",
     "reason": "unsupported_by_device",
     "required": false
    }
   ],
   "status": "active"
  },
  "command_required": {
   "device_id": "plugin:brainflow:synthetic",
   "granted": [],
   "rejected": [
    {
     "capability": "pointer_intent",
     "reason": "unsupported_by_device",
     "required": true
    },
    {
     "capability": "selection",
     "reason": "unsupported_by_device",
     "required": false
    },
    {
     "capability": "text_intent",
     "reason": "unsupported_by_device",
     "required": false
    }
   ],
   "status": "suspended"
  },
  "roles_required": {
   "device_id": "plugin:brainflow:synthetic",
   "granted": [
    "device_status",
    "recording"
   ],
   "rejected": [],
   "status": "active"
  }
 }
}
```

</details>

**`runtime.envelopes` - PASS** - Every event validates against the Concord contracts  
1253 of 1253 events validated against contract 1.4 (pydantic + JSON Schema); 0 invalid, 0 undeclared, 0 decode errors

<details><summary>evidence</summary>

```json
{
 "event_schema_versions": {
  "1.4": 1253
 },
 "event_types": {
  "device.status": 3,
  "recording.frame": 1250
 },
 "events_published": 1253,
 "events_validated": 1253,
 "invalid": [],
 "runtime_diagnostics": {
  "decode_errors": 0,
  "link_errors": 0,
  "timestamp_regressions": 0,
  "undeclared_capability": 0,
  "validation_errors": 0
 },
 "runtime_last_error": null,
 "runtime_state_at_end": "streaming",
 "schema_version": "1.4",
 "seconds": 5.0
}
```

</details>

**`runtime.provenance` - PASS** - Provenance correct; nothing becomes a command  
provenance kinds, synthetic/replayed flags, origin and model ids as declared; no command events

<details><summary>evidence</summary>

```json
{
 "command_events": {},
 "declared": {
  "origin": "brainflow:SYNTHETIC_BOARD",
  "prerecorded": false,
  "synthetic": true
 },
 "decoder_model_id": null,
 "expected_provenance": {
  "recording.frame": "raw_signal"
 },
 "problems": [],
 "regular_streams_without_events": []
}
```

</details>

## Environment

```json
{
 "certify_version": "0.1.0",
 "concord_version": "0.3.0",
 "cpu_count": 4,
 "cpu_model": "Intel(R) Xeon(R) Processor @ 2.10GHz",
 "host_api_version": "1.0",
 "host_python": "3.12.3",
 "host_sdk_version": "1.0.0",
 "machine": "x86_64",
 "memory_total_mib": 16086,
 "os": "Linux",
 "os_release": "6.18.44-fc-v310",
 "platform": "Linux-6.18.44-fc-v310-x86_64-with-glibc2.39",
 "python": "3.12.3",
 "python_implementation": "CPython",
 "report_version": "1.0",
 "sdk_api_version": "1.0",
 "sdk_version": "1.0.0"
}
```
