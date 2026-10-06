"""The processing queue, persisted in SQLite (ADR 0002, 0018): jobs survive a restart."""

from __future__ import annotations

import json
import sqlite3

from pydantic import BaseModel

from coulisses_app.storage.db import now_iso


class ChainParams(BaseModel):
    """What a chain job was asked to do, frozen when queued."""

    v: int = 1
    profile: str
    attendees: int | None = None
    glossary: list[str] = []


class Job(BaseModel):
    id: int
    session_id: str
    kind: str
    state: str
    params: ChainParams


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


def _job(row: sqlite3.Row) -> Job:
    return Job(
        id=row["id"],
        session_id=row["session_id"],
        kind=row["kind"],
        state=row["state"],
        params=ChainParams.model_validate(json.loads(row["params"])),
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
    params = job.params.model_copy(update={"attendees": attendees})
    with conn:
        conn.execute(
            "UPDATE job SET state = 'queued', finished_at = NULL, error = NULL, params = ?"
            " WHERE id = ?",
            (params.model_dump_json(), job.id),
        )


def latest_job(conn: sqlite3.Connection, session_id: str) -> Job | None:
    row = conn.execute(
        "SELECT * FROM job WHERE session_id = ? ORDER BY id DESC LIMIT 1", (session_id,)
    ).fetchone()
    return _job(row) if row else None


def running_jobs(conn: sqlite3.Connection) -> list[Job]:
    return [_job(r) for r in conn.execute("SELECT * FROM job WHERE state = 'running'")]
