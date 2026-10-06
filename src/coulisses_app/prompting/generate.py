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
import secrets
import sqlite3
import time
from collections.abc import Callable
from datetime import UTC, datetime
from importlib.metadata import version
from pathlib import Path
from typing import Literal, Protocol

from pydantic import BaseModel

from coulisses_app import actions, corrections, notes, sessions, spaces
from coulisses_app.format import clock
from coulisses_app.paths import DataDir
from coulisses_app.phases import ANSWER_SCHEMA, PhaseAnswerError, snap
from coulisses_app.prompting import assembly
from coulisses_app.prompting.ollama import ChatAnswer, InstalledModel, OllamaError
from coulisses_app.storage.db import connect, now_iso

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
    kind: Literal["unique", "section", "consolidation"]
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
    options: dict[str, object] = {
        "num_ctx": cfg.num_ctx,
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
        kind: Literal["unique", "section", "consolidation"],
        prompt: assembly.Prompt,
        covers: str | None,
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
        _check(answer, estimated, cfg.num_ctx, first_line_only=is_title)
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
                },
                ensure_ascii=False,
                indent=2,
            ),
        )
        digest = next((m.digest for m in _models(client) if m.name == model), None)
        ollama_version = _version(client)
        lines = assembly.transcript_lines(view, with_phases=not is_phases)
        whole = "\n".join(line.text for line in lines)
        prompt = assembly.assemble(chosen.prompt, context, whole)
        budget = cfg.num_ctx - reserve
        size = assembly.estimate_tokens(prompt.system + prompt.user, cfg.chars_per_token)
        cut_prompt = assembly.phases_section_prompt if is_phases else assembly.section_prompt
        answers: list[str] = []
        part_firsts: list[str] = []
        if size <= budget:
            output = call("unique", prompt, None)
            answers.append(output)
        else:
            strategy = "sections"
            fixed = assembly.estimate_tokens(
                cut_prompt(chosen.prompt, 99, 99, "00:00:00", "00:00:00")
                + assembly.assemble("", context, "").system
                + assembly.assemble("", context, "").user,
                cfg.chars_per_token,
            )
            parts: list[str] = []
            chunks = _sections(lines, budget - fixed, cfg.chars_per_token)
            for k, chunk in enumerate(chunks, start=1):
                starts = [line.start for line in chunk if line.start is not None]
                first = clock(starts[0]) if starts else "?"
                last = clock(starts[-1]) if starts else "?"
                part_prompt = assembly.assemble(
                    cut_prompt(chosen.prompt, k, len(chunks), first, last),
                    context,
                    "\n".join(line.text for line in chunk),
                )
                parts.append(call("section", part_prompt, f"{first} à {last}"))
                part_firsts.append(first)
            answers = parts
        if is_phases:
            # Each part's chapters, put on the lines they name: no merging call needed.
            detection = snap(answers, [(t.index, t.start) for t in view.turns])
            for k, first in enumerate(part_firsts[1:], start=2):
                detection.adjustments.append(
                    f"Séance lue en {len(part_firsts)} parties : un chapitre commence à "
                    f"{first} parce que la partie {k} y commence."
                )
            output = detection.model_dump_json(indent=2)
        elif strategy == "sections":
            merged = "\n\n".join(
                f"## Partie {k} sur {len(answers)}\n\n{text}" for k, text in enumerate(answers, 1)
            )
            final = assembly.assemble(
                assembly.consolidation_prompt(chosen.prompt, len(answers)),
                context,
                merged,
                heading="Comptes rendus partiels",
            )
            if assembly.estimate_tokens(final.system + final.user, cfg.chars_per_token) > budget:
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
