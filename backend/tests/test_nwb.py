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
    fx.calcium_like_unsupported(ds / "other.nwb")
    # M5: a raw-voltage ElectricalSeries file is now offered (NWBElectricalSource) instead of
    # being rejected; files with neither units nor an ElectricalSeries are still problems.
    fx.raw_voltage_only(ds / "raw.nwb")
    cat = NWBCatalog(ds, tmp_path / "models")
    devices = {d.device_id: d for d in cat.list()}
    assert sorted(devices) == ["nwb:good", "nwb:raw"]
    assert devices["nwb:raw"].modality is None  # unverified file: modality never guessed
    assert sorted(p.file for p in cat.problems) == ["broken.nwb", "other.nwb"]


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


# ------------------------------------------------- regression tests from review 2


def test_nonzero_starting_time_is_accepted(tmp_path: Path) -> None:
    """Review 2 #6: the timebase check must be relative to starting_time."""
    rec = load(fx.units_with_behavior(tmp_path / "late.nwb", starting_time=100.0))
    assert rec.t0_s == pytest.approx(100.0) and rec.bin_s == pytest.approx(0.02)
    total = sum(int(c.sum()) for _, c in rec.iter_counts())
    assert total > 0.95 * sum(ch.spike_count for ch in rec.channels)


def test_nwb_offset_and_conversion_scale_values_not_time(tmp_path: Path) -> None:
    """Review 2 #6: NWB `offset` is a value offset (data*conversion + offset), not a time shift."""
    plain = load(fx.units_with_behavior(tmp_path / "a.nwb"))
    scaled = load(fx.units_with_behavior(tmp_path / "b.nwb", conversion=2.0, offset=0.5))
    assert plain.behavior is not None and scaled.behavior is not None
    assert np.allclose(scaled.behavior.values, plain.behavior.values * 2.0 + 0.5)
    assert scaled.t0_s == plain.t0_s
    assert any("conversion" in n for n in scaled.notes)


def test_older_blacklist_mask_is_honored(tmp_path: Path) -> None:
    """Review 2 #6: older FALCON files mark excluded samples with Blacklist."""
    black = np.zeros(500, dtype=bool)
    black[:100] = True
    rec = load(fx.units_with_behavior(tmp_path / "bl.nwb", blacklist=black))
    assert rec.behavior is not None
    assert not rec.behavior.valid[:100].any() and rec.behavior.valid[100:].all()
    assert any("Blacklist" in n for n in rec.notes)


def test_duplicate_device_ids_are_reported_not_merged(tmp_path: Path) -> None:
    """Review 2 #3: same filename in two folders must not produce two devices with one id."""
    ds = tmp_path / "datasets"
    (ds / "a").mkdir(parents=True)
    (ds / "b").mkdir()
    fx.units_with_behavior(ds / "a" / "x.nwb")
    fx.units_with_behavior(ds / "b" / "x.nwb", n=400)
    cat = NWBCatalog(ds, tmp_path / "models")
    assert [d.device_id for d in cat.list()] == ["nwb:x"]
    assert len(cat.problems) == 1 and "already used" in cat.problems[0].error
    assert cat.path_for("nwb:x") == ds / "a" / "x.nwb"


async def test_set_speed_during_loop_gap_does_not_burst() -> None:
    """Review 2 #1: changing speed between passes must not replay the next pass instantly."""

    class Short(_BigSource):
        def duration_ns(self) -> int | None:
            return 200 * 1_000_000

        def records(self) -> Iterator[ReplayRecord]:
            for i in range(200):  # 0.2 s of recording
                yield ReplayRecord(t_ns=i * 1_000_000, envelope={"event_type": "device.status"})

    adapter = ReplayAdapter(Short(), speed=4.0, loop=True)
    await adapter.open()
    for _ in range(200):  # finish pass 1 (~50 ms)
        await adapter.read()
    # the read of pass 2's first record sleeps through the loop gap; change speed meanwhile,
    # exactly as a REST call would while the pump is waiting
    first = asyncio.create_task(adapter.read())
    await asyncio.sleep(0.1)
    adapter.set_speed(1.0)
    await first
    t0 = asyncio.get_running_loop().time()
    for _ in range(100):
        await adapter.read()
    elapsed = asyncio.get_running_loop().time() - t0
    assert elapsed > 0.08  # ~0.1 s of recording at 1x, not a burst
    assert adapter.loops == 1


def test_evaluation_reports_shift_null_distribution() -> None:
    """Review 2 #8: the time-shift control is a 20-shift null, not a single shift."""
    from brainos.decoding.ridge import evaluate

    rng = np.random.default_rng(1)
    counts = rng.poisson(3.0, size=(2000, 8)).astype(float)
    filt = causal_filter(counts, exponential_kernel(20.0))
    y = (filt - filt.mean(0)) / filt.std(0) @ rng.normal(size=(8, 2))
    model = fit(
        counts[:1500],
        y[:1500],
        np.ones(1500, bool),
        dims=["a", "b"],
        unit="u",
        bin_ms=20.0,
        space="s",
        training={"behavior_mean": [0.0, 0.0]},
    )
    res = evaluate(model, counts[1500:], y[1500:], np.ones(500, bool), skip_first=12)
    assert res["control_time_shift_n"] == 20
    assert res["r2"] > res["control_time_shift_max_r2"] and res["beats_all_shifts"] is True
