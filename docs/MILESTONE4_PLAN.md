# Milestone 4 — Integration ecosystem: plan

## Existing extension points (main @ 279791e)

- `adapters/base.py` `DeviceAdapter` (async open/read/normalize/close) is internal: it imports
  runtime contracts and runs in-process. `runtime/registry.py` + `runtime/live_sources.py`
  create adapters; adding a source today means editing the core.
- `runtime/pipeline.py`: features → decoder → command router (continuous `intent.pointer` only).
- `brainos.sdk` (Python) and `frontend/src/sdk` (TS): app-facing; negotiation grants
  capabilities to any connected app.

## Foundation (this commit)

- **Contract 1.3 (additive):** `DeviceDescriptor.modality` / `invasive` / `integration`
  (builtin vs plugin, package, version, API version, isolation, ecosystem; all optional,
  `None` = not declared); `intent.selection.action` gains `activate` and `cancel`;
  negotiation rejection reason `not_authorized`.
- **Adapter SDK API 1.0** (`packages/brainos-adapter-sdk`, `brainos_adapter_sdk.api`):
  synchronous `SourcePlugin` / `SourceSession`, typed stream specs (role, channels, units,
  modality, clock domain), chunks with source timestamps and sample indices, operator
  options, errors (`OpenFailed`, `LinkLost`, `ConfigurationChanged`). No write path; no
  command roles. Depends only on numpy.

## Workstreams

| # | Workstream | Deliverables |
| --- | --- | --- |
| A | Plugin host + runtime integration | Out-of-process plugin host (binary framed IPC), manifest/stream/chunk validation, API-version compatibility, entry-point discovery, `PluginAdapter` in the runtime, plugin sources in REST + console, crash/timeout isolation; example third-party adapter package; standalone install of the SDKs |
| B | Ecosystems | `brainos-brainflow` plugin on BrainFlow's official `BoardShim` API (tested against the official library: synthetic, playback-file and streaming boards); `brainos-bci2000` plugin for the documented App Connector protocol (states + control signal — processed control information, not raw signal), built from BCI2000's own `ConnectorFilters.cpp` |
| C | Control bridge | Operator authorization of applications for decoded commands (default deny, revocable, `not_authorized`), discrete actions (select / activate / cancel) from decoder outputs with hysteresis, an LDA classifier for discrete decoding, SDK command-safety helpers (staleness, dead-man, stop on revocation), two SDK-only reference apps with different needs |
| D | Certification toolkit | `brainos-certify`: runs a plugin through the real host and checks metadata, channel identity, timestamps, ordering, loss, reconnection, throughput, negotiation and contract compliance; JSON + Markdown reports with explicit validation levels |

## Validation levels (used by D and docs)

1. **Adapter implementation** — the plugin satisfies the SDK contract against its own test source.
2. **Protocol-tested** — exercised against the external ecosystem's official software
   (e.g. BrainFlow's synthetic board via `BoardShim`), no hardware.
3. **Physical hardware-tested** — run with real acquisition hardware; requires a signed
   attestation record; the toolkit can record it but never grants it.
4. **Human-participant validated** — out of scope for software; never claimed by the toolkit.
