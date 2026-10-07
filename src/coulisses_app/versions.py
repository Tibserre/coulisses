"""Versions of a session's processing (spec §7.4, §7.6, step 7 of the plan).

A version is a successful « who said what » run with the runs it comes from. Running the
transcription or the voices again makes a new one, from the version shown: the other stages
are reused as they are. The new version replaces the shown one only once it is complete,
with the corrections carried over (`processing._complete`); the former versions stay, each
with its own corrections, and can be shown again.
"""

from __future__ import annotations

import sqlite3
from importlib.metadata import version as installed_version
from typing import Literal

from coulisses.api import read_provenance
from pydantic import BaseModel

from coulisses_app import jobs, spaces
from coulisses_app.jobs import REDONE, Rerun
from coulisses_app.paths import DataDir
from coulisses_app.processing import activate
from coulisses_app.spaces import NotFoundError, SpaceError
from coulisses_app.storage.db import connect


class Version(BaseModel):
    run_id: str
    number: int
    """1 for the first processing, then in the order they were made."""
    finished_at: str | None
    shown: bool
    origin: Literal["first", "transcribe", "diarize"]
    min_voices: int | None
    """The minimum of voices its voice separation was asked for (P3)."""
    engine_version: str | None
    corrections: int
    """Corrections in force on it (carried over ones included)."""
    carried: int | None = None
    not_carried: int | None = None
    """When it replaced another version: how its corrections were carried over."""


class RerunFacts(BaseModel):
    """What the user needs to choose a rerun of the version shown."""

    possible: bool
    why_not: str | None = None
    transcribe_s: float | None = None
    """Measured computing time of the shown version's transcription and alignment."""
    diarize_s: float | None = None
    """Measured computing time of its voice separation and attribution."""
    glossary_added: list[str] = []
    """Terms of the space's glossary its transcription did not have."""
    engine_updated: bool = False
    """Its transcription was made by another version of the engine than the installed one."""
    min_voices: int | None = None
    attendees_now: int | None = None
    """People checked as present plus the unnamed ones, as the session says today."""


class Versions(BaseModel):
    versions: list[Version]
    """Newest first."""
    rerun: RerunFacts


def _shown(conn: sqlite3.Connection, session_id: str) -> str | None:
    row = conn.execute(
        "SELECT run_id FROM active_run WHERE session_id = ? AND stage = 'attribute'",
        (session_id,),
    ).fetchone()
    return row["run_id"] if row else None


def _ancestors(conn: sqlite3.Connection, run_id: str) -> dict[str, str]:
    """Stage → run, for a run and every run it comes from."""
    found: dict[str, str] = {}
    pending = [run_id]
    while pending:
        current = pending.pop()
        row = conn.execute("SELECT stage FROM run WHERE id = ?", (current,)).fetchone()
        if row is None or row["stage"] in found:
            continue
        found[row["stage"]] = current
        pending += [
            r[0]
            for r in conn.execute(
                "SELECT upstream_run_id FROM run_upstream WHERE run_id = ?", (current,)
            )
        ]
    return found


AUDIO_GONE = (
    "L'audio de cette séance a été supprimé : la transcription et les voix ne peuvent plus "
    "être refaites. Le texte, les noms et les résumés restent modifiables."
)


def _audio_removed(conn: sqlite3.Connection, session_id: str) -> bool:
    row = conn.execute(
        "SELECT audio_removed_at FROM session WHERE id = ?", (session_id,)
    ).fetchone()
    return row is not None and row["audio_removed_at"] is not None


def _chain_busy(conn: sqlite3.Connection, session_id: str) -> bool:
    return (
        conn.execute(
            "SELECT 1 FROM job WHERE session_id = ? AND kind = 'chain'"
            " AND state IN ('queued', 'running')",
            (session_id,),
        ).fetchone()
        is not None
    )


def _params(conn: sqlite3.Connection, run_id: str | None) -> jobs.ChainParams | None:
    """What the application asked of the job that made a run (attendees, glossary): its own
    record, not the engine's inputs."""
    if run_id is None:
        return None
    row = conn.execute(
        "SELECT j.params FROM run r JOIN job j ON j.id = r.job_id WHERE r.id = ?"
        " AND j.kind = 'chain'",
        (run_id,),
    ).fetchone()
    return jobs.ChainParams.model_validate_json(row["params"]) if row else None


def _glossary(conn: sqlite3.Connection, transcribe_run: str | None) -> list[str]:
    params = _params(conn, transcribe_run)
    return list(params.glossary) if params else []


def _min_voices(conn: sqlite3.Connection, diarize_run: str | None) -> int | None:
    params = _params(conn, diarize_run)
    return params.attendees if params else None


def _engine_version(conn: sqlite3.Connection, run_id: str | None) -> str | None:
    row = conn.execute("SELECT engine_version FROM run WHERE id = ?", (run_id,)).fetchone()
    return row["engine_version"] if row else None


def _duration(data: DataDir, session_id: str, run_ids: list[str | None]) -> float | None:
    total = 0.0
    for run_id in run_ids:
        if run_id is None:
            continue
        folder = data.run_dir(session_id, run_id)
        prov = read_provenance(folder) if folder.is_dir() else None
        if prov is None:
            return None
        total += prov.duration_s
    return total or None


def request_rerun(
    data: DataDir, session_id: str, rerun: Rerun, *, attendees: int | None, profile: str
) -> int:
    """Queue a rerun of the shown version: the transcription (with the space's glossary as
    it is today) or the voices (with `attendees` as the minimum of voices, P3)."""
    if attendees is not None and attendees < 1:
        raise SpaceError("Il faut au moins une personne présente.")
    conn = connect(data)
    try:
        row = conn.execute("SELECT space_id FROM session WHERE id = ?", (session_id,)).fetchone()
        if row is None:
            raise NotFoundError("Séance introuvable.")
        # Checked and queued in one write transaction: a double click queues one rerun.
        conn.execute("BEGIN IMMEDIATE")
        shown = _shown(conn, session_id)
        if shown is None:
            raise SpaceError("Cette séance n'a pas encore été traitée jusqu'au bout.")
        if _chain_busy(conn, session_id):
            raise SpaceError("Un traitement de cette séance est déjà en cours.")
        if _audio_removed(conn, session_id):
            raise SpaceError(AUDIO_GONE)
        chain = _ancestors(conn, shown)
        reuse = {
            stage: run_id
            for stage, run_id in chain.items()
            if stage not in REDONE[rerun] and stage != "attribute"
        }
        if rerun == "transcribe":
            if "diarize" not in reuse:
                raise SpaceError("La séparation des voix de cette version est introuvable.")
            glossary = spaces.glossary_terms(conn, row["space_id"])
            attendees = _min_voices(conn, reuse["diarize"])
        else:
            if "transcribe" not in reuse:
                raise SpaceError("La transcription de cette version est introuvable.")
            glossary = _glossary(conn, reuse["transcribe"])
        job_id = jobs.enqueue_rerun(
            conn,
            session_id,
            profile=profile,
            rerun=rerun,
            reuse=reuse,
            attendees=attendees,
            glossary=glossary,
        )
        conn.commit()
        return job_id
    finally:
        conn.rollback()  # nothing left open after a refusal (no effect after the commit)
        conn.close()


def list_versions(data: DataDir, session_id: str) -> Versions:
    conn = connect(data)
    try:
        session = conn.execute(
            "SELECT space_id, unnamed_attendees FROM session WHERE id = ?", (session_id,)
        ).fetchone()
        if session is None:
            raise NotFoundError("Séance introuvable.")
        shown = _shown(conn, session_id)
        rows = conn.execute(
            "SELECT r.id, r.finished_at, r.engine_version, j.params FROM run r"
            " LEFT JOIN job j ON j.id = r.job_id"
            " WHERE r.session_id = ? AND r.stage = 'attribute' AND r.status = 'succeeded'"
            " ORDER BY r.created_at, r.rowid",
            (session_id,),
        ).fetchall()
        chains = {r["id"]: _ancestors(conn, r["id"]) for r in rows}
        corrections = {
            r["run_id"]: r["n"]
            for r in conn.execute(
                "SELECT e.run_id, COUNT(*) AS n FROM edit e WHERE e.session_id = ?"
                " AND e.kind != 'revert' AND NOT EXISTS"
                " (SELECT 1 FROM edit r WHERE r.reverts_edit_id = e.id) GROUP BY e.run_id",
                (session_id,),
            )
        }
        carried = {
            r["target_run_id"]: (r["applied"], r["refused"])
            for r in conn.execute(
                "SELECT c.target_run_id, SUM(c.outcome = 'applied') AS applied,"
                " SUM(c.outcome != 'applied') AS refused FROM edit_carryover c"
                " JOIN run r ON r.id = c.target_run_id WHERE r.session_id = ?"
                " GROUP BY c.target_run_id",
                (session_id,),
            )
        }
        voices = {r["id"]: _min_voices(conn, chains[r["id"]].get("diarize")) for r in rows}
        chain = chains.get(shown) if shown else None
        had: set[str] = (
            {t.casefold() for t in _glossary(conn, chain.get("transcribe"))} if chain else set()
        )
        transcribed_with = _engine_version(conn, chain.get("transcribe")) if chain else None
        busy = _chain_busy(conn, session_id)
        gone = _audio_removed(conn, session_id)
        glossary_now = spaces.glossary_terms(conn, session["space_id"])
        attendees_now = len(spaces.attendee_ids(conn, session_id)) + (
            session["unnamed_attendees"] or 0
        )
    finally:
        conn.close()

    found: list[Version] = []
    for number, row in enumerate(rows, start=1):
        params = jobs.ChainParams.model_validate_json(row["params"]) if row["params"] else None
        counts = carried.get(row["id"])
        found.append(
            Version(
                run_id=row["id"],
                number=number,
                finished_at=row["finished_at"],
                shown=row["id"] == shown,
                origin=params.rerun if params is not None and params.rerun else "first",
                min_voices=voices[row["id"]],
                engine_version=row["engine_version"],
                corrections=corrections.get(row["id"], 0),
                carried=counts[0] if counts else None,
                not_carried=counts[1] if counts else None,
            )
        )
    found.reverse()

    if shown is None or chain is None:
        facts = RerunFacts(possible=False, why_not="La séance n'a pas encore de version.")
    else:
        facts = RerunFacts(
            possible=not busy and not gone,
            why_not=AUDIO_GONE
            if gone
            else "Un traitement de cette séance est déjà en cours."
            if busy
            else None,
            transcribe_s=_duration(data, session_id, [chain.get("transcribe"), chain.get("align")]),
            diarize_s=_duration(data, session_id, [chain.get("diarize"), chain.get("attribute")]),
            glossary_added=[t for t in glossary_now if t.casefold() not in had],
            engine_updated=transcribed_with is not None
            and transcribed_with != installed_version("coulisses"),
            min_voices=voices.get(shown),
            attendees_now=attendees_now or None,
        )
    return Versions(versions=found, rerun=facts)


def show(data: DataDir, session_id: str, run_id: str) -> None:
    """Show another version: it becomes the session's, with the runs it comes from and the
    chapters last detected on it. Its corrections are its own; nothing is carried over."""
    conn = connect(data)
    try:
        row = conn.execute(
            "SELECT stage, status FROM run WHERE id = ? AND session_id = ?", (run_id, session_id)
        ).fetchone()
        if row is None or row["stage"] != "attribute" or row["status"] != "succeeded":
            raise NotFoundError("Version introuvable.")
        with conn:
            conn.execute("BEGIN IMMEDIATE")
            if _chain_busy(conn, session_id):
                raise SpaceError(
                    "Un traitement de cette séance est en cours : la version affichée "
                    "changera à sa fin."
                )
            for stage, ancestor in _ancestors(conn, run_id).items():
                activate(conn, session_id, stage, ancestor)
            detection = conn.execute(
                "SELECT r.id FROM run r JOIN run_upstream u ON u.run_id = r.id"
                " WHERE r.session_id = ? AND r.stage = 'segment_phases'"
                " AND r.status = 'succeeded' AND u.upstream_run_id = ?"
                " ORDER BY r.created_at DESC, r.rowid DESC LIMIT 1",
                (session_id, run_id),
            ).fetchone()
            if detection is not None:
                activate(conn, session_id, "segment_phases", detection["id"])
    finally:
        conn.close()
