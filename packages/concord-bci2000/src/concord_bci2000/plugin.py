"""Concord source plugin for BCI2000's App Connector (``ConnectorOutput``) protocol.

Receive-only: the plugin binds a UDP socket and reads what BCI2000's ConnectorOutput filter
sends. It never sends anything to BCI2000 (no ConnectorInput, no Operator scripting).

What arrives is *processed control information*: BCI2000 state values and the control
signal (the output of BCI2000's signal processing module as it passes through the
application module), not raw brain signal. Raw signal is available from BCI2000 through
other interfaces (e.g. the FieldTrip buffer), which this plugin does not use.
"""

from __future__ import annotations

import logging
import math
import select
import socket
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from concord_adapter_sdk import (
    API_VERSION,
    Channel,
    Chunk,
    ClockInfo,
    ConfigurationChanged,
    DeviceInfo,
    InvalidOptions,
    LinkLost,
    MarkerChunk,
    OpenFailed,
    OptionSpec,
    PluginManifest,
    SessionInfo,
    SourcePlugin,
    SourceSession,
    StreamRole,
    StreamSpec,
)

from concord_bci2000.convert import (
    CHANGES_STREAM,
    CONTROL_STREAM,
    SOURCE_TIME,
    STATES_STREAM,
    BlockConverter,
)
from concord_bci2000.protocol import (
    PADDING_PREFIX,
    BlockAssembler,
    Layout,
    LayoutChanged,
    RawBlock,
    layout_from,
)

log = logging.getLogger(__name__)

PLUGIN_VERSION = "0.1.0"
DEVICE_KEY = "app-connector"
# ConnectorOutputAddress default in ConnectorFilters.cpp (line 167): "localhost:20321".
DEFAULT_PORT = 20321
# States defined by BCI2000's standard application frameworks: FeedbackTask.cpp
# (TargetCode, ResultCode, Feedback) and StimulusTask.cpp (StimulusCode, StimulusType).
DEFAULT_STATES = ("TargetCode", "ResultCode", "Feedback", "StimulusCode", "StimulusType")
MODEL_ID = "bci2000-control-signal"
PROCESSED = "processed control information, not raw signal"
_MAX_DATAGRAM = 65536
_RCVBUF_BYTES = 4 * 1024 * 1024
_LAYOUT_CHANGE_BLOCKS = 5

OPTIONS: dict[str, OptionSpec] = {
    "address": OptionSpec(
        "str",
        "Local address to receive on: the host part of BCI2000's ConnectorOutputAddress "
        "(127.0.0.1 when BCI2000 runs on this machine).",
        "127.0.0.1",
    ),
    "port": OptionSpec(
        "int",
        "Local UDP port: the port of BCI2000's ConnectorOutputAddress (BCI2000 default 20321).",
        DEFAULT_PORT,
    ),
    "behavior_states": OptionSpec(
        "str",
        "Comma-separated BCI2000 states to deliver as behavior samples. 'auto' = those of "
        f"{', '.join(DEFAULT_STATES)} that BCI2000 sends; empty = none.",
        "auto",
    ),
    "marker_states": OptionSpec(
        "str",
        "Comma-separated BCI2000 states whose changes become markers (e.g. 'TargetCode 0->2'). "
        "'auto' as for behavior_states; empty = none.",
        "auto",
    ),
    "sampling_rate_hz": OptionSpec(
        "float",
        "BCI2000 SamplingRate parameter in Hz, if known (0 = unknown). With sample_block_size "
        "it gives the nominal block rate (one control-signal sample per block).",
        0.0,
    ),
    "sample_block_size": OptionSpec(
        "int", "BCI2000 SampleBlockSize parameter, if known (0 = unknown).", 0
    ),
    "clock": OptionSpec(
        "choice",
        "Timestamps: 'auto' uses BCI2000's SourceTime state when it is sent, else receive "
        "time; 'receive_time' always uses receive time.",
        "auto",
        choices=("auto", "receive_time"),
    ),
    "open_timeout_s": OptionSpec(
        "float",
        "How long open() waits for BCI2000 data to learn the state list and control signal "
        "layout (> 0). BCI2000 only sends while a run is active.",
        10.0,
    ),
    "declare_synthetic": OptionSpec(
        "bool",
        "Set when BCI2000's source module generates data (e.g. SignalGenerator). The App "
        "Connector does not reveal BCI2000's source module.",
        False,
    ),
    "declare_prerecorded": OptionSpec(
        "bool",
        "Set when BCI2000 replays a recording (e.g. FilePlayback). Not visible over App Connector.",
        False,
    ),
}


@dataclass(frozen=True, slots=True)
class Settings:
    address: str
    port: int
    behavior_states: str
    marker_states: str
    sampling_rate_hz: float
    sample_block_size: int
    clock: str
    open_timeout_s: float
    declare_synthetic: bool
    declare_prerecorded: bool

    @property
    def block_rate_hz(self) -> float:
        if self.sampling_rate_hz > 0 and self.sample_block_size > 0:
            return self.sampling_rate_hz / self.sample_block_size
        return 0.0


def _bool(key: str, value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str) and value.lower() in ("true", "false", "1", "0"):
        return value.lower() in ("true", "1")
    raise InvalidOptions(f"option '{key}' must be true or false, got {value!r}")


def _int(key: str, value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int | str | float):
        raise InvalidOptions(f"option '{key}' must be an integer, got {value!r}")
    try:
        out = int(value)
    except ValueError:
        raise InvalidOptions(f"option '{key}' must be an integer, got {value!r}") from None
    if isinstance(value, float) and not value.is_integer():
        raise InvalidOptions(f"option '{key}' must be an integer, got {value!r}")
    return out


def _float(key: str, value: Any) -> float:
    if isinstance(value, bool):
        raise InvalidOptions(f"option '{key}' must be a number, got {value!r}")
    try:
        out = float(value)
    except (TypeError, ValueError):
        raise InvalidOptions(f"option '{key}' must be a number, got {value!r}") from None
    if not math.isfinite(out):
        raise InvalidOptions(f"option '{key}' must be finite, got {value!r}")
    return out


def parse_settings(options: Mapping[str, Any]) -> Settings:
    unknown = sorted(set(options) - set(OPTIONS))
    if unknown:
        raise InvalidOptions(
            f"unknown option(s) {', '.join(unknown)}; valid options: {', '.join(sorted(OPTIONS))}"
        )
    get = {k: options.get(k, spec.default) for k, spec in OPTIONS.items()}
    address = get["address"]
    if not isinstance(address, str) or not address.strip():
        raise InvalidOptions("option 'address' must be a host name or IP address")
    port = _int("port", get["port"])
    if not 1 <= port <= 65535:
        raise InvalidOptions(f"option 'port' must be 1-65535, got {port}")
    for key in ("behavior_states", "marker_states"):
        if not isinstance(get[key], str):
            raise InvalidOptions(f"option '{key}' must be a comma-separated list of state names")
    rate = _float("sampling_rate_hz", get["sampling_rate_hz"])
    sbs = _int("sample_block_size", get["sample_block_size"])
    if rate < 0 or sbs < 0:
        raise InvalidOptions("options 'sampling_rate_hz' and 'sample_block_size' must be >= 0")
    if (rate > 0) != (sbs > 0):
        raise InvalidOptions(
            "give both 'sampling_rate_hz' and 'sample_block_size' (BCI2000 parameters), or neither"
        )
    clock = get["clock"]
    if clock not in OPTIONS["clock"].choices:
        raise InvalidOptions(f"option 'clock' must be one of {', '.join(OPTIONS['clock'].choices)}")
    timeout = _float("open_timeout_s", get["open_timeout_s"])
    if timeout <= 0:
        raise InvalidOptions("option 'open_timeout_s' must be > 0")
    return Settings(
        address=address.strip(),
        port=port,
        behavior_states=get["behavior_states"],
        marker_states=get["marker_states"],
        sampling_rate_hz=rate,
        sample_block_size=sbs,
        clock=str(clock),
        open_timeout_s=timeout,
        declare_synthetic=_bool("declare_synthetic", get["declare_synthetic"]),
        declare_prerecorded=_bool("declare_prerecorded", get["declare_prerecorded"]),
    )


def select_states(key: str, value: str, layout: Layout) -> tuple[str, ...]:
    available = [s for s in layout.states if not s.startswith(PADDING_PREFIX)]
    if value.strip().lower() == "auto":
        return tuple(s for s in DEFAULT_STATES if s in available)
    names = [n.strip() for n in value.split(",") if n.strip()]
    missing = [n for n in names if n not in available]
    if missing:
        raise InvalidOptions(
            f"option '{key}': BCI2000 does not send state(s) {', '.join(missing)}; "
            f"it sends: {', '.join(available)}"
        )
    return tuple(dict.fromkeys(names))


def learn_layout(blocks: Sequence[RawBlock]) -> tuple[Layout, int] | None:
    """Layout confirmed by two consecutive identical blocks, skipping the first block
    (which may have started before the socket was bound). Returns (layout, index of the
    first block to deliver)."""
    for i in range(2, len(blocks)):
        a, b = blocks[i - 1], blocks[i]
        la, lb = layout_from(a), layout_from(b)
        if la is not None and la == lb:
            return la, i - 1
    return None


class AppConnectorSession(SourceSession):
    def __init__(self, sock: socket.socket, settings: Settings) -> None:
        self._sock: socket.socket | None = sock
        self._settings = settings
        self._assembler = BlockAssembler()
        self._pending: list[RawBlock] = []
        self._incomplete_run = 0
        self._last_shape: frozenset[tuple[int, int]] | None = None
        layout, learned = self._learn()
        self._assembler.set_layout(layout)
        self.layout = layout
        behavior = select_states("behavior_states", settings.behavior_states, layout)
        markers = select_states("marker_states", settings.marker_states, layout)
        use_source_time = settings.clock == "auto" and SOURCE_TIME in layout.states
        self._converter = BlockConverter(
            layout,
            behavior,
            markers,
            use_source_time=use_source_time,
        )
        self._info = self._build_info(layout, behavior, markers, use_source_time)
        self._pending = learned

    # -------------------------------------------------------------- open-time learning

    def _learn(self) -> tuple[Layout, list[RawBlock]]:
        """Receive until the layout is known; return it and the blocks to deliver."""
        s = self._settings
        deadline = time.monotonic() + s.open_timeout_s
        learned: list[RawBlock] = []
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                where = f"{s.address}:{s.port}"
                got = self._assembler.stats.datagrams
                hint = (
                    f"received {got} datagram(s) but no consistent App Connector blocks"
                    if got
                    else "received nothing"
                )
                raise OpenFailed(
                    f"no BCI2000 App Connector data on {where} within {s.open_timeout_s:g} s "
                    f"({hint}). Set BCI2000's ConnectorOutputAddress parameter to {where} and "
                    "start a run (BCI2000 sends only while running). If Concord stopped "
                    "receiving during the current run, BCI2000 has stopped sending until the "
                    "next run: stop and start the run (observed with BCI2000 3.6; its "
                    "ConnectorOutput opens its sockets only when a run starts)."
                )
            for data, t in self._receive(min(remaining, 0.2)):
                learned.extend(self._assembler.feed(data, t))
            found = learn_layout(learned)
            if found is not None:
                layout, first = found
                return layout, learned[first:]

    def _build_info(
        self, layout: Layout, behavior: Sequence[str], markers: Sequence[str], source_time: bool
    ) -> SessionInfo:
        s = self._settings
        if source_time:
            clock = ClockInfo(
                "source",
                "BCI2000 SourceTime state (16-bit millisecond counter of BCI2000's monotonic "
                "clock at block acquisition), unwrapped; arbitrary origin.",
            )
        else:
            clock = ClockInfo(
                "source",
                "Receive time of the block's first datagram on the Concord plugin host's "
                "monotonic clock (BCI2000 did not send SourceTime, or clock=receive_time).",
            )
        rate = s.block_rate_hz
        streams: list[StreamSpec] = []
        if layout.signals:
            streams.append(
                StreamSpec(
                    stream_id=CONTROL_STREAM,
                    role=StreamRole.DECODER_OUTPUT,
                    channels=tuple(
                        Channel(label=f"Signal({c},{e})", unit=None, type="CONTROL")
                        for c, e in layout.signals
                    ),
                    nominal_rate_hz=rate,
                    clock=clock,
                    quantity="control_signal",
                    model_id=MODEL_ID,
                )
            )
        if behavior:
            streams.append(
                StreamSpec(
                    stream_id=STATES_STREAM,
                    role=StreamRole.BEHAVIOR,
                    channels=tuple(Channel(label=n, unit=None, type="STATE") for n in behavior),
                    nominal_rate_hz=rate,
                    clock=clock,
                    quantity="bci2000_state",
                )
            )
        if markers:
            streams.append(
                StreamSpec(
                    stream_id=CHANGES_STREAM,
                    role=StreamRole.MARKERS,
                    channels=(Channel(label="state_change"),),
                    nominal_rate_hz=0.0,
                    clock=clock,
                )
            )
        if not layout.signals:
            raise OpenFailed(
                "BCI2000 sends no control signal elements (only states); the App Connector "
                "plugin needs a control signal as its primary stream"
            )
        return SessionInfo(
            streams=tuple(streams),
            primary_stream=CONTROL_STREAM,
            synthetic=s.declare_synthetic,
            prerecorded=s.declare_prerecorded,
            origin=f"bci2000:{s.address[:64]}:{s.port} ({PROCESSED})",
        )

    # -------------------------------------------------------------- reading

    def _receive(self, timeout_s: float) -> list[tuple[bytes, float]]:
        sock = self._sock
        if sock is None:
            raise LinkLost("App Connector session is closed")
        out: list[tuple[bytes, float]] = []
        try:
            ready, _, _ = select.select([sock], [], [], max(0.0, timeout_s))
            while ready:
                data = sock.recv(_MAX_DATAGRAM)
                out.append((data, time.monotonic()))
                ready, _, _ = select.select([sock], [], [], 0.0)
        except OSError as exc:
            raise LinkLost(f"App Connector socket error: {exc}") from exc
        return out

    @property
    def info(self) -> SessionInfo:
        return self._info

    def read(self, timeout_s: float) -> Sequence[Chunk | MarkerChunk]:
        if self._sock is None:
            raise LinkLost("App Connector session is closed")
        blocks, self._pending = self._pending, []
        deadline = time.monotonic() + max(0.0, timeout_s)
        while not blocks:
            remaining = deadline - time.monotonic()
            received = self._receive(max(0.0, remaining))
            for data, t in received:
                try:
                    blocks.extend(self._assembler.feed(data, t))
                except LayoutChanged as exc:
                    raise ConfigurationChanged(f"BCI2000 configuration changed: {exc}") from exc
            if remaining <= 0:
                break
        self._watch_layout(blocks)
        return self._converter.convert(blocks)

    def _watch_layout(self, blocks: Sequence[RawBlock]) -> None:
        """A control signal that shrank never completes a block: detect it."""
        for b in blocks:
            if len(b.signals) == len(self.layout.signals):
                self._incomplete_run = 0
                continue
            shape = frozenset(b.signals)
            self._incomplete_run = self._incomplete_run + 1 if shape == self._last_shape else 1
            self._last_shape = shape
            if self._incomplete_run >= _LAYOUT_CHANGE_BLOCKS and shape:
                raise ConfigurationChanged(
                    f"BCI2000 configuration changed: {self._incomplete_run} consecutive blocks "
                    f"carry {len(shape)} of {len(self.layout.signals)} control signal elements"
                )

    def stats(self) -> Mapping[str, int | float]:
        a, c = self._assembler.stats, self._converter.stats
        return {
            "datagrams": a.datagrams,
            "lines": a.lines,
            "malformed_lines": a.malformed_lines,
            "unknown_names": a.unknown_names,
            "blocks": c.blocks,
            "incomplete_blocks": c.incomplete_blocks,
            "nonfinite_blocks": c.nonfinite_blocks,
            "dropped_packets": c.dropped_lines,
            "untimed_blocks": c.untimed_blocks,
            "out_of_order_blocks": c.out_of_order_blocks,
            "state_changes": c.state_changes,
        }

    def close(self) -> None:
        sock, self._sock = self._sock, None
        if sock is not None:
            try:
                sock.close()
            except OSError:
                log.exception("closing App Connector socket failed")


class BCI2000AppConnectorPlugin(SourcePlugin):
    manifest = PluginManifest(
        name="concord-bci2000",
        version=PLUGIN_VERSION,
        api_version=API_VERSION,
        display_name="BCI2000 App Connector",
        description=(
            "Receives BCI2000's App Connector output (ConnectorOutput filter, UDP): "
            f"{PROCESSED} — the control signal computed by BCI2000's signal processing "
            "and selected BCI2000 states. Receive-only: nothing is sent to BCI2000."
        ),
        author="Concord",
        license="Proprietary (internal preview)",
        roles=frozenset({StreamRole.DECODER_OUTPUT, StreamRole.BEHAVIOR, StreamRole.MARKERS}),
        homepage="https://www.bci2000.org",
        ecosystem="bci2000",
        network=True,
        options=OPTIONS,
    )

    def discover(self, timeout_s: float) -> Sequence[DeviceInfo]:
        # A UDP receiver cannot discover BCI2000 instances; one configurable entry.
        return [
            DeviceInfo(
                DEVICE_KEY,
                "BCI2000 App Connector (UDP)",
                f"Receives BCI2000 ConnectorOutput datagrams ({PROCESSED}). Set BCI2000's "
                "ConnectorOutputAddress to this plugin's address and port.",
                {"default_address": f"127.0.0.1:{DEFAULT_PORT}"},
            )
        ]

    def open(self, device_key: str, options: Mapping[str, Any]) -> SourceSession:
        if device_key != DEVICE_KEY:
            raise OpenFailed(f"unknown device {device_key!r}; expected {DEVICE_KEY!r}")
        settings = parse_settings(options)
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        except OSError as exc:
            raise OpenFailed(f"cannot create UDP socket: {exc}") from exc
        try:
            # One datagram per line: ask for a large receive buffer so a briefly busy
            # reader does not lose lines (best effort; the kernel caps it at rmem_max).
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, _RCVBUF_BYTES)
        except OSError:
            log.warning("could not enlarge the UDP receive buffer")
        try:
            sock.bind((settings.address, settings.port))
        except OSError as exc:
            sock.close()
            raise OpenFailed(
                f"cannot receive on {settings.address}:{settings.port}: {exc}. Is another "
                "program (or another Concord session) already bound to it?"
            ) from exc
        try:
            return AppConnectorSession(sock, settings)
        except BaseException:
            sock.close()
            raise
