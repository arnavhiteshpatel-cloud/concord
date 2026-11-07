"""Measure the App Connector plugin against a genuine BCI2000 build (same machine).

Latency = time when ``read()`` returned minus the block's SourceTime. Both are
CLOCK_MONOTONIC on Linux (BCI2000: ``TimeUtils.cpp`` ``SystemClocks::MonotonicTime`` ->
``clock_gettime(CLOCK_MONOTONIC)``; Python: ``time.monotonic``), and SourceTime is that clock
in ms truncated to 16 bits, so the difference is taken modulo 65.536 s. It covers BCI2000's
signal processing and application modules, ConnectorOutput's sender thread, UDP and the
plugin.

    python packages/brainos-bci2000/scripts/measure_app_connector.py --prog-dir <BCI2000/prog>
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
import threading
import time
from pathlib import Path
from typing import Any

import numpy as np
from brainos_adapter_sdk import Chunk

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tests"))

from bci2000_live import SAMPLE_BLOCK_SIZE, SAMPLING_RATE, run_bci2000
from brainos_bci2000 import BCI2000AppConnectorPlugin
from connector_output import free_udp_port


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--prog-dir", type=Path, required=True)
    ap.add_argument("--seconds", type=float, default=10.0)
    args = ap.parse_args()
    port = free_udp_port()
    result: dict[str, Any] = {}

    def opener() -> None:
        result["session"] = BCI2000AppConnectorPlugin().open(
            "app-connector",
            {
                "port": port,
                "open_timeout_s": 30.0,
                "sampling_rate_hz": SAMPLING_RATE,
                "sample_block_size": SAMPLE_BLOCK_SIZE,
            },
        )

    t = threading.Thread(target=opener)
    t.start()
    time.sleep(0.2)
    with tempfile.TemporaryDirectory() as work:
        proc = run_bci2000(args.prog_dir, port, Path(work), run_seconds=args.seconds)
        t.join(timeout=60)
        session = result["session"]
        lat: list[float] = []
        ts_all: list[float] = []
        while proc.poll() is None:
            items = session.read(0.1)
            now = time.monotonic()
            for it in items:
                if isinstance(it, Chunk) and it.stream_id == "control_signal":
                    for ts in it.timestamps:
                        ts_all.append(float(ts))
                        # signed difference: SourceTime has 1 ms resolution (may round up)
                        lat.append((((now - ts) + 32.768) % 65.536 - 32.768) * 1000)
        stats = dict(session.stats())
        session.close()
    lat_ms = np.array(lat)
    ts = np.array(ts_all)
    print(
        json.dumps(
            {
                "blocks": int(ts.size),
                "block_rate_hz_from_source_time": round(float((ts.size - 1) / (ts[-1] - ts[0])), 3),
                "nominal_block_rate_hz": SAMPLING_RATE / SAMPLE_BLOCK_SIZE,
                "latency_ms_source_time_to_read": {
                    "median": round(float(np.median(lat_ms)), 2),
                    "p95": round(float(np.percentile(lat_ms, 95)), 2),
                    "max": round(float(np.max(lat_ms)), 2),
                },
                "stats": stats,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
