"""Only Coulisses' own page talks to the service (security review of 2026-10-13): no other
host name (DNS rebinding), no request that changes something from another site (CSRF), and
answers that no other site may frame."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from coulisses_app.api import create_app
from coulisses_app.local_only import CONTENT_SECURITY_POLICY, refusal
from coulisses_app.paths import DataDir

from .conftest import FAKE_CHAIN, local_client

HOST = "127.0.0.1:8765"


@pytest.fixture
def client(data: DataDir) -> TestClient:
    return local_client(create_app(data, FAKE_CHAIN, profile="essai", processor=None, web_dir=None))


@pytest.mark.parametrize(
    "host", ["attaquant.example:8765", "testserver", "127.0.0.1.evil.example", ""]
)
def test_another_host_name_is_refused_even_to_read(host: str) -> None:
    assert refusal({"host": host}, "GET") is not None


@pytest.mark.parametrize("host", ["127.0.0.1:8765", "localhost:8766", "LOCALHOST:8765"])
def test_the_services_own_names_may_read(host: str) -> None:
    assert refusal({"host": host}, "GET") is None


@pytest.mark.parametrize(
    "headers",
    [
        {"origin": "https://attaquant.example"},
        {"origin": "null"},  # a sandboxed frame or a file
        {"origin": "http://127.0.0.1:11434"},  # another service of this Mac (Ollama)
        {"sec-fetch-site": "cross-site"},
        {"sec-fetch-site": "same-site"},
    ],
)
def test_another_site_cannot_change_anything(headers: dict[str, str]) -> None:
    for method in ("POST", "PUT", "PATCH", "DELETE", "OPTIONS"):
        assert refusal({"host": HOST, **headers}, method) is not None


@pytest.mark.parametrize(
    "headers",
    [
        {},  # curl, the launcher, a script: no Origin
        {"origin": f"http://{HOST}", "sec-fetch-site": "same-origin"},  # the app's own page
        {"sec-fetch-site": "none"},  # typed by the user
    ],
)
def test_the_services_own_page_may_change_things(headers: dict[str, str]) -> None:
    assert refusal({"host": HOST, **headers}, "POST") is None


def test_the_service_answers_only_to_its_own_names(client: TestClient) -> None:
    assert client.get("/api/etat").status_code == 200
    rebound = client.get("/api/etat", headers={"host": "attaquant.example:8765"})
    assert rebound.status_code == 403
    assert "ne vient pas de Coulisses" in rebound.json()["detail"]  # said by the interface


def test_a_recording_cannot_be_paused_from_another_site(client: TestClient) -> None:
    """The scenario found by the review: a page open during a rehearsal pausing it."""
    forged = client.post(
        "/api/enregistrement/pause",
        headers={"origin": "https://attaquant.example", "content-type": "text/plain"},
        content="x",
    )
    assert forged.status_code == 403
    own = client.post("/api/enregistrement/pause", headers={"origin": f"http://{HOST}"})
    assert own.status_code != 403  # reaches the service, which says nothing records


def test_every_answer_forbids_framing_and_foreign_resources(client: TestClient) -> None:
    headers = client.get("/api/etat").headers
    assert headers["content-security-policy"] == CONTENT_SECURITY_POLICY
    assert "frame-ancestors 'none'" in CONTENT_SECURITY_POLICY
    assert headers["x-frame-options"] == "DENY"
    assert headers["x-content-type-options"] == "nosniff"


def test_the_api_description_is_not_served(client: TestClient) -> None:
    assert client.get("/openapi.json").status_code == 404
