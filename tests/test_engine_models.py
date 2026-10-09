"""The engine's models in the settings (spec §7.12, ADR 0036): reading, a download in the
background with its progress, stopping it, the engine's errors said in French, removing,
and everything stopped when the service stops. The engine is a fake: nothing is downloaded."""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from coulisses.api import (
    Catalog,
    CatalogModel,
    DownloadProgress,
    EnvironmentInfo,
    ErrorCode,
    InstalledModelInfo,
    Inventory,
    MissingPiece,
    ModelActionCode,
    ModelActionError,
    Readiness,
    StageName,
)
from fastapi.testclient import TestClient

from coulisses_app.api import create_app
from coulisses_app.engine_models import EngineModels, ModelsError
from coulisses_app.paths import DataDir

from .conftest import FAKE_CHAIN

ASR = CatalogModel(
    key="asr",
    stage=StageName.TRANSCRIBE,
    role="transcription",
    description="Un modèle de transcription.",
    announced_bytes=4_700_000_000,
    repo="exemple/asr",
    revision="abc",
    licence="Apache 2.0",
    required_by=("chaine-retenue",),
)


class FakeEngine:
    """Stands for the engine's functions; `fetch` goes as far as the test lets it."""

    def __init__(self, tmp_path: Path) -> None:
        self.installed: list[str] = []
        self.removed: list[str] = []
        self.stopped = 0
        self.go_on = threading.Event()
        self.failure: ModelActionError | None = None
        self.tmp_path = tmp_path

    def catalog(self) -> Catalog:
        return Catalog(models=(ASR,))

    def inventory(self, root: Path | None = None) -> Inventory:
        return Inventory(
            models_dir=self.tmp_path,
            envs_dir=self.tmp_path,
            models=tuple(
                InstalledModelInfo(key=k, state="intact", in_catalog=True, size_bytes=10)
                for k in self.installed
            ),
            partial_downloads=(),
            environments=(
                EnvironmentInfo(
                    name="diarizen", path=self.tmp_path, current=True, installed=True, size_bytes=1
                ),
            ),
            total_bytes=10 * len(self.installed) + 1,
        )

    def readiness(self, profile: str, root: Path | None = None) -> Readiness:
        missing = (
            ()
            if "asr" in self.installed
            else (
                MissingPiece(
                    code=ErrorCode.MODEL_MISSING,
                    stage=StageName.TRANSCRIBE,
                    model="asr",
                    message="missing",
                ),
            )
        )
        return Readiness(profile=profile, ready=not missing, missing=missing)

    def fetch(
        self,
        key: str,
        on_progress: Callable[[DownloadProgress], None] | None = None,
        cancel: threading.Event | None = None,
        root: Path | None = None,
    ) -> Any:
        assert on_progress is not None and cancel is not None
        on_progress(DownloadProgress(phase="download", done_bytes=1_000, total_bytes=4_000))
        while not self.go_on.wait(0.01):
            if cancel.is_set():
                raise ModelActionError(ModelActionCode.CANCELLED, "cancelled", model=key)
        if self.failure is not None:
            raise self.failure
        on_progress(DownloadProgress(phase="download", done_bytes=4_000, total_bytes=4_000))
        self.installed.append(key)

    def remove(self, key: str, root: Path | None = None) -> None:
        if key not in self.installed:
            raise ModelActionError(ModelActionCode.NOT_INSTALLED, "not installed", model=key)
        self.installed.remove(key)
        self.removed.append(key)

    def stop_all(self) -> None:
        self.stopped += 1

    def models(self) -> EngineModels:
        return EngineModels(
            "chaine-retenue",
            read_catalog=self.catalog,
            read_installed=self.inventory,
            read_readiness=self.readiness,
            fetch=self.fetch,
            install=self.fetch,
            discard=self.remove,
            stop_all=self.stop_all,
        )


def settle(models: EngineModels, state: str) -> None:
    deadline = time.monotonic() + 5
    while not any(t.state == state for t in models.actions()):
        assert time.monotonic() < deadline, f"no task reached {state}"
        time.sleep(0.01)


@pytest.fixture
def engine(tmp_path: Path) -> FakeEngine:
    return FakeEngine(tmp_path)


def test_a_download_runs_in_the_background_and_says_its_progress(engine: FakeEngine) -> None:
    models = engine.models()
    assert not models.view().readiness.ready
    task = models.start("model", "asr")
    assert task.state == "running"
    deadline = time.monotonic() + 5
    while models.actions()[0].done_bytes < 1_000:
        assert time.monotonic() < deadline
        time.sleep(0.01)
    [running] = models.actions()
    assert (running.done_bytes, running.total_bytes) == (1_000, 4_000)
    with pytest.raises(ModelsError, match="déjà en cours"):
        models.start("model", "asr")
    engine.go_on.set()
    settle(models, "done")
    view = models.view()
    assert view.readiness.ready and [m.key for m in view.inventory.models] == ["asr"]
    assert view.actions[0].done_bytes == 4_000


def test_a_download_stopped_by_the_user_can_resume(engine: FakeEngine) -> None:
    models = engine.models()
    models.start("model", "asr")
    models.cancel("model", "asr")
    settle(models, "cancelled")
    [stopped] = models.actions()
    assert stopped.error is not None and "reprendre" in stopped.error
    with pytest.raises(ModelsError, match="Rien n'est en cours"):
        models.cancel("model", "asr")
    models.forget("model", "asr")
    assert models.actions() == []


@pytest.mark.parametrize(
    ("failure", "said"),
    [
        (
            ModelActionError(
                ModelActionCode.NO_SPACE,
                "no space",
                model="asr",
                needed_bytes=4_935_000_000,
                free_bytes=1_200_000_000,
            ),
            "il faut 4,9 Go, il en reste 1,2 Go",
        ),
        (ModelActionError(ModelActionCode.NETWORK, "unreachable", model="asr"), "connexion"),
        (ModelActionError(ModelActionCode.FAILED, "boom", model="asr"), "journal du service"),
    ],
)
def test_the_engines_errors_are_said_in_french(
    engine: FakeEngine, failure: ModelActionError, said: str
) -> None:
    engine.failure = failure
    engine.go_on.set()
    models = engine.models()
    models.start("model", "asr")
    settle(models, "failed")
    [failed] = models.actions()
    assert failed.error is not None and said in failed.error
    assert failed.code == failure.code.value and failed.detail == str(failure)


def test_terms_to_accept_give_their_page(engine: FakeEngine) -> None:
    engine.failure = ModelActionError(
        ModelActionCode.TERMS_REQUIRED, "terms", model="asr", url="https://exemple.org/asr"
    )
    engine.go_on.set()
    models = engine.models()
    models.start("model", "asr")
    settle(models, "failed")
    assert models.actions()[0].terms_url == "https://exemple.org/asr"


def test_removing_is_refused_while_it_downloads_and_said_when_absent(engine: FakeEngine) -> None:
    models = engine.models()
    models.start("model", "asr")
    with pytest.raises(ModelsError, match="Arrêtez d'abord"):
        models.remove("asr")
    engine.go_on.set()
    settle(models, "done")
    models.remove("asr")
    assert engine.removed == ["asr"] and models.actions() == []
    with pytest.raises(ModelsError, match="rien à supprimer"):
        models.remove("asr")


def test_the_service_shows_them_and_stops_every_download_when_it_stops(
    data: DataDir, engine: FakeEngine
) -> None:
    models = engine.models()
    app = create_app(
        data,
        FAKE_CHAIN,
        profile="chaine-retenue",
        processor=None,
        web_dir=None,
        engine_store=models,
    )
    with TestClient(app) as client:
        view = client.get("/api/moteur/modeles").json()
        assert view["catalog"]["models"][0]["key"] == "asr"
        assert view["readiness"]["missing"][0]["model"] == "asr"
        assert client.post("/api/moteur/modeles/asr/telecharger").status_code == 202
        assert client.post("/api/moteur/modeles/asr/telecharger").status_code == 422
        assert client.get("/api/moteur/telechargements").json()[0]["state"] == "running"
        # The service stops with the download still running.
    assert engine.stopped == 1
    settle(models, "cancelled")


def test_an_environment_installs_like_a_model_downloads(engine: FakeEngine) -> None:
    models = engine.models()
    models.start("environment", "diarizen")
    assert models.downloading()
    engine.go_on.set()
    settle(models, "done")
    [installed] = models.actions()
    assert (installed.kind, installed.name) == ("environment", "diarizen")
    assert not models.downloading()


@pytest.mark.parametrize(
    ("code", "said"),
    [
        (ModelActionCode.TERMS_REQUIRED, "accepter ses conditions"),
        (ModelActionCode.INTEGRITY, "Des fichiers manquent"),
        (ModelActionCode.IN_USE, "un traitement en cours"),
        (ModelActionCode.TOOL_MISSING, "uv est introuvable"),
        (ModelActionCode.UNKNOWN_MODEL, "pas dans le catalogue"),
        (ModelActionCode.ALREADY_INSTALLED, "déjà installé"),
    ],
)
def test_every_code_is_said_in_french(code: ModelActionCode, said: str) -> None:
    from coulisses_app.engine_models import said as say

    assert said in say(ModelActionError(code, "english", model="asr"))


def test_a_removal_the_engine_refuses_is_said(engine: FakeEngine) -> None:
    def busy(key: str, root: Path | None = None) -> None:
        raise ModelActionError(ModelActionCode.IN_USE, "in use", model=key)

    models = engine.models()
    models._discard = busy  # pyright: ignore[reportPrivateUsage]
    with pytest.raises(ModelsError, match="un traitement en cours"):
        models.remove("asr")


def test_quitting_is_told_a_download_runs(data: DataDir, engine: FakeEngine) -> None:
    models = engine.models()
    client = TestClient(
        create_app(
            data,
            FAKE_CHAIN,
            profile="chaine-retenue",
            processor=None,
            web_dir=None,
            engine_store=models,
        )
    )
    client.post("/api/moteur/modeles/asr/telecharger")
    assert client.get("/api/activite").json()["downloading"] is True
    engine.go_on.set()
    settle(models, "done")
    assert client.get("/api/activite").json()["downloading"] is False
