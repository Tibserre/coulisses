"""The size measurement script (plan step 12a): read only, never in the real data."""

from __future__ import annotations

import importlib.util
import json
import sqlite3
import struct
import sys
from pathlib import Path
from types import ModuleType

import pytest

from coulisses_app import paths

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def mesure() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "mesurer_tailles", ROOT / "scripts" / "mesurer-tailles.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write_wav(path: Path, seconds: float, rate: int = 48_000, channels: int = 1) -> None:
    """A 24-bit PCM WAV of silence, with a chunk before `data` as some writers add."""
    block = channels * 3
    data = bytes(int(seconds * rate) * block)
    extra = b"LIST" + struct.pack("<I", 4) + b"INFO"
    fmt = struct.pack("<HHIIHH", 1, channels, rate, rate * block, block, 24)
    body = b"WAVE" + b"fmt " + struct.pack("<I", 16) + fmt + extra
    body += b"data" + struct.pack("<I", len(data)) + data
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"RIFF" + struct.pack("<I", len(body)) + body)


def test_sizes_are_written_as_the_finder_does(mesure) -> None:
    assert mesure.human(1_990_000_000) == "1,99 Go"
    assert mesure.human(617_000_000) == "617 Mo"
    assert mesure.human(42_700_000) == "42,7 Mo"
    assert mesure.human(-49_200) == "-49,2 ko"
    assert mesure.human(12) == "12 o"


def test_each_file_has_a_kind(mesure, tmp_path: Path) -> None:
    inside = tmp_path / "python"
    cases = {
        "lib/torch/tests/test_x.py": "tests",
        "lib/torch/testing/_x.py": "py",  # loaded by torch itself: not a test
        "lib/x/__pycache__/a.cpython-312.pyc": "pyc",
        "lib/x/a.pyi": "stubs",
        "lib/mlx/lib/mlx.metallib": "metal",
        "lib/x/include/a.h": "sources",
        "lib/x/a.cpython-312-darwin.so": "native",
        "lib/x/libz.a": "static",
        "lib/x/data.json": "other",
    }
    for relative, kind in cases.items():
        path = inside / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"x")
        assert mesure.kind_of(path, inside) == kind, relative
    program = inside / "bin" / "outil"
    program.parent.mkdir()
    program.write_bytes(b"\xcf\xfa\xed\xfe" + bytes(8))
    assert mesure.kind_of(program, inside) == "native"


def test_a_wav_duration_is_read_from_its_chunks(mesure, tmp_path: Path) -> None:
    write_wav(tmp_path / "a.wav", 0.5)
    write_wav(tmp_path / "b.wav", 0.25, rate=16_000, channels=2)
    assert mesure.wav_duration(tmp_path / "a.wav") == pytest.approx(0.5)
    assert mesure.wav_duration(tmp_path / "b.wav") == pytest.approx(0.25)
    (tmp_path / "c.wav").write_bytes(b"not a wav at all")
    assert mesure.wav_duration(tmp_path / "c.wav") is None


def package(site: Path, name: str, requires: list[str], size: int) -> None:
    """A fake installed package: its dist-info, a module of `size` bytes and its .pyc."""
    module = name.replace("-", "_")
    info = site / f"{module}-1.0.dist-info"
    info.mkdir(parents=True)
    lines = [f"Name: {name}", "Version: 1.0", *(f"Requires-Dist: {r}" for r in requires)]
    (info / "METADATA").write_text("\n".join(lines) + "\n", encoding="utf-8")
    (site / module).mkdir()
    (site / module / "__init__.py").write_bytes(bytes(size))
    cache = site / module / "__pycache__"
    cache.mkdir()
    (cache / "__init__.cpython-312.pyc").write_bytes(bytes(size))
    record = [f"{module}/__init__.py,,", f"{info.name}/METADATA,,", f"{info.name}/RECORD,,"]
    (info / "RECORD").write_text("\n".join(record) + "\n", encoding="utf-8")


def test_what_removing_a_package_saves(mesure, tmp_path: Path) -> None:
    version = f"python{sys.version_info.major}.{sys.version_info.minor}"
    python = tmp_path / "python"
    site = python / "lib" / version / "site-packages"
    package(site, "coulisses-app", ["coulisses[wav2vec2]"], 100)
    package(
        site,
        "coulisses",
        ["torch", 'librosa ; extra == "wav2vec2"', 'unused ; extra == "never"'],
        100,
    )
    package(site, "torch", ["numpy"], 600_000)
    package(site, "librosa", ["numba", "numpy"], 100_000)
    package(site, "numba", ["llvmlite"], 30_000)
    package(site, "llvmlite", [], 130_000)
    package(site, "numpy", [], 40_000)
    package(site, "unused", [], 1_000)
    package(site, "pip", [], 12_000)
    (site / "orphan.txt").write_bytes(bytes(5_000))

    found = mesure.python_packages(python, "coulisses-app")
    sizes = {n: p["size"] for n, p in found["packages"].items()}
    # Its .pyc goes with its .py: both counted for the package.
    assert sizes["llvmlite"] >= 2 * 130_000
    assert found["unowned"] >= 5_000
    librosa = found["exclusive"]["librosa"]
    assert set(librosa["with"]) == {"numba", "llvmlite"}  # numpy stays: torch wants it
    assert librosa["size"] == sizes["librosa"] + sizes["numba"] + sizes["llvmlite"]
    assert found["exclusive"]["numpy"]["size"] == sizes["numpy"]
    assert "unused" not in found["exclusive"]  # its extra is not asked for
    assert found["not_required"] == ["pip", "unused"]
    assert found["required_by"]["numpy"] == ["librosa", "torch"]


def test_audio_by_file_and_by_kind_of_session(mesure, tmp_path: Path, monkeypatch) -> None:
    data = tmp_path / "Données-dev"
    recorded = data / "sessions" / "20261001-100000-aaaa" / "sources"
    imported = data / "sessions" / "20261002-100000-bbbb" / "sources"
    write_wav(recorded / "ref.wav", 2.0)
    write_wav(recorded / "system.wav", 2.0)
    write_wav(recorded / "mix.wav", 2.0)
    (recorded / "mix.json").write_text("{}", encoding="utf-8")
    write_wav(imported / "ref.wav", 1.0, rate=16_000)
    (imported / "ref2.m4a").write_bytes(b"unreadable")
    with sqlite3.connect(data / "coulisses.db") as base:
        base.execute("CREATE TABLE audio_source (session_id, file_name, origin, removed_at)")
        base.executemany(
            "INSERT INTO audio_source VALUES (?, ?, ?, NULL)",
            [
                ("20261001-100000-aaaa", "ref.wav", "captured"),
                ("20261001-100000-aaaa", "system.wav", "captured"),
                ("20261002-100000-bbbb", "ref.wav", "imported"),
                ("20261002-100000-bbbb", "ref2.m4a", "imported"),
            ],
        )
    monkeypatch.setattr(mesure, "probed_duration", lambda path: None)

    audio = mesure.audio_facts(data)

    assert set(audio["by_file"]) == {"ref.wav", "system.wav", "dérivé : mix.wav", "importé (.wav)"}
    assert audio["by_file"]["ref.wav"]["seconds"] == pytest.approx(2.0)
    kinds = audio["by_session_kind"]
    assert kinds["enregistrée dans l'app"]["count"] == 1
    assert kinds["enregistrée dans l'app"]["seconds"] == pytest.approx(2.0)
    assert kinds["importée"]["seconds"] == pytest.approx(1.0)
    assert audio["track_per_hour"][mesure.MONO_TRACK] == 48_000 * 3 * 3600
    # Only totals: no session's name goes into the JSON kept in the repository.
    assert "20261001" not in json.dumps(audio, ensure_ascii=False)


def test_never_the_real_data_nor_an_existing_survey(
    mesure, tmp_path: Path, monkeypatch, capsys
) -> None:
    real = tmp_path / "Données"
    (real / "sessions").mkdir(parents=True)
    monkeypatch.setattr(paths, "DEFAULT_DATA_DIR", real)
    for given in (real, real / "sessions"):
        monkeypatch.setattr(sys, "argv", ["mesurer-tailles.py", "--donnees", str(given)])
        with pytest.raises(SystemExit):
            mesure.main()
    assert "données réelles" in capsys.readouterr().err

    survey = tmp_path / "releve.json"
    survey.write_text("{}", encoding="utf-8")
    arguments = ["--donnees", str(tmp_path), "--json", str(survey)]
    monkeypatch.setattr(sys, "argv", ["mesurer-tailles.py", *arguments])
    with pytest.raises(SystemExit):
        mesure.main()
    assert survey.read_text(encoding="utf-8") == "{}"
