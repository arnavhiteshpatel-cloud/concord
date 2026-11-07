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
from brainos.contracts.protocol import DeviceDescriptor

log = logging.getLogger(__name__)

REPLAY_PREFIX = "replay:"


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
    ) -> None:
        self.intents = intents
        self.recordings_dir = recordings_dir
        self._replay_loop = replay_loop
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
            REPLAY_PREFIX
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
        return out

    def describe(self, device_id: str) -> DeviceDescriptor:
        if device_id.startswith(REPLAY_PREFIX):
            return replay_descriptor(self._replay_source(device_id))
        try:
            return self._factories[device_id][0]
        except KeyError:
            raise DeviceNotFoundError(device_id) from None

    def create(self, device_id: str) -> DeviceAdapter:
        if device_id.startswith(REPLAY_PREFIX):
            return ReplayAdapter(self._replay_source(device_id), loop=self._replay_loop)
        try:
            return self._factories[device_id][1]()
        except KeyError:
            raise DeviceNotFoundError(device_id) from None
