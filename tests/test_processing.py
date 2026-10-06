"""Background processing with the engine's fake engines: a chain runs, fails visibly,
resumes without redoing what succeeded, and survives a stop or a crash of the application."""

from __future__ import annotations

import os
import signal
import sqlite3
import subprocess
import sys
import textwrap
import time
from collections.abc import Callable
from pathlib import Path

import pytest
from coulisses.api import ChainConfig, RunStillRunningError, StageConfig, read_provenance

from coulisses_app import jobs, sessions
from coulisses_app.paths import DataDir
from coulisses_app.processing import Processor
from coulisses_app.status import stage_views
from coulisses_app.storage.db import connect

from .conftest import FAKE_CHAIN

SLOW_CHAIN = ChainConfig(
    transcribe=StageConfig(engine="fake_slow", settings={"seconds": 60}),
    diarize=StageConfig(engine="fake_min_speakers"),
    attribute=StageConfig(engine="overlap"),
)
REFUSED_DIARIZATION = FAKE_CHAIN.model_copy(
    update={"diarize": StageConfig(engine="fake_under_segmenting")}
)


def import_(data: DataDir, recording: Path, attendees: int = 2) -> str:
    with recording.open("rb") as f:
        return sessions.import_recording(
            data, f, recording.name, unnamed_attendees=attendees, recorded_at=None, profile="essai"
        )


def runs(data: DataDir, session_id: str) -> list[sqlite3.Row]:
    conn = connect(data)
    try:
        return conn.execute(
            "SELECT * FROM run WHERE session_id = ? ORDER BY created_at, rowid", (session_id,)
        ).fetchall()
    finally:
        conn.close()


def claim(data: DataDir) -> jobs.Job:
    conn = connect(data)
    try:
        job = jobs.claim_next(conn)
    finally:
        conn.close()
    assert job is not None
    return job


def job_state(data: DataDir, session_id: str) -> jobs.Job:
    conn = connect(data)
    try:
        job = jobs.latest_job(conn, session_id)
    finally:
        conn.close()
    assert job is not None
    return job


def wait_for(condition: Callable[[], bool], timeout: float = 30.0) -> None:
    deadline = time.monotonic() + timeout
    while not condition():
        assert time.monotonic() < deadline, "timed out"
        time.sleep(0.1)


def test_a_chain_runs_every_stage_and_activates_them(data: DataDir, recording: Path) -> None:
    session_id = import_(data, recording)
    result = Processor(data, FAKE_CHAIN).run_job(claim(data))
    assert result.error is None
    assert job_state(data, session_id).state == "done"
    stages = [r["stage"] for r in runs(data, session_id)]
    assert sorted(stages) == ["align", "attribute", "diarize", "transcribe"]
    assert all(r["status"] == "succeeded" for r in runs(data, session_id))
    assert all(r["engine_version"] for r in runs(data, session_id))
    views = stage_views(data, FAKE_CHAIN, session_id)
    assert [v.state for v in views] == ["succeeded"] * 4
    conn = connect(data)
    try:
        active = {r["stage"] for r in conn.execute("SELECT stage FROM active_run")}
        upstream = conn.execute("SELECT COUNT(*) FROM run_upstream").fetchone()[0]
    finally:
        conn.close()
    assert active == {"transcribe", "align", "diarize", "attribute"}
    assert upstream >= 3  # align ← transcribe, attribute ← align + diarize


def test_the_attendees_reach_the_engine_as_a_minimum(data: DataDir, recording: Path) -> None:
    session_id = import_(data, recording, attendees=3)
    Processor(data, FAKE_CHAIN).run_job(claim(data))
    diarize = next(r for r in runs(data, session_id) if r["stage"] == "diarize")
    prov = read_provenance(data.run_dir(session_id, diarize["id"]))
    assert prov is not None
    assert prov.inputs["min_speakers"] == 3


def test_a_failed_stage_is_visible_and_keeps_what_succeeded(data: DataDir, recording: Path) -> None:
    session_id = import_(data, recording, attendees=3)
    result = Processor(data, REFUSED_DIARIZATION).run_job(claim(data))
    assert result.error is not None and "Qui parle quand" in result.error
    job = job_state(data, session_id)
    assert job.state == "failed"
    by_stage = {r["stage"]: r for r in runs(data, session_id)}
    assert by_stage["diarize"]["status"] == "failed"
    assert by_stage["diarize"]["error_summary"]
    assert by_stage["transcribe"]["status"] == "succeeded"
    assert "attribute" not in by_stage  # never started, nothing invented
    for row in runs(data, session_id):
        assert data.run_dir(session_id, row["id"]).is_dir()  # nothing deleted


def test_resuming_reuses_the_runs_that_succeeded(data: DataDir, recording: Path) -> None:
    session_id = import_(data, recording, attendees=3)
    Processor(data, REFUSED_DIARIZATION).run_job(claim(data))
    before = {r["stage"]: r["id"] for r in runs(data, session_id) if r["status"] == "succeeded"}
    conn = connect(data)
    try:
        jobs.requeue(conn, job_state(data, session_id).id)
    finally:
        conn.close()
    result = Processor(data, FAKE_CHAIN).run_job(claim(data))
    assert result.error is None
    after = runs(data, session_id)
    assert [r["id"] for r in after if r["stage"] == "transcribe"] == [before["transcribe"]]
    assert [r["id"] for r in after if r["stage"] == "align"] == [before["align"]]
    diarizations = [r for r in after if r["stage"] == "diarize"]
    assert [r["status"] for r in diarizations] == ["failed", "succeeded"]  # the old one stays
    assert job_state(data, session_id).state == "done"


def test_stopping_the_application_records_the_run_and_queues_the_job_again(
    data: DataDir, recording: Path
) -> None:
    session_id = import_(data, recording)
    processor = Processor(data, SLOW_CHAIN)
    processor.start()
    wait_for(lambda: any(r["status"] == "running" for r in runs(data, session_id)))
    wait_for(
        lambda: all(
            (data.run_dir(session_id, r["id"]) / "spec.json").is_file()
            for r in runs(data, session_id)
        )
    )
    processor.stop()
    assert job_state(data, session_id).state == "queued"
    transcribe = next(r for r in runs(data, session_id) if r["stage"] == "transcribe")
    assert transcribe["status"] == "failed"
    assert "Interrupted" in transcribe["error_summary"]


_CRASHING_APP = textwrap.dedent(
    """
    import sys
    from pathlib import Path
    import coulisses.testing.fakes
    from coulisses.api import ChainConfig, StageConfig
    from coulisses_app import jobs
    from coulisses_app.paths import DataDir
    from coulisses_app.processing import Processor
    from coulisses_app.storage.db import connect

    data = DataDir(Path(sys.argv[1]))
    chain = ChainConfig(
        transcribe=StageConfig(engine="fake_slow", settings={"seconds": 60}),
        diarize=StageConfig(engine="fake_min_speakers"),
        attribute=StageConfig(engine="overlap"),
    )
    conn = connect(data)
    job = jobs.claim_next(conn)
    conn.close()
    Processor(data, chain).run_job(job)
    """
)


def test_after_a_crash_the_run_is_closed_and_the_job_resumes(
    data: DataDir, recording: Path
) -> None:
    session_id = import_(data, recording)
    app = subprocess.Popen([sys.executable, "-c", _CRASHING_APP, str(data.root)])
    try:
        wait_for(
            lambda: any(
                r["stage"] == "transcribe"
                # Written by the engine once the stage's process runs (engine/README.md).
                and (data.run_dir(session_id, r["id"]) / "process.json").is_file()
                for r in runs(data, session_id)
            )
        )
    finally:
        os.kill(app.pid, signal.SIGKILL)  # like a crash: nothing gets recorded
        app.wait()
    slow = next(r for r in runs(data, session_id) if r["stage"] == "transcribe")
    assert slow["status"] == "running"
    assert read_provenance(data.run_dir(session_id, slow["id"])) is None

    problems = Processor(data, FAKE_CHAIN).recover()
    assert problems == []
    closed = next(r for r in runs(data, session_id) if r["id"] == slow["id"])
    assert closed["status"] == "failed"
    assert "Interrupted" in closed["error_summary"]
    assert job_state(data, session_id).state == "queued"

    result = Processor(data, FAKE_CHAIN).run_job(claim(data))
    assert result.error is None
    assert job_state(data, session_id).state == "done"


def test_a_missing_recording_fails_the_job_with_a_readable_message(
    data: DataDir, recording: Path
) -> None:
    session_id = import_(data, recording)
    (data.sources_dir(session_id) / "ref.wav").unlink()  # as if deleted in the Finder
    result = Processor(data, FAKE_CHAIN).run_job(claim(data))
    assert result.error is not None and "introuvable" in result.error
    assert job_state(data, session_id).state == "failed"


@pytest.mark.slow
def test_the_retained_chain_processes_a_real_recording(data: DataDir, recording: Path) -> None:
    from coulisses.api import (
        AttributedTranscript,
        load_profile,
        profile_path,
        read_output,
    )

    chain = ChainConfig.from_profile(load_profile(profile_path()))
    session_id = import_(data, recording, attendees=1)
    result = Processor(data, chain).run_job(claim(data))
    assert result.error is None, result.error
    attribute = next(r for r in runs(data, session_id) if r["stage"] == "attribute")
    transcript = read_output(data.run_dir(session_id, attribute["id"]), AttributedTranscript)
    text = " ".join(w.text for w in transcript.words).lower()
    assert "bonjour" in text
    assert all(w.start is None or w.end is not None for w in transcript.words)
    # The review underlines what the transcription model doubted (engine v1.4.0, ADR 0023).
    assert any(w.asr_confidence is not None for w in transcript.words)


def test_a_refused_closing_is_reported_and_the_job_stays_put(
    data: DataDir, recording: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    session_id = import_(data, recording)
    job = claim(data)
    folder = data.run_dir(session_id, "transcribe-0000abcd")
    folder.mkdir(parents=True)
    (folder / "spec.json").write_text("{}", encoding="utf-8")  # a run left as if crashed
    conn = connect(data)
    with conn:
        conn.execute(
            "INSERT INTO run (id, session_id, job_id, stage, status, producer, created_at)"
            " VALUES ('transcribe-0000abcd', ?, ?, 'transcribe', 'running', 'engine', 'x')",
            (session_id, job.id),
        )
    conn.close()

    def refuse(_: Path) -> None:
        raise RunStillRunningError("son processus vit encore")

    monkeypatch.setattr("coulisses_app.processing.close_interrupted", refuse)
    problems = Processor(data, FAKE_CHAIN).recover()
    assert len(problems) == 1 and "refuse" in problems[0]
    assert job_state(data, session_id).state == "running"  # not resumed twice
    row = next(r for r in runs(data, session_id) if r["id"] == "transcribe-0000abcd")
    assert "refuse" in row["error_summary"]


def test_the_processing_loop_outlives_an_error_and_shows_it(
    data: DataDir, recording: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[int] = []
    real_claim = jobs.claim_next

    def flaky(conn: sqlite3.Connection) -> jobs.Job | None:
        calls.append(1)
        if len(calls) == 1:
            raise sqlite3.OperationalError("database is locked")
        return real_claim(conn)

    monkeypatch.setattr(jobs, "claim_next", flaky)
    processor = Processor(data, FAKE_CHAIN)
    processor.start()
    try:
        wait_for(lambda: processor.loop_error is not None)
        assert "locked" in (processor.loop_error or "")
        session_id = import_(data, recording)
        processor.wake()
        wait_for(lambda: job_state(data, session_id).state == "done")
        assert processor.loop_error is None
    finally:
        processor.stop()


def test_a_run_whose_folder_was_deleted_is_made_again(data: DataDir, recording: Path) -> None:
    import shutil

    session_id = import_(data, recording, attendees=3)
    Processor(data, REFUSED_DIARIZATION).run_job(claim(data))
    lost = next(r for r in runs(data, session_id) if r["stage"] == "transcribe")
    shutil.rmtree(data.run_dir(session_id, lost["id"]))  # as if deleted in the Finder
    conn = connect(data)
    try:
        jobs.requeue(conn, job_state(data, session_id).id)
    finally:
        conn.close()
    assert Processor(data, FAKE_CHAIN).run_job(claim(data)).error is None
    transcriptions = [r["id"] for r in runs(data, session_id) if r["stage"] == "transcribe"]
    assert len(transcriptions) == 2 and transcriptions[0] == lost["id"]


def test_a_refused_diarization_says_why_with_the_engine_code(
    data: DataDir, recording: Path
) -> None:
    session_id = import_(data, recording, attendees=3)
    Processor(data, REFUSED_DIARIZATION).run_job(claim(data))
    diarize = next(v for v in stage_views(data, FAKE_CHAIN, session_id) if v.stage == "diarize")
    assert diarize.state == "failed"
    assert diarize.error_code == "too_few_speakers"
    assert diarize.error_details == {"found": 1, "expected": 3}
