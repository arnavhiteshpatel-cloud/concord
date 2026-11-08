# Changelog

Concord is research software in active development. Versions follow
[semantic versioning](https://semver.org/) while below 1.0: a minor version may change
interfaces. Each entry links to the documents that describe the change in depth.
Every release is software- and protocol-tested only: **no version has been used with
acquisition hardware or with a participant** ([validation levels](docs/VALIDATION_LEVELS.md)).

## Unreleased

**The project is now called Concord.** Every name changed with it; nothing else did.

- Python import package `concord`, command `concord`; the main distribution is
  `concordos` (`pip install "concordos[lab]"`), because `concord` is taken on PyPI.
- Companion packages: `concord-adapter-sdk`, `concord-decoder-sdk`, `concord-certify`,
  `concord-hwval`, `concord-brainflow`, `concord-bci2000` and the two examples.
- Plugin entry-point groups are `concord.sources` and `concord.decoders`: an existing
  third-party plugin must re-declare its entry point under the new group to be found.
- Environment variables start with `CONCORD_`; config and data live under `concord`
  directories; recordings use the `.concord.jsonl` extension; built-in adapter IDs start
  with `concord.`; `provenance.model_origin` for a model the runtime trained is `"concord"`.
- Desktop downloads are `Concord-macos-arm64.dmg` and `Concord-linux-x86_64.tar.gz`.
- Certification reports for the three bundled plugins were re-run on the renamed sources
  (same results and levels).

## 0.3.0 — Milestone 5 (research preview) — first downloadable release

The first release with a desktop app download ([release notes](docs/releases/v0.3.0.md)).

**Human data, decoding and communication**

- Recorded intracortical data from a participant controlling a cursor and clicking (T15,
  Dryad, CC0) replays through Concord; Concord's own Kalman cursor decoder and click
  decoder, trained only on earlier blocks, drive the communication board end to end in a
  browser test. Open loop only ([CURSOR_CLICK.md](docs/CURSOR_CLICK.md),
  [NEURAL_COMMUNICATION.md](docs/NEURAL_COMMUNICATION.md)).
- Human ECoG (AJILE12, DANDI 000055) as verified slices, with a raw-voltage importer, ECoG
  preprocessing and a movement-vs-rest decoder evaluated on held-out sessions ([ECOG.md](docs/ECOG.md)).
- Decoder SDK: bring your own decoder (ONNX, scikit-learn via skops, TorchScript /
  safetensors, or a plugin) run in an isolated process, with compatibility rules
  ([DECODER_SDK.md](docs/DECODER_SDK.md)).

**Using it in a lab**

- Desktop app for macOS (`.dmg`) and a Linux bundle; the `concord` command (start, stop,
  status, doctor, config, dataset, reproduce) ([INSTALL_MAC.md](docs/INSTALL_MAC.md),
  [LAB_SETUP.md](docs/LAB_SETUP.md)).
- Research sessions with a session log, export bundles and `concord reproduce`; safe stop;
  crash-safe recordings; retention and deletion; a support report without neural or
  personal data ([SECURITY.md](docs/SECURITY.md)).
- Communication board v2: five input methods (pointer and click, pointer with dwell
  selection, directional navigation, direct selection, scanning) chosen from what the source
  provides, and an opt-in desktop control bridge
  ([APPLICATIONS.md](docs/APPLICATIONS.md)).
- Compatibility registry: what each integration has been validated to, derived from the
  evidence ([COMPATIBILITY.md](docs/COMPATIBILITY.md)).
- Performance: 1024 channels at 30 kHz sustained for 10 minutes without loss on the test
  machine ([PERFORMANCE.md](docs/PERFORMANCE.md)).

**Verifying acquisition: `concord-hwval`**

- A toolkit that compares a Concord recording with the recording the acquisition system's
  own software made at the same time (LabRecorder XDF, Open Ephys Record Node) and writes a
  PASS / FAIL / INCONCLUSIVE report, plus the laboratory protocol for a hardware
  verification ([HARDWARE_VALIDATION.md](docs/HARDWARE_VALIDATION.md)). Exercised against
  the real LabRecorder and Open Ephys GUI with software sources.

**Fixes and changes found by that toolkit**

- Open Ephys: a sample-number reset while acquisition continues (the GUI's File Reader
  looping) no longer reconnects and loses about 0.7 s of data; the discontinuity stays
  visible ([OPEN_EPHYS.md](docs/OPEN_EPHYS.md)).
- Recording limits are configurable (default 300 s / 200 MiB with raw frames, up to 24 h /
  100 GiB); a recording stops cleanly when free disk space runs low.
- Recording headers keep the source's metadata at the start of a recording and state what
  their timestamps can reconstruct. Recordings with these fields need Concord 0.3.0 or later
  to open.

**Contract 1.4** (additive): navigation intents, `control.state`, `provenance.model_origin`,
the `spike_band_power` feature ([ARCHITECTURE.md](ARCHITECTURE.md)).

## Milestone 4 — integration ecosystem

- Source plugins through a public adapter SDK, each run in its own process
  ([ADAPTER_SDK.md](docs/ADAPTER_SDK.md)); BrainFlow and BCI2000 plugins
  ([ECOSYSTEMS.md](docs/ECOSYSTEMS.md)).
- Control bridge: decoded pointer / select / activate / cancel / text commands reach only
  the applications the operator authorizes, with stop paths
  ([CONTROL_BRIDGE.md](docs/CONTROL_BRIDGE.md)).
- Certification toolkit `concord-certify` ([CERTIFICATION.md](docs/CERTIFICATION.md)).
- Console redesigned as one session screen; the communication board opens as its own
  participant screen.

## Milestone 3 — live acquisition

- Live sources over Lab Streaming Layer and the Open Ephys ZMQ Interface
  ([LAB_GUIDE.md](docs/LAB_GUIDE.md), [OPEN_EPHYS.md](docs/OPEN_EPHYS.md)).
- Streaming processing pipeline, calibration of decoders from recordings, the command
  router, a center-out cue task ([BENCHMARKS_LIVE.md](docs/BENCHMARKS_LIVE.md)).

## Milestone 2 — genuine human intracortical data

- Recorded human intracortical data (FALCON H1, DANDI 000954) replayed through the
  unchanged runtime, every file verified by SHA-256 ([DATASETS.md](docs/DATASETS.md)).
- A baseline decoder evaluated without leakage, with controls
  ([DECODING.md](docs/DECODING.md)).

## Milestone 1 — MVP vertical slice

- Contracts (capabilities, event envelope, provenance), simulated devices (Simulated
  Profile A/B), the runtime, REST + WebSocket API, Python and TypeScript SDKs, the operator
  console and the communication board ([PRODUCT.md](PRODUCT.md),
  [ARCHITECTURE.md](ARCHITECTURE.md), [MVP_SPEC.md](MVP_SPEC.md)).
