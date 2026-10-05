"""The local service (ADR 0002): a JSON API on 127.0.0.1 and the built interface."""

from __future__ import annotations

import mimetypes
import sqlite3
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from importlib.metadata import version
from pathlib import Path
from typing import Annotated, Any

from coulisses.api import (
    AttributedTranscript,
    ChainConfig,
    RunNotSucceededError,
    read_output,
    read_provenance,
)
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from coulisses_app import jobs, sessions
from coulisses_app.media import UnreadableAudioError
from coulisses_app.paths import DataDir
from coulisses_app.processing import Processor
from coulisses_app.status import StageView, stage_views
from coulisses_app.storage.db import connect


class AppInfo(BaseModel):
    data_dir: str
    engine_version: str
    app_version: str
    profile: str
    recovery_problems: list[str]
    processing_error: str | None
    """The processing loop's own last error (not a job's): the queue may be stuck."""


class SessionDetail(BaseModel):
    session: sessions.Session
    source: sessions.AudioSource | None
    stages: list[StageView]


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
) -> FastAPI:
    """`processor` is started and stopped with the service; None in tests that drive it."""

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncGenerator[None]:
        if processor is not None:
            processor.start()
        try:
            yield
        finally:
            if processor is not None:
                processor.stop()

    app = FastAPI(title="Coulisses", lifespan=lifespan, docs_url=None, redoc_url=None)
    problems = recovery_problems or []

    @app.get("/api/etat")
    def info() -> AppInfo:
        return AppInfo(
            data_dir=str(data.root),
            engine_version=version("coulisses"),
            app_version=version("coulisses-app"),
            profile=profile,
            recovery_problems=problems,
            processing_error=processor.loop_error if processor else None,
        )

    @app.get("/api/seances")
    def list_sessions() -> list[sessions.Session]:
        return sessions.list_sessions(data)

    @app.post("/api/seances", status_code=201)
    def import_session(
        fichier: Annotated[UploadFile, File()],
        presents: Annotated[int | None, Form()] = None,
        date_fichier_ms: Annotated[int | None, Form()] = None,
    ) -> Imported:
        recorded_at = (
            datetime.fromtimestamp(date_fichier_ms / 1000, tz=UTC) if date_fichier_ms else None
        )
        try:
            session_id = sessions.import_recording(
                data,
                fichier.file,
                fichier.filename or "enregistrement",
                attendee_count=presents,
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
        return SessionDetail(
            session=session,
            source=sessions.reference_source(data, session_id),
            stages=stage_views(data, chain, session_id),
        )

    @app.post("/api/seances/{session_id}/reprendre")
    def resume(session_id: str) -> sessions.Session:
        """Put the latest failed job back in the queue: the stages that succeeded are kept."""
        conn = connect(data)
        try:
            job = jobs.latest_job(conn, session_id)
            if job is None:
                raise _not_found("Cette séance n'a jamais été traitée.")
            if job.state != "failed":
                raise HTTPException(
                    status_code=409, detail="Le traitement de cette séance n'est pas en échec."
                )
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
    def transcript(session_id: str) -> dict[str, Any]:
        conn = connect(data)
        try:
            row = conn.execute(
                "SELECT run_id FROM active_run WHERE session_id = ? AND stage = 'attribute'",
                (session_id,),
            ).fetchone()
        finally:
            conn.close()
        if row is None:
            raise _not_found("Le transcript n'est pas encore prêt.")
        folder = _run_folder(data, session_id, row["run_id"])
        try:
            result = read_output(folder, AttributedTranscript)
        except RunNotSucceededError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return {"run_id": row["run_id"], **result.model_dump(mode="json")}

    @app.get("/api/seances/{session_id}/audio")
    def audio(session_id: str) -> FileResponse:
        path = sessions.reference_audio_path(data, session_id)
        if path is None:
            raise _not_found("Séance introuvable.")
        if not path.is_file():
            raise _not_found(
                f"L'enregistrement est introuvable ({path}). "
                "A-t-il été déplacé ou supprimé dans le Finder ?"
            )
        media_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        return FileResponse(path, media_type=media_type)

    _mount_interface(app, web_dir)
    return app


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


def _mount_interface(app: FastAPI, web_dir: Path | None) -> None:
    if web_dir is not None and (web_dir / "index.html").is_file():
        app.mount("/", StaticFiles(directory=web_dir, html=True), name="interface")
        return

    @app.get("/", response_class=HTMLResponse)
    def not_built() -> str:
        return _NOT_BUILT
