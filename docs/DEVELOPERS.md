# Building on BrainOS: developer setup

Three independent roles, three independent installs. None of them requires BrainOS's
private implementation; each flow below is run in fresh virtual environments from built
wheels by `make dist-check` (and in CI), so these instructions are tested.

> Packages are not published to PyPI yet. Build the wheels from this repository
> (`uv build --wheel -o dist packages/brainos-adapter-sdk backend packages/brainos-certify`)
> and add `--find-links dist` to the `pip install` commands below.

| Package | For | Depends on |
| --- | --- | --- |
| `brainos-adapter-sdk` | writing a source plugin (device integration); `brainos-adapter` CLI | numpy |
| `brainos-certify` | testing a plugin and producing a compatibility report | brainos-adapter-sdk, jsonschema (+ `brainos` for the runtime phase) |
| `brainos` | writing an application (Python SDK) | pydantic, httpx, websockets |
| `brainos[server]` | running BrainOS (runtime server, console, plugin hosting) | + fastapi, uvicorn, brainos-adapter-sdk |
| `brainos-brainflow`, `brainos-bci2000` | ecosystem integrations (plugins) | brainos-adapter-sdk (+ brainflow) |

## 1. Integrate a device (adapter developer)

```bash
python -m venv .venv && . .venv/bin/activate
```
```bash
pip install brainos-adapter-sdk
```
```bash
brainos-adapter new my-amp --display "My amplifier"
```
```bash
pip install -e brainos-my-amp
```
```bash
brainos-adapter check my-amp
```

`new` writes a complete, installable plugin package that already works (a declared-synthetic
template signal) with `TODO` markers where your device I/O and metadata go. `check` runs it
exactly as BrainOS will: in the plugin host, in a separate process, with every declaration
and every chunk validated. Read [ADAPTER_SDK.md](ADAPTER_SDK.md) for the API, the rules,
and the isolation model; [`examples/adapters/brainos-example-adapter`](../examples/adapters/brainos-example-adapter)
is a fuller example (synthetic motor-imagery EEG with cues and markers).

Rules that matter most: declare only what you know (unknown units/modality stay unknown),
use your source's own timestamps in a declared clock domain, count samples in
`first_index` so losses are visible, raise `LinkLost` when the link drops. Plugins cannot
send anything to a device and cannot emit application commands.

## 2. Certify it

```bash
pip install brainos-certify
```
```bash
brainos-certify my-amp --duration 20 --out reports/
```

The report (JSON + Markdown) states the validation level reached. Software checks can reach
**adapter implementation**, or **protocol-tested** when you state the external reference
software that produced the data. **Hardware-tested** is only recorded from a signed operator
attestation and is shown as such; **human-participant validated** is never granted by
software. See [CERTIFICATION.md](CERTIFICATION.md) and [COMPATIBILITY.md](COMPATIBILITY.md).

## 3. Run BrainOS with the plugin (lab)

```bash
pip install "brainos[server]" brainos-my-amp
```
```bash
brainos-server
```

Open http://127.0.0.1:8000 → **Connect a source → Plugins**: the plugin is listed with its
validation result; choose the device, fill in its options, connect. The source row shows
`Plugin · <package>@<version> · isolated` and the declared modality. Everything downstream
(signal integrity, recording, pipeline, decoders, calibration, command output) works
unchanged. (From a repository checkout, `make setup && make run` does the same and also
installs the BrainFlow and BCI2000 integrations.)

## 4. Build an application (app developer)

```bash
pip install brainos
```

```python
import asyncio
from brainos.sdk import EventStream, NegotiationUpdate, is_event

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

The base `brainos` package is only the SDK and the event contracts — no server, no numpy.
Apps never name a device: they declare capabilities and adapt to what is granted. Decoded
commands (pointer, select / activate / cancel, text) reach an app only after the operator
authorizes it; until then negotiation says `not_authorized`. Use the SDK's `CommandGuard`
so stale commands never act and motion stops on revocation, disconnect or silence. See
[SDK.md](SDK.md) and [CONTROL_BRIDGE.md](CONTROL_BRIDGE.md); two complete reference apps
(continuous cursor, discrete menu) are in [`backend/examples/reference_app`](../backend/examples/reference_app).

## Versioning

- Adapter SDK API `1.0`: a plugin declares the API version it was written for; BrainOS
  accepts the same major version with a minor version ≤ its own and rejects others with a
  reason (never loads them).
- Event schema `1.3`: consumers accept the same major version; minor versions are additive.
- Packages follow semantic versioning; `brainos` is pre-1.0 (internal preview).
