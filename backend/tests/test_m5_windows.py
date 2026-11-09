"""Windows support (0.3.1): the Windows branches of Concord's platform code, exercised on every
platform by substituting what only Windows has (kernel32, msvcrt, ``sys.platform``), plus the
platform-neutral rules added for Windows (file names, zip members, line endings).

On a real Windows machine the same paths run for real in CI (job backend-windows: this suite;
job package-windows: the packaged Concord.exe / concord-cli.exe through packaging/smoke_test.py).
"""

from __future__ import annotations

import io
import json
import os
import signal
import sys
import threading
from pathlib import Path
from typing import Any

import pytest

from concord import config, launcher, oscompat
from concord.adapters.replay.format import RecordingFormatError, recording_path
from concord.adapters.simulated import profile_a
from concord.runtime import Recorder
from concord.runtime.recorder import RecorderError
from concord.runtime.sessions import SessionError, SessionManager
from concord.server import serve
from concord.server.settings import Settings

from .helpers import valid_event

# --------------------------------------------------------------------------- processes


class FakeKernel32:
    """OpenProcess / GetExitCodeProcess / CloseHandle for one pretend process table."""

    def __init__(self, table: dict[int, int | str]) -> None:
        self.table = table  # pid -> exit code (259 = still running) | "denied"
        self.closed: list[int] = []

    def OpenProcess(self, access: int, inherit: int, pid: int) -> int | None:
        entry = self.table.get(pid)
        if entry is None or entry == "denied":
            FakeKernel32.last_error = 5 if entry == "denied" else 87
            return None
        return 1000 + pid

    def GetExitCodeProcess(self, handle: int, code: Any) -> int:
        code._obj.value = self.table[handle - 1000]
        return 1

    def CloseHandle(self, handle: int) -> int:
        self.closed.append(handle)
        return 1

    last_error = 0


@pytest.fixture
def windows(monkeypatch: pytest.MonkeyPatch) -> None:
    """Concord's Windows code paths (``oscompat.is_windows`` everywhere it is imported)."""
    monkeypatch.setattr(oscompat, "is_windows", lambda: True)
    monkeypatch.setattr(launcher, "is_windows", lambda: True)


def test_windows_liveness_never_uses_os_kill(
    monkeypatch: pytest.MonkeyPatch, windows: None
) -> None:
    """Regression: ``os.kill(pid, 0)`` was the liveness probe everywhere; on Windows os.kill
    terminates the process (or sends Ctrl-C for signal 0), so probing killed the server."""
    k = FakeKernel32({100: 259, 101: 0, 102: "denied"})
    monkeypatch.setattr(oscompat, "_kernel32", lambda: k)
    monkeypatch.setattr(oscompat, "_last_error", lambda: FakeKernel32.last_error)

    def forbidden(*_: object) -> None:
        raise AssertionError("os.kill must not be called to probe a process on Windows")

    monkeypatch.setattr(os, "kill", forbidden)
    assert oscompat.pid_alive(100) is True  # STILL_ACTIVE
    assert oscompat.pid_alive(101) is False  # exited, handle still open somewhere
    assert oscompat.pid_alive(102) is True  # exists, another user's
    assert oscompat.pid_alive(103) is False  # no such process
    assert oscompat.pid_alive(0) is False and oscompat.pid_alive(-1) is False
    assert k.closed == [1100, 1101]


def test_windows_force_kill_and_terminate_use_terminateprocess(
    monkeypatch: pytest.MonkeyPatch, windows: None
) -> None:
    """signal.SIGKILL does not exist on Windows (AttributeError); os.kill with any other
    number is TerminateProcess there."""
    sent: list[tuple[int, int]] = []
    monkeypatch.setattr(os, "kill", lambda pid, sig: sent.append((pid, sig)))
    oscompat.force_kill(42)
    oscompat.terminate(43)
    assert sent == [(42, int(signal.SIGTERM)), (43, int(signal.SIGTERM))]
    # never Ctrl-C / Ctrl-Break (0 and 1 are console events on Windows, not TerminateProcess)
    assert all(sig not in (0, 1) for _, sig in sent)


def test_posix_liveness_and_kill(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(oscompat, "is_windows", lambda: False)
    if os.name != "posix":
        pytest.skip("POSIX signals")
    assert oscompat.pid_alive(os.getpid())
    sent: list[tuple[int, int]] = []
    monkeypatch.setattr(os, "kill", lambda pid, sig: sent.append((pid, sig)))
    oscompat.force_kill(7)
    oscompat.terminate(8)
    assert sent == [(7, signal.SIGKILL), (8, signal.SIGTERM)]


def test_child_process_flags(monkeypatch: pytest.MonkeyPatch) -> None:
    """Windows: helper processes and the background server get their own process group and
    no console window (the windowed desktop app has none to share; DETACHED_PROCESS would make
    each console child of the server open a new window)."""
    monkeypatch.setattr(oscompat, "is_windows", lambda: True)
    flags = oscompat.CREATE_NEW_PROCESS_GROUP | oscompat.CREATE_NO_WINDOW
    assert oscompat.child_kwargs() == {"creationflags": flags}
    assert oscompat.background_kwargs() == {"creationflags": flags}
    monkeypatch.setattr(oscompat, "is_windows", lambda: False)
    assert oscompat.child_kwargs() == {"start_new_session": True}
    assert oscompat.background_kwargs() == {"start_new_session": True}


def test_helper_programs_in_the_windows_app(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, windows: None
) -> None:
    """In the Windows app sys.executable is the windowed Concord.exe; helper processes (plugin
    and decoder hosts, `concord start`'s server) run with the console concord-cli.exe beside
    it, and messages name that program for commands."""
    app = tmp_path / "Concord" / "Concord.exe"
    app.parent.mkdir()
    app.write_bytes(b"")
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(app))
    assert oscompat.helper_executable() == str(app)  # no console program: the app itself
    (app.parent / "concord-cli.exe").write_bytes(b"")
    assert oscompat.helper_executable() == str(app.parent / "concord-cli.exe")
    assert launcher.serve_command() == [str(app.parent / "concord-cli.exe"), "serve"]
    assert config.command_hint("stop") == f"{app.parent / 'concord-cli.exe'} stop"
    monkeypatch.setattr(oscompat, "is_windows", lambda: False)
    assert oscompat.helper_executable() == str(app)


def test_command_hint_outside_the_app(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delattr(sys, "frozen", raising=False)
    assert config.command_hint("stop") == "concord stop"


# --------------------------------------------------------------------------- file locks


class FakeMsvcrt:
    LK_UNLCK, LK_NBLCK = 0, 2

    def __init__(self) -> None:
        self.held: dict[str, int] = {}  # file -> fd holding the byte at LOCK_OFFSET
        self.calls: list[tuple[int, int, int]] = []

    def locking(self, fd: int, mode: int, nbytes: int) -> None:
        pos = os.lseek(fd, 0, os.SEEK_CUR)
        self.calls.append((mode, pos, nbytes))
        key = os.readlink(f"/proc/self/fd/{fd}") if Path("/proc/self/fd").exists() else str(fd)
        if mode == self.LK_NBLCK:
            if key in self.held and self.held[key] != fd:
                raise OSError(36, "Resource deadlock avoided")  # what msvcrt raises
            self.held[key] = fd
        elif self.held.get(key) == fd:
            del self.held[key]


@pytest.mark.skipif(not Path("/proc/self/fd").exists(), reason="the fake needs /proc")
def test_windows_lock_is_beyond_the_content_and_keeps_the_position(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, windows: None
) -> None:
    """Windows locks are mandatory: locking the pid file's content would stop `concord status`
    from reading it. The lock is one byte at LOCK_OFFSET; the file position is unchanged."""
    m = FakeMsvcrt()
    monkeypatch.setattr(oscompat, "_msvcrt", lambda: m)
    path = tmp_path / "concord.pid"
    fd = os.open(path, os.O_RDWR | os.O_CREAT)
    try:
        os.write(fd, b"abc")
        assert oscompat.try_lock(fd)
        assert os.lseek(fd, 0, os.SEEK_CUR) == 3
        assert m.calls == [(m.LK_NBLCK, oscompat.LOCK_OFFSET, 1)]
        assert oscompat.is_locked(path) is True  # another handle: refused -> held
        oscompat.unlock(fd)
        assert oscompat.is_locked(path) is False
        assert m.calls[-1] == (m.LK_UNLCK, oscompat.LOCK_OFFSET, 1)
    finally:
        os.close(fd)
    assert oscompat.is_locked(tmp_path / "missing") is None


def test_instance_lock_released_in_windows_order(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Windows cannot delete an open file: the pid file is closed, then deleted (it stayed
    behind before, and every later `concord status` had to rely on the lock)."""
    monkeypatch.setattr(serve, "unlink_before_close", lambda: False)
    s = Settings(data_dir=tmp_path / "data", port=8999)
    lock = serve.acquire_instance(s)
    closed: list[int] = []
    real_close = os.close

    def close(fd: int) -> None:
        assert s.pid_file.exists(), "deleted before it was closed"
        closed.append(fd)
        real_close(fd)

    monkeypatch.setattr(os, "close", close)
    lock.release()
    assert closed == [lock.fd] and not s.pid_file.exists()


def test_clean_stop_removes_the_marker_in_windows_order(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Regression (Windows): the recording marker was deleted while still open, which fails
    there; the next start then "recovered" a cleanly closed recording as interrupted."""
    from concord.contracts import parse_envelope
    from concord.runtime import recorder as recorder_module

    monkeypatch.setattr(recorder_module, "unlink_before_close", lambda: False)
    rec = Recorder(tmp_path / "rec")
    rec.start(profile_a.descriptor(), "w1")
    env = parse_envelope(valid_event("telemetry.sample", device_id="sim-a"))
    rec.on_event(env, env.model_dump_json())
    rec.stop()
    assert not (tmp_path / "rec" / "w1.active.json").exists()
    assert Recorder(tmp_path / "rec").recover() == []
    assert rec.list()[0].complete


# --------------------------------------------------------------------------- stopping


def test_stop_request_is_watched_and_consumed(tmp_path: Path) -> None:
    pid_file = tmp_path / "concord.pid"
    stopped = threading.Event()
    watcher = serve.StopWatcher(pid_file, stopped.set, interval_s=0.02).start()
    try:
        serve.request_stop(pid_file, os.getpid() + 1)  # another process: stale, ignored
        assert not stopped.wait(0.3)
        assert not serve.stop_request_path(pid_file).exists()  # and removed
        serve.request_stop(pid_file, os.getpid())
        assert stopped.wait(5)
        assert not serve.stop_request_path(pid_file).exists()
    finally:
        watcher.close()


def test_acquiring_the_instance_clears_an_old_stop_request(tmp_path: Path) -> None:
    s = Settings(data_dir=tmp_path / "data", port=8999)
    s.data_dir.mkdir(parents=True)
    serve.request_stop(s.pid_file, os.getpid())  # left by a server that exited meanwhile
    lock = serve.acquire_instance(s)
    try:
        assert not serve.take_stop_request(s.pid_file)  # the new server is not stopped by it
    finally:
        lock.release()


def test_windows_stop_asks_through_the_data_folder(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """`concord stop` on Windows: safe stop over HTTP, then a stop request the server acts on;
    TerminateProcess only for a server it cannot ask (no pid file of its own)."""
    s = Settings(data_dir=tmp_path / "data", port=8999)
    lock = serve.acquire_instance(s)
    ended: list[int] = []
    monkeypatch.setattr(launcher, "is_windows", lambda: True)  # the lock itself: this OS's
    monkeypatch.setattr(launcher, "terminate", ended.append)
    try:
        assert launcher._ask_to_exit(os.getpid(), s.pid_file) == "stop request"
        assert serve.take_stop_request(s.pid_file)
        assert ended == []
        assert launcher._ask_to_exit(os.getpid() + 1, s.pid_file) == "terminated"
        assert launcher._ask_to_exit(os.getpid(), None) == "terminated"
        assert ended == [os.getpid() + 1, os.getpid()]
    finally:
        lock.release()


def test_desktop_quits_on_ctrl_break_and_shows_its_window_on_windows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from concord import desktop

    monkeypatch.setattr(signal, "SIGBREAK", 21, raising=False)
    assert 21 in desktop.quit_signals()
    pytest.importorskip("tkinter")
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.delenv("DISPLAY", raising=False)
    # regression: the window was only offered on macOS or with an X11 DISPLAY
    assert desktop.has_window_toolkit()


# --------------------------------------------------------------------------- folders and files


def test_windows_data_and_config_folders(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "Local"))
    monkeypatch.delenv(config.CONFIG_ENV, raising=False)
    monkeypatch.setattr(config, "source_checkout", lambda: None)
    assert config.user_dir() == tmp_path / "Local" / "Concord"
    assert config.default_data_dir() == tmp_path / "Local" / "Concord" / "data"
    assert config.default_config_path() == tmp_path / "Local" / "Concord" / "config.toml"
    monkeypatch.delenv("LOCALAPPDATA")
    assert config.user_dir() == Path.home() / "AppData" / "Local" / "Concord"


@pytest.mark.parametrize("name", ["con", "nul", "aux", "prn", "com1", "lpt9"])
def test_windows_device_names_are_not_recording_names(tmp_path: Path, name: str) -> None:
    """``con.concord.jsonl`` is the console on Windows, not a file; such names are refused on
    every platform so recordings can move between computers."""
    with pytest.raises(RecordingFormatError):
        recording_path(tmp_path, name)
    assert recording_path(tmp_path, f"{name}-1").name == f"{name}-1.concord.jsonl"


@pytest.mark.parametrize(
    "member",
    [
        "..\\..\\evil.json",
        "C:evil.json",
        "D:/x/evil.json",
        "models\\..\\..\\x",
        "con.json",
        "a/nul",
    ],
)
def test_bundle_members_that_escape_on_windows_are_refused(member: str) -> None:
    """Regression (Windows): POSIX path rules accepted "..\\x" and "C:x", which on Windows
    climb out of the extraction folder or name another drive."""
    from concord.reproduce import _safe_member

    assert not _safe_member(member)
    assert _safe_member("models/m-1.json") and _safe_member("session.json")


def test_files_are_opened_in_binary_mode(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Regression (Windows): os.open defaults to text mode there, which writes every "\\n" as
    "\\r\\n" (corrupting export zips and recording byte counts). O_BINARY is always added."""
    from concord import security

    seen: list[int] = []
    real_open = os.open
    monkeypatch.setattr(security, "O_BINARY", 0x8000)

    def spy(path: Any, flags: int, mode: int = 0o777) -> int:
        seen.append(flags)
        return real_open(path, flags & ~0x8000, mode)

    monkeypatch.setattr(os, "open", spy)
    security.write_private(tmp_path / "x.json", "a\nb\n")
    assert seen and all(f & 0x8000 for f in seen)


def test_recordings_and_session_logs_end_lines_with_lf(tmp_path: Path) -> None:
    """The same bytes on every platform: a recording made on Windows replays on Linux with the
    same sizes and hashes (TextIOWrapper would otherwise write "\\r\\n" there)."""
    from concord.contracts import parse_envelope

    rec = Recorder(tmp_path / "rec")
    rec.start(profile_a.descriptor(), "lf")
    env = parse_envelope(valid_event("telemetry.sample", device_id="sim-a"))
    rec.on_event(env, env.model_dump_json())
    rec.stop()
    raw = (tmp_path / "rec" / "lf.concord.jsonl").read_bytes()
    assert b"\r" not in raw and raw.count(b"\n") == 2
    sm = SessionManager(tmp_path / "sessions")
    info = sm.create("lf")
    sm.record("note", text="x")
    assert b"\r" not in (tmp_path / "sessions" / info.id / "log.jsonl").read_bytes()


def test_open_files_block_deletion_with_a_clear_message(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Windows cannot delete a file another program (or a replay) has open: the API answers
    with a reason (409) instead of an internal error, and nothing is half-deleted."""
    rec = Recorder(tmp_path / "rec")
    rec.start(profile_a.descriptor(), "busy")
    rec.stop()
    real_unlink = Path.unlink

    def unlink(self: Path, missing_ok: bool = False) -> None:
        if self.name.endswith(".concord.jsonl"):
            raise PermissionError(13, "The process cannot access the file", str(self))
        real_unlink(self, missing_ok=missing_ok)

    monkeypatch.setattr(Path, "unlink", unlink)
    with pytest.raises(RecorderError, match="is open"):
        rec.delete("busy")
    assert (tmp_path / "rec" / "busy.concord.jsonl").exists()

    sm = SessionManager(tmp_path / "sessions")
    info = sm.create("held")
    sm.close()

    def rmtree(path: Any, *a: Any, **k: Any) -> None:
        raise PermissionError(13, "in use", str(Path(path) / "log.jsonl"))

    monkeypatch.setattr("concord.runtime.sessions.shutil.rmtree", rmtree)
    with pytest.raises(SessionError, match="open in another program"):
        sm.delete(info.id)


def test_retrying_replace_on_windows(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """os.replace fails on Windows while another program briefly has the target open (a virus
    scanner, a reader); it is retried instead of failing the save."""
    monkeypatch.setattr(oscompat, "is_windows", lambda: True)
    src, dst = tmp_path / "a", tmp_path / "b"
    src.write_text("new", encoding="utf-8")
    dst.write_text("old", encoding="utf-8")
    real = os.replace
    failures = [PermissionError(13, "in use"), PermissionError(13, "in use")]

    def flaky(a: Any, b: Any) -> None:
        if failures:
            raise failures.pop()
        real(a, b)

    monkeypatch.setattr(os, "replace", flaky)
    oscompat.replace(src, dst, delay_s=0.001)
    assert dst.read_text(encoding="utf-8") == "new"
    monkeypatch.setattr(oscompat, "is_windows", lambda: False)
    failures.append(PermissionError(13, "denied"))
    with pytest.raises(PermissionError):  # POSIX: a real permission problem, not retried
        oscompat.replace(dst, src)


def test_console_output_never_fails_on_a_narrow_code_page() -> None:
    """A redirected Windows console encodes with the ANSI code page (cp1252), which has no
    "→"; such characters are printed escaped instead of raising UnicodeEncodeError."""
    from concord import safe_console_streams

    buf = io.TextIOWrapper(io.BytesIO(), encoding="cp1252")
    saved = sys.stdout
    sys.stdout = buf
    try:
        safe_console_streams()
        print("decoder → cursor")
        buf.flush()
    finally:
        sys.stdout = saved
    assert b"decoder \\u2192 cursor" in buf.buffer.getvalue()  # type: ignore[attr-defined]


def test_doctor_on_windows_reports_permissions_as_not_checked(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Windows has no mode bits: the support report must not print "mode 777" for a private
    folder or tell the user to chmod; it says the permissions are not checked, and why."""
    from concord import doctor

    monkeypatch.setattr(doctor, "posix_permissions", lambda: False)
    (tmp_path / "data").mkdir()
    cfg = tmp_path / "config.toml"
    cfg.write_text("[server]\nport = 8001\n", encoding="utf-8")
    report = doctor.run(data_dir=tmp_path / "data", port=1, config_path=cfg, discover_plugins=False)
    checks = {c["id"]: c for c in report["checks"]}
    assert checks["permissions"]["status"] == "info"
    assert "not checked on Windows" in checks["permissions"]["detail"]
    assert checks["data_dir"]["status"] == "ok" and "mode" not in checks["data_dir"]["detail"]
    assert checks["config"]["status"] == "ok" and "mode" not in checks["config"]["detail"]
    assert "chmod" not in json.dumps(report)


def test_plugin_hosts_write_utf8(monkeypatch: pytest.MonkeyPatch) -> None:
    from concord.adapters.plugin.host_client import host_env

    monkeypatch.delenv("PYTHONIOENCODING", raising=False)
    assert host_env()["PYTHONIOENCODING"] == "utf-8"


def test_support_report_paths_from_windows_are_redacted() -> None:
    from concord.security import redact

    home = Path("/home/runner")
    text = json.dumps({"log": r"open C:\Users\dana\x failed", "dir": r"C:\Users\dana\Concord"})
    out = redact(text, home=home)
    assert "dana" not in out and r"C:\\Users\\<user>" in out


def test_windows_command_hint_with_spaces_uses_the_powershell_call_operator(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A quoted path followed by an argument is a parse error in PowerShell; with spaces in the
    path the hint starts with the call operator `&` (regression)."""
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(oscompat, "is_windows", lambda: True)
    monkeypatch.setattr(sys, "executable", "C:/My Apps/Concord/Concord.exe")
    assert config.command_hint("stop") == '& "C:/My Apps/Concord/concord-cli.exe" stop'
    monkeypatch.setattr(sys, "executable", "C:/Users/me/Downloads/Concord/Concord.exe")
    assert config.command_hint("stop") == "C:/Users/me/Downloads/Concord/concord-cli.exe stop"


def test_python_m_tools_are_protected_on_windows_too(tmp_path: Path) -> None:
    """`python -m concord.decoding.evaluate_falcon` printed "τ" and crashed on the Windows CI
    runner (cp1252): the guard now runs when the package is imported on Windows, so every
    `python -m concord.…` tool is covered, not only the `concord` command (regression)."""
    import subprocess

    code = (
        "import os, sys, io\n"
        "os.name = 'nt'\n"  # pretend Windows before the package is imported
        "sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='cp1252')\n"
        "import concord\n"
        "print('time constant \u03c4')\n"
    )
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, timeout=60)
    assert out.returncode == 0, out.stderr
    assert b"time constant \\u03c4" in out.stdout
