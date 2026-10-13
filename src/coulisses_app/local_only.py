"""Only Coulisses' own page talks to the service (security review of 2026-10-13).

The service listens on 127.0.0.1 only, yet a web page open in a browser can still reach it:
by naming a host of its own that resolves to 127.0.0.1 (DNS rebinding), then reading what
the service answers; or, from its own site, by sending the requests a browser lets through
without asking (a form, a multipart upload, a POST without body). So:
- the Host must be 127.0.0.1 or localhost;
- a request that changes something (anything but GET and HEAD) must come from the service's
  own page: either no Origin at all (curl, the launcher, scripts) or the service's own, and
  Sec-Fetch-Site, when the browser sends it, `same-origin` or `none`;
- every answer forbids being shown in another site's frame, and lets the page load only its
  own resources (Content-Security-Policy).
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable, Mapping, MutableMapping
from typing import Any

from starlette.responses import JSONResponse

log = logging.getLogger(__name__)

ALLOWED_HOSTS = frozenset({"127.0.0.1", "localhost"})
READ_ONLY = frozenset({"GET", "HEAD"})
SAME_SITE = frozenset({"same-origin", "none"})
# Inline styles: React's style attributes. Fonts and images may be inlined by the build.
CONTENT_SECURITY_POLICY = (
    "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
    "img-src 'self' data: blob:; media-src 'self' blob:; font-src 'self' data:; "
    "connect-src 'self'; object-src 'none'; base-uri 'none'; form-action 'self'; "
    "frame-ancestors 'none'"
)
SECURITY_HEADERS = (
    (b"content-security-policy", CONTENT_SECURITY_POLICY.encode()),
    (b"x-frame-options", b"DENY"),
    (b"x-content-type-options", b"nosniff"),
    (b"referrer-policy", b"no-referrer"),
)
REFUSED = "Refusé : cette demande ne vient pas de Coulisses."

Scope = MutableMapping[str, Any]
Message = MutableMapping[str, Any]
Receive = Callable[[], Awaitable[Message]]
Send = Callable[[Message], Awaitable[None]]
ASGIApp = Callable[[Scope, Receive, Send], Awaitable[None]]


def refusal(headers: Mapping[str, str], method: str) -> str | None:
    """Why a request is refused (headers in lower case), or None if it may go on."""
    host = headers.get("host", "").lower()
    if host.split(":", 1)[0] not in ALLOWED_HOSTS:
        return f"hôte « {host} »"
    if method.upper() in READ_ONLY:
        return None
    origin = headers.get("origin")
    if origin is not None and origin.lower() != f"http://{host}":
        return f"origine « {origin} »"
    site = headers.get("sec-fetch-site")
    if site is not None and site.lower() not in SAME_SITE:
        return f"demande d'un autre site ({site})"
    return None


class LocalOnly:
    """ASGI middleware (not FastAPI's `@app.middleware`, which streams poorly: the meter's
    server-sent events go through this one untouched)."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        headers = {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope["headers"]}
        why = refusal(headers, scope["method"])
        if why is not None:
            log.warning("refused %s %s: %s", scope["method"], scope.get("path", ""), why)
            await JSONResponse({"detail": REFUSED}, status_code=403)(scope, receive, send)
            return

        async def with_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                message["headers"] = [*message.get("headers", []), *SECURITY_HEADERS]
            await send(message)

        await self.app(scope, receive, with_headers)
