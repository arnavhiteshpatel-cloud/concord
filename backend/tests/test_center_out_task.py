"""Center-out calibration task (backend/examples/center_out_task.py) over LSL."""

from __future__ import annotations

import importlib.util
import os
import sys
import threading
from pathlib import Path
from types import ModuleType
from typing import Any

import numpy as np
import pytest

from .helpers import wait_for

TASK = Path(__file__).resolve().parents[1] / "examples" / "center_out_task.py"


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("center_out_task", TASK)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules["center_out_task"] = mod
    spec.loader.exec_module(mod)
    return mod


def test_cue_schedule_is_consistent() -> None:
    m = _load()
    s = m.CueSchedule(16, seed=1)
    assert sorted(s.targets[:8]) == list(range(8)) and sorted(s.targets[8:]) == list(range(8))
    dt = 1 / m.RATE_HZ
    x = y = 0.0
    for i in range(int(s.duration_s / dt)):
        phase, _, _, px, py, vx, vy = s.at(i * dt)
        assert abs(px - x) < 0.03 and abs(py - y) < 0.03, (i, phase)  # velocity integrates
        x, y = x + vx * dt, y + vy * dt
        if phase == "hold":
            assert abs(np.hypot(px, py) - m.RADIUS) < 1e-9


async def test_cues_label_a_neural_stream_and_unrelated_signal_is_not_decodable(
    tmp_path: Path, publishers: list[Any]
) -> None:
    """Task cues attach to an ephys stream on one clock. The synthetic ephys is NOT coupled
    to these cues, so calibration must report no meaningful decoding (no fabricated skill)."""
    pytest.importorskip("pylsl")
    pytest.importorskip("scipy")
    from concord.adapters.simulated import OperatorIntentSource
    from concord.decoding.calibrate import calibrate
    from concord.runtime import DeviceRegistry, Recorder, Runtime
    from concord.runtime.pipeline import PipelineStartRequest
    from concord.testing.lsl_publishers import SyntheticEphysPublisher

    m = _load()
    sid = f"cot-{os.getpid()}"
    ephys = SyntheticEphysPublisher(channels=8, source_id=f"{sid}-ephys", latent=False)
    ephys.start()
    publishers.append(ephys)
    task = m.CueTask(m.CueSchedule(3, seed=2), source_id=sid)
    reg = DeviceRegistry(OperatorIntentSource(), tmp_path / "rec", models_dir=tmp_path / "m")
    reg.live.discover_lsl(1.5)
    reg.live.configure_lsl(f"{sid}-ephys", f"{sid}-behavior", f"{sid}-markers")
    rt = Runtime(reg, Recorder(tmp_path / "rec"))
    await rt.connect(f"lsl:{sid}-ephys")
    rt.start_pipeline(PipelineStartRequest(processing={"preset": "spikeband_threshold"}))
    await wait_for(lambda: rt.pipeline.status().warmup_remaining_s == 0, timeout=10)
    name = rt.start_recording("cues", exclude_raw=True)  # calibration needs no raw frames
    th = threading.Thread(target=task.run, daemon=True)
    th.start()
    await wait_for(task.stop.is_set, timeout=30)
    th.join(2)
    await wait_for(lambda: rt.diagnostics.totals["behavior.sample"] >= task.samples, timeout=5)
    rt.stop_recording()
    await rt.shutdown()
    assert rt.diagnostics.timestamp_regressions == 0

    path = tmp_path / "rec" / f"{name}.concord.jsonl"
    import json

    evs = [json.loads(line) for line in path.read_text().splitlines()[1:]]
    assert not any(e["event_type"] == "recording.frame" for e in evs)
    assert "Raw signal frames excluded" in json.loads(path.read_text().splitlines()[0])["note"]
    marks = [e["payload"]["label"] for e in evs if e["event_type"] == "recording.annotation"]
    assert marks == task.markers
    model, report = calibrate([path], feature_source="concord.pipeline", gap_bins=5)
    assert model.dims == ["cue_vx", "cue_vy"] and report["labelled_bins"] >= 450
    assert report["r2"] < 0.2  # unrelated synthetic signal: nothing to decode
