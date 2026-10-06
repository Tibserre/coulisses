"""One generation (a summary or the title) as a run of the application (ADR 0018, 0022).

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

from coulisses_app import corrections, sessions, spaces
from coulisses_app.format import clock
from coulisses_app.paths import DataDir
from coulisses_app.prompting import assembly
from coulisses_app.prompting.ollama import ChatAnswer, InstalledModel, OllamaError
from coulisses_app.storage.db import connect, now_iso

TITLE_REF = "titre"


class ModelClient(Protocol):
    def models(self) -> list[InstalledModel]: ...

    def version(self) -> str | None: ...

    def chat(
        self, model: str, messages: list[dict[str, str]], options: dict[str, object]
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
    stage: Literal["summarize", "title"]
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
    )


def _sections(
    lines: list[tuple[float | None, str]], budget_tokens: int, chars_per_token: float
) -> list[list[tuple[float | None, str]]]:
    """Consecutive lines, each section within the budget. A single line larger than the
    budget is refused rather than cut (P8)."""
    sections: list[list[tuple[float | None, str]]] = [[]]
    size = 0
    for line in lines:
        cost = assembly.estimate_tokens(line[1] + "\n", chars_per_token)
        if cost > budget_tokens:
            raise GenerationFailedError(
                "Une réplique est trop longue pour la fenêtre du modèle, même seule : "
                "augmentez num_ctx dans les réglages de génération."
            )
        if size + cost > budget_tokens and sections[-1]:
            sections.append([])
            size = 0
        sections[-1].append(line)
        size += cost
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
    stage: Literal["summarize", "title"] = "title" if is_title else "summarize"
    chosen = assembly.TITLE if is_title else assembly.action(action_ref)
    view = corrections.build_view(data, session_id)
    session = sessions.get_session(data, session_id)
    if view is None or session is None:
        raise GenerationFailedError("Le transcript de cette séance n'est pas encore prêt.")
    cfg = assembly.settings()
    reserve = cfg.title_reserve if is_title else cfg.response_reserve
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

    run_id = f"{stage}-{secrets.token_hex(4)}"
    folder = data.run_dir(session_id, run_id)
    conn = connect(data)
    try:
        context = assembly.context_block(_context(conn, session), view)
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
        answer = client.chat(model, prompt.messages(), options)
        record.duration_s = time.monotonic() - started_call
        record.prompt_eval_count = answer.prompt_eval_count
        record.eval_count = answer.eval_count
        record.done_reason = answer.done_reason
        record.response_file = f"calls/{index:02d}-response.md"
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
                    "model": model,
                    "options": options,
                    "source_run_id": view.run_id,
                    "edit_ids": edit_ids,
                },
                ensure_ascii=False,
                indent=2,
            ),
        )
        digest = next((m.digest for m in _models(client) if m.name == model), None)
        ollama_version = _version(client)
        lines = assembly.transcript_lines(view)
        whole = "\n".join(line for _, line in lines)
        prompt = assembly.assemble(chosen.prompt, context, whole)
        budget = cfg.num_ctx - reserve
        size = assembly.estimate_tokens(prompt.system + prompt.user, cfg.chars_per_token)
        if size <= budget:
            output = call("unique", prompt, None)
        else:
            strategy = "sections"
            fixed = assembly.estimate_tokens(
                assembly.section_prompt(chosen.prompt, 99, 99, "00:00:00", "00:00:00")
                + assembly.assemble("", context, "").system
                + assembly.assemble("", context, "").user,
                cfg.chars_per_token,
            )
            parts: list[str] = []
            chunks = _sections(lines, budget - fixed, cfg.chars_per_token)
            for k, chunk in enumerate(chunks, start=1):
                starts = [s for s, _ in chunk if s is not None]
                first = clock(starts[0]) if starts else "?"
                last = clock(starts[-1]) if starts else "?"
                part_prompt = assembly.assemble(
                    assembly.section_prompt(chosen.prompt, k, len(chunks), first, last),
                    context,
                    "\n".join(line for _, line in chunk),
                )
                parts.append(call("section", part_prompt, f"{first} à {last}"))
            merged = "\n\n".join(
                f"## Partie {k} sur {len(parts)}\n\n{text}" for k, text in enumerate(parts, 1)
            )
            final = assembly.assemble(
                assembly.consolidation_prompt(chosen.prompt, len(parts)),
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
    except (GenerationFailedError, OllamaError) as exc:
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
            ollama_version=ollama_version,
            calls=calls,
            started_at=started,
            finished_at=clock_now(),
            duration_s=time.monotonic() - t0,
            error=error,
        )
        _finish(data, session_id, run_id, folder, None if error else output, prov, is_title)
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
    is_title: bool,
) -> None:
    if output is not None:
        _write_new(folder / "output.md", output + "\n")
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
            if is_title:
                # The user's own title is never overwritten (title_edited); a session with
                # no content keeps its date as its name.
                if output != NO_CONTENT_TITLE:
                    conn.execute(
                        "UPDATE session SET title = ? WHERE id = ? AND title_edited = 0",
                        (output, session_id),
                    )
            else:
                conn.execute(
                    "INSERT INTO generation (session_id, run_id, action_ref, created_at)"
                    " VALUES (?, ?, ?, ?)",
                    (session_id, run_id, prov.action_ref, now_iso()),
                )
    finally:
        conn.close()
