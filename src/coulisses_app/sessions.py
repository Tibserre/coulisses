"""Sessions: import of a recording, listing, reading (ADR 0006, 0018)."""

from __future__ import annotations

import hashlib
import logging
import secrets
import shutil
import sqlite3
import string
from datetime import UTC, datetime
from pathlib import Path
from typing import BinaryIO

from pydantic import BaseModel

from coulisses_app import jobs, projects, retention, spaces, wav
from coulisses_app.media import probe
from coulisses_app.paths import DataDir
from coulisses_app.storage.db import connect, now_iso

log = logging.getLogger(__name__)

REFERENCE_SOURCE_ID = "ref"
"""The single source of V1, named as the engine names it in its outputs (ADR 0006)."""

_ID_ALPHABET = string.ascii_lowercase + string.digits
_CHUNK = 1024 * 1024


class AudioSource(BaseModel):
    source_id: str
    origin: str
    original_name: str
    file_name: str
    sha256: str
    size_bytes: int
    duration_s: float | None
    sample_rate: int | None
    channels: int | None
    codec: str | None
    file_present: bool
    capture_state: str | None = None
    """For a recording made in the application: recording, complete or recovered."""
    device: str | None = None
    pcm_sha256: str | None = None
    """The fingerprint of its samples, whatever its format (ADR 0046): set for a recording
    made in the application since then; None for an import or an older recording."""


class Session(BaseModel):
    id: str
    title: str | None
    title_edited: bool = False
    """Written by the user: a proposed title never replaces it."""
    recorded_at: str
    created_at: str
    space_id: int
    space_name: str
    project_id: int | None = None
    """Its project in its space, or none."""
    attendee_ids: list[int]
    """People checked as present (members and guests of the session's space)."""
    unnamed_attendees: int | None
    """People present whom nobody named, in addition to the checked ones."""
    min_voices: int | None
    """Minimum of voices asked of the engine by the latest processing (P3)."""
    processing_starts_at: str | None = None
    """Its first processing waits for the people present until then (UTC), unless started
    at once; None when it does not wait, or no longer (its time passed: it starts as soon as
    the sessions ahead of it are processed)."""
    attendees_taken: bool | None = None
    """Whether the people present now are that minimum: false once checked after its
    diarization began (a rerun of the voices takes them), or when another
    number was chosen (after « too few voices », or for a rerun); None if never processed.
    Like `min_voices`, it is the latest processing's, not the version shown's."""
    reference_source_id: str
    duration_s: float | None
    job_state: str | None
    """State of the latest job: queued, running, done, failed; None if never processed."""
    job_error: str | None
    audio: retention.AudioStatus
    """Kept, removed (when, why), or when its purge is due (spec §7.10)."""


def new_session_id(when: datetime) -> str:
    """`AAAAMMJJ-HHMMSS-xxxx`, local time: stable, never derived from the title."""
    suffix = "".join(secrets.choice(_ID_ALPHABET) for _ in range(4))
    return f"{when.astimezone().strftime('%Y%m%d-%H%M%S')}-{suffix}"


def import_recording(
    data: DataDir,
    stream: BinaryIO,
    original_name: str,
    *,
    space_id: int | None = None,
    project_id: int | None = None,
    attendee_ids: list[int] | None = None,
    unnamed_attendees: int | None = None,
    recorded_at: datetime | None,
    profile: str,
    wait_for_attendees: bool = False,
) -> str:
    """Keep the file exactly as received, make it a session and queue its processing.
    `wait_for_attendees`: an import in one gesture, made with nobody present; its processing
    waits for them (`jobs.WAIT_FOR_ATTENDEES_S`, ADR 0069).

    The file is first received in `imports-en-cours/`; if ffmpeg cannot read it, that copy
    is removed and `UnreadableAudioError` says why (the user's original is untouched)."""
    if unnamed_attendees is not None and unnamed_attendees < 1:
        raise ValueError("Le nombre de présents non nommés doit être au moins 1.")
    present = list(dict.fromkeys(attendee_ids or []))
    conn = connect(data)
    try:
        space = space_id if space_id is not None else spaces.default_space_id(conn)
        spaces.get_space(conn, space)
        projects.check(conn, space, project_id)
        spaces.check_attendees(conn, space, present)
        glossary = spaces.glossary_terms(conn, space)
    finally:
        conn.close()
    minimum = spaces.attendee_minimum(len(present), unnamed_attendees)
    data.incoming.mkdir(parents=True, exist_ok=True)
    suffix = Path(original_name).suffix.lower()
    received = data.incoming / f"{secrets.token_hex(8)}{suffix}"
    digest = hashlib.sha256()
    size = 0
    try:
        with received.open("xb") as out:
            while chunk := stream.read(_CHUNK):
                digest.update(chunk)
                out.write(chunk)
                size += len(chunk)
        info = probe(received, shown_as=original_name)
    except BaseException:
        received.unlink(missing_ok=True)
        raise

    now = datetime.now(UTC)
    session_id = new_session_id(now)
    while data.session_dir(session_id).exists():
        session_id = new_session_id(now)
    session_dir = data.session_dir(session_id)
    sources = data.sources_dir(session_id)
    stored = sources / f"{REFERENCE_SOURCE_ID}{suffix}"
    stamp = now_iso()
    conn = connect(data)
    moved = False
    try:
        conn.execute("BEGIN IMMEDIATE")
        conn.execute(
            "INSERT INTO session (id, space_id, project_id, title, recorded_at, created_at,"
            " reference_source_id, unnamed_attendees)"
            " VALUES (?, ?, ?, NULL, ?, ?, ?, ?)",
            (
                session_id,
                space,
                project_id,
                (recorded_at or now).astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
                stamp,
                REFERENCE_SOURCE_ID,
                unnamed_attendees,
            ),
        )
        conn.executemany(
            "INSERT INTO attendee (session_id, person_id) VALUES (?, ?)",
            [(session_id, p) for p in present],
        )
        conn.execute(
            "INSERT INTO audio_source (session_id, source_id, origin, original_name,"
            " file_name, sha256, size_bytes, duration_s, sample_rate, channels, codec,"
            " added_at) VALUES (?, ?, 'imported', ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                session_id,
                REFERENCE_SOURCE_ID,
                original_name,
                stored.name,
                digest.hexdigest(),
                size,
                info.duration_s,
                info.sample_rate,
                info.channels,
                info.codec,
                stamp,
            ),
        )
        jobs.enqueue_chain(
            conn,
            session_id,
            profile=profile,
            attendees=minimum,
            glossary=glossary,
            wait_s=jobs.WAIT_FOR_ATTENDEES_S if wait_for_attendees else None,
        )
        sources.mkdir(parents=True)
        shutil.move(received, stored)
        moved = True
        conn.commit()
    except BaseException:
        # Nothing half-made: the database is rolled back and the copy goes back to
        # `imports-en-cours/`, where the next start reports it (`interrupted_imports`).
        conn.rollback()
        if moved:
            shutil.move(stored, received)
        for folder in (sources, session_dir):
            if folder.is_dir() and not any(folder.iterdir()):
                folder.rmdir()
        raise
    finally:
        conn.close()
    return session_id


def _session(conn: sqlite3.Connection, row: sqlite3.Row) -> Session:
    params = row["job_params"]
    attendee_ids = spaces.attendee_ids(conn, row["id"])
    chain = jobs.ChainParams.model_validate_json(params) if params else None
    min_voices = chain.attendees if chain else None
    return Session(
        id=row["id"],
        title=row["title"],
        title_edited=bool(row["title_edited"]),
        recorded_at=row["recorded_at"],
        created_at=row["created_at"],
        space_id=row["space_id"],
        space_name=row["space_name"],
        project_id=row["project_id"],
        attendee_ids=attendee_ids,
        unnamed_attendees=row["unnamed_attendees"],
        min_voices=min_voices,
        processing_starts_at=(
            chain.starts_at
            if chain
            and chain.starts_at is not None
            and row["job_state"] == "queued"
            and chain.starts_at > now_iso()
            else None
        ),
        attendees_taken=(
            min_voices == spaces.attendee_minimum(len(attendee_ids), row["unnamed_attendees"])
            if params
            else None
        ),
        reference_source_id=row["reference_source_id"],
        duration_s=row["duration_s"],
        job_state=row["job_state"],
        job_error=row["job_error"],
        audio=retention.status_of(conn, row, retention.get_settings(conn), datetime.now(UTC)),
    )


_SESSION_QUERY = """
SELECT s.*, a.duration_s, j.state AS job_state, j.error AS job_error, j.params AS job_params,
    sp.name AS space_name
FROM session s
JOIN space sp ON sp.id = s.space_id
LEFT JOIN audio_source a ON a.session_id = s.id AND a.source_id = s.reference_source_id
LEFT JOIN job j ON j.id = (SELECT MAX(id) FROM job WHERE session_id = s.id AND kind = 'chain')
"""


def list_sessions(data: DataDir) -> list[Session]:
    conn = connect(data)
    try:
        rows = conn.execute(_SESSION_QUERY + " ORDER BY s.recorded_at DESC, s.id DESC")
        return [_session(conn, r) for r in rows]
    finally:
        conn.close()


def get_session(data: DataDir, session_id: str) -> Session | None:
    conn = connect(data)
    try:
        row = conn.execute(_SESSION_QUERY + " WHERE s.id = ?", (session_id,)).fetchone()
        return _session(conn, row) if row else None
    finally:
        conn.close()


def reference_source(data: DataDir, session_id: str) -> AudioSource | None:
    conn = connect(data)
    try:
        row = conn.execute(
            "SELECT a.* FROM audio_source a JOIN session s ON s.id = a.session_id"
            " AND a.source_id = s.reference_source_id WHERE s.id = ?",
            (session_id,),
        ).fetchone()
    finally:
        conn.close()
    if row is None:
        return None
    path = data.sources_dir(session_id) / row["file_name"]
    return AudioSource(
        source_id=row["source_id"],
        origin=row["origin"],
        original_name=row["original_name"],
        file_name=row["file_name"],
        sha256=row["sha256"],
        size_bytes=row["size_bytes"],
        duration_s=row["duration_s"],
        sample_rate=row["sample_rate"],
        channels=row["channels"],
        codec=row["codec"],
        file_present=path.is_file(),
        capture_state=row["capture_state"],
        device=row["device"],
        pcm_sha256=row["pcm_sha256"],
    )


def other_sources(data: DataDir, session_id: str) -> list[AudioSource]:
    """The session's sources besides the reference (other microphones, the computer's
    sound): kept, listed;
    not processed yet (ADR 0031)."""
    conn = connect(data)
    try:
        rows = conn.execute(
            "SELECT a.* FROM audio_source a JOIN session s ON s.id = a.session_id"
            " AND a.source_id != s.reference_source_id WHERE s.id = ? ORDER BY a.source_id",
            (session_id,),
        ).fetchall()
    finally:
        conn.close()
    return [
        AudioSource(
            source_id=row["source_id"],
            origin=row["origin"],
            original_name=row["original_name"],
            file_name=row["file_name"],
            sha256=row["sha256"],
            size_bytes=row["size_bytes"],
            duration_s=row["duration_s"],
            sample_rate=row["sample_rate"],
            channels=row["channels"],
            codec=row["codec"],
            file_present=(data.sources_dir(session_id) / row["file_name"]).is_file(),
            capture_state=row["capture_state"],
            device=row["device"],
            pcm_sha256=row["pcm_sha256"],
        )
        for row in rows
    ]


def reference_audio_path(data: DataDir, session_id: str) -> Path | None:
    source = reference_source(data, session_id)
    if source is None:
        return None
    return data.sources_dir(session_id) / source.file_name


def interrupted_imports(data: DataDir) -> list[str]:
    """What an interrupted import or a crash left on disk without a session in the database:
    reported at start, never deleted by the application (P8)."""
    found: list[str] = []
    if data.incoming.is_dir():
        found.extend(
            f"Import interrompu : une copie est restée dans {path} (l'original n'a pas bougé)."
            for path in sorted(data.incoming.iterdir())
        )
    sessions_root = data.root / "sessions"
    if sessions_root.is_dir():
        conn = connect(data)
        try:
            known = {r["id"] for r in conn.execute("SELECT id FROM session")}
        finally:
            conn.close()
        found.extend(
            f"Dossier de séance inconnu de la base : {folder}"
            for folder in sorted(sessions_root.iterdir())
            if folder.is_dir() and folder.name not in known
        )
    return found


# -- recording in the application (step 6, ADR 0005) -------------------------------------

CAPTURE_FILE = f"{REFERENCE_SOURCE_ID}.wav"
SECOND_SOURCE_ID = "mic2"
"""The first microphone added beside the reference (often the iPhone, through Continuity):
kept as a source of its own; the processing uses the reference only, for now (ADR 0031,
0033). The next ones are `mic3`, `mic4`…"""


def extra_source_id(position: int) -> str:
    """The source id of the microphone added at `position` (0 for the first: `mic2`)."""
    return f"mic{position + 2}"


def is_extra_microphone(source_id: str) -> bool:
    return source_id.startswith("mic") and source_id[3:].isdigit()


SYSTEM_SOURCE_ID = "system"
"""The computer's sound (a meeting online or hybrid), recorded with the reference on its
clock: mixed with it for the processing, for now (ADR 0032)."""
SYSTEM_DEVICE = "Son de l'ordinateur"


def _label(source_id: str) -> str:
    if source_id == SYSTEM_SOURCE_ID:
        return " (son de l'ordinateur)"
    if is_extra_microphone(source_id):
        return f" (micro {source_id[3:]})"
    return ""


def capture_file(source_id: str) -> str:
    return f"{source_id}.wav"


def start_capture(
    data: DataDir,
    *,
    space_id: int | None,
    project_id: int | None = None,
    attendee_ids: list[int],
    unnamed_attendees: int | None,
    device: str,
    sample_rate: int,
    channels: int,
    extra: list[tuple[str, int]] | None = None,
    system: bool = False,
) -> tuple[str, Path]:
    """The session of a recording about to start: made at once, so that a crash leaves it
    there to be repaired (state `recording`). Returns its id and where to write the audio.
    `extra`: (device, channels) of the microphones added, written beside it as `mic2`,
    `mic3`…;
    `system`: the computer's sound, beside it as `system` (mono)."""
    if unnamed_attendees is not None and unnamed_attendees < 1:
        raise spaces.SpaceError("Le nombre de présents non nommés doit être au moins 1.")
    present = list(dict.fromkeys(attendee_ids))
    now = datetime.now(UTC)
    session_id = new_session_id(now)
    while data.session_dir(session_id).exists():
        session_id = new_session_id(now)
    sources = data.sources_dir(session_id)
    stamp = now_iso()
    conn = connect(data)
    try:
        space = space_id if space_id is not None else spaces.default_space_id(conn)
        spaces.get_space(conn, space)
        projects.check(conn, space, project_id)
        spaces.check_attendees(conn, space, present)
        with conn:
            conn.execute(
                "INSERT INTO session (id, space_id, project_id, title, recorded_at, created_at,"
                " reference_source_id, unnamed_attendees) VALUES (?, ?, ?, NULL, ?, ?, ?, ?)",
                (
                    session_id,
                    space,
                    project_id,
                    stamp,
                    stamp,
                    REFERENCE_SOURCE_ID,
                    unnamed_attendees,
                ),
            )
            conn.executemany(
                "INSERT INTO attendee (session_id, person_id) VALUES (?, ?)",
                [(session_id, p) for p in present],
            )
            conn.executemany(
                "INSERT INTO audio_source (session_id, source_id, origin, original_name,"
                " file_name, sha256, size_bytes, sample_rate, channels, codec, device,"
                " added_at, capture_state) VALUES (?, ?, 'captured', ?, ?, '', 0, ?, ?,"
                " 'pcm_s24le', ?, ?, 'recording')",
                [
                    (
                        session_id,
                        source_id,
                        f"Enregistrement du {now.astimezone().strftime('%d/%m/%Y %H:%M')}"
                        f"{_label(source_id)}.wav",
                        capture_file(source_id),
                        sample_rate,
                        chans,
                        name,
                        stamp,
                    )
                    for source_id, name, chans in (
                        [(REFERENCE_SOURCE_ID, device, channels)]
                        + ([(SYSTEM_SOURCE_ID, SYSTEM_DEVICE, 1)] if system else [])
                        + [
                            (extra_source_id(k), name, chans)
                            for k, (name, chans) in enumerate(extra or [])
                        ]
                    )
                ],
            )
            sources.mkdir(parents=True)
    finally:
        conn.close()
    return session_id, sources / CAPTURE_FILE


def next_extra_source_id(data: DataDir, session_id: str) -> str:
    """The source id of the next microphone added to this session (`mic2`, `mic3`…), after
    every one it has, those that never recorded included."""
    conn = connect(data)
    try:
        taken = [
            int(r["source_id"][3:])
            for r in conn.execute(
                "SELECT source_id FROM audio_source WHERE session_id = ?", (session_id,)
            )
            if is_extra_microphone(r["source_id"])
        ]
    finally:
        conn.close()
    return extra_source_id(max(taken, default=1) - 1)


def add_capture_source(
    data: DataDir,
    session_id: str,
    source_id: str,
    *,
    device: str,
    sample_rate: int,
    channels: int,
) -> None:
    """A microphone added while recording (`mic2`, `mic3`…): its source, made `recording`
    like those added at the start."""
    conn = connect(data)
    try:
        with conn:
            recorded = conn.execute(
                "SELECT recorded_at FROM session WHERE id = ?", (session_id,)
            ).fetchone()["recorded_at"]
            when = datetime.fromisoformat(recorded.replace("Z", "+00:00")).astimezone()
            conn.execute(
                "INSERT INTO audio_source (session_id, source_id, origin, original_name,"
                " file_name, sha256, size_bytes, sample_rate, channels, codec, device,"
                " added_at, capture_state) VALUES (?, ?, 'captured', ?, ?, '', 0, ?, ?,"
                " 'pcm_s24le', ?, ?, 'recording')",
                (
                    session_id,
                    source_id,
                    f"Enregistrement du {when.strftime('%d/%m/%Y %H:%M')}{_label(source_id)}.wav",
                    capture_file(source_id),
                    sample_rate,
                    channels,
                    device,
                    now_iso(),
                ),
            )
    finally:
        conn.close()


def finish_capture(
    data: DataDir,
    session_id: str,
    *,
    frames: int,
    state: str = "complete",
    source_id: str = REFERENCE_SOURCE_ID,
) -> None:
    """The recording is over (stopped, or repaired after a crash): what is on disk is
    described as for an imported file (size, fingerprint, duration)."""
    path = data.sources_dir(session_id) / capture_file(source_id)
    digest = hashlib.sha256()
    with path.open("rb") as f:
        while chunk := f.read(_CHUNK):
            digest.update(chunk)
    try:
        samples: str | None = wav.pcm_sha256(path)
    except ValueError as exc:  # said, and never converted (ADR 0046): it stays as it is
        log.warning(
            "recording %s/%s: no fingerprint of its samples: %s", session_id, source_id, exc
        )
        samples = None
    conn = connect(data)
    try:
        rate = conn.execute(
            "SELECT sample_rate FROM audio_source WHERE session_id = ? AND source_id = ?",
            (session_id, source_id),
        ).fetchone()["sample_rate"]
        with conn:
            conn.execute(
                "UPDATE audio_source SET sha256 = ?, pcm_sha256 = ?, size_bytes = ?,"
                " duration_s = ?, capture_state = ?, capture_ended_at = ?"
                " WHERE session_id = ? AND source_id = ?",
                (
                    digest.hexdigest(),
                    samples,
                    path.stat().st_size,
                    frames / rate,
                    state,
                    now_iso(),
                    session_id,
                    source_id,
                ),
            )
    finally:
        conn.close()


def mark_converted(
    data: DataDir,
    session_id: str,
    source_id: str,
    *,
    file_name: str,
    sha256: str,
    size_bytes: int,
    codec: str,
) -> bool:
    """A recorded track now kept in another format, its samples the same (ADR 0046): the
    file it is in, and that file's fingerprint and size. Its `pcm_sha256` does not change.
    False if the audio was removed meanwhile: nothing is written then."""
    conn = connect(data)
    try:
        with conn:
            changed = conn.execute(
                "UPDATE audio_source SET file_name = ?, sha256 = ?, size_bytes = ?, codec = ?"
                " WHERE session_id = ? AND source_id = ? AND removed_at IS NULL"
                " AND session_id IN (SELECT id FROM session WHERE audio_removed_at IS NULL)",
                (file_name, sha256, size_bytes, codec, session_id, source_id),
            ).rowcount
    finally:
        conn.close()
    return changed == 1


def close_empty_capture(
    data: DataDir,
    session_id: str,
    *,
    reason: str,
    unreadable: bool = False,
    source_id: str = REFERENCE_SOURCE_ID,
) -> None:
    """A recording that holds nothing usable: its file could not be made (empty, duration
    0), or not be read back (`unreadable`: duration unknown, the file stays on disk).
    Closed, so that it is never left « recording », and why is logged."""
    log.warning("recording %s (%s) closed empty: %s", session_id, source_id, reason)
    conn = connect(data)
    try:
        with conn:
            conn.execute(
                "UPDATE audio_source SET duration_s = ?, capture_state = 'complete',"
                " capture_ended_at = ? WHERE session_id = ? AND source_id = ?",
                (None if unreadable else 0, now_iso(), session_id, source_id),
            )
    finally:
        conn.close()


def interrupted_captures(data: DataDir) -> list[tuple[str, str]]:
    """(session, source) whose recording was still being written when the service stopped,
    the reference first."""
    conn = connect(data)
    try:
        return [
            (r["session_id"], r["source_id"])
            for r in conn.execute(
                "SELECT a.session_id, a.source_id FROM audio_source a"
                " JOIN session s ON s.id = a.session_id WHERE a.capture_state = 'recording'"
                " ORDER BY a.session_id, a.source_id != s.reference_source_id, a.source_id"
            )
        ]
    finally:
        conn.close()


class AlreadyProcessedError(spaces.SpaceError):
    """The session already has its processing; the message is shown to the user."""


def start_processing(data: DataDir, session_id: str, *, profile: str) -> None:
    """Queue the processing of a session that has none yet (a recording stopped on battery,
    or repaired after a crash), with its attendees and its space's glossary."""
    conn = connect(data)
    try:
        row = conn.execute(
            "SELECT s.space_id, s.unnamed_attendees, s.audio_removed_at, a.capture_state,"
            " a.duration_s FROM session s"
            " JOIN audio_source a ON a.session_id = s.id AND a.source_id = s.reference_source_id"
            " WHERE s.id = ?",
            (session_id,),
        ).fetchone()
        if row is None:
            raise spaces.NotFoundError("Séance introuvable.")
        if row["capture_state"] == "recording":
            raise AlreadyProcessedError("L'enregistrement n'est pas terminé.")
        if row["audio_removed_at"]:
            raise AlreadyProcessedError("L'audio de cette séance a été supprimé : rien à traiter.")
        if row["capture_state"] is not None and row["duration_s"] is None:
            raise AlreadyProcessedError(
                "Le fichier de cet enregistrement est illisible : il n'y a rien à traiter."
            )
        if row["capture_state"] is not None and not row["duration_s"]:
            raise AlreadyProcessedError("Rien n'a été enregistré : il n'y a rien à traiter.")
        if conn.execute(
            "SELECT 1 FROM job WHERE session_id = ? AND kind = 'chain'", (session_id,)
        ).fetchone():
            raise AlreadyProcessedError("Le traitement de cette séance est déjà demandé.")
        present = spaces.attendee_ids(conn, session_id)
        minimum = spaces.attendee_minimum(len(present), row["unnamed_attendees"])
        with conn:
            jobs.enqueue_chain(
                conn,
                session_id,
                profile=profile,
                attendees=minimum,
                glossary=spaces.glossary_terms(conn, row["space_id"]),
            )
    finally:
        conn.close()
