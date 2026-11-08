"""Decoder-host IPC: ``brainos.decoder-ipc/1``.

The framing is the adapter SDK's (``brainos_adapter_sdk.ipc``): 4-byte big-endian length +
UTF-8 JSON header, then the header's ``buffers`` as raw little-endian C-ordered arrays, so
features and outputs cross the process boundary bit-exact (float64).

The host speaks first (``{"type": "hello", ...}``); the runtime then sends requests
``{"id", "cmd", "args"}`` answered by ``{"id", "ok": true, "result"}`` or
``{"id", "ok": false, "error": {"type", "message", "traceback", "problems"}}``.

Commands: ``ping``, ``manifest``, ``load``, ``reset``, ``step`` (one buffer: features
(n, width) float64; result buffers: values (n, dims) float64 and, if the manifest declares
variance / covariance, confidence (n, dims) / (n, dims * dims)), ``close``, ``shutdown``.
"""

from __future__ import annotations

from brainos_adapter_sdk.ipc import (
    LENGTH,
    MAX_FRAME_BYTES,
    MAX_HEADER_BYTES,
    WireError,
    buffer_specs,
    check_length,
    decode_buffer,
    decode_header,
    encode_message,
    read_message,
    write_message,
)

PROTOCOL = "brainos.decoder-ipc/1"
MAX_STEP_BINS = 4096

# Error types the host reports (stable strings; the runtime maps them).
LOAD_FAILED = "LoadFailed"  # the decoder could not be imported / instantiated
INCOMPATIBLE = "IncompatibleDecoder"  # manifest invalid or API version incompatible
MODEL_LOAD_ERROR = "ModelLoadError"  # load() failed (file, format, declared I/O)
UNTRUSTED_MODEL = "UntrustedModel"  # needs an explicit trust decision
INPUT_MISMATCH = "InputMismatch"
INVALID_OUTPUT = "InvalidOutput"  # an output failed validation; the decoder was stopped
DECODER_ERROR = "DecoderError"  # a DecoderError the decoder raised deliberately
INTERNAL_ERROR = "InternalError"  # unexpected exception in decoder code (stopped)
NOT_LOADED = "NotLoaded"
STOPPED = "Stopped"
BAD_REQUEST = "BadRequest"

__all__ = [
    "BAD_REQUEST",
    "DECODER_ERROR",
    "INCOMPATIBLE",
    "INPUT_MISMATCH",
    "INTERNAL_ERROR",
    "INVALID_OUTPUT",
    "LENGTH",
    "LOAD_FAILED",
    "MAX_FRAME_BYTES",
    "MAX_HEADER_BYTES",
    "MAX_STEP_BINS",
    "MODEL_LOAD_ERROR",
    "NOT_LOADED",
    "PROTOCOL",
    "STOPPED",
    "UNTRUSTED_MODEL",
    "WireError",
    "buffer_specs",
    "check_length",
    "decode_buffer",
    "decode_header",
    "encode_message",
    "read_message",
    "write_message",
]
