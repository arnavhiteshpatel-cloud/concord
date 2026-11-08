"""Entry point of the BrainOS desktop bundle (PyInstaller; see packaging/brainos.spec).

One executable, three roles:

- ``BrainOS`` (double-click, or with ``--headless``): the desktop app (brainos.desktop);
- ``BrainOS doctor|status|stop|version|config|reproduce|dataset|serve ...``: the ``brainos``
  command, so a support report can be made from the bundle itself;
- ``BrainOS -m brainos_adapter_sdk.host ...`` / ``-m brainos_decoder_sdk.host ...``: the
  source-plugin host and the isolated decoder host. BrainOS starts both as
  ``<sys.executable> -m <module>``; in a bundle ``sys.executable`` is this program, so it must
  answer like ``python -m`` for those two modules (and nothing else).
"""

from __future__ import annotations

import runpy
import sys

ALLOWED_MODULES = frozenset({"brainos_adapter_sdk.host", "brainos_decoder_sdk.host"})
CLI_COMMANDS = frozenset(
    {"doctor", "status", "stop", "start", "version", "config", "reproduce", "dataset", "serve"}
)


def route(argv: list[str]) -> tuple[str, list[str]]:
    """('module', [name, *args]) | ('cli', args) | ('app', args) | ('refuse', [module])."""
    if len(argv) >= 2 and argv[0] == "-m":
        if argv[1] in ALLOWED_MODULES:
            return "module", argv[1:]
        return "refuse", [argv[1]]
    if argv and argv[0] in CLI_COMMANDS:
        return "cli", argv
    if argv and argv[0] in ("--version", "-V"):
        return "cli", ["--version"]
    return "app", argv


def main() -> int:
    kind, args = route(sys.argv[1:])
    if kind == "module":
        sys.argv = [args[0], *args[1:]]
        runpy.run_module(args[0], run_name="__main__", alter_sys=True)
        return 0
    if kind == "refuse":
        print(f"BrainOS: -m {args[0]} is not available in the app bundle", file=sys.stderr)
        return 2
    if kind == "cli":
        from brainos.cli import main as cli

        return cli(args)
    from brainos.desktop import main as app

    return app(args)


if __name__ == "__main__":
    raise SystemExit(main())
