"""Device registry: the single place that knows which adapters exist.

Adding a device = registering a factory here. Nothing else changes.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path

from brainos.adapters.base import DeviceAdapter
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

log = logging.getLogger(__name__)

REPLAY_PREFIX = "replay:"
NWB_PREFIX = "nwb:"


class DeviceNotFoundError(LookupError):
    pass


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
    ) -> None:
        self.intents = intents
        self.recordings_dir = recordings_dir
        self._replay_loop = replay_loop
        root = recordings_dir.parent
        self.catalog = NWBCatalog(datasets_dir or root / "datasets", models_dir or root / "models")
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
            (REPLAY_PREFIX, NWB_PREFIX)
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
        if device_id.startswith(REPLAY_PREFIX):
            return replay_descriptor(self._replay_source(device_id))
        if device_id.startswith(NWB_PREFIX):
            self._nwb_path(device_id)  # raises DeviceNotFoundError
            for d in self.catalog.list():
                if d.device_id == device_id:
                    return d
            raise DeviceNotFoundError(device_id)
        try:
            return self._factories[device_id][0]
        except KeyError:
            raise DeviceNotFoundError(device_id) from None

    def create(self, device_id: str) -> DeviceAdapter:
        if device_id.startswith(REPLAY_PREFIX):
            return ReplayAdapter(self._replay_source(device_id), loop=self._replay_loop)
        if device_id.startswith(NWB_PREFIX):
            return ReplayAdapter(
                self.catalog.source(self._nwb_path(device_id)), loop=self._replay_loop
            )
        try:
            return self._factories[device_id][1]()
        except KeyError:
            raise DeviceNotFoundError(device_id) from None
