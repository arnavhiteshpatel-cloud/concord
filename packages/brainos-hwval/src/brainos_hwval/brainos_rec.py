"""Reader for BrainOS recordings (``*.brainos.jsonl``, format ``brainos.recording/1``).

Layout (backend/src/brainos/adapters/replay/format.py, runtime/recorder.py):

* line 1: header ``{"format", "schema_version", "created_at_ns", "device", "synthetic", "note"}``
  where ``device`` is the DeviceDescriptor the adapter refined after ``open()``;
* line 2+: one EventEnvelope per line, in ``seq`` order. ``recording.frame`` payloads carry
  ``samples[channel][sample]``, ``first_sample_index``, ``sample_rate_hz`` and ``unit``;
  ``device_timestamp_ns`` is the source timestamp of the frame's **first** sample and
  ``timestamp_ns`` the BrainOS host wall clock at ingest.

This reader is independent of BrainOS (a lab can run it without installing BrainOS). If
BrainOS is importable, every envelope is additionally validated against BrainOS's own
contract models.
"""

from __future__ import annotations

import json
import logging
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
from numpy.typing import NDArray

from brainos_hwval.model import InputError

log = logging.getLogger(__name__)

RECORDING_FORMAT = "brainos.recording/1"
FRAME = "recording.frame"
ANNOTATION = "recording.annotation"
STATUS = "device.status"
MAX_EXAMPLES = 10


@dataclass
class Frame:
    seq: int
    index: int  # first_sample_index
    t_dev_ns: int | None  # device_timestamp_ns (first sample)
    t_wall_ns: int  # timestamp_ns (BrainOS ingest wall clock)
    rate: float
    unit: str
    data: NDArray[np.float64]  # (n_samples, n_channels)
    flags: tuple[str, ...]
    provenance: dict[str, Any]

    @property
    def n(self) -> int:
        return int(self.data.shape[0])


@dataclass
class Annotation:
    seq: int
    t_dev_ns: int | None
    t_wall_ns: int
    label: str
    value: Any


@dataclass
class BrainOSRecording:
    path: Path
    header: dict[str, Any]
    frames: list[Frame]
    annotations: list[Annotation]
    status_events: list[dict[str, Any]]
    malformed: list[dict[str, Any]]  # unreadable or invalid lines (line number + reason)
    event_counts: dict[str, int]
    seq_gaps: list[tuple[int, int]]  # (expected seq, found seq)
    seq_regressions: int
    contract: dict[str, Any] = field(default_factory=dict)
    # BrainOS recorder markers next to the file (runtime/recorder.py, Milestone 5 D):
    # <name>.recovery.json = the writer died and the file was cut to its valid prefix;
    # <name>.active.json = a recorder is (or was, if it crashed) still writing the file.
    recovery: dict[str, Any] | None = None
    still_active: bool = False

    @property
    def device(self) -> dict[str, Any]:
        d = self.header.get("device")
        return d if isinstance(d, dict) else {}

    def capability_params(self, capability: str) -> dict[str, Any]:
        for cap in self.device.get("capabilities", []):
            if isinstance(cap, dict) and cap.get("capability") == capability:
                params = cap.get("params")
                return params if isinstance(params, dict) else {}
        return {}

    @property
    def recording_params(self) -> dict[str, Any]:
        return self.capability_params("recording")

    @property
    def channel_count(self) -> int | None:
        counts = {f.data.shape[1] for f in self.frames}
        return counts.pop() if len(counts) == 1 else None

    def channel_labels(self) -> list[str] | None:
        p = self.recording_params
        labels = p.get("channel_labels") or p.get("channel_names")
        if isinstance(labels, list) and all(isinstance(x, str) for x in labels):
            return list(labels)
        return None

    def provenance_flags(self) -> dict[str, Any]:
        synthetic = {bool(f.provenance.get("synthetic")) for f in self.frames}
        replayed = {bool(f.provenance.get("replayed")) for f in self.frames}
        origins = sorted({str(f.provenance.get("origin")) for f in self.frames})
        adapters = sorted({str(f.provenance.get("adapter")) for f in self.frames})
        return {
            "header_synthetic": bool(self.header.get("synthetic")),
            "device_kind": self.device.get("kind"),
            "frames_synthetic": sorted(synthetic),
            "frames_replayed": sorted(replayed),
            "origins": origins[:5],
            "adapters": adapters,
        }


def _contract_validator() -> Any | None:
    try:
        from brainos.contracts.events import EventEnvelope
        from pydantic import TypeAdapter
    except Exception:  # BrainOS not installed: the structural checks below still apply
        return None
    return TypeAdapter(EventEnvelope)


def load_brainos_recording(path: Path, *, validate_contract: bool = True) -> BrainOSRecording:
    path = Path(path)
    if not path.is_file():
        raise InputError(f"BrainOS recording not found: {path}")
    validator = _contract_validator() if validate_contract else None
    frames: list[Frame] = []
    annotations: list[Annotation] = []
    statuses: list[dict[str, Any]] = []
    malformed: list[dict[str, Any]] = []
    counts: Counter[str] = Counter()
    seq_gaps: list[tuple[int, int]] = []
    regressions = 0
    contract_ok = contract_bad = 0
    contract_examples: list[str] = []
    last_seq: int | None = None
    try:
        fh = path.open("r", encoding="utf-8")
    except OSError as exc:
        raise InputError(f"cannot open {path}: {exc}") from exc
    with fh:
        try:
            first = fh.readline()
            header = json.loads(first)
        except (ValueError, UnicodeDecodeError) as exc:
            raise InputError(
                f"{path.name}: line 1 is not a BrainOS recording header: {exc}"
            ) from exc
        if not isinstance(header, dict) or header.get("format") != RECORDING_FORMAT:
            got = header.get("format") if isinstance(header, dict) else type(header).__name__
            raise InputError(
                f"{path.name}: not a BrainOS recording (format {got!r}, expected "
                f"{RECORDING_FORMAT!r})"
            )
        if not isinstance(header.get("device"), dict):
            raise InputError(f"{path.name}: header has no device descriptor")
        for lineno, line in enumerate(fh, start=2):
            if not line.strip():
                continue
            try:
                env = json.loads(line)
                if not isinstance(env, dict):
                    raise ValueError("not a JSON object")
                seq = int(env["seq"])
                etype = str(env["event_type"])
                t_wall = int(env["timestamp_ns"])
            except (ValueError, KeyError, TypeError, UnicodeDecodeError) as exc:
                if len(malformed) < 1000:
                    malformed.append({"line": lineno, "reason": f"{type(exc).__name__}: {exc}"})
                continue
            if validator is not None:
                try:
                    validator.validate_python(env)
                    contract_ok += 1
                except Exception as exc:  # pydantic ValidationError
                    contract_bad += 1
                    if len(contract_examples) < MAX_EXAMPLES:
                        contract_examples.append(f"line {lineno}: {str(exc).splitlines()[0]}")
            if last_seq is not None:
                if seq < last_seq:
                    regressions += 1
                elif seq != last_seq + 1 and len(seq_gaps) < 1000:
                    seq_gaps.append((last_seq + 1, seq))
            last_seq = seq
            counts[etype] += 1
            dev = env.get("device_timestamp_ns")
            t_dev = int(dev) if isinstance(dev, int | float) else None
            if etype == FRAME:
                try:
                    frames.append(_frame(env, seq, t_dev, t_wall))
                except (ValueError, KeyError, TypeError) as exc:
                    if len(malformed) < 1000:
                        malformed.append({"line": lineno, "reason": f"bad frame: {exc}"})
            elif etype == ANNOTATION:
                p = env.get("payload") or {}
                annotations.append(
                    Annotation(seq, t_dev, t_wall, str(p.get("label")), p.get("value"))
                )
            elif etype == STATUS:
                statuses.append(
                    {"seq": seq, "t_wall_ns": t_wall, "payload": env.get("payload") or {}}
                )
    stem = path.name.removesuffix(".brainos.jsonl")
    recovery: dict[str, Any] | None = None
    rec_marker = path.parent / f"{stem}.recovery.json"
    if rec_marker.is_file():
        try:
            loaded = json.loads(rec_marker.read_text(encoding="utf-8"))
            recovery = loaded if isinstance(loaded, dict) else {"raw": loaded}
        except (OSError, ValueError) as exc:
            recovery = {"unreadable": str(exc)}
    still_active = (path.parent / f"{stem}.active.json").is_file()
    contract: dict[str, Any] = (
        {"validated": True, "valid_events": contract_ok, "invalid_events": contract_bad}
        if validator is not None
        else {"validated": False, "reason": "BrainOS is not installed; contract not validated"}
    )
    if contract_examples:
        contract["examples"] = contract_examples
    return BrainOSRecording(
        path=path,
        header=header,
        frames=frames,
        annotations=annotations,
        status_events=statuses,
        malformed=malformed,
        event_counts=dict(counts),
        seq_gaps=seq_gaps,
        seq_regressions=regressions,
        contract=contract,
        recovery=recovery,
        still_active=still_active,
    )


def _frame(env: dict[str, Any], seq: int, t_dev: int | None, t_wall: int) -> Frame:
    p = env["payload"]
    samples = p["samples"]
    data = np.asarray(samples, dtype=np.float64)
    if data.ndim != 2 or data.shape[0] != int(p["channel_count"]) or data.shape[1] == 0:
        raise ValueError(f"samples shape {data.shape} vs channel_count {p.get('channel_count')}")
    if not np.all(np.isfinite(data)):
        raise ValueError("non-finite sample values")
    q = env.get("quality") or {}
    prov = env.get("provenance") or {}
    return Frame(
        seq=seq,
        index=int(p["first_sample_index"]),
        t_dev_ns=t_dev,
        t_wall_ns=t_wall,
        rate=float(p["sample_rate_hz"]),
        unit=str(p.get("unit", "uV")),
        data=np.ascontiguousarray(data.T),
        flags=tuple(str(f) for f in q.get("flags", [])),
        provenance=dict(prov) if isinstance(prov, dict) else {},
    )


def summary(rec: BrainOSRecording) -> dict[str, Any]:
    """Short description for `inspect` and the report."""
    frames = rec.frames
    n = sum(f.n for f in frames)
    rates = sorted({f.rate for f in frames})
    units = sorted({f.unit for f in frames})
    d = rec.device
    return {
        "path": str(rec.path),
        "format": rec.header.get("format"),
        "schema_version": rec.header.get("schema_version"),
        "created_at_ns": rec.header.get("created_at_ns"),
        "device_id": d.get("device_id"),
        "display_name": d.get("display_name"),
        "adapter": d.get("adapter"),
        "kind": d.get("kind"),
        "synthetic": rec.header.get("synthetic"),
        "note": rec.header.get("note"),
        "event_counts": rec.event_counts,
        "frames": len(frames),
        "samples": n,
        "channel_count": rec.channel_count,
        "channel_labels": rec.channel_labels(),
        "sample_rates_hz": rates,
        "units": units,
        "first_sample_index": frames[0].index if frames else None,
        "last_sample_index": frames[-1].index + frames[-1].n - 1 if frames else None,
        "frames_flagged_dropped_samples": sum("dropped_samples" in f.flags for f in frames),
        "malformed_lines": len(rec.malformed),
        "seq_gaps": len(rec.seq_gaps),
        "contract": rec.contract,
    }
