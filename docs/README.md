# Concord documentation

Every document in this repository, grouped by what you want to do. If you are new, read the
first three rows in order.

## Start here

| Document | What it covers |
| --- | --- |
| [Getting started](GETTING_STARTED.md) | Step by step: install, a tour of the console, a simulated device and the communication board, real human recordings, a recorded decoder driving the board, a research session |
| [How Concord works](CONCEPTS.md) | The ideas in plain language: sources, data kinds, capabilities, decoders, command output, stopping safely |
| [User guide](USER_GUIDE.md) | Every button, field, state and message of the console and the communication board; the configuration file and the `concord` command |
| [FAQ](FAQ.md) | Short answers to common questions |
| [Glossary](GLOSSARY.md) | The terms used in the console and these documents |
| [Troubleshooting](TROUBLESHOOTING.md) | Symptoms and fixes |
| [Installing on a Mac](INSTALL_MAC.md) | The desktop app and the Python installation in detail; configuration |

## Using Concord in a lab

| Document | What it covers |
| --- | --- |
| [Connect your equipment](CONNECT_YOUR_EQUIPMENT.md) | Step by step for LSL, Open Ephys, BrainFlow, BCI2000 and your own device; rehearsing without hardware; troubleshooting |
| [Lab setup](LAB_SETUP.md) | Which adapter for which acquisition system, network layout and ports, installation, a research session step by step, data handling |
| [Lab guide](LAB_GUIDE.md) | Connecting LSL and Open Ephys sources, processing pipelines, calibrating a decoder, routing commands to applications |
| [First lab session](FIRST_LAB_SESSION.md) | A validation protocol for the first session with real equipment (a protocol, not a result) |
| [Hardware validation](HARDWARE_VALIDATION.md) | Verifying Concord against your acquisition software's own recording with `concord-hwval` |
| [Open Ephys](OPEN_EPHYS.md) | How the Open Ephys GUI ZMQ Interface is read, setup and limitations |
| [Ecosystems: BrainFlow and BCI2000](ECOSYSTEMS.md) | The two plugins: what each interface provides and how it is mapped |
| [Applications](APPLICATIONS.md) | What applications receive, the communication board's input methods, safe states |
| [Control bridge](CONTROL_BRIDGE.md) | How decoded output becomes an authorized command, and every way to stop it |
| [Security](SECURITY.md) | What is and is not protected; data handling and deletion |

## Data and results

| Document | What it covers |
| --- | --- |
| [Datasets](DATASETS.md) | The public datasets, how they are verified, licenses and known pitfalls |
| [Decoding results: FALCON H1](DECODING.md) | Offline decoding of recorded intracortical data, with controls (generated) |
| [Human ECoG](ECOG.md) and [ECoG decoding results](ECOG_DECODING.md) | The AJILE12 integration and offline movement decoding (generated) |
| [Cursor + click](CURSOR_CLICK.md) | Kalman cursor and click decoders on the T15 recordings (generated) |
| [Neural-to-communication](NEURAL_COMMUNICATION.md) | Recorded data selecting words on the communication board, end to end |
| [Validation levels](VALIDATION_LEVELS.md) | What each component has and has not been validated for |
| [Compatibility](COMPATIBILITY.md) | Every integration, the level its evidence supports, the evidence ([certification reports](compatibility/)) |
| [Benchmarks](BENCHMARKS.md), [live benchmarks](BENCHMARKS_LIVE.md), [scale benchmarks](BENCHMARKS_SCALE.md), [performance](PERFORMANCE.md) | Measured throughput, latency and loss, and what limits them |

## Building on Concord

| Document | What it covers |
| --- | --- |
| [Developers](DEVELOPERS.md) | Installing and using the SDKs, the certification toolkit and the server as a developer |
| [SDK](SDK.md) | The Python and TypeScript SDKs for applications |
| [Adapter SDK](ADAPTER_SDK.md) | Writing a source plugin for an acquisition system |
| [Certification](CERTIFICATION.md) | `concord-certify`: checking a source plugin |
| [Decoder SDK](DECODER_SDK.md) | Bringing your own decoder or model file |
| [Guided demos](DEMOS.md) | Terminal walkthroughs from a source installation |
| [Contributing](../CONTRIBUTING.md) | Development setup, rules and pull requests |

## Design and project records

| Document | What it covers |
| --- | --- |
| [Product](../PRODUCT.md) | Who Concord is for, the problem, non-goals |
| [Architecture](../ARCHITECTURE.md) | The contracts: adapters, capabilities, event envelope, provenance, runtime, API (normative) |
| [MVP specification](../MVP_SPEC.md) | The first vertical slice's requirements and acceptance tests |
| [Limitations](../LIMITATIONS.md) | What does not work or is not real |
| [Roadmap](../ROADMAP.md) | What comes next |
| [Changelog](../CHANGELOG.md) and [release notes](releases/) | What changed in each version |
| Milestone plans: [2](MILESTONE2_PLAN.md), [3](MILESTONE3_PLAN.md), [4](MILESTONE4_PLAN.md), [5](MILESTONE5_PLAN.md) | The audit and plan written at the start of each milestone (historical records) |
| [Security policy](../SECURITY.md) | How to report a vulnerability |
