"""Turn assembled App Connector blocks into BrainOS chunks (pure, no I/O).

Clock. BCI2000 defines ``SourceTime`` as a 16-bit state (``"SourceTime 16 0 0 0"``,
``src/shared/modules/signalsource/DataIOFilter.cpp``) set to ``PrecisionTime::Now()`` when a
block is acquired (``DataIOFilter::AcquireData``); ``PrecisionTime::Now`` is BCI2000's
monotonic clock in milliseconds truncated to 16 bits (``src/shared/utils/PrecisionTime.cpp``),
so it wraps every 65.536 s. When the layout contains ``SourceTime`` the block timestamp is the
unwrapped SourceTime in seconds (domain ``source``: BCI2000's own clock, arbitrary origin).
The number of wraps between two blocks is chosen so that the SourceTime difference best
matches the receive-time difference; this keeps pauses longer than 65 s (e.g. between runs)
correct. A block whose SourceTime would go backwards arrived out of order and is dropped.
Without ``SourceTime`` the timestamp is the receive time on this process's monotonic clock.

Indices and loss. Every observed block takes the next index; a stream skips the index of a
block in which its own lines were lost (gap = loss). ``dropped_packets`` counts datagrams
missing from observed blocks (the layout says how many lines each block has), plus the lines
of blocks dropped as out of order or untimed. A block whose datagrams were *all* lost
cannot be detected: App Connector carries no block or sample counter. SourceTime is not
one either -- it is the acquisition time, and in a genuine BCI2000 run (SignalGenerator,
32 blocks/s) one block arrived with a 62 ms SourceTime step followed by a ~0 ms step, so
inferring lost blocks from SourceTime steps would report losses that did not happen. Gaps
remain visible in the timestamps.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np
from brainos_adapter_sdk import Chunk, MarkerChunk

from brainos_bci2000.protocol import Layout, RawBlock

SOURCE_TIME = "SourceTime"
SOURCE_TIME_MODULUS = 65536  # ms

CONTROL_STREAM = "control_signal"
STATES_STREAM = "states"
CHANGES_STREAM = "state_changes"


@dataclass
class ConverterStats:
    blocks: int = 0
    incomplete_blocks: int = 0  # Signal elements missing (UDP loss or truncated block)
    nonfinite_blocks: int = 0  # control signal contained NaN/inf (not forwarded)
    dropped_lines: int = 0  # datagrams missing from observed blocks (or discarded with them)
    untimed_blocks: int = 0  # SourceTime clock, but the block's SourceTime line was lost
    out_of_order_blocks: int = 0
    state_changes: int = 0


class BlockConverter:
    def __init__(
        self,
        layout: Layout,
        behavior_states: Sequence[str],
        marker_states: Sequence[str],
        *,
        use_source_time: bool,
    ) -> None:
        self.layout = layout
        self.behavior_states = tuple(behavior_states)
        self.marker_states = tuple(marker_states)
        self.use_source_time = use_source_time
        self._lines_per_block = len(layout.states) + len(layout.signals)
        self.stats = ConverterStats()
        self._next_index = 0
        self._prev_st: int | None = None
        self._prev_t_ms = 0.0
        self._prev_recv = 0.0
        self._last_values: dict[str, int] = {}

    def _timestamp(self, block: RawBlock) -> tuple[float, int] | None:
        """(timestamp seconds, index) for a block, or None to drop it."""
        if not self.use_source_time:
            idx = self._next_index
            self._next_index += 1
            return block.recv_time, idx
        st = block.states.get(SOURCE_TIME)
        if st is None:
            self.stats.untimed_blocks += 1
            self._next_index += 1
            return None
        st %= SOURCE_TIME_MODULUS
        if self._prev_st is None:
            t_ms = float(st)
        else:
            d = (st - self._prev_st) % SOURCE_TIME_MODULUS
            elapsed_ms = (block.recv_time - self._prev_recv) * 1000.0
            wraps = round((elapsed_ms - d) / SOURCE_TIME_MODULUS)
            d_total = d + SOURCE_TIME_MODULUS * wraps
            if d_total < 0:
                self.stats.out_of_order_blocks += 1
                return None
            t_ms = self._prev_t_ms + d_total
        idx = self._next_index
        self._next_index += 1
        self._prev_st = st
        self._prev_t_ms = t_ms
        self._prev_recv = block.recv_time
        return t_ms / 1000.0, idx

    def convert(self, blocks: Sequence[RawBlock]) -> list[Chunk | MarkerChunk]:
        lay = self.layout
        ctrl: list[tuple[int, float, list[float]]] = []
        beh: list[tuple[int, float, list[float]]] = []
        labels: list[str] = []
        label_ts: list[float] = []
        for block in blocks:
            self.stats.blocks += 1
            stamp = self._timestamp(block)
            received = len(block.states) + len(block.signals)
            if stamp is None:
                # the whole block is discarded: its received lines count as lost too
                self.stats.dropped_lines += self._lines_per_block
                continue
            self.stats.dropped_lines += self._lines_per_block - received
            ts, idx = stamp
            if lay.signals:
                if len(block.signals) != len(lay.signals):
                    self.stats.incomplete_blocks += 1
                else:
                    values = [block.signals[k] for k in lay.signals]
                    if all(np.isfinite(values)):
                        ctrl.append((idx, ts, values))
                    else:
                        self.stats.nonfinite_blocks += 1
            if self.behavior_states and all(s in block.states for s in self.behavior_states):
                beh.append((idx, ts, [float(block.states[s]) for s in self.behavior_states]))
            for name in self.marker_states:
                if name not in block.states:
                    continue
                new = block.states[name]
                old = self._last_values.get(name)
                if old is not None and old != new:
                    labels.append(f"{name} {old}->{new}")
                    label_ts.append(ts)
                    self.stats.state_changes += 1
                self._last_values[name] = new
        out: list[Chunk | MarkerChunk] = []
        out.extend(_chunks(CONTROL_STREAM, ctrl))
        out.extend(_chunks(STATES_STREAM, beh))
        if labels:
            out.append(
                MarkerChunk(
                    stream_id=CHANGES_STREAM,
                    labels=tuple(labels),
                    timestamps=np.asarray(label_ts, dtype=np.float64),
                )
            )
        return out


def _chunks(stream_id: str, rows: list[tuple[int, float, list[float]]]) -> list[Chunk]:
    """Group rows into chunks of consecutive indices."""
    out: list[Chunk] = []
    start = 0
    for i in range(1, len(rows) + 1):
        if i == len(rows) or rows[i][0] != rows[i - 1][0] + 1:
            part = rows[start:i]
            out.append(
                Chunk(
                    stream_id=stream_id,
                    data=np.asarray([r[2] for r in part], dtype=np.float64),
                    timestamps=np.asarray([r[1] for r in part], dtype=np.float64),
                    first_index=part[0][0],
                )
            )
            start = i
    return out
