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
    "SURequireSignedFeed": True,  # a feed changed by someone else is refused
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


PRUNING = {
    "dossiers_de_tests": ["tests", "test"],
    "garder_dossiers": ["lib_utils/test"],
    "suffixes": [".h", ".c", ".pyx"],
    "garder_suffixes_dans": ["jit"],
    "paquets": ["pip"],
    "chemins": ["bin/pip3", "lib/python3.12/idlelib"],
}


def fake_python(root: Path) -> Path:
    site = root / "lib" / "python3.12" / "site-packages"
    files = [
        "bin/python3",
        "bin/pip3",
        "lib/python3.12/idlelib/__init__.py",
        "lib/python3.12/json/__init__.py",
        "site/numlib/__init__.py",
        "site/numlib/core.so",
        "site/numlib/core.pyi",
        "site/numlib/include/numlib.h",
        "site/numlib/tests/test_core.py",
        "site/numlib/linalg/test/test_x.py",
        "site/numlib-1.0.dist-info/licenses/src/LICENSE.c",
        "site/lib_utils/test/warning.py",
        "site/jit/runtime/helper.c",
        "site/pip/__init__.py",
        "site/pip-26.0.dist-info/METADATA",
    ]
    for name in files:
        path = site / name[5:] if name.startswith("site/") else root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("x" * 10)
    return root


def test_pruning_removes_what_the_app_never_loads_and_lists_it(construire, tmp_path) -> None:
    python = fake_python(tmp_path / "python")
    site = python / "lib" / "python3.12" / "site-packages"
    report = tmp_path / "elagage.txt"
    construire.prune(python, PRUNING, report)
    for gone in [
        "numlib/tests",
        "numlib/linalg/test",
        "numlib/include/numlib.h",
        "pip",
        "pip-26.0.dist-info",
    ]:
        assert not (site / gone).exists(), gone
    assert not (python / "bin" / "pip3").exists()
    assert not (python / "lib" / "python3.12" / "idlelib").exists()
    for kept in [
        "numlib/__init__.py",
        "numlib/core.so",
        "numlib/core.pyi",  # stubs stay: some libraries load their modules from them
        "numlib-1.0.dist-info/licenses/src/LICENSE.c",  # licences stay whole
        "lib_utils/test/warning.py",  # part of its library's API
        "jit/runtime/helper.c",  # a JIT compiler keeps its sources
    ]:
        assert (site / kept).exists(), kept
    assert (python / "bin" / "python3").exists()
    assert (python / "lib" / "python3.12" / "json" / "__init__.py").exists()
    listed = report.read_text().splitlines()
    assert len(listed) == 7  # 2 test folders, pip and its metadata, 2 paths, 1 header
    assert all(len(line.split("\t")) == 3 for line in listed)


def test_a_pruning_list_gone_stale_stops_the_build(construire, tmp_path) -> None:
    python = fake_python(tmp_path / "python")
    stale = {**PRUNING, "chemins": [*PRUNING["chemins"], "lib/tcl8.6"]}
    with pytest.raises(SystemExit):
        construire.prune(python, stale, tmp_path / "elagage.txt")
    assert (python / "bin" / "pip3").exists()  # nothing removed before the refusal


def test_the_shipped_pruning_list_keeps_what_the_app_loads() -> None:
    pruning = tomllib.loads((ROOT / "scripts" / "construction.toml").read_text())["elagage"]
    assert (
        "testing" not in pruning["dossiers_de_tests"]
    )  # a library may import its own `testing` module
    assert ".py" not in pruning["suffixes"]  # libraries read their sources (inspect)
    assert ".pyi" not in pruning["suffixes"]  # lazy_loader.attach_stub reads stubs
    assert "cffi" in pruning["garder_suffixes_dans"]  # it compiles at run time
