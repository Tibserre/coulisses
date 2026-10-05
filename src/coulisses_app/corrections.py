"""The user's corrections and the corrected view (ADR 0018, spec §7.6).

Corrections never touch the engine's runs: they are a journal (`edit`), only ever added
to, each one tied to the run it corrects. Undoing adds an entry pointing at the undone one;
redoing adds a copy. The corrected view — what the review screen shows and the summaries
will read — is rebuilt from the active run's output and the journal, every time.

Word times stay measured or absent (P2): a corrected word keeps the time of the word it
replaces; a word added by hand has no time of its own; a corrected stretch keeps its
measured start and end. Nothing is interpolated.
"""

from __future__ import annotations

import difflib
import json
import re
import sqlite3
from enum import StrEnum
from typing import Annotated, Literal

from coulisses.api import AttributedTranscript, read_output
from pydantic import BaseModel, Field, TypeAdapter

from coulisses_app import spaces
from coulisses_app.format import clock
from coulisses_app.paths import DataDir
from coulisses_app.spaces import COLOR_SLOTS, Person, SpaceError
from coulisses_app.storage.db import connect, now_iso

NEW_VOICE_PREFIX = "coulisses:"
"""Labels of the voices the user creates by splitting; the engine's never look like it."""


class EditKind(StrEnum):
    ASSIGN_SPEAKER = "assign_speaker"
    MERGE_SPEAKERS = "merge_speakers"
    REASSIGN_TURNS = "reassign_turns"
    EDIT_TEXT = "edit_text"
    REVERT = "revert"


# -- what the user asks ----------------------------------------------------------------


class AssignSpeaker(BaseModel):
    """Name a voice: a person of the space, a free name, or a character played by a person.
    All empty: back to « Locuteur N »."""

    kind: Literal["assign_speaker"] = "assign_speaker"
    speaker: str
    person_id: int | None = None
    name: str | None = None
    character: str | None = None


class MergeSpeakers(BaseModel):
    """Two voices are one person: every line of `source` goes to `target`."""

    kind: Literal["merge_speakers"] = "merge_speakers"
    source: str
    target: str


class ReassignTurns(BaseModel):
    """Give lines (turns of the run, by index) to another voice, or to a new one (`target`
    left empty): this is how a voice is split."""

    kind: Literal["reassign_turns"] = "reassign_turns"
    turns: list[int] = Field(min_length=1)
    target: str | None = None


class EditText(BaseModel):
    """The corrected text of one line."""

    kind: Literal["edit_text"] = "edit_text"
    turn: int
    text: str


Request = Annotated[
    AssignSpeaker | MergeSpeakers | ReassignTurns | EditText, Field(discriminator="kind")
]
_REQUEST: TypeAdapter[AssignSpeaker | MergeSpeakers | ReassignTurns | EditText] = TypeAdapter(
    Request
)


# -- what the review shows ---------------------------------------------------------------


class Word(BaseModel):
    text: str
    start: float | None
    end: float | None
    confidence: float | None
    uncertain: bool
    """The engine attributed it by a rule, not by a measured overlap."""
    corrected: bool = False
    """Its text was corrected by hand; its time is the measured time of the word it replaces."""
    added: bool = False
    """Added by hand: no measured time of its own (P2)."""
    suggestion: str | None = None
    """A glossary term this word is a known wrong spelling of."""


class Turn(BaseModel):
    index: int
    """Index of the turn in the engine's run: stable, what corrections point at."""
    speaker: str | None
    start: float | None
    end: float | None
    words: list[Word]
    edited: bool = False


class Speaker(BaseModel):
    label: str | None
    number: int | None
    """For « Locuteur N »: order of first appearance in the run, stable when others are named."""
    name: str
    named: bool
    person_id: int | None = None
    character: str | None = None
    played_by: str | None = None
    color_slot: int | None = None
    """Palette slot (the person's own, kept from one session to the next); None: unnamed."""
    seconds: float = 0.0
    turns: int = 0


class EditInfo(BaseModel):
    id: int
    kind: str
    description: str
    created_at: str
    reverted: bool


class Untranscribed(BaseModel):
    start: float
    end: float


class CorrectedView(BaseModel):
    run_id: str
    turns: list[Turn]
    speakers: list[Speaker]
    untranscribed: list[Untranscribed]
    edits: list[EditInfo]
    other_run_edits: int
    """Corrections made on another run of this session, not carried over (step 7 of the
    plan): counted and shown, never dropped (P8)."""
    word_count: int
    timed_share: float


class CorrectionError(SpaceError):
    """A correction that cannot apply; the message is shown to the user."""


# -- building the view -------------------------------------------------------------------


def _active_attribute_run(conn: sqlite3.Connection, session_id: str) -> str | None:
    row = conn.execute(
        "SELECT run_id FROM active_run WHERE session_id = ? AND stage = 'attribute'",
        (session_id,),
    ).fetchone()
    return row["run_id"] if row else None


def _norm(text: str) -> str:
    return re.sub(r"[^\w'-]", "", text.lower())


def _free_name_slot(name: str) -> int:
    return sum(ord(c) for c in name.lower()) % COLOR_SLOTS


def _apply_text(words: list[Word], text: str) -> list[Word]:
    """Corrected words of a line. Unchanged words stay as they are; a replaced word keeps
    the measured time of the one it replaces; extra words have no time; when a stretch
    gets fewer words, its last word keeps the stretch's measured end."""
    tokens = text.split()
    matcher = difflib.SequenceMatcher(None, [w.text for w in words], tokens, autojunk=False)
    out: list[Word] = []
    for op, i1, i2, j1, j2 in matcher.get_opcodes():
        if op == "equal":
            out.extend(words[i1:i2])
            continue
        old = words[i1:i2]
        new = tokens[j1:j2]
        for k, token in enumerate(new):
            if k < len(old):
                kept = old[k]
                # Checked by hand: the engine's confidence no longer applies to it.
                out.append(
                    kept.model_copy(update={"text": token, "corrected": True, "confidence": None})
                )
            else:
                out.append(
                    Word(
                        text=token,
                        start=None,
                        end=None,
                        confidence=None,
                        uncertain=False,
                        added=True,
                    )
                )
        if new and len(new) < len(old):
            last = out[-1]
            if last.start is not None and old[-1].end is not None:
                out[-1] = last.model_copy(update={"end": old[-1].end})
    return out


def _numbering(transcript: AttributedTranscript) -> dict[str, int]:
    numbers: dict[str, int] = {}
    for turn in transcript.turns:
        if turn.speaker is not None and turn.speaker not in numbers:
            numbers[turn.speaker] = len(numbers) + 1
    return numbers


class _Journal(BaseModel):
    id: int
    run_id: str
    kind: str
    payload: str
    reverts: int | None
    created_at: str


def _journal(conn: sqlite3.Connection, session_id: str) -> list[_Journal]:
    return [
        _Journal(
            id=r["id"],
            run_id=r["run_id"],
            kind=r["kind"],
            payload=r["payload"],
            reverts=r["reverts_edit_id"],
            created_at=r["created_at"],
        )
        for r in conn.execute("SELECT * FROM edit WHERE session_id = ? ORDER BY id", (session_id,))
    ]


def build_view(data: DataDir, session_id: str) -> CorrectedView | None:
    """The corrected view of the session's active « who said what » run; None before it
    exists."""
    conn = connect(data)
    try:
        run_id = _active_attribute_run(conn, session_id)
        if run_id is None:
            return None
        transcript = read_output(data.run_dir(session_id, run_id), AttributedTranscript)
        space_row = conn.execute(
            "SELECT space_id FROM session WHERE id = ?", (session_id,)
        ).fetchone()
        people = {p.id: p for p in _people(conn, space_row["space_id"])}
        variants = _variants(conn, space_row["space_id"])
        journal = _journal(conn, session_id)
    finally:
        conn.close()
    return _replay(transcript, run_id, journal, people, variants)


def _people(conn: sqlite3.Connection, space_id: int) -> list[Person]:
    return [
        spaces.get_person(conn, r[0])
        for r in conn.execute("SELECT id FROM person WHERE space_id = ?", (space_id,))
    ]


def _variants(conn: sqlite3.Connection, space_id: int) -> dict[str, str]:
    found: dict[str, str] = {}
    for row in conn.execute(
        "SELECT term, variants FROM glossary_entry WHERE space_id = ? AND archived_at IS NULL",
        (space_id,),
    ):
        for variant in json.loads(row["variants"]):
            found[_norm(variant)] = row["term"]
    return found


def _replay(
    transcript: AttributedTranscript,
    run_id: str,
    journal: list[_Journal],
    people: dict[int, Person],
    variants: dict[str, str],
) -> CorrectedView:
    numbers = _numbering(transcript)
    words_of = [
        [
            Word(
                text=w.text,
                start=w.start,
                end=w.end,
                confidence=w.confidence,
                uncertain=w.uncertain,
            )
            for w in transcript.words[t.first_word : t.end_word]
        ]
        for t in transcript.turns
    ]
    speaker_of: list[str | None] = [t.speaker for t in transcript.turns]
    edited = [False] * len(transcript.turns)
    assigned: dict[str, AssignSpeaker] = {}
    new_voices: list[str] = []

    reverted = {e.reverts for e in journal if e.kind == EditKind.REVERT and e.reverts}
    infos: list[EditInfo] = []
    other_run = 0
    for entry in journal:
        if entry.kind == EditKind.REVERT:
            continue
        if entry.run_id != run_id:
            other_run += 1
            continue
        request = _REQUEST.validate_json(entry.payload)
        live = entry.id not in reverted
        description = _describe(request, numbers, new_voices, assigned, people, transcript)
        if live:
            match request:
                case AssignSpeaker():
                    assigned[request.speaker] = request
                case MergeSpeakers():
                    speaker_of = [request.target if s == request.source else s for s in speaker_of]
                    assigned.pop(request.source, None)
                case ReassignTurns():
                    target = request.target or ""
                    if target.startswith(NEW_VOICE_PREFIX) and target not in new_voices:
                        new_voices.append(target)
                    for index in request.turns:
                        speaker_of[index] = target
                case EditText():
                    words_of[request.turn] = _apply_text(words_of[request.turn], request.text)
                    edited[request.turn] = True
        elif (
            isinstance(request, ReassignTurns)
            and request.target
            and request.target.startswith(NEW_VOICE_PREFIX)
            and request.target not in new_voices
        ):
            # An undone split still owns its label: a later redo finds the same voice.
            new_voices.append(request.target)
        infos.append(
            EditInfo(
                id=entry.id,
                kind=entry.kind,
                description=description,
                created_at=entry.created_at,
                reverted=not live,
            )
        )

    turns: list[Turn] = []
    for index, original in enumerate(transcript.turns):
        words = [
            w.model_copy(update={"suggestion": variants.get(_norm(w.text))})
            if not w.added and _norm(w.text) in variants
            else w
            for w in words_of[index]
        ]
        turns.append(
            Turn(
                index=index,
                speaker=speaker_of[index],
                start=original.start,
                end=original.end,
                words=words,
                edited=edited[index],
            )
        )

    speakers = _speakers(turns, numbers, new_voices, assigned, people)
    all_words = [w for t in turns for w in t.words]
    timed = sum(1 for w in all_words if w.start is not None)
    return CorrectedView(
        run_id=run_id,
        turns=turns,
        speakers=speakers,
        untranscribed=[Untranscribed(start=u.start, end=u.end) for u in transcript.untranscribed],
        edits=infos,
        other_run_edits=other_run,
        word_count=len(all_words),
        timed_share=timed / len(all_words) if all_words else 0.0,
    )


def _unnamed_label(label: str, numbers: dict[str, int], new_voices: list[str]) -> str:
    if label in numbers:
        return f"Locuteur {numbers[label]}"
    if label in new_voices:
        return f"Nouvelle voix {new_voices.index(label) + 1}"
    return "Locuteur inconnu"


def _speakers(
    turns: list[Turn],
    numbers: dict[str, int],
    new_voices: list[str],
    assigned: dict[str, AssignSpeaker],
    people: dict[int, Person],
) -> list[Speaker]:
    found: dict[str | None, Speaker] = {}
    for turn in turns:
        label = turn.speaker
        speaker = found.get(label)
        if speaker is None:
            speaker = _speaker(label, numbers, new_voices, assigned, people)
            found[label] = speaker
        speaker.turns += 1
        if turn.start is not None and turn.end is not None:
            speaker.seconds += turn.end - turn.start
    return list(found.values())


def _speaker(
    label: str | None,
    numbers: dict[str, int],
    new_voices: list[str],
    assigned: dict[str, AssignSpeaker],
    people: dict[int, Person],
) -> Speaker:
    if label is None:
        return Speaker(label=None, number=None, name="Locuteur inconnu", named=False)
    default = _unnamed_label(label, numbers, new_voices)
    number = numbers.get(label)
    choice = assigned.get(label)
    if choice is None:
        return Speaker(label=label, number=number, name=default, named=False)
    person = people.get(choice.person_id) if choice.person_id is not None else None
    if choice.character and person:
        return Speaker(
            label=label,
            number=number,
            name=choice.character,
            named=True,
            person_id=person.id,
            character=choice.character,
            played_by=person.name,
            color_slot=person.color_slot,
        )
    if person:
        return Speaker(
            label=label,
            number=number,
            name=person.name,
            named=True,
            person_id=person.id,
            color_slot=person.color_slot,
        )
    if choice.name:
        return Speaker(
            label=label,
            number=number,
            name=choice.name,
            named=True,
            color_slot=_free_name_slot(choice.name),
        )
    return Speaker(label=label, number=number, name=default, named=False)


def _describe(
    request: AssignSpeaker | MergeSpeakers | ReassignTurns | EditText,
    numbers: dict[str, int],
    new_voices: list[str],
    assigned: dict[str, AssignSpeaker],
    people: dict[int, Person],
    transcript: AttributedTranscript,
) -> str:
    def voice(label: str) -> str:
        return _speaker(label, numbers, new_voices, assigned, people).name

    match request:
        case AssignSpeaker():
            before = _unnamed_label(request.speaker, numbers, new_voices)
            person = people.get(request.person_id) if request.person_id is not None else None
            if request.character and person:
                return f"{before} : {request.character}, joué par {person.name}"
            if person:
                return f"{before} : {person.name}"
            if request.name:
                return f"{before} : {request.name}"
            return f"{before} : sans nom"
        case MergeSpeakers():
            return f"{voice(request.source)} fusionné avec {voice(request.target)}"
        case ReassignTurns():
            count = len(request.turns)
            lines = "1 réplique donnée" if count == 1 else f"{count} répliques données"
            target = request.target
            if target and target.startswith(NEW_VOICE_PREFIX) and target not in new_voices:
                return f"{lines} à une nouvelle voix"
            return f"{lines} à {voice(target) if target else 'une nouvelle voix'}"
        case EditText():
            start = transcript.turns[request.turn].start
            return f"Texte corrigé à {clock(start)}" if start is not None else "Texte corrigé"


# -- recording a correction --------------------------------------------------------------


def _session_space(conn: sqlite3.Connection, session_id: str) -> int:
    row = conn.execute("SELECT space_id FROM session WHERE id = ?", (session_id,)).fetchone()
    if row is None:
        raise spaces.NotFoundError("Séance introuvable.")
    return row["space_id"]


def add(data: DataDir, session_id: str, raw: object) -> CorrectedView:
    """Check a correction against the current corrected view, then record it."""
    request = _REQUEST.validate_python(raw)
    view = build_view(data, session_id)
    conn = connect(data)
    try:
        space_id = _session_space(conn, session_id)
        if view is None:
            raise CorrectionError("Le transcript n'est pas encore prêt.")
        labels = {s.label for s in view.speakers if s.label is not None}
        person_id: int | None = None
        anchor: tuple[float | None, float | None] = (None, None)
        match request:
            case AssignSpeaker():
                if request.speaker not in labels:
                    raise CorrectionError("Cette voix n'existe pas dans le transcript.")
                for field in ("name", "character"):
                    value = getattr(request, field)
                    setattr(request, field, value.strip() if value and value.strip() else None)
                if request.person_id is not None:
                    person = spaces.get_person(conn, request.person_id)
                    if person.space_id != space_id:
                        raise CorrectionError(
                            f"{person.name} n'appartient pas à l'espace de cette séance."
                        )
                    person_id = person.id
                if request.character and request.person_id is None:
                    raise CorrectionError("Un personnage est joué par une personne de l'espace.")
            case MergeSpeakers():
                if request.source not in labels or request.target not in labels:
                    raise CorrectionError("Ces voix n'existent pas dans le transcript.")
                if request.source == request.target:
                    raise CorrectionError("Une voix ne se fusionne pas avec elle-même.")
            case ReassignTurns():
                count = len(view.turns)
                if any(i < 0 or i >= count for i in request.turns):
                    raise CorrectionError("Réplique introuvable.")
                request.turns = sorted(set(request.turns))
                if request.target is None:
                    used = {
                        json.loads(r[0]).get("target")
                        for r in conn.execute(
                            "SELECT payload FROM edit WHERE session_id = ? AND kind = ?",
                            (session_id, EditKind.REASSIGN_TURNS.value),
                        )
                    }
                    n = 1
                    while f"{NEW_VOICE_PREFIX}{n}" in used:
                        n += 1
                    request.target = f"{NEW_VOICE_PREFIX}{n}"
                elif request.target not in labels and not _created_voice(
                    conn, session_id, request.target
                ):
                    raise CorrectionError("Cette voix n'existe pas dans le transcript.")
                chosen = [view.turns[i] for i in request.turns]
                starts = [t.start for t in chosen if t.start is not None]
                ends = [t.end for t in chosen if t.end is not None]
                anchor = (min(starts) if starts else None, max(ends) if ends else None)
            case EditText():
                if request.turn < 0 or request.turn >= len(view.turns):
                    raise CorrectionError("Réplique introuvable.")
                request.text = " ".join(request.text.split())
                if not request.text:
                    raise CorrectionError(
                        "Le texte d'une réplique ne peut pas être vide : donnez-la plutôt à "
                        "une autre voix."
                    )
                turn = view.turns[request.turn]
                if request.text == " ".join(w.text for w in turn.words):
                    raise CorrectionError("Le texte n'a pas changé.")
                anchor = (turn.start, turn.end)
        with conn:
            conn.execute(
                "INSERT INTO edit (session_id, run_id, kind, payload, person_id,"
                " anchor_start_s, anchor_end_s, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    session_id,
                    view.run_id,
                    request.kind,
                    request.model_dump_json(),
                    person_id,
                    anchor[0],
                    anchor[1],
                    now_iso(),
                ),
            )
    finally:
        conn.close()
    result = build_view(data, session_id)
    assert result is not None
    return result


def _created_voice(conn: sqlite3.Connection, session_id: str, label: str) -> bool:
    """A voice the user created by splitting, even if it has no line left (undone split):
    redoing the split gives it its lines back."""
    if not label.startswith(NEW_VOICE_PREFIX):
        return False
    return any(
        json.loads(r[0]).get("target") == label
        for r in conn.execute(
            "SELECT payload FROM edit WHERE session_id = ? AND kind = ?",
            (session_id, EditKind.REASSIGN_TURNS.value),
        )
    )


def _edit_row(conn: sqlite3.Connection, session_id: str, edit_id: int) -> sqlite3.Row:
    row = conn.execute(
        "SELECT * FROM edit WHERE id = ? AND session_id = ?", (edit_id, session_id)
    ).fetchone()
    if row is None or row["kind"] == EditKind.REVERT:
        raise spaces.NotFoundError("Correction introuvable.")
    return row


def undo(data: DataDir, session_id: str, edit_id: int) -> CorrectedView:
    """Undo a correction: an entry pointing at it is added; nothing is erased."""
    conn = connect(data)
    try:
        row = _edit_row(conn, session_id, edit_id)
        if conn.execute("SELECT 1 FROM edit WHERE reverts_edit_id = ?", (edit_id,)).fetchone():
            raise CorrectionError("Cette correction est déjà annulée.")
        with conn:
            conn.execute(
                "INSERT INTO edit (session_id, run_id, kind, payload, reverts_edit_id,"
                " created_at) VALUES (?, ?, ?, '{}', ?, ?)",
                (session_id, row["run_id"], EditKind.REVERT.value, edit_id, now_iso()),
            )
    finally:
        conn.close()
    view = build_view(data, session_id)
    assert view is not None
    return view


def redo(data: DataDir, session_id: str, edit_id: int) -> CorrectedView:
    """Apply an undone correction again, as a new entry (checked against today's view)."""
    conn = connect(data)
    try:
        row = _edit_row(conn, session_id, edit_id)
        undone = conn.execute("SELECT 1 FROM edit WHERE reverts_edit_id = ?", (edit_id,)).fetchone()
        # Already redone: a later copy of it that is still in force.
        redone = conn.execute(
            "SELECT 1 FROM edit e WHERE e.session_id = ? AND e.id > ? AND e.kind = ?"
            " AND e.payload = ? AND NOT EXISTS"
            " (SELECT 1 FROM edit r WHERE r.reverts_edit_id = e.id)",
            (session_id, edit_id, row["kind"], row["payload"]),
        ).fetchone()
    finally:
        conn.close()
    if not undone:
        raise CorrectionError("Cette correction n'est pas annulée.")
    if redone:
        raise CorrectionError("Cette correction est déjà rétablie.")
    return add(data, session_id, json.loads(row["payload"]))
