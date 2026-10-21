"""Spaces, their people and their glossary (ADR 0020).

A space is a troupe, a team, a client. Its people (members and guests) and its glossary
belong to it alone: a person present in two spaces has two records. Nothing is deleted:
people and glossary entries are archived, so past sessions keep their names (P8)."""

from __future__ import annotations

import json
import sqlite3
from collections import Counter

from pydantic import BaseModel

from coulisses_app.paths import DataDir
from coulisses_app.storage.db import connect, now_iso

COLOR_SLOTS = 8
"""Size of the speaker palette of the art direction; beyond it, colours loop."""


class SpaceError(ValueError):
    """A request that cannot be honoured; the message is shown to the user."""


class NotFoundError(SpaceError):
    pass


class Space(BaseModel):
    id: int
    name: str
    voice_recognition: bool
    archived: bool


class Person(BaseModel):
    id: int
    space_id: int
    kind: str
    """member or guest."""
    name: str
    role: str | None
    color_slot: int
    archived: bool


class GlossaryEntry(BaseModel):
    id: int
    space_id: int
    term: str
    category: str | None
    variants: list[str]
    """Known wrong spellings, to help the review (« Kathy » for « Cathy »)."""
    archived: bool


def _clean(text: str | None, what: str) -> str:
    value = (text or "").strip()
    if not value:
        raise SpaceError(f"{what} ne peut pas être vide.")
    return value


def _space(row: sqlite3.Row) -> Space:
    return Space(
        id=row["id"],
        name=row["name"],
        voice_recognition=bool(row["voice_recognition"]),
        archived=row["archived_at"] is not None,
    )


def _person(row: sqlite3.Row) -> Person:
    return Person(
        id=row["id"],
        space_id=row["space_id"],
        kind=row["kind"],
        name=row["name"],
        role=row["role"],
        color_slot=row["color_slot"],
        archived=row["archived_at"] is not None,
    )


def _entry(row: sqlite3.Row) -> GlossaryEntry:
    return GlossaryEntry(
        id=row["id"],
        space_id=row["space_id"],
        term=row["term"],
        category=row["category"],
        variants=json.loads(row["variants"]),
        archived=row["archived_at"] is not None,
    )


# -- spaces --------------------------------------------------------------------------


def list_spaces(data: DataDir) -> list[Space]:
    conn = connect(data)
    try:
        rows = conn.execute("SELECT * FROM space ORDER BY archived_at IS NOT NULL, name")
        return [_space(r) for r in rows]
    finally:
        conn.close()


def get_space(conn: sqlite3.Connection, space_id: int) -> Space:
    row = conn.execute("SELECT * FROM space WHERE id = ?", (space_id,)).fetchone()
    if row is None:
        raise NotFoundError("Espace introuvable.")
    return _space(row)


def default_space_id(conn: sqlite3.Connection) -> int:
    row = conn.execute("SELECT MIN(id) FROM space WHERE archived_at IS NULL").fetchone()
    if row[0] is None:
        raise SpaceError("Aucun espace : créez-en un d'abord.")
    return row[0]


TEMPLATES: dict[str, list[str]] = {
    "impro": ["resume-impro"],
    "reunion": ["compte-rendu-reunion"],
    "vide": [],
}
"""Starting templates (ADR 0020): the summaries a new space runs after processing. They
fill the settings once; there is no space type afterwards."""


def create_space(data: DataDir, name: str, template: str = "vide") -> Space:
    if template not in TEMPLATES:
        raise SpaceError("Modèle de départ inconnu.")
    conn = connect(data)
    try:
        with conn:
            cursor = conn.execute(
                "INSERT INTO space (name, created_at) VALUES (?, ?)",
                (_clean(name, "Le nom de l'espace"), now_iso()),
            )
            conn.executemany(
                "INSERT INTO action_preference (space_id, action_ref, auto_run) VALUES (?, ?, 1)",
                [(cursor.lastrowid, ref) for ref in TEMPLATES[template]],
            )
        assert cursor.lastrowid is not None
        return get_space(conn, cursor.lastrowid)
    finally:
        conn.close()


def update_space(
    data: DataDir,
    space_id: int,
    *,
    name: str | None = None,
    voice_recognition: bool | None = None,
    archived: bool | None = None,
) -> Space:
    conn = connect(data)
    try:
        get_space(conn, space_id)
        with conn:
            if name is not None:
                conn.execute(
                    "UPDATE space SET name = ? WHERE id = ?",
                    (_clean(name, "Le nom de l'espace"), space_id),
                )
            if voice_recognition is not None:
                conn.execute(
                    "UPDATE space SET voice_recognition = ? WHERE id = ?",
                    (int(voice_recognition), space_id),
                )
            if archived is not None:
                conn.execute(
                    "UPDATE space SET archived_at = ? WHERE id = ?",
                    (now_iso() if archived else None, space_id),
                )
        return get_space(conn, space_id)
    finally:
        conn.close()


# -- people --------------------------------------------------------------------------


def list_people(data: DataDir, space_id: int) -> list[Person]:
    conn = connect(data)
    try:
        get_space(conn, space_id)
        rows = conn.execute(
            "SELECT * FROM person WHERE space_id = ?"
            " ORDER BY archived_at IS NOT NULL, kind DESC, name COLLATE NOCASE",
            (space_id,),
        )
        return [_person(r) for r in rows]
    finally:
        conn.close()


def get_person(conn: sqlite3.Connection, person_id: int) -> Person:
    row = conn.execute("SELECT * FROM person WHERE id = ?", (person_id,)).fetchone()
    if row is None:
        raise NotFoundError("Personne introuvable.")
    return _person(row)


def _free_color_slot(conn: sqlite3.Connection, space_id: int) -> int:
    """The least used colour among the space's current people: everyone keeps theirs,
    and newcomers spread over the palette."""
    used = Counter(
        r[0]
        for r in conn.execute(
            "SELECT color_slot FROM person WHERE space_id = ? AND archived_at IS NULL",
            (space_id,),
        )
    )
    return min(range(COLOR_SLOTS), key=lambda slot: (used[slot], slot))


def add_person(
    data: DataDir, space_id: int, *, kind: str, name: str, role: str | None = None
) -> Person:
    if kind not in ("member", "guest"):
        raise SpaceError("Une personne est un membre ou un invité.")
    conn = connect(data)
    try:
        get_space(conn, space_id)
        with conn:
            cursor = conn.execute(
                "INSERT INTO person (space_id, kind, name, role, color_slot, created_at)"
                " VALUES (?, ?, ?, ?, ?, ?)",
                (
                    space_id,
                    kind,
                    _clean(name, "Le nom"),
                    (role or "").strip() or None,
                    _free_color_slot(conn, space_id),
                    now_iso(),
                ),
            )
        assert cursor.lastrowid is not None
        return get_person(conn, cursor.lastrowid)
    finally:
        conn.close()


def update_person(
    data: DataDir,
    person_id: int,
    *,
    name: str | None = None,
    role: str | None = None,
    kind: str | None = None,
    archived: bool | None = None,
) -> Person:
    conn = connect(data)
    try:
        get_person(conn, person_id)
        with conn:
            if name is not None:
                conn.execute(
                    "UPDATE person SET name = ? WHERE id = ?", (_clean(name, "Le nom"), person_id)
                )
            if role is not None:
                conn.execute(
                    "UPDATE person SET role = ? WHERE id = ?", (role.strip() or None, person_id)
                )
            if kind is not None:
                if kind not in ("member", "guest"):
                    raise SpaceError("Une personne est un membre ou un invité.")
                conn.execute("UPDATE person SET kind = ? WHERE id = ?", (kind, person_id))
            if archived is not None:
                conn.execute(
                    "UPDATE person SET archived_at = ? WHERE id = ?",
                    (now_iso() if archived else None, person_id),
                )
        return get_person(conn, person_id)
    finally:
        conn.close()


# -- glossary ------------------------------------------------------------------------


def _variants(values: list[str] | None) -> str:
    cleaned = [v.strip() for v in values or [] if v.strip()]
    return json.dumps(sorted(set(cleaned), key=cleaned.index), ensure_ascii=False)


def list_glossary(data: DataDir, space_id: int) -> list[GlossaryEntry]:
    conn = connect(data)
    try:
        get_space(conn, space_id)
        rows = conn.execute(
            "SELECT * FROM glossary_entry WHERE space_id = ?"
            " ORDER BY archived_at IS NOT NULL, term COLLATE NOCASE",
            (space_id,),
        )
        return [_entry(r) for r in rows]
    finally:
        conn.close()


def add_entry(
    data: DataDir,
    space_id: int,
    *,
    term: str,
    category: str | None = None,
    variants: list[str] | None = None,
) -> GlossaryEntry:
    conn = connect(data)
    try:
        get_space(conn, space_id)
        with conn:
            cursor = conn.execute(
                "INSERT INTO glossary_entry (space_id, term, category, variants, created_at)"
                " VALUES (?, ?, ?, ?, ?)",
                (
                    space_id,
                    _clean(term, "Le terme"),
                    (category or "").strip() or None,
                    _variants(variants),
                    now_iso(),
                ),
            )
        row = conn.execute(
            "SELECT * FROM glossary_entry WHERE id = ?", (cursor.lastrowid,)
        ).fetchone()
        return _entry(row)
    finally:
        conn.close()


def update_entry(
    data: DataDir,
    entry_id: int,
    *,
    term: str | None = None,
    category: str | None = None,
    variants: list[str] | None = None,
    archived: bool | None = None,
) -> GlossaryEntry:
    conn = connect(data)
    try:
        if (
            conn.execute("SELECT 1 FROM glossary_entry WHERE id = ?", (entry_id,)).fetchone()
            is None
        ):
            raise NotFoundError("Terme introuvable.")
        with conn:
            if term is not None:
                conn.execute(
                    "UPDATE glossary_entry SET term = ? WHERE id = ?",
                    (_clean(term, "Le terme"), entry_id),
                )
            if category is not None:
                conn.execute(
                    "UPDATE glossary_entry SET category = ? WHERE id = ?",
                    (category.strip() or None, entry_id),
                )
            if variants is not None:
                conn.execute(
                    "UPDATE glossary_entry SET variants = ? WHERE id = ?",
                    (_variants(variants), entry_id),
                )
            if archived is not None:
                conn.execute(
                    "UPDATE glossary_entry SET archived_at = ? WHERE id = ?",
                    (now_iso() if archived else None, entry_id),
                )
        row = conn.execute("SELECT * FROM glossary_entry WHERE id = ?", (entry_id,)).fetchone()
        return _entry(row)
    finally:
        conn.close()


def glossary_terms(conn: sqlite3.Connection, space_id: int) -> list[str]:
    """The current terms of a space, given to the engine with each recording."""
    return [
        r[0]
        for r in conn.execute(
            "SELECT term FROM glossary_entry WHERE space_id = ? AND archived_at IS NULL"
            " ORDER BY term COLLATE NOCASE",
            (space_id,),
        )
    ]


# -- attendees -----------------------------------------------------------------------


def check_attendees(conn: sqlite3.Connection, space_id: int, person_ids: list[int]) -> None:
    """Every attendee must be a person of the session's space (spaces stay sealed)."""
    for person_id in person_ids:
        person = get_person(conn, person_id)
        if person.space_id != space_id:
            raise SpaceError(f"{person.name} n'appartient pas à l'espace de cette séance.")


def set_attendees(
    data: DataDir, session_id: str, person_ids: list[int], unnamed: int | None
) -> None:
    """Who was there, checked after the fact. It does not reprocess anything: the minimum
    of voices given to the engine stays the one of the processing already done."""
    if unnamed is not None and unnamed < 1:
        raise SpaceError("Le nombre de présents non nommés doit être au moins 1.")
    conn = connect(data)
    try:
        row = conn.execute("SELECT space_id FROM session WHERE id = ?", (session_id,)).fetchone()
        if row is None:
            raise NotFoundError("Séance introuvable.")
        check_attendees(conn, row["space_id"], person_ids)
        with conn:
            conn.execute("DELETE FROM attendee WHERE session_id = ?", (session_id,))
            conn.executemany(
                "INSERT INTO attendee (session_id, person_id) VALUES (?, ?)",
                [(session_id, p) for p in dict.fromkeys(person_ids)],
            )
            conn.execute(
                "UPDATE session SET unnamed_attendees = ? WHERE id = ?", (unnamed, session_id)
            )
    finally:
        conn.close()


def move_session(data: DataDir, session_id: str, space_id: int) -> list[str]:
    """Into another space, while nothing has been processed yet (a recording started in the
    space selected, then corrected, spec §7.2). Its project and its people belong to the
    old space: the project is left, the people checked are unchecked (the page says it);
    the number not named stays. Once processed, a session stays in its space: its voices
    are attached to that space's people (ADR 0020). Returns the names unchecked, to be
    said."""
    conn = connect(data)
    try:
        row = conn.execute("SELECT space_id FROM session WHERE id = ?", (session_id,)).fetchone()
        if row is None:
            raise NotFoundError("Séance introuvable.")
        if row["space_id"] == space_id:
            return []
        space = get_space(conn, space_id)
        if space.archived:
            raise SpaceError("Cet espace est archivé : on n'y range plus de séance.")
        with conn:
            # Checked and done together: a processing asked meanwhile cannot slip between.
            conn.execute("BEGIN IMMEDIATE")
            if conn.execute("SELECT 1 FROM job WHERE session_id = ?", (session_id,)).fetchone():
                raise SpaceError("Une séance dont le traitement est demandé reste dans son espace.")
            unchecked = [
                r["name"]
                for r in conn.execute(
                    "SELECT p.name FROM attendee a JOIN person p ON p.id = a.person_id"
                    " WHERE a.session_id = ? ORDER BY p.name",
                    (session_id,),
                )
            ]
            conn.execute("DELETE FROM attendee WHERE session_id = ?", (session_id,))
            conn.execute(
                "UPDATE session SET space_id = ?, project_id = NULL WHERE id = ?",
                (space_id, session_id),
            )
        return unchecked
    finally:
        conn.close()


def attendee_ids(conn: sqlite3.Connection, session_id: str) -> list[int]:
    return [
        r[0]
        for r in conn.execute(
            "SELECT person_id FROM attendee WHERE session_id = ? ORDER BY person_id",
            (session_id,),
        )
    ]


# -- summaries run by the space -----------------------------------------------------------


class SpaceAction(BaseModel):
    action_ref: str
    auto_run: bool
    model: str | None
    """None: the default model."""


def space_actions(data: DataDir, space_id: int) -> list[SpaceAction]:
    conn = connect(data)
    try:
        get_space(conn, space_id)
        return [
            SpaceAction(action_ref=r["action_ref"], auto_run=bool(r["auto_run"]), model=r["model"])
            for r in conn.execute(
                "SELECT * FROM action_preference WHERE space_id = ? ORDER BY action_ref",
                (space_id,),
            )
        ]
    finally:
        conn.close()


def set_space_action(
    data: DataDir, space_id: int, action_ref: str, *, auto_run: bool, model: str | None
) -> list[SpaceAction]:
    conn = connect(data)
    try:
        get_space(conn, space_id)
        with conn:
            conn.execute(
                "INSERT INTO action_preference (space_id, action_ref, auto_run, model)"
                " VALUES (?, ?, ?, ?) ON CONFLICT (space_id, action_ref)"
                " DO UPDATE SET auto_run = excluded.auto_run, model = excluded.model",
                (space_id, action_ref, int(auto_run), model),
            )
    finally:
        conn.close()
    return space_actions(data, space_id)


def set_offered_action(data: DataDir, space_id: int, action_ref: str | None) -> list[SpaceAction]:
    """The summary offered first in this space's sessions (ADR 0025), in one transaction:
    only one, and the other settings of each action are left as they are."""
    conn = connect(data)
    try:
        get_space(conn, space_id)
        with conn:
            conn.execute(
                "UPDATE action_preference SET auto_run = 0 WHERE space_id = ?", (space_id,)
            )
            if action_ref is not None:
                conn.execute(
                    "INSERT INTO action_preference (space_id, action_ref, auto_run)"
                    " VALUES (?, ?, 1)"
                    " ON CONFLICT (space_id, action_ref) DO UPDATE SET auto_run = 1",
                    (space_id, action_ref),
                )
    finally:
        conn.close()
    return space_actions(data, space_id)
