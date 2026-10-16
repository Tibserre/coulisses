"""One generation (a summary, the title or the chapters) as a run of the application
(ADR 0018, 0022, 0024).

Its folder (`runs/<stage>-<hex>/`) keeps what was asked (`spec.json`), every call — the
prompt sent word for word and the answer (`calls/`) —, the result (`output.md`) and the
provenance (`provenance.json`: model, settings, counts, durations). Finished, it never
changes (P5). A prompt too long for the context window is summarised by sections then
consolidated, and the generation says so; nothing is ever cut (P8).
"""

from __future__ import annotations

import json
import logging
import math
import secrets
import sqlite3
import time
from collections.abc import Callable
from datetime import UTC, datetime
from importlib.metadata import version
from pathlib import Path
from typing import Literal, NamedTuple, Protocol

from pydantic import BaseModel

from coulisses_app import actions, corrections, notes, sessions, spaces
from coulisses_app.format import clock
from coulisses_app.paths import DataDir
from coulisses_app.phases import (
    ANSWER_SCHEMA,
    KIND_WORD,
    REVIEW_SCHEMA,
    TITLE_MAX,
    PhaseAnswerError,
    drop_before,
    join_parts,
    last_chapter,
    regroup_onto,
    review_kind,
    snap,
)
from coulisses_app.prompting import assembly
from coulisses_app.prompting.ollama import ChatAnswer, InstalledModel, OllamaError
from coulisses_app.storage.db import connect, now_iso

log = logging.getLogger(__name__)

TITLE_REF = "titre"
PHASES_REF = "chapitres"

Stage = Literal["summarize", "title", "segment_phases"]


class ModelClient(Protocol):
    def models(self) -> list[InstalledModel]: ...

    def version(self) -> str | None: ...

    def chat(
        self,
        model: str,
        messages: list[dict[str, str]],
        options: dict[str, object],
        *,
        answer_format: dict[str, object] | None = None,
    ) -> ChatAnswer: ...


class Call(BaseModel):
    index: int
    kind: Literal["unique", "section", "consolidation", "review"]
    """`review`: a chapter read again alone, for its kind (ADR 0045)."""
    covers: str | None = None
    """For a section: the stretch of the session it covers."""
    prompt_file: str
    response_file: str | None = None
    estimated_prompt_tokens: int
    prompt_eval_count: int | None = None
    eval_count: int | None = None
    done_reason: str | None = None
    duration_s: float | None = None


class GenerationError(BaseModel):
    type: str
    message: str


class Provenance(BaseModel):
    """Published as `schemas/generation-provenance.schema.json`."""

    run_id: str
    session_id: str
    stage: Stage
    producer: Literal["app"] = "app"
    app_version: str
    status: Literal["succeeded", "failed"]
    action_ref: str
    action_name: str
    model: str
    model_digest: str | None
    options: dict[str, object]
    strategy: Literal["unique", "sections"]
    source_run_id: str
    """The « who said what » run the corrected view was built from."""
    edits_applied: int
    """Corrections in force when the prompt was assembled (names, text…)."""
    edit_ids: list[int] = []
    """Which ones: a summary is stale as soon as this set differs from today's."""
    phases_run_id: str | None = None
    """The chapter detection whose chapters were in the transcript sent (none for the
    detection itself): a summary is stale when the chapters come from another one."""
    input_kind: Literal["transcript", "chapters", "summary"] = "transcript"
    """What the model read after the context: the transcript, or for a title, the
    chapters or a summary of the session (ADR 0026)."""
    input_run_id: str | None = None
    """For a title made from the chapters or a summary: the run they come from."""
    notes_digest: str | None = None
    """Of the note written after the session, as it was sent (none without one): a summary
    is stale when the note changed since."""
    ollama_version: str | None = None
    calls: list[Call]
    started_at: datetime
    finished_at: datetime
    duration_s: float
    error: GenerationError | None = None


class GenerationFailedError(RuntimeError):
    """The generation could not be made; the message is shown to the user."""


def _write_new(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as out:
        out.write(text)


def _context(conn: sqlite3.Connection, session: sessions.Session) -> assembly.SessionContext:
    attendees = [spaces.get_person(conn, i) for i in session.attendee_ids]
    when = datetime.fromisoformat(session.recorded_at.replace("Z", "+00:00")).astimezone()
    return assembly.SessionContext(
        space=session.space_name,
        date=when.strftime("%d/%m/%Y"),
        duration=clock(session.duration_s) if session.duration_s else "inconnue",
        attendees=[
            assembly.Attendee(name=p.name, role=p.role, guest=p.kind == "guest") for p in attendees
        ],
        unnamed_attendees=session.unnamed_attendees,
        glossary=spaces.glossary_terms(conn, session.space_id),
        notes=note.text if (note := notes.after_session(conn, session.id)) else None,
    )


def _sections(
    lines: list[assembly.Line], budget_tokens: int, chars_per_token: float
) -> list[list[assembly.Line]]:
    """Consecutive lines, each section within the budget, cut between chapters whenever a
    whole chapter fits: a chapter longer than the budget is cut between its lines. A single
    line larger than the budget is refused rather than cut (P8)."""
    blocks: list[list[assembly.Line]] = []
    for line in lines:
        if line.phase_heading or not blocks:
            blocks.append([])
        blocks[-1].append(line)

    def cost(line: assembly.Line) -> int:
        return assembly.estimate_tokens(line.text + "\n", chars_per_token)

    sections: list[list[assembly.Line]] = [[]]
    size = 0
    for block in blocks:
        block_size = sum(cost(line) for line in block)
        if size + block_size <= budget_tokens:
            sections[-1].extend(block)
            size += block_size
            continue
        if sections[-1] and block_size <= budget_tokens:
            sections.append(list(block))
            size = block_size
            continue
        for line in block:  # a chapter too long for one section: cut between lines
            line_size = cost(line)
            if line_size > budget_tokens:
                raise GenerationFailedError(
                    "Une réplique est trop longue pour la fenêtre du modèle, même seule : "
                    "augmentez num_ctx dans les réglages de génération."
                )
            if size + line_size > budget_tokens and sections[-1]:
                sections.append([])
                size = 0
            sections[-1].append(line)
            size += line_size
    return sections


def _minutes(starts: list[float | None]) -> float:
    """From the first time to the last, in minutes."""
    timed = [s for s in starts if s is not None]
    return (timed[-1] - timed[0]) / 60 if timed else 0.0


def _between(
    lines: list[assembly.Line], begin: float | None, until: float | None
) -> list[assembly.Line]:
    """The lines from `begin` (included) to `until` (excluded): a chapter's. A line
    without a time goes with the one before it."""
    out: list[assembly.Line] = []
    inside = begin is None
    for line in lines:
        if line.start is not None:
            inside = (begin is None or line.start >= begin) and (
                until is None or line.start < until
            )
        if inside:
            out.append(line)
    return out


def _recalled(before: list[assembly.Line], start: float, minutes: float) -> list[assembly.Line]:
    """The timed lines of the part before within `minutes` of this part's start."""
    if minutes <= 0:
        return []
    return [
        line for line in before if line.start is not None and line.start >= start - minutes * 60
    ]


def _sections_by_time(lines: list[assembly.Line], minutes: int) -> list[list[assembly.Line]]:
    """Consecutive lines in sections of the same length, each at most `minutes` long
    (ADR 0044). A line without a time stays with the one before it."""
    starts = [line.start for line in lines if line.start is not None]
    if not starts or minutes <= 0:
        return [lines]
    span = starts[-1] - starts[0]
    count = max(1, math.ceil(span / (minutes * 60)))
    length = span / count
    sections: list[list[assembly.Line]] = [[]]
    for line in lines:
        if (
            line.start is not None
            and sections[-1]
            and len(sections) < count
            and line.start >= starts[0] + len(sections) * length
        ):
            sections.append([])
        sections[-1].append(line)
    return sections


def generate(
    data: DataDir,
    session_id: str,
    action_ref: str,
    model: str,
    client: ModelClient,
    *,
    job_id: int | None = None,
    clock_now: Callable[[], datetime] = lambda: datetime.now(UTC),
) -> Provenance:
    """Make one generation and record it, succeeded or failed (never silently)."""
    is_title = action_ref == TITLE_REF
    is_phases = action_ref == PHASES_REF
    stage: Stage = "title" if is_title else "segment_phases" if is_phases else "summarize"
    modified = False
    input_kind: Literal["transcript", "chapters", "summary"] = "transcript"
    input_run_id: str | None = None
    if is_title:
        chosen = assembly.TITLE
    elif is_phases:
        chosen = assembly.PHASES
    else:
        # The action in force, the user's modified version if any (spec.json keeps it).
        conn = connect(data)
        try:
            in_force = actions.get_action(conn, action_ref)
            chosen = actions.as_prompt(in_force)
            modified = in_force.modified
        finally:
            conn.close()
    view = corrections.build_view(data, session_id)
    session = sessions.get_session(data, session_id)
    if view is None or session is None:
        raise GenerationFailedError("Le transcript de cette séance n'est pas encore prêt.")
    cfg = assembly.settings()
    reserve = (
        cfg.title_reserve if is_title else cfg.phases_reserve if is_phases else cfg.response_reserve
    )
    # The chapters, read in short sections, may have a smaller window (ADR 0044).
    num_ctx = cfg.phases_num_ctx if is_phases and cfg.phases_num_ctx else cfg.num_ctx
    # Grouped after, the chapters are first cut finer (ADR 0045).
    cut_scale = (
        cfg.phases_cut_minutes_per_chapter if cfg.phases_regroup else cfg.phases_minutes_per_chapter
    )
    options: dict[str, object] = {
        "num_ctx": num_ctx,
        "num_predict": reserve,
        "temperature": cfg.temperature,
        "seed": cfg.seed,
        # A summary is the answer itself: no reasoning trace (sent at the top of the call).
        "think": False,
    }
    if is_title:
        # The title is one line: the model is asked to stop there. Ollama's MLX runner
        # ignores it, and models go on with a summary that the reserve cuts: see _check.
        options["stop"] = ["\n"]
    edit_ids = sorted(e.id for e in view.edits if not e.reverted)
    # The detection reads the transcript without chapters; the others, with today's.
    phases_run_id = None if is_phases else view.phases_run_id
    answer_format = ANSWER_SCHEMA if is_phases else None

    title_input = _title_input(data, session_id, view) if is_title else None
    if (
        title_input is not None
        and assembly.estimate_tokens(
            assembly.system_frame() + chosen.prompt + title_input.text, cfg.chars_per_token
        )
        > cfg.num_ctx - reserve - 2000
    ):
        title_input = None  # too long to read at once: the transcript path cuts in sections
    run_id = f"{stage}-{secrets.token_hex(4)}"
    folder = data.run_dir(session_id, run_id)
    conn = connect(data)
    try:
        session_context = _context(conn, session)
        context = assembly.context_block(session_context, view)
        notes_digest = notes.digest(session_context.notes)
        with conn:
            conn.execute(
                "INSERT INTO run (id, session_id, job_id, stage, status, producer, created_at)"
                " VALUES (?, ?, ?, ?, 'running', 'app', ?)",
                (run_id, session_id, job_id, stage, now_iso()),
            )
            conn.execute(
                "INSERT INTO run_upstream (run_id, upstream_run_id) VALUES (?, ?)",
                (run_id, view.run_id),
            )
            if title_input is not None and title_input.run_id is not None:
                conn.execute(
                    "INSERT INTO run_upstream (run_id, upstream_run_id) VALUES (?, ?)",
                    (run_id, title_input.run_id),
                )
    finally:
        conn.close()

    # From here the run exists: whatever happens, it ends recorded (provenance), never
    # left « running » (P8).
    started = clock_now()
    t0 = time.monotonic()
    calls: list[Call] = []
    strategy: Literal["unique", "sections"] = "unique"
    error: GenerationError | None = None
    output = ""
    digest: str | None = None
    ollama_version: str | None = None

    def call(
        kind: Literal["unique", "section", "consolidation", "review"],
        prompt: assembly.Prompt,
        covers: str | None,
        *,
        answer_format: dict[str, object] | None = answer_format,
    ) -> str:
        index = len(calls) + 1
        prompt_file = f"calls/{index:02d}-prompt.txt"
        _write_new(folder / prompt_file, prompt.as_text())
        estimated = assembly.estimate_tokens(prompt.system + prompt.user, cfg.chars_per_token)
        record = Call(
            index=index,
            kind=kind,
            covers=covers,
            prompt_file=prompt_file,
            estimated_prompt_tokens=estimated,
        )
        calls.append(record)
        started_call = time.monotonic()
        answer = client.chat(model, prompt.messages(), options, answer_format=answer_format)
        record.duration_s = time.monotonic() - started_call
        record.prompt_eval_count = answer.prompt_eval_count
        record.eval_count = answer.eval_count
        record.done_reason = answer.done_reason
        record.response_file = f"calls/{index:02d}-response.{'json' if is_phases else 'md'}"
        _write_new(folder / record.response_file, answer.content)
        _check(answer, estimated, num_ctx, first_line_only=is_title)
        return answer.content.strip()

    try:
        _write_new(
            folder / "spec.json",
            json.dumps(
                {
                    "stage": stage,
                    "action_ref": chosen.ref,
                    "action_name": chosen.name,
                    "action_prompt": chosen.prompt,
                    # The user's modified version of a provided action, not the original.
                    "action_modified": modified,
                    "model": model,
                    "options": options,
                    "format": answer_format,
                    "source_run_id": view.run_id,
                    "edit_ids": edit_ids,
                    "phases_run_id": phases_run_id,
                    # How the chapters were read (ADR 0044): sections, recall, the scale
                    # aimed at, the window asked (0: num_ctx).
                    **(
                        {
                            "phases_section_min": cfg.phases_section_min,
                            "phases_overlap_min": cfg.phases_overlap_min,
                            "phases_minutes_per_chapter": list(cfg.phases_minutes_per_chapter),
                            "phases_cut_minutes_per_chapter": list(cut_scale),
                            "phases_review_kinds": cfg.phases_review_kinds,
                            "phases_regroup": cfg.phases_regroup,
                            "review_format": REVIEW_SCHEMA,
                            "phases_num_ctx": cfg.phases_num_ctx,
                        }
                        if is_phases
                        else {}
                    ),
                },
                ensure_ascii=False,
                indent=2,
            ),
        )
        digest = next((m.digest for m in _models(client) if m.name == model), None)
        ollama_version = _version(client)
        if title_input is not None:
            # A title needs only the outline: the chapters, or a summary (ADR 0026).
            input_kind = title_input.kind
            input_run_id = title_input.run_id
            prompt = assembly.assemble(
                chosen.prompt, context, title_input.text, heading=title_input.heading
            )
            if (
                assembly.estimate_tokens(prompt.system + prompt.user, cfg.chars_per_token)
                > cfg.num_ctx - reserve
            ):
                raise GenerationFailedError(
                    "Les chapitres et le contexte dépassent la fenêtre du modèle : augmentez "
                    "num_ctx dans les réglages de génération."
                )
            output = call("unique", prompt, None)
        else:
            lines = assembly.transcript_lines(view, with_phases=not is_phases)
            whole = "\n".join(line.text for line in lines)
            starts_all = [line.start for line in lines if line.start is not None]
            prompt = assembly.assemble(
                assembly.phases_prompt(chosen.prompt, _minutes(starts_all), cut_scale)
                if is_phases
                else chosen.prompt,
                context,
                whole,
            )
            budget = num_ctx - reserve
            size = assembly.estimate_tokens(prompt.system + prompt.user, cfg.chars_per_token)
            # The chapters are read in sections of a set length, whatever the window (ADR 0044).
            by_time = _sections_by_time(lines, cfg.phases_section_min) if is_phases else [lines]
            answers: list[str] = []
            part_firsts: list[str] = []
            recalled_out = 0
            unrecalled: list[int] = []
            if size <= budget and len(by_time) == 1:
                output = call("unique", prompt, None)
                answers.append(output)
            else:
                strategy = "sections"
                longest_previous = ("discussion", "x" * TITLE_MAX)
                fixed = assembly.estimate_tokens(
                    (
                        assembly.phases_section_prompt(
                            chosen.prompt,
                            99,
                            99,
                            "00:00:00",
                            "00:00:00",
                            999,
                            longest_previous,
                            per_chapter=cut_scale,
                            recalled=True,
                        )
                        if is_phases
                        else assembly.section_prompt(chosen.prompt, 99, 99, "00:00:00", "00:00:00")
                    )
                    + assembly.assemble("", context, "").system
                    + assembly.assemble("", context, "").user,
                    cfg.chars_per_token,
                )
                parts: list[str] = []
                chunks = [
                    chunk
                    for piece in by_time
                    for chunk in _sections(piece, budget - fixed, cfg.chars_per_token)
                ]
                for k, chunk in enumerate(chunks, start=1):
                    starts = [line.start for line in chunk if line.start is not None]
                    first = clock(starts[0]) if starts else "?"
                    last = clock(starts[-1]) if starts else "?"
                    text = "\n".join(line.text for line in chunk)
                    # The end of the part before, recalled for the model to see whether this
                    # one goes on with it (ADR 0044); left out when it would not fit.
                    recalled = (
                        _recalled(chunks[k - 2], starts[0], cfg.phases_overlap_min)
                        if is_phases and k > 1 and starts
                        else []
                    )
                    while True:
                        if is_phases:
                            part_prompt = assembly.assemble(
                                assembly.phases_section_prompt(
                                    chosen.prompt,
                                    k,
                                    len(chunks),
                                    first,
                                    last,
                                    _minutes(starts),
                                    last_chapter(parts[-1]) if parts else None,
                                    per_chapter=cut_scale,
                                    recalled=bool(recalled),
                                ),
                                context,
                                "\n".join(
                                    [line.text for line in recalled]
                                    + [assembly.section_start_line(first), text]
                                )
                                if recalled
                                else text,
                            )
                        else:
                            part_prompt = assembly.assemble(
                                assembly.section_prompt(chosen.prompt, k, len(chunks), first, last),
                                context,
                                text,
                            )
                        too_long = (
                            assembly.estimate_tokens(
                                part_prompt.system + part_prompt.user, cfg.chars_per_token
                            )
                            > budget
                        )
                        if not (recalled and too_long):
                            break
                        recalled = []
                        unrecalled.append(k)
                    previous = last_chapter(parts[-1]) if parts else None
                    answer = call("section", part_prompt, f"{first} à {last}")
                    if recalled:
                        # Chapters set in the recalled lines are the part before's to cut;
                        # the one it ended on, set there, still says the part goes on with it.
                        answer, dropped = drop_before(answer, first, previous)
                        recalled_out += dropped
                    parts.append(answer)
                    part_firsts.append(first)
                answers = parts
            if is_phases:
                # Each part's chapters, put on the lines they name: no merging call needed. A
                # part that goes on with the chapter the previous one ended on is joined to it.
                answers, joined = join_parts(answers)
                detection = snap(answers, [(t.index, t.start) for t in view.turns])
                for k, (first, was_joined) in enumerate(
                    zip(part_firsts[1:], joined, strict=True), start=2
                ):
                    detection.adjustments.append(
                        f"Séance lue en {len(part_firsts)} parties : la partie {k}, à {first}, "
                        "continue le chapitre précédent."
                        if was_joined
                        else f"Séance lue en {len(part_firsts)} parties : un chapitre commence "
                        f"à {first} parce que la partie {k} y commence."
                    )
                if recalled_out:
                    detection.adjustments.append(
                        f"{recalled_out} chapitre(s) placé(s) dans les répliques rappelées d'une "
                        "partie précédente, laissé(s) de côté : c'est à elle de les couper."
                    )
                if unrecalled:
                    detection.adjustments.append(
                        f"Partie(s) {', '.join(map(str, unrecalled))} lue(s) sans le rappel de la "
                        "précédente : la fenêtre du modèle est trop petite pour les deux."
                    )
                start_of = {t.index: t.start for t in view.turns}
                if cfg.phases_regroup and len(detection.phases) > 1:
                    # The chapters, listed alone, grouped into fewer (ADR 0045).
                    ends = [start_of.get(p.turn) for p in detection.phases[1:]]
                    ends.append(max((s for s in start_of.values() if s is not None), default=0))
                    listed = [
                        f"[{clock(start_of.get(p.turn) or 0)}] ({KIND_WORD[p.kind]}, "
                        f"{max(1, round(((until or 0) - (start_of.get(p.turn) or 0)) / 60))} min) "
                        f"{p.title}"
                        for p, until in zip(detection.phases, ends, strict=True)
                    ]
                    regroup = assembly.assemble(
                        assembly.phase_regroup_prompt(
                            _minutes(starts_all), cfg.phases_minutes_per_chapter
                        ),
                        context,
                        "\n".join(listed),
                        heading="Chapitres à regrouper",
                    )
                    if (
                        assembly.estimate_tokens(regroup.system + regroup.user, cfg.chars_per_token)
                        > budget
                    ):
                        grouped, told = (
                            detection.phases,
                            ["Trop de chapitres pour les regrouper d'un coup : ils sont gardés."],
                        )
                    else:
                        said = call("consolidation", regroup, "regroupement des chapitres")
                        grouped, told = regroup_onto(said, detection.phases, start_of)
                    detection = detection.model_copy(
                        update={"phases": grouped, "adjustments": [*detection.adjustments, *told]}
                    )
                if cfg.phases_review_kinds:
                    # Each chapter read again alone: played or not (ADR 0045).
                    bounds = [start_of.get(p.turn) for p in detection.phases]
                    for k, phase in enumerate(detection.phases):
                        begin = bounds[k]
                        until = next((b for b in bounds[k + 1 :] if b is not None), None)
                        own = _between(lines, begin, until)
                        first = clock(begin) if begin is not None else "0:00"
                        last = clock(until) if until is not None else "la fin"
                        review = assembly.assemble(
                            assembly.phase_review_prompt(first, last),
                            context,
                            "\n".join(line.text for line in own),
                        )
                        if (
                            assembly.estimate_tokens(
                                review.system + review.user, cfg.chars_per_token
                            )
                            > budget
                        ):
                            detection.adjustments.append(
                                f"« {phase.title} » : trop long pour vérifier son type seul, "
                                "type gardé."
                            )
                            continue
                        said = call(
                            "review",
                            review,
                            f"{first} à {last}",
                            answer_format=REVIEW_SCHEMA,
                        )
                        kind = review_kind(said)
                        if kind is None:
                            detection.adjustments.append(
                                f"« {phase.title} » : vérification du type illisible, type gardé."
                            )
                        elif kind != phase.kind:
                            detection.adjustments.append(
                                f"« {phase.title} » : {KIND_WORD[phase.kind]} à la découpe, "
                                f"{KIND_WORD[kind]} à la vérification : {KIND_WORD[kind]} retenu."
                            )
                            detection.phases[k] = phase.model_copy(update={"kind": kind})
                output = detection.model_dump_json(indent=2)
            elif strategy == "sections":
                merged = "\n\n".join(
                    f"## Partie {k} sur {len(answers)}\n\n{text}"
                    for k, text in enumerate(answers, 1)
                )
                final = assembly.assemble(
                    assembly.consolidation_prompt(chosen.prompt, len(answers)),
                    context,
                    merged,
                    heading="Comptes rendus partiels",
                )
                if (
                    assembly.estimate_tokens(final.system + final.user, cfg.chars_per_token)
                    > budget
                ):
                    raise GenerationFailedError(
                        "Même résumée par parties, la séance dépasse la fenêtre du modèle : "
                        "augmentez num_ctx dans les réglages de génération."
                    )
                output = call("consolidation", final, None)
        if is_title:
            output = _clean_title(output)
            if not output:
                raise GenerationFailedError("Le modèle n'a pas proposé de titre.")
    except (GenerationFailedError, OllamaError, PhaseAnswerError) as exc:
        error = GenerationError(type=type(exc).__name__, message=str(exc))
    except BaseException as exc:  # recorded as failed, then raised: never silent (P8)
        error = GenerationError(type=type(exc).__name__, message=str(exc))
        raise
    finally:
        prov = Provenance(
            run_id=run_id,
            session_id=session_id,
            stage=stage,
            app_version=version("coulisses-app"),
            status="failed" if error else "succeeded",
            action_ref=chosen.ref,
            action_name=chosen.name,
            model=model,
            model_digest=digest,
            options=options,
            strategy=strategy,
            source_run_id=view.run_id,
            edits_applied=len(edit_ids),
            edit_ids=edit_ids,
            phases_run_id=phases_run_id,
            notes_digest=notes_digest,
            input_kind=input_kind,
            input_run_id=input_run_id,
            ollama_version=ollama_version,
            calls=calls,
            started_at=started,
            finished_at=clock_now(),
            duration_s=time.monotonic() - t0,
            error=error,
        )
        _finish(data, session_id, run_id, folder, None if error else output, prov)
    return prov


def _check(
    answer: ChatAnswer, estimated: int, num_ctx: int, *, first_line_only: bool = False
) -> None:
    """What Ollama reports decides whether the answer is kept: never a cut text (P8).

    `first_line_only`: only the first line is kept (the title). A cut after it, once the
    line is complete (a line break follows it), cuts nothing that is kept."""
    if answer.prompt_eval_count is None or answer.eval_count is None:
        raise GenerationFailedError(
            "Ollama n'a pas dit combien de tokens il a lus : impossible de vérifier que rien "
            "n'a été coupé, la réponse n'est pas gardée."
        )
    if answer.prompt_eval_count + answer.eval_count >= num_ctx:
        raise GenerationFailedError(
            f"Le modèle a atteint sa fenêtre de {num_ctx} tokens : la réponse pourrait être "
            "tronquée, elle n'est pas gardée."
        )
    if answer.prompt_eval_count > estimated:
        # The estimate decides when to cut into sections: below the truth, it is unsafe.
        raise GenerationFailedError(
            f"Le prompt comptait {answer.prompt_eval_count} tokens, plus que les {estimated} "
            "estimés : baissez caracteres_par_token dans les réglages de génération."
        )
    first_line_whole = "\n" in answer.content.strip()
    if answer.done_reason == "length" and not (first_line_only and first_line_whole):
        raise GenerationFailedError(
            "La réponse a été coupée à sa longueur maximale : elle n'est pas gardée."
        )
    if not answer.content.strip():
        raise GenerationFailedError("Le modèle a renvoyé une réponse vide.")


def _models(client: ModelClient) -> list[InstalledModel]:
    try:
        return client.models()
    except OllamaError:
        return []  # the chat call that follows reports Ollama's absence, with its message


def _version(client: ModelClient) -> str | None:
    try:
        return client.version()
    except OllamaError:
        return None


NO_CONTENT_TITLE = "Séance sans contenu"


class _TitleInput(NamedTuple):
    kind: Literal["chapters", "summary"]
    heading: str
    text: str
    run_id: str | None
    """The run it comes from (the chapter detection, or the summary), kept in provenance."""


def _title_input(
    data: DataDir, session_id: str, view: corrections.CorrectedView
) -> _TitleInput | None:
    """What a title is made from, cheapest first: the chapters, else the latest summary;
    None: the transcript itself."""
    named = [p for p in view.phases if p.title]
    if named:
        return _TitleInput(
            "chapters",
            "Chapitres de la séance",
            "\n".join(
                f"- [{clock(p.start) if p.start is not None else '--:--'}] {p.title} "
                f"({KIND_WORD[p.kind]})"
                for p in named
            ),
            view.phases_run_id,
        )
    conn = connect(data)
    try:
        row = conn.execute(
            "SELECT run_id FROM generation WHERE session_id = ? ORDER BY id DESC LIMIT 1",
            (session_id,),
        ).fetchone()
    finally:
        conn.close()
    if row is not None:
        try:
            text = (data.run_dir(session_id, row["run_id"]) / "output.md").read_text("utf-8")
        except OSError as exc:
            # The transcript then, which is always there; the anomaly is said, not hidden.
            log.warning("summary %s unreadable for a title: %s", row["run_id"], exc)
            return None
        if text.strip():
            return _TitleInput("summary", "Résumé de la séance", text.strip(), row["run_id"])
    return None


def _clean_title(text: str) -> str:
    first = text.strip().splitlines()[0] if text.strip() else ""
    return first.strip().strip("#*_ ").strip("«»\"'“”").strip().rstrip(".").strip()


def _finish(
    data: DataDir,
    session_id: str,
    run_id: str,
    folder: Path,
    output: str | None,
    prov: Provenance,
) -> None:
    if output is not None:
        name = "output.json" if prov.stage == "segment_phases" else "output.md"
        _write_new(folder / name, output + "\n")
    _write_new(folder / "provenance.json", prov.model_dump_json(indent=2))
    conn = connect(data)
    try:
        with conn:
            conn.execute(
                "UPDATE run SET status = ?, finished_at = ?, engine_version = ?,"
                " error_summary = ? WHERE id = ?",
                (
                    prov.status,
                    prov.finished_at.strftime("%Y-%m-%dT%H:%M:%SZ"),
                    prov.app_version,
                    f"{prov.error.type} : {prov.error.message}" if prov.error else None,
                    run_id,
                ),
            )
            if prov.status != "succeeded":
                return
            # Chapters detected on a version no longer shown (another one was shown while
            # they were detected) do not replace those of the version shown; they stay in
            # their folder, and come back when their version is shown again.
            on_shown = (
                prov.stage != "segment_phases"
                or conn.execute(
                    "SELECT 1 FROM run_upstream u JOIN active_run a ON a.run_id = u.upstream_run_id"
                    " WHERE u.run_id = ? AND a.session_id = ? AND a.stage = 'attribute'",
                    (run_id, session_id),
                ).fetchone()
                is not None
            )
            if on_shown:
                conn.execute(
                    "INSERT INTO active_run (session_id, stage, run_id) VALUES (?, ?, ?)"
                    " ON CONFLICT (session_id, stage) DO UPDATE SET run_id = excluded.run_id",
                    (session_id, prov.stage, run_id),
                )
            if prov.stage == "title":
                # The user's own title is never overwritten (title_edited); a session with
                # no content keeps its date as its name.
                if output != NO_CONTENT_TITLE:
                    conn.execute(
                        "UPDATE session SET title = ? WHERE id = ? AND title_edited = 0",
                        (output, session_id),
                    )
            elif prov.stage == "summarize":
                conn.execute(
                    "INSERT INTO generation (session_id, run_id, action_ref, created_at)"
                    " VALUES (?, ?, ?, ?)",
                    (session_id, run_id, prov.action_ref, now_iso()),
                )
    finally:
        conn.close()
