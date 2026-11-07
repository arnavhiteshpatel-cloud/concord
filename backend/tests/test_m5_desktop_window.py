"""Milestone 5 (D): the desktop app's status window. Every way to quit — the "Stop and quit"
button, closing the window, the macOS Quit command (Cmd-Q / Dock, ``::tk::mac::Quit``) and
SIGTERM — performs a safe stop and stops the server. Needs Tk and a display (e.g. xvfb-run);
skipped otherwise. The packaged app is checked by packaging/smoke_test.py."""

from __future__ import annotations

import os
import threading
from pathlib import Path
from typing import Any

import httpx
import pytest

tk = pytest.importorskip("tkinter")
if not os.environ.get("DISPLAY") and os.uname().sysname != "Darwin":
    pytest.skip("no display (run under xvfb-run)", allow_module_level=True)

from brainos.desktop import run_window, start_server_thread  # noqa: E402

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


@pytest.mark.parametrize("how", [*QUITS, "sigterm_event"])
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

    def ready(root: Any) -> None:
        assert _find(root, f"{base}") is not None  # the window shows where the console is
        if how == "sigterm_event":
            root.after(400, stop.set)  # what the SIGTERM handler does
        else:
            root.after(400, lambda: QUITS[how](root))

    code = run_window(srv, base, stop, lambda: opened.append(1), on_ready=ready)
    assert code == 0 and not srv.alive
    rec = tmp_path / "data" / "recordings"
    assert (rec / "win.brainos.jsonl").exists() and not (rec / "win.active.json").exists()
    with pytest.raises(httpx.HTTPError):
        httpx.get(base + "/api/v1/health", timeout=0.5)
