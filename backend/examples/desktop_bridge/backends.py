"""Pointer backends for the desktop control bridge (OS side). Standard library only, plus
``pynput`` for the optional pynput backend.

A backend moves the OS pointer by a relative amount, clicks the primary button, and — where it
can tell — reports the title of the focused window. Nothing here reads Concord: the bridge
decides what to do; a backend only does it.

* :class:`DryRunBackend` — records every action, touches nothing (tests, rehearsal).
* :class:`XdotoolBackend` — X11 via the ``xdotool`` command (can report the focused window).
* :class:`PynputBackend` — ``pynput`` (Windows, macOS, X11); cannot report the focused window,
  so the bridge refuses ``--focus`` with it; offers a global stop hotkey.
"""

from __future__ import annotations

import importlib
import shutil
import subprocess
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Protocol


class BackendError(RuntimeError):
    """The backend cannot run here (missing tool, no display, ...)."""


class PointerBackend(Protocol):
    @property
    def name(self) -> str: ...

    @property
    def can_report_focus(self) -> bool: ...

    @property
    def has_hotkey(self) -> bool: ...

    def move_by(self, dx: int, dy: int) -> None: ...

    def click(self) -> None: ...

    def focused_window(self) -> str | None:
        """Title of the focused window; None when unknown."""
        ...

    def start_hotkey(self, on_press: Callable[[], None]) -> None: ...

    def close(self) -> None: ...


@dataclass
class DryRunBackend:
    """Records what it would do. ``focus`` is the title it reports (None = cannot tell)."""

    focus: str | None = "dry-run"
    name: str = "dry-run"
    has_hotkey: bool = True
    actions: list[tuple[str, int, int]] = field(default_factory=list)
    _hotkey: Callable[[], None] | None = None

    @property
    def can_report_focus(self) -> bool:
        return self.focus is not None

    def move_by(self, dx: int, dy: int) -> None:
        self.actions.append(("move", dx, dy))

    def click(self) -> None:
        self.actions.append(("click", 0, 0))

    def focused_window(self) -> str | None:
        return self.focus

    def start_hotkey(self, on_press: Callable[[], None]) -> None:
        self._hotkey = on_press

    def press_hotkey(self) -> None:
        """Test hook: the user pressed the stop hotkey."""
        if self._hotkey is not None:
            self._hotkey()

    def close(self) -> None:
        self.actions.append(("close", 0, 0))


class XdotoolBackend:
    """X11 through the ``xdotool`` command line tool (needs ``DISPLAY``)."""

    name = "xdotool"
    can_report_focus = True
    has_hotkey = False  # xdotool cannot listen for keys; use Ctrl-C in the bridge terminal

    def __init__(self, timeout_s: float = 1.0) -> None:
        exe = shutil.which("xdotool")
        if exe is None:
            raise BackendError("xdotool not found (Debian/Ubuntu: apt-get install xdotool)")
        self._exe, self._timeout = exe, timeout_s
        self._run("getmouselocation")  # fails early without a reachable X display

    def _run(self, *args: str) -> str:
        try:
            out = subprocess.run(
                [self._exe, *args],
                check=True,
                capture_output=True,
                text=True,
                timeout=self._timeout,
            )
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError) as exc:
            raise BackendError(f"xdotool {args[0]} failed: {exc}") from exc
        return out.stdout.strip()

    def move_by(self, dx: int, dy: int) -> None:
        self._run("mousemove_relative", "--", str(dx), str(dy))

    def click(self) -> None:
        self._run("click", "1")

    def focused_window(self) -> str | None:
        try:
            return self._run("getwindowfocus", "getwindowname")
        except BackendError:
            return None

    def location(self) -> tuple[int, int]:
        """Pointer position (for tests)."""
        parts = dict(p.split(":", 1) for p in self._run("getmouselocation").split() if ":" in p)
        return int(parts["x"]), int(parts["y"])

    def start_hotkey(self, on_press: Callable[[], None]) -> None:
        raise BackendError("the xdotool backend has no global hotkey")

    def close(self) -> None:
        return None


class PynputBackend:
    """``pynput`` (optional dependency: ``pip install pynput``)."""

    name = "pynput"
    can_report_focus = False  # pynput cannot tell which window has focus
    has_hotkey = True
    HOTKEY = "<ctrl>+<alt>+b"

    def __init__(self) -> None:
        try:  # optional dependency, imported only when this backend is chosen
            mouse = importlib.import_module("pynput.mouse")
            keyboard = importlib.import_module("pynput.keyboard")
        except ImportError as exc:  # pragma: no cover - depends on the machine
            raise BackendError("pynput is not installed (pip install pynput)") from exc
        self._mouse_mod: Any = mouse
        self._keyboard_mod: Any = keyboard
        self._mouse: Any = mouse.Controller()
        self._listener: Any = None

    def move_by(self, dx: int, dy: int) -> None:
        self._mouse.move(dx, dy)

    def click(self) -> None:
        self._mouse.click(self._mouse_mod.Button.left, 1)

    def focused_window(self) -> str | None:
        return None

    def start_hotkey(self, on_press: Callable[[], None]) -> None:
        self._listener = self._keyboard_mod.GlobalHotKeys({self.HOTKEY: on_press})
        self._listener.start()

    def close(self) -> None:
        if self._listener is not None:
            self._listener.stop()


def make_backend(name: str) -> PointerBackend:
    if name == "dry-run":
        return DryRunBackend()
    if name == "xdotool":
        return XdotoolBackend()
    if name == "pynput":
        return PynputBackend()
    raise BackendError(f"unknown backend {name!r} (dry-run, xdotool, pynput)")
