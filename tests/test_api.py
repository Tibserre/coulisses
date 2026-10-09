"""The service as the interface sees it: import, follow, read, listen — offline."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from coulisses_app import jobs, sessions
from coulisses_app.api import create_app
from coulisses_app.paths import DataDir
from coulisses_app.processing import Processor
from coulisses_app.storage.db import connect

from .conftest import FAKE_CHAIN


@pytest.fixture
def client(data: DataDir) -> TestClient:
    app = create_app(data, FAKE_CHAIN, profile="essai", processor=None, web_dir=None)
    return TestClient(app)


def upload(client: TestClient, recording: Path, **form: Any) -> str:
    with recording.open("rb") as f:
        response = client.post(
            "/api/seances", files={"fichier": ("Mardi soir.wav", f, "audio/wav")}, data=form
        )
    assert response.status_code == 201, response.text
    return response.json()["id"]


def process_next(data: DataDir) -> None:
    conn = connect(data)
    try:
        job = jobs.claim_next(conn)
    finally:
        conn.close()
    assert job is not None
    Processor(data, FAKE_CHAIN).run_job(job)


def test_the_service_reports_where_its_data_lives(client: TestClient, data: DataDir) -> None:
    info = client.get("/api/etat").json()
    assert info["data_dir"] == str(data.root)
    assert info["engine_version"].startswith("1.")


def test_import_then_follow_then_read(client: TestClient, data: DataDir, recording: Path) -> None:
    session_id = upload(client, recording, non_nommes="2", date_fichier_ms="1759600000000")
    listed = client.get("/api/seances").json()
    assert [s["id"] for s in listed] == [session_id]
    assert listed[0]["job_state"] == "queued"
    assert listed[0]["recorded_at"] == "2025-10-04T17:46:40Z"

    detail = client.get(f"/api/seances/{session_id}").json()
    assert [s["state"] for s in detail["stages"]] == ["pending"] * 4
    assert detail["source"]["original_name"] == "Mardi soir.wav"
    assert client.get(f"/api/seances/{session_id}/transcript").status_code == 404

    process_next(data)
    detail = client.get(f"/api/seances/{session_id}").json()
    assert [s["state"] for s in detail["stages"]] == ["succeeded"] * 4
    assert detail["session"]["job_state"] == "done"

    transcript = client.get(f"/api/seances/{session_id}/transcript").json()
    assert transcript["turns"][0]["words"][0]["text"] == "bonjour"
    assert transcript["speakers"][0]["name"] == "Locuteur 1"

    run_id = detail["stages"][0]["run_id"]
    prov = client.get(f"/api/seances/{session_id}/executions/{run_id}/provenance").json()
    assert prov["status"] == "succeeded"
    assert prov["coulisses_version"]


def test_the_audio_plays_from_any_point(client: TestClient, recording: Path) -> None:
    session_id = upload(client, recording)
    whole = client.get(f"/api/seances/{session_id}/audio")
    assert whole.status_code == 200
    assert whole.content == recording.read_bytes()
    part = client.get(f"/api/seances/{session_id}/audio", headers={"Range": "bytes=100-199"})
    assert part.status_code == 206
    assert part.content == recording.read_bytes()[100:200]


def test_an_unreadable_file_gets_a_french_message(client: TestClient, tmp_path: Path) -> None:
    bad = tmp_path / "notes.wav"
    bad.write_text("pas du son", encoding="utf-8")
    with bad.open("rb") as f:
        response = client.post("/api/seances", files={"fichier": ("notes.wav", f, "audio/wav")})
    assert response.status_code == 422
    detail = response.json()["detail"]
    assert "ffmpeg" in detail
    assert "imports-en-cours" not in detail  # no internal path shown to the user


def test_zero_attendees_is_refused(client: TestClient, recording: Path) -> None:
    with recording.open("rb") as f:
        response = client.post(
            "/api/seances", files={"fichier": ("a.wav", f, "audio/wav")}, data={"non_nommes": "0"}
        )
    assert response.status_code == 422


def test_only_a_failed_processing_can_be_resumed(
    client: TestClient, data: DataDir, recording: Path
) -> None:
    session_id = upload(client, recording)
    assert client.post(f"/api/seances/{session_id}/reprendre").status_code == 409
    (data.sources_dir(session_id) / "ref.wav").unlink()
    process_next(data)
    detail = client.get(f"/api/seances/{session_id}").json()
    assert detail["session"]["job_state"] == "failed"
    assert "introuvable" in detail["session"]["job_error"]
    assert detail["source"]["file_present"] is False
    resumed = client.post(f"/api/seances/{session_id}/reprendre")
    assert resumed.status_code == 200
    assert resumed.json()["job_state"] == "queued"


def test_unknown_things_are_404_in_french(client: TestClient) -> None:
    response = client.get("/api/seances/inconnue")
    assert response.status_code == 404
    assert response.json()["detail"] == "Séance introuvable."


def test_without_a_built_interface_the_page_says_how_to_build_it(client: TestClient) -> None:
    page = client.get("/")
    assert page.status_code == 200
    assert "npm run build" in page.text


def test_the_whole_journey_opens_no_network_connection(
    client: TestClient, data: DataDir, recording: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """P1 for the service's own process; each engine stage cuts its network itself."""
    attempts: list[object] = []

    def refuse(self: object, address: object) -> None:
        attempts.append(address)
        raise OSError("réseau coupé pendant le test")

    monkeypatch.setattr("socket.socket.connect", refuse)
    monkeypatch.setattr("socket.socket.connect_ex", refuse)
    session_id = upload(client, recording, non_nommes="2")
    process_next(data)
    assert client.get(f"/api/seances/{session_id}/transcript").status_code == 200
    assert client.get(f"/api/seances/{session_id}/audio").status_code == 200
    assert attempts == []


def test_after_too_few_voices_the_processing_resumes_with_fewer_attendees(
    data: DataDir, recording: Path
) -> None:
    from coulisses.api import StageConfig

    refused = FAKE_CHAIN.model_copy(
        update={"diarize": StageConfig(engine="fake_under_segmenting")}
    )  # finds one voice whatever the attendees
    client = TestClient(create_app(data, refused, profile="essai", processor=None, web_dir=None))
    session_id = upload(client, recording, non_nommes="3")

    def run_next() -> None:
        conn = connect(data)
        try:
            job = jobs.claim_next(conn)
        finally:
            conn.close()
        assert job is not None
        Processor(data, refused).run_job(job)

    run_next()
    stages = {s["stage"]: s for s in client.get(f"/api/seances/{session_id}").json()["stages"]}
    assert stages["diarize"]["error_code"] == "too_few_speakers"
    transcription = stages["transcribe"]["run_id"]

    assert (
        client.post(f"/api/seances/{session_id}/reprendre", json={"presents": 0}).status_code == 422
    )
    resumed = client.post(f"/api/seances/{session_id}/reprendre", json={"presents": 1})
    assert resumed.status_code == 200
    assert resumed.json()["min_voices"] == 1
    assert resumed.json()["unnamed_attendees"] == 3  # who was there does not change
    run_next()
    detail = client.get(f"/api/seances/{session_id}").json()
    assert detail["session"]["job_state"] == "done"
    stages = {s["stage"]: s for s in detail["stages"]}
    assert stages["transcribe"]["run_id"] == transcription  # not redone


def test_the_attendees_cannot_change_after_another_failure(
    client: TestClient, data: DataDir, recording: Path
) -> None:
    session_id = upload(client, recording, non_nommes="2")
    (data.sources_dir(session_id) / "ref.wav").unlink()  # fails before any diarization
    process_next(data)
    refused = client.post(f"/api/seances/{session_id}/reprendre", json={"presents": 1})
    assert refused.status_code == 409
    assert "trop peu de voix" in refused.json()["detail"]
    detail = client.get(f"/api/seances/{session_id}").json()
    assert detail["session"]["min_voices"] == 2  # untouched
    assert detail["session"]["job_state"] == "failed"


def test_the_page_is_checked_again_at_each_load_so_a_new_build_shows(
    data: DataDir, tmp_path: Path
) -> None:
    web = tmp_path / "web"
    (web / "assets").mkdir(parents=True)
    (web / "index.html").write_text("<!doctype html><title>Coulisses</title>")
    (web / "assets" / "index-abc.js").write_text("console.log(1)")
    client = TestClient(create_app(data, FAKE_CHAIN, profile="essai", processor=None, web_dir=web))
    assert client.get("/").headers["cache-control"] == "no-cache"
    assert "cache-control" not in client.get("/assets/index-abc.js").headers


def test_the_app_asks_what_quitting_would_interrupt(data: DataDir, recording: Path) -> None:
    client = TestClient(create_app(data, FAKE_CHAIN, profile="essai", processor=None, web_dir=None))
    assert client.get("/api/activite").json() == {"recording": False, "processing": False}
    with recording.open("rb") as f:
        sessions.import_recording(
            data, f, recording.name, unnamed_attendees=1, recorded_at=None, profile="essai"
        )
    conn = connect(data)
    jobs.claim_next(conn)  # running now
    conn.close()
    assert client.get("/api/activite").json() == {"recording": False, "processing": True}


def test_the_settings_show_the_folders_in_the_finder(
    data: DataDir, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    import subprocess

    from coulisses_app import api

    opened: list[list[str]] = []
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda command, **_: opened.append(command),  # pyright: ignore[reportUnknownLambdaType]
    )
    monkeypatch.setattr(api, "SERVICE_LOG", tmp_path / "absent.log")
    client = TestClient(create_app(data, FAKE_CHAIN, profile="essai", processor=None, web_dir=None))
    folders = client.get("/api/dossiers").json()
    assert folders["data"] == str(data.root) and folders["log"] is None
    data.root.mkdir(parents=True, exist_ok=True)
    assert client.post("/api/dossiers/donnees/ouvrir").status_code == 204
    assert opened == [["open", str(data.root)]]
    assert client.post("/api/dossiers/journal/ouvrir").status_code == 404  # not yet
    assert client.post("/api/dossiers/ailleurs/ouvrir").status_code == 422  # nothing else


def test_a_recording_in_progress_is_what_quitting_would_interrupt(data: DataDir) -> None:
    from coulisses_app import capture

    class Recording(capture.Recorder):
        def state(self) -> capture.RecordingState | None:
            return capture.RecordingState(
                session_id="s",
                state="recording",
                elapsed_s=1.0,
                device="Micro",
                channels=1,
                levels=capture.Levels(peak_db=-20, rms_db=-30),
                too_quiet=False,
                clipping=False,
            )

        def shutdown(self, *, profile: str) -> None:
            pass

    client = TestClient(
        create_app(
            data,
            FAKE_CHAIN,
            profile="essai",
            processor=None,
            web_dir=None,
            recorder=Recording(data),
        )
    )
    assert client.get("/api/activite").json() == {"recording": True, "processing": False}
