"""The assistants' connector (ADR 0065, `docs/produit/contrat-connecteur.md`): closed by
default and refusing everything then; a space closed to it in no answer; the names known to
a space masked everywhere unless passed on; each successful read in the journal."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from coulisses_app import corrections, jobs, marks, notes, sessions, spaces, summaries
from coulisses_app.api import create_app
from coulisses_app.connector import Masker
from coulisses_app.paths import DataDir
from coulisses_app.processing import Processor
from coulisses_app.prompting.generate import GenerationError, generate
from coulisses_app.storage.db import connect

from .conftest import FAKE_CHAIN, FakeModel, local_client
from .test_processing import claim, import_

NAMES = ("Marie", "Dupont", "Jean", "Zorglub")


def _prepared(data: DataDir, recording: Path) -> tuple[TestClient, str, int]:
    """A processed session whose space knows Marie Dupont, Jean and « Zorglub », all of them
    in its title, transcript, voices, notes and project."""
    session_id = import_(data, recording)
    session = sessions.get_session(data, session_id)
    assert session is not None
    space_id = session.space_id
    marie = spaces.add_person(data, space_id, kind="member", name="Marie Dupont")
    jean = spaces.add_person(data, space_id, kind="guest", name="Jean")
    spaces.add_entry(data, space_id, term="Zorglub", variants=["Zorglube"])
    spaces.add_entry(data, space_id, term="catch")  # a common word: stays
    assert Processor(data, FAKE_CHAIN).run_job(claim(data)).error is None
    spaces.set_attendees(data, session_id, [marie.id, jean.id], None)
    corrections.add(
        data,
        session_id,
        {
            "kind": "edit_text",
            "turn": 0,
            "text": "bonjour jean, ZORGLUBE et Marie : échauffement et catch",
        },
    )
    corrections.add(
        data, session_id, {"kind": "assign_speaker", "speaker": "S1", "person_id": marie.id}
    )
    summaries.set_title(data, session_id, "Répétition chez Dupont")
    conn = connect(data)
    try:
        marks.add_timed_note(conn, session_id, 0.2, "Jean arrive en retard")
        notes.set_after_session(conn, session_id, "Revoir la scène de Marie")
        with conn:
            project = conn.execute(
                "INSERT INTO project (space_id, name, created_at) VALUES (?, 'Cours de Jean', '')",
                (space_id,),
            ).lastrowid
            conn.execute("UPDATE session SET project_id = ? WHERE id = ?", (project, session_id))
    finally:
        conn.close()
    client = local_client(
        create_app(data, FAKE_CHAIN, profile="essai", processor=None, web_dir=None)
    )
    return client, session_id, space_id


def _open(client: TestClient, space_id: int, *, names: bool = False) -> None:
    assert client.put("/api/reglages/connecteur", json={"open": True}).json()["open"] is True
    client.patch(
        f"/api/espaces/{space_id}", json={"connector_access": True, "connector_names": names}
    )


def _reads(client: TestClient, session_id: str) -> list[tuple[str, Any]]:
    return [
        (path, client.get(path))
        for path in (
            "/api/connecteur/seances",
            f"/api/connecteur/seances/{session_id}",
            f"/api/connecteur/seances/{session_id}/transcript",
            "/api/connecteur/recherche?q=echauffement",
        )
    ]


def test_closed_by_default_it_refuses_everything_first(data: DataDir, recording: Path) -> None:
    client, session_id, space_id = _prepared(data, recording)
    settings = client.get("/api/reglages/connecteur").json()
    assert settings["open"] is False
    assert settings["claude_code_command"].startswith("claude mcp add coulisses -- ")
    client.patch(f"/api/espaces/{space_id}", json={"connector_access": True})
    for path in (
        *(p for p, _ in _reads(client, session_id)),
        "/api/connecteur/seances/inconnue",
        "/api/connecteur/seances?limite=0",  # invalid: still 403 first
        "/api/connecteur/seances?limite=abc",  # not even a number
        f"/api/connecteur/seances/{session_id}/resumes/abc",
        f"/api/connecteur/seances/{session_id}/resumes/1",
    ):
        response = client.get(path)
        assert response.status_code == 403, path
        assert "coupé" in response.json()["detail"]
    assert client.get("/api/reglages/connecteur/journal").json()["entries"] == []


def test_a_space_closed_to_it_is_in_no_answer(data: DataDir, recording: Path) -> None:
    client, session_id, space_id = _prepared(data, recording)
    _open(client, space_id)
    client.patch(f"/api/espaces/{space_id}", json={"connector_access": False})
    assert client.get("/api/connecteur/seances").json() == {"sessions": [], "next": None}
    assert client.get("/api/connecteur/recherche?q=bonjour").json()["sessions"] == []
    unknown = client.get("/api/connecteur/seances/inconnue")
    closed = client.get(f"/api/connecteur/seances/{session_id}")
    assert (closed.status_code, closed.json()) == (unknown.status_code, unknown.json())
    assert closed.status_code == 404
    assert client.get(f"/api/connecteur/seances/{session_id}/transcript").status_code == 404


def test_the_names_are_masked_everywhere(data: DataDir, recording: Path) -> None:
    client, session_id, space_id = _prepared(data, recording)
    _open(client, space_id)
    answers = {path: response for path, response in _reads(client, session_id)}
    for path, response in answers.items():
        assert response.status_code == 200, (path, response.text)
        text = json.dumps(response.json(), ensure_ascii=False).lower()
        for name in NAMES:
            assert name.lower() not in text, (path, name)
    seance = answers[f"/api/connecteur/seances/{session_id}"].json()
    assert seance["names_shared"] is False
    # In order of first appearance in the transcript: Jean, Zorglub, Marie; the same
    # letter everywhere.
    assert seance["speakers"][0]["name"] == "Personne C"
    assert sorted(seance["attendees"]) == ["Personne A", "Personne C"]
    assert seance["title"] == "Répétition chez Personne C"
    assert seance["project"] == "Cours de Personne A"
    assert seance["note"] == "Revoir la scène de Personne C"
    assert seance["timed_notes"][0]["text"] == "Personne A arrive en retard"
    transcript = answers[f"/api/connecteur/seances/{session_id}/transcript"].json()
    assert transcript["turns"][0]["text"] == (
        "bonjour Personne A, Personne B et Personne C : échauffement et catch"
    )
    assert transcript["provenance"]["engine_version"]
    assert transcript["provenance"]["profile"] == "essai"
    hit = answers["/api/connecteur/recherche?q=echauffement"].json()["sessions"][0]["hits"]
    assert any("«échauffement»" in h["excerpt"] for h in hit)


def test_a_masked_name_finds_nothing_until_names_are_passed_on(
    data: DataDir, recording: Path
) -> None:
    client, _, space_id = _prepared(data, recording)
    _open(client, space_id)
    for query in ("Marie", "zorglub", "Personne"):
        assert client.get(f"/api/connecteur/recherche?q={query}").json()["sessions"] == [], query
    client.patch(f"/api/espaces/{space_id}", json={"connector_names": True})
    found = client.get("/api/connecteur/recherche?q=marie").json()["sessions"]
    assert found and found[0]["names_shared"] is True
    assert any("«Marie»" in h["excerpt"] for h in found[0]["hits"])


def test_each_read_is_in_the_journal_without_what_was_searched(
    data: DataDir, recording: Path
) -> None:
    client, session_id, space_id = _prepared(data, recording)
    _open(client, space_id)
    _reads(client, session_id)
    client.get("/api/connecteur/recherche?q=introuvable")
    client.get("/api/connecteur/seances/inconnue")  # refused: not noted
    entries = client.get("/api/reglages/connecteur/journal").json()["entries"]
    assert [e["tool"] for e in entries] == [
        "chercher",
        "chercher",
        "lire_transcript",
        "lire_seance",
        "lister_seances",
    ]
    assert entries[0]["session_id"] is None and entries[0]["names_shared"] is None
    assert entries[1]["session_title"] == "Répétition chez Dupont"  # the user reads it
    assert all(e["names_shared"] is False for e in entries[1:])
    conn = connect(data)
    try:
        rows = [dict(r) for r in conn.execute("SELECT * FROM connector_access_log")]
    finally:
        conn.close()
    assert "introuvable" not in json.dumps(rows)
    page = client.get("/api/reglages/connecteur/journal?limite=2").json()
    assert len(page["entries"]) == 2 and page["next"] == page["entries"][-1]["id"]
    rest = client.get(f"/api/reglages/connecteur/journal?avant={page['next']}").json()
    assert [e["id"] for e in rest["entries"]] == [e["id"] for e in entries[2:]]


def test_a_reading_in_parts_says_when_the_session_changed(data: DataDir, recording: Path) -> None:
    client, session_id, space_id = _prepared(data, recording)
    _open(client, space_id)
    path = f"/api/connecteur/seances/{session_id}/transcript"
    first = client.get(path, params={"nombre": 1}).json()
    assert first["next"] is None and first["total_turns"] == 1
    assert client.get(path, params={"depuis": 5}).status_code == 422  # no « vue »
    assert client.get(path, params={"depuis": 0, "vue": first["view"]}).status_code == 200
    corrections.add(data, session_id, {"kind": "edit_text", "turn": 0, "text": "rebonjour"})
    changed = client.get(path, params={"depuis": 0, "vue": first["view"]})
    assert changed.status_code == 409 and "reprenez au début" in changed.json()["detail"]
    assert client.get(path, params={"chapitre": 3}).status_code == 422
    assert client.get(path, params={"nombre": 501}).status_code == 422


def test_only_reads_are_accepted(data: DataDir, recording: Path) -> None:
    client, session_id, space_id = _prepared(data, recording)
    _open(client, space_id)
    for path in ("/api/connecteur/seances", f"/api/connecteur/seances/{session_id}"):
        for method in ("post", "put", "patch", "delete"):
            assert getattr(client, method)(path).status_code == 405, (method, path)


def test_the_space_options_are_closed_by_default_and_changed(
    data: DataDir, recording: Path
) -> None:
    client, _, space_id = _prepared(data, recording)
    space = next(s for s in client.get("/api/espaces").json() if s["id"] == space_id)
    assert (space["connector_access"], space["connector_names"]) == (False, False)
    changed = client.patch(f"/api/espaces/{space_id}", json={"connector_access": True}).json()
    assert (changed["connector_access"], changed["connector_names"]) == (True, False)
    listed = client.put("/api/reglages/connecteur", json={"open": True}).json()["spaces"]
    assert {"id": space_id, "connector_access": True, "connector_names": False}.items() <= next(
        s for s in listed if s["id"] == space_id
    ).items()


@pytest.mark.parametrize(
    ("text", "masked"),
    [
        ("Élodie et ELODIE", "Personne A et Personne A"),
        ("Marie-Jo n'est pas Marie", "Marie-Jo n'est pas Personne B"),
        ("Mariette", "Mariette"),  # whole words only
        ("Jean-Pierre Martin parle", "Personne C parle"),
    ],
)
def test_the_masking_is_by_whole_words_accents_and_case_ignored(text: str, masked: str) -> None:
    masker = Masker([["Élodie"], ["Marie"], ["Jean-Pierre Martin", "Martin"]])
    assert masker.mask(text) == masked


def test_a_summary_is_read_masked_with_its_provenance(
    data: DataDir, recording: Path, fake_model: FakeModel
) -> None:
    client, session_id, space_id = _prepared(data, recording)
    fake_model.answer = "## Retours\n- Marie Dupont tient bien la scène."
    prov = generate(data, session_id, "resume-impro", "modele-essai", fake_model)
    _open(client, space_id)
    listed = client.get(f"/api/connecteur/seances/{session_id}").json()["generations"]
    assert [g["action"] for g in listed] == [prov.action_name]
    read = client.get(f"/api/connecteur/seances/{session_id}/resumes/{listed[0]['id']}")
    assert read.status_code == 200, read.text
    body = read.json()
    assert body["markdown"].rstrip() == "## Retours\n- Personne C tient bien la scène."
    assert body["provenance"]["model"] == "modele-essai"
    assert body["provenance"]["engine_version"]
    assert client.get(f"/api/connecteur/seances/{session_id}/resumes/999").status_code == 404


def test_the_list_and_the_search_go_on_by_pages(data: DataDir, recording: Path) -> None:
    client, first, space_id = _prepared(data, recording)
    second = import_(data, recording)
    conn = connect(data)
    try:
        while (job := jobs.claim_next(conn)) is not None:  # the chapters of the first too
            Processor(data, FAKE_CHAIN).run_job(job)
    finally:
        conn.close()
    _open(client, space_id)
    page = client.get("/api/connecteur/seances", params={"limite": 1}).json()
    assert [s["id"] for s in page["sessions"]] == [second] and page["next"]
    rest = client.get("/api/connecteur/seances", params={"limite": 1, "apres": page["next"]})
    assert [s["id"] for s in rest.json()["sessions"]] == [first] and rest.json()["next"] is None
    found = client.get("/api/connecteur/recherche", params={"q": "bonjour", "limite": 1}).json()
    assert len(found["sessions"]) == 1 and found["next"]
    more = client.get(
        "/api/connecteur/recherche", params={"q": "bonjour", "limite": 1, "apres": found["next"]}
    ).json()
    assert {found["sessions"][0]["id"], more["sessions"][0]["id"]} == {first, second}
    assert more["next"] is None
    # The results changed in between (a session deleted): said, never skipped in silence.
    client.delete(f"/api/seances/{second}")
    changed = client.get(
        "/api/connecteur/recherche", params={"q": "bonjour", "limite": 1, "apres": found["next"]}
    )
    assert changed.status_code == 409


def _longer(view: corrections.CorrectedView | None) -> corrections.CorrectedView | None:
    """The view with five lines in two chapters (the fake chain transcribes one)."""
    if view is None:
        return None
    turn = view.turns[0]
    turns = [turn.model_copy(update={"index": k}) for k in range(5)]
    phase = corrections.Phase(
        turn=0, end_turn=3, start=0.0, end=1.0, kind="discussion", title="Échauffement"
    )
    second = phase.model_copy(update={"turn": 3, "end_turn": 5, "title": "Scène de Marie"})
    return view.model_copy(update={"turns": turns, "phases": [phase, second]})


def test_a_long_transcript_is_read_in_parts_and_by_chapter(
    data: DataDir, recording: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client, session_id, space_id = _prepared(data, recording)
    _open(client, space_id)
    real = corrections.build_view
    monkeypatch.setattr(corrections, "build_view", lambda *a, **k: _longer(real(*a, **k)))
    path = f"/api/connecteur/seances/{session_id}/transcript"
    read: list[int] = []
    part = client.get(path, params={"nombre": 2}).json()
    while True:
        read += [t["index"] for t in part["turns"]]
        if part["next"] is None:
            break
        part = client.get(
            path, params={"nombre": 2, "depuis": part["next"], "vue": part["view"]}
        ).json()
    assert read == [0, 1, 2, 3, 4]  # nothing skipped, nothing twice
    chapter = client.get(path, params={"chapitre": 2}).json()
    assert chapter["phase"] == {"number": 2, "title": "Scène de Personne C"}
    assert [t["index"] for t in chapter["turns"]] == [3, 4] and chapter["next"] is None
    first = client.get(path, params={"chapitre": 1, "nombre": 2}).json()
    assert first["next"] == 2
    end = client.get(path, params={"chapitre": 1, "depuis": 2, "vue": first["view"]}).json()
    assert [t["index"] for t in end["turns"]] == [2] and end["next"] is None
    provenance = chapter["provenance"]
    assert provenance["corrections"] == 2 and provenance["duration_s"] >= 0
    assert set(provenance["models"]) <= {"transcribe", "align", "diarize", "attribute"}


def test_the_letters_changing_during_a_reading_are_said(data: DataDir, recording: Path) -> None:
    client, session_id, space_id = _prepared(data, recording)
    _open(client, space_id)
    path = f"/api/connecteur/seances/{session_id}/transcript"
    view = client.get(path).json()["view"]
    spaces.add_person(data, space_id, kind="guest", name="Bonjour")  # now a name too
    changed = client.get(path, params={"depuis": 0, "vue": view})
    assert changed.status_code == 409


def test_a_failed_summary_says_why(data: DataDir, recording: Path, fake_model: FakeModel) -> None:
    client, session_id, space_id = _prepared(data, recording)
    prov = generate(data, session_id, "resume-impro", "modele-essai", fake_model)
    folder = data.run_dir(session_id, prov.run_id)
    failed = prov.model_copy(
        update={
            "status": "failed",
            "error": GenerationError(type="X", message="Marie a tout cassé"),
        }
    )
    (folder / "provenance.json").write_text(failed.model_dump_json(), encoding="utf-8")
    _open(client, space_id)
    listed = client.get(f"/api/connecteur/seances/{session_id}").json()["generations"]
    assert len(listed) == 1  # listed all the same: said when read
    read = client.get(f"/api/connecteur/seances/{session_id}/resumes/{listed[0]['id']}")
    assert read.status_code == 409
    assert read.json()["detail"] == "La rédaction de ce résumé a échoué : Personne C a tout cassé"


def test_a_web_page_cannot_read_it(data: DataDir, recording: Path) -> None:
    client, _, space_id = _prepared(data, recording)
    _open(client, space_id)
    for headers in ({"Origin": "https://exemple.org"}, {"Sec-Fetch-Site": "cross-site"}):
        refused = client.get("/api/connecteur/seances", headers=headers)
        assert refused.status_code == 403, headers
    assert client.get("/api/reglages/connecteur/journal").json()["entries"] == []


def test_a_damaged_session_does_not_stop_the_others(data: DataDir, recording: Path) -> None:
    client, session_id, space_id = _prepared(data, recording)
    conn = connect(data)
    try:
        run_id = conn.execute(
            "SELECT run_id FROM active_run WHERE session_id = ? AND stage = 'attribute'",
            (session_id,),
        ).fetchone()["run_id"]
    finally:
        conn.close()
    (data.run_dir(session_id, run_id) / "output.json").write_text("{abîmé", encoding="utf-8")
    _open(client, space_id)
    found = client.get("/api/connecteur/recherche", params={"q": "bonjour"})
    assert found.status_code == 200
    assert found.json()["problems"] == [
        "« Répétition chez Personne A » n'a pas pu être lue pour la recherche."
    ]
    listed = client.get("/api/connecteur/seances").json()["sessions"]
    assert listed[0]["transcript_ready"] is False
    read = client.get(f"/api/connecteur/seances/{session_id}/transcript")
    assert read.status_code == 409 and "illisible" in read.json()["detail"]
