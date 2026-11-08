"""REST for source plugins (adapter SDK): list, discover, configure (/api/v1/plugins).

Operator controls on a localhost-only server. Plugin code never runs in this process:
discovery and configuration start plugin-host subprocesses.
"""

from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field

from concord.contracts.protocol import DeviceDescriptor, ErrorCode
from concord.runtime import RuntimeCommandError
from concord.runtime.plugins import (
    PluginOpenError,
    PluginOptionsError,
    PluginRecord,
    PluginRegistry,
    PluginUnavailableError,
)
from concord.server.deps import AppServices, services

router = APIRouter(prefix="/api/v1")
Svc = Annotated[AppServices, Depends(services)]
OptionValue = str | int | float | bool | None


class ProblemInfo(BaseModel):
    code: str
    message: str
    severity: Literal["error", "warning", "info"]
    where: str


class OptionInfo(BaseModel):
    name: str
    type: Literal["str", "int", "float", "bool", "choice"]
    description: str
    default: OptionValue
    required: bool
    choices: list[str]


class PluginDeviceInfo(BaseModel):
    device_key: str
    display_name: str
    description: str
    details: dict[str, str]
    device_id: str | None = Field(description="None if no valid Concord id can be formed")
    reason: str | None
    configured: bool


class PluginError(BaseModel):
    type: str
    message: str
    traceback: str | None = None


class PluginInfo(BaseModel):
    name: str = Field(description="entry-point name (part of device ids)")
    entry: str
    package: str | None
    package_version: str | None
    status: Literal["compatible", "rejected", "load_error"]
    reason: str | None = Field(description="why the plugin cannot be used (None if compatible)")
    display_name: str | None
    description: str | None
    version: str | None
    api_version: str | None
    author: str | None
    license: str | None
    homepage: str | None
    ecosystem: str | None
    network: bool | None
    roles: list[str]
    options: list[OptionInfo]
    problems: list[ProblemInfo]
    error: PluginError | None
    devices: list[PluginDeviceInfo]
    discovery_error: str | None
    log_tail: list[str]


class PluginsStatus(BaseModel):
    host_api_version: str
    sdk_version: str
    python: str
    discovering: bool
    discovered_at_ns: int | None
    error: str | None
    plugins: list[PluginInfo]


class DiscoverPluginsRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    discover_timeout_s: float | None = Field(default=None, ge=0, le=10)


class ConfigureRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    device_key: str = Field(min_length=1, max_length=40)
    options: dict[str, OptionValue] = Field(default_factory=dict, max_length=32)


def _info(r: PluginRecord, reg: PluginRegistry) -> PluginInfo:
    m = r.manifest
    err = r.error or None
    return PluginInfo(
        name=r.name,
        entry=r.entry,
        package=(r.dist or {}).get("name"),
        package_version=(r.dist or {}).get("version"),
        status=r.status,
        reason=r.reason,
        display_name=m.display_name if m else None,
        description=m.description if m else None,
        version=m.version if m else None,
        api_version=m.api_version if m else None,
        author=m.author if m else None,
        license=m.license if m else None,
        homepage=m.homepage if m else None,
        ecosystem=m.ecosystem if m else None,
        network=m.network if m else None,
        roles=sorted(str(getattr(x, "value", x)) for x in m.roles) if m else [],
        options=[
            OptionInfo(
                name=k,
                type=o.type,
                description=o.description,
                default=o.default,
                required=o.required,
                choices=list(o.choices),
            )
            for k, o in (m.options.items() if m else [])
        ],
        problems=[ProblemInfo.model_validate(p.to_dict()) for p in r.problems],
        error=(
            PluginError(
                type=str(err.get("type", "Error")),
                message=str(err.get("message", "")),
                traceback=err.get("traceback") if isinstance(err.get("traceback"), str) else None,
            )
            if err
            else None
        ),
        devices=[
            PluginDeviceInfo(
                device_key=d.info.device_key,
                display_name=d.info.display_name,
                description=d.info.description,
                details=dict(d.info.details),
                device_id=d.device_id,
                reason=d.reason,
                configured=d.device_id is not None and reg.configured(d.device_id),
            )
            for d in r.devices
        ],
        discovery_error=r.discovery_error,
        log_tail=r.log_tail,
    )


def _status(reg: PluginRegistry) -> PluginsStatus:
    return PluginsStatus(**reg.status(), plugins=[_info(r, reg) for r in reg.records()])


@router.get("/plugins")
async def plugins(svc: Svc) -> PluginsStatus:
    """Installed source plugins: manifest, compatibility / validation result, load errors."""
    return _status(svc.runtime.registry.plugins)


@router.post("/plugins/discover")
async def discover_plugins(svc: Svc, body: DiscoverPluginsRequest | None = None) -> PluginsStatus:
    reg = svc.runtime.registry.plugins
    if body is not None and body.discover_timeout_s is not None:
        reg.discover_timeout_s = body.discover_timeout_s
    try:
        await reg.discover()
    except Exception as exc:
        raise RuntimeCommandError(
            ErrorCode.DEVICE_ERROR, f"plugin discovery failed: {exc}"
        ) from None
    return _status(reg)


@router.post("/plugins/{name}/configure")
async def configure_plugin(name: str, body: ConfigureRequest, svc: Svc) -> DeviceDescriptor:
    """Validate options against the plugin's OptionSpecs, open the device once in an
    isolated host to learn its streams, and register it as a device."""
    reg = svc.runtime.registry.plugins
    rt = svc.runtime
    try:
        spec = reg.spec_for(name, body.device_key, body.options)
    except PluginUnavailableError as exc:
        code = (
            ErrorCode.DEVICE_NOT_FOUND
            if "no installed plugin" in str(exc)
            else ErrorCode.INVALID_STATE
        )
        raise RuntimeCommandError(code, str(exc).strip("'\"")) from None
    except PluginOptionsError as exc:
        raise RuntimeCommandError(ErrorCode.PROTOCOL_ERROR, f"invalid options: {exc}") from None
    except ValueError as exc:
        raise RuntimeCommandError(ErrorCode.PROTOCOL_ERROR, str(exc)) from None
    if rt.device is not None and rt.adapter is not None and rt.device.device_id == spec.device_id:
        raise RuntimeCommandError(
            ErrorCode.INVALID_STATE, "disconnect the device before configuring it again"
        )
    try:
        return await reg.configure(name, body.device_key, body.options)
    except PluginOpenError as exc:
        raise RuntimeCommandError(ErrorCode.DEVICE_ERROR, str(exc)) from None
