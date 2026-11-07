# BrainOS integration certification: brainos-bci2000 0.1.0

> **SOFTWARE CERTIFICATION ONLY - this report is not hardware certification and not human-participant validation. A pass means the plugin satisfied the BrainOS adapter SDK contract, through the real plugin host, with the data source used in this run, on this machine. It does not show that any physical device, amplifier or implant works with BrainOS, and it says nothing about safety, clinical use or decoding performance. 'hardware_tested' appears only as an operator's signed attestation, which this toolkit does not verify; 'human_participant_validated' is never set by this toolkit.**

**Level achieved: `adapter_implementation`** - adapter implementation: every required automated check passed  
Checks: 26 pass, 2 warn, 0 fail, 1 not run. Exit code 0.  
Plugin `bci2000`, device `app-connector`; origin `bci2000:127.0.0.1:20321 (processed control information, not raw signal)` (synthetic=True, prerecorded=True).  
Run 2026-11-07T20:48:58Z on Linux x86_64 (Intel(R) Xeon(R) Processor @ 2.10GHz, 4 CPUs), Python 3.12.3, adapter SDK 1.0.0 (API 1.0), BrainOS 0.3.0, brainos-certify 0.1.0.

## Summary

| Check | Status | Reason |
| --- | --- | --- |
| `manifest.load` | PASS | plugin loaded in its own host process (pid 32642) in 0.11 s |
| `manifest.valid` | PASS | manifest valid (host and local validation) |
| `manifest.api_compat` | PASS | plugin API 1.0 runs on SDK API 1.0 (SDK 1.0.0) |
| `manifest.entry_point` | PASS | entry point bci2000 = brainos_bci2000.plugin:BCI2000AppConnectorPlugin (brainos-bci2000) |
| `manifest.distribution` | PASS | brainos-bci2000 0.1.0: 9 of 9 hashed RECORD entries verified; module tree sha256 cc1a0ded75fc… (editable install: RECORD covers the .pth only; source files hashed) |
| `manifest.discover` | PASS | 1 device(s) ['app-connector'] in 0.00 s; testing 'app-connector' |
| `metadata.session_valid` | WARN | session.synthetic_and_prerecorded: both synthetic and prerecorded are set; BrainOS treats the source as synthetic |
| `metadata.units` | WARN | 19 of 19 channel(s) declare no unit (shown as 'arbitrary'; correct when the source does not state units) |
| `metadata.modality` | PASS | no signal / spike-count stream: modality not applicable (BrainOS shows 'modality not declared') |
| `metadata.channel_identity` | PASS | 4 opens (open_1, reopen_same_host, fresh_host_after_kill, brainos_runtime): identical stream ids, labels, order, units, rates (20 channels) |
| `timing.monotonic` | PASS | 1560 timestamps in 3 session(s) never decrease (within or across chunks) |
| `timing.rate` | PASS | primary 32.012347 Hz from timestamps vs nominal 32 Hz (+0.039 %, tolerance ±2 %) |
| `timing.jitter` | PASS | primary timestamp residual p50/p99/max 0.2798/2.8644/2.8758 ms; arrival interval p50/p99 31.233/37.367 ms |
| `timing.clock_domain` | PASS | source clock: offset to host monotonic 6520 s (origin unknown by declaration; not checkable); drift -21.4 ppm vs host monotonic |
| `integrity.read` | PASS | 642 reads over 20.0 s, 1346 samples (all streams), no errors |
| `integrity.chunk_validation` | PASS | 1594 chunks validated by the host and again by the certifier |
| `integrity.sample_index` | PASS | 1560 samples in 3 session(s): 0 gaps, 0 overlaps |
| `integrity.markers` | PASS | 58 marker(s) in order, within the primary stream's time span |
| `integrity.plugin_stats` | PASS | 11 counter(s), none reporting loss |
| `reconnect.clean_reopen` | PASS | closed in 0.2 ms, reopened in 0.119 s, first data 0.120 s after open; identity unchanged |
| `reconnect.host_killed` | PASS | SIGKILL after 16 reads surfaced as a link loss in 3.3 ms; fresh host: first data 0.217 s after start (0.105 s after open); identity unchanged; exit code 0 |
| `performance.throughput` | PASS | primary delivered 32.0122 samples/s over 20.0 s vs nominal 32 Hz (+0.038 %); 5426.6 B/s over IPC |
| `performance.latency` | NOT RUN | not applicable: clock domain 'source' has no known relation to a host clock (latency cannot be measured; see timing.clock_domain for the offset) |
| `performance.host_resources` | PASS | host process CPU 1.8 % of one core, RSS peak 31.1 MiB (median 31.1 MiB) |
| `performance.ipc` | PASS | 5426.6 B/s, 32.06 reads/s; ping round trip p50/p99 0.161/0.2838 ms |
| `runtime.descriptor` (optional) | PASS | descriptor kind=simulated modality=None invasive=None integration=plugin matches the declarations |
| `runtime.negotiation` (optional) | PASS | granted ['behavior', 'device_status', 'kinematic_intent', 'recording']; every other capability rejected (unsupported_by_device); command app suspended |
| `runtime.envelopes` (optional) | PASS | 343 of 343 events validated against contract 1.3 (pydantic + JSON Schema); 0 invalid, 0 undeclared, 0 decode errors |
| `runtime.provenance` (optional) | PASS | provenance kinds, synthetic/replayed flags, origin and model ids as declared; no command events |

## Validation levels

| Level | Achieved | Statement / what is missing |
| --- | --- | --- |
| `adapter_implementation` | yes | adapter implementation: every required automated check passed |
| `protocol_tested` | no | no --protocol-reference: name the external reference software that produced the data (e.g. "BrainFlow 5.23 BoardShim SYNTHETIC_BOARD") |
| `hardware_tested` | no | no operator attestation (--attestation): hardware testing cannot be established by software and is never inferred |
| `human_participant_validated` | no | out of scope for software; never granted by brainos-certify |


Level definitions: docs/CERTIFICATION.md. `adapter_implementation` is the only level this toolkit grants by itself.

## Plugin identity

| | |
| --- | --- |
| Reference | bci2000 |
| Entry point | bci2000 |
| Manifest | brainos-bci2000 0.1.0, API 1.0, ecosystem bci2000, roles ['behavior', 'decoder_output', 'markers'] |
| Distribution | brainos-bci2000 0.1.0 (editable) |
| RECORD | 9 of 9 hashed entries verified (10 files), sha256 da18e433519458dba84221bbd7b51bf2bbd78e105a3c2f2e743b5d5767ec4a4a |
| Module files | 5 files under /home/user/brainos/.claude/worktrees/agent-a3b411a3fd094ba1c/packages/brainos-bci2000/src/brainos_bci2000, tree sha256 cc1a0ded75fc5b89f336ae251b9c1c8f19fd002bb4ad2a09cca95618cd6e5bd0 |
| Git | ef626ac26d6c59210dfb645964148d41f6ca31b1 (clean) |

| Stream | Role | Channels | Rate (Hz) | Clock | Modality | Invasive | Units |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `control_signal` | decoder_output | 16 | 32 | source | None | None | None |
| `states` | behavior | 3 | 32 | source | None | None | None |
| `state_changes` | markers | 1 | 0 | source | None | None | None |

## Options

- Plugin options requested: `{"port": "20321", "sampling_rate_hz": "256", "sample_block_size": "8", "declare_synthetic": "true", "declare_prerecorded": "true"}`
- Plugin options resolved by the host: `{"address": "127.0.0.1", "port": 20321, "behavior_states": "auto", "marker_states": "auto", "sampling_rate_hz": 256.0, "sample_block_size": 8, "clock": "auto", "open_timeout_s": 10.0, "declare_synthetic": true, "declare_prerecorded": true}`
- Run: duration 20.0 s, reopen 2.0 s, rate tolerance ±2 %, runtime phase on (5.0 s)

## Details

### Manifest & compatibility

**`manifest.load` - PASS** - Plugin host starts and the plugin loads  
plugin loaded in its own host process (pid 32642) in 0.11 s

<details><summary>evidence</summary>

```json
{
 "host_api_version": "1.0",
 "host_python": "3.12.3",
 "host_sdk_version": "1.0.0",
 "pid": 32642,
 "protocol": "brainos.plugin-ipc/1",
 "startup_s": 0.112
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
  "author": "BrainOS",
  "display_name": "BCI2000 App Connector",
  "ecosystem": "bci2000",
  "homepage": "https://www.bci2000.org",
  "license": "Proprietary (internal preview)",
  "name": "brainos-bci2000",
  "network": true,
  "options": {
   "address": {
    "required": false,
    "type": "str"
   },
   "behavior_states": {
    "required": false,
    "type": "str"
   },
   "clock": {
    "required": false,
    "type": "choice"
   },
   "declare_prerecorded": {
    "required": false,
    "type": "bool"
   },
   "declare_synthetic": {
    "required": false,
    "type": "bool"
   },
   "marker_states": {
    "required": false,
    "type": "str"
   },
   "open_timeout_s": {
    "required": false,
    "type": "float"
   },
   "port": {
    "required": false,
    "type": "int"
   },
   "sample_block_size": {
    "required": false,
    "type": "int"
   },
   "sampling_rate_hz": {
    "required": false,
    "type": "float"
   }
  },
  "roles": [
   "behavior",
   "decoder_output",
   "markers"
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

**`manifest.entry_point` - PASS** - Registered as a brainos.sources entry point  
entry point bci2000 = brainos_bci2000.plugin:BCI2000AppConnectorPlugin (brainos-bci2000)

<details><summary>evidence</summary>

```json
{
 "entry_point": {
  "count": 1,
  "group": "brainos.sources",
  "name": "bci2000",
  "providers": [
   "brainos-bci2000"
  ],
  "value": "brainos_bci2000.plugin:BCI2000AppConnectorPlugin"
 }
}
```

</details>

**`manifest.distribution` - PASS** - Installed distribution identified (name, version, hashes)  
brainos-bci2000 0.1.0: 9 of 9 hashed RECORD entries verified; module tree sha256 cc1a0ded75fc… (editable install: RECORD covers the .pth only; source files hashed)

<details><summary>evidence</summary>

```json
{
 "distribution": {
  "direct_url": "file:///home/user/brainos/.claude/worktrees/agent-a3b411a3fd094ba1c/packages/brainos-bci2000",
  "editable": true,
  "name": "brainos-bci2000",
  "version": "0.1.0"
 },
 "git": {
  "commit": "ef626ac26d6c59210dfb645964148d41f6ca31b1",
  "dirty": false,
  "dirty_files": 0
 },
 "module": {
  "file_count": 5,
  "name": "brainos_bci2000.plugin",
  "path": "/home/user/brainos/.claude/worktrees/agent-a3b411a3fd094ba1c/packages/brainos-bci2000/src/brainos_bci2000",
  "tree_sha256": "cc1a0ded75fc5b89f336ae251b9c1c8f19fd002bb4ad2a09cca95618cd6e5bd0"
 },
 "record": {
  "files": 10,
  "mismatched": [],
  "missing": [],
  "sha256": "da18e433519458dba84221bbd7b51bf2bbd78e105a3c2f2e743b5d5767ec4a4a",
  "unhashed": 1,
  "verified": 9
 }
}
```

</details>

**`manifest.discover` - PASS** - discover() returns valid devices, including the one tested  
1 device(s) ['app-connector'] in 0.00 s; testing 'app-connector'

<details><summary>evidence</summary>

```json
{
 "devices": [
  {
   "description": "Receives BCI2000 ConnectorOutput datagrams (processed control information, not raw signal). Set BCI2000's ConnectorOutputAddress to this plugin's address and port.",
   "details": {
    "default_address": "127.0.0.1:20321"
   },
   "device_key": "app-connector",
   "display_name": "BCI2000 App Connector (UDP)"
  }
 ],
 "discover_s": 0.0,
 "problems": [],
 "tested_device": "app-connector"
}
```

</details>

### Metadata correctness

**`metadata.session_valid` - WARN** - open() succeeds; SessionInfo passes validation  
session.synthetic_and_prerecorded: both synthetic and prerecorded are set; BrainOS treats the source as synthetic

<details><summary>evidence</summary>

```json
{
 "open_s": 0.115,
 "options_resolved": {
  "address": "127.0.0.1",
  "behavior_states": "auto",
  "clock": "auto",
  "declare_prerecorded": true,
  "declare_synthetic": true,
  "marker_states": "auto",
  "open_timeout_s": 10.0,
  "port": 20321,
  "sample_block_size": 8,
  "sampling_rate_hz": 256.0
 },
 "origin": "bci2000:127.0.0.1:20321 (processed control information, not raw signal)",
 "prerecorded": true,
 "primary_stream": "control_signal",
 "problems": [
  {
   "code": "session.synthetic_and_prerecorded",
   "message": "both synthetic and prerecorded are set; BrainOS treats the source as synthetic",
   "severity": "warning",
   "where": ""
  }
 ],
 "streams": [
  {
   "bin_ms": null,
   "channels": 16,
   "clock": "source",
   "clock_description": "BCI2000 SourceTime state (16-bit millisecond counter of BCI2000's monotonic clock at block acquisition), unwrapped; arbitrary origin.",
   "invasive": null,
   "modality": null,
   "model_id": "bci2000-control-signal",
   "nominal_rate_hz": 32.0,
   "quantity": "control_signal",
   "role": "decoder_output",
   "stream_id": "control_signal",
   "units": [
    "None"
   ]
  },
  {
   "bin_ms": null,
   "channels": 3,
   "clock": "source",
   "clock_description": "BCI2000 SourceTime state (16-bit millisecond counter of BCI2000's monotonic clock at block acquisition), unwrapped; arbitrary origin.",
   "invasive": null,
   "modality": null,
   "model_id": null,
   "nominal_rate_hz": 32.0,
   "quantity": "bci2000_state",
   "role": "behavior",
   "stream_id": "states",
   "units": [
    "None"
   ]
  },
  {
   "bin_ms": null,
   "channels": 1,
   "clock": "source",
   "clock_description": "BCI2000 SourceTime state (16-bit millisecond counter of BCI2000's monotonic clock at block acquisition), unwrapped; arbitrary origin.",
   "invasive": null,
   "modality": null,
   "model_id": null,
   "nominal_rate_hz": 0.0,
   "quantity": null,
   "role": "markers",
   "stream_id": "state_changes",
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
19 of 19 channel(s) declare no unit (shown as 'arbitrary'; correct when the source does not state units)

<details><summary>evidence</summary>

```json
{
 "notes": [],
 "streams": {
  "control_signal": {
   "channels": 16,
   "declared": [],
   "role": "decoder_output",
   "unknown": 16
  },
  "states": {
   "channels": 3,
   "declared": [],
   "role": "behavior",
   "unknown": 3
  }
 },
 "unknown_channels": 19
}
```

</details>

**`metadata.modality` - PASS** - Modality / invasiveness declared and consistent  
no signal / spike-count stream: modality not applicable (BrainOS shows 'modality not declared')

**`metadata.channel_identity` - PASS** - Identical streams and channels on every open  
4 opens (open_1, reopen_same_host, fresh_host_after_kill, brainos_runtime): identical stream ids, labels, order, units, rates (20 channels)

<details><summary>evidence</summary>

```json
{
 "channels": 20,
 "differences": {},
 "opens_compared": [
  "open_1",
  "reopen_same_host",
  "fresh_host_after_kill",
  "brainos_runtime"
 ],
 "reference": "open_1"
}
```

</details>

### Timestamps

**`timing.monotonic` - PASS** - Timestamps never decrease  
1560 timestamps in 3 session(s) never decrease (within or across chunks)

<details><summary>evidence</summary>

```json
{
 "streams": {
  "fresh_host.control_signal": {
   "decreases": 0,
   "samples": 68
  },
  "fresh_host.states": {
   "decreases": 0,
   "samples": 68
  },
  "main.control_signal": {
   "decreases": 0,
   "samples": 644
  },
  "main.states": {
   "decreases": 0,
   "samples": 644
  },
  "reopen.control_signal": {
   "decreases": 0,
   "samples": 68
  },
  "reopen.states": {
   "decreases": 0,
   "samples": 68
  }
 }
}
```

</details>

**`timing.rate` - PASS** - Rate from source timestamps matches the nominal rate  
primary 32.012347 Hz from timestamps vs nominal 32 Hz (+0.039 %, tolerance ±2 %)

<details><summary>evidence</summary>

```json
{
 "streams": {
  "control_signal": {
   "clock": "source",
   "error_percent": 0.039,
   "nominal_hz": 32.0,
   "rate_hz": 32.012347,
   "rate_hz_lsq": 32.011494,
   "samples": 644,
   "time_span_s": 20.086
  },
  "states": {
   "clock": "source",
   "error_percent": 0.039,
   "nominal_hz": 32.0,
   "rate_hz": 32.012347,
   "rate_hz_lsq": 32.011494,
   "samples": 644,
   "time_span_s": 20.086
  }
 },
 "tolerance_percent": 2.0
}
```

</details>

**`timing.jitter` - PASS** - Timestamp and arrival jitter distribution  
primary timestamp residual p50/p99/max 0.2798/2.8644/2.8758 ms; arrival interval p50/p99 31.233/37.367 ms

<details><summary>evidence</summary>

```json
{
 "streams": {
  "control_signal": {
   "arrival_interval_ms": {
    "max": 37.6669,
    "mean": 31.2349,
    "min": 24.2751,
    "n": 641,
    "p50": 31.233,
    "p95": 31.9526,
    "p99": 37.367
   },
   "interval_error_ms": {
    "max": 3.25,
    "mean": 0.446,
    "min": 0.25,
    "n": 643,
    "p50": 0.25,
    "p95": 0.75,
    "p99": 3.25
   },
   "residual_ms": {
    "max": 2.8758,
    "mean": 0.3429,
    "min": 0.0002,
    "n": 644,
    "p50": 0.2798,
    "p95": 0.7429,
    "p99": 2.8644
   },
   "samples_per_chunk": {
    "max": 2.0,
    "mean": 1.0031,
    "min": 1.0,
    "n": 642,
    "p50": 1.0,
    "p95": 1.0,
    "p99": 1.0
   },
   "truncated_to_samples": null
  },
  "state_changes": {
   "arrival_interval_ms": {
    "max": 587.1249,
    "mean": 522.7809,
    "min": 499.7215,
    "n": 37,
    "p50": 505.7616,
    "p95": 586.8924,
    "p99": 587.0788
   },
   "residual_ms": {
    "max": 367.4294,
    "mean": 192.9948,
    "min": 1.3687,
    "n": 58,
    "p50": 198.7371,
    "p95": 360.002,
    "p99": 365.4785
   },
   "samples_per_chunk": {
    "max": 3.0,
    "mean": 1.5263,
    "min": 1.0,
    "n": 38,
    "p50": 1.0,
    "p95": 3.0,
    "p99": 3.0
   },
   "truncated_to_samples": null
  },
  "states": {
   "arrival_interval_ms": {
    "max": 37.6669,
    "mean": 31.2349,
    "min": 24.2751,
    "n": 641,
    "p50": 31.233,
    "p95": 31.9526,
    "p99": 37.367
   },
   "interval_error_ms": {
    "max": 3.25,
    "mean": 0.446,
    "min": 0.25,
    "n": 643,
    "p50": 0.25,
    "p95": 0.75,
    "p99": 3.25
   },
   "residual_ms": {
    "max": 2.8758,
    "mean": 0.3429,
    "min": 0.0002,
    "n": 644,
    "p50": 0.2798,
    "p95": 0.7429,
    "p99": 2.8644
   },
   "samples_per_chunk": {
    "max": 2.0,
    "mean": 1.0031,
    "min": 1.0,
    "n": 642,
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
source clock: offset to host monotonic 6520 s (origin unknown by declaration; not checkable); drift -21.4 ppm vs host monotonic

<details><summary>evidence</summary>

```json
{
 "description": "BCI2000 SourceTime state (16-bit millisecond counter of BCI2000's monotonic clock at block acquisition), unwrapped; arbitrary origin.",
 "domain": "source",
 "drift_ppm": -21.4,
 "drift_span_s": 20.02,
 "offset_newest_s": {
  "max": 6519.7469,
  "mean": 6519.7135,
  "min": 6519.7124,
  "n": 642,
  "p50": 6519.7133,
  "p95": 6519.7141,
  "p99": 6519.7199
 },
 "offset_oldest_s": {
  "max": 6519.7779,
  "mean": 6519.7136,
  "min": 6519.7124,
  "n": 642,
  "p50": 6519.7133,
  "p95": 6519.7142,
  "p99": 6519.7199
 },
 "reference_clock": "host monotonic clock"
}
```

</details>

### Packet ordering, loss & data validity

**`integrity.read` - PASS** - Session streams for the whole run without errors or hangs  
642 reads over 20.0 s, 1346 samples (all streams), no errors

<details><summary>evidence</summary>

```json
{
 "empty_reads": 0,
 "failure": null,
 "first_data_after_s": 0.001,
 "ran_s": 20.023,
 "reads": 642,
 "requested_s": 20.0,
 "samples": 1346
}
```

</details>

**`integrity.chunk_validation` - PASS** - Every chunk passes validation (host and local)  
1594 chunks validated by the host and again by the certifier

<details><summary>evidence</summary>

```json
{
 "chunks_validated": 1594,
 "errors": [],
 "host_notices": {},
 "warnings": []
}
```

</details>

**`integrity.sample_index` - PASS** - first_index continuity: gaps counted, no overlaps  
1560 samples in 3 session(s): 0 gaps, 0 overlaps

<details><summary>evidence</summary>

```json
{
 "gaps": 0,
 "lost_samples": 0,
 "samples": 1560,
 "streams": {
  "fresh_host.control_signal": {
   "first_index": 0,
   "gaps": 0,
   "loss_fraction": 0.0,
   "lost_samples": 0,
   "overlaps": 0,
   "samples": 68
  },
  "fresh_host.states": {
   "first_index": 0,
   "gaps": 0,
   "loss_fraction": 0.0,
   "lost_samples": 0,
   "overlaps": 0,
   "samples": 68
  },
  "main.control_signal": {
   "first_index": 0,
   "gaps": 0,
   "loss_fraction": 0.0,
   "lost_samples": 0,
   "overlaps": 0,
   "samples": 644
  },
  "main.states": {
   "first_index": 0,
   "gaps": 0,
   "loss_fraction": 0.0,
   "lost_samples": 0,
   "overlaps": 0,
   "samples": 644
  },
  "reopen.control_signal": {
   "first_index": 0,
   "gaps": 0,
   "loss_fraction": 0.0,
   "lost_samples": 0,
   "overlaps": 0,
   "samples": 68
  },
  "reopen.states": {
   "first_index": 0,
   "gaps": 0,
   "loss_fraction": 0.0,
   "lost_samples": 0,
   "overlaps": 0,
   "samples": 68
  }
 }
}
```

</details>

**`integrity.markers` - PASS** - Marker timestamps ordered and on the primary clock  
58 marker(s) in order, within the primary stream's time span

<details><summary>evidence</summary>

```json
{
 "primary_span": [
  51.156,
  71.242
 ],
 "streams": {
  "fresh_host.state_changes": {
   "decreases": 0,
   "markers": 6
  },
  "main.state_changes": {
   "decreases": 0,
   "markers": 58,
   "outside_primary_span": 0
  },
  "reopen.state_changes": {
   "decreases": 0,
   "markers": 6
  }
 }
}
```

</details>

**`integrity.plugin_stats` - PASS** - stats() returns valid integrity counters  
11 counter(s), none reporting loss

<details><summary>evidence</summary>

```json
{
 "host_counters": {
  "bytes": 108656,
  "chunks": 1322,
  "reads": 642,
  "samples": 1346
 },
 "invalid_stats": 0,
 "plugin_stats": {
  "blocks": 644,
  "datagrams": 19350,
  "dropped_packets": 0,
  "incomplete_blocks": 0,
  "lines": 19350,
  "malformed_lines": 0,
  "nonfinite_blocks": 0,
  "out_of_order_blocks": 0,
  "state_changes": 58,
  "unknown_names": 0,
  "untimed_blocks": 0
 }
}
```

</details>

### Reconnection & fault injection

**`reconnect.clean_reopen` - PASS** - Clean close, reopen, data again, identity unchanged  
closed in 0.2 ms, reopened in 0.119 s, first data 0.120 s after open; identity unchanged

<details><summary>evidence</summary>

```json
{
 "close_s": 0.0,
 "failure": null,
 "first_data_after_open_s": 0.12,
 "identity_differences": [],
 "identity_unchanged": true,
 "read_s": 2.03,
 "reopen_s": 0.119,
 "samples": 142
}
```

</details>

**`reconnect.host_killed` - PASS** - Host killed mid-stream: link loss reported, fresh open  
SIGKILL after 16 reads surfaced as a link loss in 3.3 ms; fresh host: first data 0.217 s after start (0.105 s after open); identity unchanged; exit code 0

<details><summary>evidence</summary>

```json
{
 "failure": null,
 "first_data_after_host_start_s": 0.217,
 "first_data_after_open_s": 0.105,
 "fresh_host_exit_code": 0,
 "fresh_host_start_s": 0.111,
 "identity_differences": [],
 "identity_unchanged": true,
 "kill": {
  "detect_s": 0.0033,
  "detected_as": "HostDied",
  "host_exit_code": -9,
  "killed": true,
  "message": "plugin host exited (code -9)",
  "pid": 32642,
  "reads_before_kill": 16,
  "signal": "SIGKILL"
 },
 "open_s": 0.104,
 "samples": 142
}
```

</details>

### Performance

**`performance.throughput` - PASS** - Sustained delivery rate keeps up with the nominal rate  
primary delivered 32.0122 samples/s over 20.0 s vs nominal 32 Hz (+0.038 %); 5426.6 B/s over IPC

<details><summary>evidence</summary>

```json
{
 "duration_s": 20.023,
 "ipc_bytes_per_s": 5426.6,
 "ipc_bytes_received": 108656,
 "streams": {
  "control_signal": {
   "arrival_span_s": 20.022,
   "chunks": 642,
   "error_percent": 0.038,
   "nominal_hz": 32.0,
   "rate_hz": 32.0122,
   "rate_hz_endpoints": 32.0654,
   "samples": 644,
   "samples_per_s_overall": 32.163
  },
  "state_changes": {
   "chunks": 38,
   "nominal_hz": 0.0,
   "samples": 58,
   "samples_per_s_overall": 2.897
  },
  "states": {
   "arrival_span_s": 20.022,
   "chunks": 642,
   "error_percent": 0.038,
   "nominal_hz": 32.0,
   "rate_hz": 32.0122,
   "rate_hz_endpoints": 32.0654,
   "samples": 644,
   "samples_per_s_overall": 32.163
  }
 },
 "tolerance_percent": 2.0
}
```

</details>

**`performance.latency` - NOT RUN** - Read latency (now - sample timestamp)  
not applicable: clock domain 'source' has no known relation to a host clock (latency cannot be measured; see timing.clock_domain for the offset)

**`performance.host_resources` - PASS** - Plugin host process CPU and memory  
host process CPU 1.8 % of one core, RSS peak 31.1 MiB (median 31.1 MiB)

<details><summary>evidence</summary>

```json
{
 "clock_ticks_per_s": 100,
 "cpu_percent_of_one_core": 1.8,
 "cpu_s": 0.36,
 "pid": 32642,
 "rss_mib_max_sampled": 31.1,
 "rss_mib_median": 31.1,
 "rss_mib_peak": 31.1,
 "rss_samples": 80,
 "wall_s": 20.023
}
```

</details>

**`performance.ipc` - PASS** - IPC volume and round-trip time  
5426.6 B/s, 32.06 reads/s; ping round trip p50/p99 0.161/0.2838 ms

<details><summary>evidence</summary>

```json
{
 "empty_read_fraction": 0.0,
 "host_bytes_per_s": 5426.6,
 "host_counters": {
  "bytes": 108656,
  "chunks": 1322,
  "reads": 642,
  "samples": 1346
 },
 "ping_round_trip_ms": {
  "max": 0.2916,
  "mean": 0.1712,
  "min": 0.1428,
  "n": 30,
  "p50": 0.161,
  "p95": 0.2507,
  "p99": 0.2838
 },
 "reads_per_s": 32.06
}
```

</details>

### BrainOS runtime: negotiation & event contract

**`runtime.descriptor` - PASS** - BrainOS device descriptor matches the declarations  
descriptor kind=simulated modality=None invasive=None integration=plugin matches the declarations

<details><summary>evidence</summary>

```json
{
 "brainos": {
  "adapter": "brainos-bci2000@0.1.0",
  "integration": {
   "api_version": "1.0",
   "ecosystem": "bci2000",
   "isolated": true,
   "kind": "plugin",
   "package": "brainos-bci2000",
   "version": "0.1.0"
  },
  "invasive": null,
  "kind": "simulated",
  "modality": null,
  "synthetic": true
 },
 "brainos_capabilities": [
  "recording",
  "behavior",
  "kinematic_intent",
  "device_status"
 ],
 "device_id": "plugin:bci2000:app-connector",
 "expected": {
  "capabilities": [
   "behavior",
   "device_status",
   "kinematic_intent",
   "recording"
  ],
  "integration": {
   "api_version": "1.0",
   "ecosystem": "bci2000",
   "isolated": true,
   "kind": "plugin",
   "package": "brainos-bci2000",
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
granted ['behavior', 'device_status', 'kinematic_intent', 'recording']; every other capability rejected (unsupported_by_device); command app suspended

<details><summary>evidence</summary>

```json
{
 "expected_granted": [
  "behavior",
  "device_status",
  "kinematic_intent",
  "recording"
 ],
 "negotiations": {
  "all_optional": {
   "device_id": "plugin:bci2000:app-connector",
   "granted": [
    "recording",
    "device_status",
    "behavior",
    "kinematic_intent"
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
    }
   ],
   "status": "active"
  },
  "command_required": {
   "device_id": "plugin:bci2000:app-connector",
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
   "device_id": "plugin:bci2000:app-connector",
   "granted": [
    "behavior",
    "device_status",
    "kinematic_intent",
    "recording"
   ],
   "rejected": [],
   "status": "active"
  }
 }
}
```

</details>

**`runtime.envelopes` - PASS** - Every event validates against the BrainOS contracts  
343 of 343 events validated against contract 1.3 (pydantic + JSON Schema); 0 invalid, 0 undeclared, 0 decode errors

<details><summary>evidence</summary>

```json
{
 "event_schema_versions": {
  "1.3": 343
 },
 "event_types": {
  "behavior.sample": 163,
  "device.status": 3,
  "intent.kinematics": 163,
  "recording.annotation": 14
 },
 "events_published": 343,
 "events_validated": 343,
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
 "schema_version": "1.3",
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
  "origin": "bci2000:127.0.0.1:20321 (processed control information, not raw signal)",
  "prerecorded": true,
  "synthetic": true
 },
 "decoder_model_id": "brainos-bci2000:bci2000-control-signal",
 "expected_provenance": {
  "behavior.sample": "behavioral_label",
  "intent.kinematics": "decoded_intent",
  "recording.annotation": "behavioral_label"
 },
 "problems": [],
 "regular_streams_without_events": []
}
```

</details>

## Environment

```json
{
 "brainos_version": "0.3.0",
 "certify_version": "0.1.0",
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
