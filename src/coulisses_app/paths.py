"""Where the application keeps its data (ADR 0010, 0018).

Real data lives in ~/Coulisses/Données, the default since the user validated step 1
(2026-10-05). Development runs `coulisses-app --dev` (the app « Coulisses (dév) », ADR
0040): ~/Coulisses/Données-dev, or COULISSES_DATA_DIR, never the real data. Tests use a
temporary folder.
"""

from __future__ import annotations

import os
import unicodedata
from dataclasses import dataclass
from pathlib import Path

DATA_DIR_ENV = "COULISSES_DATA_DIR"
DEFAULT_DATA_DIR = Path.home() / "Coulisses" / "Données"
DEV_DATA_DIR = Path.home() / "Coulisses" / "Données-dev"


class RealDataRefusedError(RuntimeError):
    """Development was pointed at the real data. The message is shown to the user."""


def _comparable(path: Path) -> str:
    # The Mac's disk ignores case and the composition of accents: « Données » may come
    # decomposed from the Finder or a shell.
    return unicodedata.normalize("NFC", str(path.expanduser().resolve())).casefold()


def is_real_data(path: Path) -> bool:
    """Whether `path` is the real data folder, or inside it."""
    real = _comparable(DEFAULT_DATA_DIR)
    given = _comparable(path)
    if given == real or given.startswith(real.rstrip(os.sep) + os.sep):
        return True
    # By the folders themselves: a name may hide them (a link through a parent folder, the
    # disk's other name under /System/Volumes/Data).
    if not DEFAULT_DATA_DIR.exists():
        return False
    resolved = path.expanduser().resolve()
    return any(
        os.path.samefile(folder, DEFAULT_DATA_DIR)
        for folder in (resolved, *resolved.parents)
        if folder.exists()
    )


@dataclass(frozen=True)
class DataDir:
    root: Path

    @classmethod
    def from_env(cls) -> DataDir:
        value = os.environ.get(DATA_DIR_ENV)
        return cls(Path(value).expanduser() if value else DEFAULT_DATA_DIR)

    @classmethod
    def for_development(cls) -> DataDir:
        """The development folder: COULISSES_DATA_DIR, else Données-dev; never the real
        data, which only the published app serves (ADR 0040)."""
        value = os.environ.get(DATA_DIR_ENV)
        data = cls(Path(value).expanduser() if value else DEV_DATA_DIR)
        if is_real_data(data.root):
            raise RealDataRefusedError(
                f"Coulisses (dév) refuse le dossier des données réelles ({data.root}). "
                f"Elle travaille sur {DEV_DATA_DIR} ou sur le dossier donné par "
                f"{DATA_DIR_ENV}, jamais sur les vraies séances."
            )
        return data

    @property
    def database(self) -> Path:
        return self.root / "coulisses.db"

    @property
    def backups(self) -> Path:
        return self.root / "sauvegardes"

    @property
    def incoming(self) -> Path:
        """Imports being received, before they become a session (same disk: moves are cheap)."""
        return self.root / "imports-en-cours"

    def session_dir(self, session_id: str) -> Path:
        return self.root / "sessions" / session_id

    def sources_dir(self, session_id: str) -> Path:
        return self.session_dir(session_id) / "sources"

    def runs_dir(self, session_id: str) -> Path:
        return self.session_dir(session_id) / "runs"

    def run_dir(self, session_id: str, run_id: str) -> Path:
        return self.runs_dir(session_id) / run_id
