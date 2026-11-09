"""What differs between POSIX (macOS, Linux) and Windows, in one place. Stdlib only.

* ``pid_alive``: whether a process runs. ``os.kill(pid, 0)`` is the POSIX probe, but on
  Windows ``os.kill`` *ends* the process (TerminateProcess) or sends it Ctrl-C, so it must never
  be used as a probe there; Windows asks the kernel (OpenProcess + GetExitCodeProcess).
* ``force_kill``: end a process at once (SIGKILL; TerminateProcess on Windows).
* ``try_lock`` / ``unlock`` / ``is_locked``: an exclusive lock on an open file that the OS
  releases when its holder dies, so a stale pid file or recording marker is recognised as
  stale. POSIX: ``flock``. Windows: a byte-range lock at ``LOCK_OFFSET``, far beyond the end of
  the file, because Windows locks are mandatory: locking the content would stop other
  processes from reading it.
* ``O_BINARY``: add to every ``os.open``. On Windows ``os.open`` opens in *text* mode, where
  every ``\\n`` written becomes ``\\r\\n`` (corrupting zip files and byte counts).
* ``background_kwargs`` / ``child_kwargs``: ``subprocess`` arguments for the detached server
  of ``concord start`` and for helper processes (source-plugin and decoder hosts): their own
  session or process group (Ctrl-C in a terminal does not reach them) and, on Windows, no
  console window.
* ``helper_executable``: the program helper processes run with. In the Windows desktop app
  ``sys.executable`` is the windowed ``Concord.exe``; helpers use the console program next to
  it (``concord-cli.exe``), whose standard streams always work.
* ``cli_command``: how to type a ``concord`` command for this installation (messages and docs).
"""

from __future__ import annotations

import contextlib
import ctypes
import os
import signal
import sys
import time
from pathlib import Path
from typing import Any

O_BINARY: int = getattr(os, "O_BINARY", 0)
LOCK_OFFSET = 1 << 30  # Windows: the locked byte (files Concord locks are tiny)
CLI_EXE = "concord-cli.exe"  # the console program of the Windows desktop app
APP_EXE = "Concord.exe"  # the windowed program of the Windows desktop app

# Windows constants (subprocess has them only on Windows)
CREATE_NEW_PROCESS_GROUP = 0x00000200
CREATE_NO_WINDOW = 0x08000000
_PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
_STILL_ACTIVE = 259
_ERROR_ACCESS_DENIED = 5


def is_windows() -> bool:
    return os.name == "nt"


# --------------------------------------------------------------------------- processes


def _kernel32() -> Any:  # pragma: no cover - Windows only (tests substitute a fake)
    k = getattr(ctypes, "WinDLL")("kernel32", use_last_error=True)  # noqa: B009 - Windows only
    k.OpenProcess.argtypes = (ctypes.c_uint32, ctypes.c_int, ctypes.c_uint32)
    k.OpenProcess.restype = ctypes.c_void_p
    k.GetExitCodeProcess.argtypes = (ctypes.c_void_p, ctypes.POINTER(ctypes.c_uint32))
    k.GetExitCodeProcess.restype = ctypes.c_int
    k.CloseHandle.argtypes = (ctypes.c_void_p,)
    k.CloseHandle.restype = ctypes.c_int
    return k


def _last_error() -> int:  # pragma: no cover - Windows only
    get: Any = getattr(ctypes, "get_last_error", None)
    return int(get()) if get is not None else 0


def _windows_pid_alive(pid: int) -> bool:
    k = _kernel32()
    handle = k.OpenProcess(_PROCESS_QUERY_LIMITED_INFORMATION, 0, pid)
    if not handle:
        # another user's process (or a protected one) exists; anything else: no such process
        return _last_error() == _ERROR_ACCESS_DENIED
    try:
        code = ctypes.c_uint32()
        if not k.GetExitCodeProcess(handle, ctypes.byref(code)):
            return True
        return code.value == _STILL_ACTIVE
    finally:
        k.CloseHandle(handle)


def pid_alive(pid: int, *, reap: bool = False) -> bool:
    """Whether process ``pid`` runs. ``reap``: a zombie child of this process counts as gone."""
    if pid <= 0:
        return False
    if is_windows():
        return _windows_pid_alive(pid)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True  # it exists, it is another user's
    except OSError:
        return False
    if reap:
        with contextlib.suppress(ChildProcessError, OSError):
            done, _ = os.waitpid(pid, os.WNOHANG)
            if done == pid:
                return False
    return True


def terminate(pid: int) -> None:
    """POSIX: SIGTERM (a graceful stop). Windows has no such signal: ``force_kill``."""
    if is_windows():
        force_kill(pid)
    else:
        os.kill(pid, signal.SIGTERM)


def force_kill(pid: int) -> None:
    """End ``pid`` at once: SIGKILL; on Windows TerminateProcess (what os.kill does there)."""
    if is_windows():
        os.kill(pid, int(signal.SIGTERM))  # Windows: TerminateProcess(pid, exit code 15)
    else:
        os.kill(pid, getattr(signal, "SIGKILL", signal.SIGTERM))


# --------------------------------------------------------------------------- file locks


def _msvcrt() -> Any:  # pragma: no cover - Windows only (tests substitute a fake)
    import msvcrt

    return msvcrt


def _fcntl() -> Any:
    import fcntl

    return fcntl


def try_lock(fd: int, *, shared: bool = False) -> bool:
    """Lock the open file ``fd`` without waiting; False if another holder has it.

    ``shared`` (POSIX probes) lets two probers succeed at once; Windows has exclusive locks
    only. The file position is left where it was."""
    if is_windows():
        m = _msvcrt()
        pos = os.lseek(fd, 0, os.SEEK_CUR)
        os.lseek(fd, LOCK_OFFSET, os.SEEK_SET)
        try:
            m.locking(fd, m.LK_NBLCK, 1)
        except OSError:
            return False
        finally:
            os.lseek(fd, pos, os.SEEK_SET)
        return True
    f = _fcntl()
    try:
        f.flock(fd, (f.LOCK_SH if shared else f.LOCK_EX) | f.LOCK_NB)
    except OSError:
        return False
    return True


def unlock(fd: int) -> None:
    """Release ``try_lock`` (closing the file releases it too)."""
    if is_windows():
        m = _msvcrt()
        pos = os.lseek(fd, 0, os.SEEK_CUR)
        os.lseek(fd, LOCK_OFFSET, os.SEEK_SET)
        try:
            with contextlib.suppress(OSError):
                m.locking(fd, m.LK_UNLCK, 1)
        finally:
            os.lseek(fd, pos, os.SEEK_SET)
        return
    f = _fcntl()
    with contextlib.suppress(OSError):
        f.flock(fd, f.LOCK_UN)


def is_locked(path: Path) -> bool | None:
    """Whether a live process holds ``try_lock`` on ``path``; None if it cannot be opened."""
    try:
        fd = os.open(path, os.O_RDONLY | O_BINARY)
    except OSError:
        return None
    try:
        if try_lock(fd, shared=True):
            unlock(fd)
            return False
        return True
    finally:
        os.close(fd)


def replace(src: Path, dst: Path, *, attempts: int = 20, delay_s: float = 0.05) -> None:
    """``os.replace`` (atomic). On Windows it fails while another program has ``dst`` open
    (a virus scanner, a reader of the file); that is retried for up to ~1 s."""
    for attempt in range(attempts):
        try:
            os.replace(src, dst)
            return
        except PermissionError:
            if not is_windows() or attempt == attempts - 1:
                raise
            time.sleep(delay_s)


def unlink_before_close() -> bool:
    """Order of releasing a locked file that is deleted: POSIX deletes it while still holding
    the lock (no other process can see it unlocked), Windows cannot delete an open file."""
    return not is_windows()


# --------------------------------------------------------------------------- child processes


def background_kwargs() -> dict[str, Any]:
    """``subprocess.Popen`` arguments for the detached server of ``concord start``."""
    if is_windows():
        # its own (hidden) console and process group: closing or Ctrl-C in the terminal that
        # started it does not stop it, and no console window appears
        return {"creationflags": CREATE_NEW_PROCESS_GROUP | CREATE_NO_WINDOW}
    return {"start_new_session": True}  # not killed by Ctrl-C in this terminal


def child_kwargs() -> dict[str, Any]:
    """``subprocess`` / ``asyncio.create_subprocess_exec`` arguments for helper processes
    (source-plugin and decoder hosts): a signal to the runtime's process group spares them,
    and on Windows they never open a console window (the desktop app has none)."""
    if is_windows():
        return {"creationflags": CREATE_NEW_PROCESS_GROUP | CREATE_NO_WINDOW}
    return {"start_new_session": True}


def frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def helper_executable() -> str:
    """The program helper processes (``-m concord_adapter_sdk.host`` …) and ``concord serve``
    run with: ``sys.executable``, except in the Windows desktop app, where that is the windowed
    ``Concord.exe`` and the console ``concord-cli.exe`` beside it is used instead."""
    exe = sys.executable
    if frozen() and is_windows():
        cli = Path(exe).with_name(CLI_EXE)
        if cli.is_file():
            return str(cli)
    return exe


def cli_command() -> str:
    """How the operator types a ``concord`` command for this installation."""
    if frozen():
        exe = Path(sys.executable)
        if is_windows():
            cli = str(exe.with_name(CLI_EXE))
            # PowerShell runs a quoted path only after the call operator: & "C:\My Apps\…" stop
            return f'& "{cli}"' if " " in cli else cli
        return f'"{exe}"' if " " in str(exe) else str(exe)
    return "concord"
