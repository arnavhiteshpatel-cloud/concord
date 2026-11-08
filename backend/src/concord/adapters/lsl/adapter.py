"""Lab Streaming Layer (LSL) adapter — read-only, built on the official liblsl (pylsl).

A Concord LSL *source* is one signal stream plus, optionally, a behavior stream and a
marker stream from the same experiment. All timestamps are expressed on the **signal
stream's source clock** (auxiliary streams are mapped with liblsl ``time_correction``), so
neural data and behavioral labels can be aligned for calibration.

Signal-stream interpretation (never guessed silently; recorded in metadata):
  * type in SPIKE_COUNT_TYPES (Concord convention, e.g. "SpikeCounts") or a declared
    ``<concord><feature>spike_count`` -> ``features.binned`` (provenance processed_feature;
    values must be non-negative integers; bin = 1 / nominal_srate)
  * otherwise (numeric, regular rate)  -> ``recording.frame`` (provenance raw_signal) in µV if
    every channel states a known voltage unit, else unit ``arbitrary``.

Liveness: LSL cannot tell hardware from file playback or simulation. Streams are
``kind=stream`` unless the publisher *declares* itself prerecorded or synthetic.
"""

from __future__ import annotations

import asyncio
import contextlib
import itertools
import logging
import time
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any, Literal

import numpy as np
from numpy.typing import NDArray
from pydantic import BaseModel, ConfigDict, Field

from concord.adapters.base import (
    DeviceAdapter,
    DeviceLinkError,
    EventDraft,
    NativePacket,
    PacketDecodeError,
    frame_samples_limit,
)
from concord.adapters.lsl import discovery
from concord.adapters.lsl.metadata import (
    MARKER_TYPES,
    SPIKE_COUNT_TYPES,
    StreamMeta,
    UnitPlan,
    plan_units,
)
from concord.contracts.capabilities import Capability, CapabilityDescriptor, EventType
from concord.contracts.events import Provenance, ProvenanceKind, Quality, QualityFlag
from concord.contracts.protocol import DeviceDescriptor, DeviceKind

log = logging.getLogger(__name__)

ADAPTER = "concord.lsl@0.1.0"
MAX_FRAME_SAMPLES = 2_000  # per recording.frame (contract max 10 000; smaller keeps WS frames sane)
TIME_CORRECTION_PERIOD_S = 5.0
JITTER_TOLERANCE_S = 0.002

DTYPES: dict[str, Any] = {
    "float32": np.float32,
    "double64": np.float64,
    "int32": np.int32,
    "int16": np.int16,
    "int8": np.int8,
    "int64": np.int64,
}

Interpretation = Literal["raw", "spike_counts"]


class LSLSourceSpec(BaseModel):
    """What to connect: one signal stream, optional behavior and marker streams."""

    model_config = ConfigDict(arbitrary_types_allowed=True, frozen=True)

    device_id: str
    signal: StreamMeta
    behavior: StreamMeta | None = None
    markers: StreamMeta | None = None
    max_buflen_s: int = Field(default=30, ge=1, le=360)
    open_timeout_s: float = Field(default=5.0, gt=0)
    stall_timeout_s: float | None = Field(
        default=None, gt=0, description="default max(2 s, 50 samples)"
    )
    poll_interval_s: float = Field(default=0.005, gt=0, le=0.1)
    max_chunk_samples: int = Field(default=8192, ge=16)


def interpret(meta: StreamMeta) -> Interpretation:
    if meta.is_string:
        raise ValueError(f"stream {meta.name!r} carries strings; use it as a marker stream")
    if not meta.regular:
        raise ValueError(
            f"stream {meta.name!r} has an irregular rate (nominal_srate=0); "
            "only regularly sampled streams can be the signal stream"
        )
    if meta.type.lower() in SPIKE_COUNT_TYPES or meta.declaration.feature in {
        "spike_count",
        "threshold_crossing_count",
    }:
        return "spike_counts"
    return "raw"


@dataclass
class _Stream:
    role: Literal["signal", "behavior", "markers"]
    meta: StreamMeta
    inlet: Any = None
    buffer: NDArray[Any] | None = None
    correction_s: float = 0.0
    received: int = 0
    last_ts: float | None = None
    last_rx_monotonic: float = 0.0
    gaps: int = 0
    est_missing: int = 0
    pulls: int = 0


@dataclass
class LSLStats:
    chunks: int = 0
    samples: int = 0
    gaps: int = 0
    est_missing_samples: int = 0
    lost: int = 0
    stalls: int = 0
    discarded_while_paused: int = 0
    corrections: dict[str, float] = field(default_factory=dict)


class LSLAdapter(DeviceAdapter):
    def __init__(self, spec: LSLSourceSpec) -> None:
        self.spec = spec
        self._interp: Interpretation = interpret(spec.signal)
        self._streams: list[_Stream] = [_Stream("signal", spec.signal)]
        if spec.behavior is not None:
            if spec.behavior.is_string:
                raise ValueError("behavior stream must be numeric")
            self._streams.append(_Stream("behavior", spec.behavior))
        if spec.markers is not None:
            if not spec.markers.is_string and spec.markers.type.lower() not in MARKER_TYPES:
                raise ValueError("marker stream must carry strings (LSL 'Markers' convention)")
            self._streams.append(_Stream("markers", spec.markers))
        self._open = False
        self._paused = False
        self._units: UnitPlan = plan_units(spec.signal.channels, spec.signal.channel_count)
        self.stats = LSLStats()
        self._corr_task: asyncio.Task[None] | None = None
        self.descriptor = self._build_descriptor()
        self._provenance()

    # ------------------------------------------------------------------ descriptor
    @property
    def signal(self) -> StreamMeta:
        return self._streams[0].meta

    def _kind(self) -> tuple[DeviceKind, bool]:
        d = self.signal.declaration
        if d.synthetic:
            return DeviceKind.SIMULATED, True
        if d.prerecorded:
            return DeviceKind.REPLAY, False
        return DeviceKind.STREAM, False

    def _build_descriptor(self) -> DeviceDescriptor:
        s = self.signal
        labels = [c.label or f"ch{c.index}" for c in s.channels] if s.channels else []
        caps: list[CapabilityDescriptor] = []
        if self._interp == "raw":
            caps.append(
                CapabilityDescriptor(
                    capability=Capability.RECORDING,
                    params={
                        "channel_count": s.channel_count,
                        "sample_rate_hz": s.nominal_srate,
                        "unit": self._units.unit,
                        "channel_labels": labels,
                        "stream_type": s.type,
                        "channel_format": s.channel_format,
                    },
                    description="LSL signal stream as raw samples"
                    + ("" if self._units.unit == "uV" else " (unit unknown: 'arbitrary')"),
                )
            )
        else:
            caps.append(
                CapabilityDescriptor(
                    capability=Capability.NEURAL_FEATURES,
                    params={
                        "feature": self.signal.declaration.feature or "spike_count",
                        "bin_ms": 1000.0 / s.nominal_srate,
                        "rate_hz": s.nominal_srate,
                        "channel_count": s.channel_count,
                        "channel_labels": labels,
                    },
                    description="Pre-binned spike counts published over LSL",
                )
            )
        markers = next((x for x in self._streams if x.role == "markers"), None)
        if markers is not None and self._interp != "raw":
            caps.append(
                CapabilityDescriptor(
                    capability=Capability.RECORDING,
                    params={"annotations_only": True},
                    description="LSL marker stream as recording.annotation",
                )
            )
        beh = next((x for x in self._streams if x.role == "behavior"), None)
        if beh is not None:
            b = beh.meta
            caps.append(
                CapabilityDescriptor(
                    capability=Capability.BEHAVIOR,
                    params={
                        "quantity": b.declaration.quantity or b.type.lower() or "behavior",
                        "dims": [c.label or f"dim{c.index}" for c in b.channels]
                        or [f"dim{i}" for i in range(b.channel_count)],
                        "unit": _behavior_unit(b),
                        "rate_hz": b.nominal_srate,
                    },
                    description=f"LSL stream {b.name!r} as behavioral ground truth",
                )
            )
        caps.append(CapabilityDescriptor(capability=Capability.DEVICE_STATUS))
        kind, synthetic = self._kind()
        extra = {
            DeviceKind.REPLAY: " — declared prerecorded",
            DeviceKind.SIMULATED: " — declared synthetic",
        }
        return DeviceDescriptor(
            device_id=self.spec.device_id,
            display_name=f"LSL · {s.name} ({s.type}){extra.get(kind, '')}",
            kind=kind,
            adapter=ADAPTER,
            description=(
                f"Lab Streaming Layer stream {s.name!r} from {s.hostname} "
                f"(source_id {s.source_id or 'not set'}). "
                + (
                    "Origin as declared by the publisher."
                    if kind is not DeviceKind.STREAM
                    else "Live stream; Concord cannot verify whether it comes from hardware, "
                    "a file player or a simulator."
                )
            ),
            native_format=f"LSL {s.channel_format} x {s.channel_count} @ {s.nominal_srate:g} Hz",
            capabilities=caps,
            synthetic=synthetic,
        )

    def _provenance(self) -> None:
        d = self.signal.declaration
        synthetic = bool(d.synthetic)
        replayed = bool(d.prerecorded)
        origin = d.origin or f"lsl:{self.signal.name}@{self.signal.hostname}"

        def p(kind: ProvenanceKind) -> Provenance:
            return Provenance(
                kind=kind,
                adapter=ADAPTER,
                synthetic=synthetic,
                origin=origin[:128],
                replayed=replayed,
            )

        self._p_raw = p(ProvenanceKind.RAW_SIGNAL)
        self._p_feat = p(ProvenanceKind.PROCESSED_FEATURE)
        self._p_beh = p(ProvenanceKind.BEHAVIORAL_LABEL)
        flags = []
        if synthetic:
            flags.append(QualityFlag.SYNTHETIC)
        if replayed:
            flags.append(QualityFlag.REPLAYED)
        self._flags = flags

    @property
    def origin(self) -> str:
        return self._p_raw.origin

    # ------------------------------------------------------------------ lifecycle
    async def open(self) -> None:
        try:
            for st in self._streams:
                await asyncio.to_thread(self._open_stream, st)
        except DeviceLinkError:
            await self.close()
            raise
        except Exception as exc:  # liblsl errors (timeouts, lost) during setup
            await self.close()
            raise DeviceLinkError(f"LSL open failed: {type(exc).__name__}: {exc}") from exc
        self._units = plan_units(self.signal.channels, self.signal.channel_count)
        self._interp = interpret(self.signal)
        self.descriptor = self._build_descriptor()
        self._provenance()
        now = time.monotonic()
        for st in self._streams:
            st.last_rx_monotonic = now
        self._open = True
        if self._corr_task is None or self._corr_task.done():
            self._corr_task = asyncio.create_task(
                self._refresh_corrections(), name="lsl-time-correction"
            )
        log.info("LSL source %s opened (%s)", self.spec.device_id, discovery.library_info())

    def _open_stream(self, st: _Stream) -> None:
        pylsl = discovery._pylsl()
        info = discovery.resolve(st.meta, timeout=self.spec.open_timeout_s)
        if info is None:
            raise DeviceLinkError(
                f"LSL stream {st.meta.name!r} (source_id {st.meta.source_id or '-'}, host "
                f"{st.meta.hostname}) not found on the network"
            )
        inlet = pylsl.StreamInlet(
            info,
            max_buflen=self.spec.max_buflen_s,
            max_chunklen=0,
            recover=False,  # we detect loss explicitly and let the runtime reconnect
            processing_flags=0,  # raw source timestamps; clock offset tracked separately
        )
        full = inlet.info(timeout=self.spec.open_timeout_s)
        meta = discovery.meta_from_info(full, with_desc=True)
        old = st.meta
        if (meta.channel_count, meta.nominal_srate, meta.channel_format) != (
            old.channel_count,
            old.nominal_srate,
            old.channel_format,
        ):
            inlet.close_stream()
            raise DeviceLinkError(
                f"LSL stream {old.name!r} changed configuration "
                f"({old.channel_count} ch @ {old.nominal_srate:g} Hz {old.channel_format} -> "
                f"{meta.channel_count} ch @ {meta.nominal_srate:g} Hz {meta.channel_format}); "
                "re-discover and reconnect"
            )
        inlet.open_stream(timeout=self.spec.open_timeout_s)
        st.correction_s = float(inlet.time_correction(timeout=self.spec.open_timeout_s))
        st.inlet = inlet
        st.meta = meta
        if not meta.is_string:
            dtype = DTYPES.get(meta.channel_format)
            if dtype is None:
                raise DeviceLinkError(f"unsupported LSL channel format {meta.channel_format}")
            st.buffer = np.empty((self.spec.max_chunk_samples, meta.channel_count), dtype=dtype)

    async def close(self) -> None:
        self._open = False
        if self._corr_task is not None:
            self._corr_task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await self._corr_task
            self._corr_task = None
        for st in self._streams:
            inlet, st.inlet = st.inlet, None
            if inlet is not None:
                with contextlib.suppress(Exception):
                    inlet.close_stream()
                del inlet

    def set_paused(self, paused: bool) -> None:
        self._paused = paused

    async def _refresh_corrections(self) -> None:
        while True:
            await asyncio.sleep(TIME_CORRECTION_PERIOD_S)
            for st in self._streams:
                inlet = st.inlet
                if inlet is None:
                    continue
                try:
                    st.correction_s = float(await asyncio.to_thread(inlet.time_correction, 1.0))
                except Exception as exc:  # timeout during loss: keep the last value
                    log.debug("time_correction failed for %s: %s", st.meta.name, exc)
            self.stats.corrections = {st.meta.name: st.correction_s for st in self._streams}

    # ------------------------------------------------------------------ reading
    def _stall_timeout(self) -> float:
        if self.spec.stall_timeout_s is not None:
            return self.spec.stall_timeout_s
        return max(2.0, 50.0 / self.signal.nominal_srate)

    def _pull(self, st: _Stream) -> tuple[Any, list[float]] | None:
        lost = discovery.lost_error()
        try:
            if st.buffer is not None:
                _, ts = st.inlet.pull_chunk(
                    timeout=0.0, max_samples=st.buffer.shape[0], dest_obj=st.buffer
                )
                if not ts:
                    return None
                return st.buffer[: len(ts)].copy(), list(ts)
            data, ts = st.inlet.pull_chunk(timeout=0.0, max_samples=1024)
            if not ts:
                return None
            return data, list(ts)
        except lost as exc:
            self.stats.lost += 1
            raise DeviceLinkError(f"LSL stream {st.meta.name!r} lost (publisher gone)") from exc

    async def read(self) -> NativePacket:
        sig_period = 1.0 / self.signal.nominal_srate
        while True:
            if not self._open or self._streams[0].inlet is None:
                raise DeviceLinkError(f"{self.spec.device_id}: not open")
            parts: dict[str, Any] = {}
            now = time.monotonic()
            for st in self._streams:
                got = self._pull(st)
                if got is None:
                    continue
                st.last_rx_monotonic = now
                st.pulls += 1
                data, ts = got
                if self._paused:
                    self.stats.discarded_while_paused += len(ts)
                    st.last_ts = ts[-1]
                    continue
                part: dict[str, Any] = {"data": data, "ts": ts, "first_index": st.received}
                if st.role == "signal":
                    gap_missing = 0
                    gap_starts: list[int] = []  # indices in this chunk that follow a gap
                    prev = st.last_ts
                    seq = [prev, *ts] if prev is not None else list(ts)
                    offset = 0 if prev is not None else 1
                    for k, (a, b) in enumerate(itertools.pairwise(seq)):
                        dt = b - a
                        if dt > 1.5 * sig_period and dt - sig_period > JITTER_TOLERANCE_S:
                            gap_missing += max(1, round(dt / sig_period) - 1)
                            gap_starts.append(k + offset)
                            st.gaps += 1
                            self.stats.gaps += 1
                    st.est_missing += gap_missing
                    self.stats.est_missing_samples += gap_missing
                    part["gap_missing"] = gap_missing
                    part["gap_starts"] = gap_starts
                    self.stats.samples += len(ts)
                    self.stats.chunks += 1
                else:
                    # map onto the signal stream's clock
                    part["offset_s"] = st.correction_s - self._streams[0].correction_s
                st.received += len(ts)
                st.last_ts = ts[-1]
                parts[st.role] = part
            if parts:
                return NativePacket(parts)
            if now - self._streams[0].last_rx_monotonic > self._stall_timeout():
                self.stats.stalls += 1
                raise DeviceLinkError(
                    f"no samples from LSL stream {self.signal.name!r} for "
                    f"{now - self._streams[0].last_rx_monotonic:.1f} s"
                )
            await asyncio.sleep(self.spec.poll_interval_s)

    # ------------------------------------------------------------------ normalize (pure)
    def normalize(self, packet: NativePacket) -> Sequence[EventDraft]:
        parts: dict[str, Any] = packet.data
        out: list[EventDraft] = []
        sig = parts.get("signal")
        if sig is not None:
            out.extend(self._signal_drafts(sig))
        beh = parts.get("behavior")
        if beh is not None:
            out.extend(self._behavior_drafts(beh))
        mk = parts.get("markers")
        if mk is not None:
            out.extend(self._marker_drafts(mk))
        return out

    def _quality(self, gap: bool) -> Quality:
        flags = list(self._flags)
        if gap:
            flags.append(QualityFlag.DROPPED_SAMPLES)
        return Quality(score=0.5 if gap else 1.0, flags=flags)

    def _signal_drafts(self, part: dict[str, Any]) -> list[EventDraft]:
        data = np.asarray(part["data"])
        ts: list[float] = part["ts"]
        first = int(part["first_index"])
        gap_starts: set[int] = set(part.get("gap_starts", []))
        s = self.signal
        if data.ndim != 2 or data.shape[1] != s.channel_count or data.shape[0] != len(ts):
            raise PacketDecodeError(
                f"LSL chunk shape {data.shape} does not match {s.channel_count} channels"
            )
        out: list[EventDraft] = []
        if self._interp == "spike_counts":
            if not np.all(np.isfinite(data)) or np.any(data < 0) or np.any(data != np.round(data)):
                raise PacketDecodeError(
                    "spike-count stream contains non-integer or negative values"
                )
            counts = data.astype(np.int64)
            bin_ms = 1000.0 / s.nominal_srate
            feature = (
                s.declaration.feature
                if s.declaration.feature in {"spike_count", "threshold_crossing_count"}
                else "spike_count"
            )
            for i in range(counts.shape[0]):
                out.append(
                    EventDraft(
                        EventType.FEATURES_BINNED,
                        {
                            "feature": feature,
                            "unit": "count",
                            "bin_ms": bin_ms,
                            "bin_index": first + i,
                            "channel_count": s.channel_count,
                            "counts": counts[i].tolist(),
                        },
                        self._quality(i in gap_starts),
                        self._p_feat,
                        _ns(ts[i]),
                    )
                )
            return out
        values = data.astype(np.float64)
        if not np.all(np.isfinite(values)):
            raise PacketDecodeError("LSL chunk contains NaN/Inf samples")
        if self._units.scales is not None:
            values = values * np.asarray(self._units.scales)
        # Each frame must be contiguous in time: split at every gap and at the size limit.
        n = values.shape[0]
        step = frame_samples_limit(s.channel_count, MAX_FRAME_SAMPLES)
        cuts = sorted({0, *gap_starts, *range(0, n, step)} - {n})
        for start, end in zip(cuts, [*cuts[1:], n], strict=True):
            block = values[start:end]
            out.append(
                EventDraft(
                    EventType.RECORDING_FRAME,
                    {
                        "sample_rate_hz": s.nominal_srate,
                        "channel_count": s.channel_count,
                        "first_sample_index": first + start,
                        "unit": self._units.unit,
                        # (channels, n) array view; the contract copies it (M5-E fast path)
                        "samples": block.T,
                    },
                    self._quality(start in gap_starts),
                    self._p_raw,
                    _ns(ts[start]),
                )
            )
        return out

    def _behavior_drafts(self, part: dict[str, Any]) -> list[EventDraft]:
        st = next(x for x in self._streams if x.role == "behavior")
        b = st.meta
        data = np.asarray(part["data"], dtype=np.float64)
        if data.ndim != 2 or data.shape[1] != b.channel_count:
            raise PacketDecodeError("behavior chunk shape mismatch")
        dims = [c.label or f"dim{c.index}" for c in b.channels] or [
            f"dim{i}" for i in range(b.channel_count)
        ]
        offset = float(part["offset_s"])
        out = []
        for i, row in enumerate(data):
            valid = bool(np.all(np.isfinite(row)))
            out.append(
                EventDraft(
                    EventType.BEHAVIOR_SAMPLE,
                    {
                        "quantity": b.declaration.quantity or b.type.lower() or "behavior",
                        "dims": dims,
                        "unit": _behavior_unit(b),
                        "values": [float(v) if np.isfinite(v) else 0.0 for v in row],
                        "sample_index": int(part["first_index"]) + i,
                        "valid": valid,
                    },
                    self._quality(False),
                    self._p_beh,
                    _ns(part["ts"][i] + offset),
                )
            )
        return out

    def _marker_drafts(self, part: dict[str, Any]) -> list[EventDraft]:
        offset = float(part["offset_s"])
        out = []
        for row, t in zip(part["data"], part["ts"], strict=True):
            text = str(row[0] if isinstance(row, list | tuple) and row else row).strip()
            if not text:
                continue
            out.append(
                EventDraft(
                    EventType.RECORDING_ANNOTATION,
                    {"label": text[:128], "value": None, "duration_ms": None},
                    self._quality(False),
                    self._p_beh,
                    _ns(t + offset),
                )
            )
        return out

    # ------------------------------------------------------------------ metadata
    def source_metadata(self) -> dict[str, Any]:
        def stream(st: _Stream) -> dict[str, Any]:
            m = st.meta
            return {
                "role": st.role,
                "name": m.name,
                "type": m.type,
                "source_id": m.source_id or None,
                "hostname": m.hostname,
                "uid": m.uid,
                "channel_count": m.channel_count,
                "nominal_srate": m.nominal_srate,
                "channel_format": m.channel_format,
                "manufacturer": m.manufacturer,
                "channels": [
                    {"index": c.index, "label": c.label, "unit": c.unit, "type": c.type}
                    for c in m.channels
                ],
                "channels_described": len(m.channels) == m.channel_count,
                "declared": {
                    "prerecorded": m.declaration.prerecorded,
                    "synthetic": m.declaration.synthetic,
                    "origin": m.declaration.origin,
                    "feature": m.declaration.feature,
                },
                "time_correction_s": st.correction_s,
                "received_samples": st.received,
                "gaps": st.gaps,
                "estimated_missing_samples": st.est_missing,
                "last_timestamp_s": st.last_ts,
            }

        notes = []
        if self._units.note:
            notes.append(self._units.note)
        notes.append(
            "Timestamps are LSL source timestamps of the signal stream (seconds on the "
            "publisher's local_clock); auxiliary streams are mapped onto that clock using "
            "liblsl time_correction."
        )
        notes.append(
            "Dropped samples are estimated from timestamp gaps (LSL carries no sequence numbers)."
        )
        kind, _ = self._kind()
        if kind is DeviceKind.STREAM:
            notes.append(
                "Liveness not verifiable: LSL cannot distinguish hardware from playback "
                "or simulation."
            )
        try:
            lib = discovery.library_info()
        except Exception:
            lib = "unknown"
        return {
            "protocol": "lsl",
            "library": lib,
            "device_id": self.spec.device_id,
            "interpretation": self._interp,
            "unit": self._units.unit,
            "streams": [stream(st) for st in self._streams],
            "stats": {
                "chunks": self.stats.chunks,
                "samples": self.stats.samples,
                "gaps": self.stats.gaps,
                "estimated_missing_samples": self.stats.est_missing_samples,
                "lost": self.stats.lost,
                "stalls": self.stats.stalls,
                "discarded_while_paused": self.stats.discarded_while_paused,
            },
            "notes": notes,
        }


def _ns(t: float) -> int:
    if t < 0:
        raise PacketDecodeError(f"negative LSL timestamp {t}")
    return round(t * 1e9)


def _behavior_unit(b: StreamMeta) -> str:
    units = {c.unit for c in b.channels if c.unit}
    if len(units) == 1:
        return next(iter(units))[:32]
    if not units:
        return "unspecified"
    return "mixed"
