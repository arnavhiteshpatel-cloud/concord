"""STREAMING_BOARD fed by a second official BoardShim session via add_streamer (multicast)."""

from __future__ import annotations

import random

import numpy as np
import pytest
from bf_contract import StreamTracker, check_session_info
from brainflow.board_shim import BoardIds, BoardShim, BrainFlowInputParams
from brainos_adapter_sdk import LinkLost
from brainos_brainflow import BrainFlowPlugin

DESCR = BoardShim.get_board_descr(BoardIds.SYNTHETIC_BOARD.value)
GROUP = "225.1.1.1"


def test_streaming_board_receives_a_producer_session_bit_for_bit() -> None:
    port = random.randint(20000, 40000)
    producer = BoardShim(BoardIds.SYNTHETIC_BOARD.value, BrainFlowInputParams())
    producer.prepare_session()
    session = None
    try:
        producer.add_streamer(f"streaming_board://{GROUP}:{port}")
        producer.start_stream()
        session = BrainFlowPlugin().open(
            "streaming",
            {
                "ip_address": GROUP,
                "ip_port": port,
                "master_board": "SYNTHETIC_BOARD",
                "stall_timeout_s": 1.0,
            },
        )
        info = session.info
        check_session_info(info, BrainFlowPlugin.manifest)
        assert info.origin == "brainflow:STREAMING_BOARD/SYNTHETIC_BOARD"
        assert info.prerecorded is False
        tracker = StreamTracker(info)
        tracker.read_for(session, 2.5)
        assert tracker.samples.get("exg", 0) > 400, "no data over multicast"
        produced = np.asarray(producer.get_board_data(), dtype=np.float64)
        producer.stop_stream()
        # producer gone: the consumer reports the link as lost after the stall timeout
        with pytest.raises(LinkLost):
            tracker.read_for(session, 5.0)
        stats = dict(session.stats())
    finally:
        if session is not None:
            session.close()
        producer.release_session()
    got = tracker.stacked("exg")
    ts = tracker.all_timestamps("exg")
    # The streamer sends raw doubles: every received sample equals the producer's sample
    # with the same timestamp, exactly.
    by_ts = {float(t): i for i, t in enumerate(produced[DESCR["timestamp_channel"]])}
    rows = [by_ts[float(t)] for t in ts]
    assert np.array_equal(got, produced[DESCR["eeg_channels"]][:, rows].T)
    rate = (len(ts) - 1) / (ts[-1] - ts[0])
    assert 250 * 0.9 < rate < 250 * 1.1, rate
    assert tracker.gaps["exg"] == stats["dropped_packets"]
