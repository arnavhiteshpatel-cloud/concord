"""WebSocket event stream: protocol brainos.stream/1 (see ARCHITECTURE.md §7)."""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import time

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import ValidationError
from starlette.websockets import WebSocketState

from brainos.contracts.capabilities import UnknownCapabilityError, parse_capabilities
from brainos.contracts.events import SCHEMA_VERSION
from brainos.contracts.protocol import STREAM_PROTOCOL, ErrorCode, Hello
from brainos.runtime import Runtime, Subscriber
from brainos.server.deps import AppServices

log = logging.getLogger(__name__)
router = APIRouter()

HELLO_TIMEOUT_S = 10.0
MAX_CLIENT_MESSAGE = 16 * 1024
POLICY_VIOLATION = 1008


def _error(code: ErrorCode, message: str) -> str:
    return json.dumps({"type": "error", "code": code.value, "message": message})


async def _reject(ws: WebSocket, code: ErrorCode, message: str) -> None:
    log.info("stream rejected: %s: %s", code, message)
    with contextlib.suppress(Exception):
        await ws.send_text(_error(code, message))
        await ws.close(code=POLICY_VIOLATION, reason=code.value)


async def _handshake(ws: WebSocket, runtime: Runtime) -> Subscriber | None:
    try:
        raw = await asyncio.wait_for(ws.receive_text(), HELLO_TIMEOUT_S)
    except TimeoutError:
        await _reject(ws, ErrorCode.HELLO_REQUIRED, "no hello within timeout")
        return None
    if len(raw) > MAX_CLIENT_MESSAGE:
        await _reject(ws, ErrorCode.PROTOCOL_ERROR, "message too large")
        return None
    try:
        msg = json.loads(raw)
    except ValueError:
        await _reject(ws, ErrorCode.PROTOCOL_ERROR, "message is not valid JSON")
        return None
    if not isinstance(msg, dict) or msg.get("type") != "hello":
        await _reject(ws, ErrorCode.HELLO_REQUIRED, "first message must be a hello")
        return None
    try:
        hello = Hello.model_validate(msg)
    except ValidationError as exc:
        await _reject(ws, ErrorCode.PROTOCOL_ERROR, f"invalid hello: {exc.errors()[0]['msg']}")
        return None
    if hello.protocol != STREAM_PROTOCOL:
        await _reject(
            ws,
            ErrorCode.UNSUPPORTED_PROTOCOL,
            f"server speaks {STREAM_PROTOCOL}, got {hello.protocol}",
        )
        return None
    try:
        required = parse_capabilities(hello.capabilities.required)
        optional = parse_capabilities(hello.capabilities.optional)
    except UnknownCapabilityError as exc:
        await _reject(ws, ErrorCode.UNKNOWN_CAPABILITY, str(exc))
        return None
    sub = runtime.register_app(hello.app, required, optional)
    welcome = {
        "type": "welcome",
        "protocol": STREAM_PROTOCOL,
        "schema_version": SCHEMA_VERSION,
        "connection_id": sub.connection_id,
        "negotiation": sub.negotiation.model_dump(mode="json"),
        "runtime": runtime.snapshot().model_dump(mode="json"),
    }
    await ws.send_text(json.dumps(welcome))
    return sub


async def _sender(ws: WebSocket, sub: Subscriber, runtime: Runtime) -> None:
    diag = runtime.diagnostics
    while True:
        frame, enqueued_ns = await sub.next_message()
        await ws.send_text(frame)
        if enqueued_ns is not None:
            diag.record_delivery(time.monotonic_ns() - enqueued_ns)


async def _receiver(ws: WebSocket, sub: Subscriber) -> None:
    while True:
        raw = await ws.receive_text()
        if len(raw) > MAX_CLIENT_MESSAGE:
            sub.offer_control(_error(ErrorCode.PROTOCOL_ERROR, "message too large"))
            continue
        try:
            msg = json.loads(raw)
        except ValueError:
            sub.offer_control(_error(ErrorCode.PROTOCOL_ERROR, "message is not valid JSON"))
            continue
        mtype = msg.get("type") if isinstance(msg, dict) else None
        if mtype == "ping":
            nonce = msg.get("nonce") if isinstance(msg, dict) else None
            pong = {"type": "pong", "nonce": nonce, "server_ns": time.time_ns()}
            sub.offer_control(json.dumps(pong))
        elif mtype == "hello":
            sub.offer_control(_error(ErrorCode.PROTOCOL_ERROR, "hello already completed"))
        else:
            sub.offer_control(
                _error(
                    ErrorCode.READ_ONLY_RUNTIME,
                    f"message type {mtype!r} not accepted: the v1 runtime is read-only",
                )
            )


@router.websocket("/api/v1/stream")
async def stream(ws: WebSocket) -> None:
    svc: AppServices = ws.app.state.services
    runtime = svc.runtime
    await ws.accept()
    try:
        sub = await _handshake(ws, runtime)
    except WebSocketDisconnect:
        return
    if sub is None:
        return
    sender = asyncio.create_task(_sender(ws, sub, runtime), name=f"ws-send:{sub.connection_id}")
    receiver = asyncio.create_task(_receiver(ws, sub), name=f"ws-recv:{sub.connection_id}")
    try:
        done, _ = await asyncio.wait({sender, receiver}, return_when=asyncio.FIRST_COMPLETED)
        for task in done:
            exc = task.exception()
            if exc is not None and not isinstance(exc, WebSocketDisconnect | RuntimeError):
                log.warning("stream %s ended with %r", sub.connection_id, exc)
    finally:
        for task in (sender, receiver):
            task.cancel()
        for task in (sender, receiver):
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await task
        runtime.unregister_app(sub.connection_id)
        if ws.client_state is WebSocketState.CONNECTED:
            with contextlib.suppress(Exception):
                await ws.close()
