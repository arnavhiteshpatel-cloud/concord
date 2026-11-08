"""Measure the BrainFlow plugin against the official library (no hardware).

For each source (SYNTHETIC_BOARD; STREAMING_BOARD fed by a synthetic producer over
multicast) it reads through the plugin's public API for ``--seconds`` and reports the
delivered sample rate (from BrainFlow's timestamps), loss counters, and latency = wall-clock
time when ``read()`` returned minus the sample's BrainFlow timestamp (both unix time on the
same machine). It also times the plugin's conversion step alone on a large block.

    python packages/concord-brainflow/scripts/measure_brainflow.py --seconds 10
"""

from __future__ import annotations

import argparse
import json
import platform
import random
import time
from typing import Any

import numpy as np
from brainflow.board_shim import BoardIds, BoardShim, BrainFlowInputParams
from concord_adapter_sdk import Chunk
from concord_brainflow import BrainFlowPlugin
from concord_brainflow.plugin import brainflow_version


def measure(session: Any, seconds: float) -> dict[str, Any]:
    lat: list[np.ndarray] = []
    ts_all: list[np.ndarray] = []
    reads = 0
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        items = session.read(0.05)
        now = time.time()
        reads += 1
        for it in items:
            if isinstance(it, Chunk) and it.stream_id == "exg":
                lat.append(now - it.timestamps)
                ts_all.append(it.timestamps)
    stats = dict(session.stats())
    session.close()
    lat_ms = np.concatenate(lat) * 1000
    ts = np.concatenate(ts_all)
    return {
        "samples": int(ts.size),
        "rate_hz_from_timestamps": round(float((ts.size - 1) / (ts[-1] - ts[0])), 3),
        "latency_ms": {
            "median": round(float(np.median(lat_ms)), 2),
            "p95": round(float(np.percentile(lat_ms, 95)), 2),
            "max": round(float(np.max(lat_ms)), 2),
        },
        "reads": reads,
        "stats": stats,
    }


def conversion_throughput() -> dict[str, Any]:
    session = BrainFlowPlugin().open("synthetic", {})
    n = 250_000
    data = np.random.default_rng(0).normal(size=(32, n))
    data[0] = np.arange(n) % 256
    data[30] = time.time() + np.arange(n) / 250
    t0 = time.perf_counter()
    session._convert(data)  # type: ignore[attr-defined]  # the read() post-processing step
    dt = time.perf_counter() - t0
    session.close()
    return {"samples": n, "seconds": round(dt, 4), "samples_per_s": round(n / dt)}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seconds", type=float, default=10.0)
    args = ap.parse_args()
    BoardShim.disable_board_logger()
    out: dict[str, Any] = {
        "brainflow": brainflow_version(),
        "machine": f"{platform.machine()} {platform.system()} {platform.release()}",
        "python": platform.python_version(),
    }
    out["synthetic"] = measure(BrainFlowPlugin().open("synthetic", {}), args.seconds)

    port = random.randint(20000, 40000)
    producer = BoardShim(BoardIds.SYNTHETIC_BOARD.value, BrainFlowInputParams())
    producer.prepare_session()
    producer.add_streamer(f"streaming_board://225.1.1.1:{port}")
    producer.start_stream()
    try:
        session = BrainFlowPlugin().open(
            "streaming",
            {"ip_address": "225.1.1.1", "ip_port": port, "master_board": "SYNTHETIC_BOARD"},
        )
        out["streaming"] = measure(session, args.seconds)
    finally:
        producer.release_session()
    out["conversion"] = conversion_throughput()
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
