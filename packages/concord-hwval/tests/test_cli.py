"""The command-line interface: exit codes, reports on disk, input validation, schema."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import jsonschema
import numpy as np
import pytest
from synth import BFrame, LSLCase, OECase

from concord_hwval.cli import main
from concord_hwval.model import Status, Thresholds, overall
from concord_hwval.report import SCHEMA_PATH
from concord_hwval.scope import equipment_template

SCHEMA = json.loads(SCHEMA_PATH.read_text())


def _report(out: Path, stem: str) -> dict[str, Any]:
    rep: dict[str, Any] = json.loads((out / f"{stem}.hwval.json").read_text())
    jsonschema.validate(rep, SCHEMA)
    md = (out / f"{stem}.hwval.md").read_text()
    assert md.startswith("# Concord acquisition verification")
    assert f"**Result: {rep['result'].upper()}**" in md
    assert "Hardware verified: **no**" in md
    for c in rep["checks"]:
        assert f"`{c['id']}`" in md
    return rep


def test_lsl_pass_exit_0(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    x, b = LSLCase().write(tmp_path)
    out = tmp_path / "rep"
    code = main(["lsl", "--reference", str(x), "--concord", str(b), "--out", str(out)])
    assert code == 0
    assert "Result: PASS" in capsys.readouterr().out
    rep = _report(out, "run")
    assert [i["role"] for i in rep["inputs"]] == ["reference_xdf", "concord_recording"]
    assert rep["command"][1] == "lsl"


def test_lsl_fail_exit_1(tmp_path: Path) -> None:
    case = LSLCase()
    frames = case.frames()
    del frames[3]
    x, b = case.write(tmp_path, frames=frames)
    code = main(
        [
            "lsl",
            "--reference",
            str(x),
            "--concord",
            str(b),
            "--out",
            str(tmp_path / "r"),
            "--name",
            "lossy",
        ]
    )
    assert code == 1
    rep = _report(tmp_path / "r", "lossy")
    assert "LOSS" in rep["required_checks_by_status"]["fail"]


def test_inconclusive_exit_3(tmp_path: Path) -> None:
    case = LSLCase(seconds=4)  # overlap ~3 s < default 5 s
    x, b = case.write(tmp_path)
    args = ["lsl", "--reference", str(x), "--concord", str(b), "--out", str(tmp_path / "r")]
    assert main(args) == 3
    assert main([*args, "--min-overlap", "2"]) == 0


def test_openephys_cli(tmp_path: Path) -> None:
    _ref, b = OECase(seconds=7).write(tmp_path)
    code = main(
        [
            "openephys",
            "--reference",
            str(tmp_path / "ref"),
            "--concord",
            str(b),
            "--out",
            str(tmp_path / "r"),
        ]
    )
    assert code == 0
    rep = _report(tmp_path / "r", "run")
    assert rep["inputs"][0]["kind"] == "directory"


def test_input_errors_exit_2(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    x, b = LSLCase().write(tmp_path)
    assert main(["lsl", "--reference", str(tmp_path / "missing.xdf"), "--concord", str(b)]) == 2
    assert "XDF file not found" in capsys.readouterr().err
    assert main(["lsl", "--reference", str(x), "--concord", str(x)]) == 2
    assert "not a Concord recording" in capsys.readouterr().err
    assert main(["openephys", "--reference", str(tmp_path), "--concord", str(b)]) == 2
    assert "no structure.oebin" in capsys.readouterr().err
    eq = tmp_path / "eq.json"
    eq.write_text("{}")
    assert main(["lsl", "--reference", str(x), "--concord", str(b), "--equipment", str(eq)]) == 2
    assert "equipment manifest" in capsys.readouterr().err


def test_usage_errors(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as e:
        main(["lsl", "--concord", "x"])  # --reference missing
    assert e.value.code == 2
    with pytest.raises(SystemExit):
        main(["lsl", "--reference", "a", "--concord", "b", "--max-loss-fraction", "2"])
    assert "fraction below 1" in capsys.readouterr().err


def test_inspect(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    x, b = LSLCase().write(tmp_path)
    assert main(["inspect", str(x)]) == 0
    info = json.loads(capsys.readouterr().out)
    assert info["file_type"] == "XDF" and info["streams"][0]["name"] == "synth-eeg"
    assert main(["inspect", str(b)]) == 0
    info = json.loads(capsys.readouterr().out)
    assert info["file_type"] == "Concord recording" and info["channel_labels"] == [
        "C1",
        "C2",
        "C3",
        "C4",
    ]
    OECase(seconds=1).write(tmp_path / "oe")
    assert main(["inspect", str(tmp_path / "oe" / "ref")]) == 0
    info = json.loads(capsys.readouterr().out)
    assert info["gui_version"] == "1.1.0"


def test_equipment_template_and_hardware_candidate_logic(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["equipment-template"]) == 0
    tpl = json.loads(capsys.readouterr().out)
    assert tpl == equipment_template()
    # a template as printed is incomplete: never a hardware run
    eq = tmp_path / "eq.json"
    eq.write_text(json.dumps(tpl))
    case = LSLCase(rate=50.0, seconds=260, frame=10, concord_start=20, concord_stop_before_end=20)
    x, b = case.write(tmp_path)
    out = tmp_path / "r"
    assert (
        main(
            [
                "lsl",
                "--reference",
                str(x),
                "--concord",
                str(b),
                "--equipment",
                str(eq),
                "--out",
                str(out),
            ]
        )
        == 0
    )
    rep = _report(out, "run")
    assert rep["evidence_scope"]["level"] == "software_acquisition_comparison"
    assert any("incomplete" in r for r in rep["evidence_scope"]["not_a_hardware_run_because"])
    # a complete manifest declaring hardware, a non-synthetic stream and >= 240 s overlap:
    # the run is a *candidate* — and still not hardware_verified
    full = json.loads(json.dumps(tpl))
    full.update(laboratory="Test lab", operator="A. Tester", date="2026-11-08")
    full["signal_source"] = {"kind": "acquisition_hardware", "description": "test fixture"}
    full["acquisition_hardware"].update(
        manufacturer="m", model="x", serial_number="1", firmware="1"
    )
    full["acquisition_software"].update(name="s", version="1")
    full["reference_recorder"].update(name="LabRecorder", version="1.16.4")
    full["concord"].update(version="0.3.0")
    full["hosts"] = [{"name": "h", "os": "linux", "cpu": "x", "clock_sync": "NTP"}]
    eq.write_text(json.dumps(full))
    assert (
        main(
            [
                "lsl",
                "--reference",
                str(x),
                "--concord",
                str(b),
                "--equipment",
                str(eq),
                "--out",
                str(out),
            ]
        )
        == 0
    )
    rep = _report(out, "run")
    assert rep["evidence_scope"]["level"] == "hardware_run_candidate"
    assert rep["evidence_scope"]["hardware_verified"] is False
    # a declared software simulator is never a hardware run, whatever else holds
    full["signal_source"]["kind"] = "software_simulator"
    eq.write_text(json.dumps(full))
    main(
        [
            "lsl",
            "--reference",
            str(x),
            "--concord",
            str(b),
            "--equipment",
            str(eq),
            "--out",
            str(out),
        ]
    )
    assert _report(out, "run")["evidence_scope"]["level"] == "software_acquisition_comparison"


def test_failed_run_supports_nothing(tmp_path: Path) -> None:
    case = LSLCase()
    frames = case.frames()
    frames[2] = BFrame(frames[2].index, frames[2].data * 2, frames[2].t_dev_ns, frames[2].t_wall_ns)
    x, b = case.write(tmp_path, frames=frames)
    main(["lsl", "--reference", str(x), "--concord", str(b), "--out", str(tmp_path / "r")])
    assert _report(tmp_path / "r", "run")["evidence_scope"]["level"] == "none"


def test_verdict_rules() -> None:
    from concord_hwval.model import Category, Check

    def c(st: Status, req: bool = True) -> Check:
        return Check("X", "x", Category.INTEGRITY, req, st, "", "")

    assert overall([c(Status.PASS), c(Status.FAIL, req=False)]) is Status.PASS
    assert overall([c(Status.PASS), c(Status.NOT_TESTED)]) is Status.INCONCLUSIVE
    assert overall([c(Status.INCONCLUSIVE), c(Status.FAIL)]) is Status.FAIL
    assert overall([c(Status.PASS, req=False)]) is Status.INCONCLUSIVE  # nothing required ran
    assert Thresholds().to_json()["max_loss_fraction"] == 0.0


def test_module_entry_point(tmp_path: Path) -> None:
    out = subprocess.run(
        [sys.executable, "-m", "concord_hwval", "--version"],
        capture_output=True,
        text=True,
        check=True,
    )
    assert out.stdout.startswith("concord-hwval ")


def test_report_has_no_nan(tmp_path: Path) -> None:
    case = LSLCase()
    case.values = case.values.astype(np.float64)
    x, b = case.write(tmp_path)
    main(["lsl", "--reference", str(x), "--concord", str(b), "--out", str(tmp_path / "r")])
    text = (tmp_path / "r" / "run.hwval.json").read_text()
    assert "NaN" not in text and "Infinity" not in text
