"""Capability negotiation (pure)."""

from __future__ import annotations

from concord.contracts.capabilities import Capability
from concord.contracts.protocol import (
    AppStatus,
    CapabilityRejection,
    DeviceDescriptor,
    NegotiationResult,
    RejectionReason,
)

# Provided by the runtime itself (not by a device) whenever a device is connected:
# ``control.state`` notices (schema 1.4) are produced per application by the runtime.
RUNTIME_CAPABILITIES: frozenset[Capability] = frozenset({Capability.CONTROL_STATUS})


def negotiate(
    required: list[Capability],
    optional: list[Capability],
    device: DeviceDescriptor | None,
    *,
    decoded_commands: frozenset[Capability] = frozenset(),
    authorized: frozenset[Capability] = frozenset(),
) -> NegotiationResult:
    """Grant or explicitly reject each requested capability against ``device``.

    A capability listed as both required and optional is treated as required.

    ``decoded_commands``: command capabilities the device (as negotiated) provides *only*
    through the command router, i.e. from a decoder. Those are granted only if the operator
    authorized the application for them (``authorized``); otherwise they are rejected with
    ``not_authorized`` (default deny). Capabilities the source provides natively (e.g. a
    simulator's ``simulated_intent``) are unaffected.

    ``control_status`` (:data:`RUNTIME_CAPABILITIES`) is granted whenever a device is
    connected: the runtime, not the device, produces ``control.state``.
    """
    req = list(dict.fromkeys(required))
    opt = [c for c in dict.fromkeys(optional) if c not in req]
    granted: list[Capability] = []
    rejected: list[CapabilityRejection] = []

    if device is None:
        rejected = [
            CapabilityRejection(capability=c, reason=RejectionReason.NO_DEVICE, required=c in req)
            for c in (*req, *opt)
        ]
        return NegotiationResult(
            device_id=None, status=AppStatus.NO_DEVICE, granted=[], rejected=rejected
        )

    supported = device.capability_set | RUNTIME_CAPABILITIES
    for cap in (*req, *opt):
        if cap not in supported:
            reason = RejectionReason.UNSUPPORTED_BY_DEVICE
        elif cap in decoded_commands and cap not in authorized:
            reason = RejectionReason.NOT_AUTHORIZED
        else:
            granted.append(cap)
            continue
        rejected.append(CapabilityRejection(capability=cap, reason=reason, required=cap in req))
    status = AppStatus.SUSPENDED if any(r.required for r in rejected) else AppStatus.ACTIVE
    if status is AppStatus.SUSPENDED:
        granted = []  # a suspended app receives no events
    return NegotiationResult(
        device_id=device.device_id, status=status, granted=granted, rejected=rejected
    )
