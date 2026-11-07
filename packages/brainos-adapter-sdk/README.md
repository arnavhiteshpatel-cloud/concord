# brainos-adapter-sdk

Public SDK for integrating a neural-data source with BrainOS as an isolated, read-only plugin.
Depends only on numpy; never imports BrainOS.

| Module | Purpose |
| --- | --- |
| `brainos_adapter_sdk.api` | The plugin API (1.0): `SourcePlugin`, `SourceSession`, streams, chunks, options, errors |
| `brainos_adapter_sdk.validate` | Every rule BrainOS checks, with stable problem codes |
| `brainos_adapter_sdk.host` | The plugin host process: `python -m brainos_adapter_sdk.host <plugin>` (IPC), `--list`, `--check` |
| `brainos_adapter_sdk.ipc` | `brainos.plugin-ipc/1` framing and (de)serialization |
| `brainos_adapter_sdk.client` | `SyncHostClient`: run a plugin through a real host (for tests) |

Guide: `docs/ADAPTER_SDK.md` in the BrainOS repository. Tutorial and template:
`examples/adapters/brainos-example-adapter`.
