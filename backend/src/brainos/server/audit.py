"""Operator actions -> the active research session's log (ASGI middleware).

Every state-changing API call made while a research session is active is recorded with its
outcome. For the calls that determine what a session computed (source, pipeline, router,
recording, calibration, authorization) the structured configuration is recorded too, so an
export can say exactly what was run. Free text (stop reasons, simulated text) and data
(simulated pointer moves) are not recorded. The application log is not involved.
"""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from starlette.types import ASGIApp, Message, Receive, Scope, Send

log = logging.getLogger(__name__)

MAX_BODY = 512 * 1024
Extract = Callable[[dict[str, Any], dict[str, Any], re.Match[str]], dict[str, Any]]


def _keys(d: dict[str, Any], *keys: str) -> dict[str, Any]:
    return {k: d[k] for k in keys if k in d}


def _device(resp: dict[str, Any]) -> dict[str, Any]:
    dev = resp.get("device") if "device" in resp else None
    out: dict[str, Any] = {}
    if isinstance(dev, dict):
        out["device"] = dev
    if resp.get("session_id"):
        out["runtime_session"] = resp["session_id"]
    return out


def _descriptor(resp: dict[str, Any]) -> dict[str, Any]:
    return {"device": resp} if resp.get("device_id") else {}


PIPELINE_KEYS = (
    "device_id",
    "session_id",
    "preset",
    "stages",
    "input_event_type",
    "output",
    "decoder",
    "compatibility_warnings",
    "cross_source_override",
    "router",
    "router_capabilities",
    "started_at_ns",
)


@dataclass(frozen=True)
class Rule:
    method: str
    pattern: re.Pattern[str]
    action: str
    extract: Extract | None = None
    kind: str = "operator_action"


def _rule(
    method: str,
    path: str,
    action: str,
    extract: Extract | None = None,
    kind: str = "operator_action",
) -> Rule:
    return Rule(method, re.compile(f"^/api/v1{path}$"), action, extract, kind)


RULES: list[Rule] = [
    _rule(
        "POST",
        "/runtime/connect",
        "connect",
        lambda q, r, m: {**_keys(q, "device_id"), **_device(r)},
    ),
    _rule(
        "POST", "/runtime/switch", "switch", lambda q, r, m: {**_keys(q, "device_id"), **_device(r)}
    ),
    _rule("POST", "/runtime/disconnect", "disconnect"),
    _rule("POST", "/runtime/pause", "pause"),
    _rule("POST", "/runtime/resume", "resume"),
    _rule("POST", "/runtime/playback", "playback_speed", lambda q, r, m: _keys(q, "speed")),
    _rule(
        "POST",
        "/pipeline/start",
        "pipeline_start",
        lambda q, r, m: {"request": q, "pipeline": _keys(r, *PIPELINE_KEYS)},
    ),
    _rule("POST", "/pipeline/stop", "pipeline_stop"),
    _rule("POST", "/pipeline/router", "router", lambda q, r, m: {"router": q}),
    _rule(
        "POST",
        "/recordings/start",
        "recording_start",
        lambda q, r, m: {**_keys(q, "name", "exclude_raw"), **_keys(r, "name")},
    ),
    _rule(
        "POST",
        "/recordings/stop",
        "recording_stop",
        lambda q, r, m: _keys(r, "name", "events", "size_bytes"),
    ),
    _rule(
        "POST",
        "/calibration/train",
        "calibration",
        lambda q, r, m: {
            "request": q,
            "model_id": (r.get("model") or {}).get("model_id"),
            "model": r.get("model"),
            "report": r.get("report"),
        },
        kind="calibration",
    ),
    _rule("POST", "/sources/lsl", "register_lsl", lambda q, r, m: {"request": q, **_descriptor(r)}),
    _rule("POST", "/sources/lsl/discover", "discover_lsl"),
    _rule(
        "POST",
        "/sources/openephys",
        "register_openephys",
        lambda q, r, m: {"request": q, **_descriptor(r)},
    ),
    _rule(
        "DELETE", "/sources/(?P<id>[^/]+)", "remove_source", lambda q, r, m: {"device_id": m["id"]}
    ),
    _rule("POST", "/plugins/discover", "discover_plugins"),
    _rule(
        "POST",
        "/plugins/(?P<name>[^/]+)/configure",
        "configure_plugin",
        lambda q, r, m: {"plugin": m["name"], "request": q, **_descriptor(r)},
    ),
    _rule(
        "POST",
        "/control/apps/(?P<app>[^/]+)/authorize",
        "authorize_app",
        lambda q, r, m: {"app_id": m["app"], **_keys(q, "capabilities")},
    ),
    _rule(
        "POST",
        "/control/apps/(?P<app>[^/]+)/revoke",
        "revoke_app",
        lambda q, r, m: {"app_id": m["app"], **_keys(q, "capabilities")},
    ),
    _rule("POST", "/control/stop", "stop_control"),  # the free-text reason is not recorded
    _rule("POST", "/sim/faults", "inject_fault", lambda q, r, m: _keys(q, "fault")),
    _rule(
        "DELETE",
        "/recordings/(?P<name>[^/]+)",
        "delete_recording",
        lambda q, r, m: {"recording": m["name"]},
    ),
    _rule("DELETE", "/models/(?P<id>[^/]+)", "delete_model", lambda q, r, m: {"model_id": m["id"]}),
]
# not recorded: dry runs, high-rate simulated intents, and endpoints that log themselves
SKIP = re.compile(r"^/api/v1/(negotiate|sim/(pointer|select|text)|sessions|safe-stop|system/)")


def _json(data: bytes) -> dict[str, Any]:
    if not data:
        return {}
    try:
        obj = json.loads(data)
    except ValueError:
        return {}
    return obj if isinstance(obj, dict) else {"value": obj}


class SessionAuditMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope["method"] not in ("POST", "PUT", "PATCH", "DELETE"):
            await self.app(scope, receive, send)
            return
        path: str = scope.get("path", "")
        app = scope.get("app")
        services = getattr(getattr(app, "state", None), "services", None)
        sessions = getattr(services, "sessions", None)
        if (
            sessions is None
            or sessions.active is None
            or not path.startswith("/api/v1/")
            or SKIP.match(path)
        ):
            await self.app(scope, receive, send)
            return
        rule = next(
            (r for r in RULES if r.method == scope["method"] and r.pattern.match(path)), None
        )
        match = rule.pattern.match(path) if rule else None
        req_body = bytearray()
        resp_body = bytearray()
        status = 0

        async def recv() -> Message:
            msg = await receive()
            if rule is not None and msg["type"] == "http.request" and len(req_body) < MAX_BODY:
                req_body.extend(msg.get("body", b""))
            return msg

        async def snd(msg: Message) -> None:
            nonlocal status
            if msg["type"] == "http.response.start":
                status = int(msg["status"])
            elif (
                rule is not None
                and msg["type"] == "http.response.body"
                and len(resp_body) < MAX_BODY
            ):
                resp_body.extend(msg.get("body", b""))
            await send(msg)

        try:
            await self.app(scope, recv, snd)
        finally:
            try:
                self._record(
                    sessions,
                    scope["method"],
                    path,
                    status,
                    rule,
                    match,
                    bytes(req_body),
                    bytes(resp_body),
                )
            except Exception:  # the session log must never break the API
                log.exception("could not record operator action %s %s", scope["method"], path)

    @staticmethod
    def _record(
        sessions: Any,
        method: str,
        path: str,
        status: int,
        rule: Rule | None,
        match: re.Match[str] | None,
        req: bytes,
        resp: bytes,
    ) -> None:
        if sessions.active is None:
            return
        entry: dict[str, Any] = {"method": method, "path": path, "status": status}
        kind = "operator_action"
        if rule is not None and match is not None:
            kind = rule.kind
            entry["action"] = rule.action
            rq, rs = _json(bytes(req)), _json(bytes(resp))
            if 200 <= status < 300:
                if rule.extract is not None:
                    entry.update(rule.extract(rq, rs, match))
                model_id = entry.get("model_id") or (entry.get("request") or {}).get("model_id")
                if model_id and rule.action in ("calibration", "pipeline_start"):
                    sessions.add_model(str(model_id))
            else:
                err = rs.get("error")
                if isinstance(err, dict):
                    entry["error"] = {
                        "code": str(err.get("code")),
                        "message": str(err.get("message"))[:300],
                    }
        sessions.record(kind, **entry)
