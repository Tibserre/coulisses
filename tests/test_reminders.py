"""What reminds the user that a recording runs (ADR 0054): never a stop, only a question."""

from __future__ import annotations

import pytest

from coulisses_app import reminders
from coulisses_app.paths import DataDir
from coulisses_app.storage.db import connect

R = reminders.Reminders(silence_min=5, duration_min=90)


def alert(elapsed: float, since: float, *, paused: bool = False) -> reminders.RecordingAlert | None:
    return reminders.alert_of(elapsed_s=elapsed, silence_since_s=since, paused=paused, reminders=R)


def test_nothing_while_people_speak_and_before_the_first_reminder() -> None:
    assert alert(600, 590) is None


def test_a_long_silence_asks_once_per_episode() -> None:
    first = alert(1000, 690)
    assert first is not None and first.key == "silence-690-0"
    assert first.title == "Personne ne parle depuis 5 min"
    # The same silence, later: the same key, notified once by the app in the Dock.
    assert alert(1200, 690).key == "silence-690-0"  # type: ignore[union-attr]
    # Someone spoke, then a new silence: a new key.
    assert alert(1600, 1290).key == "silence-1290-0"  # type: ignore[union-attr]


def test_a_silence_asks_again_at_each_duration_reached() -> None:
    # One notification missed must not end the reminders: the forgotten recording.
    later = alert(90 * 60 + 5, 600)
    assert later is not None and later.key == "silence-600-5400"
    assert later.title == "Personne ne parle depuis 1 h 20"


def test_the_main_microphones_error_comes_first() -> None:
    failed = reminders.alert_of(
        elapsed_s=300, silence_since_s=0, paused=True, reminders=R, error="Le micro a lâché."
    )
    assert failed is not None and failed.key == "error-300"
    assert failed.text.startswith("Le micro a lâché.")


def test_the_duration_reminds_at_each_multiple() -> None:
    at_90 = alert(90 * 60 + 5, 90 * 60)
    assert at_90 is not None and at_90.key == "duration-5400"
    assert at_90.title == "Coulisses enregistre depuis 1 h 30"
    assert alert(3 * 3600 + 5, 3 * 3600).key == "duration-10800"  # type: ignore[union-attr]
    assert alert(3 * 3600 + 5, 3 * 3600).title.endswith("3 h")  # type: ignore[union-attr]


def test_a_silence_comes_first_and_a_pause_asks_nothing() -> None:
    both = alert(100 * 60, 90 * 60)
    assert both is not None and both.key.startswith("silence-")
    assert alert(100 * 60, 90 * 60, paused=True) is None


def test_the_settings_keep_the_usual_values_only(data: DataDir) -> None:
    conn = connect(data)
    try:
        assert reminders.get(conn) == reminders.Reminders()
        reminders.put(conn, reminders.Reminders(silence_min=10, duration_min=60))
        assert reminders.get(conn) == reminders.Reminders(silence_min=10, duration_min=60)
        with pytest.raises(ValueError, match="silence"):
            reminders.put(conn, reminders.Reminders(silence_min=7))
    finally:
        conn.close()
