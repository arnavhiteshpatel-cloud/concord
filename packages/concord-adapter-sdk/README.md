# concord-adapter-sdk

Public SDK for integrating a neural-data source with Concord as an isolated, read-only plugin.
Depends only on numpy; never imports Concord.

| Module | Purpose |
| --- | --- |
| `concord_adapter_sdk.api` | The plugin API (1.0): `SourcePlugin`, `SourceSession`, streams, chunks, options, errors |
| `concord_adapter_sdk.validate` | Every rule Concord checks, with stable problem codes |
| `concord_adapter_sdk.host` | The plugin host process: `python -m concord_adapter_sdk.host <plugin>` (IPC), `--list`, `--check` |
| `concord_adapter_sdk.ipc` | `concord.plugin-ipc/1` framing and (de)serialization |
| `concord_adapter_sdk.client` | `SyncHostClient`: run a plugin through a real host (for tests) |

Guide: `docs/ADAPTER_SDK.md` in the Concord repository. Tutorial and template:
`examples/adapters/concord-example-adapter`.
