"""The language a session is transcribed in (ADR 0072): a default per space, one per
session until its text is made, passed to the engine; a processing waits for its language's
models rather than failing; « Refaire le texte » in another language; a language in use is
not removed. The engine's languages are `conftest.FakeLanguages`."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from coulisses.api import Provenance, StageName, execute_stage
from fastapi.testclient import TestClient

from coulisses_app import corrections, engine_models, jobs, languages, sessions, versions
from coulisses_app.api import create_app
from coulisses_app.paths import DataDir
from coulisses_app.processing import Processor
from coulisses_app.storage.db import connect

from .conftest import FAKE_CHAIN, FakeLanguages, local_client
from .test_import_attend import import_


class Removed:
    """Stands for the engine's `remove`: records what was removed."""

    def __init__(self) -> None:
        self.keys: list[str] = []

    def __call__(self, key: str, root: Path | None = None) -> None:
        self.keys.append(key)


@pytest.fixture
def removed() -> Removed:
    return Removed()


@pytest.fixture
def client(data: DataDir, removed: Removed) -> TestClient:
    store = engine_models.EngineModels("essai", discard=removed)
    return local_client(
        create_app(
            data, FAKE_CHAIN, profile="essai", processor=None, web_dir=None, engine_store=store
        )
    )


def claim(data: DataDir) -> jobs.Job | None:
    """The next chain job; the chapters queued after a processing are left aside."""
    conn = connect(data)
    try:
        with conn:
            conn.execute("UPDATE job SET state = 'done' WHERE kind = 'generation'")
        return jobs.claim_next(conn)
    finally:
        conn.close()


def run_next(data: DataDir) -> jobs.Job:
    job = claim(data)
    assert job is not None
    result = Processor(data, FAKE_CHAIN).run_job(job)
    assert result.error is None, result.error
    return job


def transcribed_in(data: DataDir, session_id: str) -> str | None:
    conn = connect(data)
    try:
        row = conn.execute(
            "SELECT run_id FROM active_run WHERE session_id = ? AND stage = 'transcribe'",
            (session_id,),
        ).fetchone()
    finally:
        conn.close()
    return versions.transcription_language(data, session_id, row["run_id"])


def session(client: TestClient, session_id: str) -> dict[str, Any]:
    return client.get(f"/api/seances/{session_id}").json()["session"]


# -- the languages ---------------------------------------------------------------------


def test_the_languages_are_the_engines_with_what_each_needs(client: TestClient) -> None:
    found = {lang["language"]: lang for lang in client.get("/api/langues").json()}
    assert list(found) == ["fr", "de", "en"]  # French first, then the engine's order
    assert found["fr"]["installed"] and found["fr"]["missing_models"] == []
    english = found["en"]
    assert (english["label"], english["installed"]) == ("Anglais", False)
    assert english["missing_models"] == ["aligneur-anglais"]
    assert english["download_bytes"] == 1_260_000_000
    assert english["models"] == ["aligneur-anglais", "transcripteur"]
    # The transcription model serves every language: never removed with one.
    assert english["own_models"] == ["aligneur-anglais"]
    assert found["fr"]["own_models"] == ["aligneur-francais"]
    assert english["used_by"] == {"spaces": [], "waiting_sessions": []}


def test_an_unknown_language_is_refused_with_the_possible_ones(
    client: TestClient, data: DataDir, recording: Path
) -> None:
    space = client.get("/api/espaces").json()[0]
    refused = client.patch(f"/api/espaces/{space['id']}", json={"language": "xx"})
    assert refused.status_code == 422
    assert refused.json()["detail"] == (
        "Cette langue n'est pas prise en charge. Langues possibles : français, allemand, anglais."
    )
    assert client.get("/api/espaces").json()[0]["language"] == "fr"  # nothing recorded
    with recording.open("rb") as f:
        response = client.post(
            "/api/seances", files={"fichier": ("a.wav", f, "audio/wav")}, data={"langue": "xx"}
        )
    assert response.status_code == 422
    assert client.get("/api/seances").json() == []


# -- a space, a session ----------------------------------------------------------------


def test_a_session_takes_its_spaces_language_and_keeps_it(
    client: TestClient, recording: Path
) -> None:
    first = client.get("/api/espaces").json()[0]
    assert first["language"] == "fr"  # every space so far is French
    made = client.post("/api/espaces", json={"name": "Meetings", "language": "en"}).json()
    assert made["language"] == "en"

    session_id = import_(client, recording, espace=str(made["id"]))
    assert session(client, session_id)["language"] == "en"
    # Neither changing the space's language nor moving the session changes it.
    client.patch(f"/api/espaces/{made['id']}", json={"language": "de"})
    client.put(f"/api/seances/{session_id}/espace", json={"espace": first["id"]})
    assert session(client, session_id)["language"] == "en"
    # Chosen at the import, it wins over the space's.
    chosen = import_(client, recording, espace=str(first["id"]), langue="de")
    assert session(client, chosen)["language"] == "de"


def test_the_language_changes_while_the_import_waits_not_once_the_text_is_made(
    client: TestClient, data: DataDir, recording: Path
) -> None:
    session_id = import_(client, recording, attendre_presents="true")
    before = session(client, session_id)
    assert before["language_editable"] is True

    changed = client.put(f"/api/seances/{session_id}/langue", json={"langue": "de"})
    assert changed.status_code == 200, changed.text
    assert changed.json()["language"] == "de"
    # The wait for the people present is not started again.
    assert changed.json()["processing_starts_at"] == before["processing_starts_at"]
    conn = connect(data)
    try:
        job = jobs.latest_job(conn, session_id)
    finally:
        conn.close()
    assert job is not None and isinstance(job.params, jobs.ChainParams)
    assert job.params.language == "de"

    client.put(f"/api/seances/{session_id}/langue", json={"langue": "fr"})
    client.post(f"/api/seances/{session_id}/lancer")
    run_next(data)
    after = session(client, session_id)
    assert (after["language"], after["language_editable"]) == ("fr", False)
    refused = client.put(f"/api/seances/{session_id}/langue", json={"langue": "en"})
    assert refused.status_code == 409
    assert "Refaire le texte" in refused.json()["detail"]


def test_a_recording_takes_its_language_while_it_records(data: DataDir) -> None:
    conn = connect(data)
    try:
        with conn:
            conn.execute("UPDATE space SET language = 'en'")
    finally:
        conn.close()
    session_id, _ = sessions.start_capture(
        data,
        space_id=None,
        attendee_ids=[],
        unnamed_attendees=None,
        device="Micro",
        sample_rate=48000,
        channels=1,
    )
    made = sessions.get_session(data, session_id)
    assert made is not None and (made.language, made.language_editable) == ("en", True)
    assert sessions.set_language(data, session_id, "fr").language == "fr"


def test_an_older_job_is_in_french() -> None:
    params = jobs.ChainParams.model_validate_json('{"v": 1, "profile": "essai"}')
    assert (params.language, params.waits_for_models) == ("fr", None)


# -- the engine, and the wait for a model ----------------------------------------------


def test_a_processing_waits_for_its_languages_model_then_goes(
    client: TestClient, data: DataDir, recording: Path, fake_languages: FakeLanguages
) -> None:
    english = import_(client, recording, langue="en")
    french = import_(client, recording)

    # Claimed, it goes back to wait before any stage ran: not a failure.
    held = claim(data)
    assert held is not None and held.session_id == english
    assert Processor(data, FAKE_CHAIN).run_job(held).held
    waiting = session(client, english)
    assert waiting["job_state"] == "queued"
    assert waiting["processing_waits_for"] == {
        "reason": "model_missing",
        "language": "en",
        "label": "Anglais",
        "missing_models": ["aligneur-anglais"],
        "download_bytes": 1_260_000_000,
    }
    assert client.get(f"/api/seances/{english}").json()["stages"]  # still readable
    # The other sessions do not wait behind it.
    assert run_next(data).session_id == french
    assert claim(data) is None

    fake_languages.install("aligneur-anglais")
    Processor(data, FAKE_CHAIN).release_waiting()  # after the download, or at start
    assert session(client, english)["processing_waits_for"] is None
    job = run_next(data)
    assert job.session_id == english
    assert transcribed_in(data, english) == "en"  # from the engine's provenance
    assert session(client, english)["language"] == "en"
    listed = client.get(f"/api/seances/{english}/versions").json()["versions"]
    assert [v["language"] for v in listed] == ["en"]


def test_choosing_another_language_releases_a_waiting_session(
    client: TestClient, data: DataDir, recording: Path
) -> None:
    session_id = import_(client, recording, langue="en")
    held = claim(data)
    assert held is not None and Processor(data, FAKE_CHAIN).run_job(held).held
    assert claim(data) is None

    # « Traiter en français »
    changed = client.put(f"/api/seances/{session_id}/langue", json={"langue": "fr"})
    assert changed.json()["processing_waits_for"] is None
    run_next(data)
    assert transcribed_in(data, session_id) == "fr"


def test_a_language_the_engine_no_longer_handles_waits_for_another(
    client: TestClient, data: DataDir, recording: Path
) -> None:
    session_id = import_(client, recording)
    conn = connect(data)
    try:
        with conn:  # as if chosen when the engine still had it
            conn.execute(
                "UPDATE job SET params = json_set(params, '$.language', 'nl') WHERE session_id = ?",
                (session_id,),
            )
            conn.execute("UPDATE session SET language = 'nl' WHERE id = ?", (session_id,))
    finally:
        conn.close()
    held = claim(data)
    assert held is not None and Processor(data, FAKE_CHAIN).run_job(held).held
    assert session(client, session_id)["processing_waits_for"] == {
        "reason": "language_unsupported",
        "language": "nl",
        "label": None,
        "missing_models": [],
        "download_bytes": 0,
    }


def test_a_refusal_of_the_engine_for_its_language_is_said_in_french() -> None:
    refused = Provenance.model_construct(
        inputs={},
        coulisses_version="1.14.0",
        error=type(
            "E",
            (),
            {
                "code": type("C", (), {"value": "language_unsupported"})(),
                "details": {"language": "nl"},
            },
        )(),
    )
    said = languages.said_failure(refused, "essai")
    assert said is not None and said.startswith("La langue « nl » n'est pas prise en charge")
    assert "français, allemand, anglais" in said


def test_the_language_of_a_transcription_comes_from_its_provenance() -> None:
    def made(inputs: dict[str, Any], engine: str) -> Provenance:
        return Provenance.model_construct(inputs=inputs, coulisses_version=engine)

    assert languages.of_transcription(made({"language": "en"}, "1.14.0")) == "en"
    # Before the engine had languages: French, the only one then.
    assert languages.of_transcription(made({}, "1.13.2")) == "fr"
    # Later, one that does not say it is never taken for French.
    assert languages.of_transcription(made({}, "1.14.0")) is None


# -- « Refaire le texte » in another language ------------------------------------------


def test_the_text_made_again_in_another_language_keeps_the_names(
    client: TestClient, data: DataDir, recording: Path, fake_languages: FakeLanguages
) -> None:
    fake_languages.install("aligneur-anglais")
    session_id = import_(client, recording)
    run_next(data)
    corrections.add(data, session_id, {"kind": "assign_speaker", "speaker": "S1", "name": "Marie"})
    first = client.get(f"/api/seances/{session_id}/versions").json()["versions"][0]["run_id"]

    refused = client.post(
        f"/api/seances/{session_id}/relancer", json={"etape": "diarize", "langue": "en"}
    )
    assert refused.status_code == 422
    asked = client.post(
        f"/api/seances/{session_id}/relancer", json={"etape": "transcribe", "langue": "en"}
    )
    assert asked.status_code == 202, asked.text
    # Until the new version is shown, the session keeps the language of the one shown.
    assert asked.json()["language"] == "fr"
    assert asked.json()["language_editable"] is False
    run_next(data)

    after = session(client, session_id)
    assert after["language"] == "en"
    listed = client.get(f"/api/seances/{session_id}/versions").json()["versions"]
    assert [(v["origin"], v["language"]) for v in listed] == [
        ("transcribe", "en"),
        ("first", "fr"),
    ]
    view = corrections.build_view(data, session_id)
    assert view is not None and "Marie" in {s.name for s in view.speakers if s.name}

    # The former version, shown again, in its language.
    client.post(f"/api/seances/{session_id}/versions/{first}/afficher")
    assert session(client, session_id)["language"] == "fr"


def test_a_rerun_in_a_language_without_its_model_waits(
    client: TestClient, data: DataDir, recording: Path
) -> None:
    session_id = import_(client, recording)
    run_next(data)
    client.post(f"/api/seances/{session_id}/relancer", json={"etape": "all", "langue": "en"})
    held = claim(data)
    assert held is not None and Processor(data, FAKE_CHAIN).run_job(held).held
    waiting = session(client, session_id)
    assert waiting["processing_waits_for"]["language"] == "en"
    assert waiting["language"] == "fr"  # nothing changes before the new version is shown


# -- removing a language ---------------------------------------------------------------


def test_a_language_in_use_is_not_removed_and_says_where(
    client: TestClient, data: DataDir, recording: Path, removed: Removed
) -> None:
    space = client.post("/api/espaces", json={"name": "Meetings", "language": "en"}).json()
    session_id = import_(client, recording, espace=str(space["id"]))
    held = claim(data)
    assert held is not None and Processor(data, FAKE_CHAIN).run_job(held).held
    conn = connect(data)
    try:
        with conn:
            conn.execute("UPDATE session SET title = 'Point du lundi' WHERE id = ?", (session_id,))
    finally:
        conn.close()

    used = {lang["language"]: lang for lang in client.get("/api/langues").json()}["en"]["used_by"]
    assert [s["name"] for s in used["spaces"]] == ["Meetings"]
    assert [s["id"] for s in used["waiting_sessions"]] == [session_id]

    refused = client.delete("/api/moteur/modeles/aligneur-anglais")
    assert refused.status_code == 409
    assert refused.json()["detail"] == (
        "La langue « Anglais » sert encore : c'est la langue de l'espace « Meetings », et une "
        "séance attend ce modèle (« Point du lundi »). Changez-les d'abord."
    )
    assert removed.keys == []

    client.patch(f"/api/espaces/{space['id']}", json={"language": "fr"})
    client.put(f"/api/seances/{session_id}/langue", json={"langue": "fr"})
    assert client.delete("/api/moteur/modeles/aligneur-anglais").status_code == 204
    # A model every language needs is not a language's: removed as before.
    assert client.delete("/api/moteur/modeles/transcripteur").status_code == 204
    assert removed.keys == ["aligneur-anglais", "transcripteur"]


# -- what the review asked for ---------------------------------------------------------


def test_a_waiting_job_stopped_then_resumed_is_seen_again(
    client: TestClient, data: DataDir, recording: Path, fake_languages: FakeLanguages
) -> None:
    session_id = import_(client, recording, langue="en")
    held = claim(data)
    assert held is not None and Processor(data, FAKE_CHAIN).run_job(held).held
    assert client.post(f"/api/seances/{session_id}/arreter").status_code == 200
    fake_languages.install("aligneur-anglais")  # while it was stopped: nothing saw it

    assert client.post(f"/api/seances/{session_id}/reprendre").status_code == 200
    assert session(client, session_id)["processing_waits_for"] is None
    assert run_next(data).session_id == session_id
    assert transcribed_in(data, session_id) == "en"


def failing_at(stage: StageName) -> Any:
    """The engine's stage runner, failing at this stage."""

    def engine_stage(session_id: str, models: Path | None) -> Any:
        run = execute_stage(session_id, models)

        def run_stage(at: StageName, *args: Any) -> Any:
            if at == stage:
                raise RuntimeError(f"{at.value} en échec pour l'essai")
            return run(at, *args)

        return run_stage

    return engine_stage


def test_a_rerun_that_fails_leaves_the_language_as_it_was(
    client: TestClient, data: DataDir, recording: Path, fake_languages: FakeLanguages
) -> None:
    fake_languages.install("aligneur-anglais")
    session_id = import_(client, recording)
    run_next(data)
    client.post(f"/api/seances/{session_id}/relancer", json={"etape": "transcribe", "langue": "en"})
    job = claim(data)
    assert job is not None
    failed = Processor(data, FAKE_CHAIN, engine_stage=failing_at(StageName.ATTRIBUTE)).run_job(job)
    assert failed.error is not None
    assert session(client, session_id)["language"] == "fr"
    assert transcribed_in(data, session_id) == "fr"


def test_once_a_transcription_succeeded_the_language_no_longer_changes(
    client: TestClient, data: DataDir, recording: Path
) -> None:
    session_id = import_(client, recording)
    job = claim(data)
    assert job is not None
    failed = Processor(data, FAKE_CHAIN, engine_stage=failing_at(StageName.ATTRIBUTE)).run_job(job)
    assert failed.error is not None
    assert session(client, session_id)["language_editable"] is False
    assert client.put(f"/api/seances/{session_id}/langue", json={"langue": "de"}).status_code == 409


def test_a_finished_download_releases_what_waited_for_it(data: DataDir) -> None:
    processor = Processor(data, FAKE_CHAIN)
    store = engine_models.EngineModels("essai")
    create_app(
        data, FAKE_CHAIN, profile="essai", processor=processor, web_dir=None, engine_store=store
    )
    assert store.after_install == processor.after_install


def test_a_language_the_chain_does_not_align_is_not_offered(
    client: TestClient, fake_languages: FakeLanguages
) -> None:
    fake_languages.unaligned.add("de")
    assert [lang["language"] for lang in client.get("/api/langues").json()] == ["fr", "en"]
    space = client.get("/api/espaces").json()[0]
    assert client.patch(f"/api/espaces/{space['id']}", json={"language": "de"}).status_code == 422


def test_a_model_some_languages_share_stays_while_one_of_them_serves(
    client: TestClient, removed: Removed, fake_languages: FakeLanguages
) -> None:
    fake_languages.aligners["de"] = "aligneur-germanique"
    fake_languages.aligners["en"] = "aligneur-germanique"
    english = {lang["language"]: lang for lang in client.get("/api/langues").json()}["en"]
    assert english["own_models"] == []  # neither's own
    client.post("/api/espaces", json={"name": "Meetings", "language": "en"})
    refused = client.delete("/api/moteur/modeles/aligneur-germanique")
    assert refused.status_code == 409 and "Meetings" in refused.json()["detail"]
    assert removed.keys == []


def test_the_voices_of_a_version_whose_language_is_unknown_can_be_made_again(
    client: TestClient, data: DataDir, recording: Path
) -> None:
    session_id = import_(client, recording)
    run_next(data)
    conn = connect(data)
    try:
        row = conn.execute(
            "SELECT run_id FROM active_run WHERE session_id = ? AND stage = 'transcribe'",
            (session_id,),
        ).fetchone()
    finally:
        conn.close()
    provenance = data.run_dir(session_id, row["run_id"]) / "provenance.json"
    raw = json.loads(provenance.read_text(encoding="utf-8"))
    del raw["inputs"]["language"]  # a provenance of v1.14 that does not say it
    provenance.write_text(json.dumps(raw), encoding="utf-8")
    assert transcribed_in(data, session_id) is None

    for redone in ("transcribe", "all"):
        text = client.post(f"/api/seances/{session_id}/relancer", json={"etape": redone})
        assert text.status_code == 422 and "inconnue" in text.json()["detail"]
    voices = client.post(f"/api/seances/{session_id}/relancer", json={"etape": "diarize"})
    assert voices.status_code == 202, voices.text
    run_next(data)
    assert session(client, session_id)["language"] == "fr"  # left as it was


def test_a_failure_to_release_at_start_never_stops_the_service(data: DataDir) -> None:
    processor = Processor(data, FAKE_CHAIN)

    def broken() -> None:
        raise RuntimeError("base verrouillée")

    processor.release_waiting = broken  # type: ignore[method-assign]
    processor.start()
    try:
        assert processor.release_error == "RuntimeError : base verrouillée"
    finally:
        processor.stop()


def test_a_failure_after_a_download_is_said_by_the_service(data: DataDir) -> None:
    processor = Processor(data, FAKE_CHAIN)

    def broken() -> None:
        raise RuntimeError("base verrouillée")

    working = processor.release_waiting
    processor.release_waiting = broken  # type: ignore[method-assign]
    processor.after_install()
    assert processor.release_error == "RuntimeError : base verrouillée"
    processor.loop_error = None  # a job of the loop ending says nothing about it
    assert processor.release_error is not None
    processor.release_waiting = working  # type: ignore[method-assign]
    processor.after_install()  # seen again: no longer said
    assert processor.release_error is None
