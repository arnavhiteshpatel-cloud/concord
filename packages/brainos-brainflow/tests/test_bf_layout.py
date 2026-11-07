"""Metadata mapping from BrainFlow's own board descriptions (get_board_descr, no hardware)
and package-counter loss inference."""

from __future__ import annotations

import numpy as np
import pytest
from brainflow.board_shim import BoardIds, BoardShim
from brainos_adapter_sdk import Modality
from brainos_brainflow.counter import PackageCounter
from brainos_brainflow.layout import MICROVOLTS, build_layout, row_types


def layout_of(name: str):  # type: ignore[no-untyped-def]
    return build_layout(name, BoardShim.get_board_descr(BoardIds[name].value))


def test_every_brainflow_board_description_maps_cleanly() -> None:
    for board in BoardIds:
        if board.name in ("NO_BOARD", "PLAYBACK_FILE_BOARD", "STREAMING_BOARD"):
            continue
        descr = BoardShim.get_board_descr(board.value)
        lay = build_layout(board.name, descr)
        assert lay.sampling_rate == float(descr["sampling_rate"])
        seen: set[int] = set()
        for stream in lay.signal_streams:
            labels = [c.label for c in stream.spec.channels]
            assert len(labels) == len(set(labels)), board.name
            assert not seen & set(stream.rows)
            seen |= set(stream.rows)
            if stream.spec.modality is None:
                assert stream.spec.invasive is None
            else:
                assert stream.spec.invasive in (False, None)  # never claimed invasive
        assert lay.timestamp_row not in seen
        assert lay.package_num_row not in seen


def test_cyton_rows_are_ambiguous_and_eeg_names_are_used() -> None:
    lay = layout_of("CYTON_BOARD")
    exg = lay.signal_streams[0].spec
    assert [c.label for c in exg.channels] == ["Fp1", "Fp2", "C3", "C4", "P7", "P8", "O1", "O2"]
    assert {c.type for c in exg.channels} == {"EEG|EMG|ECG|EOG"}
    assert exg.modality is None and exg.invasive is None
    assert {c.unit for c in exg.channels} == {MICROVOLTS}
    aux = lay.signal_streams[1].spec
    assert {c.type for c in aux.channels} == {"ACCEL", "OTHER", "ANALOG"}
    assert all(c.unit is None for c in aux.channels)


def test_eeg_only_board_is_noninvasive_eeg() -> None:
    lay = layout_of("MUSE_2_BOARD")
    exg = lay.signal_streams[0].spec
    assert exg.modality is Modality.EEG and exg.invasive is False
    assert [c.label for c in exg.channels] == ["TP9", "AF7", "AF8", "TP10"]


def test_eeg_rows_also_listed_as_resistance_have_no_unit() -> None:
    lay = layout_of("ANT_NEURO_EE_411_BOARD")
    exg = lay.signal_streams[0].spec
    mixed = [c for c in exg.channels if c.type == "EEG|RESISTANCE"]
    assert mixed and all(c.unit is None for c in mixed)
    assert exg.modality is None


def test_documented_adc_boards_have_no_microvolt_unit() -> None:
    lay = layout_of("GFORCE_PRO_BOARD")
    exg = lay.signal_streams[0].spec
    assert exg.modality is Modality.EMG and exg.invasive is False
    assert {c.unit for c in exg.channels} == {None}


def test_row_types_lists_battery_and_every_type() -> None:
    types = row_types(BoardShim.get_board_descr(BoardIds.SYNTHETIC_BOARD.value))
    assert types[29] == ("BATTERY",)
    assert types[1] == ("EEG", "EMG", "ECG", "EOG")


def test_counter_wrap_gap_repeat_and_chunk_boundaries() -> None:
    c = PackageCounter(256)
    a = c.assign(np.array([250.0, 251, 252, 253, 254, 255]))
    b = c.assign(np.array([0.0, 1, 4, 5, 5, 6]))  # wrap, 2 lost (2,3), 1 repeat
    assert a.tolist() == [0, 1, 2, 3, 4, 5]
    assert b.tolist() == [6, 7, 10, 11, 12, 13]
    assert c.dropped == 2 and c.repeats == 1
    d = c.assign(np.array([9.0]))  # gap across the chunk boundary: 7, 8 lost
    assert d.tolist() == [16] and c.dropped == 4


def test_counter_disables_itself_on_values_outside_its_range() -> None:
    c = PackageCounter(256)
    c.assign(np.array([0.0, 1, 2]))
    idx = c.assign(np.array([300.0, 301]))
    assert c.unusable and not c.enabled
    assert idx.tolist() == [3, 4]  # no invented gap
    assert c.dropped == 0


@pytest.mark.parametrize("modulus", [0])
def test_counter_off(modulus: int) -> None:
    c = PackageCounter(modulus)
    assert c.assign(np.array([5.0, 9.0, 1.0])).tolist() == [0, 1, 2]
    assert c.dropped == 0
