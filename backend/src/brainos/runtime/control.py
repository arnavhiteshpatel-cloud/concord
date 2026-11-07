"""Operator authorization of applications for decoded commands (Milestone 4, control bridge).

Default deny: a decoded command (``intent.pointer`` / ``intent.selection`` / ``intent.text``
with provenance ``decoded_intent``, produced only by the command router) reaches an
application only while the operator has authorized that application id for that capability.

The store is in memory only: it is empty after every runtime start, survives source switches
(the router itself is always off after a source change, see ``runtime.py``) and is changed
only through the operator REST API (``/api/v1/control``). Application ids are self-declared
by clients; on the localhost-only research runtime this is an operator safeguard against
mistakes, not authentication (LIMITATIONS.md).
"""

from __future__ import annotations

import logging
import time
from collections import deque
from dataclasses import dataclass, field

from pydantic import BaseModel

from brainos.contracts.capabilities import Capability
from brainos.contracts.events import EventEnvelope, ProvenanceKind

log = logging.getLogger(__name__)

# Capabilities whose events an application acts on (commands). Only these need authorization.
COMMAND_CAPABILITIES: frozenset[Capability] = frozenset(
    {Capability.POINTER_INTENT, Capability.SELECTION, Capability.TEXT_INTENT}
)
HISTORY = 100


def is_decoded_command(envelope: EventEnvelope, capability: Capability) -> bool:
    """A command event produced from a decoder (the only kind that needs authorization)."""
    return (
        capability in COMMAND_CAPABILITIES
        and envelope.provenance.kind is ProvenanceKind.DECODED_INTENT
    )


class ControlEvent(BaseModel):
    at_ns: int
    kind: str  # authorized | revoked | router_on | router_off
    app_id: str | None = None
    capabilities: list[Capability] = []
    detail: str = ""


@dataclass
class Grant:
    capabilities: frozenset[Capability]
    granted_at_ns: int = field(default_factory=time.time_ns)


class AuthorizationStore:
    """app id -> authorized command capabilities. Pure bookkeeping; the runtime applies it."""

    def __init__(self) -> None:
        self._grants: dict[str, Grant] = {}
        self.history: deque[ControlEvent] = deque(maxlen=HISTORY)

    def authorized(self, app_id: str) -> frozenset[Capability]:
        g = self._grants.get(app_id)
        return g.capabilities if g else frozenset()

    def grants(self) -> dict[str, Grant]:
        return dict(self._grants)

    def authorize(self, app_id: str, capabilities: frozenset[Capability]) -> Grant:
        bad = capabilities - COMMAND_CAPABILITIES
        if bad:
            raise ValueError(f"only command capabilities need authorization ({sorted(bad)} given)")
        if not capabilities:
            raise ValueError("no capabilities given")
        old = self._grants.get(app_id)
        caps = capabilities | (old.capabilities if old else frozenset())
        grant = Grant(caps)
        self._grants[app_id] = grant
        self.history.append(
            ControlEvent(
                at_ns=grant.granted_at_ns,
                kind="authorized",
                app_id=app_id,
                capabilities=sorted(capabilities),
            )
        )
        log.info("operator authorized %s for %s", app_id, sorted(capabilities))
        return grant

    def revoke(
        self, app_id: str, capabilities: frozenset[Capability] | None = None
    ) -> frozenset[Capability]:
        """Remove some (or all) of an app's authorizations; returns what was removed."""
        old = self._grants.get(app_id)
        if old is None:
            return frozenset()
        removed = old.capabilities if capabilities is None else old.capabilities & capabilities
        left = old.capabilities - removed
        if left:
            self._grants[app_id] = Grant(left, old.granted_at_ns)
        else:
            del self._grants[app_id]
        if removed:
            self.history.append(
                ControlEvent(
                    at_ns=time.time_ns(),
                    kind="revoked",
                    app_id=app_id,
                    capabilities=sorted(removed),
                )
            )
            log.info("operator revoked %s for %s", app_id, sorted(removed))
        return removed
