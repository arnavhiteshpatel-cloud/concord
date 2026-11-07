"""BrainOS benchmarks. Every number printed is measured on the machine running this script.

1. Pipeline capacity (in-process, no network): how many envelopes/s the runtime can
   stamp, validate and fan out, per event type, with N subscribers.
2. End-to-end (live server, real WebSockets): runtime-ingest timestamp ->
   received-and-validated by the Python SDK, with Profile A streaming, for
   1 and 8 concurrent SDK subscribers.

Usage:  python scripts/bench.py [--seconds 10] [--write docs/BENCHMARKS.md]
"""

from __future__ import annotations

import argparse
import asyncio
import platform
import socket
import statistics
import sys
import tempfile
import threading
import time
from pathlib import Path

import uvicorn

from brainos.adapters.base import EventDraft
from brainos.adapters.simulated import OperatorIntentSource
from brainos.adapters.simulated import profile_a as pa
from brainos.contracts.capabilities import Capability, CapabilityDescriptor, EventType
from brainos.contracts.events import Provenance, ProvenanceKind, Quality, QualityFlag
from brainos.contracts.protocol import AppInfo, DeviceDescriptor, DeviceKind
from brainos.runtime import DeviceRegistry, Recorder, Runtime
from brainos.sdk import EventStream, RuntimeClient
from brainos.server import Settings, create_app


def pct(values: list[float], p: float) -> float:
    s = sorted(values)
    return s[min(len(s) - 1, round(p * (len(s) - 1)))]


# ----------------------------------------------------------------- 1. capacity


def _drafts() -> dict[str, EventDraft]:
    q = Quality(score=1.0, flags=[QualityFlag.SYNTHETIC])
    sim = Provenance(
        kind=ProvenanceKind.SIMULATED_INTENT, adapter="bench@0.0.1", synthetic=True, origin="bench"
    )
    raw = Provenance(
        kind=ProvenanceKind.RAW_SIGNAL, adapter="bench@0.0.1", synthetic=True, origin="bench"
    )
    frame = {
        "sample_rate_hz": pa.SAMPLE_RATE_HZ,
        "channel_count": pa.CHANNELS,
        "first_sample_index": 0,
        "unit": "uV",
        "samples": [[float(i % 50)] * pa.FRAME_SAMPLES for i in range(pa.CHANNELS)],
    }
    return {
        "intent.pointer": EventDraft(EventType.INTENT_POINTER, {"vx": 0.1, "vy": -0.1}, q, sim, 1),
        f"recording.frame ({pa.CHANNELS}x{pa.FRAME_SAMPLES})": EventDraft(
            EventType.RECORDING_FRAME, frame, q, raw, 1
        ),
    }


async def bench_capacity(subscribers: int, n: int) -> list[tuple[str, int, float, float]]:
    desc = DeviceDescriptor(
        device_id="bench",
        display_name="bench",
        kind=DeviceKind.SIMULATED,
        adapter="bench@0.0.1",
        native_format="-",
        capabilities=[CapabilityDescriptor(capability=c) for c in Capability],
        synthetic=True,
    )
    tmp = Path(tempfile.mkdtemp())
    rt = Runtime(DeviceRegistry(OperatorIntentSource(), tmp), Recorder(tmp), queue_size=n + 10)
    rt._device, rt._session_id = desc, "ses_benchmark1"  # bypass adapter: measure ingest only
    subs = [
        rt.register_app(AppInfo(id=f"s{i}", name="s"), [], list(Capability))
        for i in range(subscribers)
    ]
    out = []
    for name, draft in _drafts().items():
        for s in subs:
            s._events.clear()
        t0 = time.perf_counter()
        for _ in range(n):
            rt._ingest(draft, time.monotonic_ns())
        dt = time.perf_counter() - t0
        out.append((name, subscribers, n / dt, dt / n * 1e6))
    return out


# --------------------------------------------------------------- 2. end-to-end


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


async def _consume(
    base: str, idx: int, seconds: float, lat: list[float], stats: list[dict[str, int]]
) -> None:
    async with await EventStream.connect(
        app_id=f"bench-{idx}",
        app_name="bench",
        optional=[c.value for c in Capability],
        base_url=base,
    ) as stream:
        end = time.monotonic() + seconds
        async for env in stream.events():
            lat.append((time.time_ns() - env.timestamp_ns) / 1e6)
            if time.monotonic() > end:
                break
        stats.append(
            {
                "received": stream.stats.received,
                "gaps": stream.stats.delivery_gaps,
                "out_of_order": stream.stats.out_of_order,
            }
        )


async def bench_e2e(base: str, clients: int, seconds: float) -> dict[str, float]:
    lat: list[float] = []
    stats: list[dict[str, int]] = []
    async with RuntimeClient(base) as rc:
        snap = await rc.runtime()
        if snap.state == "idle":
            await rc.connect("sim-a")
        await asyncio.sleep(1.0)
        await asyncio.gather(*(_consume(base, i, seconds, lat, stats) for i in range(clients)))
        diag = await rc.diagnostics()
    return {
        "clients": clients,
        "events_per_client_per_s": statistics.mean(s["received"] for s in stats) / seconds,
        "p50_ms": pct(lat, 0.5),
        "p95_ms": pct(lat, 0.95),
        "p99_ms": pct(lat, 0.99),
        "max_ms": max(lat),
        "samples": len(lat),
        "gaps": sum(s["gaps"] for s in stats),
        "out_of_order": sum(s["out_of_order"] for s in stats),
        "server_pipeline_p50_us": diag["pipeline_latency"]["p50_us"],
        "server_pipeline_p99_us": diag["pipeline_latency"]["p99_us"],
    }


def run_server(tmp: Path) -> tuple[str, uvicorn.Server, threading.Thread]:
    port = _free_port()
    settings = Settings(
        port=port, data_dir=tmp, reports_dir=tmp, static_dir=None, log_level="WARNING"
    )
    server = uvicorn.Server(
        uvicorn.Config(create_app(settings), host="127.0.0.1", port=port, log_level="warning")
    )
    th = threading.Thread(target=server.run, daemon=True)
    th.start()
    while not server.started:
        time.sleep(0.05)
    return f"http://127.0.0.1:{port}", server, th


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seconds", type=float, default=10.0)
    ap.add_argument("--write", type=Path, default=None)
    args = ap.parse_args()

    lines: list[str] = []
    p = lines.append
    p("# BrainOS benchmarks\n")
    p(
        f"Measured {time.strftime('%Y-%m-%d %H:%M %Z')} with `python scripts/bench.py --seconds {args.seconds:g}`.\n"
    )
    p("| | |\n|---|---|")
    p(f"| machine | `{platform.machine()}` · {platform.platform()} |")
    p(f"| cpu count | {__import__('os').cpu_count()} |")
    p(f"| python | {sys.version.split()[0]} |")
    p("")

    p("## 1. Runtime pipeline capacity (in-process, no network)\n")
    p(
        "Stamp + schema-validate + serialize + fan-out to N subscriber queues, single core, synchronous.\n"
    )
    p("| event | subscribers | envelopes/s | µs/envelope |\n|---|---:|---:|---:|")
    for subs in (1, 8):
        for name, s, rate, us in asyncio.run(bench_capacity(subs, 5000)):
            p(f"| {name} | {s} | {rate:,.0f} | {us:.1f} |")
    p("")

    p("## 2. End-to-end over WebSocket (live server, Profile A streaming)\n")
    p(
        "Latency = SDK receive wall clock - envelope `timestamp_ns` (runtime ingest), same machine. "
        "Includes JSON serialization, WebSocket, client-side JSON parse and full Pydantic validation "
        "in the Python SDK. Profile A emits ≈76 events/s (50 pointer + 25 frames + 1 telemetry).\n"
    )
    p(
        "| SDK clients | events/s per client | p50 ms | p95 ms | p99 ms | max ms | samples | "
        "delivery gaps | out-of-order | server pipeline p50/p99 µs |"
    )
    p("|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|")
    tmp = Path(tempfile.mkdtemp())
    base, server, th = run_server(tmp)
    try:
        for clients in (1, 8):
            r = asyncio.run(bench_e2e(base, clients, args.seconds))
            p(
                f"| {clients} | {r['events_per_client_per_s']:.1f} | {r['p50_ms']:.2f} | {r['p95_ms']:.2f} "
                f"| {r['p99_ms']:.2f} | {r['max_ms']:.2f} | {r['samples']:,} | {r['gaps']} "
                f"| {r['out_of_order']} | {r['server_pipeline_p50_us']:.0f} / {r['server_pipeline_p99_us']:.0f} |"
            )
    finally:
        server.should_exit = True
        th.join(timeout=10)
    p("")
    p(
        "Notes: numbers depend on the machine and its load; re-run on your own hardware. "
        "These are software-pipeline numbers with simulated devices — they say nothing about "
        "any real implant's latency."
    )
    text = "\n".join(lines) + "\n"
    print(text)
    if args.write:
        args.write.parent.mkdir(parents=True, exist_ok=True)
        args.write.write_text(text)
        print(f"wrote {args.write}")


if __name__ == "__main__":
    main()
