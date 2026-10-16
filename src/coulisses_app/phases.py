"""The session's phases, called chapters in the interface (spec §7.5, ADR 0024).

A detection is a run of the application (`runs/segment_phases-<hex>/`): the model is asked
where each chapter starts, by the time of its first line. Every boundary is put back on a
line that exists — a chapter starts at a line, whose time is measured or absent, never at
a time the model made up (P2). What had to be adjusted is kept with the detection (P8).
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from itertools import pairwise
from typing import Literal

from pydantic import BaseModel, Field

from coulisses_app.format import clock

PhaseKind = Literal["scene", "discussion", "other"]

KIND_FOR_MODEL: dict[str, PhaseKind] = {
    "scene": "scene",
    "discussion": "discussion",
    "autre": "other",
}
"""What the model answers (French) → the kind kept."""

KIND_WORD: dict[PhaseKind, str] = {"scene": "jeu", "discussion": "discussion", "other": "autre"}
"""How a kind is written in the transcript sent to the model."""

DETECTED_KINDS = ["scene", "discussion"]
"""What the detection may propose (ADR 0045): « autre » is the user's only, set by hand.
An « autre » answered all the same is still read (KIND_FOR_MODEL)."""

ANSWER_SCHEMA: dict[str, object] = {
    "type": "object",
    "properties": {
        "chapitres": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "debut": {"type": "string"},
                    "type": {"type": "string", "enum": DETECTED_KINDS},
                    "titre": {"type": "string"},
                },
                "required": ["debut", "type", "titre"],
            },
        }
    },
    "required": ["chapitres"],
}
"""Given to Ollama (`format`): the answer is this JSON, nothing else."""

REVIEW_SCHEMA: dict[str, object] = {
    "type": "object",
    "properties": {"type": {"type": "string", "enum": DETECTED_KINDS}},
    "required": ["type"],
}
"""The answer of a chapter's review (ADR 0045): played or not."""

TITLE_MAX = 120


class DetectedPhase(BaseModel):
    turn: int
    """Index of its first line in the « who said what » run."""
    kind: PhaseKind
    title: str = Field(max_length=TITLE_MAX)


class PhaseDetection(BaseModel):
    """`output.json` of a detection."""

    phases: list[DetectedPhase]
    adjustments: list[str] = []
    """What the model's answer said that had to be put right, in words (P8)."""


class _Chapter(BaseModel):
    debut: str
    type: str
    titre: str


class _Answer(BaseModel):
    chapitres: list[_Chapter]


class PhaseAnswerError(ValueError):
    """The model's answer gives no usable chapter; the message is shown to the user."""


_TIME = re.compile(r"^\[?\s*(?:(\d+):)?(\d{1,3}):(\d{2})\s*\]?$")


def parse_time(text: str) -> int | None:
    """`m:ss` or `h:mm:ss` (as written in the transcript sent), in whole seconds."""
    match = _TIME.match(text.strip())
    if match is None:
        return None
    hours, minutes, seconds = match.groups()
    if int(seconds) >= 60:
        return None
    return int(hours or 0) * 3600 + int(minutes) * 60 + int(seconds)


class _Review(BaseModel):
    type: str


def review_kind(raw: str) -> PhaseKind | None:
    """The kind a chapter's review gives; none when it cannot be read (the caller keeps
    the kind it had and says so)."""
    try:
        said = _Review.model_validate_json(raw).type.strip().lower()
    except ValueError:
        return None
    return KIND_FOR_MODEL.get(said) if said in DETECTED_KINDS else None


def _kept_title(title: str) -> str:
    """A chapter's title as snap keeps it: spaces put right, at most TITLE_MAX characters."""
    return " ".join(title.split())[:TITLE_MAX]


def last_chapter(raw: str) -> tuple[str, str] | None:
    """The (type, titre) of the last chapter of one answer, the title as snap keeps it;
    none when the answer gives none (snap then says why)."""
    try:
        chapters = _Answer.model_validate_json(raw).chapitres
    except ValueError:
        return None
    return (chapters[-1].type, _kept_title(chapters[-1].titre)) if chapters else None


def drop_before(raw: str, start: str, previous: tuple[str, str] | None = None) -> tuple[str, int]:
    """One answer without the chapters it set before `start` (as written in the
    transcript): in lines recalled from the part before, which are that part's to cut.
    When one of them is `previous` (type, titre), the chapter the part before ended on,
    the part opens by going on with it (join_parts then joins them). An answer that
    cannot be read, or a time that cannot, is passed on: snap says why."""
    limit = parse_time(start)
    try:
        chapters = _Answer.model_validate_json(raw).chapitres
    except ValueError:
        return raw, 0
    if limit is None:
        return raw, 0
    kept = [c for c in chapters if (t := parse_time(c.debut)) is None or t >= limit]
    dropped = [c for c in chapters if c not in kept]
    if (
        previous is not None
        and any(_same(c.type, previous[0]) and _same(c.titre, previous[1]) for c in dropped)
        and not (kept and _same(kept[0].type, previous[0]) and _same(kept[0].titre, previous[1]))
    ):
        kept.insert(0, _Chapter(debut=start, type=previous[0], titre=previous[1]))
    return _Answer(chapitres=kept).model_dump_json(), len(dropped)


def _same(a: str, b: str) -> bool:
    return _kept_title(a).casefold() == _kept_title(b).casefold()


def join_parts(answers: list[str]) -> tuple[list[str], list[bool]]:
    """The answers of a session read in parts, where a part that opens by going on with the
    previous part's last chapter (the same type and title, as asked) loses that opening
    chapter: the previous one runs on, uncut by the part's start.

    Returns the answers to snap and, for each part after the first, whether it was joined.
    An answer that cannot be read is passed on untouched: snap says why."""
    kept = answers[:1]
    joined: list[bool] = []
    for previous, raw in pairwise(answers):
        before = last_chapter(previous)
        try:
            chapters = _Answer.model_validate_json(raw).chapitres
        except ValueError:
            kept.append(raw)
            joined.append(False)
            continue
        # A part with no chapter of its own goes on with the one before as well.
        goes_on = not chapters or (
            before is not None
            and _same(chapters[0].type, before[0])
            and _same(chapters[0].titre, before[1])
        )
        if chapters and goes_on:
            chapters = chapters[1:]
        kept.append(_Answer(chapitres=chapters).model_dump_json())
        joined.append(goes_on)
    return kept, joined


def snap(answers: list[str], turns: Sequence[tuple[int, float | None]]) -> PhaseDetection:
    """The model's answers (one per call, in order), each chapter put on the line whose
    time it gives.

    `turns`: (index, start) of each line, in order. A time that is no line's is moved to
    the nearest line and said so; a chapter whose time cannot be read is left out and said
    so; two chapters on the same line keep the first.
    """
    chapters: list[_Chapter] = []
    for raw in answers:
        try:
            chapters.extend(_Answer.model_validate_json(raw).chapitres)
        except ValueError as exc:
            raise PhaseAnswerError("Le modèle n'a pas renvoyé de chapitres lisibles.") from exc
    timed: list[tuple[int, float]] = [(index, start) for index, start in turns if start is not None]
    if not timed:
        raise PhaseAnswerError("Aucune réplique n'a d'horodatage : rien où placer un chapitre.")
    position = {index: k for k, (index, _) in enumerate(turns)}
    adjustments: list[str] = []
    found: dict[int, DetectedPhase] = {}
    for chapter in chapters:
        title = " ".join(chapter.titre.split())
        if len(title) > TITLE_MAX:
            adjustments.append(f"« {title} » : titre raccourci à {TITLE_MAX} caractères.")
            title = title[:TITLE_MAX]
        kind = KIND_FOR_MODEL.get(chapter.type.strip().lower())
        if kind is None:
            adjustments.append(f"« {title} » : type « {chapter.type} » inconnu, mis à « autre ».")
            kind = "other"
        seconds = parse_time(chapter.debut)
        if seconds is None:
            adjustments.append(
                f"« {title} » : heure « {chapter.debut} » illisible, laissé de côté."
            )
            continue
        wanted = seconds
        exact = next((index for index, start in timed if int(start) == wanted), None)
        if exact is None:
            exact, start = min(timed, key=lambda t: abs(t[1] - wanted))
            adjustments.append(
                f"« {title} » : aucune réplique à {clock(seconds)}, placé sur celle de "
                f"{clock(start)}."
            )
        if exact in found:
            adjustments.append(
                f"« {title} » : commence sur la même réplique que « {found[exact].title} », "
                "laissé de côté."
            )
            continue
        found[exact] = DetectedPhase(turn=exact, kind=kind, title=title)
    if not found:
        raise PhaseAnswerError("Le modèle n'a renvoyé aucun chapitre utilisable.")
    phases = sorted(found.values(), key=lambda p: position[p.turn])
    first = turns[0][0]
    if phases[0].turn != first:
        adjustments.append(
            f"« {phases[0].title} » commence désormais à la première réplique, comme demandé "
            "au modèle."
        )
        phases[0] = phases[0].model_copy(update={"turn": first})
    return PhaseDetection(phases=phases, adjustments=adjustments)
