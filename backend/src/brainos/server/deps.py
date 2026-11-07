"""Shared server state and error translation."""

from __future__ import annotations

from dataclasses import dataclass

from fastapi import Request
from fastapi.responses import JSONResponse

from brainos.adapters.simulated import OperatorIntentSource
from brainos.contracts.protocol import ErrorCode
from brainos.runtime import Runtime, RuntimeCommandError
from brainos.server.settings import Settings

HTTP_STATUS: dict[ErrorCode, int] = {
    ErrorCode.DEVICE_NOT_FOUND: 404,
    ErrorCode.INVALID_STATE: 409,
    ErrorCode.UNSUPPORTED_OPERATION: 409,
    ErrorCode.CAPABILITY_UNSUPPORTED: 409,
    ErrorCode.RECORDING_ERROR: 409,
    ErrorCode.DEVICE_ERROR: 502,
    ErrorCode.UNKNOWN_CAPABILITY: 422,
    ErrorCode.PROTOCOL_ERROR: 400,
    ErrorCode.SIMULATION_DISABLED: 403,
    ErrorCode.READ_ONLY_RUNTIME: 405,
}


@dataclass
class AppServices:
    settings: Settings
    runtime: Runtime
    intents: OperatorIntentSource


def services(request: Request) -> AppServices:
    svc: AppServices = request.app.state.services
    return svc


def error_response(exc: RuntimeCommandError) -> JSONResponse:
    return JSONResponse(
        status_code=HTTP_STATUS.get(exc.code, 400),
        content={"error": {"code": exc.code.value, "message": exc.message}},
    )
