"""What a publication sends to the friends (ADR 0040; scripts/publier.py): the notes of the
version, from CHANGELOG.md; an appcast with one item, its DMG on github.com, nothing remote
in its notes; and the version it compares with, the latest one confirmed."""

from __future__ import annotations

import importlib.util
import re
from pathlib import Path
from types import ModuleType

import pytest

ROOT = Path(__file__).resolve().parents[1]

CHANGELOG = """# Journal des versions

## v0.26.0 — 2026-10-14

### Nouveautés

- publie une version pour les amis (publication)
- dit <tout> & le reste (essai)

### Corrections

- lit la signature entière (construction)

## v0.25.1 — 2026-10-13

### Corrections

- ne reprend que les étapes de la version du moteur en place (traitement)
"""


@pytest.fixture(scope="module")
def publier() -> ModuleType:
    spec = importlib.util.spec_from_file_location("publier", ROOT / "scripts" / "publier.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_only_a_version_tag_is_published(publier) -> None:
    assert publier.version_of("v0.26.0") == "0.26.0"
    for wrong in ("0.26.0", "v0.26", "main", "v0.26.0-rc1"):
        with pytest.raises(SystemExit):
            publier.version_of(wrong)


def test_the_notes_are_the_versions_section_only(publier) -> None:
    notes = publier.release_notes(CHANGELOG, "0.26.0")
    assert notes.startswith("### Nouveautés")
    assert "lit la signature entière" in notes
    assert "v0.25.1" not in notes and "ne reprend que" not in notes
    assert publier.release_notes(CHANGELOG, "0.25.1").startswith("### Corrections")
    with pytest.raises(SystemExit):
        publier.release_notes(CHANGELOG, "9.9.9")


def test_the_notes_become_plain_escaped_html(publier) -> None:
    shown = publier.notes_html(publier.release_notes(CHANGELOG, "0.26.0"))
    assert "<h3>Nouveautés</h3>" in shown and "<h3>Corrections</h3>" in shown
    assert shown.count("<ul>") == 2 and shown.count("</ul>") == 2
    assert "dit &lt;tout&gt; &amp; le reste (essai)" in shown


def appcast_of(publier: ModuleType, url: str | None = None) -> str:
    notes = publier.release_notes(CHANGELOG, "0.26.0")
    return publier.appcast(
        "0.26.0",
        notes,
        url or publier.dmg_url("Tibserre/coulisses", "0.26.0"),
        123456,
        "c2lnbmF0dXJl",
        "14.4",
    )


def test_the_appcast_offers_this_version_from_github_signed(publier) -> None:
    feed = appcast_of(publier)
    assert "<sparkle:version>0.26.0</sparkle:version>" in feed
    assert "<sparkle:minimumSystemVersion>14.4</sparkle:minimumSystemVersion>" in feed
    assert (
        'url="https://github.com/Tibserre/coulisses/releases/download/v0.26.0/Coulisses-0.26.0.dmg"'
        in feed
    )
    assert 'length="123456"' in feed and 'sparkle:edSignature="c2lnbmF0dXJl"' in feed


def test_the_appcast_fetches_nothing_else(publier) -> None:
    """Sparkle's window shows the notes: nothing in them may reach out (P1)."""
    feed = appcast_of(publier)
    assert "releaseNotesLink" not in feed
    description = re.search(r"<description>(.*)</description>", feed, re.S)
    assert description is not None
    assert not re.search(r"https?:|//|<img|<script|<link|src=", description.group(1))
    urls = re.findall(r'url="([^"]+)"', feed)
    assert urls == [publier.dmg_url("Tibserre/coulisses", "0.26.0")]


def test_a_dmg_elsewhere_than_github_is_refused(publier) -> None:
    with pytest.raises(SystemExit):
        appcast_of(publier, "https://exemple.org/Coulisses-0.26.0.dmg")


def test_the_eddsa_signature_is_read_or_refused(publier) -> None:
    output = 'sparkle:edSignature="AbC+/=" length="987"\n'
    assert publier.parse_signature(output) == ("AbC+/=", 987)
    with pytest.raises(SystemExit):
        publier.parse_signature("Error: no key in the keychain")


def test_the_previous_publication_is_the_latest_confirmed(
    publier, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(publier, "PUBLICATIONS", tmp_path)
    assert publier.previous_publication("0.26.0") is None
    for tag, confirmed in (("v0.9.0", True), ("v0.10.0", True), ("v0.11.0", False)):
        (tmp_path / tag).mkdir()
        if confirmed:
            (tmp_path / tag / publier.CONFIRMED).write_text("x", encoding="utf-8")
    (tmp_path / "brouillon").mkdir()
    # 0.10 after 0.9 (numbers, not text); an unconfirmed one is never compared with.
    assert publier.previous_publication("0.26.0") == tmp_path / "v0.10.0"
    (tmp_path / "v0.26.0").mkdir()
    (tmp_path / "v0.26.0" / publier.CONFIRMED).write_text("x", encoding="utf-8")
    assert publier.previous_publication("0.26.0") == tmp_path / "v0.10.0"


def test_a_higher_version_is_never_the_previous_one(
    publier, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(publier, "PUBLICATIONS", tmp_path)
    for tag in ("v0.10.0", "v0.30.0"):
        (tmp_path / tag).mkdir()
        (tmp_path / tag / publier.CONFIRMED).write_text("x", encoding="utf-8")
    assert publier.previous_publication("0.26.0") == tmp_path / "v0.10.0"


def test_a_preparation_sent_or_confirmed_is_never_replaced(publier, tmp_path: Path) -> None:
    out = tmp_path / "v0.26.0"
    assert publier.replaceable(out) is False  # nothing yet
    out.mkdir()
    assert publier.replaceable(out) is True  # an earlier try, never sent
    (out / publier.SENT).write_text("x", encoding="utf-8")
    with pytest.raises(SystemExit):
        publier.replaceable(out)  # its DMG is on GitHub: kept to be confirmed
    (out / publier.SENT).unlink()
    (out / publier.CONFIRMED).write_text("x", encoding="utf-8")
    with pytest.raises(SystemExit):
        publier.replaceable(out)


DMG = "Coulisses-0.26.0.dmg"


def test_only_the_very_dmg_prepared_is_confirmed(publier) -> None:
    good = {"name": DMG, "digest": "sha256:abc"}
    other = {"name": "appcast.xml", "digest": "sha256:zzz"}
    assert publier.release_state({"isPrerelease": True, "assets": [good]}, DMG, "abc") == (
        "pre-release"
    )
    # Run again after a confirmation cut short: already published, the same DMG.
    assert (
        publier.release_state({"isPrerelease": False, "assets": [good, other]}, DMG, "abc")
        == "published"
    )
    for fields in (
        {"isPrerelease": True, "assets": []},
        {"isPrerelease": True, "assets": [{"name": DMG, "digest": "sha256:autre"}]},
        {"isPrerelease": True, "assets": [{"name": DMG}]},
        {"isPrerelease": True, "assets": [good, good]},
    ):
        with pytest.raises(SystemExit):
            publier.release_state(fields, DMG, "abc")


def test_a_send_begun_protects_its_preparation_too(publier, tmp_path: Path) -> None:
    out = tmp_path / "v0.26.0"
    out.mkdir()
    (out / publier.SENDING).write_text("x", encoding="utf-8")
    with pytest.raises(SystemExit):
        publier.replaceable(out)


def test_origin_must_be_exactly_the_repository(publier) -> None:
    for origin in (
        "https://github.com/Tibserre/coulisses.git",
        "https://github.com/Tibserre/coulisses",
        "git@github.com:Tibserre/coulisses.git",
        "ssh://git@github.com/Tibserre/coulisses.git",
    ):
        assert publier.same_repository(origin, "Tibserre/coulisses"), origin
    for origin in (
        "git@github.com:Tibserre/coulisses-moteur.git",
        "https://github.com/autre/coulisses.git",
        "https://exemple.org/Tibserre/coulisses.git",
    ):
        assert not publier.same_repository(origin, "Tibserre/coulisses"), origin


def test_without_a_confirmed_version_only_the_very_first_goes_on(
    publier, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Refused before anything is checked out or built."""
    monkeypatch.setattr(publier, "PUBLICATIONS", tmp_path)
    monkeypatch.setattr(publier, "checked_out", lambda tag: pytest.fail("went on"))
    with pytest.raises(SystemExit):
        publier.prepare("v0.26.0", first=False)
    (tmp_path / "v0.25.1").mkdir()
    (tmp_path / "v0.25.1" / publier.CONFIRMED).write_text("x", encoding="utf-8")
    with pytest.raises(SystemExit):
        publier.prepare("v0.26.0", first=True)


def test_one_publication_at_a_time(
    publier, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(publier, "CACHE", tmp_path)
    first = publier.one_at_a_time()
    try:
        with pytest.raises(SystemExit):
            publier.one_at_a_time()
    finally:
        first.close()
    publier.one_at_a_time().close()  # free again once the first one ends


@pytest.mark.parametrize("action", ["--envoyer", "--confirmer"])
def test_premiere_only_prepares(action: str) -> None:
    import subprocess
    import sys

    done = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "publier.py"), "v0.26.0", action, "--premiere"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert done.returncode == 2
    assert "--premiere ne vaut que pour préparer" in done.stderr
