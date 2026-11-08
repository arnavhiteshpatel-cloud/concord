# Contributing to Concord

Thank you for helping. Concord is research software for brain-computer interfaces, so a few
rules matter more here than in most projects: they keep it honest about what has and has not
been validated, and they keep it safe. Please read them before opening a pull request.

## Ways to contribute

| You want to… | Do this |
| --- | --- |
| Report a problem | [Open a bug report](https://github.com/arnavhiteshpatel-cloud/brainos/issues/new?template=bug_report.yml). Attach the support report from **Advanced → Support report** (or `concord doctor`): it contains no neural or personal data. |
| Ask how to do something | [Ask a question](https://github.com/arnavhiteshpatel-cloud/brainos/issues/new?template=question.yml), after checking the [FAQ](docs/FAQ.md) and [troubleshooting](docs/TROUBLESHOOTING.md). |
| Share a hardware-validation result | [Submit a `concord-hwval` report](https://github.com/arnavhiteshpatel-cloud/brainos/issues/new?template=hardware_validation.yml) ([protocol](docs/HARDWARE_VALIDATION.md)). |
| Connect a new acquisition system | Write a source plugin with the [adapter SDK](docs/ADAPTER_SDK.md) and check it with [`concord-certify`](docs/CERTIFICATION.md). Plugins live in their own package; the core does not need to change. |
| Bring your own decoder | Use the [decoder SDK](docs/DECODER_SDK.md). |
| Write an application | Use the [Python or TypeScript SDK](docs/SDK.md). |
| Change Concord itself | Read the rest of this page, then open a pull request. |

Never attach neural recordings, participant information, credentials or API tokens to an
issue or a pull request.

## Development setup

You need [uv](https://docs.astral.sh/uv/) (it installs Python 3.12) and Node 20 or newer.

```bash
git clone https://github.com/arnavhiteshpatel-cloud/brainos.git
```
```bash
cd concord
```
```bash
make setup
```
```bash
make dev
```

`make dev` runs the server with reload on http://127.0.0.1:8000 and the console with hot
reload on http://127.0.0.1:5173. The [developer guide](docs/DEVELOPERS.md) explains the
packages and SDKs; [ARCHITECTURE.md](ARCHITECTURE.md) is the normative description of the
contracts.

## Before you open a pull request

```bash
make lint test
```

This runs ruff, mypy (strict) and TypeScript checks, the backend and package test suites and
the console tests. For changes to the console or the communication board also run the
browser test (`make e2e-setup` once, then `make e2e`). For changes to acquisition adapters
also run `make test-hwval` (Linux x86_64; it downloads LabRecorder and the Open Ephys GUI).

Every bug fix needs a regression test, and every new contract rule needs a test with
malformed input. Do not claim something works unless you ran it.

## Rules that are not negotiable

These come from [DEVELOPMENT.md](DEVELOPMENT.md), which lists them in full.

1. **Read-only.** Concord never sends commands, configuration or stimulation to a device.
   Adapters only receive data.
2. **No claims beyond the evidence.** Do not describe software or protocol tests as hardware
   or human validation; keep [VALIDATION_LEVELS.md](docs/VALIDATION_LEVELS.md) and
   [LIMITATIONS.md](LIMITATIONS.md) current. Never name an implant or device manufacturer as
   supported.
3. **Never fabricate numbers.** Decoding results come from the evaluation scripts run on real
   files; performance numbers come from the benchmark scripts.
4. **No data in git.** Datasets are downloaded and verified by SHA-256, never committed
   (`data/` is ignored).
5. **No leakage.** A decoder is never scored on, or replayed on, the data it was trained on.
6. **Provenance stays honest.** Recorded or simulated activity is never presented as live
   intent, and decoded commands reach an application only after the operator authorizes it.
7. **No placeholder features.** If something is not implemented, the console does not show a
   control for it.

## Changing a contract

Contracts are versioned. Edit `backend/src/concord/contracts/`, bump `SCHEMA_VERSION` (minor
for additive changes, major for breaking ones), run `make schema`, update
`frontend/src/sdk/types.ts` and ARCHITECTURE.md §4, and add valid and malformed tests.

## Pull requests

Fill in the pull request template: what changed, why, how you tested it, and what it means
for the validation level of the affected components. Keep each pull request to one purpose;
explain in it why any new dependency is needed.
