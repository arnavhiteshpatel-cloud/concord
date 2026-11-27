"""Roles and the least-privilege permission matrix.

Two layers decide every access:

1. **Role permission** (this matrix): may this role perform this kind of action at all?
2. **Record scope** (enforced in the services): the record must belong to the actor's
   organization (tenant), and additionally

   * ``participant``: only their own participant record;
   * ``care_partner``: only participants they are linked to;
   * ``coordinator`` / ``investigator``: only participants at sites they are assigned to;
   * ``sponsor_analyst``: never participant-level records; aggregates and pseudonymous
     exports only, restricted to participants who consented to ``sharing_with_sponsor``;
   * ``admin``: system administration (users, sites, backups, retention, audit verification);
     no participant-level clinical data and never the re-identification table.

The re-identification table is never visible to sponsor roles (no ``reid.read`` for
``sponsor_analyst``), and is site-scoped for site staff.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .errors import PermissionDenied

ROLES = ("participant", "care_partner", "coordinator", "investigator", "sponsor_analyst",
         "admin")
SITE_STAFF = frozenset({"coordinator", "investigator"})

P, CP, CO, IN, SA, AD = ROLES

PERMISSIONS: dict[str, frozenset[str]] = {
    # administration
    "user.manage": frozenset({AD}),
    "site.manage": frozenset({AD}),
    "sponsor.manage": frozenset({AD}),
    "backup.run": frozenset({AD}),
    "retention.manage": frozenset({AD, IN}),
    "retention.run": frozenset({AD}),
    "integrity.check": frozenset({AD, IN}),
    # studies
    "study.create": frozenset({AD, IN}),
    "study.read": frozenset({CO, IN, SA, AD}),
    "study.update": frozenset({IN, AD}),
    "protocol.manage": frozenset({IN}),
    "schedule.manage": frozenset({IN}),
    # participants
    "participant.create": frozenset({CO, IN}),
    "participant.read": frozenset({P, CP, CO, IN}),
    "enrollment.transition": frozenset({CO, IN}),
    "reid.write": frozenset({CO, IN}),
    "reid.read": frozenset({CO, IN}),
    "consent.record": frozenset({CO, IN}),
    "consent.read": frozenset({P, CP, CO, IN}),
    "consent.withdraw": frozenset({P, CO, IN}),
    "visit.manage": frozenset({CO, IN}),
    "visit.read": frozenset({P, CP, CO, IN}),
    "device.manage": frozenset({CO, IN}),
    # data collection
    "session.upload": frozenset({P, CP, CO, IN}),
    "session.read": frozenset({P, CO, IN}),
    "questionnaire.respond": frozenset({P, CP, CO, IN}),
    "questionnaire.read": frozenset({P, CP, CO, IN}),
    "instrument.read": frozenset(ROLES),
    "instrument.load_licensed": frozenset({IN}),
    "telemetry.ingest": frozenset({P, CP}),
    "telemetry.control": frozenset({P, CP, CO, IN}),
    "telemetry.review_own": frozenset({P, CP}),
    # data management
    "deviation.manage": frozenset({CO, IN}),
    "missing.record": frozenset({CO, IN}),
    "query.raise": frozenset({IN, SA}),
    "query.answer": frozenset({CO, IN}),
    "query.close": frozenset({IN, SA}),
    "data.correct": frozenset({CO, IN}),
    "record.history": frozenset({CO, IN, AD}),
    "signature.review": frozenset({CO, IN}),
    "signature.approve": frozenset({IN}),
    # oversight & outputs
    "dashboard.read": frozenset({SA, IN}),
    "audit.read": frozenset({IN, AD}),
    "audit.verify": frozenset({IN, AD}),
    "export.full": frozenset({IN}),
    "export.sponsor": frozenset({SA, IN}),
    "subject.export": frozenset({P, IN}),
    "subject.delete": frozenset({IN}),
}


@dataclass(frozen=True)
class Actor:
    user_id: str
    org_id: str
    role: str
    username: str = ""
    display_name: str = ""
    participant_id: str | None = None
    site_ids: frozenset = field(default_factory=frozenset)
    linked_participants: frozenset = field(default_factory=frozenset)

    @property
    def is_site_staff(self) -> bool:
        return self.role in SITE_STAFF


def can(role: str, perm: str) -> bool:
    if perm not in PERMISSIONS:
        raise KeyError(f"unknown permission {perm!r}")
    return role in PERMISSIONS[perm]


def require(actor: Actor, perm: str) -> None:
    if not can(actor.role, perm):
        raise PermissionDenied(f"role '{actor.role}' lacks permission '{perm}'",
                               permission=perm)


def matrix() -> dict[str, dict[str, bool]]:
    """Permission matrix as {permission: {role: allowed}} (used by docs and tests)."""
    return {p: {r: r in roles for r in ROLES} for p, roles in sorted(PERMISSIONS.items())}
