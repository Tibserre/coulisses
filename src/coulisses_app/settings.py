"""The user's settings kept in the database (`app_setting`), with their shipped defaults."""

from __future__ import annotations

import json
import sqlite3
from typing import Literal, get_args

from coulisses_app.prompting import assembly
from coulisses_app.prompting.generate import PHASES_REF, TITLE_REF

MODEL_KEY = "modele"

Writing = Literal["titre", "chapitres", "resume"]
"""What a language model writes: a session's title, its chapters, its summaries (ADR
0039; « rédaction » in the glossary)."""
WRITINGS: tuple[Writing, ...] = get_args(Writing)


def default_model(conn: sqlite3.Connection) -> str:
    """The model chosen before there was one per writing, else the shipped default
    (configuration, never code: P6). What a writing falls back on."""
    row = conn.execute("SELECT value FROM app_setting WHERE key = ?", (MODEL_KEY,)).fetchone()
    return json.loads(row[0]) if row else assembly.settings().default_model


def writing_of(action_ref: str) -> Writing:
    """What an action writes: the title, the chapters, or else a summary."""
    if action_ref == TITLE_REF:
        return "titre"
    if action_ref == PHASES_REF:
        return "chapitres"
    return "resume"


def writing_model(conn: sqlite3.Connection, writing: Writing) -> str:
    """The model chosen for this writing in the Réglages, else the default one."""
    row = conn.execute(
        "SELECT value FROM app_setting WHERE key = ?", (f"{MODEL_KEY}.{writing}",)
    ).fetchone()
    return json.loads(row[0]) if row else default_model(conn)


def writing_models(conn: sqlite3.Connection) -> dict[Writing, str]:
    return {writing: writing_model(conn, writing) for writing in WRITINGS}


def set_writing_model(conn: sqlite3.Connection, writing: Writing, model: str) -> None:
    with conn:
        conn.execute(
            "INSERT INTO app_setting (key, value) VALUES (?, ?)"
            " ON CONFLICT (key) DO UPDATE SET value = excluded.value",
            (f"{MODEL_KEY}.{writing}", json.dumps(model)),
        )
