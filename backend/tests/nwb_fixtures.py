"""Small synthetic NWB files for *error-path* tests only.

Real-data behavior is tested against the genuine DANDI 000954 files (test_nwb_real.py);
these fixtures exist because real files cannot exercise malformed/unsupported inputs.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import numpy as np
from pynwb import NWBHDF5IO, NWBFile, TimeSeries
from pynwb.ecephys import ElectricalSeries
from pynwb.file import Subject


def _file(species: str = "Homo sapiens") -> NWBFile:
    f = NWBFile(
        session_description="synthetic test fixture (not real data)",
        identifier="fixture",
        session_start_time=datetime(2020, 1, 1, tzinfo=UTC),
    )
    f.subject = Subject(subject_id="fixture", species=species)
    return f


def _units(
    f: NWBFile,
    n_units: int,
    duration_s: float,
    rate_hz: float = 20.0,
    seed: int = 0,
    t_start: float = 0.0,
) -> None:
    rng = np.random.default_rng(seed)
    for _ in range(n_units):
        n = rng.poisson(rate_hz * duration_s)
        f.add_unit(spike_times=np.sort(rng.uniform(t_start, t_start + duration_s, n)))


def write(path: Path, f: NWBFile) -> Path:
    with NWBHDF5IO(str(path), "w") as io:
        io.write(f)
    return path


def units_with_behavior(
    path: Path,
    *,
    rate_field: float = 50.0,
    n: int = 500,
    n_units: int = 4,
    mask_len: int | None = None,
    starting_time: float = 0.0,
    conversion: float = 1.0,
    offset: float = 0.0,
    blacklist: np.ndarray | None = None,
) -> Path:
    """Units + a FALCON-like velocity series. ``rate_field`` is what the file *claims*."""
    f = _file()
    duration = n * 0.02
    _units(f, n_units, duration, t_start=starting_time)
    vel = np.random.default_rng(1).normal(size=(n, 2)) * 0.01
    f.add_acquisition(
        TimeSeries(
            name="OpenLoopKinematicsVelocity",
            data=vel,
            unit="arbitrary",
            rate=rate_field,
            starting_time=starting_time,
            conversion=conversion,
            offset=offset,
            description="vx,vy",
        )
    )
    if blacklist is not None:
        f.add_acquisition(
            TimeSeries(name="Blacklist", data=blacklist, unit="bool", rate=rate_field)
        )
    else:
        f.add_acquisition(
            TimeSeries(
                name="eval_mask",
                data=np.ones(mask_len or n, dtype=bool),
                unit="bool",
                rate=rate_field,
            )
        )
    return write(path, f)


def units_only(path: Path, *, n_units: int = 3, duration_s: float = 2.0) -> Path:
    f = _file()
    _units(f, n_units, duration_s)
    return write(path, f)


def empty_units(path: Path) -> Path:
    f = _file()
    f.add_unit(spike_times=np.array([], dtype=float))
    return write(path, f)


def calcium_like_unsupported(path: Path) -> Path:
    """Valid NWB with neither units nor an ElectricalSeries (a generic TimeSeries only)."""
    f = _file()
    f.add_acquisition(
        TimeSeries(name="fluorescence", data=np.zeros((10, 2)), unit="a.u.", rate=30.0)
    )
    return write(path, f)


def electrical(
    path: Path,
    *,
    data: np.ndarray | None = None,
    fs: float = 500.0,
    starting_time: float = 10.0,
    conversion: float = 1e-6,
    channel_conversion: list[float] | None = None,
    good: list[bool] | None = None,
    bad: list[bool] | None = None,
    labels: list[str] | None = None,
    pose: bool = True,
    epochs: list[tuple[float, float, str]] | None = None,
    reaches: list[tuple[float, float]] | None = None,
) -> Path:
    """An ECoG-like raw-voltage NWB file (synthetic; NOT a substitute for the real data tests)."""
    from pynwb.behavior import Position, SpatialSeries
    from pynwb.epoch import TimeIntervals

    if data is None:
        data = np.random.default_rng(3).normal(scale=20.0, size=(1000, 4)).astype(np.float32)
    n, ch = data.shape
    f = _file()
    dev = f.create_device(name="GRID")
    grp = f.create_electrode_group(
        name="GRID", description="ECoG grid", location="unknown", device=dev
    )
    if good is not None:
        f.add_electrode_column(name="good", description="good electrodes")
    if bad is not None:
        f.add_electrode_column(name="bad", description="bad electrodes")
    if labels is not None:
        f.add_electrode_column(name="label", description="channel name")
    for i in range(ch):
        extra: dict[str, object] = {}
        if good is not None:
            extra["good"] = good[i]
        if bad is not None:
            extra["bad"] = bad[i]
        if labels is not None:
            extra["label"] = labels[i]
        f.add_electrode(group=grp, location="unknown", x=float(i), y=0.0, z=1.0, **extra)
    region = f.create_electrode_table_region(list(range(ch)), "all electrodes")
    f.add_acquisition(
        ElectricalSeries(
            name="ElectricalSeries",
            data=data,
            electrodes=region,
            rate=fs,
            starting_time=starting_time,
            conversion=conversion,
            channel_conversion=channel_conversion,
        )
    )
    if pose:
        frames = int(n / fs * 30)
        xy = np.cumsum(np.random.default_rng(4).normal(size=(frames, 2)), axis=0)
        xy[5] = np.nan  # one untracked frame
        module = f.create_processing_module(name="behavior", description="pose data")
        module.add(
            Position(
                spatial_series=[
                    SpatialSeries(
                        name=k,
                        data=xy,
                        reference_frame="unknown",
                        conversion=np.nan,
                        rate=30.0,
                        starting_time=starting_time,
                    )
                    for k in ("L_Wrist", "R_Wrist")
                ]
            )
        )
    if epochs:
        f.add_epoch_column(name="labels", description="Coarse behavioral labels")
        for a, b, lab in epochs:
            f.add_epoch(start_time=a, stop_time=b, labels=lab)
    if reaches:
        ti = TimeIntervals(name="reaches", description="Features of each reach")
        for a, b in reaches:
            ti.add_row(start_time=a, stop_time=b)
        f.add_time_intervals(ti)
    return write(path, f)


def raw_voltage_only(path: Path) -> Path:
    """Valid NWB with an ElectricalSeries but no units (unsupported by the units reader)."""
    f = _file()
    dev = f.create_device(name="array")
    grp = f.create_electrode_group(name="g", description="d", location="unknown", device=dev)
    for _ in range(2):
        f.add_electrode(group=grp, location="unknown")
    region = f.create_electrode_table_region([0, 1], "all")
    f.add_acquisition(
        ElectricalSeries(name="raw", data=np.zeros((100, 2)), electrodes=region, rate=1000.0)
    )
    return write(path, f)
