"""The computer's sound, recorded with the microphone (ADR 0032): two files on one clock,
the mix the engine hears, the program that taps it. No real device, no real tap: the
stream is a fake, the program a small script speaking its protocol."""

from __future__ import annotations

import json
import stat
import sys
import textwrap
import time
from collections.abc import Callable
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf
from numpy.typing import NDArray

from coulisses_app import capture, jobs, mixing, retention, sessions, system_audio, wav
from coulisses_app.api import create_app
from coulisses_app.paths import DataDir
from coulisses_app.processing import Processor
from coulisses_app.storage.db import connect

from .conftest import FAKE_CHAIN, local_client
from .test_capture import MIC, PHONE, Clock, CountingAwake, FakeMic, tone, wait_for


class FakeTap(FakeMic):
    """The microphone and the computer's sound as one stream, as the program gives them."""

    def __init__(self) -> None:
        super().__init__()
        self.microphone: str | None = None
        self.attempts = 0
        self.failure: Exception | None = None

    def system_factory(
        self, microphone: str, _channels: int, on_block: Callable[[NDArray[np.float32], bool], None]
    ) -> FakeTap:
        self.microphone = microphone
        self.attempts += 1
        self.on_block = on_block
        return self

    def start(self) -> None:
        if self.failure is not None:
            raise self.failure
        super().start()


def both(mic: NDArray[np.float32], system: NDArray[np.float32]) -> NDArray[np.float32]:
    return np.concatenate([mic, system], axis=1)


def system_recorder(
    data: DataDir, tap: FakeTap, awake: CountingAwake, clock: Clock, phone: FakeMic | None = None
) -> capture.Recorder:
    return capture.Recorder(
        data,
        stream_factory=(phone.factory if phone else FakeMic().factory),
        system_stream_factory=tap.system_factory,
        devices=lambda: [MIC, PHONE],
        keep_awake=awake,
        battery=lambda: True,  # nothing queued: the test looks at the files
        clock=clock,
        retry_wait_s=0.0,
    )


@pytest.fixture
def awake() -> CountingAwake:
    return CountingAwake()


@pytest.fixture
def clock() -> Clock:
    return Clock()


def start_online(rec: capture.Recorder, *, phone: bool = False) -> capture.RecordingState:
    return rec.start(
        space_id=None,
        attendee_ids=[],
        unnamed_attendees=None,
        device_index=MIC.index,
        extra_device_indexes=[PHONE.index] if phone else [],
        system=True,
    )


def read(path: Path) -> NDArray[np.float64]:
    samples, _ = sf.read(str(path), always_2d=True, dtype="float64")
    return np.asarray(samples, dtype=np.float64)


def test_the_computers_sound_is_its_own_file_on_the_same_clock(
    data: DataDir, awake: CountingAwake, clock: Clock
) -> None:
    tap = FakeTap()
    rec = system_recorder(data, tap, awake, clock)
    state = start_online(rec)
    assert tap.microphone == MIC.name
    assert state.system is not None and state.system.device == "Son de l'ordinateur"
    assert state.extra == []
    session_id = state.session_id
    tap.push(both(tone(1.0, 0.3), tone(1.0, 0.1)))
    rec.pause()
    tap.push(both(tone(0.5, 0.3), tone(0.5, 0.1)))  # heard while paused: on neither file
    rec.resume()
    tap.push(both(tone(1.0, 0.3), np.zeros((48_000, 1), np.float32)))
    wait_for(lambda: rec.state() is not None and rec.state().elapsed_s >= 2.0)  # type: ignore[union-attr]
    result = rec.stop(profile="essai")
    assert result.duration_s == pytest.approx(2.0) and result.second_problem is None

    folder = data.sources_dir(session_id)
    ref, system = read(folder / "ref.wav"), read(folder / "system.wav")
    assert ref.shape == system.shape == (2 * capture.SAMPLE_RATE, 1)
    assert np.max(np.abs(ref)) == pytest.approx(0.3, abs=1e-3)
    assert np.max(np.abs(system[:48_000])) == pytest.approx(0.1, abs=1e-3)
    assert np.max(np.abs(system[48_000:])) == 0  # silence is kept as silence
    [kept] = sessions.other_sources(data, session_id)
    assert (kept.source_id, kept.device, kept.capture_state) == (
        "system",
        "Son de l'ordinateur",
        "complete",
    )
    assert kept.duration_s == pytest.approx(2.0)
    assert awake.held == 0

    # The mix is made at once, in the background: the microphone plus the computer.
    wait_for(lambda: (folder / mixing.MIX_FACTS).is_file())
    mix = read(folder / mixing.MIX_FILE)
    assert mix.shape == ref.shape
    facts = json.loads((folder / mixing.MIX_FACTS).read_text(encoding="utf-8"))
    assert facts["gain"] == 1.0
    assert set(facts["made_from"]) == {"ref", "system"}
    np.testing.assert_allclose(mix, ref + system, atol=2 / 2**23)
    # On the page: the listening mix (ADR 0037); the engine keeps the plain sum above.
    assert mixing.listening_path(data, session_id) == folder / mixing.LISTENING_FILE


def test_the_computers_sound_never_cries_wolf_about_its_stream(
    data: DataDir, awake: CountingAwake, clock: Clock
) -> None:
    tap = FakeTap()
    rec = system_recorder(data, tap, awake, clock)
    start_online(rec)
    tap.push(both(tone(0.5, 0.3), np.zeros((24_000, 1), np.float32)))
    wait_for(lambda: rec.state() is not None and rec.state().elapsed_s >= 0.5)  # type: ignore[union-attr]
    clock.now += capture.LOW_AFTER_S + capture.SILENT_STREAM_S + 1
    state = rec.state()
    assert state is not None and state.system is not None
    # The stream stopped: the microphone says it, once; the computer's sound only says
    # it has been silent (normal when nobody speaks from afar).
    assert state.error is not None
    assert state.system.error is None and state.system.too_quiet
    rec.stop(profile="essai")


def test_the_computers_sound_and_the_iphone_together(
    data: DataDir, awake: CountingAwake, clock: Clock
) -> None:
    tap, phone = FakeTap(), FakeMic()
    rec = system_recorder(data, tap, awake, clock, phone=phone)
    state = start_online(rec, phone=True)
    assert state.system is not None and len(state.extra) == 1
    tap.push(both(tone(1.0, 0.3), tone(1.0, 0.1)))
    phone.push(tone(1.0, 0.2))
    wait_for(lambda: rec.state() is not None and rec.state().elapsed_s >= 1.0)  # type: ignore[union-attr]
    session_id = state.session_id
    rec.stop(profile="essai")
    assert sorted(s.source_id for s in sessions.other_sources(data, session_id)) == [
        "mic2",
        "system",
    ]
    assert read(data.sources_dir(session_id) / "mic2.wav").shape == (48_000, 1)


def test_a_tap_that_will_not_start_leaves_nothing_and_says_why(
    data: DataDir, awake: CountingAwake, clock: Clock
) -> None:
    tap = FakeTap()
    tap.failure = system_audio.SystemAudioError("macOS a refusé de donner le son.")
    rec = system_recorder(data, tap, awake, clock)
    with pytest.raises(capture.RecordingError, match="macOS a refusé"):
        start_online(rec)
    assert tap.attempts == 1  # a permission does not come by trying again
    assert sessions.list_sessions(data) == []

    # Without the compiler, trying again would not help: said at once.
    tap.failure = system_audio.UnavailableError("outils de développement d'Apple")
    tap.attempts = 0
    with pytest.raises(capture.RecordingError, match="outils de développement"):
        start_online(rec)
    assert tap.attempts == 1
    assert sessions.list_sessions(data) == []


# -- the mix -------------------------------------------------------------------------------


def recorded(data: DataDir, mic: NDArray[np.float32], system: NDArray[np.float32] | None) -> str:
    """A session recorded online, made directly: its files and its sources."""
    session_id, path = sessions.start_capture(
        data,
        space_id=None,
        attendee_ids=[],
        unnamed_attendees=None,
        device=MIC.name,
        sample_rate=capture.SAMPLE_RATE,
        channels=mic.shape[1],
        system=system is not None,
    )
    for source_id, sound in (("ref", mic), ("system", system)):
        if sound is None:
            continue
        writer = wav.WavWriter(
            path.with_name(f"{source_id}.wav"), capture.SAMPLE_RATE, sound.shape[1]
        )
        writer.write(sound)
        writer.close()
        sessions.finish_capture(data, session_id, frames=len(sound), source_id=source_id)
    return session_id


def test_the_mix_is_turned_down_never_to_saturate(data: DataDir) -> None:
    loud = np.full((4800, 1), 0.8, np.float32)
    session_id = recorded(data, loud, loud)
    path = mixing.processing_path(data, session_id)
    assert path is not None and path == data.sources_dir(session_id) / mixing.MIX_FILE
    mix = read(path)
    assert np.max(np.abs(mix)) == pytest.approx(mixing.CEILING, abs=1e-5)
    facts = json.loads((path.with_name(mixing.MIX_FACTS)).read_text(encoding="utf-8"))
    assert facts["gain"] == pytest.approx(mixing.CEILING / 1.6, abs=1e-5)


def test_a_stereo_microphone_is_mixed_down_and_a_shorter_track_padded(data: DataDir) -> None:
    mic = np.stack([np.full(9600, 0.2, np.float32), np.full(9600, 0.4, np.float32)], axis=1)
    system = np.full((4800, 1), 0.1, np.float32)
    session_id = recorded(data, mic, system)
    mix = read(mixing.processing_path(data, session_id))  # type: ignore[arg-type]
    assert mix.shape == (9600, 1)
    assert mix[0, 0] == pytest.approx(0.4, abs=1e-5)  # (0.2 + 0.4) / 2 + 0.1
    assert mix[-1, 0] == pytest.approx(0.3, abs=1e-5)  # the computer's sound ended


def test_the_mix_is_made_again_when_its_sources_differ(data: DataDir) -> None:
    session_id = recorded(data, tone(0.2, 0.3), tone(0.2, 0.1))
    path = mixing.processing_path(data, session_id)
    assert path is not None
    made = path.stat().st_mtime_ns
    assert mixing.processing_path(data, session_id) == path
    assert path.stat().st_mtime_ns == made  # the same sources: kept
    conn = connect(data)
    with conn:
        conn.execute(
            "UPDATE audio_source SET sha256 = 'autre' WHERE session_id = ? AND source_id = ?",
            (session_id, "system"),
        )
    conn.close()
    mixing.processing_path(data, session_id)
    facts = json.loads(path.with_name(mixing.MIX_FACTS).read_text(encoding="utf-8"))
    assert facts["made_from"]["system"] == "autre"


def test_without_the_computers_sound_the_reference_is_processed(data: DataDir) -> None:
    alone = recorded(data, tone(0.2, 0.3), None)
    assert mixing.processing_path(data, alone) == data.sources_dir(alone) / "ref.wav"
    # Recorded empty (the tap stopped at once): the microphone alone, said on the page.
    empty = recorded(data, tone(0.2, 0.3), np.zeros((0, 1), np.float32))
    assert mixing.processing_path(data, empty) == data.sources_dir(empty) / "ref.wav"


def test_a_missing_computers_sound_is_said_never_skipped(data: DataDir) -> None:
    session_id = recorded(data, tone(0.2, 0.3), tone(0.2, 0.1))
    (data.sources_dir(session_id) / "system.wav").unlink()
    with pytest.raises(mixing.MixError, match="personnes à distance"):
        mixing.processing_path(data, session_id)
    # Heard meanwhile: the microphone, never nothing.
    assert mixing.listening_path(data, session_id) == data.sources_dir(session_id) / "ref.wav"


def test_files_cannot_go_while_the_mix_is_made(data: DataDir) -> None:
    session_id = recorded(data, tone(0.2, 0.3), tone(0.2, 0.1))
    lock = mixing._lock(session_id)  # pyright: ignore[reportPrivateUsage]
    with lock, pytest.raises(retention.DeletionError, match="en train d'être réunis"):
        retention.delete_session(data, session_id)
    retention.delete_session(data, session_id)
    assert not data.session_dir(session_id).exists()


# -- the program ---------------------------------------------------------------------------


def program(tmp_path: Path, body: str) -> Path:
    """A stand-in for the Swift program: same arguments, same protocol."""
    script = tmp_path / "son-ordinateur"
    script.write_text(f"#!{sys.executable}\n" + textwrap.dedent(body), encoding="utf-8")
    script.chmod(script.stat().st_mode | stat.S_IEXEC)
    return script


SPEAKING = """
    import json, struct, sys
    args = sys.argv[1:]
    channels = int(args[args.index("--canaux") + 1])
    say = lambda **e: (sys.stderr.write(json.dumps(e) + "\\n"), sys.stderr.flush())
    say(event="ready", rate=48000, channels=channels)
    frame = [0.25] * channels + [-0.5]
    samples = struct.pack("<" + "f" * (len(frame) * 1024), *(frame * 1024))
    sys.stdout.buffer.write(struct.pack("<II", 1024, 0) + samples)
    sys.stdout.buffer.write(struct.pack("<II", 1024, 12) + samples)  # 12 frames lost before
    sys.stdout.buffer.write(struct.pack("<II", 1024, 0) + samples[:100])  # cut short
    sys.stdout.buffer.flush()
    sys.stdin.read()  # until the service closes it
"""


def test_the_program_hands_over_blocks_and_stops_when_asked(tmp_path: Path) -> None:
    got: list[tuple[NDArray[np.float32], bool]] = []
    stream = system_audio.HelperStream(
        "Micro MacBook Pro",
        2,
        lambda block, lost: got.append((block, lost)),
        program=program(tmp_path, SPEAKING),
    )
    stream.start()
    deadline = time.monotonic() + 5
    while len(got) < 2:  # the third, cut short, comes when it stops
        assert time.monotonic() < deadline
        time.sleep(0.01)
    stream.stop()
    assert [b.shape for b, _ in got] == [(1024, 3), (1024, 3), (8, 3)]
    assert got[0][0][0].tolist() == [0.25, 0.25, -0.5]
    assert [lost for _, lost in got] == [False, True, False]


def test_the_program_refusing_is_said_in_french(tmp_path: Path) -> None:
    refusing = program(
        tmp_path,
        """
        import json, sys
        said = {"event": "error", "code": "frequence", "detail": "24000 Hz"}
        sys.stderr.write(json.dumps(said) + "\\n")
        sys.exit(1)
        """,
    )
    stream = system_audio.HelperStream("AirPods", 1, lambda *_: None, program=refusing)
    with pytest.raises(system_audio.SystemAudioError, match="« AirPods » ne peut pas enregistrer"):
        stream.start()


def test_a_program_silent_at_start_points_to_the_permission(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(system_audio, "READY_WITHIN_S", 0.5)
    silent = program(tmp_path, "import sys\nsys.stdin.read()\n")
    stream = system_audio.HelperStream("Micro MacBook Pro", 1, lambda *_: None, program=silent)
    with pytest.raises(system_audio.SystemAudioError, match="Enregistrement de l'écran"):
        stream.start()


# -- what follows the recording ---------------------------------------------------------


def test_a_computers_sound_silent_all_along_is_said_after_the_stop(
    data: DataDir, awake: CountingAwake, clock: Clock
) -> None:
    tap = FakeTap()
    rec = system_recorder(data, tap, awake, clock)
    session_id = start_online(rec).session_id
    tap.push(both(tone(1.0, 0.3), np.zeros((48_000, 1), np.float32)))  # no permission
    wait_for(lambda: rec.state() is not None and rec.state().elapsed_s >= 1.0)  # type: ignore[union-attr]
    result = rec.stop(profile="essai")
    assert result.second_problem is not None and "resté muet" in result.second_problem
    wait_for(lambda: mixing.read_facts(data, session_id) is not None)
    facts = mixing.read_facts(data, session_id)
    assert facts is not None and facts.system_silent


def test_the_engine_hears_the_mix_and_the_job_keeps_what_it_was(data: DataDir) -> None:
    session_id = recorded(data, tone(1.0, 0.3), tone(1.0, 0.1))
    sessions.start_processing(data, session_id, profile="essai")
    conn = connect(data)
    job = jobs.claim_next(conn)
    conn.close()
    assert job is not None
    result = Processor(data, FAKE_CHAIN).run_job(job)
    assert result.error is None
    conn = connect(data)
    done = jobs.latest_job(conn, session_id)
    rows = conn.execute("SELECT id FROM run WHERE session_id = ?", (session_id,)).fetchall()
    conn.close()
    assert done is not None and isinstance(done.params, jobs.ChainParams)
    facts = mixing.read_facts(data, session_id)
    assert facts is not None and done.params.mix == facts.model_dump()
    from coulisses.api import read_provenance

    heard = {
        source["path"]
        for row in rows
        if (prov := read_provenance(data.run_dir(session_id, row["id"]))) is not None
        for source in prov.inputs.get("sources", [])
    }
    assert heard == {str(data.sources_dir(session_id) / mixing.MIX_FILE)}

    # Once the audio is purged, what the mix was made of is still said, from the job.
    folder = data.sources_dir(session_id)
    assert (folder / mixing.LISTENING_FILE).is_file()
    retention.remove_audio(data, session_id, "audio_deletion")
    assert not (folder / mixing.MIX_FACTS).exists()
    assert not (folder / mixing.LISTENING_FILE).exists()  # the listening mix goes too
    conn = connect(data)
    logged = conn.execute(
        "SELECT detail FROM deletion_log WHERE session_id = ? ORDER BY id DESC", (session_id,)
    ).fetchone()["detail"]
    conn.close()
    assert mixing.LISTENING_FILE in logged and mixing.MIX_FILE in logged
    # Nothing is written back after the removal, whatever asks for the mix.
    with pytest.raises(mixing.MixError, match="supprimé"):
        mixing.processing_input(data, session_id)
    assert not (folder / mixing.LISTENING_FILE).exists()
    client = local_client(
        create_app(data, FAKE_CHAIN, profile="essai", processor=None, web_dir=None)
    )
    kept = client.get(f"/api/seances/{session_id}").json()["mix"]
    assert kept["sha256"] == facts.sha256 and kept["gain"] == facts.gain


def test_a_mix_that_cannot_be_made_fails_the_job_in_words(data: DataDir) -> None:
    session_id = recorded(data, tone(0.5, 0.3), tone(0.5, 0.1))
    (data.sources_dir(session_id) / "system.wav").unlink()
    sessions.start_processing(data, session_id, profile="essai")
    conn = connect(data)
    job = jobs.claim_next(conn)
    conn.close()
    assert job is not None
    result = Processor(data, FAKE_CHAIN).run_job(job)
    assert result.error is not None and "personnes à distance" in result.error


def test_the_service_records_online_and_plays_the_mix(
    data: DataDir, awake: CountingAwake, clock: Clock
) -> None:
    tap = FakeTap()
    rec = system_recorder(data, tap, awake, clock)
    client = local_client(
        create_app(data, FAKE_CHAIN, profile="essai", processor=None, web_dir=None, recorder=rec)
    )
    started = client.post("/api/enregistrement", json={"micro": MIC.index, "son_ordinateur": True})
    assert started.status_code == 201, started.text
    assert started.json()["system"]["device"] == "Son de l'ordinateur"
    session_id = started.json()["session_id"]
    tap.push(both(tone(0.5, 0.3), tone(0.5, 0.1)))
    wait_for(lambda: client.get("/api/enregistrement").json()["elapsed_s"] >= 0.5)
    assert client.post("/api/enregistrement/arret").status_code == 200
    wait_for(lambda: client.get(f"/api/seances/{session_id}").json()["mix"] is not None)
    detail = client.get(f"/api/seances/{session_id}").json()
    assert detail["mix"]["system_silent"] is False
    played = client.get(f"/api/seances/{session_id}/audio")
    assert played.status_code == 200
    assert played.content == (data.sources_dir(session_id) / mixing.LISTENING_FILE).read_bytes()


def test_an_interrupted_computers_sound_is_repaired_and_said(
    data: DataDir, awake: CountingAwake, clock: Clock
) -> None:
    tap = FakeTap()
    rec = system_recorder(data, tap, awake, clock)
    session_id = start_online(rec).session_id
    tap.push(both(tone(1.0, 0.3), tone(1.0, 0.1)))
    wait_for(lambda: rec.state() is not None and rec.state().elapsed_s >= 1.0)  # type: ignore[union-attr]
    # The service dies here: both tracks still « recording ».
    for track in rec._current.tracks:  # type: ignore[union-attr]  # pyright: ignore[reportPrivateUsage, reportOptionalMemberAccess]
        track.writer._sync()  # pyright: ignore[reportPrivateUsage]
    told = capture.recover_interrupted(data)
    assert any("Son de l'ordinateur" in t for t in told)
    [system] = sessions.other_sources(data, session_id)
    assert system.capture_state == "recovered" and system.duration_s == pytest.approx(1.0)


FLUSHING = """
    import struct, sys
    args = sys.argv[1:]
    channels = int(args[args.index("--canaux") + 1])
    sys.stderr.write('{"event": "ready"}\\n'); sys.stderr.flush()
    block = struct.pack("<II", 512, 0) + b"\\0" * (512 * (channels + 1) * 4)
    for _ in range(200):
        sys.stdout.buffer.write(block)
    sys.stdout.buffer.flush()
    sys.stdin.read()
    for _ in range(200):  # what it heard before stopping, written as it stops
        sys.stdout.buffer.write(block)
    sys.stdout.buffer.flush()
"""


def test_stopping_waits_for_every_block_the_program_wrote(tmp_path: Path) -> None:
    got: list[int] = []

    def slow(block: NDArray[np.float32], _lost: bool) -> None:
        time.sleep(0.002)  # a reader behind the program
        got.append(len(block))

    stream = system_audio.HelperStream(
        "Micro MacBook Pro", 1, slow, program=program(tmp_path, FLUSHING)
    )
    stream.start()
    stream.stop()
    assert sum(got) == 400 * 512
