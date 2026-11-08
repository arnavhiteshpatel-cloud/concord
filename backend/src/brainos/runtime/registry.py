"""Device registry: the single place that knows which adapters exist.

Adding a device = registering a factory here. Nothing else changes.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path

from brainos.adapters.base import DeviceAdapter
from brainos.adapters.cursorclick.catalog import PREFIX as T15_PREFIX
from brainos.adapters.cursorclick.catalog import CursorClickCatalog
from brainos.adapters.replay import (
    BrainOSRecordingSource,
    RecordingFormatError,
    ReplayAdapter,
    recording_path,
    replay_descriptor,
)
from brainos.adapters.simulated import (
    OperatorIntentSource,
    ProfileAAdapter,
    ProfileBAdapter,
    profile_a,
    profile_b,
)
from brainos.contracts.protocol import DeviceDescriptor, SourceMetadata
from brainos.runtime.catalog import NWBCatalog
from brainos.runtime.live_sources import LiveSourceRegistry
from brainos.runtime.plugins import PLUGIN_PREFIX, PluginRegistry

log = logging.getLogger(__name__)

REPLAY_PREFIX = "replay:"
NWB_PREFIX = "nwb:"


class DeviceNotFoundError(LookupError):
    pass


class DeviceOpenError(RuntimeError):
    """The device exists but could not be opened (e.g. a dataset file became invalid)."""


class DeviceRegistry:
    def __init__(
        self,
        intents: OperatorIntentSource,
        recordings_dir: Path,
        *,
        seed: int | None = None,
        replay_loop: bool = True,
        datasets_dir: Path | None = None,
        models_dir: Path | None = None,
        plugins: PluginRegistry | None = None,
    ) -> None:
        self.intents = intents
        self.recordings_dir = recordings_dir
        self._replay_loop = replay_loop
        root = recordings_dir.parent
        self.catalog = NWBCatalog(datasets_dir or root / "datasets", models_dir or root / "models")
        # M5: cursor + click blocks (Dryad .mat files) in the same datasets directory
        self.cursorclick = CursorClickCatalog(datasets_dir or root / "datasets")
        self.live = LiveSourceRegistry()
        self.plugins = plugins or PluginRegistry()
        self._factories: dict[str, tuple[DeviceDescriptor, Callable[[], DeviceAdapter]]] = {
            profile_a.DEVICE_ID: (
                profile_a.descriptor(),
                lambda: ProfileAAdapter(intents, seed=seed),
            ),
            profile_b.DEVICE_ID: (
                profile_b.descriptor(),
                lambda: ProfileBAdapter(intents, seed=seed),
            ),
        }

    def register(self, descriptor: DeviceDescriptor, factory: Callable[[], DeviceAdapter]) -> None:
        """Register an additional adapter factory (extension point for new devices)."""
        if descriptor.device_id in self._factories or descriptor.device_id.startswith(
            (REPLAY_PREFIX, NWB_PREFIX, PLUGIN_PREFIX, T15_PREFIX)
        ):
            raise ValueError(f"device id {descriptor.device_id!r} already registered or reserved")
        self._factories[descriptor.device_id] = (descriptor, factory)

    def _replay_source(self, device_id: str) -> BrainOSRecordingSource:
        name = device_id.removeprefix(REPLAY_PREFIX)
        try:
            path = recording_path(self.recordings_dir, name)
            if not path.exists():
                raise DeviceNotFoundError(device_id)
            return BrainOSRecordingSource(path)
        except RecordingFormatError as exc:
            raise DeviceNotFoundError(f"{device_id}: {exc}") from exc

    def list(self) -> list[DeviceDescriptor]:
        out = [d for d, _ in self._factories.values()]
        if self.recordings_dir.exists():
            for path in sorted(self.recordings_dir.glob("*.brainos.jsonl")):
                try:
                    out.append(replay_descriptor(BrainOSRecordingSource(path)))
                except (RecordingFormatError, OSError) as exc:
                    log.warning("ignoring recording %s: %s", path.name, exc)
        out.extend(self.catalog.list())
        out.extend(self.cursorclick.list())
        out.extend(self.live.list())
        out.extend(self.plugins.list())
        return out

    def _nwb_path(self, device_id: str) -> Path:
        path = self.catalog.path_for(device_id)
        if path is None:
            reason = (
                f" ({self.catalog.unavailable_reason})" if self.catalog.unavailable_reason else ""
            )
            raise DeviceNotFoundError(f"{device_id}{reason}")
        return path

    def source_metadata(self, device_id: str) -> SourceMetadata:
        """Full provenance/metadata for an offline dataset device."""
        if not device_id.startswith(NWB_PREFIX):
            raise DeviceNotFoundError(
                f"{device_id}: no dataset metadata (not an offline dataset source)"
            )
        return self.catalog.source(self._nwb_path(device_id)).metadata()

    def describe(self, device_id: str) -> DeviceDescriptor:
        if device_id.startswith(PLUGIN_PREFIX):
            desc = self.plugins.describe(device_id)
            if desc is None:
                raise DeviceNotFoundError(f"{device_id} (configure the plugin device first)")
            return desc
        if self.live.owns(device_id):
            for d in self.live.list():
                if d.device_id == device_id:
                    return d
        if device_id.startswith(REPLAY_PREFIX):
            return replay_descriptor(self._replay_source(device_id))
        if device_id.startswith(T15_PREFIX):
            desc = self.cursorclick.describe(device_id)
            if desc is None:
                raise DeviceNotFoundError(
                    f"{device_id} ({self.cursorclick.unavailable_reason or 'file not found'})"
                )
            return desc
        if device_id.startswith(NWB_PREFIX):
            desc = self.catalog.describe(device_id)
            if desc is None:
                self._nwb_path(device_id)  # raises DeviceNotFoundError with the reason
                raise DeviceNotFoundError(device_id)
            return desc
        try:
            return self._factories[device_id][0]
        except KeyError:
            raise DeviceNotFoundError(device_id) from None

    def create(self, device_id: str) -> DeviceAdapter:
        if device_id.startswith(PLUGIN_PREFIX):
            try:
                return self.plugins.create(device_id)
            except KeyError:
                raise DeviceNotFoundError(device_id) from None
        if self.live.owns(device_id):
            try:
                return self.live.create(device_id)
            except ValueError as exc:
                raise DeviceOpenError(f"{device_id}: {exc}") from exc
        if device_id.startswith(REPLAY_PREFIX):
            return ReplayAdapter(self._replay_source(device_id), loop=self._replay_loop)
        if device_id.startswith(T15_PREFIX):
            t15 = self.cursorclick.path_for(device_id)
            if t15 is None:
                raise DeviceNotFoundError(device_id)
            try:
                return ReplayAdapter(self.cursorclick.source(t15), loop=self._replay_loop)
            except (ValueError, OSError) as exc:  # T15FormatError is a ValueError
                raise DeviceOpenError(f"{device_id}: cannot open {t15.name}: {exc}") from exc
        if device_id.startswith(NWB_PREFIX):
            path = self._nwb_path(device_id)
            try:
                source = self.catalog.source(path)
            except (ValueError, OSError) as exc:  # NWBFormatError, DecoderLeakageError: ValueError
                raise DeviceOpenError(f"{device_id}: cannot open {path.name}: {exc}") from exc
            return ReplayAdapter(source, loop=self._replay_loop)
        try:
            return self._factories[device_id][1]()
        except KeyError:
            raise DeviceNotFoundError(device_id) from None
