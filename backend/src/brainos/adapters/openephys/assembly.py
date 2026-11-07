"""Block assembly for the Open Ephys ZMQ stream (pure state machine, no I/O).

The plugin sends one ``data`` message per selected channel per processing block, all with
the same ``sample_num`` (loop over ``selectedChannels`` in ``ZmqInterface::process``), and
sends the block's TTL events and spikes *before* its data (``checkForEvents`` runs first).

:class:`BlockAssembler` turns that message sequence into items ready for normalization:

* :class:`FrameChunk` — one complete block (all learned channels, same length), split into
  chunks of at most ``max_frame_samples``. Incomplete blocks are **discarded and counted**;
  samples are never fabricated. The next chunk then carries ``dropped_before``.
* :class:`TTLItem` — held until the frame that covers its sample has been emitted, so
  device timestamps stay monotonic.
* :class:`SpikeBinItem` — spike counts per electrode on the sample clock. A bin is emitted
  only when its whole span is covered by emitted frames; bins that overlap a data gap are
  skipped (``bin_index`` then jumps) and their spikes counted as discarded.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import asdict, dataclass, field
from fractions import Fraction
from typing import Any

import numpy as np

from brainos.adapters.base import DeviceLinkError
from brainos.adapters.openephys.protocol import (
    DataMessage,
    EventMessage,
    Float32Array,
    SpikeMessage,
    TTLData,
)

#: consecutive blocks a learned channel may be missing before we call it deselected
MISSING_CHANNEL_BLOCKS = 3
MAX_PENDING_EVENTS = 4096


class ConfigurationChangedError(DeviceLinkError):
    """The stream layout changed (channels, rate, stream, restart). Reopen to re-learn."""

    def __init__(self, message: str, *, new_electrode: str | None = None) -> None:
        super().__init__(f"configuration changed: {message}")
        self.new_electrode = new_electrode


@dataclass(frozen=True, slots=True)
class StreamLayout:
    stream: str
    sample_rate: float
    #: (channel_num, channel_name) in the order the plugin sends them
    channels: tuple[tuple[int, str], ...]
    block_samples: int

    @property
    def channel_count(self) -> int:
        return len(self.channels)


@dataclass(frozen=True, slots=True)
class FrameChunk:
    first_sample_index: int
    samples: Float32Array  # [channel][sample], learned channel order
    dropped_before: bool


@dataclass(frozen=True, slots=True)
class TTLItem:
    sample_num: int
    source_node: int
    ttl: TTLData | None


@dataclass(frozen=True, slots=True)
class SpikeBinItem:
    bin_index: int
    counts: tuple[int, ...]
    incomplete: bool  # messages were lost while this bin was open


Item = FrameChunk | TTLItem | SpikeBinItem


@dataclass(slots=True)
class Counters:
    """Cumulative over the adapter's lifetime (all opens)."""

    opens: int = 0
    messages: int = 0
    bytes: int = 0
    data_messages: int = 0
    ttl_events: int = 0
    other_events: int = 0
    spikes: int = 0
    malformed: int = 0
    missed_messages: int = 0  # message_num gaps
    missing_samples: int = 0  # channel-samples never received (per-channel sample_num gaps)
    incomplete_blocks: int = 0  # blocks discarded because channel messages were missing
    discarded_samples: int = 0  # channel-samples received but discarded (incomplete block)
    nonfinite_blocks: int = 0  # blocks discarded because they contained NaN/Inf
    sample_regressions: int = 0
    duplicate_messages: int = 0
    resync_skipped_messages: int = 0  # data messages skipped while waiting for a block start
    frames_emitted: int = 0
    samples_emitted: int = 0  # per channel
    ttl_emitted: int = 0
    bins_emitted: int = 0
    spikes_binned: int = 0
    spikes_discarded: int = 0  # late, before the first bin, or inside a data gap
    spikes_unknown_electrode: int = 0
    events_overflow: int = 0
    discarded_while_paused: int = 0
    stalls: int = 0
    config_changes: int = 0
    heartbeats_sent: int = 0
    heartbeat_replies: int = 0
    heartbeat_timeouts: int = 0
    heartbeat_errors: int = 0

    def as_dict(self) -> dict[str, int]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class BinSpec:
    """Bins of ``bin_ms`` on the device sample clock; a bin is ``num/den`` samples long."""

    bin_ms: float
    num: int
    den: int

    @classmethod
    def create(cls, bin_ms: float, sample_rate: float) -> BinSpec:
        length = Fraction(bin_ms) * Fraction(sample_rate) / 1000
        if length <= 0:
            raise ValueError("bin length must be positive")
        return cls(bin_ms, length.numerator, length.denominator)

    def index(self, sample: int) -> int:
        return (sample * self.den) // self.num

    def first_starting_at_or_after(self, sample: int) -> int:
        return -((-sample * self.den) // self.num)

    def ends_by(self, index: int, sample: int) -> bool:
        """True if bin ``index`` ends at or before ``sample``."""
        return (index + 1) * self.num <= sample * self.den


@dataclass(slots=True)
class _Block:
    sample_num: int
    parts: dict[int, Float32Array] = field(default_factory=dict)


class BlockAssembler:
    def __init__(
        self,
        layout: StreamLayout,
        counters: Counters,
        *,
        max_frame_samples: int,
        electrodes: Sequence[str] = (),
        bin_spec: BinSpec | None = None,
        fixed_electrodes: bool = False,
    ) -> None:
        self.layout = layout
        self.counters = counters
        self.max_frame_samples = max_frame_samples
        self._order = [c for c, _ in layout.channels]
        self._names = dict(layout.channels)
        self._electrode_index = {e: i for i, e in enumerate(electrodes)}
        self._bins = bin_spec if electrodes else None
        self._fixed_electrodes = fixed_electrodes
        self.resync()

    # ------------------------------------------------------------------ state
    def resync(self) -> None:
        """Forget continuity (start, after a pause). Waits for the next block start."""
        self._waiting_for_start = True
        self._block: _Block | None = None
        self._next_expected: dict[int, int] = {}
        self._missing_streak: dict[int, int] = {}
        self._last_frame_end: int | None = None
        self._dropped_pending = False
        self._pending_ttl: list[TTLItem] = []
        self._pending_spikes: list[tuple[int, int]] = []  # (sample_num, electrode index)
        self._bin_counts: dict[int, list[int]] = {}
        self._next_bin: int | None = None
        self._bins_incomplete = False

    def note_message_gap(self) -> None:
        """Messages were lost: any of them may have been spikes."""
        self._bins_incomplete = True

    # --------------------------------------------------------------- messages
    def on_data(self, msg: DataMessage) -> list[Item]:
        lay = self.layout
        if msg.stream != lay.stream:
            raise ConfigurationChangedError(f"stream '{lay.stream}' -> '{msg.stream}'")
        if msg.sample_rate != lay.sample_rate:
            raise ConfigurationChangedError(
                f"sample rate {lay.sample_rate} Hz -> {msg.sample_rate} Hz"
            )
        name = self._names.get(msg.channel_num)
        if name is None:
            raise ConfigurationChangedError(
                f"channel {msg.channel_num} ('{msg.channel_name}') was not in the learned "
                "channel selection"
            )
        if name != msg.channel_name:
            raise ConfigurationChangedError(
                f"channel {msg.channel_num} renamed '{name}' -> '{msg.channel_name}'"
            )
        if msg.num_samples == 0:
            return []

        items: list[Item] = []
        if self._block is not None and msg.sample_num != self._block.sample_num:
            items += self._finalize()
        if self._waiting_for_start:
            if msg.channel_num != self._order[0]:
                self.counters.resync_skipped_messages += 1
                return items
            self._start_after_resync(msg.sample_num)
        if self._block is None:
            if self._last_frame_end is not None and msg.sample_num < self._last_frame_end:
                raise ConfigurationChangedError(
                    f"sample clock went backwards ({self._last_frame_end} -> {msg.sample_num}); "
                    "acquisition restarted?"
                )
            self._block = _Block(msg.sample_num)

        ch = msg.channel_num
        expected = self._next_expected.get(ch)
        if expected is not None and msg.sample_num != expected:
            if msg.sample_num > expected:
                self.counters.missing_samples += msg.sample_num - expected
            else:
                self.counters.sample_regressions += 1
            self._dropped_pending = True
        self._next_expected[ch] = msg.sample_num + msg.num_samples

        if ch in self._block.parts:
            self.counters.duplicate_messages += 1
            return items
        self._block.parts[ch] = msg.samples()
        if len(self._block.parts) == len(self._order):
            items += self._finalize()
        return items

    def on_event(self, msg: EventMessage) -> list[Item]:
        if not msg.is_ttl:
            self.counters.other_events += 1
            return []
        self.counters.ttl_events += 1
        item = TTLItem(msg.sample_num, msg.source_node, msg.ttl)
        if self._last_frame_end is not None and msg.sample_num < self._last_frame_end:
            # late: its frame was already emitted; emit now with its true timestamp
            self.counters.ttl_emitted += 1
            return [item]
        if len(self._pending_ttl) >= MAX_PENDING_EVENTS:
            self.counters.events_overflow += 1
            self._pending_ttl.pop(0)
        self._pending_ttl.append(item)
        return []

    def on_spike(self, msg: SpikeMessage) -> None:
        self.counters.spikes += 1
        idx = self._electrode_index.get(msg.electrode)
        if idx is None:
            if self._fixed_electrodes:
                self.counters.spikes_unknown_electrode += 1
                return
            raise ConfigurationChangedError(
                f"new spike electrode '{msg.electrode}'", new_electrode=msg.electrode
            )
        if self._bins is None:
            return
        if self._next_bin is None:
            if len(self._pending_spikes) >= MAX_PENDING_EVENTS:
                self.counters.events_overflow += 1
                self._pending_spikes.pop(0)
            self._pending_spikes.append((msg.sample_num, idx))
            return
        self._count_spike(msg.sample_num, idx)

    # ---------------------------------------------------------------- helpers
    def _start_after_resync(self, sample_num: int) -> None:
        self._waiting_for_start = False
        self._pending_ttl = [t for t in self._pending_ttl if t.sample_num >= sample_num]
        if self._bins is not None:
            self._next_bin = self._bins.first_starting_at_or_after(sample_num)
            pending, self._pending_spikes = self._pending_spikes, []
            for s, idx in pending:
                self._count_spike(s, idx)

    def _count_spike(self, sample_num: int, idx: int) -> None:
        assert self._bins is not None and self._next_bin is not None
        b = self._bins.index(sample_num)
        if b < self._next_bin:
            self.counters.spikes_discarded += 1
            return
        counts = self._bin_counts.get(b)
        if counts is None:
            counts = self._bin_counts[b] = [0] * len(self._electrode_index)
        counts[idx] += 1

    def _finalize(self) -> list[Item]:
        block, self._block = self._block, None
        assert block is not None
        n_ch = len(self._order)
        lengths = {a.size for a in block.parts.values()}
        if len(block.parts) < n_ch or len(lengths) != 1:
            self.counters.incomplete_blocks += 1
            self.counters.discarded_samples += sum(a.size for a in block.parts.values())
            self._dropped_pending = True
            for ch in self._order:
                if ch in block.parts:
                    self._missing_streak[ch] = 0
                    continue
                streak = self._missing_streak.get(ch, 0) + 1
                self._missing_streak[ch] = streak
                if streak >= MISSING_CHANNEL_BLOCKS:
                    raise ConfigurationChangedError(
                        f"channel {ch} ('{self._names[ch]}') missing from {streak} consecutive "
                        "blocks (deselected?)"
                    )
            return []
        self._missing_streak.clear()
        data = np.stack([block.parts[ch] for ch in self._order])
        n = data.shape[1]
        if not np.isfinite(data).all():
            self.counters.nonfinite_blocks += 1
            self.counters.discarded_samples += data.size
            self._dropped_pending = True
            return []
        start = block.sample_num
        if self._last_frame_end is not None and start != self._last_frame_end:
            self._dropped_pending = True
        dropped, self._dropped_pending = self._dropped_pending, False
        if dropped and self._bins is not None and self._next_bin is not None:
            # a bin is emitted only if its whole span is covered by emitted frames
            first = self._bins.first_starting_at_or_after(start)
            for b in [b for b in self._bin_counts if b < first]:
                self.counters.spikes_discarded += sum(self._bin_counts.pop(b))
            self._next_bin = max(self._next_bin, first)

        data.flags.writeable = False
        items: list[Item] = []
        step = self.max_frame_samples
        for off in range(0, n, step):
            items.append(FrameChunk(start + off, data[:, off : off + step], dropped and off == 0))
        self.counters.frames_emitted += len(items)
        self.counters.samples_emitted += n
        end = start + n
        self._last_frame_end = end

        ready = [t for t in self._pending_ttl if t.sample_num < end]
        if ready:
            self._pending_ttl = [t for t in self._pending_ttl if t.sample_num >= end]
            self.counters.ttl_emitted += len(ready)
            items += ready
        if self._bins is not None and self._next_bin is not None:
            zero = [0] * len(self._electrode_index)
            while self._bins.ends_by(self._next_bin, end):
                b = self._next_bin
                counts = self._bin_counts.pop(b, zero)
                self.counters.spikes_binned += sum(counts)
                items.append(SpikeBinItem(b, tuple(counts), self._bins_incomplete))
                self.counters.bins_emitted += 1
                self._next_bin = b + 1
                if not self._bins.ends_by(self._next_bin, end):
                    self._bins_incomplete = False
        return items

    def state(self) -> dict[str, Any]:
        return {
            "waiting_for_block_start": self._waiting_for_start,
            "last_frame_end_sample": self._last_frame_end,
            "pending_ttl": len(self._pending_ttl),
            "next_bin": self._next_bin,
        }
