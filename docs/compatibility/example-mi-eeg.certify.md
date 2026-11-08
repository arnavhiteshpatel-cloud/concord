# Concord integration certification: concord-example-adapter 0.1.0

> **SOFTWARE CERTIFICATION ONLY - this report is not hardware certification and not human-participant validation. A pass means the plugin satisfied the Concord adapter SDK contract, through the real plugin host, with the data source used in this run, on this machine. It does not show that any physical device, amplifier or implant works with Concord, and it says nothing about safety, clinical use or decoding performance. 'hardware_tested' appears only as an operator's signed attestation, which this toolkit does not verify; 'human_participant_validated' is never set by this toolkit.**

**Level achieved: `adapter_implementation`** - adapter implementation: every required automated check passed  
Checks: 27 pass, 1 warn, 0 fail, 1 not run. Exit code 0.  
Plugin `example-mi-eeg`, device `mi-eeg`; origin `concord-example-adapter:mi-eeg:seed=1` (synthetic=True, prerecorded=False).  
Run 2026-11-08T07:08:33Z on Linux x86_64 (Intel(R) Xeon(R) Processor @ 2.10GHz, 4 CPUs), Python 3.12.3, adapter SDK 1.0.0 (API 1.0), Concord 0.3.0, concord-certify 0.1.0.

## Summary

| Check | Status | Reason |
| --- | --- | --- |
| `manifest.load` | PASS | plugin loaded in its own host process (pid 2791) in 0.13 s |
| `manifest.valid` | PASS | manifest valid (host and local validation) |
| `manifest.api_compat` | PASS | plugin API 1.0 runs on SDK API 1.0 (SDK 1.0.0) |
| `manifest.entry_point` | PASS | entry point example-mi-eeg = concord_example_adapter.plugin:MotorImageryEEGPlugin (concord-example-adapter) |
| `manifest.distribution` | PASS | concord-example-adapter 0.1.0: 9 of 9 hashed RECORD entries verified; module tree sha256 00e2d8391de6… (editable install: RECORD covers the .pth only; source files hashed) |
| `manifest.discover` | PASS | 1 device(s) ['mi-eeg'] in 0.00 s; testing 'mi-eeg' |
| `metadata.session_valid` | PASS | 3 stream(s), primary 'eeg', synthetic=True prerecorded=False, opened in 0.01 s |
| `metadata.units` | WARN | 1 of 9 channel(s) declare no unit (shown as 'arbitrary'; correct when the source does not state units) |
| `metadata.modality` | PASS | declared and consistent: eeg=eeg/invasive=False |
| `metadata.channel_identity` | PASS | 4 opens (open_1, reopen_same_host, fresh_host_after_kill, concord_runtime): identical stream ids, labels, order, units, rates (10 channels) |
| `timing.monotonic` | PASS | 7200 timestamps in 3 session(s) never decrease (within or across chunks) |
| `timing.rate` | PASS | primary 250.0 Hz from timestamps vs nominal 250 Hz (+0.000 %, tolerance ±2 %) |
| `timing.jitter` | PASS | primary timestamp residual p50/p99/max 0.0/0.0/0.0 ms; arrival interval p50/p99 100.0225/103.0664 ms |
| `timing.clock_domain` | PASS | source clock: offset to host monotonic 0.0058 s (origin unknown by declaration; not checkable); drift +1.4 ppm vs host monotonic |
| `integrity.read` | PASS | 200 reads over 20.0 s, 6005 samples (all streams), no errors |
| `integrity.chunk_validation` | PASS | 487 chunks validated by the host and again by the certifier |
| `integrity.sample_index` | PASS | 7200 samples in 3 session(s): 0 gaps, 0 overlaps |
| `integrity.markers` | PASS | 5 marker(s) in order, within the primary stream's time span |
| `integrity.plugin_stats` | PASS | 2 counter(s), none reporting loss |
| `reconnect.clean_reopen` | PASS | closed in 0.1 ms, reopened in 0.001 s, first data 0.102 s after open; identity unchanged |
| `reconnect.host_killed` | PASS | SIGKILL after 5 reads surfaced as a link loss in 2.5 ms; fresh host: first data 0.227 s after start (0.11 s after open); identity unchanged; exit code 0 |
| `performance.throughput` | PASS | primary delivered 249.9997 samples/s over 20.0 s vs nominal 250 Hz (-0.000 %); 10601.9 B/s over IPC |
| `performance.latency` | NOT RUN | not applicable: clock domain 'source' has no known relation to a host clock (latency cannot be measured; see timing.clock_domain for the offset) |
| `performance.host_resources` | PASS | host process CPU 1.2 % of one core, RSS peak 38.3 MiB (median 38.3 MiB) |
| `performance.ipc` | PASS | 10601.9 B/s, 10.0 reads/s; ping round trip p50/p99 0.0963/0.2168 ms |
| `runtime.descriptor` (optional) | PASS | descriptor kind=simulated modality=eeg invasive=False integration=plugin matches the declarations |
| `runtime.negotiation` (optional) | PASS | granted ['behavior', 'device_status', 'recording']; every other capability rejected (unsupported_by_device); command app suspended |
| `runtime.envelopes` (optional) | PASS | 299 of 299 events validated against contract 1.4 (pydantic + JSON Schema); 0 invalid, 0 undeclared, 0 decode errors |
| `runtime.provenance` (optional) | PASS | provenance kinds, synthetic/replayed flags, origin and model ids as declared; no command events |

## Validation levels

| Level | Achieved | Statement / what is missing |
| --- | --- | --- |
| `adapter_implementation` | yes | adapter implementation: every required automated check passed |
| `protocol_tested` | no | no --protocol-reference: name the external reference software that produced the data (e.g. "BrainFlow 5.23 BoardShim SYNTHETIC_BOARD") |
| `hardware_tested` | no | no operator attestation (--attestation): hardware testing cannot be established by software and is never inferred |
| `human_participant_validated` | no | out of scope for software; never granted by concord-certify |


Level definitions: docs/CERTIFICATION.md. `adapter_implementation` is the only level this toolkit grants by itself.

## Plugin identity

| | |
| --- | --- |
| Reference | example-mi-eeg |
| Entry point | example-mi-eeg |
| Manifest | concord-example-adapter 0.1.0, API 1.0, ecosystem None, roles ['behavior', 'markers', 'signal'] |
| Distribution | concord-example-adapter 0.1.0 (editable) |
| RECORD | 9 of 9 hashed entries verified (10 files), sha256 fd71105015feb22366d1f71b312ffee2bcfdbea16231590b9a0ad9026a635afb |
| Module files | 4 files under /home/user/brainos/examples/adapters/concord-example-adapter/src/concord_example_adapter, tree sha256 00e2d8391de66cdfe4fc75d23b7cccf6f037c78a2f491bd82b19898f3272ce9a |
| Git | 0d86b8aefcf455c8503f12abfbdfd26afd13913e (dirty) |

| Stream | Role | Channels | Rate (Hz) | Clock | Modality | Invasive | Units |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `eeg` | signal | 8 | 250 | source | eeg | False | microvolts |
| `cue` | behavior | 1 | 50 | source | None | None | None |
| `markers` | markers | 1 | 0 | source | None | None | None |

## Options

- Plugin options requested: `{}`
- Plugin options resolved by the host: `{"seed": 1, "montage": "8", "cue_duration_s": 4.0, "effect_size": 0.5}`
- Run: duration 20.0 s, reopen 2.0 s, rate tolerance ±2 %, runtime phase on (5.0 s)

## Details

### Manifest & compatibility

**`manifest.load` - PASS** - Plugin host starts and the plugin loads  
plugin loaded in its own host process (pid 2791) in 0.13 s

<details><summary>evidence</summary>

```json
{
 "host_api_version": "1.0",
 "host_python": "3.12.3",
 "host_sdk_version": "1.0.0",
 "pid": 2791,
 "protocol": "concord.plugin-ipc/1",
 "startup_s": 0.133
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
  "author": "Concord developers",
  "display_name": "Example: motor-imagery EEG generator",
  "ecosystem": null,
  "homepage": "",
  "license": "Proprietary (internal preview)",
  "name": "concord-example-adapter",
  "network": false,
  "options": {
   "cue_duration_s": {
    "required": false,
    "type": "float"
   },
   "effect_size": {
    "required": false,
    "type": "float"
   },
   "montage": {
    "required": false,
    "type": "choice"
   },
   "seed": {
    "required": false,
    "type": "int"
   }
  },
  "roles": [
   "behavior",
   "markers",
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
entry point example-mi-eeg = concord_example_adapter.plugin:MotorImageryEEGPlugin (concord-example-adapter)

<details><summary>evidence</summary>

```json
{
 "entry_point": {
  "count": 1,
  "group": "concord.sources",
  "name": "example-mi-eeg",
  "providers": [
   "concord-example-adapter"
  ],
  "value": "concord_example_adapter.plugin:MotorImageryEEGPlugin"
 }
}
```

</details>

**`manifest.distribution` - PASS** - Installed distribution identified (name, version, hashes)  
concord-example-adapter 0.1.0: 9 of 9 hashed RECORD entries verified; module tree sha256 00e2d8391de6… (editable install: RECORD covers the .pth only; source files hashed)

<details><summary>evidence</summary>

```json
{
 "distribution": {
  "direct_url": "file:///home/user/brainos/examples/adapters/concord-example-adapter",
  "editable": true,
  "name": "concord-example-adapter",
  "version": "0.1.0"
 },
 "git": {
  "commit": "0d86b8aefcf455c8503f12abfbdfd26afd13913e",
  "dirty": true,
  "dirty_files": 4
 },
 "module": {
  "file_count": 4,
  "name": "concord_example_adapter.plugin",
  "path": "/home/user/brainos/examples/adapters/concord-example-adapter/src/concord_example_adapter",
  "tree_sha256": "00e2d8391de66cdfe4fc75d23b7cccf6f037c78a2f491bd82b19898f3272ce9a"
 },
 "record": {
  "files": 10,
  "mismatched": [],
  "missing": [],
  "sha256": "fd71105015feb22366d1f71b312ffee2bcfdbea16231590b9a0ad9026a635afb",
  "unhashed": 1,
  "verified": 9
 }
}
```

</details>

**`manifest.discover` - PASS** - discover() returns valid devices, including the one tested  
1 device(s) ['mi-eeg'] in 0.00 s; testing 'mi-eeg'

<details><summary>evidence</summary>

```json
{
 "devices": [
  {
   "description": "Synthetic EEG with a rest / left / right cue schedule.",
   "details": {
    "channels": "8 or 16 (10-20)",
    "rate": "250 Hz"
   },
   "device_key": "mi-eeg",
   "display_name": "Motor-imagery EEG generator"
  }
 ],
 "discover_s": 0.0,
 "problems": [],
 "tested_device": "mi-eeg"
}
```

</details>

### Metadata correctness

**`metadata.session_valid` - PASS** - open() succeeds; SessionInfo passes validation  
3 stream(s), primary 'eeg', synthetic=True prerecorded=False, opened in 0.01 s

<details><summary>evidence</summary>

```json
{
 "open_s": 0.01,
 "options_resolved": {
  "cue_duration_s": 4.0,
  "effect_size": 0.5,
  "montage": "8",
  "seed": 1
 },
 "origin": "concord-example-adapter:mi-eeg:seed=1",
 "prerecorded": false,
 "primary_stream": "eeg",
 "problems": [],
 "streams": [
  {
   "bin_ms": null,
   "channels": 8,
   "clock": "source",
   "clock_description": "generator sample clock: monotonic time at open() + sample index / 250 Hz",
   "invasive": false,
   "modality": "eeg",
   "model_id": null,
   "nominal_rate_hz": 250.0,
   "quantity": null,
   "role": "signal",
   "stream_id": "eeg",
   "units": [
    "microvolts"
   ]
  },
  {
   "bin_ms": null,
   "channels": 1,
   "clock": "source",
   "clock_description": "generator sample clock: monotonic time at open() + sample index / 250 Hz",
   "invasive": null,
   "modality": null,
   "model_id": null,
   "nominal_rate_hz": 50.0,
   "quantity": "class",
   "role": "behavior",
   "stream_id": "cue",
   "units": [
    "None"
   ]
  },
  {
   "bin_ms": null,
   "channels": 1,
   "clock": "source",
   "clock_description": "generator sample clock: monotonic time at open() + sample index / 250 Hz",
   "invasive": null,
   "modality": null,
   "model_id": null,
   "nominal_rate_hz": 0.0,
   "quantity": null,
   "role": "markers",
   "stream_id": "markers",
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
1 of 9 channel(s) declare no unit (shown as 'arbitrary'; correct when the source does not state units)

<details><summary>evidence</summary>

```json
{
 "notes": [],
 "streams": {
  "cue": {
   "channels": 1,
   "declared": [],
   "role": "behavior",
   "unknown": 1
  },
  "eeg": {
   "channels": 8,
   "concord_unit": "uV",
   "declared": [
    "microvolts"
   ],
   "role": "signal",
   "unknown": 0
  }
 },
 "unknown_channels": 1
}
```

</details>

**`metadata.modality` - PASS** - Modality / invasiveness declared and consistent  
declared and consistent: eeg=eeg/invasive=False

<details><summary>evidence</summary>

```json
{
 "eeg": {
  "invasive": false,
  "modality": "eeg",
  "role": "signal"
 }
}
```

</details>

**`metadata.channel_identity` - PASS** - Identical streams and channels on every open  
4 opens (open_1, reopen_same_host, fresh_host_after_kill, concord_runtime): identical stream ids, labels, order, units, rates (10 channels)

<details><summary>evidence</summary>

```json
{
 "channels": 10,
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
7200 timestamps in 3 session(s) never decrease (within or across chunks)

<details><summary>evidence</summary>

```json
{
 "streams": {
  "fresh_host.cue": {
   "decreases": 0,
   "samples": 100
  },
  "fresh_host.eeg": {
   "decreases": 0,
   "samples": 500
  },
  "main.cue": {
   "decreases": 0,
   "samples": 1000
  },
  "main.eeg": {
   "decreases": 0,
   "samples": 5000
  },
  "reopen.cue": {
   "decreases": 0,
   "samples": 100
  },
  "reopen.eeg": {
   "decreases": 0,
   "samples": 500
  }
 }
}
```

</details>

**`timing.rate` - PASS** - Rate from source timestamps matches the nominal rate  
primary 250.0 Hz from timestamps vs nominal 250 Hz (+0.000 %, tolerance ±2 %)

<details><summary>evidence</summary>

```json
{
 "streams": {
  "cue": {
   "clock": "source",
   "error_percent": 0.0,
   "nominal_hz": 50.0,
   "rate_hz": 50.0,
   "rate_hz_lsq": 50.0,
   "samples": 1000,
   "time_span_s": 19.98
  },
  "eeg": {
   "clock": "source",
   "error_percent": 0.0,
   "nominal_hz": 250.0,
   "rate_hz": 250.0,
   "rate_hz_lsq": 250.0,
   "samples": 5000,
   "time_span_s": 19.996
  }
 },
 "tolerance_percent": 2.0
}
```

</details>

**`timing.jitter` - PASS** - Timestamp and arrival jitter distribution  
primary timestamp residual p50/p99/max 0.0/0.0/0.0 ms; arrival interval p50/p99 100.0225/103.0664 ms

<details><summary>evidence</summary>

```json
{
 "streams": {
  "cue": {
   "arrival_interval_ms": {
    "max": 116.7546,
    "mean": 99.9985,
    "min": 83.3078,
    "n": 199,
    "p50": 100.0225,
    "p95": 100.7475,
    "p99": 103.0664
   },
   "interval_error_ms": {
    "max": 0.0,
    "mean": 0.0,
    "min": 0.0,
    "n": 999,
    "p50": 0.0,
    "p95": 0.0,
    "p99": 0.0
   },
   "residual_ms": {
    "max": 0.0,
    "mean": 0.0,
    "min": 0.0,
    "n": 1000,
    "p50": 0.0,
    "p95": 0.0,
    "p99": 0.0
   },
   "samples_per_chunk": {
    "max": 5.0,
    "mean": 5.0,
    "min": 5.0,
    "n": 200,
    "p50": 5.0,
    "p95": 5.0,
    "p99": 5.0
   },
   "truncated_to_samples": null
  },
  "eeg": {
   "arrival_interval_ms": {
    "max": 116.7546,
    "mean": 99.9985,
    "min": 83.3078,
    "n": 199,
    "p50": 100.0225,
    "p95": 100.7475,
    "p99": 103.0664
   },
   "interval_error_ms": {
    "max": 0.0,
    "mean": 0.0,
    "min": 0.0,
    "n": 4999,
    "p50": 0.0,
    "p95": 0.0,
    "p99": 0.0
   },
   "residual_ms": {
    "max": 0.0,
    "mean": 0.0,
    "min": 0.0,
    "n": 5000,
    "p50": 0.0,
    "p95": 0.0,
    "p99": 0.0
   },
   "samples_per_chunk": {
    "max": 25.0,
    "mean": 25.0,
    "min": 25.0,
    "n": 200,
    "p50": 25.0,
    "p95": 25.0,
    "p99": 25.0
   },
   "truncated_to_samples": null
  },
  "markers": {
   "arrival_interval_ms": {
    "max": 4000.1603,
    "mean": 3999.9639,
    "min": 3999.5483,
    "n": 4,
    "p50": 4000.0735,
    "p95": 4000.1535,
    "p99": 4000.1589
   },
   "residual_ms": {
    "max": 0.0,
    "mean": 0.0,
    "min": 0.0,
    "n": 5,
    "p50": 0.0,
    "p95": 0.0,
    "p99": 0.0
   },
   "samples_per_chunk": {
    "max": 1.0,
    "mean": 1.0,
    "min": 1.0,
    "n": 5,
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
source clock: offset to host monotonic 0.0058 s (origin unknown by declaration; not checkable); drift +1.4 ppm vs host monotonic

<details><summary>evidence</summary>

```json
{
 "description": "generator sample clock: monotonic time at open() + sample index / 250 Hz",
 "domain": "source",
 "drift_ppm": 1.4,
 "drift_span_s": 19.9,
 "offset_newest_s": {
  "max": 0.0224,
  "mean": 0.0059,
  "min": 0.0053,
  "n": 200,
  "p50": 0.0058,
  "p95": 0.0064,
  "p99": 0.0089
 },
 "offset_oldest_s": {
  "max": 0.1184,
  "mean": 0.1019,
  "min": 0.1013,
  "n": 200,
  "p50": 0.1018,
  "p95": 0.1024,
  "p99": 0.1049
 },
 "reference_clock": "host monotonic clock"
}
```

</details>

### Packet ordering, loss & data validity

**`integrity.read` - PASS** - Session streams for the whole run without errors or hangs  
200 reads over 20.0 s, 6005 samples (all streams), no errors

<details><summary>evidence</summary>

```json
{
 "empty_reads": 0,
 "failure": null,
 "first_data_after_s": 0.1,
 "ran_s": 20.0,
 "reads": 200,
 "requested_s": 20.0,
 "samples": 6005
}
```

</details>

**`integrity.chunk_validation` - PASS** - Every chunk passes validation (host and local)  
487 chunks validated by the host and again by the certifier

<details><summary>evidence</summary>

```json
{
 "chunks_validated": 487,
 "errors": [],
 "host_notices": {},
 "warnings": []
}
```

</details>

**`integrity.sample_index` - PASS** - first_index continuity: gaps counted, no overlaps  
7200 samples in 3 session(s): 0 gaps, 0 overlaps

<details><summary>evidence</summary>

```json
{
 "gaps": 0,
 "lost_samples": 0,
 "samples": 7200,
 "streams": {
  "fresh_host.cue": {
   "first_index": 0,
   "gaps": 0,
   "loss_fraction": 0.0,
   "lost_samples": 0,
   "overlaps": 0,
   "samples": 100
  },
  "fresh_host.eeg": {
   "first_index": 0,
   "gaps": 0,
   "loss_fraction": 0.0,
   "lost_samples": 0,
   "overlaps": 0,
   "samples": 500
  },
  "main.cue": {
   "first_index": 0,
   "gaps": 0,
   "loss_fraction": 0.0,
   "lost_samples": 0,
   "overlaps": 0,
   "samples": 1000
  },
  "main.eeg": {
   "first_index": 0,
   "gaps": 0,
   "loss_fraction": 0.0,
   "lost_samples": 0,
   "overlaps": 0,
   "samples": 5000
  },
  "reopen.cue": {
   "first_index": 0,
   "gaps": 0,
   "loss_fraction": 0.0,
   "lost_samples": 0,
   "overlaps": 0,
   "samples": 100
  },
  "reopen.eeg": {
   "first_index": 0,
   "gaps": 0,
   "loss_fraction": 0.0,
   "lost_samples": 0,
   "overlaps": 0,
   "samples": 500
  }
 }
}
```

</details>

**`integrity.markers` - PASS** - Marker timestamps ordered and on the primary clock  
5 marker(s) in order, within the primary stream's time span

<details><summary>evidence</summary>

```json
{
 "primary_span": [
  1177.926273383,
  1197.9222733830002
 ],
 "streams": {
  "fresh_host.markers": {
   "decreases": 0,
   "markers": 1
  },
  "main.markers": {
   "decreases": 0,
   "markers": 5,
   "outside_primary_span": 0
  },
  "reopen.markers": {
   "decreases": 0,
   "markers": 1
  }
 }
}
```

</details>

**`integrity.plugin_stats` - PASS** - stats() returns valid integrity counters  
2 counter(s), none reporting loss

<details><summary>evidence</summary>

```json
{
 "host_counters": {
  "bytes": 212040,
  "chunks": 405,
  "reads": 200,
  "samples": 6005
 },
 "invalid_stats": 0,
 "plugin_stats": {
  "catch_up_reads": 0,
  "samples": 5000
 }
}
```

</details>

### Reconnection & fault injection

**`reconnect.clean_reopen` - PASS** - Clean close, reopen, data again, identity unchanged  
closed in 0.1 ms, reopened in 0.001 s, first data 0.102 s after open; identity unchanged

<details><summary>evidence</summary>

```json
{
 "close_s": 0.0,
 "failure": null,
 "first_data_after_open_s": 0.102,
 "identity_differences": [],
 "identity_unchanged": true,
 "read_s": 2.001,
 "reopen_s": 0.001,
 "samples": 601
}
```

</details>

**`reconnect.host_killed` - PASS** - Host killed mid-stream: link loss reported, fresh open  
SIGKILL after 5 reads surfaced as a link loss in 2.5 ms; fresh host: first data 0.227 s after start (0.11 s after open); identity unchanged; exit code 0

<details><summary>evidence</summary>

```json
{
 "failure": null,
 "first_data_after_host_start_s": 0.227,
 "first_data_after_open_s": 0.11,
 "fresh_host_exit_code": 0,
 "fresh_host_start_s": 0.117,
 "identity_differences": [],
 "identity_unchanged": true,
 "kill": {
  "detect_s": 0.0025,
  "detected_as": "HostDied",
  "host_exit_code": -9,
  "killed": true,
  "message": "plugin host exited (code -9)",
  "pid": 2791,
  "reads_before_kill": 5,
  "signal": "SIGKILL"
 },
 "open_s": 0.009,
 "samples": 601
}
```

</details>

### Performance

**`performance.throughput` - PASS** - Sustained delivery rate keeps up with the nominal rate  
primary delivered 249.9997 samples/s over 20.0 s vs nominal 250 Hz (-0.000 %); 10601.9 B/s over IPC

<details><summary>evidence</summary>

```json
{
 "duration_s": 20.0,
 "ipc_bytes_per_s": 10601.9,
 "ipc_bytes_received": 212040,
 "streams": {
  "cue": {
   "arrival_span_s": 19.9,
   "chunks": 200,
   "error_percent": -0.0,
   "nominal_hz": 50.0,
   "rate_hz": 49.9999,
   "rate_hz_endpoints": 50.0008,
   "samples": 1000,
   "samples_per_s_overall": 50.0
  },
  "eeg": {
   "arrival_span_s": 19.9,
   "chunks": 200,
   "error_percent": -0.0,
   "nominal_hz": 250.0,
   "rate_hz": 249.9997,
   "rate_hz_endpoints": 250.0038,
   "samples": 5000,
   "samples_per_s_overall": 249.998
  },
  "markers": {
   "chunks": 5,
   "nominal_hz": 0.0,
   "samples": 5,
   "samples_per_s_overall": 0.25
  }
 },
 "tolerance_percent": 2.0
}
```

</details>

**`performance.latency` - NOT RUN** - Read latency (now - sample timestamp)  
not applicable: clock domain 'source' has no known relation to a host clock (latency cannot be measured; see timing.clock_domain for the offset)

**`performance.host_resources` - PASS** - Plugin host process CPU and memory  
host process CPU 1.2 % of one core, RSS peak 38.3 MiB (median 38.3 MiB)

<details><summary>evidence</summary>

```json
{
 "clock_ticks_per_s": 100,
 "cpu_percent_of_one_core": 1.2,
 "cpu_s": 0.24,
 "pid": 2791,
 "rss_mib_max_sampled": 38.3,
 "rss_mib_median": 38.3,
 "rss_mib_peak": 38.3,
 "rss_samples": 80,
 "wall_s": 20.001
}
```

</details>

**`performance.ipc` - PASS** - IPC volume and round-trip time  
10601.9 B/s, 10.0 reads/s; ping round trip p50/p99 0.0963/0.2168 ms

<details><summary>evidence</summary>

```json
{
 "empty_read_fraction": 0.0,
 "host_bytes_per_s": 10601.9,
 "host_counters": {
  "bytes": 212040,
  "chunks": 405,
  "reads": 200,
  "samples": 6005
 },
 "ping_round_trip_ms": {
  "max": 0.2211,
  "mean": 0.1137,
  "min": 0.0842,
  "n": 30,
  "p50": 0.0963,
  "p95": 0.1989,
  "p99": 0.2168
 },
 "reads_per_s": 10.0
}
```

</details>

### Concord runtime: negotiation & event contract

**`runtime.descriptor` - PASS** - Concord device descriptor matches the declarations  
descriptor kind=simulated modality=eeg invasive=False integration=plugin matches the declarations

<details><summary>evidence</summary>

```json
{
 "concord": {
  "adapter": "concord-example-adapter@0.1.0",
  "integration": {
   "api_version": "1.0",
   "ecosystem": null,
   "isolated": true,
   "kind": "plugin",
   "package": "concord-example-adapter",
   "version": "0.1.0"
  },
  "invasive": false,
  "kind": "simulated",
  "modality": "eeg",
  "synthetic": true
 },
 "concord_capabilities": [
  "recording",
  "behavior",
  "device_status"
 ],
 "device_id": "plugin:example-mi-eeg:mi-eeg",
 "expected": {
  "capabilities": [
   "behavior",
   "device_status",
   "recording"
  ],
  "integration": {
   "api_version": "1.0",
   "ecosystem": null,
   "isolated": true,
   "kind": "plugin",
   "package": "concord-example-adapter",
   "version": "0.1.0"
  },
  "invasive": false,
  "kind": "simulated",
  "modality": "eeg",
  "synthetic": true
 }
}
```

</details>

**`runtime.negotiation` - PASS** - Capability grants and rejections match the roles  
granted ['behavior', 'device_status', 'recording']; every other capability rejected (unsupported_by_device); command app suspended

<details><summary>evidence</summary>

```json
{
 "expected_granted": [
  "behavior",
  "device_status",
  "recording"
 ],
 "negotiations": {
  "all_optional": {
   "device_id": "plugin:example-mi-eeg:mi-eeg",
   "granted": [
    "recording",
    "device_status",
    "behavior",
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
   "device_id": "plugin:example-mi-eeg:mi-eeg",
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
   "device_id": "plugin:example-mi-eeg:mi-eeg",
   "granted": [
    "behavior",
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
299 of 299 events validated against contract 1.4 (pydantic + JSON Schema); 0 invalid, 0 undeclared, 0 decode errors

<details><summary>evidence</summary>

```json
{
 "event_schema_versions": {
  "1.4": 299
 },
 "event_types": {
  "behavior.sample": 245,
  "device.status": 3,
  "recording.annotation": 2,
  "recording.frame": 49
 },
 "events_published": 299,
 "events_validated": 299,
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
  "origin": "concord-example-adapter:mi-eeg:seed=1",
  "prerecorded": false,
  "synthetic": true
 },
 "decoder_model_id": null,
 "expected_provenance": {
  "behavior.sample": "behavioral_label",
  "recording.annotation": "behavioral_label",
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
