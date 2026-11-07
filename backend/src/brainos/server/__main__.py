"""`python -m brainos.server` / `brainos-server` entry point."""

from __future__ import annotations

import logging

import uvicorn

from brainos.server.app import create_app
from brainos.server.settings import Settings


def main() -> None:
    settings = Settings.from_env()
    logging.basicConfig(
        level=settings.log_level,
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
    )
    if settings.host not in ("127.0.0.1", "localhost", "::1"):
        logging.getLogger(__name__).warning(
            "binding to %s: BrainOS v1 has NO authentication; do not expose it to a network",
            settings.host,
        )
    uvicorn.run(
        create_app(settings),
        host=settings.host,
        port=settings.port,
        log_level=settings.log_level.lower(),
        ws_max_size=64 * 1024,
    )


if __name__ == "__main__":
    main()
