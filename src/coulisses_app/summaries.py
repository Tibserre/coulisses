"""The session's generations as the interface shows them, and the Markdown export."""

from __future__ import annotations

import re
from datetime import datetime
from typing import Literal

from pydantic import BaseModel

from coulisses_app import actions, corrections, jobs, notes, sessions
from coulisses_app.paths import DataDir
from coulisses_app.phases import PhaseDetection, PhasesProgress
from coulisses_app.prompting import assembly
from coulisses_app.prompting.generate import PHASES_REF, TITLE_REF, Provenance
from coulisses_app.storage.db import connect


class Generation(BaseModel):
    id: int
    run_id: str
    action_ref: str
    action_name: str
    model: str
    created_at: str
    strategy: str
    """unique, or sections (the session was summarised in parts, then consolidated)."""
    calls: int
    duration_s: float
    output: str | None
    """None when the output file is missing (moved or deleted in the Finder)."""
    stale: bool
    """Corrections, chapters, the note after the session or the transcript changed since."""
    problem: str | None = None
    """Why it cannot be read as usual (missing or unreadable files), said as it is."""


class PendingGeneration(BaseModel):
    job_id: int
    action_ref: str
    action_name: str
    model: str
    state: str
    error: str | None


class Generations(BaseModel):
    generations: list[Generation]
    pending: list[PendingGeneration]


def action_name(ref: str, names: dict[str, str]) -> str:
    """`names`: the actions in force, by key. An archived action is shown by its key."""
    if ref == TITLE_REF:
        return assembly.TITLE.name
    if ref == PHASES_REF:
        return assembly.PHASES.name
    return names.get(ref, ref)


def _live_edits(view: corrections.CorrectedView | None) -> tuple[str | None, list[int]]:
    if view is None:
        return None, []
    return view.run_id, sorted(e.id for e in view.edits if not e.reverted)


def list_generations(data: DataDir, session_id: str) -> Generations:
    view = corrections.build_view(data, session_id, recognise=False)
    source, live = _live_edits(view)
    conn = connect(data)
    try:
        rows = conn.execute(
            "SELECT * FROM generation WHERE session_id = ? ORDER BY id DESC", (session_id,)
        ).fetchall()
        names = {a.ref: a.name for a in actions.list_actions(conn)}
        note = notes.after_session(conn, session_id)
        notes_now = notes.digest(note.text if note else None)
        pending = [
            PendingGeneration(
                job_id=j.id,
                action_ref=j.params.action_ref,
                action_name=action_name(j.params.action_ref, names),
                model=j.params.model,
                state=j.state,
                error=j.error,
            )
            for j in jobs.generation_jobs(conn, session_id)
            # The chapters have their own place (phases_status), next to the transcript.
            if isinstance(j.params, jobs.GenerationParams) and j.params.action_ref != PHASES_REF
        ]
    finally:
        conn.close()
    found: list[Generation] = []
    for row in rows:
        folder = data.run_dir(session_id, row["run_id"])
        try:
            prov = Provenance.model_validate_json(
                (folder / "provenance.json").read_text(encoding="utf-8")
            )
        except (OSError, ValueError) as exc:
            # Unreadable or missing provenance: listed as such, with its output if it is
            # there, never hidden (P8).
            output_file = folder / "output.md"
            found.append(
                Generation(
                    id=row["id"],
                    run_id=row["run_id"],
                    action_ref=row["action_ref"],
                    action_name=action_name(row["action_ref"], names),
                    model="?",
                    created_at=row["created_at"],
                    strategy="?",
                    calls=0,
                    duration_s=0.0,
                    output=output_file.read_text(encoding="utf-8")
                    if output_file.is_file()
                    else None,
                    stale=False,
                    problem="Sa provenance est illisible ou introuvable "
                    f"({type(exc).__name__}) dans {folder}.",
                )
            )
            continue
        output_file = folder / "output.md"
        found.append(
            Generation(
                id=row["id"],
                run_id=row["run_id"],
                action_ref=row["action_ref"],
                action_name=prov.action_name,
                model=prov.model,
                created_at=row["created_at"],
                strategy=prov.strategy,
                calls=len(prov.calls),
                duration_s=prov.duration_s,
                output=output_file.read_text(encoding="utf-8") if output_file.is_file() else None,
                stale=prov.source_run_id != source
                or prov.edit_ids != live
                or prov.phases_run_id != (view.phases_run_id if view else None)
                or prov.notes_digest != notes_now,
            )
        )
    return Generations(generations=found, pending=pending)


def prompts_of(data: DataDir, session_id: str, generation_id: int) -> str:
    """Every prompt sent for a generation, word for word (developer mode, P7)."""
    conn = connect(data)
    try:
        row = conn.execute(
            "SELECT run_id FROM generation WHERE id = ? AND session_id = ?",
            (generation_id, session_id),
        ).fetchone()
    finally:
        conn.close()
    if row is None:
        raise KeyError(generation_id)
    folder = data.run_dir(session_id, row["run_id"]) / "calls"
    parts = [
        f"##### {path.name}\n\n{path.read_text(encoding='utf-8')}"
        for path in sorted(folder.glob("*-prompt.txt"))
    ]
    return "\n\n".join(parts)


def set_title(data: DataDir, session_id: str, title: str) -> None:
    """The user's title: never overwritten by a generated one afterwards."""
    cleaned = " ".join(title.split())
    if not cleaned:
        raise ValueError("Le titre ne peut pas être vide.")
    conn = connect(data)
    try:
        with conn:
            conn.execute(
                "UPDATE session SET title = ?, title_edited = 1 WHERE id = ?",
                (cleaned, session_id),
            )
    finally:
        conn.close()


def export_markdown(
    data: DataDir, session_id: str, *, summary: bool, transcript: bool, generation_id: int | None
) -> tuple[str, str, str | None]:
    """(file name, Markdown, the summary written in it: its action's name, or None) of the
    summary and/or the corrected transcript."""
    session = sessions.get_session(data, session_id)
    if session is None:
        raise KeyError(session_id)
    when = datetime.fromisoformat(session.recorded_at.replace("Z", "+00:00")).astimezone()
    title = session.title or f"Séance du {when.strftime('%d/%m/%Y')}"
    # What the model wrote (title, summary, chapters) is made inert; the rest is as typed.
    lines = [
        f"# {inert_markdown(title)}",
        "",
        f"_{session.space_name} · {when.strftime('%d/%m/%Y')}_",
        "",
    ]
    written: str | None = None
    if summary:
        found = list_generations(data, session_id).generations
        chosen = next((g for g in found if generation_id is None or g.id == generation_id), None)
        if chosen and chosen.output:
            lines += [f"## {chosen.action_name}", "", inert_markdown(chosen.output.strip()), ""]
            written = chosen.action_name
    if transcript:
        view = corrections.build_view(data, session_id, recognise=False)
        if view is not None:
            lines += ["## Transcription", ""]
            for line in assembly.transcript_lines(view):
                if line.phase_heading:
                    # « [12:34] ── Chapitre « Titre » (jeu) ── » → a Markdown heading.
                    lines += [
                        f"### {inert_markdown(line.text.split('── ', 1)[1].rstrip(' ─'))}",
                        "",
                    ]
                    continue
                stamp, _, rest = line.text.partition("] ")
                name, _, text = rest.partition(" : ")
                lines.append(f"**{stamp}] {name}** : {text}" if text else line.text)
                lines.append("")
    name = f"{when.strftime('%Y-%m-%d')} {title}".replace("/", "-")
    return f"{name}.md", "\n".join(lines).rstrip() + "\n", written


# Every form of image: inline, by reference, collapsed and shortcut (`![alt]`, its address
# defined elsewhere in the text).
_IMAGE = re.compile(r"!\[([^\]]*)\](?:\([^)]*\)|\[[^\]]*\])?")
_LINK = re.compile(r"(?<!!)\[([^\]]+)\]\([^)]*\)")
_TAG = re.compile(r"<(?=[A-Za-z/!?])")


def inert_markdown(text: str) -> str:
    """The text as the app shows it (SummaryPanel): an image keeps only its description, a
    link only its text, and raw HTML shows as text. Opened in an editor that loads remote
    images, an exported text written by the model can then fetch nothing (P1; security
    review of 2026-10-13). Nothing else changes."""
    text = _IMAGE.sub(lambda m: m.group(1), text)
    text = _LINK.sub(lambda m: m.group(1), text)
    return _TAG.sub("&lt;", text)


class PhasesSteps(BaseModel):
    """How far a running detection is (ADR 0061)."""

    step: Literal["reading", "checking", "done"]
    """Reading part after part, then checking each chapter's kind."""
    part: int
    parts: int
    read_until: float | None
    """Measured time of the last line read: beyond it, nothing is known yet."""
    checked: int
    to_check: int
    problem: str | None = None
    """Why the chapters so far cannot be shown at this step."""


class PhasesStatus(BaseModel):
    """Where the chapter detection stands, for the review screen."""

    state: Literal["none", "queued", "running", "failed", "done"]
    error: str | None = None
    model: str | None = None
    finished_at: datetime | None = None
    adjustments: list[str] = []
    """What the model's answer said that had to be put right (shown in developer mode)."""
    progress: PhasesSteps | None = None
    """While running: how far the detection is (ADR 0061)."""
    progress_problem: str | None = None
    """While running: why its progress cannot be read. The detection goes on: not a failure."""
    provisional: list[corrections.Phase] = []
    """While running: the chapters so far, placed on lines that exist like the final ones,
    the markers set while recording first, the user's changes over them (ADR 0061). All may
    still change until the state is « done »: the last one may go on, a kind may be changed
    when checked. Not to be changed by the user meanwhile; never kept as the result."""


def phases_status(data: DataDir, session_id: str) -> PhasesStatus:
    view = corrections.build_view(data, session_id, recognise=False)
    conn = connect(data)
    try:
        waiting = [
            j
            for j in jobs.generation_jobs(conn, session_id)
            if isinstance(j.params, jobs.GenerationParams) and j.params.action_ref == PHASES_REF
        ]
    finally:
        conn.close()
    if waiting:
        job = waiting[-1]
        assert isinstance(job.params, jobs.GenerationParams)
        state: Literal["queued", "running", "failed"] = (
            "running" if job.state == "running" else "failed" if job.state == "failed" else "queued"
        )
        if state == "running":
            return _running(data, session_id, job.id, job.params.model)
        return PhasesStatus(state=state, error=job.error, model=job.params.model)
    if view is None or view.phases_run_id is None:
        return PhasesStatus(state="none")
    folder = data.run_dir(session_id, view.phases_run_id)
    try:
        prov = Provenance.model_validate_json((folder / "provenance.json").read_text("utf-8"))
        detection = PhaseDetection.model_validate_json((folder / "output.json").read_text("utf-8"))
    except (OSError, ValueError) as exc:
        return PhasesStatus(
            state="done",
            error=f"La détection {view.phases_run_id} est illisible ({type(exc).__name__}).",
        )
    return PhasesStatus(
        state="done",
        model=prov.model,
        finished_at=prov.finished_at,
        adjustments=detection.adjustments,
    )


def _running(data: DataDir, session_id: str, job_id: int, model: str) -> PhasesStatus:
    """A running detection, with how far it is and its chapters so far, read from its run's
    `phases-progress.json` (ADR 0061). Before its first step there is nothing more to say than
    « running ». The chapters so far are shown only on the version of « who said what » they
    were detected on: on another, their lines would be others (P2)."""
    conn = connect(data)
    try:
        row = conn.execute(
            "SELECT id FROM run WHERE job_id = ? AND stage = 'segment_phases'"
            " AND status = 'running' ORDER BY created_at DESC LIMIT 1",
            (job_id,),
        ).fetchone()
        upstream = (
            conn.execute(
                "SELECT upstream_run_id FROM run_upstream WHERE run_id = ?", (row["id"],)
            ).fetchone()
            if row is not None
            else None
        )
    finally:
        conn.close()
    status = PhasesStatus(state="running", model=model)
    if row is None:
        return status
    path = data.run_dir(session_id, row["id"]) / "phases-progress.json"
    try:
        progress = PhasesProgress.model_validate_json(path.read_text("utf-8"))
    except FileNotFoundError:
        return status
    except (OSError, ValueError) as exc:
        status.progress_problem = (
            f"L'avancement des chapitres est illisible ({type(exc).__name__})."
        )
        return status
    status.progress = PhasesSteps(
        step=progress.step,
        part=progress.part,
        parts=progress.parts,
        read_until=progress.read_until,
        checked=progress.checked,
        to_check=progress.to_check,
        problem=progress.problem,
    )
    if progress.detection is not None and progress.detection.phases:
        view = corrections.build_view(
            data, session_id, recognise=False, provisional=(row["id"], progress.detection)
        )
        if view is None:
            return status
        if upstream is None or view.run_id != upstream["upstream_run_id"]:
            status.progress.problem = (
                "Les chapitres en cours sont détectés sur une autre version de la séance : "
                "ils s'afficheront une fois la détection finie."
            )
        else:
            status.provisional = view.phases
    return status
