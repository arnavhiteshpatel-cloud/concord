"""Milestone 5 (D): recordings interrupted by a crash or kill keep their valid prefix, are
marked incomplete, and nothing is dropped silently. Includes killing a real server process."""

from __future__ import annotations

import hashlib
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import httpx
import pytest

from concord.adapters.replay import ConcordRecordingSource
from concord.adapters.simulated import profile_a
from concord.config import Retention
from concord.runtime import Recorder
from concord.runtime.retention import enforce
from concord.runtime.sessions import SessionManager
from concord.server.serve import request_stop

from .conftest import free_port
from .helpers import POSIX, assert_mode, graceful_stop, kill_now, server_pid, valid_event


def _write_events(rec: Recorder, n: int) -> None:
    from concord.contracts import parse_envelope

    for i in range(n):
        env = parse_envelope(valid_event("telemetry.sample", seq=i, device_id="sim-a"))
        rec.on_event(env, env.model_dump_json())


def test_recording_files_are_private_and_marked_while_written(tmp_path: Path) -> None:
    """Also on Windows: the marker's lock (a byte-range lock there) keeps a recording that is
    being written from being "recovered", and a clean stop removes the marker (Windows cannot
    delete a file that is still open: regression, the marker stayed behind)."""
    rec = Recorder(tmp_path / "rec")
    name = rec.start(profile_a.descriptor(), "r1")
    path = tmp_path / "rec" / "r1.concord.jsonl"
    marker = tmp_path / "rec" / "r1.active.json"
    assert_mode(path, 0o600)
    assert_mode(tmp_path / "rec", 0o700)
    assert marker.exists() and json.loads(marker.read_text(encoding="utf-8"))["pid"] == os.getpid()
    # another recorder (a second process would behave the same) leaves a held recording alone
    assert Recorder(tmp_path / "rec").recover() == []
    _write_events(rec, 5)
    info = rec.stop()
    assert info is not None and info.events == 5 and info.complete
    assert not marker.exists()
    assert rec.list()[0].name == name and rec.list()[0].complete


def test_interrupted_recording_keeps_its_valid_prefix(tmp_path: Path) -> None:
    rec = Recorder(tmp_path / "rec")
    rec.start(profile_a.descriptor(), "crash-1")
    _write_events(rec, 20)
    assert rec._fh is not None
    rec._fh.flush()
    path = tmp_path / "rec" / "crash-1.concord.jsonl"
    whole = path.read_bytes()
    partial = b'{"schema_version":"1.0","session_id":"ses_x","seq":20,"timest'
    with path.open("ab") as fh:
        fh.write(partial)  # a line cut by the crash
    # simulate the process dying: drop the file handle and the lock without a clean stop
    rec._fh = None
    assert rec._marker_fd is not None
    os.close(rec._marker_fd)
    rec._marker_fd = None
    rec._name = None

    fresh = Recorder(tmp_path / "rec")
    recovered = fresh.recover()
    assert [n for n, _ in recovered] == ["crash-1"]
    info = recovered[0][1]
    assert info.status == "incomplete" and info.valid_events == 20
    assert info.valid_bytes == len(whole) and info.discarded_bytes == len(partial)
    assert info.discarded_sha256 == hashlib.sha256(partial).hexdigest()
    assert path.read_bytes() == whole  # valid prefix kept byte for byte
    assert (tmp_path / "rec" / "crash-1.discarded.bin").read_bytes() == partial  # nothing lost
    assert not (tmp_path / "rec" / "crash-1.active.json").exists()
    listed = fresh.list()[0]
    assert not listed.complete and listed.recovery is not None and listed.events == 20
    assert sum(1 for _ in ConcordRecordingSource(path).records()) == 20  # replayable
    assert fresh.recover() == []  # idempotent
    freed = fresh.delete("crash-1")  # sidecars go with it
    assert freed > 0 and list((tmp_path / "rec").iterdir()) == []


def test_old_recording_without_marker_cut_mid_line_is_recovered(tmp_path: Path) -> None:
    rec = Recorder(tmp_path / "rec")
    rec.start(profile_a.descriptor(), "legacy")
    _write_events(rec, 3)
    rec.stop()
    path = tmp_path / "rec" / "legacy.concord.jsonl"
    with path.open("ab") as fh:
        fh.write(b'{"partial":')
    out = Recorder(tmp_path / "rec").recover()
    assert out and out[0][1].valid_events == 3 and out[0][1].discarded_bytes == 11


def test_unreadable_header_is_reported_not_touched(tmp_path: Path) -> None:
    d = tmp_path / "rec"
    d.mkdir()
    (d / "bad.concord.jsonl").write_bytes(b"not json")
    (d / "bad.active.json").write_text('{"pid": 999999}', encoding="utf-8")
    out = Recorder(d).recover()
    assert out[0][1].status == "unreadable"
    assert (d / "bad.concord.jsonl").read_bytes() == b"not json"


def test_retention_policy(tmp_path: Path) -> None:
    rec = Recorder(tmp_path / "rec")
    rec.start(profile_a.descriptor(), "old")
    rec.stop()
    rec.start(profile_a.descriptor(), "new")
    rec.stop()
    rec.start(profile_a.descriptor(), "active")
    sm = SessionManager(tmp_path / "sessions")
    s = sm.create("old session")
    sm.close()
    models = tmp_path / "models"
    models.mkdir()
    (models / "old-model.json").write_text(
        '{"created_at": "2020-01-01T00:00:00Z"}', encoding="utf-8"
    )
    (models / "running-model.json").write_text(
        '{"created_at": "2020-01-01T00:00:00Z"}', encoding="utf-8"
    )
    (models / "new-model.json").write_text(
        '{"created_at": "2999-01-01T00:00:00Z"}', encoding="utf-8"
    )
    old_header = json.loads(
        (tmp_path / "rec" / "old.concord.jsonl").read_text(encoding="utf-8").splitlines()[0]
    )
    now = old_header["created_at_ns"] + 40 * 86_400 * 10**9
    # make "new" 1 day old relative to `now`
    lines = (tmp_path / "rec" / "new.concord.jsonl").read_text(encoding="utf-8").splitlines()
    h = json.loads(lines[0])
    h["created_at_ns"] = now - 86_400 * 10**9
    (tmp_path / "rec" / "new.concord.jsonl").write_text(json.dumps(h) + "\n", encoding="utf-8")
    result = enforce(
        Retention(recordings_days=30, sessions_days=30, models_days=30),
        recorder=rec,
        sessions=sm,
        models_dir=models,
        model_in_use="running-model",
        now_ns=now,
    )
    deleted = {(d.kind, d.name) for d in result.deleted}
    assert ("recording", "old") in deleted and ("session", s.id) in deleted
    assert ("model", "old-model") in deleted
    assert ("recording", "new") not in deleted and ("model", "new-model") not in deleted
    assert any("active" in k for k in result.kept_in_use)  # the recording being written
    assert any("running-model" in k for k in result.kept_in_use)
    assert (models / "running-model.json").exists() and (
        tmp_path / "rec" / "active.concord.jsonl"
    ).exists()
    assert not result.errors
    rec.stop()


# --------------------------------------------------------------------------- a real process


def _server(tmp_path: Path, port: int) -> subprocess.Popen[bytes]:
    env = {
        **os.environ,
        "CONCORD_PORT": str(port),
        "CONCORD_DATA_DIR": str(tmp_path / "data"),
        "CONCORD_CONFIG": str(tmp_path / "absent.toml"),
        "CONCORD_STATIC_DIR": str(tmp_path / "no-console"),
        "CONCORD_PLUGINS": "0",
        "CONCORD_LOG_LEVEL": "INFO",
    }
    return subprocess.Popen(
        [sys.executable, "-m", "concord.server"],  # concord-server (= concord serve)
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def _wait(base: str, proc: subprocess.Popen[bytes], timeout: float = 30) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        assert proc.poll() is None, "server exited"
        try:
            if httpx.get(base + "/api/v1/health", timeout=0.5).status_code == 200:
                return
        except httpx.HTTPError:
            pass
        time.sleep(0.1)
    raise AssertionError("server did not start")


def _record_for(base: str, seconds: float) -> str:
    httpx.post(base + "/api/v1/runtime/connect", json={"device_id": "sim-a"}).raise_for_status()
    r = httpx.post(base + "/api/v1/recordings/start", json={"name": "killed"})
    r.raise_for_status()
    time.sleep(seconds)
    name: str = r.json()["name"]
    return name


@pytest.mark.parametrize("how", ["kill", "graceful", "stop_request"])
def test_server_killed_mid_recording(tmp_path: Path, how: str) -> None:
    """Killed (SIGKILL; TerminateProcess on Windows): the next start keeps the valid prefix and
    marks it incomplete. Graceful (SIGTERM; a stop request on Windows) and a stop request (on
    every platform): the recording is closed completely."""
    killed = how == "kill"
    port = free_port()
    base = f"http://127.0.0.1:{port}"
    proc = _server(tmp_path, port)
    try:
        _wait(base, proc)
        name = _record_for(base, 1.5)
        if killed:
            kill_now(server_pid(tmp_path / "data" / "concord.pid"))
        elif how == "stop_request":  # what `concord stop` sends on Windows; works everywhere
            pid_file = tmp_path / "data" / "concord.pid"
            request_stop(pid_file, server_pid(pid_file))
        else:
            graceful_stop(proc.pid, tmp_path / "data" / "concord.pid")
        code = proc.wait(30)
        # uvicorn re-raises SIGTERM after its graceful shutdown; Windows: TerminateProcess's 15
        if killed:
            assert code == (-signal.SIGKILL if POSIX else 15), code
        elif how == "stop_request":
            assert code == 0, code
            assert not (tmp_path / "data" / "concord.pid").exists()  # lock released and removed
        else:
            assert code in (0, -signal.SIGTERM), code
    finally:
        if proc.poll() is None:
            proc.kill()
    rec_dir = tmp_path / "data" / "recordings"
    assert (rec_dir / f"{name}.active.json").exists() == killed

    proc = _server(tmp_path, port)
    try:
        _wait(base, proc)
        recs: list[dict[str, Any]] = httpx.get(base + "/api/v1/recordings").json()
        r = next(x for x in recs if x["name"] == name)
        if killed:
            assert r["complete"] is False and r["recovery"]["status"] == "incomplete"
            assert r["recovery"]["valid_events"] > 20  # flushed at least every 0.25 s
            storage = httpx.get(base + "/api/v1/storage").json()
            assert storage["recovered_recordings"] == [name]
        else:
            assert r["complete"] is True and r["recovery"] is None
        assert not (rec_dir / f"{name}.active.json").exists()
        assert_mode(rec_dir / f"{name}.concord.jsonl", 0o600)
        # the recording is usable as a replay source
        snap = httpx.post(base + "/api/v1/runtime/connect", json={"device_id": f"replay:{name}"})
        assert snap.status_code == 200 and snap.json()["state"] == "streaming"
        httpx.post(base + "/api/v1/runtime/disconnect")
        log_text = (tmp_path / "data" / "logs" / "concord.log").read_text(encoding="utf-8")
        if killed:
            assert "was interrupted" in log_text
    finally:
        proc.terminate()
        proc.wait(30)
