"""The bridge `coulisses-mcp` (ADR 0065): MCP on stdio, read only, its own app only. It sends
nothing but GET, to nothing but 127.0.0.1; it wakes its app when closed and stops when the
app was updated."""

from __future__ import annotations

import inspect
import io
import json
import re
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit

import pytest
from fastapi.testclient import TestClient

from coulisses_app import bridge
from coulisses_app.bridge import DEVELOPMENT, PUBLISHED, BridgeError, Service
from coulisses_app.paths import DataDir

from .test_connecteur import _open, _prepared


class Through:
    """The bridge's requests sent to the app of the test, answered as the real service
    answers them; each one kept, to check what the bridge sends."""

    def __init__(self, client: TestClient, build: str = "v0.37.0") -> None:
        self.client = client
        self.build = build
        self.sent: list[Any] = []
        self.down = False

    def __call__(self, request: Any, timeout: float) -> Any:
        self.sent.append(request)
        if self.down:
            raise URLError("connection refused")
        url = urlsplit(request.full_url)
        if url.path == "/api/etat":
            return {"app_build": self.build}
        response = self.client.get(url.path + (f"?{url.query}" if url.query else ""))
        if response.status_code >= 400:
            raise HTTPError(
                request.full_url,
                response.status_code,
                "",
                None,  # pyright: ignore[reportArgumentType]
                io.BytesIO(response.content),
            )
        return response.json()


def _exchange(service: Service, *messages: dict[str, Any]) -> list[dict[str, Any]]:
    stdin = io.StringIO("".join(json.dumps(m) + "\n" for m in messages))
    stdout = io.StringIO()
    assert bridge.serve(service, stdin, stdout) == 0
    return [json.loads(line) for line in stdout.getvalue().splitlines()]


def _call(n: int, name: str, **arguments: Any) -> dict[str, Any]:
    return {
        "jsonrpc": "2.0",
        "id": n,
        "method": "tools/call",
        "params": {"name": name, "arguments": arguments},
    }


def _text(reply: dict[str, Any]) -> str:
    return reply["result"]["content"][0]["text"]


def test_an_assistant_reads_coulisses_through_it(data: DataDir, recording: Path) -> None:
    client, session_id, space_id = _prepared(data, recording)
    _open(client, space_id)
    replies = _exchange(
        Service(PUBLISHED, fetch=Through(client)),
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {"protocolVersion": "2025-06-18"},
        },
        {"jsonrpc": "2.0", "method": "notifications/initialized"},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
        _call(3, "lister_seances"),
        _call(4, "lire_seance", seance=session_id),
        _call(5, "lire_transcript", seance=session_id, nombre=50),
        _call(6, "chercher", q="échauffement"),
        _call(7, "lire_seance", seance="inconnue"),
        {"jsonrpc": "2.0", "id": 8, "method": "ping"},
    )
    assert [r["id"] for r in replies] == [1, 2, 3, 4, 5, 6, 7, 8]  # no answer to a notification
    assert replies[0]["result"]["serverInfo"]["name"] == "coulisses"
    assert replies[0]["result"]["protocolVersion"] == "2025-06-18"
    assert {t["name"] for t in replies[1]["result"]["tools"]} == {
        "chercher",
        "lister_seances",
        "lire_seance",
        "lire_resume",
        "lire_transcript",
    }
    assert json.loads(_text(replies[2]))["sessions"][0]["id"] == session_id
    assert replies[3]["result"]["isError"] is False
    assert json.loads(_text(replies[3]))["title"] == "Répétition chez Personne C"
    assert "Personne" in json.loads(_text(replies[4]))["turns"][0]["text"]
    assert json.loads(_text(replies[5]))["sessions"]
    assert replies[6]["result"]["isError"] is True
    assert _text(replies[6]) == "Séance introuvable, ou dans un espace fermé au connecteur."


def test_it_sends_nothing_but_get_to_nothing_but_its_own_service(
    data: DataDir, recording: Path
) -> None:
    client, session_id, space_id = _prepared(data, recording)
    _open(client, space_id)
    through = Through(client)
    calls = [
        _call(n, str(tool["name"]), seance=session_id, resume=1, q="bonjour")
        for n, tool in enumerate(bridge.TOOLS)
    ]
    _exchange(Service(PUBLISHED, fetch=through), *calls)
    assert len(through.sent) > len(calls)
    for request in through.sent:
        url = urlsplit(request.full_url)
        assert request.get_method() == "GET", request.full_url
        assert (url.scheme, url.hostname, url.port) == ("http", "127.0.0.1", 8765)
        assert request.data is None
    # And by construction: one place makes a request, in GET, to HOST only.
    source = inspect.getsource(bridge)
    assert source.count("Request(") == 1 and 'method="GET"' in source
    assert not re.search(r"\b(POST|PUT|PATCH|DELETE)\b", source)
    assert re.findall(r"https?://[^\s\"']+", source) == ["http://{HOST}:{variant.port}"]
    assert bridge.HOST == "127.0.0.1"


def test_closed_the_assistant_is_told_why(data: DataDir, recording: Path) -> None:
    client, session_id, _ = _prepared(data, recording)
    service = Service(PUBLISHED, fetch=Through(client))
    replies = _exchange(service, _call(1, "lire_seance", seance=session_id))
    assert replies[0]["result"]["isError"] is True
    assert "coupé" in _text(replies[0])


def test_the_app_closed_is_woken_without_a_window(data: DataDir, recording: Path) -> None:
    client, _, space_id = _prepared(data, recording)
    _open(client, space_id)
    through = Through(client)
    through.down = True
    opened: list[list[str]] = []

    def opener(args: list[str]) -> int:
        opened.append(args)
        through.down = False
        return 0

    service = Service(DEVELOPMENT, fetch=through, opener=opener, sleep=lambda _s: None)
    replies = _exchange(service, _call(1, "lister_seances"))
    assert opened == [["open", "-g", "-b", "local.coulisses.app.dev", "--args", "--connecteur"]]
    assert replies[0]["result"]["isError"] is False
    assert all(urlsplit(r.full_url).port == 8766 for r in through.sent)


def test_an_app_that_does_not_start_is_said(data: DataDir, recording: Path) -> None:
    client, _, _ = _prepared(data, recording)
    through = Through(client)
    through.down = True
    now = [0.0]

    def sleep(seconds: float) -> None:
        now[0] += seconds

    service = Service(
        PUBLISHED, fetch=through, opener=lambda _a: 0, clock=lambda: now[0], sleep=sleep
    )
    with pytest.raises(BridgeError, match="60 secondes"):
        service.get("/api/connecteur/seances")
    assert now[0] >= bridge.WAKE_WAIT_S


def test_it_stops_once_the_app_was_updated(data: DataDir, recording: Path) -> None:
    client, _, space_id = _prepared(data, recording)
    _open(client, space_id)
    through = Through(client)

    class Updating(io.StringIO):
        def write(self, s: str) -> int:
            through.build = "v0.38.0"  # updated after the first answer
            return super().write(s)

    stdin = io.StringIO("".join(json.dumps(_call(n, "lister_seances")) + "\n" for n in (1, 2)))
    stdout = Updating()
    assert bridge.serve(Service(PUBLISHED, fetch=through), stdin, stdout) == 0
    assert [json.loads(line)["id"] for line in stdout.getvalue().splitlines()] == [1]


def test_what_is_not_mcp_is_refused() -> None:
    service = Service(PUBLISHED, fetch=lambda _r, _t: {"app_build": "x"})
    unknown = json.dumps({"jsonrpc": "2.0", "id": 3, "method": "inconnu"})
    stdout = io.StringIO()
    bridge.serve(service, io.StringIO(f"pas du json\n[1]\n{unknown}\n"), stdout)
    codes = [json.loads(line)["error"]["code"] for line in stdout.getvalue().splitlines()]
    assert codes == [-32700, -32600, -32601]


def _never(*_args: Any) -> Any:
    pytest.fail("not expected")


def test_an_app_not_installed_is_said_at_once(data: DataDir, recording: Path) -> None:
    client, _, _ = _prepared(data, recording)
    through = Through(client)
    through.down = True
    service = Service(PUBLISHED, fetch=through, opener=lambda _a: 1, sleep=_never)
    with pytest.raises(BridgeError, match="introuvable"):
        service.get("/api/connecteur/seances")


def test_it_stops_once_the_app_went_away(data: DataDir, recording: Path) -> None:
    """Quit (or being updated) after answering: the bridge stops, never opens it again."""
    client, _, space_id = _prepared(data, recording)
    _open(client, space_id)
    through = Through(client)

    class Quitting(io.StringIO):
        def write(self, s: str) -> int:
            through.down = True
            return super().write(s)

    stdin = io.StringIO("".join(json.dumps(_call(n, "lister_seances")) + "\n" for n in (1, 2)))
    stdout = Quitting()
    service = Service(PUBLISHED, fetch=through, opener=_never)
    assert bridge.serve(service, stdin, stdout) == 0
    assert [json.loads(line)["id"] for line in stdout.getvalue().splitlines()] == [1]


def test_bad_arguments_and_unreadable_answers_are_said() -> None:
    def fetch(request: Any, _timeout: float) -> Any:
        if urlsplit(request.full_url).path == "/api/etat":
            return {"app_build": "x"}
        raise ValueError("pas du JSON")

    replies = _exchange(
        Service(PUBLISHED, fetch=fetch),
        {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": [1]},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"arguments": "x"}},
        _call(3, "lister_seances"),
    )
    assert [r.get("error", {}).get("code") for r in replies[:2]] == [-32602, -32602]
    assert replies[2]["result"]["isError"] and "illisible" in _text(replies[2])


class _Local(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        if self.path == "/redirige":
            self.send_response(302)
            self.send_header("Location", "http://exemple.invalid/vole")
            self.end_headers()
            return
        body = json.dumps({"chemin": self.path}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: Any) -> None:
        return


def test_no_proxy_and_no_redirection_whatever_the_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A proxy in the environment would get 127.0.0.1's requests, with what is read; a
    redirection could send them elsewhere: neither is followed (P1)."""
    for name in ("HTTP_PROXY", "http_proxy", "ALL_PROXY"):
        monkeypatch.setenv(name, "http://exemple.invalid:3128")
    monkeypatch.delenv("NO_PROXY", raising=False)
    monkeypatch.delenv("no_proxy", raising=False)
    server = HTTPServer(("127.0.0.1", 0), _Local)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base = f"http://127.0.0.1:{server.server_port}"
        # Through the proxy, it would fail: exemple.invalid does not exist.
        assert bridge._fetch(bridge.Request(base + "/api/etat", method="GET"), 5) == {  # pyright: ignore[reportPrivateUsage]
            "chemin": "/api/etat"
        }
        with pytest.raises(HTTPError) as refused:
            bridge._fetch(bridge.Request(base + "/redirige", method="GET"), 5)  # pyright: ignore[reportPrivateUsage]
        assert refused.value.code == 302
    finally:
        server.shutdown()
        server.server_close()
