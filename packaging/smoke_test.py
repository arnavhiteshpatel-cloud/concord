"""Smoke-test a built Concord desktop bundle as a user would run it (no repository code used).

    python packaging/smoke_test.py EXECUTABLE [--cli PROGRAM] [--app Concord.app] [--gui]
                                   [--window] [--dmg Concord.dmg] [--report report.json]

EXECUTABLE is ``Concord.app/Contents/MacOS/Concord`` (macOS), ``Concord/Concord`` (Linux) or
``Concord\\Concord.exe`` (Windows). ``--cli`` is the program that answers ``concord`` commands:
the same executable on macOS and Linux, ``Concord\\concord-cli.exe`` on Windows (the windowed
``Concord.exe`` has no console output). Steps (each recorded in the report; any failure exits 1):

1. ``--version``, the decoder host and ``doctor`` from the bundle itself.
2. Headless launch with a fresh data directory: health, the console page, the built-in
   sources, bundled native parts (scipy pipeline presets, NWB support, liblsl), the plugin
   host inside the bundle (BCI2000 plugin discovered as compatible), Simulated Profile A
   connected over REST with events flowing, a research session and a recording; then quit
   (SIGTERM; on Windows ``concord-cli.exe stop``, which has no SIGTERM to send) and checks that
   the recording was closed cleanly (with private permissions, on POSIX).
3. Crash recovery: kill mid-recording (SIGKILL / TerminateProcess), relaunch, the recording
   is kept and marked incomplete.
3a. Another copy answering on the app's address (e.g. an older build still running): the app
   does not start, says so in its log and exits 3; it only asks that copy for its health.
4. ``start`` / ``status`` / ``stop`` from the command program: the background server.
5. ``--window``: the Tk status window opens, and the same quit stops everything cleanly.
6. ``--gui`` (macOS): ``open`` the .app like a double-click, then quit it with an Apple Event
   (as Cmd-Q / Dock > Quit do) and check the clean shutdown.
7. ``--dmg``: attach the disk image read-only and run step 2 from the mounted app.
"""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import shutil
import signal
import socket
import stat
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
from collections.abc import Callable, Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, ParamSpec

P = ParamSpec("P")
BUNDLE_ID = "org.concord.desktop"
STEPS: list[dict[str, Any]] = []
WINDOWS = sys.platform == "win32"


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port: int = s.getsockname()[1]
        return port


def http(method: str, url: str, body: Any = None, timeout: float = 10) -> Any:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        url, data=data, method=method, headers={"content-type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        raw = r.read()
        ctype = r.headers.get("content-type", "")
    return json.loads(raw) if "json" in ctype else raw.decode("utf-8", "replace")


def healthy(base: str) -> dict[str, Any] | None:
    try:
        h = http("GET", base + "/api/v1/health", timeout=1)
        return h if isinstance(h, dict) else None
    except (OSError, urllib.error.URLError, ValueError):
        return None


def wait_until(cond: Any, timeout: float, what: str, interval: float = 0.25) -> Any:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        value = cond()
        if value:
            return value
        time.sleep(interval)
    raise AssertionError(f"timed out after {timeout:.0f} s waiting for {what}")


def step(name: str) -> Callable[[Callable[P, str]], Callable[P, str]]:
    def deco(fn: Callable[P, str]) -> Callable[P, str]:
        def run(*a: P.args, **kw: P.kwargs) -> str:
            t0 = time.monotonic()
            try:
                detail = fn(*a, **kw)
            except Exception as exc:
                STEPS.append(
                    {
                        "step": name,
                        "ok": False,
                        "seconds": round(time.monotonic() - t0, 1),
                        "detail": f"{type(exc).__name__}: {exc}",
                    }
                )
                print(f"  FAIL {name}: {exc}", flush=True)
                raise
            STEPS.append(
                {
                    "step": name,
                    "ok": True,
                    "seconds": round(time.monotonic() - t0, 1),
                    "detail": detail,
                }
            )
            print(f"  ok   {name}: {detail}", flush=True)
            return detail

        return run

    return deco


def env_for(data: Path, port: int) -> dict[str, str]:
    env = {k: v for k, v in os.environ.items() if not k.startswith("CONCORD_")}
    env.update(
        {
            "CONCORD_DATA_DIR": str(data),
            "CONCORD_PORT": str(port),
            "CONCORD_CONFIG": str(data.parent / "no-config.toml"),
            "CONCORD_OPEN_BROWSER": "0",
        }
    )
    return env


def run_cli(cli: Path, args: list[str], data: Path, port: int, timeout: float = 180) -> Any:
    """A ``concord`` command from the bundle, for the instance on ``data`` / ``port``."""
    return subprocess.run(
        [str(cli), *args],
        env=env_for(data, port),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
    )


def launch(exe: Path, data: Path, port: int, *, window: bool = False) -> subprocess.Popen[bytes]:
    log = (data.parent / f"launch-{port}.log").open("ab")
    args = ["--no-browser"] if window else ["--headless", "--no-browser"]
    return subprocess.Popen(
        [str(exe), *args],
        env={**env_for(data, port), "PYTHONIOENCODING": "utf-8"},
        stdout=log,
        stderr=subprocess.STDOUT,
    )


def quit_app(proc: subprocess.Popen[bytes], cli: Path, data: Path, port: int) -> tuple[int, str]:
    """Quit like `concord stop` does: SIGTERM on POSIX; on Windows the command program's
    `stop` (a stop request: Windows has no SIGTERM a program can catch). Returns the app's
    exit code and how it was asked."""
    if WINDOWS:
        out = run_cli(cli, ["stop"], data, port, timeout=120)
        text = (out.stdout + out.stderr).strip()
        assert out.returncode == 0, f"stop exited {out.returncode}: {text[-1500:]}"
        assert "Concord stopped" in text, text[-1500:]
        how = "concord-cli.exe stop"
    else:
        proc.send_signal(signal.SIGTERM)
        how = "SIGTERM"
    return proc.wait(60), how


def wait_healthy(
    base: str, proc: subprocess.Popen[bytes] | None, timeout: float = 180
) -> dict[str, Any]:
    def ready() -> dict[str, Any] | None:
        if proc is not None and proc.poll() is not None:
            raise AssertionError(f"the app exited during startup (code {proc.returncode})")
        return healthy(base)

    h: dict[str, Any] = wait_until(ready, timeout, "the app to become healthy")
    return h


def mode(p: Path) -> int:
    return stat.S_IMODE(p.stat().st_mode)


def lock_released(pid_file: Path) -> bool:
    """No process holds the server's instance lock. Windows: the file is gone (the server
    deletes it after closing it). POSIX: the file may stay behind after SIGTERM (uvicorn ends
    the process by re-raising the signal), but nobody holds its lock."""
    if not pid_file.exists():
        return True
    if WINDOWS:
        return False
    import fcntl

    with pid_file.open("rb") as fh:
        try:
            fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            return False
    return True


def private(rec: Path, data: Path) -> str:
    """POSIX: the recording is 0600 and the data folder 0700. Windows has no mode bits (the
    data folder's access comes from the user's profile folder)."""
    if WINDOWS:
        return "permissions: Windows ACLs (not checked)"
    assert mode(rec) == 0o600 and mode(data) == 0o700, "private permissions"
    return "0600, data dir 0700"


@step("version")
def check_version(exe: Path) -> str:
    out = subprocess.run(
        [str(exe), "--version"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=120,
    )
    text = (out.stdout + out.stderr).strip()
    assert out.returncode == 0, text
    if not text:  # a windowed bootloader may have no console streams; doctor checks the rest
        return "exit 0 (no console output from the windowed executable)"
    assert text.startswith("Concord "), text
    return text


@step("decoder host from the bundle")
def check_decoder_host(exe: Path) -> str:
    """The isolated decoder host (M5-A) is started as ``<exe> -m concord_decoder_sdk.host``."""
    out = subprocess.run(
        [str(exe), "-m", "concord_decoder_sdk.host", "--list"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=120,
    )
    assert out.returncode == 0, (out.stdout + out.stderr).strip()[-2000:]
    if not out.stdout.strip():  # a windowed bootloader may have no console streams
        return "exit 0 (no console output from the windowed executable)"
    listed = json.loads(out.stdout)
    return f"--list answered ({len(listed) if isinstance(listed, list) else 'object'})"


@step("doctor from the bundle")
def check_doctor(exe: Path, work: Path) -> str:
    data, port = work / "doctor-data", free_port()
    report = work / "doctor.json"
    out = run_cli(exe, ["doctor", "--json", str(report), "--no-plugins"], data, port)
    rep = json.loads(report.read_text(encoding="utf-8"))
    assert rep["format"] == "concord.support-report/1", rep.get("format")
    checks = {c["id"]: c["status"] for c in rep["checks"]}
    for cid in ("dsp", "nwb", "lsl", "zmq"):
        assert checks.get(cid) == "ok", f"{cid}: {checks.get(cid)} (bundled dependency missing?)"
    assert rep["platform"]["frozen_app"] is True
    assert out.returncode == 0, out.stdout + out.stderr
    tk = checks.get("tk", "n/a")
    return f"exit 0; {rep['summary']}; install={rep['concord']['install']}; tk={tk}"


def exercise(base: str, label: str) -> dict[str, Any]:
    """Everything a first session touches, through the REST API the console uses."""
    page = http("GET", base + "/")
    assert isinstance(page, str) and "<title>" in page and "Concord" in page, "console page"
    devices = {d["device_id"] for d in http("GET", base + "/api/v1/devices")}
    assert {"sim-a", "sim-b"} <= devices, devices
    presets = http("GET", base + "/api/v1/pipeline/presets")
    assert "spikeband_threshold" in presets, "scipy pipeline presets missing"
    assert http("GET", base + "/api/v1/datasets")["nwb_support"] is True, "pynwb missing"
    lsl = http("POST", base + "/api/v1/sources/lsl/discover", {"wait_s": 0.3})
    assert lsl["library"], "liblsl did not load"
    plugins = wait_until(
        lambda: (p := http("GET", base + "/api/v1/plugins"))["discovered_at_ns"] and p,
        120,
        "plugin discovery",
    )
    status = {p["name"]: p["status"] for p in plugins["plugins"]}
    assert status.get("bci2000") == "compatible", f"plugin host in the bundle: {status}"
    session = http("POST", base + "/api/v1/sessions", {"name": f"smoke {label}"})
    http("POST", base + "/api/v1/runtime/connect", {"device_id": "sim-a"})
    first = http("GET", base + "/api/v1/diagnostics")["counters"]["events_published"]
    wait_until(
        lambda: (
            http("GET", base + "/api/v1/diagnostics")["counters"]["events_published"] > first + 50
        ),
        20,
        "events from Simulated Profile A",
    )
    rates = {
        e["event_type"]: e["rate_hz"]
        for e in http("GET", base + "/api/v1/diagnostics")["event_types"]
    }
    rec = http("POST", base + "/api/v1/recordings/start", {"name": f"smoke-{label}"})["name"]
    time.sleep(1.5)
    return {
        "session": session["id"],
        "recording": rec,
        "frame_rate_hz": rates.get("recording.frame"),
        "plugins": status,
        "lsl": lsl["library"][:40],
    }


@step("headless launch, sources, plugin host, events, quit")
def check_headless(exe: Path, cli: Path, work: Path, label: str = "headless") -> str:
    data, port = work / f"data-{label}", free_port()
    base = f"http://127.0.0.1:{port}"
    proc = launch(exe, data, port)
    try:
        h = wait_healthy(base, proc)
        info = exercise(base, label)
        code, how = quit_app(proc, cli, data, port)
    finally:
        if proc.poll() is None:
            proc.kill()
    assert code == 0, f"exit code {code} after {how}"
    assert healthy(base) is None, "still answering after quit"
    rec = data / "recordings" / f"{info['recording']}.concord.jsonl"
    assert rec.exists() and not (data / "recordings" / f"{info['recording']}.active.json").exists()
    perms = private(rec, data)
    s = json.loads(
        (data / "sessions" / info["session"] / "session.json").read_text(encoding="utf-8")
    )
    assert s["status"] == "closed", s["status"]
    assert not (data / "concord.pid").exists(), "instance lock not released"
    return (
        f"Concord {h['version']} healthy; sim-a frames {info['frame_rate_hz']} Hz; plugins "
        f"{info['plugins']}; quit by {how}; recording closed cleanly ({perms}); session closed"
    )


@step("crash recovery (killed mid-recording, relaunch)")
def check_crash(exe: Path, cli: Path, work: Path) -> str:
    data, port = work / "data-crash", free_port()
    base = f"http://127.0.0.1:{port}"
    proc = launch(exe, data, port)
    try:
        wait_healthy(base, proc)
        http("POST", base + "/api/v1/runtime/connect", {"device_id": "sim-a"})
        name = http("POST", base + "/api/v1/recordings/start", {"name": "crash"})["name"]
        time.sleep(1.5)
        proc.kill()  # SIGKILL; TerminateProcess on Windows
        proc.wait(30)
    finally:
        if proc.poll() is None:
            proc.kill()
    proc = launch(exe, data, port)
    try:
        wait_healthy(base, proc)
        rec = next(r for r in http("GET", base + "/api/v1/recordings") if r["name"] == name)
        assert rec["complete"] is False and rec["recovery"]["valid_events"] > 0, rec
        code, how = quit_app(proc, cli, data, port)
        assert code == 0, f"exit code {code} after {how}"
    finally:
        if proc.poll() is None:
            proc.kill()
    return f"kept {rec['recovery']['valid_events']} events, marked incomplete"


@step("command program: start (background server), status, stop")
def check_cli_server(cli: Path, work: Path) -> str:
    data, port = work / "data-cli", free_port()
    base = f"http://127.0.0.1:{port}"
    started = False
    try:
        out = run_cli(cli, ["start", "--no-browser"], data, port)
        text = (out.stdout + out.stderr).strip()
        assert out.returncode == 0, f"start exited {out.returncode}: {text[-1500:]}"
        started = True
        assert healthy(base) is not None, "start returned but the server is not healthy"
        st = run_cli(cli, ["status", "--json"], data, port, timeout=60)
        status = json.loads(st.stdout)
        assert st.returncode == 0 and status["running"] is True, st.stdout + st.stderr
        http("POST", base + "/api/v1/runtime/connect", {"device_id": "sim-a"})
        name = http("POST", base + "/api/v1/recordings/start", {"name": "cli"})["name"]
        time.sleep(1.0)
        stop = run_cli(cli, ["stop"], data, port, timeout=120)
        said = (stop.stdout + stop.stderr).strip()
        assert stop.returncode == 0 and "Concord stopped" in said, said[-1500:]
        started = False
    finally:
        if started:  # do not leave a server behind on a failed check
            with contextlib.suppress(Exception):
                run_cli(cli, ["stop", "--timeout", "10"], data, port, timeout=60)
    wait_until(lambda: healthy(base) is None, 30, "the server to stop")
    rec = data / "recordings" / f"{name}.concord.jsonl"
    assert rec.exists() and not (data / "recordings" / f"{name}.active.json").exists()
    assert lock_released(data / "concord.pid"), "instance lock not released"
    return f"pid {status['pid']} started in the background; {said.splitlines()[-1]}"


@contextlib.contextmanager
def other_copy(port: int) -> Iterator[list[str]]:
    """Another copy of Concord on ``port`` (as an older build still running would be): it
    answers ``/api/v1/health`` with another version and stream protocol, and records every
    request line it receives."""
    health = {
        "status": "ok",
        "version": "0.0.0-smoke",
        "schema_version": "1.0",
        "stream_protocol": "other.stream/1",
        "simulation_enabled": True,
        "read_only": True,
        "pid": os.getpid(),
    }
    seen: list[str] = []

    class Handler(BaseHTTPRequestHandler):
        def _answer(self) -> None:
            seen.append(f"{self.command} {self.path}")
            if self.command != "GET" or self.path != "/api/v1/health":
                self.send_error(404)
                return
            body = json.dumps(health).encode()
            self.send_response(200)
            self.send_header("content-type", "application/json")
            self.send_header("content-length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        do_GET = do_POST = _answer

        def log_message(self, format: str, *args: Any) -> None:
            pass

    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield seen
    finally:
        server.shutdown()
        server.server_close()


@step("another copy on the app's address is reported, not silently opened")
def check_other_copy(exe: Path, work: Path) -> str:
    data, port = work / "data-other-copy", free_port()
    with other_copy(port) as seen:
        proc = launch(exe, data, port)
        try:
            code = proc.wait(180)
        finally:
            if proc.poll() is None:
                proc.kill()
    assert code == 3, f"exit code {code} (expected 3: another copy is running)"
    log = data / "logs" / "concord.log"
    assert log.exists() and "another copy of Concord answers at" in log.read_text(), (
        "not reported in the app's log"
    )
    assert not (data / "concord.pid").exists(), "the app took its instance lock"
    assert seen and set(seen) == {"GET /api/v1/health"}, f"sent to the other copy: {seen}"
    stderr = (work / f"launch-{port}.log").read_text(errors="replace")
    shown = "and stderr" if "Another copy of Concord is running" in stderr else "(no stderr)"
    return f"exit 3; reported in concord.log {shown}; only its health was requested"


@step("window mode (Tk status window), quit reaches the window's event loop")
def check_window(exe: Path, cli: Path, work: Path) -> str:
    data, port = work / "data-window", free_port()
    base = f"http://127.0.0.1:{port}"
    proc = launch(exe, data, port, window=True)
    try:
        wait_healthy(base, proc)
        http("POST", base + "/api/v1/runtime/connect", {"device_id": "sim-a"})
        name = http("POST", base + "/api/v1/recordings/start", {"name": "window"})["name"]
        time.sleep(1.0)
        text = (data / "logs" / "concord.log").read_text(encoding="utf-8")
        assert "Concord window open" in text, "the app did not open its window"
        assert "no window could be created" not in text and "no window toolkit" not in text
        code, how = quit_app(proc, cli, data, port)
    finally:
        if proc.poll() is None:
            proc.kill()
    assert code == 0, f"exit code {code} after {how}"
    rec = data / "recordings" / f"{name}.concord.jsonl"
    assert rec.exists() and not (data / "recordings" / f"{name}.active.json").exists()
    return f"window opened; quit by {how} stopped the server cleanly; recording closed"


@step("macOS: open the .app (double-click equivalent), quit with an Apple Event")
def check_gui(app: Path, work: Path) -> str:
    data, port = work / "data-gui", free_port()
    base = f"http://127.0.0.1:{port}"
    subprocess.run(
        [
            "open",
            "-n",
            str(app),
            "--args",
            "--no-browser",
            "--port",
            str(port),
            "--data-dir",
            str(data),
        ],
        check=True,
        timeout=60,
    )
    h = wait_healthy(base, None)
    http("POST", base + "/api/v1/runtime/connect", {"device_id": "sim-a"})
    name = http("POST", base + "/api/v1/recordings/start", {"name": "gui"})["name"]
    time.sleep(1.0)
    how = "Apple Event (quit)"
    q = subprocess.run(
        ["osascript", "-e", f'tell application id "{BUNDLE_ID}" to quit'],
        capture_output=True,
        text=True,
        timeout=60,
    )
    if q.returncode != 0:
        how = f"SIGTERM (Apple Event refused on this machine: {q.stderr.strip()[:120]})"
        subprocess.run(["pkill", "-TERM", "-f", str(app / "Contents" / "MacOS" / "Concord")])
    wait_until(lambda: healthy(base) is None, 60, "the app to quit")
    wait_until(lambda: not (data / "concord.pid").exists(), 30, "the instance lock to be released")
    rec = data / "recordings" / f"{name}.concord.jsonl"
    assert rec.exists() and not (data / "recordings" / f"{name}.active.json").exists(), (
        "recording not closed"
    )
    window = "unknown"
    log = data / "logs" / "concord.log"
    if log.exists():
        window = (
            "headless fallback"
            if "no window toolkit" in log.read_text(encoding="utf-8")
            else "Tk window"
        )
    return f"Concord {h['version']} launched via `open`; quit by {how}; recording closed; {window}"


@step("macOS: the .dmg mounts and its app runs")
def check_dmg(dmg: Path, work: Path) -> str:
    mnt = work / "mnt"
    mnt.mkdir()
    subprocess.run(
        ["hdiutil", "attach", "-nobrowse", "-readonly", "-mountpoint", str(mnt), str(dmg)],
        check=True,
        timeout=120,
    )
    try:
        app = mnt / "Concord.app"
        assert app.is_dir() and (mnt / "Applications").is_symlink(), "dmg layout"
        exe = app / "Contents" / "MacOS" / "Concord"
        detail = check_headless(exe, exe, work, label="dmg")
    finally:
        subprocess.run(["hdiutil", "detach", str(mnt)], timeout=120)
    return f"mounted read-only; {detail}"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("executable", type=Path)
    ap.add_argument(
        "--cli",
        type=Path,
        help="the program that answers concord commands (Windows: concord-cli.exe; "
        "default: EXECUTABLE)",
    )
    ap.add_argument("--app", type=Path, help="the .app bundle (macOS) for --gui")
    ap.add_argument("--gui", action="store_true")
    ap.add_argument(
        "--window",
        action="store_true",
        help="also run with the status window (needs a display: macOS, Windows, or Linux DISPLAY)",
    )
    ap.add_argument("--dmg", type=Path)
    ap.add_argument("--report", type=Path)
    ap.add_argument("--keep", action="store_true")
    args = ap.parse_args(argv)
    if args.gui and (sys.platform != "darwin" or args.app is None):
        raise SystemExit("--gui needs macOS and --app")
    exe = args.executable.resolve()
    cli = (args.cli or args.executable).resolve()
    if WINDOWS and cli == exe:
        raise SystemExit("Windows: pass --cli Concord\\concord-cli.exe (Concord.exe is windowed)")
    work = Path(tempfile.mkdtemp(prefix="concord-smoke-"))
    checks: list[Callable[[], str]] = [
        lambda: check_version(cli),
        lambda: check_decoder_host(cli),
        lambda: check_doctor(cli, work),
        lambda: check_headless(exe, cli, work),
        lambda: check_crash(exe, cli, work),
        lambda: check_cli_server(cli, work),
        lambda: check_other_copy(exe, work),
    ]
    if args.window:
        checks.append(lambda: check_window(exe, cli, work))
    if args.gui:
        checks.append(lambda: check_gui(args.app, work))
    if args.dmg:
        checks.append(lambda: check_dmg(args.dmg, work))
    ok = False
    try:
        # every check runs even if an earlier one failed: one CI run reports all of them
        failures = (AssertionError, OSError, subprocess.SubprocessError, ValueError, KeyError)
        for check in checks:
            with contextlib.suppress(*failures):  # recorded in STEPS by @step
                check()
        ok = len(STEPS) >= len(checks) and all(s["ok"] for s in STEPS)
    finally:
        report = {
            "ok": ok,
            "platform": sys.platform,
            "executable": str(args.executable),
            "cli": str(cli),
            "steps": STEPS,
        }
        if args.report:
            args.report.write_text(json.dumps(report, indent=1) + "\n", encoding="utf-8")
        if not ok:
            logs = [*sorted(work.glob("launch-*.log")), *sorted(work.glob("data-*/logs/*.log"))]
            for log in logs:
                print(
                    f"--- {log.relative_to(work)} (tail)\n"
                    + "\n".join(
                        log.read_text(errors="replace", encoding="utf-8").splitlines()[-40:]
                    )
                )
        if not args.keep:
            shutil.rmtree(work, ignore_errors=True)
    print("SMOKE TEST PASSED" if ok else "SMOKE TEST FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
