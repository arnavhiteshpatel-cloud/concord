"""Streaming neural signal processing (requires the optional ``dsp`` extra: numpy + scipy)."""

from brainos.processing.chain import (
    PRESET_INFO,
    FeatureFrame,
    OutputSpec,
    ProcessingSpec,
    SignalChain,
)
from brainos.processing.stages import StageConfigError

__all__ = [
    "PRESET_INFO",
    "FeatureFrame",
    "OutputSpec",
    "ProcessingSpec",
    "SignalChain",
    "StageConfigError",
]
