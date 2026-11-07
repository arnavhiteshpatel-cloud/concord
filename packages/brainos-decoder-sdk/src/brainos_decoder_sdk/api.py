"""BrainOS decoder SDK — public API, version 1.0.

The ONLY interface a third-party decoder uses; it does not import BrainOS. A decoder turns
per-bin neural *features* (``features.binned`` / ``features.vector`` events computed by the
BrainOS pipeline or delivered by a source) into decoder outputs:

* ``continuous`` values (e.g. a 2-D velocity), optionally with a variance or covariance;
* ``classes``: class posteriors that sum to 1 (e.g. rest / left / right);
* ``event``: per-event probabilities in [0, 1] (e.g. ``click``).

BrainOS publishes the outputs as ``intent.kinematics`` (provenance ``decoded_intent`` with
the model id). They never reach applications as commands unless the operator enables the
command router and authorizes the application.

Two ways to provide a decoder:

1. **A decoder plugin**: a :class:`Decoder` subclass with a class attribute ``manifest``,
   exposed in the ``brainos.decoders`` entry-point group of an installed distribution::

       [project.entry-points."brainos.decoders"]
       my-decoder = "my_package.decoder:MyDecoder"

2. **A model file** in a supported, safe format (ONNX, scikit-learn via skops, TorchScript,
   a PyTorch ``state_dict`` in safetensors) next to a manifest JSON
   (``<model id>.manifest.json``) in BrainOS's models directory. BrainOS loads it with the
   loaders in :mod:`brainos_decoder_sdk.formats`.

Both run in a separate *decoder host* process (``python -m brainos_decoder_sdk.host``):
fault isolation, not a security sandbox (see docs/DECODER_SDK.md).

Rules a decoder must follow (the host checks them on every step):

* Declare what the model was trained on: modality, inputs (feature, bin, channels and their
  labels, unit), preprocessing, the participant/source and sessions, outputs. BrainOS refuses
  to run a model on data that does not match, and never reorders, rescales or remaps
  channels silently.
* ``step()`` is causal: it may use the current and earlier bins only.
* Outputs have the declared shape and are finite; posteriors sum to 1; probabilities lie in
  [0, 1].
"""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

import numpy as np
from numpy.typing import NDArray

API_VERSION = "1.0"
ENTRY_POINT_GROUP = "brainos.decoders"
MANIFEST_SCHEMA = "brainos.decoder-manifest/1"
MODEL_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:\-]{0,95}$")
FEATURE_EVENTS = ("features.binned", "features.vector")
# feature names per event type (BrainOS contract; features.vector names grow with the contract)
BINNED_FEATURES = frozenset({"spike_count", "threshold_crossing_count"})

FloatArray = NDArray[np.float64]


class Modality(StrEnum):
    """Recording modality (same values as the BrainOS contract)."""

    EEG = "eeg"
    MEG = "meg"
    EMG = "emg"
    ECOG = "ecog"
    SEEG = "seeg"
    INTRACORTICAL = "intracortical"
    OTHER = "other"


class OutputKind(StrEnum):
    CONTINUOUS = "continuous"  # real values per dim (e.g. velocity)
    CLASSES = "classes"  # class posteriors, one per class, summing to 1
    EVENT = "event"  # independent event probabilities in [0, 1] (e.g. click)


class Confidence(StrEnum):
    """What ``DecodeOutput.confidence`` means."""

    NONE = "none"  # no confidence is reported
    POSTERIOR = "posterior"  # the values themselves are probabilities (classes / event)
    VARIANCE = "variance"  # confidence = per-dim variance, shape (dims,)
    COVARIANCE = "covariance"  # confidence = covariance matrix, shape (dims, dims)


@dataclass(frozen=True, slots=True)
class InputSpec:
    """One feature stream the model consumes, exactly as it was trained.

    ``channel_labels`` ``None`` means *positional*: the model knows only the channel order.
    A model with several inputs receives them concatenated in declaration order.
    """

    event_type: str  # "features.binned" | "features.vector"
    feature: str  # e.g. "threshold_crossing_count", "log_band_power", "spike_band_power"
    bin_ms: float
    channel_count: int
    channel_labels: tuple[str, ...] | None = None
    unit: str | None = None  # e.g. "count", "log10(uV^2)"; None = not declared
    band_hz: tuple[float, float] | None = None  # band of a band-power feature, if any


@dataclass(frozen=True, slots=True)
class Preprocessing:
    """How the features were computed when the model was trained.

    ``preset`` / ``params`` name a BrainOS pipeline preset and its parameters (e.g.
    ``spikeband_threshold`` with ``threshold_k=-4.5``); BrainOS refuses a pipeline that
    computes the features differently. ``None`` = the features came from the source itself
    or the author does not know. ``description`` documents steps inside the model.
    """

    preset: str | None = None
    params: Mapping[str, float | int | str | bool] = field(default_factory=dict)
    description: str = ""


@dataclass(frozen=True, slots=True)
class ParticipantCompat:
    """Who and what the model was calibrated on.

    ``participant_specific`` decoders (almost all neural decoders) run only on the same
    ``source_identity`` (participant / implant / dataset subject) unless the operator
    explicitly overrides. ``sessions`` are never decoded with this model (that would score
    it on its own training data).
    """

    participant_specific: bool = True
    source_identity: str | None = None
    sessions: tuple[str, ...] = ()
    calibration_profile: str | None = None


@dataclass(frozen=True, slots=True)
class CalibrationSpec:
    """What it takes to (re)calibrate the model for a participant."""

    required: bool = True
    task: str = ""  # e.g. "center-out cursor task with cued velocity"
    label_quantity: str | None = None  # behavior quantity used as targets, e.g. "velocity"
    label_dims: tuple[str, ...] = ()
    min_labelled_bins: int = 0


@dataclass(frozen=True, slots=True)
class OutputSpec:
    kind: OutputKind
    quantity: str  # e.g. "velocity", "class_posterior", "click_probability"
    dims: tuple[str, ...]  # dimension names, class names, or event names
    unit: str  # e.g. "workspace/s", "probability"
    space: str  # e.g. "screen_2d", "falcon_h1_7dof"
    # typical magnitude of each continuous dim (e.g. the training targets' std); BrainOS's
    # command router divides by it before applying gain / dead-zone. None = not declared.
    scale: tuple[float, ...] | None = None


@dataclass(frozen=True, slots=True)
class ModelProvenance:
    training_data_sha256: tuple[str, ...] = ()  # hashes of the training files
    code_version: str = ""  # e.g. "my-lab-decoders 1.4.2 (git abc123)"
    created_at: str = ""  # ISO 8601 UTC
    trained_by: str = ""  # tool or person
    notes: str = ""


@dataclass(frozen=True, slots=True)
class Artifact:
    """The serialized model a file-based decoder loads (absent for plugin decoders).

    ``format``: ``onnx``, ``skops``, ``torchscript``, ``safetensors`` (a PyTorch state_dict
    for a built-in architecture), ``brainos-json`` (BrainOS's own families), or the unsafe
    ``pickle`` / ``joblib`` (refused unless the operator marks the exact file trusted).
    ``file`` is relative to the manifest; ``sha256`` binds the manifest (and any trust
    decision) to the file's content. ``io`` holds format-specific declarations (names and
    shapes of tensors, the estimator method, recurrent state); see formats/.
    """

    format: str
    file: str
    sha256: str
    io: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ModelManifest:
    model_id: str  # unique; becomes provenance.model_id of every decoded event
    name: str  # human-readable name
    version: str  # the model's own semantic version
    api_version: str  # decoder SDK API it was written for, e.g. "1.0"
    family: str  # e.g. "ridge", "lda", "onnx", "sklearn", "torchscript", "my-lab-gru"
    description: str
    author: str
    license: str
    modalities: frozenset[Modality]  # modalities the model may run on (non-empty)
    inputs: tuple[InputSpec, ...]
    output: OutputSpec
    confidence: Confidence = Confidence.NONE
    preprocessing: Preprocessing = field(default_factory=Preprocessing)
    compatibility: ParticipantCompat = field(default_factory=ParticipantCompat)
    calibration: CalibrationSpec = field(default_factory=CalibrationSpec)
    provenance: ModelProvenance = field(default_factory=ModelProvenance)
    artifact: Artifact | None = None

    @property
    def input_width(self) -> int:
        """Length of the feature vector ``step()`` receives (all inputs concatenated)."""
        return sum(i.channel_count for i in self.inputs)


@dataclass(frozen=True, slots=True)
class DecodeOutput:
    """One bin's output. ``values`` has shape (dims,). ``confidence`` per the manifest:
    None (``none`` / ``posterior``), (dims,) variances, or a (dims, dims) covariance."""

    values: FloatArray
    confidence: FloatArray | None = None


# ----------------------------------------------------------------------------- errors


class DecoderError(Exception):
    """Base class; the message is shown to the operator, so make it actionable."""


class ModelLoadError(DecoderError):
    """The model could not be loaded (missing file, wrong format, declared I/O mismatch)."""


class UntrustedModelError(ModelLoadError):
    """The file needs code execution to load (pickle, joblib, untrusted skops types) and the
    operator has not marked this exact file as trusted."""


class InputMismatch(DecoderError):
    """``step()`` received features of the wrong shape."""


# ----------------------------------------------------------------------------- decoder


class Decoder(ABC):
    """A causal decoder. Called from a single thread: load -> (reset, step...)* -> close.

    Plugins set ``manifest`` as a class attribute and are instantiated without arguments;
    file loaders set it per instance.
    """

    manifest: ModelManifest

    def load(self) -> None:  # noqa: B027 - optional hook
        """Load parameters (files shipped with the package, a model file...).

        Raise :class:`ModelLoadError` with an operator-readable message on failure.
        """

    @abstractmethod
    def reset(self) -> None:
        """Forget all history (filter state, recurrent state). Called before decoding starts
        and whenever the input stream restarts."""

    @abstractmethod
    def step(self, features: FloatArray, timestamp_s: float) -> DecodeOutput:
        """Decode one bin. ``features`` has shape (manifest.input_width,), float64, all
        inputs concatenated in declaration order; ``timestamp_s`` is the bin end on the
        source clock."""

    def close(self) -> None:  # noqa: B027 - optional hook
        """Release resources. Idempotent; must not raise."""


def check_features(manifest: ModelManifest, features: FloatArray) -> FloatArray:
    """Validate the shape of one feature vector (helper for decoders and hosts)."""
    x = np.asarray(features, dtype=np.float64)
    if x.shape != (manifest.input_width,):
        raise InputMismatch(
            f"expected {manifest.input_width} features (all inputs concatenated), got shape "
            f"{x.shape}"
        )
    return x
