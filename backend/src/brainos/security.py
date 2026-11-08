"""Local-first safeguards: bind policy, private files and directories, redaction, logging.

BrainOS is research software without authentication. These measures limit accidental
exposure on the operator's own machine; they are not a security boundary against other
programs running as the same user (docs/SECURITY.md).

Stdlib only: used by the ``brainos`` command without the server extra.
"""

from __future__ import annotations

import contextlib
import ipaddress
import logging
import logging.handlers
import os
import re
import socket
import stat
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path

PRIVATE_DIR = 0o700
PRIVATE_FILE = 0o600
LOG_MAX_BYTES = 5 * 1024 * 1024
LOG_BACKUPS = 3
MAX_LOG_MESSAGE = 4000

log = logging.getLogger(__name__)


# --------------------------------------------------------------------------- bind policy


class BindRefused(Exception):
    """A non-loopback bind address without the explicit allow flag."""


def is_loopback(host: str) -> bool:
    if host.strip().lower() == "localhost":
        return True
    try:
        return ipaddress.ip_address(host.strip("[]")).is_loopback
    except ValueError:
        return False


def check_bind(host: str, allow_remote: bool) -> str | None:
    """Refuse a non-loopback host unless ``allow_remote``; return the warning to show if allowed."""
    if is_loopback(host):
        return None
    if not allow_remote:
        raise BindRefused(
            f"refusing to listen on {host!r}: BrainOS has no authentication and no TLS, so "
            "anyone who can reach this port could control the runtime and read neural data. "
            "Keep host = 127.0.0.1. To listen on another interface anyway (an isolated, trusted "
            "network only), set allow_remote = true in the config file, BRAINOS_ALLOW_REMOTE=1, "
            "or pass --allow-remote."
        )
    return (
        f"LISTENING ON {host}: BrainOS has NO authentication and NO TLS. Anyone who can reach "
        "this port can control the runtime and read neural data. Use only on an isolated, "
        "trusted network."
    )


# --------------------------------------------------------------------------- permissions


def _owned(path: Path) -> bool:
    return os.name != "posix" or path.lstat().st_uid == os.getuid()


def ensure_private_dir(path: Path) -> Path:
    """Create ``path`` (and parents) and make it 0700 if it is ours and not a symlink.

    Symlinked directories (e.g. a shared datasets directory) are left alone: changing their
    target's permissions is the owner's decision.
    """
    path.mkdir(parents=True, exist_ok=True)
    if (
        os.name == "posix"
        and not path.is_symlink()
        and _owned(path)
        and stat.S_IMODE(path.stat().st_mode) != PRIVATE_DIR
    ):
        os.chmod(path, PRIVATE_DIR)
    return path


def harden_file(path: Path) -> None:
    if (
        os.name == "posix"
        and path.is_file()
        and not path.is_symlink()
        and _owned(path)
        and stat.S_IMODE(path.stat().st_mode) != PRIVATE_FILE
    ):
        os.chmod(path, PRIVATE_FILE)


def open_private(path: Path, mode: str = "w", *, exclusive: bool = False) -> int:
    """Open ``path`` for writing with mode 0600 (also on an existing file); returns an fd."""
    flags = os.O_WRONLY | os.O_CREAT
    if exclusive:
        flags |= os.O_EXCL
    flags |= os.O_APPEND if mode == "a" else os.O_TRUNC
    fd = os.open(path, flags, PRIVATE_FILE)
    if os.name == "posix":
        os.fchmod(fd, PRIVATE_FILE)
    return fd


def write_private(path: Path, data: str | bytes) -> Path:
    """Write a whole file atomically with mode 0600."""
    tmp = path.with_name(f".{path.name}.tmp")
    fd = open_private(tmp)
    with os.fdopen(fd, "wb") as fh:
        fh.write(data.encode("utf-8") if isinstance(data, str) else data)
    os.replace(tmp, path)
    return path


@dataclass
class HardenReport:
    dirs_fixed: int = 0
    files_fixed: int = 0
    symlinks_skipped: list[str] = field(default_factory=list)


def harden_tree(root: Path, *, skip: Iterable[str] = ()) -> HardenReport:
    """Make every directory 0700 and every file 0600 under ``root`` (not following symlinks).

    Top-level entries named in ``skip`` are left alone (e.g. downloaded public datasets).
    """
    report = HardenReport()
    if os.name != "posix" or not root.exists():
        return report
    skipped = set(skip)
    ensure_private_dir(root)
    for dirpath, dirnames, filenames in os.walk(root):
        here = Path(dirpath)
        if here == root:
            dirnames[:] = [d for d in dirnames if d not in skipped]
        for d in list(dirnames):
            p = here / d
            if p.is_symlink():
                report.symlinks_skipped.append(str(p))
                dirnames.remove(d)
                continue
            if _owned(p) and stat.S_IMODE(p.stat().st_mode) != PRIVATE_DIR:
                os.chmod(p, PRIVATE_DIR)
                report.dirs_fixed += 1
        for f in filenames:
            p = here / f
            if p.is_symlink():
                report.symlinks_skipped.append(str(p))
                continue
            if _owned(p) and stat.S_IMODE(p.stat().st_mode) != PRIVATE_FILE:
                os.chmod(p, PRIVATE_FILE)
                report.files_fixed += 1
    return report


def open_permissions(root: Path, *, skip: Iterable[str] = ()) -> tuple[int, int]:
    """Count directories and files under ``root`` that group/others can access (doctor)."""
    if os.name != "posix" or not root.exists():
        return 0, 0
    skipped = set(skip)
    dirs = files = 0
    mask = stat.S_IRWXG | stat.S_IRWXO
    for dirpath, dirnames, filenames in os.walk(root):
        here = Path(dirpath)
        if here == root:
            dirnames[:] = [d for d in dirnames if d not in skipped]
        for d in list(dirnames):
            p = here / d
            if p.is_symlink():
                dirnames.remove(d)
            elif p.stat().st_mode & mask:
                dirs += 1
        for f in filenames:
            p = here / f
            if not p.is_symlink() and p.stat().st_mode & mask:
                files += 1
    return dirs, files


# --------------------------------------------------------------------------- redaction

_NUM = r"-?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?"
# eight or more numbers in brackets: sample arrays, feature vectors, weight matrices
_ARRAY = re.compile(rf"\[\s*{_NUM}(?:(?:\s*,\s*|\s+){_NUM}){{7,}}\s*,?\s*\]")
_SECRET = re.compile(
    r"(?i)\b(password|passwd|secret|token|api[_-]?key|access[_-]?key|private[_-]?key|"
    r"client[_-]?secret|authorization|auth)(\"?\s*[:=]\s*\"?)([^\s,;\"'}&]+)"
)
_BEARER = re.compile(r"(?i)\b(bearer|basic)\s+[A-Za-z0-9._~+/=-]{8,}")
_EMAIL = re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b")
_IPV4 = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
_HOME = re.compile(r"(/Users/|/home/)[^/\s\"']+")


def _ip(match: re.Match[str]) -> str:
    text = match.group(0)
    try:
        ip = ipaddress.ip_address(text)
    except ValueError:
        return text
    return text if ip.is_loopback or ip.is_unspecified else "<ip>"


def redact_secrets(text: str) -> str:
    """Secrets and long numeric arrays. Used for every log line BrainOS writes."""
    text = _BEARER.sub(lambda m: f"{m.group(1)} [redacted]", text)
    text = _SECRET.sub(lambda m: f"{m.group(1)}{m.group(2)}[redacted]", text)
    return _ARRAY.sub(
        lambda m: f"[{len(re.findall(_NUM, m.group(0)))} values redacted]",
        text,
    )


def redact(text: str, *, home: Path | None = None) -> str:
    """Everything ``redact_secrets`` does, plus personal and network identifiers.

    For support reports that leave the machine: the home directory becomes ``~``, other
    users' home directories ``/home/<user>``, e-mail addresses, the host name and non-loopback
    IPv4 addresses are replaced.
    """
    text = redact_secrets(text)
    homes = {str(home or Path.home())}
    with contextlib.suppress(OSError):
        homes.add(str((home or Path.home()).resolve()))
    for h in sorted(homes, key=len, reverse=True):
        if h and h != "/":
            text = text.replace(h, "~")
    text = _HOME.sub(lambda m: f"{m.group(1)}<user>", text)
    text = _EMAIL.sub("<email>", text)
    text = _IPV4.sub(_ip, text)
    host = socket.gethostname()
    if host and len(host) > 2 and host not in ("localhost",):
        text = re.sub(rf"\b{re.escape(host)}\b", "<host>", text)
    return text


# --------------------------------------------------------------------------- logging


class RedactingFormatter(logging.Formatter):
    """Never writes secrets or sample arrays; caps the length of a log record."""

    def format(self, record: logging.LogRecord) -> str:
        text = redact_secrets(super().format(record))
        if len(text) > MAX_LOG_MESSAGE:
            text = text[:MAX_LOG_MESSAGE] + f" … [{len(text) - MAX_LOG_MESSAGE} chars truncated]"
        return text


LOG_FORMAT = "%(asctime)s %(levelname)-7s %(name)s: %(message)s"


def configure_logging(level: str, log_file: Path | None) -> None:
    """Root logging for a BrainOS process: stderr + an optional rotating private file."""
    formatter = RedactingFormatter(LOG_FORMAT)
    root = logging.getLogger()
    for h in list(root.handlers):
        root.removeHandler(h)
    stream = logging.StreamHandler()
    stream.setFormatter(formatter)
    root.addHandler(stream)
    if log_file is not None:
        ensure_private_dir(log_file.parent)
        os.close(open_private(log_file, "a"))
        fh = logging.handlers.RotatingFileHandler(
            log_file, maxBytes=LOG_MAX_BYTES, backupCount=LOG_BACKUPS, encoding="utf-8"
        )
        fh.setFormatter(formatter)
        root.addHandler(fh)
    root.setLevel(level)
    # request lines from the console's polling would flood the log; DEBUG shows them
    logging.getLogger("uvicorn.access").setLevel(logging.DEBUG if level == "DEBUG" else "WARNING")
