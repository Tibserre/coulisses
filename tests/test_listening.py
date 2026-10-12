"""The mix heard on the session's page (ADR 0037): the microphone turned down while
nobody speaks into it, and while only the computer speaks; never a word cut; the engine's
mix untouched. Synthetic sound only: tones for speech, short bursts for keystrokes."""

from __future__ import annotations

import json
import time
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf
from numpy.typing import NDArray

from coulisses_app import listening, mixing
from coulisses_app.paths import DataDir

from .test_system_audio import recorded

RATE = 48_000
FRAME = round(RATE * listening.FRAME_S)


def silence(seconds: float) -> NDArray[np.float32]:
    return np.zeros(round(seconds * RATE), dtype=np.float32)


def voice(seconds: float, amplitude: float = 0.2) -> NDArray[np.float32]:
    """A held tone: as long as a word or a sentence."""
    t = np.arange(round(seconds * RATE)) / RATE
    return (amplitude * np.sin(2 * np.pi * 220 * t)).astype(np.float32)


def typing(seconds: float, amplitude: float = 0.3) -> NDArray[np.float32]:
    """Keystrokes: 15 ms bursts every 180 ms."""
    sound = silence(seconds)
    rng = np.random.default_rng(7)
    burst = round(0.015 * RATE)
    for start in range(0, len(sound) - burst, round(0.18 * RATE)):
        sound[start : start + burst] = amplitude * rng.uniform(-1, 1, burst)
    return sound


def at(gains: NDArray[np.float64], second: float) -> float:
    return float(20 * np.log10(gains[round(second / listening.FRAME_S)]))


def test_a_keystroke_is_not_speech_a_held_sound_is() -> None:
    sound = np.concatenate([typing(2.0), silence(0.5), voice(1.0), silence(1.0)])
    speaking = listening.speaking(listening.frame_db(sound, FRAME))
    assert not speaking[round(1.0 / listening.FRAME_S)]  # among the keys
    assert speaking[round(3.0 / listening.FRAME_S)]  # in the voice
    # Up before the voice starts (2,5 s), held after it ends (3,5 s).
    assert speaking[round((2.5 - listening.LEAD_S + 0.02) / listening.FRAME_S)]
    assert speaking[round((3.5 + listening.HOLD_S - 0.05) / listening.FRAME_S)]
    assert not speaking[round(4.3 / listening.FRAME_S)]


def test_the_microphone_is_down_while_nobody_speaks_into_it() -> None:
    mic = np.concatenate([typing(2.0), typing(2.0), voice(1.0), silence(1.0)])
    computer = np.concatenate([silence(2.0), voice(2.0), silence(2.0)])
    gains = listening.microphone_gains(
        listening.frame_db(mic, FRAME), listening.frame_db(computer, FRAME)
    )
    assert at(gains, 1.0) == pytest.approx(listening.QUIET_DB, abs=0.5)  # keys alone
    assert at(gains, 3.0) == pytest.approx(listening.DUCK_DB, abs=0.5)  # someone online
    assert at(gains, 4.5) == pytest.approx(0.0, abs=0.5)  # someone in the room
    assert at(gains, 5.8) == pytest.approx(listening.QUIET_DB, abs=0.5)
    # Soft changes: the 15 dB of a change are spread over several frames, never one jump.
    steps = np.abs(np.diff(20 * np.log10(gains)))
    assert steps.max() < abs(listening.DUCK_DB) / 2


def test_a_silent_track_is_never_speech() -> None:
    assert not listening.speaking(listening.frame_db(silence(2.0), FRAME)).any()


def test_the_page_hears_the_listening_mix_the_engine_the_plain_one(data: DataDir) -> None:
    mic = np.concatenate([typing(2.0), voice(1.0)]).reshape(-1, 1)
    computer = np.concatenate([silence(2.0), silence(1.0)]).reshape(-1, 1)
    session_id = recorded(data, mic, computer)
    path = mixing.processing_path(data, session_id)
    folder = data.sources_dir(session_id)
    assert path == folder / mixing.MIX_FILE
    plain, _ = sf.read(str(folder / mixing.MIX_FILE), dtype="float64")
    heard, _ = sf.read(str(folder / mixing.LISTENING_FILE), dtype="float64")
    np.testing.assert_allclose(plain, (mic + computer)[:, 0], atol=2 / 2**23)  # untouched
    facts = mixing.read_facts(data, session_id)
    assert facts is not None and facts.listening_mix is not None
    keys = slice(round(0.5 * RATE), round(1.5 * RATE))
    speech = slice(round(2.3 * RATE), round(2.9 * RATE))
    lowered = np.max(np.abs(heard[keys])) / facts.listening_mix.gain
    kept = np.max(np.abs(heard[speech])) / facts.listening_mix.gain
    assert 20 * np.log10(lowered / np.max(np.abs(plain[keys]))) == pytest.approx(
        listening.QUIET_DB, abs=1.0
    )
    assert kept == pytest.approx(np.max(np.abs(plain[speech])), rel=0.02)
    assert len(heard) == len(plain)  # nothing moves in time
    assert mixing.listening_path(data, session_id) == folder / mixing.LISTENING_FILE


def test_a_mix_made_before_gets_its_listening_mix(data: DataDir) -> None:
    session_id = recorded(data, voice(0.5).reshape(-1, 1), voice(0.5).reshape(-1, 1))
    mixing.processing_path(data, session_id)
    folder = data.sources_dir(session_id)
    engine_input = (folder / mixing.MIX_FILE).read_bytes()
    # As a mix made before ADR 0037: no listening mix.
    facts = json.loads((folder / mixing.MIX_FACTS).read_text(encoding="utf-8"))
    del facts["listening_mix"]
    (folder / mixing.MIX_FACTS).write_text(json.dumps(facts), encoding="utf-8")
    (folder / mixing.LISTENING_FILE).unlink()
    assert mixing.listening_path(data, session_id) == folder / mixing.MIX_FILE  # meanwhile
    deadline = time.monotonic() + 10
    while not Path(folder / mixing.LISTENING_FILE).is_file():
        assert time.monotonic() < deadline, "the listening mix was not made"
        time.sleep(0.05)
    while mixing.busy(session_id):
        time.sleep(0.05)
    assert mixing.listening_path(data, session_id) == folder / mixing.LISTENING_FILE
    # What the engine heard is untouched, byte for byte.
    assert (folder / mixing.MIX_FILE).read_bytes() == engine_input
