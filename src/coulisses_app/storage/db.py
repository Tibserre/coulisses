"""The SQLite database: connection, forward-only migrations, backup before each (ADR 0018)."""

from __future__ import annotations

import logging
import re
import sqlite3
from datetime import UTC, datetime
from importlib.resources import files
from pathlib import Path

from coulisses_app.paths import DataDir

log = logging.getLogger(__name__)

_MIGRATION_NAME = re.compile(r"^(\d{4})_[a-z0-9_]+\.sql$")


ISO_FORMAT = "%Y-%m-%dT%H:%M:%SZ"
"""Times in the database: UTC, to the second; compared as text."""


def now_iso() -> str:
    return datetime.now(UTC).strftime(ISO_FORMAT)


def connect(data: DataDir) -> sqlite3.Connection:
    """A connection for one unit of work. Each thread opens its own."""
    conn = sqlite3.connect(data.database, timeout=10.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA busy_timeout = 10000")
    return conn


def migrations() -> list[tuple[int, str, str]]:
    """(version, file name, SQL) of every migration shipped with the application, in order."""
    found: list[tuple[int, str, str]] = []
    for entry in files("coulisses_app.storage.migrations").iterdir():
        match = _MIGRATION_NAME.match(entry.name)
        if match:
            found.append((int(match.group(1)), entry.name, entry.read_text(encoding="utf-8")))
    found.sort()
    versions = [v for v, _, _ in found]
    if versions != list(range(1, len(versions) + 1)):
        raise RuntimeError(f"migrations must be numbered 0001, 0002… without gaps: {versions}")
    return found


class DatabaseTooNewError(RuntimeError):
    """The database was migrated by a newer version of the application."""


def migrate(data: DataDir) -> list[Path]:
    """Bring the database to the latest schema. Returns the backups made (one per run of
    pending migrations on an existing database); a new database needs none."""
    data.root.mkdir(parents=True, exist_ok=True)
    pending_all = migrations()
    latest = pending_all[-1][0] if pending_all else 0
    conn = connect(data)
    try:
        current: int = conn.execute("PRAGMA user_version").fetchone()[0]
        if current > latest:
            raise DatabaseTooNewError(
                f"La base {data.database} est en version {current}, plus récente que cette "
                f"application ({latest}). Mettez l'application à jour."
            )
        pending = [m for m in pending_all if m[0] > current]
        if not pending:
            return []
        backups: list[Path] = []
        if current > 0:
            backups.append(_backup(conn, data, before=pending[0][0]))
        for version, name, sql in pending:
            log.info("applying migration %s", name)
            try:
                conn.executescript(f"BEGIN;\n{sql}\nPRAGMA user_version = {version};\nCOMMIT;")
            except sqlite3.Error:
                if conn.in_transaction:
                    conn.rollback()
                raise
        return backups
    finally:
        conn.close()


def _backup(conn: sqlite3.Connection, data: DataDir, before: int) -> Path:
    data.backups.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S")
    target = data.backups / f"coulisses-avant-{before:04d}-{stamp}.db"
    with sqlite3.connect(target) as copy:
        conn.backup(copy)
    copy.close()
    log.info("database saved to %s before migration %04d", target, before)
    return target
