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

from coulisses_app import marks, spaces
from coulisses_app.format import clock
from coulisses_app.marks import Marker, TimedNote
from coulisses_app.paths import DataDir
from coulisses_app.phases import KIND_WORD, TITLE_MAX, PhaseDetection, PhaseKind
from coulisses_app.spaces import COLOR_SLOTS, Person, SpaceError
from coulisses_app.storage.db import connect, now_iso

NEW_VOICE_PREFIX = "coulisses:"
"""Labels of the voices the user creates by splitting; the engine's never look like it."""


class EditKind(StrEnum):
    ASSIGN_SPEAKER = "assign_speaker"
    MERGE_SPEAKERS = "merge_speakers"
    REASSIGN_TURNS = "reassign_turns"
    EDIT_TEXT = "edit_text"
    SET_PHASE = "set_phase"
    REMOVE_PHASE = "remove_phase"
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


class SetPhase(BaseModel):
    """A chapter starts at this line: created if none does, otherwise its kind or title
    changed (what is left empty stays as it was; a new one takes the kind of the chapter it
    cuts, and no title)."""

    kind: Literal["set_phase"] = "set_phase"
    turn: int
    phase_kind: PhaseKind | None = None
    title: str | None = Field(default=None, max_length=TITLE_MAX)


class RemovePhase(BaseModel):
    """No chapter starts at this line any more: its lines join the chapter before."""

    kind: Literal["remove_phase"] = "remove_phase"
    turn: int


AnyRequest = AssignSpeaker | MergeSpeakers | ReassignTurns | EditText | SetPhase | RemovePhase
Request = Annotated[AnyRequest, Field(discriminator="kind")]
_REQUEST: TypeAdapter[AnyRequest] = TypeAdapter(Request)


def parse_request(payload: str) -> AnyRequest:
    """A correction as the journal keeps it."""
    return _REQUEST.validate_json(payload)


# -- what the review shows ---------------------------------------------------------------


class Word(BaseModel):
    text: str
    start: float | None
    end: float | None
    asr_confidence: float | None
    """How sure the transcription model was of the word (engine `asr_confidence`, ADR 0023
    of the engine): below 0.3 it doubted. Absent on runs before engine v1.4.0."""
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
    undone_by: int | None = None
    """Journal entry that undid it: the latest undone is the one Cmd-Shift-Z redoes."""
    redone: bool = False
    """Undone, then applied again by a later copy that is still in force."""
    turn: int | None = None
    """For a text correction: the line it corrects."""


class Phase(BaseModel):
    """A chapter: from its first line to the next chapter's (or the end)."""

    turn: int
    """Its first line (index in the run)."""
    end_turn: int
    """The first line after it (exclusive)."""
    start: float | None
    """Measured start of its first line; None when that line has no time (P2)."""
    end: float | None
    kind: PhaseKind
    title: str
    edited: bool = False
    """Changed or created by the user (the detection said otherwise)."""
    marked: bool = False
    """Cut by a play or discussion marker set while recording: it comes before the
    detection (spec §7.5)."""


class Untranscribed(BaseModel):
    start: float
    end: float


class NotCarried(BaseModel):
    """A correction of the replaced version that could not be carried over (P8)."""

    edit_id: int
    description: str
    """What it was, as it read on its own version."""
    reason: str
    at_s: float | None
    """Measured time of the passage it corrected, when it has one."""
    text: str | None = None
    """For a text correction: the corrected text, to take back by hand."""
    partial: bool = False
    """Carried for some of its lines only; the reason says how many."""


class Carryover(BaseModel):
    """How the corrections of the version this one replaced were carried over to it."""

    from_run_id: str
    carried: int
    """Carried over in full."""
    not_carried: list[NotCarried]
    """Not carried, or only in part."""


class CorrectedView(BaseModel):
    run_id: str
    turns: list[Turn]
    speakers: list[Speaker]
    untranscribed: list[Untranscribed]
    edits: list[EditInfo]
    carryover: Carryover | None = None
    """When this version replaced another: what was carried over from it, and what was not
    (step 7 of the plan). The other version keeps its own corrections."""
    word_count: int
    timed_share: float
    phases: list[Phase] = []
    """Empty until a detection succeeds (or the user cuts a chapter)."""
    phases_run_id: str | None = None
    """The detection the chapters come from: a summary made with another is stale."""
    phases_problem: str | None = None
    """Why the detection's chapters could not be read, when they could not (P8)."""
    markers: list[Marker] = []
    """Set while recording (play, discussion, key moment), at recorded times."""
    timed_notes: list[TimedNote] = []
    """Notes taken while recording, at the time their first letter was typed."""
    phases_by_markers: list[str] = []
    """Detected cuts a marker replaced, in words (shown in developer mode, ADR 0024)."""


class CorrectionError(SpaceError):
    """A correction that cannot apply; the message is shown to the user."""


class VersionChangedError(CorrectionError):
    """The correction was meant for another version than the one now shown (a rerun ended,
    or another version was shown meanwhile): nothing is written, the page reloads."""


def _guard(conn: sqlite3.Connection, session_id: str, checked_on: str, version: str | None) -> None:
    """Inside the write transaction (BEGIN IMMEDIATE, as the carrying over of a new version
    is): the version the correction was checked against, and the one the page showed, are
    still the version shown. Otherwise a correction could land on another version's line,
    or on a version just replaced, after its corrections were carried over."""
    shown = _active_attribute_run(conn, session_id)
    if shown != checked_on or (version is not None and version != shown):
        raise VersionChangedError(
            "La version affichée vient de changer : rien n'a été enregistré. La page se met à jour."
        )


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
                # Checked by hand: the model's doubt no longer applies to it.
                out.append(
                    kept.model_copy(
                        update={"text": token, "corrected": True, "asr_confidence": None}
                    )
                )
            else:
                out.append(
                    Word(
                        text=token,
                        start=None,
                        end=None,
                        asr_confidence=None,
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


def build_view(
    data: DataDir, session_id: str, *, run_id: str | None = None
) -> CorrectedView | None:
    """The corrected view of the session's active « who said what » run (or of another of
    its runs, with that run's own corrections); None before it exists."""
    conn = connect(data)
    try:
        if run_id is None:
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
        detection_run = _active_detection(conn, session_id, run_id)
        marked = marks.markers(conn, session_id)
        notes_taken = marks.timed_notes(conn, session_id)
        carried = _carryover(conn, run_id)
    finally:
        conn.close()
    detection: PhaseDetection | None = None
    problem: str | None = None
    if detection_run is not None:
        path = data.run_dir(session_id, detection_run) / "output.json"
        try:
            detection = PhaseDetection.model_validate_json(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            problem = (
                f"Les chapitres détectés ({detection_run}/output.json) sont illisibles : "
                f"{type(exc).__name__}. A-t-il été modifié ou supprimé dans le Finder ?"
            )
    view = _replay(
        transcript,
        run_id,
        journal,
        people,
        variants,
        detection=detection,
        detection_run_id=detection_run,
        detection_problem=problem,
        markers=marked,
        timed_notes=notes_taken,
    )
    view.carryover = carried
    return view


def _carryover(conn: sqlite3.Connection, run_id: str) -> Carryover | None:
    rows = conn.execute(
        "SELECT c.edit_id, c.outcome, c.reason, c.description, e.run_id, e.kind, e.payload,"
        " e.anchor_start_s FROM edit_carryover c JOIN edit e ON e.id = c.edit_id"
        " WHERE c.target_run_id = ? ORDER BY e.id",
        (run_id,),
    ).fetchall()
    if not rows:
        return None
    missing: list[NotCarried] = []
    for row in rows:
        if row["outcome"] == "applied":
            continue
        request = parse_request(row["payload"])
        missing.append(
            NotCarried(
                edit_id=row["edit_id"],
                description=row["description"],
                reason=row["reason"] or "",
                at_s=row["anchor_start_s"],
                text=request.text if isinstance(request, EditText) else None,
                partial=row["outcome"] == "partial",
            )
        )
    return Carryover(
        from_run_id=rows[0]["run_id"],
        carried=sum(1 for r in rows if r["outcome"] == "applied"),
        not_carried=missing,
    )


def _active_detection(conn: sqlite3.Connection, session_id: str, run_id: str) -> str | None:
    """The latest chapters detected on this « who said what » run (a detection made on
    another run points at other lines: it does not apply)."""
    row = conn.execute(
        "SELECT a.run_id FROM active_run a JOIN run_upstream u ON u.run_id = a.run_id"
        " WHERE a.session_id = ? AND a.stage = 'segment_phases' AND u.upstream_run_id = ?",
        (session_id, run_id),
    ).fetchone()
    return row["run_id"] if row else None


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
    *,
    detection: PhaseDetection | None = None,
    detection_run_id: str | None = None,
    detection_problem: str | None = None,
    markers: list[Marker] | None = None,
    timed_notes: list[TimedNote] | None = None,
) -> CorrectedView:
    numbers = _numbering(transcript)
    words_of = [
        [
            Word(
                text=w.text,
                start=w.start,
                end=w.end,
                asr_confidence=w.asr_confidence,
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
    phase_edits: list[SetPhase | RemovePhase] = []

    undone_by = {e.reverts: e.id for e in journal if e.kind == EditKind.REVERT and e.reverts}
    reverted = set(undone_by)
    infos: list[EditInfo] = []
    for entry in journal:
        if entry.kind == EditKind.REVERT:
            continue
        if entry.run_id != run_id:
            continue  # another version's: carried over or listed (Carryover), or its own
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
                case SetPhase() | RemovePhase():
                    phase_edits.append(request)
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
                undone_by=undone_by.get(entry.id),
                turn=request.turn if isinstance(request, EditText) else None,
            )
        )
    in_force = [
        (e.id, e.kind, e.payload)
        for e in journal
        if e.kind != EditKind.REVERT and e.id not in reverted and e.run_id == run_id
    ]
    payloads = {e.id: (e.kind, e.payload) for e in journal}
    for info in infos:
        # Redone: a later copy of it, on the same run, still in force.
        info.redone = info.reverted and any(
            later > info.id and (kind, payload) == payloads[info.id]
            for later, kind, payload in in_force
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
    phases, outside, replaced = _phases(turns, detection, phase_edits, markers or [])
    if outside:
        detection_problem = " ".join(
            filter(
                None,
                [
                    detection_problem,
                    f"{outside} chapitre(s) ou correction(s) de chapitre visent une réplique "
                    "absente de ce traitement : ignorés ici, gardés dans leurs fichiers.",
                ],
            )
        )
    all_words = [w for t in turns for w in t.words]
    timed = sum(1 for w in all_words if w.start is not None)
    return CorrectedView(
        run_id=run_id,
        turns=turns,
        speakers=speakers,
        untranscribed=[Untranscribed(start=u.start, end=u.end) for u in transcript.untranscribed],
        edits=infos,
        word_count=len(all_words),
        timed_share=timed / len(all_words) if all_words else 0.0,
        phases=phases,
        phases_run_id=detection_run_id if detection is not None else None,
        phases_problem=detection_problem,
        markers=markers or [],
        timed_notes=timed_notes or [],
        phases_by_markers=replaced,
    )


MARKER_ABSORBS_S = 60.0
"""A detected cut this close to a marker is the same cut: the marker's line wins, the
detection's title stays."""


def _line_after(turns: list[Turn], at_s: float) -> int | None:
    """The first line starting at or after a time (half a second of slack: a marker set
    while someone starts speaking belongs to that line)."""
    return next((t.index for t in turns if t.start is not None and t.start >= at_s - 0.5), None)


def _phases(
    turns: list[Turn],
    detection: PhaseDetection | None,
    edits: list[SetPhase | RemovePhase],
    marked: list[Marker],
) -> tuple[list[Phase], int, list[str]]:
    """The detection's chapters, the cuts marked while recording over them, then the
    user's changes in the order they were made; and how many of the detection's chapters
    or of the changes point at no line of this run (never expected: counted, not hidden)."""
    count = len(turns)
    detected = detection.phases if detection else []
    outside = sum(1 for p in detected if not 0 <= p.turn < count)
    # Chapter start (line index) → (kind, title, edited, marked).
    starts: dict[int, tuple[PhaseKind, str, bool, bool]] = {
        p.turn: (p.kind, p.title, False, False) for p in detected if 0 <= p.turn < count
    }
    replaced: list[str] = []
    cutting = [m for m in marked if m.kind != "key_moment"]
    first_line = turns[0].index if turns else None

    def nearest_marker(at: float) -> Marker | None:
        return min(cutting, key=lambda m: abs(m.at_s - at), default=None)

    for marker in cutting:
        line = _line_after(turns, marker.at_s)
        if line is None:
            continue  # set after the last line: nothing to cut
        # The detected cut that is this marker's (closest to it, and to no other marker),
        # if close enough: replaced by it, its title kept. The opening chapter stays.
        claimed = [
            first
            for first, (_, _, _, by_marker) in starts.items()
            if not by_marker
            and first != first_line
            and (at := turns[first].start) is not None
            and abs(at - marker.at_s) <= MARKER_ABSORBS_S
            and nearest_marker(at) is marker
        ]
        title = starts[line][1] if line in starts else ""
        if claimed:
            closest = min(claimed, key=lambda first: abs((turns[first].start or 0.0) - marker.at_s))
            title = starts.pop(closest)[1]
            replaced.append(
                f"Marqueur {KIND_WORD['scene' if marker.kind == 'scene' else 'discussion']} à "
                f"{clock(marker.at_s)} : remplace la coupure détectée à "
                f"{clock(turns[closest].start or 0.0)}" + (f" (« {title} »)" if title else "")
            )
        kind: PhaseKind = "scene" if marker.kind == "scene" else "discussion"
        starts[line] = (kind, title, False, True)
    for edit in edits:
        if not 0 <= edit.turn < count:
            outside += 1
            continue
        if isinstance(edit, RemovePhase):
            starts.pop(edit.turn, None)
            continue
        current = starts.get(edit.turn)
        if current is None:
            before = [t for t in starts if t < edit.turn]
            kind: PhaseKind = starts[max(before)][0] if before else "discussion"
            current = (kind, "", True, False)
        starts[edit.turn] = (
            edit.phase_kind or current[0],
            current[1] if edit.title is None else edit.title,
            True,
            current[3],
        )
    ordered = sorted(starts)
    phases: list[Phase] = []
    for k, first in enumerate(ordered):
        end_turn = ordered[k + 1] if k + 1 < len(ordered) else count
        kind, title, edited, by_marker = starts[first]
        ends = [t.end for t in turns[first:end_turn] if t.end is not None]
        phases.append(
            Phase(
                turn=first,
                end_turn=end_turn,
                start=turns[first].start,
                end=max(ends) if ends else None,
                kind=kind,
                title=title,
                edited=edited,
                marked=by_marker,
            )
        )
    return phases, outside, replaced


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
    request: AnyRequest,
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
            source, target = voice(request.source), voice(request.target)
            if source == target:
                return f"Les deux voix de {source} réunies"
            return f"{source} fusionné avec {target}"
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
        case SetPhase() | RemovePhase():
            start = (
                transcript.turns[request.turn].start
                if 0 <= request.turn < len(transcript.turns)
                else None
            )
            at = f" à {clock(start)}" if start is not None else ""
            if isinstance(request, RemovePhase):
                return f"Coupure de chapitre retirée{at}"
            changes: list[str] = []
            if request.title is not None:
                changes.append(f"« {request.title} »" if request.title else "sans titre")
            if request.phase_kind is not None:
                changes.append(KIND_WORD[request.phase_kind])
            if not changes:
                return f"Nouveau chapitre{at}"
            return f"Chapitre{at} : {', '.join(changes)}"


# -- recording a correction --------------------------------------------------------------


def _session_space(conn: sqlite3.Connection, session_id: str) -> int:
    row = conn.execute("SELECT space_id FROM session WHERE id = ?", (session_id,)).fetchone()
    if row is None:
        raise spaces.NotFoundError("Séance introuvable.")
    return row["space_id"]


def add(
    data: DataDir, session_id: str, raw: object, *, version: str | None = None
) -> CorrectedView:
    """Check a correction against the current corrected view, then record it. `version`:
    the « who said what » run the page showed when the user made it."""
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
                if request.person_id is not None and not request.character:
                    # The same person as another voice: one voice the engine split in two
                    # (P3), so they become one, as the user means (undone like any merge).
                    same = next(
                        (
                            v
                            for v in view.speakers
                            if v.label not in (None, request.speaker)
                            and v.person_id == request.person_id
                            and not v.character
                        ),
                        None,
                    )
                    if same is not None and same.label is not None:
                        request = MergeSpeakers(source=request.speaker, target=same.label)
                        person_id = None
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
            case SetPhase():
                if request.turn < 0 or request.turn >= len(view.turns):
                    raise CorrectionError("Réplique introuvable.")
                if request.title is not None:
                    request.title = " ".join(request.title.split())
                current = next((p for p in view.phases if p.turn == request.turn), None)
                if (
                    current is not None
                    and request.phase_kind in (None, current.kind)
                    and (request.title in (None, current.title))
                ):
                    raise CorrectionError(
                        "Un chapitre commence déjà ici."
                        if request.phase_kind is None and request.title is None
                        else "Ce chapitre est déjà ainsi."
                    )
                turn = view.turns[request.turn]
                anchor = (turn.start, turn.end)
            case RemovePhase():
                if not any(p.turn == request.turn for p in view.phases):
                    raise CorrectionError("Aucun chapitre ne commence à cette réplique.")
                if view.turns[0].index == request.turn:
                    raise CorrectionError(
                        "Le chapitre qui ouvre la séance ne se retire pas : renommez-le ou "
                        "changez son type."
                    )
                turn = view.turns[request.turn]
                anchor = (turn.start, turn.end)
        with conn:
            conn.execute("BEGIN IMMEDIATE")
            _guard(conn, session_id, view.run_id, version)
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


def undo(
    data: DataDir, session_id: str, edit_id: int, *, version: str | None = None
) -> CorrectedView:
    """Undo a correction of the version shown: an entry pointing at it is added; nothing is
    erased."""
    conn = connect(data)
    try:
        row = _edit_row(conn, session_id, edit_id)
        if conn.execute("SELECT 1 FROM edit WHERE reverts_edit_id = ?", (edit_id,)).fetchone():
            raise CorrectionError("Cette correction est déjà annulée.")
        with conn:
            conn.execute("BEGIN IMMEDIATE")
            _guard(conn, session_id, row["run_id"], version)
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


def reset_text(
    data: DataDir, session_id: str, turn: int, *, version: str | None = None
) -> CorrectedView:
    """Back to the engine's text for one line: every text correction of it still in force
    is undone (each one by an entry of its own, so it can be redone)."""
    view = build_view(data, session_id)
    if view is None:
        raise CorrectionError("Le transcript n'est pas encore prêt.")
    live = [e.id for e in view.edits if e.turn == turn and not e.reverted]
    if not live:
        raise CorrectionError("Le texte de cette réplique n'a pas été corrigé.")
    conn = connect(data)
    try:
        with conn:
            conn.execute("BEGIN IMMEDIATE")
            _guard(conn, session_id, view.run_id, version)
            conn.executemany(
                "INSERT INTO edit (session_id, run_id, kind, payload, reverts_edit_id,"
                " created_at) VALUES (?, ?, ?, '{}', ?, ?)",
                # Latest first: redoing then brings them back in their original order.
                [
                    (session_id, view.run_id, EditKind.REVERT.value, i, now_iso())
                    for i in reversed(live)
                ],
            )
    finally:
        conn.close()
    result = build_view(data, session_id)
    assert result is not None
    return result


def redo(
    data: DataDir, session_id: str, edit_id: int, *, version: str | None = None
) -> CorrectedView:
    """Apply an undone correction of the version shown again, as a new entry (checked
    against today's view)."""
    conn = connect(data)
    try:
        row = _edit_row(conn, session_id, edit_id)
        undone = conn.execute("SELECT 1 FROM edit WHERE reverts_edit_id = ?", (edit_id,)).fetchone()
        # Already redone: a later copy of it that is still in force.
        # (On the same version: a copy carried over to another one is not a redo.)
        redone = conn.execute(
            "SELECT 1 FROM edit e WHERE e.session_id = ? AND e.run_id = ? AND e.id > ?"
            " AND e.kind = ? AND e.payload = ? AND NOT EXISTS"
            " (SELECT 1 FROM edit r WHERE r.reverts_edit_id = e.id)",
            (session_id, row["run_id"], edit_id, row["kind"], row["payload"]),
        ).fetchone()
    finally:
        conn.close()
    if not undone:
        raise CorrectionError("Cette correction n'est pas annulée.")
    if redone:
        raise CorrectionError("Cette correction est déjà rétablie.")
    # Its line numbers are those of its own version: replayed on that version only.
    return add(data, session_id, json.loads(row["payload"]), version=version or row["run_id"])
