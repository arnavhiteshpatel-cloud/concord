"""``concord-decoder new`` scaffolds a plugin that passes ``check`` unchanged."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from concord_decoder_sdk.cli import main


def test_new_scaffold_runs_through_the_host(tmp_path: Path) -> None:
    root = tmp_path / "pkg"
    assert main(["new", "lab-gru", "--dir", str(root)]) == 0
    assert (root / "pyproject.toml").read_text().count('[project.entry-points."concord.decoders"]')
    assert main(["new", "lab-gru", "--dir", str(root)]) == 1  # not empty: refused
    assert main(["new", "Bad_Name", "--dir", str(tmp_path / "x")]) == 2
    env = {**os.environ, "PYTHONPATH": str(root / "src")}
    r = subprocess.run(
        [
            sys.executable,
            "-m",
            "concord_decoder_sdk.cli",
            "check",
            "concord_lab_gru.decoder:LabGruDecoder",
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
    assert "PLACEHOLDER" in (root / "src" / "concord_lab_gru" / "decoder.py").read_text()
