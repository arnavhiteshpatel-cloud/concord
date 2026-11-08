"""Envelope JSON, byte-identical to ``envelope.model_dump_json()``, faster for raw frames.

A ``recording.frame`` whose ``samples`` is held as a float64 numpy array (see
``contracts/events.py: _samples_in``) is serialized as the envelope without ``samples``
followed by the samples array encoded directly from the array buffer, instead of building
one Python float object per value. ``samples`` is the last key of the payload and the
payload the last key of the envelope, so the splice reproduces pydantic's output exactly
(tested byte for byte, including edge-case floats).

The array encoder is orjson when it is installed (``OPT_SERIALIZE_NUMPY``; its float
formatting is the same shortest round-trip form pydantic-core emits), and otherwise
pydantic's own encoder on ``ndarray.tolist()`` (always identical, slower). Measured in
docs/PERFORMANCE.md; ``CONCORD_NO_ORJSON=1`` forces the fallback.
"""

from __future__ import annotations

import logging
import os
from collections.abc import Callable
from typing import Any

from pydantic import TypeAdapter

from concord.contracts.capabilities import EventType
from concord.contracts.events import EventEnvelope

log = logging.getLogger(__name__)

_SAMPLES = TypeAdapter(list[list[float]])
_EXCLUDE_SAMPLES = {"payload": {"samples"}}
_TAIL = "}}"  # end of the payload object, end of the envelope object


def _pydantic_samples(arr: Any) -> str:
    return _SAMPLES.dump_json(arr.tolist()).decode()


def _load_orjson() -> Callable[[Any], str] | None:
    if os.environ.get("CONCORD_NO_ORJSON"):
        return None
    try:
        import orjson
    except ImportError:
        return None
    opt = orjson.OPT_SERIALIZE_NUMPY

    def encode(arr: Any) -> str:
        return orjson.dumps(arr, option=opt).decode()

    return encode


_orjson_samples = _load_orjson()
ENCODER = "orjson" if _orjson_samples is not None else "pydantic"


def samples_json(arr: Any) -> str:
    """JSON text of a float64 (channels, samples) array, as pydantic writes the equivalent
    ``list[list[float]]``."""
    if _orjson_samples is not None and arr.dtype.kind == "f" and arr.flags.c_contiguous:
        return _orjson_samples(arr)
    return _pydantic_samples(arr)


def envelope_json(envelope: EventEnvelope) -> str:
    """``envelope.model_dump_json()``, without per-value Python objects for array frames."""
    if envelope.event_type is EventType.RECORDING_FRAME:
        samples = envelope.payload.samples
        if getattr(samples, "flags", None) is not None:
            head = envelope.model_dump_json(exclude=_EXCLUDE_SAMPLES)
            if head.endswith(_TAIL):  # one copy of the (large) samples text, not three
                return "".join((head[: -len(_TAIL)], ',"samples":', samples_json(samples), _TAIL))
            log.error("unexpected envelope JSON layout; using the generic serializer")
    return envelope.model_dump_json()
