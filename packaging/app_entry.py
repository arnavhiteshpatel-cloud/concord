"""Entry point of the Concord desktop bundle (PyInstaller; see packaging/concord.spec).

One executable, three roles:

- ``Concord`` (double-click, or with ``--headless``): the desktop app (concord.desktop);
- ``Concord doctor|status|stop|version|config|reproduce|dataset|serve|publish ...``: the ``concord``
  command, so a support report can be made from the bundle itself;
- ``Concord -m concord_adapter_sdk.host ...`` / ``-m concord_decoder_sdk.host ...``: the
  source-plugin host and the isolated decoder host. Concord starts both as
  ``<sys.executable> -m <module>``; in a bundle ``sys.executable`` is this program, so it must
  answer like ``python -m`` for those two modules (and nothing else).

Windows has two programs built from this file, because a Windows program is either windowed
(no console: double-clicking it opens no terminal window) or a console program (its output
appears in the terminal that ran it, and the terminal waits for it):

- ``Concord.exe``, windowed: the desktop app. Given a command it still runs it, printing to the
  terminal it was started from if there is one (the prompt does not wait for it);
- ``concord-cli.exe``, console: the ``concord`` command (``concord-cli.exe stop``; without a
  command it prints the help), and the program Concord runs its helper processes and
  ``concord start``'s server with (concord.oscompat.helper_executable).
"""

from __future__ import annotations

import os
import runpy
import sys
from pathlib import PureWindowsPath

ALLOWED_MODULES = frozenset({"concord_adapter_sdk.host", "concord_decoder_sdk.host"})
CLI_COMMANDS = frozenset(
    {
        "doctor",
        "status",
        "stop",
        "start",
        "version",
        "config",
        "reproduce",
        "dataset",
        "serve",
        "publish",
    }
)
CLI_PROGRAM = "concord-cli.exe"  # Windows: the console program (concord.oscompat.CLI_EXE)


def is_cli_program(executable: str) -> bool:
    # PureWindowsPath: splits on "\\" and "/" alike
    return PureWindowsPath(executable).name.lower() == CLI_PROGRAM


def route(argv: list[str], *, cli_program: bool = False) -> tuple[str, list[str]]:
    """('module', [name, *args]) | ('cli', args) | ('app', args) | ('refuse', [module])."""
    if len(argv) >= 2 and argv[0] == "-m":
        if argv[1] in ALLOWED_MODULES:
            return "module", argv[1:]
        return "refuse", [argv[1]]
    if cli_program:  # concord-cli.exe is the `concord` command, nothing else
        return "cli", argv or ["--help"]
    if argv and argv[0] in CLI_COMMANDS:
        return "cli", argv
    if argv and argv[0] in ("--version", "-V"):
        return "cli", ["--version"]
    return "app", argv


def attach_parent_console() -> None:
    """Windowed Concord.exe run with a command from a terminal: print there.

    A windowed Windows program has no standard streams (``sys.stdout`` is None); attaching to
    the console of the terminal that started it makes ``Concord.exe status`` readable. Without
    such a terminal (double-click) nothing happens; output is then discarded."""
    if sys.platform != "win32" or sys.stdout is not None:
        return
    import ctypes

    kernel32 = getattr(ctypes, "windll").kernel32  # noqa: B009 - Windows only
    if not kernel32.AttachConsole(-1):  # ATTACH_PARENT_PROCESS
        return
    try:
        sys.stdout = open("CONOUT$", "w", encoding="utf-8")  # noqa: SIM115 - process lifetime
        sys.stderr = open("CONOUT$", "w", encoding="utf-8")  # noqa: SIM115 - process lifetime
    except OSError:
        return


def null_streams() -> None:
    """A windowed program (Concord.exe) has no standard streams. Code that writes to them
    directly (not through print or logging) must not fail: give it a sink."""
    if sys.stdout is None:
        sys.stdout = open(os.devnull, "w", encoding="utf-8")  # noqa: SIM115 - process lifetime
    if sys.stderr is None:
        sys.stderr = open(os.devnull, "w", encoding="utf-8")  # noqa: SIM115 - process lifetime


def main() -> int:
    kind, args = route(sys.argv[1:], cli_program=is_cli_program(sys.executable))
    if kind == "cli":
        attach_parent_console()
    null_streams()
    if kind == "module":
        sys.argv = [args[0], *args[1:]]
        runpy.run_module(args[0], run_name="__main__", alter_sys=True)
        return 0
    if kind == "refuse":
        print(f"Concord: -m {args[0]} is not available in the app bundle", file=sys.stderr)
        return 2
    if kind == "cli":
        from concord.cli import main as cli

        return cli(args)
    from concord.desktop import main as app

    return app(args)


if __name__ == "__main__":
    raise SystemExit(main())
