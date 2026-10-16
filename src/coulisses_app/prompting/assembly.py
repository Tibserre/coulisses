"""The single assembly of every prompt sent to the model (spec §7.9, rules/prompts.md).

Always in this order, for every action and every partial call:
1. system frame; 2. the action's prompt; 3. the fallback rule; 4. the French instruction;
5. the session's context; 6. the transcript (`[mm:ss] Nom : texte`).
The French instruction has no switch to turn it off (P4). Names come from the corrected
view, never the raw « Locuteur 3 » when a name exists.
"""

from __future__ import annotations

import math
import tomllib
from dataclasses import dataclass
from importlib.resources import files

from pydantic import BaseModel

from coulisses_app.corrections import CorrectedView, Phase, Speaker
from coulisses_app.format import clock
from coulisses_app.phases import KIND_WORD

FALLBACK_RULE = (
    "Si la transcription et les notes ne contiennent aucun échange substantiel (salutations, "
    "bavardage, essais de micro…), réponds par une seule phrase factuelle qui dit ce qui a été "
    "capté. Si rien n'est exploitable, réponds exactement : « Aucun contenu substantiel n'a été "
    "capté. » Ne renvoie jamais une réponse vide, et n'invente rien pour remplir une section."
)

FRENCH_INSTRUCTION = (
    "Rédige toute ta réponse en français, dans un français naturel et correct, même si une "
    "partie de la transcription est dans une autre langue. Garde tels quels les noms propres, "
    "les citations exactes et le vocabulaire propre au groupe."
)


class Advice(BaseModel):
    """The language model advised to a Mac from this much memory; empty until one is
    measured on real sessions."""

    min_memory_gb: int
    model: str


class Settings(BaseModel):
    default_model: str
    num_ctx: int
    response_reserve: int
    title_reserve: int
    title_max_words: int
    """A title longer than this is asked once more, shorter; never cut."""
    phases_reserve: int
    phases_section_min: int
    """The chapters are read in sections of at most this many minutes."""
    phases_overlap_min: float
    """Each section of the chapters but the first is sent after this many minutes of the
    one before, to cut nothing in them (0: none)."""
    phases_minutes_per_chapter: tuple[float, float]
    """How long a chapter lasts, shortest and longest, in minutes: what the model aims at."""
    phases_review_kinds: bool
    """Each chapter detected is read again alone, to check whether it is played (ADR 0045)."""
    chars_per_token: float
    temperature: float
    seed: int
    advice: list[Advice]
    """From the most memory to the least."""
    writing_min_memory_gb: int
    """Under it, writing may run out of memory: said, not refused."""


def settings() -> Settings:
    raw = tomllib.loads(_text("reglages.toml"))
    return Settings(
        default_model=raw["modele_par_defaut"],
        num_ctx=raw["num_ctx"],
        response_reserve=raw["reserve_reponse"],
        title_reserve=raw["reserve_titre"],
        title_max_words=raw["mots_max_titre"],
        phases_reserve=raw["reserve_chapitres"],
        phases_section_min=raw["partie_chapitres_min"],
        phases_overlap_min=raw["rappel_chapitres_min"],
        phases_minutes_per_chapter=tuple(raw["minutes_par_chapitre"]),
        phases_review_kinds=raw["verifier_types_chapitres"],
        chars_per_token=raw["caracteres_par_token"],
        temperature=raw["temperature"],
        seed=raw["graine"],
        advice=sorted(
            (Advice(min_memory_gb=a["memoire_min_go"], model=a["modele"]) for a in raw["conseil"]),
            key=lambda a: a.min_memory_gb,
            reverse=True,
        ),
        writing_min_memory_gb=raw["memoire_min_redaction_go"],
    )


def advice_for(memory_gb: float, advice: list[Advice]) -> Advice | None:
    """The tier of a Mac with this much memory (the largest it reaches), if any."""
    return next((a for a in advice if memory_gb >= a.min_memory_gb), None)


def _text(name: str) -> str:
    return files("coulisses_app.prompting.textes").joinpath(name).read_text(encoding="utf-8")


class Action(BaseModel):
    ref: str
    name: str
    description: str
    prompt: str


def _parse_action(ref: str, raw: str) -> Action:
    """`---` front matter (nom, description), then the prompt."""
    _, head, body = raw.split("---", 2)
    fields = dict(
        (key.strip(), value.strip())
        for key, value in (line.split(":", 1) for line in head.strip().splitlines())
    )
    return Action(
        ref=ref, name=fields["nom"], description=fields["description"], prompt=body.strip()
    )


def provided_actions() -> list[Action]:
    folder = files("coulisses_app.prompting.textes").joinpath("actions")
    found = [
        _parse_action(entry.name.removesuffix(".md"), entry.read_text(encoding="utf-8"))
        for entry in folder.iterdir()
        if entry.name.endswith(".md")
    ]
    return sorted(found, key=lambda a: a.name)


def action(ref: str) -> Action:
    for candidate in provided_actions():
        if candidate.ref == ref:
            return candidate
    raise KeyError(ref)


TITLE = Action(
    ref="titre",
    name="Titre de la séance",
    description="Un titre court pour retrouver la séance.",
    prompt=_text("titre.md").strip(),
)

PHASES = Action(
    ref="chapitres",
    name="Chapitres",
    description="La séance découpée en chapitres : jeu, discussion ou autre.",
    prompt=_text("chapitres.md").strip(),
)

PHASE_REVIEW_PROMPT = _text("chapitres-relecture.md").strip()
"""Each chapter read again alone: played or not (ADR 0045)."""


def title_retry_prompt(action_prompt: str, previous: str, words: int, max_words: int) -> str:
    """The title asked once more, when the first one is too long."""
    return (
        f"{action_prompt}\n\n"
        f"Ta première proposition, « {previous} », fait {words} mots : c'est trop long pour une "
        f"liste. Propose un titre de {max_words} mots au plus, qui garde le sujet principal."
    )


def phase_review_prompt(start: str, end: str) -> str:
    return (
        f"{PHASE_REVIEW_PROMPT}\n\n"
        f"Le chapitre va de {start} à {end} : tu reçois ses seules répliques."
    )


def system_frame() -> str:
    return _text("cadre-systeme.md").strip()


# -- the session ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Attendee:
    name: str
    role: str | None
    guest: bool


@dataclass(frozen=True)
class SessionContext:
    space: str
    date: str
    duration: str
    attendees: list[Attendee]
    unnamed_attendees: int | None
    glossary: list[str]
    project: str | None = None
    notes: str | None = None
    """The note written by hand after the session."""


def _voice(speaker: Speaker) -> str:
    if speaker.played_by:
        return f"{speaker.name} (personnage joué par {speaker.played_by})"
    if not speaker.named:
        return f"{speaker.name} (voix non identifiée)"
    return speaker.name


def context_block(ctx: SessionContext, view: CorrectedView) -> str:
    lines = ["# Contexte de la séance", f"- Espace : {ctx.space}"]
    if ctx.project:
        lines.append(f"- Projet : {ctx.project}")
    lines.append(f"- Date : {ctx.date}")
    lines.append(f"- Durée : {ctx.duration}")
    if ctx.attendees or ctx.unnamed_attendees:
        people = [
            f"{a.name} ({'invité' if a.guest else (a.role or 'membre')})" for a in ctx.attendees
        ]
        if ctx.unnamed_attendees:
            people.append(f"{ctx.unnamed_attendees} personne(s) non nommée(s)")
        lines.append(f"- Présents : {', '.join(people)}")
    voices = [_voice(s) for s in view.speakers if s.label is not None]
    if voices:
        lines.append(f"- Voix de la transcription : {', '.join(voices)}")
    if ctx.glossary:
        lines.append(f"- Glossaire du groupe : {', '.join(ctx.glossary)}")
    if ctx.notes:
        lines += ["", "## Notes prises après la séance", ctx.notes]
    return "\n".join(lines)


@dataclass(frozen=True)
class Line:
    start: float | None
    text: str
    phase_heading: bool = False
    """A chapter heading: where a long session is best cut into sections."""


def phase_heading(phase: Phase) -> str:
    stamp = f"[{clock(phase.start)}]" if phase.start is not None else "[--:--]"
    title = f" « {phase.title} »" if phase.title else ""
    return f"{stamp} ── Chapitre{title} ({KIND_WORD[phase.kind]}) ──"


def transcript_lines(view: CorrectedView, *, with_phases: bool = True) -> list[Line]:
    """One line per line of the corrected view, `[mm:ss] Nom : texte`, with untranscribed
    stretches, key moments and notes taken while recording in their place and, unless
    asked otherwise, a heading at each chapter (spec §7.9)."""
    names = {s.label: s.name for s in view.speakers}
    played = {s.label: s.played_by for s in view.speakers}
    starts = {p.turn: p for p in view.phases} if with_phases else {}
    items: list[tuple[float, int, str, bool]] = []
    for turn in view.turns:
        name = names.get(turn.speaker, "Locuteur inconnu")
        if played.get(turn.speaker):
            name = f"{name} (joué par {played[turn.speaker]})"
        stamp = f"[{clock(turn.start)}]" if turn.start is not None else "[--:--]"
        text = " ".join(w.text for w in turn.words)
        key = turn.start if turn.start is not None else math.inf
        if turn.index in starts:
            items.append((key, 1, phase_heading(starts[turn.index]), True))
        items.append((key, 2, f"{stamp} {name} : {text}", False))
    for gap in view.untranscribed:
        items.append(
            (
                gap.start,
                0,
                f"[{clock(gap.start)}] (passage non transcrit jusqu'à {clock(gap.end)})",
                False,
            )
        )
    # What was marked while recording, at its time. Play and discussion markers already
    # cut the chapters; the detection, which reads no chapters, sees them as such.
    for marker in view.markers:
        if marker.kind == "key_moment":
            text = "★ Moment clé marqué pendant la séance"
        elif with_phases:
            continue
        else:
            text = "▸ Marqueur posé pendant la séance : début de " + (
                "jeu" if marker.kind == "scene" else "discussion"
            )
        items.append((marker.at_s, 0, f"[{clock(marker.at_s)}] {text}", False))
    for note in view.timed_notes:
        items.append(
            (
                note.at_s,
                0,
                f"[{clock(note.at_s)}] ✎ Note prise pendant la séance : {note.text}",
                False,
            )
        )
    # Lines without a time keep the engine's order: a stable sort on the start only (a
    # heading is added just before its line, so it stays there).
    ordered = sorted(enumerate(items), key=lambda e: (e[1][0], e[0]))
    return [
        Line(start=None if math.isinf(i[0]) else i[0], text=i[2], phase_heading=i[3])
        for _, i in ordered
    ]


# -- the assembly --------------------------------------------------------------------------


@dataclass(frozen=True)
class Prompt:
    """What is sent, in the fixed order: the first four blocks as the system message, the
    context and the transcript as the user message."""

    system: str
    user: str

    def messages(self) -> list[dict[str, str]]:
        return [{"role": "system", "content": self.system}, {"role": "user", "content": self.user}]

    def as_text(self) -> str:
        return f"=== système ===\n{self.system}\n\n=== utilisateur ===\n{self.user}\n"


def assemble(
    action_prompt: str, context: str, transcript: str, *, heading: str = "Transcription"
) -> Prompt:
    """`heading` names the last block: the transcript, or the partial summaries that
    replace it for a consolidation."""
    system = "\n\n".join([system_frame(), action_prompt.strip(), FALLBACK_RULE, FRENCH_INSTRUCTION])
    user = f"{context}\n\n# {heading}\n{transcript}"
    return Prompt(system=system, user=user)


def estimate_tokens(text: str, chars_per_token: float) -> int:
    """A deliberate overestimate: Ollama cannot count before sending (ADR 0022)."""
    return math.ceil(len(text) / chars_per_token)


def section_prompt(action_prompt: str, index: int, count: int, start: str, end: str) -> str:
    return (
        f"{action_prompt}\n\n"
        f"La séance est trop longue pour être lue d'un coup : cette demande ne porte que sur la "
        f"partie {index} sur {count}, de {start} à {end}. Rédige le compte rendu de cette partie "
        f"seule, avec la même structure ; il sera ensuite fusionné avec les autres. N'annonce pas "
        f"que c'est une partie."
    )


def phases_scale(minutes: float, per_chapter: tuple[float, float]) -> str:
    """How many chapters to aim at for this many minutes (ADR 0044), from how many minutes
    a chapter lasts (shortest, longest): a small model left without it cuts at nearly every
    exchange, or too seldom."""
    rounded = max(1, round(minutes))
    shortest, longest = per_chapter
    low = max(1, round(minutes / longest))
    high = max(low + 1, round(minutes / shortest))
    return (
        f"Ce passage dure environ {rounded} minute{'s' if rounded > 1 else ''} : vise entre "
        f"{low} et {high} chapitres. Mieux vaut un chapitre un peu long qu'une coupure à chaque "
        f"échange."
    )


def phases_prompt(action_prompt: str, minutes: float, per_chapter: tuple[float, float]) -> str:
    """The chapters of a session read at once."""
    return f"{action_prompt}\n\n{phases_scale(minutes, per_chapter)}"


def phases_section_prompt(
    action_prompt: str,
    index: int,
    count: int,
    start: str,
    end: str,
    minutes: float,
    previous: tuple[str, str] | None = None,
    *,
    per_chapter: tuple[float, float],
    recalled: bool = False,
) -> str:
    """`previous`: the (type, titre) the part before ended on, for the part to go on with
    it rather than cut there. `recalled`: the end of the part before comes first in the
    transcript sent, up to `section_start_line`."""
    text = (
        f"{action_prompt}\n\n"
        f"La séance est lue en {count} parties : cette demande ne porte que sur la partie "
        f"{index}, de {start} à {end}. Découpe cette partie seule : son premier chapitre "
        f"commence à sa première réplique. {phases_scale(minutes, per_chapter)}"
    )
    if recalled:
        text += (
            " Les répliques qui précèdent la ligne « Début de la partie à découper » sont "
            "rappelées pour que tu voies ce qui se passait juste avant : ne les découpe pas."
        )
    if previous is not None:
        kind, title = previous
        text += (
            f" La partie précédente se terminait sur le chapitre « {title} » (type `{kind}`). "
            f"Si cette partie commence par la suite de ce même moment, donne à ton premier "
            f"chapitre exactement ce type et ce titre : les deux seront réunis. Sinon, donne-lui "
            f"son propre titre."
        )
    return text


def section_start_line(start: str) -> str:
    """Where the part to cut starts, after the lines recalled from the part before."""
    return f"[{start}] ── Début de la partie à découper ──"


def consolidation_prompt(action_prompt: str, count: int) -> str:
    return (
        f"{action_prompt}\n\n"
        f"La séance a été résumée en {count} parties, dans l'ordre, à partir de sa transcription. "
        f"À la place de la transcription, tu reçois ces {count} comptes rendus partiels. "
        f"Fusionne-les en un seul compte rendu, avec la structure demandée : regroupe ce qui va "
        f"ensemble, supprime les doublons, garde les attributions, et n'ajoute rien qui n'y soit "
        f"pas."
    )
