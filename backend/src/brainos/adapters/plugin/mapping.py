"""Pure mapping from adapter-SDK declarations and chunks to BrainOS descriptors and events.

Role -> event type (ARCHITECTURE.md §12):

=============== ========================= ====================================================
SIGNAL          ``recording.frame``       ``raw_signal``; µV only if every channel states a
                                          known voltage unit, else ``arbitrary``
SPIKE_COUNTS    ``features.binned``       ``processed_feature``, ``spike_count``; the sample
                                          timestamp is the bin end
BEHAVIOR        ``behavior.sample``       ``behavioral_label``
MARKERS         ``recording.annotation``  ``behavioral_label``
DECODER_OUTPUT  ``intent.kinematics``     ``decoded_intent``, model_id ``<plugin>:<model>``
=============== ========================= ====================================================

BrainOS delivers ONE stream per role (the primary stream for its role, else the first
declared); further streams of the same role are listed as not delivered, with the reason.
All streams share one clock domain (enforced by ``validate_session_info``), so every
timestamp maps directly to ``device_timestamp_ns``.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

import numpy as np
from brainos_adapter_sdk import (
    Chunk,
    DeviceInfo,
    MarkerChunk,
    PluginManifest,
    SessionInfo,
    StreamRole,
    StreamSpec,
)
from brainos_adapter_sdk.validate import version_core

from brainos.adapters.base import EventDraft, PacketDecodeError, frame_samples_limit
from brainos.adapters.lsl.metadata import ChannelMeta, UnitPlan, plan_units
from brainos.contracts.capabilities import Capability, CapabilityDescriptor, EventType
from brainos.contracts.events import (
    DEVICE_ID_PATTERN,
    Provenance,
    ProvenanceKind,
    Quality,
    QualityFlag,
)
from brainos.contracts.protocol import (
    INVASIVE_MODALITIES,
    NONINVASIVE_MODALITIES,
    DeviceDescriptor,
    DeviceKind,
    IntegrationInfo,
    Modality,
)

PLUGIN_PREFIX = "plugin:"
MAX_FRAME_SAMPLES = 2_000  # per recording.frame (same as the LSL adapter)
EVENT_FOR_ROLE: dict[StreamRole, EventType] = {
    StreamRole.SIGNAL: EventType.RECORDING_FRAME,
    StreamRole.SPIKE_COUNTS: EventType.FEATURES_BINNED,
    StreamRole.BEHAVIOR: EventType.BEHAVIOR_SAMPLE,
    StreamRole.MARKERS: EventType.RECORDING_ANNOTATION,
    StreamRole.DECODER_OUTPUT: EventType.INTENT_KINEMATICS,
}
_SLUG = re.compile(r"[^a-z0-9_.\-]+")


def device_id(entry_point: str, device_key: str) -> str:
    did = f"{PLUGIN_PREFIX}{entry_point}:{device_key}"
    if len(did) > 64 or not re.match(DEVICE_ID_PATTERN, did):
        raise ValueError(
            f"device id {did!r} would exceed 64 characters or contain invalid characters; "
            "use a shorter entry-point name or device key"
        )
    return did


def adapter_name(manifest: PluginManifest) -> str:
    """'brainos-example-adapter@0.1.0' (the plugin as the producing adapter)."""
    slug = _SLUG.sub("-", manifest.name.lower()).strip("-")[:100] or "plugin"
    return f"{slug}@{version_core(manifest.version)}"


def _common_unit(spec: StreamSpec) -> str:
    units = {c.unit for c in spec.channels if c.unit}
    if len(units) == 1:
        return next(iter(units))[:32]
    return "unspecified" if not units else "mixed"


@dataclass(frozen=True, slots=True)
class StreamPlan:
    spec: StreamSpec
    event_type: EventType | None  # None: not delivered
    reason: str | None = None
    units: UnitPlan | None = None  # SIGNAL only

    @property
    def labels(self) -> list[str]:
        return [c.label for c in self.spec.channels]


@dataclass(frozen=True, slots=True)
class SessionPlan:
    manifest: PluginManifest
    info: SessionInfo
    streams: dict[str, StreamPlan]
    adapter: str
    flags: tuple[QualityFlag, ...]
    provenance: dict[str, Provenance] = field(default_factory=dict)  # per stream id

    @property
    def delivered(self) -> list[StreamPlan]:
        return [p for p in self.streams.values() if p.event_type is not None]

    def plan_for(self, role: StreamRole) -> StreamPlan | None:
        return next((p for p in self.delivered if p.spec.role is role), None)


def plan_session(manifest: PluginManifest, info: SessionInfo) -> SessionPlan:
    """Decide which streams become which events. ``info`` must already be validated."""
    order = sorted(info.streams, key=lambda s: s.stream_id != info.primary_stream)
    taken: dict[StreamRole, str] = {}
    streams: dict[str, StreamPlan] = {}
    synthetic = info.synthetic
    replayed = info.prerecorded and not synthetic
    adapter = adapter_name(manifest)
    origin = info.origin[:128]
    provenance: dict[str, Provenance] = {}
    for s in order:
        role = StreamRole(s.role)
        if role in taken:
            streams[s.stream_id] = StreamPlan(
                s,
                None,
                f"not delivered: BrainOS takes one {role.value} stream per device "
                f"({taken[role]!r} is used)",
            )
            continue
        taken[role] = s.stream_id
        units = None
        if role is StreamRole.SIGNAL:
            meta = tuple(ChannelMeta(i, c.label, c.unit, c.type) for i, c in enumerate(s.channels))
            units = plan_units(meta, len(s.channels))
        streams[s.stream_id] = StreamPlan(s, EVENT_FOR_ROLE[role], None, units)
        kind = {
            StreamRole.SIGNAL: ProvenanceKind.RAW_SIGNAL,
            StreamRole.SPIKE_COUNTS: ProvenanceKind.PROCESSED_FEATURE,
            StreamRole.BEHAVIOR: ProvenanceKind.BEHAVIORAL_LABEL,
            StreamRole.MARKERS: ProvenanceKind.BEHAVIORAL_LABEL,
            StreamRole.DECODER_OUTPUT: ProvenanceKind.DECODED_INTENT,
        }[role]
        provenance[s.stream_id] = Provenance(
            kind=kind,
            adapter=adapter,
            synthetic=synthetic,
            model_id=f"{manifest.name}:{s.model_id}"[:128] if s.model_id else None,
            origin=origin,
            replayed=replayed,
        )
    flags: list[QualityFlag] = []
    if synthetic:
        flags.append(QualityFlag.SYNTHETIC)
    if replayed:
        flags.append(QualityFlag.REPLAYED)
    # keep declaration order for display
    ordered = {s.stream_id: streams[s.stream_id] for s in info.streams}
    return SessionPlan(manifest, info, ordered, adapter, tuple(flags), provenance)


# ----------------------------------------------------------------------------- descriptor


def neural_modality(info: SessionInfo) -> tuple[Modality | None, bool | None]:
    """Modality of the device = that of its PRIMARY neural stream; never taken from a
    secondary stream (e.g. an accelerometer group declared ``other`` must not relabel a
    signal whose modality is unknown). ``invasive`` follows the declaration, or the
    contract's categories for a declared modality; never guessed."""
    primary = next((s for s in info.streams if s.stream_id == info.primary_stream), None)
    if primary is None or primary.role not in (StreamRole.SIGNAL, StreamRole.SPIKE_COUNTS):
        return None, None
    invasive = primary.invasive
    if primary.modality is None:
        return None, invasive
    mod = Modality(str(primary.modality))
    if invasive is None and mod in INVASIVE_MODALITIES:
        invasive = True
    elif invasive is None and mod in NONINVASIVE_MODALITIES:
        invasive = False
    return mod, invasive


def _capabilities(plan: SessionPlan) -> list[CapabilityDescriptor]:
    caps: list[CapabilityDescriptor] = []
    sig = plan.plan_for(StreamRole.SIGNAL)
    mk = plan.plan_for(StreamRole.MARKERS)
    if sig is not None:
        s = sig.spec
        assert sig.units is not None
        caps.append(
            CapabilityDescriptor(
                capability=Capability.RECORDING,
                params={
                    "channel_count": len(s.channels),
                    "sample_rate_hz": float(s.nominal_rate_hz),
                    "unit": sig.units.unit,
                    "channel_labels": sig.labels,
                    "channel_units": [c.unit or "unknown" for c in s.channels],
                    "stream_id": s.stream_id,
                    "modality": str(s.modality) if s.modality else "not declared",
                    "annotations": mk is not None,
                },
                description="Plugin signal stream as raw samples"
                + ("" if sig.units.unit == "uV" else " (unit unknown: 'arbitrary')"),
            )
        )
    elif mk is not None:
        caps.append(
            CapabilityDescriptor(
                capability=Capability.RECORDING,
                params={"annotations_only": True, "stream_id": mk.spec.stream_id},
                description="Plugin marker stream as recording.annotation",
            )
        )
    sc = plan.plan_for(StreamRole.SPIKE_COUNTS)
    if sc is not None:
        s = sc.spec
        caps.append(
            CapabilityDescriptor(
                capability=Capability.NEURAL_FEATURES,
                params={
                    "feature": "spike_count",
                    "bin_ms": float(s.bin_ms or 0.0),
                    "rate_hz": float(s.nominal_rate_hz),
                    "channel_count": len(s.channels),
                    "channel_labels": sc.labels,
                    "stream_id": s.stream_id,
                    "modality": str(s.modality) if s.modality else "not declared",
                },
                description="Plugin spike-count stream (counts per bin)",
            )
        )
    beh = plan.plan_for(StreamRole.BEHAVIOR)
    if beh is not None:
        s = beh.spec
        caps.append(
            CapabilityDescriptor(
                capability=Capability.BEHAVIOR,
                params={
                    "quantity": s.quantity or "behavior",
                    "dims": beh.labels,
                    "unit": _common_unit(s),
                    "rate_hz": float(s.nominal_rate_hz),
                    "stream_id": s.stream_id,
                },
                description="Plugin behavior stream as behavioral labels",
            )
        )
    dec = plan.plan_for(StreamRole.DECODER_OUTPUT)
    if dec is not None:
        s = dec.spec
        caps.append(
            CapabilityDescriptor(
                capability=Capability.KINEMATIC_INTENT,
                params={
                    "quantity": s.quantity or "decoder_output",
                    "dims": dec.labels,
                    "unit": _common_unit(s),
                    "rate_hz": float(s.nominal_rate_hz),
                    "model_id": plan.provenance[s.stream_id].model_id or "",
                    "stream_id": s.stream_id,
                },
                description="Output of the plugin's external decoder (decoded_intent); never a "
                "command unless the operator enables the command router",
            )
        )
    caps.append(CapabilityDescriptor(capability=Capability.DEVICE_STATUS))
    return caps


def device_kind(info: SessionInfo) -> DeviceKind:
    if info.synthetic:
        return DeviceKind.SIMULATED
    if info.prerecorded:
        return DeviceKind.REPLAY
    return DeviceKind.STREAM


def build_descriptor(
    did: str, manifest: PluginManifest, device: DeviceInfo | None, plan: SessionPlan
) -> DeviceDescriptor:
    info = plan.info
    kind = device_kind(info)
    modality, invasive = neural_modality(info)
    streams = ", ".join(
        f"{p.spec.stream_id} ({StreamRole(p.spec.role).value}, {len(p.spec.channels)} ch"
        + (f" @ {p.spec.nominal_rate_hz:g} Hz" if p.spec.nominal_rate_hz else ", irregular")
        + (")" if p.event_type is not None else ", not delivered)")
        for p in plan.streams.values()
    )
    origin_note = {
        DeviceKind.SIMULATED: "The plugin declares the data synthetic.",
        DeviceKind.REPLAY: "The plugin declares the data prerecorded (played back).",
        DeviceKind.STREAM: "Live source as declared by the plugin; BrainOS cannot verify "
        "whether it comes from hardware.",
    }[kind]
    name = device.display_name if device is not None else manifest.display_name
    lead = f"{device.description} " if device is not None and device.description else ""
    return DeviceDescriptor(
        device_id=did,
        display_name=name[:80],
        kind=kind,
        adapter=plan.adapter,
        description=(
            f"{lead}Provided by the plugin {manifest.display_name!r} ({manifest.name} "
            f"{manifest.version}), running in its own process. Origin: {info.origin}. "
            f"{origin_note}"
        ),
        native_format=f"BrainOS adapter SDK {manifest.api_version} plugin; streams: {streams}",
        capabilities=_capabilities(plan),
        synthetic=info.synthetic,
        modality=modality,
        invasive=invasive,
        integration=integration(manifest),
    )


def integration(manifest: PluginManifest) -> IntegrationInfo:
    return IntegrationInfo(
        kind="plugin",
        package=manifest.name[:128],
        version=manifest.version[:64],
        api_version=manifest.api_version[:16],
        isolated=True,
        ecosystem=manifest.ecosystem,
    )


def provisional_descriptor(
    did: str, manifest: PluginManifest, device: DeviceInfo | None
) -> DeviceDescriptor:
    """Before the first open(): nothing is known about streams; nothing is claimed."""
    return DeviceDescriptor(
        device_id=did,
        display_name=(device.display_name if device else manifest.display_name)[:80],
        kind=DeviceKind.STREAM,
        adapter=adapter_name(manifest),
        description=f"Plugin {manifest.display_name!r} ({manifest.name} {manifest.version}); "
        "not opened yet.",
        native_format=f"BrainOS adapter SDK {manifest.api_version} plugin",
        capabilities=[CapabilityDescriptor(capability=Capability.DEVICE_STATUS)],
        synthetic=False,
        integration=integration(manifest),
    )


# ----------------------------------------------------------------------------- events


def _ns(t: float) -> int:
    return round(t * 1e9)


@dataclass(frozen=True, slots=True)
class Received:
    """A validated chunk plus the number of samples lost right before it."""

    chunk: Chunk | MarkerChunk
    lost_before: int = 0


def _quality(plan: SessionPlan, lost: bool) -> Quality:
    flags = list(plan.flags)
    if lost:
        flags.append(QualityFlag.DROPPED_SAMPLES)
    return Quality(score=0.5 if lost else 1.0, flags=flags)


def normalize(plan: SessionPlan, items: Sequence[Received]) -> list[EventDraft]:
    out: list[EventDraft] = []
    for r in items:
        sp = plan.streams.get(r.chunk.stream_id)
        if sp is None:
            raise PacketDecodeError(f"chunk for undeclared stream {r.chunk.stream_id!r}")
        if sp.event_type is None:
            continue  # declared but not delivered (see StreamPlan.reason)
        prov = plan.provenance[sp.spec.stream_id]
        if isinstance(r.chunk, MarkerChunk):
            for label, t in zip(r.chunk.labels, r.chunk.timestamps.tolist(), strict=True):
                out.append(
                    EventDraft(
                        EventType.RECORDING_ANNOTATION,
                        {"label": label.strip()[:128], "value": None, "duration_ms": None},
                        _quality(plan, False),
                        prov,
                        _ns(t),
                    )
                )
            continue
        out.extend(_numeric(plan, sp, prov, r))
    return out


def _numeric(plan: SessionPlan, sp: StreamPlan, prov: Provenance, r: Received) -> list[EventDraft]:
    c = r.chunk
    assert isinstance(c, Chunk)
    s = sp.spec
    ts: list[float] = c.timestamps.tolist()
    first = int(c.first_index)
    lost = r.lost_before > 0
    out: list[EventDraft] = []
    if sp.event_type is EventType.RECORDING_FRAME:
        assert sp.units is not None
        values: np.ndarray[Any, np.dtype[np.float64]] = c.data.astype(np.float64)
        if sp.units.scales is not None and any(x != 1.0 for x in sp.units.scales):
            values = values * np.asarray(sp.units.scales)
        n = values.shape[0]
        step = frame_samples_limit(len(s.channels), MAX_FRAME_SAMPLES)
        for start in range(0, n, step):
            block = values[start : start + step]
            out.append(
                EventDraft(
                    EventType.RECORDING_FRAME,
                    {
                        "sample_rate_hz": float(s.nominal_rate_hz),
                        "channel_count": len(s.channels),
                        "first_sample_index": first + start,
                        "unit": sp.units.unit,
                        "samples": block.T,  # (channels, n) array view (M5-E fast path)
                    },
                    _quality(plan, lost and start == 0),
                    prov,
                    _ns(ts[start]),
                )
            )
        return out
    rows = c.data
    for i in range(rows.shape[0]):
        q = _quality(plan, lost and i == 0)
        if sp.event_type is EventType.FEATURES_BINNED:
            payload: dict[str, Any] = {
                "feature": "spike_count",
                "unit": "count",
                "bin_ms": float(s.bin_ms or 0.0),
                "bin_index": first + i,
                "channel_count": len(s.channels),
                "counts": rows[i].astype(np.int64).tolist(),
            }
        elif sp.event_type is EventType.BEHAVIOR_SAMPLE:
            payload = {
                "quantity": s.quantity or "behavior",
                "dims": sp.labels,
                "unit": _common_unit(s),
                "values": rows[i].astype(np.float64).tolist(),
                "sample_index": first + i,
                "valid": True,
            }
        else:  # intent.kinematics from the plugin's external decoder
            payload = {
                "quantity": s.quantity or "decoder_output",
                "dims": sp.labels,
                "unit": _common_unit(s),
                "values": rows[i].astype(np.float64).tolist(),
                "space": f"{plan.manifest.name}:{s.model_id}"[:64],
            }
        out.append(EventDraft(sp.event_type, payload, q, prov, _ns(ts[i])))  # type: ignore[arg-type]
    return out
