"""The BrainOS runtime server (requires the ``server`` extra: ``pip install "brainos[server]"``).

Imports are lazy so that ``brainos-server`` can explain a missing extra instead of failing
with a traceback, and so the application SDK never imports the web stack.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from brainos.server.app import create_app
    from brainos.server.settings import Settings

__all__ = ["Settings", "create_app"]


def __getattr__(name: str) -> Any:
    if name == "create_app":
        from brainos.server.app import create_app

        return create_app
    if name == "Settings":
        from brainos.server.settings import Settings

        return Settings
    raise AttributeError(name)
