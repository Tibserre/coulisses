"""What a session shows while it is being processed (ADR 0058): the text once transcribed,
before anyone is told apart, with what was marked during the recording.

Read from the last transcription (aligned once the alignment is done) of the session's
runs, through the engine's contract only. A line's time is the measured time of its first
word, or none (P2): nothing is spread over the text. The names come with « who said what »;
until then, the text is an outline, never kept: the review reads the engine's runs.
"""

from __future__ import annotations

import logging
import re
import sqlite3

from coulisses.api import Transcript, read_output
from pydantic import BaseModel

from coulisses_app import marks
from coulisses_app.paths import DataDir
from coulisses_app.storage.db import connect

log = logging.getLogger(__name__)

SENTENCE_END = re.compile(r"[.?!…]$")
GAP_S = 2.0
"""A silence this long between two words starts a new line."""
MAX_WORDS = 40


class PreviewLine(BaseModel):
    start: float | None
    """The measured time of its first word; none when the engine did not measure it."""
    text: str


class Preview(BaseModel):
    lines: list[PreviewLine]
    aligned: bool
    """Its words' times are those of the alignment, measured on the audio."""
    markers: list[marks.Marker]
    notes: list[marks.TimedNote]


def _succeeded(conn: sqlite3.Connection, session_id: str, stage: str) -> str | None:
    """The stage's run of the session's last processing (as the stages show it), else the
    one of the version shown: never a run of another engine's version beside it (ADR 0040)."""
    job = conn.execute(
        "SELECT id FROM job WHERE session_id = ? AND kind = 'chain' ORDER BY id DESC LIMIT 1",
        (session_id,),
    ).fetchone()
    if job is not None:
        row = conn.execute(
            "SELECT id FROM run WHERE job_id = ? AND stage = ? AND status = 'succeeded'"
            " ORDER BY created_at DESC, rowid DESC LIMIT 1",
            (job["id"], stage),
        ).fetchone()
        if row is not None:
            return row["id"]
    row = conn.execute(
        "SELECT run_id FROM active_run WHERE session_id = ? AND stage = ?", (session_id, stage)
    ).fetchone()
    return row["run_id"] if row else None


def _upstream_of(conn: sqlite3.Connection, run_id: str) -> set[str]:
    return {
        r["upstream_run_id"]
        for r in conn.execute(
            "SELECT upstream_run_id FROM run_upstream WHERE run_id = ?", (run_id,)
        )
    }


class PreviewError(ValueError):
    """The transcription's output could not be read: said in French, its detail logged."""


def preview(data: DataDir, session_id: str) -> Preview:
    """The text as far as the processing has got; no line before the transcription. The
    alignment is taken only if it aligned the transcription taken."""
    conn = connect(data)
    try:
        transcribed = _succeeded(conn, session_id, "transcribe")
        aligned = _succeeded(conn, session_id, "align")
        if aligned is not None and (
            transcribed is None or transcribed not in _upstream_of(conn, aligned)
        ):
            aligned = None
        markers = marks.markers(conn, session_id)
        notes = marks.timed_notes(conn, session_id)
    finally:
        conn.close()
    run = aligned or transcribed
    lines: list[PreviewLine] = []
    if run is not None:
        try:
            transcript = read_output(data.run_dir(session_id, run), Transcript)
        except Exception as exc:
            log.exception("preview of %s (run %s)", session_id, run)
            raise PreviewError("L'aperçu du texte n'a pas pu être lu.") from exc
        lines = _lines(transcript)
    return Preview(lines=lines, aligned=aligned is not None, markers=markers, notes=notes)


def _lines(transcript: Transcript) -> list[PreviewLine]:
    measured = transcript.measured_word_timestamps
    lines: list[PreviewLine] = []
    words: list[str] = []
    start: float | None = None
    last_end: float | None = None
    for word in transcript.words:
        word_start = word.start if measured else None
        gap = word_start is not None and last_end is not None and word_start - last_end >= GAP_S
        if words and (gap or len(words) >= MAX_WORDS):
            lines.append(PreviewLine(start=start, text=" ".join(words)))
            words, start = [], None
        if not words:
            start = word_start
        words.append(word.text.strip())
        last_end = word.end if measured else None
        if SENTENCE_END.search(word.text.strip()):
            lines.append(PreviewLine(start=start, text=" ".join(words)))
            words, start = [], None
    if words:
        lines.append(PreviewLine(start=start, text=" ".join(words)))
    return [line for line in lines if line.text]
