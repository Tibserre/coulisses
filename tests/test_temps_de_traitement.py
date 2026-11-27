"""The processing times, exported by the user with this Mac's description (ADR 0095): each
engine run, failed ones included, without anything of a session (no title, name or text)."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from coulisses_app import machine
from coulisses_app.api import create_app
from coulisses_app.paths import DataDir

from .conftest import FAKE_CHAIN, local_client
from .test_spaces_api import processed_session


@pytest.fixture
def client(data: DataDir) -> TestClient:
    return local_client(create_app(data, FAKE_CHAIN, profile="essai", processor=None, web_dir=None))


def test_each_run_is_exported_with_the_mac_and_nothing_of_the_session(
    client: TestClient, data: DataDir, recording: Path
) -> None:
    space_id = client.get("/api/espaces").json()[0]["id"]
    client.post(f"/api/espaces/{space_id}/glossaire", json={"term": "Zorglub"})
    session_id = processed_session(client, data, recording)
    client.patch(f"/api/seances/{session_id}", json={"title": "Répétition secrète"})

    from coulisses.api import read_provenance

    from coulisses_app.storage.db import connect

    conn = connect(data)
    transcription = conn.execute("SELECT id FROM run WHERE stage = 'transcribe'").fetchone()[0]
    conn.close()
    heard = read_provenance(data.run_dir(session_id, transcription))
    assert heard is not None and "Zorglub" in str(heard.inputs)  # there, and left out below

    answer = client.get("/api/temps-de-traitement")

    assert answer.status_code == 200
    assert "attachment" in answer.headers["content-disposition"]
    text = answer.text
    for secret in (session_id, "Zorglub", "Répétition secrète", "a.wav", str(data.root)):
        assert secret not in text
    export = answer.json()
    assert export["machine"]["memory_gb"] == machine.memory_gb()
    assert export["machine"]["engine_version"] and export["machine"]["app_version"]
    (session,) = export["sessions"]
    assert session["session"] == 1 and session["audio_s"] > 0
    stages = [run["stage"] for run in session["runs"]]
    assert set(stages) == {"transcribe", "align", "diarize", "attribute"}
    for run in session["runs"]:
        assert run["status"] == "succeeded" and run["duration_s"] >= 0
        assert run["processing"] == 1 and run["engine_id"]


def test_a_failed_attempt_stays_beside_the_one_that_succeeded(
    data: DataDir, recording: Path
) -> None:
    from coulisses.api import StageConfig

    from coulisses_app import jobs
    from coulisses_app.processing import Processor
    from coulisses_app.storage.db import connect

    refused = FAKE_CHAIN.model_copy(
        update={"diarize": StageConfig(engine="fake_under_segmenting")}
    )  # finds one voice whatever the attendees
    client = local_client(create_app(data, refused, profile="essai", processor=None, web_dir=None))

    def run_next() -> None:
        conn = connect(data)
        try:
            job = jobs.claim_next(conn)
        finally:
            conn.close()
        assert job is not None
        Processor(data, refused).run_job(job)

    with recording.open("rb") as f:
        session_id = client.post(
            "/api/seances", files={"fichier": ("a.wav", f, "audio/wav")}, data={"non_nommes": "3"}
        ).json()["id"]
    run_next()  # the diarization refused: too few voices
    client.post(f"/api/seances/{session_id}/reprendre", json={"presents": 1})
    run_next()

    runs = client.get("/api/temps-de-traitement").json()["sessions"][0]["runs"]
    voices = [r for r in runs if r["stage"] == "diarize"]
    assert [r["status"] for r in voices] == ["failed", "succeeded"]
    assert voices[0]["error_code"] == "too_few_speakers"
    assert [r["min_speakers"] for r in voices] == [3, 1]
    assert len([r for r in runs if r["stage"] == "transcribe"]) == 1  # reused, not redone


def test_the_mac_is_described_by_macos_itself() -> None:
    described = machine.describe()
    assert described["memory_gb"] == machine.memory_gb()
    assert set(described) >= {"chip", "cores", "performance_cores", "efficiency_cores", "macos"}


def test_only_names_numbers_and_flags_of_the_settings_go_out() -> None:
    from coulisses_app.processing_times import technical

    settings = {
        "model": "qwen3-asr-1.7b-8bit",
        "threads": 6,
        "device": "mps",
        "use_glossary": True,
        "threshold": None,
        "hotwords": ["Zorglub"],
        "prompt": "Une répétition de la troupe",
        "joined": "Zorglub,Fantasio",
        "models": {"fr": "bofenghuang/asr-wav2vec2-ctc-french", "note": "deux mots"},
    }
    assert technical(settings) == {
        "model": "qwen3-asr-1.7b-8bit",
        "threads": 6,
        "device": "mps",
        "use_glossary": True,
        "threshold": None,
        "models": {"fr": "bofenghuang/asr-wav2vec2-ctc-french"},
    }
    assert technical({"lib": "WeSpeaker, segments alone >= 1.0 s"}, names_only=False) == {
        "lib": "WeSpeaker, segments alone >= 1.0 s"
    }


def test_a_run_without_its_provenance_is_said_absent_or_unreadable(
    client: TestClient, data: DataDir, recording: Path
) -> None:
    import shutil

    from coulisses_app.storage.db import connect

    session_id = processed_session(client, data, recording)
    conn = connect(data)
    rows = dict(conn.execute("SELECT stage, id FROM run").fetchall())
    conn.close()
    shutil.rmtree(data.run_dir(session_id, rows["align"]))
    (data.run_dir(session_id, rows["diarize"]) / "provenance.json").write_text("{abîmé")

    runs = client.get("/api/temps-de-traitement").json()["sessions"][0]["runs"]
    said = {r["stage"]: r["provenance"] for r in runs}
    assert said == {
        "transcribe": "lue",
        "align": "absente",
        "diarize": "illisible",
        "attribute": "lue",
    }
