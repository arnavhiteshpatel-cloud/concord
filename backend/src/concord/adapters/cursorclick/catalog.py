"""Catalog of cursor + click blocks on disk, offered as offline replay devices ``t15:...``.

Scans ``datasets_dir`` (recursively) for ``t15_day*_block*.mat``. Each readable file becomes a
device; unreadable files are listed in ``problems`` and not offered. Listing matches files to
the pinned Dryad manifest by name and size (cheap); the SHA-256 is verified when a device is
opened, and an unverified file is labelled as such.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from concord.contracts.protocol import DeviceDescriptor

if TYPE_CHECKING:
    from concord.adapters.cursorclick.source import T15CursorClickSource

log = logging.getLogger(__name__)

PREFIX = "t15:"
PATTERN = "t15_day*_block*.mat"


@dataclass(frozen=True, slots=True)
class CatalogProblem:
    file: str
    error: str


class CursorClickCatalog:
    def __init__(self, datasets_dir: Path) -> None:
        self.datasets_dir = datasets_dir
        self._cache: dict[tuple[str, int, int], DeviceDescriptor] = {}
        self._paths: dict[str, Path] = {}
        self.problems: list[CatalogProblem] = []
        self.available, self.unavailable_reason = self._probe()

    @staticmethod
    def _probe() -> tuple[bool, str | None]:
        try:
            import numpy  # noqa: F401
            import scipy.io  # noqa: F401
        except ImportError as exc:
            return (
                False,
                f"MATLAB-file support not installed ({exc.name}): pip install 'concordos[dsp]'",
            )
        return True, None

    def source(self, path: Path, *, verify: bool = True) -> T15CursorClickSource:
        """``verify``: hash the file against the pinned manifest (done when a device is opened)."""
        from concord.adapters.cursorclick.source import T15CursorClickSource

        return T15CursorClickSource(path, verify=verify)

    def list(self) -> list[DeviceDescriptor]:
        self.problems = []
        if not self.available or not self.datasets_dir.exists():
            return []
        from concord.adapters.cursorclick.reader import T15FormatError

        out: list[DeviceDescriptor] = []
        paths: dict[str, Path] = {}
        for path in sorted(self.datasets_dir.rglob(PATTERN)):
            st = path.stat()
            key = (str(path), st.st_mtime_ns, st.st_size)
            desc = self._cache.get(key)
            if desc is None:
                try:
                    desc = self.source(path, verify=False).descriptor()
                except (T15FormatError, ValueError, OSError) as exc:
                    self.problems.append(CatalogProblem(path.name, str(exc)))
                    log.warning("cursor+click file %s not offered: %s", path.name, exc)
                    continue
                self._cache[key] = desc
            if desc.device_id in paths:
                self.problems.append(
                    CatalogProblem(path.name, f"device id {desc.device_id} already used")
                )
                continue
            paths[desc.device_id] = path
            out.append(desc)
        self._paths = paths
        return out

    def owns(self, device_id: str) -> bool:
        return device_id.startswith(PREFIX)

    def path_for(self, device_id: str) -> Path | None:
        if device_id not in self._paths:
            self.list()
        return self._paths.get(device_id)

    def describe(self, device_id: str) -> DeviceDescriptor | None:
        path = self.path_for(device_id)
        if path is None:
            return None
        st = path.stat()
        return self._cache.get((str(path), st.st_mtime_ns, st.st_size))
