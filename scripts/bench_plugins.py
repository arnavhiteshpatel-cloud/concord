#!/usr/bin/env python
"""Measured throughput of the plugin-host IPC for 64 ch x 30 kHz float32 (this machine).

Three layers, each for a few chunk sizes, with an unpaced test plugin (it returns data as
fast as it is asked, so the numbers are the ceiling of the path, not of a device):

1. host IPC: AsyncHostClient ``read`` round trips (plugin -> host validation -> binary
   frames -> runtime process); every chunk is checked bit-exact against what was sent;
2. adapter: ``PluginAdapter.read()`` (adds runtime-side validation and loss accounting);
3. adapter + normalize: also builds ``recording.frame`` drafts (float64 + ``tolist``).

Usage: python scripts/bench_plugins.py [--seconds 2] [--write docs/ADAPTER_SDK_BENCH.md]
Nothing here is asserted; numbers depend on the machine.
"""

from __future__ import annotations

import argparse
import asyncio
import platform
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
PLUGINS = ROOT / "backend" / "tests" / "plugins"
sys.path.insert(0, str(PLUGINS))

from brainos_adapter_sdk import ipc  # noqa: E402

from brainos.adapters.plugin import PluginAdapter, PluginSpec  # noqa: E402
from brainos.adapters.plugin.host_client import AsyncHostClient  # noqa: E402

RATE = 30_000.0
CHANNELS = 64
REF = "bos_test_plugins:FastPlugin"


def _expected_block(chunk: int) -> np.ndarray:  # type: ignore[type-arg]
    rng = np.random.default_rng(0)
    return rng.standard_normal((chunk, CHANNELS)).astype(np.float32)


async def bench_ipc(chunk: int, seconds: float) -> dict[str, float]:
    client = AsyncHostClient(REF, extra_path=[str(PLUGINS)])
    await client.start(10.0)
    await client.request("open", {"device_key": "fast", "options": {"chunk": chunk}}, timeout_s=10)
    expected = _expected_block(chunk).tobytes()
    samples = reads = 0
    exact = True
    rtts: list[float] = []
    t0 = time.perf_counter()
    while time.perf_counter() - t0 < seconds:
        t = time.perf_counter()
        result, arrays = await client.request("read", {"timeout_s": 0.1}, timeout_s=10)
        rtts.append(time.perf_counter() - t)
        chunks = ipc.chunks_from_wire(result["chunks"], arrays)
        for c in chunks:
            assert isinstance(c.data, np.ndarray)
            exact = exact and c.data.dtype == np.float32 and c.data.tobytes() == expected
            samples += c.data.shape[0]
        reads += 1
    elapsed = time.perf_counter() - t0
    await client.close()
    return {
        "samples_per_s": samples / elapsed,
        "mb_per_s": samples * CHANNELS * 4 / elapsed / 1e6,
        "realtime_x": samples / elapsed / RATE,
        "rtt_ms_p50": float(np.percentile(rtts, 50) * 1e3),
        "rtt_ms_p95": float(np.percentile(rtts, 95) * 1e3),
        "reads": reads,
        "bit_exact": float(exact),
    }


async def bench_adapter(chunk: int, seconds: float, normalize: bool) -> dict[str, float]:
    sys.path.insert(0, str(PLUGINS))
    from bos_test_plugins import FastPlugin

    spec = PluginSpec(
        device_id="plugin:bench:fast",
        entry_point=REF,
        device_key="fast",
        options={"chunk": chunk},
        manifest=FastPlugin.manifest,
        extra_path=(str(PLUGINS),),
        start_timeout_s=10,
        open_timeout_s=10,
    )
    a = PluginAdapter(spec)
    await a.open()
    samples = drafts = 0
    t0 = time.perf_counter()
    while time.perf_counter() - t0 < seconds:
        packet = await a.read()
        for r in packet.data:
            samples += r.chunk.data.shape[0]
        if normalize:
            drafts += len(a.normalize(packet))
    elapsed = time.perf_counter() - t0
    await a.close()
    return {
        "samples_per_s": samples / elapsed,
        "mb_per_s": samples * CHANNELS * 4 / elapsed / 1e6,
        "realtime_x": samples / elapsed / RATE,
        "drafts": drafts,
    }


async def run(seconds: float) -> str:
    rows = []
    for chunk in (300, 1500, 6000):  # 10 ms, 50 ms, 200 ms of data per read
        ipc_r = await bench_ipc(chunk, seconds)
        ad = await bench_adapter(chunk, seconds, normalize=False)
        nz = await bench_adapter(chunk, seconds, normalize=True)
        rows.append(
            f"| {chunk} ({chunk / RATE * 1e3:.0f} ms) | {ipc_r['mb_per_s']:.0f} MB/s · "
            f"{ipc_r['realtime_x']:.1f}x | {ipc_r['rtt_ms_p50']:.2f} / {ipc_r['rtt_ms_p95']:.2f} "
            f"| {'yes' if ipc_r['bit_exact'] else 'NO'} | {ad['realtime_x']:.1f}x "
            f"| {nz['realtime_x']:.1f}x |"
        )
    head = (
        f"Measured {time.strftime('%Y-%m-%d')} on {platform.machine()} "
        f"({platform.python_implementation()} {platform.python_version()}), {seconds:g} s "
        "per cell, unpaced test plugin, 64 ch float32 (real time = 30 000 samples/s = "
        "7.68 MB/s).\n\n"
        "| samples per read | host IPC throughput | read round trip p50 / p95 (ms) "
        "| bit-exact | adapter (IPC + runtime validation) | adapter + normalize to events |\n"
        "| --- | --- | --- | --- | --- | --- |\n"
    )
    return head + "\n".join(rows) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--seconds", type=float, default=2.0)
    ap.add_argument("--write", type=Path, help="write the markdown table to this file")
    a = ap.parse_args()
    table = asyncio.run(run(a.seconds))
    print(table)
    if a.write:
        a.write.write_text(table)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
