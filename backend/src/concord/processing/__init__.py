"""Streaming neural signal processing (requires the optional ``dsp`` extra: numpy + scipy)."""

from concord.processing.chain import (
    PRESET_INFO,
    FeatureFrame,
    OutputSpec,
    ProcessingSpec,
    SignalChain,
)
from concord.processing.stages import StageConfigError

__all__ = [
    "PRESET_INFO",
    "FeatureFrame",
    "OutputSpec",
    "ProcessingSpec",
    "SignalChain",
    "StageConfigError",
]
