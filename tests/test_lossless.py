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

    assert done is not None and [c.kept.name for c in done] == ["ref.m4a"]
    assert not (folder / "ref.wav").exists()
    after = sessions.reference_source(data, session_id)
    assert after is not None
    assert (after.file_name, after.codec, after.pcm_sha256) == (
        "ref.m4a",
        "flac",
        before.pcm_sha256,
    )
    assert after.size_bytes == (folder / "ref.m4a").stat().st_size < wav_bytes
    assert after.sha256 != before.sha256
    # Decoded, the very samples recorded (24 bits, mono, 48 kHz).
    assert lossless.decoded_pcm_sha256(folder / "ref.m4a") == before.pcm_sha256
    assert sessions.reference_audio_path(data, session_id) == folder / "ref.m4a"
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
    assert entry["kept"] == [{"path": "sources/ref.m4a", "bytes": after.size_bytes}]
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
    assert sorted(c.kept.name for c in done) == [
        "listening.m4a",
        "mix.m4a",
        "ref.m4a",
        "system.m4a",
    ]
    assert sorted(p.name for p in folder.iterdir()) == [
        "listening.m4a",
        "mix.json",
        "mix.m4a",
        "ref.m4a",
        "system.m4a",
    ]
    facts = mixing.read_facts(data, session_id)
    assert facts is not None and facts.listening_mix is not None
    # Each in an MP4, where the page's player seeks exactly (ADR 0073).
    assert (facts.file, facts.listening_mix.file) == ("mix.m4a", "listening.m4a")
    assert (facts.made_from, facts.made_at, facts.gain) == (
        before.made_from,
        before.made_at,
        before.gain,
    )
    assert lossless.decoded_pcm_sha256(folder / "mix.m4a") == plain_samples == facts.pcm_sha256
    assert lossless.decoded_pcm_sha256(folder / "listening.m4a") == heard_samples
    # The engine is given the mix in FLAC, never made again; the page plays the listening one.
    made = (folder / "mix.m4a").stat().st_mtime_ns
    assert mixing.processing_path(data, session_id) == folder / "mix.m4a"
    assert (folder / "mix.m4a").stat().st_mtime_ns == made
    assert mixing.listening_path(data, session_id) == folder / "listening.m4a"


def test_a_mix_made_again_from_flac_tracks_reads_them_without_loss(data: DataDir) -> None:
    session_id = recorded(data, tone(1.0, 0.3), tone(1.0, 0.1))
    mixing.processing_path(data, session_id)
    lossless.convert_session(data, session_id)
    folder = data.sources_dir(session_id)
    first = lossless.decoded_pcm_sha256(folder / "mix.m4a")
    (folder / mixing.MIX_FACTS).unlink()  # lost: the mix is made again, from the FLAC tracks

    path = mixing.processing_path(data, session_id)

    assert path is not None and path == folder / mixing.MIX_FILE
    assert wav.pcm_sha256(path) == first  # the same samples as from the WAV tracks
    # Without its facts, nothing tells the old FLAC mixes were these: they stay until the
    # next conversion proves them the same, and takes them.
    assert (folder / "mix.m4a").is_file()
    lossless.convert_session(data, session_id)
    assert sorted(p.name for p in folder.iterdir()) == [
        "listening.m4a",
        "mix.json",
        "mix.m4a",
        "ref.m4a",
        "system.m4a",
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

    assert not (folder / "mix.m4a").exists() and not (folder / "listening.m4a").exists()
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
    monkeypatch.setattr(
        lossless,
        "_encode",
        lambda source, target, suffix: real_encode(other, target, suffix),
    )

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
    assert path.is_file() and not path.with_suffix(".m4a").exists()
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

    assert sorted(p.name for p in folder.iterdir()) == ["ref.m4a"]
    after = sessions.reference_source(data, session_id)
    assert after is not None and after.file_name == "ref.m4a"
    assert lossless.pending(data) == []


def test_a_wav_left_after_the_base_said_flac_goes_once_proven(data: DataDir) -> None:
    session_id = recorded(data, tone(1.0, 0.3), None)
    folder = data.sources_dir(session_id)
    kept = (folder / "ref.wav").read_bytes()
    lossless.convert_session(data, session_id)
    (folder / "ref.wav").write_bytes(kept)  # the service stopped before removing it
    assert lossless.pending(data) == [session_id]

    lossless.convert_session(data, session_id)

    assert sorted(p.name for p in folder.iterdir()) == ["ref.m4a"]
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
    flac = folder / "ref.m4a"
    flac.write_bytes(flac.read_bytes()[: flac.stat().st_size // 2])  # …and the FLAC cut short

    lossless.convert_session(data, session_id)

    assert (folder / "ref.wav").read_bytes() == kept
    assert "mis de côté" in journal(data, session_id)[-1]["problems"][0]
    # The base names the true one again; the damaged FLAC is kept aside, not tried again.
    source = sessions.reference_source(data, session_id)
    assert source is not None and (source.file_name, source.codec) == ("ref.wav", "pcm_s24le")
    assert (folder / "ref.m4a.abime").is_file()
    assert lossless.pending(data) == []


def test_a_flac_made_again_has_its_own_fingerprint_in_the_base(data: DataDir) -> None:
    session_id = recorded(data, tone(1.0, 0.3), None)
    folder = data.sources_dir(session_id)
    kept = (folder / "ref.wav").read_bytes()
    lossless.convert_session(data, session_id)
    (folder / "ref.wav").write_bytes(kept)
    (folder / "ref.m4a").unlink()  # gone in the Finder; the base still names it

    lossless.convert_session(data, session_id)

    source = sessions.reference_source(data, session_id)
    assert source is not None and source.file_name == "ref.m4a"
    assert source.sha256 == lossless._file_sha256(folder / "ref.m4a")  # pyright: ignore[reportPrivateUsage]
    assert source.size_bytes == (folder / "ref.m4a").stat().st_size
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

    assert not (folder / mixing.MIX_FILE).exists() and (folder / "mix.m4a").is_file()
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
    assert after is not None and after.file_name == "ref.m4a"


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
        file_name="ref.m4a",
        sha256="x",
        size_bytes=1,
        codec="flac",
    )


@pytest.mark.slow
def test_the_engine_hears_the_same_from_a_wav_its_flac_and_its_mp4(
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
    # The same FLAC in an MP4, as every track is kept (ADR 0074).
    as_mp4 = tmp_path / "repetition.m4a"
    subprocess.run(
        ["ffmpeg", "-v", "error", "-i", str(as_flac), "-c:a", "copy", "-f", "mp4", str(as_mp4)],
        check=True,
    )
    chain = ChainConfig.from_profile(load_profile(profile_path()))
    heard = []
    for path in (as_24_bits, as_flac, as_mp4):
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
    assert heard[0] == heard[1] == heard[2] and heard[0]


# -- one file for each sound, in an MP4 (ADR 0074) -------------------------------------------


def served(data: DataDir, session_id: str) -> tuple[bytes, str]:
    with local_client(
        create_app(data, FAKE_CHAIN, profile="essai", processor=None, web_dir=None)
    ) as client:
        answer = client.get(f"/api/seances/{session_id}/audio")
    assert answer.status_code == 200
    return answer.content, answer.headers["content-type"]


def names(data: DataDir, session_id: str) -> list[str]:
    return sorted(p.name for p in data.sources_dir(session_id).iterdir())


def test_the_page_is_served_the_track_itself_in_an_mp4(data: DataDir) -> None:
    session_id = recorded(data, tone(1.0, 0.3), None)
    lossless.convert_session(data, session_id)

    assert names(data, session_id) == ["ref.m4a"]  # one file for the sound, no copy
    folder = data.sources_dir(session_id)
    assert served(data, session_id) == ((folder / "ref.m4a").read_bytes(), "audio/mp4")


def test_without_an_ffmpeg_writing_mp4_tracks_stay_in_raw_flac(
    data: DataDir, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(lossless, "mp4_available", lambda: "pas de MP4")
    alone = recorded(data, tone(1.0, 0.3), None)
    meeting = recorded(data, tone(1.0, 0.3), tone(1.0, 0.1))
    mixing.processing_path(data, meeting)

    lossless.convert_session(data, alone)
    lossless.convert_session(data, meeting)

    assert names(data, alone) == ["ref.flac"]
    assert names(data, meeting) == [
        "listening.flac",
        "mix.flac",
        "mix.json",
        "ref.flac",
        "system.flac",
    ]
    assert served(data, alone)[1] == served(data, meeting)[1] == "audio/flac"
    lines: list[str] = []
    assert lossless.rewrap_all(data, lines.append) == 1
    assert lines == ["Rien n'est fait : pas de MP4."]


def older(data: DataDir, monkeypatch: pytest.MonkeyPatch, system: bool) -> str:
    """A session kept in raw FLAC, before ADR 0073."""
    with monkeypatch.context() as before:
        before.setattr(lossless, "mp4_available", lambda: "avant l'ADR 0073")
        session_id = recorded(data, tone(1.0, 0.3), tone(1.0, 0.1) if system else None)
        if system:
            mixing.processing_path(data, session_id)
        lossless.convert_session(data, session_id)
    return session_id


def test_an_older_session_is_put_in_an_mp4_at_start_not_after_a_processing(
    data: DataDir, monkeypatch: pytest.MonkeyPatch
) -> None:
    alone, meeting = older(data, monkeypatch, False), older(data, monkeypatch, True)
    before = {s: names(data, s) for s in (alone, meeting)}

    # A processing over: nothing of them changes; it is done at start (ADR 0074).
    lossless.convert_session(data, alone)
    lossless.convert_session(data, meeting)
    assert {s: names(data, s) for s in before} == before
    assert lossless.rewrap_pending(data) == sorted([alone, meeting])

    lossless.at_start(data)
    wait_for(lambda: lossless.rewrap_pending(data) == [])
    wait_for(lambda: not lossless.busy(alone) and not lossless.busy(meeting))

    assert names(data, alone) == ["ref.m4a"]
    assert names(data, meeting) == [
        "listening.m4a",
        "mix.json",
        "mix.m4a",
        "ref.m4a",
        "system.m4a",
    ]


def test_a_session_that_fails_keeps_its_files_and_waits_for_the_command(
    data: DataDir, monkeypatch: pytest.MonkeyPatch
) -> None:
    alone, fine = older(data, monkeypatch, False), older(data, monkeypatch, False)
    other = data.sources_dir(alone).parent / "autre.wav"
    writer = wav.WavWriter(other, capture.SAMPLE_RATE, 1)
    writer.write(tone(1.0, 0.2))
    writer.close()
    real_encode = lossless._encode  # pyright: ignore[reportPrivateUsage]
    tried: list[str] = []

    def wrong_for_alone(source: Path, target: Path, suffix: str) -> None:
        tried.append(source.parent.parent.name)
        real_encode(other if alone in str(source) else source, target, suffix)

    monkeypatch.setattr(lossless, "_encode", wrong_for_alone)

    lossless.migrate(data)

    assert names(data, alone) == ["ref.flac"] and names(data, fine) == ["ref.m4a"]
    [entry] = [e for e in journal(data, alone) if e["problems"]]
    assert "ne rend pas les mêmes échantillons : ref.flac est gardé" in entry["problems"][0]
    # Not tried again at the next start: the journal would say it again each time.
    tried.clear()
    lossless.migrate(data)
    assert tried == []
    # Asked by the user, it is; done, it is no longer marked.
    monkeypatch.setattr(lossless, "_encode", real_encode)
    assert lossless.rewrap_all(data, lambda line: None) == 0
    assert names(data, alone) == ["ref.m4a"]
    assert lossless.rewrap_pending(data) == []


def test_without_an_ffmpeg_writing_mp4_nothing_is_migrated(
    data: DataDir, monkeypatch: pytest.MonkeyPatch
) -> None:
    alone = older(data, monkeypatch, False)
    monkeypatch.setattr(lossless, "mp4_available", lambda: "pas de MP4")

    lossless.migrate(data)

    assert names(data, alone) == ["ref.flac"]


def test_asked_older_tracks_are_put_in_an_mp4_one_file_for_each_sound(
    data: DataDir, monkeypatch: pytest.MonkeyPatch
) -> None:
    alone, meeting = older(data, monkeypatch, False), older(data, monkeypatch, True)
    folder = data.sources_dir(meeting)
    facts_before = mixing.read_facts(data, meeting)
    assert facts_before is not None and facts_before.listening_mix is not None
    sources_before = {s: sessions.reference_source(data, s) for s in (alone, meeting)}
    raw = {n: (folder / n).stat().st_size for n in names(data, meeting) if n.endswith(".flac")}
    entries = len(journal(data, meeting))

    lines: list[str] = []
    assert lossless.rewrap_all(data, lines.append) == 0

    assert names(data, alone) == ["ref.m4a"]
    assert names(data, meeting) == [
        "listening.m4a",
        "mix.json",
        "mix.m4a",
        "ref.m4a",
        "system.m4a",
    ]
    # The base and `mix.json` name the MP4; the samples, and what the mix was made from, do
    # not change: nothing is mixed or processed again for it.
    for session_id, before in sources_before.items():
        after = sessions.reference_source(data, session_id)
        assert before is not None and after is not None
        assert (after.file_name, after.codec) == ("ref.m4a", "flac")
        assert after.pcm_sha256 == before.pcm_sha256
        assert after.sha256 != before.sha256
        assert (
            lossless.decoded_pcm_sha256(data.sources_dir(session_id) / "ref.m4a")
            == before.pcm_sha256
        )
    facts = mixing.read_facts(data, meeting)
    assert facts is not None and facts.listening_mix is not None
    assert (facts.file, facts.listening_mix.file) == ("mix.m4a", "listening.m4a")
    assert (facts.made_from, facts.made_at, facts.pcm_sha256) == (
        facts_before.made_from,
        facts_before.made_at,
        facts_before.pcm_sha256,
    )
    assert facts.listening_mix.pcm_sha256 == facts_before.listening_mix.pcm_sha256
    made = (folder / "mix.m4a").stat().st_mtime_ns
    assert mixing.processing_path(data, meeting) == folder / "mix.m4a"
    assert (folder / "mix.m4a").stat().st_mtime_ns == made
    # Each raw FLAC removed is journaled, with its fingerprints.
    [entry] = journal(data, meeting)[entries:]
    assert entry["problems"] == []
    assert sorted((f["path"], f["bytes"]) for f in entry["files"]) == sorted(
        (f"sources/{n}", size) for n, size in raw.items()
    )
    assert served(data, alone)[1] == served(data, meeting)[1] == "audio/mp4"
    assert sorted(lines) == sorted(
        [
            f"{alone} : ref.flac → ref.m4a",
            f"{meeting} : ref.flac → ref.m4a, system.flac → system.m4a, mix.flac → mix.m4a, "
            "listening.flac → listening.m4a",
        ]
    )
    # Done once: asked again, nothing is left.
    assert lossless.rewrap_pending(data) == []
    again: list[str] = []
    assert lossless.rewrap_all(data, again.append) == 0 and again == []


def test_a_copy_heard_made_by_0_38_2_goes_once_its_track_is_in_an_mp4(
    data: DataDir, monkeypatch: pytest.MonkeyPatch
) -> None:
    alone = older(data, monkeypatch, False)
    folder = data.sources_dir(alone)
    copy = folder / lossless.LISTENING_COPY
    lossless._encode(folder / "ref.flac", copy, lossless.MP4_SUFFIX)  # pyright: ignore[reportPrivateUsage]
    copy_bytes = copy.stat().st_size
    assert served(data, alone) == (copy.read_bytes(), "audio/mp4")  # heard meanwhile
    assert lossless.rewrap_pending(data) == [alone]

    lossless.rewrap_all(data, lambda line: None)

    assert names(data, alone) == ["ref.m4a"]
    # Journaled as freed whole: nothing is kept in its place.
    [entry] = [e for e in journal(data, alone) if any("copy" in f["path"] for f in e["files"])]
    flac = next(f for f in entry["files"] if f["path"] == "sources/ref.flac")
    assert ("sources/listening-copy.m4a", copy_bytes) in [
        (f["path"], f["bytes"]) for f in entry["files"]
    ]
    assert [k["path"] for k in entry["kept"]] == ["sources/ref.m4a"]
    assert entry["bytes"] == flac["bytes"] - entry["kept"][0]["bytes"] + copy_bytes
    assert served(data, alone) == ((folder / "ref.m4a").read_bytes(), "audio/mp4")


def test_a_copy_that_differs_from_its_track_is_kept(
    data: DataDir, monkeypatch: pytest.MonkeyPatch
) -> None:
    alone = older(data, monkeypatch, False)
    folder = data.sources_dir(alone)
    other = folder.parent / "autre.wav"
    writer = wav.WavWriter(other, capture.SAMPLE_RATE, 1)
    writer.write(tone(1.0, 0.2))
    writer.close()
    lossless._encode(other, folder / lossless.LISTENING_COPY, lossless.MP4_SUFFIX)  # pyright: ignore[reportPrivateUsage]

    lines: list[str] = []
    assert lossless.rewrap_all(data, lines.append) == 1

    assert names(data, alone) == [lossless.LISTENING_COPY, "ref.m4a"]
    assert "ne rend pas les échantillons" in lines[-1]


def test_a_putting_in_an_mp4_cut_short_is_finished_at_start(
    data: DataDir, monkeypatch: pytest.MonkeyPatch
) -> None:
    alone, cut = older(data, monkeypatch, False), older(data, monkeypatch, False)
    source = sessions.reference_source(data, alone)
    assert source is not None and source.pcm_sha256 is not None
    # The service stopped once the MP4 took its name, before the base said so; and another
    # while its MP4 was half written.
    lossless.convert_file(data.sources_dir(alone) / "ref.flac", source.pcm_sha256)
    (data.sources_dir(cut) / "ref.m4a.partiel").write_bytes(b"coupe")
    assert lossless.pending(data) == sorted([alone, cut])

    lossless.convert_session(data, alone)
    lossless.convert_session(data, cut)

    assert names(data, alone) == names(data, cut) == ["ref.m4a"]
    after = sessions.reference_source(data, alone)
    assert after is not None and after.file_name == "ref.m4a"
    assert lossless.pending(data) == []


def test_a_putting_in_an_mp4_that_does_not_give_the_same_samples_changes_nothing(
    data: DataDir, monkeypatch: pytest.MonkeyPatch
) -> None:
    alone = older(data, monkeypatch, False)
    other = data.sources_dir(alone).parent / "autre.wav"
    writer = wav.WavWriter(other, capture.SAMPLE_RATE, 1)
    writer.write(tone(1.0, 0.2))
    writer.close()
    real_encode = lossless._encode  # pyright: ignore[reportPrivateUsage]
    monkeypatch.setattr(
        lossless, "_encode", lambda source, target, suffix: real_encode(other, target, suffix)
    )

    lines: list[str] = []
    assert lossless.rewrap_all(data, lines.append) == 1

    assert names(data, alone) == ["ref.flac"]
    after = sessions.reference_source(data, alone)
    assert after is not None and (after.file_name, after.codec) == ("ref.flac", "flac")
    assert "ne rend pas les mêmes échantillons : ref.flac est gardé" in lines[-1]


def test_a_session_whose_processing_waits_is_left_and_said(
    data: DataDir, monkeypatch: pytest.MonkeyPatch
) -> None:
    alone = older(data, monkeypatch, False)
    sessions.start_processing(data, alone, profile="essai")

    lines: list[str] = []
    assert lossless.rewrap_all(data, lines.append) == 1

    assert names(data, alone) == ["ref.flac"]
    assert "un traitement l'attend" in lines[0]


def test_the_audio_cannot_go_while_its_tracks_are_put_in_an_mp4(
    data: DataDir, monkeypatch: pytest.MonkeyPatch
) -> None:
    alone = older(data, monkeypatch, False)
    tried: list[str] = []
    real_encode = lossless._encode  # pyright: ignore[reportPrivateUsage]

    def remove_meanwhile(source: Path, target: Path, suffix: str) -> None:
        try:
            retention.remove_audio(data, alone, "audio_deletion")
        except retention.DeletionError as exc:
            tried.append(str(exc))
        real_encode(source, target, suffix)

    monkeypatch.setattr(lossless, "_encode", remove_meanwhile)
    lossless.rewrap_all(data, lambda line: None)

    assert tried and "en train d'être gardées" in tried[0]


def test_a_listening_mix_conversion_cut_short_is_finished(data: DataDir) -> None:
    session_id = recorded(data, tone(1.0, 0.3), tone(1.0, 0.1))
    mixing.processing_path(data, session_id)
    folder = data.sources_dir(session_id)
    kept = (folder / mixing.LISTENING_FILE).read_bytes()
    lossless.convert_session(data, session_id)
    (folder / mixing.LISTENING_FILE).write_bytes(kept)  # mix.json said MP4, the WAV stayed
    assert lossless.pending(data) == [session_id]

    lossless.convert_session(data, session_id)

    assert not (folder / mixing.LISTENING_FILE).exists()
    assert (folder / "listening.m4a").is_file()
    assert lossless.pending(data) == []


def test_the_command_is_asked_by_name() -> None:
    from coulisses_app.cli import parse_args

    assert parse_args(["--dev", "--ecoute-exacte"]).ecoute_exacte
    assert not parse_args(["--dev"]).ecoute_exacte


def test_a_copy_left_unfinished_or_beside_its_track_in_an_mp4_goes_at_start(
    data: DataDir, monkeypatch: pytest.MonkeyPatch
) -> None:
    unfinished, beside = older(data, monkeypatch, False), older(data, monkeypatch, False)
    (data.sources_dir(unfinished) / (lossless.LISTENING_COPY + ".partiel")).write_bytes(b"coupe")
    folder = data.sources_dir(beside)
    lossless._encode(folder / "ref.flac", folder / lossless.LISTENING_COPY, lossless.MP4_SUFFIX)  # pyright: ignore[reportPrivateUsage]
    lossless.rewrap_all(data, lambda line: None)
    # The service stopped after the reference took its MP4, before the copy went.
    lossless._encode(folder / "ref.m4a", folder / lossless.LISTENING_COPY, lossless.MP4_SUFFIX)  # pyright: ignore[reportPrivateUsage]
    (data.sources_dir(unfinished) / (lossless.LISTENING_COPY + ".partiel")).write_bytes(b"coupe")
    assert lossless.pending(data) == sorted([unfinished, beside])

    for session_id in lossless.pending(data):
        lossless.convert_session(data, session_id)

    assert names(data, unfinished) == names(data, beside) == ["ref.m4a"]
    assert lossless.pending(data) == []


def test_a_session_put_in_an_mp4_reuses_its_runs_whatever_the_path_they_read(
    data: DataDir, monkeypatch: pytest.MonkeyPatch
) -> None:
    from coulisses.api import read_provenance

    from coulisses_app import versions
    from coulisses_app.status import stage_views

    from .test_versions import claim, shown

    alone = older(data, monkeypatch, False)
    sessions.start_processing(data, alone, profile="essai")
    assert Processor(data, FAKE_CHAIN).run_job(claim(data)).error is None
    first = shown(data, alone)

    def read(stage: str) -> str:
        prov = read_provenance(data.run_dir(alone, shown(data, alone)[stage]))
        assert prov is not None
        return json.dumps(prov.inputs)

    assert "ref.flac" in read("diarize")
    assert lossless.rewrap_all(data, lambda line: None) == 0

    # The runs read ref.flac, gone: they are still the version, never made again for it.
    assert shown(data, alone) == first
    stages = {s.stage: s for s in stage_views(data, FAKE_CHAIN, alone)}
    assert all(s.state == "succeeded" and not s.stale for s in stages.values())
    # Run again, the voices only: the text is reused (by its run, not by the path it read),
    # the new run reads the same samples from the MP4.
    versions.request_rerun(data, alone, "diarize", attendees=3, profile="essai")
    assert Processor(data, FAKE_CHAIN).run_job(claim(data)).error is None
    now = shown(data, alone)
    assert (now["transcribe"], now["align"]) == (first["transcribe"], first["align"])
    assert now["diarize"] != first["diarize"]
    assert "ref.m4a" in read("diarize") and "ref.flac" in read("transcribe")


def heard_like_the_mix(data: DataDir, session_id: str) -> None:
    """The microphone never turned down: the listening mix gives the mix's very samples."""
    folder = data.sources_dir(session_id)
    (folder / mixing.LISTENING_FILE).write_bytes((folder / mixing.MIX_FILE).read_bytes())
    facts = mixing.read_facts(data, session_id)
    assert facts is not None and facts.listening_mix is not None
    heard = facts.listening_mix.model_copy(
        update={
            "sha256": lossless._file_sha256(folder / mixing.LISTENING_FILE),  # pyright: ignore[reportPrivateUsage]
            "pcm_sha256": facts.pcm_sha256,
        }
    )
    mixing.write_facts(data, session_id, facts.model_copy(update={"listening_mix": heard}))


def test_a_listening_mix_the_same_as_the_mix_is_heard_from_the_mix(data: DataDir) -> None:
    session_id = recorded(data, tone(1.0, 0.3), tone(1.0, 0.1))
    mixing.processing_path(data, session_id)
    heard_like_the_mix(data, session_id)
    folder = data.sources_dir(session_id)

    lossless.convert_session(data, session_id)

    # One file for the sound: the listening mix is heard from the mix's (ADR 0074).
    assert names(data, session_id) == ["mix.json", "mix.m4a", "ref.m4a", "system.m4a"]
    facts = mixing.read_facts(data, session_id)
    assert facts is not None and facts.listening_mix is not None
    assert (facts.listening_mix.file, facts.listening_mix.sha256) == (facts.file, facts.sha256)
    assert facts.listening_mix.pcm_sha256 == facts.pcm_sha256
    assert served(data, session_id) == ((folder / "mix.m4a").read_bytes(), "audio/mp4")
    # Journaled: the listening WAV kept in an MP4, then that MP4 freed whole, nothing kept in
    # its place.
    [entry] = journal(data, session_id)
    removed = [f["path"] for f in entry["files"]]
    assert "sources/listening.wav" in removed and "sources/listening.m4a" in removed
    assert entry["bytes"] == sum(f["bytes"] for f in entry["files"]) - sum(
        k["bytes"] for k in entry["kept"]
    )
    # Nothing mixed again for it, nothing left to do.
    made = (folder / "mix.m4a").stat().st_mtime_ns
    assert mixing.processing_path(data, session_id) == folder / "mix.m4a"
    assert (folder / "mix.m4a").stat().st_mtime_ns == made
    assert lossless.pending(data) == []


def test_an_older_listening_mix_the_same_as_the_mix_goes_at_start(
    data: DataDir, monkeypatch: pytest.MonkeyPatch
) -> None:
    with monkeypatch.context() as before:
        before.setattr(lossless, "mp4_available", lambda: "avant l'ADR 0073")
        meeting = recorded(data, tone(1.0, 0.3), tone(1.0, 0.1))
        mixing.processing_path(data, meeting)
        heard_like_the_mix(data, meeting)
        lossless.convert_session(data, meeting)
    # In raw FLAC, both stay: the mix will still move into an MP4.
    assert "listening.flac" in names(data, meeting) and "mix.flac" in names(data, meeting)

    lossless.migrate(data)

    assert names(data, meeting) == ["mix.json", "mix.m4a", "ref.m4a", "system.m4a"]
    facts = mixing.read_facts(data, meeting)
    assert facts is not None and facts.listening_mix is not None
    assert facts.listening_mix.file == facts.file == "mix.m4a"
    assert lossless.pending(data) == [] and lossless.rewrap_pending(data) == []


def test_a_listening_mix_left_beside_the_mix_it_equals_goes_once_proven(
    data: DataDir,
) -> None:
    session_id = recorded(data, tone(1.0, 0.3), tone(1.0, 0.1))
    mixing.processing_path(data, session_id)
    heard_like_the_mix(data, session_id)
    lossless.convert_session(data, session_id)
    folder = data.sources_dir(session_id)
    # The service stopped once `mix.json` named the mix's file, before the other went.
    (folder / "listening.m4a").write_bytes((folder / "mix.m4a").read_bytes())
    assert lossless.pending(data) == [session_id]

    lossless.convert_session(data, session_id)

    assert names(data, session_id) == ["mix.json", "mix.m4a", "ref.m4a", "system.m4a"]
    assert lossless.pending(data) == []


def test_a_listening_mix_of_its_own_stays(data: DataDir) -> None:
    session_id = recorded(data, tone(1.0, 0.3), tone(1.0, 0.1))
    mixing.processing_path(data, session_id)
    lossless.convert_session(data, session_id)
    facts = mixing.read_facts(data, session_id)
    assert facts is not None and facts.listening_mix is not None
    assert facts.listening_mix.pcm_sha256 != facts.pcm_sha256
    assert "listening.m4a" in names(data, session_id)


def test_a_listening_mix_heard_from_the_mix_follows_it_into_an_mp4(
    data: DataDir, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Heard from the mix's raw FLAC (as `mix.json` may say): the mix moves, it follows."""
    meeting = older(data, monkeypatch, True)
    folder = data.sources_dir(meeting)
    facts = mixing.read_facts(data, meeting)
    assert facts is not None and facts.listening_mix is not None
    (folder / facts.listening_mix.file).unlink()
    heard = facts.listening_mix.model_copy(
        update={"file": facts.file, "sha256": facts.sha256, "pcm_sha256": facts.pcm_sha256}
    )
    mixing.write_facts(data, meeting, facts.model_copy(update={"listening_mix": heard}))

    assert lossless.rewrap_all(data, lambda line: None) == 0

    after = mixing.read_facts(data, meeting)
    assert after is not None and after.listening_mix is not None
    assert (after.file, after.listening_mix.file) == ("mix.m4a", "mix.m4a")
    assert after.listening_mix.sha256 == after.sha256
    assert names(data, meeting) == ["mix.json", "mix.m4a", "ref.m4a", "system.m4a"]
    made = (folder / "mix.m4a").stat().st_mtime_ns
    assert mixing.processing_path(data, meeting) == folder / "mix.m4a"
    assert (folder / "mix.m4a").stat().st_mtime_ns == made
    assert not (folder / mixing.LISTENING_FILE).exists()  # nothing made again
