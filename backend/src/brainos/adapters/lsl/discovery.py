"""LSL stream discovery and resolution (wraps the official liblsl via pylsl).

All functions here block (network I/O); call them from a worker thread.
"""

from __future__ import annotations

import logging
from typing import Any

from brainos.adapters.lsl.metadata import (
    FORMAT_NAMES,
    ChannelMeta,
    Declaration,
    StreamMeta,
    _bool,
    _opt,
)

log = logging.getLogger(__name__)


class LSLUnavailableError(RuntimeError):
    pass


def _pylsl() -> Any:
    try:
        import pylsl
    except ImportError as exc:  # pragma: no cover - depends on install
        raise LSLUnavailableError("LSL support not installed: pip install 'brainos[live]'") from exc
    return pylsl


def library_info() -> str:
    pylsl = _pylsl()
    return f"pylsl {pylsl.__version__}, liblsl {pylsl.library_version()}"


def meta_from_info(info: Any, *, with_desc: bool) -> StreamMeta:
    channels: list[ChannelMeta] = []
    decl = Declaration()
    manufacturer = None
    if with_desc:
        desc = info.desc()
        ch = desc.child("channels").child("channel")
        i = 0
        while not ch.empty():
            channels.append(
                ChannelMeta(
                    index=i,
                    label=_opt(ch.child_value("label")),
                    unit=_opt(ch.child_value("unit")),
                    type=_opt(ch.child_value("type")),
                )
            )
            ch = ch.next_sibling("channel")
            i += 1
        b = desc.child("brainos")
        if not b.empty():
            decl = Declaration(
                prerecorded=_bool(b.child_value("prerecorded")),
                synthetic=_bool(b.child_value("synthetic")),
                origin=_opt(b.child_value("origin")),
                feature=_opt(b.child_value("feature")),
                quantity=_opt(b.child_value("quantity")),
            )
        manufacturer = _opt(desc.child_value("manufacturer"))
    return StreamMeta(
        name=info.name(),
        type=info.type(),
        source_id=info.source_id(),
        hostname=info.hostname(),
        uid=info.uid(),
        channel_count=int(info.channel_count()),
        nominal_srate=float(info.nominal_srate()),
        channel_format=FORMAT_NAMES.get(int(info.channel_format()), "unknown"),
        created_at=float(info.created_at()),
        channels=tuple(channels),
        declaration=decl,
        manufacturer=manufacturer,
    )


def full_info(info: Any, timeout: float = 2.0) -> tuple[Any, StreamMeta]:
    """Open a temporary inlet to obtain the full StreamInfo (incl. <desc>)."""
    pylsl = _pylsl()
    inlet = pylsl.StreamInlet(info, max_buflen=1, recover=False)
    try:
        full = inlet.info(timeout=timeout)
        return full, meta_from_info(full, with_desc=True)
    finally:
        inlet.close_stream()
        del inlet


def discover(wait_s: float = 1.5, *, with_desc: bool = True) -> list[tuple[Any, StreamMeta]]:
    """Resolve all LSL streams visible on the network within ``wait_s``."""
    pylsl = _pylsl()
    infos = pylsl.resolve_streams(wait_time=wait_s)
    out: list[tuple[Any, StreamMeta]] = []
    for info in infos:
        if with_desc:
            try:
                out.append(full_info(info))
                continue
            except Exception as exc:  # timeout/lost: keep the header-only view
                log.warning("LSL: could not read metadata of %s: %s", info.name(), exc)
        out.append((info, meta_from_info(info, with_desc=False)))
    return out


def resolve(meta: StreamMeta, timeout: float) -> Any | None:
    """Find the current incarnation of a stream (it may have restarted with a new uid).

    Identity is the source_id when the publisher set one (LSL's recommended practice);
    otherwise name + hostname + type.
    """
    pylsl = _pylsl()
    if meta.source_id:
        found = pylsl.resolve_byprop("source_id", meta.source_id, minimum=1, timeout=timeout)
    else:

        def q(s: str) -> str:
            return s.replace("'", "")

        pred = f"name='{q(meta.name)}' and hostname='{q(meta.hostname)}' and type='{q(meta.type)}'"
        found = pylsl.resolve_bypred(pred, minimum=1, timeout=timeout)
    if not found:
        return None
    # newest incarnation first
    return max(found, key=lambda i: i.created_at())
