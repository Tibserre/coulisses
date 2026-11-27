"""The processing times (ADR 0095): each engine run of each session, failed ones included,
with what the engine measured (duration, peak memory) and ran (engine, model, settings),
for the user to export and compare Macs. Read from the runs' provenance, kept for good
(P5, P7): nothing new is recorded. Nothing of a session goes out: no id, title, name, text,
glossary or path; a session is a number, in the order it came into the app."""

from __future__ import annotations

import logging
import re
from typing import Any, cast

from coulisses.api import read_provenance

from coulisses_app.paths import DataDir
from coulisses_app.storage.db import connect

log = logging.getLogger(__name__)

FORMAT = 1
INPUTS_KEPT = ("language", "min_speakers")
"""The inputs of a run that say how much work it had, never what it heard (the glossary,
the sources' paths are left out)."""
LONGEST_TEXT = 80


NAME = re.compile(rf"[\w.@:/+-]{{1,{LONGEST_TEXT}}}")
"""A setting's text that may go out: a name (a model, a device), never words or a phrase."""


def _kept(value: Any, *, names_only: bool) -> bool:
    """What keeps a session's words in: lists (a glossary, hotwords), long texts, and in the
    settings any text that is not a single name (an instruction, words joined by commas)."""
    if value is None or isinstance(value, bool | int | float | dict):
        return True
    if isinstance(value, str):
        return bool(NAME.fullmatch(value)) if names_only else len(value) <= LONGEST_TEXT
    return False


def technical(value: Any, *, names_only: bool = True) -> Any:
    """`value` with only what cannot hold a session's words (`_kept`): numbers, flags,
    names and their maps. Kept rather than removed: a newer engine's text stays home."""
    if isinstance(value, dict):
        items = cast("dict[Any, Any]", value)  # the provenance's maps are untyped JSON
        return {
            str(k): technical(v, names_only=names_only)
            for k, v in items.items()
            if _kept(v, names_only=names_only)
        }
    return value if _kept(value, names_only=names_only) else None


def export(data: DataDir) -> list[dict[str, Any]]:
    """Every session with an engine run, in the order they came into the app."""
    conn = connect(data)
    try:
        rows = conn.execute(
            "SELECT s.id, a.duration_s FROM session s LEFT JOIN audio_source a"
            " ON a.session_id = s.id AND a.source_id = s.reference_source_id"
            " WHERE EXISTS (SELECT 1 FROM run r"
            " WHERE r.session_id = s.id AND r.producer = 'engine')"
            " ORDER BY s.created_at, s.id"
        ).fetchall()
        sessions: list[dict[str, Any]] = []
        for number, row in enumerate(rows, start=1):
            jobs = {
                job["id"]: (rank, job["params"])
                for rank, job in enumerate(
                    conn.execute(
                        "SELECT id, json_extract(params, '$.rerun') AS params FROM job"
                        " WHERE session_id = ? AND kind = 'chain' ORDER BY id",
                        (row["id"],),
                    ).fetchall(),
                    start=1,
                )
            }
            runs = conn.execute(
                "SELECT id, job_id, stage, status FROM run WHERE session_id = ?"
                " AND producer = 'engine' AND status IN ('succeeded', 'failed')"
                " ORDER BY created_at, rowid",
                (row["id"],),
            ).fetchall()
            sessions.append(
                {
                    "session": number,
                    "audio_s": row["duration_s"],
                    "runs": [_run(data, row["id"], run, jobs) for run in runs],
                }
            )
        return sessions
    finally:
        conn.close()


def _run(
    data: DataDir, session_id: str, row: Any, jobs: dict[int, tuple[int, str | None]]
) -> dict[str, Any]:
    rank, rerun = jobs.get(row["job_id"], (None, None))
    said: dict[str, Any] = {
        "processing": rank,
        "rerun": rerun,
        "stage": row["stage"],
        "status": row["status"],
    }
    try:
        prov = read_provenance(data.run_dir(session_id, row["id"]))
    except (OSError, ValueError) as exc:  # damaged by hand, or a newer engine's
        log.warning("processing times: the provenance of %s is unreadable: %s", row["id"], exc)
        return {**said, "provenance": "illisible"}
    if prov is None:
        # Closed by the application before the engine wrote it (a stage that could not
        # start): said as such, never dropped (P8).
        return {**said, "provenance": "absente"}
    inputs = prov.inputs
    return {
        **said,
        "provenance": "lue",
        "engine_id": prov.engine_id,
        "duration_s": round(prov.duration_s, 3),
        "max_rss_bytes": prov.max_rss_bytes or None,
        "exit_code": prov.exit_code,
        "error_type": prov.error.type if prov.error is not None else None,
        "error_code": prov.error.code.value
        if prov.error is not None and prov.error.code is not None
        else None,
        **{key: technical(inputs.get(key)) for key in INPUTS_KEPT},
        "model": {"repo": prov.model.repo, "revision": prov.model.revision}
        if prov.model is not None
        else None,
        "settings": technical(prov.settings),
        "versions": technical(prov.versions, names_only=False),
        "engine_version": prov.coulisses_version,
        "platform": technical(prov.machine.get("platform"), names_only=False),
    }
