"""Record a source through BrainOS's own runtime for a verification run (needs BrainOS).

This drives the unchanged BrainOS acquisition path — LiveSourceRegistry, the LSL or Open
Ephys adapter, Runtime and Recorder — exactly as the console does, and writes:

* ``<name>.brainos.jsonl``  the BrainOS recording (format brainos.recording/1); since BrainOS
  Milestone 5 its header holds the adapter's source metadata at the START (LSL uid,
  source_id, host, time correction) and a statement of what its timestamps can reconstruct;
* ``<name>.capture.json``   a sidecar with what the recording itself does not keep: the
  adapter's source metadata at the END (final integrity counters), BrainOS wall-clock vs
  ``lsl_local_clock`` pairs (for absolute latency), runtime diagnostics and versions.

The console or REST API can produce the same recording; the sidecar is optional for the
comparison. The recorder's duration and size limits are set per capture (BrainOS's own
defaults, 300 s and 200 MiB with raw frames, are configurable in its ``[recording]`` config).
"""

from __future__ import annotations

import asyncio
import json
import logging
import platform
import re
import socket
import time
from pathlib import Path
from typing import Any, cast

from brainos_hwval import __version__
from brainos_hwval.model import InputError

log = logging.getLogger(__name__)

SIDECAR_FORMAT = "brainos-hwval.capture/1"
MAX_DURATION_S = 24 * 3600.0  # BrainOS's upper bound for a recording limit (MAX_RECORDING_S)
MAX_SIZE_MB = 100 * 1024  # BrainOS's upper bound for a recording size limit (MAX_RECORDING_MIB)
DEFAULT_MAX_SIZE_MB = 2048
LIMIT_MARGIN_S = 30.0  # the recorder's duration limit sits this far past --duration
NAME_RE = re.compile(r"^[a-z0-9][a-z0-9_\-]{0,47}$")  # BrainOS recording names


def _import_brainos() -> Any:
    try:
        import brainos
        from brainos.runtime import DeviceRegistry, Recorder, Runtime  # noqa: F401
    except ImportError as exc:
        raise InputError(
            "`brainos-hwval capture` needs BrainOS installed (pip install -e 'backend[live]' "
            f"from the BrainOS repository): {exc}"
        ) from exc
    return brainos


def _clock_pair() -> dict[str, Any] | None:
    try:
        import pylsl
    except ImportError:
        return None
    best: tuple[int, float, int] | None = None
    for _ in range(9):  # keep the tightest of several back-to-back readings
        a = time.time_ns()
        lc = float(pylsl.local_clock())
        b = time.time_ns()
        if best is None or b - a < best[2]:
            best = ((a + b) // 2, lc, b - a)
    assert best is not None
    return {"wall_ns": best[0], "lsl_local_clock_s": best[1], "uncertainty_ns": best[2]}


def _prepare(out_dir: Path, name: str, duration_s: float, max_size_mb: int) -> None:
    if not 0 < duration_s <= MAX_DURATION_S - LIMIT_MARGIN_S:
        raise InputError(
            f"--duration must be in (0, {MAX_DURATION_S - LIMIT_MARGIN_S:g}] s "
            "(BrainOS recording limit)"
        )
    if not 1 <= max_size_mb <= MAX_SIZE_MB:
        raise InputError(f"--max-size-mb must be 1-{MAX_SIZE_MB}")
    if not NAME_RE.match(name):
        raise InputError(f"--name {name!r}: use [a-z0-9][a-z0-9_-]*, at most 48 characters")
    out_dir.mkdir(parents=True, exist_ok=True)
    rec_path = out_dir / f"{name}.brainos.jsonl"
    if rec_path.exists():
        raise InputError(f"{rec_path} already exists; choose another --name")


async def _run(
    configure: Any,
    duration_s: float,
    out_dir: Path,
    name: str,
    protocol: str,
    params: dict[str, Any],
    max_size_mb: int = DEFAULT_MAX_SIZE_MB,
) -> tuple[Path, Path]:
    brainos = _import_brainos()
    from brainos.adapters.simulated import OperatorIntentSource
    from brainos.runtime import DeviceRegistry, Recorder, Runtime

    rec_path = out_dir / f"{name}.brainos.jsonl"
    reg = DeviceRegistry(
        OperatorIntentSource(),
        out_dir,
        datasets_dir=out_dir / "_none",
        models_dir=out_dir / "_none",
    )
    device_id = await asyncio.to_thread(configure, reg)
    try:
        recorder = Recorder(
            out_dir,
            max_duration_s=duration_s + LIMIT_MARGIN_S,
            max_bytes=max_size_mb * 1024 * 1024,
        )
    except TypeError as exc:  # a BrainOS from before configurable recording limits
        raise InputError(
            f"this BrainOS cannot set recording limits (needs Milestone 5 or later): {exc}"
        ) from exc
    rt = Runtime(reg, recorder)
    pairs: list[dict[str, Any]] = []
    started = time.time_ns()
    try:
        await rt.connect(device_id)
        p = _clock_pair() if protocol == "lsl" else None
        if p:
            pairs.append(p)
        rt.start_recording(name)
        t_end = time.monotonic() + duration_s
        while time.monotonic() < t_end:
            await asyncio.sleep(min(0.5, max(0.0, t_end - time.monotonic())))
            if rt.recorder.active_name is None:
                break
        p = _clock_pair() if protocol == "lsl" else None
        if p:
            pairs.append(p)
        stop_reason = "duration reached"
        if rt.recorder.active_name is not None:
            rt.stop_recording()
        else:
            stop_reason = f"recorder stopped early: {rt.recorder.stop_reason}"
        adapter = rt.adapter
        source_metadata = getattr(adapter, "source_metadata", None)
        meta = source_metadata() if callable(source_metadata) else None
        diag = rt.diagnostics_snapshot().model_dump(mode="json")
    finally:
        await rt.shutdown()
    sidecar = {
        "format": SIDECAR_FORMAT,
        "tool": f"brainos-hwval {__version__}",
        "protocol": protocol,
        "brainos_version": getattr(brainos, "__version__", None),
        "recording": rec_path.name,
        "device_id": device_id,
        "parameters": params,
        "started_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(started / 1e9)),
        "duration_s": (time.time_ns() - started) / 1e9,
        "stop_reason": stop_reason,
        "recorder_limits": {"max_duration_s": recorder.max_duration_s, "max_size_mb": max_size_mb},
        "host": {"hostname": socket.gethostname(), "platform": platform.platform()},
        "clock_pairs": pairs,
        "source_metadata": meta,
        "diagnostics": diag,
    }
    side = out_dir / f"{name}.capture.json"
    side.write_text(json.dumps(sidecar, indent=1, default=str) + "\n", encoding="utf-8")
    return rec_path, side


def capture_lsl(
    *,
    stream: str,
    source_id: str | None,
    hostname: str | None,
    duration_s: float,
    out_dir: Path,
    name: str,
    discover_s: float = 2.0,
    max_size_mb: int = DEFAULT_MAX_SIZE_MB,
) -> tuple[Path, Path]:
    """Record the LSL stream named ``stream`` (optionally narrowed by source_id / host)."""

    def configure(reg: Any) -> str:
        found = reg.live.discover_lsl(discover_s)
        hits = [
            d
            for d in found
            if d.meta.name == stream
            and (source_id is None or d.meta.source_id == source_id)
            and (hostname is None or d.meta.hostname == hostname)
        ]
        if len(hits) != 1:
            seen = [
                f"{d.meta.name} ({d.meta.type}, source_id={d.meta.source_id!r}, "
                f"host={d.meta.hostname})"
                for d in found
            ]
            raise InputError(
                f"{len(hits)} LSL streams match name={stream!r} source_id={source_id!r} "
                f"host={hostname!r}; visible: {seen or 'none'}"
            )
        d = hits[0]
        if not d.usable_as_signal:
            raise InputError(f"stream {stream!r} cannot be a BrainOS signal stream: {d.reason}")
        return str(reg.live.configure_lsl(d.key, None, None).device_id)

    params = {"stream": stream, "source_id": source_id, "hostname": hostname}
    _prepare(out_dir, name, duration_s, max_size_mb)
    return asyncio.run(_run(configure, duration_s, out_dir, name, "lsl", params, max_size_mb))


def capture_openephys(
    *,
    host: str,
    data_port: int,
    unit: str,
    duration_s: float,
    out_dir: Path,
    name: str,
    max_size_mb: int = DEFAULT_MAX_SIZE_MB,
) -> tuple[Path, Path]:
    """Record the Open Ephys ZMQ Interface at ``host:data_port``."""

    def configure(reg: Any) -> str:
        from brainos.adapters.openephys import OpenEphysConfig

        try:
            cfg = OpenEphysConfig(host=host, data_port=data_port, unit=cast(Any, unit))
        except ValueError as exc:
            raise InputError(f"invalid Open Ephys settings: {exc}") from exc
        return str(reg.live.configure_openephys(cfg).device_id)

    params = {"host": host, "data_port": data_port, "unit": unit}
    _prepare(out_dir, name, duration_s, max_size_mb)
    return asyncio.run(_run(configure, duration_s, out_dir, name, "openephys", params, max_size_mb))
