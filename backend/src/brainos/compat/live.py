"""The registry as this installation sees it: load ``compat/registry.json`` and attach live
status (is the integration installed here, and is it the version the evidence is for?).

Live status never changes a level: a level belongs to the evidence, which is for the version
recorded in the registry. An installed version that differs is reported as "evidence for a
different version".
"""

from __future__ import annotations

import importlib.util
import logging
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ValidationError

from brainos.compat.model import Entry, Registry

log = logging.getLogger(__name__)

LiveState = Literal["installed", "different_version", "unavailable", "not_installed", "not_checked"]


class LiveStatus(BaseModel):
    state: LiveState
    installed_version: str | None = None
    version_matches: bool | None = None
    detail: str


@dataclass(frozen=True)
class InstalledPlugin:
    """What plugin discovery reported for one installed distribution."""

    package: str
    version: str | None
    status: str  # compatible | rejected | load_error
    reason: str | None


def load_registry(path: Path) -> Registry:
    """Read and validate the registry (raises ``OSError`` / ``ValueError``)."""
    try:
        return Registry.model_validate_json(path.read_bytes())
    except ValidationError as exc:
        raise ValueError(f"{path.name} does not match the registry schema: {exc}") from None


def module_available(name: str) -> bool:
    try:
        return importlib.util.find_spec(name) is not None
    except (ImportError, ValueError):
        return False


def _different(evidence: str, installed: str) -> str:
    return (
        f"Evidence for a different version: the evidence is for {evidence}, "
        f"{installed} is installed"
    )


def builtin_status(
    entry: Entry, brainos_version: str, available: Callable[[str], bool] = module_available
) -> LiveStatus:
    present = available(entry.module) if entry.module else entry.in_checkout
    if not present:
        return LiveStatus(
            state="not_installed",
            installed_version=None,
            detail="Not part of this installation",
        )
    missing = [m for m in entry.requires_modules if not available(m)]
    matches = brainos_version == entry.version
    if not matches:
        return LiveStatus(
            state="different_version",
            installed_version=brainos_version,
            version_matches=False,
            detail=_different(f"BrainOS {entry.version}", f"BrainOS {brainos_version}"),
        )
    if missing:
        return LiveStatus(
            state="unavailable",
            installed_version=brainos_version,
            version_matches=True,
            detail=f"Needs {', '.join(missing)}, which is not installed",
        )
    return LiveStatus(
        state="installed",
        installed_version=brainos_version,
        version_matches=True,
        detail=f"Built into BrainOS {brainos_version}",
    )


def plugin_status(entry: Entry, installed: Sequence[InstalledPlugin] | None) -> LiveStatus:
    if installed is None:
        return LiveStatus(state="not_checked", detail="Plugin discovery has not run yet")
    found = next((p for p in installed if p.package == entry.package), None)
    if found is None:
        return LiveStatus(state="not_installed", detail="Not installed in this BrainOS environment")
    matches = found.version == entry.version if found.version else None
    if matches is False:
        return LiveStatus(
            state="different_version",
            installed_version=found.version,
            version_matches=False,
            detail=_different(entry.version, str(found.version)),
        )
    if found.status != "compatible":
        return LiveStatus(
            state="unavailable",
            installed_version=found.version,
            version_matches=matches,
            detail=f"Installed but not usable: {found.reason or found.status}",
        )
    return LiveStatus(
        state="installed",
        installed_version=found.version,
        version_matches=matches,
        detail=f"Installed, version {found.version}" if found.version else "Installed",
    )


def live_status(
    registry: Registry,
    *,
    brainos_version: str,
    installed_plugins: Sequence[InstalledPlugin] | None,
    available: Callable[[str], bool] = module_available,
) -> Mapping[str, LiveStatus]:
    out: dict[str, LiveStatus] = {}
    for e in registry.entries:
        if e.kind == "source_plugin":
            out[e.id] = plugin_status(e, installed_plugins)
        else:
            out[e.id] = builtin_status(e, brainos_version, available)
    return out
