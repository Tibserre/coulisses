"""Keeping the audio, purging it when due, and deleting by hand (spec §7.10, ADR 0029).

The audio of a processed session is kept `retention_days` from the day it entered the
application (import or recording), or longer if the user extended it, or forever if the
user chose « Garder l'audio ». A coming purge is announced first (banner, macOS
notification) and only happens once the notice has run its course from that announcement:
nothing older ever disappears unannounced. A purge removes the audio files only; the text,
the corrections and the summaries stay (P5).

Deleting a session by hand removes everything: its rows, its folder, and its rows in the
backup copies of the database too. Every purge and deletion is written in `deletion_log`,
which keeps no text of a deleted session (P8: visible, never silent).
"""

from __future__ import annotations

import json
import logging
import re
import shutil
import sqlite3
import subprocess
import sys
import threading
import time
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Literal

from pydantic import BaseModel

from coulisses_app.paths import DataDir
from coulisses_app.spaces import NotFoundError, SpaceError
from coulisses_app.storage.db import connect, now_iso

log = logging.getLogger(__name__)

RETENTION_KEY = "conservation_jours"
NOTICE_KEY = "preavis_jours"
DEFAULT_RETENTION_DAYS = 90
DEFAULT_NOTICE_DAYS = 7

AudioState = Literal["kept", "removed", "scheduled", "announced", "never_processed"]


class RetentionSettings(BaseModel):
    retention_days: int
    notice_days: int


class AudioStatus(BaseModel):
    """What becomes of a session's audio, as the interface says it."""

    state: AudioState
    """kept: « Garder l'audio »; removed: gone (`removed_reason`); never_processed: never
    purged until its processing succeeds; scheduled: due on `purge_on`; announced: the
    purge was announced, it happens on `purge_on`."""
    purge_on: str | None = None
    removed_at: str | None = None
    removed_reason: Literal["purge", "audio_deletion"] | None = None


class LogEntry(BaseModel):
    id: int
    at: str
    kind: Literal["purge", "audio_deletion", "session_deletion"]
    session_id: str
    session_title: str | None
    files: int
    bytes: int
    problems: list[str]
    """What could not be done: an incomplete deletion is said, never shown as done."""


class Backup(BaseModel):
    name: str
    """The file's name (developer mode)."""
    made_on: str
    """Its day, as the user reads it."""
    bytes: int


class DeletionError(SpaceError):
    """A deletion that could not be done (in full); the message is shown to the user."""


# -- settings -------------------------------------------------------------------------------


def _setting(conn: sqlite3.Connection, key: str, default: int) -> int:
    row = conn.execute("SELECT value FROM app_setting WHERE key = ?", (key,)).fetchone()
    return int(json.loads(row[0])) if row else default


def get_settings(conn: sqlite3.Connection) -> RetentionSettings:
    return RetentionSettings(
        retention_days=_setting(conn, RETENTION_KEY, DEFAULT_RETENTION_DAYS),
        notice_days=_setting(conn, NOTICE_KEY, DEFAULT_NOTICE_DAYS),
    )


def set_settings(conn: sqlite3.Connection, retention_days: int, notice_days: int) -> None:
    if retention_days < 1:
        raise SpaceError("L'audio se garde au moins un jour.")
    if not 1 <= notice_days <= retention_days:
        raise SpaceError("Le préavis va d'un jour à la durée de conservation.")
    with conn:
        for key, value in ((RETENTION_KEY, retention_days), (NOTICE_KEY, notice_days)):
            conn.execute(
                "INSERT INTO app_setting (key, value) VALUES (?, ?)"
                " ON CONFLICT (key) DO UPDATE SET value = excluded.value",
                (key, json.dumps(value)),
            )
        # A shorter delay is announced again from now: never a purge without its notice.
        conn.execute("UPDATE session SET purge_announced_at = NULL")


# -- when -----------------------------------------------------------------------------------


def _parse(iso: str) -> datetime:
    return datetime.fromisoformat(iso.replace("Z", "+00:00"))


def _iso(when: datetime) -> str:
    return when.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _processed(conn: sqlite3.Connection, session_id: str) -> bool:
    """Its processing succeeded (a « who said what » version exists): only then is its audio
    ever purged (spec §7.10)."""
    return (
        conn.execute(
            "SELECT 1 FROM active_run WHERE session_id = ? AND stage = 'attribute'", (session_id,)
        ).fetchone()
        is not None
    )


def _due(row: sqlite3.Row, settings: RetentionSettings) -> datetime:
    due = _parse(row["created_at"]) + timedelta(days=settings.retention_days)
    if row["retain_until"]:
        due = max(due, _parse(row["retain_until"]))
    return due


def _purge_on(row: sqlite3.Row, settings: RetentionSettings) -> datetime:
    """The day the purge happens: when due, and never before the notice has run its course
    from its announcement (an announcement still to come counts from today)."""
    due = _due(row, settings)
    announced = _parse(row["purge_announced_at"]) if row["purge_announced_at"] else None
    if announced is None:
        return due
    return max(due, announced + timedelta(days=settings.notice_days))


def status_of(
    conn: sqlite3.Connection, row: sqlite3.Row, settings: RetentionSettings, now: datetime
) -> AudioStatus:
    """`row`: the session's row (`session.*`)."""
    if row["audio_removed_at"]:
        return AudioStatus(
            state="removed",
            removed_at=row["audio_removed_at"],
            removed_reason=row["audio_removed_reason"],
        )
    if row["keep_audio"]:
        return AudioStatus(state="kept")
    if not _processed(conn, row["id"]):
        return AudioStatus(state="never_processed")
    when = _purge_on(row, settings)
    if row["purge_announced_at"] is None and when - now > timedelta(days=settings.notice_days):
        return AudioStatus(state="scheduled", purge_on=_iso(when))
    if row["purge_announced_at"] is None:
        # Not announced yet: it will be at the next check, the notice counting from then.
        when = max(when, now + timedelta(days=settings.notice_days))
        return AudioStatus(state="scheduled", purge_on=_iso(when))
    return AudioStatus(state="announced", purge_on=_iso(when))


def audio_status(data: DataDir, session_id: str, now: datetime | None = None) -> AudioStatus:
    conn = connect(data)
    try:
        row = conn.execute("SELECT * FROM session WHERE id = ?", (session_id,)).fetchone()
        if row is None:
            raise NotFoundError("Séance introuvable.")
        return status_of(conn, row, get_settings(conn), now or datetime.now(UTC))
    finally:
        conn.close()


# -- the user's choices ---------------------------------------------------------------------


def keep_audio(data: DataDir, session_id: str, keep: bool) -> None:
    """« Garder l'audio » on or off. Off, the delay counts again from its entry date, and a
    purge is announced again before it happens."""
    conn = connect(data)
    try:
        with conn:
            done = conn.execute(
                "UPDATE session SET keep_audio = ?, purge_announced_at = NULL WHERE id = ?",
                (int(keep), session_id),
            ).rowcount
        if not done:
            raise NotFoundError("Séance introuvable.")
    finally:
        conn.close()


def extend(data: DataDir, session_id: str, now: datetime | None = None) -> None:
    """« Prolonger » : the audio kept a whole retention delay from today."""
    conn = connect(data)
    try:
        settings = get_settings(conn)
        until = (now or datetime.now(UTC)) + timedelta(days=settings.retention_days)
        with conn:
            done = conn.execute(
                "UPDATE session SET retain_until = ?, purge_announced_at = NULL WHERE id = ?",
                (_iso(until), session_id),
            ).rowcount
        if not done:
            raise NotFoundError("Séance introuvable.")
    finally:
        conn.close()


# -- removing -------------------------------------------------------------------------------


def _busy(conn: sqlite3.Connection, session_id: str, *, waiting_counts: bool) -> str | None:
    """Why the session cannot lose its files now, if it cannot. `waiting_counts`: a
    processing waiting in the queue needs the audio too (the session's deletion takes its
    queue with it)."""
    if conn.execute(
        "SELECT 1 FROM audio_source WHERE session_id = ? AND capture_state = 'recording'",
        (session_id,),
    ).fetchone():
        return "La séance est en train d'être enregistrée : arrêtez l'enregistrement d'abord."
    if conn.execute(
        "SELECT 1 FROM job WHERE session_id = ? AND state = 'running'", (session_id,)
    ).fetchone():
        return "Un traitement de cette séance est en cours : attendez qu'il se termine."
    if (
        waiting_counts
        and conn.execute(
            "SELECT 1 FROM job WHERE session_id = ? AND kind = 'chain' AND state = 'queued'",
            (session_id,),
        ).fetchone()
    ):
        return (
            "Un traitement de cette séance attend son tour et a besoin de l'audio : "
            "attendez qu'il se termine."
        )
    return None


def _name(row: sqlite3.Row) -> str:
    """How the user knows the session: its title, else its date."""
    if row["title"]:
        return f"« {row['title']} »"
    return f"la séance du {_day(row['recorded_at'][:10])}"


def _files(folder: Path) -> list[tuple[Path, int]]:
    if not folder.is_dir():
        return []
    return sorted((p, p.stat().st_size) for p in folder.rglob("*") if p.is_file())


def _log(
    conn: sqlite3.Connection,
    kind: str,
    session_id: str,
    title: str | None,
    files: list[tuple[Path, int]],
    root: Path,
) -> int:
    detail = {
        "files": [{"path": str(p.relative_to(root)), "bytes": size} for p, size in files],
        "bytes": sum(size for _, size in files),
        "problems": [],
    }
    cursor = conn.execute(
        "INSERT INTO deletion_log (at, kind, session_id, session_title, detail)"
        " VALUES (?, ?, ?, ?, ?)",
        (now_iso(), kind, session_id, title, json.dumps(detail, ensure_ascii=False)),
    )
    assert cursor.lastrowid is not None
    return cursor.lastrowid


def _log_problems(data: DataDir, log_id: int, problems: list[str]) -> None:
    conn = connect(data)
    try:
        with conn:
            conn.execute(
                "UPDATE deletion_log SET detail = json_set(detail, '$.problems', json(?))"
                " WHERE id = ?",
                (json.dumps(problems, ensure_ascii=False), log_id),
            )
    finally:
        conn.close()


class NotDueError(DeletionError):
    """A purge no longer due when it was about to happen (kept, extended, or announced
    again meanwhile): nothing is removed."""


def remove_audio(
    data: DataDir,
    session_id: str,
    reason: Literal["purge", "audio_deletion"],
    now: datetime | None = None,
) -> list[str]:
    """Remove every audio file of the session (the originals; runs hold none, engine
    guarantee since v1.2.0). The text stays. Written in the deletion log. Returns what
    stayed on the disk (said and logged); the audio is gone from Coulisses anyway.

    Decided under the database's write lock: no processing can be claimed meanwhile, and a
    purge is checked once more against the user's latest choice (« Garder l'audio »,
    « Prolonger »). The session says the audio is gone before its files go: a processing
    claimed afterwards finds it so, never a file half deleted."""
    now = now or datetime.now(UTC)
    conn = connect(data)
    try:
        conn.execute("BEGIN IMMEDIATE")
        try:
            row = conn.execute("SELECT * FROM session WHERE id = ?", (session_id,)).fetchone()
            if row is None:
                raise NotFoundError("Séance introuvable.")
            if row["audio_removed_at"]:
                raise DeletionError("L'audio de cette séance est déjà supprimé.")
            if (why := _busy(conn, session_id, waiting_counts=True)) is not None:
                raise DeletionError(why)
            if reason == "purge" and (
                row["keep_audio"]
                or row["purge_announced_at"] is None
                or not _processed(conn, session_id)
                or _purge_on(row, get_settings(conn)) > now
            ):
                raise NotDueError("La purge de cette séance n'est plus due.")
            files = _files(data.sources_dir(session_id))
            log_id = _log(
                conn, reason, session_id, row["title"], files, data.session_dir(session_id)
            )
            stamp = now_iso()
            conn.execute(
                "UPDATE session SET audio_removed_at = ?, audio_removed_reason = ?,"
                " purge_announced_at = NULL WHERE id = ?",
                (stamp, reason, session_id),
            )
            conn.execute(
                "UPDATE audio_source SET removed_at = ? WHERE session_id = ?"
                " AND removed_at IS NULL",
                (stamp, session_id),
            )
            conn.commit()
        except BaseException:
            conn.rollback()
            raise
    finally:
        conn.close()
    problems: list[str] = []
    for path, _ in files:
        try:
            path.unlink()
        except FileNotFoundError:
            pass  # already gone (the Finder): what was asked is done
        except OSError as exc:
            problems.append(f"un fichier audio n'a pas pu être effacé ({exc.strerror or exc})")
    if problems:
        _log_problems(data, log_id, problems)
    return problems


def _checkpoint(conn: sqlite3.Connection) -> bool:
    """Empty the database's journal (WAL), where a deleted session's pages may still be.
    Retried while another connection reads."""
    for _ in range(10):
        busy, _, _ = conn.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()
        if not busy:
            return True
        time.sleep(0.2)
    return False


def delete_session(data: DataDir, session_id: str) -> list[str]:
    """Delete a session entirely, processed or not: its rows (corrections, notes, summaries
    with them), its folder, and its rows in the backup copies of the database. Securely:
    what SQLite frees is overwritten, the journal emptied. The log keeps no text of it.
    Returns what could not be done on the disk (said to the user and logged); the session
    itself is gone from Coulisses."""
    conn = connect(data)
    try:
        conn.execute("PRAGMA secure_delete = ON")
        conn.execute("BEGIN IMMEDIATE")
        try:
            row = conn.execute("SELECT id FROM session WHERE id = ?", (session_id,)).fetchone()
            if row is None:
                raise NotFoundError("Séance introuvable.")
            if (why := _busy(conn, session_id, waiting_counts=False)) is not None:
                raise DeletionError(why)
            folder = data.session_dir(session_id)
            files = _files(folder)
            log_id = _log(conn, "session_deletion", session_id, None, files, folder)
            conn.execute("DELETE FROM session WHERE id = ?", (session_id,))
            conn.commit()
        except BaseException:
            conn.rollback()
            raise
        problems: list[str] = []
        if not _checkpoint(conn):
            problems.append(
                "le journal de la base n'a pas pu être vidé tout de suite ; il le sera à la "
                "prochaine fermeture de Coulisses"
            )
    finally:
        conn.close()
    if folder.exists():
        try:
            shutil.rmtree(folder)
        except OSError as exc:
            problems.append(f"le dossier de la séance : {exc.strerror or exc}")
    problems += _forget_in_backups(data, session_id)
    if problems:
        _log_problems(data, log_id, problems)
    return problems


def _forget_in_backups(data: DataDir, session_id: str) -> list[str]:
    """The session's rows removed from each backup copy of the database, which then is
    compacted (nothing of it left in its free pages)."""
    problems: list[str] = []
    if not data.backups.is_dir():
        return problems
    for backup in sorted(data.backups.glob("*.db")):
        try:
            copy = sqlite3.connect(backup)
            try:
                copy.execute("PRAGMA foreign_keys = ON")
                with copy:
                    found = copy.execute("DELETE FROM session WHERE id = ?", (session_id,)).rowcount
                if found:
                    copy.execute("VACUUM")
            finally:
                copy.close()
        except sqlite3.Error as exc:
            problems.append(f"la sauvegarde du {_backup_day(backup)} : {exc}")
    return problems


# -- the purge ------------------------------------------------------------------------------


class Announcement(BaseModel):
    session_id: str
    title: str | None
    recorded_at: str
    purge_on: str


class CheckResult(BaseModel):
    announced: list[Announcement]
    """Purges announced by this check (to notify)."""
    purged: list[str]
    problems: list[str]


def check(data: DataDir, now: datetime | None = None) -> CheckResult:
    """Announce the purges coming within the notice, and purge what is due and was
    announced long enough ago. Run at start, then every hour."""
    now = now or datetime.now(UTC)
    conn = connect(data)
    try:
        settings = get_settings(conn)
        rows = conn.execute(
            "SELECT * FROM session WHERE keep_audio = 0 AND audio_removed_at IS NULL"
        ).fetchall()
        announced: list[Announcement] = []
        due: list[tuple[str, str]] = []
        for row in rows:
            if not _processed(conn, row["id"]):
                continue
            if row["purge_announced_at"] is None:
                if _due(row, settings) - now <= timedelta(days=settings.notice_days):
                    with conn:
                        conn.execute(
                            "UPDATE session SET purge_announced_at = ? WHERE id = ?",
                            (_iso(now), row["id"]),
                        )
                    when = max(_due(row, settings), now + timedelta(days=settings.notice_days))
                    announced.append(
                        Announcement(
                            session_id=row["id"],
                            title=row["title"],
                            recorded_at=row["recorded_at"],
                            purge_on=_iso(when),
                        )
                    )
                continue
            if _purge_on(row, settings) <= now:
                due.append((row["id"], _name(row)))
    finally:
        conn.close()
    purged: list[str] = []
    problems: list[str] = []
    for session_id, name in due:
        try:
            left = remove_audio(data, session_id, "purge", now)
            purged.append(session_id)
            problems += [f"Purge de l'audio de {name} : {p}" for p in left]
        except NotDueError:
            continue  # kept or extended in the meantime: nothing to do, nothing to say
        except SpaceError as exc:
            # Busy (recording, processing) or a file that would not go: tried again at the
            # next check, and said (P8).
            problems.append(f"Purge de l'audio de {name} : {exc}")
    return CheckResult(announced=announced, purged=purged, problems=problems)


def coming(data: DataDir, now: datetime | None = None) -> list[Announcement]:
    """The purges announced and not done yet: the banner's list."""
    now = now or datetime.now(UTC)
    conn = connect(data)
    try:
        settings = get_settings(conn)
        rows = conn.execute(
            "SELECT * FROM session WHERE keep_audio = 0 AND audio_removed_at IS NULL"
            " AND purge_announced_at IS NOT NULL ORDER BY recorded_at"
        ).fetchall()
        return [
            Announcement(
                session_id=r["id"],
                title=r["title"],
                recorded_at=r["recorded_at"],
                purge_on=_iso(_purge_on(r, settings)),
            )
            for r in rows
        ]
    finally:
        conn.close()


def journal(data: DataDir, limit: int = 200) -> list[LogEntry]:
    conn = connect(data)
    try:
        rows = conn.execute(
            "SELECT * FROM deletion_log ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
    finally:
        conn.close()
    entries: list[LogEntry] = []
    for r in rows:
        detail = json.loads(r["detail"])
        entries.append(
            LogEntry(
                id=r["id"],
                at=r["at"],
                kind=r["kind"],
                session_id=r["session_id"],
                session_title=r["session_title"],
                files=len(detail.get("files", [])),
                bytes=int(detail.get("bytes", 0)),
                problems=[str(p) for p in detail.get("problems", [])],
            )
        )
    return entries


def backups(data: DataDir) -> list[Backup]:
    if not data.backups.is_dir():
        return []
    return [
        Backup(name=p.name, made_on=_backup_day(p), bytes=p.stat().st_size)
        for p in sorted(data.backups.glob("*.db"))
    ]


_BACKUP_DATE = re.compile(r"(\d{4})(\d{2})(\d{2})T")


def _backup_day(path: Path) -> str:
    """« 7 octobre 2026 », from the backup's name (`…-20261007T094553.db`), else its file."""
    found = _BACKUP_DATE.search(path.name)
    if found:
        day = f"{found.group(1)}-{found.group(2)}-{found.group(3)}"
    else:
        day = datetime.fromtimestamp(path.stat().st_mtime, UTC).strftime("%Y-%m-%d")
    return f"{_day(day)} {day[:4]}"


# -- telling the user -----------------------------------------------------------------------


def notify(announced: list[Announcement], run: Callable[[list[str]], object] | None = None) -> None:
    """A macOS notification for the purges just announced (the banner says it too). A
    notification that cannot be shown is logged; the banner stays."""
    if not announced or sys.platform != "darwin":
        return
    count = len(announced)
    days = {a.purge_on[:10] for a in announced}
    first = min(days)
    text = (
        f"L'audio d'une séance sera supprimé le {_day(first)}."
        if count == 1
        else f"L'audio de {count} séances sera supprimé à partir du {_day(first)}."
    ) + " Ouvrez Coulisses pour le garder ou prolonger."
    command = [
        "osascript",
        "-e",
        "on run argv",
        "-e",
        'display notification (item 1 of argv) with title "Coulisses"',
        "-e",
        "end run",
        text,
    ]
    try:
        if run is not None:
            run(command)
        else:
            subprocess.run(command, check=True, timeout=10)
    except (OSError, subprocess.SubprocessError) as exc:
        log.warning("purge notification not shown: %s", exc)


def _day(iso_date: str) -> str:
    months = (
        "janvier",
        "février",
        "mars",
        "avril",
        "mai",
        "juin",
        "juillet",
        "août",
        "septembre",
        "octobre",
        "novembre",
        "décembre",
    )
    when = datetime.fromisoformat(iso_date)
    return f"{when.day} {months[when.month - 1]}"


class Watcher:
    """Checks the purges at start, then every hour, in a background thread; a coming purge
    is notified once, when announced."""

    def __init__(
        self,
        data: DataDir,
        *,
        every_s: float = 3600.0,
        notifier: Callable[[list[Announcement]], None] = notify,
    ) -> None:
        self.data = data
        self.every_s = every_s
        self.notifier = notifier
        self.problems: list[str] = []
        """What the last check could not do (shown in the settings, P8)."""
        self._stop = threading.Event()
        self._running = threading.Lock()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        self._thread = threading.Thread(target=self._loop, name="coulisses-retention", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=5)

    def run_once(self) -> CheckResult:
        """One check at a time (the hourly one, or one asked after a change of settings)."""
        with self._running:
            return self._run()

    def _run(self) -> CheckResult:
        result = check(self.data)
        self.notifier(result.announced)
        for session_id in result.purged:
            log.info("audio of %s purged (retention)", session_id)
        self.problems = result.problems
        return result

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                self.run_once()
            # The watch must outlive an error (a locked database…): logged, shown, retried.
            except Exception as exc:
                log.exception("retention check failed")
                self.problems = [f"La vérification de la conservation a échoué : {exc}"]
            self._stop.wait(self.every_s)
