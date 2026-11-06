"""The tracks recorded in the application, kept in FLAC once the recording is over, without
loss (ADR 0046), in an MP4 (ADR 0074).

While recording, nothing changes: a WAV kept up to date, repaired after a crash (ADR 0027).
Once a recording is over and its mixes made, each track it holds (the microphones, the
computer's sound, the mix the engine hears, the listening mix) is encoded in FLAC beside
it, forced onto the disk, read back whole: its rate, channels and 24 bits must be the WAV's,
and the fingerprint of the samples decoded from it that of the WAV's samples. Only then
does the FLAC take its name, the base (or `mix.json`) say so, and the WAV go, once both are
proven again to hold those samples. Otherwise the WAV stays, and the problem is logged and
written in the journal (P8). Each conversion is in the journal (ADR 0029): the files
removed with their fingerprints, what was kept, the room freed.

The FLAC is put in an MP4 (`.m4a`), one file for each sound: in a raw FLAC, the page's
player (WebKit) lands seconds away from where it says after a jump, so the word lit is not
the word heard; in an MP4 it lands exactly (ADR 0073, 0074). The engine reads it through ffmpeg
as any other file. With an ffmpeg that does not write MP4, the FLAC stays raw, as before.
The tracks kept in raw FLAC before are put in an MP4 after the update, in the background
at each start until done (`migrate`, decided by the user, ADR 0074): each FLAC put in an
MP4 without encoding it again, proven, then the raw FLAC removed, the same way; the copy
heard made by version 0.38.2 removed once proven. A session that fails keeps its files and
waits for `coulisses-app --ecoute-exacte`.

Never while a processing of the session waits or runs (it reads the tracks): it is done
after. A conversion holds the session's lock (`mixing.session_lock`), which the processing
takes to read its input, and checks under the base's write lock that the audio was not
removed meanwhile. Imported files are never converted (spec §7.2), nor recordings made
before ADR 0046 (they have no fingerprint of their samples), nor recordings recovered after
a crash: converting those is the user's decision.

Interrupted (the service stopped, the Mac crashed), a conversion is taken up again at the
next start: every step leaves the file it started from, or one proven identical, in place.
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
from functools import cache
from pathlib import Path

import numpy as np

from coulisses_app import disk, mixing, sessions, wav
from coulisses_app.paths import DataDir
from coulisses_app.storage.db import connect, now_iso

log = logging.getLogger(__name__)

RAW_SUFFIX = ".flac"
"""A FLAC alone: before ADR 0073, or with an ffmpeg that does not write MP4."""
MP4_SUFFIX = ".m4a"
"""The FLAC in an MP4, where the page's player seeks exactly (ADR 0074)."""
CODEC = "flac"
"""What the base says of a track kept so, in either container."""
WAV_CODEC = "pcm_s24le"
"""What a recording is in until kept in FLAC (`sessions.start_capture`)."""
RAW_MEDIA_TYPE = "audio/flac"
"""What the session's page is served for a raw FLAC (Python would say `audio/x-flac`)."""
MP4_MEDIA_TYPE = "audio/mp4"
LISTENING_COPY = "listening-copy.m4a"
"""The copy in an MP4 of a reference kept in raw FLAC, made by version 0.38.2 for a session
without the computer's sound: heard until the reference is itself in an MP4, then removed,
proven the same (one file for each sound, ADR 0074)."""
COMPRESSION_LEVEL = 5
"""ffmpeg's default: level 8 saves 0.1 % more, measured on a real recording (ADR 0046)."""

_running: set[str] = set()
_running_lock = threading.Lock()


class ConversionError(RuntimeError):
    """A track could not be converted: the file it was made from stays. The message is in
    French."""


@dataclass(frozen=True)
class Converted:
    source: Path
    """The file removed: a WAV, or a raw FLAC put in an MP4."""
    source_bytes: int
    source_sha256: str
    pcm_sha256: str
    kept: Path
    """The FLAC kept in its place."""
    kept_bytes: int
    duplicate: bool = False
    """`source` was a second file of the sound `kept` already held (the copy heard of
    version 0.38.2): all of it freed, nothing kept in its place."""


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


def _encode(source: Path, target: Path, suffix: str) -> None:
    """`source` encoded in FLAC, or only put in another container (`-c:a copy`) when it is
    one already. An MP4 has its index first, read before the sound."""
    codec = (
        ("copy",)
        if source.suffix.lower() == RAW_SUFFIX
        else ("flac", "-compression_level", str(COMPRESSION_LEVEL))
    )
    container = ("-f", "mp4", "-movflags", "+faststart") if suffix == MP4_SUFFIX else ("-f", "flac")
    done = subprocess.run(
        [
            *("ffmpeg", "-nostdin", "-v", "error", "-i", str(source), "-map", "0:a:0"),
            *("-map_metadata", "-1", "-c:a", *codec, *container, str(target)),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if done.returncode != 0:
        raise ConversionError(
            f"ffmpeg n'a pas pu encoder {source.name} en FLAC : {done.stderr.strip()}"
        )


@cache
def mp4_available() -> str | None:
    """Why the FLAC cannot be put in an MP4 here, or None. Tried for real, once per
    service: some ffmpeg write MP4, but not FLAC in it."""
    found = shutil.which("ffmpeg")
    if found is None:
        return "ffmpeg est introuvable"
    listed = subprocess.run(
        [found, "-hide_banner", "-muxers"], capture_output=True, text=True, check=False
    )
    names = {line.split()[1] for line in listed.stdout.splitlines() if len(line.split()) > 1}
    if "mp4" not in names:
        return "le ffmpeg de cette app n'écrit pas de MP4"
    with tempfile.TemporaryDirectory(prefix="coulisses-mp4-") as work:
        sample = Path(work) / "essai.wav"
        writer = wav.WavWriter(sample, 48_000, 1)
        writer.write(np.zeros((4_800, 1), dtype=np.float32))
        writer.close()
        try:
            _encode(sample, Path(work) / "essai.m4a", MP4_SUFFIX)
            if decoded_pcm_sha256(Path(work) / "essai.m4a") != wav.pcm_sha256(sample):
                return "le ffmpeg de cette app ne rend pas le FLAC mis dans un MP4"
        except ConversionError as exc:
            return f"le ffmpeg de cette app ne met pas de FLAC dans un MP4 ({exc})"
    return None


def kept_suffix() -> str:
    """How a track is kept here: in an MP4 when ffmpeg writes one (ADR 0074)."""
    return MP4_SUFFIX if mp4_available() is None else RAW_SUFFIX


def media_type(path: Path) -> str | None:
    """What the session's page is served for a track kept in FLAC; None for another file."""
    return {RAW_SUFFIX: RAW_MEDIA_TYPE, MP4_SUFFIX: MP4_MEDIA_TYPE}.get(path.suffix.lower())


def heard_path(data: DataDir, session_id: str) -> Path | None:
    """What the session's page plays: `mixing.listening_path`, or the copy in an MP4 of a
    reference still kept in raw FLAC, while there is one."""
    path = mixing.listening_path(data, session_id)
    if path is None or path.suffix.lower() != RAW_SUFFIX:
        return path
    copy = path.parent / LISTENING_COPY
    if copy.is_file() and path == sessions.reference_audio_path(data, session_id):
        return copy
    return path


def _layout(source: Path) -> tuple[int, int, str]:
    """(rate, channels, the fingerprint of its samples) of a WAV of Coulisses or a FLAC of
    24 bits. Raises `ConversionError` for what cannot be kept without loss."""
    if source.suffix.lower() == ".wav":
        rate, channels, data_bytes = wav.layout(source)
        size = source.stat().st_size
        if size != wav.HEADER_BYTES + data_bytes:
            # A frame cut by a crash, or more than a WAV can say: what the header leaves
            # out would be lost. The WAV stays.
            raise ConversionError(
                f"{source.name} contient {size - wav.HEADER_BYTES - data_bytes} octets que "
                "son en-tête n'annonce pas : il est gardé tel quel."
            )
        return rate, channels, wav.pcm_sha256(source)
    rate, channels, bits = _described(source)
    if bits != 8 * wav.SAMPLE_BYTES:
        raise ConversionError(f"{source.name} n'est pas en 24 bits : il est gardé tel quel.")
    return rate, channels, decoded_pcm_sha256(source)


def _prove(kept: Path, rate: int, channels: int, samples: str, source: Path) -> None:
    """`kept` holds the very samples of `source`, as it was recorded: ConversionError if
    not."""
    if _described(kept) != (rate, channels, 8 * wav.SAMPLE_BYTES):
        raise ConversionError(
            f"Le FLAC de {source.name} n'a pas la fréquence, les canaux ou les 24 bits de "
            f"{source.name} : {source.name} est gardé."
        )
    if decoded_pcm_sha256(kept) != samples:
        raise ConversionError(
            f"Le FLAC de {source.name} ne rend pas les mêmes échantillons : {source.name} est "
            "gardé."
        )


def convert_file(source: Path, expected: str | None, suffix: str | None = None) -> Converted:
    """`source` (a WAV of Coulisses, or a raw FLAC) kept as FLAC beside it (`kept_suffix`
    unless said), on the disk, once proven to hold its samples (and those recorded when it
    closed, `expected`). `source` is not removed here. Raises `ConversionError`, `OSError`
    or `ValueError`: `source` is then left as it is."""
    suffix = suffix or kept_suffix()
    rate, channels, samples = _layout(source)
    if expected is not None and samples != expected:
        raise ConversionError(
            f"{source.name} n'a plus les échantillons enregistrés à sa fermeture : il est "
            "gardé tel quel."
        )
    target = source.with_suffix(suffix)
    if target.is_file():
        # Left by a conversion interrupted after the FLAC took its name: proven again. One
        # that fails is set aside (never removed: the file beside it is the true one), so
        # that nothing points to it any more and it is not tried again at each start.
        try:
            _prove(target, rate, channels, samples, source)
        except ConversionError as exc:
            aside = target.with_name(target.name + ".abime")
            os.replace(target, aside)
            disk.sync_folder(target.parent)
            raise ConversionError(f"{exc} Ce FLAC est mis de côté : {aside.name}.") from exc
    else:
        partial = _partial(target)
        partial.unlink(missing_ok=True)
        try:
            _encode(source, partial, suffix)
            disk.sync_file(partial)  # on the disk before it takes its name, a crash or not
            _prove(partial, rate, channels, samples, source)
            os.replace(partial, target)
            disk.sync_folder(target.parent)
        finally:
            partial.unlink(missing_ok=True)
    return Converted(
        source=source,
        source_bytes=source.stat().st_size,
        source_sha256=_file_sha256(source),
        pcm_sha256=samples,
        kept=target,
        kept_bytes=target.stat().st_size,
    )


def _partial(target: Path) -> Path:
    return target.with_name(target.name + ".partiel")


def _remove_source(made: Converted) -> None:
    """The file whose FLAC took its place, removed only if both still hold those samples
    (the FLAC read back: an interruption may have left it short)."""
    rate, channels, samples = _layout(made.source)
    if samples != made.pcm_sha256:
        raise ConversionError(
            f"{made.source.name} n'a plus les échantillons de son FLAC : il est gardé."
        )
    _prove(made.kept, rate, channels, made.pcm_sha256, made.source)
    made.source.unlink()
    disk.sync_folder(made.source.parent)


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
                "path": str(c.source.relative_to(folder)),
                "bytes": c.source_bytes,
                "sha256": c.source_sha256,
                "pcm_sha256": c.pcm_sha256,
            }
            for c in done
        ],
        # What the conversion freed: the files removed, less the FLAC kept in their place.
        "bytes": sum(c.source_bytes - (0 if c.duplicate else c.kept_bytes) for c in done),
        "kept": [
            {"path": str(c.kept.relative_to(folder)), "bytes": c.kept_bytes}
            for c in done
            if not c.duplicate
        ],
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


def convert_session(
    data: DataDir, session_id: str, *, rewrap: bool = False
) -> list[Converted] | None:
    """Converts what is left to convert in this session; None when it is not the time (a
    processing waits or runs, a recording runs, the audio is gone). `rewrap`: its tracks
    kept in raw FLAC are put in an MP4 too (asked by the user, ADR 0046). Problems are
    logged and written in the journal, never raised."""
    found = _convert(data, session_id, rewrap)
    return None if found is None else found[0]


def _convert(
    data: DataDir, session_id: str, rewrap: bool
) -> tuple[list[Converted], list[str]] | None:
    with mixing.session_lock(session_id):
        with _running_lock:
            _running.add(session_id)
        try:
            return _convert_session(data, session_id, rewrap)
        finally:
            with _running_lock:
                _running.discard(session_id)


def _source_of(folder: Path, name: str, rewrap: bool) -> Path | None:
    """The file to keep in FLAC for the track named `name`: its WAV; or, kept in raw FLAC
    while ffmpeg writes MP4, its raw FLAC when asked (`rewrap`) or when its putting in an
    MP4 was begun (the service stopped meanwhile)."""
    stem = folder / Path(name).stem
    if stem.with_suffix(".wav").is_file():
        return stem.with_suffix(".wav")
    raw, target = stem.with_suffix(RAW_SUFFIX), stem.with_suffix(MP4_SUFFIX)
    if not raw.is_file() or kept_suffix() != MP4_SUFFIX:
        return None
    if rewrap or target.is_file() or _partial(target).is_file():
        return raw
    return None


def _convert_session(
    data: DataDir, session_id: str, rewrap: bool
) -> tuple[list[Converted], list[str]] | None:
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
        source = _source_of(folder, track.file_name, rewrap)
        if source is not None:
            attempt(source.name, _track_step(data, session_id, track, source, done))
    if mixing.read_facts(data, session_id) is not None:
        attempt("le mix", lambda: _convert_mix(data, session_id, rewrap, done))
        attempt("le mix d'écoute", lambda: _convert_listening(data, session_id, rewrap, done))
        if _same_listening(data, session_id) is not None:
            attempt("le mix d'écoute", lambda: _drop_same_listening(data, session_id, done))
    if (folder / LISTENING_COPY).is_file():
        attempt("la copie d'écoute", lambda: _drop_copy(data, session_id, done))
    unfinished = _partial(folder / LISTENING_COPY)
    if unfinished.is_file():
        # Left by version 0.38.2 cut short: never finished, never heard, nothing of the
        # sound in it that the reference does not hold. Said in the service's log.
        attempt("la copie d'écoute inachevée", unfinished.unlink)
        if not unfinished.exists():
            log.info("%s: %s cut short, removed", session_id, unfinished.name)
    if done or problems:
        _journal(data, session_id, session.title, done, problems)
    if done:
        log.info(
            "%s: %d tracks kept in FLAC, %d bytes freed",
            session_id,
            sum(1 for c in done if not c.duplicate),
            sum(c.source_bytes - (0 if c.duplicate else c.kept_bytes) for c in done),
        )
    return done, problems


def _track_step(
    data: DataDir, session_id: str, track: sessions.AudioSource, source: Path, done: list[Converted]
) -> Callable[[], None]:
    return lambda: _convert_track(data, session_id, track, source, done)


def _codec_of(path: Path) -> str:
    return WAV_CODEC if path.suffix.lower() == ".wav" else CODEC


def _convert_track(
    data: DataDir, session_id: str, track: sessions.AudioSource, source: Path, done: list[Converted]
) -> None:
    assert track.pcm_sha256 is not None
    try:
        made = convert_file(source, track.pcm_sha256)
    except ConversionError:
        if track.file_name != source.name and not (source.parent / track.file_name).exists():
            # The base named a FLAC set aside: it names the file kept again, the true one.
            sessions.mark_converted(
                data,
                session_id,
                track.source_id,
                file_name=source.name,
                sha256=_file_sha256(source),
                size_bytes=source.stat().st_size,
                codec=_codec_of(source),
            )
        raise
    # Written each time, the name the same or not: a FLAC made again has its own fingerprint.
    marked = sessions.mark_converted(
        data,
        session_id,
        track.source_id,
        file_name=made.kept.name,
        sha256=_file_sha256(made.kept),
        size_bytes=made.kept_bytes,
        codec=CODEC,
    )
    if not marked:  # the audio was removed meanwhile: nothing of it is kept
        made.kept.unlink(missing_ok=True)
        raise ConversionError(
            f"L'audio a été supprimé pendant que {source.name} était converti : son FLAC "
            "est retiré aussi."
        )
    _remove_source(made)
    done.append(made)


def _convert_mix(data: DataDir, session_id: str, rewrap: bool, done: list[Converted]) -> None:
    """The mix the engine hears, kept in FLAC; `mix.json` names it (the fingerprint of its
    samples does not change, nor what it was made from)."""
    facts = mixing.read_facts(data, session_id)
    if facts is None:
        return
    plain = _source_of(data.sources_dir(session_id), facts.file, rewrap)
    if plain is None:
        return
    try:
        made = convert_file(plain, facts.pcm_sha256)
    except ConversionError:
        if facts.file != plain.name and not (plain.parent / facts.file).exists():
            back: dict[str, object] = {"file": plain.name, "sha256": _file_sha256(plain)}
            if facts.listening_mix is not None and facts.listening_mix.file == facts.file:
                # Heard from the mix's file: it follows the mix back (ADR 0074).
                back["listening_mix"] = facts.listening_mix.model_copy(
                    update={"file": back["file"], "sha256": back["sha256"]}
                )
            mixing.write_facts(data, session_id, facts.model_copy(update=back))
        raise
    update: dict[str, object] = {
        "file": made.kept.name,
        "sha256": _file_sha256(made.kept),
        "pcm_sha256": made.pcm_sha256,
    }
    if facts.listening_mix is not None and facts.listening_mix.file == facts.file:
        # Heard from the mix's own file (the same sound, ADR 0074): it follows the mix.
        heard = {"file": update["file"], "sha256": update["sha256"]}
        update["listening_mix"] = facts.listening_mix.model_copy(update=heard)
    mixing.write_facts(data, session_id, facts.model_copy(update=update))
    _remove_source(made)
    done.append(made)


def _convert_listening(data: DataDir, session_id: str, rewrap: bool, done: list[Converted]) -> None:
    facts = mixing.read_facts(data, session_id)
    if facts is None or facts.listening_mix is None:
        return
    heard = facts.listening_mix
    if heard.file == facts.file:
        return  # heard from the mix's file, which the mix keeps (ADR 0074)
    path = _source_of(data.sources_dir(session_id), heard.file, rewrap)
    if path is None:
        return
    try:
        made = convert_file(path, heard.pcm_sha256)
    except ConversionError:
        if heard.file != path.name and not (path.parent / heard.file).exists():
            back = heard.model_copy(update={"file": path.name, "sha256": _file_sha256(path)})
            mixing.write_facts(data, session_id, facts.model_copy(update={"listening_mix": back}))
        raise
    update = {
        "file": made.kept.name,
        "sha256": _file_sha256(made.kept),
        "pcm_sha256": made.pcm_sha256,
    }
    listening_mix = heard.model_copy(update=update)
    mixing.write_facts(data, session_id, facts.model_copy(update={"listening_mix": listening_mix}))
    _remove_source(made)
    done.append(made)


def _same_listening(data: DataDir, session_id: str) -> Path | None:
    """The file of a listening mix that gives the very samples of the mix (the microphone
    never turned down, ADR 0037), kept beside it: a second file of the same sound. Also the
    one left once `mix.json` named the mix's file (the service stopped between). Read
    only."""
    facts = mixing.read_facts(data, session_id)
    if facts is None or facts.listening_mix is None or facts.pcm_sha256 is None:
        return None
    heard = facts.listening_mix
    folder = data.sources_dir(session_id)
    # Once the mix is in an MP4, its last form: never a file a later step would move.
    if Path(facts.file).suffix.lower() != MP4_SUFFIX:
        return None
    if not (folder / facts.file).is_file() or heard.pcm_sha256 != facts.pcm_sha256:
        return None
    if heard.file != facts.file:
        named = folder / heard.file
        same_kind = named.suffix.lower() == Path(facts.file).suffix.lower()
        return named if same_kind and named.is_file() else None
    left = (folder / mixing.LISTENING_FILE).with_suffix(Path(facts.file).suffix)
    return left if left.is_file() else None


def _drop_same_listening(data: DataDir, session_id: str, done: list[Converted]) -> None:
    """The listening mix the same sound as the mix: `mix.json` has it heard from the mix's
    file, then its own file goes, once both are proven to hold those samples (ADR 0074)."""
    facts = mixing.read_facts(data, session_id)
    heard = _same_listening(data, session_id)
    if facts is None or facts.listening_mix is None or heard is None:
        return
    folder = data.sources_dir(session_id)
    kept = folder / facts.file
    rate, channels, samples = _layout(heard)
    if samples != facts.pcm_sha256:
        raise ConversionError(
            f"{heard.name} ne rend pas les échantillons de {kept.name} : il est gardé."
        )
    _prove(kept, rate, channels, samples, heard)
    made = Converted(
        source=heard,
        source_bytes=heard.stat().st_size,
        source_sha256=_file_sha256(heard),
        pcm_sha256=samples,
        kept=kept,
        kept_bytes=kept.stat().st_size,
        duplicate=True,
    )
    if facts.listening_mix.file != facts.file:
        update = {"file": facts.file, "sha256": facts.sha256}
        listening_mix = facts.listening_mix.model_copy(update=update)
        mixing.write_facts(
            data, session_id, facts.model_copy(update={"listening_mix": listening_mix})
        )
    heard.unlink()
    disk.sync_folder(folder)
    done.append(made)


def _drop_copy(data: DataDir, session_id: str, done: list[Converted]) -> None:
    """The copy heard of a reference now itself in an MP4: a second file of the same sound,
    removed once proven to hold the reference's samples (ADR 0074)."""
    reference = sessions.reference_source(data, session_id)
    folder = data.sources_dir(session_id)
    if reference is None or Path(reference.file_name).suffix.lower() != MP4_SUFFIX:
        return  # still heard from it
    kept, copy = folder / reference.file_name, folder / LISTENING_COPY
    rate, channels, samples = _layout(copy)
    if reference.pcm_sha256 is not None and samples != reference.pcm_sha256:
        raise ConversionError(
            f"{copy.name} ne rend pas les échantillons de {kept.name} : il est gardé."
        )
    _prove(kept, rate, channels, samples, copy)
    made = Converted(
        source=copy,
        source_bytes=copy.stat().st_size,
        source_sha256=_file_sha256(copy),
        pcm_sha256=samples,
        kept=kept,
        kept_bytes=kept.stat().st_size,
        duplicate=True,
    )
    copy.unlink()
    disk.sync_folder(folder)
    done.append(made)


# -- the tracks kept in raw FLAC before (ADR 0074) ------------------------------------------

FAILED_KEY = "lossless.mp4_failed"
"""The sessions whose putting in an MP4 failed (`app_setting`, a JSON list): not tried
again at each start, only when the user asks (`rewrap_all`); the journal says why."""


def _failed(data: DataDir) -> set[str]:
    conn = connect(data)
    try:
        row = conn.execute("SELECT value FROM app_setting WHERE key = ?", (FAILED_KEY,)).fetchone()
    finally:
        conn.close()
    return set(json.loads(row[0])) if row else set()


def _set_failed(data: DataDir, session_id: str, failed: bool) -> None:
    now = _failed(data)
    changed = now | {session_id} if failed else now - {session_id}
    if changed == now:
        return
    conn = connect(data)
    try:
        with conn:
            conn.execute(
                "INSERT INTO app_setting (key, value) VALUES (?, ?)"
                " ON CONFLICT (key) DO UPDATE SET value = excluded.value",
                (FAILED_KEY, json.dumps(sorted(changed))),
            )
    finally:
        conn.close()


def _rewrap(data: DataDir, session_id: str) -> tuple[list[Converted], list[str]] | None:
    """One session put in an MP4; None when it is not the time (a processing needs it: done
    at a later start). A session with a problem is marked, not tried again by itself."""
    found = _convert(data, session_id, True)
    if found is not None:
        _set_failed(data, session_id, bool(found[1]))
    return found


def migrate(data: DataDir) -> None:
    """After the update, at each start, in the background (decided by the user, ADR 0074):
    every session kept in raw FLAC put in an MP4, one after the other, and the copies heard
    of version 0.38.2 removed, each step proven and journaled. Cut short, it goes on at the
    next start; a session that failed waits for `rewrap_all`."""
    if mp4_available() is not None:
        log.info("tracks kept in raw FLAC: %s", mp4_available())
        return
    failed = _failed(data)
    for session_id in rewrap_pending(data):
        if session_id not in failed:
            _rewrap(data, session_id)


def rewrap_pending(data: DataDir) -> list[str]:
    """The sessions with a track, a mix or a listening mix kept in raw FLAC (or a copy
    heard of one), which `rewrap_all` would put in an MP4. Read only."""
    conn = connect(data)
    try:
        rows = conn.execute(
            "SELECT DISTINCT a.session_id FROM audio_source a JOIN session s"
            " ON s.id = a.session_id WHERE a.origin = 'captured' AND a.pcm_sha256 IS NOT NULL"
            " AND a.removed_at IS NULL AND s.audio_removed_at IS NULL ORDER BY a.session_id"
        ).fetchall()
    finally:
        conn.close()
    found: list[str] = []
    for row in rows:
        session_id = str(row["session_id"])
        reference = sessions.reference_source(data, session_id)
        names = [
            s.file_name
            for s in [reference, *sessions.other_sources(data, session_id)]
            if s is not None and s.origin == "captured"
        ]
        facts = mixing.read_facts(data, session_id)
        if facts is not None:
            names.append(facts.file)
            if facts.listening_mix is not None:
                names.append(facts.listening_mix.file)
        folder = data.sources_dir(session_id)
        if (folder / LISTENING_COPY).is_file() or any(
            n.lower().endswith(RAW_SUFFIX) and (folder / n).is_file() for n in names
        ):
            found.append(session_id)
    return found


def rewrap_all(data: DataDir, say: Callable[[str], None]) -> int:
    """Every session of `rewrap_pending` put in an MP4, those that failed before too (asked
    by the user: `coulisses-app --ecoute-exacte`); each one said. Returns how many were left
    (in whole or in part) as they were."""
    missing = mp4_available()
    if missing is not None:
        say(f"Rien n'est fait : {missing}.")
        return 1
    left = 0
    for session_id in rewrap_pending(data):
        found = _rewrap(data, session_id)
        if found is None:
            left += 1
            say(
                f"{session_id} : laissée telle quelle, un traitement l'attend ou la lit : "
                "relancez la commande après lui."
            )
            continue
        done, problems = found
        say(
            f"{session_id} : "
            + (", ".join(f"{c.source.name} → {c.kept.name}" for c in done) or "rien de fait")
        )
        for problem in problems:
            say(f"{session_id} : {problem}")
        left += 1 if problems else 0
    return left


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


def _reference_in_mp4(data: DataDir, session_id: str) -> bool:
    reference = sessions.reference_source(data, session_id)
    return reference is not None and Path(reference.file_name).suffix.lower() == MP4_SUFFIX


def pending(data: DataDir) -> list[str]:
    """The sessions recorded since ADR 0046 where a conversion was cut short (a WAV or a raw
    FLAC beside the FLAC kept in its place, a FLAC half written). The others are converted
    after their recording or their processing, never at start: a problem is then not
    written again at each start."""
    conn = connect(data)
    try:
        rows = conn.execute(
            "SELECT DISTINCT session_id FROM audio_source WHERE origin = 'captured'"
            " AND pcm_sha256 IS NOT NULL AND removed_at IS NULL ORDER BY session_id"
        ).fetchall()
    finally:
        conn.close()
    kept = (RAW_SUFFIX, MP4_SUFFIX)
    found: list[str] = []
    for row in rows:
        folder = data.sources_dir(row["session_id"])
        names: set[str] = {p.name for p in folder.iterdir()} if folder.is_dir() else set()
        stems = {n.rsplit(".", 1)[0] for n in names if n.endswith(MP4_SUFFIX)}
        cut_short = (
            any(n.endswith(suffix + ".partiel") for n in names for suffix in kept)
            or any(
                n.endswith(".wav") and n[: -len(".wav")] + suffix in names
                for n in names
                for suffix in kept
            )
            or any(n.endswith(RAW_SUFFIX) and n[: -len(RAW_SUFFIX)] in stems for n in names)
            # The copy heard of version 0.38.2, unfinished, or beside its reference now in an
            # MP4 (a second file of the same sound, ADR 0074).
            or LISTENING_COPY + ".partiel" in names
            or (LISTENING_COPY in names and _reference_in_mp4(data, row["session_id"]))
            # A listening mix kept beside the mix it equals (ADR 0074).
            or _same_listening(data, row["session_id"]) is not None
        )
        if cut_short:
            found.append(str(row["session_id"]))
    return found


def at_start(data: DataDir) -> None:
    """At the service's start: what an interruption left half done is taken up again, then
    the sessions kept in raw FLAC before are put in an MP4 (`migrate`)."""

    def work() -> None:
        for session_id in pending(data):
            convert_session(data, session_id)
        migrate(data)  # the sessions kept in raw FLAC before (ADR 0074)

    _in_background("flac-start", work)
