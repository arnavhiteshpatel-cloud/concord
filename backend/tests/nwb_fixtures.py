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
    f: NWBFile, n_units: int, duration_s: float, rate_hz: float = 20.0, seed: int = 0
) -> None:
    rng = np.random.default_rng(seed)
    for _ in range(n_units):
        n = rng.poisson(rate_hz * duration_s)
        f.add_unit(spike_times=np.sort(rng.uniform(0, duration_s, n)))


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
) -> Path:
    """Units + a FALCON-like velocity series. ``rate_field`` is what the file *claims*."""
    f = _file()
    duration = n * 0.02
    _units(f, n_units, duration)
    vel = np.random.default_rng(1).normal(size=(n, 2)) * 0.01
    f.add_acquisition(
        TimeSeries(
            name="OpenLoopKinematicsVelocity",
            data=vel,
            unit="arbitrary",
            rate=rate_field,
            description="vx,vy",
        )
    )
    f.add_acquisition(
        TimeSeries(
            name="eval_mask", data=np.ones(mask_len or n, dtype=bool), unit="bool", rate=rate_field
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


def raw_voltage_only(path: Path) -> Path:
    """Valid NWB with an ElectricalSeries but no units: an unsupported modality."""
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
