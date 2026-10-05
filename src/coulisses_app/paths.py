"""Where the application keeps its data (ADR 0010, 0018).

Real data lives in ~/Coulisses/Données, the default since the user validated step 1
(2026-10-05). Development sets COULISSES_DATA_DIR=~/Coulisses/Données-dev; tests use a
temporary folder.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

DATA_DIR_ENV = "COULISSES_DATA_DIR"
DEFAULT_DATA_DIR = Path.home() / "Coulisses" / "Données"


@dataclass(frozen=True)
class DataDir:
    root: Path

    @classmethod
    def from_env(cls) -> DataDir:
        value = os.environ.get(DATA_DIR_ENV)
        return cls(Path(value).expanduser() if value else DEFAULT_DATA_DIR)

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
