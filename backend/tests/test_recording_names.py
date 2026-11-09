"""Regression: recording a live source (LSL, Open Ephys, plugin) failed with "invalid recording
name", because the default name was built from a device id that contains ':' and '.'. And a
cursor + click file replay ("t15:") reached the name check instead of being refused plainly."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from concord.adapters.replay.format import NAME_PATTERN
from concord.adapters.simulated import profile_a
from concord.runtime import Recorder
from concord.runtime.recorder import RecorderError, default_recording_name, is_file_replay

LIVE_IDS = [
    "lsl:falcon-h1-19250108t110520-counts",
    "openephys:127.0.0.1:5576",
    "plugin:my-amp:default",
    "plugin:concord-brainflow:synthetic-board-with-a-very-long-device-name",
    "sim-a",
    "::",
]


@pytest.mark.parametrize("device_id", LIVE_IDS)
def test_default_name_is_a_valid_recording_name(device_id: str) -> None:
    name = default_recording_name(device_id, when=0.0)
    assert NAME_PATTERN.match(name), name
    assert len(name) <= 48
    assert re.search(r"-\d{8}-\d{6}$", name), name  # ends with the YYYYmmdd-HHMMSS stamp


def test_default_name_keeps_the_device_readable() -> None:
    assert default_recording_name("openephys:127.0.0.1:5576", when=0.0).startswith(
        "openephys-127-0-0-1-5576-"
    )
    assert default_recording_name("sim-a", when=0.0).startswith("sim-a-")


@pytest.mark.parametrize(
    "device_id", ["lsl:falcon-h1-counts", "openephys:127.0.0.1:5576", "plugin:my-amp:default"]
)
def test_live_sources_record_with_the_default_name(tmp_path: Path, device_id: str) -> None:
    rec = Recorder(tmp_path)
    device = profile_a.descriptor().model_copy(update={"device_id": device_id})
    name = rec.start(device)
    rec.stop()
    assert (tmp_path / f"{name}.concord.jsonl").is_file()


@pytest.mark.parametrize(
    "device_id", ["replay:sim-a-1", "nwb:sub-x", "t15:day00468-block03-grid-evaluation"]
)
def test_file_replays_are_refused_with_a_plain_reason(tmp_path: Path, device_id: str) -> None:
    assert is_file_replay(device_id)
    device = profile_a.descriptor().model_copy(update={"device_id": device_id})
    with pytest.raises(RecorderError, match="already a recording"):
        Recorder(tmp_path).start(device)


def test_live_sources_are_not_file_replays() -> None:
    assert not any(is_file_replay(d) for d in LIVE_IDS)
