"""The tracks recorded in the application, kept in FLAC once the recording is over, without
loss (ADR 0046).

While recording, nothing changes: a WAV kept up to date, repaired after a crash (ADR 0027).
Once a recording is over and its mixes made, each track it holds (the microphones, the
computer's sound, the mix the engine hears, the listening mix) is encoded in FLAC beside
it, forced onto the disk, read back whole: its rate, channels and 24 bits must be the WAV's,
and the fingerprint of the samples decoded from it that of the WAV's samples. Only then
does the FLAC take its name, the base (or `mix.json`) say so, and the WAV go, once both are
proven again to hold those samples. Otherwise the WAV stays, and the problem is logged and
written in the journal (P8). Each conversion is in the journal (ADR 0029): the WAV files
removed with their fingerprints, what was kept, the room freed.

Never while a processing of the session waits or runs (it reads the tracks): it is done
after. A conversion holds the session's lock (`mixing.session_lock`), which the processing
takes to read its input, and checks under the base's write lock that the audio was not
removed meanwhile. Imported files are never converted (spec §7.2), nor recordings made
before ADR 0046 (they have no fingerprint of their samples), nor recordings recovered after
a crash: converting those is the user's decision.

Interrupted (the service stopped, the Mac crashed), a conversion is taken up again at the
next start: every step leaves the WAV, or a FLAC proven identical, in place.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import shutil
import sqlite3
import subprocess
import tempfile
import threading
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from coulisses_app import disk, mixing, sessions, wav
from coulisses_app.paths import DataDir
from coulisses_app.storage.db import connect, now_iso

log = logging.getLogger(__name__)

SUFFIX = ".flac"
CODEC = "flac"
WAV_CODEC = "pcm_s24le"
"""What a recording is in until kept in FLAC (`sessions.start_capture`)."""
MEDIA_TYPE = "audio/flac"
"""What the session's page is served (Python would say `audio/x-flac`)."""
COMPRESSION_LEVEL = 5
"""ffmpeg's default: level 8 saves 0.1 % more, measured on a real recording (ADR 0046)."""

_running: set[str] = set()
_running_lock = threading.Lock()


class ConversionError(RuntimeError):
    """A track could not be converted: its WAV stays. The message is in French."""


@dataclass(frozen=True)
class Converted:
    wav: Path
    wav_bytes: int
    wav_sha256: str
    pcm_sha256: str
    flac: Path
    flac_bytes: int


def busy(session_id: str) -> bool:
    """A conversion of this session runs: its files must not go meanwhile."""
    with _running_lock:
        return session_id in _running


# -- one file -------------------------------------------------------------------------------


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        while chunk := f.read(1 << 20):
            digest.update(chunk)
    return digest.hexdigest()


def decoded_pcm_sha256(path: Path) -> str:
    """The fingerprint of the samples ffmpeg decodes from `path`, as 24-bit little-endian
    interleaved PCM: comparable with `wav.pcm_sha256` of a Coulisses WAV."""
    command = [
        *("ffmpeg", "-nostdin", "-v", "error", "-i", str(path), "-map", "0:a:0"),
        *("-c:a", "pcm_s24le", "-f", "s24le", "pipe:1"),
    ]
    digest = hashlib.sha256()
    # Its errors to a file, never a pipe: a damaged file can say more than a pipe holds,
    # and ffmpeg would then wait while this reads its output.
    with tempfile.TemporaryFile() as errors:
        with subprocess.Popen(command, stdout=subprocess.PIPE, stderr=errors) as process:
            assert process.stdout is not None
            while chunk := process.stdout.read(1 << 20):
                digest.update(chunk)
        if process.returncode != 0:
            errors.seek(0)
            said = errors.read().decode(errors="replace").strip()
            raise ConversionError(f"ffmpeg n'a pas pu relire {path.name} : {said}")
    return digest.hexdigest()


def _described(path: Path) -> tuple[int, int, int]:
    """(rate, channels, bits) of the audio in `path`, as ffprobe reads it."""
    done = subprocess.run(
        [
            *("ffprobe", "-v", "error", "-select_streams", "a:0", "-of", "json"),
            *("-show_entries", "stream=sample_rate,channels,bits_per_raw_sample", str(path)),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    try:
        stream = json.loads(done.stdout)["streams"][0]
        return (
            int(stream["sample_rate"]),
            int(stream["channels"]),
            int(stream["bits_per_raw_sample"]),
        )
    except (ValueError, KeyError, IndexError) as exc:
        raise ConversionError(
            f"ffprobe ne décrit pas {path.name} : {done.stderr.strip() or exc}"
        ) from exc


def _encode(source: Path, target: Path) -> None:
    done = subprocess.run(
        [
            *("ffmpeg", "-nostdin", "-v", "error", "-i", str(source), "-map", "0:a:0"),
            *("-map_metadata", "-1", "-c:a", "flac", "-compression_level"),
            *(str(COMPRESSION_LEVEL), "-f", "flac", str(target)),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if done.returncode != 0:
        raise ConversionError(
            f"ffmpeg n'a pas pu encoder {source.name} en FLAC : {done.stderr.strip()}"
        )


def _prove(flac: Path, rate: int, channels: int, samples: str, source: Path) -> None:
    """`flac` holds the very samples of `source`, as it was recorded: ConversionError if
    not."""
    if _described(flac) != (rate, channels, 8 * wav.SAMPLE_BYTES):
        raise ConversionError(
            f"Le FLAC de {source.name} n'a pas la fréquence, les canaux ou les 24 bits du "
            "WAV : le WAV est gardé."
        )
    if decoded_pcm_sha256(flac) != samples:
        raise ConversionError(
            f"Le FLAC de {source.name} ne rend pas les mêmes échantillons : le WAV est gardé."
        )


def convert_file(source: Path, expected: str | None) -> Converted:
    """`source` (a WAV of Coulisses) kept as FLAC beside it, on the disk, once the FLAC is
    proven to hold the WAV's samples (and those recorded when it closed, `expected`). The
    WAV is not removed here. Raises `ConversionError`, `OSError` or `ValueError`: the WAV is
    then left as it is."""
    rate, channels, data_bytes = wav.layout(source)
    size = source.stat().st_size
    if size != wav.HEADER_BYTES + data_bytes:
        # A frame cut by a crash, or more than a WAV can say: what the header leaves out
        # would be lost. The WAV stays.
        raise ConversionError(
            f"{source.name} contient {size - wav.HEADER_BYTES - data_bytes} octets que son "
            "en-tête n'annonce pas : il est gardé tel quel."
        )
    samples = wav.pcm_sha256(source)
    if expected is not None and samples != expected:
        raise ConversionError(
            f"{source.name} n'a plus les échantillons enregistrés à sa fermeture : il est "
            "gardé tel quel."
        )
    target = source.with_suffix(SUFFIX)
    if target.is_file():
        # Left by a conversion interrupted after the FLAC took its name: proven again. One
        # that fails is set aside (never removed: the WAV beside it is the true one), so that
        # nothing points to it any more and it is not tried again at each start.
        try:
            _prove(target, rate, channels, samples, source)
        except ConversionError as exc:
            aside = target.with_name(target.name + ".abime")
            os.replace(target, aside)
            disk.sync_folder(target.parent)
            raise ConversionError(f"{exc} Ce FLAC est mis de côté : {aside.name}.") from exc
    else:
        partial = target.with_name(target.name + ".partiel")
        partial.unlink(missing_ok=True)
        try:
            _encode(source, partial)
            disk.sync_file(partial)  # on the disk before it takes its name, a crash or not
            _prove(partial, rate, channels, samples, source)
            os.replace(partial, target)
            disk.sync_folder(target.parent)
        finally:
            partial.unlink(missing_ok=True)
    return Converted(
        wav=source,
        wav_bytes=size,
        wav_sha256=_file_sha256(source),
        pcm_sha256=samples,
        flac=target,
        flac_bytes=target.stat().st_size,
    )


def _remove_wav(made: Converted) -> None:
    """The WAV whose FLAC took its place, removed only if both still hold those samples
    (the FLAC read back: an interruption may have left it short)."""
    rate, channels, _ = wav.layout(made.wav)
    if wav.pcm_sha256(made.wav) != made.pcm_sha256:
        raise ConversionError(
            f"{made.wav.name} n'a plus les échantillons de son FLAC : il est gardé."
        )
    _prove(made.flac, rate, channels, made.pcm_sha256, made.wav)
    made.wav.unlink()
    disk.sync_folder(made.wav.parent)


# -- a session ------------------------------------------------------------------------------


def _may_convert(data: DataDir, session_id: str) -> bool:
    """Under the base's write lock, so that a removal of the audio under way is over first
    (and one that starts after sees this conversion running): the audio is there, and no
    processing waits for it nor reads it."""
    conn = connect(data)
    try:
        conn.execute("BEGIN IMMEDIATE")
        try:
            removed = conn.execute(
                "SELECT audio_removed_at FROM session WHERE id = ?", (session_id,)
            ).fetchone()
            needed = conn.execute(
                "SELECT 1 FROM job WHERE session_id = ? AND kind = 'chain'"
                " AND state IN ('queued', 'running')",
                (session_id,),
            ).fetchone()
        finally:
            conn.rollback()
    finally:
        conn.close()
    return removed is not None and removed["audio_removed_at"] is None and needed is None


def _journal(
    data: DataDir, session_id: str, title: str | None, done: list[Converted], problems: list[str]
) -> None:
    folder = data.session_dir(session_id)
    detail = {
        "files": [
            {
                "path": str(c.wav.relative_to(folder)),
                "bytes": c.wav_bytes,
                "sha256": c.wav_sha256,
                "pcm_sha256": c.pcm_sha256,
            }
            for c in done
        ],
        # What the conversion freed: the WAV removed, less the FLAC kept in their place.
        "bytes": sum(c.wav_bytes - c.flac_bytes for c in done),
        "kept": [{"path": str(c.flac.relative_to(folder)), "bytes": c.flac_bytes} for c in done],
        "problems": problems,
    }
    conn = connect(data)
    try:
        with conn:
            conn.execute(
                "INSERT INTO deletion_log (at, kind, session_id, session_title, detail)"
                " VALUES (?, 'conversion', ?, ?, ?)",
                (now_iso(), session_id, title, json.dumps(detail, ensure_ascii=False)),
            )
    finally:
        conn.close()


def convert_session(data: DataDir, session_id: str) -> list[Converted] | None:
    """Converts what is left to convert in this session; None when it is not the time (a
    processing waits or runs, a recording runs, the audio is gone). Problems are logged and
    written in the journal, never raised."""
    with mixing.session_lock(session_id):
        with _running_lock:
            _running.add(session_id)
        try:
            return _convert_session(data, session_id)
        finally:
            with _running_lock:
                _running.discard(session_id)


def _convert_session(data: DataDir, session_id: str) -> list[Converted] | None:
    if not _may_convert(data, session_id):
        return None
    session = sessions.get_session(data, session_id)
    if session is None:
        return None
    tracks = [
        s
        for s in [
            sessions.reference_source(data, session_id),
            *sessions.other_sources(data, session_id),
        ]
        if s is not None and s.origin == "captured" and s.pcm_sha256 is not None
    ]
    if not tracks:  # an import, or a recording made before ADR 0046
        return None
    # Still recording; or recovered after a crash (ADR 0027): its last frame may be cut, and
    # it is processed only when the user asks; it stays in WAV, as it was found.
    if any(s.capture_state != "complete" for s in tracks):
        return None
    folder = data.sources_dir(session_id)
    done: list[Converted] = []
    problems: list[str] = []

    def attempt(what: str, step: Callable[[], None]) -> None:
        try:
            step()
        except (ConversionError, OSError, ValueError, sqlite3.Error) as exc:
            log.error("converting %s of %s: %s", what, session_id, exc)
            problems.append(str(exc) if isinstance(exc, ConversionError) else f"{what} : {exc}")

    for track in tracks:
        wav_path = (folder / track.file_name).with_suffix(".wav")
        if wav_path.is_file():
            attempt(wav_path.name, _track_step(data, session_id, track, wav_path, done))
    if mixing.read_facts(data, session_id) is not None:
        attempt("le mix", lambda: _convert_mix(data, session_id, done))
        attempt("le mix d'écoute", lambda: _convert_listening(data, session_id, done))
    if done or problems:
        _journal(data, session_id, session.title, done, problems)
    if done:
        log.info(
            "%s: %d tracks kept in FLAC, %d bytes freed",
            session_id,
            len(done),
            sum(c.wav_bytes - c.flac_bytes for c in done),
        )
    return done


def _track_step(
    data: DataDir, session_id: str, track: sessions.AudioSource, source: Path, done: list[Converted]
) -> Callable[[], None]:
    return lambda: _convert_track(data, session_id, track, source, done)


def _convert_track(
    data: DataDir, session_id: str, track: sessions.AudioSource, source: Path, done: list[Converted]
) -> None:
    assert track.pcm_sha256 is not None
    try:
        made = convert_file(source, track.pcm_sha256)
    except ConversionError:
        if track.file_name != source.name and not (source.parent / track.file_name).exists():
            # The base named a FLAC set aside: it names the WAV again, the true one.
            sessions.mark_converted(
                data,
                session_id,
                track.source_id,
                file_name=source.name,
                sha256=_file_sha256(source),
                size_bytes=source.stat().st_size,
                codec=WAV_CODEC,
            )
        raise
    # Written each time, the name the same or not: a FLAC made again has its own fingerprint.
    marked = sessions.mark_converted(
        data,
        session_id,
        track.source_id,
        file_name=made.flac.name,
        sha256=_file_sha256(made.flac),
        size_bytes=made.flac_bytes,
        codec=CODEC,
    )
    if not marked:  # the audio was removed meanwhile: nothing of it is kept
        made.flac.unlink(missing_ok=True)
        raise ConversionError(
            f"L'audio a été supprimé pendant que {source.name} était converti : son FLAC "
            "est retiré aussi."
        )
    _remove_wav(made)
    done.append(made)


def _convert_mix(data: DataDir, session_id: str, done: list[Converted]) -> None:
    """The mix the engine hears, kept in FLAC; `mix.json` names it (the fingerprint of its
    samples does not change, nor what it was made from)."""
    facts = mixing.read_facts(data, session_id)
    if facts is None:
        return
    plain = (data.sources_dir(session_id) / facts.file).with_suffix(".wav")
    if not plain.is_file():
        return
    try:
        made = convert_file(plain, facts.pcm_sha256)
    except ConversionError:
        if facts.file != plain.name and not (plain.parent / facts.file).exists():
            back = {"file": plain.name, "sha256": _file_sha256(plain)}
            mixing.write_facts(data, session_id, facts.model_copy(update=back))
        raise
    update = {
        "file": made.flac.name,
        "sha256": _file_sha256(made.flac),
        "pcm_sha256": made.pcm_sha256,
    }
    mixing.write_facts(data, session_id, facts.model_copy(update=update))
    _remove_wav(made)
    done.append(made)


def _convert_listening(data: DataDir, session_id: str, done: list[Converted]) -> None:
    facts = mixing.read_facts(data, session_id)
    if facts is None or facts.listening_mix is None:
        return
    heard = facts.listening_mix
    path = (data.sources_dir(session_id) / heard.file).with_suffix(".wav")
    if not path.is_file():
        return
    try:
        made = convert_file(path, heard.pcm_sha256)
    except ConversionError:
        if heard.file != path.name and not (path.parent / heard.file).exists():
            back = heard.model_copy(update={"file": path.name, "sha256": _file_sha256(path)})
            mixing.write_facts(data, session_id, facts.model_copy(update={"listening_mix": back}))
        raise
    update = {
        "file": made.flac.name,
        "sha256": _file_sha256(made.flac),
        "pcm_sha256": made.pcm_sha256,
    }
    listening_mix = heard.model_copy(update=update)
    mixing.write_facts(data, session_id, facts.model_copy(update={"listening_mix": listening_mix}))
    _remove_wav(made)
    done.append(made)


# -- when -----------------------------------------------------------------------------------


def available() -> str | None:
    """Why no conversion can be made here, or None: ffmpeg must write FLAC, and read it and
    the WAV back as 24-bit PCM to prove it (`decoded_pcm_sha256`). Without one of them, each
    recording would end with a conversion error; the tracks stay in WAV, the log says why."""
    found = shutil.which("ffmpeg")
    if found is None:
        return "ffmpeg est introuvable"
    for listing, needed in (
        ("-encoders", (("flac", "l'encodeur FLAC"), (WAV_CODEC, "l'encodeur PCM 24 bits"))),
        ("-muxers", (("flac", "le format FLAC"), ("s24le", "le format PCM 24 bits"))),
        ("-decoders", (("flac", "le décodeur FLAC"), (WAV_CODEC, "le décodeur PCM 24 bits"))),
    ):
        listed = subprocess.run(
            [found, "-hide_banner", listing], capture_output=True, text=True, check=False
        )
        names = {line.split()[1] for line in listed.stdout.splitlines() if len(line.split()) > 1}
        for key, name in needed:
            if key not in names:
                return f"le ffmpeg de cette app n'a pas {name}"
    return None


def _in_background(name: str, work: Callable[[], object]) -> None:
    def run() -> None:
        missing = available()
        if missing is not None:
            # Nothing removed: the tracks stay in WAV, and the service's log says why.
            log.warning("tracks kept in WAV: %s", missing)
            return
        try:
            work()
        except Exception:
            log.exception("conversion in FLAC (%s)", name)

    threading.Thread(target=run, name=name, daemon=True).start()


def after_recording(data: DataDir, session_id: str) -> None:
    """Once a recording stopped: its mixes made (if any), then its tracks converted,
    unless a processing waits for them (it is then done after the processing)."""

    def work() -> None:
        try:
            mixing.processing_input(data, session_id)
        except mixing.MixError as exc:  # said on the session's page; the tracks still go
            log.warning("mix of %s before conversion: %s", session_id, exc)
        convert_session(data, session_id)

    _in_background(f"flac-{session_id}", work)


def after_processing(data: DataDir, session_id: str) -> None:
    _in_background(f"flac-{session_id}", lambda: convert_session(data, session_id))


def pending(data: DataDir) -> list[str]:
    """The sessions recorded since ADR 0046 where a conversion was cut short (a WAV beside
    its FLAC, a FLAC half written). The others are converted after their recording or
    their processing, never at start: a problem is then not written again at each start."""
    conn = connect(data)
    try:
        rows = conn.execute(
            "SELECT DISTINCT session_id FROM audio_source WHERE origin = 'captured'"
            " AND pcm_sha256 IS NOT NULL AND removed_at IS NULL ORDER BY session_id"
        ).fetchall()
    finally:
        conn.close()
    found: list[str] = []
    for row in rows:
        folder = data.sources_dir(row["session_id"])
        names: set[str] = {p.name for p in folder.iterdir()} if folder.is_dir() else set()
        cut_short = any(n.endswith(SUFFIX + ".partiel") for n in names) or any(
            n.endswith(".wav") and n[: -len(".wav")] + SUFFIX in names for n in names
        )
        if cut_short:
            found.append(str(row["session_id"]))
    return found


def at_start(data: DataDir) -> None:
    """At the service's start: what an interruption left half done is taken up again."""

    def work() -> None:
        for session_id in pending(data):
            convert_session(data, session_id)

    _in_background("flac-start", work)
