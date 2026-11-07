# Compatibility matrix

Which data sources BrainOS integrates, how, the highest evidence level each has actually
reached, the evidence, and what would be needed for the next level. Levels as defined in
[VALIDATION_LEVELS.md](VALIDATION_LEVELS.md) (project-wide, 1-4) and, for plugins, the
certification levels of [CERTIFICATION.md](CERTIFICATION.md) (`adapter_implementation`,
`protocol_tested`, `hardware_tested`, `human_participant_validated`).

**Nothing in BrainOS has been run with acquisition hardware or with a person.** No source is
at level 3 or 4, and no certification report here contains `hardware_tested` or
`human_participant_validated`. "Simulated", "synthetic board", "replay" and "capture" below
mean exactly that.

## Matrix

| Source | Integration | Level reached | Evidence (all executed) | Missing for the next level |
| --- | --- | --- | --- | --- |
| Simulated Profile A / B | built-in (`adapters/simulated`) | 1 — software | `test_adapters.py`, `test_runtime.py`, `test_server.py`, e2e demo; intents labelled `simulated_intent` | Not applicable: a simulator never becomes hardware evidence |
| NWB offline (DANDI 000954 FALCON H1) | built-in (`adapters/nwb`), "Offline Replay" | real-data replay (beside level 2) | `test_nwb_real.py` on the checksum-pinned real files (runs in CI), `test_nwb.py`; decoding results in DECODING.md from `make decoding-report` | Not live acquisition by definition; a live source is a different integration |
| BrainOS recording replay | built-in (`adapters/replay`) | 1 | Record → replay round trips in `test_runtime.py`, `test_plugin_example.py` | Replays BrainOS's own files; no external producer |
| Lab Streaming Layer | built-in (`adapters/lsl`) | **2 — protocol-tested** | `test_lsl.py` against liblsl 1.18 outlets; publisher in a separate process (BENCHMARKS_LIVE.md); reconnect after killing the publisher | A real amplifier's LSL app with a reference recorder (LabRecorder → XDF) comparing counts, values and timestamps (level 3) |
| Open Ephys ZMQ Interface | built-in (`adapters/openephys`) | **2 — protocol-tested** | `test_openephys.py`; the official plugin Python client parses our publisher's output bit-exactly | Open Ephys GUI with an acquisition board, compared against the GUI's own recording (level 3); see OPEN_EPHYS.md |
| `example-mi-eeg` (`brainos-example-adapter` 0.1.0) | plugin, adapter SDK 1.0, isolated host | certify: **`adapter_implementation`** (level 1) | [report](compatibility/example-mi-eeg.certify.md): 27 pass, 1 warn, 0 fail; `test_plugin_example.py`, `test_m4_demo.py` | Not applicable: a declared-synthetic generator for tutorials, never brain data |
| `brainflow` (`brainos-brainflow` 0.1.0), device `synthetic` | plugin, ecosystem `brainflow` | certify: **`protocol_tested`** against "BrainFlow 5.23 BoardShim SYNTHETIC_BOARD" (operator statement); project level **2** | [report](compatibility/brainflow-synthetic.certify.md): 26 pass, 2 warn, 0 fail, all 5 protocol consistency rules hold (installed brainflow 5.23.0); 41 package tests against the official library (synthetic, playback-file, streaming boards); `test_plugin_ecosystems.py` | A physical BrainFlow-supported board, with an operator attestation for `hardware_tested`; for project level 3 also a comparison against an independent reference recording |
| `bci2000` (`brainos-bci2000` 0.1.0), device `app-connector` | plugin, ecosystem `bci2000` | certify: **`adapter_implementation`** in this run; project level **2** (from the opt-in live test) | [report](compatibility/bci2000-app-connector.certify.md): 26 pass, 2 warn, 0 fail, fed by `replay_bci2000_capture.py` (genuine BCI2000 3.6 ConnectorOutput capture, looped); the package's opt-in test against a locally built genuine BCI2000 (ECOSYSTEMS.md) | For `protocol_tested` in a certification report: a live BCI2000 run with `--protocol-reference "BCI2000 3.6 …"`. Attempted: BCI2000 stops sending for the rest of a run once its receiver is unreachable for ~1 s (measured; ECOSYSTEMS.md), so the certifier's deliberate kill/reopen phase needs a BCI2000 run restart between phases — a certify option to pause for an operator/automated run restart is the missing piece. For hardware: a real amplifier source module and an attestation |
| Any other third-party plugin | plugin | whatever its report says | `brainos-certify <entry point>` | — |

## Certification runs in this repository

Generated with `brainos-certify` 0.1.0 on 2026-11-07 in a 4-vCPU x86_64 Linux container
(Intel Xeon @ 2.10 GHz, Python 3.12.3, adapter SDK 1.0.0, BrainOS 0.3.0, contract 1.3), from
commit `ef626ac` with clean plugin source trees. Each report states its plugin's file hashes,
the full environment and every measured value; numbers are machine-dependent.

| | `example-mi-eeg` | `brainflow` / `synthetic` | `bci2000` / `app-connector` |
| --- | --- | --- | --- |
| Command | `brainos-certify example-mi-eeg` | `brainos-certify brainflow --device synthetic --protocol-reference "BrainFlow 5.23 BoardShim SYNTHETIC_BOARD"` | `brainos-certify bci2000 --option port=20321 --option sampling_rate_hz=256 --option sample_block_size=8 --option declare_synthetic=true --option declare_prerecorded=true` with `replay_bci2000_capture.py --port 20321` running |
| Data source | the plugin's own generator (declared synthetic) | BrainFlow 5.23.0 `SYNTHETIC_BOARD` via the official `BoardShim` | 2 010 recorded ConnectorOutput datagrams (67 complete blocks) re-sent with original timing, looping; declared synthetic + prerecorded |
| Level | `adapter_implementation` | `protocol_tested` (operator statement) | `adapter_implementation` |
| Warnings | 1 channel without unit (`cue` class label) | 13 of 29 channels without unit (BrainFlow aux rows); modality not declared (ambiguous EXG rows) | both synthetic and prerecorded declared (BrainOS treats as synthetic); 19 of 19 channels without unit (App Connector carries none) |
| Rate from timestamps vs nominal | 250.000 vs 250 Hz (+0.000 %) | 249.933 vs 250 Hz (−0.027 %) | 32.012 vs 32 Hz (+0.039 %) |
| Delivered rate (host clock), 20 s | 249.998 /s (−0.001 %) | 249.934 /s (−0.026 %) | 32.012 /s (+0.038 %) |
| Timestamp residual p50 / p99 / max | 0 / 0 / 0 ms (computed from the sample index) | 0.026 / 0.161 / 2.52 ms | 0.28 / 2.86 / 2.88 ms (1 ms SourceTime resolution) |
| Clock | `source` (host monotonic + index / 250); offset 5.6 ms, drift +7.3 ppm | `unix`; median 1.70 ms behind the wall clock, drift +0.0 ppm | `source` (BCI2000 SourceTime); drift −21.4 ppm vs host monotonic |
| Read latency p50 / p99 / max | n/a (`source` clock) | 1.74 / 3.13 / 10.50 ms | n/a (`source` clock) |
| Gaps / overlaps (3 sessions) | 0 / 0 in 7 200 samples | 0 / 0 in 12 004 samples | 0 / 0 in 1 560 samples |
| Markers | 5, ordered | no markers stream | 58 state-change markers, ordered |
| Clean reopen: close / reopen / first data | 0.2 ms / 1 ms / 0.102 s | 1.6 ms / 1 ms / 0.002 s | 0.2 ms / 0.119 s / 0.120 s |
| Host SIGKILL: detected as link loss in | 3.3 ms | 4.0 ms | 3.3 ms |
| Fresh host: first data after start (after open) | 0.256 s (0.114 s) | 0.174 s (0.007 s) | 0.217 s (0.105 s) |
| Channel identity over 4 opens | identical (10 channels) | identical (29 channels) | identical (20 channels) |
| Host CPU / RSS peak | 1.1 % / 37.4 MiB | 16.5 % / 34.9 MiB | 1.8 % / 31.1 MiB |
| IPC volume, ping p50 | 10.6 kB/s, 0.17 ms | 62.0 kB/s, 0.12 ms | 5.4 kB/s, 0.16 ms |
| BrainOS runtime: events validated (contract 1.3) | 305 / 305 | 1 251 / 1 251 | 343 / 343 |
| Granted to a test app (all others rejected; command app suspended) | recording, behavior, device_status | recording, device_status | recording, behavior, kinematic_intent, device_status |

The BCI2000 control signal reaches BrainOS as `intent.kinematics` with provenance
`decoded_intent` and model id `brainos-bci2000:bci2000-control-signal`; the runtime phase
verified that no command event was produced (the command router was off).

### How the replayed BCI2000 capture differs from live BCI2000

`packages/brainos-certify/scripts/replay_bci2000_capture.py` re-sends the datagrams of
`packages/brainos-bci2000/tests/fixtures/bci2000_connector_output.json` with their recorded
timing. To loop it, the truncated last block (cut when BCI2000 stopped the run) is not sent,
and `SourceTime` is advanced by one loop period (2 093 ms) per loop, modulo 65 536, so the
replayed acquisition clock keeps running forward; loops are paced on that clock. Everything
else is byte-for-byte what BCI2000 sent. It is a replay, so this certification run does not
claim `protocol_tested`.

## Defects caught (deliberately broken test plugins)

`python packages/brainos-certify/scripts/certify_broken_plugins.py --markdown` certifies every
plugin in `backend/tests/plugins/bos_test_plugins` (3 s runs). Every defect is caught by a
specific failing check and no broken plugin reaches a level:

| Test plugin | Defect | Level | Caught by | Reason (from the report) |
| --- | --- | --- | --- | --- |
| `GoodPlugin` | none (control) | `adapter_implementation` | — | — |
| `GarbagePlugin` | writes to stdout / fd 1 | `adapter_implementation` | — | contained by the plugin host's stdout isolation: not a contract violation |
| `OpenFailsPlugin` | `open()` raises `OpenFailed` | none | `metadata.session_valid` | open() failed: OpenFailed: test device is unplugged |
| `OpenCrashPlugin` | `open()` raises an unexpected exception | none | `metadata.session_valid` | open() failed: InternalError: open() raised RuntimeError: bug in open |
| `UndeclaredRolePlugin` | session role missing from the manifest | none | `metadata.session_valid` | InvalidSession: … role 'decoder_output' is not declared in the manifest's roles [stream.role.undeclared] |
| `HangPlugin` | `read()` blocks forever | none | `integrity.read` | plugin host did not answer within 2.1 s (killed) |
| `ExitPlugin` | process exits mid-stream | none | `integrity.read` | plugin host exited (code 3) |
| `SysExitPlugin` | `read()` calls `sys.exit` | none | `integrity.read` | read() raised SystemExit: 2 |
| `UndeclaredStreamPlugin` | chunk for an undeclared stream | none | `integrity.chunk_validation` | chunk.stream.unknown: chunk for stream 'bogus', which the session did not declare |
| `WrongChannelsPlugin` | wrong channel count | none | `integrity.chunk_validation` | chunk.data.channels: data has 3 channels; stream declares 4 |
| `NaNPlugin` | NaN in the data | none | `integrity.chunk_validation` | chunk.data.finite: data contains NaN or infinity |
| `DecreasingTimestampsPlugin` | timestamps jump back | none | `timing.monotonic` | chunk.timestamps.decreasing: first timestamp 0.52 is before the previous chunk's last timestamp 1.019 |
| `SlowReadPlugin` | 0.3 s per read | none | `performance.throughput` | 'sig' falls behind: delivered 66.31 samples/s vs nominal 1000 Hz (−93.37 %) |
| `FastPlugin` | unpaced source | none | `performance.throughput` | 'sig' runs ahead of real time: 1.101e+06 samples/s vs nominal 30000 Hz (unpaced; machine-dependent) |
| `HangDiscoverPlugin` | `discover()` blocks forever | none | `manifest.discover` | HostDied: plugin host did not answer within 12 s (killed) |
| `Api2Plugin` | written for SDK API 2.0 | none | `manifest.api_compat` | written for adapter SDK API 2.0 … (major versions differ) |
| `NotAPlugin` | not a `SourcePlugin` | none | `manifest.load` | LoadFailed: … is not a SourcePlugin subclass |
| `import_error` module | `ImportError` on import | none | `manifest.load` | LoadFailed: … ImportError: this test plugin depends on a library that is not installed |

The certifier's own test suite (`packages/brainos-certify/tests`) adds crafted defects for the
remaining checks: unknown units and undeclared modality (warnings), labels that change between
opens (`metadata.channel_identity`), a source 10 % slower than declared (`timing.rate`),
sample-index gaps (warning, counted) and overlaps, out-of-order and off-clock markers, `unix`
timestamps that are not unix time (`timing.clock_domain`), timestamp jitter (`timing.jitter`),
invalid and lossy `stats()`, a device lock that a killed host leaves behind
(`reconnect.host_killed`), an invalid manifest, no devices, and an unknown device or option.

## Reproducing

```bash
pip install -e packages/brainos-adapter-sdk -e "backend[server,dev,nwb,dsp,live]" \
    -e examples/adapters/brainos-example-adapter -e packages/brainos-brainflow \
    -e packages/brainos-bci2000 -e packages/brainos-certify
brainos-certify example-mi-eeg --out docs/compatibility --name example-mi-eeg
brainos-certify brainflow --device synthetic \
    --protocol-reference "BrainFlow 5.23 BoardShim SYNTHETIC_BOARD" \
    --out docs/compatibility --name brainflow-synthetic
python packages/brainos-certify/scripts/replay_bci2000_capture.py --port 20321 --seconds 150 &
brainos-certify bci2000 --option port=20321 --option sampling_rate_hz=256 \
    --option sample_block_size=8 --option declare_synthetic=true \
    --option declare_prerecorded=true --out docs/compatibility --name bci2000-app-connector
python packages/brainos-certify/scripts/certify_broken_plugins.py --markdown
```
