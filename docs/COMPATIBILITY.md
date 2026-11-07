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

The machine-readable form of this page is the [compatibility registry](#registry-m5-f)
(`compat/registry.json`, `GET /api/v1/compatibility`, console: Advanced → Compatibility). Its
levels are derived from evidence by fixed rules; where the hand-written matrix below and the
registry disagree, the registry's derivation is the one CI checks.

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

## Registry (M5-F)

Milestone 5, workstream F. A machine-readable registry of every integration: what it is, the
validation level it has reached, and the evidence for that level. Nothing in it is typed in
by hand except where evidence lives; the level is **derived**.

| | |
| --- | --- |
| Registry | `compat/registry.json`, JSON Schema `compat/registry.schema.json` (generated from the pydantic models in `backend/src/brainos/compat/model.py`) |
| Inputs | `compat/sources.json` (curated: integrations, evidence paths, anchors, not-tested notes; **no level field**, a typed-in level is refused) and every `docs/compatibility/*.certify.json` (brainos-certify reports) |
| Generator | `make compat` = `python -m brainos.compat.build`; writes the registry, its schema and the generated section below |
| Staleness | `make compat-check` = `python -m brainos.compat.build --check`, run in CI (backend job, step "Workstream F: compatibility registry is current"): exit 1 when any generated file differs from what the checkout produces, 2 when the input is refused |
| REST | `GET /api/v1/compatibility`: the registry plus, per entry, what this installation has (`live`) |
| Console | Advanced → Compatibility: a read-only table (integration, kind, level, evidence, not tested) |

**What an entry holds.** id, kind (`builtin_adapter`, `source_plugin`, `offline_dataset`),
ecosystem / protocol, package and the version the evidence is for, modalities as declared by
the integration (built-in adapters other than the T15 adapter declare none), a read-only
statement, the derived level with its rule-by-rule trace (`level_basis`), whether real-data
replay applies, the evidence (type `test` / `certify_report` / `benchmark` / `doc`, path,
description, date, what it supports, whether it was counted and why not), what was not tested,
and known limitations.

**How the level is derived** (`backend/src/brainos/compat/rules.py`; the rules are also
written into the registry and the generated section). Levels are those of
[VALIDATION_LEVELS.md](VALIDATION_LEVELS.md); the build fails if that page stops defining them.

1. `software_implemented`: a counted test file, or a counted certify report with
   `adapter_implementation`.
2. `protocol_tested`: level 1, and a counted certify report with `protocol_tested` (every
   consistency rule holds), or a counted test that names the real protocol stack or official
   reference implementation it runs against and contains the anchor text tying it to it
   (e.g. `pylsl.StreamOutlet`, `plot_process_zmq.py`, `from brainflow.board_shim import`).
3. `hardware_verified`: level 2, a counted certify report whose `hardware_tested` rests on an
   accepted, signature-verified operator attestation, **and** a document of a comparison
   against an independent reference. An attestation alone is not level 3; a comparison
   document without an attestation is refused. **No entry meets this.**
4. `human_validated`: never derived by software; evidence claiming it is refused. **No entry
   is at level 4.**

Counting: a test that does not run in CI (the BCI2000 live test) counts only with a recorded
execution, i.e. a document containing a given anchor. A certify report counts only if its
plugin version and plugin source files (`tree_sha256`, the same hash brainos-certify records)
equal this checkout's; otherwise it is listed with the reason and not counted. Real-data
replay (beside level 2, not a level) needs a counted test that reads recordings pinned by
SHA-256 in a dataset manifest. Benchmarks and documents are context.

Refused (nothing is written, exit 2): a missing evidence path, anchor or recorded execution;
a typed-in level or any unknown field; a protocol claim without an anchor; a malformed,
schema-invalid or internally inconsistent certify report (e.g. `protocol_tested` with a
broken consistency rule, `hardware_tested` without an accepted attestation, any
`human_participant_validated`); a reference-comparison claim without an accepted attestation;
any level-4 claim; an adapter id that does not appear in its code; a declared modality the
code never uses.

**Live status** (`live` in the REST response, per entry id). Built-in adapters: `installed`
when the code is importable and the running BrainOS version equals the registry's;
`unavailable` when an optional module it needs (e.g. `pylsl`, `zmq`, `pynwb`) is missing;
`not_installed` when its code is not in this installation. Plugins, from the last plugin
discovery: `installed` (version equal to the registry's), `different_version` (shown as
"evidence for a different version"), `unavailable` (rejected or failed to load),
`not_installed`, or `not_checked` (discovery has not run). Live status never changes a level.

**Limitations of the registry.** It checks that evidence exists and says what it claims to
(paths, anchors, report consistency, source hashes); it does not re-run tests or read test
results: a counted CI test is one CI runs on every change, and CI fails if it fails. Dates of
tests, benchmarks and documents are curated (the date the evidence was produced or last
changed); certify-report dates come from the report. A plugin outside this repository cannot
be hash-checked; its report counts for the version it names. Built-in adapters carry the
BrainOS package version. The T15 cursor+click adapter (`brainos.cursorclick.t15`, workstream
P0) is listed as not in this checkout until its code is merged; its evidence is read only then.

<!-- BEGIN compat-registry (generated by `make compat`; do not edit by hand) -->

_Generated from `compat/registry.json` (registry 1.0, BrainOS 0.3.0) by `make compat`; CI fails when it is stale (`python -m brainos.compat.build --check`). Edit `compat/sources.json` or add certify reports, never this table._

Levels are derived from the evidence listed for each entry by rules R1-R7; none is entered by hand. An entry is at the highest level whose evidence exists in this checkout, not the level it was designed for. No entry has reached hardware_verified (level 3) or human_validated (level 4).

| Integration | Kind | Package | Level (derived) | Counted evidence | Not tested |
| --- | --- | --- | --- | --- | --- |
| Simulated Profile A (`brainos.sim.profile_a`) | built-in adapter | brainos 0.3.0 | 1: Software-implemented | [test_adapters.py](../backend/tests/test_adapters.py), [test_runtime.py](../backend/tests/test_runtime.py), [test_server.py](../backend/tests/test_server.py) | Not applicable beyond software: a simulator never becomes protocol, hardware or human evidence. |
| Simulated Profile B (`brainos.sim.profile_b`) | built-in adapter | brainos 0.3.0 | 1: Software-implemented | [test_adapters.py](../backend/tests/test_adapters.py), [test_runtime.py](../backend/tests/test_runtime.py) | Not applicable beyond software: a simulator never becomes protocol, hardware or human evidence. |
| BrainOS recording replay (`brainos.replay`) | built-in adapter | brainos 0.3.0 | 1: Software-implemented | [test_runtime.py](../backend/tests/test_runtime.py), [test_plugin_example.py](../backend/tests/test_plugin_example.py) | Replays only BrainOS's own recording format; no external producer. |
| NWB recordings, offline replay (DANDI 000954, FALCON H1) (`brainos.nwb.units`) | offline dataset | brainos 0.3.0 | 1: Software-implemented · real-data replay | [test_nwb_real.py](../backend/tests/test_nwb_real.py), [test_nwb.py](../backend/tests/test_nwb.py) | Not live acquisition by definition: offline replay of recordings made in the past. |
| Cursor + click recordings, offline replay (Dryad doi:10.5061/dryad.prr4xgxzq, participant T15) (`brainos.cursorclick.t15`) | offline dataset | brainos 0.3.0 | none (not in this checkout) | — | Not live acquisition by definition: offline replay of recordings made in the past. |
| Lab Streaming Layer (`brainos.lsl`) | built-in adapter | brainos 0.3.0 | 2: Protocol-tested · real-data replay | [test_lsl.py](../backend/tests/test_lsl.py), [test_pipeline_live.py](../backend/tests/test_pipeline_live.py) | Third-party LSL producers (vendor LSL apps, LabRecorder interop). Acquisition hardware: level 3 needs a real amplifier's LSL app recorded at the same time by a reference recorder (LabRecorder to XDF), with counts, values and timestamps compared offline. |
| Open Ephys ZMQ Interface (`brainos.openephys.zmq`) | built-in adapter | brainos 0.3.0 | 2: Protocol-tested | [test_openephys.py](../backend/tests/test_openephys.py) | Never run against the Open Ephys GUI or an acquisition board: the test publisher reproduces the plugin's format from its source, so a mismatch with the real plugin binary is possible. Level 3 needs the GUI with an acquisition board, compared against the GUI's own Binary-format recording, with TTL alignment checked against a known pulse generator. |
| Example: motor-imagery EEG generator (`brainos-example-adapter`) | source plugin | brainos-example-adapter 0.1.0 | 1: Software-implemented | [example-mi-eeg.certify.json](../docs/compatibility/example-mi-eeg.certify.json), [test_example_mi_eeg.py](../examples/adapters/brainos-example-adapter/tests/test_example_mi_eeg.py), [test_plugin_example.py](../backend/tests/test_plugin_example.py), [test_m4_demo.py](../backend/tests/test_m4_demo.py) | Not applicable beyond software: a declared-synthetic generator for tutorials, never brain data. |
| BrainFlow (`brainos-brainflow`) | source plugin | brainos-brainflow 0.1.0 | 2: Protocol-tested | [brainflow-synthetic.certify.json](../docs/compatibility/brainflow-synthetic.certify.json), [test_bf_synthetic.py](../packages/brainos-brainflow/tests/test_bf_synthetic.py), [test_bf_playback.py](../packages/brainos-brainflow/tests/test_bf_playback.py), [test_bf_streaming.py](../packages/brainos-brainflow/tests/test_bf_streaming.py), [test_bf_options.py](../packages/brainos-brainflow/tests/test_bf_options.py), [test_bf_layout.py](../packages/brainos-brainflow/tests/test_bf_layout.py), [test_plugin_ecosystems.py](../backend/tests/test_plugin_ecosystems.py) | No hardware board was connected; units, channel types and package counters of real boards come from BrainFlow's descriptions only. hardware_tested needs a physical BrainFlow-supported board and an operator-signed attestation; level 3 also needs a comparison against an independent reference recording. |
| BCI2000 App Connector (`brainos-bci2000`) | source plugin | brainos-bci2000 0.1.0 | 2: Protocol-tested | [test_bci_real_bci2000.py](../packages/brainos-bci2000/tests/test_bci_real_bci2000.py), [test_bci_plugin.py](../packages/brainos-bci2000/tests/test_bci_plugin.py), [test_bci_protocol.py](../packages/brainos-bci2000/tests/test_bci_protocol.py), [test_plugin_ecosystems.py](../backend/tests/test_plugin_ecosystems.py) | No amplifier and no BCI2000 source module other than SignalGenerator; no application other than DummyApplication; BCI2000 on Windows or macOS, or on another machine. protocol_tested in a certification report: needs a live BCI2000 run, and BCI2000 stops sending for the rest of a run after its receiver is unreachable for about 1 s, so the certifier's kill and reopen phases need a run restart. The official bci2000.org distribution: the build is from a public fork's source. |

Evidence listed but **not counted**:

- `brainos-bci2000`: [bci2000-app-connector.certify.json](../docs/compatibility/bci2000-app-connector.certify.json): Evidence for an earlier revision of this version: plugin source changed after this run (plugin.py); re-run brainos-certify to count it

Derivation rules:

- R1 software_implemented: at least one counted test file, or a counted brainos-certify report that achieved adapter_implementation.
- R2 protocol_tested: R1, and a counted brainos-certify report that achieved protocol_tested (every consistency rule holds), or a counted test that names the real protocol stack or official reference implementation it runs against (protocol_reference) and contains the anchor text tying it to that stack.
- R3 hardware_verified: R2, and a counted certify report whose hardware_tested level rests on an accepted (signature-verified) operator attestation, and a document of a comparison against an independent reference. An attestation alone is not level 3; a comparison document without an accepted attestation is refused.
- R4 human_validated: never derived by software. It requires an approved human-research protocol run by qualified investigators; any evidence claiming it is refused.
- R5 counting: a test that does not run in CI counts only with a recorded execution (a document containing the given anchor). A certify report counts only if its plugin version and plugin source files (tree_sha256) equal this checkout's; otherwise it is listed and not counted. Benchmarks and documents are context; they do not establish a level.
- R6 refused (nothing is written): a missing evidence path or anchor, a typed-in level or any unknown field, a malformed or internally inconsistent certify report, a certify report claiming human_participant_validated, hardware_tested without an accepted attestation, and the claims refused by R3 and R4.
- R7 real-data replay (beside level 2, not a level): a counted test that reads recordings pinned by SHA-256 in a dataset manifest.

<!-- END compat-registry -->
