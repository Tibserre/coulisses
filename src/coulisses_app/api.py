"""The local service (ADR 0002): a JSON API on 127.0.0.1 and the built interface."""

from __future__ import annotations

import asyncio
import logging
import mimetypes
import os
import sqlite3
import subprocess
from collections.abc import AsyncGenerator, Generator
from contextlib import asynccontextmanager, contextmanager
from datetime import UTC, datetime
from importlib.metadata import version
from pathlib import Path
from typing import Annotated, Any, Literal
from urllib.parse import quote

from coulisses.api import (
    ChainConfig,
    ErrorCode,
    RunNotSucceededError,
    models_dir,
    read_provenance,
)
from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import (
    FileResponse,
    HTMLResponse,
    JSONResponse,
    PlainTextResponse,
    Response,
    StreamingResponse,
)
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from coulisses_app import (
    actions,
    capture,
    corrections,
    engine_models,
    exports,
    jobs,
    marks,
    mixing,
    notes,
    projects,
    retention,
    search,
    sessions,
    settings,
    spaces,
    summaries,
    versions,
)
from coulisses_app.media import UnreadableAudioError
from coulisses_app.paths import DataDir
from coulisses_app.processing import Processor
from coulisses_app.prompting.generate import PHASES_REF, TITLE_REF, ModelClient
from coulisses_app.prompting.ollama import InstalledModel, OllamaClient, OllamaError
from coulisses_app.status import StageView, stage_views
from coulisses_app.storage.db import connect

log = logging.getLogger(__name__)


class AppInfo(BaseModel):
    data_dir: str
    engine_version: str
    app_version: str
    pid: int
    """The service's process: the app in the Dock takes back one left running alone."""
    profile: str
    recovery_problems: list[str]
    processing_error: str | None
    """The processing loop's own last error (not a job's): the queue may be stuck."""


SERVICE_LOG = Path.home() / "Library" / "Logs" / "Coulisses" / "service.log"
"""Where the app in the Dock writes the service's output (ADR 0034)."""

Folder = Literal["donnees", "modeles", "journal"]


class Folders(BaseModel):
    """What can be shown in the Finder from the settings."""

    data: str
    models: str
    log: str | None
    """None until the app in the Dock has started the service once."""


_FOLDER_FIELDS: dict[str, str] = {"donnees": "data", "modeles": "models", "journal": "log"}


class Activity(BaseModel):
    """What quitting the app would interrupt (ADR 0034)."""

    recording: bool
    processing: bool
    """A stage or a generation running now (it resumes at the next start)."""
    downloading: bool = False
    """A model downloading, or an environment installing (it resumes next time)."""


class SessionDetail(BaseModel):
    session: sessions.Session
    source: sessions.AudioSource | None
    stages: list[StageView]
    version: str | None = None
    """The « who said what » run of the version shown; None before the first is complete."""
    rerun: jobs.Rerun | None = None
    """What the latest processing of the session runs again; None for the first one."""
    other_sources: list[sessions.AudioSource] = []
    """Tracks beside the reference: microphones added (kept, not processed yet), the
    computer's sound (mixed in, ADR 0032)."""
    mix: mixing.MixFacts | None = None
    """The microphone mixed with the computer's sound, once made (from the job that used
    it, once the audio is purged); whether the computer's sound held anything."""


class RerunRequest(BaseModel):
    etape: jobs.Rerun
    """transcribe: the transcription (and the alignment); diarize: the voices."""
    presents: int | None = Field(default=None, ge=1)
    """For the voices: the minimum of voices to look for (P3)."""


class ResumeRequest(BaseModel):
    presents: int | None = Field(default=None, ge=1)


class AttendeesRequest(BaseModel):
    person_ids: list[int] = []
    unnamed: int | None = None


class SpaceRequest(BaseModel):
    name: str | None = None
    voice_recognition: bool | None = None
    archived: bool | None = None
    template: str = "vide"
    """At creation only: impro, reunion or vide (ADR 0020)."""


class OfferedActionRequest(BaseModel):
    action_ref: str | None = None


class SpaceActionRequest(BaseModel):
    auto_run: bool
    model: str | None = None


class GenerationRequest(BaseModel):
    action_ref: str
    model: str | None = None
    """None: the default model (and a given one becomes the default)."""


class ModelRequest(BaseModel):
    model: str


class TitleRequest(BaseModel):
    title: str


class ModelsInfo(BaseModel):
    reachable: bool
    error: str | None
    default: str
    models: list[InstalledModel]


class RecordingRequest(BaseModel):
    espace: int | None = None
    projet: int | None = None
    presents: list[int] = []
    non_nommes: int | None = None
    micro: int | None = None
    """Index of the input device; None: the system's default microphone."""
    micros_en_plus: list[int] = []
    """Microphones added, recording at the same time (often an iPhone), each its file."""
    son_ordinateur: bool = False
    """The computer's sound too: a meeting online or hybrid (ADR 0032)."""


class MarkerRequest(BaseModel):
    kind: marks.MarkerKind
    at_s: float | None = None
    """None: now. A time already recorded: a marker taken back by mistake, put back."""


class TimedNoteRequest(BaseModel):
    text: str
    at_s: float
    """Recorded time when its first letter was typed."""


class RetentionInfo(BaseModel):
    settings: retention.RetentionSettings
    coming: list[retention.Announcement]
    """Purges announced and not done yet: the banner."""
    journal: list[retention.LogEntry]
    backups: list[retention.Backup]
    problems: list[str]
    """What the last check could not do."""


class RetentionRequest(BaseModel):
    retention_days: int
    notice_days: int


class ProjectRequest(BaseModel):
    name: str | None = None
    archived: bool | None = None


class SessionProjectRequest(BaseModel):
    projet: int | None
    """None: no project."""


class ExportFolderRequest(BaseModel):
    dossier: str | None


class FolderExportRequest(BaseModel):
    contenu: str = "tout"
    """resume, transcript or tout."""
    resume: int | None = None
    remplacer: bool = False
    """Replace a file of the same name already in the folder (asked to the user first)."""


class FolderExported(BaseModel):
    fichier: str
    resume: str | None
    """The summary written in it (its action's name); None: the transcript only."""


class KeepAudioRequest(BaseModel):
    keep: bool


class AudioRemoved(BaseModel):
    session: sessions.Session
    problems: list[str]
    """What stayed on the disk; the audio is gone from Coulisses anyway."""


class Deleted(BaseModel):
    problems: list[str]
    """What could not be done on the disk; the session is gone from Coulisses anyway."""


class PowerInfo(BaseModel):
    on_battery: bool


class ActionRequest(BaseModel):
    name: str
    description: str = ""
    prompt: str


class NoteRequest(BaseModel):
    text: str


class PersonRequest(BaseModel):
    name: str | None = None
    kind: str | None = None
    role: str | None = None
    archived: bool | None = None


class GlossaryRequest(BaseModel):
    term: str | None = None
    category: str | None = None
    variants: list[str] | None = None
    archived: bool | None = None


class Imported(BaseModel):
    id: str


def _not_found(what: str) -> HTTPException:
    return HTTPException(status_code=404, detail=what)


def create_app(
    data: DataDir,
    chain: ChainConfig,
    *,
    profile: str,
    processor: Processor | None,
    web_dir: Path | None,
    recovery_problems: list[str] | None = None,
    model_client: ModelClient | None = None,
    recorder: capture.Recorder | None = None,
    watcher: retention.Watcher | None = None,
    engine_store: engine_models.EngineModels | None = None,
) -> FastAPI:
    """`processor` is started and stopped with the service; None in tests that drive it.
    `model_client` answers the list of installed models (Ollama by default)."""
    model_client = model_client or (processor.model_client if processor else OllamaClient())
    recorder = recorder or capture.Recorder(data)
    engine_store = engine_store or engine_models.EngineModels(profile)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncGenerator[None]:
        if processor is not None:
            processor.start()
        if watcher is not None:
            watcher.start()
        try:
            yield
        finally:
            if watcher is not None:
                watcher.stop()
            try:
                # Downloads stop; their partial folders are kept (engine ADR 0035).
                engine_store.shutdown()
            finally:
                try:
                    # A recording in progress is closed properly, never lost (spec §7.2).
                    recorder.shutdown(profile=profile)
                finally:
                    if processor is not None:
                        processor.stop()

    app = FastAPI(title="Coulisses", lifespan=lifespan, docs_url=None, redoc_url=None)

    @contextmanager
    def _db() -> Generator[sqlite3.Connection]:
        conn = connect(data)
        try:
            yield conn
        finally:
            conn.close()

    @app.exception_handler(spaces.SpaceError)
    async def refused(_: Request, exc: spaces.SpaceError) -> JSONResponse:
        """Requests that cannot be honoured, with the French reason (spaces, corrections)."""
        status = (
            404
            if isinstance(exc, spaces.NotFoundError)
            else 409
            if isinstance(exc, corrections.VersionChangedError)
            else 422
        )
        return JSONResponse(status_code=status, content={"detail": str(exc)})

    problems = recovery_problems or []

    @app.get("/api/etat")
    def info() -> AppInfo:
        return AppInfo(
            data_dir=str(data.root),
            engine_version=version("coulisses"),
            app_version=version("coulisses-app"),
            pid=os.getpid(),
            profile=profile,
            recovery_problems=problems,
            processing_error=processor.loop_error if processor else None,
        )

    def _folders() -> Folders:
        return Folders(
            data=str(data.root),
            models=str(models_dir()),
            log=str(SERVICE_LOG) if SERVICE_LOG.is_file() else None,
        )

    @app.get("/api/dossiers")
    def folders() -> Folders:
        return _folders()

    @app.post("/api/dossiers/{quoi}/ouvrir", status_code=204)
    def open_folder(quoi: Folder) -> None:
        """Shown in the Finder (the log selected in its folder). Nothing else is opened."""
        target = getattr(_folders(), _FOLDER_FIELDS[quoi])
        if target is None or not Path(target).exists():
            raise _not_found("Ce dossier n'existe pas encore.")
        command = ["open", "-R", target] if quoi == "journal" else ["open", target]
        try:
            subprocess.run(command, check=True, timeout=10, capture_output=True)
        except (OSError, subprocess.SubprocessError) as exc:
            log.warning("opening %s: %s", target, exc)
            raise HTTPException(
                status_code=422, detail="Le Finder n'a pas pu ouvrir ce dossier."
            ) from exc

    # -- the engine's models (spec §7.12, ADR 0036) ------------------------------------

    @app.get("/api/moteur/modeles")
    def engine_models_view() -> engine_models.ModelsView:
        return engine_store.view()

    @app.get("/api/moteur/telechargements")
    def engine_actions() -> list[engine_models.ModelAction]:
        return engine_store.actions()

    @app.post("/api/moteur/modeles/{cle}/telecharger", status_code=202)
    def download_model(cle: str) -> engine_models.ModelAction:
        return engine_store.start("model", cle)

    @app.post("/api/moteur/environnements/{nom}/installer", status_code=202)
    def install_environment(nom: str) -> engine_models.ModelAction:
        return engine_store.start("environment", nom)

    @app.post("/api/moteur/{genre}/{nom}/annuler", status_code=204)
    def cancel_engine_task(genre: Literal["modeles", "environnements"], nom: str) -> None:
        engine_store.cancel("model" if genre == "modeles" else "environment", nom)

    @app.delete("/api/moteur/{genre}/{nom}/telechargement", status_code=204)
    def forget_engine_task(genre: Literal["modeles", "environnements"], nom: str) -> None:
        engine_store.forget("model" if genre == "modeles" else "environment", nom)

    @app.delete("/api/moteur/modeles/{cle}", status_code=204)
    def remove_model(cle: str) -> None:
        engine_store.remove(cle)

    @app.get("/api/activite")
    def activity() -> Activity:
        with _db() as conn:
            running = bool(jobs.running_jobs(conn))
        return Activity(
            recording=recorder.state() is not None,
            processing=running,
            downloading=engine_store.downloading(),
        )

    @app.get("/api/seances")
    def list_sessions() -> list[sessions.Session]:
        return sessions.list_sessions(data)

    @app.post("/api/seances", status_code=201)
    def import_session(
        fichier: Annotated[UploadFile, File()],
        espace: Annotated[int | None, Form()] = None,
        projet: Annotated[int | None, Form()] = None,
        presents: Annotated[list[int] | None, Form()] = None,
        non_nommes: Annotated[int | None, Form()] = None,
        date_fichier_ms: Annotated[int | None, Form()] = None,
    ) -> Imported:
        """`presents`: the people checked (repeated field); `non_nommes`: people present
        whom nobody names, added to them as a minimum of voices (P3)."""
        recorded_at = (
            datetime.fromtimestamp(date_fichier_ms / 1000, tz=UTC) if date_fichier_ms else None
        )
        try:
            session_id = sessions.import_recording(
                data,
                fichier.file,
                fichier.filename or "enregistrement",
                space_id=espace,
                project_id=projet,
                attendee_ids=presents or [],
                unnamed_attendees=non_nommes,
                recorded_at=recorded_at,
                profile=profile,
            )
        except (UnreadableAudioError, ValueError) as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        if processor is not None:
            processor.wake()
        return Imported(id=session_id)

    @app.get("/api/seances/{session_id}")
    def session_detail(session_id: str) -> SessionDetail:
        session = sessions.get_session(data, session_id)
        if session is None:
            raise _not_found("Séance introuvable.")
        conn = connect(data)
        try:
            shown = conn.execute(
                "SELECT run_id FROM active_run WHERE session_id = ? AND stage = 'attribute'",
                (session_id,),
            ).fetchone()
            latest = jobs.latest_job(conn, session_id)
            used_mix = jobs.latest_mix(conn, session_id)
        finally:
            conn.close()
        return SessionDetail(
            session=session,
            source=sessions.reference_source(data, session_id),
            stages=stage_views(data, chain, session_id),
            version=shown["run_id"] if shown else None,
            other_sources=sessions.other_sources(data, session_id),
            rerun=latest.params.rerun
            if latest is not None and isinstance(latest.params, jobs.ChainParams)
            else None,
            # Once the audio is purged, from the job that used it (P7).
            mix=mixing.read_facts(data, session_id)
            or (mixing.MixFacts.model_validate(used_mix) if used_mix is not None else None),
        )

    @app.get("/api/seances/{session_id}/versions")
    def session_versions(session_id: str) -> versions.Versions:
        return versions.list_versions(data, session_id)

    @app.post("/api/seances/{session_id}/versions/{run_id}/afficher")
    def show_version(session_id: str, run_id: str) -> versions.Versions:
        versions.show(data, session_id, run_id)
        return versions.list_versions(data, session_id)

    @app.post("/api/seances/{session_id}/relancer", status_code=202)
    def rerun(session_id: str, demande: RerunRequest) -> sessions.Session:
        """Run the transcription or the voices again, from the version shown: a new version,
        which replaces it once complete, with the corrections carried over."""
        attendees = demande.presents if demande.etape == "diarize" else None
        versions.request_rerun(
            data, session_id, demande.etape, attendees=attendees, profile=profile
        )
        if processor is not None:
            processor.wake()
        session = sessions.get_session(data, session_id)
        assert session is not None
        return session

    @app.post("/api/seances/{session_id}/reprendre")
    def resume(session_id: str, demande: ResumeRequest | None = None) -> sessions.Session:
        """Put the latest failed job back in the queue: the stages that succeeded are kept.
        `presents` changes the minimum of voices (after « too few speakers »)."""
        conn = connect(data)
        try:
            job = jobs.latest_job(conn, session_id)
            if job is None:
                raise _not_found("Cette séance n'a jamais été traitée.")
            if job.state != "failed":
                raise HTTPException(
                    status_code=409, detail="Le traitement de cette séance n'est pas en échec."
                )
            if retention.audio_status(data, session_id).state == "removed":
                raise HTTPException(status_code=409, detail=versions.AUDIO_GONE)
            if demande is not None and demande.presents is not None:
                # Only a diarization refused for too few voices may be redone with another
                # minimum: after any other failure, the successful runs (diarization
                # included) are reused, and they were made with the former minimum.
                if not _refused_for_too_few_voices(data, session_id, job.id):
                    raise HTTPException(
                        status_code=409,
                        detail="Le nombre de présents ne peut changer qu'après une diarisation "
                        "refusée pour trop peu de voix.",
                    )
                jobs.resume_with_attendees(conn, job, demande.presents)
            else:
                jobs.requeue(conn, job.id)
        finally:
            conn.close()
        if processor is not None:
            processor.wake()
        session = sessions.get_session(data, session_id)
        assert session is not None
        return session

    @app.get("/api/seances/{session_id}/executions/{run_id}/provenance")
    def provenance(session_id: str, run_id: str) -> dict[str, Any]:
        folder = _run_folder(data, session_id, run_id)
        prov = read_provenance(folder)
        if prov is None:
            raise HTTPException(status_code=409, detail="Cette étape n'est pas terminée.")
        return prov.model_dump(mode="json")

    @app.get("/api/seances/{session_id}/transcript")
    def transcript(session_id: str) -> corrections.CorrectedView:
        """The corrected view: the active run with the user's corrections applied."""
        return _corrected(data, session_id)

    # `version`: the « who said what » run the page shows; a correction made for another
    # one is refused (409), never written elsewhere (step 7).
    @app.post("/api/seances/{session_id}/corrections", status_code=201)
    def add_correction(
        session_id: str, demande: corrections.Request, version: str | None = None
    ) -> corrections.CorrectedView:
        return corrections.add(data, session_id, demande.model_dump(), version=version)

    @app.post("/api/seances/{session_id}/corrections/{edit_id}/annuler")
    def undo_correction(
        session_id: str, edit_id: int, version: str | None = None
    ) -> corrections.CorrectedView:
        return corrections.undo(data, session_id, edit_id, version=version)

    @app.post("/api/seances/{session_id}/corrections/{edit_id}/retablir")
    def redo_correction(
        session_id: str, edit_id: int, version: str | None = None
    ) -> corrections.CorrectedView:
        return corrections.redo(data, session_id, edit_id, version=version)

    @app.post("/api/seances/{session_id}/repliques/{turn}/texte-d-origine")
    def reset_text(
        session_id: str, turn: int, version: str | None = None
    ) -> corrections.CorrectedView:
        return corrections.reset_text(data, session_id, turn, version=version)

    @app.put("/api/seances/{session_id}/presents")
    def set_attendees(session_id: str, demande: AttendeesRequest) -> sessions.Session:
        spaces.set_attendees(data, session_id, demande.person_ids, demande.unnamed)
        session = sessions.get_session(data, session_id)
        assert session is not None
        return session

    # -- spaces, people, glossary ---------------------------------------------------

    @app.get("/api/espaces")
    def list_spaces() -> list[spaces.Space]:
        return spaces.list_spaces(data)

    @app.post("/api/espaces", status_code=201)
    def create_space(demande: SpaceRequest) -> spaces.Space:
        return spaces.create_space(data, demande.name or "", demande.template)

    @app.get("/api/espaces/{space_id}/actions")
    def space_actions(space_id: int) -> list[spaces.SpaceAction]:
        return spaces.space_actions(data, space_id)

    @app.put("/api/espaces/{space_id}/resume-propose")
    def set_offered_action(
        space_id: int, demande: OfferedActionRequest
    ) -> list[spaces.SpaceAction]:
        if demande.action_ref is not None:
            _check_action(data, demande.action_ref)
        return spaces.set_offered_action(data, space_id, demande.action_ref)

    @app.put("/api/espaces/{space_id}/actions/{action_ref}")
    def set_space_action(
        space_id: int, action_ref: str, demande: SpaceActionRequest
    ) -> list[spaces.SpaceAction]:
        _check_action(data, action_ref)
        return spaces.set_space_action(
            data, space_id, action_ref, auto_run=demande.auto_run, model=demande.model
        )

    # -- summaries --------------------------------------------------------------------

    @app.get("/api/modeles")
    def models() -> ModelsInfo:
        conn = connect(data)
        try:
            default = settings.default_model(conn)
        finally:
            conn.close()
        try:
            found = model_client.models()
        except OllamaError as exc:
            return ModelsInfo(reachable=False, error=str(exc), default=default, models=[])
        return ModelsInfo(reachable=True, error=None, default=default, models=found)

    @app.put("/api/reglages/modele")
    def set_model(demande: ModelRequest) -> ModelsInfo:
        conn = connect(data)
        try:
            settings.set_default_model(conn, demande.model)
        finally:
            conn.close()
        return models()

    # -- recording (step 6, ADR 0005) ---------------------------------------------------

    @app.get("/api/micros")
    def microphones() -> list[capture.InputDevice]:
        try:
            return recorder.list_devices()
        except capture.RecordingError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        except Exception as exc:  # PortAudio could not list them: said, the cause logged
            log.exception("listing the microphones")
            raise HTTPException(
                status_code=503, detail="Les micros n'ont pas pu être listés."
            ) from exc

    @app.get("/api/alimentation")
    def power() -> PowerInfo:
        return PowerInfo(on_battery=capture.on_battery())

    @app.get("/api/enregistrement")
    def recording() -> capture.RecordingState | None:
        return recorder.state()

    @app.post("/api/enregistrement", status_code=201)
    def start_recording(demande: RecordingRequest) -> capture.RecordingState:
        return recorder.start(
            space_id=demande.espace,
            project_id=demande.projet,
            attendee_ids=demande.presents,
            unnamed_attendees=demande.non_nommes,
            device_index=demande.micro,
            extra_device_indexes=demande.micros_en_plus,
            system=demande.son_ordinateur,
        )

    @app.post("/api/enregistrement/pause")
    def pause_recording() -> capture.RecordingState:
        return recorder.pause()

    @app.post("/api/enregistrement/reprise")
    def resume_recording() -> capture.RecordingState:
        return recorder.resume()

    @app.post("/api/enregistrement/arret")
    def stop_recording() -> capture.StopResult:
        stopped = recorder.stop(profile=profile)
        if processor is not None and stopped.processing:
            processor.wake()
        return stopped

    @app.post("/api/enregistrement/marqueurs", status_code=201)
    def mark(demande: MarkerRequest) -> capture.RecordingState:
        return recorder.mark(demande.kind, demande.at_s)

    @app.post("/api/enregistrement/marqueurs/{marker_id}/retirer")
    def unmark(marker_id: int) -> capture.RecordingState:
        return recorder.take_back("marker", marker_id)

    @app.post("/api/enregistrement/notes", status_code=201)
    def timed_note(demande: TimedNoteRequest) -> capture.RecordingState:
        return recorder.note(demande.text, demande.at_s)

    @app.post("/api/enregistrement/notes/{note_id}/retirer")
    def unnote(note_id: int) -> capture.RecordingState:
        return recorder.take_back("note", note_id)

    @app.get("/api/enregistrement/niveaux")
    async def recording_levels() -> StreamingResponse:
        """The state ten times a second while recording (server-sent events), for the meter;
        the stream ends with the recording."""

        async def events() -> AsyncGenerator[str]:
            while (state := recorder.state()) is not None:
                yield f"data: {state.model_dump_json()}\n\n"
                await asyncio.sleep(0.1)
            yield "event: fin\ndata: {}\n\n"

        return StreamingResponse(events(), media_type="text/event-stream")

    @app.post("/api/seances/{session_id}/traiter", status_code=202)
    def process_session(session_id: str) -> sessions.Session:
        """Start the processing a recording left waiting (stopped on battery, or repaired)."""
        sessions.start_processing(data, session_id, profile=profile)
        if processor is not None:
            processor.wake()
        session = sessions.get_session(data, session_id)
        assert session is not None
        return session

    @app.get("/api/actions")
    def list_actions() -> list[actions.ActionInfo]:
        with _db() as conn:
            return actions.list_actions(conn)

    @app.post("/api/actions", status_code=201)
    def create_action(demande: ActionRequest) -> actions.ActionInfo:
        with _db() as conn:
            return actions.create(conn, demande.name, demande.description, demande.prompt)

    @app.put("/api/actions/{ref}")
    def update_action(ref: str, demande: ActionRequest) -> actions.ActionInfo:
        with _db() as conn:
            return actions.update(conn, ref, demande.name, demande.description, demande.prompt)

    @app.post("/api/actions/{ref}/restaurer")
    def restore_action(ref: str) -> actions.ActionInfo:
        with _db() as conn:
            return actions.restore(conn, ref)

    @app.post("/api/actions/{ref}/dupliquer", status_code=201)
    def duplicate_action(ref: str) -> actions.ActionInfo:
        with _db() as conn:
            return actions.duplicate(conn, ref)

    @app.post("/api/actions/{ref}/archiver", status_code=204)
    def archive_action(ref: str) -> Response:
        with _db() as conn:
            actions.archive(conn, ref)
        return Response(status_code=204)

    @app.get("/api/seances/{session_id}/notes")
    def session_notes(session_id: str) -> notes.Note | None:
        with _db() as conn:
            return notes.after_session(conn, session_id)

    @app.put("/api/seances/{session_id}/notes")
    def write_notes(session_id: str, demande: NoteRequest) -> notes.Note:
        with _db() as conn:
            return notes.set_after_session(conn, session_id, demande.text)

    @app.get("/api/seances/{session_id}/resumes")
    def generations(session_id: str) -> summaries.Generations:
        return summaries.list_generations(data, session_id)

    @app.post("/api/seances/{session_id}/resumes", status_code=202)
    def request_generation(session_id: str, demande: GenerationRequest) -> summaries.Generations:
        _check_action(data, demande.action_ref)
        if corrections.build_view(data, session_id) is None:
            raise HTTPException(status_code=409, detail="Le transcript n'est pas encore prêt.")
        conn = connect(data)
        try:
            if demande.model:
                # Chosen by hand: it becomes the default (ADR 0022).
                settings.set_default_model(conn, demande.model)
            model = demande.model or settings.default_model(conn)
            with conn:
                jobs.enqueue_generation(
                    conn, session_id, action_ref=demande.action_ref, model=model
                )
        finally:
            conn.close()
        if processor is not None:
            processor.wake()
        return summaries.list_generations(data, session_id)

    @app.get("/api/seances/{session_id}/chapitres")
    def phases(session_id: str) -> summaries.PhasesStatus:
        return summaries.phases_status(data, session_id)

    @app.post("/api/seances/{session_id}/chapitres", status_code=202)
    def detect_phases(session_id: str) -> summaries.PhasesStatus:
        """Detect the chapters again (the user's changes to them stay in force)."""
        if corrections.build_view(data, session_id) is None:
            raise HTTPException(status_code=409, detail="Le transcript n'est pas encore prêt.")
        conn = connect(data)
        try:
            with conn:
                jobs.enqueue_generation(
                    conn, session_id, action_ref=PHASES_REF, model=settings.default_model(conn)
                )
        finally:
            conn.close()
        if processor is not None:
            processor.wake()
        return summaries.phases_status(data, session_id)

    @app.get("/api/seances/{session_id}/resumes/{generation_id}/prompts")
    def generation_prompts(session_id: str, generation_id: int) -> PlainTextResponse:
        try:
            return PlainTextResponse(summaries.prompts_of(data, session_id, generation_id))
        except KeyError as exc:
            raise _not_found("Résumé introuvable.") from exc

    @app.patch("/api/seances/{session_id}")
    def rename_session(session_id: str, demande: TitleRequest) -> sessions.Session:
        if sessions.get_session(data, session_id) is None:
            raise _not_found("Séance introuvable.")
        try:
            summaries.set_title(data, session_id, demande.title)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        session = sessions.get_session(data, session_id)
        assert session is not None
        return session

    @app.get("/api/seances/{session_id}/export")
    def export(session_id: str, contenu: str = "tout", resume: int | None = None) -> Response:
        if contenu not in ("resume", "transcript", "tout"):
            raise HTTPException(status_code=422, detail="Contenu inconnu.")
        try:
            name, text, _ = summaries.export_markdown(
                data,
                session_id,
                summary=contenu in ("resume", "tout"),
                transcript=contenu in ("transcript", "tout"),
                generation_id=resume,
            )
        except KeyError as exc:
            raise _not_found("Séance introuvable.") from exc
        return Response(
            text,
            media_type="text/markdown; charset=utf-8",
            headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(name)}"},
        )

    @app.patch("/api/espaces/{space_id}")
    def update_space(space_id: int, demande: SpaceRequest) -> spaces.Space:
        return spaces.update_space(
            data,
            space_id,
            name=demande.name,
            voice_recognition=demande.voice_recognition,
            archived=demande.archived,
        )

    @app.get("/api/espaces/{space_id}/personnes")
    def list_people(space_id: int) -> list[spaces.Person]:
        return spaces.list_people(data, space_id)

    @app.post("/api/espaces/{space_id}/personnes", status_code=201)
    def add_person(space_id: int, demande: PersonRequest) -> spaces.Person:
        return spaces.add_person(
            data,
            space_id,
            kind=demande.kind or "member",
            name=demande.name or "",
            role=demande.role,
        )

    @app.patch("/api/personnes/{person_id}")
    def update_person(person_id: int, demande: PersonRequest) -> spaces.Person:
        return spaces.update_person(
            data,
            person_id,
            name=demande.name,
            role=demande.role,
            kind=demande.kind,
            archived=demande.archived,
        )

    @app.get("/api/espaces/{space_id}/glossaire")
    def list_glossary(space_id: int) -> list[spaces.GlossaryEntry]:
        return spaces.list_glossary(data, space_id)

    @app.post("/api/espaces/{space_id}/glossaire", status_code=201)
    def add_entry(space_id: int, demande: GlossaryRequest) -> spaces.GlossaryEntry:
        return spaces.add_entry(
            data,
            space_id,
            term=demande.term or "",
            category=demande.category,
            variants=demande.variants,
        )

    @app.patch("/api/glossaire/{entry_id}")
    def update_entry(entry_id: int, demande: GlossaryRequest) -> spaces.GlossaryEntry:
        return spaces.update_entry(
            data,
            entry_id,
            term=demande.term,
            category=demande.category,
            variants=demande.variants,
            archived=demande.archived,
        )

    @app.get("/api/seances/{session_id}/audio")
    def audio(session_id: str) -> FileResponse:
        # With the computer's sound, the mix once made: everyone is heard (ADR 0032).
        path = mixing.listening_path(data, session_id)
        if path is None:
            raise _not_found("Séance introuvable.")
        status = retention.audio_status(data, session_id)
        if status.state == "removed":
            raise _not_found("L'audio de cette séance a été supprimé.")
        if not path.is_file():
            raise _not_found(
                "L'enregistrement est introuvable dans le dossier de la séance. "
                "A-t-il été déplacé ou supprimé dans le Finder ?"
            )
        media_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        return FileResponse(path, media_type=media_type)

    # -- projects, search, export to a folder (step 8, ADR 0030) -----------------------

    @app.get("/api/projets")
    def list_projects() -> list[projects.Project]:
        return projects.list_projects(data)

    @app.post("/api/espaces/{space_id}/projets", status_code=201)
    def create_project(space_id: int, demande: ProjectRequest) -> projects.Project:
        return projects.create(data, space_id, demande.name or "")

    @app.patch("/api/projets/{project_id}")
    def update_project(project_id: int, demande: ProjectRequest) -> projects.Project:
        return projects.update(data, project_id, name=demande.name, archived=demande.archived)

    @app.put("/api/seances/{session_id}/projet")
    def set_session_project(session_id: str, demande: SessionProjectRequest) -> sessions.Session:
        projects.set_session_project(data, session_id, demande.projet)
        session = sessions.get_session(data, session_id)
        assert session is not None
        return session

    @app.get("/api/recherche")
    def search_sessions(q: str = "") -> search.Results:
        return search.search(data, q)

    @app.get("/api/export")
    def export_folder() -> exports.ExportFolder:
        conn = connect(data)
        try:
            return exports.get_folder(conn)
        finally:
            conn.close()

    @app.put("/api/export")
    def set_export_folder(demande: ExportFolderRequest) -> exports.ExportFolder:
        conn = connect(data)
        try:
            return exports.set_folder(conn, demande.dossier)
        finally:
            conn.close()

    @app.post("/api/export/choisir")
    def choose_export_folder() -> exports.ExportFolder:
        """The Finder's window to choose the folder; cancelled, nothing changes."""
        chosen = exports.choose_folder()
        conn = connect(data)
        try:
            return exports.set_folder(conn, chosen) if chosen else exports.get_folder(conn)
        finally:
            conn.close()

    @app.post("/api/seances/{session_id}/exporter-dossier")
    def export_to_folder(session_id: str, demande: FolderExportRequest) -> FolderExported:
        if demande.contenu not in ("resume", "transcript", "tout"):
            raise HTTPException(status_code=422, detail="Contenu inconnu.")
        try:
            name, written = exports.export_to_folder(
                data,
                session_id,
                summary=demande.contenu in ("resume", "tout"),
                transcript=demande.contenu in ("transcript", "tout"),
                generation_id=demande.resume,
                replace=demande.remplacer,
            )
        except exports.FileExistsInFolderError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return FolderExported(fichier=name, resume=written)

    # -- keeping the audio, deleting (step 9, ADR 0029) --------------------------------

    def _retention_info() -> RetentionInfo:
        conn = connect(data)
        try:
            settings_now = retention.get_settings(conn)
        finally:
            conn.close()
        return RetentionInfo(
            settings=settings_now,
            coming=retention.coming(data),
            journal=retention.journal(data),
            backups=retention.backups(data),
            problems=watcher.problems if watcher is not None else [],
        )

    @app.get("/api/conservation")
    def retention_info() -> RetentionInfo:
        return _retention_info()

    @app.put("/api/conservation")
    def set_retention(demande: RetentionRequest) -> RetentionInfo:
        conn = connect(data)
        try:
            retention.set_settings(conn, demande.retention_days, demande.notice_days)
        finally:
            conn.close()
        if watcher is not None:
            # Announced at once with the new delays; a failed check is said, the settings
            # are saved all the same.
            try:
                watcher.run_once()
            except Exception as exc:
                log.exception("retention check after a change of settings")
                watcher.problems = [f"La vérification de la conservation a échoué : {exc}"]
        return _retention_info()

    def _session_now(session_id: str) -> sessions.Session:
        session = sessions.get_session(data, session_id)
        if session is None:
            raise _not_found("Séance introuvable.")
        return session

    @app.put("/api/seances/{session_id}/garder-audio")
    def keep_audio(session_id: str, demande: KeepAudioRequest) -> sessions.Session:
        retention.keep_audio(data, session_id, demande.keep)
        return _session_now(session_id)

    @app.post("/api/seances/{session_id}/prolonger")
    def extend_audio(session_id: str) -> sessions.Session:
        retention.extend(data, session_id)
        return _session_now(session_id)

    @app.post("/api/seances/{session_id}/supprimer-audio")
    def remove_audio(session_id: str) -> AudioRemoved:
        left = retention.remove_audio(data, session_id, "audio_deletion")
        return AudioRemoved(session=_session_now(session_id), problems=left)

    @app.delete("/api/seances/{session_id}")
    def delete_session(session_id: str) -> Deleted:
        return Deleted(problems=retention.delete_session(data, session_id))

    _mount_interface(app, web_dir)
    return app


def _check_action(data: DataDir, ref: str) -> None:
    if ref in (TITLE_REF, PHASES_REF):
        return  # the title and the chapters can be made again too
    conn = connect(data)
    try:
        actions.get_action(conn, ref)  # NotFoundError: 404, with its message
    finally:
        conn.close()


def _corrected(data: DataDir, session_id: str) -> corrections.CorrectedView:
    try:
        view = corrections.build_view(data, session_id)
    except RunNotSucceededError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise _not_found(
            "Le résultat du traitement est introuvable. "
            "A-t-il été déplacé ou supprimé dans le Finder ?"
        ) from exc
    if view is None:
        raise _not_found("Le transcript n'est pas encore prêt.")
    return view


def _refused_for_too_few_voices(data: DataDir, session_id: str, job_id: int) -> bool:
    """Whether the job's latest diarization failed with `too_few_speakers` (engine code)."""
    conn = connect(data)
    try:
        row = conn.execute(
            "SELECT id, status FROM run WHERE job_id = ? AND stage = 'diarize'"
            " ORDER BY created_at DESC, rowid DESC LIMIT 1",
            (job_id,),
        ).fetchone()
    finally:
        conn.close()
    if row is None or row["status"] != "failed":
        return False
    folder = data.run_dir(session_id, row["id"])
    prov = read_provenance(folder) if folder.is_dir() else None
    return (
        prov is not None
        and prov.error is not None
        and prov.error.code == ErrorCode.TOO_FEW_SPEAKERS
    )


def _run_folder(data: DataDir, session_id: str, run_id: str) -> Path:
    conn = connect(data)
    try:
        row: sqlite3.Row | None = conn.execute(
            "SELECT id FROM run WHERE id = ? AND session_id = ?", (run_id, session_id)
        ).fetchone()
    finally:
        conn.close()
    if row is None:
        raise _not_found("Exécution introuvable.")
    folder = data.run_dir(session_id, run_id)
    if not folder.is_dir():
        raise _not_found(
            f"Le dossier de l'exécution est introuvable ({folder}). "
            "A-t-il été déplacé ou supprimé dans le Finder ?"
        )
    return folder


_NOT_BUILT = """<!doctype html><html lang="fr"><meta charset="utf-8"><title>Coulisses</title>
<body style="font-family: -apple-system, sans-serif; padding: 3rem; max-width: 40rem">
<h1>L'interface n'est pas construite</h1>
<p>Construisez-la une fois : <code>cd web &amp;&amp; npm install &amp;&amp; npm run build</code>,
puis rechargez cette page. L'API répond déjà sur <code>/api/etat</code>.</p></body></html>"""


class _Interface(StaticFiles):
    """The built interface. The page is checked again at each load, so that a new build is
    seen on the next reload; its scripts and styles carry a hash in their name."""

    def file_response(self, *args: Any, **kwargs: Any) -> Response:
        response = super().file_response(*args, **kwargs)
        if response.media_type == "text/html":
            response.headers["Cache-Control"] = "no-cache"
        return response


def _mount_interface(app: FastAPI, web_dir: Path | None) -> None:
    if web_dir is not None and (web_dir / "index.html").is_file():
        app.mount("/", _Interface(directory=web_dir, html=True), name="interface")
        return

    @app.get("/", response_class=HTMLResponse)
    def not_built() -> str:
        return _NOT_BUILT
