"""Simulation-only operator endpoints (/api/v1/sim).

These feed the *simulated intention source* and inject faults into simulated
devices. They are an operator/test tool, not part of the application API, and
they are disabled with CONCORD_ENABLE_SIM=0. Intents a profile does not
support are rejected explicitly (409 capability_unsupported).
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field

from concord.adapters.simulated import Fault, SimulatedAdapter
from concord.contracts.capabilities import Capability
from concord.contracts.protocol import ErrorCode, RuntimeState
from concord.runtime import RuntimeCommandError
from concord.server.deps import AppServices, services

router = APIRouter(prefix="/api/v1/sim")
Svc = Annotated[AppServices, Depends(services)]


class _Body(BaseModel):
    model_config = ConfigDict(extra="forbid")


class PointerBody(_Body):
    vx: float = Field(ge=-1, le=1, allow_inf_nan=False)
    vy: float = Field(ge=-1, le=1, allow_inf_nan=False)


class TextBody(_Body):
    text: str = Field(min_length=1, max_length=32)


class FaultBody(_Body):
    fault: Fault


class Accepted(BaseModel):
    accepted: bool = True
    device_id: str


class SimStatus(BaseModel):
    enabled: bool
    device_id: str | None
    simulated: bool
    accepts: list[Capability]
    faults: list[Fault]


def _sim_adapter(svc: AppServices, *, streaming: bool) -> SimulatedAdapter:
    if not svc.settings.enable_sim:
        raise RuntimeCommandError(ErrorCode.SIMULATION_DISABLED, "simulation endpoints disabled")
    adapter = svc.runtime.adapter
    if not isinstance(adapter, SimulatedAdapter):
        raise RuntimeCommandError(
            ErrorCode.INVALID_STATE,
            "no simulated device is connected (replay and idle not accepted)",
        )
    if streaming and svc.runtime.state is not RuntimeState.STREAMING:
        raise RuntimeCommandError(
            ErrorCode.INVALID_STATE, f"runtime is {svc.runtime.state}; intents need streaming"
        )
    return adapter


def _require(adapter: SimulatedAdapter, cap: Capability) -> None:
    if not adapter.descriptor.supports(cap):
        raise RuntimeCommandError(
            ErrorCode.CAPABILITY_UNSUPPORTED,
            f"{adapter.descriptor.display_name} does not support {cap.value}",
        )


@router.get("")
async def sim_status(svc: Svc) -> SimStatus:
    adapter = svc.runtime.adapter
    sim = isinstance(adapter, SimulatedAdapter)
    accepts = (
        [
            c
            for c in (Capability.POINTER_INTENT, Capability.SELECTION, Capability.TEXT_INTENT)
            if adapter.descriptor.supports(c)
        ]
        if sim and adapter is not None
        else []
    )
    return SimStatus(
        enabled=svc.settings.enable_sim,
        device_id=adapter.device_id if adapter else None,
        simulated=sim,
        accepts=accepts,
        faults=list(Fault),
    )


@router.post("/pointer")
async def sim_pointer(body: PointerBody, svc: Svc) -> Accepted:
    adapter = _sim_adapter(svc, streaming=True)
    _require(adapter, Capability.POINTER_INTENT)
    svc.intents.set_pointer(body.vx, body.vy)
    return Accepted(device_id=adapter.device_id)


@router.post("/select")
async def sim_select(svc: Svc) -> Accepted:
    adapter = _sim_adapter(svc, streaming=True)
    _require(adapter, Capability.SELECTION)
    svc.intents.submit_select()
    return Accepted(device_id=adapter.device_id)


@router.post("/text")
async def sim_text(body: TextBody, svc: Svc) -> Accepted:
    adapter = _sim_adapter(svc, streaming=True)
    _require(adapter, Capability.TEXT_INTENT)
    svc.intents.submit_text(body.text)
    return Accepted(device_id=adapter.device_id)


@router.post("/faults")
async def sim_fault(body: FaultBody, svc: Svc) -> Accepted:
    adapter = _sim_adapter(svc, streaming=False)
    adapter.inject_fault(body.fault)
    return Accepted(device_id=adapter.device_id)
