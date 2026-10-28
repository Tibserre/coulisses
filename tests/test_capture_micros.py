"""The microphones while recording: cut one, or all, and bring them back; add one on the way.
Silence is written in their place, on the reference's clock
(P2): every file keeps the recording's length."""

from __future__ import annotations

import time
from pathlib import Path

import numpy as np
import pytest
from numpy.typing import NDArray

from coulisses_app import capture, sessions, wav
from coulisses_app.paths import DataDir

from . import wav_reader
from .test_capture import (
    MIC,
    PHONE,
    Clock,
    CountingAwake,
    TwoMics,
    start_both,
    tone,
    two_recorder,
    wait_for,
)

SECOND = capture.SAMPLE_RATE


@pytest.fixture
def awake() -> CountingAwake:
    return CountingAwake()


@pytest.fixture
def clock() -> Clock:
    return Clock()


def read(path: Path) -> NDArray[np.float64]:
    return wav_reader.read(path, always_2d=True)


def elapsed(rec: capture.Recorder, at_least: float) -> None:
    wait_for(lambda: (s := rec.state()) is not None and s.elapsed_s >= at_least)


def start_mac(rec: capture.Recorder, **kwargs: object) -> capture.RecordingState:
    return rec.start(
        space_id=None,
        attendee_ids=[],
        unnamed_attendees=2,
        device_index=MIC.index,
        **kwargs,  # type: ignore[arg-type]
    )


def test_a_microphone_cut_keeps_its_length_and_says_when(
    data: DataDir, awake: CountingAwake, clock: Clock
) -> None:
    mics = TwoMics()
    rec = two_recorder(data, mics, awake, clock)
    session_id = start_both(rec).session_id
    mics.mac.push(tone(1.0, 0.3))
    mics.phone.push(tone(1.0, 0.2))
    elapsed(rec, 1.0)
    cut = rec.mute("mic2", True)
    assert cut.extra[0].muted and cut.extra[0].cuts == [capture.Cut(from_s=1.0)]
    assert rec.mute("mic2", True).extra[0].cuts == [capture.Cut(from_s=1.0)]  # twice is once
    mics.mac.push(tone(1.0, 0.3))
    mics.phone.push(tone(1.0, 0.2))
    elapsed(rec, 2.0)
    back = rec.mute("mic2", False)
    assert not back.extra[0].muted
    assert back.extra[0].cuts == [capture.Cut(from_s=1.0, to_s=2.0)]
    mics.mac.push(tone(1.0, 0.3))
    mics.phone.push(tone(1.0, 0.2))
    elapsed(rec, 3.0)
    with pytest.raises(capture.RecordingError, match="pas dans l'enregistrement"):
        rec.mute("mic9", True)
    rec.stop(profile="essai")

    phone = read(data.sources_dir(session_id) / "mic2.wav")
    assert phone.shape == (3 * SECOND, 1)  # the same clock
    assert np.max(np.abs(phone[SECOND : 2 * SECOND])) == 0.0
    assert np.max(np.abs(phone[2 * SECOND :])) == pytest.approx(0.2, abs=1e-3)
    mac = read(data.sources_dir(session_id) / "ref.wav")
    assert np.max(np.abs(mac[SECOND : 2 * SECOND])) == pytest.approx(0.3, abs=1e-3)


def test_all_the_microphones_cut_at_once_the_main_one_too(
    data: DataDir, awake: CountingAwake, clock: Clock
) -> None:
    mics = TwoMics()
    rec = two_recorder(data, mics, awake, clock)
    session_id = start_both(rec).session_id
    state = rec.mute_microphones(True)
    assert state.muted and state.extra[0].muted and state.source_id == "ref"
    mics.mac.push(tone(1.0, 0.3))
    mics.phone.push(tone(1.0, 0.2))
    elapsed(rec, 1.0)
    clock.now += capture.LOW_AFTER_S + 1
    assert rec.state().too_quiet is False  # type: ignore[union-attr]  # cut, not too quiet
    state = rec.mute_microphones(False)
    assert state.cuts == [capture.Cut(from_s=0.0, to_s=1.0)] and not state.muted
    mics.mac.push(tone(1.0, 0.3))
    mics.phone.push(tone(1.0, 0.2))
    elapsed(rec, 2.0)
    rec.stop(profile="essai")
    for name in ("ref.wav", "mic2.wav"):
        sound = read(data.sources_dir(session_id) / name)
        assert sound.shape == (2 * SECOND, 1)
        assert np.max(np.abs(sound[:SECOND])) == 0.0 and np.max(np.abs(sound[SECOND:])) > 0.1


def test_a_microphone_added_on_the_way_starts_with_silence_on_the_same_clock(
    data: DataDir, awake: CountingAwake, clock: Clock
) -> None:
    mics = TwoMics()
    rec = two_recorder(data, mics, awake, clock)
    session_id = start_mac(rec).session_id
    mics.mac.push(tone(1.0, 0.3))
    elapsed(rec, 1.0)
    state = rec.add_microphone(PHONE.index)
    assert [(t.source_id, t.device) for t in state.extra] == [("mic2", PHONE.name)]
    with pytest.raises(capture.RecordingError, match="déjà"):
        rec.add_microphone(PHONE.index)
    with pytest.raises(capture.RecordingError, match="plus là"):
        rec.add_microphone(99)
    mics.phone.push(tone(1.0, 0.2))
    mics.mac.push(tone(1.0, 0.3))
    elapsed(rec, 2.0)
    rec.stop(profile="essai")

    [phone] = sessions.other_sources(data, session_id)
    assert (phone.source_id, phone.capture_state) == ("mic2", "complete")
    assert phone.duration_s == pytest.approx(2.0)
    sound = read(data.sources_dir(session_id) / "mic2.wav")
    assert np.max(np.abs(sound[:SECOND])) == 0.0  # before it was added
    assert np.max(np.abs(sound[SECOND:])) == pytest.approx(0.2, abs=1e-3)


def test_a_microphone_that_will_not_open_on_the_way_changes_nothing(
    data: DataDir, awake: CountingAwake, clock: Clock
) -> None:
    mics = TwoMics()
    rec = two_recorder(data, mics, awake, clock)
    session_id = start_mac(rec).session_id
    mics.phone.refuse_start = True
    with pytest.raises(capture.RecordingError, match="n'a pas pu s'ouvrir"):
        rec.add_microphone(PHONE.index)
    assert rec.state().extra == []  # type: ignore[union-attr]
    mics.mac.push(tone(1.0, 0.3))
    elapsed(rec, 1.0)
    rec.stop(profile="essai")
    assert sessions.other_sources(data, session_id) == []


def test_the_service_cuts_and_adds(data: DataDir, awake: CountingAwake, clock: Clock) -> None:
    from coulisses_app.api import create_app

    from .conftest import FAKE_CHAIN, local_client

    mics = TwoMics()
    rec = two_recorder(data, mics, awake, clock)
    client = local_client(
        create_app(data, FAKE_CHAIN, profile="essai", processor=None, web_dir=None, recorder=rec)
    )
    started = client.post("/api/enregistrement", json={"micro": MIC.index})
    assert started.status_code == 201, started.text
    added = client.post("/api/enregistrement/micros", json={"micro": PHONE.index})
    assert added.status_code == 200, added.text
    assert added.json()["extra"][0]["source_id"] == "mic2"
    assert client.post("/api/enregistrement/micros", json={"micro": PHONE.index}).status_code == 422
    one = client.post("/api/enregistrement/pistes/mic2/coupe", json={"coupe": True}).json()
    assert one["extra"][0]["muted"] and not one["muted"]
    every = client.post("/api/enregistrement/micros/coupe", json={"coupe": True}).json()
    assert every["muted"] and every["extra"][0]["muted"]
    unknown = client.post("/api/enregistrement/pistes/autre/coupe", json={"coupe": True})
    assert unknown.status_code == 422
    assert client.post("/api/enregistrement/arret").status_code == 200


def test_a_microphone_added_while_paused_waits_for_the_time_recorded(
    data: DataDir, awake: CountingAwake, clock: Clock
) -> None:
    mics = TwoMics()
    rec = two_recorder(data, mics, awake, clock)
    session_id = start_mac(rec).session_id
    mics.mac.push(tone(1.0, 0.3))
    elapsed(rec, 1.0)
    rec.pause()
    rec.add_microphone(PHONE.index)
    mics.phone.push(tone(0.5, 0.2))  # heard while paused: written nowhere
    mics.mac.push(tone(0.5, 0.3))
    rec.resume()
    mics.phone.push(tone(1.0, 0.2))
    mics.mac.push(tone(1.0, 0.3))
    elapsed(rec, 2.0)
    rec.stop(profile="essai")
    sound = read(data.sources_dir(session_id) / "mic2.wav")
    assert sound.shape == (2 * SECOND, 1)
    assert np.max(np.abs(sound[:SECOND])) == 0.0
    assert np.max(np.abs(sound[SECOND:])) == pytest.approx(0.2, abs=1e-3)


def test_a_microphone_added_then_silent_until_the_stop_still_says_when_it_came(
    data: DataDir, awake: CountingAwake, clock: Clock
) -> None:
    mics = TwoMics()
    rec = two_recorder(data, mics, awake, clock)
    session_id = start_mac(rec).session_id
    mics.mac.push(tone(1.0, 0.3))
    elapsed(rec, 1.0)
    rec.pause()
    rec.add_microphone(PHONE.index)
    mics.phone.push(tone(0.5, 0.2))  # paused until the stop
    time.sleep(0.1)
    rec.stop(profile="essai")
    [phone] = sessions.other_sources(data, session_id)
    assert phone.duration_s == pytest.approx(1.0)  # silence up to when it came


def test_a_file_that_cannot_be_made_for_a_microphone_added_is_said_and_tried_again(
    data: DataDir, awake: CountingAwake, clock: Clock, monkeypatch: pytest.MonkeyPatch
) -> None:
    mics = TwoMics()
    rec = two_recorder(data, mics, awake, clock)
    session_id = start_mac(rec).session_id
    real = wav.WavWriter

    def refused(path: Path, *args: object, **kwargs: object) -> wav.WavWriter:
        if path.name == "mic2.wav":
            raise OSError("disque plein")
        return real(path, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(wav, "WavWriter", refused)
    with pytest.raises(capture.RecordingError, match=r"disque plein.*continue sans lui"):
        rec.add_microphone(PHONE.index)
    state = rec.add_microphone(PHONE.index)  # tried again: the next one, nothing written over
    assert [t.source_id for t in state.extra] == ["mic3"]
    mics.mac.push(tone(1.0, 0.3))
    mics.phone.push(tone(1.0, 0.2))
    elapsed(rec, 1.0)
    rec.stop(profile="essai")
    assert {s.source_id for s in sessions.other_sources(data, session_id)} >= {"mic3"}
