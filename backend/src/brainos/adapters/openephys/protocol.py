"""Open Ephys ZMQ Interface wire protocol: pure parsing and encoding (no I/O).

Source of truth: the plugin source ``open-ephys-plugins/zmq-interface`` at commit
``38513917`` (``Source/ZmqInterface.cpp``: ``sendData``, ``sendEvent``,
``sendSpikeEvent``, ``run``) and its official client
``Resources/python_client/plot_process_zmq.py``.

Every PUB message is multipart ``[envelope, header_json, (binary)]``:

* envelope ``b"DATA\\0"`` (continuous data) or ``b"EVENT\\0"`` (TTL events *and* spikes);
  the C++ code sends ``strlen + 1`` bytes, so the NUL is part of the frame.
* header: JSON object written by JUCE ``JSON::toString`` (multi-line format), keys in
  the order the C++ code sets them. Every header has ``message_num`` (+1 per message of
  any type, reset at acquisition start, first message is 1), ``type`` and ``timestamp``
  (sender wall clock, ms since the epoch).
* ``data``: ``content{stream, channel_num, channel_name, num_samples, sample_num,
  sample_rate}``, ``data_size = num_samples * 4``; binary frame = float32 samples.
* ``event``: ``content{stream, source_node, type, sample_num}``, ``data_size``; a binary
  frame follows only if ``data_size > 0``. TTL payload (official client): byte 0 = line,
  byte 1 = state, bytes 2..9 = uint64 word (little-endian).
* ``spike``: key ``spike`` (not ``content``) ``{stream, source_node, electrode,
  sample_num, num_channels, num_samples, sorted_id, threshold[]}``, no ``data_size``;
  binary frame = float32 waveform, ``num_channels * num_samples`` values.

Physical units are **not** transmitted by this protocol.
"""

from __future__ import annotations

import json
import math
import struct
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

import numpy as np
import numpy.typing as npt

from brainos.adapters.base import PacketDecodeError

PLUGIN_REFERENCE = "zmq-interface@38513917"
ENVELOPE_DATA = b"DATA\x00"
ENVELOPE_EVENT = b"EVENT\x00"
HEARTBEAT_REPLY = b"heartbeat received"
EVENT_REPLY = b"message correctly parsed"
BAD_JSON_REPLY = b"JSON message could not be read"

#: EventChannel types as mapped by the official client.
EVENT_TYPES: dict[int, str] = {
    0: "TIMESTAMP",
    1: "BUFFER_SIZE",
    2: "PARAMETER_CHANGE",
    3: "TTL",
    4: "SPIKE",
    5: "MESSAGE",
    6: "BINARY_MSG",
}
TTL_EVENT_TYPE = 3
TTL_PAYLOAD = struct.Struct("<BBQ")  # line, state, word -> 10 bytes
FLOAT32 = np.dtype("<f4")

Float32Array = npt.NDArray[np.float32]


# ------------------------------------------------------------------------- messages


@dataclass(frozen=True, slots=True)
class DataMessage:
    """One channel's samples for one processing block."""

    message_num: int
    timestamp_ms: int
    stream: str
    channel_num: int
    channel_name: str
    num_samples: int
    sample_num: int
    sample_rate: float
    payload: bytes

    def samples(self) -> Float32Array:
        """The samples as a read-only float32 array (zero-copy view of the payload)."""
        return np.frombuffer(self.payload, dtype=FLOAT32)


@dataclass(frozen=True, slots=True)
class TTLData:
    line: int
    state: int
    word: int


@dataclass(frozen=True, slots=True)
class EventMessage:
    message_num: int
    timestamp_ms: int
    stream: str
    source_node: int
    event_type: int
    sample_num: int
    payload: bytes

    @property
    def is_ttl(self) -> bool:
        return self.event_type == TTL_EVENT_TYPE

    @property
    def ttl(self) -> TTLData | None:
        """Decoded TTL payload (as the official client decodes it), if any."""
        if not self.is_ttl or not self.payload:
            return None
        line, state, word = TTL_PAYLOAD.unpack_from(self.payload)
        return TTLData(line, state, word)


@dataclass(frozen=True, slots=True)
class SpikeMessage:
    message_num: int
    timestamp_ms: int
    stream: str
    source_node: int
    electrode: str
    sample_num: int
    num_channels: int
    num_samples: int
    sorted_id: int
    threshold: tuple[float, ...]
    payload: bytes

    def waveform(self) -> Float32Array:
        """Waveform as float32 ``[channel][sample]`` (read-only)."""
        arr = np.frombuffer(self.payload, dtype=FLOAT32)
        return arr.reshape(self.num_channels, self.num_samples)


Message = DataMessage | EventMessage | SpikeMessage


# -------------------------------------------------------------------------- parsing


def _fail(reason: str) -> PacketDecodeError:
    return PacketDecodeError(f"open ephys zmq: {reason}")


def _obj(container: dict[str, Any], key: str, where: str) -> dict[str, Any]:
    if key not in container:
        raise _fail(f"{where}: missing field '{key}'")
    value = container[key]
    if not isinstance(value, dict):
        raise _fail(f"{where}: field '{key}' must be an object, got {type(value).__name__}")
    return value


def _int(container: dict[str, Any], key: str, where: str, *, minimum: int | None = 0) -> int:
    if key not in container:
        raise _fail(f"{where}: missing field '{key}'")
    value = container[key]
    if isinstance(value, bool) or not isinstance(value, int):
        raise _fail(f"{where}: field '{key}' must be an integer, got {type(value).__name__}")
    if minimum is not None and value < minimum:
        raise _fail(f"{where}: field '{key}' must be >= {minimum}, got {value}")
    return value


def _str(container: dict[str, Any], key: str, where: str) -> str:
    if key not in container:
        raise _fail(f"{where}: missing field '{key}'")
    value = container[key]
    if not isinstance(value, str):
        raise _fail(f"{where}: field '{key}' must be a string, got {type(value).__name__}")
    return value


def _num(value: Any, where: str) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise _fail(f"{where} must be a number, got {type(value).__name__}")
    f = float(value)
    if not math.isfinite(f):
        raise _fail(f"{where} must be finite")
    return f


def _frame_count(frames: Sequence[bytes], expected: int, what: str) -> None:
    if len(frames) != expected:
        raise _fail(f"{what} message must have {expected} frames, got {len(frames)}")


def parse_message(frames: Sequence[bytes]) -> Message:
    """Parse one multipart PUB message. Raises :class:`PacketDecodeError` with a reason."""
    if len(frames) < 2 or len(frames) > 3:
        raise _fail(f"expected 2 or 3 frames, got {len(frames)}")
    envelope = bytes(frames[0])
    if envelope not in (ENVELOPE_DATA, ENVELOPE_EVENT):
        if envelope in (b"DATA", b"EVENT"):
            raise _fail(f"envelope {envelope!r} is missing its NUL terminator")
        raise _fail(f"unknown envelope {envelope[:16]!r}")
    try:
        text = bytes(frames[1]).decode("utf-8")
    except UnicodeDecodeError as exc:
        raise _fail(f"header is not valid UTF-8 ({exc.reason} at byte {exc.start})") from None
    try:
        header = json.loads(text)
    except ValueError as exc:
        raise _fail(f"header is not valid JSON ({exc})") from None
    if not isinstance(header, dict):
        raise _fail(f"header must be a JSON object, got {type(header).__name__}")

    mtype = _str(header, "type", "header")
    message_num = _int(header, "message_num", "header")
    timestamp = _int(header, "timestamp", "header")
    if envelope == ENVELOPE_DATA:
        if mtype != "data":
            raise _fail(f"envelope DATA carries type '{mtype}' (expected 'data')")
        return _parse_data(frames, header, message_num, timestamp)
    if mtype == "event":
        return _parse_event(frames, header, message_num, timestamp)
    if mtype == "spike":
        return _parse_spike(frames, header, message_num, timestamp)
    raise _fail(f"envelope EVENT carries unknown type '{mtype}'")


def _parse_data(
    frames: Sequence[bytes], header: dict[str, Any], message_num: int, timestamp: int
) -> DataMessage:
    c = _obj(header, "content", "data header")
    w = "data content"
    stream = _str(c, "stream", w)
    channel_num = _int(c, "channel_num", w)
    channel_name = _str(c, "channel_name", w)
    num_samples = _int(c, "num_samples", w)
    sample_num = _int(c, "sample_num", w)
    if "sample_rate" not in c:
        raise _fail(f"{w}: missing field 'sample_rate'")
    sample_rate = _num(c["sample_rate"], f"{w}: field 'sample_rate'")
    if sample_rate <= 0:
        raise _fail(f"{w}: field 'sample_rate' must be > 0, got {sample_rate}")
    data_size = _int(header, "data_size", "data header")
    if data_size != num_samples * 4:
        raise _fail(f"data_size {data_size} != num_samples*4 ({num_samples * 4})")
    _frame_count(frames, 3, "data")
    payload = bytes(frames[2])
    if len(payload) != data_size:
        raise _fail(f"data payload has {len(payload)} bytes, header data_size={data_size}")
    return DataMessage(
        message_num,
        timestamp,
        stream,
        channel_num,
        channel_name,
        num_samples,
        sample_num,
        sample_rate,
        payload,
    )


def _parse_event(
    frames: Sequence[bytes], header: dict[str, Any], message_num: int, timestamp: int
) -> EventMessage:
    c = _obj(header, "content", "event header")
    w = "event content"
    stream = _str(c, "stream", w)
    source_node = _int(c, "source_node", w, minimum=None)
    event_type = _int(c, "type", w)
    if event_type > 255:
        raise _fail(f"{w}: field 'type' must be a uint8, got {event_type}")
    sample_num = _int(c, "sample_num", w)
    data_size = _int(header, "data_size", "event header")
    if data_size == 0:
        _frame_count(frames, 2, "event (data_size=0)")
        payload = b""
    else:
        _frame_count(frames, 3, "event (data_size>0)")
        payload = bytes(frames[2])
        if len(payload) != data_size:
            raise _fail(f"event payload has {len(payload)} bytes, header data_size={data_size}")
    if event_type == TTL_EVENT_TYPE and payload and len(payload) < TTL_PAYLOAD.size:
        raise _fail(f"TTL payload has {len(payload)} bytes, need >= {TTL_PAYLOAD.size}")
    return EventMessage(
        message_num, timestamp, stream, source_node, event_type, sample_num, payload
    )


def _parse_spike(
    frames: Sequence[bytes], header: dict[str, Any], message_num: int, timestamp: int
) -> SpikeMessage:
    if "content" in header and "spike" not in header:
        raise _fail("spike header uses 'content'; the plugin puts spike fields under 'spike'")
    s = _obj(header, "spike", "spike header")
    w = "spike"
    stream = _str(s, "stream", w)
    source_node = _int(s, "source_node", w, minimum=None)
    electrode = _str(s, "electrode", w)
    sample_num = _int(s, "sample_num", w)
    num_channels = _int(s, "num_channels", w)
    num_samples = _int(s, "num_samples", w)
    sorted_id = _int(s, "sorted_id", w, minimum=None)
    if "threshold" not in s:
        raise _fail(f"{w}: missing field 'threshold'")
    raw_thr = s["threshold"]
    if not isinstance(raw_thr, list):
        raise _fail(f"{w}: field 'threshold' must be a list, got {type(raw_thr).__name__}")
    threshold = tuple(_num(v, f"{w}: threshold[{i}]") for i, v in enumerate(raw_thr))
    if len(threshold) != num_channels:
        raise _fail(f"{w}: {len(threshold)} thresholds for num_channels={num_channels}")
    _frame_count(frames, 3, "spike")
    payload = bytes(frames[2])
    expected = num_channels * num_samples * 4
    if len(payload) != expected:
        raise _fail(
            f"spike waveform has {len(payload)} bytes, expected num_channels*num_samples*4 "
            f"= {expected}"
        )
    return SpikeMessage(
        message_num,
        timestamp,
        stream,
        source_node,
        electrode,
        sample_num,
        num_channels,
        num_samples,
        sorted_id,
        threshold,
        payload,
    )


# ------------------------------------------------------------------------- encoding
# JUCE ``JSON::toString(var)`` (allOnOneLine = false, maximumDecimalPlaces = 15):
# multi-line, 2-space indent, JUCE ``newLine`` ("\r\n"), '"key": value'.

_NL = "\r\n"
_INDENT = 2
_ESCAPES = {'"': '\\"', "\\": "\\\\", "\b": "\\b", "\f": "\\f", "\t": "\\t", "\r": "\\r"}
_ESCAPES["\n"] = "\\n"


def _juce_string(s: str) -> str:
    out = []
    for ch in s:
        if ch in _ESCAPES:
            out.append(_ESCAPES[ch])
        elif ord(ch) < 0x20:
            out.append(f"\\u{ord(ch):04x}")
        else:
            out.append(ch)
    return '"' + "".join(out) + '"'


def _reduce_float_string(s: str) -> str:
    """Trailing-zero trimming like JUCE ``reduceLengthOfFloatString`` (keeps 'x.0')."""
    mantissa, _, exponent = s.partition("e")
    if "." in mantissa:
        mantissa = mantissa.rstrip("0")
        if mantissa.endswith("."):
            mantissa += "0"
    if not exponent:
        return mantissa
    sign = "-" if exponent.startswith("-") else ""
    digits = exponent.lstrip("+-").lstrip("0")
    return mantissa if not digits else f"{mantissa}e{sign}{digits}"


def _juce_double(d: float) -> str:
    """JUCE ``serialiseDouble(d, 15)``. Exact for |d| in (1e-5, 1e6); the scientific
    branch outside that range is a best-effort reproduction."""
    if not math.isfinite(d):
        return "null"
    a = abs(d)
    if a >= 1.0e6 or a <= 1.0e-5:
        return _reduce_float_string(f"{d:.15e}")
    if float(int(d)) == d:
        return f"{d:.1f}"
    return _reduce_float_string(f"{d:.15f}")


def juce_json(value: Any, indent: int = 0) -> str:
    """Serialize like JUCE ``JSON::toString`` (multi-line). ``dict`` order is preserved."""
    if isinstance(value, str):
        return _juce_string(value)
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return _juce_double(value)
    pad = " " * (indent + _INDENT)
    if isinstance(value, list | tuple):
        if not value:
            return "[]"
        items = [pad + juce_json(v, indent + _INDENT) for v in value]
        return "[" + _NL + ("," + _NL).join(items) + _NL + " " * indent + "]"
    if isinstance(value, dict):
        items = [
            f"{pad}{_juce_string(str(k))}: {juce_json(v, indent + _INDENT)}"
            for k, v in value.items()
        ]
        return "{" + _NL + ("," + _NL).join(items) + _NL + " " * indent + "}"
    raise TypeError(f"cannot serialize {type(value).__name__}")


def _header(obj: dict[str, Any]) -> bytes:
    # The plugin sends s.toRawUTF8() with s.length() (characters) bytes: identical to the
    # UTF-8 encoding for ASCII headers (non-ASCII names would be truncated by the plugin).
    return juce_json(obj).encode("utf-8")


def encode_data(
    *,
    message_num: int,
    stream: str,
    channel_num: int,
    channel_name: str,
    sample_num: int,
    sample_rate: float,
    samples: npt.ArrayLike,
    timestamp_ms: int,
) -> list[bytes]:
    """Build a data message exactly as ``ZmqInterface::sendData`` does."""
    arr = np.ascontiguousarray(samples, dtype=FLOAT32)
    if arr.ndim != 1:
        raise ValueError("samples must be 1-D")
    header = {
        "message_num": message_num,
        "type": "data",
        "content": {
            "stream": stream,
            "channel_num": channel_num,
            "channel_name": channel_name,
            "num_samples": int(arr.size),
            "sample_num": sample_num,
            "sample_rate": float(sample_rate),
        },
        "data_size": int(arr.size) * 4,
        "timestamp": timestamp_ms,
    }
    return [ENVELOPE_DATA, _header(header), arr.tobytes()]


def encode_ttl_payload(line: int, state: int, word: int) -> bytes:
    """TTL payload layout as decoded by the official client."""
    return TTL_PAYLOAD.pack(line, state, word)


def encode_event(
    *,
    message_num: int,
    stream: str,
    source_node: int,
    event_type: int,
    sample_num: int,
    payload: bytes,
    timestamp_ms: int,
) -> list[bytes]:
    """Build an event message exactly as ``ZmqInterface::sendEvent`` does."""
    header = {
        "message_num": message_num,
        "type": "event",
        "content": {
            "stream": stream,
            "source_node": source_node,
            "type": event_type,
            "sample_num": sample_num,
        },
        "data_size": len(payload),
        "timestamp": timestamp_ms,
    }
    frames = [ENVELOPE_EVENT, _header(header)]
    if payload:
        frames.append(bytes(payload))
    return frames


def encode_spike(
    *,
    message_num: int,
    stream: str,
    source_node: int,
    electrode: str,
    sample_num: int,
    sorted_id: int,
    threshold: Sequence[float],
    waveform: npt.ArrayLike,
    timestamp_ms: int,
) -> list[bytes]:
    """Build a spike message exactly as ``ZmqInterface::sendSpikeEvent`` does.

    ``waveform`` is ``[channel][sample]``.
    """
    wf = np.ascontiguousarray(waveform, dtype=FLOAT32)
    if wf.ndim != 2:
        raise ValueError("waveform must be 2-D [channel][sample]")
    n_ch, n_s = wf.shape
    if len(threshold) != n_ch:
        raise ValueError("one threshold per waveform channel is required")
    header = {
        "message_num": message_num,
        "type": "spike",
        "spike": {
            "stream": stream,
            "source_node": source_node,
            "electrode": electrode,
            "sample_num": sample_num,
            "num_channels": int(n_ch),
            "num_samples": int(n_s),
            "sorted_id": sorted_id,
            # float -> var(double): JUCE writes doubles; keep the float32 value exactly
            "threshold": [float(np.float32(t)) for t in threshold],
        },
        "timestamp": timestamp_ms,
    }
    return [ENVELOPE_EVENT, _header(header), wf.tobytes()]


def heartbeat_request(application: str, uuid: str) -> bytes:
    """The heartbeat JSON a client sends on the REQ socket (official client format)."""
    return json.dumps({"application": application, "uuid": uuid, "type": "heartbeat"}).encode()


def heartbeat_reply(request: bytes) -> bytes:
    """What ``ZmqInterface::run`` replies to a REQ message."""
    try:
        v = json.loads(request.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        return BAD_JSON_REPLY
    if not isinstance(v, dict | list):  # JUCE JSON::parse accepts only an object or array
        return BAD_JSON_REPLY
    if isinstance(v, dict) and v.get("type") == "event":
        return EVENT_REPLY
    return HEARTBEAT_REPLY
