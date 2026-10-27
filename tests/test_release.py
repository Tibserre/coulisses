"""Versions numbered at publication only (ADR 0064; scripts/release.py): a merge rewrites
the « Non publié » section and sets no tag; numbering a publication writes the version, its
section and its tag; between two versions, `git describe` names the checkout."""

from __future__ import annotations

import importlib.util
import subprocess
from pathlib import Path
from types import ModuleType

import pytest

ROOT = Path(__file__).resolve().parents[1]

RELEASE_TOML = """verrous = []

[[fichiers]]
chemin = "pyproject.toml"
motif = '^version = "([^"]+)"'
"""

CHANGELOG = """# Journal des versions

Texte d'introduction.

## v0.34.0 — 2026-10-20

### Nouveautés

- Les Réglages se rangent en quatre onglets (réécrit pour les utilisateurs).
"""


def git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, text=True, check=True
    ).stdout.strip()


@pytest.fixture
def repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A main branch published at v0.34.0, with no hook of this Mac."""
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", "/dev/null")
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    git(tmp_path, "init", "-q", "-b", "main")
    git(tmp_path, "config", "user.name", "Essai")
    git(tmp_path, "config", "user.email", "essai@example.invalid")
    (tmp_path / "release.toml").write_text(RELEASE_TOML, encoding="utf-8")
    (tmp_path / "pyproject.toml").write_text('[project]\nversion = "0.34.0"\n', encoding="utf-8")
    (tmp_path / "CHANGELOG.md").write_text(CHANGELOG, encoding="utf-8")
    git(tmp_path, "add", ".")
    git(tmp_path, "commit", "-q", "-m", "chore(version): v0.34.0")
    git(tmp_path, "tag", "-a", "v0.34.0", "-m", "v0.34.0")
    return tmp_path


@pytest.fixture
def release(repo: Path, monkeypatch: pytest.MonkeyPatch) -> ModuleType:
    spec = importlib.util.spec_from_file_location("release", ROOT / "scripts" / "release.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, "ROOT", repo)
    return module


def change(repo: Path, message: str) -> None:
    (repo / "fichier.txt").write_text(message, encoding="utf-8")
    git(repo, "add", "fichier.txt")
    git(repo, "commit", "-q", "-m", message)


def changelog(repo: Path) -> str:
    return (repo / "CHANGELOG.md").read_text(encoding="utf-8")


def test_a_merge_lists_what_is_unreleased_and_sets_no_tag(release, repo: Path) -> None:
    change(repo, "feat(voix): reconnaît les voix")
    change(repo, "docs(plan): note la suite")
    release.unreleased()
    assert git(repo, "tag", "--list") == "v0.34.0"
    assert 'version = "0.34.0"' in (repo / "pyproject.toml").read_text(encoding="utf-8")
    text = changelog(repo)
    assert text.index("## Non publié") < text.index("## v0.34.0")
    assert "- reconnaît les voix (voix)" in text
    assert "note la suite" not in text
    assert "Texte d'introduction." in text
    assert git(repo, "log", "-1", "--format=%s") == (
        "chore(changelog): met à jour la section « Non publié »"
    )


def test_the_unreleased_section_is_rewritten_never_doubled(release, repo: Path) -> None:
    change(repo, "feat(voix): reconnaît les voix")
    release.unreleased()
    change(repo, "fix(conversion): garde les pistes en WAV")
    release.unreleased()
    text = changelog(repo)
    assert text.count("## Non publié") == 1
    assert "- reconnaît les voix (voix)" in text
    assert "- garde les pistes en WAV (conversion)" in text
    assert "(réécrit pour les utilisateurs)" in text


def test_nothing_unreleased_commits_nothing(release, repo: Path) -> None:
    change(repo, "docs(plan): note la suite")
    head = git(repo, "rev-parse", "HEAD")
    release.unreleased()
    assert git(repo, "rev-parse", "HEAD") == head
    assert "## Non publié" not in changelog(repo)


def test_off_main_nothing_happens(release, repo: Path) -> None:
    git(repo, "switch", "-q", "-c", "feat/essai")
    change(repo, "feat(voix): reconnaît les voix")
    head = git(repo, "rev-parse", "HEAD")
    release.unreleased()
    assert git(repo, "rev-parse", "HEAD") == head
    with pytest.raises(SystemExit):
        release.number()


def test_numbering_takes_every_change_since_the_last_version(release, repo: Path) -> None:
    change(repo, "feat(rappels): rappelle qu'un enregistrement tourne")
    release.unreleased()
    change(repo, "feat(voix): reconnaît les voix")
    release.unreleased()
    change(repo, "fix(conversion): garde les pistes en WAV")
    release.unreleased()
    assert release.upcoming()[0] == "0.35.0"  # one step, whatever the merges in between
    assert release.number() == "0.35.0"
    assert git(repo, "describe", "--tags") == "v0.35.0"
    assert 'version = "0.35.0"' in (repo / "pyproject.toml").read_text(encoding="utf-8")
    text = changelog(repo)
    assert "## Non publié" not in text
    assert text.index("## v0.35.0") < text.index("## v0.34.0")
    assert "- rappelle qu'un enregistrement tourne (rappels)" in text
    assert "- garde les pistes en WAV (conversion)" in text
    assert git(repo, "log", "-1", "--format=%s") == "chore(version): v0.35.0"


def test_nothing_to_publish_is_refused(release, repo: Path) -> None:
    change(repo, "docs(plan): note la suite")
    with pytest.raises(SystemExit, match="Aucune version"):
        release.number()
    assert git(repo, "tag", "--list") == "v0.34.0"


def test_numbering_needs_a_clean_checkout(release, repo: Path) -> None:
    change(repo, "fix(conversion): garde les pistes en WAV")
    (repo / "fichier.txt").write_text("pas commité", encoding="utf-8")
    with pytest.raises(SystemExit, match="pas commitées"):
        release.number()


def test_between_two_versions_the_identifier_says_where(release, repo: Path) -> None:
    assert release.identifier() == "v0.34.0"
    change(repo, "fix(conversion): garde les pistes en WAV")
    found = release.identifier()
    assert found.startswith("v0.34.0-1-g")
    (repo / "fichier.txt").write_text("pas commité", encoding="utf-8")
    assert release.identifier() == f"{found}-modifie"


def test_only_version_tags_count(release, repo: Path) -> None:
    git(repo, "tag", "essai-paquet")
    git(repo, "tag", "v0.35.0-essai")
    assert release.last_tag() == "v0.34.0"


def test_a_hand_rewritten_unreleased_section_is_replaced_and_said(
    release, repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    change(repo, "feat(voix): reconnaît les voix")
    release.unreleased()
    capsys.readouterr()
    text = changelog(repo).replace("- reconnaît les voix (voix)", "- Coulisses reconnaît les voix.")
    (repo / "CHANGELOG.md").write_text(text, encoding="utf-8")
    git(repo, "commit", "-q", "-am", "docs(changelog): réécrit pour les utilisateurs")
    change(repo, "fix(conversion): garde les pistes en WAV")
    release.unreleased()
    assert "réécrite à la main" in capsys.readouterr().err
    assert "- reconnaît les voix (voix)" in changelog(repo)


def test_a_generated_section_replaced_says_nothing(
    release, repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    change(repo, "feat(voix): reconnaît les voix")
    release.unreleased()
    change(repo, "fix(conversion): garde les pistes en WAV")
    release.unreleased()
    assert "réécrite à la main" not in capsys.readouterr().err


def test_an_only_unreleased_section_comes_and_goes(release, repo: Path) -> None:
    (repo / "CHANGELOG.md").write_text("# Journal des versions\n", encoding="utf-8")
    git(repo, "commit", "-q", "-am", "docs(changelog): vide")
    assert release.write_changelog("## Non publié\n\n### Corrections\n\n- essai\n")
    assert (
        changelog(repo) == "# Journal des versions\n\n## Non publié\n\n### Corrections\n\n- essai\n"
    )
    assert release.write_changelog(None)
    assert changelog(repo) == "# Journal des versions\n"
