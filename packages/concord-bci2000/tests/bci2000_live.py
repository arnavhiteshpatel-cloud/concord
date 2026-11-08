"""Drive a locally built, genuine BCI2000 (SignalGenerator + DummySignalProcessing +
DummyApplication, whose application framework links ConnectorFilters.cpp) from an Operator
script, so that BCI2000's own ConnectorOutput filter sends App Connector datagrams.

Used by the opt-in live test (``BCI2000_PROG_DIR`` = directory with ``BCI2000Shell``,
``Operator``, ``SignalGenerator``, ``DummySignalProcessing``, ``DummyApplication``) and by
``scripts/capture_app_connector.py`` (which recorded ``fixtures/bci2000_connector_output.json``).
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

SOURCE_CH = 2
SAMPLE_BLOCK_SIZE = 8
SAMPLING_RATE = 256


def batch_script(port: int, data_dir: Path, run_seconds: float = 2.0) -> str:
    step = max(0.25, run_seconds / 4)
    return "\n".join(
        [
            "Change directory $BCI2000LAUNCHDIR",
            "Reset system",
            "Startup system localhost",
            "Start executable SignalGenerator --local",
            "Start executable DummySignalProcessing --local",
            "Start executable DummyApplication --local",
            "Wait for Connected",
            # DummyApplication defines no task states; add the standard FeedbackTask ones
            # (FeedbackTask.cpp: TargetCode 8, ResultCode 8, Feedback 1) to exercise them.
            "Add state TargetCode 8 0",
            "Add state ResultCode 8 0",
            "Add state Feedback 1 0",
            f"Set parameter SourceCh {SOURCE_CH}",
            f"Set parameter SampleBlockSize {SAMPLE_BLOCK_SIZE}",
            f"Set parameter SamplingRate {SAMPLING_RATE}Hz",
            f"Set parameter ConnectorOutputAddress localhost:{port}",
            f"Set parameter DataDirectory {data_dir}",
            "Set config",
            "Wait for Resting 20",
            "Start",
            "Wait for Running 10",
            f"Sleep {step}",
            "Set state TargetCode 2",
            f"Sleep {step}",
            "Set state Feedback 1",
            f"Sleep {step}",
            "Set states TargetCode 0 ResultCode 2 Feedback 0",
            f"Sleep {step}",
            "Stop",
            "Wait for Resting 10",
            "Quit",
            "",
        ]
    )


def run_bci2000(
    prog_dir: Path, port: int, work: Path, run_seconds: float = 2.0
) -> subprocess.Popen[bytes]:
    """Start BCI2000Shell with the script; returns the running process."""
    work.mkdir(parents=True, exist_ok=True)
    (work / "data").mkdir(exist_ok=True)
    bat = work / "concord_app_connector.bat"
    bat.write_text(batch_script(port, work / "data", run_seconds))
    env = dict(os.environ, QT_QPA_PLATFORM="offscreen")
    return subprocess.Popen(
        [str(prog_dir / "BCI2000Shell"), str(bat)],
        cwd=str(prog_dir),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
