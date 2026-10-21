"""Spaces, people, glossary, attendees and corrections, as the interface uses them."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from coulisses_app import jobs
from coulisses_app.api import create_app
from coulisses_app.paths import DataDir
from coulisses_app.processing import Processor
from coulisses_app.storage import db
from coulisses_app.storage.db import connect

from .conftest import FAKE_CHAIN, local_client


@pytest.fixture
def client(data: DataDir) -> TestClient:
    return local_client(create_app(data, FAKE_CHAIN, profile="essai", processor=None, web_dir=None))


def processed_session(client: TestClient, data: DataDir, recording: Path, **form: object) -> str:
    with recording.open("rb") as f:
        response = client.post(
            "/api/seances", files={"fichier": ("a.wav", f, "audio/wav")}, data=form
        )
    assert response.status_code == 201, response.text
    conn = connect(data)
    try:
        job = jobs.claim_next(conn)
    finally:
        conn.close()
    assert job is not None
    Processor(data, FAKE_CHAIN).run_job(job)
    return response.json()["id"]


def test_spaces_hold_their_people_with_stable_colours(client: TestClient) -> None:
    space = client.post("/api/espaces", json={"name": "Équipe produit"}).json()
    ids = []
    for name in ("Ana", "Bruno", "Chloé"):
        person = client.post(
            f"/api/espaces/{space['id']}/personnes",
            json={"name": name, "kind": "member", "role": "cheffe de projet"},
        ).json()
        ids.append(person["color_slot"])
    assert ids == [0, 1, 2]  # newcomers spread over the palette
    guest = client.post(
        f"/api/espaces/{space['id']}/personnes", json={"name": "Dana", "kind": "guest"}
    ).json()
    assert guest["kind"] == "guest" and guest["color_slot"] == 3
    archived = client.patch(f"/api/personnes/{guest['id']}", json={"archived": True}).json()
    assert archived["archived"] is True  # archived, never deleted
    names = [p["name"] for p in client.get(f"/api/espaces/{space['id']}/personnes").json()]
    assert names[-1] == "Dana"


def test_empty_names_are_refused_in_french(client: TestClient) -> None:
    response = client.post("/api/espaces", json={"name": "  "})
    assert response.status_code == 422
    assert "vide" in response.json()["detail"]
    assert client.get("/api/espaces/999/personnes").status_code == 404


def test_the_glossary_reaches_the_engine_and_helps_the_review(
    client: TestClient, data: DataDir, recording: Path
) -> None:
    space_id = client.get("/api/espaces").json()[0]["id"]
    entry = client.post(
        f"/api/espaces/{space_id}/glossaire",
        json={"term": "Bonjour", "category": "jargon", "variants": ["bonjour", " ", "bonjour"]},
    ).json()
    assert entry["variants"] == ["bonjour"]
    session_id = processed_session(client, data, recording)
    conn = connect(data)
    try:
        params = conn.execute("SELECT params FROM job").fetchone()[0]
    finally:
        conn.close()
    assert '"glossary":["Bonjour"]' in params
    view = client.get(f"/api/seances/{session_id}/transcript").json()
    assert view["turns"][0]["words"][0]["suggestion"] == "Bonjour"


def test_checked_and_unnamed_attendees_add_up_to_the_minimum_of_voices(
    client: TestClient, data: DataDir, recording: Path
) -> None:
    space_id = client.get("/api/espaces").json()[0]["id"]
    a = client.post(f"/api/espaces/{space_id}/personnes", json={"name": "Ana"}).json()
    b = client.post(f"/api/espaces/{space_id}/personnes", json={"name": "Bruno"}).json()
    session_id = processed_session(
        client, data, recording, presents=[str(a["id"]), str(b["id"])], non_nommes="1"
    )
    session = client.get(f"/api/seances/{session_id}").json()["session"]
    assert session["attendee_ids"] == [a["id"], b["id"]]
    assert session["min_voices"] == 3
    conn = connect(data)
    try:
        params = conn.execute("SELECT params FROM job").fetchone()[0]
    finally:
        conn.close()
    assert '"attendees":3' in params  # what the engine was asked (P3: a minimum)


def test_a_person_of_another_space_cannot_attend(client: TestClient, recording: Path) -> None:
    other = client.post("/api/espaces", json={"name": "Client X"}).json()
    stranger = client.post(f"/api/espaces/{other['id']}/personnes", json={"name": "Zoé"}).json()
    with recording.open("rb") as f:
        response = client.post(
            "/api/seances",
            files={"fichier": ("a.wav", f, "audio/wav")},
            data={"presents": [str(stranger["id"])]},
        )
    assert response.status_code == 422
    assert "n'appartient pas" in response.json()["detail"]


def test_name_correct_undo_redo_a_session(
    client: TestClient, data: DataDir, recording: Path
) -> None:
    space_id = client.get("/api/espaces").json()[0]["id"]
    marie = client.post(f"/api/espaces/{space_id}/personnes", json={"name": "Marie"}).json()
    session_id = processed_session(client, data, recording, non_nommes="2")
    base = f"/api/seances/{session_id}"
    view = client.get(f"{base}/transcript").json()
    first = view["speakers"][0]["label"]

    named = client.post(
        f"{base}/corrections",
        json={"kind": "assign_speaker", "speaker": first, "person_id": marie["id"]},
    )
    assert named.status_code == 201
    speaker = named.json()["speakers"][0]
    assert (speaker["name"], speaker["color_slot"]) == ("Marie", marie["color_slot"])

    edited = client.post(
        f"{base}/corrections", json={"kind": "edit_text", "turn": 0, "text": "bonsoir à tous"}
    ).json()
    words = edited["turns"][0]["words"]
    assert [w["text"] for w in words] == ["bonsoir", "à", "tous"]
    assert words[0]["start"] is not None and words[0]["corrected"]
    assert words[1]["start"] is None and words[1]["added"]  # no invented time (P2)

    edit_id = edited["edits"][-1]["id"]
    undone = client.post(f"{base}/corrections/{edit_id}/annuler").json()
    assert undone["turns"][0]["words"][0]["text"] == "bonjour"
    assert undone["edits"][-1]["reverted"] is True  # listed, not erased
    assert client.post(f"{base}/corrections/{edit_id}/annuler").status_code == 422
    redone = client.post(f"{base}/corrections/{edit_id}/retablir").json()
    assert redone["turns"][0]["words"][0]["text"] == "bonsoir"
    assert len(redone["edits"]) == 3


def test_a_split_creates_a_new_voice_and_can_be_undone(
    client: TestClient, data: DataDir, recording: Path
) -> None:
    session_id = processed_session(client, data, recording, non_nommes="2")
    base = f"/api/seances/{session_id}"
    before = client.get(f"{base}/transcript").json()["turns"][0]["speaker"]
    split = client.post(f"{base}/corrections", json={"kind": "reassign_turns", "turns": [0]})
    assert split.status_code == 201
    view = split.json()
    new_voice = view["turns"][0]["speaker"]
    assert new_voice.startswith("coulisses:")
    assert [s["name"] for s in view["speakers"]] == ["Nouvelle voix 1"]
    split_id = view["edits"][0]["id"]
    undone = client.post(f"{base}/corrections/{split_id}/annuler").json()
    assert undone["turns"][0]["speaker"] == before
    redone = client.post(f"{base}/corrections/{split_id}/retablir")
    assert redone.status_code == 200, redone.text
    assert redone.json()["turns"][0]["speaker"] == new_voice  # the same voice comes back
    again = client.post(f"{base}/corrections/{split_id}/retablir")
    assert again.status_code == 422 and "déjà rétablie" in again.json()["detail"]


def test_bad_corrections_are_refused_with_a_reason(
    client: TestClient, data: DataDir, recording: Path
) -> None:
    session_id = processed_session(client, data, recording, non_nommes="2")
    base = f"/api/seances/{session_id}/corrections"
    assert client.post(base, json={"kind": "edit_text", "turn": 0, "text": "  "}).status_code == 422
    assert client.post(base, json={"kind": "edit_text", "turn": 99, "text": "x"}).status_code == 422
    response = client.post(base, json={"kind": "assign_speaker", "speaker": "inconnu"})
    assert response.status_code == 422 and "voix" in response.json()["detail"]
    assert client.post(base, json={"kind": "nope"}).status_code == 422


def test_attendees_can_be_checked_after_the_fact(
    client: TestClient, data: DataDir, recording: Path
) -> None:
    space_id = client.get("/api/espaces").json()[0]["id"]
    ana = client.post(f"/api/espaces/{space_id}/personnes", json={"name": "Ana"}).json()
    session_id = processed_session(client, data, recording, non_nommes="2")
    session = client.put(
        f"/api/seances/{session_id}/presents", json={"person_ids": [ana["id"]], "unnamed": 1}
    ).json()
    assert session["attendee_ids"] == [ana["id"]]
    assert session["unnamed_attendees"] == 1
    assert session["min_voices"] == 2  # the processing already done keeps its minimum


def test_a_step_1_database_is_migrated_without_losing_anything(tmp_path: Path) -> None:
    data = DataDir(tmp_path)
    data.root.mkdir(parents=True, exist_ok=True)
    first = db.migrations()[0]
    with sqlite3.connect(data.database) as conn:
        conn.executescript(first[2] + "\nPRAGMA user_version = 1;")
        conn.execute(
            "INSERT INTO session (id, troupe_id, recorded_at, created_at, reference_source_id,"
            " attendee_count) VALUES ('s1', 1, 'x', 'x', 'ref', 4)"
        )
    conn.close()
    backups = db.migrate(data)
    assert len(backups) == 1
    conn = db.connect(data)
    try:
        row = conn.execute("SELECT space_id, unnamed_attendees FROM session").fetchone()
        assert (row["space_id"], row["unnamed_attendees"]) == (1, 4)
        assert conn.execute("SELECT name FROM space").fetchone()[0] == "Ma troupe"
    finally:
        conn.close()


def test_zero_unnamed_attendees_after_the_fact_is_refused(
    client: TestClient, data: DataDir, recording: Path
) -> None:
    session_id = processed_session(client, data, recording, non_nommes="2")
    response = client.put(f"/api/seances/{session_id}/presents", json={"unnamed": 0})
    assert response.status_code == 422


def test_a_line_goes_back_to_the_engine_text_and_the_history_says_what_to_redo(
    client: TestClient, data: DataDir, recording: Path
) -> None:
    session_id = processed_session(client, data, recording, non_nommes="2")
    base = f"/api/seances/{session_id}"
    client.post(f"{base}/corrections", json={"kind": "edit_text", "turn": 0, "text": "bonsoir"})
    second = client.post(
        f"{base}/corrections", json={"kind": "edit_text", "turn": 0, "text": "bonsoir tous"}
    ).json()
    assert [e["turn"] for e in second["edits"]] == [0, 0]
    back = client.post(f"{base}/repliques/0/texte-d-origine").json()
    assert back["turns"][0]["words"][0]["text"] == "bonjour"
    assert not back["turns"][0]["edited"]
    assert all(e["reverted"] and e["undone_by"] for e in back["edits"])
    assert client.post(f"{base}/repliques/0/texte-d-origine").status_code == 422
    view = back
    for _ in range(2):  # Cmd-Shift-Z twice: the latest undone first
        target = max(
            (e for e in view["edits"] if e["reverted"] and not e["redone"]),
            key=lambda e: e["undone_by"],
        )
        view = client.post(f"{base}/corrections/{target['id']}/retablir").json()
    assert [w["text"] for w in view["turns"][0]["words"]] == ["bonsoir", "tous"]
    assert all(e["redone"] for e in view["edits"] if e["reverted"])


def test_naming_a_voice_after_a_person_who_has_one_merges_them(
    client: TestClient, data: DataDir, recording: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from coulisses_app import corrections

    from .test_corrections import TRANSCRIPT  # voices 7, 2 and 4

    session_id = processed_session(client, data, recording)
    run_id = client.get(f"/api/seances/{session_id}/transcript").json()["run_id"]

    def view_with_three_voices(data: DataDir, session_id: str) -> corrections.CorrectedView:
        conn = connect(data)
        try:
            journal = corrections._journal(conn, session_id)
            people = {p.id: p for p in corrections._people(conn, 1)}
        finally:
            conn.close()
        return corrections._replay(TRANSCRIPT, run_id, journal, people, {})

    monkeypatch.setattr(corrections, "build_view", view_with_three_voices)
    marie = client.post("/api/espaces/1/personnes", json={"name": "Marie"}).json()["id"]
    url = f"/api/seances/{session_id}/corrections"
    client.post(url, json={"kind": "assign_speaker", "speaker": "7", "person_id": marie})
    merged = client.post(url, json={"kind": "assign_speaker", "speaker": "2", "person_id": marie})
    assert merged.status_code == 201, merged.text
    view = merged.json()
    assert [s["name"] for s in view["speakers"] if s["label"] in ("7", "2")] == ["Marie"]
    assert view["edits"][-1]["kind"] == "merge_speakers"  # undone with Cmd-Z like any merge
    undone = client.post(f"{url}/{view['edits'][-1]['id']}/annuler").json()
    assert {s["label"] for s in undone["speakers"]} >= {"7", "2"}  # two voices again
    client.post(f"{url}/{view['edits'][-1]['id']}/retablir")
    # A character played by the same person stays a voice of its own.
    played = client.post(
        url,
        json={"kind": "assign_speaker", "speaker": "4", "person_id": marie, "character": "Le roi"},
    ).json()
    assert {s["name"] for s in played["speakers"]} >= {"Marie", "Le roi"}


def test_a_session_not_processed_yet_moves_to_another_space(
    client: TestClient, data: DataDir, recording: Path
) -> None:
    from coulisses_app import sessions

    first = client.post("/api/espaces", json={"name": "Ma troupe"}).json()
    other = client.post("/api/espaces", json={"name": "Équipe produit"}).json()
    ana = client.post(f"/api/espaces/{first['id']}/personnes", json={"name": "Ana"}).json()
    project = client.post(f"/api/espaces/{first['id']}/projets", json={"name": "Spectacle"}).json()
    # A recording started in the space selected, the wrong one: not processed yet.
    session_id, _ = sessions.start_capture(
        data,
        space_id=first["id"],
        project_id=project["id"],
        attendee_ids=[ana["id"]],
        unnamed_attendees=2,
        device="Micro",
        sample_rate=48_000,
        channels=1,
    )
    moved = client.put(f"/api/seances/{session_id}/espace", json={"espace": other["id"]})
    assert moved.status_code == 200, moved.text
    assert moved.json()["session"]["space_id"] == other["id"]
    assert moved.json()["session"]["project_id"] is None
    assert moved.json()["unchecked"] == ["Ana"]  # said on the recording screen
    conn = connect(data)
    try:
        attendees = conn.execute(
            "SELECT COUNT(*) FROM attendee WHERE session_id = ?", (session_id,)
        ).fetchone()[0]
        unnamed = conn.execute(
            "SELECT unnamed_attendees FROM session WHERE id = ?", (session_id,)
        ).fetchone()[0]
    finally:
        conn.close()
    assert attendees == 0 and unnamed == 2  # the people of the old space are unchecked

    # Once processed, a session stays in its space.
    processed = processed_session(client, data, recording)
    refused = client.put(f"/api/seances/{processed}/espace", json={"espace": other["id"]})
    assert refused.status_code == 422 and "reste dans son espace" in refused.json()["detail"]
