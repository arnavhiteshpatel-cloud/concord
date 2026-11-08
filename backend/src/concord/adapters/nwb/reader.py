"""Read spike-time recordings from NWB files (PyNWB), with explicit metadata handling.

Supported in this milestone:
  * NWB ``units`` tables with ``spike_times`` (sorted or multi-unit activity), binned on
    demand into counts per channel per time bin.
  * Optionally, one 2-D behavioral ``TimeSeries`` in ``acquisition`` that defines the bin
    timebase (FALCON H1 profile: ``OpenLoopKinematicsVelocity`` + ``eval_mask``).

Not supported (rejected with a clear error): files without a units table, e.g. raw
voltage ``ElectricalSeries`` only, calcium imaging, or ``processing``-only features.

Nothing here invents metadata. What the file does not provide is reported in
``notes``; what the file states inconsistently is corrected only when the correction
is unambiguous, and every correction is recorded in ``notes``.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
from numpy.typing import NDArray

log = logging.getLogger(__name__)

DEFAULT_BIN_S = 0.02
TIMEBASE_TOLERANCE = 0.02  # relative mismatch allowed between behavior duration and spike span
CHUNK_BINS = 512


class NWBFormatError(ValueError):
    """The file cannot be used: not NWB, corrupt, or internally inconsistent."""


class UnsupportedModalityError(NWBFormatError):
    """The file is valid NWB but holds a modality this reader does not support."""


@dataclass(frozen=True, slots=True)
class Channel:
    index: int
    unit_id: int
    spike_count: int
    electrode: str | None  # None: the file provides no electrode mapping


@dataclass(frozen=True, slots=True)
class Behavior:
    series: str
    quantity: str
    dims: list[str]
    unit: str
    values: NDArray[np.float64]  # (n_bins, n_dims)
    valid: NDArray[np.bool_]  # (n_bins,)
    trial: NDArray[np.int64] | None  # (n_bins,) trial number, if provided


@dataclass
class NWBUnitsRecording:
    path: Path
    identifier: str
    session_description: str
    session_start_time: str
    experiment_description: str
    institution: str
    lab: str
    species: str | None
    subject_id: str | None
    channels: list[Channel]
    bin_s: float
    t0_s: float  # end time of the first bin
    n_bins: int
    profile: str
    feature: str
    behavior: Behavior | None
    notes: list[str] = field(default_factory=list)
    _spikes: list[NDArray[np.float64]] = field(default_factory=list, repr=False)

    @property
    def channel_count(self) -> int:
        return len(self.channels)

    @property
    def duration_s(self) -> float:
        return self.n_bins * self.bin_s

    def bin_end_s(self, i: int) -> float:
        return self.t0_s + i * self.bin_s

    def counts(self, start: int, stop: int) -> NDArray[np.int64]:
        """Counts for bins [start, stop): shape (stop-start, channels).

        Bin i covers [t_i - bin, t_i) where t_i is the bin end time (FALCON convention).
        """
        stop = min(stop, self.n_bins)
        if start >= stop:
            return np.zeros((0, self.channel_count), dtype=np.int64)
        # Edge k is computed as t0 + k*bin (k = start-1 .. stop-1) exactly like the reference
        # loader's timestamps, so spikes that sit on an edge land in the same bin.
        edges = self.t0_s + self.bin_s * np.arange(start - 1, stop, dtype=np.float64)
        last = stop == self.n_bins  # np.histogram closes the final bin on the right
        out = np.empty((stop - start, self.channel_count), dtype=np.int64)
        for c, spikes in enumerate(self._spikes):
            idx = np.searchsorted(spikes, edges, side="left")
            if last:
                idx[-1] = np.searchsorted(spikes, edges[-1], side="right")
            out[:, c] = np.diff(idx)
        return out

    def iter_counts(self, chunk: int = CHUNK_BINS) -> Iterator[tuple[int, NDArray[np.int64]]]:
        """Yield (first_bin_index, counts chunk) without materializing the whole session."""
        for start in range(0, self.n_bins, chunk):
            yield start, self.counts(start, start + chunk)


def _str(x: Any) -> str:
    return "" if x is None else str(x)


def _resolve_period(rate: float, n: int, spike_span_s: float, notes: list[str], name: str) -> float:
    """Determine the sample period of a regularly sampled TimeSeries.

    Accepts ``rate`` as Hz when consistent with the spike-time span. Some files store
    the *period* in the ``rate`` field; that is accepted only when it is the unique
    interpretation consistent with the spike times, and it is recorded in ``notes``.
    """
    if not np.isfinite(rate) or rate <= 0:
        raise NWBFormatError(f"{name}: invalid rate {rate!r}")
    as_hz = n / rate
    as_period = n * rate
    ok_hz = abs(as_hz - spike_span_s) <= TIMEBASE_TOLERANCE * spike_span_s + 2 / rate
    ok_period = abs(as_period - spike_span_s) <= TIMEBASE_TOLERANCE * spike_span_s + 2 * rate
    if ok_hz and not ok_period:
        return 1.0 / rate
    if ok_period and not ok_hz:
        notes.append(
            f"Timebase correction: {name}.rate = {rate:g} would imply {as_hz:,.0f} s of data "
            f"({n} samples), but spikes span {spike_span_s:.2f} s. Interpreted as a sample "
            f"period of {rate * 1000:g} ms ({1 / rate:g} Hz), giving {as_period:.2f} s. This is "
            "the only interpretation consistent with the spike times and matches the dataset "
            "authors' reference loader (FALCON: timestamps = offset + i * rate)."
        )
        return rate
    raise NWBFormatError(
        f"{name}: cannot establish a timebase: rate={rate:g} gives {as_hz:.2f} s as Hz or "
        f"{as_period:.2f} s as a period, but spikes span {spike_span_s:.2f} s"
    )


def describe_contents(nwbfile: Any) -> str:
    acq = {k: type(v).__name__ for k, v in (nwbfile.acquisition or {}).items()}
    proc = {k: list(m.data_interfaces) for k, m in (nwbfile.processing or {}).items()}
    return f"acquisition={acq or '{}'}, processing={proc or '{}'}"


def load(path: Path, *, bin_s: float = DEFAULT_BIN_S) -> NWBUnitsRecording:
    """Open an NWB file and extract a spike-time recording plus metadata."""
    try:
        from pynwb import NWBHDF5IO
    except ImportError as exc:  # pragma: no cover - depends on install
        raise NWBFormatError("NWB support is not installed: pip install 'concordos[nwb]'") from exc

    path = Path(path)
    if not path.is_file():
        raise NWBFormatError(f"{path}: no such file")
    try:
        io = NWBHDF5IO(str(path), "r")
    except Exception as exc:  # h5py/hdmf raise many types for non-HDF5 input
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
        return _extract(path, nwb, bin_s)


def _extract(path: Path, nwb: Any, default_bin_s: float) -> NWBUnitsRecording:
    notes: list[str] = []
    units = nwb.units
    if units is None or "spike_times" not in units.colnames:
        raise UnsupportedModalityError(
            f"{path.name}: no units table with spike_times. This reader supports spike-time "
            f"recordings only; file contains {describe_contents(nwb)}"
        )
    n_units = len(units.id)
    if n_units == 0:
        raise NWBFormatError(f"{path.name}: units table is empty")
    unit_ids = [int(i) for i in units.id[:]]
    spikes: list[NDArray[np.float64]] = []
    for i in range(n_units):
        s = np.asarray(units["spike_times"][i], dtype=np.float64)
        if s.size and not np.all(np.isfinite(s)):
            raise NWBFormatError(f"{path.name}: unit {unit_ids[i]} has non-finite spike times")
        if s.size > 1 and np.any(np.diff(s) < 0):
            s = np.sort(s)
            notes.append(f"Unit {unit_ids[i]}: spike times were not sorted; sorted on load.")
        spikes.append(s)
    nonempty = [s for s in spikes if s.size]
    if not nonempty:
        raise NWBFormatError(f"{path.name}: units table has no spikes")
    span_hi = max(float(s[-1]) for s in nonempty)

    electrode_col = "electrodes" in units.colnames
    if nwb.electrodes is None:
        notes.append(
            "No electrode table: physical electrode locations and array assignment are not "
            "provided by this file. Channels are identified by unit id only."
        )
    channels = [
        Channel(
            index=i,
            unit_id=unit_ids[i],
            spike_count=int(spikes[i].size),
            electrode=_electrode_label(units, i) if electrode_col else None,
        )
        for i in range(n_units)
    ]
    silent = sum(1 for c in channels if c.spike_count == 0)
    if silent:
        notes.append(f"{silent} channel(s) have no spikes in this file.")

    acq = nwb.acquisition or {}
    behavior: Behavior | None = None
    profile = "units-only"
    if "OpenLoopKinematicsVelocity" in acq:
        profile = "falcon-h1"
        behavior, bin_s, t0 = _falcon_h1_behavior(path, acq, span_hi, notes)
        n_bins = behavior.values.shape[0]
    else:
        bin_s = default_bin_s
        t0 = bin_s  # first bin covers [0, bin_s)
        n_bins = int(np.ceil((span_hi + 1e-12) / bin_s))
        notes.append(
            f"No supported behavioral series found; binned spikes at {bin_s * 1000:g} ms "
            f"from t=0 to the last spike ({span_hi:.2f} s)."
        )
    if t0 < 0:
        raise NWBFormatError(f"{path.name}: negative timebase start {t0}")
    late = sum(int(np.sum(s >= t0 + (n_bins - 1) * bin_s)) for s in spikes)
    early = sum(int(np.sum(s < t0 - bin_s)) for s in spikes)
    if early or late:
        notes.append(
            f"{early + late} spike(s) fall outside the behavioral timebase "
            f"[{t0 - bin_s:.3f}, {t0 + (n_bins - 1) * bin_s:.3f}) s and are not counted."
        )

    subject = nwb.subject
    desc = _str(getattr(units, "description", ""))
    feature = "spike_count"
    if "Autogenerated" in desc or not desc:
        notes.append(
            "Units table does not state whether units are single neurons or multi-unit "
            "threshold activity; counts are reported as 'spike_count' per unit."
        )
    return NWBUnitsRecording(
        path=path,
        identifier=_str(nwb.identifier),
        session_description=_str(nwb.session_description),
        session_start_time=nwb.session_start_time.isoformat() if nwb.session_start_time else "",
        experiment_description=_str(nwb.experiment_description),
        institution=_str(nwb.institution),
        lab=_str(nwb.lab),
        species=_str(subject.species) if subject is not None and subject.species else None,
        subject_id=_str(subject.subject_id) if subject is not None and subject.subject_id else None,
        channels=channels,
        bin_s=float(bin_s),
        t0_s=float(t0),
        n_bins=int(n_bins),
        profile=profile,
        feature=feature,
        behavior=behavior,
        notes=notes,
        _spikes=spikes,
    )


def _electrode_label(units: Any, i: int) -> str | None:
    try:
        row = units["electrodes"][i]
        return str(row.index.tolist() if hasattr(row, "index") else row)
    except Exception:  # electrode references vary widely across files
        return None


def _falcon_h1_behavior(
    path: Path, acq: Any, last_spike_s: float, notes: list[str]
) -> tuple[Behavior, float, float]:
    vel = acq["OpenLoopKinematicsVelocity"]
    data = np.asarray(vel.data[:], dtype=np.float64)
    # NWB: true values = data * conversion + offset (offset is a VALUE offset, not a time shift)
    conversion = float(getattr(vel, "conversion", 1.0) or 1.0)
    value_offset = float(getattr(vel, "offset", 0.0) or 0.0)
    if conversion != 1.0 or value_offset != 0.0:
        data = data * conversion + value_offset
        notes.append(
            f"Behavior values scaled per NWB: data * conversion ({conversion:g}) "
            f"+ offset ({value_offset:g})."
        )
    if data.ndim != 2 or data.shape[0] == 0:
        raise NWBFormatError(
            f"{path.name}: OpenLoopKinematicsVelocity must be 2-D, got {data.shape}"
        )
    if not np.all(np.isfinite(data)):
        bad = int(np.sum(~np.isfinite(data).all(axis=1)))
        notes.append(f"{bad} behavior sample(s) contain NaN/Inf; marked invalid and sent as 0.")
    n, d = data.shape
    if vel.timestamps is not None:
        ts = np.asarray(vel.timestamps[:], dtype=np.float64)
        steps = np.diff(ts)
        if ts.size != n or np.any(steps <= 0):
            raise NWBFormatError(f"{path.name}: behavior timestamps are not strictly increasing")
        bin_s = float(np.median(steps))
        if not np.allclose(steps, bin_s, rtol=1e-3):
            raise NWBFormatError(f"{path.name}: irregular behavior timestamps are not supported")
        t0 = float(ts[0])
    else:
        t0 = float(getattr(vel, "starting_time", 0.0) or 0.0)
        # spikes run from about one bin before t0 to the end of the series
        bin_s = _resolve_period(
            float(vel.rate), n, last_spike_s - t0, notes, "OpenLoopKinematicsVelocity"
        )
    dims = [s.strip() for s in _str(vel.description).split(",") if s.strip()]
    if len(dims) != d:
        notes.append(
            f"Behavior description does not name {d} dimensions ({vel.description!r}); "
            "using generic names."
        )
        dims = [f"dim{i}" for i in range(d)]
    valid = np.ones(n, dtype=bool)
    if "eval_mask" in acq:
        mask = np.asarray(acq["eval_mask"].data[:]).astype(bool)
        if mask.shape != (n,):
            raise NWBFormatError(
                f"{path.name}: eval_mask length {mask.shape} != behavior length {n}"
            )
        valid = mask
        notes.append(
            "eval_mask: True = sample included in evaluation, following the dataset authors' "
            "reference loader ('True if should evaluate'). The file's own description "
            "('Timesteps to ignore covariates') reads as the opposite; the loader is "
            f"authoritative. {valid.mean() * 100:.1f}% of samples are valid."
        )
    else:
        notes.append("No eval_mask: all behavior samples treated as valid.")
    if "eval_mask" not in acq and "Blacklist" in acq:
        black = np.asarray(acq["Blacklist"].data[:]).astype(bool)
        if black.shape != (n,):
            raise NWBFormatError(
                f"{path.name}: Blacklist length {black.shape} != behavior length {n}"
            )
        valid = ~black
        notes[-1] = (
            "Older FALCON format: no eval_mask; valid = NOT Blacklist, as in the authors' loader. "
            f"{valid.mean() * 100:.1f}% of samples are valid."
        )
    valid &= np.isfinite(data).all(axis=1)
    data = np.where(np.isfinite(data), data, 0.0)
    trial = None
    if "TrialNum" in acq:
        tn = np.asarray(acq["TrialNum"].data[:])
        if tn.shape == (n,):
            trial = tn.astype(np.int64)
        else:
            notes.append("TrialNum length does not match behavior; trial numbers ignored.")
    unit = _str(vel.unit) or "unspecified"
    if unit == "arbitrary":
        notes.append("Kinematic velocity unit is 'arbitrary' in the file (no physical scale).")
    # FALCON: bin timestamps are bin *ends*; first bin ends at t0.
    return (
        Behavior(
            series="OpenLoopKinematicsVelocity",
            quantity="velocity",
            dims=dims,
            unit=unit,
            values=data,
            valid=valid,
            trial=trial,
        ),
        bin_s,
        t0,
    )
