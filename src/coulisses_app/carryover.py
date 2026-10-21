"""Carrying the user's corrections over to a new version (spec §7.6, step 7 of the plan).

Running the transcription or the voices again gives a new « who said what » run, with its
own lines and its own voices. The corrections in force on the version it replaces are
translated onto it by measured time, never by guess: what cannot be placed with certainty
is not carried, and is listed with the reason (P8). The originals stay on their run, which
stays viewable; a carried correction is a copy on the new run, undone like any other.

- a voice's name goes to the new voice holding at least half of its speaking time;
- a merge, to the new voices of the two merged ones (already one: nothing to write);
- lines given to another voice, to the new lines lying mostly inside them, when they
  cover at least half of their time;
- a text correction, only to a new line with exactly the same original text, at the same
  time;
- a chapter cut, to the new line starting within two seconds of the old one.
"""

from __future__ import annotations

import sqlite3
from bisect import bisect_left
from collections import defaultdict

from coulisses.api import AttributedTranscript, read_output
from pydantic import BaseModel

from coulisses_app import corrections
from coulisses_app.corrections import (
    NEW_VOICE_PREFIX,
    AnyRequest,
    AssignSpeaker,
    EditKind,
    EditText,
    MergeSpeakers,
    ReassignTurns,
    RejectVoiceMatch,
    RemovePhase,
    SetPhase,
)
from coulisses_app.format import clock
from coulisses_app.paths import DataDir
from coulisses_app.storage.db import now_iso

NAME_SHARE = 0.5
"""A new voice takes an old voice's name when it holds at least this share of its time."""
LINES_SHARE = 0.5
"""Lines given to a voice are found again when the new lines lying mostly inside them cover
at least this share of their time."""
CUT_SLACK_S = 2.0
"""A chapter cut goes to the new line starting this close to the old one."""


class Carried(BaseModel):
    """What becomes of one correction on the new run."""

    edit_id: int
    description: str
    applied: bool
    partial: bool = False
    """Carried for some of its lines only: listed too, with the reason."""
    reason: str | None = None
    copy_request: AnyRequest | None = None
    """The correction to write on the new run; None when not carried, or when nothing
    needs writing."""
    person_id: int | None = None
    anchor: tuple[float | None, float | None] = (None, None)


def _turn_overlaps(a: AttributedTranscript, b: AttributedTranscript) -> dict[int, dict[int, float]]:
    """Seconds shared by each timed line of `a` with each timed line of `b`."""
    timed = sorted(
        (t.start, t.end, j)
        for j, t in enumerate(b.turns)
        if t.start is not None and t.end is not None
    )
    starts = [s for s, _, _ in timed]
    longest = max((e - s for s, e, _ in timed), default=0.0)
    found: dict[int, dict[int, float]] = defaultdict(dict)
    for i, turn in enumerate(a.turns):
        if turn.start is None or turn.end is None:
            continue
        k = bisect_left(starts, turn.end) - 1
        # Any line of `b` overlapping this one starts after its start minus the longest.
        while k >= 0 and timed[k][0] >= turn.start - longest:
            s, e, j = timed[k]
            shared = min(e, turn.end) - max(s, turn.start)
            if shared > 0:
                found[i][j] = shared
            k -= 1
    return found


def _duration(t: AttributedTranscript, i: int) -> float:
    turn = t.turns[i]
    if turn.start is None or turn.end is None:
        return 0.0
    return max(0.0, turn.end - turn.start)


def _text(t: AttributedTranscript, i: int) -> str:
    turn = t.turns[i]
    return " ".join(w.text for w in t.words[turn.first_word : turn.end_word])


def plan(
    source: AttributedTranscript,
    target: AttributedTranscript,
    edits: list[tuple[int, AnyRequest]],
    *,
    names: dict[str, str],
    descriptions: dict[int, str],
) -> list[Carried]:
    """What becomes of each correction in force on `source` (in the order made), on
    `target`. A correction another one later replaced (an earlier name of the same voice,
    an earlier text of the same line) is not considered: only what the user sees."""
    shared = _turn_overlaps(source, target)

    # Old voice → new voice, by speaking time.
    voice_time: dict[str, float] = defaultdict(float)
    pair_time: dict[tuple[str, str], float] = defaultdict(float)
    for i, turn in enumerate(source.turns):
        if turn.speaker is None:
            continue
        voice_time[turn.speaker] += _duration(source, i)
        for j, seconds in shared.get(i, {}).items():
            new = target.turns[j].speaker
            if new is not None:
                pair_time[(turn.speaker, new)] += seconds
    voice_of: dict[str, str] = {}
    held: dict[str, float] = {}
    for (old, new), seconds in pair_time.items():
        if seconds > held.get(old, 0.0):
            voice_of[old], held[old] = new, seconds
    for old in list(voice_of):
        if held[old] < NAME_SHARE * voice_time[old]:
            del voice_of[old]

    # The old voices the user made one (merges), each group under its final label.
    joined: dict[str, str] = {}

    def group(label: str) -> str:
        while label in joined:
            label = joined[label]
        return label

    for _, request in edits:
        if isinstance(request, MergeSpeakers) and group(request.source) != group(request.target):
            joined[group(request.source)] = group(request.target)
    # A new voice belongs to the group holding most of it. Another old voice found inside
    # it cannot take it over: carrying its name or its merge would carry the owner's lines
    # along (the engine fused two people the user had told apart).
    group_time: dict[tuple[str, str], float] = defaultdict(float)
    for (old, new), seconds in pair_time.items():
        group_time[(group(old), new)] += seconds
    owner: dict[str, str] = {}
    owned: dict[str, float] = {}
    for (kept, new), seconds in group_time.items():
        if seconds > owned.get(new, 0.0):
            owner[new], owned[new] = kept, seconds

    # Only what is in force in the end: the latest name of a voice (a merged voice's name
    # goes with it), the latest text of a line.
    named_by: dict[str, int] = {}
    text_by: dict[int, int] = {}
    for edit_id, request in edits:
        match request:
            case AssignSpeaker():
                named_by[request.speaker] = edit_id
            case MergeSpeakers():
                named_by.pop(request.source, None)
            case EditText():
                text_by[request.turn] = edit_id
            case _:
                pass
    current = set(named_by.values()) | set(text_by.values())

    created: set[str] = set()

    def new_voice(old: str) -> tuple[str | None, str]:
        """The new voice of an old one, or why there is none."""
        if old.startswith(NEW_VOICE_PREFIX):
            if old in created:
                return old, ""
            return (
                None,
                "la voix créée en scindant n'a pas pu être recréée dans la nouvelle version",
            )
        new = voice_of.get(old)
        if new is None:
            return None, (
                "aucune voix de la nouvelle version ne reprend au moins la moitié du temps de "
                f"parole de {names.get(group(old), 'cette voix')}"
            )
        if owner.get(new, group(old)) != group(old):
            return None, (
                "dans la nouvelle version, sa voix est réunie avec celle de "
                f"{names.get(owner[new], 'une autre voix')}"
            )
        return new, ""

    def span(lines: list[int]) -> tuple[float | None, float | None]:
        starts = [s for j in lines if (s := target.turns[j].start) is not None]
        ends = [e for j in lines if (e := target.turns[j].end) is not None]
        return (min(starts) if starts else None, max(ends) if ends else None)

    results: list[Carried] = []
    for edit_id, request in edits:
        what = descriptions.get(edit_id, "Correction")

        def refused(reason: str, *, edit_id: int = edit_id, what: str = what) -> None:
            results.append(Carried(edit_id=edit_id, description=what, applied=False, reason=reason))

        match request:
            case AssignSpeaker():
                if edit_id not in current:
                    continue
                new, why = new_voice(request.speaker)
                if new is None:
                    refused(why)
                    continue
                results.append(
                    Carried(
                        edit_id=edit_id,
                        description=what,
                        applied=True,
                        copy_request=request.model_copy(update={"speaker": new}),
                        person_id=request.person_id,
                    )
                )
            case RejectVoiceMatch():
                new, why = new_voice(request.speaker)
                if new is None:
                    refused(why)
                    continue
                results.append(
                    Carried(
                        edit_id=edit_id,
                        description=what,
                        applied=True,
                        copy_request=request.model_copy(update={"speaker": new}),
                    )
                )
            case MergeSpeakers():
                (source_new, why_source), (target_new, why_target) = (
                    new_voice(request.source),
                    new_voice(request.target),
                )
                if source_new is None or target_new is None:
                    refused(why_source if source_new is None else why_target)
                elif source_new == target_new:
                    results.append(
                        Carried(
                            edit_id=edit_id,
                            description=what,
                            applied=True,
                            reason="déjà une seule voix dans la nouvelle version",
                        )
                    )
                else:
                    results.append(
                        Carried(
                            edit_id=edit_id,
                            description=what,
                            applied=True,
                            copy_request=MergeSpeakers(source=source_new, target=target_new),
                        )
                    )
            case ReassignTurns():
                chosen = set(request.turns)
                inside: dict[int, float] = defaultdict(float)
                for i in chosen:
                    for j, seconds in shared.get(i, {}).items():
                        inside[j] += seconds
                lines = sorted(
                    j
                    for j, seconds in inside.items()
                    if seconds >= LINES_SHARE * _duration(target, j)
                )
                covered = sum(inside[j] for j in lines)
                total = sum(_duration(source, i) for i in chosen)
                if not lines or total <= 0 or covered < LINES_SHARE * total:
                    refused("ces répliques ne se retrouvent pas dans la nouvelle version")
                    continue
                old_target = request.target or ""
                if old_target.startswith(NEW_VOICE_PREFIX):
                    new = old_target
                else:
                    found, why = new_voice(old_target)
                    if found is None:
                        refused(why)
                        continue
                    new = found
                if new.startswith(NEW_VOICE_PREFIX):
                    created.add(new)
                missing = sorted(
                    i for i in chosen if not any(j in shared.get(i, {}) for j in lines)
                )
                found = len(chosen) - len(missing)
                partial = bool(missing)
                at = [clock(t) for i in missing if (t := source.turns[i].start) is not None]
                results.append(
                    Carried(
                        edit_id=edit_id,
                        description=what,
                        applied=True,
                        partial=partial,
                        reason=f"reportée en partie : {found} réplique{'s' if found > 1 else ''} "
                        f"sur {len(chosen)} retrouvée{'s' if found > 1 else ''} dans la nouvelle "
                        "version" + (f" (manquent celles de {', '.join(at)})" if at else "")
                        if partial
                        else None,
                        copy_request=ReassignTurns(turns=lines, target=new),
                        anchor=span(lines),
                    )
                )
            case EditText():
                if edit_id not in current:
                    continue
                original = _text(source, request.turn)
                near = shared.get(request.turn, {})
                same = [j for j in near if _text(target, j) == original]
                if not same:
                    refused(
                        "cette réplique a changé dans la nouvelle version"
                        if near
                        else "cette réplique n'a pas d'équivalent dans la nouvelle version"
                    )
                    continue
                line = max(same, key=lambda j: near[j])
                results.append(
                    Carried(
                        edit_id=edit_id,
                        description=what,
                        applied=True,
                        copy_request=request.model_copy(update={"turn": line}),
                        anchor=span([line]),
                    )
                )
            case SetPhase() | RemovePhase():
                at = (
                    source.turns[request.turn].start
                    if 0 <= request.turn < len(source.turns)
                    else None
                )
                candidates = [
                    (abs(s - at), j)
                    for j, t in enumerate(target.turns)
                    if at is not None and (s := t.start) is not None and abs(s - at) <= CUT_SLACK_S
                ]
                if not candidates:
                    refused(
                        "aucune réplique ne commence au même moment dans la nouvelle version "
                        "(à deux secondes près)"
                    )
                    continue
                line = min(candidates)[1]
                results.append(
                    Carried(
                        edit_id=edit_id,
                        description=what,
                        applied=True,
                        copy_request=request.model_copy(update={"turn": line}),
                        anchor=span([line]),
                    )
                )
    return results


def carry(
    conn: sqlite3.Connection, data: DataDir, session_id: str, source_run: str, target_run: str
) -> list[Carried]:
    """Carry the corrections in force on `source_run` over to `target_run`, inside the
    caller's transaction (begun with BEGIN IMMEDIATE, so that no correction slips in
    meanwhile). Done once per new run: a second call finds its rows and does nothing."""
    if conn.execute(
        "SELECT 1 FROM edit_carryover WHERE target_run_id = ? LIMIT 1", (target_run,)
    ).fetchone():
        return []
    view = corrections.build_view(data, session_id, run_id=source_run, recognise=False)
    if view is None:
        return []
    in_force = {e.id for e in view.edits if not e.reverted}
    if not in_force:
        return []
    rows = conn.execute(
        "SELECT id, payload FROM edit WHERE session_id = ? AND run_id = ? AND kind != ?"
        " ORDER BY id",
        (session_id, source_run, EditKind.REVERT.value),
    ).fetchall()
    edits = [
        (row["id"], corrections.parse_request(row["payload"]))
        for row in rows
        if row["id"] in in_force
    ]
    source = read_output(data.run_dir(session_id, source_run), AttributedTranscript)
    target = read_output(data.run_dir(session_id, target_run), AttributedTranscript)
    names = {s.label: s.name for s in view.speakers if s.label is not None}
    results = plan(
        source,
        target,
        edits,
        names=names,
        descriptions={e.id: e.description for e in view.edits},
    )
    now = now_iso()
    for result in results:
        copy_id: int | None = None
        if result.copy_request is not None:
            cursor = conn.execute(
                "INSERT INTO edit (session_id, run_id, kind, payload, person_id,"
                " anchor_start_s, anchor_end_s, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    session_id,
                    target_run,
                    result.copy_request.kind,
                    result.copy_request.model_dump_json(),
                    result.person_id,
                    result.anchor[0],
                    result.anchor[1],
                    now,
                ),
            )
            copy_id = cursor.lastrowid
        conn.execute(
            "INSERT INTO edit_carryover (edit_id, target_run_id, outcome, reason,"
            " carried_edit_id, description, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                result.edit_id,
                target_run,
                "not_applied" if not result.applied else "partial" if result.partial else "applied",
                result.reason,
                copy_id,
                result.description,
                now,
            ),
        )
    return results
