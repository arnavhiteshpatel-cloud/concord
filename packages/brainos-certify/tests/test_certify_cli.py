"""The ``brainos-certify`` command: exit codes, files written, and running without BrainOS."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from certify_helpers import PLUGINS_DIR, attestation_doc, keypair, ref, sign

from brainos_certify.cli import main
from brainos_certify.report import validate_report

FAST = ["--duration", "1", "--reopen-seconds", "0.5", "--read-grace", "1", "--quiet"]


def run_cli(tmp: Path, *args: str) -> int:
    return main([*args, "--path", str(PLUGINS_DIR), "--out", str(tmp), *FAST])


def test_good_plugin_exits_zero_and_writes_both_reports(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code = run_cli(tmp_path, ref(), "--no-runtime", "--name", "good")
    assert code == 0
    doc = json.loads((tmp_path / "good.certify.json").read_text())
    assert validate_report(doc) == []
    assert doc["summary"]["exit_code"] == 0
    assert all(
        c["status"] == "not_run" and not c["applicable"]
        for c in doc["checks"]
        if c["id"].startswith("runtime.")
    )
    md = (tmp_path / "good.certify.md").read_text()
    assert "not hardware certification" in md.splitlines()[2]
    assert "level: adapter_implementation" in capsys.readouterr().out


def test_failing_plugin_exits_one(tmp_path: Path) -> None:
    code = run_cli(tmp_path, ref(), "--no-runtime", "--option", "defect=wrong_rate")
    assert code == 1
    doc = json.loads(next(tmp_path.glob("*.certify.json")).read_text())
    assert doc["summary"]["level"] is None
    assert any(b.startswith("timing.rate") for b in doc["summary"]["blocking"])


@pytest.mark.parametrize(
    "args",
    [
        [],  # no plugin
        [ref(), "--duration", "0"],
        [ref(), "--rate-tolerance", "2"],
        [ref(), "--option", "no-equals-sign"],
    ],
)
def test_usage_errors_exit_two(args: list[str]) -> None:
    with pytest.raises(SystemExit) as e:
        main(args)
    assert e.value.code == 2


def test_print_schema(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["--print-schema"]) == 0
    schema = json.loads(capsys.readouterr().out)
    assert schema["properties"]["report_version"] == {"const": "1.0"}


def test_runs_without_brainos(tmp_path: Path) -> None:
    """A directory whose ``brainos`` package fails to import shadows the installed BrainOS:
    the certifier still runs every host-level check and grants the level; the runtime phase
    is reported as not run (not passed)."""
    shadow = tmp_path / "shadow"
    (shadow / "brainos").mkdir(parents=True)
    (shadow / "brainos" / "__init__.py").write_text("raise ImportError('BrainOS hidden')\n")
    env = {**os.environ, "PYTHONPATH": os.pathsep.join([str(shadow), str(PLUGINS_DIR)])}
    out = tmp_path / "out"
    p = subprocess.run(
        [sys.executable, "-m", "brainos_certify.cli", ref(), "--out", str(out), "--name", "x",
         *FAST],
        env=env, capture_output=True, text=True, timeout=120, check=False,
    )  # fmt: skip
    assert p.returncode == 0, p.stdout + p.stderr
    doc = json.loads((out / "x.certify.json").read_text())
    rt = [c for c in doc["checks"] if c["id"].startswith("runtime.")]
    assert rt and all(c["status"] == "not_run" for c in rt)
    assert "BrainOS hidden" in rt[0]["reason"]
    notes = doc["levels"]["levels"]["adapter_implementation"]["notes"]
    assert notes and "runtime phase not run" in notes[0]


def test_protocol_reference_needs_a_declared_ecosystem(tmp_path: Path) -> None:
    code = run_cli(
        tmp_path, ref(), "--no-runtime", "--name", "p", "--protocol-reference", "Some Software 1.0"
    )
    assert code == 0  # level 1 still achieved: the exit code depends on it alone
    doc = json.loads((tmp_path / "p.certify.json").read_text())
    pt = doc["levels"]["levels"]["protocol_tested"]
    assert not pt["achieved"] and any("ecosystem_declared" in m for m in pt["missing"])
    assert doc["summary"]["level"] == "adapter_implementation"


@pytest.mark.skipif(shutil.which("openssl") is None, reason="openssl not installed")
def test_signed_attestation_end_to_end(tmp_path: Path) -> None:
    key, pub = keypair(tmp_path)
    att = tmp_path / "attestation.json"
    doc = attestation_doc(plugin={"name": "certify-test-plugins", "version": "0.0.1"})
    att.write_text(json.dumps(doc))
    sign(att, key)  # -> attestation.json.sig, the CLI's default signature path
    code = run_cli(
        tmp_path, ref(), "--no-runtime", "--name", "a",
        "--attestation", str(att), "--attestation-public-key", str(pub),
    )  # fmt: skip
    assert code == 0
    rep = json.loads((tmp_path / "a.certify.json").read_text())
    assert rep["attestation"]["accepted"] is True
    assert rep["summary"]["level"] == "hardware_tested"
    assert "not verified by this toolkit" in rep["summary"]["level_statement"]
    assert rep["levels"]["levels"]["human_participant_validated"]["achieved"] is False
    md = (tmp_path / "a.certify.md").read_text()
    assert "operator-attested" in md and "hardware claims NOT verified" in md
