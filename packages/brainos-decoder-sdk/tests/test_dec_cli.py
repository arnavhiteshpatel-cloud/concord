"""``brainos-decoder new`` scaffolds a plugin that passes ``check`` unchanged."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from brainos_decoder_sdk.cli import main


def test_new_scaffold_runs_through_the_host(tmp_path: Path) -> None:
    root = tmp_path / "pkg"
    assert main(["new", "lab-gru", "--dir", str(root)]) == 0
    assert (root / "pyproject.toml").read_text().count('[project.entry-points."brainos.decoders"]')
    assert main(["new", "lab-gru", "--dir", str(root)]) == 1  # not empty: refused
    assert main(["new", "Bad_Name", "--dir", str(tmp_path / "x")]) == 2
    env = {**os.environ, "PYTHONPATH": str(root / "src")}
    r = subprocess.run(
        [
            sys.executable,
            "-m",
            "brainos_decoder_sdk.cli",
            "check",
            "brainos_lab_gru.decoder:LabGruDecoder",
            "--steps",
            "30",
        ],
        capture_output=True,
        text=True,
        timeout=120,
        env=env,
    )
    assert r.returncode == 0, r.stdout + r.stderr
    assert "OK: manifest, load and every output passed validation" in r.stdout
    # the template is honest about what it is not
    assert "compatibility.source_unknown" in r.stdout
    assert "PLACEHOLDER" in (root / "src" / "brainos_lab_gru" / "decoder.py").read_text()
