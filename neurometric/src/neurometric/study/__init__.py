"""NeuroMetric study data management: tenants, roles, studies, participants, consent,
schedules, functional sessions, questionnaires, telemetry, audit trail, signatures, exports.

Research software, not a medical device. The audit trail, e-signature records and access
controls are technical controls oriented to 21 CFR Part 11; the system is NOT Part 11
compliant or validated, not HIPAA compliant and has no SOC 2 attestation.
"""
from .audit import AuditTrail
from .db import Database
from .errors import (AuthenticationFailed, Conflict, ConsentRequired, DemoMixError,
                     InvalidTransition, NotFound, PermissionDenied, ReasonRequired, StudyError,
                     ValidationFailed)
from .permissions import ROLES, Actor, PERMISSIONS, can
from .service import StudyService

__all__ = ["AuditTrail", "Database", "StudyService", "Actor", "ROLES", "PERMISSIONS", "can",
           "StudyError", "ValidationFailed", "NotFound", "PermissionDenied", "Conflict",
           "AuthenticationFailed", "ReasonRequired", "ConsentRequired", "InvalidTransition",
           "DemoMixError"]
