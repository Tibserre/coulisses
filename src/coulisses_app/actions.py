"""The actions (spec §7.9): the summaries one can ask for, provided or written by the user.

Provided actions are files of the application (`prompting/textes/actions/`), read-only.
Modifying one creates its modified version in the database (`action.based_on`), used in its
place under the same key; restoring the original archives that version. An action of the
user's own has the key `perso-<id>`. Nothing is deleted: an action is archived, and every
generation keeps the exact prompt it was made with (spec.json, P5).
"""

from __future__ import annotations

import sqlite3

from pydantic import BaseModel

from coulisses_app.prompting import assembly
from coulisses_app.spaces import NotFoundError, SpaceError
from coulisses_app.storage.db import now_iso

OWN_PREFIX = "perso-"
NAME_MAX = 80
DESCRIPTION_MAX = 300


class ActionInfo(BaseModel):
    ref: str
    name: str
    description: str
    prompt: str
    provided: bool
    """Shipped with the application (possibly modified)."""
    modified: bool
    """A provided action whose modified version is in force: the original is restorable."""
    updated_at: str | None = None


def _provided() -> dict[str, assembly.Action]:
    return {a.ref: a for a in assembly.provided_actions()}


def _own_id(ref: str) -> int | None:
    if not ref.startswith(OWN_PREFIX):
        return None
    try:
        return int(ref.removeprefix(OWN_PREFIX))
    except ValueError:
        return None


def list_actions(conn: sqlite3.Connection) -> list[ActionInfo]:
    """Every action in force, provided ones first in their modified version if any."""
    rows = conn.execute("SELECT * FROM action WHERE archived_at IS NULL ORDER BY id").fetchall()
    provided = _provided()
    overrides = {r["based_on"]: r for r in rows if r["based_on"] in provided}
    found: list[ActionInfo] = []
    for ref, original in provided.items():
        row = overrides.get(ref)
        found.append(
            ActionInfo(
                ref=ref,
                name=row["name"] if row else original.name,
                description=row["description"] if row else original.description,
                prompt=row["prompt"] if row else original.prompt,
                provided=True,
                modified=row is not None,
                updated_at=row["updated_at"] if row else None,
            )
        )
    found.sort(key=lambda a: a.name.lower())
    own = [
        ActionInfo(
            ref=f"{OWN_PREFIX}{r['id']}",
            name=r["name"],
            description=r["description"],
            prompt=r["prompt"],
            provided=False,
            modified=False,
            updated_at=r["updated_at"],
        )
        for r in rows
        # A modified version whose provided action is no longer shipped stays usable, as
        # an action of the user's own: never hidden (P8).
        if r["based_on"] not in provided
    ]
    return found + sorted(own, key=lambda a: a.name.lower())


def get_action(conn: sqlite3.Connection, ref: str) -> ActionInfo:
    for found in list_actions(conn):
        if found.ref == ref:
            return found
    raise NotFoundError("Action introuvable.")


def as_prompt(action: ActionInfo) -> assembly.Action:
    return assembly.Action(
        ref=action.ref, name=action.name, description=action.description, prompt=action.prompt
    )


def _checked(name: str, description: str, prompt: str) -> tuple[str, str, str]:
    name = " ".join(name.split())
    description = " ".join(description.split())
    prompt = prompt.strip()
    if not name:
        raise SpaceError("Une action a besoin d'un nom.")
    if len(name) > NAME_MAX:
        raise SpaceError(f"Le nom d'une action tient en {NAME_MAX} caractères.")
    if len(description) > DESCRIPTION_MAX:
        raise SpaceError(f"La description tient en {DESCRIPTION_MAX} caractères.")
    if not prompt:
        raise SpaceError("Le prompt d'une action ne peut pas être vide.")
    return name, description, prompt


def create(conn: sqlite3.Connection, name: str, description: str, prompt: str) -> ActionInfo:
    name, description, prompt = _checked(name, description, prompt)
    now = now_iso()
    with conn:
        cursor = conn.execute(
            "INSERT INTO action (name, description, prompt, created_at, updated_at)"
            " VALUES (?, ?, ?, ?, ?)",
            (name, description, prompt, now, now),
        )
    return get_action(conn, f"{OWN_PREFIX}{cursor.lastrowid}")


def update(
    conn: sqlite3.Connection, ref: str, name: str, description: str, prompt: str
) -> ActionInfo:
    """Save an action. For a provided one, its modified version (created the first time)."""
    current = get_action(conn, ref)
    name, description, prompt = _checked(name, description, prompt)
    if (name, description, prompt) == (current.name, current.description, current.prompt):
        return current
    now = now_iso()
    with conn:
        if current.provided and not current.modified:
            conn.execute(
                "INSERT INTO action (name, description, prompt, based_on, created_at,"
                " updated_at) VALUES (?, ?, ?, ?, ?, ?)",
                (name, description, prompt, ref, now, now),
            )
        elif current.provided:
            conn.execute(
                "UPDATE action SET name = ?, description = ?, prompt = ?, updated_at = ?"
                " WHERE based_on = ? AND archived_at IS NULL",
                (name, description, prompt, now, ref),
            )
        else:
            conn.execute(
                "UPDATE action SET name = ?, description = ?, prompt = ?, updated_at = ?"
                " WHERE id = ?",
                (name, description, prompt, now, _own_id(ref)),
            )
    return get_action(conn, ref)


def restore(conn: sqlite3.Connection, ref: str) -> ActionInfo:
    """Back to the provided original: its modified version is archived, not erased."""
    current = get_action(conn, ref)
    if not current.modified:
        raise SpaceError("Cette action n'a pas été modifiée.")
    with conn:
        conn.execute(
            "UPDATE action SET archived_at = ? WHERE based_on = ? AND archived_at IS NULL",
            (now_iso(), ref),
        )
    return get_action(conn, ref)


def duplicate(conn: sqlite3.Connection, ref: str) -> ActionInfo:
    source = get_action(conn, ref)
    name = f"Copie de {source.name}"
    if len(name) > NAME_MAX:
        name = source.name  # never cut: the same name, to be renamed by the user
    return create(conn, name, source.description, source.prompt)


def archive(conn: sqlite3.Connection, ref: str) -> None:
    """Remove an action of the user's own from the lists; its row, its settings in each
    space and every summary made with it stay (it is no longer offered). A provided action
    is restored instead, never removed."""
    current = get_action(conn, ref)
    if current.provided:
        raise SpaceError(
            "Une action fournie ne se retire pas : restaurez l'original ou ne la lancez plus."
        )
    with conn:
        conn.execute("UPDATE action SET archived_at = ? WHERE id = ?", (now_iso(), _own_id(ref)))
