"""Refuse requests that a web page on another site makes through the operator's browser.

Concord has no authentication, so any web page open in the operator's browser could
otherwise send requests to http://127.0.0.1:8000 (cross-site POSTs need no CORS approval, and
WebSockets are not subject to CORS at all: a page could read the live event stream), or use
DNS rebinding (a site whose name resolves to 127.0.0.1) to read the API as if same-origin.

Rules, for HTTP and WebSocket alike:

* an ``Origin`` header must name this server (same host and port as the request) or a
  loopback host (the console, the board app, the Vite dev server);
* ``Sec-Fetch-Site: cross-site`` is refused;
* a request that comes from a browser (``Origin``, ``Sec-Fetch-*`` or a browser user agent)
  must address the server by a loopback host name (``127.0.0.1``, ``localhost``, ``::1``),
  unless the operator allowed remote access (then by the configured host).

Programs that are not browsers (the SDKs, scripts, curl) send none of these headers and are
unaffected; they run as local processes and could use the API anyway (docs/SECURITY.md).
"""

from __future__ import annotations

import ipaddress
import json
import logging
from urllib.parse import urlsplit

from starlette.types import ASGIApp, Receive, Scope, Send

log = logging.getLogger(__name__)


def _hostname(netloc: str) -> str:
    if netloc.startswith("["):
        return netloc[1:].split("]", 1)[0]
    return netloc.rsplit(":", 1)[0] if netloc.count(":") == 1 else netloc


def loopback_name(host: str) -> bool:
    host = host.strip().lower()
    if host == "localhost" or host.endswith(".localhost"):
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


class LocalOriginMiddleware:
    def __init__(self, app: ASGIApp, *, allow_remote: bool = False) -> None:
        self.app = app
        self.allow_remote = allow_remote

    def _reason(self, scope: Scope) -> str | None:
        headers = {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope["headers"]}
        host_header = headers.get("host", "")
        origin = headers.get("origin")
        fetch_site = headers.get("sec-fetch-site")
        browser = (
            origin is not None
            or fetch_site is not None
            or "mozilla/" in headers.get("user-agent", "").lower()
        )
        if fetch_site == "cross-site":
            return "cross-site request from another web site"
        if origin is not None and origin != "null":
            o = urlsplit(origin)
            same = o.netloc.lower() == host_header.lower()
            if not (same or loopback_name(o.hostname or "")):
                return f"request from the web page {origin}"
        elif origin == "null":
            return "request from an opaque origin (sandboxed page or file)"
        if browser and host_header and not self.allow_remote:
            name = _hostname(host_header)
            if not loopback_name(name):  # DNS rebinding: a site name that resolves to us
                return f"browser request for host {name!r} (use http://127.0.0.1)"
        return None

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] not in ("http", "websocket"):
            await self.app(scope, receive, send)
            return
        reason = self._reason(scope)
        if reason is None:
            await self.app(scope, receive, send)
            return
        log.warning("refused %s %s: %s", scope["type"], scope.get("path", ""), reason)
        if scope["type"] == "websocket":
            await receive()  # websocket.connect; closing before accepting refuses the handshake
            await send({"type": "websocket.close", "code": 1008, "reason": "origin not allowed"})
            return
        body = json.dumps(
            {"error": {"code": "forbidden_origin", "message": f"refused: {reason}"}}
        ).encode()
        await send(
            {
                "type": "http.response.start",
                "status": 403,
                "headers": [(b"content-type", b"application/json")],
            }
        )
        await send({"type": "http.response.body", "body": body})
