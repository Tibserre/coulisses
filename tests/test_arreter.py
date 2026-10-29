"""The user stops a processing (« si en fait je ne veux pas la faire »), or deletes its
session while it runs (a file imported by mistake): the running stages are cancelled by the
engine and kept as it closed them (P5), the stopped job says so, « Reprendre » goes on."""

from __future__ import annotations

from pathlib import Path

import pytest
from coulisses.api import StageConfig

from coulisses_app import jobs, processing
from coulisses_app.api import create_app
from coulisses_app.paths import DataDir
from coulisses_app.processing import Processor

from .conftest import FAKE_CHAIN, local_client
from .test_processing import SLOW_CHAIN, claim, import_, job_state, runs, wait_for

SLOW_REFUSED = SLOW_CHAIN.model_copy(
    update={"diarize": StageConfig(engine="fake_under_segmenting")}
)


def started(data: DataDir, session_id: str) -> bool:
    return any(
        r["status"] == "running" and (data.run_dir(session_id, r["id"]) / "spec.json").is_file()
        for r in runs(data, session_id)
    )


def test_a_running_processing_is_stopped_and_resumed(data: DataDir, recording: Path) -> None:
    session_id = import_(data, recording)
    processor = Processor(data, SLOW_CHAIN)
    client = local_client(
        create_app(data, SLOW_CHAIN, profile="essai", processor=processor, web_dir=None)
    )
    processor.start()
    try:
        wait_for(lambda: started(data, session_id))
        wait_for(
            lambda: any(
                r["stage"] == "diarize" and r["status"] == "succeeded"
                for r in runs(data, session_id)
            )
        )
        response = client.post(f"/api/seances/{session_id}/arreter")
        assert response.status_code == 200, response.text
        session = response.json()
        assert session["processing_stopped"] is True
        assert (session["job_state"], session["job_error"]) == ("failed", jobs.STOPPED)
        transcribe = next(r for r in runs(data, session_id) if r["stage"] == "transcribe")
        assert transcribe["status"] == "failed" and "Cancelled" in transcribe["error_summary"]
        assert data.run_dir(session_id, transcribe["id"]).is_dir()  # kept as it ended
        diarize = next(r for r in runs(data, session_id) if r["stage"] == "diarize")
        assert diarize["status"] == "succeeded"
        # Nothing to stop any more.
        assert client.post(f"/api/seances/{session_id}/arreter").status_code == 409

        resumed = client.post(f"/api/seances/{session_id}/reprendre").json()
        assert resumed["processing_stopped"] is False and resumed["job_state"] != "failed"
        # The voices are not made again.
        wait_for(
            lambda: len([r for r in runs(data, session_id) if r["stage"] == "transcribe"]) == 2
        )
        assert [r["id"] for r in runs(data, session_id) if r["stage"] == "diarize"] == [
            diarize["id"]
        ]
    finally:
        processor.stop()


def test_a_session_is_deleted_while_it_is_processed(data: DataDir, recording: Path) -> None:
    session_id = import_(data, recording)
    processor = Processor(data, SLOW_CHAIN)
    client = local_client(
        create_app(data, SLOW_CHAIN, profile="essai", processor=processor, web_dir=None)
    )
    processor.start()
    try:
        wait_for(lambda: started(data, session_id))
        response = client.delete(f"/api/seances/{session_id}")
        assert response.status_code == 200, response.text
        assert client.get(f"/api/seances/{session_id}").status_code == 404
        assert not data.session_dir(session_id).exists()
    finally:
        processor.stop()


def test_a_processing_waiting_in_the_queue_is_stopped_before_it_starts(
    data: DataDir, recording: Path
) -> None:
    session_id = import_(data, recording)
    client = local_client(
        create_app(data, FAKE_CHAIN, profile="essai", processor=None, web_dir=None)
    )
    session = client.post(f"/api/seances/{session_id}/arreter").json()
    assert session["processing_stopped"] is True
    conn_job = job_state(data, session_id)
    assert isinstance(conn_job.params, jobs.ChainParams) and conn_job.params.stopped_at
    assert runs(data, session_id) == []
    client.post(f"/api/seances/{session_id}/reprendre")
    job = claim(data)
    assert isinstance(job.params, jobs.ChainParams) and job.params.stopped_at is None
    assert Processor(data, FAKE_CHAIN).run_job(job).error is None
    assert client.post("/api/seances/inconnue/arreter").status_code == 404


def test_a_job_stopped_as_it_was_claimed_starts_no_stage(data: DataDir, recording: Path) -> None:
    session_id = import_(data, recording)
    job = claim(data)
    processor = Processor(data, FAKE_CHAIN)
    processor._stopped_by_user.add(job.id)  # pyright: ignore[reportPrivateUsage]  # stopped meanwhile
    assert processor.run_job(job).error == jobs.STOPPED
    assert job_state(data, session_id).state == "failed"
    assert runs(data, session_id) == []


def test_a_stage_that_failed_for_real_is_still_said_after_a_stop(
    data: DataDir, recording: Path
) -> None:
    """The voices refused (too few), then the user stops the text: what the session says
    is that refusal and what to do, not « arrêté » (P8)."""
    session_id = import_(data, recording, attendees=9)
    processor = Processor(data, SLOW_REFUSED)
    processor.start()
    try:
        wait_for(lambda: started(data, session_id))
        wait_for(
            lambda: any(
                r["stage"] == "diarize" and r["status"] == "failed" for r in runs(data, session_id)
            )
        )
        assert processor.stop_processing(session_id) == "stopped"
        job = job_state(data, session_id)
        assert job.state == "failed" and job.error != jobs.STOPPED
        assert isinstance(job.params, jobs.ChainParams) and job.params.stopped_at is None
    finally:
        processor.stop()


def test_a_stop_that_takes_too_long_is_said_and_the_session_is_not_deleted(
    data: DataDir, recording: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(processing, "STOP_WAIT_S", 0.3)
    session_id = import_(data, recording)
    processor = Processor(data, SLOW_CHAIN, engine_cancel=lambda _folder: None)  # kills nothing
    client = local_client(
        create_app(data, SLOW_CHAIN, profile="essai", processor=processor, web_dir=None)
    )
    processor.start()
    try:
        wait_for(lambda: started(data, session_id))
        asked = client.post(f"/api/seances/{session_id}/arreter")
        assert asked.status_code == 202 and asked.json()["job_state"] == "running"
        refused = client.delete(f"/api/seances/{session_id}")
        assert refused.status_code == 409 and "réessayez" in refused.json()["detail"]
        assert data.session_dir(session_id).is_dir()
    finally:
        processor.stop()
