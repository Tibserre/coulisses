"""Keeping the audio, the purge with its notice, deleting by hand (step 9, ADR 0029)."""

from __future__ import annotations

import json
import sqlite3
import threading
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from coulisses_app import corrections, jobs, retention, sessions, versions
from coulisses_app.api import create_app
from coulisses_app.paths import DataDir
from coulisses_app.processing import Processor
from coulisses_app.spaces import SpaceError
from coulisses_app.storage.db import connect

from .conftest import FAKE_CHAIN, local_client
from .test_versions import claim, processed

NOW = datetime(2026, 10, 7, 12, 0, tzinfo=UTC)


def entered(data: DataDir, session_id: str, days_ago: float) -> None:
    """As if the session had entered the application that long ago."""
    when = (NOW - timedelta(days=days_ago)).strftime("%Y-%m-%dT%H:%M:%SZ")
    conn = connect(data)
    try:
        with conn:
            conn.execute("UPDATE session SET created_at = ? WHERE id = ?", (when, session_id))
    finally:
        conn.close()


def log_rows(data: DataDir) -> list[sqlite3.Row]:
    conn = connect(data)
    try:
        return conn.execute("SELECT * FROM deletion_log ORDER BY id").fetchall()
    finally:
        conn.close()


def sources(data: DataDir, session_id: str) -> list[Path]:
    return sorted(data.sources_dir(session_id).iterdir())


# -- removing the audio ----------------------------------------------------------------------


def test_removing_the_audio_keeps_the_text_and_says_it(data: DataDir, recording: Path) -> None:
    session_id = processed(data, recording)
    corrections.add(data, session_id, {"kind": "assign_speaker", "speaker": "S1", "name": "Marie"})
    size = sum(p.stat().st_size for p in sources(data, session_id))

    retention.remove_audio(data, session_id, "audio_deletion")

    assert sources(data, session_id) == []
    view = corrections.build_view(data, session_id)
    assert view is not None and view.speakers[0].name == "Marie"  # the text stays
    status = retention.audio_status(data, session_id)
    assert (status.state, status.removed_reason) == ("removed", "audio_deletion")
    [row] = log_rows(data)
    detail = json.loads(row["detail"])
    assert (row["kind"], detail["bytes"], detail["problems"]) == ("audio_deletion", size, [])
    # Corrections still work; the transcription and the voices cannot be redone.
    corrections.add(data, session_id, {"kind": "edit_text", "turn": 0, "text": "bonjour Kathy"})
    with pytest.raises(SpaceError, match="supprimé"):
        versions.request_rerun(data, session_id, "transcribe", attendees=None, profile="essai")
    assert versions.list_versions(data, session_id).rerun.possible is False
    with pytest.raises(retention.DeletionError, match="déjà supprimé"):
        retention.remove_audio(data, session_id, "audio_deletion")

    client = local_client(
        create_app(data, FAKE_CHAIN, profile="essai", processor=None, web_dir=None)
    )
    assert client.get(f"/api/seances/{session_id}/audio").status_code == 404
    listed = client.get(f"/api/seances/{session_id}").json()["session"]["audio"]
    assert listed["state"] == "removed"


def test_nothing_is_removed_while_recording_or_processing(data: DataDir, recording: Path) -> None:
    session_id = processed(data, recording)
    versions.request_rerun(data, session_id, "transcribe", attendees=None, profile="essai")
    job = claim(data)  # now running
    with pytest.raises(retention.DeletionError, match="en cours"):
        retention.remove_audio(data, session_id, "audio_deletion")
    with pytest.raises(retention.DeletionError, match="en cours"):
        retention.delete_session(data, session_id)
    Processor(data, FAKE_CHAIN).run_job(job)
    assert sources(data, session_id)
    conn = connect(data)
    try:
        with conn:
            conn.execute(
                "UPDATE audio_source SET capture_state = 'recording' WHERE session_id = ?",
                (session_id,),
            )
    finally:
        conn.close()
    with pytest.raises(retention.DeletionError, match="enregistrée"):
        retention.delete_session(data, session_id)


# -- deleting a session ----------------------------------------------------------------------


def test_deleting_a_session_removes_everything_backups_included(
    data: DataDir, recording: Path
) -> None:
    session_id = processed(data, recording)
    corrections.add(data, session_id, {"kind": "assign_speaker", "speaker": "S1", "name": "Marie"})
    data.backups.mkdir(parents=True, exist_ok=True)
    backup = data.backups / "coulisses-avant-0008-test.db"
    source = connect(data)
    try:
        copy = sqlite3.connect(backup)
        source.backup(copy)
        copy.close()
    finally:
        source.close()

    assert retention.delete_session(data, session_id) == []

    assert not data.session_dir(session_id).exists()
    conn = connect(data)
    try:
        for table in ("session", "edit", "run", "job", "audio_source"):
            count = conn.execute(
                f"SELECT COUNT(*) FROM {table} WHERE {'id' if table == 'session' else 'session_id'} = ?",  # noqa: E501
                (session_id,),
            ).fetchone()[0]
            assert count == 0, table
    finally:
        conn.close()
    copy = sqlite3.connect(backup)
    try:
        assert copy.execute("SELECT COUNT(*) FROM session").fetchone()[0] == 0
        assert copy.execute("SELECT COUNT(*) FROM edit").fetchone()[0] == 0
    finally:
        copy.close()
    assert b"Marie" not in backup.read_bytes()  # compacted: nothing left in free pages
    [row] = log_rows(data)
    assert (row["kind"], row["session_id"], row["session_title"]) == (
        "session_deletion",
        session_id,
        None,
    )
    assert json.loads(row["detail"])["bytes"] > 0


def test_a_session_never_processed_can_be_deleted(data: DataDir, recording: Path) -> None:
    with recording.open("rb") as f:
        session_id = sessions.import_recording(
            data, f, recording.name, unnamed_attendees=1, recorded_at=None, profile="essai"
        )
    client = local_client(
        create_app(data, FAKE_CHAIN, profile="essai", processor=None, web_dir=None)
    )
    deleted = client.delete(f"/api/seances/{session_id}")
    assert (deleted.status_code, deleted.json()) == (200, {"problems": []})
    assert sessions.get_session(data, session_id) is None
    conn = connect(data)
    try:
        assert conn.execute("SELECT COUNT(*) FROM job").fetchone()[0] == 0
    finally:
        conn.close()
    assert client.delete(f"/api/seances/{session_id}").status_code == 404


# -- the purge ---------------------------------------------------------------------------


def test_the_purge_is_announced_first_and_happens_after_the_notice(
    data: DataDir, recording: Path
) -> None:
    session_id = processed(data, recording)
    entered(data, session_id, days_ago=200)  # long overdue: still announced before anything

    first = retention.check(data, NOW)
    assert [a.session_id for a in first.announced] == [session_id]
    assert first.purged == []
    assert first.announced[0].purge_on == "2026-10-14T12:00:00Z"
    assert retention.audio_status(data, session_id, NOW).state == "announced"
    assert [a.session_id for a in retention.coming(data, NOW)] == [session_id]

    again = retention.check(data, NOW + timedelta(days=6, hours=23))
    assert (again.announced, again.purged) == ([], [])  # announced once, not yet due
    assert sources(data, session_id)

    due = retention.check(data, NOW + timedelta(days=7))
    assert due.purged == [session_id]
    assert sources(data, session_id) == []
    status = retention.audio_status(data, session_id)
    assert (status.state, status.removed_reason) == ("removed", "purge")
    assert [r["kind"] for r in log_rows(data)] == ["purge"]


def test_a_recent_session_is_scheduled_not_announced(data: DataDir, recording: Path) -> None:
    session_id = processed(data, recording)
    entered(data, session_id, days_ago=10)
    assert retention.check(data, NOW).announced == []
    status = retention.audio_status(data, session_id, NOW)
    assert (status.state, status.purge_on) == ("scheduled", "2026-12-26T12:00:00Z")  # +80 days


def test_kept_or_extended_audio_is_not_purged(data: DataDir, recording: Path) -> None:
    kept = processed(data, recording)
    extended = processed(data, recording)
    for session_id in (kept, extended):
        entered(data, session_id, days_ago=200)
    assert len(retention.check(data, NOW).announced) == 2

    retention.keep_audio(data, kept, True)
    retention.extend(data, extended, NOW)
    later = retention.check(data, NOW + timedelta(days=30))
    assert later.purged == [] and later.announced == []
    assert retention.audio_status(data, kept).state == "kept"
    assert retention.audio_status(data, extended, NOW).purge_on == "2027-01-05T12:00:00Z"

    retention.keep_audio(data, kept, False)  # announced again before anything happens
    assert [a.session_id for a in retention.check(data, NOW + timedelta(days=31)).announced] == [
        kept
    ]


def test_a_session_whose_processing_did_not_succeed_is_never_purged(
    data: DataDir, recording: Path
) -> None:
    with recording.open("rb") as f:
        session_id = sessions.import_recording(
            data, f, recording.name, unnamed_attendees=1, recorded_at=None, profile="essai"
        )
    entered(data, session_id, days_ago=400)
    result = retention.check(data, NOW + timedelta(days=30))
    assert (result.announced, result.purged) == ([], [])
    assert retention.audio_status(data, session_id).state == "never_processed"


def test_a_shorter_delay_is_announced_again_from_now(data: DataDir, recording: Path) -> None:
    session_id = processed(data, recording)
    entered(data, session_id, days_ago=85)
    assert retention.check(data, NOW).announced  # within 7 days of the 90
    conn = connect(data)
    try:
        retention.set_settings(conn, 30, 3)
        with pytest.raises(SpaceError):
            retention.set_settings(conn, 30, 40)
        with pytest.raises(SpaceError):
            retention.set_settings(conn, 0, 1)
    finally:
        conn.close()
    renewed = retention.check(data, NOW + timedelta(hours=1))
    assert [a.purge_on for a in renewed.announced] == ["2026-10-10T13:00:00Z"]
    assert retention.check(data, NOW + timedelta(days=2)).purged == []


def test_the_notification_names_no_session_and_failures_are_logged() -> None:
    sent: list[list[str]] = []
    coming = [
        retention.Announcement(
            session_id="a", title="Secret", recorded_at="x", purge_on="2026-10-14T12:00:00Z"
        )
    ]
    retention.notify(coming, run=sent.append)
    if sent:  # macOS only
        assert sent[0][0] == "osascript"
        assert sent[0][-1].startswith("L'audio d'une séance sera supprimé le 14 octobre.")
        assert "Secret" not in sent[0][-1]

    def failing(_: list[str]) -> None:
        raise OSError("pas d'osascript")

    retention.notify(coming, run=failing)  # logged, never raised


def test_the_watcher_notifies_what_it_announces(data: DataDir, recording: Path) -> None:
    session_id = processed(data, recording)
    entered(data, session_id, days_ago=200)
    told: list[list[retention.Announcement]] = []
    watcher = retention.Watcher(data, notifier=told.append)
    watcher.run_once()
    assert [[a.session_id for a in batch] for batch in told] == [[session_id]]


def test_the_service_keeps_extends_removes_and_lists(data: DataDir, recording: Path) -> None:
    session_id = processed(data, recording)
    client = local_client(
        create_app(data, FAKE_CHAIN, profile="essai", processor=None, web_dir=None)
    )
    kept = client.put(f"/api/seances/{session_id}/garder-audio", json={"keep": True})
    assert kept.json()["audio"]["state"] == "kept"
    assert client.post(f"/api/seances/{session_id}/prolonger").status_code == 200
    removed = client.post(f"/api/seances/{session_id}/supprimer-audio").json()
    assert (removed["session"]["audio"]["state"], removed["problems"]) == ("removed", [])
    info = client.get("/api/conservation").json()
    assert info["settings"] == {"retention_days": 90, "notice_days": 7}
    assert [e["kind"] for e in info["journal"]] == ["audio_deletion"]
    changed = client.put("/api/conservation", json={"retention_days": 60, "notice_days": 5})
    assert changed.json()["settings"] == {"retention_days": 60, "notice_days": 5}
    refused = client.put("/api/conservation", json={"retention_days": 5, "notice_days": 9})
    assert refused.status_code == 422


def test_a_waiting_rerun_holds_the_purge_and_the_deletion_of_the_audio(
    data: DataDir, recording: Path
) -> None:
    session_id = processed(data, recording)
    entered(data, session_id, days_ago=200)
    retention.check(data, NOW)
    versions.request_rerun(data, session_id, "transcribe", attendees=None, profile="essai")
    later = retention.check(data, NOW + timedelta(days=8))
    assert later.purged == []
    assert later.problems and "attend son tour" in later.problems[0]
    assert "Structure" not in later.problems[0] and session_id not in later.problems[0]
    with pytest.raises(retention.DeletionError, match="attend son tour"):
        retention.remove_audio(data, session_id, "audio_deletion")
    assert sources(data, session_id)


def test_a_purge_kept_at_the_last_moment_does_not_happen(data: DataDir, recording: Path) -> None:
    session_id = processed(data, recording)
    entered(data, session_id, days_ago=200)
    retention.check(data, NOW)
    retention.keep_audio(data, session_id, True)  # between the choice and the removal
    with pytest.raises(retention.NotDueError):
        retention.remove_audio(data, session_id, "purge", NOW + timedelta(days=8))
    assert sources(data, session_id)
    assert log_rows(data) == []


def test_files_that_will_not_go_are_said_and_logged(
    data: DataDir, recording: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    session_id = processed(data, recording)

    def refuse(self: Path, missing_ok: bool = False) -> None:
        raise PermissionError(13, "Permission refusée")

    monkeypatch.setattr(Path, "unlink", refuse)
    left = retention.remove_audio(data, session_id, "audio_deletion")
    monkeypatch.undo()
    assert left == ["un fichier audio n'a pas pu être effacé (Permission refusée)"]
    # Gone from Coulisses (nothing will use it again), the leftover said in the journal.
    assert retention.audio_status(data, session_id).state == "removed"
    [entry] = retention.journal(data)
    assert entry.problems == left


def test_a_session_deleted_from_coulisses_says_what_stayed_on_the_disk(
    data: DataDir, recording: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    session_id = processed(data, recording)

    def refuse(path: Path) -> None:
        raise PermissionError(13, "Permission refusée")

    monkeypatch.setattr("coulisses_app.retention.shutil.rmtree", refuse)
    problems = retention.delete_session(data, session_id)
    assert problems == ["le dossier de la séance : Permission refusée"]
    assert sessions.get_session(data, session_id) is None
    [entry] = retention.journal(data)
    assert entry.problems == problems


def test_nothing_is_processed_again_once_the_audio_is_gone(data: DataDir, recording: Path) -> None:
    session_id = processed(data, recording)
    retention.remove_audio(data, session_id, "audio_deletion")
    conn = connect(data)
    try:
        with conn:
            jobs.enqueue_chain(conn, session_id, profile="essai", attendees=1)
    finally:
        conn.close()
    result = Processor(data, FAKE_CHAIN).run_job(claim(data))
    assert result.error is not None and "supprimé" in result.error
    with pytest.raises(SpaceError):
        sessions.start_processing(data, session_id, profile="essai")


def test_the_watcher_outlives_a_failed_check(
    data: DataDir, monkeypatch: pytest.MonkeyPatch
) -> None:
    def broken(*_: object) -> None:
        raise sqlite3.OperationalError("database is locked")

    monkeypatch.setattr("coulisses_app.retention.check", broken)
    watcher = retention.Watcher(data, every_s=0.05, notifier=lambda _: None)
    watcher.start()
    try:
        deadline = datetime.now(UTC) + timedelta(seconds=5)
        while not watcher.problems and datetime.now(UTC) < deadline:
            threading.Event().wait(0.05)
    finally:
        watcher.stop()
    assert watcher.problems and "a échoué" in watcher.problems[0]


def test_a_failed_processing_is_not_offered_again_once_the_audio_is_gone(
    data: DataDir, recording: Path
) -> None:
    session_id = processed(data, recording, attendees=1)
    versions.request_rerun(data, session_id, "diarize", attendees=3, profile="essai")
    from .test_processing import REFUSED_DIARIZATION

    assert Processor(data, REFUSED_DIARIZATION).run_job(claim(data)).error is not None
    retention.remove_audio(data, session_id, "audio_deletion")
    client = local_client(
        create_app(data, FAKE_CHAIN, profile="essai", processor=None, web_dir=None)
    )
    refused = client.post(f"/api/seances/{session_id}/reprendre")
    assert refused.status_code == 409
    assert refused.json()["detail"] == versions.AUDIO_GONE
