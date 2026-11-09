"""Milestone 5 (D): the desktop app's status window. Every way to quit — the "Stop and quit"
button, closing the window, the macOS Quit command (Cmd-Q / Dock, ``::tk::mac::Quit``),
SIGTERM and a stop request (what `concord stop` sends on Windows) — performs a safe stop and
stops the server. Needs Tk and a display (macOS and Windows always have one; Linux: e.g.
xvfb-run); skipped otherwise. The packaged app is checked by packaging/smoke_test.py."""

from __future__ import annotations

import os
import signal
import sys
import threading
from pathlib import Path
from typing import Any

import httpx
import pytest

tk = pytest.importorskip("tkinter")
# os.uname() does not exist on Windows
if not os.environ.get("DISPLAY") and sys.platform not in ("darwin", "win32"):
    pytest.skip("no display (run under xvfb-run)", allow_module_level=True)

from concord.desktop import run_window, start_server_thread  # noqa: E402
from concord.server.serve import StopWatcher, request_stop  # noqa: E402

from .conftest import free_port, make_settings  # noqa: E402


def _find(widget: Any, text: str) -> Any:
    for child in widget.winfo_children():
        try:
            if child.cget("text") == text:
                return child
        except tk.TclError:
            pass
        found = _find(child, text)
        if found is not None:
            return found
    return None


QUITS = {
    "button": lambda root: _find(root, "Stop and quit").invoke(),
    "close_window": lambda root: root.tk.call(root.protocol("WM_DELETE_WINDOW")),
    "mac_quit_command": lambda root: root.tk.call("::tk::mac::Quit"),
}


SIGTERM_SIGNAL = pytest.param(
    "sigterm_signal",
    # Windows: os.kill(own pid, SIGTERM) is TerminateProcess, it would end the test run
    marks=pytest.mark.skipif(sys.platform == "win32", reason="no SIGTERM delivery on Windows"),
)


@pytest.mark.parametrize("how", [*QUITS, "sigterm_event", SIGTERM_SIGNAL, "stop_request"])
def test_every_quit_path_stops_safely(tmp_path: Path, how: str) -> None:
    port = free_port()
    settings = make_settings(tmp_path, port=port)
    srv = start_server_thread(settings)
    assert srv.wait_ready(30)
    base = f"http://127.0.0.1:{port}"
    httpx.post(base + "/api/v1/runtime/connect", json={"device_id": "sim-a"}).raise_for_status()
    httpx.post(base + "/api/v1/recordings/start", json={"name": "win"}).raise_for_status()
    stop = threading.Event()
    opened: list[int] = []

    watcher = StopWatcher(settings.pid_file, stop.set, interval_s=0.05).start()

    def ready(root: Any) -> None:
        assert _find(root, f"{base}") is not None  # the window shows where the console is
        if how == "stop_request":  # `concord stop` on Windows; desktop.main watches for it
            root.after(400, lambda: request_stop(settings.pid_file, os.getpid()))
        elif how == "sigterm_event":
            root.after(400, stop.set)  # what the SIGTERM handler does
        elif how == "sigterm_signal":  # a real SIGTERM, after Tk is initialized (macOS CI)
            root.after(400, lambda: os.kill(os.getpid(), signal.SIGTERM))
        else:
            root.after(400, lambda: QUITS[how](root))

    before = signal.getsignal(signal.SIGTERM)
    try:
        code = run_window(srv, base, stop, lambda: opened.append(1), on_ready=ready)
    finally:
        watcher.close()
    assert code == 0 and not srv.alive
    assert signal.getsignal(signal.SIGTERM) is before  # the window restores the handlers
    rec = tmp_path / "data" / "recordings"
    assert (rec / "win.concord.jsonl").exists() and not (rec / "win.active.json").exists()
    with pytest.raises(httpx.HTTPError):
        httpx.get(base + "/api/v1/health", timeout=0.5)
