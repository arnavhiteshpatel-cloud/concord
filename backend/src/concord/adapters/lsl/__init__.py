"""Lab Streaming Layer adapter. Requires the optional ``live`` extra (pylsl)."""

from concord.adapters.lsl.adapter import LSLAdapter, LSLSourceSpec, interpret
from concord.adapters.lsl.metadata import (
    ChannelMeta,
    Declaration,
    StreamMeta,
    plan_units,
    stream_key,
    unit_scale_to_uv,
)

__all__ = [
    "ChannelMeta",
    "Declaration",
    "LSLAdapter",
    "LSLSourceSpec",
    "StreamMeta",
    "interpret",
    "plan_units",
    "stream_key",
    "unit_scale_to_uv",
]
