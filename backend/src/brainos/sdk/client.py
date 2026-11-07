"""BrainOS Python SDK.

Two clients:

* :class:`RuntimeClient` — REST control/inspection (devices, connect/switch,
  diagnostics, negotiation dry-runs).
* :class:`EventStream` — the application event stream. Declare required and
  optional capabilities; receive validated, typed envelopes for granted
  capabilities only, plus negotiation/runtime updates.

Example::

    async with await EventStream.connect(
        app_id="my-app", app_name="My App",
        required=["selection"], optional=["pointer_intent"],
    ) as stream:
        async for item in stream:
            if isinstance(item, NegotiationUpdate):
                print("granted:", item.negotiation.granted)
            elif is_event(item):
                print(item.seq, item.event_type, item.payload)
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from types import TracebackType
from typing import Any, Self, TypeGuard

import httpx
import websockets
from pydantic import BaseModel, TypeAdapter, ValidationError
from websockets.asyncio.client import ClientConnection

from brainos.contracts.events import (
    ENVELOPE_ADAPTER,
    SCHEMA_MAJOR,
    EventEnvelope,
)
from brainos.contracts.protocol import (
    STREAM_PROTOCOL,
    DeviceDescriptor,
    NegotiationResult,
    RuntimeSnapshot,
)

DEFAULT_BASE_URL = "http://127.0.0.1:8000"
HANDSHAKE_TIMEOUT_S = 10.0

_DEVICES = TypeAdapter(list[DeviceDescriptor])


class BrainOSError(Exception):
    """Error reported by the runtime (``code`` is a stable machine-readable string)."""

    def __init__(self, code: str, message: str, status: int | None = None) -> None:
        self.code = code
        self.message = message
        self.status = status
        super().__init__(f"{code}: {message}")


class StreamClosedError(BrainOSError):
    pass


# --------------------------------------------------------------------------- REST


class RuntimeClient:
    def __init__(self, base_url: str = DEFAULT_BASE_URL, *, timeout: float = 10.0) -> None:
        self.base_url = base_url.rstrip("/")
        self._http = httpx.AsyncClient(base_url=self.base_url + "/api/v1", timeout=timeout)

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.close()

    async def close(self) -> None:
        await self._http.aclose()

    async def _call(self, method: str, path: str, body: dict[str, Any] | None = None) -> Any:
        resp = await self._http.request(method, path, json=body)
        if resp.status_code >= 400:
            try:
                err = resp.json()["error"]
                raise BrainOSError(err["code"], err["message"], resp.status_code)
            except (ValueError, KeyError, TypeError):
                raise BrainOSError("http_error", resp.text[:300], resp.status_code) from None
        return resp.json()

    async def health(self) -> dict[str, Any]:
        result: dict[str, Any] = await self._call("GET", "/health")
        return result

    async def devices(self) -> list[DeviceDescriptor]:
        return _DEVICES.validate_python(await self._call("GET", "/devices"))

    async def runtime(self) -> RuntimeSnapshot:
        return RuntimeSnapshot.model_validate(await self._call("GET", "/runtime"))

    async def connect(self, device_id: str) -> RuntimeSnapshot:
        data = await self._call("POST", "/runtime/connect", {"device_id": device_id})
        return RuntimeSnapshot.model_validate(data)

    async def switch(self, device_id: str) -> RuntimeSnapshot:
        data = await self._call("POST", "/runtime/switch", {"device_id": device_id})
        return RuntimeSnapshot.model_validate(data)

    async def disconnect(self) -> RuntimeSnapshot:
        return RuntimeSnapshot.model_validate(await self._call("POST", "/runtime/disconnect"))

    async def pause(self) -> RuntimeSnapshot:
        return RuntimeSnapshot.model_validate(await self._call("POST", "/runtime/pause"))

    async def resume(self) -> RuntimeSnapshot:
        return RuntimeSnapshot.model_validate(await self._call("POST", "/runtime/resume"))

    async def diagnostics(self) -> dict[str, Any]:
        result: dict[str, Any] = await self._call("GET", "/diagnostics")
        return result

    async def negotiate(
        self,
        required: list[str],
        optional: list[str] | None = None,
        device_id: str | None = None,
    ) -> NegotiationResult:
        body = {"required": required, "optional": optional or [], "device_id": device_id}
        return NegotiationResult.model_validate(await self._call("POST", "/negotiate", body))


# ------------------------------------------------------------------------- stream


@dataclass(frozen=True, slots=True)
class NegotiationUpdate:
    negotiation: NegotiationResult


@dataclass(frozen=True, slots=True)
class RuntimeUpdate:
    runtime: RuntimeSnapshot


@dataclass(frozen=True, slots=True)
class ServerNotice:
    """A non-fatal error notice from the server (e.g. read_only_runtime)."""

    code: str
    message: str


StreamItem = EventEnvelope | NegotiationUpdate | RuntimeUpdate | ServerNotice


def is_event(item: StreamItem) -> TypeGuard[EventEnvelope]:
    return isinstance(item, BaseModel) and hasattr(item, "event_type")


@dataclass
class StreamStats:
    received: int = 0
    invalid: int = 0
    delivery_gaps: int = 0  # number of gaps in delivery_seq (server-side drops)
    missed_events: int = 0  # total events missed across gaps
    out_of_order: int = 0  # envelope seq not increasing within a session
    _last_delivery: int | None = None
    _last_seq: dict[str, int] = field(default_factory=dict)

    def observe(self, delivery_seq: int, env: EventEnvelope | None) -> None:
        if self._last_delivery is not None and delivery_seq != self._last_delivery + 1:
            self.delivery_gaps += 1
            self.missed_events += max(0, delivery_seq - self._last_delivery - 1)
        self._last_delivery = delivery_seq
        if env is None:
            return
        self.received += 1
        last = self._last_seq.get(env.session_id)
        if last is not None and env.seq <= last:
            self.out_of_order += 1
        self._last_seq[env.session_id] = env.seq


class EventStream:
    def __init__(self, ws: ClientConnection, welcome: dict[str, Any]) -> None:
        self._ws = ws
        self.connection_id: str = welcome["connection_id"]
        self.schema_version: str = welcome["schema_version"]
        self.negotiation = NegotiationResult.model_validate(welcome["negotiation"])
        self.runtime: RuntimeSnapshot = RuntimeSnapshot.model_validate(welcome["runtime"])
        self.stats = StreamStats()

    @classmethod
    async def connect(
        cls,
        *,
        app_id: str,
        app_name: str,
        required: list[str] | None = None,
        optional: list[str] | None = None,
        base_url: str = DEFAULT_BASE_URL,
        kind: str = "sdk",
    ) -> EventStream:
        """Open the stream and negotiate capabilities.

        Raises :class:`BrainOSError` with code ``unknown_capability`` if a
        requested capability is not in the vocabulary.
        """
        url = base_url.replace("http://", "ws://").replace("https://", "wss://").rstrip("/")
        ws = await websockets.connect(url + "/api/v1/stream", max_size=8 * 1024 * 1024)
        hello = {
            "type": "hello",
            "protocol": STREAM_PROTOCOL,
            "app": {"id": app_id, "name": app_name, "kind": kind},
            "capabilities": {"required": required or [], "optional": optional or []},
        }
        try:
            await ws.send(json.dumps(hello))
            first = json.loads(await asyncio.wait_for(ws.recv(), HANDSHAKE_TIMEOUT_S))
            if not isinstance(first, dict):
                raise ValueError("welcome is not an object")
        except websockets.ConnectionClosed as exc:
            raise StreamClosedError("closed", f"server closed during handshake: {exc}") from exc
        except (TimeoutError, ValueError) as exc:
            await ws.close()
            raise BrainOSError("protocol_error", f"handshake failed: {exc!r}") from exc
        if first.get("type") == "error":
            await ws.close()
            raise BrainOSError(first["code"], first["message"])
        if first.get("type") != "welcome":
            await ws.close()
            raise BrainOSError("protocol_error", f"expected welcome, got {first.get('type')}")
        try:
            major = int(str(first["schema_version"]).split(".")[0])
            stream = cls(ws, first)
        except (KeyError, ValueError) as exc:
            await ws.close()
            raise BrainOSError("protocol_error", f"malformed welcome: {exc!r}") from exc
        if major != SCHEMA_MAJOR:
            await ws.close()
            raise BrainOSError("unsupported_schema", f"server schema {first['schema_version']}")
        return stream

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        await self.close()

    async def close(self) -> None:
        await self._ws.close()

    async def ping(self, nonce: str = "") -> None:
        await self._ws.send(json.dumps({"type": "ping", "nonce": nonce}))

    async def send_raw(self, message: dict[str, Any]) -> None:
        """Send an arbitrary message (testing only; the runtime is read-only)."""
        await self._ws.send(json.dumps(message))

    def __aiter__(self) -> AsyncIterator[StreamItem]:
        return self._iterate()

    async def _iterate(self) -> AsyncIterator[StreamItem]:
        while True:
            try:
                raw = await self._ws.recv()
            except websockets.ConnectionClosedOK:
                return
            except websockets.ConnectionClosed as exc:
                raise StreamClosedError("closed", str(exc)) from exc
            item = self._decode(raw)
            if item is not None:
                yield item

    async def events(self) -> AsyncIterator[EventEnvelope]:
        """Iterate only events (negotiation/runtime updates still update attributes)."""
        async for item in self:
            if is_event(item):
                yield item

    def _decode(self, raw: str | bytes) -> StreamItem | None:
        msg = json.loads(raw)
        mtype = msg.get("type")
        if mtype == "event":
            try:
                env = ENVELOPE_ADAPTER.validate_python(msg["event"])
            except ValidationError:
                # never hand an app an event that violates the contract
                self.stats.invalid += 1
                self.stats.observe(int(msg["delivery_seq"]), None)
                return None
            self.stats.observe(int(msg["delivery_seq"]), env)
            return env
        if mtype == "negotiation":
            self.negotiation = NegotiationResult.model_validate(msg["negotiation"])
            return NegotiationUpdate(self.negotiation)
        if mtype == "runtime":
            self.runtime = RuntimeSnapshot.model_validate(msg["runtime"])
            return RuntimeUpdate(self.runtime)
        if mtype == "error":
            return ServerNotice(str(msg.get("code")), str(msg.get("message")))
        return None  # pong and future message types are ignored
