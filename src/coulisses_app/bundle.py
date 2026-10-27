"""What the service takes from the repository in development, and from Coulisses.app once
built (ADR 0040): the built interface, and the tools it and the engine run (ffmpeg,
ffprobe, uv, the computer's sound program). Where uv keeps the Python and the cache of the
engine's environments is the engine's own (v1.7.0: under `envs_dir()/uv`).

The app in the Dock says the service runs from the .app by giving COULISSES_RESSOURCES,
its `Contents/Resources` folder. Nothing is ever written there: the .app stays as signed.
"""

from __future__ import annotations

import functools
import logging
import os
import subprocess
from collections.abc import Mapping
from dataclasses import dataclass
from importlib.metadata import version
from pathlib import Path

log = logging.getLogger(__name__)

RESOURCES_ENV = "COULISSES_RESSOURCES"
REPOSITORY = Path(__file__).resolve().parents[2]
BUILD_ID_FILE = "identifiant-de-version"
"""Written by the build (`scripts/construire.py`): which code the .app holds (ADR 0064)."""

SYSTEM_AUDIO_PROGRAM = "coulisses-son-ordinateur"
# Found by name on the PATH, by the service and by the engine (its README's prerequisites).
TOOLS = ("ffmpeg", "ffprobe", "uv", SYSTEM_AUDIO_PROGRAM)


class IncompleteAppError(RuntimeError):
    """The .app lacks something it was built with. The message is shown to the user."""


def _read_build_id(root: Path) -> str | None:
    """What the build wrote, or None when the file is missing, unreadable or empty."""
    try:
        return (root / BUILD_ID_FILE).read_text(encoding="utf-8").strip() or None
    except OSError:
        return None


@dataclass(frozen=True)
class Resources:
    root: Path | None
    """The .app's `Contents/Resources`; None when the service runs from the repository."""

    @classmethod
    def from_env(cls, environ: Mapping[str, str] = os.environ) -> Resources:
        value = environ.get(RESOURCES_ENV)
        return cls(Path(value).expanduser() if value else None)

    @property
    def web_dir(self) -> Path:
        return self.root / "web" if self.root else REPOSITORY / "web" / "dist"

    @property
    def tools_dir(self) -> Path | None:
        return self.root / "bin" if self.root else None

    @property
    def system_audio_program(self) -> Path | None:
        """Built with the .app; None from the repository, where it is built when needed."""
        return self.tools_dir / SYSTEM_AUDIO_PROGRAM if self.tools_dir else None

    def check(self) -> None:
        """Raises `IncompleteAppError` if the .app lacks one of its parts."""
        if self.root is None or self.tools_dir is None:
            return
        missing = [] if (self.web_dir / "index.html").is_file() else ["l'interface"]
        if not _read_build_id(self.root):
            missing.append("l'identifiant de version")
        missing += [
            tool
            for tool in TOOLS
            if not (self.tools_dir / tool).is_file()
            or not os.access(self.tools_dir / tool, os.X_OK)
        ]
        if missing:
            raise IncompleteAppError(
                f"Coulisses est incomplète : il manque {', '.join(missing)} dans {self.root}. "
                "Réinstallez-la depuis le DMG."
            )

    def build_identifier(self) -> str:
        """Which code runs (ADR 0064): `vX.Y.Z` on a version, else `vX.Y.Z-<commits>-g<commit>`
        (`-modifie` with changes; the commit alone without any tag, as `release.py` says it).
        From the .app, what its build wrote (`IncompleteAppError` without it); from the
        repository, `git describe`; without git, the package's version, and the log says why."""
        if self.root is not None:
            found = _read_build_id(self.root)
            if not found:
                raise IncompleteAppError(
                    f"Coulisses est incomplète : il manque l'identifiant de version dans "
                    f"{self.root}. Réinstallez-la depuis le DMG."
                )
            return found
        try:
            done = subprocess.run(
                [
                    *("git", "-C", str(REPOSITORY), "describe", "--tags"),
                    *("--match", "v[0-9]*.[0-9]*.[0-9]*", "--dirty=-modifie", "--always"),
                ],
                capture_output=True,
                text=True,
                check=False,
            )
        except OSError as exc:
            said = str(exc)
        else:
            if done.returncode == 0 and done.stdout.strip():
                return done.stdout.strip()
            said = done.stderr.strip() or f"git describe a rendu {done.returncode}"
        log.warning("build identifier unknown, the package's version instead: %s", said)
        return version("coulisses-app")

    def environment(self, environ: Mapping[str, str]) -> dict[str, str]:
        """The variables to set for the service and the engine it runs. From the .app: its
        tools first on the PATH, and no bytecode written by any Python it starts (the .app
        stays as signed; the engine's steps inherit it, its README asks it of the caller).
        The .app's launcher sets it before Python starts (ADR 0040, with `-B`); here, a
        safeguard for whatever the service starts. From the repository, nothing changes."""
        if self.tools_dir is None:
            return {}
        path = environ.get("PATH", "")
        return {
            "PATH": f"{self.tools_dir}{os.pathsep}{path}" if path else str(self.tools_dir),
            "PYTHONDONTWRITEBYTECODE": "1",
        }


@functools.cache
def build_identifier() -> str:
    """Which code this process runs (ADR 0064), read once: for `/api/etat` and the
    provenance of what is written (P7)."""
    return Resources.from_env().build_identifier()
