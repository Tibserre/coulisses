"""What reminds the user that a recording runs (ADR 0054): a long silence, a long recording,
a main microphone that fails.

The service decides; the app in the Dock shows each alert once, as a macOS notification
with « Arrêter » and « Continuer », and the menu bar says the recording runs. Nothing ever
stops a recording by itself (the user's choice): an alert only asks.
"""

from __future__ import annotations

import json
import logging
import sqlite3

from pydantic import BaseModel, Field, ValidationError

log = logging.getLogger(__name__)

SETTING_KEY = "rappels_enregistrement"

SILENCE_STEPS_MIN = (2, 3, 5, 10, 15, 20, 30)
DURATION_STEPS_MIN = (30, 45, 60, 90, 120, 180, 240)


class Reminders(BaseModel):
    """After how long the user is asked whether the meeting is over."""

    silence_min: int = Field(default=5, gt=0)
    """Nobody heard for this long (pauses left out)."""
    duration_min: int = Field(default=90, gt=0)
    """Recorded this long, then again at each multiple."""


class RecordingAlert(BaseModel):
    """An alert ready to show, in French. `key` stays the same for one alert and changes
    for the next: the app in the Dock notifies once per (session, key)."""

    key: str
    title: str
    text: str


def get(conn: sqlite3.Connection) -> Reminders:
    """The values kept; raises `ValueError` if they cannot be read (said in the Réglages)."""
    row = conn.execute("SELECT value FROM app_setting WHERE key = ?", (SETTING_KEY,)).fetchone()
    if row is None:
        return Reminders()
    try:
        return Reminders.model_validate(json.loads(row[0]))
    except (ValueError, ValidationError) as exc:
        raise ValueError(f"Les rappels d'enregistrement n'ont pas pu être lus : {exc}") from exc


def for_recording(conn: sqlite3.Connection) -> Reminders:
    """The values a recording follows: never a recording refused for its reminders. Values
    that cannot be read are logged, the usual ones are followed, and the Réglages say it."""
    try:
        return get(conn)
    except ValueError:
        log.exception("recording reminders")
        return Reminders()


def put(conn: sqlite3.Connection, reminders: Reminders) -> None:
    if reminders.silence_min not in SILENCE_STEPS_MIN:
        raise ValueError(f"Durée de silence non prévue : {reminders.silence_min} min.")
    if reminders.duration_min not in DURATION_STEPS_MIN:
        raise ValueError(f"Durée de rappel non prévue : {reminders.duration_min} min.")
    with conn:
        conn.execute(
            "INSERT INTO app_setting (key, value) VALUES (?, ?)"
            " ON CONFLICT (key) DO UPDATE SET value = excluded.value",
            (SETTING_KEY, reminders.model_dump_json()),
        )


def minutes(value: int) -> str:
    """« 5 min », « 1 h », « 1 h 30 »."""
    hours, rest = divmod(value, 60)
    if not hours:
        return f"{rest} min"
    return f"{hours} h {rest:02d}" if rest else f"{hours} h"


def alert_of(
    *,
    elapsed_s: float,
    silence_since_s: float,
    paused: bool,
    reminders: Reminders,
    error: str | None = None,
) -> RecordingAlert | None:
    """The alert to show now, if any. Times are recorded times (pauses left out):
    `silence_since_s` is where the last voice was heard.

    The main microphone's error comes first: it stops the time, so nothing else would ever
    remind. A silence comes before the duration (the likelier sign that the meeting is
    over), and asks again at each duration reached: one notification missed does not end
    the reminders."""
    if error is not None:
        return RecordingAlert(
            key=f"error-{int(elapsed_s)}",
            title="L'enregistrement a un problème",
            text=f"{error} Ouvrez Coulisses pour voir ce qui se passe.",
        )
    if paused:
        return None
    period = reminders.duration_min * 60
    reached = int(elapsed_s // period) * period
    silent = elapsed_s - silence_since_s
    if silent >= reminders.silence_min * 60:
        said = max(reminders.silence_min, int(silent // 60))
        return RecordingAlert(
            key=f"silence-{int(silence_since_s)}-{reached}",
            title=f"Personne ne parle depuis {minutes(said)}",
            text="La réunion est finie ? L'enregistrement continue tant que vous ne l'arrêtez pas.",
        )
    if reached:
        return RecordingAlert(
            key=f"duration-{reached}",
            title=f"Coulisses enregistre depuis {minutes(reached // 60)}",
            text="Pensez à l'arrêter si la réunion est finie.",
        )
    return None
