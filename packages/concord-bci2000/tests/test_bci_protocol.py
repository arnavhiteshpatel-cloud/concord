"""App Connector parsing, block assembly and conversion (pure; no sockets).

Datagrams come from ``connector_output.block_lines``, a byte-for-byte reproduction of
ConnectorOutput::Process / Connection::OnExecute (ConnectorFilters.cpp lines 217-264).
"""

from __future__ import annotations

import numpy as np
import pytest
from concord_adapter_sdk import Chunk, MarkerChunk
from concord_bci2000.convert import BlockConverter
from concord_bci2000.plugin import learn_layout
from concord_bci2000.protocol import BlockAssembler, Layout, LayoutChanged, RawBlock, parse_line
from connector_output import DEFAULT_STATES, block_lines, ostream_double

N_CH, N_EL = 2, 3
LAYOUT = Layout(DEFAULT_STATES, tuple((c, e) for c in range(N_CH) for e in range(N_EL)))


def states(source_time: int, target: int = 0, result: int = 0) -> list[tuple[str, int]]:
    values = {
        "Recording": 1,
        "Running": 1,
        "FilePart": 1,
        "SourceTime": source_time,
        "TargetCode": target,
        "ResultCode": result,
    }
    return [(n, values.get(n, 0)) for n in DEFAULT_STATES]


def signal(k: int) -> list[list[float]]:
    return [[k + 0.125 * c + 0.001 * e for e in range(N_EL)] for c in range(N_CH)]


def block(k: int, source_time: int, target: int = 0, result: int = 0) -> list[bytes]:
    return block_lines(states(source_time, target, result), signal(k))


def assemble(
    datagrams: list[bytes], t0: float = 100.0, dt: float = 0.0001, layout: Layout | None = LAYOUT
) -> tuple[BlockAssembler, list[RawBlock]]:
    asm = BlockAssembler()
    if layout is not None:
        asm.set_layout(layout)
    out: list[RawBlock] = []
    for i, d in enumerate(datagrams):
        out.extend(asm.feed(d, t0 + i * dt))
    return asm, out


def converter(**kw: object) -> BlockConverter:
    args: dict[str, object] = {"use_source_time": True}
    args.update(kw)
    return BlockConverter(
        LAYOUT, ("TargetCode", "ResultCode"), ("TargetCode", "ResultCode"), **args
    )  # type: ignore[arg-type]


def chunks(items: list[Chunk | MarkerChunk], sid: str) -> list[Chunk]:
    return [c for c in items if isinstance(c, Chunk) and c.stream_id == sid]


def test_parse_line_accepts_exactly_the_connector_output_format() -> None:
    assert parse_line("Running 1") == ("Running", 1)
    assert parse_line("SourceChannel1 2147483874") == ("SourceChannel1", 2147483874)
    assert parse_line("Signal(1,0) 1e-08") == ((1, 0), 1e-08)
    assert parse_line("Signal(0,7) -81.3793") == ((0, 7), -81.3793)
    value = parse_line("Signal(0,0) nan")
    assert value is not None and np.isnan(value[1])
    for bad in [
        "",
        "Running",
        "Running  1",
        "Running 1 2",
        "Running -1",
        "Running 1.5",
        "Running 4294967296",
        "Signal(0,0)",
        "Signal(0) 1",
        "Signal(a,0) 1",
        "Signal(0,0) abc",
        "Signal(0,0)  1",
        "1abc 2",
        " Running 1",
    ]:
        assert parse_line(bad) is None, bad


def test_ostream_formatting_matches_real_bci2000_lines() -> None:
    # values copied from the genuine capture (fixtures/bci2000_connector_output.json)
    for text in ["22.6223", "106.779", "100.11", "-81.3793", "-39.462"]:
        assert ostream_double(float(text)) == text
    assert ostream_double(1e-8) == "1e-08"


def test_block_boundaries_and_completion() -> None:
    data = block(0, 1000) + block(1, 1031) + block(2, 1062)
    asm, blocks = assemble(data)
    # with a known layout, each block completes at its last Signal element
    assert len(blocks) == 3
    assert [b.states["SourceTime"] for b in blocks] == [1000, 1031, 1062]
    assert blocks[1].signals[(1, 2)] == pytest.approx(1 + 0.125 + 0.002)
    assert asm.stats.malformed_lines == 0
    assert asm.stats.lines == len(data)


def test_layout_is_learned_from_two_identical_blocks_after_skipping_the_first() -> None:
    # joined mid-block: the first datagrams are the tail of a block
    data = block(0, 1000)[9:] + block(1, 1031) + block(2, 1062) + block(3, 1093)
    _, blocks = assemble(data, layout=None)
    found = learn_layout(blocks)
    assert found is not None
    layout, first = found
    assert layout == LAYOUT
    assert blocks[first].states["SourceTime"] == 1031


def test_lost_datagrams_skip_indices_in_the_affected_streams_only() -> None:
    b1 = block(1, 1031)
    del b1[-2]  # one control-signal element lost
    b2 = block(2, 1062)
    del b2[b2.index(b"TargetCode 0\n")]  # one selected state lost
    _, blocks = assemble(block(0, 1000) + b1 + b2 + block(3, 1093))
    conv = converter()
    out = conv.convert(blocks)
    ctrl = chunks(out, "control_signal")
    assert [(c.first_index, c.data.shape[0]) for c in ctrl] == [(0, 1), (2, 2)]
    beh = chunks(out, "states")
    assert [(c.first_index, c.data.shape[0]) for c in beh] == [(0, 2), (3, 1)]
    assert conv.stats.incomplete_blocks == 1
    assert conv.stats.dropped_lines == 2  # exactly the two datagrams removed


def test_truncated_block_end_is_handled() -> None:
    # Process() calls Clear(): unsent tail lines of a block are discarded (ConnectorFilters.cpp:224)
    b1 = block(1, 1031)[:16]
    _, blocks = assemble(block(0, 1000) + b1 + block(2, 1062))
    conv = converter()
    out = conv.convert(blocks)
    assert [c.first_index for c in chunks(out, "control_signal")] == [0, 2]
    assert conv.stats.incomplete_blocks == 1
    assert conv.stats.dropped_lines == len(block(1, 1031)) - 16


def test_lost_first_state_line_still_starts_a_new_block() -> None:
    b1 = block(1, 1031)[1:]  # "Notes" (first state) lost
    _, blocks = assemble(block(0, 1000) + b1 + block(2, 1062))
    assert [b.states["SourceTime"] for b in blocks] == [1000, 1031, 1062]
    assert all(len(b.signals) == N_CH * N_EL for b in blocks)


def test_reordered_lines_within_a_block() -> None:
    b1 = block(1, 1031)
    b1[-1], b1[-3] = b1[-3], b1[-1]  # two Signal datagrams swapped
    _, blocks = assemble(block(0, 1000) + b1 + block(2, 1062))
    conv = converter()
    out = conv.convert(blocks)
    ctrl = np.concatenate([c.data for c in chunks(out, "control_signal")])
    # element order follows the layout, not arrival order
    expected = np.array([np.ravel(signal(k)) for k in range(3)])
    assert np.array_equal(ctrl, expected)


def test_reordered_block_is_dropped_not_jumped_forward() -> None:
    # block 2 arrives before block 1: SourceTime would go backwards
    _, blocks = assemble(block(0, 1000) + block(2, 1062) + block(1, 1031) + block(3, 1093))
    conv = converter()
    out = conv.convert(blocks)
    ts = np.concatenate([c.timestamps for c in chunks(out, "control_signal")])
    assert np.all(np.diff(ts) >= 0)
    assert conv.stats.out_of_order_blocks == 1


def test_source_time_wrap_is_unwrapped() -> None:
    sts = [
        65500,
        65531,
        26,
        57,
    ]  # 16-bit ms counter wraps (PrecisionTime::NumType = unsigned short)
    data: list[bytes] = []
    for k, st in enumerate(sts):
        data += block(k, st)
    _, blocks = assemble(data, dt=0.031 / 30)
    out = converter().convert(blocks)
    ts = np.concatenate([c.timestamps for c in chunks(out, "control_signal")])
    assert np.allclose(np.diff(ts), 0.031)
    assert ts[0] == pytest.approx(65.5)


def test_long_pause_uses_receive_time_to_count_wraps() -> None:
    # 200 s pause between runs: SourceTime alone cannot tell how many times it wrapped
    asm = BlockAssembler()
    asm.set_layout(LAYOUT)
    blocks = []
    for d in block(0, 1000):
        blocks += asm.feed(d, 10.0)
    st_after = (1000 + 200_000) % 65536
    for d in block(1, st_after):
        blocks += asm.feed(d, 210.0)
    out = converter().convert(blocks)
    ts = np.concatenate([c.timestamps for c in chunks(out, "control_signal")])
    assert ts[1] - ts[0] == pytest.approx(200.0)


def test_wholly_lost_blocks_are_not_invented_from_source_time() -> None:
    # Blocks 1 and 2 never arrived. App Connector has no block counter and SourceTime is an
    # acquisition time that jitters (a genuine run showed a 62 ms step then ~0 ms), so the
    # plugin does not infer lost blocks: indices stay contiguous, the gap is in the timestamps.
    data = block(0, 1000) + block(3, 1094) + block(4, 1125)
    _, blocks = assemble(data)
    conv = converter()
    out = conv.convert(blocks)
    ctrl = chunks(out, "control_signal")
    assert [(c.first_index, c.data.shape[0]) for c in ctrl] == [(0, 3)]
    assert np.allclose(np.diff(ctrl[0].timestamps), [0.094, 0.031])
    assert conv.stats.dropped_lines == 0


def test_state_changes_become_markers() -> None:
    data = block(0, 1000, 0) + block(1, 1031, 2) + block(2, 1062, 2) + block(3, 1093, 0, 2)
    _, blocks = assemble(data)
    out = converter().convert(blocks)
    marks = [m for m in out if isinstance(m, MarkerChunk)]
    assert len(marks) == 1
    assert marks[0].labels == ("TargetCode 0->2", "TargetCode 2->0", "ResultCode 0->2")
    assert marks[0].timestamps.tolist() == [1.031, 1.093, 1.093]


def test_malformed_and_unknown_lines_are_counted_not_fatal() -> None:
    data = block(0, 1000)
    data.insert(3, b"garbage line\n")
    data.insert(4, b"Running 1")  # no newline
    data.insert(5, b"\xff\xfe\n")
    data.insert(6, b"Unknown_State 5\n")
    asm, blocks = assemble(data + block(1, 1031))
    assert asm.stats.malformed_lines == 3
    assert asm.stats.unknown_names == 1
    assert len(blocks) == 2


def test_multiline_datagram_is_accepted() -> None:
    joined = b"".join(block(0, 1000))
    _, blocks = assemble([joined])
    assert len(blocks) == 1 and len(blocks[0].signals) == N_CH * N_EL


def test_signal_outside_layout_raises_layout_changed() -> None:
    with pytest.raises(LayoutChanged):
        assemble([*block(0, 1000), b"Signal(5,0) 1\n"])


def test_nonfinite_control_values_are_not_forwarded() -> None:
    lines = block_lines(states(1000), [[float("nan"), 1, 2], [3, 4, 5]])
    _, blocks = assemble(lines + block(1, 1031))
    conv = converter()
    out = conv.convert(blocks)
    assert [c.first_index for c in chunks(out, "control_signal")] == [1]
    assert conv.stats.nonfinite_blocks == 1


def test_receive_time_clock_when_no_source_time() -> None:
    _, blocks = assemble(block(0, 1000) + block(1, 1031), t0=50.0, dt=0.001)
    out = converter(use_source_time=False).convert(blocks)
    ts = np.concatenate([c.timestamps for c in chunks(out, "control_signal")])
    assert ts[0] == pytest.approx(50.0)
    assert ts[1] == pytest.approx(50.0 + 0.001 * len(block(0, 0)))
