"""Standardized event envelope, schema 1.x.

This module is the normative definition of what applications receive. It has
no I/O. Provenance rules (ARCHITECTURE.md §4.2) are enforced here so that no
producer — simulator, replay, or a future decoder — can blur the line between
raw signal, behavioral labels, simulated intents and decoded intents.
"""

from __future__ import annotations

import sys
from enum import StrEnum
from typing import Annotated, Any, Literal, Self

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    SerializerFunctionWrapHandler,
    StrictBool,
    TypeAdapter,
    ValidatorFunctionWrapHandler,
    WrapSerializer,
    WrapValidator,
    model_validator,
)

from brainos.contracts.capabilities import Capability, EventType, capability_for

SCHEMA_VERSION = "1.4"
# 1.1: features.binned, behavior.sample, intent.kinematics
# 1.2: features.vector; recording.frame unit "arbitrary" (source did not state a known unit)
SCHEMA_MAJOR = 1

FiniteFloat = Annotated[float, Field(allow_inf_nan=False)]
UnitFloat = Annotated[float, Field(ge=0.0, le=1.0, allow_inf_nan=False)]


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False, frozen=True)


# --------------------------------------------------------------------------- quality


class QualityFlag(StrEnum):
    SYNTHETIC = "synthetic"
    REPLAYED = "replayed"
    LOW_LINK_QUALITY = "low_link_quality"
    TIMESTAMP_REGRESSION = "timestamp_regression"
    SATURATED = "saturated"
    DROPPED_SAMPLES = "dropped_samples"


class Quality(_Strict):
    """Adapter-provided quality estimate. ``score`` is in [0, 1]; 1 = nominal."""

    score: UnitFloat
    flags: list[QualityFlag] = Field(default_factory=list, max_length=16)


# ------------------------------------------------------------------------ provenance


class ProvenanceKind(StrEnum):
    RAW_SIGNAL = "raw_signal"
    BEHAVIORAL_LABEL = "behavioral_label"
    SIMULATED_INTENT = "simulated_intent"
    DECODED_INTENT = "decoded_intent"
    DEVICE_REPORT = "device_report"
    RUNTIME = "runtime"
    PROCESSED_FEATURE = "processed_feature"  # 1.1: derived from neural data, not an intent


_INTENT_KINDS = frozenset({ProvenanceKind.SIMULATED_INTENT, ProvenanceKind.DECODED_INTENT})

ALLOWED_PROVENANCE: dict[EventType, frozenset[ProvenanceKind]] = {
    EventType.RECORDING_FRAME: frozenset({ProvenanceKind.RAW_SIGNAL}),
    EventType.RECORDING_ANNOTATION: frozenset({ProvenanceKind.BEHAVIORAL_LABEL}),
    EventType.INTENT_POINTER: _INTENT_KINDS,
    EventType.INTENT_SELECTION: _INTENT_KINDS,
    EventType.INTENT_TEXT: _INTENT_KINDS,
    EventType.TELEMETRY_SAMPLE: frozenset({ProvenanceKind.DEVICE_REPORT}),
    EventType.DEVICE_STATUS: frozenset({ProvenanceKind.DEVICE_REPORT, ProvenanceKind.RUNTIME}),
    EventType.FEATURES_BINNED: frozenset({ProvenanceKind.PROCESSED_FEATURE}),
    EventType.FEATURES_VECTOR: frozenset({ProvenanceKind.PROCESSED_FEATURE}),
    EventType.BEHAVIOR_SAMPLE: frozenset({ProvenanceKind.BEHAVIORAL_LABEL}),
    EventType.INTENT_KINEMATICS: _INTENT_KINDS,
    EventType.INTENT_NAVIGATE: _INTENT_KINDS,
    EventType.CONTROL_STATE: frozenset({ProvenanceKind.RUNTIME}),
}


class Provenance(_Strict):
    kind: ProvenanceKind
    adapter: str = Field(pattern=r"^[a-z0-9_.\-]+@\d+\.\d+\.\d+$", max_length=128)
    synthetic: bool
    model_id: str | None = Field(default=None, min_length=1, max_length=128)
    origin: str = Field(min_length=1, max_length=128)
    replayed: bool = False
    # 1.4: who produced a decoded_intent: a model BrainOS trained/loaded ("brainos"), an
    # external system's live decoder ("external", e.g. a device's own decoder), or the
    # recorded outputs of a research system's original online decoder ("historical").
    model_origin: Literal["brainos", "external", "historical"] | None = None


def check_provenance(event_type: EventType, provenance: Provenance) -> None:
    """Raise ValueError if ``provenance`` is not allowed for ``event_type``."""
    allowed = ALLOWED_PROVENANCE[event_type]
    if provenance.kind not in allowed:
        raise ValueError(
            f"provenance kind '{provenance.kind}' is not allowed for '{event_type}' "
            f"(allowed: {sorted(k.value for k in allowed)})"
        )
    if provenance.kind is ProvenanceKind.SIMULATED_INTENT and not provenance.synthetic:
        raise ValueError("simulated_intent must have synthetic=true")
    if provenance.kind is ProvenanceKind.DECODED_INTENT and not provenance.model_id:
        raise ValueError("decoded_intent requires provenance.model_id")
    if provenance.kind is not ProvenanceKind.DECODED_INTENT and provenance.model_id is not None:
        raise ValueError("model_id is only valid for decoded_intent")
    if provenance.kind is not ProvenanceKind.DECODED_INTENT and provenance.model_origin is not None:
        raise ValueError("model_origin is only valid for decoded_intent")
    if provenance.model_origin == "historical" and not provenance.replayed:
        raise ValueError("historical decoder outputs are recorded data: replayed must be true")


# -------------------------------------------------------------------------- payloads


def _ndarray(value: object) -> Any:
    """``value`` if it is a numpy array, else None (numpy is never imported from here: the
    base SDK install has no numpy, and an array can only exist if numpy is loaded)."""
    np = sys.modules.get("numpy")
    return value if np is not None and isinstance(value, np.ndarray) else None


def _samples_in(value: Any, handler: ValidatorFunctionWrapHandler) -> Any:
    """``samples`` given as a 2-D numpy array (channels x samples): an in-process fast path
    for adapters (no per-value Python objects). The wire format and JSON Schema are those of
    ``list[list[FiniteFloat]]``. A valid real-valued 2-D array is kept as an owned, read-only,
    C-ordered float64 copy; anything else, including an array with a NaN/Inf, is validated
    by the list path (``tolist()``), so accept/reject decisions and errors are identical."""
    arr = _ndarray(value)
    if arr is None:
        return handler(value)
    np = sys.modules["numpy"]
    if arr.ndim == 2 and arr.dtype.kind in "biuf":
        out = np.array(arr, dtype=np.float64, order="C")
        if np.isfinite(out).all():
            out.flags.writeable = False
            return out
    return handler(arr.tolist())


def _samples_out(value: Any, handler: SerializerFunctionWrapHandler) -> Any:
    arr = _ndarray(value)
    return handler(value if arr is None else arr.tolist())


# list[list[FiniteFloat]] on the wire and in the schema; may hold a float64 ndarray in-process
FrameSamples = Annotated[
    list[list[FiniteFloat]], WrapValidator(_samples_in), WrapSerializer(_samples_out)
]


class RecordingFramePayload(_Strict):
    sample_rate_hz: float = Field(gt=0, le=100_000, allow_inf_nan=False)
    channel_count: int = Field(ge=1, le=1024)
    first_sample_index: int = Field(ge=0)
    # "uV": microvolts (converted exactly from the source's stated unit).
    # "arbitrary" (1.2): the source did not state a physical unit BrainOS knows; values are
    # passed through unscaled and must not be interpreted as microvolts.
    unit: Literal["uV", "arbitrary"] = "uV"
    # samples[channel][sample]. In-process it may be a read-only float64 numpy array of shape
    # (channels, samples) (see _samples_in); it serializes identically either way.
    samples: FrameSamples = Field(description="samples[channel][sample]")

    @model_validator(mode="after")
    def _shape(self) -> Self:
        shape = getattr(self.samples, "shape", None)
        if shape is not None:  # numpy array: rectangular by construction
            if shape[0] != self.channel_count:
                raise ValueError(
                    f"samples has {shape[0]} channels, channel_count={self.channel_count}"
                )
            lengths = {int(shape[1])}
        else:
            if len(self.samples) != self.channel_count:
                raise ValueError(
                    f"samples has {len(self.samples)} channels, channel_count={self.channel_count}"
                )
            lengths = {len(ch) for ch in self.samples}
        if len(lengths) != 1:
            raise ValueError("all channels must have the same number of samples")
        n = lengths.pop()
        if not 1 <= n <= 10_000:
            raise ValueError("samples per channel must be in [1, 10000]")
        return self


class RecordingAnnotationPayload(_Strict):
    label: str = Field(min_length=1, max_length=128)
    value: FiniteFloat | str | None = None
    duration_ms: float | None = Field(default=None, ge=0, allow_inf_nan=False)


class PointerIntentPayload(_Strict):
    """Velocity in workspace units per second; the workspace is the unit square."""

    vx: float = Field(ge=-10, le=10, allow_inf_nan=False)
    vy: float = Field(ge=-10, le=10, allow_inf_nan=False)


class SelectionIntentPayload(_Strict):
    """Discrete action. ``primary`` = select the highlighted item; 1.3 adds ``activate``
    (trigger / confirm) and ``cancel`` (back / undo)."""

    action: Literal["primary", "activate", "cancel"] = "primary"
    confidence: UnitFloat


class NavigateIntentPayload(_Strict):
    """Discrete navigation (schema 1.4): move a highlight/focus, not a cursor."""

    direction: Literal["up", "down", "left", "right", "next", "previous"]
    confidence: UnitFloat


class ControlStatePayload(_Strict):
    """Runtime notice to ONE application (schema 1.4): whether decoded command output is
    currently delivered to it. ``active: false`` = stop acting and enter a safe state."""

    active: StrictBool  # a safety signal: no coercion of "no"/"0" to False
    capabilities: list[str] = Field(default_factory=list, max_length=16)
    reason: str = Field(max_length=256)


class TextIntentPayload(_Strict):
    text: str = Field(min_length=1, max_length=64)
    mode: Literal["character", "word"]
    confidence: UnitFloat


class TelemetryMetric(_Strict):
    name: str = Field(pattern=r"^[a-z][a-z0-9_]{0,47}$")
    value: FiniteFloat
    unit: str = Field(max_length=16)


class TelemetrySamplePayload(_Strict):
    metrics: list[TelemetryMetric] = Field(min_length=1, max_length=64)


class DeviceState(StrEnum):
    CONNECTED = "connected"
    STREAMING = "streaming"
    PAUSED = "paused"
    RECONNECTING = "reconnecting"
    DISCONNECTED = "disconnected"
    ERROR = "error"
    ENDED = "ended"


class DeviceStatusPayload(_Strict):
    state: DeviceState
    detail: str = Field(default="", max_length=512)


class FeaturesBinnedPayload(_Strict):
    """One time bin of a processed neural feature per channel (schema 1.1).

    ``counts[c]`` is the feature value for channel ``c`` in the bin that *ends* at the
    envelope's ``device_timestamp_ns`` and spans ``bin_ms`` before it.
    """

    feature: Literal["threshold_crossing_count", "spike_count"]
    unit: Literal["count"] = "count"
    bin_ms: float = Field(gt=0, le=10_000, allow_inf_nan=False)
    bin_index: int = Field(ge=0)
    channel_count: int = Field(ge=1, le=4096)
    counts: list[Annotated[int, Field(ge=0)]]

    @model_validator(mode="after")
    def _shape(self) -> Self:
        if len(self.counts) != self.channel_count:
            raise ValueError(
                f"counts has {len(self.counts)} values, channel_count={self.channel_count}"
            )
        return self


class FeaturesVectorPayload(_Strict):
    """One time bin of a continuous-valued neural feature per channel (schema 1.2).

    E.g. log band power. The bin ends at the envelope's ``device_timestamp_ns``.
    """

    # "spike_band_power" (1.4): mean power of the spike band (e.g. 250-5000 Hz) per bin, the
    # intracortical feature recorded by many research systems.
    feature: Literal["band_power", "log_band_power", "spike_band_power"]
    unit: str = Field(max_length=32, description="e.g. 'uV^2', 'log10(uV^2)', 'log10(arbitrary^2)'")
    band_hz: tuple[FiniteFloat, FiniteFloat] | None = None
    bin_ms: float = Field(gt=0, le=10_000, allow_inf_nan=False)
    bin_index: int = Field(ge=0)
    channel_count: int = Field(ge=1, le=4096)
    values: list[FiniteFloat]

    @model_validator(mode="after")
    def _shape(self) -> Self:
        if len(self.values) != self.channel_count:
            n = len(self.values)
            raise ValueError(f"values has {n} entries, channel_count={self.channel_count}")
        if self.band_hz is not None and not 0 <= self.band_hz[0] < self.band_hz[1]:
            raise ValueError("band_hz must be (low, high) with 0 <= low < high")
        return self


class _VectorPayload(_Strict):
    quantity: str = Field(min_length=1, max_length=64)
    dims: list[Annotated[str, Field(min_length=1, max_length=32)]] = Field(
        min_length=1, max_length=64
    )
    unit: str = Field(max_length=32)
    values: list[FiniteFloat]

    @model_validator(mode="after")
    def _shape(self) -> Self:
        if len(self.values) != len(self.dims):
            raise ValueError(f"values has {len(self.values)} entries, dims has {len(self.dims)}")
        return self


class BehaviorSamplePayload(_VectorPayload):
    """Recorded behavioral ground truth (schema 1.1). Never an intent.

    ``valid`` is false where the dataset marks the sample as excluded from
    training/evaluation (e.g. FALCON ``eval_mask``).
    """

    sample_index: int = Field(ge=0)
    valid: bool = True


class KinematicIntentPayload(_VectorPayload):
    """Multi-dimensional movement intent (schema 1.1), in the source's own dimension space."""

    space: str = Field(min_length=1, max_length=64, description="e.g. falcon_h1_7dof")


# -------------------------------------------------------------------------- envelope

SESSION_ID_PATTERN = r"^ses_[A-Za-z0-9]{6,64}$"
DEVICE_ID_PATTERN = r"^[a-z0-9][a-z0-9_.:\-]{0,63}$"


class _EnvelopeBase(_Strict):
    schema_version: str = Field(pattern=r"^\d+\.\d+$")
    session_id: str = Field(pattern=SESSION_ID_PATTERN)
    device_id: str = Field(pattern=DEVICE_ID_PATTERN)
    seq: int = Field(ge=0)
    timestamp_ns: int = Field(ge=0, description="Runtime wall clock at ingest, UTC ns")
    device_timestamp_ns: int | None = Field(
        default=None, ge=0, description="Device clock from the native packet, if any"
    )
    capability: Capability
    quality: Quality
    provenance: Provenance

    @model_validator(mode="after")
    def _contract(self) -> Self:
        major = int(self.schema_version.split(".", 1)[0])
        if major != SCHEMA_MAJOR:
            raise ValueError(
                f"unsupported schema major version {major} (supported: {SCHEMA_MAJOR})"
            )
        event_type = EventType(getattr(self, "event_type"))  # noqa: B009 - defined by subclasses
        expected = capability_for(event_type)
        if self.capability is not expected:
            raise ValueError(
                f"capability '{self.capability}' does not match event type "
                f"'{event_type}' (expected '{expected}')"
            )
        check_provenance(event_type, self.provenance)
        return self


class RecordingFrameEvent(_EnvelopeBase):
    event_type: Literal[EventType.RECORDING_FRAME]
    payload: RecordingFramePayload


class RecordingAnnotationEvent(_EnvelopeBase):
    event_type: Literal[EventType.RECORDING_ANNOTATION]
    payload: RecordingAnnotationPayload


class PointerIntentEvent(_EnvelopeBase):
    event_type: Literal[EventType.INTENT_POINTER]
    payload: PointerIntentPayload


class SelectionIntentEvent(_EnvelopeBase):
    event_type: Literal[EventType.INTENT_SELECTION]
    payload: SelectionIntentPayload


class TextIntentEvent(_EnvelopeBase):
    event_type: Literal[EventType.INTENT_TEXT]
    payload: TextIntentPayload


class TelemetrySampleEvent(_EnvelopeBase):
    event_type: Literal[EventType.TELEMETRY_SAMPLE]
    payload: TelemetrySamplePayload


class DeviceStatusEvent(_EnvelopeBase):
    event_type: Literal[EventType.DEVICE_STATUS]
    payload: DeviceStatusPayload


class FeaturesVectorEvent(_EnvelopeBase):
    event_type: Literal[EventType.FEATURES_VECTOR]
    payload: FeaturesVectorPayload


class FeaturesBinnedEvent(_EnvelopeBase):
    event_type: Literal[EventType.FEATURES_BINNED]
    payload: FeaturesBinnedPayload


class BehaviorSampleEvent(_EnvelopeBase):
    event_type: Literal[EventType.BEHAVIOR_SAMPLE]
    payload: BehaviorSamplePayload


class KinematicIntentEvent(_EnvelopeBase):
    event_type: Literal[EventType.INTENT_KINEMATICS]
    payload: KinematicIntentPayload


class NavigateIntentEvent(_EnvelopeBase):
    event_type: Literal[EventType.INTENT_NAVIGATE]
    payload: NavigateIntentPayload


class ControlStateEvent(_EnvelopeBase):
    event_type: Literal[EventType.CONTROL_STATE]
    payload: ControlStatePayload


EventEnvelope = Annotated[
    RecordingFrameEvent
    | RecordingAnnotationEvent
    | PointerIntentEvent
    | SelectionIntentEvent
    | TextIntentEvent
    | TelemetrySampleEvent
    | DeviceStatusEvent
    | FeaturesBinnedEvent
    | FeaturesVectorEvent
    | BehaviorSampleEvent
    | KinematicIntentEvent
    | NavigateIntentEvent
    | ControlStateEvent,
    Field(discriminator="event_type"),
]

ENVELOPE_ADAPTER: TypeAdapter[EventEnvelope] = TypeAdapter(EventEnvelope)

PAYLOAD_MODELS: dict[EventType, type[BaseModel]] = {
    EventType.RECORDING_FRAME: RecordingFramePayload,
    EventType.RECORDING_ANNOTATION: RecordingAnnotationPayload,
    EventType.INTENT_POINTER: PointerIntentPayload,
    EventType.INTENT_SELECTION: SelectionIntentPayload,
    EventType.INTENT_TEXT: TextIntentPayload,
    EventType.TELEMETRY_SAMPLE: TelemetrySamplePayload,
    EventType.DEVICE_STATUS: DeviceStatusPayload,
    EventType.FEATURES_BINNED: FeaturesBinnedPayload,
    EventType.FEATURES_VECTOR: FeaturesVectorPayload,
    EventType.BEHAVIOR_SAMPLE: BehaviorSamplePayload,
    EventType.INTENT_KINEMATICS: KinematicIntentPayload,
    EventType.INTENT_NAVIGATE: NavigateIntentPayload,
    EventType.CONTROL_STATE: ControlStatePayload,
}


def parse_envelope(data: Any) -> EventEnvelope:
    """Validate a decoded JSON object (dict) as an event envelope."""
    return ENVELOPE_ADAPTER.validate_python(data)


def parse_envelope_json(raw: str | bytes) -> EventEnvelope:
    return ENVELOPE_ADAPTER.validate_json(raw)


def envelope_json_schema() -> dict[str, Any]:
    schema = ENVELOPE_ADAPTER.json_schema()
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["$id"] = f"https://brainos.local/schemas/event-envelope.v{SCHEMA_MAJOR}.json"
    schema["title"] = f"BrainOS EventEnvelope {SCHEMA_VERSION}"
    return schema
