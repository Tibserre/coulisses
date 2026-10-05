"""Where a session's processing stands, read from the database and the run folders, by the
rule of the engine's contract: a run with `provenance.json` is finished; with `spec.json`
only, it runs (`progress.json`, if any, says how far); silent for 15 minutes, it has
probably stopped."""

from __future__ import annotations

import sqlite3
import time
from pathlib import Path

from coulisses.api import ChainConfig, Progress, read_provenance
from pydantic import BaseModel, ValidationError

from coulisses_app.paths import DataDir
from coulisses_app.processing import STAGE_LABELS, error_summary, planned_stages
from coulisses_app.storage.db import connect

SILENCE_LIMIT_S = 15 * 60


class ProgressView(BaseModel):
    phase: str
    done: float
    total: float
    unit: str


class StageView(BaseModel):
    stage: str
    label: str
    state: str
    """pending (not started yet), running, stalled (silent for 15 min), succeeded, failed."""
    run_id: str | None = None
    progress: ProgressView | None = None
    started_at: str | None = None
    finished_at: str | None = None
    duration_s: float | None = None
    max_rss_bytes: int | None = None
    error: str | None = None
    folder_missing: bool = False


def _last_change(folder: Path) -> float | None:
    times = [
        p.stat().st_mtime for p in (folder / "spec.json", folder / "progress.json") if p.is_file()
    ]
    return max(times) if times else None


def _read_progress(folder: Path) -> ProgressView | None:
    path = folder / "progress.json"
    if not path.is_file():
        return None
    try:
        progress = Progress.model_validate_json(path.read_text(encoding="utf-8"))
    except (OSError, ValidationError):
        # Rewritten in one block at most once a second: a partial read is retried at the
        # next poll, nothing is lost.
        return None
    return ProgressView(
        phase=progress.phase, done=progress.done, total=progress.total, unit=progress.unit
    )


def stage_views(data: DataDir, chain: ChainConfig, session_id: str) -> list[StageView]:
    conn = connect(data)
    try:
        job = conn.execute(
            "SELECT id FROM job WHERE session_id = ? ORDER BY id DESC LIMIT 1", (session_id,)
        ).fetchone()
        views: list[StageView] = []
        for stage in planned_stages(chain):
            row = None
            if job is not None:
                row = conn.execute(
                    "SELECT * FROM run WHERE job_id = ? AND stage = ?"
                    " ORDER BY created_at DESC, rowid DESC LIMIT 1",
                    (job["id"], stage.value),
                ).fetchone()
            if row is None:
                row = conn.execute(
                    "SELECT r.* FROM active_run a JOIN run r ON r.id = a.run_id"
                    " WHERE a.session_id = ? AND a.stage = ?",
                    (session_id, stage.value),
                ).fetchone()
            label = STAGE_LABELS.get(stage.value, stage.value)
            if row is None:
                views.append(StageView(stage=stage.value, label=label, state="pending"))
                continue
            views.append(_run_view(data, session_id, stage.value, label, row))
        return views
    finally:
        conn.close()


def _run_view(
    data: DataDir, session_id: str, stage: str, label: str, row: sqlite3.Row
) -> StageView:
    folder = data.run_dir(session_id, row["id"])
    view = StageView(
        stage=stage,
        label=label,
        state=row["status"],
        run_id=row["id"],
        started_at=row["created_at"],
        finished_at=row["finished_at"],
        error=row["error_summary"],
    )
    if not folder.is_dir():
        # A run that never started has no folder; a finished one must have it (Finder?).
        view.folder_missing = row["status"] == "succeeded"
        return view
    prov = read_provenance(folder)
    if prov is not None:
        view.state = prov.status
        view.duration_s = prov.duration_s
        view.max_rss_bytes = prov.max_rss_bytes or None
        view.error = error_summary(prov) or row["error_summary"]
        return view
    if row["status"] in ("queued", "running"):
        view.state = "running"
        view.progress = _read_progress(folder)
        last = _last_change(folder)
        if last is not None and time.time() - last > SILENCE_LIMIT_S:
            view.state = "stalled"
    return view
