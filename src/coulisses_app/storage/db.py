"""The SQLite database: connection, forward-only migrations, backup before each (ADR 0018)."""

from __future__ import annotations

import json
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


class MigrationMismatchError(RuntimeError):
    """The database received, under a number, another migration than this application's (two
    branches that each made their own): refused at start rather than failing later."""


APPLIED_KEY = "applied_migrations"
"""Key of `app_setting`: {version: file name} of each migration applied since this key exists.
A database migrated before has no names for its earlier migrations: those are not checked,
never refused on a guess."""

_APP_SETTING_SINCE = 3
"""The migration that creates `app_setting` (0003): from it on, the names are written."""


def _applied(conn: sqlite3.Connection) -> dict[int, str]:
    if not conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'app_setting'"
    ).fetchone():
        return {}
    row = conn.execute("SELECT value FROM app_setting WHERE key = ?", (APPLIED_KEY,)).fetchone()
    if row is None:
        return {}
    try:
        found = json.loads(row[0])
        return {int(version): str(name) for version, name in found.items()}
    except (ValueError, AttributeError) as exc:
        raise MigrationMismatchError(
            f"La liste des migrations reçues par la base est illisible ({exc}). "
            "Revenez à une copie de la base, ou signalez-le."
        ) from exc


def _check_names(database: Path, applied: dict[int, str], shipped: dict[int, str]) -> None:
    for version, name in sorted(applied.items()):
        ours = shipped.get(version)
        if ours is not None and ours != name:
            raise MigrationMismatchError(
                f"La base {database} a reçu la migration « {name} », mais cette version de"
                f" Coulisses a « {ours} » sous le même numéro : elle a été mise à jour par une"
                " autre version de l'application. Utilisez celle-là, ou revenez à une copie de"
                " la base faite avant cette migration."
            )


def _record(applied: dict[int, str]) -> str:
    """SQL writing the names, in the transaction of the migration it follows."""
    value = json.dumps({str(v): n for v, n in sorted(applied.items())}).replace("'", "''")
    key = APPLIED_KEY.replace("'", "''")
    return (
        f"INSERT INTO app_setting (key, value) VALUES ('{key}', '{value}')"
        " ON CONFLICT (key) DO UPDATE SET value = excluded.value;"
    )


def check(database: Path) -> None:
    """Whether this application can take that database as it is, before it replaces another
    (`rapatrier-donnees.py`): not newer, the same migrations under the same numbers."""
    shipped = migrations()
    latest = shipped[-1][0] if shipped else 0
    conn = sqlite3.connect(f"file:{database}?mode=ro", uri=True)
    try:
        current: int = conn.execute("PRAGMA user_version").fetchone()[0]
        if current > latest:
            raise DatabaseTooNewError(
                f"La base {database} est en version {current}, plus récente que cette "
                f"application ({latest}). Mettez l'application à jour."
            )
        _check_names(database, _applied(conn), {v: name for v, name, _ in shipped})
    finally:
        conn.close()


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
        applied = _applied(conn)
        _check_names(data.database, applied, {v: name for v, name, _ in pending_all})
        pending = [m for m in pending_all if m[0] > current]
        if not pending:
            return []
        backups: list[Path] = []
        if current > 0:
            backups.append(_backup(conn, data, before=pending[0][0]))
        for version, name, sql in pending:
            log.info("applying migration %s", name)
            applied[version] = name
            names = _record(applied) if version >= _APP_SETTING_SINCE else ""
            try:
                conn.executescript(
                    f"BEGIN;\n{sql}\n{names}\nPRAGMA user_version = {version};\nCOMMIT;"
                )
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
