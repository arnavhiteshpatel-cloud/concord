"""Regression (0.3.1): a recording that stopped by itself at its size limit left every console
showing "· Recording" (Stop then answered "not recording"), because no runtime update was sent."""

from __future__ import annotations

import json
from pathlib import Path

from concord.adapters.simulated import OperatorIntentSource, profile_a
from concord.contracts import parse_envelope
from concord.runtime import DeviceRegistry, Recorder, Runtime

from .helpers import valid_event


def test_a_recording_that_stops_at_its_limit_is_announced_to_the_consoles(tmp_path: Path) -> None:
    rec = Recorder(tmp_path, max_bytes=4 * 1024)
    rt = Runtime(DeviceRegistry(OperatorIntentSource(), tmp_path, seed=1), rec)
    sent: list[dict[str, object]] = []
    rt.bus.broadcast_control = lambda msg: sent.append(json.loads(msg))  # type: ignore[method-assign]
    name = rec.start(profile_a.descriptor())
    assert sent and sent[-1]["runtime"]["recording"] == name  # type: ignore[index]
    i = 0
    while rec.active_name is not None:  # write until the 4 KiB limit stops it
        env = parse_envelope(valid_event("telemetry.sample", seq=i, device_id="sim-a"))
        rec.on_event(env, env.model_dump_json())
        i += 1
    assert sent[-1]["type"] == "runtime"
    assert sent[-1]["runtime"]["recording"] is None  # type: ignore[index]


def test_reproduce_instructions_point_to_the_release_wheels() -> None:
    """Regression (0.3.1): REPRODUCE.md told readers to `pip install concordos`, which is not on
    PyPI; it now says to install the release wheels (or use the desktop app)."""
    from concord import __version__
    from concord.runtime.export import ExportOptions, _reproduce_md
    from concord.runtime.sessions import SessionInfo

    info = SessionInfo(
        id="20261109-000000-abcd", name="t", created_at_ns=1, concord_version=__version__
    )
    md = _reproduce_md(info, [], [], [], [], [], ExportOptions())
    assert f'pip install --find-links <folder> "concordos[lab]=={__version__}"' in md
    assert "not on PyPI" in md and "release page" in md
