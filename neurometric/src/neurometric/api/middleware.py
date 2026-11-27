"""HTTP hardening: security headers, request-size limits and login rate limiting."""
from __future__ import annotations

import os
import threading
import time
from collections import defaultdict, deque
from typing import Callable

from starlette.types import ASGIApp, Message, Receive, Scope, Send

CSP = ("default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; "
       "script-src 'self'; connect-src 'self'; font-src 'self'; object-src 'none'; "
       "frame-ancestors 'none'; base-uri 'none'; form-action 'self'")

SECURITY_HEADERS = {
    b"x-content-type-options": b"nosniff",
    b"x-frame-options": b"DENY",
    b"referrer-policy": b"no-referrer",
    b"permissions-policy": b"camera=(), microphone=(), geolocation=(), payment=(), usb=()",
    b"cross-origin-opener-policy": b"same-origin",
    b"cross-origin-resource-policy": b"same-origin",
    b"content-security-policy": CSP.encode(),
}


class SecurityHeadersMiddleware:
    """Adds security headers to every response; API responses are never cached."""

    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        path = scope.get("path", "")

        async def send_wrapper(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = [(k, v) for k, v in message.get("headers", [])
                           if k.lower() not in SECURITY_HEADERS and k.lower() != b"server"]
                headers += list(SECURITY_HEADERS.items())
                if path.startswith("/api"):
                    headers.append((b"cache-control", b"no-store"))
                    headers.append((b"pragma", b"no-cache"))
                if scope.get("scheme") == "https":
                    headers.append((b"strict-transport-security",
                                    b"max-age=31536000; includeSubDomains"))
                message["headers"] = headers
            await send(message)

        await self.app(scope, receive, send_wrapper)


class BodySizeLimitMiddleware:
    """Rejects request bodies above a limit (413), checking Content-Length and the streamed
    byte count. ``limits`` maps path prefixes to smaller limits (longest prefix wins)."""

    def __init__(self, app: ASGIApp, default_limit: int, limits: dict[str, int] | None = None):
        self.app = app
        self.default = default_limit
        self.limits = sorted((limits or {}).items(), key=lambda kv: -len(kv[0]))

    def _limit(self, path: str) -> int:
        for prefix, lim in self.limits:
            if path.startswith(prefix):
                return lim
        return self.default

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        limit = self._limit(scope.get("path", ""))
        for k, v in scope.get("headers", []):
            if k == b"content-length":
                try:
                    if int(v) > limit:
                        await _reject_413(send, limit)
                        return
                except ValueError:
                    await _reject_413(send, limit)
                    return
        seen = 0
        too_big = False

        async def receive_wrapper() -> Message:
            nonlocal seen, too_big
            msg = await receive()
            if msg["type"] == "http.request":
                seen += len(msg.get("body", b""))
                if seen > limit:
                    too_big = True
                    raise _TooLarge()
            return msg

        try:
            await self.app(scope, receive_wrapper, send)
        except _TooLarge:
            await _reject_413(send, limit)


class _TooLarge(Exception):
    pass


async def _reject_413(send: Send, limit: int) -> None:
    body = (b'{"error":"payload_too_large","message":"request body exceeds %d bytes"}' % limit)
    await send({"type": "http.response.start", "status": 413,
                "headers": [(b"content-type", b"application/json"),
                            (b"content-length", str(len(body)).encode())]})
    await send({"type": "http.response.body", "body": body})


class LoginRateLimiter:
    """Sliding-window limiter for login attempts, per client address and per username.

    * at most ``max_failures`` failed logins per username or per address within ``window_s``
      (then 429 until the window passes);
    * at most ``max_attempts`` attempts (failed or not) per address within ``window_s``.
    In-memory: a multi-process deployment needs a shared store (documented gap).
    """

    def __init__(self, max_failures: int = 5, max_attempts: int = 30, window_s: float = 300.0,
                 clock: Callable[[], float] = time.monotonic):
        self.max_failures, self.max_attempts, self.window = max_failures, max_attempts, window_s
        self.clock = clock
        self._fail: dict[str, deque] = defaultdict(deque)
        self._all: dict[str, deque] = defaultdict(deque)
        self._lock = threading.Lock()

    def _prune(self, q: deque, now: float) -> None:
        while q and now - q[0] > self.window:
            q.popleft()

    def check(self, ip: str, username: str) -> bool:
        now = self.clock()
        with self._lock:
            for key, q, lim in ((f"ip:{ip}", self._all, self.max_attempts),
                                (f"ip:{ip}", self._fail, self.max_failures),
                                (f"user:{username.lower()}", self._fail, self.max_failures)):
                d = q[key]
                self._prune(d, now)
                if len(d) >= lim:
                    return False
            self._all[f"ip:{ip}"].append(now)
            return True

    def failure(self, ip: str, username: str) -> None:
        now = self.clock()
        with self._lock:
            self._fail[f"ip:{ip}"].append(now)
            self._fail[f"user:{username.lower()}"].append(now)

    def success(self, ip: str, username: str) -> None:
        with self._lock:
            self._fail.pop(f"user:{username.lower()}", None)


def env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except ValueError:
        return default
