"""Shared fixtures. Everything runs in a temporary data folder, never ~/Coulisses/Données.

The recording is synthetic (`say -v Thomas`), made at test time and never committed. The
chain uses the engine's fake engines (`coulisses.testing`), which load no model; only the
tests marked `slow` use the real chain."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import coulisses.testing.fakes  # noqa: F401  # registers the fake engines
import pytest
from coulisses.api import (
    Catalog,
    CatalogModel,
    ChainConfig,
    ErrorCode,
    Languages,
    LanguageSupport,
    MissingPiece,
    Readiness,
    StageConfig,
    StageName,
)
from fastapi import FastAPI
from fastapi.testclient import TestClient

from coulisses_app.paths import DataDir
from coulisses_app.prompting.ollama import ChatAnswer, InstalledModel, OllamaError
from coulisses_app.storage.db import migrate

FAKE_CHAIN = ChainConfig(
    transcribe=StageConfig(engine="fake_unmeasured"),
    align=StageConfig(engine="fake_aligner"),
    diarize=StageConfig(engine="fake_min_speakers"),
    attribute=StageConfig(engine="overlap"),
)

SPOKEN = (
    "Bonjour à tous. On commence par l'échauffement, puis une scène à deux. "
    "Ensuite on fera un retour sur la scène."
)


@pytest.fixture(scope="session")
def recording(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """A short French recording, 48 kHz mono WAV, made with the system voice."""
    if shutil.which("say") is None or shutil.which("ffmpeg") is None:
        pytest.skip("needs macOS `say` and ffmpeg")
    folder = tmp_path_factory.mktemp("enregistrement")
    aiff = folder / "voix.aiff"
    wav = folder / "repetition.wav"
    subprocess.run(["say", "-v", "Thomas", "-o", str(aiff), SPOKEN], check=True)
    subprocess.run(
        ["ffmpeg", "-v", "error", "-i", str(aiff), "-ar", "48000", "-ac", "1", str(wav)],
        check=True,
    )
    return wav


@pytest.fixture
def data(tmp_path: Path) -> DataDir:
    data = DataDir(tmp_path / "donnees")
    migrate(data)
    return data


class FakeModel:
    """Stands for Ollama in the tests: no model, no network. Records every call."""

    def __init__(self, answer: str = "## Décisions\n- On garde la fin.", *, down: bool = False):
        self.answer = answer
        self.phases_answer = (
            '{"chapitres": [{"debut": "0:00", "type": "discussion", "titre": "Essai"}]}'
        )
        """What it answers when asked for chapters (a JSON schema given)."""
        self.down = down
        self.calls: list[tuple[str, list[dict[str, str]], dict[str, object]]] = []
        self.formats: list[dict[str, object] | None] = []
        self.prompt_tokens = 1000
        self.done_reason: str | None = "stop"
        self.counted = True

    def version(self) -> str | None:
        return "0.0-essai"

    def models(self) -> list[InstalledModel]:
        if self.down:
            raise OllamaError(
                "Ollama ne répond pas sur 127.0.0.1:11434 : lancez l'application Ollama."
            )
        return [InstalledModel(name="modele-essai", size_bytes=1, digest="abc")]

    def chat(
        self,
        model: str,
        messages: list[dict[str, str]],
        options: dict[str, object],
        *,
        answer_format: dict[str, object] | None = None,
    ) -> ChatAnswer:
        if self.down:
            raise OllamaError(
                "Ollama ne répond pas sur 127.0.0.1:11434 : lancez l'application Ollama."
            )
        self.calls.append((model, messages, options))
        self.formats.append(answer_format)
        return ChatAnswer(
            content=self.phases_answer if answer_format is not None else self.answer,
            prompt_eval_count=self.prompt_tokens if self.counted else None,
            eval_count=50 if self.counted else None,
            done_reason=self.done_reason,
            total_duration_s=0.1,
        )


@pytest.fixture(autouse=True)
def fake_model(monkeypatch: pytest.MonkeyPatch) -> FakeModel:
    """No test talks to the real Ollama: the processing gets this fake by default."""
    fake = FakeModel()
    monkeypatch.setattr("coulisses_app.processing.OllamaClient", lambda: fake)
    monkeypatch.setattr("coulisses_app.api.OllamaClient", lambda: fake)
    return fake


def local_client(app: FastAPI) -> TestClient:
    """A client as the service's own page: the service refuses any other host name."""
    return TestClient(app, base_url="http://127.0.0.1:8765")


class FakeLanguages:
    """Stands for the engine's `languages()` in the tests: French installed, English and
    German each missing its aligner, unless `install` is called. No model is read."""

    def __init__(self) -> None:
        self.missing: dict[str, set[str]] = {
            "en": {"aligneur-anglais"},
            "de": {"aligneur-allemand"},
        }
        self.calls = 0
        self.aligners = {"fr": "aligneur-francais", "de": "aligneur-allemand"}
        self.aligners["en"] = "aligneur-anglais"
        self.unaligned: set[str] = set()
        self.chain_missing: set[str] = set()
        """Models of the other stages (who speaks when), missing whatever the language."""
        self.environments: dict[str, str] = {}
        """Environments missing: name → what it is for."""
        self.altered: set[str] = set()
        """Models on disk but damaged."""

    def install(self, key: str) -> None:
        for keys in self.missing.values():
            keys.discard(key)
        self.chain_missing.discard(key)
        self.environments.pop(key, None)

    def readiness(
        self, profile: str = "chaine-retenue", root: Path | None = None, language: str = "fr"
    ) -> Readiness:
        """The engine's `readiness`: the language's models and the others, the environments."""
        missing = (
            [
                MissingPiece(code=ErrorCode.MODEL_MISSING, stage=stage, model=key, message="absent")
                for stage, keys in (
                    (StageName.ALIGN, sorted(self.missing.get(language, set()))),
                    (StageName.DIARIZE, sorted(self.chain_missing)),
                )
                for key in keys
            ]
            + [
                MissingPiece(
                    code=ErrorCode.ENVIRONMENT_MISSING,
                    stage=StageName.DIARIZE,
                    environment=name,
                    label=label,
                    message="absent",
                    announced_bytes=900_000_000,
                )
                for name, label in self.environments.items()
            ]
            + [
                MissingPiece(
                    code=ErrorCode.MODEL_ALTERED,
                    stage=StageName.DIARIZE,
                    model=key,
                    message="abîmé",
                )
                for key in sorted(self.altered)
            ]
        )
        return Readiness(
            profile=profile, language=language, ready=not missing, missing=tuple(missing)
        )

    def catalog(self) -> Catalog:
        return Catalog(
            models=tuple(
                CatalogModel(
                    key=key,
                    stage=StageName.DIARIZE,
                    role="diarisation",
                    description="",
                    announced_bytes=size,
                    repo="x/y",
                    revision="r",
                    licence="MIT",
                )
                for key, size in [
                    *((k, 500_000_000) for k in sorted(self.chain_missing | self.altered)),
                    *((k, 1_260_000_000) for k in sorted(self.aligners.values())),
                ]
            )
        )

    def __call__(self, profile: str = "chaine-retenue", root: Path | None = None) -> Languages:
        self.calls += 1
        rows = [("fr", "Français"), ("de", "Allemand"), ("en", "Anglais")]
        return Languages(
            profile=profile,
            languages=tuple(
                LanguageSupport(
                    language=code,
                    label=label,
                    transcribed=True,
                    aligned=code not in self.unaligned,
                    transcription_model="transcripteur",
                    alignment_model=self.aligners[code],
                    missing_models=tuple(sorted(self.missing.get(code, set()))),
                    download_bytes=1_260_000_000 * len(self.missing.get(code, set())),
                )
                for code, label in rows
            ),
        )


@pytest.fixture(autouse=True)
def fake_languages(monkeypatch: pytest.MonkeyPatch) -> FakeLanguages:
    """No test reads the models on this Mac to know its languages (ADR 0072)."""
    fake = FakeLanguages()
    monkeypatch.setattr("coulisses_app.languages.engine_languages", fake)
    monkeypatch.setattr("coulisses_app.languages.engine_readiness", fake.readiness)
    monkeypatch.setattr("coulisses_app.languages.engine_catalog", fake.catalog)
    return fake
