"""What the service takes from the repository in development, and from Coulisses.app once
built (ADR 0040): the built interface, and the tools it and the engine run (ffmpeg,
ffprobe, uv, the computer's sound program). Where uv keeps the Python and the cache of the
engine's environments is the engine's own (v1.7.0: under `envs_dir()/uv`).

The app in the Dock says the service runs from the .app by giving COULISSES_RESSOURCES,
its `Contents/Resources` folder. Nothing is ever written there: the .app stays as signed.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

RESOURCES_ENV = "COULISSES_RESSOURCES"
REPOSITORY = Path(__file__).resolve().parents[2]

SYSTEM_AUDIO_PROGRAM = "coulisses-son-ordinateur"
# Found by name on the PATH, by the service and by the engine (its README's prerequisites).
TOOLS = ("ffmpeg", "ffprobe", "uv", SYSTEM_AUDIO_PROGRAM)


class IncompleteAppError(RuntimeError):
    """The .app lacks something it was built with. The message is shown to the user."""


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
