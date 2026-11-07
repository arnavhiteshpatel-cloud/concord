"""BrainOS decoder SDK: bring a decoder (plugin or model file) to BrainOS safely.

``brainos_decoder_sdk.api`` is the interface, ``brainos_decoder_sdk.manifest`` the rules
BrainOS checks, ``brainos_decoder_sdk.formats`` the model-file loaders and trust policy,
``python -m brainos_decoder_sdk.host --check <decoder>`` (or ``brainos-decoder check``) runs a
decoder exactly as BrainOS does. Guide: docs/DECODER_SDK.md.
"""

from brainos_decoder_sdk.api import (
    API_VERSION,
    ENTRY_POINT_GROUP,
    MANIFEST_SCHEMA,
    Artifact,
    CalibrationSpec,
    Confidence,
    DecodeOutput,
    Decoder,
    DecoderError,
    InputMismatch,
    InputSpec,
    Modality,
    ModelLoadError,
    ModelManifest,
    ModelProvenance,
    OutputKind,
    OutputSpec,
    ParticipantCompat,
    Preprocessing,
    UntrustedModelError,
    check_features,
)

__all__ = [
    "API_VERSION",
    "ENTRY_POINT_GROUP",
    "MANIFEST_SCHEMA",
    "Artifact",
    "CalibrationSpec",
    "Confidence",
    "DecodeOutput",
    "Decoder",
    "DecoderError",
    "InputMismatch",
    "InputSpec",
    "Modality",
    "ModelLoadError",
    "ModelManifest",
    "ModelProvenance",
    "OutputKind",
    "OutputSpec",
    "ParticipantCompat",
    "Preprocessing",
    "UntrustedModelError",
    "check_features",
]
__version__ = "1.0.0"
