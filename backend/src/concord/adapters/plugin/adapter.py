"""``PluginAdapter``: a third-party source plugin, run out of process, as a DeviceAdapter.

Every connection (and every reconnect) starts a fresh plugin-host process. The adapter
re-validates everything the host sends (the host runs third-party code and is not trusted)
and maps it to standard events with :mod:`concord.adapters.plugin.mapping`.

Failure policy:
  * host exit / hang / protocol error, ``LinkLost``, ``ConfigurationChanged`` ->
    :class:`DeviceLinkError`: the runtime's reconnect policy reopens a fresh host.
  * invalid data, an undeclared stream, an invalid session, an incompatible manifest, an
    unexpected exception in plugin code -> the plugin is STOPPED: the host is killed and
    every further ``open()`` fails with the reason, so the runtime ends in ``error`` with
    a clear message instead of looping.
  * ``MAX_FAILURES_WITHOUT_DATA`` consecutive sessions that fail before delivering any data
    (e.g. a plugin that always hangs) also stop it.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from concord_adapter_sdk import Chunk, DeviceInfo, MarkerChunk, PluginManifest, SessionInfo, ipc
from concord_adapter_sdk import validate as v

from concord.adapters.base import DeviceAdapter, DeviceLinkError, EventDraft, NativePacket
from concord.adapters.plugin import mapping
from concord.adapters.plugin.host_client import (
    AsyncHostClient,
    HostFailure,
    RemoteError,
)
from concord.contracts.protocol import DeviceDescriptor

log = logging.getLogger(__name__)

RECOVERABLE = frozenset({ipc.LINK_LOST, ipc.CONFIGURATION_CHANGED})
MAX_FAILURES_WITHOUT_DATA = 3
STATS_PERIOD_S = 1.0


@dataclass(frozen=True)
class PluginSpec:
    """Everything needed to (re)open one plugin device. ``options`` are already validated."""

    device_id: str
    entry_point: str  # entry-point name (or module:Class in tests)
    device_key: str
    options: Mapping[str, Any]
    manifest: PluginManifest
    device: DeviceInfo | None = None
    python: str | None = None
    extra_path: Sequence[str] = field(default_factory=tuple)
    start_timeout_s: float = 4.0  # hello (process start + plugin import)
    open_timeout_s: float = 4.0
    read_timeout_s: float = 0.1  # passed to SourceSession.read()
    read_grace_s: float = 5.0  # extra time before a read counts as hung
    stall_timeout_s: float | None = None  # default: max(5 s, 50 primary periods)


class PluginStopped(DeviceLinkError):
    """The plugin was stopped for a contract violation; reconnecting will not help."""


class PluginAdapter(DeviceAdapter):
    def __init__(self, spec: PluginSpec, info: SessionInfo | None = None) -> None:
        self.spec = spec
        self._client: AsyncHostClient | None = None
        self._plan: mapping.SessionPlan | None = None
        self._validator: v.ChunkValidator | None = None
        self._fatal: str | None = None
        self._failures_without_data = 0
        self._delivered_since_open = False
        self._last_data = time.monotonic()
        self._last_stats = 0.0
        self.plugin_stats: dict[str, Any] = {}
        self.counters: dict[str, int] = {
            "opens": 0,
            "chunks": 0,
            "samples": 0,
            "lost_samples": 0,
            "gaps": 0,
            "host_failures": 0,
            "link_lost": 0,
        }
        self.session_problems: list[dict[str, str]] = []
        self.log_tail: list[str] = []
        self.last_exit: str | None = None
        self._last_failure: str | None = None
        if info is not None:
            self._plan = mapping.plan_session(spec.manifest, info)
        self.descriptor = self._descriptor()

    # ------------------------------------------------------------------ descriptor
    def _descriptor(self) -> DeviceDescriptor:
        if self._plan is None:  # not opened yet: only what the manifest says
            return mapping.provisional_descriptor(
                self.spec.device_id, self.spec.manifest, self.spec.device
            )
        return mapping.build_descriptor(
            self.spec.device_id, self.spec.manifest, self.spec.device, self._plan
        )

    @property
    def origin(self) -> str:
        return self._plan.info.origin[:128] if self._plan else self.spec.device_id

    @property
    def session_info(self) -> SessionInfo | None:
        return self._plan.info if self._plan else None

    @property
    def host_pid(self) -> int | None:
        return self._client.pid if self._client else None

    @property
    def stopped_reason(self) -> str | None:
        return self._fatal

    def _stop(self, reason: str) -> PluginStopped:
        self._fatal = reason
        log.error("%s: plugin stopped: %s", self.spec.device_id, reason)
        if self._client is not None:
            self._client.kill_now()
        return PluginStopped(f"plugin stopped: {reason}")

    # ------------------------------------------------------------------ lifecycle
    async def open(self) -> None:
        if self._fatal is not None:
            raise PluginStopped(f"plugin stopped: {self._fatal}")
        if self._failures_without_data >= MAX_FAILURES_WITHOUT_DATA:
            raise self._stop(
                f"{MAX_FAILURES_WITHOUT_DATA} consecutive sessions failed before delivering "
                f"any data (last: {self._last_failure or self.last_exit or 'unknown'})"
            )
        await self.close()
        s = self.spec
        client = AsyncHostClient(
            s.entry_point, python=s.python, extra_path=s.extra_path, label=s.device_id
        )
        self._client = client
        try:
            await self._open_session(client)
        except PluginStopped:
            await client.close()
            raise
        except RemoteError as exc:
            await client.close()
            self._remember(client)
            if exc.type in (ipc.OPEN_FAILED, ipc.INVALID_OPTIONS, ipc.LINK_LOST):
                self._failures_without_data += 1
                self._last_failure = exc.message
                raise DeviceLinkError(f"{s.device_id}: {exc.message}") from None
            raise self._stop(self._remote_reason(exc)) from None
        except HostFailure as exc:
            await client.close()
            self._remember(client)
            self._failures_without_data += 1
            self._last_failure = str(exc)
            self.counters["host_failures"] += 1
            raise DeviceLinkError(f"{s.device_id}: {exc}") from None
        except BaseException:  # cancelled (open timeout) or a bug: never leak the process
            client.kill_now()
            raise
        self.counters["opens"] += 1
        self._delivered_since_open = False
        self._last_data = time.monotonic()

    async def _open_session(self, client: AsyncHostClient) -> None:
        s = self.spec
        hello = await client.start(s.start_timeout_s)
        if not hello.get("loaded"):
            err = hello.get("load_error") or {}
            raise self._stop(f"plugin failed to load: {err.get('message', 'unknown error')}")
        result, _ = await client.request("manifest", timeout_s=s.open_timeout_s)
        try:
            manifest = ipc.manifest_from_dict(result.get("manifest") or {})
        except ipc.WireError as exc:
            raise self._stop(f"malformed manifest from the host: {exc}") from None
        problems = v.validate_manifest(manifest)
        if v.has_errors(problems):
            raise self._stop(f"manifest rejected: {v.summarize(problems)}")
        if (manifest.name, manifest.version) != (s.manifest.name, s.manifest.version):
            raise self._stop(
                f"the installed plugin changed since discovery ({s.manifest.name} "
                f"{s.manifest.version} -> {manifest.name} {manifest.version}); "
                "run plugin discovery again"
            )
        result, _ = await client.request(
            "open",
            {"device_key": s.device_key, "options": dict(s.options)},
            timeout_s=s.open_timeout_s,
        )
        try:
            info = ipc.session_info_from_dict(result.get("info") or {})
        except ipc.WireError as exc:
            raise self._stop(f"malformed session info from the host: {exc}") from None
        problems = v.validate_session_info(info, manifest)
        self.session_problems = [p.to_dict() for p in problems]
        if v.has_errors(problems):
            raise self._stop(f"session rejected: {v.summarize(problems)}")
        self._plan = mapping.plan_session(manifest, info)
        self._validator = v.ChunkValidator(info)
        self.descriptor = self._descriptor()

    @staticmethod
    def _remote_reason(exc: RemoteError) -> str:
        detail = ""
        if exc.problems:
            first = v.Problem.from_dict(exc.problems[0])
            detail = f" [{first.code}]"
        tb = ""
        if exc.type == ipc.INTERNAL_ERROR and exc.traceback:
            tb = " (traceback in the plugin log)"
        return f"{exc.type}: {exc.message}{detail}{tb}"[:500]

    def _remember(self, client: AsyncHostClient) -> None:
        self.log_tail = list(client.stderr_tail)[-50:]
        if client.proc is not None and client.proc.returncode is not None:
            self.last_exit = client._exit_message(client.proc.returncode)

    async def close(self) -> None:
        client, self._client = self._client, None
        if client is not None:
            try:
                await client.close()
            finally:
                self._remember(client)

    def set_paused(self, paused: bool) -> None:
        # The runtime discards data while paused; the plugin keeps acquiring so that its
        # sample indices stay honest (no artificial gap on resume).
        pass

    async def probe(self) -> None:
        """Open once and close (used when the operator configures a device)."""
        try:
            await self.open()
        finally:
            await self.close()

    # ------------------------------------------------------------------ reading
    def _stall_timeout(self) -> float | None:
        if self.spec.stall_timeout_s is not None:
            return self.spec.stall_timeout_s
        plan = self._plan
        if plan is None:
            return None
        primary = next(x for x in plan.info.streams if x.stream_id == plan.info.primary_stream)
        if primary.nominal_rate_hz <= 0:
            return None  # irregular primary (e.g. decoder events): silence is legitimate
        return max(5.0, 50.0 / primary.nominal_rate_hz)

    async def read(self) -> NativePacket:
        s = self.spec
        while True:
            client, validator = self._client, self._validator
            if self._fatal is not None:
                raise PluginStopped(f"plugin stopped: {self._fatal}")
            if client is None or validator is None:
                raise DeviceLinkError(f"{s.device_id}: not open")
            try:
                result, arrays = await client.request(
                    "read",
                    {"timeout_s": s.read_timeout_s},
                    timeout_s=s.read_timeout_s + s.read_grace_s,
                )
            except RemoteError as exc:
                self._remember(client)
                if exc.type in RECOVERABLE:
                    self.counters["link_lost"] += 1
                    self._failures_without_data = 0
                    raise DeviceLinkError(f"{s.device_id}: {exc.message}") from None
                raise self._stop(self._remote_reason(exc)) from None
            except HostFailure as exc:
                self.counters["host_failures"] += 1
                self._remember(client)
                self._last_failure = str(exc)
                if not self._delivered_since_open:
                    self._failures_without_data += 1
                raise DeviceLinkError(f"{s.device_id}: {exc}") from None
            try:
                chunks = ipc.chunks_from_wire(result.get("chunks"), arrays)
            except ipc.WireError as exc:
                raise self._stop(f"malformed chunks from the host: {exc}") from None
            received = self._check(chunks, validator)
            await self._maybe_stats(client)
            if received:
                self._last_data = time.monotonic()
                self._delivered_since_open = True
                self._failures_without_data = 0
                return NativePacket(received)
            stall = self._stall_timeout()
            if stall is not None and time.monotonic() - self._last_data > stall:
                raise DeviceLinkError(
                    f"{s.device_id}: no data from the plugin for "
                    f"{time.monotonic() - self._last_data:.1f} s"
                )

    def _check(
        self, chunks: list[Chunk | MarkerChunk], validator: v.ChunkValidator
    ) -> list[mapping.Received]:
        """Runtime-side validation (defence in depth: the host process is untrusted)."""
        out: list[mapping.Received] = []
        for c in chunks:
            known = isinstance(c, Chunk) and c.stream_id in self._stream_ids()
            expected = validator.next_index(c.stream_id) if known else 0
            problems = validator.check(c)
            if v.has_errors(problems):
                raise self._stop(f"invalid data: {v.summarize(problems)}")
            lost = 0
            if isinstance(c, Chunk):
                lost = max(0, int(c.first_index) - expected)
                n = c.data.shape[0]
            else:
                n = len(c.labels)
            if n == 0:
                continue
            if lost:
                self.counters["gaps"] += 1
                self.counters["lost_samples"] += lost
            self.counters["chunks"] += 1
            self.counters["samples"] += n
            out.append(mapping.Received(c, lost))
        return out

    def _stream_ids(self) -> set[str]:
        return {x.stream_id for x in self._plan.info.streams} if self._plan else set()

    async def _maybe_stats(self, client: AsyncHostClient) -> None:
        now = time.monotonic()
        if now - self._last_stats < STATS_PERIOD_S:
            return
        self._last_stats = now
        try:
            result, _ = await client.request("stats", timeout_s=self.spec.read_grace_s)
        except RemoteError as exc:
            log.debug("%s: stats() failed: %s", self.spec.device_id, exc)
            return
        stats = result.get("stats")
        if isinstance(stats, dict):
            self.plugin_stats = {str(k): val for k, val in list(stats.items())[:64]}

    # ------------------------------------------------------------------ normalize (pure)
    def normalize(self, packet: NativePacket) -> Sequence[EventDraft]:
        if self._plan is None:
            return []
        return mapping.normalize(self._plan, packet.data)

    # ------------------------------------------------------------------ metadata
    def source_metadata(self) -> dict[str, Any]:
        m = self.spec.manifest
        plan = self._plan
        streams = []
        if plan is not None:
            for p in plan.streams.values():
                sp = p.spec
                streams.append(
                    {
                        "stream_id": sp.stream_id,
                        "role": str(sp.role),
                        "delivered_as": p.event_type.value if p.event_type else None,
                        "reason": p.reason,
                        "channel_count": len(sp.channels),
                        "channels": [
                            {"label": c.label, "unit": c.unit, "type": c.type} for c in sp.channels
                        ],
                        "nominal_rate_hz": sp.nominal_rate_hz,
                        "clock": {"domain": sp.clock.domain, "description": sp.clock.description},
                        "modality": str(sp.modality) if sp.modality else None,
                        "invasive": sp.invasive,
                        "unit": p.units.unit if p.units else None,
                        "next_index": (
                            self._validator.next_index(sp.stream_id) if self._validator else None
                        ),
                    }
                )
        notes = [
            "Third-party plugin code runs in a separate process (the plugin host); everything "
            "it declares and sends is validated by the host and again by the runtime.",
            "Timestamps are the plugin's own source timestamps; all streams share the primary "
            "stream's clock domain (mixing clock domains is rejected).",
            "Lost samples are counted from gaps in the plugin's sample indices.",
        ]
        if plan is not None:
            for p in plan.streams.values():
                if p.units is not None and p.units.note:
                    notes.append(p.units.note)
        return {
            "protocol": "plugin",
            "device_id": self.spec.device_id,
            "plugin": {
                "entry_point": self.spec.entry_point,
                "package": m.name,
                "version": m.version,
                "api_version": m.api_version,
                "display_name": m.display_name,
                "author": m.author,
                "license": m.license,
                "homepage": m.homepage,
                "ecosystem": m.ecosystem,
                "network": m.network,
            },
            "device_key": self.spec.device_key,
            "options": dict(self.spec.options),
            "isolated": True,
            "host_pid": self.host_pid,
            "origin": plan.info.origin if plan else None,
            "synthetic": plan.info.synthetic if plan else None,
            "prerecorded": plan.info.prerecorded if plan else None,
            "primary_stream": plan.info.primary_stream if plan else None,
            "streams": streams,
            "stats": dict(self.counters),
            "plugin_stats": dict(self.plugin_stats),
            "session_problems": list(self.session_problems),
            "stopped": self._fatal,
            "last_exit": self.last_exit,
            "log_tail": list(self._client.stderr_tail)[-20:]
            if self._client
            else self.log_tail[-20:],
            "notes": notes,
        }


async def probe_plugin(spec: PluginSpec) -> PluginAdapter:
    """Open the device once to learn its session (streams, units, modality), then close."""
    adapter = PluginAdapter(spec)
    await adapter.probe()
    return adapter
