# Concord performance at scale (Milestone 5, workstream E)

What limits Concord as channel counts grow, which alternatives were measured, what was changed,
what was deliberately not changed, and the limits on the measurement machine.

Every number here comes from `scripts/bench_scale.py` (`make bench-scale`): the full report is
[BENCHMARKS_SCALE.md](BENCHMARKS_SCALE.md); raw results are in `docs/perf/bench_scale_before.json`
(code at 6b82e05) and `docs/perf/bench_scale_after.json` (this branch), and the before/after
tables in §5 are printed by
`python scripts/bench_scale.py --compare docs/perf/bench_scale_before.json docs/perf/bench_scale_after.json`.
All streams are benchmark-generated synthetic data (declared synthetic over LSL) and all
decoders are random-weight decoders made by the benchmark: these are software timings, not
decoding results, and they say nothing about any implant.

## 1. Summary

- **The bottleneck was the representation of raw samples, not the signal processing.** Before
  this work, one 10 ms chunk of 1024 channels at 30 kHz cost 38.4 ms of CPU in the runtime
  (adapter `normalize` 8.2 ms, envelope validation and JSON 22.9 ms, pipeline 7.3 ms) — almost
  four cores' worth for one second of data — of which the DSP itself (scipy) is about 4 ms. The
  same chunk now costs 5.1 ms (7.5x less) when no client subscribes to raw frames, and 13.1 ms
  (ingest with serialization for one raw subscriber, plus normalize and pipeline) when one does.
- **Sustained without loss on this 4-vCPU machine (one runtime process, one core):** raw
  broadband 30 kHz up to **1024 channels** (the contract's maximum for `recording.frame`) with
  the full chain spikeband -> decoder -> router -> SDK app, including a **600 s soak at 1024
  channels** (30,004 of 30,000 expected bins, no gaps, no drops, flat RSS, runtime at 75% of a
  core, bin -> command p99 34.0 ms / max 85.2 ms); 1 kHz raw up to 1024 channels at 14% of a
  core; spike-count features up to **4096 channels at 100 Hz** at 13% of a core (bin -> command
  p99 10.5 ms). Before: raw 30 kHz worked at 64 channels; at 256 channels the runtime's memory
  grew past 2.5 GB within 17 s and was stopped.
- **No native code was added.** The alternatives that won were removing work (no `tolist`, no
  per-value validation, no JSON nobody reads) and an existing compiled library (orjson). A native
  SOS filter (numba / C prototypes, 2.9x faster than scipy at 1024 channels) is measured but not
  justified while raw signal is capped at 1024 channels (§4, §6).
- Measured robustness defects at scale were fixed: the event loop starved under overload,
  count-bounded queues grew to gigabytes, raw frames at 256+ channels exceeded the Python SDK's
  8 MiB message limit, and WebSocket compression made a raw-signal viewer cost more than the
  rest of the runtime.

## 2. Method

- **Processes** (the deployment shape): an LSL publisher (`scripts/bench_scale.py _pub-*`, a
  pre-generated looped buffer so the publisher costs only the LSL push), the runtime server
  (`python -m concord.server`), and the SDK application (the benchmark, Python SDK over the
  WebSocket); raw-signal viewers run in their own process. CPU and RSS are read per process
  from `/proc`.
- **Latency** is measured at the SDK app after it has received and validated the event: LSL
  clock now minus the event's `device_timestamp_ns` (the LSL time of the last sample of the
  bin), so it includes transport, adapter polling (5 ms), validation, DSP, decoder, router,
  WebSocket and SDK parsing. Same host, one monotonic clock.
- **Before/after**: the same benchmark script was run against the 6b82e05 sources installed in a
  separate virtualenv with the same Python (3.12.3) and identical dependency versions
  (constraints frozen from the branch's environment).
- **The machine was shared** with other workloads (load averages are printed with every run;
  the 1-minute load ranged from below 1 to above 11 on 4 vCPUs during these runs). Throughput and loss
  results were stable across repeated runs; tail latencies are the most sensitive to this.
- A watchdog stops any runtime whose RSS exceeds 2.5 GB (the host is shared); such cells are
  reported as failures with the time at which the limit was reached.
- docs/BENCHMARKS.md and docs/BENCHMARKS_LIVE.md were generated before these changes (by their
  own scripts) and were not regenerated here.

## 3. Bottlenecks measured

Per 10 ms chunk of 30 kHz float32 LSL data, in-process, real code paths (report §1, code at
6b82e05):

| channels | adapter normalize (`tolist`) | runtime ingest (validate + JSON) | pipeline (`np.asarray` + DSP) | total | share of one core |
|---:|---:|---:|---:|---:|---:|
| 64 | 235 µs | 1,192 µs | 1,003 µs | 2,431 µs | 24% |
| 256 | 1,392 µs | 6,947 µs | 2,319 µs | 10,658 µs | 107% |
| 1024 | 8,200 µs | 22,902 µs | 7,268 µs | 38,370 µs | 384% |

Per value at 1024 channels: the adapter's `normalize` (`astype` + `tolist`) 26.7 ns (above),
pydantic `list[list[FiniteFloat]]` validation 16.9 ns, pydantic JSON 39.2 ns,
`np.asarray(list)` in the pipeline 19.1 ns (report §2) — while
the whole `SignalChain` costs 3.9 ms per 1024-channel chunk (bandpass 2.5 ms, CAR 0.5 ms,
threshold crossings + binning 0.7 ms).

Defects that only appear at scale (report §4, §8, §2.5; before = 6b82e05):

1. **Event-loop starvation.** When acquisition outpaces processing, `LSLAdapter.read()` returns
   immediately (data is always waiting) and the runtime pump never yields: the pipeline task,
   WebSocket senders and REST all stop. Measured: REST and new WebSocket handshakes time out.
2. **Count-bounded queues are not memory-bounded.** The pipeline input queue (4096 events) and
   subscriber queues (2048 events) held list-of-lists frames; a starved pipeline grew the
   runtime past 2.5 GB in 16 s at 256 channels (an earlier run without the benchmark's RSS
   watchdog was killed by the kernel's OOM killer).
3. **Raw frames exceeded the SDK's message limit.** Frames of up to 2000 samples at 256+ channels
   are larger than the Python SDK's 8 MiB WebSocket limit: raw-signal clients were disconnected
   (`1009 message too big`).
4. **WebSocket permessage-deflate** (uvicorn's and the websockets client's default) compresses
   every raw frame at ~16 MB/s: 11.5 ms of CPU for one 64 x 150 frame, 94.9 ms for one
   256 x 300 frame (report §2.5). Before (all four defects and the costs above combined), one
   raw viewer at 64 channels kept the runtime at 83% of a core and 1.7 GB RSS, its REST
   unresponsive, and the command app received no features.

## 4. Alternatives compared (head to head, with correctness checks)

Decision rule, set before implementing: **adopt an alternative only if it is at least 2x faster
on a bottleneck that limits a realistic workload** (up to 1024 raw channels at 30 kHz with the
full chain; up to 4096 feature channels; an operator console subscribed to everything), keeps
outputs identical (or within a documented tolerance), and works without a compiler.

| bottleneck (1024 ch, per value unless noted) | today | alternative | measured | correctness | decision |
|---|---|---|---|---|---|
| sample representation (adapter -> runtime -> pipeline) | `tolist` + pydantic list validation + `np.asarray` (~60 ns) | keep the numpy array; validate with numpy | 1.13 ns to validate an array payload (owned copy included) vs 16.9 ns; `tolist` and `np.asarray` removed | identical accept/reject and error messages (invalid arrays are re-validated by the list path); JSON Schema unchanged | **adopted** |
| JSON for every envelope at ingest | 39.2 ns (+ `tolist`) for every frame, even with no consumer | serialize lazily, once, shared | 0 when no client or recorder wants raw frames (the common case: apps subscribe to features or commands) | same bytes when serialized | **adopted** |
| JSON when a client does want raw frames | `tolist` + pydantic: 62.3 ns | orjson on the array: 21.0 ns; msgspec on a list: 38.1 ns; shipped splice (`runtime/fastjson.py`): 24.5 ns | 2.5x (shipped) vs the fallback | byte-identical to pydantic, tested incl. edge-case floats, both encoders | **adopted** (orjson in the `server` extra; pure fallback kept) |
| spike-band SOS filter (µs per 300-sample chunk) | scipy `sosfilt`, (n, ch) C order: 2,442 µs | scipy on F order (what array frames give): 2,115; numba, channels innermost: 830; C `-O3` via ctypes: 831 | 1.15x (F order, free); 2.9x (numba / C) | numba identical; C max error 3.4e-13 µV (floating-point rounding) | F order: adopted as a side effect; **native: not adopted** (§6) |
| WebSocket compression of raw frames | deflate: 11.5 ms per 64 x 150 frame | off for the local server | removes the cost | transport-level; clients negotiate it | **adopted** for `python -m concord.server` |

A Rust/PyO3 SOS filter was not built separately: the C prototype already measures what a
compiled, channel-vectorized loop of this recurrence achieves (numba, an independent compiler,
lands at the same time), a Rust version would be expected to compile to an equivalent loop, and
it would add per-platform wheels for a component §6 shows is not limiting. A native JSON encoder
was not built: orjson (Rust) already spends ~21 ns per value, which is mostly shortest
round-trip float formatting; the real fix for raw viewers is to stop sending raw samples as JSON
text (§8).

## 5. What changed, and before/after

All changes keep the public contracts, the wire format and SDK behaviour (ARCHITECTURE.md §13):

1. **Array-backed raw frames** (`contracts/events.py`, LSL / Open Ephys / plugin adapters):
   `recording.frame` `samples` may be a read-only float64 numpy array in-process; on the wire and
   in the schema it is unchanged.
2. **Lazy, shared JSON** (`runtime/bus.py`, `runtime/fastjson.py`): serialized on first use by
   a sender or a tap; the pipeline tap opts out (`json=False`), the recorder asks only while
   recording (`when=`); frames dropped for a slow client are never serialized.
3. **Memory bounds**: subscriber queues by bytes (64 MiB) as well as count; the pipeline input
   queue by queued sample values (16 M) as well as count.
4. **Pump fairness** (`runtime/runtime.py`): yield after every packet.
5. **Frame size cap** (`adapters/base.py: MAX_FRAME_VALUES`): frames split at 262,144
   channel-samples (256 samples at 1024 channels; unchanged at <= 131 channels).
6. **No permessage-deflate** in `python -m concord.server`.

Correctness: `backend/tests/test_perf_paths.py` (42 tests) checks the array path against the
list path (values, JSON bytes, `model_dump`, malformed-input errors, schema), byte-identical JSON
with orjson and with the fallback (including extreme floats), lazy/shared serialization, both
queue bounds, the pump's yield (fails, rather than hangs, without the fix), adapter output
equivalence, the frame cap, the server option, and a smoke run of the benchmark itself.

Before/after (generated by `--compare`; "failed" = the cell did not complete; see the notes
below each table):

Per 10 ms chunk of 30 kHz data (section 1 of the report):

| channels | stage | before µs | after µs | speed-up |
|---:|---|---:|---:|---:|
| 64 | normalize | 235 | 36 | 6.5x |
| 64 | ingest | 1,192 | 36 | 32.8x |
| 64 | ingest + send | 1,374 | 533 | 2.6x |
| 64 | process | 1,003 | 223 | 4.5x |
| 64 | **normalize + ingest + process** | 2,431 | 296 | **8.2x** |
| 256 | normalize | 1,392 | 122 | 11.4x |
| 256 | ingest | 6,947 | 113 | 61.2x |
| 256 | ingest + send | 6,063 | 2,248 | 2.7x |
| 256 | process | 2,319 | 1,291 | 1.8x |
| 256 | **normalize + ingest + process** | 10,658 | 1,526 | **7.0x** |
| 1024 | normalize | 8,200 | 724 | 11.3x |
| 1024 | ingest | 22,902 | 759 | 30.2x |
| 1024 | ingest + send | 18,563 | 8,763 | 2.1x |
| 1024 | process | 7,268 | 3,652 | 2.0x |
| 1024 | **normalize + ingest + process** | 38,370 | 5,135 | **7.5x** |

**raw** (before → after)

| channels | rate | runtime CPU % | samples/s/ch | features/s at app | missing bins | feature p99 ms | command p99 ms | dropped inputs |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 64 | 30000 | 34 → 12 | 30,058 → 30,029 | 50.1 → 50.0 | 0 → 0 | 10.8 → 8.7 | 11.1 → 8.8 | 0 → 0 |
| 256 | 30000 | failed → 22 | failed → 30,017 | failed → 50.1 | failed → 0 | failed → 10.2 | failed → 10.6 | failed → 0 |
| 1024 | 30000 | failed → 68 | failed → 30,384 | failed → 50.8 | failed → 0 | failed → 42.9 | failed → 44.3 | failed → 0 |
| 2048 | 30000 | failed → 85 | failed → 36,463 | failed → 0.0 | failed → 0 | failed → — | failed → — | failed → 0 |

- before, 256 ch: runtime RSS exceeded 2500 MB 16.4 s after start; stopped by the benchmark; after: ran.

- before, 1024 ch: runtime RSS exceeded 2500 MB 20.0 s after start (before the pipeline could start); stopped by the benchmark; after: ran.

- before, 2048 ch: runtime RSS exceeded 2500 MB 6.2 s after start (before the pipeline could start); stopped by the benchmark; after: ran.

**ecog** (before → after)

| channels | rate | runtime CPU % | samples/s/ch | features/s at app | missing bins | feature p99 ms | command p99 ms | dropped inputs |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 64 | 1000 | 12 → 10 | 1,001 → 1,002 | 20.1 → 20.1 | 0 → 0 | 7.7 → 6.6 | — → — | 0 → 0 |
| 256 | 1000 | 16 → 8 | 1,001 → 1,001 | 20.0 → 20.1 | 0 → 0 | 9.6 → 7.2 | — → — | 0 → 0 |
| 1024 | 1000 | 41 → 14 | 1,002 → 1,001 | 20.1 → 20.0 | 0 → 0 | 86.9 → 9.9 | — → — | 0 → 0 |

**counts** (before → after)

| channels | rate | runtime CPU % | samples/s/ch | features/s at app | missing bins | feature p99 ms | command p99 ms | dropped inputs |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 64 | 50 | 7 → 5 | 53 → 50 | 52.6 → 50.1 | 0 → 0 | 378.0 → 6.0 | 378.0 → 6.5 | 0 → 0 |
| 256 | 50 | 7 → 5 | 50 → 50 | 50.1 → 50.1 | 0 → 0 | 7.2 → 6.0 | 7.3 → 6.4 | 0 → 0 |
| 1024 | 50 | 7 → 5 | 50 → 50 | 50.1 → 50.1 | 0 → 0 | 8.3 → 6.4 | 8.9 → 6.6 | 0 → 0 |
| 2048 | 50 | 9 → 6 | 50 → 50 | 50.2 → 50.2 | 0 → 0 | 10.1 → 6.8 | 11.6 → 7.2 | 0 → 0 |
| 4096 | 50 | 12 → 8 | 50 → 50 | 50.3 → 50.2 | 0 → 0 | 14.5 → 6.8 | 15.9 → 7.1 | 0 → 0 |
| 64 | 100 | 9 → 9 | 100 → 100 | 100.4 → 100.2 | 0 → 0 | 7.5 → 6.2 | 8.2 → 6.4 | 0 → 0 |
| 256 | 100 | 11 → 9 | 100 → 100 | 100.4 → 100.2 | 0 → 0 | 8.4 → 9.8 | 9.1 → 10.3 | 0 → 0 |
| 1024 | 100 | 14 → 10 | 100 → 100 | 100.5 → 100.3 | 0 → 0 | 10.9 → 9.0 | 11.6 → 9.7 | 0 → 0 |
| 2048 | 100 | 16 → 11 | 100 → 100 | 100.4 → 100.3 | 0 → 0 | 8.3 → 9.5 | 8.6 → 10.2 | 0 → 0 |
| 4096 | 100 | 22 → 13 | 100 → 100 | 100.6 → 100.4 | 0 → 0 | 9.5 → 8.9 | 10.2 → 10.5 | 0 → 0 |

**consumers** (before → after)

| channels | rate | runtime CPU % | samples/s/ch | features/s at app | missing bins | feature p99 ms | command p99 ms | dropped inputs | viewer frames/s |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| raw viewer 64 | 30000 | 83 → 21 | — → 30,057 | 0.0 → 50.2 | 0 → 0 | — → 18.9 | — → 18.9 | — → 0 | 29.0 → 101.7 |
| raw viewer 256 | 30000 | failed → 38 | failed → 30,116 | failed → 50.3 | failed → 0 | failed → 52.3 | failed → 55.6 | failed → 0 | failed → 41.6 |
| raw viewer 1024 | 30000 | failed → 89 | failed → 30,442 | failed → 49.9 | failed → 0 | failed → 330.2 | failed → 330.2 | failed → 0 | failed → 23.8 |
| frozen client 256 | 30000 | failed → 27 | failed → 30,057 | failed → 50.2 | failed → 0 | failed → 13.2 | failed → 13.9 | failed → 0 | failed → — |

- before, 256 ch: runtime RSS exceeded 2500 MB 23.5 s after start (before the pipeline could start); stopped by the benchmark; after: ran.

- before, 1024 ch: runtime RSS exceeded 2500 MB 13.3 s after start (before the pipeline could start); stopped by the benchmark; after: ran.

- before, 256 ch: runtime RSS exceeded 2500 MB 17.0 s after start; stopped by the benchmark; after: ran.

**recovery** (before → after)

- 256 ch: RuntimeError: no features reached the app before the kill → recovered in 1.27 s
- 1024 ch: runtime RSS exceeded 2500 MB; stopped by the benchmark → recovered in 2.56 s

Notes on the tables: the "after" 2048-channel raw row ran but delivered nothing by design — every
frame is rejected by the contract (`channel_count <= 1024`; 5,016 validation errors in the
window), see §7. In the baseline, the recovery test at 256 channels could not start because the
runtime never delivered a feature before the publisher was killed.

## 6. What was not changed, and why

- **Signal processing stays on scipy.** The numba and C prototypes of the spike-band SOS filter
  are 2.9x faster than `scipy.signal.sosfilt` at 1024 channels (830 vs 2,442 µs per chunk) and
  bit-identical (numba) or within 3.4e-13 µV (C). But at 1024 channels — the most a
  `recording.frame` can carry — the whole `SignalChain` uses 51% of a core (report §3) and the
  complete runtime sustains 30 kHz with the full chain at 68–75% of a core with zero loss for
  600 s. The filter limits nothing that the contract can represent, so it fails the 2x-on-a-
  limiting-bottleneck rule; shipping it would add a compiled dependency (or a JIT) for headroom
  nobody can use yet. It becomes justified with raw signal beyond 1024 channels: the scipy chain
  needs 121% of a core at 2048 channels and 268% at 4096 (report §3).
- **No native JSON encoder.** orjson is already compiled code at ~21 ns per value; formatting
  each float64 as shortest round-trip text is the floor of that design. Sending raw samples as
  JSON text is the problem to remove (§8), not to accelerate further.
- **No binary WebSocket encoding was implemented.** It must be negotiated (old clients keep
  JSON), and it spans the protocol, the server, and both SDKs (the TypeScript SDK and the console
  belong to other workstreams). It is specified as the first next step in §8.
- **Spike-count / feature events keep the list path.** At 4096 channels and 100 Hz the runtime
  uses 13% of a core end to end; the array path would save little there.
- **`concord.testing.publish` and `bench_live.py` are unchanged** apart from `bench_live` taps
  declaring `json=False`, so they measure what production does.

## 7. Limits on this machine

One runtime process (it holds one device; acquisition, DSP, decoder, router and WebSocket share
one core), 4 vCPUs shared with other work, synthetic LSL streams on the same host:

| stream | largest size sustained without loss | runtime CPU | latency at the SDK app |
|---|---|---:|---|
| raw 30 kHz, spikeband + decoder + router + app | **1024 channels** (contract maximum; 600 s soak: 0 gaps, 0 missing bins, flat RSS) | 68–75% | bin -> command p50 11.5–21.6 ms, p99 34.0–44.3 ms (soak / 10 s run) |
| raw 1 kHz, `ecog_high_gamma` | **1024 channels** (contract maximum) | 14% | bin -> feature p50 4.7 ms, p99 9.9 ms |
| spike counts 100 Hz, decoder + router + app | **4096 channels** (contract maximum for features) | 13% | bin -> command p50 4.5 ms, p99 10.5 ms |
| 3 runtimes x 256 channels raw 30 kHz, concurrently | all three loss-free | 24% each | bin -> feature p50 6.4–6.9 ms; bin -> command p99 41.2–76.4 ms |

- **Raw above 1024 channels is not possible in contract 1.4.** A 2048-channel stream connects and
  is received in full (36,463 samples/s/ch measured while catching up, no gaps), but every frame
  is rejected; the runtime still spends 85% of a core receiving and rejecting it, and its RSS
  reached 1.5 GB (liblsl's time-based inlet buffer holds whatever backlog builds up).
- **A raw-signal viewer at high channel counts degrades other apps.** With a Python SDK client
  subscribed to raw frames at 1024 channels, nothing is lost for the command app (0 missing bins,
  0 dropped inputs, 0 acquisition gaps; the viewer gets 23.8 of 200 frames/s and the rest are
  dropped and counted), but its bin -> command p99 rises from 44.3 ms to 330.2 ms and the runtime
  reaches 89% of a core. At 256 channels the cost is moderate (38%, command p99 55.6 ms); at 64
  channels the viewer receives every frame (21%).
- **Recovery under load**: publisher killed and restarted with the same `source_id`: detected in
  under 10 ms, features flowing again 1.27 s (256 channels) and 2.56 s (1024 channels) after the
  restart (including the publisher's start-up and LSL resolution); the pipeline survives.
- A frozen client (never reads) costs nothing beyond its bounded queue: the command app at 256
  channels kept p99 13.9 ms with 1,535 frames dropped for the frozen client.

## 8. Architecture notes for scale and portability

**Where process separation helps (measured).** Independent runtime processes scale across cores:
three concurrent runtimes at 256 channels were each loss-free at ~24% of a core, with tail
latency rising under contention (p99 up to 76.4 ms with publishers, runtimes, the benchmark and
other workloads sharing 4 vCPUs). Inside one runtime, everything shares one event loop, and the
measurements show what competes: at 1024 channels the pipeline needs ~37% of a core, ingest
plus serialization for one raw subscriber ~88% (report §1), and a raw viewer raises the command
app's p99 latency 7x. Recommended, in order:

1. **Negotiated binary raw frames** for viewers: the hello offers
   `encodings: ["json", "frame-f32"]`; when both sides agree the server sends raw frames as a
   binary WebSocket message (a small JSON header, then little-endian samples); everything else
   stays JSON and old clients never see it. Encoding cost becomes a memory copy instead of
   ~21–25 ns per value, and the client parses no text. A server-side **decimated preview**
   (display rate, selected channels) would cut the volume itself; the console does not need
   30 kHz x 1024 channels to draw traces.
2. **Serve WebSocket clients from a separate process** (fan-out) fed by **shared-memory ring
   buffers** of samples and envelopes, so that no client — slow, frozen or raw-hungry — can take
   CPU from acquisition, the pipeline and command delivery. The lazy `EventJson` holder and the
   byte-bounded queues are the in-process version of that contract.
3. **An acquisition process** (adapter read + normalize) writing into the same ring buffers
   would isolate device I/O and liblsl's buffering; it pays off once a runtime approaches one
   core (today: 1024 raw channels plus a viewer).
4. **Contract 1.5 for more than 1024 raw channels** (raise the limit or add channel groups to
   `recording.frame`), and then a native SOS filter (§6) — measured 2.9x on the filter, which is
   63% of the chain.
5. **Byte-aware liblsl buffering** (`max_buflen` from channels x rate) and per-app priority (send
   commands before raw frames).

**Portability.** The core has no macOS-specific dependency. Everything here was run on Linux
(x86_64, glibc 2.39). Not verified: macOS and Windows timings (uvicorn falls back to the asyncio
event loop where uvloop is unavailable), and the benchmark's per-process CPU/RSS columns, which
read Linux `/proc` (shown as "—" elsewhere). orjson is optional at runtime: without it raw-frame
JSON uses pydantic's encoder (identical output, tested), ~2.5x slower per value. The C and numba
prototypes are built by the benchmark only when a C compiler / numba is present and are never
imported by Concord.
