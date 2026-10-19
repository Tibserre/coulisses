"""The tracks recorded in the application, kept in FLAC once the recording is over (ADR 0046):
the same samples, proven before any WAV goes; nothing done while a processing needs them."""

from __future__ import annotations

import json
import sqlite3
import subprocess
from pathlib import Path

import pytest

from coulisses_app import capture, jobs, lossless, mixing, retention, sessions, wav
from coulisses_app.api import create_app
from coulisses_app.paths import DataDir
from coulisses_app.processing import ChainConfig, Processor
from coulisses_app.storage.db import connect

from .conftest import FAKE_CHAIN, local_client
from .test_capture import Clock, CountingAwake, FakeMic, recorder, start, tone, wait_for
from .test_system_audio import recorded

pytestmark = pytest.mark.skipif(
    lossless.available() is not None, reason="ffmpeg sachant encoder en FLAC requis"
)


def journal(data: DataDir, session_id: str) -> list[dict]:
    conn = connect(data)
    rows = conn.execute(
        "SELECT kind, session_title, detail FROM deletion_log WHERE session_id = ? ORDER BY id",
        (session_id,),
    ).fetchall()
    conn.close()
    return [{"kind": r["kind"], **json.loads(r["detail"])} for r in rows]


def test_a_recording_is_kept_in_flac_with_the_same_samples(data: DataDir) -> None:
    sound = tone(1.0, 0.3)
    session_id = recorded(data, sound, None)
    folder = data.sources_dir(session_id)
    before = sessions.reference_source(data, session_id)
    assert before is not None and before.pcm_sha256 == wav.pcm_sha256(folder / "ref.wav")
    wav_bytes = (folder / "ref.wav").stat().st_size

    done = lossless.convert_session(data, session_id)

    assert done is not None and [c.flac.name for c in done] == ["ref.flac"]
    assert not (folder / "ref.wav").exists()
    after = sessions.reference_source(data, session_id)
    assert after is not None
    assert (after.file_name, after.codec, after.pcm_sha256) == (
        "ref.flac",
        "flac",
        before.pcm_sha256,
    )
    assert after.size_bytes == (folder / "ref.flac").stat().st_size < wav_bytes
    assert after.sha256 != before.sha256
    # Decoded, the very samples recorded (24 bits, mono, 48 kHz).
    assert lossless.decoded_pcm_sha256(folder / "ref.flac") == before.pcm_sha256
    assert sessions.reference_audio_path(data, session_id) == folder / "ref.flac"
    [entry] = journal(data, session_id)
    assert entry["kind"] == "conversion" and entry["problems"] == []
    assert entry["files"] == [
        {
            "path": "sources/ref.wav",
            "bytes": wav_bytes,
            "sha256": before.sha256,
            "pcm_sha256": before.pcm_sha256,
        }
    ]
    assert entry["kept"] == [{"path": "sources/ref.flac", "bytes": after.size_bytes}]
    assert entry["bytes"] == wav_bytes - after.size_bytes
    # Nothing left to do: a second pass changes nothing, writes nothing.
    assert lossless.convert_session(data, session_id) == []
    assert len(journal(data, session_id)) == 1


def test_a_meeting_keeps_its_tracks_and_mixes_in_flac_without_mixing_again(
    data: DataDir,
) -> None:
    session_id = recorded(data, tone(1.0, 0.3), tone(1.0, 0.1))
    folder = data.sources_dir(session_id)
    path = mixing.processing_path(data, session_id)
    assert path == folder / mixing.MIX_FILE
    before = mixing.read_facts(data, session_id)
    assert before is not None and before.listening_mix is not None
    plain_samples = wav.pcm_sha256(folder / mixing.MIX_FILE)
    heard_samples = wav.pcm_sha256(folder / mixing.LISTENING_FILE)

    done = lossless.convert_session(data, session_id)

    assert done is not None
    assert sorted(c.flac.name for c in done) == [
        "listening.flac",
        "mix.flac",
        "ref.flac",
        "system.flac",
    ]
    assert sorted(p.name for p in folder.iterdir()) == [
        "listening.flac",
        "mix.flac",
        "mix.json",
        "ref.flac",
        "system.flac",
    ]
    facts = mixing.read_facts(data, session_id)
    assert facts is not None and facts.listening_mix is not None
    assert (facts.file, facts.listening_mix.file) == ("mix.flac", "listening.flac")
    assert (facts.made_from, facts.made_at, facts.gain) == (
        before.made_from,
        before.made_at,
        before.gain,
    )
    assert lossless.decoded_pcm_sha256(folder / "mix.flac") == plain_samples == facts.pcm_sha256
    assert lossless.decoded_pcm_sha256(folder / "listening.flac") == heard_samples
    # The engine is given the mix in FLAC, never made again; the page plays the listening one.
    made = (folder / "mix.flac").stat().st_mtime_ns
    assert mixing.processing_path(data, session_id) == folder / "mix.flac"
    assert (folder / "mix.flac").stat().st_mtime_ns == made
    assert mixing.listening_path(data, session_id) == folder / "listening.flac"


def test_a_mix_made_again_from_flac_tracks_reads_them_without_loss(data: DataDir) -> None:
    session_id = recorded(data, tone(1.0, 0.3), tone(1.0, 0.1))
    mixing.processing_path(data, session_id)
    lossless.convert_session(data, session_id)
    folder = data.sources_dir(session_id)
    first = lossless.decoded_pcm_sha256(folder / "mix.flac")
    (folder / mixing.MIX_FACTS).unlink()  # lost: the mix is made again, from the FLAC tracks

    path = mixing.processing_path(data, session_id)

    assert path is not None and path == folder / mixing.MIX_FILE
    assert wav.pcm_sha256(path) == first  # the same samples as from the WAV tracks
    # Without its facts, nothing tells the old FLAC mixes were these: they stay until the
    # next conversion proves them the same, and takes them.
    assert (folder / "mix.flac").is_file()
    lossless.convert_session(data, session_id)
    assert sorted(p.name for p in folder.iterdir()) == [
        "listening.flac",
        "mix.flac",
        "mix.json",
        "ref.flac",
        "system.flac",
    ]


def test_mixes_made_again_replace_those_kept_in_flac(data: DataDir) -> None:
    session_id = recorded(data, tone(1.0, 0.3), tone(1.0, 0.1))
    mixing.processing_path(data, session_id)
    lossless.convert_session(data, session_id)
    folder = data.sources_dir(session_id)
    conn = connect(data)
    with conn:  # other samples for the computer's sound: the mix is made again
        conn.execute(
            "UPDATE audio_source SET pcm_sha256 = 'autre' WHERE session_id = ? AND source_id = ?",
            (session_id, "system"),
        )
    conn.close()

    assert mixing.processing_path(data, session_id) == folder / mixing.MIX_FILE

    assert not (folder / "mix.flac").exists() and not (folder / "listening.flac").exists()
    assert (folder / mixing.LISTENING_FILE).is_file()


def test_nothing_is_converted_while_a_processing_needs_the_tracks(data: DataDir) -> None:
    session_id = recorded(data, tone(1.0, 0.3), None)
    sessions.start_processing(data, session_id, profile="essai")
    assert lossless.convert_session(data, session_id) is None
    assert (data.sources_dir(session_id) / "ref.wav").is_file()
    # Once processed, it is: the processing calls back.
    conn = connect(data)
    job = jobs.claim_next(conn)
    conn.close()
    assert job is not None
    called: list[str] = []
    Processor(data, FAKE_CHAIN, after_chain=called.append).run_job(job)
    assert called == [session_id]
    assert lossless.convert_session(data, session_id)


def test_a_flac_that_does_not_give_the_same_samples_leaves_the_wav(
    data: DataDir, monkeypatch: pytest.MonkeyPatch
) -> None:
    session_id = recorded(data, tone(1.0, 0.3), None)
    folder = data.sources_dir(session_id)
    other = folder.parent / "autre.wav"
    writer = wav.WavWriter(other, capture.SAMPLE_RATE, 1)
    writer.write(tone(1.0, 0.2))
    writer.close()
    real_encode = lossless._encode  # pyright: ignore[reportPrivateUsage]
    monkeypatch.setattr(lossless, "_encode", lambda source, target: real_encode(other, target))

    assert lossless.convert_session(data, session_id) == []

    assert sorted(p.name for p in folder.iterdir()) == ["ref.wav"]
    source = sessions.reference_source(data, session_id)
    assert source is not None and (source.file_name, source.codec) == ("ref.wav", "pcm_s24le")
    [entry] = journal(data, session_id)
    assert entry["files"] == [] and entry["bytes"] == 0
    assert "ne rend pas les mêmes échantillons" in entry["problems"][0]


def test_a_wav_whose_samples_changed_is_never_removed(data: DataDir) -> None:
    session_id = recorded(data, tone(1.0, 0.3), None)
    path = data.sources_dir(session_id) / "ref.wav"
    with path.open("r+b") as f:
        f.seek(wav.HEADER_BYTES + 300)
        f.write(b"\x01\x02\x03")
    assert lossless.convert_session(data, session_id) == []
    assert path.is_file() and not path.with_suffix(".flac").exists()
    assert "plus les échantillons" in journal(data, session_id)[0]["problems"][0]


def test_a_conversion_cut_short_is_taken_up_at_start(data: DataDir) -> None:
    session_id = recorded(data, tone(1.0, 0.3), None)
    folder = data.sources_dir(session_id)
    source = sessions.reference_source(data, session_id)
    assert source is not None and source.pcm_sha256 is not None
    # The service stopped once the FLAC took its name, before the base said so.
    lossless.convert_file(folder / "ref.wav", source.pcm_sha256)
    assert lossless.pending(data) == [session_id]

    lossless.convert_session(data, session_id)

    assert sorted(p.name for p in folder.iterdir()) == ["ref.flac"]
    after = sessions.reference_source(data, session_id)
    assert after is not None and after.file_name == "ref.flac"
    assert lossless.pending(data) == []


def test_a_wav_left_after_the_base_said_flac_goes_once_proven(data: DataDir) -> None:
    session_id = recorded(data, tone(1.0, 0.3), None)
    folder = data.sources_dir(session_id)
    kept = (folder / "ref.wav").read_bytes()
    lossless.convert_session(data, session_id)
    (folder / "ref.wav").write_bytes(kept)  # the service stopped before removing it
    assert lossless.pending(data) == [session_id]

    lossless.convert_session(data, session_id)

    assert sorted(p.name for p in folder.iterdir()) == ["ref.flac"]
    logged = journal(data, session_id)[-1]["files"]
    assert [(f["path"], f["bytes"]) for f in logged] == [("sources/ref.wav", len(kept))]


def test_imports_older_and_recovered_recordings_are_left_as_they_are(
    data: DataDir, recording: Path
) -> None:
    from .test_processing import import_

    imported = import_(data, recording)
    conn = connect(data)
    with conn:
        conn.execute("UPDATE job SET state = 'done' WHERE session_id = ?", (imported,))
    older = recorded(data, tone(1.0, 0.3), None)
    recovered = recorded(data, tone(1.0, 0.3), None)
    with conn:
        conn.execute("UPDATE audio_source SET pcm_sha256 = NULL WHERE session_id = ?", (older,))
        conn.execute(
            "UPDATE audio_source SET capture_state = 'recovered' WHERE session_id = ?",
            (recovered,),
        )
    conn.close()
    assert lossless.convert_session(data, imported) is None
    for session_id in (older, recovered):
        assert lossless.convert_session(data, session_id) is None
        assert (data.sources_dir(session_id) / "ref.wav").is_file()


def test_files_cannot_go_while_they_are_converted(data: DataDir) -> None:
    session_id = recorded(data, tone(1.0, 0.3), None)
    lossless._running.add(session_id)  # pyright: ignore[reportPrivateUsage]
    try:
        with pytest.raises(retention.DeletionError, match="gardées en FLAC"):
            retention.delete_session(data, session_id)
    finally:
        lossless._running.discard(session_id)  # pyright: ignore[reportPrivateUsage]


def test_the_page_is_served_flac(data: DataDir) -> None:
    session_id = recorded(data, tone(1.0, 0.3), None)
    lossless.convert_session(data, session_id)
    with local_client(
        create_app(data, FAKE_CHAIN, profile="essai", processor=None, web_dir=None)
    ) as client:
        answer = client.get(f"/api/seances/{session_id}/audio")
    assert answer.status_code == 200
    assert answer.headers["content-type"] == "audio/flac"


def test_the_recorder_hands_over_once_stopped(data: DataDir) -> None:
    mic = FakeMic()
    rec = recorder(data, mic, CountingAwake(), Clock())
    stopped: list[str] = []
    rec._after_stop = stopped.append  # pyright: ignore[reportPrivateUsage]
    session_id = start(rec).session_id
    mic.push(tone(0.5, 0.3))
    wait_for(lambda: rec.state() is not None and rec.state().elapsed_s >= 0.5)  # type: ignore[union-attr]
    rec.stop(profile="essai")
    assert stopped == [session_id]


def test_an_older_base_journals_conversions_and_keeps_its_rows(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from coulisses_app.storage import db

    shipped = db.migrations()
    older = DataDir(tmp_path / "ancienne")
    monkeypatch.setattr(db, "migrations", lambda: [m for m in shipped if m[0] <= 8])
    db.migrate(older)
    conn = connect(older)
    with conn:
        conn.execute(
            "INSERT INTO deletion_log (id, at, kind, session_id, session_title, detail)"
            " VALUES (7, '2026-10-01T00:00:00Z', 'purge', 's', 'Répétition', '{\"bytes\": 3}')"
        )
    conn.close()
    monkeypatch.setattr(db, "migrations", lambda: shipped)
    assert len(db.migrate(older)) == 1  # a backup before migration 0009

    conn = connect(older)
    row = conn.execute("SELECT * FROM deletion_log").fetchone()
    assert (row["id"], row["kind"], row["session_title"]) == (7, "purge", "Répétition")
    assert conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'index' AND name = 'deletion_log_by_date'"
    ).fetchone()
    with conn:
        conn.execute(
            "INSERT INTO deletion_log (at, kind, session_id, detail)"
            " VALUES ('2026-10-19T00:00:00Z', 'conversion', 'x', '{}')"
        )
    with pytest.raises(sqlite3.IntegrityError, match="CHECK"), conn:
        conn.execute(
            "INSERT INTO deletion_log (at, kind, session_id, detail)"
            " VALUES ('2026-10-19T00:00:00Z', 'autre', 'x', '{}')"
        )
    columns = {r["name"] for r in conn.execute("PRAGMA table_info(audio_source)")}
    conn.close()
    assert "pcm_sha256" in columns


def test_the_journal_reads_a_conversion(data: DataDir) -> None:
    session_id = recorded(data, tone(1.0, 0.3), None)
    lossless.convert_session(data, session_id)
    [entry] = retention.journal(data)
    assert entry.kind == "conversion" and entry.files == 1 and entry.bytes > 0
    with local_client(
        create_app(data, FAKE_CHAIN, profile="essai", processor=None, web_dir=None)
    ) as client:
        answer = client.get("/api/conservation")
    assert answer.status_code == 200, answer.text
    assert answer.json()["journal"][0]["kind"] == "conversion"


def test_a_damaged_flac_beside_its_wav_never_takes_its_place(data: DataDir) -> None:
    session_id = recorded(data, tone(1.0, 0.3), None)
    folder = data.sources_dir(session_id)
    kept = (folder / "ref.wav").read_bytes()
    lossless.convert_session(data, session_id)
    (folder / "ref.wav").write_bytes(kept)  # stopped before the WAV went…
    flac = folder / "ref.flac"
    flac.write_bytes(flac.read_bytes()[: flac.stat().st_size // 2])  # …and the FLAC cut short

    lossless.convert_session(data, session_id)

    assert (folder / "ref.wav").read_bytes() == kept
    assert "mis de côté" in journal(data, session_id)[-1]["problems"][0]
    # The base names the true one again; the damaged FLAC is kept aside, not tried again.
    source = sessions.reference_source(data, session_id)
    assert source is not None and (source.file_name, source.codec) == ("ref.wav", "pcm_s24le")
    assert (folder / "ref.flac.abime").is_file()
    assert lossless.pending(data) == []


def test_a_flac_made_again_has_its_own_fingerprint_in_the_base(data: DataDir) -> None:
    session_id = recorded(data, tone(1.0, 0.3), None)
    folder = data.sources_dir(session_id)
    kept = (folder / "ref.wav").read_bytes()
    lossless.convert_session(data, session_id)
    (folder / "ref.wav").write_bytes(kept)
    (folder / "ref.flac").unlink()  # gone in the Finder; the base still names it

    lossless.convert_session(data, session_id)

    source = sessions.reference_source(data, session_id)
    assert source is not None and source.file_name == "ref.flac"
    assert source.sha256 == lossless._file_sha256(folder / "ref.flac")  # pyright: ignore[reportPrivateUsage]
    assert source.size_bytes == (folder / "ref.flac").stat().st_size
    assert not (folder / "ref.wav").exists()


def test_a_mix_conversion_cut_short_is_finished(data: DataDir) -> None:
    session_id = recorded(data, tone(1.0, 0.3), tone(1.0, 0.1))
    mixing.processing_path(data, session_id)
    folder = data.sources_dir(session_id)
    kept = (folder / mixing.MIX_FILE).read_bytes()
    lossless.convert_session(data, session_id)
    (folder / mixing.MIX_FILE).write_bytes(kept)  # mix.json said FLAC, the WAV stayed
    assert lossless.pending(data) == [session_id]

    lossless.convert_session(data, session_id)

    assert not (folder / mixing.MIX_FILE).exists() and (folder / "mix.flac").is_file()
    assert journal(data, session_id)[-1]["files"][0]["path"] == "sources/mix.wav"


def test_at_start_what_was_cut_short_is_taken_up(data: DataDir) -> None:
    session_id = recorded(data, tone(1.0, 0.3), None)
    folder = data.sources_dir(session_id)
    source = sessions.reference_source(data, session_id)
    assert source is not None and source.pcm_sha256 is not None
    lossless.convert_file(folder / "ref.wav", source.pcm_sha256)
    lossless.at_start(data)
    wait_for(lambda: not (folder / "ref.wav").exists())
    wait_for(lambda: not lossless.busy(session_id))
    after = sessions.reference_source(data, session_id)
    assert after is not None and after.file_name == "ref.flac"


def test_audio_removed_meanwhile_keeps_no_flac(data: DataDir) -> None:
    session_id = recorded(data, tone(1.0, 0.3), None)
    retention.remove_audio(data, session_id, "audio_deletion")
    assert lossless.convert_session(data, session_id) is None
    source = sessions.reference_source(data, session_id)
    assert source is not None
    assert not sessions.mark_converted(
        data,
        session_id,
        "ref",
        file_name="ref.flac",
        sha256="x",
        size_bytes=1,
        codec="flac",
    )


@pytest.mark.slow
def test_the_engine_hears_the_same_from_a_wav_and_its_flac(
    data: DataDir, recording: Path, tmp_path: Path
) -> None:
    from coulisses.api import AttributedTranscript, load_profile, profile_path, read_output

    from .test_processing import claim, import_, runs

    as_24_bits = tmp_path / "repetition.wav"
    subprocess.run(
        ["ffmpeg", "-v", "error", "-i", str(recording), "-c:a", "pcm_s24le", str(as_24_bits)],
        check=True,
    )
    as_flac = tmp_path / "repetition.flac"
    subprocess.run(
        ["ffmpeg", "-v", "error", "-i", str(as_24_bits), "-c:a", "flac", str(as_flac)], check=True
    )
    chain = ChainConfig.from_profile(load_profile(profile_path()))
    heard = []
    for path in (as_24_bits, as_flac):
        session_id = import_(data, path, attendees=1)
        conn = connect(data)
        with conn:  # the chapters asked after a chain: not this test's
            conn.execute("UPDATE job SET state = 'done' WHERE kind = 'generation'")
        conn.close()
        result = Processor(data, chain).run_job(claim(data))
        assert result.error is None, result.error
        attribute = next(r for r in runs(data, session_id) if r["stage"] == "attribute")
        words = read_output(data.run_dir(session_id, attribute["id"]), AttributedTranscript).words
        heard.append([(w.text, w.start, w.end, w.speaker) for w in words])
    assert heard[0] == heard[1] and heard[0]
