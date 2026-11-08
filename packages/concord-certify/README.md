# concord-certify

Integration certification toolkit for Concord source plugins (adapter SDK API 1.x).

`concord-certify` runs a plugin **exactly as Concord runs it** — in the adapter SDK's
out-of-process plugin host, over the binary IPC, with host-side validation — measures what it
delivers, and writes a JSON + Markdown report with an explicit validation level.

> **Software checks only.** A passing report is not hardware certification and not
> human-participant validation. The toolkit grants exactly one level by itself
> (`adapter_implementation`); `protocol_tested` rests on an operator statement,
> `hardware_tested` only on an operator-signed attestation it does not verify, and
> `human_participant_validated` is never set. Definitions: [docs/CERTIFICATION.md](../../docs/CERTIFICATION.md).

## Install

Depends only on `concord-adapter-sdk`, `numpy` and `jsonschema` — Concord itself is optional.

```bash
pip install -e packages/concord-adapter-sdk -e packages/concord-certify
# optional runtime phase (negotiation + event-contract compliance through Concord):
pip install -e "backend" -e "packages/concord-certify[runtime]"
```

The plugin must be importable by the interpreter that runs the plugin host (`--python`,
default: the one running `concord-certify`); `--path DIR` adds `sys.path` entries for it.

## Use

```bash
concord-certify example-mi-eeg                       # by concord.sources entry point
concord-certify my_pkg.plugin:MyPlugin --path src    # by module:Class (entry point unverified)
concord-certify brainflow --device synthetic \
    --protocol-reference "BrainFlow 5.23 BoardShim SYNTHETIC_BOARD"
concord-certify bci2000 --option port=20321 --option declare_synthetic=true
concord-certify my-device --attestation att.json --attestation-public-key operator.pub
```

| Option | Meaning |
| --- | --- |
| `--device KEY`, `--option NAME=VALUE` | what to open (default: the first discovered device) |
| `--duration S` (20) | main acquisition length; `--reopen-seconds S` (2) after each reopen |
| `--rate-tolerance F` (0.02) | allowed \|measured / nominal − 1\| for rate and throughput |
| `--read-grace S` (5), `--start-timeout`, `--open-timeout`, `--kill-detect-limit S` (2) | hang / fault limits |
| `--no-runtime`, `--runtime-seconds S` (5) | the optional Concord phase |
| `--protocol-reference TEXT` | operator statement for `protocol_tested` |
| `--attestation F [--attestation-signature F.sig] --attestation-public-key K.pub` | operator hardware attestation (Ed25519) |
| `--out DIR`, `--name STEM` | writes `STEM.certify.json` and `STEM.certify.md` |
| `--print-schema` | the report's JSON Schema |

Exit code: **0** only if `adapter_implementation` was achieved, **1** otherwise, **2** for
usage errors.

## What it checks

29 checks with stable ids (`manifest.*`, `metadata.*`, `timing.*`, `integrity.*`,
`reconnect.*`, `performance.*`, `runtime.*`), each with status `pass` / `fail` / `warn` /
`not_run`, a one-line reason and the measured evidence. Full list, thresholds and the run
sequence: [docs/CERTIFICATION.md](../../docs/CERTIFICATION.md). Results for the plugins in this
repository: [docs/COMPATIBILITY.md](../../docs/COMPATIBILITY.md).

## Develop

```bash
cd packages/concord-certify && pytest -q          # 87 tests, ~90 s (real plugin hosts)
ruff check . && ruff format --check . && mypy      # strict; needs the [dev] extra's stubs
```

`scripts/replay_bci2000_capture.py` replays the recorded BCI2000 App Connector capture over
UDP (looping, original timing) so the `bci2000` plugin can be certified without BCI2000;
`scripts/certify_broken_plugins.py` certifies Concord's deliberately broken test plugins and
tabulates which check catches each defect.
