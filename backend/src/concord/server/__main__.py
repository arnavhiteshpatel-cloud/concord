"""`python -m concord.server` / `concord-server` entry point (same as `concord serve`)."""

from __future__ import annotations

import sys

try:
    import uvicorn  # noqa: F401

    from concord.server.serve import run
    from concord.server.settings import Settings
except ImportError as exc:  # base install = application SDK only
    _MISSING: ImportError | None = exc
else:
    _MISSING = None


def main() -> None:
    if _MISSING is not None:
        sys.exit(
            f"The Concord server is not installed ({_MISSING.name or _MISSING}). The base "
            'package is the application SDK; install the server: pip install "concordos[server]"'
        )
    from concord.config import ConfigError

    try:
        settings = Settings.from_env()
    except ConfigError as exc:
        sys.exit(f"concord: {exc}")
    sys.exit(run(settings))


if __name__ == "__main__":
    main()
