"""The user's settings kept in the database (`app_setting`), with their shipped defaults."""

from __future__ import annotations

import json
import sqlite3

from coulisses_app.prompting import assembly

MODEL_KEY = "modele"


def default_model(conn: sqlite3.Connection) -> str:
    """The model chosen last in the interface, else the shipped default (configuration,
    never code: P6)."""
    row = conn.execute("SELECT value FROM app_setting WHERE key = ?", (MODEL_KEY,)).fetchone()
    return json.loads(row[0]) if row else assembly.settings().default_model


def set_default_model(conn: sqlite3.Connection, model: str) -> None:
    with conn:
        conn.execute(
            "INSERT INTO app_setting (key, value) VALUES (?, ?)"
            " ON CONFLICT (key) DO UPDATE SET value = excluded.value",
            (MODEL_KEY, json.dumps(model)),
        )
