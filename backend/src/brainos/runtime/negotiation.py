"""Capability negotiation (pure)."""

from __future__ import annotations

from brainos.contracts.capabilities import Capability
from brainos.contracts.protocol import (
    AppStatus,
    CapabilityRejection,
    DeviceDescriptor,
    NegotiationResult,
    RejectionReason,
)


def negotiate(
    required: list[Capability],
    optional: list[Capability],
    device: DeviceDescriptor | None,
) -> NegotiationResult:
    """Grant or explicitly reject each requested capability against ``device``.

    A capability listed as both required and optional is treated as required.
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

    supported = device.capability_set
    for cap in (*req, *opt):
        if cap in supported:
            granted.append(cap)
        else:
            rejected.append(
                CapabilityRejection(
                    capability=cap,
                    reason=RejectionReason.UNSUPPORTED_BY_DEVICE,
                    required=cap in req,
                )
            )
    status = AppStatus.SUSPENDED if any(r.required for r in rejected) else AppStatus.ACTIVE
    if status is AppStatus.SUSPENDED:
        granted = []  # a suspended app receives no events
    return NegotiationResult(
        device_id=device.device_id, status=status, granted=granted, rejected=rejected
    )
