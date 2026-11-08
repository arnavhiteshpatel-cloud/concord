"""The example decoder through the real BrainOS decoder host, plus its rule on known inputs."""

from __future__ import annotations

import subprocess
import sys

import numpy as np
from brainos_decoder_sdk.manifest import validate_manifest

from brainos_example_decoder.decoder import LateralizationDecoder


def test_manifest_is_valid_and_honest() -> None:
    m = LateralizationDecoder.manifest
    assert [p for p in validate_manifest(m) if p.severity == "error"] == []
    assert not m.compatibility.participant_specific and not m.calibration.required
    assert "NOT trained" in m.description
    assert m.inputs[0].channel_labels == ("C3", "C4") and m.inputs[0].band_hz == (8.0, 13.0)


def test_rule_follows_contralateral_desynchronization() -> None:
    d = LateralizationDecoder()
    d.load()
    for _ in range(50):  # baseline at equal power
        d.step(np.array([1.0, 1.0]), 0.0)
    for _ in range(20):  # mu power drops over C4 -> left-hand imagery
        out = d.step(np.array([1.0, 0.4]), 0.0).values
    assert int(np.argmax(out)) == 1 and abs(out.sum() - 1) < 1e-12
    d.reset()
    for _ in range(50):
        d.step(np.array([1.0, 1.0]), 0.0)
    for _ in range(20):  # C3 drops -> right-hand imagery
        out = d.step(np.array([0.4, 1.0]), 0.0).values
    assert int(np.argmax(out)) == 2


def test_passes_the_brainos_decoder_host_check() -> None:
    r = subprocess.run(
        [sys.executable, "-m", "brainos_decoder_sdk.host", "example-mi-lateralization", "--check"],
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert r.returncode == 0, r.stdout + r.stderr
    assert "OK: manifest, load and every output passed validation" in r.stdout
