"""Which data and which port the service takes: « Coulisses (dév) » never gets the real
data, and does not share the published app's port (ADR 0040)."""

from __future__ import annotations

import unicodedata
from pathlib import Path

import pytest

from coulisses_app import cli, paths
from coulisses_app.paths import DATA_DIR_ENV, RealDataRefusedError


@pytest.fixture
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A ~/Coulisses of its own: the real data folder of these tests is a temporary one."""
    root = tmp_path / "Coulisses"
    monkeypatch.setattr(paths, "DEFAULT_DATA_DIR", root / "Données")
    monkeypatch.setattr(paths, "DEV_DATA_DIR", root / "Données-dev")
    monkeypatch.delenv(DATA_DIR_ENV, raising=False)
    return root


def settings(*argv: str) -> tuple[Path, int]:
    data, port = cli.launch_settings(cli.parse_args(list(argv)))
    return data.root, port


def test_the_published_app_serves_the_real_data_on_its_port(home: Path) -> None:
    assert settings("--sans-navigateur") == (home / "Données", 8765)


def test_the_development_app_has_its_own_data_and_port(home: Path) -> None:
    assert settings("--dev", "--sans-navigateur") == (home / "Données-dev", 8766)


def test_a_port_given_wins(home: Path) -> None:
    assert settings("--dev", "--port", "9000")[1] == 9000
    assert settings("--port", "9001")[1] == 9001


def test_development_takes_the_folder_it_is_given(
    home: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(DATA_DIR_ENV, str(tmp_path / "essai"))
    assert settings("--dev")[0] == tmp_path / "essai"


@pytest.mark.parametrize(
    "given",
    [
        lambda home: home / "Données",
        lambda home: home / "Données" / "sessions",
        lambda home: home / "Données" / ".." / "Données",
        lambda home: Path(unicodedata.normalize("NFD", str(home / "Données"))),
        lambda home: home / "DONNÉES",
    ],
    ids=["itself", "inside", "detour", "decomposed-accent", "other-case"],
)
def test_development_refuses_the_real_data(
    home: Path, monkeypatch: pytest.MonkeyPatch, given
) -> None:
    monkeypatch.setenv(DATA_DIR_ENV, str(given(home)))
    with pytest.raises(RealDataRefusedError, match="refuse le dossier des données réelles"):
        settings("--dev")


def test_development_refuses_a_link_to_the_real_data(
    home: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (home / "Données").mkdir(parents=True)
    link = tmp_path / "raccourci"
    link.symlink_to(home / "Données")
    monkeypatch.setenv(DATA_DIR_ENV, str(link))
    with pytest.raises(RealDataRefusedError):
        settings("--dev")


def test_development_refuses_the_real_data_reached_through_a_linked_parent(
    home: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (home / "Données" / "sessions").mkdir(parents=True)
    link = tmp_path / "ailleurs"
    link.symlink_to(home)
    monkeypatch.setenv(DATA_DIR_ENV, str(link / "Données" / "sessions"))
    with pytest.raises(RealDataRefusedError):
        settings("--dev")


def test_development_refuses_the_real_data_under_another_name(
    home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The disk's other name for the same folder (a firmlink on macOS): the folders are
    compared, not their names."""
    volume = Path("/System/Volumes/Data")
    if not volume.is_dir():
        pytest.skip("needs the data volume of macOS")
    (home / "Données").mkdir(parents=True)
    other_name = volume / (home / "Données").resolve().relative_to("/")
    assert other_name.is_dir()
    monkeypatch.setenv(DATA_DIR_ENV, str(other_name))
    with pytest.raises(RealDataRefusedError):
        settings("--dev")


def test_a_neighbour_of_the_real_data_is_not_mistaken_for_it(home: Path) -> None:
    (home / "Données").mkdir(parents=True)
    (home / "Données-dev").mkdir()
    assert not paths.is_real_data(home / "Données-dev")
    assert not paths.is_real_data(home / "Données anciennes")


def test_refused_development_stops_before_touching_anything(
    home: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv(DATA_DIR_ENV, str(home / "Données"))
    with pytest.raises(SystemExit) as stopped:
        cli.main(["--dev", "--sans-navigateur"])
    assert stopped.value.code == 1
    assert "refuse le dossier des données réelles" in capsys.readouterr().err
    assert not (home / "Données").exists()
