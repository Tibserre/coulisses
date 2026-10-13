"""The library (step 8, ADR 0030): projects, the full-text search, the export to a folder."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from coulisses_app import (
    corrections,
    exports,
    projects,
    retention,
    search,
    sessions,
    spaces,
    summaries,
)
from coulisses_app.api import create_app
from coulisses_app.paths import DataDir
from coulisses_app.spaces import SpaceError
from coulisses_app.storage.db import connect, now_iso

from .conftest import FAKE_CHAIN, local_client
from .test_versions import processed


def client_for(data: DataDir) -> TestClient:
    return local_client(create_app(data, FAKE_CHAIN, profile="essai", processor=None, web_dir=None))


# -- projects --------------------------------------------------------------------------------


def test_projects_group_sessions_of_their_own_space(data: DataDir, recording: Path) -> None:
    session_id = processed(data, recording)
    space = sessions.get_session(data, session_id)
    assert space is not None
    show = projects.create(data, space.space_id, "  Spectacle   d'avril ")
    assert show.name == "Spectacle d'avril"
    with pytest.raises(SpaceError, match="existe déjà"):
        projects.create(data, space.space_id, "spectacle d'avril")

    projects.set_session_project(data, session_id, show.id)
    moved = sessions.get_session(data, session_id)
    assert moved is not None and moved.project_id == show.id

    other = spaces.create_space(data, "Équipe produit")
    elsewhere = projects.create(data, other.id, "Comités")
    with pytest.raises(SpaceError, match="autre espace"):
        projects.set_session_project(data, session_id, elsewhere.id)

    renamed = projects.update(data, show.id, name="Spectacle de mai")
    assert renamed.name == "Spectacle de mai"
    projects.update(data, show.id, archived=True)
    kept = sessions.get_session(data, session_id)
    assert kept is not None and kept.project_id == show.id  # its sessions stay in it
    with pytest.raises(SpaceError, match="archivé"):
        projects.set_session_project(data, session_id, show.id)
    projects.set_session_project(data, session_id, None)


def test_a_recording_is_imported_into_a_project(data: DataDir, recording: Path) -> None:
    client = client_for(data)
    space = client.get("/api/espaces").json()[0]["id"]
    show = client.post(f"/api/espaces/{space}/projets", json={"name": "Ateliers"}).json()
    with recording.open("rb") as f:
        answer = client.post(
            "/api/seances",
            files={"fichier": ("atelier.wav", f, "audio/wav")},
            data={"espace": str(space), "projet": str(show["id"])},
        )
    assert answer.status_code == 201, answer.text
    session = client.get(f"/api/seances/{answer.json()['id']}").json()["session"]
    assert session["project_id"] == show["id"]
    assert [p["name"] for p in client.get("/api/projets").json()] == ["Ateliers"]


# -- search ----------------------------------------------------------------------------------


def hits(data: DataDir, query: str) -> list[tuple[str, str, str]]:
    """(session, kind, excerpt as text) of every hit."""
    return [
        (s.session_id, h.kind, "".join(p.text for p in h.excerpt))
        for s in search.search(data, query).sessions
        for h in s.hits
    ]


def test_the_search_finds_the_corrected_text_whatever_the_accents(
    data: DataDir, recording: Path
) -> None:
    session_id = processed(data, recording)
    assert [(s, k) for s, k, _ in hits(data, "BONJOUR")] == [(session_id, "turn")]

    corrections.add(
        data, session_id, {"kind": "edit_text", "turn": 0, "text": "L'échauffement commence"}
    )
    assert hits(data, "bonjour") == []  # what was corrected is no longer found
    [(_, kind, excerpt)] = hits(data, "echauf")  # accents and the end of the word ignored
    assert (kind, excerpt) == ("turn", "L'échauffement commence")
    parts = search.search(data, "echauffement").sessions[0].hits[0].excerpt
    assert [p.text for p in parts if p.hit] == ["échauffement"]
    assert search.search(data, "echauffement").sessions[0].hits[0].at_s is not None


def test_the_search_reads_notes_summaries_and_titles(data: DataDir, recording: Path) -> None:
    session_id = processed(data, recording)
    conn = connect(data)
    try:
        with conn:
            conn.execute(
                "UPDATE session SET title = 'Filage du dimanche' WHERE id = ?", (session_id,)
            )
            conn.execute(
                "INSERT INTO note (session_id, at_s, text, created_at, updated_at)"
                " VALUES (?, NULL, 'Penser aux costumes', ?, ?)",
                (session_id, now_iso(), now_iso()),
            )
            conn.execute(
                "INSERT INTO run (id, session_id, stage, status, producer, created_at)"
                " VALUES ('summarize-1', ?, 'summarize', 'succeeded', 'app', ?)",
                (session_id, now_iso()),
            )
            conn.execute(
                "INSERT INTO generation (session_id, run_id, action_ref, created_at)"
                " VALUES (?, 'summarize-1', 'resume-impro', ?)",
                (session_id, now_iso()),
            )
    finally:
        conn.close()
    folder = data.run_dir(session_id, "summarize-1")
    folder.mkdir(parents=True)
    (folder / "output.md").write_text("## Décisions\n- La fin à deux voix.", encoding="utf-8")

    assert [k for _, k, _ in hits(data, "dimanche")] == ["title"]
    assert [k for _, k, _ in hits(data, "costumes")] == ["note"]
    assert [k for _, k, _ in hits(data, "deux voix")] == ["summary"]


def test_typed_operators_are_words_and_a_deleted_session_is_forgotten(
    data: DataDir, recording: Path
) -> None:
    session_id = processed(data, recording)
    for query in ('"bonjour', "bonjour AND OR (", "bon*", "NEAR(bonjour)"):
        search.search(data, query)  # never an FTS5 syntax error
    assert search.search(data, "  ").sessions == []
    assert hits(data, "bonjour")
    retention.delete_session(data, session_id)
    assert hits(data, "bonjour") == []
    conn = connect(data)
    try:
        assert conn.execute("SELECT COUNT(*) FROM search_index").fetchone()[0] == 0
    finally:
        conn.close()


def test_the_service_searches(data: DataDir, recording: Path) -> None:
    session_id = processed(data, recording)
    found = client_for(data).get("/api/recherche", params={"q": "bonj"}).json()
    assert found["sessions"][0]["session_id"] == session_id
    assert found["sessions"][0]["hits"][0]["excerpt"] == [{"text": "bonjour", "hit": True}]


# -- export to a folder ------------------------------------------------------------------------


def test_the_export_writes_in_the_chosen_folder_and_never_replaces_silently(
    data: DataDir, recording: Path, tmp_path: Path
) -> None:
    session_id = processed(data, recording)
    client = client_for(data)
    url = f"/api/seances/{session_id}/exporter-dossier"
    assert client.post(url, json={}).status_code == 422  # no folder chosen yet

    assert client.put("/api/export", json={"dossier": str(tmp_path / "absent")}).status_code == 422
    folder = tmp_path / "Mon Drive" / "Troupe"
    folder.mkdir(parents=True)
    chosen = client.put("/api/export", json={"dossier": str(folder)}).json()
    assert chosen == {"folder": str(folder.resolve()), "present": True}

    first = client.post(url, json={"contenu": "transcript"})
    assert first.status_code == 200, first.text
    assert first.json()["resume"] is None  # no summary yet: the transcript only, said
    written = folder / first.json()["fichier"]
    assert "bonjour" in written.read_text(encoding="utf-8")
    assert [p.name for p in folder.iterdir()] == [written.name]  # nothing half-written left

    again = client.post(url, json={"contenu": "transcript"})
    assert again.status_code == 409
    written.write_text("modifié à la main", encoding="utf-8")
    assert client.post(url, json={"contenu": "transcript", "remplacer": True}).status_code == 200
    assert "bonjour" in written.read_text(encoding="utf-8")

    folder.rename(tmp_path / "ailleurs")
    gone = client.get("/api/export").json()
    assert gone["present"] is False
    refused = client.post(url, json={})
    assert refused.status_code == 422 and "introuvable" in refused.json()["detail"]
    conn = connect(data)
    try:
        assert exports.set_folder(conn, None).folder is None
    finally:
        conn.close()


def test_no_word_of_a_deleted_session_stays_in_the_files(data: DataDir, recording: Path) -> None:
    session_id = processed(data, recording)
    corrections.add(data, session_id, {"kind": "edit_text", "turn": 0, "text": "Zygomatiquement"})
    assert hits(data, "zygomatiquement")  # indexed
    data.backups.mkdir(parents=True, exist_ok=True)
    backup = data.backups / "coulisses-avant-0009-test.db"
    source = connect(data)
    try:
        source.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        copy = sqlite3.connect(backup)
        source.backup(copy)
        copy.close()
    finally:
        source.close()
    assert b"Zygomatiquement" in backup.read_bytes()

    assert retention.delete_session(data, session_id) == []
    for path in (data.database, backup):
        assert b"ygomatiquement" not in path.read_bytes(), path.name
    wal = data.database.with_name(data.database.name + "-wal")
    assert not wal.exists() or b"ygomatiquement" not in wal.read_bytes()


def test_a_project_back_in_use_keeps_its_name_unique(data: DataDir, recording: Path) -> None:
    session_id = processed(data, recording)
    session = sessions.get_session(data, session_id)
    assert session is not None
    old = projects.create(data, session.space_id, "Ateliers")
    projects.update(data, old.id, archived=True)
    projects.create(data, session.space_id, "Ateliers")
    with pytest.raises(SpaceError, match="déjà en usage"):
        projects.update(data, old.id, archived=False)
    assert (
        projects.update(data, old.id, name="Ateliers 2025", archived=False).name == "Ateliers 2025"
    )


def test_the_index_follows_a_title_changed_after_a_search(data: DataDir, recording: Path) -> None:
    session_id = processed(data, recording)
    assert hits(data, "filage") == []
    summaries.set_title(data, session_id, "Filage du dimanche")
    assert [k for _, k, _ in hits(data, "filage")] == ["title"]


def test_an_unreadable_session_is_said_and_the_others_found(data: DataDir, recording: Path) -> None:
    broken = processed(data, recording)
    fine = processed(data, recording)
    conn = connect(data)
    try:
        run = conn.execute(
            "SELECT run_id FROM active_run WHERE session_id = ? AND stage = 'attribute'", (broken,)
        ).fetchone()[0]
    finally:
        conn.close()
    (data.run_dir(broken, run) / "output.json").write_text("{", encoding="utf-8")
    found = search.search(data, "bonjour")
    assert [s.session_id for s in found.sessions] == [fine]
    assert found.problems and broken not in found.problems[0]


def test_a_recording_starts_in_its_project(data: DataDir) -> None:
    conn = connect(data)
    try:
        space = spaces.default_space_id(conn)
    finally:
        conn.close()
    show = projects.create(data, space, "Spectacle")
    session_id, _ = sessions.start_capture(
        data,
        space_id=space,
        project_id=show.id,
        attendee_ids=[],
        unnamed_attendees=None,
        device="Micro de test",
        sample_rate=48000,
        channels=1,
    )
    started = sessions.get_session(data, session_id)
    assert started is not None and started.project_id == show.id


def test_the_export_says_which_summary_it_wrote(
    data: DataDir, recording: Path, tmp_path: Path
) -> None:
    session_id = processed(data, recording)
    conn = connect(data)
    try:
        with conn:
            conn.execute(
                "INSERT INTO run (id, session_id, stage, status, producer, created_at)"
                " VALUES ('summarize-1', ?, 'summarize', 'succeeded', 'app', ?)",
                (session_id, now_iso()),
            )
            conn.execute(
                "INSERT INTO generation (session_id, run_id, action_ref, created_at)"
                " VALUES (?, 'summarize-1', 'resume-impro', ?)",
                (session_id, now_iso()),
            )
        exports.set_folder(conn, str(tmp_path))
    finally:
        conn.close()
    folder = data.run_dir(session_id, "summarize-1")
    folder.mkdir(parents=True)
    (folder / "output.md").write_text("- La fin à deux voix.", encoding="utf-8")

    name, written = exports.export_to_folder(
        data, session_id, summary=True, transcript=True, generation_id=None, replace=False
    )
    assert written is not None
    text = (tmp_path / name).read_text(encoding="utf-8")
    assert f"## {written}" in text and "La fin à deux voix" in text
