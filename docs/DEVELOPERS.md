# Building on Concord: developer setup

Three independent roles, three independent installs. None of them requires Concord's
private implementation; each flow below is run in fresh virtual environments from built
wheels by `make dist-check` (and in CI), so these instructions are tested.

> **None of these packages is on PyPI.** Each GitHub release ships them as wheels (from 0.3.1:
> `concordos`, `concord_adapter_sdk`, `concord_decoder_sdk`, `concord_certify`, `concord_hwval`,
> `concord_brainflow`, `concord_bci2000`). Download all `.whl` files of the
> [release](https://github.com/arnavhiteshpatel-cloud/concord/releases/latest) into one folder and
> pass it to pip with `--find-links <folder>`, as in the commands below. Third-party
> dependencies (numpy, fastapi, brainflow, …) come from PyPI. To build the wheels yourself from
> this repository: `uv build --wheel -o dist packages/concord-adapter-sdk backend
> packages/concord-certify` (and the other packages), then `--find-links dist`.

| Package | For | Depends on |
| --- | --- | --- |
| `concord-adapter-sdk` | writing a source plugin (device integration); `concord-adapter` CLI | numpy |
| `concord-certify` | testing a plugin and producing a compatibility report | concord-adapter-sdk, jsonschema (+ `concordos` for the runtime phase) |
| `concordos` (import name `concord`) | writing an application (Python SDK) | pydantic, httpx, websockets |
| `concordos[server]` | running Concord (runtime server, console, plugin hosting) | + fastapi, uvicorn, concord-adapter-sdk |
| `concordos[lab]` | `[server]` plus processing, NWB, LSL and Open Ephys | + numpy, scipy, pynwb, pylsl, pyzmq |
| `concord-brainflow`, `concord-bci2000` | ecosystem integrations (plugins) | concord-adapter-sdk (+ brainflow) |

## 1. Integrate a device (adapter developer)

```bash
python -m venv .venv && . .venv/bin/activate
```
```bash
pip install --find-links <wheels folder> concord-adapter-sdk
```
```bash
concord-adapter new my-amp --display "My amplifier"
```
```bash
pip install --find-links <wheels folder> -e concord-my-amp
```

(Installing the scaffold builds it with `hatchling`, which pip downloads from PyPI.)
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
pip install --find-links <wheels folder> concord-certify
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
pip install --find-links <wheels folder> "concordos[lab]" concord-my-amp
```
```bash
concord start
```

(`concord-server` runs the same server in the foreground.) Open http://127.0.0.1:8000 →
**Connect a source → Plugins** (**Search again** if Concord was already running): the plugin is
listed with its validation result; open the device's **Options**, fill them in, **Connect**.
The form labels are your options' descriptions. The source row shows
`Plugin · <package>@<version> · isolated` and the declared modality. Everything downstream
(signal integrity, recording, pipeline, decoders, calibration, command output) works unchanged;
in 0.3.1 the console does not show a plugin's own counters (**Advanced → Acquisition details**
says *No telemetry*), they are in `GET /api/v1/devices/{id}/source`. The desktop app cannot load
additional plugins (it includes only BCI2000's); use a Python installation. (From a repository
checkout, `make setup && make run` does the same and also installs the BrainFlow and BCI2000
integrations.) Researcher-facing steps: [Connect your equipment §4.5](CONNECT_YOUR_EQUIPMENT.md#45-your-own-device-a-source-plugin).

## 4. Build an application (app developer)

```bash
pip install --find-links <wheels folder> concordos
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

The base `concordos` distribution (imported as `concord`) is only the SDK and the event
contracts — no server, no numpy.
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
