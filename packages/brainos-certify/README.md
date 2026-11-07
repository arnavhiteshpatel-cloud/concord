# brainos-certify

Integration certification toolkit for BrainOS source plugins (adapter SDK API 1.x).

`brainos-certify` runs a plugin **exactly as BrainOS runs it** — in the adapter SDK's
out-of-process plugin host, over the binary IPC, with host-side validation — measures what it
delivers, and writes a JSON + Markdown report with an explicit validation level.

> **Software checks only.** A passing report is not hardware certification and not
> human-participant validation. The toolkit grants exactly one level by itself
> (`adapter_implementation`); `protocol_tested` rests on an operator statement,
> `hardware_tested` only on an operator-signed attestation it does not verify, and
> `human_participant_validated` is never set. Definitions: [docs/CERTIFICATION.md](../../docs/CERTIFICATION.md).

## Install

Depends only on `brainos-adapter-sdk`, `numpy` and `jsonschema` — BrainOS itself is optional.

```bash
pip install -e packages/brainos-adapter-sdk -e packages/brainos-certify
# optional runtime phase (negotiation + event-contract compliance through BrainOS):
pip install -e "backend" -e "packages/brainos-certify[runtime]"
```

The plugin must be importable by the interpreter that runs the plugin host (`--python`,
default: the one running `brainos-certify`); `--path DIR` adds `sys.path` entries for it.

## Use

```bash
brainos-certify example-mi-eeg                       # by brainos.sources entry point
brainos-certify my_pkg.plugin:MyPlugin --path src    # by module:Class (entry point unverified)
brainos-certify brainflow --device synthetic \
    --protocol-reference "BrainFlow 5.23 BoardShim SYNTHETIC_BOARD"
brainos-certify bci2000 --option port=20321 --option declare_synthetic=true
brainos-certify my-device --attestation att.json --attestation-public-key operator.pub
```

| Option | Meaning |
| --- | --- |
| `--device KEY`, `--option NAME=VALUE` | what to open (default: the first discovered device) |
| `--duration S` (20) | main acquisition length; `--reopen-seconds S` (2) after each reopen |
| `--rate-tolerance F` (0.02) | allowed \|measured / nominal − 1\| for rate and throughput |
| `--read-grace S` (5), `--start-timeout`, `--open-timeout`, `--kill-detect-limit S` (2) | hang / fault limits |
| `--no-runtime`, `--runtime-seconds S` (5) | the optional BrainOS phase |
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
cd packages/brainos-certify && pytest -q          # 87 tests, ~90 s (real plugin hosts)
ruff check . && ruff format --check . && mypy      # strict; needs the [dev] extra's stubs
```

`scripts/replay_bci2000_capture.py` replays the recorded BCI2000 App Connector capture over
UDP (looping, original timing) so the `bci2000` plugin can be certified without BCI2000;
`scripts/certify_broken_plugins.py` certifies BrainOS's deliberately broken test plugins and
tabulates which check catches each defect.
