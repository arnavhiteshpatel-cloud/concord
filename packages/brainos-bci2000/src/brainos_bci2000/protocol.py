"""BCI2000 App Connector protocol: line parsing and block assembly (pure, no I/O).

What BCI2000 sends (``src/shared/modules/application/ConnectorFilters.cpp``, BCI2000 3.6):

* ``ConnectorOutput::Process`` (lines 217-234) writes, once per data block and for every
  configured address, one line per state in StateList order ``"<StateName> <value>\\n"``
  (line 226) followed by one line per element of its input signal
  ``"Signal(<channel>,<element>) <value>\\n"`` (lines 227-229), channel-major, zero-based.
* ``ConnectorOutput::Connection::OnExecute`` (lines 243-264) sends each line as its own UDP
  datagram (``getline`` then ``mSocket.Write``).
* Before writing a block, ``Process`` calls ``Clear()`` (line 224; ``ConnectorFilters.h``
  ``Clear() { str(""); clear(); }``): lines of the previous block that the sender thread has
  not sent yet are discarded. Blocks can therefore be truncated at the end, in addition to
  ordinary UDP loss/reordering.
* State values are ``State::ValueType`` = ``uint32_t`` (``src/shared/types/State.h``) read at
  sample 0 of the block (``EnvironmentBase::State`` returns ``StateRef(..., 0)``,
  ``src/shared/accessors/Environment.cpp``). Signal values are ``double`` printed with the
  default ``std::ostream`` format (6 significant digits, like ``%g``).
* StateList order is definition order followed by alignment padding states ``__pad<N>``
  (``StateList::AddPadding``, ``src/shared/types/StateList.cpp``).

Block boundary rule derived from that order: a block starts with a state line; a new block
begins when a state line follows a Signal line, when a state or Signal element repeats
within the current block, or (once the layout is known) when the first state of the layout
arrives. Once the layout is known a block is complete as soon as its last Signal element
arrives (or, for a layout without Signal elements, its last state).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

STATE_LINE = re.compile(r"([A-Za-z_][A-Za-z0-9_]*) ([0-9]{1,10})")
SIGNAL_LINE = re.compile(r"Signal\(([0-9]{1,6}),([0-9]{1,6})\) (\S+)")
UINT32_MAX = 2**32 - 1
PADDING_PREFIX = "__pad"

SignalKey = tuple[int, int]


class LayoutChanged(Exception):
    """A Signal element outside the learned layout arrived (BCI2000 was reconfigured)."""


@dataclass
class RawBlock:
    recv_time: float  # receive time (monotonic seconds) of the block's first line
    states: dict[str, int] = field(default_factory=dict)
    state_order: list[str] = field(default_factory=list)
    signals: dict[SignalKey, float] = field(default_factory=dict)
    signal_order: list[SignalKey] = field(default_factory=list)

    def empty(self) -> bool:
        return not self.states and not self.signals


@dataclass(frozen=True)
class Layout:
    states: tuple[str, ...]  # StateList order as sent by BCI2000
    signals: tuple[SignalKey, ...]  # (channel, element), channel-major

    @property
    def channels(self) -> int:
        return 1 + max((c for c, _ in self.signals), default=-1)

    @property
    def elements(self) -> int:
        return 1 + max((e for _, e in self.signals), default=-1)


def parse_line(line: str) -> tuple[str, int] | tuple[SignalKey, float] | None:
    """Parse one App Connector line (without its newline). ``None`` if malformed."""
    m = SIGNAL_LINE.fullmatch(line)
    if m is not None:
        try:
            value = float(m.group(3))
        except ValueError:
            return None
        return (int(m.group(1)), int(m.group(2))), value
    if line.startswith("Signal("):
        return None
    m = STATE_LINE.fullmatch(line)
    if m is None:
        return None
    ivalue = int(m.group(2))
    if ivalue > UINT32_MAX:
        return None
    return m.group(1), ivalue


def layout_from(block: RawBlock) -> Layout | None:
    """The layout a block describes, if its Signal elements form a complete grid."""
    keys = block.signal_order
    if not block.state_order:
        return None
    if keys:
        n_ch = 1 + max(c for c, _ in keys)
        n_el = 1 + max(e for _, e in keys)
        grid = [(c, e) for c in range(n_ch) for e in range(n_el)]
        if sorted(keys) != grid:
            return None
        return Layout(tuple(block.state_order), tuple(grid))
    return Layout(tuple(block.state_order), ())


@dataclass
class AssemblerStats:
    datagrams: int = 0
    lines: int = 0
    malformed_lines: int = 0
    unknown_names: int = 0


class BlockAssembler:
    """Groups App Connector lines into blocks, following the boundary rule above."""

    def __init__(self) -> None:
        self.layout: Layout | None = None
        self.stats = AssemblerStats()
        self._cur: RawBlock | None = None
        self._layout_states: frozenset[str] = frozenset()
        self._layout_signals: frozenset[SignalKey] = frozenset()

    def set_layout(self, layout: Layout) -> None:
        self.layout = layout
        self._layout_states = frozenset(layout.states)
        self._layout_signals = frozenset(layout.signals)

    def feed(self, datagram: bytes, recv_time: float) -> list[RawBlock]:
        """Process one datagram; return the blocks it finished (in order)."""
        self.stats.datagrams += 1
        done: list[RawBlock] = []
        try:
            text = datagram.decode("ascii")
        except UnicodeDecodeError:
            self.stats.malformed_lines += 1
            return done
        if not text.endswith("\n"):
            # every App Connector line is newline-terminated; a datagram without one is not
            # protocol data (or was truncated)
            self.stats.malformed_lines += 1
            return done
        for line in text[:-1].split("\n"):
            self.stats.lines += 1
            parsed = parse_line(line)
            if parsed is None:
                self.stats.malformed_lines += 1
                continue
            name, value = parsed
            if isinstance(name, str):
                assert isinstance(value, int)
                self._on_state(name, value, recv_time, done)
            else:
                self._on_signal(name, float(value), recv_time, done)
        return done

    def flush(self) -> list[RawBlock]:
        """Finish the current block (e.g. when the session closes)."""
        out: list[RawBlock] = []
        self._finish(out)
        return out

    def _finish(self, out: list[RawBlock]) -> None:
        if self._cur is not None and not self._cur.empty():
            out.append(self._cur)
        self._cur = None

    def _block(self, t: float) -> RawBlock:
        if self._cur is None:
            self._cur = RawBlock(recv_time=t)
        return self._cur

    def _on_state(self, name: str, value: int, t: float, out: list[RawBlock]) -> None:
        lay = self.layout
        if lay is not None and name not in self._layout_states:
            self.stats.unknown_names += 1
            return
        cur = self._cur
        if cur is not None and (
            cur.signals
            or name in cur.states
            or (lay is not None and lay.states and name == lay.states[0] and not cur.empty())
        ):
            self._finish(out)
        cur = self._block(t)
        cur.states[name] = value
        cur.state_order.append(name)
        if lay is not None and not lay.signals and len(cur.states) == len(lay.states):
            self._finish(out)

    def _on_signal(self, key: SignalKey, value: float, t: float, out: list[RawBlock]) -> None:
        lay = self.layout
        if lay is not None and key not in self._layout_signals:
            raise LayoutChanged(
                f"Signal({key[0]},{key[1]}) is outside the control signal layout "
                f"({lay.channels} channels x {lay.elements} elements)"
            )
        cur = self._cur
        if cur is not None and key in cur.signals:
            self._finish(out)
        cur = self._block(t)
        cur.signals[key] = value
        cur.signal_order.append(key)
        if lay is not None and len(cur.signals) == len(lay.signals):
            self._finish(out)
