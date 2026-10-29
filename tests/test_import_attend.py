"""An import in one gesture waits for the people present before its first processing
(ADR 0069): started by `/lancer`, with or without them, or by itself after a while, even
across a restart. Other sessions do not wait behind it."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from coulisses_app import jobs
from coulisses_app.api import create_app
from coulisses_app.paths import DataDir
from coulisses_app.storage.db import ISO_FORMAT, connect

from .conftest import FAKE_CHAIN, local_client


@pytest.fixture
def client(data: DataDir) -> TestClient:
    return local_client(create_app(data, FAKE_CHAIN, profile="essai", processor=None, web_dir=None))


def import_(client: TestClient, recording: Path, **form: str) -> str:
    with recording.open("rb") as f:
        response = client.post(
            "/api/seances", files={"fichier": ("a.wav", f, "audio/wav")}, data=form
        )
    assert response.status_code == 201, response.text
    return response.json()["id"]


def claim(data: DataDir) -> jobs.Job | None:
    conn = connect(data)
    try:
        return jobs.claim_next(conn)
    finally:
        conn.close()


def test_the_processing_waits_for_the_attendees_then_starts_with_them(
    client: TestClient, data: DataDir, recording: Path
) -> None:
    session_id = import_(client, recording, attendre_presents="true")
    session = client.get(f"/api/seances/{session_id}").json()["session"]
    starts = datetime.strptime(session["processing_starts_at"], ISO_FORMAT).replace(tzinfo=UTC)
    waited = (starts - datetime.now(UTC)).total_seconds()
    assert jobs.WAIT_FOR_ATTENDEES_S - 5 < waited <= jobs.WAIT_FOR_ATTENDEES_S
    assert session["job_state"] == "queued"
    assert claim(data) is None  # neither the text nor the voices start

    client.put(f"/api/seances/{session_id}/presents", json={"unnamed": 3})
    started = client.post(f"/api/seances/{session_id}/lancer")
    assert started.status_code == 200, started.text
    assert started.json()["processing_starts_at"] is None
    job = claim(data)
    assert job is not None and isinstance(job.params, jobs.ChainParams)
    assert (job.session_id, job.params.attendees, job.params.starts_at) == (session_id, 3, None)
    # Started already: asked again, nothing changes.
    again = client.post(f"/api/seances/{session_id}/lancer")
    assert again.status_code == 200 and again.json()["job_state"] == "running"


def test_without_the_attendees_it_starts_alone_and_others_do_not_wait_behind_it(
    client: TestClient, data: DataDir, recording: Path
) -> None:
    waiting = import_(client, recording, attendre_presents="true")
    other = import_(client, recording)
    job = claim(data)
    assert job is not None and job.session_id == other
    assert claim(data) is None
    # Its time passed (the app closed meanwhile, or not): it starts, with nobody present.
    conn = connect(data)
    try:
        conn.execute(
            "UPDATE job SET params = json_set(params, '$.starts_at', '2000-01-01T00:00:00Z')"
            " WHERE session_id = ?",
            (waiting,),
        )
        conn.commit()
    finally:
        conn.close()
    session = client.get(f"/api/seances/{waiting}").json()["session"]
    assert session["processing_starts_at"] is None  # never a time already gone
    job = claim(data)
    assert job is not None and job.session_id == waiting
    assert isinstance(job.params, jobs.ChainParams) and job.params.attendees is None


def test_going_on_without_the_attendees_starts_at_once(
    client: TestClient, data: DataDir, recording: Path
) -> None:
    session_id = import_(client, recording, attendre_presents="true")
    assert client.post(f"/api/seances/{session_id}/lancer").json()["job_state"] == "queued"
    job = claim(data)
    assert job is not None and job.session_id == session_id


def test_an_import_that_does_not_wait_and_an_unknown_session(
    client: TestClient, recording: Path
) -> None:
    session_id = import_(client, recording, non_nommes="2")
    session = client.post(f"/api/seances/{session_id}/lancer").json()
    assert session["processing_starts_at"] is None and session["min_voices"] == 2
    assert client.post("/api/seances/inconnue/lancer").status_code == 404
