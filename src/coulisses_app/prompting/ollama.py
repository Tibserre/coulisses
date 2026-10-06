"""The only client of the language model: Ollama on 127.0.0.1 (P1, P4).

Nothing else in the application talks to a model. Every call states its context window
(`num_ctx`): Ollama silently drops what does not fit, so the caller checks the counts
the answer reports (`prompt_eval_count`, `eval_count`) against it.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any

from pydantic import BaseModel, ValidationError

OLLAMA_URL = "http://127.0.0.1:11434"
"""Local only: the one network access the application makes at run time (P1)."""


class OllamaError(RuntimeError):
    """Ollama cannot answer; the message is shown to the user."""


class InstalledModel(BaseModel):
    name: str
    size_bytes: int
    digest: str
    family: str | None = None
    parameter_size: str | None = None


class ChatAnswer(BaseModel):
    content: str
    prompt_eval_count: int | None
    eval_count: int | None
    done_reason: str | None
    total_duration_s: float | None


# -- what Ollama answers (the part we read) ----------------------------------------------


class _Details(BaseModel):
    family: str | None = None
    parameter_size: str | None = None


class _Tag(BaseModel):
    name: str
    size: int = 0
    digest: str = ""
    details: _Details | None = None


class _Tags(BaseModel):
    models: list[_Tag] = []


class _Show(BaseModel):
    model_info: dict[str, Any] = {}


class _Message(BaseModel):
    content: str = ""


class _Chat(BaseModel):
    message: _Message = _Message()
    prompt_eval_count: int | None = None
    eval_count: int | None = None
    done_reason: str | None = None
    total_duration: int | None = None


class _Version(BaseModel):
    version: str | None = None


class _Error(BaseModel):
    error: str


class OllamaClient:
    def __init__(self, base_url: str = OLLAMA_URL, timeout_s: float = 3600.0) -> None:
        if not base_url.startswith(("http://127.0.0.1", "http://localhost", "http://[::1]")):
            raise ValueError("Ollama must be local (P1)")
        self.base_url = base_url
        self.timeout_s = timeout_s

    def _send(self, path: str, body: dict[str, Any] | None, timeout_s: float) -> bytes:
        request = urllib.request.Request(
            self.base_url + path,
            data=None if body is None else json.dumps(body).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="GET" if body is None else "POST",
        )
        try:
            # The URL is local, checked in __init__.
            with urllib.request.urlopen(request, timeout=timeout_s) as response:
                return response.read()
        except urllib.error.HTTPError as exc:
            raw = exc.read().decode("utf-8", errors="replace")
            try:
                detail = _Error.model_validate_json(raw).error
            except ValidationError:
                detail = raw  # not Ollama's JSON: shown as it is, never hidden
            raise OllamaError(f"Ollama a refusé la demande : {detail}") from exc
        except (urllib.error.URLError, TimeoutError, ConnectionError) as exc:
            raise OllamaError(
                "Ollama ne répond pas sur 127.0.0.1:11434 : lancez l'application Ollama, "
                "puis relancez le résumé."
            ) from exc

    def models(self) -> list[InstalledModel]:
        tags = _Tags.model_validate_json(self._send("/api/tags", None, 10.0))
        return [
            InstalledModel(
                name=t.name,
                size_bytes=t.size,
                digest=t.digest,
                family=t.details.family if t.details else None,
                parameter_size=t.details.parameter_size if t.details else None,
            )
            for t in tags.models
        ]

    def version(self) -> str | None:
        return _Version.model_validate_json(self._send("/api/version", None, 10.0)).version

    def context_length(self, model: str) -> int | None:
        """The model's own maximum context, from its metadata."""
        show = _Show.model_validate_json(self._send("/api/show", {"model": model}, 60.0))
        for key, value in show.model_info.items():
            if key.endswith(".context_length") and isinstance(value, int):
                return value
        return None

    def chat(
        self,
        model: str,
        messages: list[dict[str, str]],
        options: dict[str, Any],
        *,
        answer_format: dict[str, Any] | None = None,
    ) -> ChatAnswer:
        """One call, not streamed. `options` must hold `num_ctx` (Ollama truncates
        silently otherwise). `answer_format`: a JSON schema the answer must follow."""
        if "num_ctx" not in options:
            raise ValueError("num_ctx is mandatory: Ollama truncates silently without it")
        model_options = {k: v for k, v in options.items() if k != "think"}
        raw = self._send(
            "/api/chat",
            {
                "model": model,
                "messages": messages,
                "stream": False,
                # Given with the options so that it is recorded with them (provenance).
                "think": bool(options.get("think", False)),
                "options": model_options,
                **({"format": answer_format} if answer_format is not None else {}),
            },
            self.timeout_s,
        )
        answer = _Chat.model_validate_json(raw)
        return ChatAnswer(
            content=answer.message.content,
            prompt_eval_count=answer.prompt_eval_count,
            eval_count=answer.eval_count,
            done_reason=answer.done_reason,
            total_duration_s=answer.total_duration / 1e9 if answer.total_duration else None,
        )
