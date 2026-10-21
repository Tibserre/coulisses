"""Recognising voices from one session to the next (ADR 0057), in the spaces that turned it on.

No voice profile is stored: a person's profile is rebuilt, each time it is needed, from
what already lasts — the user's namings in the journal of corrections, and the embedding
the engine keeps for each speaker of a diarization (immutable, survives the purge of the
audio). Undoing a naming, showing another version or deleting a session changes the
profile with nothing to keep in step; turning recognition off leaves nothing to erase.

Only a confirmation feeds a profile: a voice of the version shown named after a person of
the space (not a character, not a free name), or merged into such a voice. A proposal
never does, and is never applied without the user (P3).
"""

from __future__ import annotations

import logging
import sqlite3
from datetime import datetime
from pathlib import Path

from coulisses.api import (
    RunNotSucceededError,
    SpeakerVoice,
    VoiceProfile,
    add_to_voice_profile,
    match_voice,
    read_speaker_embeddings,
)

from coulisses_app.corrections import (
    AssignSpeaker,
    CorrectedView,
    EditKind,
    JournalEntry,
    MergeSpeakers,
    RejectVoiceMatch,
    VoiceProposal,
    journal_of,
    parse_request,
)
from coulisses_app.paths import DataDir
from coulisses_app.spaces import Person

log = logging.getLogger(__name__)

_EMBEDDINGS: dict[Path, dict[str, SpeakerVoice | None]] = {}
"""Read once per diarization run: a finished run never changes (P5)."""


def _embeddings(run_dir: Path) -> dict[str, SpeakerVoice | None]:
    found = _EMBEDDINGS.get(run_dir)
    if found is None:
        found = read_speaker_embeddings(run_dir)
        _EMBEDDINGS[run_dir] = found
    return found


def choices(
    journal: list[JournalEntry], run_id: str
) -> tuple[dict[str, int], set[tuple[str, int]]]:
    """On one « who said what » run, from the corrections in force: each voice confirmed
    as a person (its label, the person), and the people the user said a voice is not."""
    undone = {e.reverts for e in journal if e.kind == EditKind.REVERT and e.reverts}
    assigned: dict[str, AssignSpeaker] = {}
    joined: dict[str, str] = {}
    rejected: set[tuple[str, int]] = set()
    for entry in journal:
        if entry.run_id != run_id or entry.kind == EditKind.REVERT or entry.id in undone:
            continue
        match parse_request(entry.payload):
            case AssignSpeaker() as request:
                assigned[request.speaker] = request
            case MergeSpeakers() as request:
                joined[request.source] = request.target
                assigned.pop(request.source, None)
            case RejectVoiceMatch() as request:
                rejected.add((request.speaker, request.person_id))
            case _:
                pass

    def group(label: str) -> str:
        seen = {label}
        while label in joined and joined[label] not in seen:
            label = joined[label]
            seen.add(label)
        return label

    confirmed: dict[str, int] = {}
    for label in {*assigned, *joined}:
        choice = assigned.get(group(label))
        if choice is not None and choice.person_id is not None and not choice.character:
            confirmed[label] = choice.person_id
    return confirmed, rejected


def _diarization(conn: sqlite3.Connection, attribute_run: str) -> str | None:
    row = conn.execute(
        "SELECT r.id FROM run_upstream u JOIN run r ON r.id = u.upstream_run_id"
        " WHERE u.run_id = ? AND r.stage = 'diarize'",
        (attribute_run,),
    ).fetchone()
    return row["id"] if row else None


def _unreadable(conn: sqlite3.Connection, session_id: str, what: str, exc: Exception) -> str:
    """The session as the user knows it; the technical detail goes to the log."""
    log.warning("voices of %s not compared (%s): %r", session_id, what, exc)
    row = conn.execute(
        "SELECT title, recorded_at FROM session WHERE id = ?", (session_id,)
    ).fetchone()
    if row is not None and row["title"]:
        return f"« {row['title']} »"
    day = datetime.fromisoformat(row["recorded_at"]) if row is not None else None
    return f"la séance du {day:%d/%m/%Y}" if day else "une séance"


def profiles(
    data: DataDir, conn: sqlite3.Connection, space_id: int
) -> tuple[dict[int, VoiceProfile], list[str]]:
    """Each person's voice profile, from the confirmations of the version shown of every
    session of the space; and the sessions whose voices could not be read (P8): one of
    them never stops the others, nor the review."""
    found: dict[int, VoiceProfile] = {}
    problems: list[str] = []
    rows = conn.execute(
        "SELECT a.session_id, a.run_id FROM active_run a JOIN session s ON s.id = a.session_id"
        " WHERE s.space_id = ? AND a.stage = 'attribute' ORDER BY s.recorded_at, s.id",
        (space_id,),
    ).fetchall()
    for row in rows:
        session_id, attribute_run = row["session_id"], row["run_id"]
        try:
            confirmed, _ = choices(journal_of(conn, session_id), attribute_run)
            if not confirmed:
                continue
            diarize_run = _diarization(conn, attribute_run)
            if diarize_run is None:
                continue
            voices = _embeddings(data.run_dir(session_id, diarize_run))
            added = dict(found)
            for label in sorted(confirmed):
                voice = voices.get(label)
                if voice is None:
                    continue  # too little speech alone, or a run from before engine v1.12.0
                person = confirmed[label]
                added[person] = add_to_voice_profile(
                    added.get(person), f"{session_id}/{diarize_run}/{label}", voice
                )
        except (OSError, ValueError, RunNotSucceededError) as exc:
            problems.append(_unreadable(conn, session_id, attribute_run, exc))
            continue
        found = added  # all of a session's voices, or none of them
    return found, problems


def propose(
    data: DataDir,
    conn: sqlite3.Connection,
    session_id: str,
    space_id: int,
    view: CorrectedView,
    people: dict[int, Person],
) -> None:
    """Gives each unnamed voice of the view the person whose voice profile it is closest
    to, under the engine's threshold, unless the user said it is not that person."""
    unnamed = [s for s in view.speakers if not s.named and s.label is not None]
    if not unnamed:
        return
    diarize_run = _diarization(conn, view.run_id)
    if diarize_run is None:
        return
    known, problems = profiles(data, conn, space_id)
    try:
        voices = _embeddings(data.run_dir(session_id, diarize_run))
        _, rejected = choices(journal_of(conn, session_id), view.run_id)
    except (OSError, ValueError, RunNotSucceededError) as exc:
        problems.append(_unreadable(conn, session_id, diarize_run, exc))
        voices = {}
        rejected: set[tuple[str, int]] = set()
    for speaker in unnamed:
        voice = voices.get(speaker.label) if speaker.label is not None else None
        if voice is None:
            continue
        candidates = {
            str(person_id): profile
            for person_id, profile in known.items()
            if person_id in people
            and not people[person_id].archived
            and (speaker.label, person_id) not in rejected
        }
        try:
            matches = match_voice(voice.embedding, candidates)
        except ValueError as exc:  # embeddings of another dimension: never compared
            problems.append(_unreadable(conn, session_id, f"voice {speaker.label}", exc))
            continue
        if matches:
            person = people[int(matches[0].name)]
            speaker.proposal = VoiceProposal(
                person_id=person.id,
                name=person.name,
                color_slot=person.color_slot,
                distance=matches[0].distance,
            )
    if problems:
        view.voices_problem = (
            "Coulisses n'a pas pu lire les voix de "
            + ", ".join(dict.fromkeys(problems))
            + " pour les reconnaître. Un fichier a-t-il été modifié ou supprimé dans le Finder ?"
        )
