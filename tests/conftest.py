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

from coulisses_app.paths import DataDir
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
