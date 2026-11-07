"""NWB ingestion: error handling, timebase rules, catalog, decoder maths, replay yielding.

Uses small synthetic NWB fixtures only where real files cannot exercise the path.
Real-data tests live in test_nwb_real.py.
"""

from __future__ import annotations

import asyncio
import shutil
from collections.abc import Iterator
from pathlib import Path

import numpy as np
import pytest

pytest.importorskip("pynwb")

from brainos.adapters.nwb import (
    NWBFormatError,
    NWBUnitsSource,
    UnsupportedModalityError,
    load,
)
from brainos.adapters.replay import ReplayAdapter, ReplayRecord
from brainos.contracts.protocol import DeviceDescriptor, DeviceKind
from brainos.decoding.ridge import (
    causal_filter,
    exponential_kernel,
    fit,
    r2_variance_weighted,
)
from brainos.runtime.catalog import NWBCatalog

from . import nwb_fixtures as fx


def test_not_an_nwb_file(tmp_path: Path) -> None:
    """M2-AT-5: garbage with an .nwb name is rejected with a clear error."""
    p = tmp_path / "fake.nwb"
    p.write_text("this is not HDF5")
    with pytest.raises(NWBFormatError, match="not a readable NWB/HDF5 file"):
        load(p)


def test_missing_file(tmp_path: Path) -> None:
    with pytest.raises(NWBFormatError, match="no such file"):
        load(tmp_path / "nope.nwb")


def test_unsupported_modality_raw_voltage(tmp_path: Path) -> None:
    """M2-AT-5: valid NWB without units (raw ElectricalSeries) -> explicit unsupported error."""
    p = fx.raw_voltage_only(tmp_path / "raw.nwb")
    with pytest.raises(UnsupportedModalityError, match="ElectricalSeries"):
        load(p)


def test_empty_units(tmp_path: Path) -> None:
    p = fx.empty_units(tmp_path / "empty.nwb")
    with pytest.raises(NWBFormatError, match="no spikes"):
        load(p)


def test_rate_in_hz_is_accepted_without_correction(tmp_path: Path) -> None:
    rec = load(fx.units_with_behavior(tmp_path / "ok.nwb", rate_field=50.0))
    assert rec.bin_s == pytest.approx(0.02) and rec.n_bins == 500
    assert not any("Timebase correction" in n for n in rec.notes)


def test_rate_holding_period_is_corrected_and_recorded(tmp_path: Path) -> None:
    """M2-AT-3: the FALCON-style 'rate = period' inconsistency is corrected *and* noted."""
    rec = load(fx.units_with_behavior(tmp_path / "period.nwb", rate_field=0.02))
    assert rec.bin_s == pytest.approx(0.02)
    assert any("Timebase correction" in n for n in rec.notes)


def test_inconsistent_timebase_is_rejected(tmp_path: Path) -> None:
    """Neither Hz nor period matches the spike span -> refuse rather than guess."""
    with pytest.raises(NWBFormatError, match="cannot establish a timebase"):
        load(fx.units_with_behavior(tmp_path / "bad.nwb", rate_field=7.0))


def test_eval_mask_length_mismatch(tmp_path: Path) -> None:
    with pytest.raises(NWBFormatError, match="eval_mask length"):
        load(fx.units_with_behavior(tmp_path / "mask.nwb", mask_len=10))


def test_units_only_file_bins_without_behavior(tmp_path: Path) -> None:
    rec = load(fx.units_only(tmp_path / "u.nwb", duration_s=2.0))
    assert rec.behavior is None and rec.profile == "units-only"
    total = sum(c.sum() for _, c in rec.iter_counts())
    assert total == sum(ch.spike_count for ch in rec.channels)  # every spike counted once


def test_chunked_counts_equal_single_pass(tmp_path: Path) -> None:
    rec = load(fx.units_with_behavior(tmp_path / "c.nwb"))
    whole = rec.counts(0, rec.n_bins)
    chunked = np.concatenate([c for _, c in rec.iter_counts(chunk=37)])
    assert np.array_equal(whole, chunked)


def test_unverified_file_is_labelled_unverified(tmp_path: Path) -> None:
    src = NWBUnitsSource(fx.units_with_behavior(tmp_path / "x.nwb"))
    meta = src.metadata()
    assert meta.file.verified is False and meta.dataset is None
    assert src.origin == "file:x.nwb"
    desc = src.descriptor()
    assert desc.synthetic is False and desc.kind is DeviceKind.REPLAY
    assert "Offline Replay" in desc.display_name and "not a live implant" in desc.description


def test_catalog_reports_problem_files_and_offers_good_ones(tmp_path: Path) -> None:
    ds = tmp_path / "datasets"
    ds.mkdir()
    fx.units_with_behavior(ds / "good.nwb")
    (ds / "broken.nwb").write_bytes(b"\x89HDF\r\n garbage")
    fx.raw_voltage_only(ds / "raw.nwb")
    cat = NWBCatalog(ds, tmp_path / "models")
    ids = [d.device_id for d in cat.list()]
    assert ids == ["nwb:good"]
    assert sorted(p.file for p in cat.problems) == ["broken.nwb", "raw.nwb"]


# ----------------------------------------------------------------- decoder maths


def test_causal_filter_is_causal_and_normalized() -> None:
    k = exponential_kernel(20.0)
    assert len(k) == 12 and k.sum() == pytest.approx(1.0)
    x = np.zeros((30, 1))
    x[10] = 1.0
    y = causal_filter(x, k)
    assert np.all(y[:10] == 0) and y[10, 0] == pytest.approx(k[0])


def test_ridge_recovers_linear_map_and_streaming_matches_offline() -> None:
    rng = np.random.default_rng(0)
    counts = rng.poisson(3.0, size=(3000, 10)).astype(float)
    true_w = rng.normal(size=(10, 2))
    filtered = causal_filter(counts, exponential_kernel(20.0))
    y = (filtered - filtered.mean(0)) / filtered.std(0) @ true_w
    model = fit(
        counts,
        y,
        np.ones(3000, bool),
        dims=["a", "b"],
        unit="u",
        bin_ms=20.0,
        space="s",
        training={},
    )
    assert r2_variance_weighted(y, model.predict_counts(counts)) > 0.99
    stream = model.streaming()
    online = np.array([stream.step(row) for row in counts[:200]])
    assert np.allclose(online, model.predict_counts(counts[:200]))


def test_r2_matches_definition() -> None:
    y = np.array([[1.0, 2.0], [2.0, 4.0], [3.0, 9.0]])
    assert r2_variance_weighted(y, y) == pytest.approx(1.0)
    assert r2_variance_weighted(y, np.broadcast_to(y.mean(0), y.shape)) == pytest.approx(0.0)


# ------------------------------------------------------------ replay scheduling


class _BigSource:
    name = "big"
    origin = "test:big"

    def descriptor(self) -> DeviceDescriptor:
        return DeviceDescriptor(
            device_id="replay:big",
            display_name="big",
            kind=DeviceKind.REPLAY,
            adapter="t@0.0.1",
            native_format="-",
            capabilities=[],
            synthetic=True,
        )

    def duration_ns(self) -> int | None:
        return 10_000 * 1_000_000

    def records(self) -> Iterator[ReplayRecord]:
        for i in range(10_000):
            yield ReplayRecord(t_ns=i * 1_000_000, envelope={"event_type": "device.status"})


async def test_fast_replay_yields_to_event_loop() -> None:
    """Regression: replay behind schedule must not starve other tasks (WebSocket senders)."""
    adapter = ReplayAdapter(_BigSource(), speed=64.0, loop=False)
    await adapter.open()
    ticks = 0

    async def ticker() -> None:
        nonlocal ticks
        while True:
            ticks += 1
            await asyncio.sleep(0)

    t = asyncio.create_task(ticker())
    for _ in range(3000):
        await adapter.read()
    t.cancel()
    assert ticks > 20


async def test_set_speed_reanchors_without_jump() -> None:
    adapter = ReplayAdapter(_BigSource(), speed=1.0, loop=False)
    await adapter.open()
    for _ in range(5):
        await adapter.read()
    before = adapter.playback_status().position_s
    adapter.set_speed(8.0)
    t0 = asyncio.get_running_loop().time()
    for _ in range(80):
        await adapter.read()
    elapsed = asyncio.get_running_loop().time() - t0
    assert adapter.playback_status().speed == 8.0
    assert adapter.playback_status().position_s == pytest.approx(before + 0.08, abs=0.002)
    assert 0.005 < elapsed < 0.05  # 80 ms of recording at 8x ~= 10 ms
    with pytest.raises(ValueError):
        adapter.set_speed(0)


def test_source_files_are_not_mutated(tmp_path: Path) -> None:
    p = fx.units_with_behavior(tmp_path / "ro.nwb")
    before = p.read_bytes()
    list(NWBUnitsSource(p).records())
    assert p.read_bytes() == before
    shutil.rmtree(tmp_path)
