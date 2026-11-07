"""Registry of live acquisition sources (LSL streams, Open Ephys ZMQ endpoints).

Live sources are not files on disk: they are discovered (LSL) or configured by the operator
(Open Ephys host/port). The registry keeps their specs; ``create()`` builds a fresh adapter
for each connection. Discovery and adapter creation block on network I/O and must be called
from a worker thread.
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from typing import Any

from brainos.adapters.base import DeviceAdapter
from brainos.contracts.protocol import DeviceDescriptor

log = logging.getLogger(__name__)

LSL_PREFIX = "lsl:"
OPENEPHYS_PREFIX = "openephys:"


@dataclass(frozen=True, slots=True)
class DiscoveredStream:
    key: str
    meta: Any  # StreamMeta
    usable_as_signal: bool
    reason: str | None


class LiveSourceRegistry:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._streams: dict[str, DiscoveredStream] = {}
        self._lsl_specs: dict[str, Any] = {}  # device_id -> LSLSourceSpec
        self._oe_configs: dict[str, Any] = {}  # device_id -> OpenEphysConfig
        self.last_discovery_ns: int | None = None
        self.last_discovery_error: str | None = None

    # ------------------------------------------------------------------ LSL
    def discover_lsl(self, wait_s: float) -> list[DiscoveredStream]:
        import time

        from brainos.adapters.lsl import discovery, interpret
        from brainos.adapters.lsl.metadata import stream_key

        try:
            found = discovery.discover(wait_s)
        except discovery.LSLUnavailableError as exc:
            self.last_discovery_error = str(exc)
            raise
        streams: dict[str, DiscoveredStream] = {}
        for _info, meta in found:
            key = stream_key(meta)
            base, n = key, 2
            while key in streams:  # two streams without source_id on one host
                key = f"{base}-{n}"
                n += 1
            try:
                interpret(meta)
                usable, reason = True, None
            except ValueError as exc:
                usable, reason = False, str(exc)
            streams[key] = DiscoveredStream(key, meta, usable, reason)
        with self._lock:
            self._streams = streams
            self.last_discovery_ns = time.time_ns()
            self.last_discovery_error = None
            # every usable stream is offered as a simple source unless already configured
            for k, s in streams.items():
                did = LSL_PREFIX + k
                if s.usable_as_signal and did not in self._lsl_specs:
                    self._lsl_specs[did] = self._spec(did, s.meta, None, None)
        return list(streams.values())

    @staticmethod
    def _spec(device_id: str, signal: Any, behavior: Any, markers: Any) -> Any:
        from brainos.adapters.lsl import LSLSourceSpec

        return LSLSourceSpec(device_id=device_id, signal=signal, behavior=behavior, markers=markers)

    def configure_lsl(
        self, signal: str, behavior: str | None, markers: str | None
    ) -> DeviceDescriptor:
        """Attach optional behavior/marker streams to a discovered signal stream."""
        from brainos.adapters.lsl import LSLAdapter

        with self._lock:

            def get(k: str | None, role: str) -> Any:
                if k is None:
                    return None
                if k not in self._streams:
                    raise KeyError(f"unknown LSL stream {k!r} for {role}; run discovery first")
                return self._streams[k].meta

            sig = get(signal, "signal")
            did = LSL_PREFIX + signal
            spec = self._spec(did, sig, get(behavior, "behavior"), get(markers, "markers"))
            desc = LSLAdapter(spec).descriptor  # validates the combination
            self._lsl_specs[did] = spec
        return desc

    def streams(self) -> list[DiscoveredStream]:
        with self._lock:
            return list(self._streams.values())

    # ------------------------------------------------------------------ Open Ephys
    def configure_openephys(self, config: Any) -> DeviceDescriptor:
        from brainos.adapters.openephys import OpenEphysAdapter

        adapter = OpenEphysAdapter(config)
        did = adapter.descriptor.device_id
        with self._lock:
            self._oe_configs[did] = config
        return adapter.descriptor

    # ------------------------------------------------------------------ registry API
    def remove(self, device_id: str) -> bool:
        with self._lock:
            return bool(
                self._lsl_specs.pop(device_id, None) or self._oe_configs.pop(device_id, None)
            )

    def list(self) -> list[DeviceDescriptor]:
        out: list[DeviceDescriptor] = []
        with self._lock:
            lsl = list(self._lsl_specs.values())
            oe = list(self._oe_configs.values())
        if lsl:
            from brainos.adapters.lsl import LSLAdapter

            for spec in lsl:
                try:
                    out.append(LSLAdapter(spec).descriptor)
                except ValueError as exc:
                    log.warning("LSL source %s not offered: %s", spec.device_id, exc)
        if oe:
            from brainos.adapters.openephys import OpenEphysAdapter

            out.extend(OpenEphysAdapter(c).descriptor for c in oe)
        return out

    def owns(self, device_id: str) -> bool:
        with self._lock:
            return device_id in self._lsl_specs or device_id in self._oe_configs

    def create(self, device_id: str) -> DeviceAdapter:
        with self._lock:
            spec = self._lsl_specs.get(device_id)
            oe = self._oe_configs.get(device_id)
        if spec is not None:
            from brainos.adapters.lsl import LSLAdapter

            return LSLAdapter(spec)
        if oe is not None:
            from brainos.adapters.openephys import OpenEphysAdapter

            return OpenEphysAdapter(oe)
        raise KeyError(device_id)
