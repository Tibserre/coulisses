"""Background processing: one chain at a time, through the engine's public API only.

Each stage is a run of the engine in its own folder (`sessions/<id>/runs/<run_id>/`),
recorded in the database. A job resumes after a stop or a crash: the runs it already
finished successfully are reused, the others start again in a new folder (P5, ADR 0018).
Only those made by the engine now installed are reused: after an update of the engine, a
resumed chain never mixes two versions (P7, ADR 0040); the older runs stay on disk.

A job's runs become the session's version all at once, when every stage has succeeded: a
rerun that stops halfway leaves the version shown as it was. The corrections of the
version shown until then are carried over to the new one in the same transaction (step 7).
"""

from __future__ import annotations

import logging
import secrets
import sqlite3
import threading
import time
from collections.abc import Callable
from importlib.metadata import version
from pathlib import Path
from typing import Literal

from coulisses.api import (
    ChainConfig,
    ChainInput,
    ChainRuns,
    ErrorCode,
    Provenance,
    RunNotRunningHereError,
    RunStage,
    RunStillRunningError,
    StageConfig,
    StageName,
    cancel,
    close_interrupted,
    execute_stage,
    read_provenance,
    run_chain,
    stop_all,
)
from pydantic import BaseModel

from coulisses_app import carryover, jobs, languages, mixing, settings
from coulisses_app.capture import KeepAwake
from coulisses_app.paths import DataDir
from coulisses_app.prompting.generate import (
    PHASES_REF,
    GenerationFailedError,
    ModelClient,
    generate,
)
from coulisses_app.prompting.ollama import OllamaClient
from coulisses_app.spaces import SpaceError
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


def activate(conn: sqlite3.Connection, session_id: str, stage: str, run_id: str) -> None:
    """A successful run becomes the one shown and used downstream for its stage. Only ever
    with the rest of its version (`_complete`, `versions.show`)."""
    conn.execute(
        "INSERT INTO active_run (session_id, stage, run_id) VALUES (?, ?, ?)"
        " ON CONFLICT (session_id, stage) DO UPDATE SET run_id = excluded.run_id",
        (session_id, stage, run_id),
    )


STOPPED_CODES = (ErrorCode.INTERRUPTED, ErrorCode.CANCELLED)
"""Codes of a run stopped by its caller rather than failed (engine ADR 0021)."""

HELPERS_STILL_RUNNING = "HelpersStillRunning"
"""The engine's error when a process of a stage still runs 10 s after its stop (v1.13.2):
its folder is not safe to delete yet. Its cause is in `details.previous_error`."""


def stopped_late(prov: Provenance) -> bool:
    """Stopped by its caller (cancelled, interrupted), but a process of it outlived the stop."""
    return (
        prov.error is not None
        and prov.error.type == HELPERS_STILL_RUNNING
        and prov.error.details.get("previous_error") in ("Cancelled", "Interrupted")
    )


class ApplicationStoppingError(RuntimeError):
    """A stage was about to start while the application stops: it is not started."""


class StoppedByUserError(RuntimeError):
    """A stage was about to start in a job the user stopped: it is not started."""


STOP_WAIT_S = 30.0
"""How long stopping a processing waits for its running stages to end."""
STOP_POLL_S = 0.2


class ChainJobResult(BaseModel):
    error: str | None
    """None when every planned stage succeeded."""
    held: bool = False
    """Back in the queue before any stage ran: its language cannot be processed yet."""


class Processor:
    """Runs queued jobs in a background thread, one at a time."""

    def __init__(
        self,
        data: DataDir,
        chain: ChainConfig,
        *,
        models: Path | None = None,
        engine_stage: Callable[[str, Path | None], RunStage] = execute_stage,
        engine_cancel: Callable[[Path], None] = cancel,
        model_client: ModelClient | None = None,
        keep_awake: KeepAwake | None = None,
        after_chain: Callable[[str], None] | None = None,
        waits_for: Callable[[str, str], jobs.WaitsFor | None] | None = None,
    ) -> None:
        """`waits_for(profile, language)`: what a processing in that language waits for
        (`languages.waits_for` on the models of `models` by default)."""
        self.data = data
        self._waits_for: Callable[[str, str], jobs.WaitsFor | None] = (
            waits_for or self._models_waits_for
        )
        # Once a chain is over, what waited for it (the tracks kept in FLAC, ADR 0046).
        self._after_chain = after_chain
        # The Mac does not go to sleep while a job runs (spec §7.4); none in tests.
        self.keep_awake = keep_awake
        self.model_client: ModelClient = model_client or OllamaClient()
        self.chain = chain
        self.models = models
        self._engine_stage = engine_stage
        self._engine_cancel = engine_cancel
        self._stopped_by_user: set[int] = set()
        """Jobs the user stopped: no stage of theirs starts any more."""
        self._stopped_lock = threading.Lock()
        self._cancel_sent: set[str] = set()
        """Runs the engine was asked to cancel: an error they raise is the stop's."""
        self._wake = threading.Event()
        self._stopping = threading.Event()
        self._thread: threading.Thread | None = None
        self.loop_error: str | None = None
        """Last error of the processing loop itself (not of a job), shown by the service."""
        self.release_error: str | None = None
        """Last failure to see again the jobs waiting for a model (at start, after a
        download): they stay waiting until it succeeds; shown by the service."""

    # -- lifecycle ----------------------------------------------------------------------

    def start(self) -> None:
        # Models installed while the app was closed: what waited for them goes. A failure
        # here never stops the service: said, and seen again at the next download.
        self.after_install()
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

    def _models_waits_for(self, profile: str, language: str) -> jobs.WaitsFor | None:
        return languages.waits_for(profile, language, self.models)

    def after_install(self) -> None:
        """Models may have been installed (at start, after a download): what waited for
        them goes. A failure here is said by the service (`release_error`), not only logged,
        until the jobs waiting are seen again (the next start, or the next download)."""
        try:
            self.release_waiting()
        except Exception as exc:
            log.exception("releasing the jobs waiting for a model")
            self.release_error = f"{type(exc).__name__} : {exc}"

    def release_waiting(self) -> None:
        """The jobs waiting for a model, or for another language, seen again: those that
        can now run go back in their turn; the others say what they still wait for (a model
        installed since, of two). After a download, at start, after a language changed."""
        conn = connect(self.data)
        try:
            released = False
            for job in jobs.waiting_jobs(conn):
                assert isinstance(job.params, jobs.ChainParams)
                waits = self._waits_for(job.params.profile, job.params.language)
                if waits != job.params.waits_for_models:
                    jobs.set_waits(conn, job.id, waits, language=job.params.language)
                released = released or waits is None
        finally:
            conn.close()
        self.release_error = None
        if released:
            log.info("jobs waiting for a model may run now")
            self._wake.set()

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

    def stop_processing(
        self, session_id: str, *, wait_s: float | None = None
    ) -> Literal["stopped", "stopping", "nothing"]:
        """The user stops the session's processing (« Arrêter »), waiting or running: no
        stage of it starts any more, and those running are cancelled by the engine (their
        runs stay as it closed them, P5); the stages made are kept, « Reprendre » goes on.
        Returns once it is no longer running (stopped), or after `wait_s` (`STOP_WAIT_S`;
        stopping: it ends when its running stages do); nothing: nothing to stop."""
        conn = connect(self.data)
        try:
            job = jobs.latest_job(conn, session_id)
            if job is None or job.state not in ("queued", "running"):
                return "nothing"
            if job.state == "queued" and jobs.mark_stopped(conn, job.id, only_queued=True):
                log.info("job %s stopped by the user before it started", job.id)
                return "stopped"
            # Running, or claimed a moment ago: stopped where it runs.
            with self._stopped_lock:
                self._stopped_by_user.add(job.id)
            wait_s = STOP_WAIT_S if wait_s is None else wait_s
            deadline = time.monotonic() + wait_s
            while True:
                state = conn.execute("SELECT state FROM job WHERE id = ?", (job.id,)).fetchone()
                if state is None or state["state"] != "running":
                    # Ended: it read the stop already, or finished before it.
                    with self._stopped_lock:
                        self._stopped_by_user.discard(job.id)
                    return "stopped"
                if time.monotonic() > deadline:
                    log.warning("job %s: still running %.0f s after being stopped", job.id, wait_s)
                    return "stopping"
                # Again each time: a stage may have started between two looks.
                for row in conn.execute(
                    "SELECT id FROM run WHERE job_id = ? AND status = 'running'", (job.id,)
                ).fetchall():
                    with self._stopped_lock:
                        self._cancel_sent.add(row["id"])
                    try:
                        self._engine_cancel(self.data.run_dir(session_id, row["id"]))
                    # Not running in this process yet, or no longer (just ended): the next
                    # look tells. Expected, every 0.2 s: not a trace each time.
                    except RunNotRunningHereError:
                        log.debug("job %s: %s not running here", job.id, row["id"])
                    except Exception:
                        log.exception("job %s: cancelling %s", job.id, row["id"])
                time.sleep(STOP_POLL_S)
        finally:
            conn.close()

    # -- one job ------------------------------------------------------------------------

    def run_job(self, job: jobs.Job) -> ChainJobResult:
        if self.keep_awake is not None:
            self.keep_awake.hold()
        try:
            return self._run_job(job)
        finally:
            if self.keep_awake is not None:
                self.keep_awake.release()

    def _run_job(self, job: jobs.Job) -> ChainJobResult:
        if isinstance(job.params, jobs.GenerationParams):
            return self._run_generation_job(job, job.params)
        log.info("job %s: chain for session %s", job.id, job.session_id)
        interrupted: list[str] = []
        failures: list[str] = []
        try:
            result = self._run_chain_job(job, interrupted, failures)
        # A job never takes the processing down: its error is recorded and shown (P8).
        except Exception as exc:
            log.exception("job %s failed", job.id)
            result = ChainJobResult(error=f"{type(exc).__name__} : {exc}")
        with self._stopped_lock:
            stopped = job.id in self._stopped_by_user
            self._stopped_by_user.discard(job.id)
        conn = connect(self.data)
        try:
            if result.held and stopped:
                # Stopped as it went back to wait: the user's stop wins.
                jobs.mark_stopped(conn, job.id)
                result = ChainJobResult(error=jobs.STOPPED)
            elif result.held:
                log.info("job %s waits for its language's models", job.id)
                # A download that ended between the check and the wait did not see it.
                self.release_waiting()
            elif stopped and result.error is not None and interrupted and not failures:
                # The user's choice, not a failure: its runs are kept as they ended. Its
                # tracks stay in WAV until it is resumed and ends (`after_chain`, ADR 0046):
                # converting them now would hold back a deletion asked with the stop.
                # (Stopped once every stage had succeeded: done, its version in place. A
                # stage that failed for real: that failure is what the session says, P8.)
                jobs.mark_stopped(conn, job.id)
                log.info("job %s stopped by the user (%s)", job.id, result.error)
                result = ChainJobResult(error=jobs.STOPPED)
            elif self._stopping.is_set() and interrupted:
                # Stopped by the application, not failed: it resumes at next start. Its
                # interrupted runs keep their provenance (Interrupted).
                jobs.requeue(conn, job.id)
                log.info("job %s back in the queue (application stopping)", job.id)
            else:
                jobs.finish(conn, job.id, error=result.error)
                if result.error is None:
                    self._queue_generations(conn, job.session_id)
                if self._after_chain is not None:
                    self._after_chain(job.session_id)
        finally:
            conn.close()
        return result

    def _queue_generations(self, conn: sqlite3.Connection, session_id: str) -> None:
        """After a successful chain: the chapters, with their model (ADR 0039). The title and the
        summaries are made on demand only (ADR 0025, 0026)."""
        model = settings.writing_model(conn, "chapitres")
        with conn:
            jobs.enqueue_generation(conn, session_id, action_ref=PHASES_REF, model=model)
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
        except (GenerationFailedError, SpaceError) as exc:
            # Messages written for the user (an action archived since it was asked…).
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

    def _run_chain_job(
        self, job: jobs.Job, interrupted: list[str], failures: list[str]
    ) -> ChainJobResult:
        """`interrupted`: the stages stopped (by the application or the user), not run or
        cancelled; `failures`: those that failed for real."""
        conn = connect(self.data)
        try:
            removed = conn.execute(
                "SELECT audio_removed_at FROM session WHERE id = ?", (job.session_id,)
            ).fetchone()
        finally:
            conn.close()
        if removed is not None and removed["audio_removed_at"]:
            return ChainJobResult(
                error="L'audio de cette séance a été supprimé : le traitement ne peut plus "
                "reprendre."
            )
        assert isinstance(job.params, jobs.ChainParams)
        # A model of its language missing, or the language no longer handled: it waits
        # in the queue, saying so, rather than failing (ADR 0072). Nothing is downloaded.
        waits = self._waits_for(job.params.profile, job.params.language)
        if waits is not None:
            conn = connect(self.data)
            try:
                jobs.hold(conn, job.id, waits)
            finally:
                conn.close()
            return ChainJobResult(error=None, held=True)
        try:
            # The microphone with the computer's sound, for a meeting online (ADR 0032).
            audio, mix = mixing.processing_input(self.data, job.session_id)
        except mixing.MixError as exc:
            return ChainJobResult(error=str(exc))
        if mix is not None:
            conn = connect(self.data)
            try:
                jobs.record_mix(conn, job, mix.model_dump())
            finally:
                conn.close()
        if audio is None or not audio.is_file():
            return ChainJobResult(
                error=f"L'enregistrement de la séance est introuvable ({audio}). "
                "A-t-il été déplacé ou supprimé dans le Finder ?"
            )
        engine_run = self._engine_stage(job.session_id, self.models)
        runs_dir = self.data.runs_dir(job.session_id)
        runs_dir.mkdir(parents=True, exist_ok=True)

        params = job.params
        assert isinstance(params, jobs.ChainParams)

        # A rerun keeps stages of the version it starts from: never made again in silence.
        for stage, kept in params.reuse.items():
            kept_dir = runs_dir / kept
            done = read_provenance(kept_dir) if kept_dir.is_dir() else None
            if done is None or done.status != "succeeded":
                return ChainJobResult(
                    error=f"L'étape « {STAGE_LABELS.get(stage, stage)} » de la version de "
                    "départ est introuvable dans le dossier de la séance. A-t-elle été "
                    "supprimée dans le Finder ? La relance s'arrête ; la version affichée n'a "
                    "pas changé."
                )

        engine_now = version("coulisses")  # what the engine writes in its provenance

        def folder_of(stage: StageName) -> Path:
            kept = params.reuse.get(stage.value)
            if kept is not None:
                # A rerun: this stage is the one of the version it starts from, chosen by
                # the user whatever engine made it (ADR 0028).
                return runs_dir / kept
            conn = connect(self.data)
            try:
                row = conn.execute(
                    "SELECT id, engine_version FROM run WHERE job_id = ? AND stage = ?"
                    " AND status = 'succeeded' ORDER BY created_at DESC LIMIT 1",
                    (job.id, stage.value),
                ).fetchone()
            finally:
                conn.close()
            if row is not None and (runs_dir / row["id"]).is_dir():
                if row["engine_version"] == engine_now:
                    return runs_dir / row["id"]
                log.info(
                    "job %s: %s made by engine %s, made again by %s (%s kept)",
                    job.id,
                    stage.value,
                    row["engine_version"],
                    engine_now,
                    row["id"],
                )
            # Never run, failed, its folder deleted in the Finder, or made by another
            # version of the engine: a new run.
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
            with self._stopped_lock:
                if job.id in self._stopped_by_user:
                    interrupted.append(stage.value)
                    raise StoppedByUserError(f"{stage.value} non lancée : traitement arrêté")
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
                with self._stopped_lock:
                    cancelled = folder.name in self._cancel_sent
                    self._cancel_sent.discard(folder.name)
                # Stopped by the application, or cancelled at the user's request: what the
                # stop made of the stage (its cancelling failed on the way: an engine error)
                # is not a failure of the recording. Its error stays in the run, and is said
                # here. A stage not yet cancelled that raises: a failure, said as one.
                if self._stopping.is_set() or cancelled:
                    interrupted.append(stage.value)
                    if cancelled:
                        log.warning(
                            "job %s: %s raised while being cancelled, counted as stopped: %s",
                            job.id,
                            stage.value,
                            exc,
                        )
                else:
                    failures.append(stage.value)
                conn = connect(self.data)
                try:
                    with conn:
                        conn.execute(
                            "UPDATE run SET status = 'failed', finished_at = ?,"
                            " error_summary = ? WHERE id = ?",
                            (now_iso(), f"{type(exc).__name__} : {exc}", folder.name),
                        )
                    if cancelled:
                        # After the run is closed with its error: failing here loses neither.
                        try:
                            jobs.record_stopped_run(conn, job.id, folder.name)
                        except Exception:
                            log.exception("job %s: %s not recorded as stopped", job.id, folder.name)
                finally:
                    conn.close()
                raise
            with self._stopped_lock:
                cancelled = folder.name in self._cancel_sent
                self._cancel_sent.discard(folder.name)
            # Stopped, but a process of it outlived the stop (engine v1.13.2): stopped all
            # the same; its error stays in the run, and the deletion waits for it.
            outlived = stopped_late(prov)
            if prov.error is not None and (prov.error.code in STOPPED_CODES or outlived):
                interrupted.append(stage.value)
            elif prov.error is not None:
                failures.append(stage.value)
            conn = connect(self.data)
            try:
                with conn:
                    _record_finished(conn, folder.name, prov)
                if outlived and cancelled:
                    try:
                        jobs.record_stopped_run(conn, job.id, folder.name)
                    except Exception:
                        log.exception("job %s: %s not recorded as stopped", job.id, folder.name)
            finally:
                conn.close()
            return prov, used

        runs = run_chain(
            self.chain,
            ChainInput(
                audio=audio,
                attendees=params.attendees,
                glossary=tuple(params.glossary),
                language=params.language,
            ),
            folder_of,
            run_stage,  # type: ignore[arg-type]
        )
        failed = [r for r in runs.all if not r.succeeded]
        if failed:
            first = failed[0]
            label = STAGE_LABELS.get(first.provenance.stage, first.provenance.stage)
            # Refused for its language after all: said with what to do.
            said = languages.said_failure(first.provenance, params.profile, self.models)
            return ChainJobResult(
                error=f"Étape « {label} » en échec : "
                f"{said or error_summary(first.provenance) or 'erreur inconnue'}"
            )
        missing = [s.value for s in planned_stages(self.chain) if not _ran(runs, s)]
        if missing:
            return ChainJobResult(error=f"Étapes non lancées : {', '.join(missing)}")
        try:
            self._complete(job.session_id, runs)
        except Exception as exc:
            # The details go to the log; the user reads what happened and what to do.
            log.exception("job %s: the new version could not be put in place: %s", job.id, exc)
            return ChainJobResult(
                error="Le report des corrections sur la nouvelle version a échoué. La version "
                "affichée n'a pas changé ; reprendre le traitement réessaie."
            )
        return ChainJobResult(error=None)

    def _complete(self, session_id: str, runs: ChainRuns) -> None:
        """The job's runs become the session's version, all at once; the corrections of the
        version shown until then are carried over to it first, in the same transaction, and
        the session takes its language, read in its transcription's provenance (P7, ADR
        0072; one that does not say it leaves it as it was). Done again after a crash, it
        changes nothing."""
        target = runs.attribute.folder.name if runs.attribute is not None else None
        conn = connect(self.data)
        try:
            with conn:
                conn.execute("BEGIN IMMEDIATE")
                row = conn.execute(
                    "SELECT run_id FROM active_run WHERE session_id = ? AND stage = 'attribute'",
                    (session_id,),
                ).fetchone()
                source = row["run_id"] if row else None
                if target is not None and source is not None and source != target:
                    carried = carryover.carry(conn, self.data, session_id, source, target)
                    log.info(
                        "session %s: %d correction(s) considered for %s, %d not carried",
                        session_id,
                        len(carried),
                        target,
                        sum(1 for c in carried if not c.applied),
                    )
                for run in runs.all:
                    if run.succeeded:
                        activate(conn, session_id, run.provenance.stage, run.folder.name)
                spoken = next(
                    (
                        languages.of_transcription(run.provenance)
                        for run in runs.text
                        if run.provenance.stage == StageName.TRANSCRIBE and run.succeeded
                    ),
                    None,
                )
                if spoken is not None:
                    conn.execute(
                        "UPDATE session SET language = ? WHERE id = ?", (spoken, session_id)
                    )
        finally:
            conn.close()

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
            # Succeeded or not, it becomes part of a version only when its job ends
            # (`_complete`): the job goes back in the queue and reuses it.
            _record_finished(conn, run_id, prov)
        return None


def _ran(runs: ChainRuns, stage: StageName) -> bool:
    return any(r.provenance.stage == stage for r in runs.all)
