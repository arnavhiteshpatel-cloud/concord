"""NWB neural recordings (requires the optional ``nwb`` extra: ``pip install 'brainos[nwb]'``)."""

from brainos.adapters.nwb.ecog import (
    NWBElectricalRecording,
    NWBElectricalSource,
    has_electrical_series,
    load_electrical,
    verify_electrical,
)
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
    "NWBElectricalRecording",
    "NWBElectricalSource",
    "NWBFormatError",
    "NWBUnitsRecording",
    "NWBUnitsSource",
    "UnsupportedModalityError",
    "device_id_for",
    "has_electrical_series",
    "load",
    "load_electrical",
    "verify_electrical",
]
