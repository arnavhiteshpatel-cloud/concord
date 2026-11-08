"""Option validation and open failures (official BrainFlow library, no hardware)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from concord_adapter_sdk import InvalidOptions, OpenFailed
from concord_brainflow import BrainFlowPlugin


@pytest.mark.parametrize(
    ("device", "options", "match"),
    [
        ("board", {"bogus": 1}, "unknown option"),
        ("board", {"board": "CYTON"}, "Did you mean: CYTON_BOARD"),
        ("board", {"board": "NO_BOARD"}, "unknown BrainFlow board"),
        ("board", {"board": "SYNTHETIC_BOARD", "ip_port": 70000}, "0-65535"),
        ("board", {"board": "SYNTHETIC_BOARD", "ip_port": "x"}, "integer"),
        ("board", {"board": "SYNTHETIC_BOARD", "ip_port": True}, "integer"),
        ("board", {"board": "SYNTHETIC_BOARD", "timeout": -1}, ">= 0"),
        ("board", {"board": "SYNTHETIC_BOARD", "ip_protocol": "SCTP"}, "ip_protocol"),
        ("board", {"board": "SYNTHETIC_BOARD", "serial_port": 3}, "string"),
        ("board", {"board": "SYNTHETIC_BOARD", "stall_timeout_s": 0}, "> 0"),
        ("board", {"board": "SYNTHETIC_BOARD", "stall_timeout_s": "nan"}, "finite"),
        ("board", {"board": "SYNTHETIC_BOARD", "package_num_modulus": -1}, ">= 0"),
        ("synthetic", {"master_board": "CYTON_BOARD"}, "only applies"),
        ("synthetic", {"board": "CYTON_BOARD"}, "conflicts"),
        ("playback", {"master_board": "SYNTHETIC_BOARD"}, "needs option 'file'"),
        (
            "playback",
            {"file": "/nonexistent/concord.csv", "master_board": "SYNTHETIC_BOARD"},
            "not a readable file",
        ),
        ("playback", {"file": __file__}, "needs option 'master_board'"),
        ("playback", {"file": __file__, "master_board": "STREAMING_BOARD"}, "cannot be"),
        ("playback", {"file": __file__, "master_board": "SYNTHETIC"}, "Did you mean"),
        ("streaming", {"master_board": "SYNTHETIC_BOARD"}, "ip_address"),
    ],
)
def test_invalid_options(device: str, options: dict[str, Any], match: str) -> None:
    with pytest.raises(InvalidOptions, match=match):
        BrainFlowPlugin().open(device, options)


def test_unknown_device_key() -> None:
    with pytest.raises(OpenFailed, match="unknown BrainFlow device"):
        BrainFlowPlugin().open("cyton-1", {})


def test_failing_prepare_session_is_open_failed_with_brainflow_error_code() -> None:
    # A real BrainFlow board driver (Cyton, serial) pointed at a port that does not exist.
    with pytest.raises(OpenFailed) as err:
        BrainFlowPlugin().open(
            "board", {"board": "CYTON_BOARD", "serial_port": "/dev/concord-no-such-port"}
        )
    msg = str(err.value)
    assert "prepare_session failed for CYTON_BOARD" in msg
    assert "BrainFlow exit code" in msg
    assert "UNABLE_TO_OPEN_PORT_ERROR" in msg


def test_playback_of_a_file_that_is_not_brainflow_data_fails_cleanly(tmp_path: Path) -> None:
    empty = tmp_path / "empty.csv"
    empty.write_text("")
    with pytest.raises(OpenFailed, match="prepare_session failed"):
        BrainFlowPlugin().open("playback", {"file": str(empty), "master_board": "SYNTHETIC_BOARD"})
    # the failed session was released; the synthetic board still opens
    BrainFlowPlugin().open("synthetic", {}).close()


def test_defaults_filled_in_by_a_host_are_accepted() -> None:
    plugin = BrainFlowPlugin()
    defaults = {k: v.default for k, v in plugin.manifest.options.items()}
    session = plugin.open("synthetic", defaults)
    session.close()
