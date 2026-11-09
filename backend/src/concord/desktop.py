"""The desktop app (Concord.app): start the server, open the console, stop cleanly on quit.

The server runs in a background thread of this process; the main thread shows a small
status window (Tk) because macOS delivers "Quit" (Cmd-Q, Dock menu, logout) to the app's main
event loop. Quitting performs a safe stop (command output off, recording closed, source
disconnected) and then a graceful server shutdown, so recordings are closed properly.

Without a window toolkit, or with ``--headless``, it runs until SIGTERM/SIGINT with the same
clean shutdown. Inside the bundle the same executable also answers ``concord`` commands
(``Concord doctor``, ``Concord status`` …) and serves as the source-plugin host.

Windows (Concord.exe): the same window; ``concord stop`` (``concord-cli.exe stop``) reaches
the app through a stop request in the data folder (Windows has no SIGTERM to catch), and
Ctrl-C / Ctrl-Break quit a ``--headless`` app in a console.
"""

from __future__ import annotations

import argparse
import contextlib
import logging
import os
import signal
import sys
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from concord import __version__

log = logging.getLogger(__name__)

READY_TIMEOUT_S = 90.0
STOP_TIMEOUT_S = 30.0


class WindowUnavailable(Exception):
    pass


@dataclass
class ServerThread:
    """uvicorn in a background thread with its own event loop."""

    server: Any
    thread: threading.Thread
    error: list[BaseException] = field(default_factory=list)

    @property
    def alive(self) -> bool:
        return self.thread.is_alive()

    def wait_ready(self, timeout: float) -> bool:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self.server.started:
                return True
            if not self.thread.is_alive():
                return False
            time.sleep(0.05)
        return False

    def stop(self, timeout: float = STOP_TIMEOUT_S) -> bool:
        self.server.should_exit = True
        self.thread.join(timeout)
        return not self.thread.is_alive()


def start_server_thread(settings: Any) -> ServerThread:
    import uvicorn

    from concord.server.app import create_app
    from concord.server.serve import uvicorn_config

    server = uvicorn.Server(uvicorn_config(settings, create_app(settings)))
    holder: list[BaseException] = []

    def target() -> None:
        try:
            server.run()
        except BaseException as exc:  # SystemExit from a failed bind, or a crash
            holder.append(exc)
            log.error("server thread ended: %r", exc)

    thread = threading.Thread(target=target, name="concord-server", daemon=True)
    thread.start()
    return ServerThread(server, thread, holder)


def safe_stop_via_api(url: str) -> None:
    from concord.launcher import http_json

    with contextlib.suppress(Exception):
        http_json(url + "/api/v1/safe-stop", "POST", {"reason": "desktop app quit"}, timeout=10)


def run_headless(srv: ServerThread, url: str, stop_event: threading.Event) -> int:
    while not stop_event.is_set() and srv.alive:
        stop_event.wait(0.2)
    if srv.alive:
        safe_stop_via_api(url)
        return 0 if srv.stop() else 1
    return 1


def run_window(
    srv: ServerThread,
    url: str,
    stop_event: threading.Event,
    open_console: Callable[[], None],
    on_ready: Callable[[Any], None] | None = None,
) -> int:
    """A small Tk status window. Closing it, Cmd-Q or the Dock's Quit stop Concord.

    Raises ``WindowUnavailable`` if no window can be created (the caller runs headless).
    ``on_ready(root)`` is called before the event loop starts (tests drive the window)."""
    import tkinter as tk

    try:
        root = tk.Tk()
    except Exception as exc:  # TclError: no display, broken Tcl/Tk installation
        raise WindowUnavailable(str(exc)) from exc
    # Creating the Tk root initializes Cocoa on macOS, which can replace the process's SIGTERM
    # disposition (CI: the windowed app exited with status 1 on SIGTERM without the safe quit).
    # Reinstate ours so SIGTERM / SIGINT (e.g. `concord stop`) run the same quit as the window.
    previous = {sig: signal.getsignal(sig) for sig in quit_signals()}
    for sig in previous:
        signal.signal(sig, lambda *_: stop_event.set())
    root.title("Concord")
    root.resizable(False, False)
    icon = window_icon()
    if icon is not None:
        with contextlib.suppress(tk.TclError):
            root.iconbitmap(default=str(icon))  # type: ignore[no-untyped-call]
    frame = tk.Frame(root, padx=18, pady=14)
    frame.pack()
    tk.Label(frame, text="Concord is running", font=("TkDefaultFont", 14, "bold")).pack(anchor="w")
    tk.Label(frame, text=url).pack(anchor="w", pady=(2, 8))
    tk.Label(
        frame,
        text="Research use only · not a medical device · read-only.\n"
        "Quitting stops command output, closes any recording\nand disconnects the source.",
        justify="left",
    ).pack(anchor="w")
    status = tk.StringVar(value="")
    tk.Label(frame, textvariable=status, fg="#a33").pack(anchor="w")
    buttons = tk.Frame(frame, pady=10)
    buttons.pack(anchor="w")
    result = {"code": 0, "quitting": 0}

    def quit_app() -> None:
        if result["quitting"]:
            return
        result["quitting"] = 1
        status.set("Stopping…")
        root.update_idletasks()
        safe_stop_via_api(url)
        result["code"] = 0 if srv.stop() else 1
        root.destroy()

    tk.Button(buttons, text="Open console", command=open_console).pack(side="left")
    tk.Button(buttons, text="Stop and quit", command=quit_app).pack(side="left", padx=(8, 0))
    root.protocol("WM_DELETE_WINDOW", quit_app)
    with contextlib.suppress(tk.TclError):  # macOS application menu / Dock / Cmd-Q
        root.createcommand("::tk::mac::Quit", quit_app)
        root.createcommand("::tk::mac::ReopenApplication", open_console)

    def poll() -> None:
        if stop_event.is_set():
            quit_app()
            return
        if not srv.alive:
            status.set("The server stopped unexpectedly; see the log in the data folder.")
            result["code"] = 1
            root.after(4000, root.destroy)
            return
        root.after(200, poll)

    root.after(200, poll)
    if on_ready is not None:
        on_ready(root)
    try:
        root.mainloop()
    finally:
        for sig, handler in previous.items():
            signal.signal(sig, handler)
    return result["code"]


def window_icon() -> Path | None:
    """The Windows app's icon (``concord.ico`` bundled next to the program), else None: macOS
    takes the icon from the .app, and Linux bundles have none."""
    if sys.platform != "win32" or not getattr(sys, "frozen", False):
        return None
    base = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    icon = base / "concord.ico"
    return icon if icon.is_file() else None


def quit_signals() -> tuple[signal.Signals, ...]:
    """Signals that quit the app like its window does. Windows: Ctrl-C and Ctrl-Break in a
    console (SIGTERM cannot be sent there; ``concord stop`` uses a stop request instead)."""
    sigs = [signal.SIGTERM, signal.SIGINT]
    brk = getattr(signal, "SIGBREAK", None)  # Windows only
    if brk is not None:
        sigs.append(brk)
    return tuple(sigs)


def has_window_toolkit() -> bool:
    """Tk is usable: always on macOS and Windows (their desktop is always there), on Linux
    and other X11 systems only with a display."""
    try:
        import tkinter

        if sys.platform not in ("darwin", "win32") and not os.environ.get("DISPLAY"):
            return False
        return bool(tkinter.TkVersion)
    except Exception:
        return False


def parse(argv: list[str]) -> argparse.Namespace:
    ap = argparse.ArgumentParser(prog="Concord", description="Concord desktop app")
    ap.add_argument("--headless", action="store_true", help="no window; stop with SIGTERM/Ctrl-C")
    ap.add_argument("--no-browser", action="store_true", help="do not open the console")
    ap.add_argument("--port", type=int)
    ap.add_argument("--data-dir")
    ap.add_argument("--config")
    # macOS may pass a process serial number when launched from Finder
    args, _unknown = ap.parse_known_args([a for a in argv if not a.startswith("-psn_")])
    return args


def main(argv: list[str] | None = None) -> int:
    args = parse(list(sys.argv[1:] if argv is None else argv))
    from concord.cli import _apply_overrides
    from concord.config import ConfigError, command_hint
    from concord.launcher import find, open_browser
    from concord.security import BindRefused
    from concord.server.serve import AlreadyRunning, StopWatcher, prepare
    from concord.server.settings import Settings

    _apply_overrides(args)
    try:
        settings = Settings.from_env()
    except ConfigError as exc:
        print(f"Concord: {exc}", file=sys.stderr)
        return 2
    url = settings.url
    existing = find(url, settings.pid_file)
    if existing is not None and existing.health is not None:
        # single instance: a second launch just shows the running console
        print(f"Concord is already running at {existing.url}")
        if settings.open_browser and not args.no_browser:
            open_browser(existing.url)
        return 0
    try:
        lock, _ = prepare(settings)
    except (BindRefused, AlreadyRunning) as exc:
        print(f"Concord: {exc}", file=sys.stderr)
        return 2
    stop_event = threading.Event()
    for sig in quit_signals():
        signal.signal(sig, lambda *_: stop_event.set())
    # `concord stop` on Windows (no catchable SIGTERM there) asks through the data folder
    watcher = StopWatcher(settings.pid_file, stop_event.set).start()
    try:
        srv = start_server_thread(settings)
        if not srv.wait_ready(READY_TIMEOUT_S):
            log.error("Concord server did not start: %r", srv.error[0] if srv.error else "timeout")
            print(
                "Concord could not start; see the log in " + str(settings.log_file), file=sys.stderr
            )
            srv.stop(5)
            return 1
        log.info("Concord %s desktop app ready at %s", __version__, url)
        print(f"Concord {__version__} is running at {url}", flush=True)
        if settings.open_browser and not args.no_browser:
            open_browser(url)
        if not args.headless and has_window_toolkit():

            def show_console() -> None:
                open_browser(url)

            try:
                quit_hint = (
                    "close it, Cmd-Q, or the Dock's Quit"
                    if sys.platform == "darwin"
                    else "Stop and quit, or close the window"
                )
                log.info("Concord window open (quit: %s)", quit_hint)
                return run_window(srv, url, stop_event, show_console)
            except WindowUnavailable as exc:
                log.warning("no window could be created (%s)", exc)
        if not args.headless:
            log.info(
                "no window toolkit available; running headless (stop: Ctrl-C or %s)",
                command_hint("stop"),
            )
        return run_headless(srv, url, stop_event)
    finally:
        watcher.close()
        lock.release()
