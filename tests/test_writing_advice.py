"""The language model advised to a Mac in the Rédaction tab (lot 11g of the plan): by its
memory, from tiers of reglages.toml where a model is named only once measured; and a model
missing from Ollama said in French, with what to do."""

from __future__ import annotations

import io
import urllib.error
from email.message import Message

import pytest
from fastapi.testclient import TestClient

from coulisses_app import api, machine
from coulisses_app.api import create_app
from coulisses_app.paths import DataDir
from coulisses_app.prompting import assembly, ollama
from coulisses_app.prompting.ollama import InstalledModel, OllamaClient, OllamaError

from .conftest import FAKE_CHAIN, FakeModel, local_client

TIERS = [
    assembly.Advice(min_memory_gb=48, model="grand:35b"),
    assembly.Advice(min_memory_gb=24, model=""),
    assembly.Advice(min_memory_gb=16, model="petit:8b"),
]


@pytest.mark.parametrize(
    ("memory", "advised"),
    [(64.0, "grand:35b"), (48.0, "grand:35b"), (32.0, ""), (16.0, "petit:8b"), (15.9, None)],
)
def test_a_mac_gets_the_tier_of_its_memory(memory: float, advised: str | None) -> None:
    tier = assembly.advice_for(memory, TIERS)
    assert (tier.model if tier else None) == advised


def test_the_tiers_shipped_name_no_model_until_one_is_measured() -> None:
    rules = assembly.settings()
    assert [a.min_memory_gb for a in rules.advice] == [48, 24, 16]
    assert all(a.model == "" for a in rules.advice)
    assert rules.writing_min_memory_gb == 16


def installed(name: str) -> InstalledModel:
    return InstalledModel(name=name, size_bytes=1, digest="d", family=None, parameter_size=None)


def advice(monkeypatch: pytest.MonkeyPatch, memory: float | None, found: list[str]):
    rules = assembly.settings().model_copy(update={"advice": TIERS})
    monkeypatch.setattr(api.assembly, "settings", lambda: rules)
    monkeypatch.setattr(api, "memory_gb", lambda: memory)
    return api.writing_advice([installed(n) for n in found])


def test_the_advice_says_if_the_model_is_installed(monkeypatch: pytest.MonkeyPatch) -> None:
    missing = advice(monkeypatch, 64.0, ["autre:7b"])
    assert (missing.model, missing.installed) == ("grand:35b", False)
    there = advice(monkeypatch, 64.0, ["grand:35b"])
    assert (there.model, there.installed) == ("grand:35b", True)


def test_no_advice_unmeasured_under_the_minimum_or_memory_unknown(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert advice(monkeypatch, 32.0, []).model is None  # tier not measured yet
    small = advice(monkeypatch, 8.0, [])
    assert small.model is None and small.memory_gb == 8.0 and small.minimum_gb == 16
    unknown = advice(monkeypatch, None, [])
    assert unknown.memory_gb is None and unknown.model is None


def test_the_writing_tab_gets_the_advice_even_without_ollama(
    data: DataDir, fake_model: FakeModel
) -> None:
    client: TestClient = local_client(
        create_app(
            data, FAKE_CHAIN, profile="essai", processor=None, web_dir=None, model_client=fake_model
        )
    )
    fake_model.down = True
    shown = client.get("/api/modeles").json()
    assert shown["reachable"] is False
    assert set(shown["advice"]) == {"memory_gb", "model", "installed", "minimum_gb"}
    assert shown["advice"]["minimum_gb"] == 16 and shown["advice"]["installed"] is False


def test_a_memory_sysconf_does_not_know_is_unknown(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(machine.os, "sysconf", lambda _: -1)
    assert machine.memory_gb() is None


def test_a_model_missing_from_ollama_is_said_in_french(monkeypatch: pytest.MonkeyPatch) -> None:
    def refused(*_: object, **__: object) -> None:
        body = io.BytesIO(b'{"error": "model \\"absent:35b\\" not found, try pulling it first"}')
        raise urllib.error.HTTPError(
            "http://127.0.0.1:11434/api/chat", 404, "Not Found", Message(), body
        )

    monkeypatch.setattr(ollama.urllib.request, "urlopen", refused)
    with pytest.raises(OllamaError, match="« absent:35b » n'est pas installé dans Ollama"):
        OllamaClient()._send("/api/chat", {"model": "absent:35b"}, 5.0)


def test_another_404_keeps_ollamas_own_words(monkeypatch: pytest.MonkeyPatch) -> None:
    """An older Ollama without the route: not taken for a missing model."""

    def refused(*_: object, **__: object) -> None:
        body = io.BytesIO(b"404 page not found")  # Go's default page, not Ollama's JSON
        raise urllib.error.HTTPError(
            "http://127.0.0.1:11434/api/chat", 404, "Not Found", Message(), body
        )

    monkeypatch.setattr(ollama.urllib.request, "urlopen", refused)
    with pytest.raises(OllamaError, match="Ollama a refusé la demande : 404 page not found"):
        OllamaClient()._send("/api/chat", {"model": "absent:35b"}, 5.0)
