# BrainOS live-acquisition benchmarks (Milestone 3)

> Measured on the machine below by `scripts/bench_live.py`. Publishers run in a separate process and speak real LSL (liblsl) or the Open Ephys ZMQ wire format; **no hardware was involved**. Synthetic signals are declared synthetic; FALCON H1 is real human data streamed as *prerecorded*. Re-run on your own machine: `make bench-live`.

Measured 2026-11-07 05:56 UTC with `python scripts/bench_live.py --seconds 10 --soak 120`.

| | |
|---|---|
| machine | `x86_64` · Linux-6.18.44-fc-v310-x86_64-with-glibc2.39 |
| cpu count | 4 |
| python | 3.12.3 |
| liblsl | git:d7f892d78a9ddad8f55cdd43ca4a35bd7787ee89/branch:refs/tags/v1.18.0.b6/build:Release/compiler:GNU-11.4.0/link:SHARED |

## 1. LSL broadband ephys -> spike-band threshold crossings (20 ms bins)

Synthetic 30 kHz float32 stream. *Acq->feature latency* is defined in the script docstring (LSL clock, same host; a bin cannot be emitted before its last sample arrives). CPU = runtime process (adapter + runtime + pipeline), % of one core.

| channels | samples/s/ch received | gaps / missing | features/s | acq->feature p50 / p99 / max ms | pipeline µs/input p50 / p99 | dropped inputs | CPU % |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 32 | 29,998 | 0 / 0 | 50.0 | 5.7 / 9.6 / 14.3 | 618 / 2,453 | 0 | 22 |
| 96 | 29,997 | 0 / 0 | 50.0 | 8.8 / 14.3 / 19.1 | 1,325 / 6,057 | 0 | 47 |

## 2. Open Ephys ZMQ -> spike-band threshold crossings

Synthetic 30 kHz stream, 1024-sample blocks (one ZMQ message per channel per block, as the plugin sends). Open Ephys sample numbers are not on a clock shared with this host, so latency is reported from runtime ingest of a block to the derived feature (pipeline queueing + processing).

| channels | samples/s/ch | missed msgs / incomplete blocks / malformed | features/s | ingest->feature p50 / p99 ms | pipeline µs/input p50 / p99 | dropped inputs | CPU % |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 32 | 30,002 | 0 / 0 / 0 | 50.1 | 4.1 / 7.1 | 1,595 / 3,704 | 0 | 22 |
| 64 | 29,998 | 0 / 0 / 0 | 50.0 | 7.3 / 11.2 | 2,712 / 4,301 | 0 | 40 |

## 3. FALCON H1 over LSL (real data, prerecorded) -> decoder -> router -> command

Block 19250108T111022 streamed at 1x (50 bins/s, 176 units) with a ridge decoder trained on block 19250108T110520 and the command router on. Latency: LSL stamp of the bin -> `intent.pointer` (decoded_intent) ingested.

| commands/s | bin->command p50 / p99 / max ms | pipeline µs/bin p50 / p99 | gaps | dropped inputs | CPU % |
|---:|---:|---:|---:|---:|---:|
| 50.0 | 3.8 / 6.6 / 7.1 | 143 / 255 | 0 | 0 | 7 |

## 4. Reconnect under load (LSL, 32 ch @ 30 kHz, pipeline running)

The publisher process is killed, then restarted ~2 s later with the same `source_id`. *Detect* = kill -> runtime state `reconnecting`; *recover* = restart -> frames flowing again (includes the publisher's own start-up and LSL resolution).

| detect s | recover s | final state | reconnects | pipeline survived |
|---:|---:|---|---:|---|
| 0.01 | 1.03 | streaming | 1 | yes |

## 5. Soak: 120 s, LSL 32 ch @ 30 kHz + behavior stream, spike-band pipeline

| seconds | features / expected | gaps / missing samples | dropped inputs | errors | acq->feature p50 / p99 ms | RSS start -> end MB | ts regressions | invalid |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 120 | 6,000 / 6,000 | 0 / 0 | 0 | 0 | 5.5 / 8.9 | 366 -> 366 | 0 | 0 |

Notes: software/protocol measurements on one host. They do not characterize any amplifier, implant or network, and say nothing about closed-loop control performance.
