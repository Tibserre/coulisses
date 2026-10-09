"""The engine's models and environments, for the « Modèles » section of the settings (spec
§7.12; engine ADR 0035, app ADR 0036).

Reading never touches the network. A download, or an environment's install, is an explicit
action of the user (the one exception to P1): it runs in the background, one at a time per
model, its progress followed by the interface, stoppable; every one is stopped when the
service stops (`stop_downloads`). The engine's errors are said in French, by their code.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from coulisses.api import (
    Catalog,
    DownloadProgress,
    Inventory,
    ModelActionCode,
    ModelActionError,
    Readiness,
    catalog,
    download,
    install_environment,
    installed,
    readiness,
    remove,
    stop_downloads,
)
from pydantic import BaseModel

from coulisses_app.spaces import SpaceError

log = logging.getLogger(__name__)

Kind = Literal["model", "environment"]


class ModelsError(SpaceError):
    """An action on a model that cannot be done; the message is shown to the user."""


class ModelAction(BaseModel):
    """A download or an install, running or just over (not a `job`: those are a
    session's)."""

    kind: Kind
    name: str
    state: Literal["running", "done", "failed", "cancelled"]
    done_bytes: int = 0
    total_bytes: int | None = None
    """None while unknown (an environment's install never knows it)."""
    error: str | None = None
    """Said in French, by the engine's code."""
    code: str | None = None
    detail: str | None = None
    """The engine's own message (developer mode)."""
    terms_url: str | None = None
    """For `terms_required`: the page where its terms are accepted."""
    started_at: datetime
    finished_at: datetime | None = None


class ModelsView(BaseModel):
    catalog: Catalog
    inventory: Inventory
    readiness: Readiness
    actions: list[ModelAction]


def _gb(value: Any) -> str:
    return f"{int(value) / 1e9:.1f}".replace(".", ",") if isinstance(value, int) else "?"


def said(error: ModelActionError) -> str:
    """The engine's error, in French (its message, in English, stays in `detail`)."""
    details: dict[str, Any] = dict(getattr(error, "details", {}) or {})
    match error.code:
        case ModelActionCode.UNKNOWN_MODEL:
            return "Ce modèle n'est pas dans le catalogue du moteur."
        case ModelActionCode.ALREADY_INSTALLED:
            return "C'est déjà installé."
        case ModelActionCode.NOT_INSTALLED:
            return "Ce modèle n'est pas installé : rien à supprimer."
        case ModelActionCode.NO_SPACE:
            return (
                f"Pas assez de place sur le disque : il faut "
                f"{_gb(details.get('needed_bytes'))} Go, il en reste "
                f"{_gb(details.get('free_bytes'))} Go."
            )
        case ModelActionCode.NETWORK:
            return (
                "La source n'a pas pu être jointe. Vérifiez la connexion, puis relancez : le "
                "téléchargement reprendra là où il s'est arrêté."
            )
        case ModelActionCode.TERMS_REQUIRED:
            return (
                "Ce modèle demande d'accepter ses conditions sur sa page avant d'être téléchargé."
            )
        case ModelActionCode.INTEGRITY:
            return (
                "Des fichiers manquent après le téléchargement. Relancez : ce qui est déjà là est "
                "gardé."
            )
        case ModelActionCode.CANCELLED:
            return "Arrêté. Relancez pour reprendre là où il s'est arrêté."
        case ModelActionCode.IN_USE:
            return (
                "Ce modèle est déjà en cours de téléchargement, ou un traitement en cours "
                "l'utilise : attendez qu'il se termine."
            )
        case ModelActionCode.TOOL_MISSING:
            return "uv est introuvable : il faut l'installer pour préparer cet environnement."
        case _:
            return "L'opération a échoué (le détail est dans le journal du service)."


class EngineModels:
    """The models' section of the service. The engine's functions are given in tests."""

    def __init__(
        self,
        profile: str,
        *,
        root: Path | None = None,
        read_catalog: Callable[[], Catalog] = catalog,
        read_installed: Callable[..., Inventory] = installed,
        read_readiness: Callable[..., Readiness] = readiness,
        fetch: Callable[..., Any] = download,
        install: Callable[..., Any] = install_environment,
        discard: Callable[..., None] = remove,
        stop_all: Callable[[], None] = stop_downloads,
    ) -> None:
        self.profile = profile
        self._root = root
        self._catalog = read_catalog
        self._installed = read_installed
        self._readiness = read_readiness
        self._fetch = fetch
        self._install = install
        self._discard = discard
        self._stop_all = stop_all
        self._lock = threading.Lock()
        self._tasks: dict[tuple[Kind, str], ModelAction] = {}
        self._cancels: dict[tuple[Kind, str], threading.Event] = {}
        self._threads: list[threading.Thread] = []

    # -- reading ------------------------------------------------------------------------

    def view(self) -> ModelsView:
        """Everything the section shows (measures the sizes on disk: about a second)."""
        return ModelsView(
            catalog=self._catalog(),
            inventory=self._installed(root=self._root),
            readiness=self._readiness(self.profile, root=self._root),
            actions=self.actions(),
        )

    def actions(self) -> list[ModelAction]:
        with self._lock:
            return [t.model_copy() for t in self._tasks.values()]

    def ready(self) -> Readiness:
        return self._readiness(self.profile, root=self._root)

    # -- actions ------------------------------------------------------------------------

    def start(self, kind: Kind, name: str) -> ModelAction:
        """A download (a model of the catalog) or an install (an environment), in the
        background. Asked by the user only."""
        key = (kind, name)
        with self._lock:
            running = self._tasks.get(key)
            if running is not None and running.state == "running":
                raise ModelsError("C'est déjà en cours.")
            task = ModelAction(kind=kind, name=name, state="running", started_at=datetime.now(UTC))
            cancel = threading.Event()
            self._tasks[key] = task
            self._cancels[key] = cancel
        thread = threading.Thread(
            target=self._run, args=(key, cancel), name=f"{kind}-{name}", daemon=True
        )
        with self._lock:
            self._threads = [t for t in self._threads if t.is_alive()] + [thread]
        thread.start()
        return task.model_copy()

    def _run(self, key: tuple[Kind, str], cancel: threading.Event) -> None:
        kind, name = key

        def progress(step: DownloadProgress) -> None:
            with self._lock:
                task = self._tasks[key]
                task.done_bytes = step.done_bytes
                task.total_bytes = step.total_bytes

        try:
            if kind == "model":
                self._fetch(name, on_progress=progress, cancel=cancel, root=self._root)
            else:
                self._install(name, on_progress=progress, cancel=cancel)
        except ModelActionError as exc:
            log.warning("%s %s: %s %s", kind, name, exc.code, exc)
            details: dict[str, Any] = dict(getattr(exc, "details", {}) or {})
            self._finish(
                key,
                "cancelled" if exc.code == ModelActionCode.CANCELLED else "failed",
                error=said(exc),
                code=exc.code.value,
                detail=str(exc),
                terms_url=details.get("url") if isinstance(details.get("url"), str) else None,
            )
            return
        # Anything else: said, never lost in a thread (P8).
        except Exception as exc:
            log.exception("%s %s", kind, name)
            self._finish(
                key,
                "failed",
                error="L'opération a échoué (le détail est dans le journal du service).",
                code="failed",
                detail=f"{type(exc).__name__}: {exc}",
            )
            return
        self._finish(key, "done")

    def _finish(self, key: tuple[Kind, str], state: str, **fields: Any) -> None:
        with self._lock:
            task = self._tasks[key]
            self._tasks[key] = task.model_copy(
                update={"state": state, "finished_at": datetime.now(UTC), **fields}
            )

    def cancel(self, kind: Kind, name: str) -> None:
        with self._lock:
            task = self._tasks.get((kind, name))
            if task is None or task.state != "running":
                raise ModelsError("Rien n'est en cours pour celui-ci.")
            self._cancels[(kind, name)].set()

    def remove(self, name: str) -> None:
        """A model removed, and its interrupted download: asked and confirmed by the user."""
        with self._lock:
            task = self._tasks.get(("model", name))
            if task is not None and task.state == "running":
                raise ModelsError("Arrêtez d'abord son téléchargement.")
        try:
            self._discard(name, root=self._root)
        except ModelActionError as exc:
            log.warning("removing %s: %s %s", name, exc.code, exc)
            raise ModelsError(said(exc)) from exc
        with self._lock:
            self._tasks.pop(("model", name), None)

    def forget(self, kind: Kind, name: str) -> None:
        """A finished task, put away (its message read)."""
        with self._lock:
            task = self._tasks.get((kind, name))
            if task is not None and task.state != "running":
                del self._tasks[(kind, name)]

    def shutdown(self) -> None:
        """The service stops: every download and install is stopped (their partial folders
        are kept, they resume next time)."""
        try:
            self._stop_all()
        finally:
            with self._lock:
                cancels = list(self._cancels.values())
                threads = list(self._threads)
            for cancel in cancels:
                cancel.set()
            for thread in threads:
                thread.join(timeout=10)

    def downloading(self) -> bool:
        """Something is being downloaded or installed (quitting would stop it)."""
        with self._lock:
            return any(a.state == "running" for a in self._tasks.values())
