"""Catalog of offline neural datasets (NWB files) available as replay devices.

Scans ``datasets_dir`` for ``*.nwb``; each readable file becomes a device ``nwb:<slug>``.
Unreadable or unsupported files are listed in ``problems`` (never silently dropped) and
are not offered as devices.

Decoders (JSON models in ``models_dir``) are attached to a file only if the model was
evaluated on exactly that file (by SHA-256) and was not trained on its session.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from brainos.contracts.protocol import DeviceDescriptor

if TYPE_CHECKING:  # optional dependency: imported lazily
    from brainos.adapters.nwb.source import NWBUnitsSource
    from brainos.decoding.ridge import RidgeDecoder

log = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class CatalogProblem:
    file: str
    error: str


class NWBCatalog:
    def __init__(self, datasets_dir: Path, models_dir: Path) -> None:
        self.datasets_dir = datasets_dir
        self.models_dir = models_dir
        self._descriptors: dict[tuple[str, int, int, str], DeviceDescriptor] = {}
        self._paths: dict[str, Path] = {}
        self._by_id: dict[str, DeviceDescriptor] = {}
        self.problems: list[CatalogProblem] = []
        self.available, self.unavailable_reason = self._probe_support()

    @staticmethod
    def _probe_support() -> tuple[bool, str | None]:
        try:
            import numpy  # noqa: F401
            import pynwb  # noqa: F401
        except ImportError as exc:
            return (
                False,
                f"NWB support not installed ({exc.name}); install with: pip install 'brainos[nwb]'",
            )
        return True, None

    # ------------------------------------------------------------------ models
    def _decoders(self) -> list[RidgeDecoder]:
        from brainos.decoding.ridge import RidgeDecoder

        out = []
        if self.models_dir.exists():
            for p in sorted(self.models_dir.glob("*.json")):
                try:
                    out.append(RidgeDecoder.load(p))
                except (ValueError, TypeError, KeyError, OSError) as exc:
                    log.warning("ignoring model %s: %s", p.name, exc)
        return out

    def _decoder_for(self, sha256: str) -> RidgeDecoder | None:
        matches = [
            d for d in self._decoders() if any(e.get("sha256") == sha256 for e in d.evaluations)
        ]
        return max(matches, key=lambda d: d.created_at) if matches else None

    # ------------------------------------------------------------------ sources
    def source(self, path: Path) -> NWBUnitsSource:
        from brainos.adapters.nwb.source import NWBUnitsSource
        from brainos.datasets import verify_file

        verification = verify_file(path)
        return NWBUnitsSource(
            path, decoder=self._decoder_for(verification.sha256), verification=verification
        )

    def list(self) -> list[DeviceDescriptor]:
        self.problems = []
        if not self.available or not self.datasets_dir.exists():
            return []
        from brainos.adapters.nwb.reader import NWBFormatError

        out: list[DeviceDescriptor] = []
        paths: dict[str, Path] = {}
        models_sig = (
            ",".join(
                f"{p.name}:{p.stat().st_mtime_ns}" for p in sorted(self.models_dir.glob("*.json"))
            )
            if self.models_dir.exists()
            else ""
        )
        for path in sorted(self.datasets_dir.rglob("*.nwb")):
            st = path.stat()
            key = (str(path), st.st_mtime_ns, st.st_size, models_sig)
            desc = self._descriptors.get(key)
            if desc is None:
                try:
                    desc = self.source(path).descriptor()
                except (NWBFormatError, ValueError, OSError) as exc:
                    self.problems.append(CatalogProblem(path.name, str(exc)))
                    log.warning("dataset file %s not offered: %s", path.name, exc)
                    continue
                self._descriptors[key] = desc
            if desc.device_id in paths:
                # never let two files share an id: the second would silently replace the first
                self.problems.append(
                    CatalogProblem(
                        str(path.relative_to(self.datasets_dir)),
                        f"device id {desc.device_id} already used by "
                        f"{paths[desc.device_id].relative_to(self.datasets_dir)}; rename one file",
                    )
                )
                continue
            paths[desc.device_id] = path
            out.append(desc)
        self._paths = paths
        self._by_id = {d.device_id: d for d in out}
        return out

    def describe(self, device_id: str) -> DeviceDescriptor | None:
        """Cached descriptor (no file I/O unless the catalog has never been listed)."""
        if device_id not in self._by_id:
            self.list()
        return self._by_id.get(device_id)

    def path_for(self, device_id: str) -> Path | None:
        if device_id not in self._paths:
            self.list()
        return self._paths.get(device_id)
