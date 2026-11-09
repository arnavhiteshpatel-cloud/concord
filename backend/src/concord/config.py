"""Concord configuration file: one TOML file with safe defaults (stdlib only).

Precedence for every setting: environment variable > config file > built-in default. The
file is optional; nothing in it is required for ordinary use. Location:

- ``$CONCORD_CONFIG`` if set;
- macOS: ``~/Library/Application Support/Concord/config.toml``;
- Windows: ``%LOCALAPPDATA%\\Concord\\config.toml`` (next to the data folder
  ``%LOCALAPPDATA%\\Concord\\data``);
- Linux and others: ``$XDG_CONFIG_HOME/concord/config.toml`` (``~/.config/concord/config.toml``).

``concord config init`` writes a commented template (mode 0600). A config file that other
users can write to, or that belongs to another user, is refused: it decides where neural data
is written and which network interface the server listens on. (POSIX only: Windows has no
mode bits; the default location is inside the user's profile, which Windows already keeps
private to that user.)

This module must stay importable without the server extra (the ``concord`` command uses it).
"""

from __future__ import annotations

import json
import os
import stat
import sys
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

CONFIG_ENV = "CONCORD_CONFIG"
PACKAGE_DIR = Path(__file__).resolve().parent
# repository root when running from a source checkout (backend/src/concord/config.py)
_REPO_CANDIDATE = PACKAGE_DIR.parents[2]


class ConfigError(ValueError):
    """The config file cannot be used (syntax, unknown key, wrong type, unsafe permissions)."""


# section -> key -> (type, description).
# Types: "str", "int", "bool", "days", "level", "seconds", "mib", "mib0".
SCHEMA: dict[str, dict[str, tuple[str, str]]] = {
    "server": {
        "host": ("str", "interface to listen on; keep 127.0.0.1 (Concord has no authentication)"),
        "port": ("int", "TCP port of the console and API"),
        "allow_remote": (
            "bool",
            "allow a non-loopback host (refused otherwise; Concord has no authentication or TLS)",
        ),
        "open_browser": ("bool", "`concord start` and the desktop app open the console"),
        "log_level": ("level", "DEBUG, INFO, WARNING or ERROR"),
    },
    "storage": {
        "data_dir": ("str", "recordings, models, sessions, exports and logs (created 0700)"),
        "reports_dir": ("str", "test and calibration reports"),
    },
    "retention": {
        "recordings_days": ("days", "delete recordings older than this at startup (0 = keep)"),
        "sessions_days": ("days", "delete closed sessions and their exports (0 = keep)"),
        "exports_days": ("days", "delete export bundles older than this (0 = keep)"),
        "models_days": ("days", "delete decoder models older than this (0 = keep)"),
    },
    "recording": {
        "max_duration_s": (
            "seconds",
            "a recording with raw signal frames stops after this many seconds (default 300)",
        ),
        "max_duration_no_raw_s": (
            "seconds",
            "a features-and-labels-only recording stops after this many seconds (default 3600)",
        ),
        "max_size_mb": ("mib", "a recording stops after this many MiB (default 200)"),
        "min_free_mb": (
            "mib0",
            "a recording refuses to start, or stops cleanly, below this much free disk "
            "space in MiB (default 256)",
        ),
    },
    "simulation": {
        "enabled": ("bool", "offer Simulated Profile A/B and the simulator controls"),
    },
    "plugins": {
        "discover": ("bool", "discover installed source plugins at startup"),
    },
}

LOG_LEVELS = ("DEBUG", "INFO", "WARNING", "ERROR")
# Upper bounds for [recording] limits: long validation runs, but never unbounded.
MAX_RECORDING_S = 24 * 3600
MAX_RECORDING_MIB = 100 * 1024


def frozen() -> bool:
    """True inside a bundled desktop app (PyInstaller)."""
    return bool(getattr(sys, "frozen", False))


def source_checkout() -> Path | None:
    """The repository root when Concord runs from a source checkout (``make setup``)."""
    if frozen():
        return None
    root = _REPO_CANDIDATE
    if (root / "backend" / "pyproject.toml").is_file() and (root / "frontend").is_dir():
        return root
    return None


def user_dir() -> Path:
    """Per-user Concord directory for installed copies (wheel or desktop app)."""
    home = Path.home()
    if sys.platform == "darwin":
        return home / "Library" / "Application Support" / "Concord"
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA")
        return Path(base) / "Concord" if base else home / "AppData" / "Local" / "Concord"
    base = os.environ.get("XDG_DATA_HOME")
    return (Path(base) if base else home / ".local" / "share") / "concord"


def default_config_path() -> Path:
    env = os.environ.get(CONFIG_ENV)
    if env:
        return Path(env).expanduser()
    if sys.platform in ("darwin", "win32"):
        return user_dir() / "config.toml"
    base = os.environ.get("XDG_CONFIG_HOME")
    return (Path(base) if base else Path.home() / ".config") / "concord" / "config.toml"


def command_hint(args: str) -> str:
    """A ``concord`` command as the operator types it for this installation: ``concord stop``;
    in the desktop app the bundled program, e.g. on Windows
    ``"C:\\Users\\me\\Downloads\\Concord\\concord-cli.exe" stop``."""
    from concord.oscompat import cli_command

    return f"{cli_command()} {args}".strip()


def toml_string(value: str) -> str:
    """``value`` as a TOML basic string. Windows paths contain backslashes, which TOML reads
    as escapes ("C:\\Users" would be an invalid \\U escape), so they are escaped."""
    return json.dumps(value, ensure_ascii=False)


def packaged_console_dir() -> Path:
    """The built console shipped inside the package (wheel built with the console, or app)."""
    return PACKAGE_DIR / "server" / "console"


def default_data_dir() -> Path:
    root = source_checkout()
    return root / "data" if root else user_dir() / "data"


def default_reports_dir() -> Path:
    root = source_checkout()
    return root / "reports" if root else user_dir() / "reports"


def default_static_dir() -> Path | None:
    root = source_checkout()
    if root is not None and (root / "frontend" / "dist" / "index.html").is_file():
        return root / "frontend" / "dist"
    packaged = packaged_console_dir()
    if (packaged / "index.html").is_file():
        return packaged
    return root / "frontend" / "dist" if root else None


@dataclass(frozen=True)
class Retention:
    """Retention policy in days; ``None`` keeps forever. Enforced at server startup."""

    recordings_days: float | None = None
    sessions_days: float | None = None
    exports_days: float | None = None
    models_days: float | None = None

    @property
    def active(self) -> bool:
        return any(
            v is not None
            for v in (self.recordings_days, self.sessions_days, self.exports_days, self.models_days)
        )

    def as_dict(self) -> dict[str, float | None]:
        return {
            "recordings_days": self.recordings_days,
            "sessions_days": self.sessions_days,
            "exports_days": self.exports_days,
            "models_days": self.models_days,
        }


@dataclass(frozen=True)
class FileConfig:
    path: Path
    exists: bool
    values: dict[str, dict[str, Any]] = field(default_factory=dict)

    def get(self, section: str, key: str) -> Any:
        return self.values.get(section, {}).get(key)

    def retention(self) -> Retention:
        r = self.values.get("retention", {})
        return Retention(
            recordings_days=r.get("recordings_days"),
            sessions_days=r.get("sessions_days"),
            exports_days=r.get("exports_days"),
            models_days=r.get("models_days"),
        )


def permission_problem(path: Path) -> str | None:
    """Why a config file is unsafe to trust, or None. POSIX only."""
    if os.name != "posix":
        return None
    st = path.stat()
    if st.st_uid != os.getuid():
        return f"{path} belongs to another user (uid {st.st_uid})"
    if st.st_mode & (stat.S_IWGRP | stat.S_IWOTH):
        return (
            f"{path} can be changed by other users (mode {stat.S_IMODE(st.st_mode):o}); chmod 600"
        )
    return None


def _coerce(section: str, key: str, value: Any, where: str | None = None) -> Any:
    kind, _ = SCHEMA[section][key]
    where = where or f"[{section}] {key}"
    if kind == "seconds":
        if (
            isinstance(value, bool)
            or not isinstance(value, int | float)
            or not 0 < value <= MAX_RECORDING_S
        ):
            raise ConfigError(f"{where} must be a number of seconds in (0, {MAX_RECORDING_S}]")
        return float(value)
    if kind in ("mib", "mib0"):
        low = 1 if kind == "mib" else 0
        if isinstance(value, bool) or not isinstance(value, int):
            raise ConfigError(f"{where} must be an integer number of MiB")
        if not low <= value <= MAX_RECORDING_MIB:
            raise ConfigError(f"{where} must be {low}-{MAX_RECORDING_MIB} MiB")
        return value
    if kind == "bool":
        if not isinstance(value, bool):
            raise ConfigError(f"{where} must be true or false")
        return value
    if kind == "int":
        if isinstance(value, bool) or not isinstance(value, int):
            raise ConfigError(f"{where} must be an integer")
        if key == "port" and not 1 <= value <= 65535:
            raise ConfigError(f"{where} must be 1-65535")
        return value
    if kind == "str":
        if not isinstance(value, str) or not value.strip():
            raise ConfigError(f"{where} must be a non-empty string")
        return value
    if kind == "level":
        if not isinstance(value, str) or value.upper() not in LOG_LEVELS:
            raise ConfigError(f"{where} must be one of {', '.join(LOG_LEVELS)}")
        return value.upper()
    # days
    if isinstance(value, bool) or not isinstance(value, int | float) or value < 0:
        raise ConfigError(f"{where} must be a number of days >= 0")
    return None if value == 0 else float(value)


def coerce_env(env: str, section: str, key: str, raw: str) -> Any:
    """An environment variable for a numeric config key, validated like the file value."""
    kind, _ = SCHEMA[section][key]
    try:
        value: Any = int(raw) if kind in ("mib", "mib0") else float(raw)
    except ValueError:
        raise ConfigError(f"{env}={raw!r} is not a number") from None
    return _coerce(section, key, value, env)


def parse_config(text: str, path: Path) -> dict[str, dict[str, Any]]:
    try:
        raw = tomllib.loads(text)
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"{path}: invalid TOML: {exc}") from None
    out: dict[str, dict[str, Any]] = {}
    for section, body in raw.items():
        if section not in SCHEMA:
            raise ConfigError(f"{path}: unknown section [{section}] (known: {', '.join(SCHEMA)})")
        if not isinstance(body, dict):
            raise ConfigError(f"{path}: [{section}] must be a table")
        for key, value in body.items():
            if key not in SCHEMA[section]:
                known = ", ".join(SCHEMA[section])
                raise ConfigError(f"{path}: unknown key [{section}] {key} (known: {known})")
            out.setdefault(section, {})[key] = _coerce(section, key, value)
    return out


def load_config(path: Path | None = None) -> FileConfig:
    """Read and validate the config file. A missing file is fine (defaults apply)."""
    path = path or default_config_path()
    if not path.exists():
        return FileConfig(path=path, exists=False)
    problem = permission_problem(path)
    if problem:
        raise ConfigError(f"refusing to use the config file: {problem}")
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise ConfigError(f"{path}: cannot read: {exc}") from None
    return FileConfig(path=path, exists=True, values=parse_config(text, path))


def template() -> str:
    """A commented config file listing every key with its default."""
    lines = [
        "# Concord configuration. Every key is optional; delete a line to use the default.",
        "# Environment variables (CONCORD_PORT, CONCORD_DATA_DIR, ...) override this file.",
        "# Documentation: docs/INSTALL_MAC.md, docs/INSTALL_WINDOWS.md, docs/LAB_SETUP.md, "
        "docs/SECURITY.md.",
        "",
        "[server]",
        'host = "127.0.0.1"        # loopback only: Concord has no authentication or TLS',
        "port = 8000",
        "allow_remote = false      # true is required for any other host (not recommended)",
        "open_browser = true",
        'log_level = "INFO"',
        "",
        "[storage]",
        f"# data_dir = {toml_string(str(default_data_dir()))}",
        f"# reports_dir = {toml_string(str(default_reports_dir()))}",
        "",
        "[retention]",
        "# Days to keep each kind of data; 0 keeps it forever. Enforced when the server starts;",
        "# items in use (an active recording or session, a running model) are never deleted.",
        "recordings_days = 0",
        "sessions_days = 0",
        "exports_days = 0",
        "models_days = 0",
        "",
        "[recording]",
        "# Limits of one recording; it stops cleanly (and is complete and replayable) when one",
        "# is reached. For longer runs raise them; at most 86400 s and 102400 MiB.",
        "max_duration_s = 300          # with raw signal frames",
        "max_duration_no_raw_s = 3600  # features and labels only",
        "max_size_mb = 200",
        "min_free_mb = 256             # stop before the disk is full",
        "",
        "[simulation]",
        "enabled = true",
        "",
        "[plugins]",
        "discover = true",
        "",
    ]
    return "\n".join(lines)


def write_template(path: Path | None = None) -> Path:
    """Create the config file (0600) with the template. Refuses to overwrite."""
    path = path or default_config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    from concord.oscompat import O_BINARY

    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | O_BINARY, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write(template())
    return path
