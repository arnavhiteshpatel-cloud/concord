"""Milestone 5 (D): `concord doctor` (no neural or personal data) and the `concord` command
(start / status / stop / version / config / serve), run as real processes."""

from __future__ import annotations

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

from concord import __version__, doctor
from concord.adapters.simulated import profile_a
from concord.contracts import parse_envelope
from concord.contracts.protocol import STREAM_PROTOCOL
from concord.runtime import Recorder
from concord.runtime.sessions import SessionManager

from .conftest import free_port
from .helpers import POSIX, assert_mode, fake_concord_at, graceful_stop, valid_event

posix = pytest.mark.skipif(not POSIX, reason="POSIX signals (SIGTERM ignored, zombie reaping)")

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
        "values [12345.678, 1, 2, 3, 4, 5, 6, 7, 8] contact alice@example.org\n",
        encoding="utf-8",
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
    # Windows: the home folder as JSON writes it (backslashes doubled), e.g. in tmp_path
    assert json.dumps(str(Path.home()) + os.sep)[1:-1] not in text
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
    assert_mode(j, 0o600)
    assert m.read_text(encoding="utf-8") == md


def test_doctor_reports_unsafe_config_and_busy_port(tmp_path: Path) -> None:
    import socket

    cfg = tmp_path / "config.toml"
    cfg.write_text("[server]\nport = 8000\n", encoding="utf-8")
    cfg.chmod(0o666)
    with socket.socket() as busy:
        busy.bind(("127.0.0.1", 0))
        busy.listen()
        port = busy.getsockname()[1]
        report = doctor.run(
            data_dir=tmp_path / "data", port=port, config_path=cfg, discover_plugins=False
        )
    checks = {c["id"]: c for c in report["checks"]}
    if POSIX:  # Windows has no mode bits: the file is not refused there
        assert checks["config"]["status"] == "fail" and "other users" in checks["config"]["detail"]
    # regression (Windows): SO_REUSEADDR there binds a port another program listens on, so a
    # busy port looked free
    assert checks["port"]["status"] == "fail" and "another program" in checks["port"]["detail"]
    assert checks["data_dir"]["status"] == "ok"  # not created yet is fine
    assert report["summary"]["fail"] >= (2 if POSIX else 1)


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
    assert r.returncode == 0
    assert_mode(tmp_path / "config.toml", 0o600)
    assert concord(["config", "init"], cli_env).returncode == 1  # never overwritten
    shown = json.loads(concord(["config", "show"], cli_env).stdout)
    assert shown["host"] == "127.0.0.1" and shown["allow_remote"] is False
    assert shown["data_dir"] == str(tmp_path / "data")  # environment beats the file
    (tmp_path / "config.toml").write_text("[server]\nhots = 1\n", encoding="utf-8")
    r = concord(["config", "show"], cli_env)
    assert r.returncode == 2 and "unknown key" in r.stderr


def test_serve_refuses_remote_bind_unless_allowed(cli_env: dict[str, str]) -> None:
    r = concord(["serve", "--host", "0.0.0.0"], cli_env, timeout=60)
    assert r.returncode == 2 and "refusing to listen" in r.stderr and "--allow-remote" in r.stderr
    r = concord(["start", "--host", "192.168.1.20"], cli_env, timeout=60)
    assert r.returncode == 2 and "no authentication" in r.stderr


def test_start_status_doctor_stop(cli_env: dict[str, str], tmp_path: Path) -> None:
    """Also on Windows: `start` detaches the server (own hidden console and process group) and
    `stop` reaches it through a stop request (Windows has no SIGTERM to catch)."""
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
        info = json.loads((tmp_path / "data" / "concord.pid").read_text(encoding="utf-8"))
        assert info["pid"] == pid and info["port"] == int(port)
        # starting again finds the running server instead of starting a second one
        r2 = concord(["start"], cli_env)
        assert r2.returncode == 0 and f"is running: {base}" in r2.stdout
        assert f"data: {tmp_path / 'data'}" in r2.stdout and not r2.stderr
        assert httpx.get(base + "/api/v1/health").json()["pid"] == pid
        # do something worth stopping safely
        httpx.post(base + "/api/v1/runtime/connect", json={"device_id": "sim-a"}).raise_for_status()
        httpx.post(base + "/api/v1/recordings/start", json={"name": "cli-rec"}).raise_for_status()
        st = json.loads(concord(["status", "--json"], cli_env).stdout)
        assert st["running"] and st["pid"] == pid and st["runtime"]["state"] == "streaming"
        assert st["differences"] == []  # this data directory's own server
        assert st["runtime"]["recording"] == "cli-rec" and st["command_output"] == "off"
        r = concord(["doctor", "--json", str(tmp_path / "d.json"), "--no-plugins"], cli_env)
        rep = json.loads((tmp_path / "d.json").read_text(encoding="utf-8"))
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
    assert_mode(log, 0o600)
    assert "ready" in log.read_text(encoding="utf-8")


def test_start_reports_a_port_used_by_another_program(cli_env: dict[str, str]) -> None:
    import socket

    with socket.socket() as busy:
        busy.bind(("127.0.0.1", int(cli_env["CONCORD_PORT"])))
        busy.listen()
        r = concord(["start"], cli_env)
    assert r.returncode == 1 and "in use by another program" in r.stderr


# /api/v1/health of a build from before the rename, started with its own data directory
PRE_RENAME_COPY = {
    "status": "ok",
    "version": "0.3.0",
    "schema_version": "1.4",
    "stream_protocol": "previous-name.stream/1",
    "simulation_enabled": True,
    "read_only": True,
    "pid": 4242,
}


def test_differences_name_what_sets_another_copy_apart() -> None:
    from concord import launcher

    own = {"status": "ok", "version": __version__, "stream_protocol": STREAM_PROTOCOL}

    def diff(health: dict[str, Any], pid_file: bool = True, launched: bool = False) -> list[str]:
        inst = launcher.Instance(1, "http://127.0.0.1:1", health, pid_file, launched)
        return launcher.differences(inst, version=__version__, stream_protocol=STREAM_PROTOCOL)

    assert diff(own) == []  # this data directory's own server
    assert diff(own, pid_file=False, launched=True) == []  # the one `start` just launched
    assert diff(own, pid_file=False) == ["data_dir"]  # same build, found only by its URL
    assert diff({**own, "version": "0.0.1"}) == ["version"]  # this data directory, older build
    assert diff({"status": "ok"}, pid_file=False) == ["data_dir", "version", "stream_protocol"]


def test_start_does_not_claim_this_data_dir_for_another_copy(
    cli_env: dict[str, str], tmp_path: Path
) -> None:
    """Another installation answers on the port: `start` names it and what differs, and exits
    3 instead of reporting it as this data directory's Concord."""
    port = cli_env["CONCORD_PORT"]
    data = tmp_path / "data"
    with fake_concord_at(int(port), PRE_RENAME_COPY) as base:
        r = concord(["start", "--port", port], cli_env)
        st = concord(["status"], cli_env)
        st_json = json.loads(concord(["status", "--json"], cli_env).stdout)
    assert r.returncode == 3, (r.stdout, r.stderr)
    assert r.stdout == ""  # no "is running", no "data: <this data directory>"
    assert f"another copy of Concord is running at {base} (version 0.3.0, pid 4242)" in r.stderr
    assert f"it does not use this data directory ({data})" in r.stderr
    assert (
        f"its stream protocol is previous-name.stream/1; this version's is {STREAM_PROTOCOL}"
        in (r.stderr)
    )
    assert "Nothing was started" in r.stderr
    assert f"`concord stop --port {port}`, or quit it where it runs" in r.stderr
    assert not (data / "concord.pid").exists()
    # status reports the server it finds, as another copy and without this data directory
    assert st.returncode == 0, st.stderr
    assert st.stdout.startswith(f"Another copy of Concord is running at {base}")
    assert f"data: {data}" not in st.stdout and "concord stop --port" not in st.stdout
    assert st_json["running"] and st_json["pid"] == 4242 and st_json["data_dir"] == str(data)
    assert st_json["differences"][0] == "data_dir" and "stream_protocol" in st_json["differences"]


def test_start_names_where_to_quit_another_copy_without_a_pid(cli_env: dict[str, str]) -> None:
    older = {k: v for k, v in PRE_RENAME_COPY.items() if k != "pid"}  # before M5-D
    with fake_concord_at(int(cli_env["CONCORD_PORT"]), older):
        r = concord(["start"], cli_env)
    assert r.returncode == 3 and "pid unknown" in r.stderr
    assert "quit the other copy where it runs" in r.stderr and "concord stop" not in r.stderr


@posix
def test_start_reports_an_older_server_of_this_data_dir(
    cli_env: dict[str, str], tmp_path: Path
) -> None:
    """This data directory's server (it holds the instance lock) at another version: same
    report, and the data directory is the one in use."""
    import fcntl

    port = int(cli_env["CONCORD_PORT"])
    data = tmp_path / "data"
    data.mkdir()
    fd = os.open(data / "concord.pid", os.O_RDWR | os.O_CREAT, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        base = f"http://127.0.0.1:{port}"
        os.write(fd, json.dumps({"pid": 4242, "url": base, "port": port}).encode())
        older = {**PRE_RENAME_COPY, "version": "0.2.0", "stream_protocol": STREAM_PROTOCOL}
        with fake_concord_at(port, older):
            r = concord(["start"], cli_env)
            st = concord(["status"], cli_env)
    finally:
        os.close(fd)
    assert r.returncode == 3 and r.stdout == "", (r.stdout, r.stderr)
    assert f"another copy of Concord is running at {base} (version 0.2.0, pid 4242)" in r.stderr
    assert f"its version is 0.2.0; this is {__version__}" in r.stderr
    assert "data directory" not in r.stderr and "stream protocol" not in r.stderr
    assert "`concord stop`, or quit it where it runs" in r.stderr
    assert st.returncode == 0 and f"data: {data}" in st.stdout
    assert f"its version is 0.2.0; this is {__version__}" in st.stdout


def test_desktop_app_headless_starts_and_stops_cleanly(
    cli_env: dict[str, str], tmp_path: Path
) -> None:
    """The desktop app's controller (what Concord.app / Concord.exe run), headless: SIGTERM =
    Quit; on Windows the stop request that `concord stop` writes."""
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
        graceful_stop(proc.pid, tmp_path / "data" / "concord.pid")
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
