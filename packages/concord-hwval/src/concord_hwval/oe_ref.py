"""Reference side for Open Ephys: the GUI's Binary recording format.

Facts used (Open Ephys GUI v1.1.0 source, ``Source/Processors/RecordNode/BinaryFormat/
BinaryRecording.cpp`` and ``SIMDConverter.cpp``; official reader ``open-ephys-python-tools``
``open_ephys/analysis/formats/BinaryRecording.py``):

``<Record Node N>/experimentE/recordingR/``
    ``structure.oebin``  JSON: ``"GUI version"``, ``continuous[]`` (folder_name, sample_rate,
    num_channels, stream_name, source_processor_name/id, channels[] with channel_name,
    bit_volts, units, history), ``events[]``, ``spikes[]``.
    ``continuous/<folder>/continuous.dat``  int16, interleaved (sample-major), value =
    clamp(round(µV / bit_volts), -32768, 32767).
    ``continuous/<folder>/sample_numbers.npy``  int64 sample number per row (GUI >= 0.6).
    ``continuous/<folder>/timestamps.npy``  float64 seconds (GUI >= 0.6, synchronised); in
    GUI 0.5.x this file holds the int64 sample numbers instead.
    ``events/<folder>/TTL/``  ``states.npy`` int16 = (line + 1) * (+1 rising | -1 falling),
    ``sample_numbers.npy``, ``timestamps.npy``, ``full_words.npy`` (0.5.x:
    ``channel_states.npy`` and int64 sample numbers in ``timestamps.npy``).
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
from numpy.typing import NDArray

from concord_hwval.model import InputError

log = logging.getLogger(__name__)

INT16_MIN, INT16_MAX = -32768, 32767


@dataclass
class OEChannel:
    name: str
    bit_volts: float
    units: str
    history: str | None


@dataclass
class OEContinuous:
    folder_name: str
    stream_name: str
    sample_rate: float
    source_processor_name: str
    source_processor_id: int | None
    channels: list[OEChannel]
    samples: NDArray[np.int16]  # (n, channels), memory-mapped
    sample_numbers: NDArray[np.int64]
    timestamps: NDArray[np.float64] | None
    problems: list[str] = field(default_factory=list)

    @property
    def n(self) -> int:
        return int(self.samples.shape[0])

    def describe(self) -> dict[str, Any]:
        sn = self.sample_numbers
        return {
            "folder_name": self.folder_name,
            "stream_name": self.stream_name,
            "sample_rate": self.sample_rate,
            "source_processor": f"{self.source_processor_name} ({self.source_processor_id})",
            "num_channels": len(self.channels),
            "channel_names": [c.name for c in self.channels],
            "units": sorted({c.units for c in self.channels}),
            "bit_volts": sorted({c.bit_volts for c in self.channels}),
            "samples": self.n,
            "first_sample_number": int(sn[0]) if len(sn) else None,
            "last_sample_number": int(sn[-1]) if len(sn) else None,
            "history": sorted({c.history for c in self.channels if c.history}),
            "problems": self.problems,
        }


@dataclass
class OETTL:
    folder: str
    lines: NDArray[np.int64]  # 0-based line
    rising: NDArray[np.bool_]
    sample_numbers: NDArray[np.int64]
    full_words: NDArray[np.uint64] | None


@dataclass
class OERecording:
    path: Path
    gui_version: str
    version: float
    oebin: dict[str, Any]
    continuous: list[OEContinuous]
    ttl: list[OETTL]
    sync_messages: str | None

    def stream(self, name: str | None) -> OEContinuous:
        if name is None:
            if len(self.continuous) == 1:
                return self.continuous[0]
            names = [c.stream_name for c in self.continuous]
            raise InputError(
                f"{self.path} has {len(names)} continuous streams {names}; choose one with --stream"
            )
        for c in self.continuous:
            if name in (c.stream_name, c.folder_name, c.folder_name.rstrip("/")):
                return c
        names = [c.stream_name for c in self.continuous]
        raise InputError(f"stream {name!r} not in {self.path} (streams: {names})")


def find_recordings(path: Path) -> list[Path]:
    """Recording directories (containing structure.oebin) at or below ``path``."""
    path = Path(path)
    if path.is_file() and path.name == "structure.oebin":
        return [path.parent]
    if (path / "structure.oebin").is_file():
        return [path]
    if not path.is_dir():
        raise InputError(f"Open Ephys recording not found: {path}")
    return sorted(p.parent for p in path.rglob("structure.oebin"))


def resolve_recording(path: Path) -> Path:
    found = find_recordings(path)
    if not found:
        raise InputError(
            f"no structure.oebin under {path}: not an Open Ephys Binary-format recording "
            "(set the Record Node's format to Binary)"
        )
    if len(found) > 1:
        listing = "\n  ".join(str(p) for p in found)
        raise InputError(f"{path} contains {len(found)} recordings; pass one of them:\n  {listing}")
    return found[0]


def _version(text: str) -> float:
    try:
        return float(".".join(text.split(".")[:2]))
    except ValueError:
        return 0.0


def load_oe_recording(path: Path) -> OERecording:
    rdir = resolve_recording(path)
    try:
        oebin = json.loads((rdir / "structure.oebin").read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise InputError(f"{rdir / 'structure.oebin'}: unreadable JSON: {exc}") from exc
    if not isinstance(oebin, dict) or not isinstance(oebin.get("continuous"), list):
        raise InputError(f"{rdir / 'structure.oebin'}: no 'continuous' list")
    gui = str(oebin.get("GUI version", ""))
    version = _version(gui)
    conts = [_continuous(rdir, info, version) for info in oebin["continuous"]]
    ttl = _ttl(rdir, version)
    sync = rdir / "sync_messages.txt"
    return OERecording(
        path=rdir,
        gui_version=gui,
        version=version,
        oebin=oebin,
        continuous=conts,
        ttl=ttl,
        sync_messages=sync.read_text(encoding="utf-8", errors="replace")
        if sync.is_file()
        else None,
    )


def _continuous(rdir: Path, info: dict[str, Any], version: float) -> OEContinuous:
    try:
        folder = str(info["folder_name"])
        rate = float(info["sample_rate"])
        nch = int(info["num_channels"])
        chans = [
            OEChannel(
                name=str(c["channel_name"]),
                bit_volts=float(c["bit_volts"]),
                units=str(c.get("units", "")),
                history=str(c["history"]) if c.get("history") else None,
            )
            for c in info["channels"]
        ]
    except (KeyError, TypeError, ValueError) as exc:
        raise InputError(f"structure.oebin: malformed continuous entry: {exc}") from exc
    problems: list[str] = []
    if len(chans) != nch:
        problems.append(f"num_channels={nch} but {len(chans)} channel entries")
    d = rdir / "continuous" / folder
    dat = d / "continuous.dat"
    if not dat.is_file():
        raise InputError(f"missing {dat}")
    size = dat.stat().st_size
    width = max(nch, 1) * 2
    if size % width:
        problems.append(
            f"continuous.dat has {size} bytes, not a multiple of {width} "
            f"({nch} channels x int16): file truncated or channel count wrong"
        )
    rows = size // width
    raw = np.memmap(dat, mode="r", dtype="<i2", shape=(rows * max(nch, 1),)) if rows else None
    samples = (
        raw.reshape(rows, max(nch, 1))
        if raw is not None
        else np.zeros((0, max(nch, 1)), dtype=np.int16)
    )
    sn_file = d / ("sample_numbers.npy" if version >= 0.6 else "timestamps.npy")
    ts: NDArray[np.float64] | None = None
    try:
        if sn_file.is_file():
            sample_numbers = np.asarray(np.load(sn_file, mmap_mode="r"), dtype=np.int64)
        else:
            problems.append(f"{sn_file.name} missing: sample numbers assumed 0..n-1")
            sample_numbers = np.arange(rows, dtype=np.int64)
        if version >= 0.6 and (d / "timestamps.npy").is_file():
            ts = np.asarray(np.load(d / "timestamps.npy", mmap_mode="r"), dtype=np.float64)
    except (OSError, ValueError) as exc:
        raise InputError(f"{d}: unreadable .npy file: {exc}") from exc
    if len(sample_numbers) != rows:
        problems.append(
            f"{sn_file.name} has {len(sample_numbers)} entries, continuous.dat {rows} rows"
        )
    if ts is not None and len(ts) != rows:
        problems.append(f"timestamps.npy has {len(ts)} entries, continuous.dat {rows} rows")
    n = min(rows, len(sample_numbers)) if len(sample_numbers) else rows
    return OEContinuous(
        folder_name=folder.rstrip("/"),
        stream_name=str(info.get("stream_name") or info.get("source_processor_sub_idx", "")),
        sample_rate=rate,
        source_processor_name=str(info.get("source_processor_name", "")),
        source_processor_id=_int(info.get("source_processor_id")),
        channels=chans,
        samples=samples[:n],
        sample_numbers=sample_numbers[:n],
        timestamps=ts[:n] if ts is not None else None,
        problems=problems,
    )


def _int(x: Any) -> int | None:
    try:
        return int(x)
    except (TypeError, ValueError):
        return None


def _ttl(rdir: Path, version: float) -> list[OETTL]:
    out = []
    for d in sorted((rdir / "events").glob("*/TTL*")):
        if not d.is_dir():
            continue
        try:
            if version >= 0.6:
                states = np.load(d / "states.npy").astype(np.int64)
                sn = np.load(d / "sample_numbers.npy").astype(np.int64)
            else:
                states = np.load(d / "channel_states.npy").astype(np.int64)
                sn = np.load(d / "timestamps.npy").astype(np.int64)
            fw_file = d / "full_words.npy"
            fw = np.load(fw_file).astype(np.uint64) if fw_file.is_file() else None
        except (OSError, ValueError) as exc:
            raise InputError(f"{d}: unreadable TTL event files: {exc}") from exc
        if len(states) != len(sn):
            raise InputError(f"{d}: {len(states)} states but {len(sn)} sample numbers")
        out.append(
            OETTL(
                folder=d.parent.name,
                lines=np.abs(states) - 1,
                rising=states > 0,
                sample_numbers=sn,
                full_words=fw,
            )
        )
    return out


def official_crosscheck(rec: OERecording, stream: OEContinuous) -> dict[str, Any]:
    """Compare this parser with the official reader (open-ephys-python-tools), if installed."""
    try:
        from open_ephys.analysis.formats.BinaryRecording import BinaryRecording
    except Exception as exc:
        return {"status": "not_tested", "reason": f"open-ephys-python-tools not importable: {exc}"}
    try:
        factory: Any = BinaryRecording  # the official reader is not fully typed
        off = factory(str(rec.path))
        conts = off.continuous or []
    except Exception as exc:
        # the official reader cannot read this file at all (e.g. open-ephys-python-tools 1.0.1
        # raises KeyError 'source_processor_sub_dx' on every GUI < 0.6 recording): no
        # cross-check is possible, which is not evidence against this parser
        return {
            "status": "not_tested",
            "reason": f"official reader cannot load it: {type(exc).__name__}: {exc}",
        }
    match = None
    for c in conts:
        if c.name.rstrip("/") == stream.folder_name:
            match = c
    if match is None:
        return {"status": "fail", "reason": f"official reader has no stream {stream.folder_name}"}
    problems = []
    if list(match.metadata.channel_names) != [c.name for c in stream.channels]:
        problems.append("channel names differ")
    if [float(b) for b in match.metadata.bit_volts] != [c.bit_volts for c in stream.channels]:
        problems.append("bit_volts differ")
    if float(match.metadata.sample_rate) != stream.sample_rate:
        problems.append("sample rate differs")
    n = stream.n
    if match.samples.shape[0] < n or not np.array_equal(
        np.asarray(match.sample_numbers[:n]), stream.sample_numbers
    ):
        problems.append("sample numbers differ")
    probe = sorted({0, n // 2, max(n - 1, 0)}) if n else []
    for i in probe:
        got = np.asarray(match.get_samples(i, i + 1))[0]
        mine = stream.samples[i].astype(np.float64) * np.array(
            [c.bit_volts for c in stream.channels]
        )
        if not np.allclose(got, mine, rtol=0, atol=1e-9):
            problems.append(f"scaled values differ at row {i}")
    ttl_official = 0
    try:
        ev = off.events
        ttl_official = 0 if ev is None else len(ev)
    except Exception as exc:
        problems.append(f"official events failed: {exc}")
    ttl_mine = sum(len(t.sample_numbers) for t in rec.ttl)
    if ttl_official != ttl_mine:
        problems.append(f"TTL event count {ttl_mine} vs official {ttl_official}")
    import importlib.metadata as md

    try:
        version = md.version("open-ephys-python-tools")
    except md.PackageNotFoundError:
        version = "unknown"
    return {
        "status": "fail" if problems else "pass",
        "reader": f"open-ephys-python-tools {version}",
        "rows_compared": "all sample numbers; scaled values at rows " + ", ".join(map(str, probe)),
        "problems": problems,
    }
