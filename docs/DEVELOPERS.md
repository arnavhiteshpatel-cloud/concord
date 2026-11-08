# Building on Concord: developer setup

Three independent roles, three independent installs. None of them requires Concord's
private implementation; each flow below is run in fresh virtual environments from built
wheels by `make dist-check` (and in CI), so these instructions are tested.

> Packages are not published to PyPI yet. Build the wheels from this repository
> (`uv build --wheel -o dist packages/concord-adapter-sdk backend packages/concord-certify`)
> and add `--find-links dist` to the `pip install` commands below.

| Package | For | Depends on |
| --- | --- | --- |
| `concord-adapter-sdk` | writing a source plugin (device integration); `concord-adapter` CLI | numpy |
| `concord-certify` | testing a plugin and producing a compatibility report | concord-adapter-sdk, jsonschema (+ `concord` for the runtime phase) |
| `concord` | writing an application (Python SDK) | pydantic, httpx, websockets |
| `concordos[server]` | running Concord (runtime server, console, plugin hosting) | + fastapi, uvicorn, concord-adapter-sdk |
| `concord-brainflow`, `concord-bci2000` | ecosystem integrations (plugins) | concord-adapter-sdk (+ brainflow) |

## 1. Integrate a device (adapter developer)

```bash
python -m venv .venv && . .venv/bin/activate
```
```bash
pip install concord-adapter-sdk
```
```bash
concord-adapter new my-amp --display "My amplifier"
```
```bash
pip install -e concord-my-amp
```
```bash
concord-adapter check my-amp
```

`new` writes a complete, installable plugin package that already works (a declared-synthetic
template signal) with `TODO` markers where your device I/O and metadata go. `check` runs it
exactly as Concord will: in the plugin host, in a separate process, with every declaration
and every chunk validated. Read [ADAPTER_SDK.md](ADAPTER_SDK.md) for the API, the rules,
and the isolation model; [`examples/adapters/concord-example-adapter`](../examples/adapters/concord-example-adapter)
is a fuller example (synthetic motor-imagery EEG with cues and markers).

Rules that matter most: declare only what you know (unknown units/modality stay unknown),
use your source's own timestamps in a declared clock domain, count samples in
`first_index` so losses are visible, raise `LinkLost` when the link drops. Plugins cannot
send anything to a device and cannot emit application commands.

## 2. Certify it

```bash
pip install concord-certify
```
```bash
concord-certify my-amp --duration 20 --out reports/
```

The report (JSON + Markdown) states the validation level reached. Software checks can reach
**adapter implementation**, or **protocol-tested** when you state the external reference
software that produced the data. **Hardware-tested** is only recorded from a signed operator
attestation and is shown as such; **human-participant validated** is never granted by
software. See [CERTIFICATION.md](CERTIFICATION.md) and [COMPATIBILITY.md](COMPATIBILITY.md).

## 3. Run Concord with the plugin (lab)

```bash
pip install "concordos[server]" concord-my-amp
```
```bash
concord-server
```

Open http://127.0.0.1:8000 → **Connect a source → Plugins**: the plugin is listed with its
validation result; choose the device, fill in its options, connect. The source row shows
`Plugin · <package>@<version> · isolated` and the declared modality. Everything downstream
(signal integrity, recording, pipeline, decoders, calibration, command output) works
unchanged. (From a repository checkout, `make setup && make run` does the same and also
installs the BrainFlow and BCI2000 integrations.)

## 4. Build an application (app developer)

```bash
pip install concordos
```

```python
import asyncio
from concord.sdk import EventStream, NegotiationUpdate, is_event

async def main() -> None:
    async with await EventStream.connect(
        app_id="my-app", app_name="My App",
        required=["selection"], optional=["pointer_intent", "text_intent"],
    ) as stream:
        async for item in stream:
            if isinstance(item, NegotiationUpdate):
                print("granted:", item.negotiation.granted, "rejected:", item.negotiation.rejected)
            elif is_event(item):
                print(item.event_type, item.payload, item.provenance.kind)

asyncio.run(main())
```

The base `concord` package is only the SDK and the event contracts — no server, no numpy.
Apps never name a device: they declare capabilities and adapt to what is granted. Decoded
commands (pointer, select / activate / cancel, text) reach an app only after the operator
authorizes it; until then negotiation says `not_authorized`. Use the SDK's `CommandGuard`
so stale commands never act and motion stops on revocation, disconnect or silence. See
[SDK.md](SDK.md) and [CONTROL_BRIDGE.md](CONTROL_BRIDGE.md); two complete reference apps
(continuous cursor, discrete menu) are in [`backend/examples/reference_app`](../backend/examples/reference_app).

## Versioning

- Adapter SDK API `1.0`: a plugin declares the API version it was written for; Concord
  accepts the same major version with a minor version ≤ its own and rejects others with a
  reason (never loads them).
- Event schema `1.3`: consumers accept the same major version; minor versions are additive.
- Packages follow semantic versioning; `concord` is pre-1.0 (internal preview).

## M5-D: the `concord` command, the desktop bundle, the lab acceptance test

`concordos[server]` installs the `concord` command: `start` / `stop` / `status` / `serve`,
`doctor` (support report), `config` (an optional TOML file; environment variables override
it), `dataset`, `reproduce`, `version`. `concordos[lab]` adds processing, NWB, LSL and Open Ephys.
To ship the console inside the wheel, stage it before building
(`python packaging/stage_console.py --build`); otherwise a wheel install serves the API only.

The desktop bundle is built with PyInstaller (`make app`; `packaging/concord.spec`); the same
executable answers `concord` commands and hosts source plugins (`-m concord_adapter_sdk.host`).
`make app-smoke` runs it like a user. `make lab-acceptance` (`scripts/lab_acceptance.py`)
extends `make dist-check` with the whole researcher workflow from built wheels in fresh
virtualenvs. CI: `package-linux`, `package-macos`, `lab-acceptance`.
