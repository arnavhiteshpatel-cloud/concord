"""Milestone 5 (D): `concord doctor` (no neural or personal data) and the `concord` command
(start / status / stop / version / config / serve), run as real processes."""

from __future__ import annotations

import json
import os
import signal
import stat
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import httpx
import pytest

from concord import __version__, doctor
from concord.adapters.simulated import profile_a
from concord.contracts import parse_envelope
from concord.runtime import Recorder
from concord.runtime.sessions import SessionManager

from .conftest import free_port
from .helpers import valid_event

posix = pytest.mark.skipif(os.name != "posix", reason="POSIX processes and permissions")

SENSITIVE = [
    "12345.678",  # a sample value in a recording
    "-98765.4321",
    "Dr Example Person",  # operator
    "Participant P-07",  # notes
    "pilot-p07",  # session / recording names
    "hunter2",  # a secret in a log line
    "192.168.77.20",  # an acquisition host address
    "alice@example.org",
]


def _sensitive_data_dir(root: Path) -> Path:
    data = root / "data"
    rec = Recorder(data / "recordings")
    rec.start(profile_a.descriptor(), "pilot-p07-block1")
    ev = valid_event("recording.frame", device_id="sim-a")
    ev["payload"]["samples"] = [[12345.678, -98765.4321]] * 2
    env = parse_envelope(ev)
    rec.on_event(env, env.model_dump_json())
    rec.stop()
    sm = SessionManager(data / "sessions")
    sm.create("pilot-p07", operator="Dr Example Person", notes="Participant P-07 felt tired")
    sm.close()
    logs = data / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    home = Path.home()
    (logs / "concord.log").write_text(
        "2026-11-07 10:00:00,000 INFO    concord.x: fine\n"
        f"2026-11-07 10:00:01,000 WARNING concord.x: cannot open {home}/concord/data/x.nwb\n"
        "2026-11-07 10:00:02,000 ERROR   concord.y: lsl outlet at 192.168.77.20 password=hunter2 "
        "values [12345.678, 1, 2, 3, 4, 5, 6, 7, 8] contact alice@example.org\n"
    )
    return data


def test_doctor_report_has_no_neural_or_personal_data(tmp_path: Path) -> None:
    data = _sensitive_data_dir(tmp_path)
    report = doctor.run(
        data_dir=data,
        port=free_port(),
        config_path=tmp_path / "absent.toml",
        discover_plugins=False,
    )
    text = json.dumps(report) + doctor.to_markdown(report)
    for s in SENSITIVE:
        assert s not in text, s
    assert str(Path.home()) + "/" not in text
    assert (
        report["format"] == "concord.support-report/1"
        and report["concord"]["version"] == __version__
    )
    ids = {c["id"] for c in report["checks"]}
    for cid in (
        "concord",
        "server_extra",
        "config",
        "dsp",
        "nwb",
        "lsl",
        "zmq",
        "brainflow",
        "bci2000",
        "bind",
        "port",
        "data_dir",
        "permissions",
        "disk",
        "logs",
        "plugins",
    ):
        assert cid in ids, cid
    assert (
        report["storage"]["counts"]["recordings"] == 1
        and report["storage"]["counts"]["sessions"] == 1
    )
    assert report["logs"]["counts"] == {"WARNING": 1, "ERROR": 1, "CRITICAL": 0}
    assert any("~/concord/data" in line for line in report["logs"]["recent"])
    assert any("neural data" in e for e in report["excluded"])
    pkgs = {p["name"]: p for p in report["packages"]}
    assert pkgs["concordos"]["installed"] and pkgs["concordos"]["version"] == __version__
    md = doctor.to_markdown(report)
    assert "## Not included in this report" in md and "| Check | Status | Detail |" in md
    j, m = doctor.write(report, tmp_path / "support")
    assert stat.S_IMODE(j.stat().st_mode) == 0o600 and m.read_text() == md


def test_doctor_reports_unsafe_config_and_busy_port(tmp_path: Path) -> None:
    import socket

    cfg = tmp_path / "config.toml"
    cfg.write_text("[server]\nport = 8000\n")
    cfg.chmod(0o666)
    with socket.socket() as busy:
        busy.bind(("127.0.0.1", 0))
        busy.listen()
        port = busy.getsockname()[1]
        report = doctor.run(
            data_dir=tmp_path / "data", port=port, config_path=cfg, discover_plugins=False
        )
    checks = {c["id"]: c for c in report["checks"]}
    assert checks["config"]["status"] == "fail" and "other users" in checks["config"]["detail"]
    assert checks["port"]["status"] == "fail" and "another program" in checks["port"]["detail"]
    assert checks["data_dir"]["status"] == "ok"  # not created yet is fine
    assert report["summary"]["fail"] >= 2


# --------------------------------------------------------------------------- the command


def concord(
    args: list[str], env: dict[str, str], timeout: float = 120
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "concord", *args],
        env=env,
        text=True,
        capture_output=True,
        timeout=timeout,
    )


@pytest.fixture
def cli_env(tmp_path: Path) -> dict[str, str]:
    return {
        **os.environ,
        "CONCORD_CONFIG": str(tmp_path / "config.toml"),
        "CONCORD_DATA_DIR": str(tmp_path / "data"),
        "CONCORD_PORT": str(free_port()),
        "CONCORD_STATIC_DIR": str(tmp_path / "no-console"),
        "CONCORD_PLUGINS": "0",
        "CONCORD_OPEN_BROWSER": "0",
    }


def test_version_and_config_commands(cli_env: dict[str, str], tmp_path: Path) -> None:
    r = concord(["version", "--json"], cli_env)
    assert r.returncode == 0 and json.loads(r.stdout)["concord"] == __version__
    assert concord(["--version"], cli_env).stdout.strip() == f"Concord {__version__}"
    assert concord(["config", "path"], cli_env).stdout.strip() == str(tmp_path / "config.toml")
    r = concord(["config", "init"], cli_env)
    assert r.returncode == 0 and stat.S_IMODE((tmp_path / "config.toml").stat().st_mode) == 0o600
    assert concord(["config", "init"], cli_env).returncode == 1  # never overwritten
    shown = json.loads(concord(["config", "show"], cli_env).stdout)
    assert shown["host"] == "127.0.0.1" and shown["allow_remote"] is False
    assert shown["data_dir"] == str(tmp_path / "data")  # environment beats the file
    (tmp_path / "config.toml").write_text("[server]\nhots = 1\n")
    r = concord(["config", "show"], cli_env)
    assert r.returncode == 2 and "unknown key" in r.stderr


@posix
def test_serve_refuses_remote_bind_unless_allowed(cli_env: dict[str, str]) -> None:
    r = concord(["serve", "--host", "0.0.0.0"], cli_env, timeout=60)
    assert r.returncode == 2 and "refusing to listen" in r.stderr and "--allow-remote" in r.stderr
    r = concord(["start", "--host", "192.168.1.20"], cli_env, timeout=60)
    assert r.returncode == 2 and "no authentication" in r.stderr


@posix
def test_start_status_doctor_stop(cli_env: dict[str, str], tmp_path: Path) -> None:
    port = cli_env["CONCORD_PORT"]
    base = f"http://127.0.0.1:{port}"
    r = concord(["status"], cli_env)
    assert r.returncode == 3 and "not running" in r.stdout
    r = concord(["start", "--timeout", "90"], cli_env)
    try:
        assert r.returncode == 0, r.stderr
        assert f"is running: {base}" in r.stdout and "concord stop" in r.stdout
        h = httpx.get(base + "/api/v1/health").json()
        pid = h["pid"]
        info = json.loads((tmp_path / "data" / "concord.pid").read_text())
        assert info["pid"] == pid and info["port"] == int(port)
        # starting again finds the running server instead of starting a second one
        r2 = concord(["start"], cli_env)
        assert r2.returncode == 0 and f"is running: {base}" in r2.stdout
        assert httpx.get(base + "/api/v1/health").json()["pid"] == pid
        # do something worth stopping safely
        httpx.post(base + "/api/v1/runtime/connect", json={"device_id": "sim-a"}).raise_for_status()
        httpx.post(base + "/api/v1/recordings/start", json={"name": "cli-rec"}).raise_for_status()
        st = json.loads(concord(["status", "--json"], cli_env).stdout)
        assert st["running"] and st["pid"] == pid and st["runtime"]["state"] == "streaming"
        assert st["runtime"]["recording"] == "cli-rec" and st["command_output"] == "off"
        r = concord(["doctor", "--json", str(tmp_path / "d.json"), "--no-plugins"], cli_env)
        rep = json.loads((tmp_path / "d.json").read_text())
        port_check = next(c for c in rep["checks"] if c["id"] == "port")
        assert "in use by Concord" in port_check["detail"] and rep["server"]["running"]
        rep_rest = httpx.get(base + "/api/v1/system/doctor").json()
        assert rep_rest["format"] == "concord.support-report/1"
        md = httpx.get(base + "/api/v1/system/doctor", params={"format": "markdown"})
        assert md.status_code == 200 and md.text.startswith("# Concord support report")
    finally:
        r = concord(["stop"], cli_env)
    assert r.returncode == 0, r.stderr
    assert "recording cli-rec closed" in r.stdout and "source disconnected" in r.stdout
    assert "Concord stopped" in r.stdout
    with pytest.raises(httpx.HTTPError):
        httpx.get(base + "/api/v1/health", timeout=1)
    rec = tmp_path / "data" / "recordings"
    assert (rec / "cli-rec.concord.jsonl").exists() and not (rec / "cli-rec.active.json").exists()
    assert concord(["status"], cli_env).returncode == 3
    assert "not running" in concord(["stop"], cli_env).stdout
    log = tmp_path / "data" / "logs" / "concord.log"
    assert stat.S_IMODE(log.stat().st_mode) == 0o600 and "ready" in log.read_text()


@posix
def test_start_reports_a_port_used_by_another_program(cli_env: dict[str, str]) -> None:
    import socket

    with socket.socket() as busy:
        busy.bind(("127.0.0.1", int(cli_env["CONCORD_PORT"])))
        busy.listen()
        r = concord(["start"], cli_env)
    assert r.returncode == 1 and "in use by another program" in r.stderr


@posix
def test_desktop_app_headless_starts_and_stops_cleanly(
    cli_env: dict[str, str], tmp_path: Path
) -> None:
    """The desktop app's controller (what Concord.app runs), headless: SIGTERM = Quit."""
    port = cli_env["CONCORD_PORT"]
    base = f"http://127.0.0.1:{port}"
    proc = subprocess.Popen(
        [
            sys.executable,
            "-c",
            "import sys; from concord.desktop import main; sys.exit(main())",
            "--headless",
            "--no-browser",
        ],
        env=cli_env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    try:
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            assert proc.poll() is None, proc.stdout.read() if proc.stdout else ""
            try:
                if httpx.get(base + "/api/v1/health", timeout=0.5).status_code == 200:
                    break
            except httpx.HTTPError:
                time.sleep(0.1)
        httpx.post(base + "/api/v1/runtime/connect", json={"device_id": "sim-a"}).raise_for_status()
        httpx.post(base + "/api/v1/recordings/start", json={"name": "app-rec"}).raise_for_status()
        # a second launch only points at the running instance (single instance)
        again = subprocess.run(
            [
                sys.executable,
                "-c",
                "import sys; from concord.desktop import main; sys.exit(main())",
                "--headless",
                "--no-browser",
            ],
            env=cli_env,
            text=True,
            capture_output=True,
            timeout=60,
        )
        assert again.returncode == 0 and "already running" in again.stdout
        time.sleep(0.5)
        proc.send_signal(signal.SIGTERM)
        code = proc.wait(60)
        out: Any = proc.stdout.read() if proc.stdout else ""
    finally:
        if proc.poll() is None:
            proc.kill()
    assert code == 0, out
    assert f"is running at {base}" in out
    rec = tmp_path / "data" / "recordings"
    assert (rec / "app-rec.concord.jsonl").exists() and not (rec / "app-rec.active.json").exists()
    assert not (tmp_path / "data" / "concord.pid").exists()


@posix
def test_stop_counts_a_server_without_lock_and_api_as_stopped(tmp_path: Path) -> None:
    """A server that released its instance lock and no longer answers is stopped, even if its
    process has not been reaped yet (containers without an init); never SIGKILLed then."""
    from concord import launcher

    proc = subprocess.Popen(
        [
            sys.executable,
            "-c",
            "import signal, time; signal.signal(signal.SIGTERM, "
            "signal.SIG_IGN); print('ready', flush=True); time.sleep(60)",
        ],
        stdout=subprocess.PIPE,
        text=True,
    )
    try:
        assert proc.stdout is not None and proc.stdout.readline().strip() == "ready"
        inst = launcher.Instance(
            pid=proc.pid, url=f"http://127.0.0.1:{free_port()}", health=None, from_pid_file=True
        )
        t0 = time.monotonic()
        result = launcher.stop(inst, timeout_s=10, pid_file=tmp_path / "concord.pid")
        assert not result["forced"] and time.monotonic() - t0 < 5
        assert proc.poll() is None  # it ignored SIGTERM and was not killed
        # without the lock information, the same process is force-stopped after the timeout
        result = launcher.stop(inst, timeout_s=1)
        assert result["forced"]
        assert proc.wait(10) == -signal.SIGKILL
    finally:
        if proc.poll() is None:
            proc.kill()
