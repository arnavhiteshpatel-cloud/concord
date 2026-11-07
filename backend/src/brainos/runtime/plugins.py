"""Registry of installed source plugins and the plugin devices the operator configured.

Discovery runs ``python -m brainos_adapter_sdk.host --list`` in a subprocess, which in turn
probes every plugin in its own host process; plugin code is never imported here. The
runtime re-validates every manifest and device list it receives.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import sys
import threading
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Literal

from brainos_adapter_sdk import (
    API_VERSION,
    KEY_PATTERN,
    DeviceInfo,
    PluginManifest,
    SessionInfo,
    ipc,
)
from brainos_adapter_sdk import __version__ as SDK_VERSION
from brainos_adapter_sdk import validate as v

from brainos.adapters.base import DeviceAdapter, DeviceLinkError
from brainos.adapters.plugin import PLUGIN_PREFIX, PluginAdapter, PluginSpec, device_id
from brainos.adapters.plugin.host_client import host_env
from brainos.contracts.protocol import DeviceDescriptor

log = logging.getLogger(__name__)

Status = Literal["compatible", "rejected", "load_error"]


class PluginUnavailableError(LookupError):
    """Unknown plugin, or a plugin that was rejected / failed to load (with the reason)."""


class PluginOptionsError(ValueError):
    def __init__(self, problems: list[v.Problem]) -> None:
        self.problems = problems
        super().__init__(v.summarize(problems))


class PluginOpenError(RuntimeError):
    """Configuring the device failed because opening it failed."""


@dataclass
class PluginDevice:
    info: DeviceInfo
    device_id: str | None
    reason: str | None


@dataclass
class PluginRecord:
    name: str  # entry-point name
    entry: str  # module:attr
    dist: dict[str, str] | None
    status: Status
    manifest: PluginManifest | None
    problems: list[v.Problem]
    error: dict[str, Any] | None
    devices: list[PluginDevice]
    discovery_error: str | None
    log_tail: list[str]

    @property
    def reason(self) -> str | None:
        if self.status == "compatible":
            return None
        if self.error:
            return str(self.error.get("message") or self.error.get("type") or "failed to load")
        return v.summarize(self.problems)


@dataclass
class ConfiguredDevice:
    spec: PluginSpec
    info: SessionInfo | None  # from the probe at configure time
    descriptor: DeviceDescriptor
    metadata: dict[str, Any]


@dataclass
class PluginRegistry:
    python: str | None = None  # interpreter for plugin hosts (default: this one)
    extra_path: Sequence[str] = ()  # extra sys.path entries for plugin hosts
    discover_timeout_s: float = 1.0  # passed to each plugin's discover()
    list_timeout_s: float = 60.0
    _records: dict[str, PluginRecord] = field(default_factory=dict)
    _devices: dict[str, ConfiguredDevice] = field(default_factory=dict)
    _lock: threading.Lock = field(default_factory=threading.Lock)
    _discovery: asyncio.Lock | None = None
    discovering: bool = False
    last_discovery_ns: int | None = None
    last_error: str | None = None

    # ------------------------------------------------------------------ discovery
    async def discover(self) -> list[PluginRecord]:
        if self._discovery is None:
            self._discovery = asyncio.Lock()
        async with self._discovery:
            self.discovering = True
            try:
                doc = await self._run_list()
            except Exception as exc:
                self.last_error = str(exc)[:500]
                log.error("plugin discovery failed: %s", exc)
                raise
            finally:
                self.discovering = False
            records = [self._record(r) for r in doc.get("plugins", []) if isinstance(r, dict)]
            with self._lock:
                self._records = {r.name: r for r in records}
                self.last_discovery_ns = time.time_ns()
                self.last_error = None
            for r in records:
                if r.status != "compatible":
                    log.warning("plugin %s not usable: %s", r.name, r.reason)
            log.info(
                "plugin discovery: %d installed, %d compatible",
                len(records),
                sum(r.status == "compatible" for r in records),
            )
            return records

    async def _run_list(self) -> dict[str, Any]:
        proc = await asyncio.create_subprocess_exec(
            self.python or sys.executable,
            "-m",
            "brainos_adapter_sdk.host",
            "--list",
            "--discover-timeout",
            str(self.discover_timeout_s),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=host_env(self.extra_path),
            start_new_session=True,
        )
        try:
            out, err = await asyncio.wait_for(proc.communicate(), self.list_timeout_s)
        except (TimeoutError, asyncio.CancelledError):
            with contextlib.suppress(ProcessLookupError):
                proc.kill()
            await proc.wait()
            raise
        if proc.returncode != 0:
            tail = err.decode("utf-8", "replace").strip().splitlines()[-3:]
            raise RuntimeError(f"plugin listing exited with {proc.returncode}: {' | '.join(tail)}")
        try:
            doc = json.loads(out.decode("utf-8"))
        except ValueError as exc:
            raise RuntimeError(f"plugin listing produced invalid JSON: {exc}") from None
        if not isinstance(doc, dict):
            raise RuntimeError("plugin listing produced an unexpected document")
        return doc

    def _record(self, r: dict[str, Any]) -> PluginRecord:
        """Rebuild and RE-VALIDATE what the listing process reported."""
        name = str(r.get("name", ""))[:64]
        problems = [v.Problem.from_dict(p) for p in r.get("problems") or [] if isinstance(p, dict)]
        raw_status = r.get("status")
        status: Status = (
            "compatible"
            if raw_status == "compatible"
            else "load_error"
            if raw_status == "load_error"
            else "rejected"
        )
        manifest: PluginManifest | None = None
        raw = r.get("manifest")
        if isinstance(raw, dict):
            try:
                manifest = ipc.manifest_from_dict(raw)
            except ipc.WireError as exc:
                problems.append(v.Problem("manifest.malformed", str(exc)))
        if status == "compatible":
            local = v.validate_entry_point_name(name)
            local += (
                v.validate_manifest(manifest)
                if manifest
                else [v.Problem("manifest.missing", "no manifest reported")]
            )
            if v.has_errors(local):
                status = "rejected"
                problems += [p for p in local if p.severity == "error"]
        devices: list[PluginDevice] = []
        derr = r.get("discovery_error")
        discovery_error = str(derr.get("message")) if isinstance(derr, dict) else None
        raw_devices = r.get("devices")
        if status == "compatible" and isinstance(raw_devices, list):
            try:
                infos = [ipc.device_from_dict(d) for d in raw_devices if isinstance(d, dict)]
            except ipc.WireError as exc:
                infos, discovery_error = [], f"malformed device list: {exc}"
            dp = v.validate_devices(infos)
            if v.has_errors(dp):
                infos, discovery_error = [], f"invalid device list: {v.summarize(dp)}"
            for d in infos:
                try:
                    devices.append(PluginDevice(d, device_id(name, d.device_key), None))
                except ValueError as exc:
                    devices.append(PluginDevice(d, None, str(exc)))
        dist = r.get("dist")
        error = r.get("error")
        tail = r.get("stderr_tail")
        return PluginRecord(
            name=name,
            entry=str(r.get("entry", ""))[:256],
            dist={str(k): str(x) for k, x in dist.items()} if isinstance(dist, dict) else None,
            status=status,
            manifest=manifest,
            problems=problems,
            error=error if isinstance(error, dict) else None,
            devices=devices,
            discovery_error=discovery_error,
            log_tail=[str(x)[:500] for x in tail][-20:] if isinstance(tail, list) else [],
        )

    def records(self) -> list[PluginRecord]:
        with self._lock:
            return list(self._records.values())

    def record(self, name: str) -> PluginRecord:
        with self._lock:
            rec = self._records.get(name)
        if rec is None:
            raise PluginUnavailableError(f"no installed plugin named {name!r} (run discovery)")
        return rec

    # ------------------------------------------------------------------ configure
    def spec_for(self, name: str, device_key: str, options: Mapping[str, object]) -> PluginSpec:
        rec = self.record(name)
        if rec.status != "compatible" or rec.manifest is None:
            raise PluginUnavailableError(f"plugin {name!r} cannot be used: {rec.reason}")
        if not isinstance(device_key, str) or not KEY_PATTERN.match(device_key):
            raise PluginOptionsError(
                [v.Problem("device.key", f"device_key {device_key!r} is not valid", "error")]
            )
        resolved, problems = v.validate_options(rec.manifest.options, options)
        if v.has_errors(problems):
            raise PluginOptionsError(problems)
        did = device_id(name, device_key)  # ValueError if too long
        info = next((d.info for d in rec.devices if d.info.device_key == device_key), None)
        return PluginSpec(
            device_id=did,
            entry_point=name,
            device_key=device_key,
            options=resolved,
            manifest=rec.manifest,
            device=info,
            python=self.python,
            extra_path=tuple(self.extra_path),
        )

    async def configure(
        self, name: str, device_key: str, options: Mapping[str, object]
    ) -> DeviceDescriptor:
        """Validate options, open the device once (to learn its streams), register it."""
        return await self.register(self.spec_for(name, device_key, options))

    async def register(self, spec: PluginSpec, *, probe: bool = True) -> DeviceDescriptor:
        """Register a device spec. With ``probe`` (default) the device is opened once in an
        isolated host so its descriptor states real streams, units and modality."""
        adapter = PluginAdapter(spec)
        if probe:
            try:
                await adapter.probe()
            except DeviceLinkError as exc:
                raise PluginOpenError(str(exc)) from None
        with self._lock:
            self._devices[spec.device_id] = ConfiguredDevice(
                spec, adapter.session_info, adapter.descriptor, adapter.source_metadata()
            )
        log.info("plugin device %s configured (%s)", spec.device_id, dict(spec.options))
        return adapter.descriptor

    # ------------------------------------------------------------------ registry API
    def owns(self, did: str) -> bool:
        with self._lock:
            return did in self._devices

    def configured(self, did: str) -> bool:
        return self.owns(did)

    def list(self) -> list[DeviceDescriptor]:
        with self._lock:
            return [d.descriptor for d in self._devices.values()]

    def describe(self, did: str) -> DeviceDescriptor | None:
        with self._lock:
            d = self._devices.get(did)
        return d.descriptor if d else None

    def source_metadata(self, did: str) -> dict[str, Any] | None:
        with self._lock:
            d = self._devices.get(did)
        return dict(d.metadata) if d else None

    def create(self, did: str) -> DeviceAdapter:
        with self._lock:
            d = self._devices.get(did)
        if d is None:
            raise KeyError(did)
        return PluginAdapter(d.spec, d.info)

    def remove(self, did: str) -> bool:
        with self._lock:
            return self._devices.pop(did, None) is not None

    def status(self) -> dict[str, Any]:
        return {
            "host_api_version": API_VERSION,
            "sdk_version": SDK_VERSION,
            "python": self.python or sys.executable,
            "discovering": self.discovering,
            "discovered_at_ns": self.last_discovery_ns,
            "error": self.last_error,
        }


__all__ = [
    "PLUGIN_PREFIX",
    "PluginOpenError",
    "PluginOptionsError",
    "PluginRecord",
    "PluginRegistry",
    "PluginUnavailableError",
]
