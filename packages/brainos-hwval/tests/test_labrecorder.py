"""Real LabRecorder round trip: LabRecorderCLI and BrainOS record the same LSL stream.

The reference XDF file is written by the official LabRecorder 1.16.4 (C++, liblsl 1.16.2) and
read by pyxdf; the BrainOS recording is made by BrainOS's unchanged runtime (LSL adapter,
Runtime, Recorder) through ``brainos-hwval capture``. Neither recording is produced by code in
this package. The source is the declared-synthetic test signal (software, not hardware).

Then BrainOS-side defects are injected into copies of the *real* BrainOS recording and must be
detected against the *real* LabRecorder file.
"""

from __future__ import annotations

import copy
import json
import os
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
import refsoft
from helpers import by_id, failed, frames_of, mutate_header, mutate_recording, status

from brainos_hwval import report as R
from brainos_hwval.compare_lsl import LSLOptions, compare_lsl
from brainos_hwval.testsignal import LSLTestSignal

pytestmark = pytest.mark.reference_software
EXAMPLES = os.environ.get("HWVAL_EXAMPLES_DIR")


def _need(exc: Exception) -> None:
    if refsoft.REQUIRE:
        pytest.fail(f"reference software required but unavailable: {exc}")
    pytest.skip(f"reference software unavailable: {exc}")


Session = tuple[Path, Path, Path, str]


def _session(root: Path, tag: str, drop: list[tuple[int, int]] | None = None) -> Session:
    try:
        lr = refsoft.labrecorder()
        pytest.importorskip("pylsl")
        import brainos.runtime  # noqa: F401

        from brainos_hwval import capture
    except (refsoft.Unavailable, ImportError) as exc:
        _need(exc)
        raise
    name = f"hwval-{tag}-{os.getpid()}"
    sig = LSLTestSignal(name, channels=8, rate=1000.0, chunk=20, seed=11, drop=drop).start()
    if sig.error:
        _need(sig.error if isinstance(sig.error, Exception) else RuntimeError(sig.error))
    rec = refsoft.LabRecorderRun(lr, root / "labrecorder.xdf", f'name="{name}"')
    try:
        rec.wait_started()
        time.sleep(0.5)
        bos, side = capture.capture_lsl(
            stream=name,
            source_id=None,
            hostname=None,
            duration_s=10.0,
            out_dir=root,
            name="brainos",
        )
        time.sleep(0.5)  # LabRecorder keeps recording a little after BrainOS stops
    finally:
        log = rec.stop()
        sig.close()
    return root / "labrecorder.xdf", bos, side, log + f"\n[{lr.version}]"


@pytest.fixture(scope="module")
def clean(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Session]:
    yield _session(tmp_path_factory.mktemp("lr-clean"), "clean")


@pytest.fixture(scope="module")
def gapped(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Session]:
    # the source withholds 150 samples at 9 s (inside BrainOS's 10 s recording, which starts
    # once LabRecorder records): a real discontinuity both recorders see
    yield _session(tmp_path_factory.mktemp("lr-gap"), "gap", drop=[(9000, 150)])


def _cmp(xdf: Path, bos: Path, side: Path | None = None) -> dict[str, Any]:
    return compare_lsl(xdf, bos, LSLOptions(sidecar=side))


def test_recording_header_identifies_the_outlet_without_the_sidecar(clean: Session) -> None:
    """BrainOS >= M5 keeps the LSL adapter's source metadata in the recording header, so a
    recording made from the console (no capture sidecar) is matched to its XDF stream by uid."""
    xdf, bos, _side, _log = clean
    with bos.open(encoding="utf-8") as fh:
        header = json.loads(fh.readline())
    signal = next(s for s in header["source_metadata"]["streams"] if s["role"] == "signal")
    rep = _cmp(xdf, bos, None)
    ident = by_id(rep)["IDENTITY"]
    assert ident["status"] == "pass"
    assert ident["evidence"]["selected_by"] == "same LSL stream uid (recording header)"
    assert ident["evidence"]["xdf_stream"]["uid"] == signal["uid"]
    assert "cannot be reconstructed" in header["timing"]
    from brainos_hwval.capture import LIMIT_MARGIN_S

    assert header["limits"]["max_duration_s"] == 10.0 + LIMIT_MARGIN_S


def test_labrecorder_round_trip_passes(clean: Session) -> None:
    xdf, bos, side, log = clean
    assert "Wrote footer" in log  # LabRecorder closed the file normally
    rep = _cmp(xdf, bos, side)
    assert rep["result"] == "pass", rep["result_explanation"]
    st = status(rep)
    assert st["IDENTITY"] == "pass" and "uid" in by_id(rep)["IDENTITY"]["summary"]
    v = by_id(rep)["VALUES"]["evidence"]
    assert v["values_exactly_equal"] == v["values_compared"] > 8 * 8000  # bit-exact, >= 8 s
    ts = by_id(rep)["TS-AGREE"]["evidence"]
    assert ts["max_abs_diff_s"] < 1e-6
    assert rep["summary"]["missing_in_brainos"] == 0
    assert rep["summary"]["duplicated_in_brainos"] == 0
    assert by_id(rep)["CLOCKS"]["evidence"]["labrecorder_clock_offsets"]["usable"] >= 1
    d = by_id(rep)["DELAY"]["evidence"]
    assert 0 < d["latency_median_s"] < 0.5  # absolute latency from the measured clock pair
    assert by_id(rep)["PROVENANCE"]["status"] == "pass"  # declared synthetic, carried through
    assert rep["evidence_scope"]["level"] == "software_acquisition_comparison"
    assert rep["evidence_scope"]["hardware_verified"] is False
    assert any("synthetic" in r for r in rep["evidence_scope"]["not_a_hardware_run_because"])
    if EXAMPLES:
        rep["acquisition"]["reference_software_version"] = log.rsplit("[", 1)[-1].rstrip("]")
        R.write(rep, Path(EXAMPLES), "labrecorder-pass")


def test_source_gap_is_a_source_discontinuity_not_brainos_loss(gapped: Session) -> None:
    xdf, bos, side, _ = gapped
    rep = _cmp(xdf, bos, side)
    st = status(rep)
    assert st["LOSS"] == "pass" and st["VALUES"] == "pass"
    gaps = by_id(rep)["REF-CONTINUITY"]["evidence"]["reference"]
    assert gaps["gaps"] == 1 and gaps["est_missing"] == 150
    # the gap lies inside the samples BrainOS recorded (otherwise this test proves nothing)
    lo, hi = by_id(rep)["OVERLAP"]["evidence"]["reference_row_span"]
    assert lo <= gaps["examples"][0]["after_row"] < hi
    assert st["REF-CONTINUITY"] == "inconclusive"  # advisory: the source has a gap
    # BrainOS's own gap detection flagged the frame after the gap
    assert by_id(rep)["REF-CONTINUITY"]["evidence"]["brainos_frames_flagged_dropped_samples"] >= 1
    assert rep["result"] == "pass", rep["result_explanation"]
    if EXAMPLES:
        R.write(rep, Path(EXAMPLES), "labrecorder-source-gap")


def _drop_frame(envs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    fr = frames_of(envs)
    victim = fr[len(fr) // 2]
    return [e for e in envs if e is not victim]


def _swap_channels(envs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    for e in frames_of(envs):
        s = e["payload"]["samples"]
        s[2], s[5] = s[5], s[2]
    return envs


def _millivolts(envs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    for e in frames_of(envs):
        e["payload"]["samples"] = [[v / 1000 for v in ch] for ch in e["payload"]["samples"]]
    return envs


def _corrupt_value(envs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    e = frames_of(envs)[7]
    e["payload"]["samples"][1][3] += 0.001
    return envs


def _shift_timestamps(envs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    for e in frames_of(envs):
        e["device_timestamp_ns"] += 3_000_000  # three samples at 1 kHz
    return envs


def _duplicate(envs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    fr = frames_of(envs)
    i = envs.index(fr[10])
    return [*envs[: i + 1], copy.deepcopy(fr[10]), *envs[i + 1 :]]


def _delay(envs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    fr = frames_of(envs)
    for e in fr[len(fr) // 2 :]:
        e["timestamp_ns"] += 2_000_000_000  # frames ingested 2 s late
    return envs


@pytest.mark.parametrize(
    ("mutation", "expect"),
    [
        (_drop_frame, {"LOSS", "LOSS-FLAGGED", "SAMPLE-COUNT"}),
        (_swap_channels, {"CHANNEL-ORDER", "VALUES"}),
        (_millivolts, {"SCALE", "VALUES"}),
        (_corrupt_value, {"VALUES"}),
        (_shift_timestamps, {"TS-AGREE", "ALIGN-CONTENT"}),
        (_duplicate, {"DUPLICATES"}),
        (_delay, {"DELAY"}),
    ],
    ids=[
        "dropped-frame",
        "channel-swap",
        "unit-error",
        "corrupt-value",
        "timestamp-shift",
        "duplicate-frame",
        "delayed",
    ],
)
def test_injected_defects_detected_against_real_labrecorder_file(
    clean: Session, tmp_path: Path, mutation: Any, expect: set[str]
) -> None:
    xdf, bos, side, _ = clean
    bad = mutate_recording(bos, tmp_path / "bad.brainos.jsonl", mutation)
    rep = _cmp(xdf, bad, side)
    assert rep["result"] == "fail"
    assert expect <= failed(rep), (expect, failed(rep))


def test_corrupt_metadata_detected_against_real_file(clean: Session, tmp_path: Path) -> None:
    xdf, bos, side, _ = clean

    def relabel(h: dict[str, Any]) -> None:
        params = h["device"]["capabilities"][0]["params"]
        params["channel_labels"] = list(reversed(params["channel_labels"]))
        params["sample_rate_hz"] = 1024.0

    bad = mutate_header(bos, tmp_path / "meta.brainos.jsonl", relabel)
    rep = _cmp(xdf, bad, side)
    assert {"META-CHANNELS", "META-RATE"} <= failed(rep)
