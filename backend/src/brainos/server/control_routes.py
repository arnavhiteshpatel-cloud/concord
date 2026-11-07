"""REST for the control bridge (/api/v1/control): operator authorization of applications for
decoded commands, and the command-output stop.

Operator endpoints on a localhost-only server. Applications never call them: an application
declares the command capabilities it needs and waits (negotiation reason ``not_authorized``)
until the operator authorizes it here. Nothing here sends anything to a device.
"""

from __future__ import annotations

import re
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field

from brainos.contracts.capabilities import Capability, UnknownCapabilityError, parse_capabilities
from brainos.contracts.protocol import AppStatus, ErrorCode, RejectionReason
from brainos.runtime import Runtime, RuntimeCommandError
from brainos.runtime.control import COMMAND_CAPABILITIES, ControlEvent
from brainos.runtime.pipeline import RouterEvent, RouterSpec
from brainos.server.deps import AppServices, services

router = APIRouter(prefix="/api/v1/control")
Svc = Annotated[AppServices, Depends(services)]
APP_ID = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_.\-]{0,63}$")


class _Body(BaseModel):
    model_config = ConfigDict(extra="forbid")


class AuthorizeRequest(_Body):
    capabilities: list[str] = Field(min_length=1, max_length=4)


class RevokeRequest(_Body):
    capabilities: list[str] | None = Field(default=None, max_length=4)


class StopRequest(_Body):
    reason: str | None = Field(default=None, max_length=200)


class Waiting(BaseModel):
    capability: Capability
    reason: RejectionReason
    required: bool


class AppControl(BaseModel):
    """One application id that asks for command capabilities (or holds an authorization)."""

    app_id: str
    name: str | None
    kind: str | None  # application | console | sdk (self-declared); None = offline
    connections: int
    status: AppStatus | None  # negotiation status of its (first) connection; None = offline
    requested: list[Capability]  # command capabilities it asks for (required or optional)
    required: list[Capability]
    authorized: list[Capability]
    authorized_at_ns: int | None
    receiving: list[Capability]  # command capabilities currently granted to it
    waiting: list[Waiting]  # requested command capabilities not granted, with the reason
    refused_commands: int  # decoded commands not delivered because it was not authorized
    # schema 1.4: what its last control.state said (None: it did not ask for control_status,
    # or no session has started since it connected)
    control_active: bool | None = None
    control_reason: str | None = None


class ControlStatus(BaseModel):
    router_on: bool
    model_id: str | None
    provides: list[Capability]  # command capabilities the router currently provides
    router: RouterSpec | None
    stall_limit_ms: float | None
    last_stop: RouterEvent | None
    apps: list[AppControl]
    history: list[ControlEvent]


def _caps(names: list[str]) -> list[Capability]:
    try:
        caps = parse_capabilities(names)
    except UnknownCapabilityError as exc:
        raise RuntimeCommandError(ErrorCode.UNKNOWN_CAPABILITY, str(exc)) from None
    bad = [c for c in caps if c not in COMMAND_CAPABILITIES]
    if bad:
        raise RuntimeCommandError(
            ErrorCode.PROTOCOL_ERROR,
            f"only command capabilities ({', '.join(sorted(COMMAND_CAPABILITIES))}) need "
            f"authorization; got {', '.join(bad)}",
        )
    return caps


def _app_id(app_id: str) -> str:
    if not APP_ID.match(app_id):
        raise RuntimeCommandError(ErrorCode.PROTOCOL_ERROR, f"invalid application id {app_id!r}")
    return app_id


def control_status(rt: Runtime) -> ControlStatus:
    pl = rt.pipeline
    st = pl.status()
    apps: dict[str, AppControl] = {}
    for sub in rt.command_requests():
        requested = [c for c in (*sub.required, *sub.optional) if c in COMMAND_CAPABILITIES]
        entry = apps.get(sub.app.id)
        if entry is None:
            grant = rt.authorizations.grants().get(sub.app.id)
            entry = apps[sub.app.id] = AppControl(
                app_id=sub.app.id,
                name=sub.app.name,
                kind=sub.app.kind,
                connections=0,
                status=sub.negotiation.status,
                requested=list(dict.fromkeys(requested)),
                required=[c for c in sub.required if c in COMMAND_CAPABILITIES],
                authorized=sorted(grant.capabilities) if grant else [],
                authorized_at_ns=grant.granted_at_ns if grant else None,
                receiving=[c for c in sub.negotiation.granted if c in COMMAND_CAPABILITIES],
                waiting=[
                    Waiting(capability=r.capability, reason=r.reason, required=r.required)
                    for r in sub.negotiation.rejected
                    if r.capability in COMMAND_CAPABILITIES
                ],
                refused_commands=0,
                control_active=sub.control_state[1] if sub.control_state else None,
                control_reason=sub.control_reason or None,
            )
        entry.connections += 1
        entry.refused_commands += sub.refused_commands
    for app_id, grant in rt.authorizations.grants().items():
        if app_id not in apps:  # authorized, not connected now
            apps[app_id] = AppControl(
                app_id=app_id,
                name=None,
                kind=None,
                connections=0,
                status=None,
                requested=[],
                required=[],
                authorized=sorted(grant.capabilities),
                authorized_at_ns=grant.granted_at_ns,
                receiving=[],
                waiting=[],
                refused_commands=0,
            )
    history = [
        *rt.authorizations.history,
        *(
            ControlEvent(at_ns=e.at_ns, kind="router_on" if e.on else "router_off", detail=e.reason)
            for e in pl.router_log
        ),
    ]
    history.sort(key=lambda e: e.at_ns)
    return ControlStatus(
        router_on=pl.router_on,
        model_id=st.decoder["model_id"] if st.decoder else None,
        provides=st.router_capabilities,
        router=st.router,
        stall_limit_ms=st.stall_limit_ms,
        last_stop=st.last_router_stop,
        apps=sorted(apps.values(), key=lambda a: a.app_id),
        history=history[-50:],
    )


@router.get("")
async def get_control(svc: Svc) -> ControlStatus:
    return control_status(svc.runtime)


@router.post("/apps/{app_id}/authorize")
async def authorize(app_id: str, body: AuthorizeRequest, svc: Svc) -> ControlStatus:
    svc.runtime.authorize_app(_app_id(app_id), _caps(body.capabilities))
    return control_status(svc.runtime)


@router.post("/apps/{app_id}/revoke")
async def revoke(app_id: str, svc: Svc, body: RevokeRequest | None = None) -> ControlStatus:
    caps = _caps(body.capabilities) if body is not None and body.capabilities else None
    svc.runtime.revoke_app(_app_id(app_id), caps)
    return control_status(svc.runtime)


@router.post("/stop")
async def stop(svc: Svc, body: StopRequest | None = None) -> ControlStatus:
    reason = (body.reason if body and body.reason else None) or "stopped by operator"
    svc.runtime.stop_control(reason)
    return control_status(svc.runtime)
