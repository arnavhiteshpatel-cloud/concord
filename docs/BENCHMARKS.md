# Concord benchmarks

> Every number below was measured on the machine listed in the table, by this script. Regenerate on your own hardware with `make bench` (real-data rows need `make dataset model`).

Measured 2026-11-07 03:01 UTC with `python scripts/bench.py --seconds 10`.

| | |
|---|---|
| machine | `x86_64` · Linux-6.18.44-fc-v300-x86_64-with-glibc2.39 |
| cpu count | 4 |
| python | 3.12.3 |

## 1. Runtime pipeline capacity (in-process, no network)

Stamp + schema-validate + serialize + fan-out to N subscriber queues, single core, synchronous.

| event | subscribers | envelopes/s | µs/envelope |
|---|---:|---:|---:|
| intent.pointer | 1 | 89,996 | 11.1 |
| recording.frame (32x40) | 1 | 12,896 | 77.5 |
| intent.pointer | 8 | 72,712 | 13.8 |
| recording.frame (32x40) | 8 | 14,624 | 68.4 |

## 2. End-to-end over WebSocket (live server, Profile A streaming)

Latency = SDK receive wall clock - envelope `timestamp_ns` (runtime ingest), same machine. Includes JSON serialization, WebSocket, client-side JSON parse and full Pydantic validation in the Python SDK. Profile A emits ≈76 events/s (50 pointer + 25 frames + 1 telemetry).

| SDK clients | events/s per client | p50 ms | p95 ms | p99 ms | max ms | samples | delivery gaps | out-of-order | server pipeline p50/p99 µs |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | 76.1 | 1.19 | 1.68 | 2.09 | 22.88 | 761 | 0 | 0 | 275 / 564 |
| 8 | 76.1 | 2.22 | 5.55 | 7.04 | 10.16 | 6,089 | 0 | 0 | 281 / 564 |

## 3. Real recorded data replay (FALCON H1, DANDI 000954, Milestone 2)

File `sub-HumanPitt-held-in-calib_ses-19250108T111022.nwb` (176 channels, 20 ms bins, with behavior and the held-out decoder attached = 3 events per bin). In-process subscriber. *Timing error* = wall-clock time of delivery minus the recording-clock time scaled by speed, relative to the first bin (absolute value); *drift* = signed error at the last bin. 64x is the maximum speed: it measures throughput when replay is CPU-bound.

| speed | duration s | events/s | bins/s | recording s per s | timing error p50 / p99 / max ms | drift ms | pipeline p50 / p99 µs |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 1x | 10.0 | 150 | 50 | 1.00 | 0.67 / 1.36 / 5.55 | +1.08 | 68 / 219 |
| 8x | 5.0 | 1,200 | 400 | 8.00 | 0.65 / 1.39 / 5.44 | +1.06 | 52 / 180 |
| 64x | 2.1 | 9,584 | 3,194 | 63.88 | 0.63 / 8.70 / 14.99 | -0.59 | 31 / 146 |

Notes: numbers depend on the machine and its load; re-run on your own hardware. These are software-pipeline numbers (simulated devices and offline file replay) — they say nothing about any real implant's latency.
