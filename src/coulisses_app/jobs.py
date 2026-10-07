"""The processing queue, persisted in SQLite (ADR 0002, 0018): jobs survive a restart."""

from __future__ import annotations

import json
import sqlite3
from typing import Literal

from pydantic import BaseModel

from coulisses_app.storage.db import now_iso

Rerun = Literal["transcribe", "diarize"]

REDONE: dict[str, tuple[str, ...]] = {
    "transcribe": ("transcribe", "align", "attribute"),
    "diarize": ("diarize", "attribute"),
}
"""The stages a rerun makes again; the others are those of the version it starts from."""


class ChainParams(BaseModel):
    """What a chain job was asked to do, frozen when queued."""

    v: int = 1
    profile: str
    attendees: int | None = None
    glossary: list[str] = []
    rerun: Rerun | None = None
    """None: the session's first processing. Otherwise the stage run again (with the stages
    after it) to make a new version (step 7 of the plan)."""
    reuse: dict[str, str] = {}
    """For a rerun: stage → run of the version it starts from, used as it is."""


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
) -> int:
    params = ChainParams(profile=profile, attendees=attendees, glossary=glossary or [])
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
    """Take the oldest queued job and mark it running, atomically."""
    with conn:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute(
            "SELECT * FROM job WHERE state = 'queued' ORDER BY id LIMIT 1"
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
    """Put a job back in the queue: it resumes, reusing the runs that succeeded."""
    with conn:
        conn.execute(
            "UPDATE job SET state = 'queued', finished_at = NULL, error = NULL WHERE id = ?",
            (job_id,),
        )


def resume_with_attendees(conn: sqlite3.Connection, job: Job, attendees: int) -> None:
    """Resume a failed job asking for another minimum of voices, only after a diarization
    refused with `too_few_speakers` (checked by the caller). The former minimum stays in
    that run's provenance (`error.details.expected`): nothing is lost. Who was present is
    not changed: people can be present without speaking."""
    assert isinstance(job.params, ChainParams)
    params = job.params.model_copy(update={"attendees": attendees})
    with conn:
        conn.execute(
            "UPDATE job SET state = 'queued', finished_at = NULL, error = NULL, params = ?"
            " WHERE id = ?",
            (params.model_dump_json(), job.id),
        )


def latest_job(conn: sqlite3.Connection, session_id: str, kind: str = "chain") -> Job | None:
    row = conn.execute(
        "SELECT * FROM job WHERE session_id = ? AND kind = ? ORDER BY id DESC LIMIT 1",
        (session_id, kind),
    ).fetchone()
    return _job(row) if row else None


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
