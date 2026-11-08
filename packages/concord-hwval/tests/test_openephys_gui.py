"""Real Open Ephys GUI round trip: the GUI's Record Node and Concord record the same stream.

The official Open Ephys GUI 1.1.0 runs headless (Xvfb + PulseAudio null sink) with the signal
chain File Reader -> ZMQ Interface -> Record Node (Binary). The File Reader plays the sample
recording shipped with the GUI; Concord's unchanged Open Ephys adapter, runtime and recorder
receive the ZMQ Interface's stream (``concord-hwval capture openephys``) while the Record Node
writes the reference. The official open-ephys-python-tools reader cross-checks this package's
Binary parser on the GUI's own output.

The File Reader is file playback, not hardware: these runs are software-level evidence.
"""

from __future__ import annotations

import os
import threading
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import numpy as np
import pytest
import refsoft
from helpers import by_id, failed, frames_of, mutate_recording, status

from concord_hwval import report as R
from concord_hwval.compare_oe import OEOptions, compare_openephys
from concord_hwval.model import Thresholds
from concord_hwval.oe_ref import find_recordings, load_oe_recording

pytestmark = pytest.mark.reference_software
EXAMPLES = os.environ.get("HWVAL_EXAMPLES_DIR")
OPTS = OEOptions(thresholds=Thresholds(min_overlap_s=2.0))  # the GUI's sample file is 5 s long


class GUIs:
    """Starts a fresh GUI for every recording: GUI 1.1.0 aborts when a ZMQ Interface 1.0.0
    processor is deleted through the HTTP API, so a chain is never reconfigured in place."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.n = 0
        self.last: refsoft.OpenEphysGUI | None = None

    def start(self) -> refsoft.OpenEphysGUI:
        self.n += 1
        g = refsoft.OpenEphysGUI(self.root / f"home{self.n}")
        g.home.mkdir(parents=True)
        g.start()
        self.last = g
        return g


@pytest.fixture(scope="module")
def guis(tmp_path_factory: pytest.TempPathFactory) -> Iterator[GUIs]:
    try:
        pytest.importorskip("zmq")
        import concord.runtime  # noqa: F401

        factory = GUIs(tmp_path_factory.mktemp("oe-homes"))
        factory.start().stop()  # download, install and prove the GUI starts here
    except (refsoft.Unavailable, ImportError) as exc:
        if refsoft.REQUIRE:
            pytest.fail(f"reference software required but unavailable: {exc}")
        pytest.skip(f"reference software unavailable: {exc}")
    yield factory


def _record(
    guis: GUIs,
    root: Path,
    *,
    unit: str = "uV",
    seconds: float = 3.0,
    between: list[str] | None = None,
) -> tuple[Path, Path]:
    gui = guis.start()
    try:
        return _record_with(gui, root, unit=unit, seconds=seconds, between=between)
    finally:
        gui.stop()


def _record_with(
    gui: refsoft.OpenEphysGUI, root: Path, *, unit: str, seconds: float, between: list[str] | None
) -> tuple[Path, Path]:
    from concord_hwval import capture

    port = refsoft.free_port()
    gui.build_chain(port, root / "ref", between=between)
    out: dict[str, Any] = {}

    def cap() -> None:
        try:
            out["paths"] = capture.capture_openephys(
                host="127.0.0.1",
                data_port=port,
                unit=unit,
                duration_s=seconds,
                out_dir=root,
                name="concord",
            )
        except Exception as exc:  # surfaced below
            out["error"] = exc

    t = threading.Thread(target=cap)
    t.start()
    time.sleep(0.2)  # Concord waits (open timeout 4 s) for the first complete block
    gui.set_status("RECORD")
    t.join(seconds + 30)
    time.sleep(0.3)
    gui.set_status("IDLE")
    if "error" in out:
        raise out["error"]
    recs = find_recordings(root / "ref")
    assert len(recs) == 1, recs
    return recs[0], out["paths"][0]


@pytest.fixture(scope="module")
def run_uv(guis: GUIs, tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, Path]:
    return _record(guis, tmp_path_factory.mktemp("oe-uv"))


def test_gui_round_trip_passes(run_uv: tuple[Path, Path]) -> None:
    ref, ours = run_uv
    rep = compare_openephys(ref, ours, OPTS)
    assert rep["result"] == "pass", rep["result_explanation"]
    st = status(rep)
    assert st["REF-READER"] == "pass"  # official reader == this parser on real GUI output
    assert st["META-CHAIN"] == "pass"
    assert rep["summary"]["gui_version"] == "1.1.0"
    assert rep["summary"]["missing_in_concord"] == 0
    assert rep["summary"]["samples_compared"] > 2 * 40_000
    v = by_id(rep)["VALUES"]["evidence"]
    assert v["values_out_of_tolerance"] == 0
    assert v["max_abs_diff"] <= 0.5 * 0.05  # within half a quantisation step (bit_volts 0.05)
    assert st["TS-AGREE"] == "pass"
    assert any("File Reader" in r for r in rep["evidence_scope"]["not_a_hardware_run_because"])
    if EXAMPLES:
        R.write(rep, Path(EXAMPLES), "openephys-gui-pass")


def test_gui_unit_not_declared_is_arbitrary(guis: GUIs, tmp_path: Path) -> None:
    ref, ours = _record(guis, tmp_path, unit="unknown")
    rep = compare_openephys(ref, ours, OPTS)
    assert rep["result"] == "pass", rep["result_explanation"]
    assert "arbitrary" in by_id(rep)["META-UNITS"]["summary"]


def test_gui_processor_between_zmq_and_record_node(guis: GUIs, tmp_path: Path) -> None:
    """A Bandpass Filter after the ZMQ Interface: the file legitimately differs."""
    ref, ours = _record(guis, tmp_path, between=["Bandpass Filter"])
    rep = compare_openephys(ref, ours, OPTS)
    assert status(rep)["META-CHAIN"] == "inconclusive"
    assert "Bandpass Filter" in by_id(rep)["META-CHAIN"]["summary"]
    assert status(rep)["VALUES"] == "inconclusive"
    failed = {k: v for k, v in status(rep).items() if v == "fail"}
    assert rep["result"] == "inconclusive", (failed, rep["result_explanation"])
    assert status(rep)["LOSS"] == "pass"  # sample accounting is still valid
    if EXAMPLES:
        R.write(rep, Path(EXAMPLES), "openephys-gui-filter-between")


def test_gui_file_reader_loop_reset(guis: GUIs, tmp_path: Path) -> None:
    """Recording past the 5 s sample file: the File Reader restarts its sample numbers.

    The toolkit attributes the reset to the reference (advisory REF-CONTINUITY) and checks
    that Concord followed it without reordering or loss. (Before the Milestone 5 release the
    adapter treated the reset as an acquisition restart, reconnected and lost ~0.72 s; this
    test reported that FAIL and now guards the fix.)
    """
    ref, ours = _record(guis, tmp_path, seconds=7.0)
    rep = compare_openephys(ref, ours, OPTS)
    st = status(rep)
    assert by_id(rep)["REF-CONTINUITY"]["evidence"]["regressions"] >= 1
    assert st["ORDER"] == "pass"  # Concord followed the source's reset; not a reordering
    assert st["VALUES"] == "pass"
    assert st["DELAY"] == "pass"
    loss = by_id(rep)["LOSS"]["evidence"]
    # Regression (fixed in the Milestone 5 release): Concord used to reconnect at the reset and
    # lose ~0.72 s (28,793 samples at 40 kHz). It now follows the source's new sample base.
    assert loss["missing_samples"] == 0 and st["LOSS"] == "pass", loss
    assert st["SAMPLE-COUNT"] == "pass" and rep["result"] == "pass"
    if EXAMPLES:
        R.write(rep, Path(EXAMPLES), "openephys-gui-file-reader-loop")


def _drop_block(envs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    victim = frames_of(envs)[20]
    return [e for e in envs if e is not victim]


def _scale(envs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    for e in frames_of(envs):
        e["payload"]["samples"] = [[v * 1000 for v in ch] for ch in e["payload"]["samples"]]
    return envs


def _swap(envs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    for e in frames_of(envs):
        s = e["payload"]["samples"]
        s[0], s[9] = s[9], s[0]
    return envs


def _index_shift(envs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    for e in frames_of(envs):
        e["payload"]["first_sample_index"] += 64
        e["device_timestamp_ns"] = round(e["payload"]["first_sample_index"] * 1e9 / 40000)
    return envs


@pytest.mark.parametrize(
    ("mutation", "expect"),
    [
        (_drop_block, {"LOSS", "LOSS-FLAGGED"}),
        (_scale, {"SCALE"}),
        (_swap, {"CHANNEL-ORDER"}),
        (_index_shift, {"ALIGN-CONTENT", "VALUES"}),
    ],
    ids=["packet-loss", "unit-error", "channel-swap", "sample-number-shift"],
)
def test_injected_defects_detected_against_real_gui_recording(
    run_uv: tuple[Path, Path], tmp_path: Path, mutation: Any, expect: set[str]
) -> None:
    ref, ours = run_uv
    bad = mutate_recording(ours, tmp_path / "bad.concord.jsonl", mutation)
    rep = compare_openephys(ref, bad, OPTS)
    assert expect <= failed(rep), (expect, failed(rep))


def test_legacy_reader_matches_gui_file_reader(guis: GUIs, run_uv: tuple[Path, Path]) -> None:
    """The GUI ships its sample data in the old (0.4.5) Binary layout. The GUI's own File
    Reader parsed it and the Record Node re-recorded it in the 1.1 layout: this package's
    legacy parser must give the same int16 samples as the GUI's re-recording."""
    assert guis.last is not None
    legacy = load_oe_recording(guis.last.bundled_sample())
    assert legacy.gui_version == "0.4.5" and legacy.version < 0.6
    old = legacy.continuous[0]
    new = load_oe_recording(run_uv[0]).continuous[0]
    assert [c.name for c in old.channels] == [c.name for c in new.channels]
    n = min(new.n, old.n, 100_000)
    # the File Reader starts playback at the file's first sample; the Record Node numbers
    # samples from 0 at acquisition start
    assert int(new.sample_numbers[0]) == 0
    assert np.array_equal(np.asarray(old.samples[:n]), np.asarray(new.samples[:n]))
