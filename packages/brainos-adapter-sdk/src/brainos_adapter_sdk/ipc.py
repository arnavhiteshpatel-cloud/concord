"""Plugin-host IPC: framing and (de)serialization of the public API types.

Protocol ``brainos.plugin-ipc/1`` over the host process's original stdin/stdout:

* Every frame is a 4-byte big-endian unsigned length followed by that many bytes.
* A *message* is one header frame (UTF-8 JSON object) followed by ``len(header["buffers"])``
  binary frames. Each entry of ``buffers`` is ``{"dtype": "<f4", "shape": [n, c]}`` and the
  matching frame holds the array's raw little-endian, C-ordered bytes. Sample data and
  timestamps never go through JSON, so values (and dtypes) arrive bit-exact.
* The host speaks first with ``{"type": "hello", ...}``. After that the runtime sends
  requests ``{"id": n, "cmd": ..., "args": {...}}`` and the host answers each with
  ``{"id": n, "ok": true, "result": {...}}`` or
  ``{"id": n, "ok": false, "error": {"type", "message", "traceback", "problems"}}``.

This module is pure (bytes in, bytes out) apart from :func:`read_message` /
:func:`write_message`, which work on blocking binary files.
"""

from __future__ import annotations

import json
import math
import struct
from collections.abc import Mapping, Sequence
from typing import IO, Any, cast

import numpy as np
from numpy.typing import NDArray

from brainos_adapter_sdk.api import (
    Channel,
    Chunk,
    ClockInfo,
    DeviceInfo,
    MarkerChunk,
    Modality,
    OptionSpec,
    PluginManifest,
    SessionInfo,
    StreamRole,
    StreamSpec,
)

PROTOCOL = "brainos.plugin-ipc/1"
LENGTH = struct.Struct(">I")
MAX_HEADER_BYTES = 4 * 1024 * 1024
MAX_FRAME_BYTES = 128 * 1024 * 1024
MAX_BUFFERS = 256

# Error types the host reports (stable strings; the runtime maps them).
LOAD_FAILED = "LoadFailed"  # the plugin could not be imported / instantiated
INCOMPATIBLE = "IncompatiblePlugin"  # manifest invalid or API version incompatible
INVALID_OPTIONS = "InvalidOptions"
OPEN_FAILED = "OpenFailed"
LINK_LOST = "LinkLost"
CONFIGURATION_CHANGED = "ConfigurationChanged"
PLUGIN_ERROR = "PluginError"  # a PluginError the plugin raised deliberately
INVALID_SESSION = "InvalidSession"  # SessionInfo failed validation
INVALID_DATA = "InvalidData"  # a chunk failed validation; the session was stopped
INVALID_DEVICES = "InvalidDevices"
INTERNAL_ERROR = "InternalError"  # unexpected exception in plugin code (with traceback)
NOT_OPEN = "NotOpen"
BAD_REQUEST = "BadRequest"


class WireError(ValueError):
    """Malformed frame or message (protocol violation)."""


# ----------------------------------------------------------------------------- frames


def _check_dtype(dt: np.dtype[Any]) -> None:
    if dt.kind not in "fiu" or dt.itemsize not in (1, 2, 4, 8) or dt.byteorder == ">":
        raise WireError(f"unsupported wire dtype {dt.str!r}")


def wire_array(a: NDArray[Any]) -> NDArray[Any]:
    """C-contiguous little-endian copy (or view) suitable for the wire."""
    dt = a.dtype
    if dt.byteorder == ">" or (dt.byteorder == "=" and not _little()):
        a = a.astype(dt.newbyteorder("<"))
    a = np.ascontiguousarray(a)
    _check_dtype(a.dtype)
    return a


def _little() -> bool:
    return bool(np.little_endian)


def encode_message(header: Mapping[str, Any], buffers: Sequence[NDArray[Any]] = ()) -> bytes:
    arrays = [wire_array(b) for b in buffers]
    h = dict(header)
    h["buffers"] = [{"dtype": a.dtype.str, "shape": list(a.shape)} for a in arrays]
    raw = json.dumps(h, separators=(",", ":"), allow_nan=False).encode("utf-8")
    if len(raw) > MAX_HEADER_BYTES:
        raise WireError(f"header of {len(raw)} bytes exceeds {MAX_HEADER_BYTES}")
    parts = [LENGTH.pack(len(raw)), raw]
    for a in arrays:
        if a.nbytes > MAX_FRAME_BYTES:
            raise WireError(f"buffer of {a.nbytes} bytes exceeds {MAX_FRAME_BYTES}")
        parts.append(LENGTH.pack(a.nbytes))
        parts.append(a.tobytes(order="C"))
    return b"".join(parts)


def decode_header(raw: bytes) -> dict[str, Any]:
    try:
        h = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as exc:
        preview = raw[:40]
        raise WireError(f"header is not UTF-8 JSON ({exc}); starts with {preview!r}") from None
    if not isinstance(h, dict):
        raise WireError("header must be a JSON object")
    bufs = h.get("buffers", [])
    if not isinstance(bufs, list) or len(bufs) > MAX_BUFFERS:
        raise WireError("header 'buffers' must be a list (max 256)")
    return cast(dict[str, Any], h)


def buffer_specs(header: Mapping[str, Any]) -> list[tuple[np.dtype[Any], tuple[int, ...]]]:
    out = []
    for spec in header.get("buffers", []):
        if not isinstance(spec, dict):
            raise WireError("buffer spec must be an object")
        try:
            dt = np.dtype(str(spec["dtype"]))
            shape = tuple(int(x) for x in spec["shape"])
        except (KeyError, TypeError, ValueError) as exc:
            raise WireError(f"malformed buffer spec {spec!r}: {exc}") from None
        _check_dtype(dt)
        if len(shape) > 2 or any(x < 0 for x in shape):
            raise WireError(f"buffer shape {shape} not allowed")
        out.append((dt, shape))
    return out


def decode_buffer(dt: np.dtype[Any], shape: tuple[int, ...], raw: bytes) -> NDArray[Any]:
    expected = math.prod(shape) * dt.itemsize
    if len(raw) != expected:
        raise WireError(f"buffer has {len(raw)} bytes, expected {expected} for {dt.str}{shape}")
    return np.frombuffer(raw, dtype=dt).reshape(shape)


def check_length(n: int, limit: int = MAX_FRAME_BYTES) -> int:
    if n > limit:
        raise WireError(f"frame length {n} exceeds {limit} bytes (corrupt stream?)")
    return n


def _read_exact(f: IO[bytes], n: int) -> bytes | None:
    buf = bytearray()
    while len(buf) < n:
        part = f.read(n - len(buf))
        if not part:
            if not buf:
                return None
            raise WireError(f"stream ended inside a frame ({len(buf)} of {n} bytes)")
        buf += part
    return bytes(buf)


def read_message(f: IO[bytes]) -> tuple[dict[str, Any], list[NDArray[Any]]] | None:
    """Blocking read of one message; None on a clean end of stream."""
    head = _read_exact(f, 4)
    if head is None:
        return None
    n = check_length(LENGTH.unpack(head)[0], MAX_HEADER_BYTES)
    raw = _read_exact(f, n)
    if raw is None:
        raise WireError("stream ended before the header")
    header = decode_header(raw)
    arrays = []
    for dt, shape in buffer_specs(header):
        lb = _read_exact(f, 4)
        if lb is None:
            raise WireError("stream ended before a buffer")
        m = check_length(LENGTH.unpack(lb)[0])
        data = _read_exact(f, m) if m else b""
        if data is None:
            raise WireError("stream ended inside a buffer")
        arrays.append(decode_buffer(dt, shape, data))
    return header, arrays


def write_message(
    f: IO[bytes], header: Mapping[str, Any], buffers: Sequence[NDArray[Any]] = ()
) -> None:
    f.write(encode_message(header, buffers))
    f.flush()


# ----------------------------------------------------------------------------- API types


def _typed(key: str, v: object, typ: type | tuple[type, ...]) -> Any:
    types = typ if isinstance(typ, tuple) else (typ,)
    # bool is a subclass of int: only accept it where bool is asked for
    if not isinstance(v, types) or (isinstance(v, bool) and bool not in types):
        raise WireError(f"field {key!r} has type {type(v).__name__}")
    return v


def _req(d: Mapping[str, Any], key: str, typ: type | tuple[type, ...]) -> Any:
    if key not in d:
        raise WireError(f"missing field {key!r}")
    return _typed(key, d[key], typ)


def _opt(d: Mapping[str, Any], key: str, typ: type | tuple[type, ...]) -> Any:
    v = d.get(key)
    return None if v is None else _typed(key, v, typ)


def option_to_dict(o: OptionSpec) -> dict[str, Any]:
    return {
        "type": o.type,
        "description": o.description,
        "default": o.default,
        "required": o.required,
        "choices": list(o.choices),
    }


def option_from_dict(d: Mapping[str, Any]) -> OptionSpec:
    default = d.get("default")
    if default is not None and not isinstance(default, str | int | float | bool):
        raise WireError("option default must be a scalar")
    choices = d.get("choices", [])
    if not isinstance(choices, list):
        raise WireError("option choices must be a list")
    return OptionSpec(
        type=_req(d, "type", str),
        description=_req(d, "description", str),
        default=default,
        required=bool(_req(d, "required", bool)),
        choices=tuple(str(c) for c in choices),
    )


def manifest_to_dict(m: PluginManifest) -> dict[str, Any]:
    return {
        "name": m.name,
        "version": m.version,
        "api_version": m.api_version,
        "display_name": m.display_name,
        "description": m.description,
        "author": m.author,
        "license": m.license,
        "roles": sorted(str(getattr(r, "value", r)) for r in m.roles),
        "homepage": m.homepage,
        "ecosystem": m.ecosystem,
        "network": m.network,
        "options": {str(k): option_to_dict(v) for k, v in m.options.items()},
    }


def manifest_from_dict(d: Mapping[str, Any]) -> PluginManifest:
    """Rebuild a manifest. Unknown role names are kept as plain strings so validation can
    report them (instead of failing here with a less helpful message)."""
    roles = _req(d, "roles", list)
    opts = _req(d, "options", dict)
    return PluginManifest(
        name=_req(d, "name", str),
        version=_req(d, "version", str),
        api_version=_req(d, "api_version", str),
        display_name=_req(d, "display_name", str),
        description=_req(d, "description", str),
        author=_req(d, "author", str),
        license=_req(d, "license", str),
        roles=cast(
            frozenset[StreamRole],
            frozenset(
                StreamRole(r) if r in StreamRole._value2member_map_ else r
                for r in roles
                if isinstance(r, str)
            ),
        ),
        homepage=str(d.get("homepage") or ""),
        ecosystem=_opt(d, "ecosystem", str),
        network=bool(d.get("network", False)),
        options={str(k): option_from_dict(v) for k, v in opts.items() if isinstance(v, dict)},
    )


def stream_to_dict(s: StreamSpec) -> dict[str, Any]:
    return {
        "stream_id": s.stream_id,
        "role": str(getattr(s.role, "value", s.role)),
        "channels": [{"label": c.label, "unit": c.unit, "type": c.type} for c in s.channels],
        "nominal_rate_hz": float(s.nominal_rate_hz),
        "clock": {"domain": s.clock.domain, "description": s.clock.description},
        "modality": None if s.modality is None else str(getattr(s.modality, "value", s.modality)),
        "invasive": s.invasive,
        "bin_ms": s.bin_ms,
        "quantity": s.quantity,
        "model_id": s.model_id,
    }


def stream_from_dict(d: Mapping[str, Any]) -> StreamSpec:
    role = _req(d, "role", str)
    if role not in StreamRole._value2member_map_:
        raise WireError(f"unknown stream role {role!r}")
    clock = _req(d, "clock", dict)
    modality = _opt(d, "modality", str)
    if modality is not None and modality not in Modality._value2member_map_:
        raise WireError(f"unknown modality {modality!r}")
    rate = _req(d, "nominal_rate_hz", (int, float))
    bin_ms = _opt(d, "bin_ms", (int, float))
    return StreamSpec(
        stream_id=_req(d, "stream_id", str),
        role=StreamRole(role),
        channels=tuple(
            Channel(
                label=_req(c, "label", str),
                unit=_opt(c, "unit", str),
                type=_opt(c, "type", str),
            )
            for c in _req(d, "channels", list)
            if isinstance(c, dict)
        ),
        nominal_rate_hz=float(rate),
        clock=ClockInfo(
            domain=_req(clock, "domain", str),
            description=str(clock.get("description") or ""),
        ),
        modality=None if modality is None else Modality(modality),
        invasive=_opt(d, "invasive", bool),
        bin_ms=None if bin_ms is None else float(bin_ms),
        quantity=_opt(d, "quantity", str),
        model_id=_opt(d, "model_id", str),
    )


def session_info_to_dict(info: SessionInfo) -> dict[str, Any]:
    return {
        "streams": [stream_to_dict(s) for s in info.streams],
        "primary_stream": info.primary_stream,
        "synthetic": info.synthetic,
        "prerecorded": info.prerecorded,
        "origin": info.origin,
    }


def session_info_from_dict(d: Mapping[str, Any]) -> SessionInfo:
    return SessionInfo(
        streams=tuple(stream_from_dict(s) for s in _req(d, "streams", list) if isinstance(s, dict)),
        primary_stream=_req(d, "primary_stream", str),
        synthetic=_req(d, "synthetic", bool),
        prerecorded=_req(d, "prerecorded", bool),
        origin=_req(d, "origin", str),
    )


def device_to_dict(d: DeviceInfo) -> dict[str, Any]:
    return {
        "device_key": d.device_key,
        "display_name": d.display_name,
        "description": d.description,
        "details": dict(d.details),
    }


def device_from_dict(d: Mapping[str, Any]) -> DeviceInfo:
    details = d.get("details") or {}
    if not isinstance(details, dict):
        raise WireError("device details must be an object")
    return DeviceInfo(
        device_key=_req(d, "device_key", str),
        display_name=_req(d, "display_name", str),
        description=str(d.get("description") or ""),
        details={str(k): str(v) for k, v in details.items()},
    )


def chunks_to_wire(
    items: Sequence[Chunk | MarkerChunk],
) -> tuple[list[dict[str, Any]], list[NDArray[Any]]]:
    """Chunk headers (JSON) + the arrays to send as binary frames, in order."""
    heads: list[dict[str, Any]] = []
    arrays: list[NDArray[Any]] = []
    for item in items:
        if isinstance(item, Chunk):
            heads.append(
                {
                    "kind": "numeric",
                    "stream_id": item.stream_id,
                    "first_index": int(item.first_index),
                }
            )
            arrays.append(item.data)
            arrays.append(np.asarray(item.timestamps, dtype=np.float64))
        else:
            heads.append(
                {"kind": "markers", "stream_id": item.stream_id, "labels": list(item.labels)}
            )
            arrays.append(np.asarray(item.timestamps, dtype=np.float64))
    return heads, arrays


def chunks_from_wire(heads: object, arrays: Sequence[NDArray[Any]]) -> list[Chunk | MarkerChunk]:
    if not isinstance(heads, list):
        raise WireError("'chunks' must be a list")
    out: list[Chunk | MarkerChunk] = []
    k = 0

    def take() -> NDArray[Any]:
        nonlocal k
        if k >= len(arrays):
            raise WireError("fewer buffers than the chunk headers require")
        a = arrays[k]
        k += 1
        return a

    for h in heads:
        if not isinstance(h, dict):
            raise WireError("chunk header must be an object")
        kind = h.get("kind")
        sid = _req(h, "stream_id", str)
        if kind == "numeric":
            idx = _req(h, "first_index", int)
            data = take()
            ts = take()
            if data.ndim != 2 or ts.ndim != 1 or ts.dtype != np.float64:
                raise WireError("numeric chunk buffers must be 2-D data and 1-D float64 times")
            out.append(Chunk(sid, data, ts, idx))
        elif kind == "markers":
            labels = _req(h, "labels", list)
            ts = take()
            if ts.ndim != 1 or ts.dtype != np.float64:
                raise WireError("marker timestamps must be 1-D float64")
            out.append(MarkerChunk(sid, tuple(str(x) for x in labels), ts))
        else:
            raise WireError(f"unknown chunk kind {kind!r}")
    if k != len(arrays):
        raise WireError("more buffers than the chunk headers use")
    return out
