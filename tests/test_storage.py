"""The database: migrations, backups, and the import of a recording."""

from __future__ import annotations

import hashlib
import sqlite3
from pathlib import Path

import pytest

from coulisses_app import jobs, sessions
from coulisses_app.lock import AlreadyRunningError, hold_data_lock
from coulisses_app.media import UnreadableAudioError
from coulisses_app.paths import DataDir
from coulisses_app.storage import db


def tables(data: DataDir) -> set[str]:
    conn = db.connect(data)
    try:
        rows = conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
        return {r["name"] for r in rows}
    finally:
        conn.close()


def test_a_new_database_gets_the_tables_of_step_1_without_a_backup(tmp_path: Path) -> None:
    data = DataDir(tmp_path)
    assert db.migrate(data) == []
    assert {
        "space",
        "session",
        "audio_source",
        "job",
        "run",
        "run_upstream",
        "active_run",
        "person",
        "attendee",
        "glossary_entry",
        "edit",
    } <= (tables(data))
    assert not data.backups.exists()


def test_migrating_again_changes_nothing(data: DataDir) -> None:
    assert db.migrate(data) == []


def test_a_pending_migration_is_preceded_by_a_backup(
    data: DataDir, monkeypatch: pytest.MonkeyPatch
) -> None:
    shipped = db.migrations()
    extra = (len(shipped) + 1, "9999_essai.sql", "CREATE TABLE essai (id INTEGER PRIMARY KEY);")
    monkeypatch.setattr(db, "migrations", lambda: [*shipped, extra])
    backups = db.migrate(data)
    assert len(backups) == 1
    with sqlite3.connect(backups[0]) as copy:
        names = {r[0] for r in copy.execute("SELECT name FROM sqlite_master")}
    assert "session" in names and "essai" not in names
    assert "essai" in tables(data)


def test_a_failing_migration_leaves_the_database_as_it_was(
    data: DataDir, monkeypatch: pytest.MonkeyPatch
) -> None:
    shipped = db.migrations()
    broken = (len(shipped) + 1, "9999_cassee.sql", "CREATE TABLE a (x); CREATE TABLE a (x);")
    monkeypatch.setattr(db, "migrations", lambda: [*shipped, broken])
    with pytest.raises(sqlite3.Error):
        db.migrate(data)
    assert "a" not in tables(data)
    conn = db.connect(data)
    try:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == len(shipped)
    finally:
        conn.close()


def test_a_database_from_a_newer_application_is_refused(data: DataDir) -> None:
    conn = db.connect(data)
    conn.execute("PRAGMA user_version = 999")
    conn.close()
    with pytest.raises(db.DatabaseTooNewError):
        db.migrate(data)


def test_an_import_keeps_the_file_exactly_and_queues_its_processing(
    data: DataDir, recording: Path
) -> None:
    with recording.open("rb") as f:
        session_id = sessions.import_recording(
            data, f, "Répétition.WAV", unnamed_attendees=4, recorded_at=None, profile="essai"
        )
    stored = data.sources_dir(session_id) / "ref.wav"
    assert stored.read_bytes() == recording.read_bytes()
    source = sessions.reference_source(data, session_id)
    assert source is not None
    assert source.original_name == "Répétition.WAV"
    assert source.sha256 == hashlib.sha256(recording.read_bytes()).hexdigest()
    assert source.sample_rate == 48000 and source.channels == 1
    assert source.duration_s is not None and source.duration_s > 1
    session = sessions.get_session(data, session_id)
    assert session is not None
    assert session.unnamed_attendees == 4
    assert session.min_voices == 4
    assert session.space_name == "Ma troupe"
    assert session.job_state == "queued"
    assert session.title is None  # generated later (step 3), never the folder name


def test_a_session_id_is_dated_and_never_holds_the_title(data: DataDir, recording: Path) -> None:
    with recording.open("rb") as f:
        session_id = sessions.import_recording(
            data, f, "x.wav", unnamed_attendees=None, recorded_at=None, profile="essai"
        )
    date, clock, suffix = session_id.split("-")
    assert len(date) == 8 and len(clock) == 6 and len(suffix) == 4


def test_an_unreadable_file_is_refused_and_leaves_nothing(data: DataDir, tmp_path: Path) -> None:
    fake = tmp_path / "pas-un-son.wav"
    fake.write_text("ceci n'est pas un enregistrement", encoding="utf-8")
    with fake.open("rb") as f, pytest.raises(UnreadableAudioError):
        sessions.import_recording(
            data, f, fake.name, unnamed_attendees=3, recorded_at=None, profile="essai"
        )
    assert sessions.list_sessions(data) == []
    assert list(data.incoming.iterdir()) == []
    assert fake.exists()  # the user's file is never touched


def test_a_failed_import_leaves_nothing_half_made(
    data: DataDir, recording: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def broken(*_: object, **__: object) -> int:
        raise sqlite3.OperationalError("disk I/O error")

    monkeypatch.setattr(jobs, "enqueue_chain", broken)
    with recording.open("rb") as f, pytest.raises(sqlite3.OperationalError):
        sessions.import_recording(
            data, f, "a.wav", unnamed_attendees=None, recorded_at=None, profile="essai"
        )
    assert sessions.list_sessions(data) == []
    assert not (data.root / "sessions").exists() or not any((data.root / "sessions").iterdir())
    leftovers = sessions.interrupted_imports(data)
    assert len(leftovers) == 1 and "Import interrompu" in leftovers[0]


def test_an_unknown_session_folder_is_reported_not_deleted(data: DataDir) -> None:
    stray = data.session_dir("20260101-000000-zzzz")
    stray.mkdir(parents=True)
    assert sessions.interrupted_imports(data) == [f"Dossier de séance inconnu de la base : {stray}"]
    assert stray.is_dir()


def test_only_the_session_deletion_cascades(data: DataDir, recording: Path) -> None:
    with recording.open("rb") as f:
        session_id = sessions.import_recording(
            data, f, "a.wav", unnamed_attendees=None, recorded_at=None, profile="essai"
        )
    conn = db.connect(data)
    try:
        with pytest.raises(sqlite3.IntegrityError), conn:
            conn.execute(
                "INSERT INTO run (id, session_id, job_id, stage, status, producer, created_at)"
                " SELECT 'r1', session_id, id, 'transcribe', 'succeeded', 'engine', 'x' FROM job"
            )
            conn.execute("DELETE FROM job")  # a job with runs cannot vanish alone
        with conn:
            conn.execute("DELETE FROM session WHERE id = ?", (session_id,))
        assert conn.execute("SELECT COUNT(*) FROM job").fetchone()[0] == 0
    finally:
        conn.close()


def test_a_second_application_on_the_same_data_is_refused(data: DataDir) -> None:
    first = hold_data_lock(data)
    try:
        with pytest.raises(AlreadyRunningError):
            hold_data_lock(data)
    finally:
        first.close()
    hold_data_lock(data).close()  # released with its holder


def test_migration_0010_journals_copies_of_the_base_and_keeps_the_rows(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    shipped = db.migrations()
    older = DataDir(tmp_path / "ancienne")
    monkeypatch.setattr(db, "migrations", lambda: [m for m in shipped if m[0] <= 9])
    db.migrate(older)
    conn = db.connect(older)
    with conn:
        conn.execute(
            "INSERT INTO deletion_log (id, at, kind, session_id, session_title, detail)"
            " VALUES (7, '2026-10-01T00:00:00Z', 'conversion', 's', 'Répétition', '{}')"
        )
    conn.close()
    monkeypatch.setattr(db, "migrations", lambda: shipped)
    assert len(db.migrate(older)) == 1

    conn = db.connect(older)
    try:
        row = conn.execute("SELECT * FROM deletion_log").fetchone()
        assert (row["id"], row["kind"], row["session_id"]) == (7, "conversion", "s")
        assert conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'index' AND name = 'deletion_log_by_date'"
        ).fetchone()
        with conn:
            conn.execute(
                "INSERT INTO deletion_log (at, kind, session_id, detail)"
                " VALUES ('2026-10-20T00:00:00Z', 'backup_pruning', NULL, '{}')"
            )
        # A session's deletion still names its session; a copy of the base names none.
        for kind, session_id in (("purge", None), ("backup_pruning", "s")):
            with pytest.raises(sqlite3.IntegrityError, match="CHECK"), conn:
                conn.execute(
                    "INSERT INTO deletion_log (at, kind, session_id, detail)"
                    " VALUES ('2026-10-20T00:00:00Z', ?, ?, '{}')",
                    (kind, session_id),
                )
    finally:
        conn.close()
