# BrainOS benchmarks

> These numbers were measured in a 4-vCPU Linux cloud container during development, **not on an
> M4 MacBook Pro**. Run `make bench` on your machine to regenerate this file with your numbers.

Measured 2026-11-07 01:43 UTC with `python scripts/bench.py --seconds 10`.

| | |
|---|---|
| machine | `x86_64` · Linux-6.18.44-fc-v300-x86_64-with-glibc2.39 |
| cpu count | 4 |
| python | 3.12.3 |

## 1. Runtime pipeline capacity (in-process, no network)

Stamp + schema-validate + serialize + fan-out to N subscriber queues, single core, synchronous.

| event | subscribers | envelopes/s | µs/envelope |
|---|---:|---:|---:|
| intent.pointer | 1 | 92,459 | 10.8 |
| recording.frame (32x40) | 1 | 13,242 | 75.5 |
| intent.pointer | 8 | 113,831 | 8.8 |
| recording.frame (32x40) | 8 | 13,852 | 72.2 |

## 2. End-to-end over WebSocket (live server, Profile A streaming)

Latency = SDK receive wall clock - envelope `timestamp_ns` (runtime ingest), same machine. Includes JSON serialization, WebSocket, client-side JSON parse and full Pydantic validation in the Python SDK. Profile A emits ≈76 events/s (50 pointer + 25 frames + 1 telemetry).

| SDK clients | events/s per client | p50 ms | p95 ms | p99 ms | max ms | samples | delivery gaps | out-of-order | server pipeline p50/p99 µs |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | 76.1 | 1.07 | 1.42 | 1.74 | 6.26 | 761 | 0 | 0 | 255 / 586 |
| 8 | 76.1 | 2.09 | 5.25 | 6.87 | 9.44 | 6,088 | 0 | 0 | 254 / 521 |

Notes: numbers depend on the machine and its load; re-run on your own hardware. These are software-pipeline numbers with simulated devices — they say nothing about any real implant's latency.
