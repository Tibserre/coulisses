"""The processing queue, persisted in SQLite (ADR 0002, 0018): jobs survive a restart."""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

from pydantic import BaseModel

from coulisses_app.storage.db import ISO_FORMAT, now_iso

STOPPED = "Traitement arrêté à votre demande."
"""The error of a job the user stopped: failed, not by an error; resumed like a failure."""

WAIT_FOR_ATTENDEES_S = 120.0
"""How long an import in one gesture waits for the people present before its first
processing starts without them (ADR 0069)."""

Rerun = Literal["transcribe", "diarize", "all"]

REDONE: dict[str, tuple[str, ...]] = {
    "transcribe": ("transcribe", "align", "attribute"),
    "diarize": ("diarize", "attribute"),
    "all": ("transcribe", "align", "diarize", "attribute"),
}
"""The stages a rerun makes again; the others are those of the version it starts from."""


class ChainParams(BaseModel):
    """What a chain job was asked to do, fixed when claimed: before that, only
    `take_attendees` changes `attendees`; `mix` is set when the job runs."""

    v: int = 1
    profile: str
    attendees: int | None = None
    glossary: list[str] = []
    rerun: Rerun | None = None
    """None: the session's first processing. Otherwise the stage run again (with the stages
    after it) to make a new version (step 7 of the plan)."""
    reuse: dict[str, str] = {}
    """For a rerun: stage → run of the version it starts from, used as it is."""
    starts_at: str | None = None
    """A first processing waiting for the people present (an import in one gesture): not
    claimed before this time (UTC), unless started at once (`start_now`). Set as a time, it
    holds across a restart: past due, it starts with the service."""
    stopped_at: str | None = None
    """When the user stopped it (« Arrêter »): its stages already made are kept, those
    running were cancelled by the engine (their runs stay as it closed them, P5)."""
    stopped_runs: list[str] = []
    """Runs cancelled at the user's request that raised an error on the way (the engine's
    cancelling refused by macOS): stopped, not failed, though their provenance may not say
    so. The ones the engine closed as Cancelled say it themselves."""
    mix: dict[str, Any] | None = None
    """When the engine heard the microphone mixed with the computer's sound (ADR 0032):
    what the mix was made of (`mixing.MixFacts`), set when the job runs. Kept here, it
    outlives the purge of the session's audio (P7)."""


class GenerationParams(BaseModel):
    """A summary or the title to generate, with the model chosen when queued."""

    v: int = 1
    action_ref: str
    model: str


class Job(BaseModel):
    id: int
    session_id: str
    kind: str
    """chain (the engine's stages) or generation (a summary or the title)."""
    state: str
    params: ChainParams | GenerationParams
    error: str | None = None


def enqueue_chain(
    conn: sqlite3.Connection,
    session_id: str,
    *,
    profile: str,
    attendees: int | None,
    glossary: list[str] | None = None,
    wait_s: float | None = None,
) -> int:
    """`wait_s`: the first processing waits that long for the people present."""
    starts_at = (
        (datetime.now(UTC) + timedelta(seconds=wait_s)).strftime(ISO_FORMAT)
        if wait_s is not None
        else None
    )
    params = ChainParams(
        profile=profile, attendees=attendees, glossary=glossary or [], starts_at=starts_at
    )
    cursor = conn.execute(
        "INSERT INTO job (session_id, kind, state, params, requested_at)"
        " VALUES (?, 'chain', 'queued', ?, ?)",
        (session_id, params.model_dump_json(), now_iso()),
    )
    assert cursor.lastrowid is not None
    return cursor.lastrowid


def enqueue_rerun(
    conn: sqlite3.Connection,
    session_id: str,
    *,
    profile: str,
    rerun: Rerun,
    reuse: dict[str, str],
    attendees: int | None,
    glossary: list[str],
) -> int:
    params = ChainParams(
        profile=profile, attendees=attendees, glossary=glossary, rerun=rerun, reuse=reuse
    )
    cursor = conn.execute(
        "INSERT INTO job (session_id, kind, state, params, requested_at)"
        " VALUES (?, 'chain', 'queued', ?, ?)",
        (session_id, params.model_dump_json(), now_iso()),
    )
    assert cursor.lastrowid is not None
    return cursor.lastrowid


def enqueue_generation(
    conn: sqlite3.Connection, session_id: str, *, action_ref: str, model: str
) -> int:
    params = GenerationParams(action_ref=action_ref, model=model)
    cursor = conn.execute(
        "INSERT INTO job (session_id, kind, state, params, requested_at)"
        " VALUES (?, 'generation', 'queued', ?, ?)",
        (session_id, params.model_dump_json(), now_iso()),
    )
    assert cursor.lastrowid is not None
    return cursor.lastrowid


def _job(row: sqlite3.Row) -> Job:
    raw = json.loads(row["params"])
    params: ChainParams | GenerationParams = (
        GenerationParams.model_validate(raw)
        if row["kind"] == "generation"
        else ChainParams.model_validate(raw)
    )
    return Job(
        id=row["id"],
        session_id=row["session_id"],
        kind=row["kind"],
        state=row["state"],
        params=params,
        error=row["error"],
    )


def claim_next(conn: sqlite3.Connection) -> Job | None:
    """Take the oldest queued job and mark it running, atomically. One waiting for the people
    present (`starts_at`) is left until its time; the others go ahead of it."""
    with conn:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute(
            "SELECT * FROM job WHERE state = 'queued'"
            " AND coalesce(json_extract(params, '$.starts_at'), '') <= ? ORDER BY id LIMIT 1",
            (now_iso(),),
        ).fetchone()
        if row is None:
            return None
        conn.execute(
            "UPDATE job SET state = 'running', started_at = ?, finished_at = NULL, error = NULL"
            " WHERE id = ?",
            (now_iso(), row["id"]),
        )
    return _job(row)


def finish(conn: sqlite3.Connection, job_id: int, *, error: str | None) -> None:
    with conn:
        conn.execute(
            "UPDATE job SET state = ?, finished_at = ?, error = ? WHERE id = ?",
            ("failed" if error else "done", now_iso(), error, job_id),
        )


def requeue(conn: sqlite3.Connection, job_id: int) -> None:
    """Put a job back in the queue: it resumes, reusing the runs that succeeded. Stopped by
    the user, it is no longer said so."""
    with conn:
        conn.execute(
            "UPDATE job SET state = 'queued', finished_at = NULL, error = NULL,"
            " params = json_remove(params, '$.stopped_at') WHERE id = ?",
            (job_id,),
        )


def record_stopped_run(conn: sqlite3.Connection, job_id: int, run_id: str) -> None:
    """A run of this job, cancelled at the user's request, raised an error on the way: it
    was stopped, not failed (`ChainParams.stopped_runs`)."""
    with conn:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute("SELECT params FROM job WHERE id = ?", (job_id,)).fetchone()
        if row is None:
            return
        params = ChainParams.model_validate_json(row["params"])
        params = params.model_copy(update={"stopped_runs": [*params.stopped_runs, run_id]})
        conn.execute("UPDATE job SET params = ? WHERE id = ?", (params.model_dump_json(), job_id))


def mark_stopped(conn: sqlite3.Connection, job_id: int, *, only_queued: bool = False) -> bool:
    """The user stopped this job: failed with `STOPPED`, and when (`stopped_at`). Returns
    whether it was marked (`only_queued`: not if it was claimed meanwhile)."""
    with conn:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute("SELECT * FROM job WHERE id = ?", (job_id,)).fetchone()
        if row is None or (only_queued and row["state"] != "queued"):
            return False
        job = _job(row)
        stamp = now_iso()
        params = (
            job.params.model_copy(update={"stopped_at": stamp})
            if isinstance(job.params, ChainParams)
            else job.params
        )
        conn.execute(
            "UPDATE job SET state = 'failed', finished_at = ?, error = ?, params = ? WHERE id = ?",
            (stamp, STOPPED, params.model_dump_json(), job_id),
        )
    return True


def record_mix(conn: sqlite3.Connection, job: Job, facts: dict[str, Any]) -> None:
    """What the engine is about to hear, when it is a mix: kept with the job (P7)."""
    _update_params(conn, job.id, mix=facts)


def _update_params(conn: sqlite3.Connection, job_id: int, **changes: Any) -> None:
    """Changes some of a chain job's params, read again under the lock: what another
    writer put there meanwhile (`stopped_runs`…) is kept."""
    with conn:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute("SELECT params FROM job WHERE id = ?", (job_id,)).fetchone()
        if row is None:
            return
        params = ChainParams.model_validate_json(row["params"]).model_copy(update=changes)
        conn.execute("UPDATE job SET params = ? WHERE id = ?", (params.model_dump_json(), job_id))


def resume_with_attendees(conn: sqlite3.Connection, job: Job, attendees: int) -> None:
    """Resume a failed job asking for another minimum of voices, only after a diarization
    refused with `too_few_speakers` (checked by the caller). The former minimum stays in
    that run's provenance (`error.details.expected`): nothing is lost. Who was present is
    not changed: people can be present without speaking."""
    with conn:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute("SELECT params FROM job WHERE id = ?", (job.id,)).fetchone()
        if row is None:
            return
        params = ChainParams.model_validate_json(row["params"]).model_copy(
            update={"attendees": attendees}
        )
        conn.execute(
            "UPDATE job SET state = 'queued', finished_at = NULL, error = NULL, params = ?"
            " WHERE id = ?",
            (params.model_dump_json(), job.id),
        )


def take_attendees(conn: sqlite3.Connection, session_id: str, attendees: int | None) -> bool:
    """The people checked after a session was queued, before its processing began: its first
    processing takes them as its minimum of voices (P3). The engine diarizes from the start
    of the job, alongside the transcription: once it has begun, or for a rerun or a job
    resumed (its runs already made with the former minimum), nothing changes. Returns
    whether it was taken. Within the caller's transaction."""
    row = conn.execute(
        "SELECT * FROM job j WHERE session_id = ? AND kind = 'chain' AND state = 'queued'"
        " AND NOT EXISTS (SELECT 1 FROM run r WHERE r.job_id = j.id)"
        " ORDER BY id DESC LIMIT 1",
        (session_id,),
    ).fetchone()
    if row is None:
        return False
    job = _job(row)
    assert isinstance(job.params, ChainParams)
    if job.params.rerun is not None:
        return False
    params = job.params.model_copy(update={"attendees": attendees})
    conn.execute(
        "UPDATE job SET params = ? WHERE id = ? AND state = 'queued'",
        (params.model_dump_json(), job.id),
    )
    return True


def start_now(conn: sqlite3.Connection, session_id: str) -> bool:
    """The first processing waiting for the people present starts now: they are checked, or
    the user goes on without them. Returns whether one was waiting."""
    with conn:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute(
            "SELECT * FROM job WHERE session_id = ? AND kind = 'chain' AND state = 'queued'"
            " AND json_extract(params, '$.starts_at') IS NOT NULL",
            (session_id,),
        ).fetchone()
        if row is None:
            return False
        job = _job(row)
        assert isinstance(job.params, ChainParams)
        params = job.params.model_copy(update={"starts_at": None})
        conn.execute("UPDATE job SET params = ? WHERE id = ?", (params.model_dump_json(), job.id))
    return True


def latest_job(conn: sqlite3.Connection, session_id: str, kind: str = "chain") -> Job | None:
    row = conn.execute(
        "SELECT * FROM job WHERE session_id = ? AND kind = ? ORDER BY id DESC LIMIT 1",
        (session_id, kind),
    ).fetchone()
    return _job(row) if row else None


def latest_mix(conn: sqlite3.Connection, session_id: str) -> dict[str, Any] | None:
    """What the latest mix the engine heard was made of, from the jobs that used one."""
    for row in conn.execute(
        "SELECT * FROM job WHERE session_id = ? AND kind = 'chain' ORDER BY id DESC",
        (session_id,),
    ):
        job = _job(row)
        if isinstance(job.params, ChainParams) and job.params.mix is not None:
            return job.params.mix
    return None


def generation_jobs(conn: sqlite3.Connection, session_id: str) -> list[Job]:
    """The session's generations still waiting or running, and the failed ones not asked
    again since (a failure followed by a new request for the same summary is history: its
    run keeps its error)."""
    found = [
        _job(r)
        for r in conn.execute(
            "SELECT * FROM job WHERE session_id = ? AND kind = 'generation' ORDER BY id",
            (session_id,),
        )
    ]
    shown: list[Job] = []
    for job in found:
        if job.state == "done" or not isinstance(job.params, GenerationParams):
            continue
        ref = job.params.action_ref
        asked_again = any(
            later.id > job.id
            and isinstance(later.params, GenerationParams)
            and later.params.action_ref == ref
            for later in found
        )
        if job.state == "failed" and asked_again:
            continue
        shown.append(job)
    return shown


def running_jobs(conn: sqlite3.Connection) -> list[Job]:
    return [_job(r) for r in conn.execute("SELECT * FROM job WHERE state = 'running'")]
