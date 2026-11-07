"""BrainOS source plugin for BrainFlow (``brainflow.board_shim.BoardShim``).

Read-only: the plugin calls ``prepare_session``, ``start_stream``, ``get_board_data_count``,
``get_board_data``, ``stop_stream`` and ``release_session``. It never calls
``config_board`` / ``config_board_with_bytes`` / ``insert_marker`` (which send data to the
board) and never adds streamers.

No MARKERS stream: BrainFlow fills its marker row only from ``insert_marker`` calls on the
same session (see ``layout.py``); the marker row is still watched and non-zero values are
counted in ``stats()['marker_row_nonzero']`` so a change in BrainFlow's behaviour is visible.

Only BrainFlow's DEFAULT preset is read. Boards that put some sensors into the auxiliary or
ancillary presets (e.g. Muse accelerometer/PPG) deliver only their DEFAULT-preset rows.
"""

from __future__ import annotations

import contextlib
import itertools
import logging
import time
from collections.abc import Mapping, Sequence
from importlib import metadata
from typing import Any

import numpy as np
from brainflow.board_shim import BoardIds, BoardShim, BrainFlowError, BrainFlowPresets
from brainflow.exit_codes import BrainFlowExitCodes
from brainos_adapter_sdk import (
    API_VERSION,
    Chunk,
    DeviceInfo,
    InvalidOptions,
    LinkLost,
    MarkerChunk,
    OpenFailed,
    PluginManifest,
    SessionInfo,
    SourcePlugin,
    SourceSession,
    StreamRole,
)
from numpy.typing import NDArray

from brainos_brainflow.counter import PackageCounter
from brainos_brainflow.layout import BoardLayout, build_layout
from brainos_brainflow.options import OPTIONS, BoardOptions, board_name, parse_options

log = logging.getLogger(__name__)

PLUGIN_VERSION = "0.1.0"
_PRESET = BrainFlowPresets.DEFAULT_PRESET
_POLL_S = 0.002

# device_key -> fixed board (None: taken from the 'board' option)
DEVICE_BOARDS: dict[str, str | None] = {
    "synthetic": "SYNTHETIC_BOARD",
    "playback": "PLAYBACK_FILE_BOARD",
    "streaming": "STREAMING_BOARD",
    "board": None,
}


def brainflow_version() -> str:
    try:
        return metadata.version("brainflow")
    except metadata.PackageNotFoundError:  # pragma: no cover - brainflow is a dependency
        return "unknown"


def _error_text(exc: BrainFlowError) -> str:
    code = getattr(exc, "exit_code", None)
    try:
        name = BrainFlowExitCodes(code).name
    except ValueError:
        name = "UNKNOWN_ERROR"
    return f"{name} (BrainFlow exit code {code}): {exc}"


class BrainFlowSession(SourceSession):
    def __init__(self, shim: BoardShim, opts: BoardOptions, layout: BoardLayout) -> None:
        self._shim: BoardShim | None = shim
        self._opts = opts
        self._layout = layout
        board = opts.board
        source = opts.master_board or board
        origin = f"brainflow:{board}" + (f"/{opts.master_board}" if opts.master_board else "")
        self._info = SessionInfo(
            streams=layout.specs(),
            primary_stream=layout.primary_stream,
            # Generated data: the synthetic board itself, or a playback/stream whose data
            # format is the synthetic board's (only the synthetic board produces it).
            synthetic=source == "SYNTHETIC_BOARD",
            prerecorded=board == "PLAYBACK_FILE_BOARD",
            origin=origin,
        )
        self._counter = PackageCounter(
            opts.package_num_modulus if layout.package_num_row is not None else 0
        )
        self._last_ts = -np.inf
        self._last_data = time.monotonic()
        self._samples = 0
        self._ts_regressions = 0
        self._marker_nonzero = 0
        self._chunks = 0

    @property
    def info(self) -> SessionInfo:
        return self._info

    def read(self, timeout_s: float) -> Sequence[Chunk | MarkerChunk]:
        shim = self._shim
        if shim is None:
            raise LinkLost("BrainFlow session is closed")
        deadline = time.monotonic() + max(0.0, timeout_s)
        while True:
            try:
                count = shim.get_board_data_count(_PRESET)
            except BrainFlowError as exc:
                raise LinkLost(f"BrainFlow stopped delivering data: {_error_text(exc)}") from exc
            now = time.monotonic()
            if count > 0:
                break
            silent = now - self._last_data
            if silent > self._opts.stall_timeout_s:
                raise LinkLost(
                    f"no samples from BrainFlow board {self._opts.board} for {silent:.1f} s "
                    "(device disconnected, producer stopped, or playback file ended)"
                )
            if now >= deadline:
                return []
            time.sleep(min(_POLL_S, deadline - now))
        try:
            data = shim.get_board_data(count, _PRESET)
        except BrainFlowError as exc:
            raise LinkLost(f"BrainFlow stopped delivering data: {_error_text(exc)}") from exc
        self._last_data = time.monotonic()
        return self._convert(np.asarray(data, dtype=np.float64))

    def _convert(self, data: NDArray[np.float64]) -> list[Chunk | MarkerChunk]:
        lay = self._layout
        n = int(data.shape[1])
        if n == 0:
            return []
        self._samples += n
        if lay.package_num_row is not None:
            idx = self._counter.assign(data[lay.package_num_row])
        else:
            idx = self._counter.assign(np.zeros(n))
        raw_ts = data[lay.timestamp_row]
        # Timestamps must not go backwards (a wall clock can be stepped). Count and clamp.
        ts = np.maximum.accumulate(np.concatenate(([self._last_ts], raw_ts)))[1:]
        self._ts_regressions += int(np.count_nonzero(ts != raw_ts))
        self._last_ts = float(ts[-1])
        out: list[Chunk | MarkerChunk] = []
        breaks = np.flatnonzero(np.diff(idx) != 1) + 1
        bounds = [0, *breaks.tolist(), n]
        for s, e in itertools.pairwise(bounds):
            for stream in lay.signal_streams:
                out.append(
                    Chunk(
                        stream_id=stream.spec.stream_id,
                        data=np.ascontiguousarray(data[list(stream.rows), s:e].T),
                        timestamps=np.ascontiguousarray(ts[s:e]),
                        first_index=int(idx[s]),
                    )
                )
                self._chunks += 1
        if lay.marker_row is not None:
            self._marker_nonzero += int(np.count_nonzero(data[lay.marker_row]))
        return out

    def stats(self) -> Mapping[str, int | float]:
        return {
            "samples_received": self._samples,
            "dropped_packets": self._counter.dropped,
            "package_num_repeats": self._counter.repeats,
            "package_num_unusable": int(self._counter.unusable),
            "timestamp_regressions": self._ts_regressions,
            "marker_row_nonzero": self._marker_nonzero,
            "chunks_emitted": self._chunks,
        }

    def close(self) -> None:
        shim, self._shim = self._shim, None
        if shim is None:
            return
        _release(shim)


def _release(shim: BoardShim) -> None:
    try:
        if shim.is_prepared():
            with contextlib.suppress(BrainFlowError):  # the stream was not running
                shim.stop_stream()
            shim.release_session()
    except Exception:  # close() must not raise
        log.exception("failed to release BrainFlow session")


class BrainFlowPlugin(SourcePlugin):
    manifest = PluginManifest(
        name="brainos-brainflow",
        version=PLUGIN_VERSION,
        api_version=API_VERSION,
        display_name="BrainFlow",
        description=(
            "Reads noninvasive research/consumer biosensing boards (EEG, EMG, ECG, ...) "
            "through BrainFlow's official BoardShim API, plus BrainFlow's synthetic, "
            "playback-file and streaming boards. Receive-only: no commands are sent to boards."
        ),
        author="BrainOS",
        license="Proprietary (internal preview)",
        roles=frozenset({StreamRole.SIGNAL}),
        homepage="https://brainflow.org",
        ecosystem="brainflow",
        # BrainFlow opens sockets for WiFi boards and the multicast streaming board.
        network=True,
        options=OPTIONS,
    )

    def discover(self, timeout_s: float) -> Sequence[DeviceInfo]:
        # BrainFlow has no generic device enumeration; these are the entries an operator
        # can open, not detected hardware.
        version = brainflow_version()
        return [
            DeviceInfo(
                "synthetic",
                "BrainFlow synthetic board",
                "Generated test signals from BrainFlow's SYNTHETIC_BOARD (not a real device).",
                {"brainflow": version, "board": "SYNTHETIC_BOARD"},
            ),
            DeviceInfo(
                "playback",
                "BrainFlow playback file",
                "Replays a file recorded with BrainFlow (PLAYBACK_FILE_BOARD). Needs options "
                "'file' and 'master_board'.",
                {"brainflow": version, "board": "PLAYBACK_FILE_BOARD"},
            ),
            DeviceInfo(
                "streaming",
                "BrainFlow streaming board",
                "Receives data another BrainFlow session publishes with "
                "add_streamer('streaming_board://<group>:<port>'). Needs options 'ip_address', "
                "'ip_port' and 'master_board'.",
                {"brainflow": version, "board": "STREAMING_BOARD"},
            ),
            DeviceInfo(
                "board",
                "Configure a BrainFlow board",
                "Any board supported by BrainFlow: choose 'board' and fill the connection "
                "options BrainFlow's documentation lists for it. Not detected automatically.",
                {"brainflow": version},
            ),
        ]

    def open(self, device_key: str, options: Mapping[str, Any]) -> SourceSession:
        if device_key not in DEVICE_BOARDS:
            raise OpenFailed(
                f"unknown BrainFlow device {device_key!r}; expected one of "
                f"{', '.join(DEVICE_BOARDS)}"
            )
        fixed = DEVICE_BOARDS[device_key]
        requested = options.get("board")
        if fixed is None:
            board = board_name("board", requested if requested is not None else "SYNTHETIC_BOARD")
        else:
            if requested not in (None, fixed, OPTIONS["board"].default):
                raise InvalidOptions(
                    f"device '{device_key}' always opens {fixed}; option 'board'={requested!r} "
                    "conflicts (use the 'board' device entry to choose a board)"
                )
            board = fixed
        if board not in BoardIds.__members__ or board == "NO_BOARD":
            raise InvalidOptions(f"option 'board': unknown BrainFlow board {board!r}")
        opts = parse_options(board, options)
        format_board = opts.master_board or board
        try:
            descr = BoardShim.get_board_descr(BoardIds[format_board].value, _PRESET)
            layout = build_layout(format_board, descr)
        except (BrainFlowError, ValueError) as exc:
            raise OpenFailed(
                f"BrainFlow has no usable description for {format_board}: {exc}"
            ) from exc

        shim = BoardShim(BoardIds[board].value, opts.params)
        try:
            shim.prepare_session()
        except BrainFlowError as exc:
            _release(shim)
            raise OpenFailed(
                f"BrainFlow prepare_session failed for {board}: {_error_text(exc)}. "
                "Check the connection options BrainFlow's documentation lists for this board."
            ) from exc
        try:
            shim.start_stream()
        except BrainFlowError as exc:
            _release(shim)
            raise OpenFailed(
                f"BrainFlow start_stream failed for {board}: {_error_text(exc)}"
            ) from exc
        log.info(
            "opened BrainFlow %s (format %s, brainflow %s)",
            board,
            format_board,
            brainflow_version(),
        )
        return BrainFlowSession(shim, opts, layout)
