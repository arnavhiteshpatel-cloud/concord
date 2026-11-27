"""Thin storage layer: SQLite (stdlib) with WAL, foreign keys and a schema-migrations table.

All SQL in the study package goes through :class:`Database`. Statements use ``?`` placeholders
and portable SQL (TEXT / INTEGER / REAL / BLOB, no SQLite-only functions in queries), so a
Postgres backend can be added by implementing the same five methods (``execute``, ``query``,
``one``, ``tx``, ``migrate``) and translating placeholders. SQLite-specific defence-in-depth
(append-only triggers, demo-mix triggers) lives in the migrations and would be re-expressed as
Postgres triggers / row-level security.

Time stamps are always produced by the *server* clock (``utc_now``), in UTC ISO-8601 with a
``Z`` suffix. Client-supplied times are stored only as data, never as audit time.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterator, Optional

from .schema import MIGRATIONS


def _default_clock() -> datetime:
    return datetime.now(timezone.utc)


def iso(dt: datetime) -> str:
    if dt.tzinfo is None:
        raise ValueError("naive datetime: all NeuroMetric time stamps are timezone-aware UTC")
    return dt.astimezone(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


def parse_iso(s: str) -> datetime:
    """Parse an ISO-8601 time stamp; naive values are rejected (no silent local-time guess)."""
    if not isinstance(s, str):
        raise ValueError("time stamp must be an ISO-8601 string")
    dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        raise ValueError(f"time stamp {s!r} has no UTC offset")
    return dt.astimezone(timezone.utc)


def canonical_json(obj: Any) -> str:
    """Deterministic JSON used for every hash in the system."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                      allow_nan=False, default=str)


def sha256_hex(data: bytes | str) -> str:
    if isinstance(data, str):
        data = data.encode("utf-8")
    return hashlib.sha256(data).hexdigest()


class Database:
    """SQLite connection wrapper (one connection, serialised by a re-entrant lock).

    ``clock`` is injectable for tests (retention, clock-skew); production uses the system UTC
    clock. The same clock is used for every server time stamp.
    """

    dialect = "sqlite"

    def __init__(self, path: str | Path, clock: Optional[Callable[[], datetime]] = None):
        self.path = str(path)
        self.clock = clock or _default_clock
        self._lock = threading.RLock()
        self._depth = 0
        self.conn = sqlite3.connect(self.path, isolation_level=None, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        if self.path != ":memory:":
            self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA foreign_keys=ON")
        self.conn.execute("PRAGMA synchronous=FULL")
        self.conn.execute("PRAGMA busy_timeout=5000")
        self.conn.execute("PRAGMA secure_delete=ON")  # overwrite deleted content (privacy)
        self.migrate()

    # ------------------------------------------------------------------ time
    def now(self) -> datetime:
        dt = self.clock()
        if dt.tzinfo is None:
            raise ValueError("clock must return an aware datetime")
        return dt.astimezone(timezone.utc)

    def now_iso(self) -> str:
        return iso(self.now())

    # ------------------------------------------------------------------ statements
    @contextmanager
    def tx(self) -> Iterator["Database"]:
        """Transaction (nestable: inner blocks join the outer transaction)."""
        with self._lock:
            outer = self._depth == 0
            if outer:
                self.conn.execute("BEGIN IMMEDIATE")
            self._depth += 1
            try:
                yield self
            except BaseException:
                self._depth -= 1
                if outer:
                    self.conn.execute("ROLLBACK")
                raise
            else:
                self._depth -= 1
                if outer:
                    self.conn.execute("COMMIT")

    def execute(self, sql: str, params: tuple | list = ()) -> sqlite3.Cursor:
        with self._lock:
            return self.conn.execute(sql, tuple(params))

    def query(self, sql: str, params: tuple | list = ()) -> list[dict[str, Any]]:
        with self._lock:
            return [dict(r) for r in self.conn.execute(sql, tuple(params)).fetchall()]

    def one(self, sql: str, params: tuple | list = ()) -> Optional[dict[str, Any]]:
        with self._lock:
            r = self.conn.execute(sql, tuple(params)).fetchone()
            return dict(r) if r is not None else None

    def scalar(self, sql: str, params: tuple | list = ()) -> Any:
        with self._lock:
            r = self.conn.execute(sql, tuple(params)).fetchone()
            return r[0] if r is not None else None

    def tables(self) -> list[str]:
        return [r["name"] for r in self.query(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' "
            "ORDER BY name")]

    def columns(self, table: str) -> list[dict[str, Any]]:
        if table not in self.tables():
            raise ValueError(f"unknown table {table!r}")
        return self.query(f"PRAGMA table_info({table})")

    # ------------------------------------------------------------------ migrations
    def migrate(self) -> list[int]:
        """Apply pending migrations in order. Each migration is checksummed; a changed
        already-applied migration is refused (schema drift)."""
        with self._lock:
            self.conn.execute(
                "CREATE TABLE IF NOT EXISTS schema_migrations (version INTEGER PRIMARY KEY, "
                "name TEXT NOT NULL, checksum TEXT NOT NULL, applied_at TEXT NOT NULL)")
            applied = {r["version"]: r for r in self.query("SELECT * FROM schema_migrations")}
            done = []
            for version, name, sql in MIGRATIONS:
                checksum = sha256_hex(sql)
                if version in applied:
                    if applied[version]["checksum"] != checksum:
                        raise RuntimeError(
                            f"migration {version} ({name}) changed after it was applied")
                    continue
                stmt = (f"BEGIN;\n{sql}\nINSERT INTO schema_migrations VALUES "
                        f"({version}, '{name}', '{checksum}', '{self.now_iso()}');\nCOMMIT;")
                try:
                    self.conn.executescript(stmt)
                except Exception:
                    if self.conn.in_transaction:
                        self.conn.execute("ROLLBACK")
                    raise
                done.append(version)
            return done

    def schema_version(self) -> int:
        return int(self.scalar("SELECT COALESCE(MAX(version), 0) FROM schema_migrations"))

    def close(self) -> None:
        with self._lock:
            self.conn.close()
