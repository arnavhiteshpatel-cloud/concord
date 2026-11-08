"""The Concord runtime server (requires the ``server`` extra: ``pip install "concordos[server]"``).

Imports are lazy so that ``concord-server`` can explain a missing extra instead of failing
with a traceback, and so the application SDK never imports the web stack.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from concord.server.app import create_app
    from concord.server.settings import Settings

__all__ = ["Settings", "create_app"]


def __getattr__(name: str) -> Any:
    if name == "create_app":
        from concord.server.app import create_app

        return create_app
    if name == "Settings":
        from concord.server.settings import Settings

        return Settings
    raise AttributeError(name)
