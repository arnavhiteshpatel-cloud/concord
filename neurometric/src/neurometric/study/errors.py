"""Domain errors (mapped to HTTP status codes by the API layer)."""
from __future__ import annotations


class StudyError(Exception):
    status = 400
    code = "bad_request"

    def __init__(self, message: str = "", code: str | None = None, **detail):
        super().__init__(message or self.code)
        if code:
            self.code = code
        self.detail = detail


class ValidationFailed(StudyError):
    status = 422
    code = "validation_failed"


class NotFound(StudyError):
    """Also used for records of another tenant: existence is never revealed across tenants."""
    status = 404
    code = "not_found"


class PermissionDenied(StudyError):
    status = 403
    code = "forbidden"


class AuthenticationFailed(StudyError):
    status = 401
    code = "unauthenticated"


class Conflict(StudyError):
    status = 409
    code = "conflict"


class ReasonRequired(StudyError):
    status = 422
    code = "reason_for_change_required"


class ConsentRequired(StudyError):
    status = 403
    code = "consent_required"


class InvalidTransition(StudyError):
    status = 409
    code = "invalid_transition"


class DemoMixError(StudyError):
    status = 409
    code = "demo_mix"


class ConfigurationError(StudyError):
    status = 500
    code = "configuration_error"
