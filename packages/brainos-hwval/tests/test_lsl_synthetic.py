"""LSL / XDF comparison on synthetic sessions with known, injected defects.

Every defect named in the assignment is injected into an otherwise perfect pair (an XDF file
read back by pyxdf, a BrainOS recording validated against BrainOS's contract models) and must
be reported by the specific check, with the evidence, while the clean pair passes.
"""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import numpy as np
import pytest
import pyxdf
from helpers import by_id, failed, status
from synth import BFrame, LSLCase, lsl_provenance, write_xdf

from brainos_hwval.compare_lsl import LSLOptions, compare_lsl
from brainos_hwval.model import InputError, Thresholds


def run(case: LSLCase, tmp: Path, **kw: Any) -> dict[str, Any]:
    x, b = case.write(tmp, **kw)
    return compare_lsl(x, b, LSLOptions())


def test_synthetic_xdf_is_valid_for_pyxdf(tmp_path: Path) -> None:
    case = LSLCase()
    x, _ = case.write(tmp_path)
    streams, _ = pyxdf.load_xdf(str(x), synchronize_clocks=False, dejitter_timestamps=False)
    s = streams[0]
    assert np.array_equal(s["time_series"], case.values)
    assert np.array_equal(s["time_stamps"], case.stamps)
    assert s["info"]["desc"][0]["channels"][0]["channel"][2]["label"] == ["C3"]


def test_clean_session_passes(tmp_path: Path) -> None:
    case = LSLCase()
    rep = run(case, tmp_path)
    st = status(rep)
    assert rep["result"] == "pass", rep["result_explanation"]
    assert st["BOS-FILE"] == "pass"  # synthetic envelopes satisfy BrainOS's contract models
    assert by_id(rep)["BOS-FILE"]["evidence"]["contract"]["validated"] is True
    assert st["IDENTITY"] == "pass"
    v = by_id(rep)["VALUES"]["evidence"]
    assert v["values_out_of_tolerance"] == 0
    assert v["values_exactly_equal"] == v["values_compared"] > 0
    assert rep["summary"]["missing_in_brainos"] == 0
    # BrainOS started 250 samples after LabRecorder: outside the overlap, not loss
    assert by_id(rep)["OVERLAP"]["evidence"]["overlap_rows"] == case.n - 250 - 100
    assert rep["evidence_scope"]["hardware_verified"] is False
    assert by_id(rep)["DELAY"]["status"] == "pass"


def test_dropped_frame_is_loss_and_silent(tmp_path: Path) -> None:
    case = LSLCase()
    frames = case.frames()
    del frames[40]
    rep = run(case, tmp_path, frames=frames)
    assert rep["result"] == "fail"
    assert {"LOSS", "SAMPLE-COUNT", "LOSS-FLAGGED"} <= failed(rep)
    loss = by_id(rep)["LOSS"]["evidence"]
    assert loss["missing_samples"] == case.frame
    assert loss["runs"][0]["reference_row"] == case.bos_start + 40 * case.frame
    assert failed(rep).isdisjoint({"VALUES", "DUPLICATES", "EXTRA", "TS-AGREE"})


def test_flagged_loss_is_still_loss_but_not_silent(tmp_path: Path) -> None:
    case = LSLCase()
    frames = case.frames()
    del frames[40]
    frames[40].flags = ["dropped_samples"]
    rep = run(case, tmp_path, frames=frames)
    assert "LOSS" in failed(rep)
    assert status(rep)["LOSS-FLAGGED"] == "pass"


def test_loss_tolerance_is_explicit(tmp_path: Path) -> None:
    case = LSLCase()
    frames = case.frames()
    del frames[40]
    frames[40].flags = ["dropped_samples"]
    x, b = case.write(tmp_path, frames=frames)
    rep = compare_lsl(x, b, LSLOptions(thresholds=Thresholds(max_loss_fraction=0.01)))
    assert status(rep)["LOSS"] == "pass"
    assert rep["thresholds"]["max_loss_fraction"] == 0.01
    assert rep["summary"]["missing_in_brainos"] == case.frame  # still reported


def test_duplicated_frame(tmp_path: Path) -> None:
    case = LSLCase()
    frames = case.frames()
    frames.insert(31, copy.deepcopy(frames[30]))
    rep = run(case, tmp_path, frames=frames)
    assert "DUPLICATES" in failed(rep)
    assert by_id(rep)["DUPLICATES"]["evidence"]["duplicated_samples"] == case.frame


def test_altered_value(tmp_path: Path) -> None:
    case = LSLCase()
    frames = case.frames()
    frames[12].data[3, 2] += 0.5
    rep = run(case, tmp_path, frames=frames)
    assert failed(rep) == {"VALUES"}
    ex = by_id(rep)["VALUES"]["evidence"]["examples"][0]
    assert ex["reference_row"] == case.bos_start + 12 * case.frame + 3
    assert ex["channel"] == 2
    assert status(rep)["CHANNEL-ORDER"] == "inconclusive"


def test_float32_rounding_is_tolerance_not_corruption(tmp_path: Path) -> None:
    case = LSLCase(fmt="double64")
    case.values = case.values.astype(np.float64) + 1e-3  # not representable in float32
    frames = case.frames()
    for f in frames:
        f.data = f.data.astype(np.float32).astype(np.float64)
    x, b = case.write(tmp_path, frames=frames)
    rep = compare_lsl(x, b, LSLOptions())
    assert status(rep)["VALUES"] == "pass"
    v = by_id(rep)["VALUES"]["evidence"]
    assert v["values_exactly_equal"] < v["values_compared"]
    strict = compare_lsl(x, b, LSLOptions(thresholds=Thresholds(value_rtol=0.0)))
    assert status(strict)["VALUES"] == "fail"


def test_channel_swap_detected(tmp_path: Path) -> None:
    case = LSLCase()
    frames = case.frames()
    for f in frames:
        f.data[:, [1, 3]] = f.data[:, [3, 1]]
    rep = run(case, tmp_path, frames=frames)
    assert "CHANNEL-ORDER" in failed(rep)
    perm = by_id(rep)["CHANNEL-ORDER"]["evidence"]["permutation"]
    assert {(p["brainos_channel"], p["carries_reference_channel"]) for p in perm} == {
        (1, 3),
        (3, 1),
    }
    assert by_id(rep)["CHANNEL-ORDER"]["evidence"]["labels_follow_data"] is False


def test_channel_swap_with_labels(tmp_path: Path) -> None:
    case = LSLCase()
    frames = case.frames()
    for f in frames:
        f.data[:, [0, 2]] = f.data[:, [2, 0]]
    labels = list(case.labels)
    labels[0], labels[2] = labels[2], labels[0]
    rep = run(case, tmp_path, frames=frames, device=case.device(labels=labels))
    assert {"CHANNEL-ORDER", "META-CHANNELS"} <= failed(rep)
    assert by_id(rep)["CHANNEL-ORDER"]["evidence"]["labels_follow_data"] is True


@pytest.mark.parametrize("factor", [1e3, 1e-3])
def test_unit_error_detected(tmp_path: Path, factor: float) -> None:
    case = LSLCase()
    frames = case.frames()
    for f in frames:
        f.data = f.data * factor
    rep = run(case, tmp_path, frames=frames)
    assert "SCALE" in failed(rep)
    assert by_id(rep)["SCALE"]["evidence"]["unit_factor"] == pytest.approx(factor)


def test_millivolt_reference_converted(tmp_path: Path) -> None:
    case = LSLCase(units="millivolts")
    rep = run(case, tmp_path)  # BrainOS frames are µV = mV x 1000
    assert rep["result"] == "pass", rep["result_explanation"]
    assert by_id(rep)["META-UNITS"]["evidence"]["factors_to_uV"] == [1000.0] * 4


def test_unit_label_misinterpreted(tmp_path: Path) -> None:
    case = LSLCase()
    frames = case.frames()
    for f in frames:
        f.unit = "arbitrary"
    rep = run(case, tmp_path, frames=frames)
    assert "META-UNITS" in failed(rep)


def test_unknown_units_must_be_arbitrary(tmp_path: Path) -> None:
    case = LSLCase(units="counts")
    frames = case.frames()
    for f in frames:
        f.unit = "arbitrary"
    rep = run(case, tmp_path, frames=frames, device=case.device(unit="arbitrary"))
    assert rep["result"] == "pass", rep["result_explanation"]
    rep2 = run(case, tmp_path)  # frames claim µV without a basis
    assert "META-UNITS" in failed(rep2)


def test_timestamps_shifted_by_whole_samples(tmp_path: Path) -> None:
    """Timestamps of another sample: content locates the data 5 samples earlier."""
    case = LSLCase()
    frames = case.frames()
    for f in frames:
        assert f.t_dev_ns is not None
        f.t_dev_ns += round(5 / case.rate * 1e9)
    rep = run(case, tmp_path, frames=frames)
    assert {"TS-AGREE", "ALIGN-CONTENT", "VALUES"} <= failed(rep)
    d = by_id(rep)["ALIGN-CONTENT"]["evidence"]["disagreements"][0]
    assert d["offset_rows"] == -5


def test_timestamps_offset_sub_sample(tmp_path: Path) -> None:
    case = LSLCase()
    frames = case.frames()
    for f in frames:
        assert f.t_dev_ns is not None
        f.t_dev_ns += 600_000  # 0.6 ms at 500 Hz: between samples
    rep = run(case, tmp_path, frames=frames)
    assert {"TS-AGREE", "EXTRA"} <= failed(rep)
    errs = by_id(rep)["TS-AGREE"]["evidence"]["content_timestamp_errors_s"]
    assert errs and all(abs(e - 0.0006) < 1e-6 for e in errs)


def test_brainos_clock_drift_detected(tmp_path: Path) -> None:
    case = LSLCase()
    frames = case.frames()
    t0 = frames[0].t_dev_ns
    assert t0 is not None
    for f in frames:
        assert f.t_dev_ns is not None
        f.t_dev_ns = t0 + round((f.t_dev_ns - t0) * (1 + 200e-6))  # 200 ppm fast clock
    rep = run(case, tmp_path, frames=frames)
    assert "TS-AGREE" in failed(rep)
    assert by_id(rep)["RATE-EFFECTIVE"]["evidence"]["brainos_ppm"] == pytest.approx(-200, abs=2)


def test_reference_clock_drift_characterised(tmp_path: Path) -> None:
    case = LSLCase(seconds=30)
    clock = [(case.t0 + t + 0.25 + 20e-6 * t, 0.25 + 20e-6 * t) for t in range(0, 30, 2)]
    rep = run(case, tmp_path, xstream=case.xstream(clock=clock))
    c = by_id(rep)["CLOCKS"]["evidence"]["labrecorder_clock_offsets"]
    assert c["drift_ppm"] == pytest.approx(20.0, rel=0.01)
    assert rep["result"] == "pass"  # an offset between clock domains is not an error


def test_bogus_clock_offset_discarded(tmp_path: Path) -> None:
    """LabRecorder writes a zero-time offset when a time-correction query times out."""
    case = LSLCase()
    clock = [(case.t0 + 1.0, 0.0), (case.t0 + 6.0, 0.0), (6.9e-310, 0.0)]
    rep = run(case, tmp_path, xstream=case.xstream(clock=clock))
    c = by_id(rep)["CLOCKS"]["evidence"]["labrecorder_clock_offsets"]
    assert c["discarded"] == 1 and c["usable"] == 2


def test_reordered_frames(tmp_path: Path) -> None:
    case = LSLCase()
    frames = case.frames()
    a, b = frames[20], frames[21]
    a.data, b.data = b.data, a.data
    a.t_dev_ns, b.t_dev_ns = b.t_dev_ns, a.t_dev_ns
    a.index, b.index = b.index, a.index
    rep = run(case, tmp_path, frames=frames)
    assert "ORDER" in failed(rep)


def test_source_gap_in_both_is_not_brainos_loss(tmp_path: Path) -> None:
    """Samples the source never sent are absent from both recordings."""
    case = LSLCase()
    gap = slice(2000, 2100)
    keep = np.ones(case.n, bool)
    keep[gap] = False
    xs = case.xstream(values=case.values[keep], stamps=case.stamps[keep])
    frames = case.frames()
    out = []
    for f in frames:
        a = f.index + case.bos_start
        rows = [r for r in range(a, a + f.data.shape[0]) if keep[r]]
        if not rows:
            continue
        # BrainOS splits frames at gaps; samples stay consecutive in its own index
        out.append(
            BFrame(
                0,
                case.values[rows].astype(np.float64),
                round(float(case.stamps[rows[0]]) * 1e9),
                f.t_wall_ns,
                ["dropped_samples"] if rows[0] == gap.stop else [],
            )
        )
    idx = 0
    for f in out:
        f.index = idx
        idx += f.data.shape[0]
    rep = run(case, tmp_path, xstream=xs, frames=out)
    st = status(rep)
    assert st["LOSS"] == "pass" and st["VALUES"] == "pass"
    assert st["REF-CONTINUITY"] == "inconclusive"
    assert by_id(rep)["REF-CONTINUITY"]["required"] is False
    assert rep["result"] == "pass"


def test_reference_gap_brainos_has_data(tmp_path: Path) -> None:
    """LabRecorder lost samples that BrainOS has: unverifiable, not a BrainOS error."""
    case = LSLCase()
    keep = np.ones(case.n, bool)
    keep[3000:3100] = False
    rep = run(
        case, tmp_path, xstream=case.xstream(values=case.values[keep], stamps=case.stamps[keep])
    )
    assert status(rep)["EXTRA"] == "inconclusive"
    assert rep["result"] == "inconclusive"


@pytest.mark.parametrize(
    ("change", "check"),
    [
        ({"rate": 250.0}, "META-RATE"),
        ({"labels": ["C1", "C2", "X3", "C4"]}, "META-CHANNELS"),
        ({"fmt": "int16"}, "META-FORMAT"),
        ({"stype": "ECoG"}, "META-FORMAT"),
    ],
)
def test_corrupt_metadata(tmp_path: Path, change: dict[str, object], check: str) -> None:
    case = LSLCase()
    rep = run(case, tmp_path, device=case.device(**change))
    assert check in failed(rep)


def test_frame_rate_corrupt(tmp_path: Path) -> None:
    case = LSLCase()
    frames = case.frames()
    frames[5].rate = 512.0
    rep = run(case, tmp_path, frames=frames)
    assert "META-RATE" in failed(rep)


def test_channel_count_corrupt(tmp_path: Path) -> None:
    case = LSLCase()
    frames = case.frames()
    frames[5].data = frames[5].data[:, :3]
    rep = run(case, tmp_path, frames=frames)
    assert "META-CHANNELS" in failed(rep)
    assert "LOSS" in failed(rep)  # the malformed frame's samples are not verified


def test_wrong_stream_identity(tmp_path: Path) -> None:
    case = LSLCase()
    x, b = case.write(tmp_path, device=case.device(name="other-stream", sid="other"))
    rep = compare_lsl(x, b, LSLOptions(stream="synth-eeg"))
    assert "IDENTITY" in failed(rep)


def test_stream_selection_among_several(tmp_path: Path) -> None:
    case = LSLCase()
    other = LSLCase(name="aux", sid="aux-sid", seed=99, channels=4)
    x, b = case.write(tmp_path)
    write_xdf(x, [other.xstream(), case.xstream()])  # replace: two streams in the file
    rep = compare_lsl(x, b, LSLOptions())
    assert rep["result"] == "pass"
    assert rep["acquisition"]["xdf_stream"]["name"] == "synth-eeg"
    with pytest.raises(InputError, match="matches 0 XDF streams"):
        compare_lsl(x, b, LSLOptions(stream="nope"))


def test_provenance_must_be_carried(tmp_path: Path) -> None:
    case = LSLCase()
    xs = case.xstream(declaration={"synthetic": "true"})
    rep = run(case, tmp_path, xstream=xs)
    assert "PROVENANCE" in failed(rep)
    rep2 = run(
        case,
        tmp_path,
        xstream=xs,
        device=case.device(synthetic=True),
        prov=lsl_provenance(case.name, case.host, synthetic=True),
    )
    assert status(rep2)["PROVENANCE"] == "pass"
    assert any("synthetic" in r for r in rep2["evidence_scope"]["not_a_hardware_run_because"])


def test_truncated_brainos_file(tmp_path: Path) -> None:
    case = LSLCase()
    x, b = case.write(tmp_path)
    text = b.read_text()
    b.write_text(text[: len(text) - 300])  # crash mid-write
    rep = compare_lsl(x, b, LSLOptions())
    assert "BOS-FILE" in failed(rep)
    assert by_id(rep)["BOS-FILE"]["evidence"]["malformed_lines"] == 1


def test_no_overlap_is_inconclusive(tmp_path: Path) -> None:
    case = LSLCase()
    frames = case.frames()
    for f in frames:
        assert f.t_dev_ns is not None
        f.t_dev_ns += 3600 * 10**9
    rep = run(case, tmp_path, frames=frames)
    assert rep["result"] == "inconclusive"
    assert status(rep)["OVERLAP"] == "inconclusive"


def test_flat_signal_content_alignment_inconclusive(tmp_path: Path) -> None:
    case = LSLCase()
    case.values = np.zeros_like(case.values)
    rep = run(case, tmp_path)
    assert status(rep)["ALIGN-CONTENT"] == "inconclusive"
    assert rep["result"] == "inconclusive"


def test_not_xdf_is_input_error(tmp_path: Path) -> None:
    case = LSLCase()
    _, b = case.write(tmp_path)
    bad = tmp_path / "bad.xdf"
    bad.write_bytes(b"not an xdf file at all")
    with pytest.raises(InputError):
        compare_lsl(bad, b, LSLOptions())
    with pytest.raises(InputError, match="not a BrainOS recording"):
        compare_lsl(tmp_path / "ref.xdf", tmp_path / "ref.xdf", LSLOptions())
