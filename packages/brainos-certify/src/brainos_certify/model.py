"""Check definitions (stable ids) and results.

Every check has a stable id ``<group>.<name>``, a status (``pass`` / ``fail`` / ``warn`` /
``not_run``), a one-line reason and the measured evidence. ``required`` checks must pass (or
warn) for the ``adapter_implementation`` level; a required check that was ``not_run`` only
counts as satisfied when it was not applicable to the plugin (``applicable = False``, e.g.
"no markers stream declared"). Optional checks (the BrainOS runtime phase) do not have to
run, but a failing optional check still blocks the level.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

Status = Literal["pass", "fail", "warn", "not_run"]
STATUSES: tuple[Status, ...] = ("pass", "fail", "warn", "not_run")


@dataclass(frozen=True, slots=True)
class CheckDef:
    id: str
    title: str
    required: bool = True


GROUPS: dict[str, str] = {
    "manifest": "Manifest & compatibility",
    "metadata": "Metadata correctness",
    "timing": "Timestamps",
    "integrity": "Packet ordering, loss & data validity",
    "reconnect": "Reconnection & fault injection",
    "performance": "Performance",
    "runtime": "BrainOS runtime: negotiation & event contract",
}

CHECKS: tuple[CheckDef, ...] = (
    CheckDef("manifest.load", "Plugin host starts and the plugin loads"),
    CheckDef("manifest.valid", "Manifest passes validate_manifest (host and local)"),
    CheckDef("manifest.api_compat", "Plugin API version is compatible with the installed SDK"),
    CheckDef("manifest.entry_point", "Registered as a brainos.sources entry point"),
    CheckDef("manifest.distribution", "Installed distribution identified (name, version, hashes)"),
    CheckDef("manifest.discover", "discover() returns valid devices, including the one tested"),
    CheckDef("metadata.session_valid", "open() succeeds; SessionInfo passes validation"),
    CheckDef("metadata.units", "Channel units declared (unknown units are a warning)"),
    CheckDef("metadata.modality", "Modality / invasiveness declared and consistent"),
    CheckDef("metadata.channel_identity", "Identical streams and channels on every open"),
    CheckDef("timing.monotonic", "Timestamps never decrease"),
    CheckDef("timing.rate", "Rate from source timestamps matches the nominal rate"),
    CheckDef("timing.jitter", "Timestamp and arrival jitter distribution"),
    CheckDef("timing.clock_domain", "Timestamps are plausible for the declared clock domain"),
    CheckDef("integrity.read", "Session streams for the whole run without errors or hangs"),
    CheckDef("integrity.chunk_validation", "Every chunk passes validation (host and local)"),
    CheckDef("integrity.sample_index", "first_index continuity: gaps counted, no overlaps"),
    CheckDef("integrity.markers", "Marker timestamps ordered and on the primary clock"),
    CheckDef("integrity.plugin_stats", "stats() returns valid integrity counters"),
    CheckDef("reconnect.clean_reopen", "Clean close, reopen, data again, identity unchanged"),
    CheckDef("reconnect.host_killed", "Host killed mid-stream: link loss reported, fresh open"),
    CheckDef("performance.throughput", "Sustained delivery rate keeps up with the nominal rate"),
    CheckDef("performance.latency", "Read latency (now - sample timestamp)"),
    CheckDef("performance.host_resources", "Plugin host process CPU and memory"),
    CheckDef("performance.ipc", "IPC volume and round-trip time"),
    CheckDef("runtime.descriptor", "BrainOS device descriptor matches the declarations", False),
    CheckDef("runtime.negotiation", "Capability grants and rejections match the roles", False),
    CheckDef("runtime.envelopes", "Every event validates against the BrainOS contracts", False),
    CheckDef("runtime.provenance", "Provenance correct; nothing becomes a command", False),
)
CHECK_IDS: tuple[str, ...] = tuple(c.id for c in CHECKS)
_BY_ID = {c.id: c for c in CHECKS}


def check_def(check_id: str) -> CheckDef:
    return _BY_ID[check_id]


def group_of(check_id: str) -> str:
    return check_id.split(".", 1)[0]


@dataclass(slots=True)
class CheckResult:
    id: str
    status: Status
    reason: str
    evidence: dict[str, Any] = field(default_factory=dict)
    applicable: bool = True

    @property
    def definition(self) -> CheckDef:
        return _BY_ID[self.id]

    def to_dict(self) -> dict[str, Any]:
        d = self.definition
        return {
            "id": self.id,
            "group": group_of(self.id),
            "title": d.title,
            "required": d.required,
            "status": self.status,
            "applicable": self.applicable,
            "reason": self.reason,
            "evidence": self.evidence,
        }


class Results:
    """Collects check results; every defined check ends up with exactly one result."""

    def __init__(self) -> None:
        self._r: dict[str, CheckResult] = {}

    def set(
        self,
        check_id: str,
        status: Status,
        reason: str,
        evidence: dict[str, Any] | None = None,
        *,
        applicable: bool = True,
    ) -> CheckResult:
        if check_id not in _BY_ID:
            raise KeyError(f"unknown check id {check_id!r}")
        if status not in STATUSES:
            raise ValueError(f"unknown status {status!r}")
        r = CheckResult(
            check_id,
            status,
            reason.strip().splitlines()[0][:300] if reason else "",
            evidence or {},
            applicable,
        )
        self._r[check_id] = r
        return r

    def get(self, check_id: str) -> CheckResult | None:
        return self._r.get(check_id)

    def has(self, check_id: str) -> bool:
        return check_id in self._r

    def not_run(self, check_ids: list[str] | tuple[str, ...], reason: str) -> None:
        """Mark checks that have no result yet as not run (prerequisite failed)."""
        for cid in check_ids:
            if cid not in self._r:
                self.set(cid, "not_run", reason)

    def finalize(self, reason: str) -> list[CheckResult]:
        self.not_run(CHECK_IDS, reason)
        return [self._r[cid] for cid in CHECK_IDS]

    def all(self) -> list[CheckResult]:
        return [self._r[cid] for cid in CHECK_IDS if cid in self._r]
