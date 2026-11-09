"""Concord: hardware-agnostic, read-only runtime and SDK for implanted BCIs (MVP)."""

import contextlib
import os
import sys

__version__ = "0.3.1"


def safe_console_streams() -> None:
    """Never crash on a character the console cannot show. A Windows console or a redirected
    stream encodes with the ANSI code page (cp1252), which has no Greek letters, arrows, etc.;
    such characters are printed escaped instead of raising UnicodeEncodeError."""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            with contextlib.suppress(ValueError, OSError):
                reconfigure(errors="backslashreplace")


# Every entry point (`concord …`, the desktop app, and the `python -m concord.…` tools and
# report scripts) imports this package first, so on Windows this covers them all.
if os.name == "nt":
    safe_console_streams()
