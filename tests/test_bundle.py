"""The service from Coulisses.app (ADR 0040): it finds the interface and its tools in the
.app, never builds nor writes anything there, and refuses to start from an incomplete .app.
From the repository, nothing changes."""

from __future__ import annotations

import logging
import os
import subprocess
from importlib.metadata import version
from pathlib import Path

import pytest

from coulisses_app import bundle, cli, system_audio
from coulisses_app.bundle import RESOURCES_ENV, TOOLS, IncompleteAppError, Resources
from coulisses_app.paths import DATA_DIR_ENV


def make_app(root: Path, *, without: str | None = None) -> Path:
    """A `Contents/Resources` folder as the build makes it, its tools mere scripts."""
    resources = root / "Coulisses.app" / "Contents" / "Resources"
    if without != "l'interface":
        (resources / "web").mkdir(parents=True)
        (resources / "web" / "index.html").write_text("<!doctype html>", encoding="utf-8")
    (resources / "bin").mkdir(parents=True)
    if without != "l'identifiant de version":
        (resources / bundle.BUILD_ID_FILE).write_text("v0.37.1-3-gabc1234\n", encoding="utf-8")
    for tool in TOOLS:
        if tool != without:
            program = resources / "bin" / tool
            program.write_text("#!/bin/sh\n", encoding="utf-8")
            program.chmod(0o755)
    return resources


def snapshot(folder: Path) -> dict[str, float]:
    return {str(p.relative_to(folder)): p.stat().st_mtime for p in folder.rglob("*")}


def test_from_the_repository_nothing_changes() -> None:
    resources = Resources.from_env({})
    assert resources.root is None
    assert resources.web_dir == bundle.REPOSITORY / "web" / "dist"
    assert resources.system_audio_program is None
    assert resources.environment({"PATH": "/usr/bin"}) == {}
    resources.check()


def test_the_app_gives_its_interface_and_tools(tmp_path: Path) -> None:
    root = make_app(tmp_path)
    resources = Resources.from_env({RESOURCES_ENV: str(root)})
    resources.check()
    assert resources.web_dir == root / "web"
    assert resources.system_audio_program == root / "bin" / "coulisses-son-ordinateur"


@pytest.mark.parametrize("missing", ["l'interface", "l'identifiant de version", *TOOLS])
def test_an_incomplete_app_is_said(tmp_path: Path, missing: str) -> None:
    resources = Resources(make_app(tmp_path, without=missing))
    with pytest.raises(IncompleteAppError, match=f"il manque {missing} dans"):
        resources.check()


def test_a_tool_that_cannot_run_counts_as_missing(tmp_path: Path) -> None:
    root = make_app(tmp_path)
    (root / "bin" / "ffprobe").chmod(0o644)
    with pytest.raises(IncompleteAppError, match="ffprobe"):
        Resources(root).check()


def test_the_apps_tools_come_first_on_the_path(tmp_path: Path) -> None:
    root = make_app(tmp_path)
    env = Resources(root).environment({"PATH": "/opt/homebrew/bin:/usr/bin"})
    assert env["PATH"].split(os.pathsep) == [str(root / "bin"), "/opt/homebrew/bin", "/usr/bin"]
    assert Resources(root).environment({})["PATH"] == str(root / "bin")


def test_where_uv_keeps_its_downloads_is_left_to_the_engine(tmp_path: Path) -> None:
    """The engine (v1.7.0) puts uv's Python and cache under its environments folder; set
    by the service, they would override it."""
    env = Resources(make_app(tmp_path)).environment({"PATH": "/usr/bin"})
    assert not {"UV_PYTHON_INSTALL_DIR", "UV_CACHE_DIR"} & set(env)


def test_no_python_of_the_app_writes_bytecode(tmp_path: Path) -> None:
    """From the .app, the service and the engine's steps write no bytecode: the .app stays
    as signed (the engine's README asks it of the caller since v1.7.1)."""
    assert Resources(make_app(tmp_path)).environment({})["PYTHONDONTWRITEBYTECODE"] == "1"
    assert "PYTHONDONTWRITEBYTECODE" not in Resources(None).environment({})


def test_the_apps_sound_program_is_used_as_shipped(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = make_app(tmp_path)
    before = snapshot(root.parent.parent)

    def no_compiler(name: str) -> str:
        raise AssertionError(f"{name} looked for: nothing is built from the .app")

    monkeypatch.setattr(system_audio.shutil, "which", no_compiler)
    assert system_audio.ensure_built(Resources(root)) == root / "bin" / "coulisses-son-ordinateur"
    assert snapshot(root.parent.parent) == before


def test_a_missing_sound_program_is_said_not_built(tmp_path: Path) -> None:
    root = make_app(tmp_path, without="coulisses-son-ordinateur")
    with pytest.raises(system_audio.UnavailableError, match="réinstallez-la"):
        system_audio.ensure_built(Resources(root))


def test_the_service_refuses_an_incomplete_app_before_touching_the_data(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv(RESOURCES_ENV, str(make_app(tmp_path, without="ffmpeg")))
    monkeypatch.setenv(DATA_DIR_ENV, str(tmp_path / "donnees"))
    with pytest.raises(SystemExit) as stopped:
        cli.main(["--sans-navigateur"])
    assert stopped.value.code == 1
    assert "il manque ffmpeg" in capsys.readouterr().err
    assert not (tmp_path / "donnees").exists()


def test_the_interface_comes_from_the_app_unless_told_otherwise(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = make_app(tmp_path)
    monkeypatch.delenv(cli.WEB_DIR_ENV, raising=False)
    assert cli.default_web_dir(Resources(root)) == root / "web"
    monkeypatch.setenv(cli.WEB_DIR_ENV, str(tmp_path / "autre"))
    assert cli.default_web_dir(Resources(root)) == tmp_path / "autre"


# -- which code runs (ADR 0064) ------------------------------------------------------------


def test_the_app_says_the_code_its_build_wrote(tmp_path: Path) -> None:
    assert Resources(make_app(tmp_path)).build_identifier() == "v0.37.1-3-gabc1234"


def test_an_empty_identifier_is_an_incomplete_app(tmp_path: Path) -> None:
    root = make_app(tmp_path)
    (root / bundle.BUILD_ID_FILE).write_text("\n", encoding="utf-8")
    with pytest.raises(IncompleteAppError, match="il manque l'identifiant de version"):
        Resources(root).check()
    with pytest.raises(IncompleteAppError):
        Resources(root).build_identifier()


@pytest.mark.parametrize(
    "described", ["v0.34.0", "v0.34.0-36-gcac1f05", "v0.34.0-36-gcac1f05-modifie", "cac1f05"]
)
def test_the_repository_says_what_git_describes(
    monkeypatch: pytest.MonkeyPatch, described: str
) -> None:
    asked: list[list[str]] = []

    def run(command: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        asked.append(command)
        return subprocess.CompletedProcess(command, 0, stdout=f"{described}\n", stderr="")

    monkeypatch.setattr(subprocess, "run", run)
    assert Resources(None).build_identifier() == described
    assert asked[0][:4] == ["git", "-C", str(bundle.REPOSITORY), "describe"]
    assert "--dirty=-modifie" in asked[0]


def test_the_real_repository_is_described_once() -> None:
    assert bundle.build_identifier() == bundle.build_identifier() != ""


def test_without_git_the_packages_version_is_given_and_the_log_says_why(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setattr(bundle, "REPOSITORY", tmp_path)  # not a repository
    with caplog.at_level(logging.WARNING, logger="coulisses_app.bundle"):
        assert Resources(None).build_identifier() == version("coulisses-app")
    assert "build identifier unknown" in caplog.text
