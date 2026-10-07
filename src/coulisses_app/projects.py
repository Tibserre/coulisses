"""Projects: they group the sessions of a space (a show, for a troupe; spec §7.1, §7.11).

A session belongs to one project of its own space, or to none. A project is archived,
never deleted: its sessions stay in it.
"""

from __future__ import annotations

import sqlite3

from pydantic import BaseModel

from coulisses_app.paths import DataDir
from coulisses_app.spaces import NotFoundError, SpaceError
from coulisses_app.storage.db import connect, now_iso

NAME_MAX = 120


class Project(BaseModel):
    id: int
    space_id: int
    name: str
    archived: bool


def _project(row: sqlite3.Row) -> Project:
    return Project(
        id=row["id"],
        space_id=row["space_id"],
        name=row["name"],
        archived=row["archived_at"] is not None,
    )


def _name(name: str) -> str:
    cleaned = " ".join(name.split())
    if not cleaned:
        raise SpaceError("Un projet a besoin d'un nom.")
    if len(cleaned) > NAME_MAX:
        raise SpaceError(f"Un nom de projet tient en {NAME_MAX} caractères.")
    return cleaned


def list_projects(data: DataDir) -> list[Project]:
    """Every project, of every space, archived ones included (the interface sorts)."""
    conn = connect(data)
    try:
        return [
            _project(r)
            for r in conn.execute("SELECT * FROM project ORDER BY name COLLATE NOCASE, id")
        ]
    finally:
        conn.close()


def _get(conn: sqlite3.Connection, project_id: int) -> sqlite3.Row:
    row = conn.execute("SELECT * FROM project WHERE id = ?", (project_id,)).fetchone()
    if row is None:
        raise NotFoundError("Projet introuvable.")
    return row


def create(data: DataDir, space_id: int, name: str) -> Project:
    cleaned = _name(name)
    conn = connect(data)
    try:
        if conn.execute("SELECT 1 FROM space WHERE id = ?", (space_id,)).fetchone() is None:
            raise NotFoundError("Espace introuvable.")
        if conn.execute(
            "SELECT 1 FROM project WHERE space_id = ? AND archived_at IS NULL"
            " AND name = ? COLLATE NOCASE",
            (space_id, cleaned),
        ).fetchone():
            raise SpaceError(f"Un projet « {cleaned} » existe déjà dans cet espace.")
        with conn:
            cursor = conn.execute(
                "INSERT INTO project (space_id, name, created_at) VALUES (?, ?, ?)",
                (space_id, cleaned, now_iso()),
            )
        assert cursor.lastrowid is not None
        return _project(_get(conn, cursor.lastrowid))
    finally:
        conn.close()


def update(
    data: DataDir, project_id: int, *, name: str | None = None, archived: bool | None = None
) -> Project:
    conn = connect(data)
    try:
        row = _get(conn, project_id)
        with conn:
            if name is not None:
                cleaned = _name(name)
                if conn.execute(
                    "SELECT 1 FROM project WHERE space_id = ? AND archived_at IS NULL"
                    " AND name = ? COLLATE NOCASE AND id != ?",
                    (row["space_id"], cleaned, project_id),
                ).fetchone():
                    raise SpaceError(f"Un projet « {cleaned} » existe déjà dans cet espace.")
                conn.execute("UPDATE project SET name = ? WHERE id = ?", (cleaned, project_id))
            # Back in use: its name must not be another project's in use.
            if (
                archived is False
                and row["archived_at"] is not None
                and conn.execute(
                    "SELECT 1 FROM project WHERE space_id = ? AND archived_at IS NULL"
                    " AND name = ? COLLATE NOCASE AND id != ?",
                    (row["space_id"], _name(name) if name else row["name"], project_id),
                ).fetchone()
            ):
                raise SpaceError(
                    f"Un projet « {row['name']} » est déjà en usage dans cet espace : "
                    "renommez l'un des deux."
                )
            if archived is not None:
                conn.execute(
                    "UPDATE project SET archived_at = ? WHERE id = ?",
                    (now_iso() if archived else None, project_id),
                )
        return _project(_get(conn, project_id))
    finally:
        conn.close()


def check(conn: sqlite3.Connection, space_id: int, project_id: int | None) -> None:
    """A session's project is one of its own space, still in use."""
    if project_id is None:
        return
    row = _get(conn, project_id)
    if row["space_id"] != space_id:
        raise SpaceError("Ce projet appartient à un autre espace.")
    if row["archived_at"] is not None:
        raise SpaceError("Ce projet est archivé.")


def set_session_project(data: DataDir, session_id: str, project_id: int | None) -> None:
    conn = connect(data)
    try:
        row = conn.execute("SELECT space_id FROM session WHERE id = ?", (session_id,)).fetchone()
        if row is None:
            raise NotFoundError("Séance introuvable.")
        check(conn, row["space_id"], project_id)
        with conn:
            conn.execute("UPDATE session SET project_id = ? WHERE id = ?", (project_id, session_id))
    finally:
        conn.close()
