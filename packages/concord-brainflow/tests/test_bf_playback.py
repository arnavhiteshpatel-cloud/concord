"""PLAYBACK_FILE_BOARD replaying a file written by BrainFlow's own DataFilter.write_file."""

from __future__ import annotations

import time
from pathlib import Path

import numpy as np
import pytest
from bf_contract import StreamTracker, check_session_info
from brainflow.board_shim import BoardIds, BoardShim, BrainFlowInputParams
from brainflow.data_filter import DataFilter
from concord_adapter_sdk import LinkLost
from concord_brainflow import BrainFlowPlugin

DESCR = BoardShim.get_board_descr(BoardIds.SYNTHETIC_BOARD.value)
PKG = DESCR["package_num_channel"]
MARK = DESCR["marker_channel"]
TS = DESCR["timestamp_channel"]
DROP = slice(300, 305)  # five consecutive samples removed from the file: a known loss


def _capture(seconds: float) -> np.ndarray:
    """Record the official synthetic board with BoardShim (test-side, not the plugin)."""
    shim = BoardShim(BoardIds.SYNTHETIC_BOARD.value, BrainFlowInputParams())
    shim.prepare_session()
    try:
        shim.start_stream()
        time.sleep(seconds)
        shim.stop_stream()
        return np.asarray(shim.get_board_data(), dtype=np.float64)
    finally:
        shim.release_session()


@pytest.fixture(scope="module")
def recording(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, np.ndarray]:
    data = _capture(2.4)
    assert data.shape[1] > 400, "need > 256 samples to cross the package counter wrap"
    data[MARK, 20] = 3.0
    data[MARK, 150] = 7.5
    data = np.ascontiguousarray(np.delete(data, np.arange(DROP.start, DROP.stop), axis=1))
    path = tmp_path_factory.mktemp("bf") / "synthetic.csv"
    DataFilter.write_file(data, str(path), "w")
    # What BrainFlow's own reader gets back from the file. write_file prints "%lf"
    # (data_handler.cpp), i.e. 6 decimals: the file holds the capture at that precision.
    from_file = np.asarray(DataFilter.read_file(str(path)), dtype=np.float64)
    six_decimals = np.vectorize(lambda x: float(f"{x:.6f}"))(data)
    assert np.array_equal(from_file, six_decimals)
    return path, from_file


def test_playback_values_arrive_bit_for_bit_and_are_marked_prerecorded(
    recording: tuple[Path, np.ndarray],
) -> None:
    path, expected = recording
    session = BrainFlowPlugin().open(
        "playback", {"file": str(path), "master_board": "SYNTHETIC_BOARD"}
    )
    info = session.info
    check_session_info(info, BrainFlowPlugin.manifest)
    assert info.prerecorded is True
    assert info.synthetic is True  # the recording came from the synthetic board
    assert info.origin == "brainflow:PLAYBACK_FILE_BOARD/SYNTHETIC_BOARD"
    n_file = expected.shape[1]
    tracker = StreamTracker(info)
    t_start = time.time()
    try:
        tracker.read_for(session, 15.0, until=lambda t: t.samples.get("exg", 0) >= n_file)
        stats = dict(session.stats())
    finally:
        session.close()
    assert tracker.samples["exg"] == n_file
    streams = {s.stream_id: s for s in info.streams}
    exg_rows = DESCR["eeg_channels"]
    got = tracker.stacked("exg")
    assert got.shape == (n_file, len(streams["exg"].channels))
    assert np.array_equal(got, expected[exg_rows].T)  # exact, bit for bit
    aux_rows = sorted(
        {
            r
            for k, v in DESCR.items()
            if k.endswith("_channels")
            and k not in ("eeg_channels", "emg_channels", "ecg_channels", "eog_channels")
            for r in v
        }
        | {DESCR["battery_channel"]}
    )
    assert np.array_equal(tracker.stacked("aux"), expected[aux_rows].T)
    # the 5 removed samples show up as a gap in first_index and in dropped_packets
    assert tracker.gaps["exg"] == 5
    assert stats["dropped_packets"] == 5
    idx = tracker.all_indices("exg")
    assert idx[-1] == n_file - 1 + 5
    # crossing the 8-bit counter wrap (255 -> 0) is not mistaken for loss
    assert np.any(np.diff(expected[PKG]) < 0)
    # BrainFlow's playback board overwrites the marker row (Board::push_package fills it
    # only from insert_marker on the same session): markers in the file do not arrive.
    # This is why the plugin declares no MARKERS stream.
    assert expected[MARK, 20] == 3.0 and expected[MARK, 150] == 7.5
    assert stats["marker_row_nonzero"] == 0
    assert "markers" not in {s.stream_id for s in info.streams}
    # BrainFlow's default for playback is new timestamps (time of replay), on the unix clock
    ts = tracker.all_timestamps("exg")
    assert abs(ts[0] - t_start) < 5.0
    assert ts[0] > expected[TS, -1]


def test_playback_end_of_file_is_reported_as_link_lost(recording: tuple[Path, np.ndarray]) -> None:
    path, expected = recording
    session = BrainFlowPlugin().open(
        "playback",
        {"file": str(path), "master_board": "SYNTHETIC_BOARD", "stall_timeout_s": 0.5},
    )
    tracker = StreamTracker(session.info)
    try:
        with pytest.raises(LinkLost, match="no samples"):
            tracker.read_for(session, 20.0)
    finally:
        session.close()
    assert tracker.samples["exg"] == expected.shape[1]
