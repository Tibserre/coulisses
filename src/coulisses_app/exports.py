"""Export to a folder chosen once (spec §7.11, question Q7 decided 2026-10-07, ADR 0030).

The user picks a folder of the Mac (often one that Google Drive keeps in sync); « Exporter
vers le dossier » writes the session's Markdown file there. The application only writes a
file on the disk: it never sends anything anywhere (P1). An export never replaces a file
without the user saying so (P8).
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

from pydantic import BaseModel

from coulisses_app import summaries
from coulisses_app.paths import DataDir
from coulisses_app.spaces import NotFoundError, SpaceError
from coulisses_app.storage.db import connect

log = logging.getLogger(__name__)

FOLDER_KEY = "dossier_export"
PROMPT = '"Dossier où Coulisses dépose les exports"'


class ExportFolder(BaseModel):
    folder: str | None
    present: bool
    """The folder chosen is there and writable (a disk unplugged, a Drive logged out: no)."""


class FileExistsInFolderError(SpaceError):
    """A file of the same name is already in the folder: replaced only if asked."""


def _usable(path: Path) -> bool:
    return path.is_dir() and os.access(path, os.W_OK)


def get_folder(conn: sqlite3.Connection) -> ExportFolder:
    row = conn.execute("SELECT value FROM app_setting WHERE key = ?", (FOLDER_KEY,)).fetchone()
    if row is None:
        return ExportFolder(folder=None, present=False)
    folder = str(json.loads(row[0]))
    return ExportFolder(folder=folder, present=_usable(Path(folder)))


def set_folder(conn: sqlite3.Connection, folder: str | None) -> ExportFolder:
    with conn:
        if folder is None:
            conn.execute("DELETE FROM app_setting WHERE key = ?", (FOLDER_KEY,))
            return get_folder(conn)
        path = Path(folder).expanduser()
        if not path.is_dir():
            raise SpaceError("Ce dossier n'existe pas.")
        if not os.access(path, os.W_OK):
            raise SpaceError("Coulisses ne peut pas écrire dans ce dossier.")
        conn.execute(
            "INSERT INTO app_setting (key, value) VALUES (?, ?)"
            " ON CONFLICT (key) DO UPDATE SET value = excluded.value",
            (FOLDER_KEY, json.dumps(str(path.resolve()))),
        )
    return get_folder(conn)


def choose_folder() -> str | None:
    """The Finder's own « choose a folder » window, on the user's Mac (the service runs
    there). None when the user cancels."""
    if sys.platform != "darwin":
        raise SpaceError("Le choix d'un dossier par le Finder n'existe que sur macOS.")
    try:
        result = subprocess.run(
            [
                "osascript",
                "-e",
                f"POSIX path of (choose folder with prompt {PROMPT})",
            ],
            capture_output=True,
            text=True,
            timeout=600,
        )
    except subprocess.TimeoutExpired as exc:
        raise SpaceError("Aucun dossier n'a été choisi en dix minutes : rien n'a changé.") from exc
    except OSError as exc:
        log.warning("choose folder: %s", exc)
        raise SpaceError("La fenêtre du Finder n'a pas pu s'ouvrir.") from exc
    if result.returncode != 0:
        if "-128" in result.stderr:  # « Annuler »
            return None
        # The raw message goes to the log; the user reads what happened.
        log.warning("choose folder: osascript said %s", result.stderr.strip())
        raise SpaceError("La fenêtre du Finder n'a pas pu s'ouvrir.")
    return result.stdout.strip() or None


def export_to_folder(
    data: DataDir,
    session_id: str,
    *,
    summary: bool,
    transcript: bool,
    generation_id: int | None,
    replace: bool,
) -> tuple[str, str | None]:
    """Write the session's Markdown file in the export folder; returns its name and the
    summary written in it (none: the transcript only)."""
    conn = connect(data)
    try:
        chosen = get_folder(conn)
    finally:
        conn.close()
    if chosen.folder is None:
        raise SpaceError("Aucun dossier d'export n'est choisi : choisissez-le dans les Réglages.")
    if not chosen.present:
        raise SpaceError(
            "Le dossier d'export est introuvable ou n'accepte pas d'écriture. Est-il sur un "
            "disque débranché, ou Google Drive est-il déconnecté ?"
        )
    try:
        name, text, written = summaries.export_markdown(
            data, session_id, summary=summary, transcript=transcript, generation_id=generation_id
        )
    except KeyError as exc:
        raise NotFoundError("Séance introuvable.") from exc
    target = Path(chosen.folder) / name.replace(":", "-")
    if target.exists() and not replace:
        raise FileExistsInFolderError(f"« {target.name} » est déjà dans le dossier d'export.")
    # Written beside, then put in place: a reader (Google Drive) never sees half a file.
    partial = target.with_name(f".{target.name}.coulisses")
    try:
        partial.write_text(text, encoding="utf-8")
        partial.replace(target)
    except OSError as exc:
        try:
            partial.unlink(missing_ok=True)
        except OSError as left:  # the disk itself gone: said in the log, the cause kept
            log.warning("export: %s could not be removed: %s", partial, left)
        log.warning("export of %s to %s: %s", session_id, target, exc)
        raise SpaceError(
            f"Le fichier n'a pas pu être écrit dans le dossier d'export ({exc.strerror or exc})."
            " Le disque est-il plein, ou Google Drive déconnecté ?"
        ) from exc
    return target.name, written
