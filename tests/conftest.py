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
from coulisses.api import ChainConfig, StageConfig
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
