"""Background processing: one chain at a time, through the engine's public API only.

Each stage is a run of the engine in its own folder (`sessions/<id>/runs/<run_id>/`),
recorded in the database. A job resumes after a stop or a crash: the runs it already
finished successfully are reused, the others start again in a new folder (P5, ADR 0018).
"""

from __future__ import annotations

import logging
import secrets
import sqlite3
import threading
from collections.abc import Callable
from pathlib import Path

from coulisses.api import (
    ChainConfig,
    ChainInput,
    ChainRuns,
    ErrorCode,
    Provenance,
    RunStage,
    RunStillRunningError,
    StageConfig,
    StageName,
    close_interrupted,
    execute_stage,
    read_provenance,
    run_chain,
    stop_all,
)
from pydantic import BaseModel

from coulisses_app import jobs, settings
from coulisses_app.paths import DataDir
from coulisses_app.prompting.generate import (
    PHASES_REF,
    TITLE_REF,
    GenerationFailedError,
    ModelClient,
    generate,
)
from coulisses_app.prompting.ollama import OllamaClient
from coulisses_app.sessions import reference_audio_path
from coulisses_app.storage.db import connect, now_iso

log = logging.getLogger(__name__)

ENGINE_STAGES = (StageName.TRANSCRIBE, StageName.ALIGN, StageName.DIARIZE, StageName.ATTRIBUTE)

STAGE_LABELS = {  # shown to the user
    "transcribe": "Transcription",
    "align": "Alignement des mots",
    "diarize": "Qui parle quand",
    "attribute": "Qui a dit quoi",
}


def planned_stages(chain: ChainConfig) -> list[StageName]:
    """The engine stages a chain will run, in display order."""
    return [s for s in ENGINE_STAGES if getattr(chain, s.value) is not None]


def error_summary(prov: Provenance) -> str | None:
    if prov.error is None:
        return None
    return f"{prov.error.type} : {prov.error.message}"


def _record_finished(conn: sqlite3.Connection, run_id: str, prov: Provenance) -> None:
    conn.execute(
        "UPDATE run SET status = ?, finished_at = ?, engine_version = ?, error_summary = ?"
        " WHERE id = ?",
        (
            prov.status,
            prov.finished_at.strftime("%Y-%m-%dT%H:%M:%SZ"),
            prov.coulisses_version,
            error_summary(prov),
            run_id,
        ),
    )


def _activate(conn: sqlite3.Connection, session_id: str, stage: str, run_id: str) -> None:
    """A successful run becomes the one shown and used downstream for its stage."""
    conn.execute(
        "INSERT INTO active_run (session_id, stage, run_id) VALUES (?, ?, ?)"
        " ON CONFLICT (session_id, stage) DO UPDATE SET run_id = excluded.run_id",
        (session_id, stage, run_id),
    )


_STOPPED = (ErrorCode.INTERRUPTED, ErrorCode.CANCELLED)
"""Codes of a run stopped by its caller rather than failed (engine ADR 0021)."""


class ApplicationStoppingError(RuntimeError):
    """A stage was about to start while the application stops: it is not started."""


class ChainJobResult(BaseModel):
    error: str | None
    """None when every planned stage succeeded."""


class Processor:
    """Runs queued jobs in a background thread, one at a time."""

    def __init__(
        self,
        data: DataDir,
        chain: ChainConfig,
        *,
        models: Path | None = None,
        engine_stage: Callable[[str, Path | None], RunStage] = execute_stage,
        model_client: ModelClient | None = None,
    ) -> None:
        self.data = data
        self.model_client: ModelClient = model_client or OllamaClient()
        self.chain = chain
        self.models = models
        self._engine_stage = engine_stage
        self._wake = threading.Event()
        self._stopping = threading.Event()
        self._thread: threading.Thread | None = None
        self.loop_error: str | None = None
        """Last error of the processing loop itself (not of a job), shown by the service."""

    # -- lifecycle ----------------------------------------------------------------------

    def start(self) -> None:
        self._thread = threading.Thread(target=self._loop, name="coulisses-processing")
        self._thread.start()

    def wake(self) -> None:
        self._wake.set()

    def stop(self) -> None:
        """Stop for good: the running stages are stopped and recorded as interrupted by the
        engine (`stop_all`); their job goes back to the queue, to resume at next start."""
        self._stopping.set()
        self._wake.set()
        stop_all()
        if self._thread is not None:
            self._thread.join()

    def _loop(self) -> None:
        while not self._stopping.is_set():
            try:
                job = self._claim()
                if job is not None:
                    self.run_job(job)
                    self.loop_error = None
                    continue
            # The loop must outlive a database error, or later imports would wait forever
            # without a word: the error is logged, shown by the service, and retried (P8).
            except Exception as exc:
                log.exception("processing loop error")
                self.loop_error = f"{type(exc).__name__} : {exc}"
            self._wake.wait(timeout=2.0)
            self._wake.clear()

    def _claim(self) -> jobs.Job | None:
        conn = connect(self.data)
        try:
            return jobs.claim_next(conn)
        finally:
            conn.close()

    # -- one job ------------------------------------------------------------------------

    def run_job(self, job: jobs.Job) -> ChainJobResult:
        if isinstance(job.params, jobs.GenerationParams):
            return self._run_generation_job(job, job.params)
        log.info("job %s: chain for session %s", job.id, job.session_id)
        interrupted: list[str] = []
        try:
            result = self._run_chain_job(job, interrupted)
        # A job never takes the processing down: its error is recorded and shown (P8).
        except Exception as exc:
            log.exception("job %s failed", job.id)
            result = ChainJobResult(error=f"{type(exc).__name__} : {exc}")
        conn = connect(self.data)
        try:
            if self._stopping.is_set() and interrupted:
                # Stopped by the application, not failed: it resumes at next start. Its
                # interrupted runs keep their provenance (Interrupted).
                jobs.requeue(conn, job.id)
                log.info("job %s back in the queue (application stopping)", job.id)
            else:
                jobs.finish(conn, job.id, error=result.error)
                if result.error is None:
                    self._queue_generations(conn, job.session_id)
        finally:
            conn.close()
        return result

    def _queue_generations(self, conn: sqlite3.Connection, session_id: str) -> None:
        """After a successful chain: the chapters (the summaries read them), the title, then
        the summaries the space runs automatically (ADR 0020), with the model chosen for
        each or the default one."""
        space_id = conn.execute(
            "SELECT space_id FROM session WHERE id = ?", (session_id,)
        ).fetchone()[0]
        default = settings.default_model(conn)
        with conn:
            jobs.enqueue_generation(conn, session_id, action_ref=PHASES_REF, model=default)
            jobs.enqueue_generation(conn, session_id, action_ref=TITLE_REF, model=default)
            for action_ref, model in settings.auto_actions(conn, space_id):
                jobs.enqueue_generation(
                    conn, session_id, action_ref=action_ref, model=model or default
                )
        self._wake.set()

    def _run_generation_job(self, job: jobs.Job, params: jobs.GenerationParams) -> ChainJobResult:
        log.info("job %s: %s for session %s", job.id, params.action_ref, job.session_id)
        try:
            prov = generate(
                self.data,
                job.session_id,
                params.action_ref,
                params.model,
                self.model_client,
                job_id=job.id,
            )
            result = ChainJobResult(error=prov.error.message if prov.error else None)
        except GenerationFailedError as exc:
            result = ChainJobResult(error=str(exc))
        # A job never takes the processing down: its error is recorded and shown (P8).
        except Exception as exc:
            log.exception("job %s failed", job.id)
            result = ChainJobResult(error=f"{type(exc).__name__} : {exc}")
        conn = connect(self.data)
        try:
            if self._stopping.is_set() and result.error:
                jobs.requeue(conn, job.id)
            else:
                jobs.finish(conn, job.id, error=result.error)
        finally:
            conn.close()
        return result

    def _run_chain_job(self, job: jobs.Job, interrupted: list[str]) -> ChainJobResult:
        audio = reference_audio_path(self.data, job.session_id)
        if audio is None or not audio.is_file():
            return ChainJobResult(
                error=f"L'enregistrement de la séance est introuvable ({audio}). "
                "A-t-il été déplacé ou supprimé dans le Finder ?"
            )
        engine_run = self._engine_stage(job.session_id, self.models)
        runs_dir = self.data.runs_dir(job.session_id)
        runs_dir.mkdir(parents=True, exist_ok=True)

        def folder_of(stage: StageName) -> Path:
            conn = connect(self.data)
            try:
                row = conn.execute(
                    "SELECT id FROM run WHERE job_id = ? AND stage = ? AND status = 'succeeded'"
                    " ORDER BY created_at DESC LIMIT 1",
                    (job.id, stage.value),
                ).fetchone()
            finally:
                conn.close()
            if row is not None and (runs_dir / row["id"]).is_dir():
                return runs_dir / row["id"]
            # Never run, failed, or its folder deleted in the Finder: a new run.
            return runs_dir / f"{stage.value}-{secrets.token_hex(4)}"

        def run_stage(
            stage: StageName,
            cfg: StageConfig,
            inputs: object,
            folder: Path,
            upstream: tuple[str, ...],
        ) -> tuple[Provenance, Path]:
            done = read_provenance(folder) if folder.is_dir() else None
            if done is not None and done.status == "succeeded":
                log.info("job %s: %s reused (%s)", job.id, stage.value, folder.name)
                return done, folder
            if self._stopping.is_set():
                interrupted.append(stage.value)
                raise ApplicationStoppingError(f"{stage.value} non lancée : l'application s'arrête")
            conn = connect(self.data)
            try:
                with conn:
                    conn.execute(
                        "INSERT INTO run (id, session_id, job_id, stage, status, producer,"
                        " created_at) VALUES (?, ?, ?, ?, 'running', 'engine', ?)",
                        (folder.name, job.session_id, job.id, stage.value, now_iso()),
                    )
                    conn.executemany(
                        "INSERT INTO run_upstream (run_id, upstream_run_id) VALUES (?, ?)",
                        [(folder.name, up) for up in upstream],
                    )
            finally:
                conn.close()
            try:
                prov, used = engine_run(stage, cfg, inputs, folder, upstream)  # type: ignore[arg-type]
            except BaseException as exc:
                if self._stopping.is_set():
                    interrupted.append(stage.value)
                conn = connect(self.data)
                try:
                    with conn:
                        conn.execute(
                            "UPDATE run SET status = 'failed', finished_at = ?,"
                            " error_summary = ? WHERE id = ?",
                            (now_iso(), f"{type(exc).__name__} : {exc}", folder.name),
                        )
                finally:
                    conn.close()
                raise
            if prov.error is not None and prov.error.code in _STOPPED:
                interrupted.append(stage.value)
            conn = connect(self.data)
            try:
                with conn:
                    _record_finished(conn, folder.name, prov)
                    if prov.status == "succeeded":
                        _activate(conn, job.session_id, stage.value, folder.name)
            finally:
                conn.close()
            return prov, used

        params = job.params
        assert isinstance(params, jobs.ChainParams)
        runs = run_chain(
            self.chain,
            ChainInput(audio=audio, attendees=params.attendees, glossary=tuple(params.glossary)),
            folder_of,
            run_stage,  # type: ignore[arg-type]
        )
        failed = [r for r in runs.all if not r.succeeded]
        if failed:
            first = failed[0]
            label = STAGE_LABELS.get(first.provenance.stage, first.provenance.stage)
            return ChainJobResult(
                error=f"Étape « {label} » en échec : "
                f"{error_summary(first.provenance) or 'erreur inconnue'}"
            )
        missing = [s.value for s in planned_stages(self.chain) if not _ran(runs, s)]
        if missing:
            return ChainJobResult(error=f"Étapes non lancées : {', '.join(missing)}")
        return ChainJobResult(error=None)

    # -- after a crash ------------------------------------------------------------------

    def recover(self) -> list[str]:
        """Before starting: close the runs a crashed application left behind and put their
        jobs back in the queue. A job whose run the engine refuses to close stays as it is,
        and the refusal is returned, to be shown; the next start tries again."""
        problems: list[str] = []
        conn = connect(self.data)
        try:
            for job in jobs.running_jobs(conn):
                rows = conn.execute(
                    "SELECT id, session_id FROM run WHERE job_id = ?"
                    " AND status IN ('queued', 'running')",
                    (job.id,),
                ).fetchall()
                refused = [
                    problem
                    for row in rows
                    if (problem := self._close(conn, row["session_id"], row["id"]))
                ]
                if refused:
                    problems.extend(refused)
                    continue
                jobs.requeue(conn, job.id)
                log.info("job %s was interrupted: back in the queue", job.id)
        finally:
            conn.close()
        return problems

    def _close(self, conn: sqlite3.Connection, session_id: str, run_id: str) -> str | None:
        folder = self.data.run_dir(session_id, run_id)
        producer = conn.execute("SELECT producer FROM run WHERE id = ?", (run_id,)).fetchone()
        if producer is not None and producer[0] == "app":
            # The application's own run (a generation): its folder stays as it was left,
            # the database says it was interrupted; the job runs it again.
            with conn:
                conn.execute(
                    "UPDATE run SET status = 'failed', finished_at = ?, error_summary = ?"
                    " WHERE id = ?",
                    (
                        now_iso(),
                        "Interrompue : Coulisses s'est arrêté pendant la génération",
                        run_id,
                    ),
                )
            return None
        prov = read_provenance(folder) if folder.is_dir() else None
        if prov is None and not (folder / "spec.json").is_file():
            with conn:
                conn.execute(
                    "UPDATE run SET status = 'failed', finished_at = ?, error_summary = ?"
                    " WHERE id = ?",
                    (now_iso(), "Interrompue avant d'avoir démarré", run_id),
                )
            return None
        if prov is None:
            try:
                prov = close_interrupted(folder)
            except RunStillRunningError as exc:
                message = f"Exécution {run_id} : le moteur refuse de la clore ({exc})"
                with conn:
                    conn.execute("UPDATE run SET error_summary = ? WHERE id = ?", (message, run_id))
                return message
        with conn:
            _record_finished(conn, run_id, prov)
            if prov.status == "succeeded":
                _activate(conn, session_id, prov.stage, run_id)
        return None


def _ran(runs: ChainRuns, stage: StageName) -> bool:
    return any(r.provenance.stage == stage for r in runs.all)
