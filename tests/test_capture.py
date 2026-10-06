"""Recording in the application (spec §7.2, ADR 0005): the WAV kept true on disk, pause,
levels and alerts, stop, battery, repair after a crash. The microphone is a fake: blocks
of synthetic sound pushed by the test; no real device is opened."""

from __future__ import annotations

import time
from collections.abc import Callable
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf
from fastapi.testclient import TestClient
from numpy.typing import NDArray

from coulisses_app import capture, sessions, wav
from coulisses_app.api import create_app
from coulisses_app.paths import DataDir
from coulisses_app.storage.db import connect

from .conftest import FAKE_CHAIN

BLOCK = 4800  # 0.1 s at 48 kHz


def tone(seconds: float, amplitude: float, channels: int = 1) -> NDArray[np.float32]:
    t = np.arange(int(seconds * capture.SAMPLE_RATE)) / capture.SAMPLE_RATE
    wave = (amplitude * np.sin(2 * np.pi * 440 * t)).astype(np.float32)
    return np.repeat(wave[:, None], channels, axis=1)


class FakeMic:
    """Stands for the microphone: the test pushes blocks, the recorder receives them."""

    def __init__(self) -> None:
        self.on_block: Callable[[NDArray[np.float32], bool], None] | None = None
        self.started = False
        self.closed = False
        self.refuse_start = False
        self.refuse_stop = False

    def factory(
        self, _device: int, _channels: int, on_block: Callable[[NDArray[np.float32], bool], None]
    ) -> FakeMic:
        self.on_block = on_block
        return self

    def start(self) -> None:
        if self.refuse_start:
            raise OSError("accès refusé")
        self.started = True

    def stop(self) -> None:
        if self.refuse_stop:
            raise OSError("périphérique disparu")

    def close(self) -> None:
        self.closed = True

    def push(self, sound: NDArray[np.float32], *, lost: bool = False) -> None:
        assert self.on_block is not None
        for i in range(0, len(sound), BLOCK):
            self.on_block(sound[i : i + BLOCK], lost and i == 0)


class CountingAwake(capture.KeepAwake):
    def __init__(self) -> None:
        super().__init__(command=[])
        self.held = 0

    def hold(self) -> None:
        self.held += 1

    def release(self) -> None:
        self.held -= 1


MIC = capture.InputDevice(index=3, name="Micro MacBook Pro", channels=1, default=True)


class Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


@pytest.fixture
def mic() -> FakeMic:
    return FakeMic()


@pytest.fixture
def awake() -> CountingAwake:
    return CountingAwake()


@pytest.fixture
def clock() -> Clock:
    return Clock()


def recorder(
    data: DataDir, mic: FakeMic, awake: CountingAwake, clock: Clock, *, battery: bool = False
) -> capture.Recorder:
    return capture.Recorder(
        data,
        stream_factory=mic.factory,
        devices=lambda: [MIC],
        keep_awake=awake,
        battery=lambda: battery,
        clock=clock,
    )


def wait_for(condition: Callable[[], bool]) -> None:
    deadline = time.monotonic() + 5
    while not condition():
        assert time.monotonic() < deadline, "the writer did not catch up"
        time.sleep(0.01)


def start(rec: capture.Recorder) -> capture.RecordingState:
    return rec.start(space_id=None, attendee_ids=[], unnamed_attendees=2, device_index=None)


# -- the file ------------------------------------------------------------------------------


def test_the_wav_is_24_bit_48_khz_and_its_header_follows_what_is_written(tmp_path: Path) -> None:
    path = tmp_path / "ref.wav"
    writer = wav.WavWriter(path, 48_000, 1, sync_s=0.0)  # header rewritten on every block
    sound = tone(1.0, 0.5)
    writer.write(sound)
    info = sf.info(str(path))  # read while still open: the header is already true
    assert (info.samplerate, info.channels, info.subtype, info.frames) == (
        48_000,
        1,
        "PCM_24",
        48_000,
    )
    writer.close()
    back, _ = sf.read(str(path), dtype="float32")
    assert np.max(np.abs(back - sound[:, 0])) < 1e-6  # as captured, nothing processed


def test_an_interrupted_file_is_repaired_from_what_is_on_disk(tmp_path: Path) -> None:
    path = tmp_path / "ref.wav"
    writer = wav.WavWriter(path, 48_000, 1, sync_s=3600)  # the header stays at 0 frames
    writer.write(tone(2.0, 0.3))
    writer._file.flush()  # the process dies here: the data is on disk, the header is not
    assert sf.info(str(path)).frames == 0
    assert wav.repair(path) == 96_000
    assert sf.info(str(path)).frames == 96_000
    with pytest.raises(ValueError, match="lisible"):
        (tmp_path / "autre.wav").write_bytes(b"pas un wav")
        wav.repair(tmp_path / "autre.wav")


# -- the recorder ---------------------------------------------------------------------------


def test_a_recording_keeps_what_is_heard_but_not_the_pauses_then_is_processed(
    data: DataDir, mic: FakeMic, awake: CountingAwake, clock: Clock
) -> None:
    rec = recorder(data, mic, awake, clock)
    state = start(rec)
    assert mic.started and awake.held == 1  # the Mac stays awake while recording
    mic.push(tone(1.0, 0.3))
    wait_for(lambda: (rec.state() or state).elapsed_s >= 1.0)
    assert rec.pause().state == "paused"
    mic.push(tone(1.0, 0.3))  # heard while paused: shown on the meter, not recorded
    wait_for(lambda: (rec.state() or state).levels.rms_db > -30)
    rec.resume()
    mic.push(tone(0.5, 0.3))
    wait_for(lambda: (rec.state() or state).elapsed_s >= 1.5)
    stopped = rec.stop(profile="essai")
    assert stopped.duration_s == pytest.approx(1.5)
    assert stopped.processing and not stopped.on_battery
    assert awake.held == 0 and mic.closed and rec.state() is None
    source = sessions.reference_source(data, stopped.session_id)
    assert source is not None
    assert (source.origin, source.capture_state, source.duration_s) == ("captured", "complete", 1.5)
    assert source.size_bytes > 0 and len(source.sha256) == 64
    assert sessions.get_session(data, stopped.session_id).job_state == "queued"  # type: ignore[union-attr]


def test_on_battery_the_processing_waits_for_the_user(
    data: DataDir, mic: FakeMic, awake: CountingAwake, clock: Clock
) -> None:
    rec = recorder(data, mic, awake, clock, battery=True)
    start(rec)
    mic.push(tone(0.5, 0.3))
    wait_for(lambda: rec.state() is not None and rec.state().elapsed_s >= 0.5)  # type: ignore[union-attr]
    stopped = rec.stop(profile="essai")
    assert stopped.on_battery and not stopped.processing
    assert sessions.get_session(data, stopped.session_id).job_state is None  # type: ignore[union-attr]
    sessions.start_processing(data, stopped.session_id, profile="essai")
    assert sessions.get_session(data, stopped.session_id).job_state == "queued"  # type: ignore[union-attr]
    with pytest.raises(sessions.AlreadyProcessedError):
        sessions.start_processing(data, stopped.session_id, profile="essai")


def test_too_quiet_and_saturation_are_said(
    data: DataDir, mic: FakeMic, awake: CountingAwake, clock: Clock
) -> None:
    rec = recorder(data, mic, awake, clock)
    start(rec)
    mic.push(tone(0.2, 0.0005))  # about -69 dBFS
    wait_for(lambda: rec.state().elapsed_s >= 0.2)  # type: ignore[union-attr]  # processed
    assert rec.state().levels.rms_db < capture.LOW_DB  # type: ignore[union-attr]
    assert not rec.state().too_quiet  # type: ignore[union-attr]  # not at once
    clock.now += capture.LOW_AFTER_S + 1
    assert rec.state().too_quiet  # type: ignore[union-attr]
    clock.now += 1  # the microphone keeps delivering
    mic.push(tone(0.2, 1.0))  # full scale
    wait_for(lambda: rec.state().elapsed_s >= 0.4)  # type: ignore[union-attr]
    assert rec.state().clipping and rec.state().error is None  # type: ignore[union-attr]
    assert not rec.state().too_quiet  # type: ignore[union-attr]
    clock.now += capture.CLIP_SHOWN_S + 1
    mic.push(tone(0.1, 0.3))
    wait_for(lambda: rec.state().elapsed_s >= 0.5)  # type: ignore[union-attr]
    assert not rec.state().clipping  # type: ignore[union-attr]
    rec.stop(profile="essai")


def test_a_microphone_that_stops_delivering_is_said(
    data: DataDir, mic: FakeMic, awake: CountingAwake, clock: Clock
) -> None:
    rec = recorder(data, mic, awake, clock)
    start(rec)
    clock.now += capture.SILENT_STREAM_S + 1
    assert "débranché" in (rec.state().error or "")  # type: ignore[union-attr]
    rec.stop(profile="essai")


def test_one_recording_at_a_time_and_a_microphone_that_cannot_open_leaves_nothing(
    data: DataDir, mic: FakeMic, awake: CountingAwake, clock: Clock
) -> None:
    rec = recorder(data, mic, awake, clock)
    start(rec)
    with pytest.raises(capture.RecordingError, match="déjà en cours"):
        start(rec)
    rec.stop(profile="essai")

    def refusing(*_: object) -> FakeMic:
        raise OSError("périphérique occupé")

    broken = capture.Recorder(
        data, stream_factory=refusing, devices=lambda: [MIC], keep_awake=awake
    )
    before = len(sessions.list_sessions(data))
    with pytest.raises(capture.RecordingError, match="occupé"):
        start(broken)
    assert len(sessions.list_sessions(data)) == before and awake.held == 0
    nothing = capture.Recorder(data, stream_factory=mic.factory, devices=list, keep_awake=awake)
    with pytest.raises(capture.RecordingError, match="Aucun micro"):
        start(nothing)


def test_a_recording_cut_by_a_crash_is_repaired_at_start_and_not_processed_alone(
    data: DataDir, mic: FakeMic, awake: CountingAwake, clock: Clock
) -> None:
    rec = recorder(data, mic, awake, clock)
    session_id = start(rec).session_id
    mic.push(tone(1.0, 0.3))
    wait_for(lambda: rec.state().elapsed_s >= 1.0)  # type: ignore[union-attr]
    # The service dies here: no stop. At the next start:
    told = capture.recover_interrupted(data)
    assert len(told) == 1 and "récupéré" in told[0]
    source = sessions.reference_source(data, session_id)
    assert source is not None and source.capture_state == "recovered"
    assert source.duration_s == pytest.approx(1.0, abs=0.11)
    assert sessions.get_session(data, session_id).job_state is None  # type: ignore[union-attr]
    assert capture.recover_interrupted(data) == []  # repaired once


# -- the service ---------------------------------------------------------------------------


def test_the_interface_drives_the_recording(
    data: DataDir, mic: FakeMic, awake: CountingAwake, clock: Clock
) -> None:
    rec = recorder(data, mic, awake, clock, battery=True)
    client = TestClient(
        create_app(data, FAKE_CHAIN, profile="essai", processor=None, web_dir=None, recorder=rec)
    )
    assert client.get("/api/enregistrement").json() is None
    started = client.post("/api/enregistrement", json={"non_nommes": 2})
    assert started.status_code == 201, started.text
    assert started.json()["device"] == "Micro MacBook Pro"
    mic.push(tone(0.5, 0.3))
    wait_for(lambda: client.get("/api/enregistrement").json()["elapsed_s"] >= 0.5)
    assert client.post("/api/enregistrement/pause").json()["state"] == "paused"
    assert client.post("/api/enregistrement/reprise").json()["state"] == "recording"
    assert client.post("/api/enregistrement", json={}).status_code == 422  # one at a time
    stopped = client.post("/api/enregistrement/arret").json()
    assert stopped["on_battery"] and not stopped["processing"]
    # The meter's stream ends with the recording.
    assert "event: fin" in client.get("/api/enregistrement/niveaux").text
    session_id = stopped["session_id"]
    detail = client.get(f"/api/seances/{session_id}").json()
    assert detail["source"]["capture_state"] == "complete"
    assert client.post(f"/api/seances/{session_id}/traiter").status_code == 202
    assert client.post(f"/api/seances/{session_id}/traiter").status_code == 422
    assert client.post("/api/enregistrement/arret").status_code == 422


def test_the_processing_keeps_the_mac_awake(data: DataDir, recording: Path) -> None:
    from coulisses_app import jobs
    from coulisses_app.processing import Processor

    awake = CountingAwake()
    seen: list[int] = []

    class Watching(Processor):
        def _run_job(self, job: jobs.Job):  # type: ignore[no-untyped-def]
            seen.append(awake.held)
            return super()._run_job(job)

    with recording.open("rb") as f:
        session_id = sessions.import_recording(
            data, f, "a.wav", unnamed_attendees=1, recorded_at=None, profile="essai"
        )
    conn = connect(data)
    try:
        job = jobs.claim_next(conn)
    finally:
        conn.close()
    assert job is not None and job.session_id == session_id
    Watching(data, FAKE_CHAIN, keep_awake=awake).run_job(job)
    assert seen == [1] and awake.held == 0


def test_a_microphone_that_refuses_to_start_leaves_nothing(
    data: DataDir, mic: FakeMic, awake: CountingAwake, clock: Clock
) -> None:
    mic.refuse_start = True
    before = len(sessions.list_sessions(data))
    with pytest.raises(capture.RecordingError, match="Confidentialité"):
        start(recorder(data, mic, awake, clock))
    assert len(sessions.list_sessions(data)) == before and mic.closed and awake.held == 0


def test_a_microphone_failing_at_stop_still_closes_the_session(
    data: DataDir, mic: FakeMic, awake: CountingAwake, clock: Clock
) -> None:
    rec = recorder(data, mic, awake, clock)
    start(rec)
    mic.push(tone(0.5, 0.3))
    wait_for(lambda: rec.state().elapsed_s >= 0.5)  # type: ignore[union-attr]
    mic.refuse_stop = True
    stopped = rec.stop(profile="essai")
    source = sessions.reference_source(data, stopped.session_id)
    assert source is not None and source.capture_state == "complete"
    assert stopped.duration_s == pytest.approx(0.5) and awake.held == 0


def test_lost_sound_and_a_full_file_are_said_and_what_was_written_is_kept(
    data: DataDir, mic: FakeMic, awake: CountingAwake, clock: Clock
) -> None:
    # A WAV « full » after half a second, to stand for its 4 GiB.
    rec = capture.Recorder(
        data,
        stream_factory=mic.factory,
        devices=lambda: [MIC],
        keep_awake=awake,
        battery=lambda: True,
        clock=clock,
        max_data_bytes=capture.SAMPLE_RATE * 3 // 2,
    )
    start(rec)
    mic.push(tone(0.2, 0.3), lost=True)
    mic.push(tone(1.0, 0.3))
    wait_for(lambda: rec.state().error is not None)  # type: ignore[union-attr]
    state = rec.state()
    assert state is not None and state.dropouts == 1 and "taille maximale" in (state.error or "")
    stopped = rec.stop(profile="essai")
    assert stopped.duration_s == pytest.approx(0.5)  # everything up to the limit
    assert (
        sf.info(str(capture.sessions.reference_audio_path(data, stopped.session_id))).frames
        == 24_000
    )


def test_an_empty_recording_cannot_be_processed(
    data: DataDir, mic: FakeMic, awake: CountingAwake, clock: Clock
) -> None:
    rec = recorder(data, mic, awake, clock, battery=True)
    session_id = start(rec).session_id
    rec.stop(profile="essai")
    with pytest.raises(sessions.AlreadyProcessedError, match="Rien n'a été enregistré"):
        sessions.start_processing(data, session_id, profile="essai")


def test_keep_awake_runs_one_process_while_held_and_stops_it(tmp_path: Path) -> None:
    awake = capture.KeepAwake(command=["sleep", "60"])
    awake.hold()
    awake.hold()
    process = awake._process
    assert process is not None and process.poll() is None
    awake.release()
    assert process.poll() is None  # still held once
    awake.release()
    assert process.wait(timeout=5) is not None and awake._process is None


def test_the_power_source_is_read_from_pmset() -> None:
    assert capture.battery_in("Now drawing from 'Battery Power'\n -InternalBattery-0")
    assert not capture.battery_in("Now drawing from 'AC Power'\n -InternalBattery-0")


def test_stopping_the_service_closes_the_recording(
    data: DataDir, mic: FakeMic, awake: CountingAwake, clock: Clock
) -> None:
    rec = recorder(data, mic, awake, clock, battery=True)
    app = create_app(data, FAKE_CHAIN, profile="essai", processor=None, web_dir=None, recorder=rec)
    with TestClient(app) as client:
        session_id = client.post("/api/enregistrement", json={}).json()["session_id"]
        mic.push(tone(0.3, 0.3))
        wait_for(lambda: rec.state().elapsed_s >= 0.3)  # type: ignore[union-attr]
    # The service stopped (its shutdown ran): the session is closed, with its sound.
    source = sessions.reference_source(data, session_id)
    assert source is not None and source.capture_state == "complete"
    assert source.duration_s == pytest.approx(0.3) and awake.held == 0


# -- markers and notes while recording (6b) --------------------------------------------


def test_markers_and_notes_are_set_at_the_recorded_time_and_can_be_taken_back(
    data: DataDir, mic: FakeMic, awake: CountingAwake, clock: Clock
) -> None:
    rec = recorder(data, mic, awake, clock, battery=True)
    client = TestClient(
        create_app(data, FAKE_CHAIN, profile="essai", processor=None, web_dir=None, recorder=rec)
    )
    session_id = client.post("/api/enregistrement", json={}).json()["session_id"]
    mic.push(tone(1.0, 0.3))
    wait_for(lambda: rec.state().elapsed_s >= 1.0)  # type: ignore[union-attr]
    played = client.post("/api/enregistrement/marqueurs", json={"kind": "scene"})
    assert played.status_code == 201
    assert [(m["kind"], m["at_s"]) for m in played.json()["markers"]] == [("scene", 1.0)]
    moment = client.post("/api/enregistrement/marqueurs", json={"kind": "key_moment"}).json()
    slip = moment["markers"][-1]["id"]
    # A note dated when its first letter was typed (0.4 s), not when it was sent.
    noted = client.post("/api/enregistrement/notes", json={"text": " Belle écoute ", "at_s": 0.4})
    assert [(n["at_s"], n["text"]) for n in noted.json()["notes"]] == [(0.4, "Belle écoute")]
    assert (
        client.post("/api/enregistrement/notes", json={"text": "x", "at_s": 99}).status_code == 422
    )
    assert (
        client.post("/api/enregistrement/notes", json={"text": "  ", "at_s": 0.5}).status_code
        == 422
    )
    taken = client.post(f"/api/enregistrement/marqueurs/{slip}/retirer").json()
    assert [m["kind"] for m in taken["markers"]] == ["scene"]
    assert client.post("/api/enregistrement/marqueurs/999/retirer").status_code == 404
    client.post("/api/enregistrement/arret")
    conn = connect(data)
    try:
        from coulisses_app import marks

        assert [(m.kind, m.at_s) for m in marks.markers(conn, session_id)] == [("scene", 1.0)]
        assert [(n.at_s, n.text) for n in marks.timed_notes(conn, session_id)] == [
            (0.4, "Belle écoute")
        ]
    finally:
        conn.close()
    assert client.post("/api/enregistrement/marqueurs", json={"kind": "scene"}).status_code == 422


def test_a_note_taken_back_can_never_be_the_note_after_the_session_and_a_marker_comes_back(
    data: DataDir, mic: FakeMic, awake: CountingAwake, clock: Clock
) -> None:
    from coulisses_app import notes as after_notes

    rec = recorder(data, mic, awake, clock, battery=True)
    client = TestClient(
        create_app(data, FAKE_CHAIN, profile="essai", processor=None, web_dir=None, recorder=rec)
    )
    session_id = client.post("/api/enregistrement", json={}).json()["session_id"]
    conn = connect(data)
    try:
        after_id = after_notes.set_after_session(conn, session_id, "Après la séance")
        after_row = conn.execute(
            "SELECT id FROM note WHERE session_id = ? AND at_s IS NULL", (session_id,)
        ).fetchone()["id"]
    finally:
        conn.close()
    del after_id
    assert client.post(f"/api/enregistrement/notes/{after_row}/retirer").status_code == 404
    mic.push(tone(1.0, 0.3))
    wait_for(lambda: rec.state().elapsed_s >= 1.0)  # type: ignore[union-attr]
    note = client.post("/api/enregistrement/notes", json={"text": "Idée", "at_s": 0.5}).json()
    note_id = note["notes"][0]["id"]
    assert client.post(f"/api/enregistrement/notes/{note_id}/retirer").json()["notes"] == []
    # Taken back by mistake: put back where it was.
    back = client.post("/api/enregistrement/marqueurs", json={"kind": "scene", "at_s": 0.3}).json()
    assert [(m["kind"], m["at_s"]) for m in back["markers"]] == [("scene", 0.3)]
    assert (
        client.post("/api/enregistrement/marqueurs", json={"kind": "scene", "at_s": 50}).status_code
        == 422
    )
    client.post("/api/enregistrement/arret")
    conn = connect(data)
    try:
        assert after_notes.after_session(conn, session_id).text == "Après la séance"  # type: ignore[union-attr]
    finally:
        conn.close()
