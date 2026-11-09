"""Open Ephys Binary comparison on synthetic recordings with injected defects.

The Binary layout written here is read back by the official open-ephys-python-tools reader
(REF-READER) in every test, so the fixtures follow the real format; real GUI output is tested
in test_openephys_gui.py.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from helpers import by_id, failed, status
from synth import BFrame, OECase, oe_device

from concord_hwval.compare_oe import OEOptions, compare_openephys
from concord_hwval.model import InputError
from concord_hwval.oe_ref import load_oe_recording


def run(case: OECase, tmp: Path, **kw: Any) -> dict[str, Any]:
    ref, b = case.write(tmp, **kw)
    return compare_openephys(ref, b, OEOptions())


def test_clean_recording_passes(tmp_path: Path) -> None:
    case = OECase()
    rep = run(case, tmp_path)
    st = status(rep)
    assert rep["result"] == "pass", rep["result_explanation"]
    assert st["REF-READER"] == "pass"  # the official reader parses the fixture identically
    assert st["CONCORD-FILE"] == "pass"
    v = by_id(rep)["VALUES"]["evidence"]
    assert v["values_out_of_tolerance"] == 0
    # quantisation: the difference is real but below half a step of 0.195 µV
    assert 0 < v["max_abs_diff"] <= 0.51 * 0.195
    assert st["EVENTS"] == "not_tested"
    assert by_id(rep)["EVENTS"]["required"] is False


def test_whole_directory_tree_is_resolved(tmp_path: Path) -> None:
    case = OECase()
    _ref, b = case.write(tmp_path)
    top = tmp_path / "ref"  # session folder above "Record Node 101"
    rep = compare_openephys(top, b, OEOptions())
    assert rep["result"] == "pass"
    (top / "Record Node 102" / "experiment1" / "recording1").mkdir(parents=True)
    (top / "Record Node 102" / "experiment1" / "recording1" / "structure.oebin").write_text(
        "{}", encoding="utf-8"
    )
    with pytest.raises(InputError, match="contains 2 recordings"):
        compare_openephys(top, b, OEOptions())


def test_packet_loss_whole_block(tmp_path: Path) -> None:
    case = OECase()
    frames = case.frames()
    del frames[10]
    frames[10].flags = ["dropped_samples"]  # what the adapter does after an incomplete block
    rep = run(case, tmp_path, frames=frames)
    assert {"LOSS", "SAMPLE-COUNT"} <= failed(rep)
    assert status(rep)["LOSS-FLAGGED"] == "pass"
    run0 = by_id(rep)["LOSS"]["evidence"]["runs"][0]
    assert run0["length"] == case.block
    assert run0["key"] == case.first_sample + (case.concord_start_block + 10) * case.block


def test_silent_loss(tmp_path: Path) -> None:
    case = OECase()
    frames = case.frames()
    del frames[3]
    rep = run(case, tmp_path, frames=frames)
    assert {"LOSS", "LOSS-FLAGGED"} <= failed(rep)


def test_duplicated_block(tmp_path: Path) -> None:
    case = OECase()
    frames = case.frames()
    frames.insert(
        6, BFrame(frames[5].index, frames[5].data.copy(), frames[5].t_dev_ns, frames[5].t_wall_ns)
    )
    rep = run(case, tmp_path, frames=frames)
    assert "DUPLICATES" in failed(rep)


def test_channel_order(tmp_path: Path) -> None:
    case = OECase()
    frames = case.frames()
    for f in frames:
        f.data[:, [0, 5]] = f.data[:, [5, 0]]
    rep = run(case, tmp_path, frames=frames)
    assert "CHANNEL-ORDER" in failed(rep)


def test_unit_error_mv_declared(tmp_path: Path) -> None:
    """Operator told Concord the GUI unit is mV: Concord multiplies by 1000."""
    case = OECase()
    frames = case.frames()
    for f in frames:
        f.data = f.data * 1e3
    rep = run(case, tmp_path, frames=frames, device=oe_device(case.names, case.rate, unit="mV"))
    assert {"SCALE", "META-UNITS"} <= failed(rep)
    assert by_id(rep)["SCALE"]["evidence"]["unit_factor"] == pytest.approx(1e3)


def test_arbitrary_unit_is_honest(tmp_path: Path) -> None:
    case = OECase()
    rep = run(
        case,
        tmp_path,
        frames=case.frames(unit="unknown"),
        device=oe_device(case.names, case.rate, unit="unknown"),
    )
    assert rep["result"] == "pass"
    assert "arbitrary" in by_id(rep)["META-UNITS"]["summary"]


def test_value_beyond_quantisation_fails(tmp_path: Path) -> None:
    case = OECase()
    frames = case.frames()
    frames[2].data[7, 1] += 0.2  # one step is 0.195 µV
    rep = run(case, tmp_path, frames=frames)
    assert failed(rep) == {"VALUES"}


def test_clipped_reference_samples_excluded(tmp_path: Path) -> None:
    case = OECase()
    a = case.concord_start_block * case.block + 100

    def clip(c: OECase) -> dict[str, Any]:
        s = c.i16.copy()
        s[a : a + 10, 2] = 32767  # saturated in the file; Concord has the true float
        return {"samples": s}

    rep = run(case, tmp_path, mutate_ref=clip)
    assert rep["result"] == "pass"
    per = by_id(rep)["VALUES"]["evidence"]["per_channel"][2]
    assert per["excluded_clipped_in_reference"] == 10


def test_ttl_events(tmp_path: Path) -> None:
    case = OECase()
    lo = case.first_sample + case.concord_start_block * case.block
    ev_sn = np.array([lo + 500, lo + 900, lo + 30_000, case.first_sample + 10])
    lines = np.array([0, 0, 3, 1])
    rising = np.array([1, 0, 1, 1])

    def ttl(_: OECase) -> dict[str, Any]:
        return {"ttl": (ev_sn, lines, rising)}

    def ann(sn: int, line: int, state: int) -> tuple[int, int, str, Any]:
        t = round(sn * 1e9 / case.rate)
        return (t, t, "ttl", f"line={line} state={state} word=0")

    good = [
        ann(int(s), int(ln), int(r)) for s, ln, r in zip(ev_sn[:3], lines, rising, strict=False)
    ]
    rep = run(case, tmp_path, mutate_ref=ttl, annotations=good)
    assert status(rep)["EVENTS"] == "pass"  # the 4th event precedes Concord: not compared
    assert by_id(rep)["EVENTS"]["evidence"]["reference_events_in_range"] == 3
    rep2 = run(case, tmp_path / "b", mutate_ref=ttl, annotations=good[:2])
    assert "EVENTS" in failed(rep2)
    assert by_id(rep2)["EVENTS"]["evidence"]["missing_in_concord"] == [[int(ev_sn[2]), 3, 1]]


def test_reference_sample_number_reset(tmp_path: Path) -> None:
    """The File Reader loops: sample numbers restart. Concord frames after the reset map."""
    case = OECase(seconds=6)
    half = case.n // 2
    sn = np.concatenate([case.sn[:half], np.arange(case.n - half, dtype=np.int64)])

    def reset(_: OECase) -> dict[str, Any]:
        return {"sample_numbers": sn}

    frames = []
    for a in range(case.concord_start_block * case.block, case.n - case.block, case.block):
        b = a + case.block
        if a < half <= b - 1:
            continue  # Concord cannot have a frame straddling the reset
        idx = int(sn[a])
        frames.append(
            BFrame(
                idx,
                case.float_uv[a:b].astype(np.float64),
                round(idx * 1e9 / case.rate),
                1_700_000_000_000_000_000 + round(b / case.rate * 1e9),
            )
        )
    rep = run(case, tmp_path, mutate_ref=reset, frames=frames)
    assert status(rep)["REF-CONTINUITY"] == "inconclusive"
    assert by_id(rep)["REF-CONTINUITY"]["evidence"]["regressions"] == 1
    assert status(rep)["VALUES"] == "pass"


def test_truncated_continuous_dat(tmp_path: Path) -> None:
    case = OECase()
    ref, b = case.write(tmp_path)
    dat = next(ref.rglob("continuous.dat"))
    with dat.open("r+b") as fh:
        fh.truncate(dat.stat().st_size - 3)
    rep = compare_openephys(ref, b, OEOptions())
    assert "REF-FILE" in failed(rep)


def test_processor_between_zmq_and_record_node(tmp_path: Path) -> None:
    case = OECase()

    def chain(_: OECase) -> dict[str, Any]:
        return {"history": "Acquisition Board -> ZMQ Interface -> Bandpass Filter -> Record Node"}

    frames = case.frames()
    for f in frames:
        f.data = f.data * 0.9  # the filter changed the recorded data, not Concord's
    rep = run(case, tmp_path, mutate_ref=chain, frames=frames)
    assert status(rep)["META-CHAIN"] == "inconclusive"
    assert status(rep)["VALUES"] == "inconclusive"
    assert rep["result"] == "inconclusive"


def test_file_reader_is_not_hardware(tmp_path: Path) -> None:
    case = OECase()

    def fr(_: OECase) -> dict[str, Any]:
        return {"source": "File Reader", "history": "File Reader -> ZMQ Interface -> Record Node"}

    rep = run(case, tmp_path, mutate_ref=fr)
    assert rep["result"] == "pass"
    assert any("File Reader" in r for r in rep["evidence_scope"]["not_a_hardware_run_because"])


def test_legacy_05_format(tmp_path: Path) -> None:
    case = OECase()

    def legacy(_: OECase) -> dict[str, Any]:
        return {"gui_version": "0.5.5", "history": None}

    rep = run(case, tmp_path, mutate_ref=legacy)
    assert status(rep)["META-CHAIN"] == "not_tested"
    assert status(rep)["VALUES"] == "pass"
    # open-ephys-python-tools 1.0.1 cannot read GUI < 0.6 files (KeyError
    # 'source_processor_sub_dx'): no cross-check, which is reported, not counted as a failure
    rr = by_id(rep)["REF-READER"]
    assert rr["status"] == "not_tested" and "source_processor_sub_dx" in rr["summary"]


def test_wrong_stream(tmp_path: Path) -> None:
    case = OECase()
    rep = run(case, tmp_path, device=oe_device(case.names, case.rate, stream="other"))
    assert "IDENTITY" in failed(rep)


def test_channel_subset_by_name(tmp_path: Path) -> None:
    case = OECase()
    sel = [1, 4, 6]
    frames = case.frames()
    for f in frames:
        f.data = f.data[:, sel]
    rep = run(
        case, tmp_path, frames=frames, device=oe_device([case.names[i] for i in sel], case.rate)
    )
    assert rep["result"] == "pass", rep["result_explanation"]
    assert by_id(rep)["META-CHANNELS"]["evidence"]["mapping"] == sel


def test_missing_oebin_is_input_error(tmp_path: Path) -> None:
    case = OECase()
    _, b = case.write(tmp_path)
    (tmp_path / "empty").mkdir()
    with pytest.raises(InputError, match=r"no structure\.oebin"):
        compare_openephys(tmp_path / "empty", b, OEOptions())


def test_reader_parses_official_layout(tmp_path: Path) -> None:
    case = OECase(seconds=1)
    ref, _ = case.write(tmp_path)
    rec = load_oe_recording(ref)
    s = rec.stream(None)
    assert s.n == case.n and np.array_equal(s.sample_numbers, case.sn)
    assert np.array_equal(np.asarray(s.samples), case.i16)
    oebin = json.loads((ref / "structure.oebin").read_text(encoding="utf-8"))
    assert s.folder_name == oebin["continuous"][0]["folder_name"].rstrip("/")
