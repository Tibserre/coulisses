"""The measured envelope of the sound a session's page plays (ADR 0092): peaks read from the
listening file, never made from the turns' times (P2); kept beside the session, it outlives
the purge of the audio."""

from __future__ import annotations

import numpy as np
import pytest
from fastapi.testclient import TestClient

from coulisses_app import lossless, retention, waveform
from coulisses_app.api import create_app
from coulisses_app.paths import DataDir

from .conftest import FAKE_CHAIN, local_client
from .test_capture import Clock, CountingAwake, FakeMic, recorder, start, tone, wait_for
from .test_system_audio import recorded

pytestmark = pytest.mark.skipif(lossless.available() is not None, reason="ffmpeg requis")


@pytest.fixture
def client(data: DataDir) -> TestClient:
    return local_client(create_app(data, FAKE_CHAIN, profile="essai", processor=None, web_dir=None))


def envelope(client: TestClient, session_id: str, bars: int) -> dict:
    """Asked until it is made: 409 while it is measured, in the background."""
    url = f"/api/seances/{session_id}/onde?barres={bars}"
    answers: list = []
    wait_for(lambda: answers.append(client.get(url)) or answers[-1].status_code != 409)
    assert answers[0].status_code == 409  # never measured while the page asked for it
    assert answers[-1].status_code == 200, answers[-1].text
    return answers[-1].json()


def test_the_envelope_is_measured_on_the_sound_played(client: TestClient, data: DataDir) -> None:
    sound = np.concatenate([tone(1.0, 0.5), np.zeros((48_000, 1), dtype=np.float32)])
    session_id = recorded(data, sound, None)

    made = envelope(client, session_id, 4)

    assert made["duration_s"] == pytest.approx(2.0, abs=0.01)
    assert made["heard_version"] == client.get(f"/api/seances/{session_id}").json()["heard_version"]
    loud, _, quiet, _ = made["levels_db"]
    assert loud == pytest.approx(20 * np.log10(0.5), abs=0.2)  # the tone's peak, measured
    assert quiet == -120.0  # silence: the floor


def test_it_outlives_the_purge_and_is_made_again_when_the_sound_is_replaced(
    client: TestClient, data: DataDir
) -> None:
    session_id = recorded(data, tone(1.0, 0.3), None)
    before = envelope(client, session_id, 10)

    lossless.convert_session(data, session_id)  # the sound played, put in an MP4
    after = envelope(client, session_id, 10)
    assert after["heard_version"] != before["heard_version"]
    assert after["levels_db"] == pytest.approx(before["levels_db"], abs=0.1)  # no loss

    retention.remove_audio(data, session_id, "audio_deletion")
    kept = client.get(f"/api/seances/{session_id}/onde?barres=10")
    assert kept.status_code == 200 and kept.json() == after


def test_more_bars_than_measured_gives_each_measure_once(client: TestClient, data: DataDir) -> None:
    session_id = recorded(data, tone(0.2, 0.3), None)
    made = envelope(client, session_id, 10_000)
    assert len(made["levels_db"]) == 4  # 0.2 s, one peak every 50 ms


def test_nothing_is_measured_while_it_records(data: DataDir) -> None:
    mic = FakeMic()
    rec = recorder(data, mic, CountingAwake(), Clock())
    client = local_client(
        create_app(data, FAKE_CHAIN, profile="essai", processor=None, web_dir=None, recorder=rec)
    )
    state = start(rec)
    mic.push(tone(0.5, 0.3))
    wait_for(lambda: (rec.state() or state).elapsed_s >= 0.5)
    assert client.get(f"/api/seances/{state.session_id}/onde?barres=10").status_code == 409
    rec.stop(profile="essai")


def test_a_session_without_sound_is_said(client: TestClient) -> None:
    assert client.get("/api/seances/inconnue/onde?barres=10").status_code == 404


def test_the_waveform_is_measured_before_the_audio_goes_even_unseen(
    client: TestClient, data: DataDir
) -> None:
    session_id = recorded(data, tone(1.0, 0.3), None)
    retention.remove_audio(data, session_id, "audio_deletion")  # never asked by the page
    kept = client.get(f"/api/seances/{session_id}/onde?barres=4")
    assert kept.status_code == 200, kept.text
    assert kept.json()["levels_db"][0] == pytest.approx(20 * np.log10(0.3), abs=0.2)


def test_a_failed_measure_is_said_and_not_tried_again_in_a_loop(
    client: TestClient, data: DataDir, monkeypatch: pytest.MonkeyPatch
) -> None:
    session_id = recorded(data, tone(1.0, 0.3), None)
    tried: list[object] = []

    def broken(path: object) -> tuple[float, list[float]]:
        tried.append(path)
        raise lossless.ConversionError("ffmpeg n'a pas pu relire ref.wav : illisible")

    monkeypatch.setattr(waveform, "measure", broken)
    url = f"/api/seances/{session_id}/onde?barres=4"
    answers: list = []
    wait_for(lambda: answers.append(client.get(url)) or answers[-1].status_code != 409)
    assert answers[-1].status_code == 404
    assert "journal du service" in answers[-1].json()["detail"]
    assert client.get(url).status_code == 404 and len(tried) == 1  # once for this sound


def test_without_its_sound_on_the_disk_nothing_is_measured(
    client: TestClient, data: DataDir
) -> None:
    session_id = recorded(data, tone(1.0, 0.3), None)
    (data.sources_dir(session_id) / "ref.wav").unlink()  # moved in the Finder
    missing = client.get(f"/api/seances/{session_id}/onde?barres=4")
    assert missing.status_code == 404 and "introuvable" in missing.json()["detail"]


def test_a_session_is_not_deleted_while_its_waveform_is_written(data: DataDir) -> None:
    session_id = recorded(data, tone(1.0, 0.3), None)
    with waveform._measuring_lock:
        waveform._measuring.add(session_id)
    try:
        with pytest.raises(retention.DeletionError, match="onde"):
            retention.delete_session(data, session_id)
    finally:
        with waveform._measuring_lock:
            waveform._measuring.discard(session_id)


def test_a_waveform_that_cannot_be_measured_before_the_purge_is_said_with_it(
    data: DataDir, monkeypatch: pytest.MonkeyPatch
) -> None:
    session_id = recorded(data, tone(1.0, 0.3), None)

    def broken(path: object) -> tuple[float, list[float]]:
        raise lossless.ConversionError("illisible")

    monkeypatch.setattr(waveform, "measure", broken)
    problems = retention.remove_audio(data, session_id, "audio_deletion")
    assert problems == ["l'onde du son n'a pas pu être mesurée avant la suppression (illisible)"]
    assert retention.audio_status(data, session_id).state == "removed"  # not held back


def test_a_failure_before_the_measure_leaves_the_session_free(
    client: TestClient, data: DataDir, monkeypatch: pytest.MonkeyPatch
) -> None:
    session_id = recorded(data, tone(1.0, 0.3), None)
    calls: list[str] = []
    real = waveform.heard_version

    def failing_in_the_background(data: DataDir, sid: str) -> str | None:
        calls.append(sid)
        if len(calls) == 2:  # the background's own look
            raise OSError("disque indisponible")
        return real(data, sid)

    monkeypatch.setattr(waveform, "heard_version", failing_in_the_background)
    assert client.get(f"/api/seances/{session_id}/onde?barres=4").status_code == 409
    wait_for(lambda: not waveform.busy(session_id))  # never left raised
