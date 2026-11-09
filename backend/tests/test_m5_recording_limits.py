"""Milestone 5: configurable recording limits, a free-space guard, and what a recording header
keeps about its source (the adapter's metadata snapshot, a timing statement, the limits)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from concord.adapters.replay import ConcordRecordingSource
from concord.adapters.simulated import OperatorIntentSource, profile_a
from concord.config import ConfigError, parse_config
from concord.contracts import parse_envelope
from concord.runtime import DeviceRegistry, Recorder, Runtime
from concord.runtime import recorder as recorder_mod
from concord.runtime.recorder import RecorderError
from concord.server.app import create_app
from concord.server.settings import Settings

from .helpers import valid_event

MIB = 1024 * 1024


def _write(rec: Recorder, n: int, start: int = 0) -> None:
    for i in range(start, start + n):
        env = parse_envelope(valid_event("telemetry.sample", seq=i, device_id="sim-a"))
        rec.on_event(env, env.model_dump_json())


def _strict_header(path: Path) -> dict[str, Any]:
    def no_constants(name: str) -> None:
        raise AssertionError(f"non-JSON constant {name} in the header")

    with path.open(encoding="utf-8") as fh:
        out: dict[str, Any] = json.loads(fh.readline(), parse_constant=no_constants)
    return out


@pytest.mark.parametrize(
    "kwargs",
    [
        {"max_duration_s": 0},
        {"max_duration_s": -1.0},
        {"max_duration_s": 24 * 3600 + 1},
        {"max_duration_no_raw_s": 0},
        {"max_bytes": 0},
        {"max_bytes": 100 * 1024**3 + 1},
        {"min_free_bytes": -1},
    ],
)
def test_recorder_limits_are_bounded(tmp_path: Path, kwargs: dict[str, Any]) -> None:
    with pytest.raises(ValueError, match="must be"):
        Recorder(tmp_path, **kwargs)


def test_a_configured_duration_beyond_300_s_is_honoured_and_stops_cleanly(tmp_path: Path) -> None:
    rec = Recorder(tmp_path, max_duration_s=1800.0)
    rec.start(profile_a.descriptor(), "long")
    _write(rec, 3)
    rec._started -= 400.0  # 400 s in: past the old fixed 300 s cap, still recording
    _write(rec, 3, start=3)
    assert rec.active_name == "long"
    rec._started -= 1500.0  # 1900 s in: past the configured limit
    _write(rec, 1, start=6)
    assert rec.active_name is None and rec.stop_reason == "max duration reached"
    assert rec.list()[0].complete
    path = tmp_path / "long.concord.jsonl"
    assert _strict_header(path)["limits"] == {"max_duration_s": 1800.0, "max_bytes": 200 * MIB}
    assert sum(1 for _ in ConcordRecordingSource(path).records()) == 7  # nothing half-written


def test_size_limit_stops_after_a_whole_event(tmp_path: Path) -> None:
    rec = Recorder(tmp_path, max_bytes=8 * 1024)
    rec.start(profile_a.descriptor(), "small")
    _write(rec, 200)
    assert rec.active_name is None and rec.stop_reason == "max size reached"
    path = tmp_path / "small.concord.jsonl"
    lines = path.read_bytes().split(b"\n")
    assert lines[-1] == b""  # ends on a complete line
    n = len(lines) - 2
    assert 0 < n < 200 and rec.list()[0].complete
    assert sum(1 for _ in ConcordRecordingSource(path).records()) == n


def test_low_disk_space_refuses_to_start_and_stops_a_running_recording_cleanly(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    free = {"bytes": 10 * MIB}
    monkeypatch.setattr(recorder_mod, "_free_bytes", lambda _d: free["bytes"])
    rec = Recorder(tmp_path, min_free_bytes=64 * MIB)
    with pytest.raises(RecorderError, match="10 MiB free"):
        rec.start(profile_a.descriptor(), "nospace")
    assert not (tmp_path / "nospace.concord.jsonl").exists()

    free["bytes"] = 10 * 1024 * MIB
    rec.start(profile_a.descriptor(), "fills")
    _write(rec, 5)
    assert rec.active_name == "fills"
    free["bytes"] = 32 * MIB
    rec._next_space_check = 0  # the guard runs every 32 MiB written; force it
    _write(rec, 1, start=5)
    assert rec.active_name is None and rec.stop_reason == "disk space low (32 MiB free)"
    assert rec.list()[0].complete
    path = tmp_path / "fills.concord.jsonl"
    assert sum(1 for _ in ConcordRecordingSource(path).records()) == 6


def test_header_keeps_a_plain_json_source_metadata_snapshot(tmp_path: Path) -> None:
    meta: dict[str, Any] = {
        "protocol": "lsl",
        "streams": [{"uid": "u-1", "source_id": "s-1", "time_correction_s": float("nan")}],
        "nested": {"values": (1, 2.5, float("inf")), "path": Path("/x")},
        3: "non-string key",
    }
    rec = Recorder(tmp_path)
    rec.start(profile_a.descriptor(), "meta", source_metadata=meta)
    meta["protocol"] = "changed after start"  # the header is a snapshot
    rec.stop()
    path = tmp_path / "meta.concord.jsonl"
    header = _strict_header(path)  # strict JSON: NaN / Infinity became null
    assert header["source_metadata"] == {
        "protocol": "lsl",
        "streams": [{"uid": "u-1", "source_id": "s-1", "time_correction_s": None}],
        "nested": {"values": [1, 2.5, None], "path": str(Path("/x"))},
        "3": "non-string key",
    }
    assert "first + i / sample_rate_hz" in header["timing"]
    assert "cannot be reconstructed" in header["timing"]
    src = ConcordRecordingSource(path)  # validated by RecordingHeader
    assert src.header().source_metadata == header["source_metadata"]


def test_unrepresentable_metadata_never_blocks_a_recording(tmp_path: Path) -> None:
    deep: dict[str, Any] = {}
    node = deep
    for _ in range(40):
        node["n"] = {}
        node = node["n"]
    rec = Recorder(tmp_path)
    rec.start(profile_a.descriptor(), "deep", source_metadata=deep)
    rec.stop()
    assert "source_metadata" not in _strict_header(tmp_path / "deep.concord.jsonl")


def test_recordings_with_the_earlier_header_still_replay(tmp_path: Path) -> None:
    rec = Recorder(tmp_path)
    rec.start(profile_a.descriptor(), "old")
    _write(rec, 4)
    rec.stop()
    path = tmp_path / "old.concord.jsonl"
    lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
    header = json.loads(lines[0])
    for key in ("source_metadata", "timing", "limits"):
        header.pop(key, None)
    path.write_text(json.dumps(header) + "\n" + "".join(lines[1:]), encoding="utf-8")
    src = ConcordRecordingSource(path)
    assert src.header().timing is None and src.header().source_metadata is None
    assert sum(1 for _ in src.records()) == 4


async def test_runtime_records_the_adapter_source_metadata(tmp_path: Path) -> None:
    rec_dir = tmp_path / "rec"
    rt = Runtime(DeviceRegistry(OperatorIntentSource(), rec_dir, seed=1), Recorder(rec_dir))
    await rt.connect("sim-a")
    name = rt.start_recording("no-meta")  # simulated adapters describe no external source
    rt.stop_recording()
    assert "source_metadata" not in _strict_header(rec_dir / f"{name}.concord.jsonl")

    adapter = rt.adapter
    assert adapter is not None
    adapter.source_metadata = lambda: {"protocol": "test", "uid": "abc"}  # type: ignore[attr-defined]
    name = rt.start_recording("with-meta")
    rt.stop_recording()
    header = _strict_header(rec_dir / f"{name}.concord.jsonl")
    assert header["source_metadata"] == {"protocol": "test", "uid": "abc"}

    def broken() -> dict[str, Any]:
        raise RuntimeError("source went away")

    adapter.source_metadata = broken  # type: ignore[attr-defined]
    name = rt.start_recording("meta-failed")  # still records; the failure is visible
    rt.stop_recording()
    assert "source_metadata" not in _strict_header(rec_dir / f"{name}.concord.jsonl")
    errors = rt.diagnostics.snapshot([]).recent_errors
    assert any(e.kind == "source_metadata" and "source went away" in e.message for e in errors)
    await rt.shutdown()


def test_recording_limits_from_config_file_and_environment(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    for var in (
        "CONCORD_RECORDING_MAX_S",
        "CONCORD_RECORDING_MAX_NO_RAW_S",
        "CONCORD_RECORDING_MAX_MB",
        "CONCORD_RECORDING_MIN_FREE_MB",
    ):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("CONCORD_CONFIG", str(tmp_path / "absent.toml"))
    s = Settings.from_env()
    assert (s.recording_max_duration_s, s.recording_max_bytes) == (300.0, 200 * MIB)
    assert s.recording_min_free_bytes == 256 * MIB

    cfg = tmp_path / "config.toml"
    cfg.write_text(
        "[recording]\nmax_duration_s = 1800\nmax_size_mb = 4096\nmin_free_mb = 0\n",
        encoding="utf-8",
    )
    cfg.chmod(0o600)
    monkeypatch.setenv("CONCORD_CONFIG", str(cfg))
    s = Settings.from_env()
    assert s.recording_max_duration_s == 1800.0 and s.recording_max_bytes == 4096 * MIB
    assert s.recording_max_duration_no_raw_s == 3600.0 and s.recording_min_free_bytes == 0
    monkeypatch.setenv("CONCORD_RECORDING_MAX_S", "7200")  # environment beats the file
    monkeypatch.setenv("CONCORD_DATA_DIR", str(tmp_path / "data"))
    s = Settings.from_env()
    assert s.recording_max_duration_s == 7200.0

    app = create_app(s)
    recorder = app.state.services.runtime.recorder
    assert (recorder.max_duration_s, recorder.max_bytes) == (7200.0, 4096 * MIB)
    assert recorder.min_free_bytes == 0

    for value, match in (("abc", "not a number"), ("0", r"\(0, 86400\]"), ("1e9", "86400")):
        monkeypatch.setenv("CONCORD_RECORDING_MAX_S", value)
        with pytest.raises(ConfigError, match=match):
            Settings.from_env()


@pytest.mark.parametrize(
    ("text", "match"),
    [
        ("[recording]\nmax_duration_s = 0\n", "seconds"),
        ("[recording]\nmax_duration_s = 90000\n", "seconds"),
        ('[recording]\nmax_duration_s = "1h"\n', "seconds"),
        ("[recording]\nmax_size_mb = 0\n", "1-102400"),
        ("[recording]\nmax_size_mb = 1.5\n", "integer"),
        ("[recording]\nmin_free_mb = -1\n", "0-102400"),
        ("[recording]\nsegment_s = 60\n", "unknown key"),
    ],
)
def test_malformed_recording_limits_are_refused(text: str, match: str) -> None:
    with pytest.raises(ConfigError, match=match):
        parse_config(text, Path("c.toml"))
