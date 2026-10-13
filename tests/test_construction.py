"""What the build of Coulisses.app writes about its updates (ADR 0040): never an automatic
download nor install, never a system profile; a feed only with the update key, and only
from GitHub. The build script is the repository's (`scripts/construire.py`)."""

from __future__ import annotations

import importlib.util
import tomllib
from pathlib import Path
from types import ModuleType

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def construire() -> ModuleType:
    spec = importlib.util.spec_from_file_location("construire", ROOT / "scripts" / "construire.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def sparkle(**over: str) -> dict[str, str]:
    pinned = tomllib.loads((ROOT / "scripts" / "construction.toml").read_text(encoding="utf-8"))
    return {**pinned["sparkle"], **over}


NEVER_ON_ITS_OWN = {
    "SUEnableSystemProfiling": False,
    "SUAllowsAutomaticUpdates": False,
    "SUAutomaticallyUpdate": False,
}


def test_with_its_key_the_app_may_look_for_updates_never_on_its_own(construire) -> None:
    keys = construire.update_settings(sparkle(public_key="clé"), ad_hoc=False)
    assert NEVER_ON_ITS_OWN.items() <= keys.items()
    assert keys["SUPublicEDKey"] == "clé"
    assert keys["SUFeedURL"].startswith("https://github.com/Tibserre/coulisses/releases/")
    assert keys["SUScheduledCheckInterval"] == 86400
    assert "SUEnableAutomaticChecks" not in keys  # the user is asked, never decided for


def test_without_the_key_only_a_try_builds_and_it_has_no_updates(construire) -> None:
    with pytest.raises(SystemExit):
        construire.update_settings(sparkle(public_key=""), ad_hoc=False)
    keys = construire.update_settings(sparkle(public_key=""), ad_hoc=True)
    assert NEVER_ON_ITS_OWN.items() <= keys.items()
    assert "SUFeedURL" not in keys and "SUPublicEDKey" not in keys


def test_a_feed_elsewhere_than_github_is_refused(construire) -> None:
    with pytest.raises(SystemExit):
        construire.update_settings(
            sparkle(public_key="clé", feed_url="http://exemple.org/appcast.xml"), ad_hoc=False
        )
