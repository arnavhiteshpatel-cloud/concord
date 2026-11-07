"""BrainFlow SYNTHETIC_BOARD end to end through the official BoardShim (no mocks)."""

from __future__ import annotations

import time

import numpy as np
import pytest
from bf_contract import StreamTracker, check_manifest, check_session_info
from brainflow.board_shim import BoardIds, BoardShim
from brainos_adapter_sdk import LinkLost, Modality, StreamRole
from brainos_adapter_sdk.api import KEY_PATTERN
from brainos_brainflow import BrainFlowPlugin
from brainos_brainflow.layout import MICROVOLTS


def test_manifest_and_discover() -> None:
    plugin = BrainFlowPlugin()
    check_manifest(plugin.manifest)
    assert plugin.manifest.ecosystem == "brainflow"
    assert plugin.manifest.roles == {StreamRole.SIGNAL}
    devices = plugin.discover(0.1)
    keys = [d.device_key for d in devices]
    assert keys == ["synthetic", "playback", "streaming", "board"]
    for d in devices:
        assert KEY_PATTERN.match(d.device_key)
        # honest entries: nothing claims to be detected hardware or an implant
        assert "implant" not in d.description.lower()
    assert "not a real device" in devices[0].description


def test_synthetic_metadata_from_board_descr() -> None:
    session = BrainFlowPlugin().open("synthetic", {})
    try:
        info = session.info
        check_session_info(info, BrainFlowPlugin.manifest)
        assert info.synthetic is True
        assert info.prerecorded is False
        assert info.origin == "brainflow:SYNTHETIC_BOARD"
        assert info.primary_stream == "exg"
        descr = BoardShim.get_board_descr(BoardIds.SYNTHETIC_BOARD.value)
        streams = {s.stream_id: s for s in info.streams}
        exg = streams["exg"]
        assert exg.nominal_rate_hz == float(descr["sampling_rate"])
        assert [c.label for c in exg.channels] == descr["eeg_names"].split(",")
        # The synthetic board lists rows 1-16 as EEG, EMG, ECG and EOG at once: ambiguous.
        assert {c.type for c in exg.channels} == {"EEG|EMG|ECG|EOG"}
        assert exg.modality is None
        assert exg.invasive is None
        assert {c.unit for c in exg.channels} == {MICROVOLTS}
        assert exg.clock.domain == "unix"
        aux = streams["aux"]
        aux_types = [c.type for c in aux.channels]
        assert aux_types.count("ACCEL") == len(descr["accel_channels"])
        assert aux_types.count("GYRO") == len(descr["gyro_channels"])
        assert "BATTERY" in aux_types and "TEMPERATURE" in aux_types
        assert all(c.unit is None for c in aux.channels)  # BrainFlow documents no unit
        assert set(streams) == {"exg", "aux"}
        assert aux.modality is Modality.OTHER and aux.invasive is None
    finally:
        session.close()


def test_synthetic_streams_at_documented_rate_with_ordered_unix_timestamps() -> None:
    session = BrainFlowPlugin().open("synthetic", {})
    tracker = StreamTracker(session.info)
    latencies: list[float] = []

    def on_read(items: object, now: float) -> None:
        for item in items:  # type: ignore[attr-defined]
            if getattr(item, "stream_id", "") == "exg" and hasattr(item, "data"):
                latencies.append(now - float(item.timestamps[-1]))

    t0 = time.time()
    try:
        tracker.read_for(session, 3.0, on_read=on_read)
        stats = dict(session.stats())
    finally:
        session.close()
    n = tracker.samples["exg"]
    assert tracker.samples["aux"] == n
    ts = tracker.all_timestamps("exg")
    span = ts[-1] - ts[0]
    rate = (n - 1) / span
    assert 250 * 0.9 < rate < 250 * 1.1, rate
    # unix clock: within a few seconds of the wall clock
    assert abs(ts[0] - t0) < 5.0
    assert tracker.gaps["exg"] == 0
    assert stats["dropped_packets"] == 0
    assert stats["samples_received"] == n
    idx = tracker.all_indices("exg")
    assert idx[0] == 0 and np.all(np.diff(idx) == 1)
    assert np.all(np.isfinite(tracker.stacked("exg")))
    assert latencies and float(np.median(latencies)) < 1.0


def test_close_is_idempotent_and_read_after_close_is_link_lost() -> None:
    session = BrainFlowPlugin().open("synthetic", {})
    session.close()
    session.close()
    with pytest.raises(LinkLost):
        session.read(0.01)
    # the board was released: it can be opened again
    again = BrainFlowPlugin().open("synthetic", {})
    again.close()


def test_board_device_entry_opens_the_chosen_board() -> None:
    session = BrainFlowPlugin().open("board", {"board": "SYNTHETIC_BOARD"})
    try:
        assert session.info.origin == "brainflow:SYNTHETIC_BOARD"
    finally:
        session.close()
