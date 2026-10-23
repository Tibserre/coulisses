"""Full-text search in the corrected transcripts, the notes and the summaries (spec §7.11).

The index (`search_index`, SQLite FTS5, accents and case ignored) is a cache, never a
source of truth: a session is indexed again whenever what its text is made of changed
(version shown, corrections, notes, summaries, title), checked at each search. Deleting
it entirely loses nothing.
"""

from __future__ import annotations

import logging
import re
import sqlite3
from typing import Literal

from coulisses.api import RunNotSucceededError
from pydantic import BaseModel

from coulisses_app import corrections, notes
from coulisses_app.paths import DataDir
from coulisses_app.storage.db import connect

log = logging.getLogger(__name__)

Kind = Literal["title", "turn", "note", "summary"]

HIT_START = "\x02"
HIT_END = "\x03"
MAX_SESSIONS = 30
MAX_HITS = 5


class Part(BaseModel):
    text: str
    hit: bool


class Hit(BaseModel):
    kind: Kind
    ref: str
    """The line's index, the note's id, the generation's id; empty for the title."""
    at_s: float | None
    """Measured time of the line or the note, when it has one (P2)."""
    excerpt: list[Part]


class SessionHits(BaseModel):
    session_id: str
    hits: list[Hit]


class Results(BaseModel):
    query: str
    sessions: list[SessionHits]
    more: bool = False
    """Some hits are not shown (too many sessions, or passages in one): said, not hidden."""
    problems: list[str] = []
    """Sessions that could not be indexed (unreadable files…): said, not hidden (P8)."""


def _key(conn: sqlite3.Connection, session_id: str) -> str:
    """What a session's indexed text is made of: it changes, the index is redone."""
    parts = conn.execute(
        "SELECT s.title,"
        " (SELECT run_id FROM active_run WHERE session_id = s.id AND stage = 'attribute'),"
        " (SELECT run_id FROM active_run WHERE session_id = s.id AND stage = 'segment_phases'),"
        " (SELECT MAX(id) FROM edit WHERE session_id = s.id),"
        " (SELECT MAX(updated_at) || ':' || COUNT(*) FROM note WHERE session_id = s.id),"
        " (SELECT MAX(id) FROM generation WHERE session_id = s.id)"
        " FROM session s WHERE s.id = ?",
        (session_id,),
    ).fetchone()
    return "|".join("" if p is None else str(p) for p in parts)


def _entries(
    data: DataDir, conn: sqlite3.Connection, session_id: str
) -> list[tuple[Kind, str, float | None, str]]:
    found: list[tuple[Kind, str, float | None, str]] = []
    row = conn.execute("SELECT title FROM session WHERE id = ?", (session_id,)).fetchone()
    if row and row["title"]:
        found.append(("title", "", None, row["title"]))
    view = corrections.build_view(data, session_id, recognise=False)
    if view is not None:
        found.extend(
            ("turn", str(t.index), t.start, " ".join(w.text for w in t.words))
            for t in view.turns
            if t.words
        )
        found.extend(("note", str(n.id), n.at_s, n.text) for n in view.timed_notes)
    after = notes.after_session(conn, session_id)
    if after is not None and after.text.strip():
        found.append(("note", "apres", None, after.text))
    # The version shown of each summary, its latest (ADR 0060): a hit opens what it found.
    # The older ones stay on the disk, out of the search.
    for gen in conn.execute(
        "SELECT g.id, g.run_id FROM generation g WHERE g.session_id = ? AND g.id = ("
        " SELECT MAX(id) FROM generation WHERE session_id = g.session_id"
        " AND action_ref = g.action_ref) ORDER BY g.id",
        (session_id,),
    ):
        output = data.run_dir(session_id, gen["run_id"]) / "output.md"
        if output.is_file():
            found.append(("summary", str(gen["id"]), None, output.read_text(encoding="utf-8")))
    return found


def refresh(data: DataDir) -> list[str]:
    """Index again the sessions whose text changed, forget the deleted ones. Returns what
    could not be indexed."""
    problems: list[str] = []
    conn = connect(data)
    try:
        with conn:
            conn.execute(
                "DELETE FROM search_index WHERE session_id NOT IN (SELECT id FROM session)"
            )
        known = {r["session_id"]: r["key"] for r in conn.execute("SELECT * FROM search_state")}
        for row in conn.execute("SELECT id, title, recorded_at FROM session").fetchall():
            session_id = row["id"]
            key = _key(conn, session_id)
            if known.get(session_id) == key:
                continue
            try:
                entries = _entries(data, conn, session_id)
            # An unreadable output must not stop the search of the others: said (P8).
            except (OSError, ValueError, RunNotSucceededError) as exc:
                log.warning("search: %s not indexed: %s", session_id, exc)
                name = row["title"] or f"la séance du {row['recorded_at'][:10]}"
                problems.append(f"« {name} » n'a pas pu être lue pour la recherche.")
                continue
            with conn:
                conn.execute("DELETE FROM search_index WHERE session_id = ?", (session_id,))
                conn.executemany(
                    "INSERT INTO search_index (session_id, kind, ref, at_s, text)"
                    " VALUES (?, ?, ?, ?, ?)",
                    [(session_id, k, ref, at, text) for k, ref, at, text in entries],
                )
                conn.execute(
                    "INSERT INTO search_state (session_id, key) VALUES (?, ?)"
                    " ON CONFLICT (session_id) DO UPDATE SET key = excluded.key",
                    (session_id, key),
                )
    finally:
        conn.close()
    return problems


def _match(query: str) -> str | None:
    """Every word typed, as a prefix (« repet » finds « répétition »): FTS5 syntax is never
    passed through from the user."""
    words = re.findall(r"\w+", query)
    if not words:
        return None
    return " ".join(f'"{w}"*' for w in words)


def _parts(snippet: str) -> list[Part]:
    parts: list[Part] = []
    for k, piece in enumerate(re.split(f"[{HIT_START}{HIT_END}]", snippet)):
        if piece:
            parts.append(Part(text=piece, hit=k % 2 == 1))
    return parts


def search(data: DataDir, query: str) -> Results:
    problems = refresh(data)
    match = _match(query)
    if match is None:
        return Results(query=query, sessions=[], problems=problems)
    conn = connect(data)
    try:
        rows = conn.execute(
            "SELECT session_id, kind, ref, at_s,"
            f" snippet(search_index, 4, '{HIT_START}', '{HIT_END}', '…', 14) AS excerpt"
            " FROM search_index WHERE search_index MATCH ? ORDER BY rank LIMIT 500",
            (match,),
        ).fetchall()
    finally:
        conn.close()
    found: dict[str, SessionHits] = {}
    more = len(rows) >= 500
    for row in rows:
        hits = found.get(row["session_id"])
        if hits is None:
            if len(found) >= MAX_SESSIONS:
                more = True
                continue
            hits = found[row["session_id"]] = SessionHits(session_id=row["session_id"], hits=[])
        if len(hits.hits) >= MAX_HITS:
            more = True
        else:
            hits.hits.append(
                Hit(
                    kind=row["kind"],
                    ref=row["ref"],
                    at_s=row["at_s"],
                    excerpt=_parts(row["excerpt"]),
                )
            )
    return Results(query=query, sessions=list(found.values()), more=more, problems=problems)
