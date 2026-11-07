"""NWB neural recordings (requires the optional ``nwb`` extra: ``pip install 'brainos[nwb]'``)."""

from brainos.adapters.nwb.reader import (
    NWBFormatError,
    NWBUnitsRecording,
    UnsupportedModalityError,
    load,
)
from brainos.adapters.nwb.source import (
    DEVICE_PREFIX,
    HUMAN_LABEL,
    DecoderLeakageError,
    DecoderMismatchError,
    NWBUnitsSource,
    device_id_for,
)

__all__ = [
    "DEVICE_PREFIX",
    "HUMAN_LABEL",
    "DecoderLeakageError",
    "DecoderMismatchError",
    "NWBFormatError",
    "NWBUnitsRecording",
    "NWBUnitsSource",
    "UnsupportedModalityError",
    "device_id_for",
    "load",
]
