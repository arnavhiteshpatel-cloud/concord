# Concord — Product Specification

> Internal project name: **Concord**. Not a public brand. This document is the
> source of truth for *what* we are building and *for whom*. See
> [ARCHITECTURE.md](ARCHITECTURE.md) for *how*.

## One-line summary

Concord is a hardware-agnostic, read-only runtime and SDK that lets software
consume standardized, capability-negotiated events from implanted
brain-computer interfaces (BCIs) without being rewritten for each manufacturer.

## The problem

Every implanted-BCI program today builds a vertical stack: electrode → device
firmware → proprietary decoder → bespoke application. Consequences:

1. **Applications are not portable.** A communication app built for one implant
   must be rewritten for another, because event formats, timing semantics,
   available signals, and decoder outputs differ.
2. **Research software is not reusable.** Labs re-implement acquisition,
   buffering, replay, and visualization for each rig and dataset.
3. **Provenance is ambiguous.** It is often unclear whether a "cursor
   movement" came from a real-time neural decoder, a recorded behavioral label,
   or a simulation. That ambiguity is dangerous in research and unacceptable in
   anything that will eventually face regulators.
4. **No capability contract.** Applications assume features (continuous
   pointer control, text entry, raw channels) that a given device may not
   provide, and fail in undefined ways.

## Value proposition

| For | Concord provides |
| --- | --- |
| Application developers | One typed, versioned event API and SDK. Declare the capabilities you need; get them or get an explicit rejection. |
| Implant manufacturers | One adapter contract to implement. A device that implements it immediately runs the Concord application ecosystem. |
| Research labs | Recording and replay with first-class provenance, a diagnostics surface, and a path to running offline datasets through the same pipeline as live devices. |

## Users (initial audience)

1. **BCI research engineers** in academic labs who build closed-loop
   experiments and need reusable infrastructure.
2. **Assistive-technology / application developers** who want to target
   multiple neural interfaces without per-device forks.
3. **Device-side engineers at implant companies** evaluating whether a common
   application layer is worth implementing an adapter for.
4. **Technical investors / advisors** evaluating whether the abstraction is
   real and the team can execute.

## Core use cases (v1)

1. *As an application developer*, I connect to the runtime, declare required
   and optional capabilities, and receive only standardized events I was
   granted.
2. *As an operator*, I connect a device, pause/resume streaming, switch
   devices, and inspect live diagnostics (rates, latency, drops, errors).
3. *As an application*, I keep working after a device switch, adapting to the
   newly negotiated capability set, with no code change.
4. *As a researcher*, I record a session and replay it through the identical
   pipeline, with replayed events clearly marked as replayed.
5. *As a device engineer*, I implement one adapter (read native packets →
   normalize to drafts) and the runtime handles validation, sequencing,
   routing, and diagnostics.

## Non-goals (explicit)

- **No stimulation or any write path to a device.** v1 is read-only by
  architecture: the adapter contract has no write/stimulate operation.
- **No medical decisions, diagnosis, or treatment.** Concord is not a medical
  device and makes no clinical claims.
- **No patient-facing clinical deployment.** The demo communication board is a
  demonstration application only.
- **No real neural decoding in v1.** We ship no decoder model. Intents in the
  demo are *simulated* and labelled as such in every event.
- **No commercial implant compatibility.** We have no proprietary device
  access. Simulated profiles are generic and do not represent any company's
  product.
- **Not an EEG consumer app, not a visual mockup, not an AI wrapper.**

## Competitive differentiation

The landscape (stated at the level of general public knowledge, not
competitive intelligence):

- **Vertically integrated implant companies** ship their own closed software
  stacks. Concord is the neutral layer between devices and apps.
- **Research acquisition frameworks** (e.g. general-purpose BCI/EEG research
  toolkits and streaming protocols) solve acquisition and streaming of
  time-series, but are not designed around *application-facing intent events*,
  *capability negotiation*, or *provenance as a contract*.
- **Data standards** for neurophysiology storage target archival and sharing,
  not real-time application APIs. Concord replay is designed to ingest such
  datasets, not replace them.

Concord differentiators:

1. **Capability negotiation** with explicit rejection — not "best effort".
2. **Provenance in the schema**: raw signal vs. behavioral label vs. simulated
   intent vs. model-decoded intent is a validated field, not documentation.
3. **Adapter contract** that cleanly separates device-native packets from
   application events.
4. **Read-only by construction** for v1, which simplifies the safety story.
5. **Same pipeline for live, simulated, and replayed data.**

## What "done" looks like for the MVP

See [MVP_SPEC.md](MVP_SPEC.md). In short: start the app, connect simulated
device A, watch standardized events, control a communication board, switch to
simulated device B, keep using the same board unchanged, and inspect real
diagnostics and test results.
