"""The user stops a processing (« si en fait je ne veux pas la faire »), or deletes its
session while it runs (a file imported by mistake): the running stages are cancelled by the
engine and kept as it closed them (P5), the stopped job says so, « Reprendre » goes on."""

from __future__ import annotations

import threading
from pathlib import Path

import pytest
from coulisses.api import Provenance, RunStage, StageConfig

from coulisses_app import jobs, processing
from coulisses_app.api import create_app
from coulisses_app.paths import DataDir
from coulisses_app.processing import Processor
from coulisses_app.status import stage_views

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
        views = {v.stage: v for v in stage_views(data, SLOW_CHAIN, session_id)}
        assert views["transcribe"].stopped and not views["diarize"].stopped
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


def test_a_stage_whose_cancelling_fails_is_still_a_stop(data: DataDir, recording: Path) -> None:
    """The engine's cancelling may itself fail (macOS refusing to kill the stage's group:
    PermissionError): the user asked for the stop, the session says « arrêté »."""
    cancelled = threading.Event()

    def engine_stage(_session_id: str, _models: Path | None) -> RunStage:
        def run(*_args: object) -> tuple[Provenance, Path]:
            assert cancelled.wait(10)
            raise PermissionError(1, "Operation not permitted")

        return run  # type: ignore[return-value]

    session_id = import_(data, recording)
    processor = Processor(
        data, FAKE_CHAIN, engine_stage=engine_stage, engine_cancel=lambda _f: cancelled.set()
    )
    processor.start()
    try:
        wait_for(lambda: any(r["status"] == "running" for r in runs(data, session_id)))
        assert processor.stop_processing(session_id) == "stopped"
        job = job_state(data, session_id)
        assert (job.state, job.error) == ("failed", jobs.STOPPED)
        failed = [r for r in runs(data, session_id) if r["status"] == "failed"]
        assert failed and all("PermissionError" in r["error_summary"] for r in failed)
        views = [v for v in stage_views(data, FAKE_CHAIN, session_id) if v.state == "failed"]
        assert views and all(v.stopped for v in views)
    finally:
        processor.stop()


def test_a_stage_crashing_before_it_was_cancelled_is_a_failure(
    data: DataDir, recording: Path
) -> None:
    """Stopped a moment after a stage crashed for another reason: that crash is what the
    session says, not « arrêté » (P8)."""
    holder: list[Processor] = []

    def engine_stage(_session_id: str, _models: Path | None) -> RunStage:
        def run(*_args: object) -> tuple[Provenance, Path]:
            # The user stops it now, as it crashes: no cancelling was sent yet.
            holder[0]._stopped_by_user.add(job_state(data, session_id).id)  # pyright: ignore[reportPrivateUsage]
            raise MemoryError("plus de mémoire")

        return run  # type: ignore[return-value]

    session_id = import_(data, recording)
    processor = Processor(data, FAKE_CHAIN, engine_stage=engine_stage)
    holder.append(processor)
    result = processor.run_job(claim(data))
    assert result.error is not None and "MemoryError" in result.error
    job = job_state(data, session_id)
    assert job.state == "failed" and job.error != jobs.STOPPED


def test_a_failure_before_a_resume_stays_a_failure_once_stopped(
    data: DataDir, recording: Path
) -> None:
    """A real failure, « Reprendre », then a stop before the stage runs again: the stage
    still shows that failure and its message, never « arrêtée » (P8)."""
    session_id = import_(data, recording, attendees=9)
    refused = FAKE_CHAIN.model_copy(update={"diarize": StageConfig(engine="fake_under_segmenting")})
    assert Processor(data, refused).run_job(claim(data)).error is not None
    client = local_client(create_app(data, refused, profile="essai", processor=None, web_dir=None))
    client.post(f"/api/seances/{session_id}/reprendre")
    session = client.post(f"/api/seances/{session_id}/arreter").json()
    assert session["processing_stopped"] is True
    diarize = next(v for v in stage_views(data, refused, session_id) if v.stage == "diarize")
    assert diarize.state == "failed" and not diarize.stopped and diarize.error


def test_a_stop_that_cannot_be_recorded_still_closes_the_run_with_its_error(
    data: DataDir, recording: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def refused(*_args: object) -> None:
        raise RuntimeError("base verrouillée")

    monkeypatch.setattr(jobs, "record_stopped_run", refused)
    cancelled = threading.Event()

    def engine_stage(_session_id: str, _models: Path | None) -> RunStage:
        def run(*_args: object) -> tuple[Provenance, Path]:
            assert cancelled.wait(10)
            raise PermissionError(1, "Operation not permitted")

        return run  # type: ignore[return-value]

    session_id = import_(data, recording)
    processor = Processor(
        data, FAKE_CHAIN, engine_stage=engine_stage, engine_cancel=lambda _f: cancelled.set()
    )
    processor.start()
    try:
        wait_for(lambda: any(r["status"] == "running" for r in runs(data, session_id)))
        assert processor.stop_processing(session_id) == "stopped"
        failed = [r for r in runs(data, session_id) if r["status"] == "failed"]
        assert failed and all("PermissionError" in r["error_summary"] for r in failed)
        assert not any(r["status"] == "running" for r in runs(data, session_id))
    finally:
        processor.stop()
