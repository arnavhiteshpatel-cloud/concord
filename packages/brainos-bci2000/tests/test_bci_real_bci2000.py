"""Against a genuine BCI2000 build (opt-in): BCI2000's own ConnectorOutput sends, the plugin
receives. Set ``BCI2000_PROG_DIR`` to a BCI2000 ``prog`` directory containing BCI2000Shell,
Operator, SignalGenerator, DummySignalProcessing and DummyApplication (see
docs/ECOSYSTEMS.md for the build used). Skipped when the variable is not set, because BCI2000
is not a dependency of this package; the CI-safe equivalent is the fixture replay in
test_bci_plugin.py, recorded from the same build.
"""

from __future__ import annotations

import os
import threading
import time
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from bci2000_live import SAMPLE_BLOCK_SIZE, SAMPLING_RATE, SOURCE_CH, run_bci2000
from bci_contract import StreamTracker, check_session_info
from brainos_bci2000 import BCI2000AppConnectorPlugin
from connector_output import free_udp_port

PROG = os.environ.get("BCI2000_PROG_DIR")
pytestmark = pytest.mark.skipif(not PROG, reason="BCI2000_PROG_DIR not set (opt-in live test)")


def test_genuine_bci2000_connector_output(tmp_path: Path) -> None:
    assert PROG is not None
    port = free_udp_port()
    result: dict[str, Any] = {}

    def opener() -> None:
        try:
            result["session"] = BCI2000AppConnectorPlugin().open(
                "app-connector",
                {
                    "port": port,
                    "open_timeout_s": 30.0,
                    "sampling_rate_hz": SAMPLING_RATE,
                    "sample_block_size": SAMPLE_BLOCK_SIZE,
                    "declare_synthetic": True,  # BCI2000 runs SignalGenerator
                },
            )
        except BaseException as exc:
            result["error"] = exc

    t = threading.Thread(target=opener)
    t.start()
    time.sleep(0.2)  # let open() bind before BCI2000 starts sending
    proc = run_bci2000(Path(PROG), port, tmp_path, run_seconds=4.0)
    t.join(timeout=60)
    if "error" in result:
        proc.kill()
        raise result["error"]
    session = result["session"]
    info = session.info
    check_session_info(info, BCI2000AppConnectorPlugin.manifest)
    tracker = StreamTracker(info)
    arrivals: list[float] = []
    try:
        end = time.monotonic() + 30
        while time.monotonic() < end and proc.poll() is None:
            items = session.read(0.1)
            if any(getattr(i, "stream_id", "") == "control_signal" for i in items):
                arrivals.append(time.monotonic())
            tracker.feed(items)
        tracker.feed(session.read(0.2))
        stats = dict(session.stats())
    finally:
        session.close()
        proc.wait(timeout=30)
    n_ctrl = len(info.streams[0].channels)
    assert n_ctrl == SOURCE_CH * SAMPLE_BLOCK_SIZE  # DummySignalProcessing passes the signal on
    ts = tracker.all_timestamps("control_signal")
    rate = (len(ts) - 1) / (ts[-1] - ts[0])
    expected_rate = SAMPLING_RATE / SAMPLE_BLOCK_SIZE
    assert abs(rate - expected_rate) / expected_rate < 0.05, rate
    assert stats["dropped_packets"] == 0
    assert stats["malformed_lines"] == 0
    labels = [m for m, _ in tracker.markers["state_changes"]]
    assert labels == [
        "TargetCode 0->2",
        "Feedback 0->1",
        "TargetCode 2->0",
        "ResultCode 0->2",
        "Feedback 1->0",
    ]
    print(
        f"\nBCI2000 live: {len(ts)} control blocks, SourceTime rate {rate:.3f} Hz "
        f"(nominal {expected_rate}), median block interval {1000 * np.median(np.diff(ts)):.2f} ms, "
        f"stats {stats}"
    )
