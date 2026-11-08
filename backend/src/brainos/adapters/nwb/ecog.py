"""Raw-voltage intracranial recordings (e.g. ECoG) from NWB ``ElectricalSeries`` (Milestone 5).

``load_electrical(path)`` reads the metadata of one NWB file whose neural data is a continuous
voltage ``ElectricalSeries`` (no spike-sorted units): sampling, unit conversion, the electrodes
table (labels, groups, locations, coordinates, good/bad flags), pose ``SpatialSeries`` and
interval tables. ``NWBElectricalSource`` replays it through the standard ``ReplayAdapter``:

  * ``recording.frame`` — raw voltage, 100 ms frames, in **µV** only when the file declares a
    convertible unit (NWB: value in volts = data x conversion [x channel_conversion] + offset),
    otherwise ``arbitrary`` (values unscaled)                    (provenance ``raw_signal``)
  * ``behavior.sample`` — pose keypoints, one sample per video frame (``behavioral_label``)
  * ``recording.annotation`` — rows of the file's interval tables (``behavioral_label``)

It is an OFFLINE REPLAY of a past recording (``kind = replay``), never a live device. It
emits no intents: decoding happens only in the BrainOS pipeline with a held-out model.

Nothing is invented: what the file does not state is reported in ``notes``; dataset facts that
are not in the file (modality, mains frequency) come only from the pinned dataset manifest.
"""

from __future__ import annotations

import bisect
import heapq
import json
import re
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

import numpy as np
from numpy.typing import NDArray

from brainos.adapters.nwb.reader import NWBFormatError, UnsupportedModalityError, describe_contents
from brainos.adapters.nwb.source import device_id_for
from brainos.adapters.replay.format import ReplayRecord
from brainos.contracts.capabilities import Capability, CapabilityDescriptor, EventType
from brainos.contracts.events import Provenance, ProvenanceKind, Quality, QualityFlag
from brainos.contracts.protocol import (
    INVASIVE_MODALITIES,
    DatasetInfo,
    DeviceDescriptor,
    DeviceKind,
    Modality,
    SourceBehavior,
    SourceElectrode,
    SourceFile,
    SourceIntervals,
    SourceMetadata,
    SourceSignal,
    SourceSlice,
)
from brainos.datasets import Verification, sha256_file, verify_file, verify_slice

ADAPTER = "brainos.nwb.ecog@0.1.0"
FRAME_MS = 100.0
READ_BLOCK = 4096  # samples read per HDF5 access (chunk-friendly)
VOLT_UNITS = {"volts": 1.0, "volt": 1.0, "v": 1.0, "millivolts": 1e-3, "mv": 1e-3}
VOLT_UNITS |= {"microvolts": 1e-6, "uv": 1e-6, "µv": 1e-6}
MODALITY_WORDS = {
    Modality.ECOG: "ECoG",
    Modality.SEEG: "sEEG",
    Modality.INTRACORTICAL: "Intracortical Data",
    Modality.EEG: "EEG",
}
# AJILE12-style coarse labels: which blocklisted epochs invalidate which stream
DATA_BREAK = re.compile(r"blocklist.*data break", re.I)
POSE_BLOCK = re.compile(r"blocklist.*camera", re.I)
# per-electrode quality flags: column name -> True means "bad"
BAD_COLUMNS: tuple[tuple[str, bool], ...] = (("bad", True), ("good", False))
LABEL_COLUMNS = ("label", "channel_name", "electrode_name", "name")


@dataclass(frozen=True, slots=True)
class Electrode:
    index: int
    id: int
    label: str
    group: str | None
    group_description: str | None
    location: str | None
    x: float | None
    y: float | None
    z: float | None
    bad: bool | None
    filtering: str | None


@dataclass(frozen=True, slots=True)
class Interval:
    table: str
    start_s: float
    stop_s: float
    value: str | None


@dataclass
class PoseData:
    series: list[str]
    dims: list[str]
    rate: float
    start_s: float  # time of frame 0
    values: NDArray[np.float64]  # (frames, dims)
    valid: NDArray[np.bool_]
    unit: str
    declared_unit: str


@dataclass
class NWBElectricalRecording:
    path: Path
    identifier: str
    session_description: str
    session_start_time: str
    experiment_description: str
    institution: str
    lab: str
    species: str | None
    subject_id: str | None
    series: str
    fs: float
    t0_s: float  # time of the first sample (seconds since session start)
    n_samples: int
    electrodes: list[Electrode]
    unit: Literal["uV", "arbitrary"]
    declared_unit: str
    conversion: float | None
    scale: NDArray[np.float64]  # per channel: stored value -> output unit
    offset_out: float  # added after scaling (output unit)
    pose: PoseData | None
    intervals: list[Interval]
    interval_tables: dict[str, tuple[str, int]]  # name -> (description, rows)
    provenance: dict[str, Any] | None  # BrainOS extract note, if the file is an extract
    notes: list[str] = field(default_factory=list)

    @property
    def channel_count(self) -> int:
        return len(self.electrodes)

    @property
    def duration_s(self) -> float:
        return self.n_samples / self.fs

    @property
    def channel_labels(self) -> list[str]:
        return [e.label for e in self.electrodes]

    @property
    def bad_channels(self) -> list[str]:
        return [e.label for e in self.electrodes if e.bad]

    @property
    def first_sample_index(self) -> int:
        if self.provenance and isinstance(self.provenance.get("samples"), list):
            return int(self.provenance["samples"][0])
        return 0

    def data_breaks(self) -> list[tuple[float, float]]:
        return [
            (iv.start_s, iv.stop_s)
            for iv in self.intervals
            if iv.value is not None and DATA_BREAK.search(iv.value)
        ]

    def iter_samples(self, block: int = READ_BLOCK) -> Iterator[tuple[int, NDArray[np.float64]]]:
        """(first index, samples (n, channels) in the output unit), reading lazily."""
        import h5py

        with h5py.File(self.path, "r") as f:
            ds = f[self.series + "/data"]
            if ds.shape[0] != self.n_samples or ds.shape[1] != self.channel_count:
                raise NWBFormatError(f"{self.path.name}: {self.series} changed on disk")
            for start in range(0, self.n_samples, block):
                raw = np.asarray(ds[start : start + block, :], dtype=np.float64)
                yield start, raw * self.scale + self.offset_out

    def samples(self, start: int, stop: int) -> NDArray[np.float64]:
        import h5py

        with h5py.File(self.path, "r") as f:
            raw = np.asarray(f[self.series + "/data"][start:stop, :], dtype=np.float64)
        return raw * self.scale + self.offset_out


def _s(x: Any) -> str:
    if x is None:
        return ""
    return x.decode() if isinstance(x, bytes) else str(x)


def _f(x: Any) -> float | None:
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return v if np.isfinite(v) else None


def has_electrical_series(path: Path) -> bool:
    """Cheap check (h5py only): an ElectricalSeries in acquisition and no spike-time units."""
    import h5py

    try:
        with h5py.File(path, "r") as f:
            if "units" in f and "spike_times" in f["units"]:
                return False
            acq = f.get("acquisition", {})
            return any(
                _s(acq[k].attrs.get("neurodata_type", "")) == "ElectricalSeries" for k in acq
            )
    except OSError:
        return False


def load_electrical(path: Path, *, modality: Modality | None = None) -> NWBElectricalRecording:
    try:
        from pynwb import NWBHDF5IO
        from pynwb.ecephys import ElectricalSeries
    except ImportError as exc:  # pragma: no cover - depends on install
        raise NWBFormatError("NWB support is not installed: pip install 'brainos[nwb]'") from exc
    path = Path(path)
    if not path.is_file():
        raise NWBFormatError(f"{path}: no such file")
    try:
        io = NWBHDF5IO(str(path), "r")
    except Exception as exc:
        raise NWBFormatError(
            f"{path.name}: not a readable NWB/HDF5 file ({type(exc).__name__}: {exc})"
        ) from exc
    with io:
        try:
            nwb = io.read()
        except Exception as exc:
            raise NWBFormatError(
                f"{path.name}: NWB read failed ({type(exc).__name__}: {exc})"
            ) from exc
        series = [
            (k, v) for k, v in (nwb.acquisition or {}).items() if isinstance(v, ElectricalSeries)
        ]
        if not series:
            raise UnsupportedModalityError(
                f"{path.name}: no ElectricalSeries in acquisition; file contains "
                f"{describe_contents(nwb)}"
            )
        notes: list[str] = []
        if len(series) > 1:
            notes.append(
                f"{len(series)} ElectricalSeries in acquisition; using {series[0][0]!r} "
                f"(others: {[k for k, _ in series[1:]]})."
            )
        return _extract(path, nwb, series[0][0], series[0][1], notes, modality)


def _extract(
    path: Path, nwb: Any, name: str, es: Any, notes: list[str], modality: Modality | None
) -> NWBElectricalRecording:
    shape = es.data.shape
    if len(shape) != 2 or shape[0] == 0 or shape[1] == 0:
        raise NWBFormatError(f"{path.name}: {name} must be 2-D (samples, channels), got {shape}")
    if es.timestamps is not None:
        raise NWBFormatError(
            f"{path.name}: {name} uses explicit timestamps; only regularly sampled series "
            "(starting_time + rate) are supported"
        )
    fs = float(es.rate)
    if not np.isfinite(fs) or fs <= 0 or fs > 100_000:
        raise NWBFormatError(f"{path.name}: {name} has an invalid rate {es.rate!r}")
    n, n_ch = int(shape[0]), int(shape[1])
    if n_ch > 1024:
        raise NWBFormatError(f"{path.name}: {n_ch} channels exceed the 1024-channel frame limit")
    electrodes = _electrodes(path, es, n_ch, notes)
    unit, scale, offset_out, declared, conversion = _units(es, n_ch, notes)
    pose = _pose(nwb, notes)
    intervals, tables = _intervals(nwb, notes)
    if pose is not None:
        blocked = [
            (iv.start_s, iv.stop_s) for iv in intervals if iv.value and POSE_BLOCK.search(iv.value)
        ]
        if blocked:
            t = pose.start_s + np.arange(pose.values.shape[0]) / pose.rate
            for a, b in blocked:
                pose.valid[(t >= a) & (t < b)] = False
            notes.append(
                f"Pose samples inside {len(blocked)} camera-blocklisted epoch(s) are marked "
                "invalid (the dataset's own coarse labels)."
            )
    breaks = [iv for iv in intervals if iv.value and DATA_BREAK.search(iv.value)]
    if breaks:
        notes.append(
            f"{len(breaks)} 'data break' epoch(s) (blocklisted by the dataset authors) overlap "
            "this recording; samples there are passed through unchanged, and frames overlapping "
            "them are flagged dropped_samples (quality 0.5)."
        )
    prov = _provenance(nwb)
    if prov is not None:
        notes.append(
            f"BrainOS extract of {prov.get('asset_path')} samples {prov.get('samples')} "
            "(streamed from DANDI with HTTP range requests). Times are seconds since the original "
            "session start."
        )
    subject = nwb.subject
    return NWBElectricalRecording(
        path=path,
        identifier=_s(nwb.identifier),
        session_description=_s(nwb.session_description),
        session_start_time=nwb.session_start_time.isoformat() if nwb.session_start_time else "",
        experiment_description=_s(nwb.experiment_description),
        institution=_s(nwb.institution),
        lab=_s(nwb.lab),
        species=_s(subject.species) if subject is not None and subject.species else None,
        subject_id=_s(subject.subject_id) if subject is not None and subject.subject_id else None,
        series=f"acquisition/{name}",
        fs=fs,
        t0_s=float(es.starting_time or 0.0),
        n_samples=n,
        electrodes=electrodes,
        unit=unit,
        declared_unit=declared,
        conversion=conversion,
        scale=scale,
        offset_out=offset_out,
        pose=pose,
        intervals=intervals,
        interval_tables=tables,
        provenance=prov,
        notes=notes,
    )


def _provenance(nwb: Any) -> dict[str, Any] | None:
    txt = _s(getattr(nwb, "notes", None))
    if not txt.startswith("{"):
        return None
    try:
        obj = json.loads(txt).get("brainos_extract")
    except (ValueError, AttributeError):
        return None
    return obj if isinstance(obj, dict) else None


def _electrodes(path: Path, es: Any, n_ch: int, notes: list[str]) -> list[Electrode]:
    region = es.electrodes
    if region is None:
        notes.append("No electrodes table region: channels are numbered only.")
        return [
            Electrode(i, i, f"ch{i}", None, None, None, None, None, None, None, None)
            for i in range(n_ch)
        ]
    table = region.table
    rows = [int(r) for r in region.data[:]]
    if len(rows) != n_ch:
        raise NWBFormatError(
            f"{path.name}: electrodes region has {len(rows)} rows for {n_ch} channels"
        )
    cols = set(table.colnames)
    ids = [int(i) for i in table.id[:]]
    label_col = next((c for c in LABEL_COLUMNS if c in cols), None)
    bad_col = next(((c, inv) for c, inv in BAD_COLUMNS if c in cols), None)

    def col(c: str) -> list[Any] | None:
        return list(table[c].data[:]) if c in cols else None

    labels, groups, locs = col(label_col) if label_col else None, col("group_name"), col("location")
    xs, ys, zs, filt = col("x"), col("y"), col("z"), col("filtering")
    flags = col(bad_col[0]) if bad_col else None
    group_objs = col("group")
    out: list[Electrode] = []
    for i, r in enumerate(rows):
        gname = _s(groups[r]) if groups else None
        gobj = group_objs[r] if group_objs else None
        bad = None if flags is None or bad_col is None else bool(flags[r]) == bad_col[1]
        out.append(
            Electrode(
                index=i,
                id=ids[r],
                label=_s(labels[r]) if labels else f"{gname or 'e'}/{ids[r]}",
                group=gname,
                group_description=_s(getattr(gobj, "description", None)) or None,
                location=_s(locs[r]) if locs else None,
                x=_f(xs[r]) if xs else None,
                y=_f(ys[r]) if ys else None,
                z=_f(zs[r]) if zs else None,
                bad=bad,
                filtering=_s(filt[r]) if filt else None,
            )
        )
    if not label_col:
        notes.append(
            "The electrodes table stores no channel names; channels are labelled "
            "'<electrode group>/<electrode id>' from the table."
        )
    if locs is not None and all(_s(v).lower() in ("", "unknown") for v in locs):
        notes.append(
            "Electrode 'location' is 'unknown' for every electrode in the file; no anatomical "
            "labels are available (x/y/z are reported as stored, coordinate space not stated)."
        )
    if bad_col is None:
        notes.append("No good/bad electrode column: channel quality is not stated by the file.")
    else:
        nbad = sum(1 for e in out if e.bad)
        notes.append(
            f"Electrode quality from the file's '{bad_col[0]}' column: {nbad} of {n_ch} marked "
            f"bad ({', '.join(e.label for e in out if e.bad) or 'none'})."
        )
    return out


def _units(
    es: Any, n_ch: int, notes: list[str]
) -> tuple[Literal["uV", "arbitrary"], NDArray[np.float64], float, str, float | None]:
    declared = _s(getattr(es, "unit", "")) or ""
    conv = _f(getattr(es, "conversion", None))
    offset = _f(getattr(es, "offset", 0.0)) or 0.0
    chconv = getattr(es, "channel_conversion", None)
    per_ch = np.ones(n_ch)
    if chconv is not None:
        per_ch = np.asarray(chconv[:], dtype=np.float64)
        if per_ch.shape != (n_ch,) or not np.all(np.isfinite(per_ch)) or np.any(per_ch == 0):
            notes.append("channel_conversion is malformed; signal reported as 'arbitrary'.")
            return "arbitrary", np.ones(n_ch), 0.0, declared, conv
    factor = VOLT_UNITS.get(declared.strip().lower())
    if factor is None or conv is None or conv == 0:
        why = (
            f"unit {declared!r} is not a voltage unit"
            if factor is None
            else f"conversion {getattr(es, 'conversion', None)!r} is not a usable factor"
        )
        notes.append(f"Signal reported as 'arbitrary' (values unscaled): {why}.")
        return "arbitrary", np.ones(n_ch), 0.0, declared, conv
    # NWB: value_in_unit = data * conversion * channel_conversion + offset
    scale = conv * per_ch * factor * 1e6
    notes.append(
        f"Signal in µV from the file's declaration: data x conversion ({conv:g})"
        + (" x channel_conversion" if chconv is not None else "")
        + f" in {declared} -> x {scale[0]:g} to µV"
        + (f", offset {offset:g} {declared}" if offset else "")
        + "."
    )
    return "uV", scale, offset * factor * 1e6, declared, conv


def _pose(nwb: Any, notes: list[str]) -> PoseData | None:
    from pynwb.behavior import Position

    module = (nwb.processing or {}).get("behavior")
    pos = None
    if module is not None:
        pos = next((v for v in module.data_interfaces.values() if isinstance(v, Position)), None)
    if pos is None or not pos.spatial_series:
        notes.append("No pose/position series in processing/behavior: no behavior stream.")
        return None
    names = sorted(pos.spatial_series)
    ss = [pos.spatial_series[k] for k in names]
    rate = _f(ss[0].rate)
    start = _f(ss[0].starting_time) or 0.0
    n = ss[0].data.shape[0]
    keep = [
        (k, s)
        for k, s in zip(names, ss, strict=True)
        if s.timestamps is None
        and _f(s.rate) == rate
        and (_f(s.starting_time) or 0.0) == start
        and s.data.shape[0] == n
    ]
    if rate is None or not keep:
        notes.append("Pose series are not regularly sampled on one timebase; no behavior stream.")
        return None
    if len(keep) < len(names):
        notes.append(
            f"Pose series not on the common timebase were skipped: "
            f"{sorted(set(names) - {k for k, _ in keep})}."
        )
    dims: list[str] = []
    cols: list[NDArray[np.float64]] = []
    axes = "xyz"
    for k, s in keep:
        d = np.asarray(s.data[:], dtype=np.float64)
        d = d[:, None] if d.ndim == 1 else d
        for j in range(d.shape[1]):
            dims.append(f"{k}.{axes[j] if j < 3 else j}"[:32])
            cols.append(d[:, j])
    values = np.stack(cols, axis=1)
    declared = _s(keep[0][1].unit)
    convs = {_f(s.conversion) for _, s in keep}
    unit = "arbitrary"
    if None in convs:
        notes.append(
            f"Pose series declare unit {declared!r} but conversion "
            f"{float(keep[0][1].conversion)!r}: no valid scale. Positions are reported unscaled "
            "as 'arbitrary' (the dataset documents them as video pixel coordinates)."
        )
    elif convs == {1.0} and declared:
        unit = declared
    valid = np.isfinite(values).all(axis=1)
    if not valid.all():
        notes.append(
            f"{int((~valid).sum())} pose frame(s) contain NaN (keypoint not tracked); marked "
            "invalid and sent as 0."
        )
    values = np.where(np.isfinite(values), values, 0.0)
    return PoseData(
        series=[k for k, _ in keep],
        dims=dims,
        rate=rate,
        start_s=start,
        values=values,
        valid=valid,
        unit=unit,
        declared_unit=declared,
    )


def _intervals(nwb: Any, notes: list[str]) -> tuple[list[Interval], dict[str, tuple[str, int]]]:
    out: list[Interval] = []
    tables: dict[str, tuple[str, int]] = {}
    for name, tab in (nwb.intervals or {}).items():
        df_cols = tab.colnames
        start = np.asarray(tab["start_time"].data[:], dtype=np.float64)
        stop = np.asarray(tab["stop_time"].data[:], dtype=np.float64)
        text_col = next(
            (
                c
                for c in df_cols
                if c not in ("start_time", "stop_time")
                and len(tab[c].data) > 0
                and isinstance(tab[c].data[0], str | bytes)
            ),
            None,
        )
        vals = [_s(v) for v in tab[text_col].data[:]] if text_col else [None] * len(start)
        tables[name] = (_s(tab.description), len(start))
        for a, b, v in zip(start, stop, vals, strict=True):
            out.append(Interval(name, float(a), float(b), v if v else None))
    out.sort(key=lambda iv: iv.start_s)
    if not tables:
        notes.append("No interval tables (trials/epochs/events): no annotations.")
    return out, tables


# =========================================================================== source


def _is_human(species: str | None) -> bool:
    return bool(species) and "homo sapiens" in str(species).lower()


def verify_electrical(path: Path) -> Verification:
    """Whole-file match against pinned assets, else extract-slice match by data digest."""
    from brainos.datasets.extract import extract_digest

    v = verify_file(path)
    if v.verified:
        return v
    digest, _ = extract_digest(path)
    return verify_slice(v.sha256, digest) if digest else v


class NWBElectricalSource:
    """A raw-voltage NWB recording as a ``ReplaySource`` (offline replay, never live)."""

    def __init__(
        self,
        path: Path,
        *,
        verification: Verification | None = None,
        recording: NWBElectricalRecording | None = None,
    ) -> None:
        self.path = Path(path)
        self.verification = verification or verify_electrical(self.path)
        m = self.verification.manifest
        self.modality = Modality(m.modality) if m is not None and m.modality else None
        self.line_hz = m.line_hz if m is not None else None
        self.rec = recording or load_electrical(self.path, modality=self.modality)
        self._check_slice()
        self.name = self.path.stem
        a, s = self.verification.asset, self.verification.slice
        if m and a and s:
            t0, t1 = self.rec.t0_s, self.rec.t0_s + self.rec.duration_s
            self.origin = f"dandi:{m.dandiset}/{a.path}#t={t0:g}-{t1:g}"[:128]
        elif m and a:
            self.origin = f"dandi:{m.dandiset}/{a.path}"[:128]
        else:
            self.origin = f"file:{self.path.name}"[:128]
        self.frame_samples = max(1, round(self.rec.fs * FRAME_MS / 1000))
        self._q = Quality(score=1.0, flags=[])
        self._q_break = Quality(score=0.5, flags=[QualityFlag.DROPPED_SAMPLES])
        self._p_raw = Provenance(
            kind=ProvenanceKind.RAW_SIGNAL, adapter=ADAPTER, synthetic=False, origin=self.origin
        )
        self._p_beh = Provenance(
            kind=ProvenanceKind.BEHAVIORAL_LABEL,
            adapter=ADAPTER,
            synthetic=False,
            origin=self.origin,
        )

    def _check_slice(self) -> None:
        s, rec = self.verification.slice, self.rec
        if s is None:
            return
        a, b = s.samples
        if rec.n_samples != b - a or rec.channel_count != s.channels:
            raise NWBFormatError(
                f"{self.path.name}: shape ({rec.n_samples}, {rec.channel_count}) does not match "
                f"pinned slice {s.id} ({b - a}, {s.channels})"
            )
        if abs(rec.t0_s - a / rec.fs) > 0.5 / rec.fs:
            raise NWBFormatError(
                f"{self.path.name}: starting_time {rec.t0_s} s is not the pinned slice start "
                f"{a / rec.fs} s; the timeline was altered"
            )

    # ------------------------------------------------------------ labels
    @property
    def label(self) -> str:
        human = _is_human(self.rec.species)
        what = MODALITY_WORDS.get(self.modality, "Neural Data") if self.modality else "Neural Data"
        return f"Recorded {'Human ' if human else ''}{what} — Offline Replay"

    @property
    def invasive(self) -> bool | None:
        return None if self.modality is None else self.modality in INVASIVE_MODALITIES

    # --------------------------------------------------------- ReplaySource API
    def duration_ns(self) -> int | None:
        return round(self.rec.duration_s * 1e9)

    def descriptor(self) -> DeviceDescriptor:
        rec = self.rec
        params: dict[str, Any] = {
            "sample_rate_hz": rec.fs,
            "channel_count": rec.channel_count,
            "unit": rec.unit,
            "frame_samples": self.frame_samples,
            "channel_labels": rec.channel_labels,
            "bad_channels": rec.bad_channels,
        }
        if self.line_hz:
            params["line_hz"] = float(self.line_hz)
        caps = [
            CapabilityDescriptor(
                capability=Capability.RECORDING,
                params=params,
                description=(
                    "Recorded raw voltage per electrode"
                    + (
                        " (µV, from the file's unit declaration)"
                        if rec.unit == "uV"
                        else " (arbitrary units: the file declares no convertible unit)"
                    )
                    + "; interval tables as annotations."
                ),
            )
        ]
        if rec.pose is not None:
            caps.append(
                CapabilityDescriptor(
                    capability=Capability.BEHAVIOR,
                    params={
                        "quantity": "position",
                        "dims": rec.pose.dims,
                        "unit": rec.pose.unit,
                        "rate_hz": rec.pose.rate,
                    },
                    description="Recorded pose (behavioral ground truth, not an intent).",
                )
            )
        caps.append(CapabilityDescriptor(capability=Capability.DEVICE_STATUS))
        m = self.verification.manifest
        where = f"DANDI {m.dandiset}" if m else "unverified local file"
        return DeviceDescriptor(
            device_id=device_id_for(self.path),
            display_name=self.label,
            kind=DeviceKind.REPLAY,
            adapter=ADAPTER,
            description=(
                f"{self.path.name} ({where}). Offline replay of a recording made in the past; "
                "not a live implant connection."
            ),
            native_format="NWB 2.x / HDF5: ElectricalSeries (raw voltage) + electrodes table",
            capabilities=caps,
            synthetic=False,
            modality=self.modality,
            invasive=self.invasive,
        )

    def records(self) -> Iterator[ReplayRecord]:
        return heapq.merge(
            self._frames(), self._behavior(), self._annotations(), key=lambda r: r.t_ns
        )

    def _t_ns(self, t_s: float) -> int:
        return max(0, round(t_s * 1e9))

    def _frames(self) -> Iterator[ReplayRecord]:
        rec, fsz = self.rec, self.frame_samples
        breaks = sorted(rec.data_breaks())
        b_start = [a for a, _ in breaks]
        b_reach = np.maximum.accumulate([b for _, b in breaks]) if breaks else np.zeros(0)

        def overlaps_break(t0: float, t1: float) -> bool:
            k = bisect.bisect_left(b_start, t1)  # breaks starting before the frame ends
            return k > 0 and bool(b_reach[k - 1] > t0)  # ... one of which ends after it starts

        first_index = rec.first_sample_index
        pending: NDArray[np.float64] | None = None
        pending_start = 0
        for start, block in rec.iter_samples():
            if pending is not None and pending.shape[0]:
                block = np.vstack([pending, block])
                start = pending_start
            usable = (block.shape[0] // fsz) * fsz
            last = start + block.shape[0] >= rec.n_samples
            if last:
                usable = block.shape[0]
            for j in range(0, usable, fsz):
                part = block[j : j + fsz]
                i0 = start + j
                t_first = rec.t0_s + i0 / rec.fs
                t_end = rec.t0_s + (i0 + part.shape[0]) / rec.fs
                hit = overlaps_break(t_first, t_end)
                yield ReplayRecord(
                    # paced when the frame's LAST sample exists (causal availability);
                    # device time = its first sample
                    t_ns=self._t_ns(t_end),
                    envelope={
                        "event_type": EventType.RECORDING_FRAME.value,
                        "payload": {
                            "sample_rate_hz": rec.fs,
                            "channel_count": rec.channel_count,
                            "first_sample_index": first_index + i0,
                            "unit": rec.unit,
                            "samples": part.T.tolist(),
                        },
                        "quality": self._q_break if hit else self._q,
                        "provenance": self._p_raw,
                        "device_timestamp_ns": self._t_ns(t_first),
                    },
                )
            pending = block[usable:]
            pending_start = start + usable

    def _behavior(self) -> Iterator[ReplayRecord]:
        pose = self.rec.pose
        if pose is None:
            return
        t_lo, t_hi = self.rec.t0_s, self.rec.t0_s + self.rec.duration_s
        for i in range(pose.values.shape[0]):
            t = pose.start_s + i / pose.rate
            if not t_lo <= t < t_hi:
                continue
            yield ReplayRecord(
                t_ns=self._t_ns(t),
                envelope={
                    "event_type": EventType.BEHAVIOR_SAMPLE.value,
                    "payload": {
                        "quantity": "position",
                        "dims": pose.dims,
                        "unit": pose.unit,
                        "values": [float(v) for v in pose.values[i]],
                        "sample_index": i,
                        "valid": bool(pose.valid[i]),
                    },
                    "quality": self._q,
                    "provenance": self._p_beh,
                    "device_timestamp_ns": self._t_ns(t),
                },
            )

    def _annotations(self) -> Iterator[ReplayRecord]:
        t_lo, t_hi = self.rec.t0_s, self.rec.t0_s + self.rec.duration_s
        for iv in self.rec.intervals:
            if not t_lo <= iv.start_s < t_hi:
                continue  # rows that start outside the recording are not emitted
            if iv.table == "epochs" and iv.value is None:
                continue  # unlabelled stretch of the coarse-label timeline
            label = "epoch" if iv.table == "epochs" else iv.table
            yield ReplayRecord(
                t_ns=self._t_ns(iv.start_s),
                envelope={
                    "event_type": EventType.RECORDING_ANNOTATION.value,
                    "payload": {
                        "label": label[:128],
                        "value": iv.value[:256] if iv.value else None,
                        "duration_ms": max(0.0, (iv.stop_s - iv.start_s) * 1000),
                    },
                    "quality": self._q,
                    "provenance": self._p_beh,
                    "device_timestamp_ns": self._t_ns(iv.start_s),
                },
            )

    # ---------------------------------------------------------------- metadata
    def metadata(self) -> SourceMetadata:
        rec, v = self.rec, self.verification
        m, a, s = v.manifest, v.asset, v.slice
        notes = list(m.notes) if m else []
        notes += rec.notes
        if rec.session_start_time[:4].isdigit() and int(rec.session_start_time[:4]) <= 2000:
            notes.append(
                f"Session date {rec.session_start_time[:10]} is a de-identification date shift, "
                "not the real recording date."
            )
        t_lo, t_hi = rec.t0_s, rec.t0_s + rec.duration_s
        intervals = [
            SourceIntervals(
                table=name,
                description=desc,
                rows=sum(
                    1 for iv in rec.intervals if iv.table == name and t_lo <= iv.start_s < t_hi
                ),
                emitted_as=f"recording.annotation label '{'epoch' if name == 'epochs' else name}'",
            )
            for name, (desc, _rows) in rec.interval_tables.items()
        ]
        pose = rec.pose
        return SourceMetadata(
            device_id=device_id_for(self.path),
            label=self.label,
            source_type="nwb_electrical_series",
            dataset=DatasetInfo(
                id=m.id,
                title=m.title,
                dandiset=m.dandiset,
                version=m.version,
                url=m.url,
                license=m.license,
                access=m.access,
                citation=m.citation,
                asset_id=a.asset_id,
                asset_path=a.path,
            )
            if m and a
            else None,
            file=SourceFile(
                name=self.path.name,
                size_bytes=self.path.stat().st_size,
                sha256=v.sha256,
                verified=v.verified,
                verification=v.describe(),
            ),
            species=rec.species,
            subject_id=rec.subject_id,
            identifier=rec.identifier,
            session_description=rec.session_description,
            session_start_time=rec.session_start_time,
            experiment_description=rec.experiment_description,
            institution=rec.institution,
            lab=rec.lab,
            recording_type=m.recording_type if m else "raw voltage (NWB ElectricalSeries)",
            profile="ajile12" if m and m.id == "ajile12" else "electrical-series",
            feature="raw_voltage",
            feature_unit=rec.unit,
            bin_ms=1000.0 / rec.fs,
            n_bins=rec.n_samples,
            duration_s=round(rec.duration_s, 3),
            channel_count=rec.channel_count,
            channels=[],
            behavior=SourceBehavior(
                series="Position/" + ",".join(pose.series),
                quantity="position",
                dims=pose.dims,
                unit=pose.unit,
                valid_fraction=round(float(pose.valid.mean()), 4) if pose.valid.size else 0.0,
            )
            if pose is not None
            else None,
            decoder=None,
            notes=notes,
            modality=self.modality,
            invasive=self.invasive,
            signal=SourceSignal(
                series=rec.series,
                sample_rate_hz=rec.fs,
                unit=rec.unit,
                declared_unit=rec.declared_unit,
                conversion=rec.conversion,
                n_samples=rec.n_samples,
                start_s=rec.t0_s,
                first_sample_index=rec.first_sample_index,
                frame_samples=self.frame_samples,
                line_hz=self.line_hz,
                bad_channels=rec.bad_channels,
            ),
            electrodes=[
                SourceElectrode(
                    index=e.index,
                    id=e.id,
                    label=e.label,
                    group=e.group,
                    group_description=e.group_description,
                    location=e.location,
                    x=e.x,
                    y=e.y,
                    z=e.z,
                    bad=e.bad,
                    filtering=e.filtering,
                )
                for e in rec.electrodes
            ],
            intervals=intervals,
            slice=SourceSlice(
                id=s.id,
                asset_path=s.asset_path,
                asset_sha256=a.sha256 if a else "",
                series=s.series,
                samples=list(s.samples),
                data_sha256=s.data_sha256,
                role=s.role,
            )
            if s
            else None,
        )


__all__ = [
    "NWBElectricalRecording",
    "NWBElectricalSource",
    "has_electrical_series",
    "load_electrical",
    "sha256_file",
    "verify_electrical",
]
