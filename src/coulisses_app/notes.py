"""Notes taken by hand (spec §7.8): here, the free note written after the session. It goes
into the context of every generation; a summary made before it changed is stale."""

from __future__ import annotations

import hashlib
import sqlite3

from pydantic import BaseModel

from coulisses_app.spaces import NotFoundError, SpaceError
from coulisses_app.storage.db import now_iso

TEXT_MAX = 20_000


class Note(BaseModel):
    text: str
    updated_at: str


def after_session(conn: sqlite3.Connection, session_id: str) -> Note | None:
    row = conn.execute(
        "SELECT text, updated_at FROM note WHERE session_id = ? AND at_s IS NULL"
        " ORDER BY id LIMIT 1",
        (session_id,),
    ).fetchone()
    return Note(text=row["text"], updated_at=row["updated_at"]) if row else None


def set_after_session(conn: sqlite3.Connection, session_id: str, text: str) -> Note:
    """Write the note after the session. Emptied, it stays as an empty note (the user's
    own doing, visible), and no longer goes into the context."""
    if conn.execute("SELECT 1 FROM session WHERE id = ?", (session_id,)).fetchone() is None:
        raise NotFoundError("Séance introuvable.")
    text = text.strip()
    if len(text) > TEXT_MAX:
        raise SpaceError(f"Une note tient en {TEXT_MAX} caractères.")
    now = now_iso()
    with conn:
        updated = conn.execute(
            "UPDATE note SET text = ?, updated_at = ? WHERE id = (SELECT id FROM note"
            " WHERE session_id = ? AND at_s IS NULL ORDER BY id LIMIT 1)",
            (text, now, session_id),
        )
        if updated.rowcount == 0:
            conn.execute(
                "INSERT INTO note (session_id, at_s, text, created_at, updated_at)"
                " VALUES (?, NULL, ?, ?, ?)",
                (session_id, text, now, now),
            )
    note = after_session(conn, session_id)
    assert note is not None
    return note


def digest(text: str | None) -> str | None:
    """What a summary remembers of the notes it read: None when there were none."""
    if not text:
        return None
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]
