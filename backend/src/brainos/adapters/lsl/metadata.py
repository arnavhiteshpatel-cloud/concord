"""Pure helpers for LSL stream metadata (no liblsl calls here; unit-testable).

LSL stream metadata follows the XDF/LSL "meta-data" conventions:
``<desc><channels><channel><label/><unit/><type/></channel>...</channels></desc>``
(https://github.com/sccn/xdf/wiki/Meta-Data). Fields that a stream does not provide are
reported as missing; nothing is guessed.

BrainOS-specific declarations a *publisher* may add (optional, honoured but never assumed):
``<desc><brainos><prerecorded>true</prerecorded><synthetic>false</synthetic>
<origin>dandi:000954/…</origin><feature>spike_count</feature><quantity>velocity</quantity>
</brainos></desc>``
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# Exact scale factors to microvolts. Keys are lower-cased unit strings seen in the wild
# (XDF recommends "microvolts"); anything else is "unknown" -> values passed as 'arbitrary'.
UNIT_TO_UV: dict[str, float] = {
    "microvolts": 1.0,
    "microvolt": 1.0,
    "uv": 1.0,
    "µv": 1.0,
    "μv": 1.0,  # Greek mu
    "millivolts": 1e3,
    "millivolt": 1e3,
    "mv": 1e3,
    "volts": 1e6,
    "volt": 1e6,
    "v": 1e6,
    "nanovolts": 1e-3,
    "nanovolt": 1e-3,
    "nv": 1e-3,
}

# LSL content types treated as electrophysiology (raw signal) by default.
EPHYS_TYPES = frozenset({"eeg", "ecog", "seeg", "ieeg", "lfp", "emg", "exg", "ephys", "spikeband"})
# BrainOS convention for pre-binned spike counts (no LSL standard exists for this).
SPIKE_COUNT_TYPES = frozenset({"spikecounts", "binnedspikes"})
MARKER_TYPES = frozenset({"markers", "marker", "events"})

FORMAT_NAMES = {
    1: "float32",
    2: "double64",
    3: "string",
    4: "int32",
    5: "int16",
    6: "int8",
    7: "int64",
}


@dataclass(frozen=True, slots=True)
class ChannelMeta:
    index: int
    label: str | None
    unit: str | None
    type: str | None


@dataclass(frozen=True, slots=True)
class Declaration:
    """Optional facts a publisher states about itself in ``<desc><brainos>``."""

    prerecorded: bool | None = None
    synthetic: bool | None = None
    origin: str | None = None
    feature: str | None = None
    quantity: str | None = None


@dataclass(frozen=True, slots=True)
class StreamMeta:
    name: str
    type: str
    source_id: str
    hostname: str
    uid: str
    channel_count: int
    nominal_srate: float
    channel_format: str
    created_at: float
    channels: tuple[ChannelMeta, ...] = ()
    declaration: Declaration = field(default_factory=Declaration)
    manufacturer: str | None = None

    @property
    def is_string(self) -> bool:
        return self.channel_format == "string"

    @property
    def regular(self) -> bool:
        return self.nominal_srate > 0


def _bool(s: str | None) -> bool | None:
    if s is None or s.strip() == "":
        return None
    v = s.strip().lower()
    if v in {"true", "1", "yes"}:
        return True
    if v in {"false", "0", "no"}:
        return False
    return None


def _opt(s: str | None) -> str | None:
    return s.strip() if s and s.strip() else None


def unit_scale_to_uv(unit: str | None) -> float | None:
    """Exact factor to convert ``unit`` to microvolts, or None if the unit is not known."""
    if unit is None:
        return None
    return UNIT_TO_UV.get(unit.strip().lower())


@dataclass(frozen=True, slots=True)
class UnitPlan:
    """How a stream's values become recording.frame values."""

    unit: str  # "uV" or "arbitrary"
    scales: tuple[float, ...] | None  # per-channel multiply-to-µV, None if arbitrary
    note: str | None


def plan_units(channels: tuple[ChannelMeta, ...], channel_count: int) -> UnitPlan:
    """Convert to µV only if *every* channel states a known voltage unit."""
    if len(channels) != channel_count:
        return UnitPlan(
            "arbitrary",
            None,
            "Stream metadata does not describe every channel; units unknown, values passed "
            "through unscaled as 'arbitrary'.",
        )
    scales = [unit_scale_to_uv(c.unit) for c in channels]
    if all(s is not None for s in scales):
        return UnitPlan("uV", tuple(float(s) for s in scales if s is not None), None)
    unknown = sorted({str(c.unit) for c, s in zip(channels, scales, strict=True) if s is None})
    return UnitPlan(
        "arbitrary",
        None,
        f"Channel unit(s) {unknown} are not a known voltage unit; values passed through "
        "unscaled as 'arbitrary' (BrainOS does not guess units).",
    )


_SLUG = re.compile(r"[^a-z0-9_.\-]+")


def slug(text: str, limit: int = 40) -> str:
    s = _SLUG.sub("-", text.lower()).strip("-")
    return s[:limit] or "stream"


def stream_key(meta: StreamMeta) -> str:
    """Stable identity across restarts: source_id if set, else name@host/type."""
    if meta.source_id:
        return slug(meta.source_id)
    return slug(f"{meta.name}@{meta.hostname}-{meta.type}")
