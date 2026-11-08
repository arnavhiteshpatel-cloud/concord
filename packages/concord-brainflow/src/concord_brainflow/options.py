"""Operator options for the BrainFlow plugin and their validation.

The BrainFlow-specific options are the fields of ``brainflow.board_shim.BrainFlowInputParams``
(see BrainFlow's ``docs/SupportedBoards.rst`` for which fields each board needs).
"""

from __future__ import annotations

import difflib
import math
import os
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from brainflow.board_shim import BoardIds, BrainFlowInputParams, IpProtocolTypes
from concord_adapter_sdk import InvalidOptions, OptionSpec

BOARD_NAMES: tuple[str, ...] = tuple(b.name for b in BoardIds if b is not BoardIds.NO_BOARD)
# Boards whose data format is defined by another ("master") board.
FORWARDING_BOARDS = frozenset({"PLAYBACK_FILE_BOARD", "STREAMING_BOARD"})
IP_PROTOCOLS: tuple[str, ...] = tuple(p.name for p in IpProtocolTypes)

_STR_PARAMS = ("serial_port", "mac_address", "ip_address", "serial_number", "file", "other_info")

OPTIONS: dict[str, OptionSpec] = {
    "board": OptionSpec(
        "choice",
        "BrainFlow board id (BoardIds name). Only used with the 'board' device entry.",
        default="SYNTHETIC_BOARD",
        choices=BOARD_NAMES,
    ),
    "master_board": OptionSpec(
        "str",
        "PLAYBACK_FILE_BOARD / STREAMING_BOARD only: BoardIds name of the board that produced "
        "the data (defines channel layout and sampling rate), e.g. SYNTHETIC_BOARD.",
        default="",
    ),
    "serial_port": OptionSpec("str", "BrainFlowInputParams.serial_port, e.g. /dev/ttyUSB0", ""),
    "mac_address": OptionSpec("str", "BrainFlowInputParams.mac_address (Bluetooth boards)", ""),
    "ip_address": OptionSpec(
        "str",
        "BrainFlowInputParams.ip_address (WiFi boards; multicast group for STREAMING_BOARD)",
        "",
    ),
    "ip_port": OptionSpec("int", "BrainFlowInputParams.ip_port (0-65535)", 0),
    "ip_protocol": OptionSpec(
        "choice", "BrainFlowInputParams.ip_protocol", "NO_IP_PROTOCOL", choices=IP_PROTOCOLS
    ),
    "serial_number": OptionSpec("str", "BrainFlowInputParams.serial_number", ""),
    "file": OptionSpec("str", "BrainFlowInputParams.file (PLAYBACK_FILE_BOARD: recorded file)", ""),
    "other_info": OptionSpec("str", "BrainFlowInputParams.other_info (board-specific)", ""),
    "timeout": OptionSpec(
        "int", "BrainFlowInputParams.timeout in seconds (board-specific, >= 0)", 0
    ),
    "stall_timeout_s": OptionSpec(
        "float",
        "Report the link as lost when no sample arrives for this many seconds (> 0). "
        "A playback file that reached its end also stalls.",
        5.0,
    ),
    "package_num_modulus": OptionSpec(
        "int",
        "Range of the board's package counter, used to detect lost samples (BrainFlow's "
        "synthetic board counts 0-255). 0 disables loss detection.",
        256,
    ),
}


@dataclass(frozen=True, slots=True)
class BoardOptions:
    board: str
    master_board: str
    params: BrainFlowInputParams
    stall_timeout_s: float
    package_num_modulus: int


def _suggest(value: str, choices: tuple[str, ...]) -> str:
    close = difflib.get_close_matches(value.upper(), choices, n=3)
    return f" Did you mean: {', '.join(close)}?" if close else ""


def _as_int(key: str, value: Any) -> int:
    if isinstance(value, bool):
        raise InvalidOptions(f"option '{key}' must be an integer, got {value!r}")
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, str):
        try:
            return int(value.strip())
        except ValueError:
            pass
    raise InvalidOptions(f"option '{key}' must be an integer, got {value!r}")


def _as_float(key: str, value: Any) -> float:
    if isinstance(value, bool):
        raise InvalidOptions(f"option '{key}' must be a number, got {value!r}")
    try:
        out = float(value)
    except (TypeError, ValueError):
        raise InvalidOptions(f"option '{key}' must be a number, got {value!r}") from None
    if not math.isfinite(out):
        raise InvalidOptions(f"option '{key}' must be finite, got {value!r}")
    return out


def _as_str(key: str, value: Any) -> str:
    if not isinstance(value, str):
        raise InvalidOptions(f"option '{key}' must be a string, got {value!r}")
    return value


def board_name(key: str, value: Any) -> str:
    name = _as_str(key, value).strip()
    if name not in BOARD_NAMES:
        raise InvalidOptions(
            f"option '{key}': unknown BrainFlow board {name!r}.{_suggest(name, BOARD_NAMES)} "
            "Use a brainflow.board_shim.BoardIds name such as SYNTHETIC_BOARD or CYTON_BOARD."
        )
    return name


def parse_options(board: str, options: Mapping[str, Any]) -> BoardOptions:
    """Validate ``options`` for ``board`` and build ``BrainFlowInputParams``."""
    unknown = sorted(set(options) - set(OPTIONS))
    if unknown:
        raise InvalidOptions(
            f"unknown option(s) {', '.join(unknown)}; valid options: {', '.join(sorted(OPTIONS))}"
        )
    params = BrainFlowInputParams()
    for key in _STR_PARAMS:
        if key in options:
            setattr(params, key, _as_str(key, options[key]))
    if "ip_port" in options:
        port = _as_int("ip_port", options["ip_port"])
        if not 0 <= port <= 65535:
            raise InvalidOptions(f"option 'ip_port' must be 0-65535, got {port}")
        params.ip_port = port
    if "ip_protocol" in options:
        proto = _as_str("ip_protocol", options["ip_protocol"])
        if proto not in IP_PROTOCOLS:
            raise InvalidOptions(
                f"option 'ip_protocol' must be one of {', '.join(IP_PROTOCOLS)}, got {proto!r}"
            )
        params.ip_protocol = IpProtocolTypes[proto].value
    if "timeout" in options:
        timeout = _as_int("timeout", options["timeout"])
        if timeout < 0:
            raise InvalidOptions(f"option 'timeout' must be >= 0, got {timeout}")
        params.timeout = timeout
    stall = _as_float("stall_timeout_s", options.get("stall_timeout_s", 5.0))
    if stall <= 0:
        raise InvalidOptions(f"option 'stall_timeout_s' must be > 0, got {stall}")
    modulus = _as_int("package_num_modulus", options.get("package_num_modulus", 256))
    if modulus < 0:
        raise InvalidOptions(f"option 'package_num_modulus' must be >= 0, got {modulus}")

    master_raw = _as_str("master_board", options.get("master_board", "")).strip()
    master = ""
    if board in FORWARDING_BOARDS:
        if not master_raw:
            raise InvalidOptions(
                f"{board} needs option 'master_board': the BoardIds name of the board that "
                "produced the data (e.g. SYNTHETIC_BOARD)"
            )
        master = board_name("master_board", master_raw)
        if master in FORWARDING_BOARDS:
            raise InvalidOptions(f"option 'master_board' cannot be {master}")
        params.master_board = BoardIds[master].value
    elif master_raw:
        raise InvalidOptions(
            "option 'master_board' only applies to PLAYBACK_FILE_BOARD and STREAMING_BOARD"
        )

    if board == "PLAYBACK_FILE_BOARD":
        if not params.file:
            raise InvalidOptions("PLAYBACK_FILE_BOARD needs option 'file' (a BrainFlow data file)")
        if not os.path.isfile(params.file):
            raise InvalidOptions(f"option 'file': {params.file!r} is not a readable file")
    if board == "STREAMING_BOARD" and (not params.ip_address or params.ip_port <= 0):
        raise InvalidOptions(
            "STREAMING_BOARD needs options 'ip_address' (multicast group, e.g. 225.1.1.1) and "
            "'ip_port' — the address the producing BrainFlow session passed to add_streamer"
        )
    return BoardOptions(
        board=board,
        master_board=master,
        params=params,
        stall_timeout_s=stall,
        package_num_modulus=modulus,
    )
