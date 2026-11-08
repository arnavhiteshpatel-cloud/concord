"""Reference side for LSL: XDF files (LabRecorder output), read with pyxdf.

XDF stores, per stream, the samples with their **source** timestamps (seconds on the
publisher's ``lsl_local_clock``) plus ClockOffset measurements (recorder clock minus source
clock, measured by the recorder). pyxdf by default applies those offsets and dejitters the
timestamps; this module loads the file with ``synchronize_clocks=False`` and
``dejitter_timestamps=False`` so that the timestamps are exactly what the source sent, i.e.
the same clock domain as BrainOS's ``device_timestamp_ns`` (BrainOS opens LSL inlets with
``processing_flags=0``). The clock offsets are analysed separately (``timing.clock_offsets``).
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
from numpy.typing import NDArray

from brainos_hwval.model import InputError

log = logging.getLogger(__name__)

# Exact factors to microvolts (XDF meta-data convention recommends "microvolts").
UNIT_TO_UV: dict[str, float] = {
    "microvolts": 1.0,
    "microvolt": 1.0,
    "uv": 1.0,
    "µv": 1.0,
    "μv": 1.0,
    "millivolts": 1e3,
    "millivolt": 1e3,
    "mv": 1e3,
    "volts": 1e6,
    "volt": 1e6,
    "v": 1e6,
    "nanovolts": 1e-3,
    "nanovolt": 1e-3,
    "nv": 1e-3,
}


@dataclass
class XDFChannel:
    index: int
    label: str | None
    unit: str | None
    type: str | None


@dataclass
class XDFStream:
    stream_id: int
    name: str
    type: str
    source_id: str
    hostname: str
    uid: str
    session_id: str
    channel_count: int
    nominal_srate: float
    channel_format: str
    created_at: float | None
    channels: list[XDFChannel]
    declaration: dict[str, str]  # <desc><brainos>...</brainos> if present
    manufacturer: str | None
    values: NDArray[Any] | None  # (n, channels) numeric; None for string streams
    strings: list[Any] | None
    time_stamps: NDArray[np.float64]
    clock_times: NDArray[np.float64]
    clock_values: NDArray[np.float64]
    footer: dict[str, Any]
    pyxdf_effective_srate: float | None
    info_raw: dict[str, Any] = field(repr=False, default_factory=dict)

    @property
    def is_numeric(self) -> bool:
        return self.values is not None

    @property
    def n(self) -> int:
        return len(self.time_stamps)

    def describe(self) -> dict[str, Any]:
        return {
            "stream_id": self.stream_id,
            "name": self.name,
            "type": self.type,
            "source_id": self.source_id or None,
            "hostname": self.hostname,
            "uid": self.uid,
            "channel_count": self.channel_count,
            "nominal_srate": self.nominal_srate,
            "channel_format": self.channel_format,
            "samples": self.n,
            "channels_described": len(self.channels) == self.channel_count,
            "manufacturer": self.manufacturer,
            "declaration": self.declaration or None,
        }


def _first(d: Any, key: str) -> Any:
    if not isinstance(d, dict):
        return None
    v = d.get(key)
    if isinstance(v, list):
        return v[0] if v else None
    return v


def _text(d: Any, key: str) -> str | None:
    v = _first(d, key)
    if v is None:
        return None
    s = str(v).strip()
    return s or None


def _channels(desc: Any) -> list[XDFChannel]:
    # pyxdf: desc -> {"channels": [{"channel": [ {label: [..]}, ... ]}]}
    container = _first(desc, "channels")
    items = container.get("channel", []) if isinstance(container, dict) else []
    out = []
    for i, ch in enumerate(items):
        out.append(XDFChannel(i, _text(ch, "label"), _text(ch, "unit"), _text(ch, "type")))
    return out


def _declaration(desc: Any) -> dict[str, str]:
    b = _first(desc, "brainos")
    if not isinstance(b, dict):
        return {}
    out = {}
    for k in ("prerecorded", "synthetic", "origin", "feature", "quantity"):
        t = _text(b, k)
        if t is not None:
            out[k] = t
    return out


def _float(s: Any) -> float | None:
    try:
        x = float(s)
    except (TypeError, ValueError):
        return None
    return x if math.isfinite(x) else None


def load_xdf(path: Path) -> tuple[dict[str, Any], list[XDFStream]]:
    path = Path(path)
    if not path.is_file():
        raise InputError(f"XDF file not found: {path}")
    try:
        import pyxdf
    except ImportError as exc:  # pragma: no cover - dependency of the package
        raise InputError("pyxdf is required to read XDF files (pip install pyxdf)") from exc
    try:
        raw_streams, header = pyxdf.load_xdf(
            str(path),
            synchronize_clocks=False,
            dejitter_timestamps=False,
            handle_clock_resets=False,
        )
    except Exception as exc:  # pyxdf raises plain Exceptions / struct errors on bad files
        raise InputError(
            f"{path.name}: not a readable XDF file: {type(exc).__name__}: {exc}"
        ) from exc
    streams = [_stream(s) for s in raw_streams]
    hdr = header.get("info", {}) if isinstance(header, dict) else {}
    file_header = {k: _first(hdr, k) for k in hdr} if isinstance(hdr, dict) else {}
    return file_header, streams


def _stream(s: dict[str, Any]) -> XDFStream:
    info = s.get("info", {})
    desc = _first(info, "desc")
    fmt = str(_text(info, "channel_format") or "")
    count = int(_text(info, "channel_count") or 0)
    ts = np.asarray(s.get("time_stamps", []), dtype=np.float64).reshape(-1)
    series = s.get("time_series")
    values: NDArray[Any] | None = None
    strings: list[Any] | None = None
    if fmt == "string":
        strings = list(series) if series is not None else []
    else:
        arr = np.asarray(series)
        if arr.size == 0:
            arr = np.zeros((0, count), dtype=np.float64)
        values = arr.reshape(-1, count) if count else arr
    footer_info = _first(s.get("footer", {}), "info") if s.get("footer") else None
    footer: dict[str, Any] = {}
    if isinstance(footer_info, dict):
        for k in ("first_timestamp", "last_timestamp", "sample_count"):
            footer[k] = _text(footer_info, k)
    ct = np.asarray(s.get("clock_times", []), dtype=np.float64).reshape(-1)
    cv = np.asarray(s.get("clock_values", []), dtype=np.float64).reshape(-1)
    eff = info.get("effective_srate") if isinstance(info, dict) else None
    return XDFStream(
        stream_id=int(info.get("stream_id", 0)) if isinstance(info, dict) else 0,
        name=_text(info, "name") or "",
        type=_text(info, "type") or "",
        source_id=_text(info, "source_id") or "",
        hostname=_text(info, "hostname") or "",
        uid=_text(info, "uid") or "",
        session_id=_text(info, "session_id") or "",
        channel_count=count,
        nominal_srate=_float(_text(info, "nominal_srate")) or 0.0,
        channel_format=fmt,
        created_at=_float(_text(info, "created_at")),
        channels=_channels(desc),
        declaration=_declaration(desc),
        manufacturer=_text(desc, "manufacturer") if isinstance(desc, dict) else None,
        values=values,
        strings=strings,
        time_stamps=ts,
        clock_times=ct,
        clock_values=cv,
        footer=footer,
        pyxdf_effective_srate=_float(eff),
        info_raw={k: v for k, v in info.items() if k != "desc"} if isinstance(info, dict) else {},
    )


def unit_scales(stream: XDFStream) -> tuple[list[float] | None, list[str | None]]:
    """Per-channel factor to µV if every channel states a known voltage unit, else None."""
    units = [c.unit for c in stream.channels]
    if len(stream.channels) != stream.channel_count:
        return None, units
    scales = [UNIT_TO_UV.get(u.strip().lower()) if u else None for u in units]
    if any(s is None for s in scales):
        return None, units
    return [float(s) for s in scales if s is not None], units
