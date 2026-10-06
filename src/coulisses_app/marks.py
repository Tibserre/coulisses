"""What the user marks while recording (spec §7.2, §7.5, §7.8): markers (play, discussion,
key moment) and timed notes, at a time of the recording (pauses left out). Play and
discussion markers cut chapters before the detection does (ADR 0024)."""

from __future__ import annotations

import sqlite3
from typing import Literal

from pydantic import BaseModel

from coulisses_app.spaces import NotFoundError, SpaceError
from coulisses_app.storage.db import now_iso

MarkerKind = Literal["scene", "discussion", "key_moment"]
NOTE_MAX = 2000


class Marker(BaseModel):
    id: int
    kind: MarkerKind
    at_s: float


class TimedNote(BaseModel):
    id: int
    at_s: float
    text: str


def markers(conn: sqlite3.Connection, session_id: str) -> list[Marker]:
    return [
        Marker(id=r["id"], kind=r["kind"], at_s=r["at_s"])
        for r in conn.execute(
            "SELECT id, kind, at_s FROM marker WHERE session_id = ? ORDER BY at_s, id",
            (session_id,),
        )
    ]


def timed_notes(conn: sqlite3.Connection, session_id: str) -> list[TimedNote]:
    return [
        TimedNote(id=r["id"], at_s=r["at_s"], text=r["text"])
        for r in conn.execute(
            "SELECT id, at_s, text FROM note WHERE session_id = ? AND at_s IS NOT NULL"
            " AND text != '' ORDER BY at_s, id",
            (session_id,),
        )
    ]


def add_marker(conn: sqlite3.Connection, session_id: str, kind: MarkerKind, at_s: float) -> Marker:
    with conn:
        cursor = conn.execute(
            "INSERT INTO marker (session_id, kind, at_s, created_at) VALUES (?, ?, ?, ?)",
            (session_id, kind, at_s, now_iso()),
        )
    assert cursor.lastrowid is not None
    return Marker(id=cursor.lastrowid, kind=kind, at_s=at_s)


def add_timed_note(conn: sqlite3.Connection, session_id: str, at_s: float, text: str) -> TimedNote:
    text = text.strip()
    if not text:
        raise SpaceError("Une note vide n'est pas gardée.")
    if len(text) > NOTE_MAX:
        raise SpaceError(f"Une note tient en {NOTE_MAX} caractères.")
    now = now_iso()
    with conn:
        cursor = conn.execute(
            "INSERT INTO note (session_id, at_s, text, created_at, updated_at)"
            " VALUES (?, ?, ?, ?, ?)",
            (session_id, at_s, text, now, now),
        )
    assert cursor.lastrowid is not None
    return TimedNote(id=cursor.lastrowid, at_s=at_s, text=text)


def remove(
    conn: sqlite3.Connection, session_id: str, what: Literal["marker", "note"], item_id: int
) -> None:
    """Taken back by the user while recording (a slip of the finger), at their request."""
    table = "marker" if what == "marker" else "note"
    extra = "" if what == "marker" else " AND at_s IS NOT NULL"
    with conn:
        removed = conn.execute(
            f"DELETE FROM {table} WHERE id = ? AND session_id = ?{extra}",  # fixed names
            (item_id, session_id),
        ).rowcount
    if not removed:
        raise NotFoundError("Marqueur ou note introuvable.")
