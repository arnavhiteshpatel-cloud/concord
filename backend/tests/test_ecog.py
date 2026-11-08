"""Milestone 5 / workstream B: raw-voltage (ECoG) NWB importer, ECoG processing, modality guards.

Synthetic NWB fixtures here cover exact unit conversion, metadata handling and error paths that
the real recordings cannot exercise. The real AJILE12 data is tested in test_ecog_real.py.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import numpy as np
import pytest

pytest.importorskip("pynwb")
pytest.importorskip("scipy")

from concord.adapters.nwb import (
    NWBElectricalSource,
    NWBFormatError,
    UnsupportedModalityError,
    load_electrical,
)
from concord.adapters.nwb.ecog import _units
from concord.contracts import parse_envelope
from concord.contracts.capabilities import Capability
from concord.contracts.events import ProvenanceKind, QualityFlag
from concord.contracts.protocol import DeviceDescriptor, DeviceKind, ErrorCode, Modality
from concord.datasets import manifest
from concord.decoding.lda import LDAClassifier
from concord.decoding.model import check, model_modality
from concord.decoding.ridge import RidgeDecoder
from concord.processing import ProcessingSpec, SignalChain, StageConfigError
from concord.processing.stages import common_average_reference
from concord.runtime.catalog import NWBCatalog
from concord.runtime.pipeline import PipelineError, _source_specific

from . import nwb_fixtures as fx

# ------------------------------------------------------------------ importer


def test_microvolts_from_declared_conversion(tmp_path: Path) -> None:
    """recording.frame values are µV exactly as NWB defines them: data x conversion (V)."""
    data = np.arange(2000, dtype=np.float32).reshape(500, 4)
    p = fx.electrical(tmp_path / "a.nwb", data=data, conversion=2e-6)
    rec = load_electrical(p)
    assert rec.unit == "uV" and rec.declared_unit == "volts"
    assert np.array_equal(rec.samples(0, 500), data.astype(np.float64) * 2.0)
    assert any("µV" in n for n in rec.notes)


def test_channel_conversion_is_applied_per_channel(tmp_path: Path) -> None:
    data = np.ones((500, 3), dtype=np.float32)
    p = fx.electrical(
        tmp_path / "a.nwb", data=data, conversion=1e-6, channel_conversion=[1.0, 2.0, 0.5]
    )
    rec = load_electrical(p)
    assert np.allclose(rec.samples(0, 2), [[1.0, 2.0, 0.5]] * 2)


@pytest.mark.parametrize(
    ("unit", "conversion", "why"),
    [
        ("degrees", 1.0, "not a voltage unit"),
        ("volts", float("nan"), "not a usable factor"),
        ("volts", 0.0, "not a usable factor"),
    ],
)
def test_undeclared_or_unusable_unit_is_arbitrary(unit: str, conversion: float, why: str) -> None:
    """Never silently rescaled: without a usable declaration the frames are 'arbitrary'."""
    es = SimpleNamespace(unit=unit, conversion=conversion, offset=0.0, channel_conversion=None)
    notes: list[str] = []
    out, scale, offset, _, _ = _units(es, 2, notes)
    assert out == "arbitrary" and np.all(scale == 1.0) and offset == 0.0
    assert why in notes[-1]


def test_millivolts_and_offset() -> None:
    es = SimpleNamespace(unit="mV", conversion=1.0, offset=0.5, channel_conversion=None)
    out, scale, offset, _, _ = _units(es, 1, [])
    assert out == "uV" and scale[0] == pytest.approx(1000.0) and offset == pytest.approx(500.0)


def test_electrode_metadata_and_bad_channels(tmp_path: Path) -> None:
    p = fx.electrical(tmp_path / "a.nwb", good=[True, False, True, True])
    rec = load_electrical(p)
    assert rec.channel_labels == ["GRID/0", "GRID/1", "GRID/2", "GRID/3"]
    assert rec.bad_channels == ["GRID/1"]
    e = rec.electrodes[1]
    assert e.group == "GRID" and e.group_description == "ECoG grid" and e.location == "unknown"
    notes = " ".join(rec.notes)
    assert "'good' column: 1 of 4 marked bad" in notes and "no channel names" in notes
    assert "'unknown' for every electrode" in notes


def test_label_and_bad_columns_are_used_when_present(tmp_path: Path) -> None:
    p = fx.electrical(
        tmp_path / "a.nwb", bad=[False, False, True, False], labels=["A1", "A2", "A3", "A4"]
    )
    rec = load_electrical(p)
    assert rec.channel_labels == ["A1", "A2", "A3", "A4"] and rec.bad_channels == ["A3"]


def test_no_quality_column_means_unknown_not_good(tmp_path: Path) -> None:
    rec = load_electrical(fx.electrical(tmp_path / "a.nwb"))
    assert all(e.bad is None for e in rec.electrodes) and rec.bad_channels == []
    assert any("channel quality is not stated" in n for n in rec.notes)


def test_units_file_is_not_an_electrical_recording(tmp_path: Path) -> None:
    p = fx.units_only(tmp_path / "u.nwb")
    with pytest.raises(UnsupportedModalityError, match="no ElectricalSeries"):
        load_electrical(p)
    with pytest.raises(NWBFormatError, match="no such file"):
        load_electrical(tmp_path / "missing.nwb")


def test_source_is_offline_replay_never_live_and_modality_not_guessed(tmp_path: Path) -> None:
    p = fx.electrical(tmp_path / "a.nwb", good=[True] * 4)
    src = NWBElectricalSource(p)
    d = src.descriptor()
    assert d.kind is DeviceKind.REPLAY and d.synthetic is False
    assert "Offline Replay" in d.display_name and "not a live implant" in d.description
    assert d.modality is None and d.invasive is None  # unverified file: not declared anywhere
    assert src.origin == "file:a.nwb" and not src.verification.verified
    caps = {c.capability: c for c in d.capabilities}
    assert set(caps) == {Capability.RECORDING, Capability.BEHAVIOR, Capability.DEVICE_STATUS}
    rec = caps[Capability.RECORDING].params
    assert rec["sample_rate_hz"] == 500.0 and rec["unit"] == "uV" and rec["frame_samples"] == 50
    assert rec["channel_labels"] == ["GRID/0", "GRID/1", "GRID/2", "GRID/3"]
    assert "line_hz" not in rec  # unverified: the mains frequency is not known


def test_records_frames_behavior_annotations(tmp_path: Path) -> None:
    data = np.random.default_rng(0).normal(size=(1000, 4)).astype(np.float32)
    p = fx.electrical(
        tmp_path / "a.nwb",
        data=data,
        starting_time=10.0,
        epochs=[(9.0, 10.5, ""), (10.6, 10.65, "Blocklist (Data break)"), (11.0, 11.5, "Eat")],
        reaches=[(10.2, 11.0), (13.0, 13.5)],  # the second starts after the recording ends
    )
    src = NWBElectricalSource(p)
    recs = list(src.records())
    assert [r.t_ns for r in recs] == sorted(r.t_ns for r in recs)
    frames = [r.envelope for r in recs if r.envelope["event_type"] == "recording.frame"]
    beh = [r.envelope for r in recs if r.envelope["event_type"] == "behavior.sample"]
    ann = [r.envelope for r in recs if r.envelope["event_type"] == "recording.annotation"]
    assert len(frames) == 20  # 1000 samples / 50
    got = np.concatenate([np.array(f["payload"]["samples"]).T for f in frames])
    assert np.array_equal(got, data.astype(np.float64))  # x 1e-6 V -> µV: unchanged
    assert frames[0]["device_timestamp_ns"] == 10_000_000_000
    assert frames[1]["payload"]["first_sample_index"] == 50
    assert {f["provenance"].kind for f in frames} == {ProvenanceKind.RAW_SIGNAL}
    # a frame overlapping the dataset's "data break" epoch is flagged, others are not
    flagged = [f for f in frames if QualityFlag.DROPPED_SAMPLES in f["quality"].flags]
    assert [f["payload"]["first_sample_index"] for f in flagged] == [300]
    assert len(beh) == 60 and beh[5]["payload"]["valid"] is False  # the NaN frame
    assert beh[0]["payload"]["dims"] == ["L_Wrist.x", "L_Wrist.y", "R_Wrist.x", "R_Wrist.y"]
    assert beh[0]["payload"]["unit"] == "arbitrary"  # conversion NaN in the file
    labels = [(a["payload"]["label"], a["payload"]["value"]) for a in ann]
    # the unlabelled epoch and rows starting outside the recording are not emitted
    assert labels == [("reaches", None), ("epoch", "Blocklist (Data break)"), ("epoch", "Eat")]
    assert ann[0]["payload"]["duration_ms"] == pytest.approx(800.0)
    assert not [r for r in recs if r.envelope["event_type"].startswith("intent.")]


async def test_replay_adapter_marks_replayed_and_validates(tmp_path: Path) -> None:
    from concord.adapters.simulated import OperatorIntentSource
    from concord.runtime import DeviceRegistry, Recorder, Runtime

    from .conftest import subscribe
    from .helpers import drain, events, wait_for

    ds = tmp_path / "data" / "datasets"
    ds.mkdir(parents=True)
    fx.electrical(ds / "ecog.nwb", good=[True, True, False, True])
    reg = DeviceRegistry(OperatorIntentSource(), tmp_path / "data" / "recordings")
    rt = Runtime(reg, Recorder(tmp_path / "data" / "recordings"))
    try:
        sub = subscribe(rt)
        await rt.connect("nwb:ecog")
        await rt.set_playback_speed(8.0)
        await wait_for(lambda: rt.diagnostics.totals["recording.frame"] >= 10, timeout=10)
        evs = [parse_envelope(e) for e in events(drain(sub))]
        frames = [e for e in evs if e.event_type == "recording.frame"]
        assert frames and all(e.provenance.replayed and not e.provenance.synthetic for e in frames)
        assert all(QualityFlag.REPLAYED in e.quality.flags for e in frames)
        assert rt.diagnostics.validation_errors == 0 and rt.diagnostics.decode_errors == 0
    finally:
        await rt.shutdown()


def test_catalog_offers_electrical_and_units_files(tmp_path: Path) -> None:
    ds = tmp_path / "datasets"
    ds.mkdir()
    fx.electrical(ds / "ecog.nwb")
    fx.units_with_behavior(ds / "units.nwb")
    cat = NWBCatalog(ds, tmp_path / "models")
    devs = {d.device_id: d for d in cat.list()}
    assert sorted(devs) == ["nwb:ecog", "nwb:units"] and not cat.problems
    assert devs["nwb:ecog"].adapter.startswith("concord.nwb.ecog@")
    meta = cat.source(ds / "ecog.nwb").metadata()
    assert meta.source_type == "nwb_electrical_series" and meta.live is False
    assert meta.signal is not None and meta.signal.unit == "uV" and meta.signal.n_samples == 1000
    assert meta.electrodes is not None and len(meta.electrodes) == 4 and meta.channels == []


def test_altered_timeline_or_shape_of_a_pinned_extract_is_refused(tmp_path: Path) -> None:
    """An extract whose data digest matches a pinned slice must also keep its pinned shape and
    start time (no silent re-timing)."""
    from concord.datasets import Verification

    m = manifest("ajile12")
    s = m.slices[0]
    fake = Verification("0" * 64, m, m.by_path(s.asset_path), s)
    p = fx.electrical(tmp_path / "a.nwb")
    with pytest.raises(NWBFormatError, match="does not match pinned slice"):
        NWBElectricalSource(p, verification=fake)


# ------------------------------------------------------------------ processing


def _chunks(x: np.ndarray, seed: int = 0) -> list[np.ndarray]:
    rng = np.random.default_rng(seed)
    out, i = [], 0
    while i < len(x):
        n = int(rng.integers(1, 700))
        out.append(x[i : i + n])
        i += n
    return out


def test_car_excluding_bad_channels() -> None:
    """A broken electrode must not leak into every other channel through the reference."""
    rng = np.random.default_rng(0)
    x = rng.normal(size=(400, 6))
    x[:, 2] += 1e4 * np.sin(np.linspace(0, 40, 400))  # huge artifact on channel 2
    ref = np.ones(6, dtype=bool)
    ref[2] = False
    y = common_average_reference(x, ref)
    others = [0, 1, 3, 4, 5]
    assert np.abs(y[:, others]).max() < 10  # artifact absent from good channels
    assert np.allclose(y[:, others].mean(axis=1), 0)
    with pytest.raises(StageConfigError):
        common_average_reference(x, np.zeros(6, dtype=bool))


def test_ecog_chain_with_car_exclusion_is_chunk_invariant_and_causal() -> None:
    fs = 500.0
    rng = np.random.default_rng(1)
    x = rng.normal(scale=30.0, size=(int(fs * 8), 8))
    spec = ProcessingSpec(preset="ecog_high_gamma", bin_ms=100, line_hz=60)
    kw: dict[str, Any] = {"car_exclude": [3], "channel_labels": [f"c{i}" for i in range(8)]}
    whole = SignalChain(spec, fs, 8, "uV", **kw)
    a = whole.push(x)
    c = SignalChain(spec, fs, 8, "uV", **kw)
    b = [f for part in _chunks(x) for f in c.push(part)]
    assert len(a) == len(b) == 80
    for fa, fb in zip(a, b, strict=True):
        assert fa.end_sample == fb.end_sample and np.allclose(fa.values, fb.values, rtol=1e-9)
    assert "excluded as bad: c3" in " ".join(whole.stages)
    assert [s for s in whole.stages if s.startswith("notch")] == [
        "notch 60 Hz (Q=30)",
        "notch 120 Hz (Q=30)",
        "notch 180 Hz (Q=30)",
    ]
    # causality: changing the future does not change past bins
    y = x.copy()
    y[4000 - 250 :] += rng.normal(scale=500.0, size=y[4000 - 250 :].shape)
    later = SignalChain(spec, fs, 8, "uV", **kw).push(y)
    for fa, fy in zip(a, later, strict=True):
        if fa.end_sample <= 4000 - 250:
            assert np.array_equal(fa.values, fy.values)


def test_invalid_car_exclusion_is_refused() -> None:
    spec = ProcessingSpec(preset="ecog_high_gamma")
    with pytest.raises(StageConfigError, match="outside"):
        SignalChain(spec, 500.0, 4, "uV", car_exclude=[7])
    with pytest.raises(StageConfigError, match="every channel"):
        SignalChain(spec, 500.0, 2, "uV", car_exclude=[0, 1])


def _params(**kw: Any) -> dict[str, Any]:
    return {"channel_labels": ["a", "b", "c"], **kw}


def test_pipeline_uses_the_sources_mains_frequency_and_bad_channels() -> None:
    spec, excl = _source_specific(
        ProcessingSpec(preset="ecog_high_gamma"), _params(line_hz=50.0, bad_channels=["b"]), 3
    )
    assert spec.line_hz == 50 and excl == [1]
    # an explicit, contradicting notch is refused; an explicit "no notch" is allowed
    with pytest.raises(PipelineError) as e:
        _source_specific(
            ProcessingSpec(preset="ecog_high_gamma", line_hz=60), _params(line_hz=50.0), 3
        )
    assert e.value.code is ErrorCode.CAPABILITY_UNSUPPORTED and "declares 50 Hz" in e.value.message
    spec, _ = _source_specific(
        ProcessingSpec(preset="ecog_high_gamma", line_hz=None), _params(line_hz=50.0), 3
    )
    assert spec.line_hz is None
    with pytest.raises(PipelineError, match="not source channels"):
        _source_specific(ProcessingSpec(preset="ecog_high_gamma"), _params(bad_channels=["z"]), 3)
    # without a declaration the operator's / default setting stands
    spec, excl = _source_specific(ProcessingSpec(preset="ecog_high_gamma"), _params(), 3)
    assert spec.line_hz == 60 and excl == []


# ------------------------------------------------------------------ modality guards


def _lda(
    modality: str | None,
    labels: list[str] | None = None,
    identity: str = "dandi:000055:07",
    **inp: Any,
) -> LDAClassifier:
    labels = labels or ["a", "b"]
    return LDAClassifier(
        model_id="m-lda-1",
        space="move_vs_rest",
        classes=["rest", "move"],
        class_values=[0.0, 1.0],
        bin_ms=100.0,
        tau_ms=0.0,
        kernel=[1.0],
        x_mean=[0.0] * len(labels),
        x_std=[1.0] * len(labels),
        coef=[[0.0] * len(labels), [1.0] * len(labels)],
        intercept=[0.0, 0.0],
        priors=[0.5, 0.5],
        shrinkage=0.1,
        training={"session": "5"},
        input={
            "event_type": "features.vector",
            "feature": "log_band_power",
            "bin_ms": 100.0,
            "channel_count": len(labels),
            "channel_labels": labels,
            **({"modality": modality} if modality else {}),
            **inp,
        },
        source={"identity": identity},
    )


def _check(model: Any, modality: str | None, **kw: Any) -> Any:
    args: dict[str, Any] = {
        "event_type": "features.vector",
        "feature": "log_band_power",
        "bin_ms": 100.0,
        "channel_count": 2,
        "channel_labels": ["a", "b"],
        "stream_identity": "dandi:000055:07",
        "stream_session": "6",
    }
    args.update(kw)
    return check(model, stream_modality=modality, **args)


@pytest.mark.parametrize(
    ("trained", "stream"),
    [("ecog", "intracortical"), ("intracortical", "ecog"), ("eeg", "ecog"), ("ecog", "eeg")],
)
def test_model_is_refused_on_another_modality_even_with_override(trained: str, stream: str) -> None:
    c = _check(_lda(trained), stream, allow_cross_source=True)
    assert not c.ok
    assert any(f"trained on {trained} recordings; this source is {stream}" in e for e in c.errors)


def test_same_modality_passes_and_unknown_is_a_warning() -> None:
    assert _check(_lda("ecog"), "ecog").ok
    c = _check(_lda("ecog"), None)
    assert c.ok and any("does not declare its modality" in w for w in c.warnings)
    # a model from a DANDI dataset inherits the manifest's modality (AJILE12: ecog) ...
    assert model_modality(_lda(None)) == "ecog"
    # ... one from an undeclared source has none: a warning, not a guess
    c = _check(_lda(None, identity="lsl:ECoG@lab"), "ecog", stream_identity="lsl:ECoG@lab")
    assert c.ok and any("does not declare the recording modality" in w for w in c.warnings)


def test_falcon_models_inherit_intracortical_from_the_pinned_manifest() -> None:
    """Older models without input.modality: the training dataset's manifest declares it."""
    ridge = RidgeDecoder(
        model_id="falcon-h1-ridge-x",
        space="falcon_h1_7dof",
        quantity="velocity",
        dims=["tx"],
        unit="arbitrary",
        bin_ms=20.0,
        tau_ms=240.0,
        kernel=[1.0],
        x_mean=[0.0, 0.0],
        x_std=[1.0, 1.0],
        weights=[[0.0], [0.0]],
        intercept=[0.0],
        alpha=1.0,
        training={"dataset": "DANDI:000954"},
    )
    assert model_modality(ridge) == "intracortical"
    c = check(
        ridge,
        event_type="features.vector",
        feature="log_band_power",
        bin_ms=100.0,
        channel_count=2,
        channel_labels=None,
        stream_identity="dandi:000055:07",
        stream_modality="ecog",
        allow_cross_source=True,
    )
    assert any("trained on intracortical recordings; this source is ecog" in e for e in c.errors)


def test_using_a_channel_the_source_marks_bad_is_a_warning() -> None:
    m = _lda("ecog", excluded_channels=["a"])
    assert not _check(m, "ecog", stream_bad_channels=["a"]).warnings
    c = _check(_lda("ecog"), "ecog", stream_bad_channels=["b"])
    assert c.ok and any("marks bad: b" in w for w in c.warnings)


def test_manifests_declare_modality() -> None:
    assert manifest("falcon-h1").modality == "intracortical"
    m = manifest("ajile12")
    assert m.modality == "ecog" and m.line_hz == 60
    assert {s.role for s in m.slices} == {"train", "test"}
    # held-out slices never share a session with training slices
    train = {s.session for s in m.slices if s.role == "train"}
    test = {s.session for s in m.slices if s.role == "test"}
    assert train and test and not train & test


def test_descriptor_modality_values_are_contract_values() -> None:
    d = DeviceDescriptor(
        device_id="x",
        display_name="x",
        kind=DeviceKind.REPLAY,
        adapter="a@0.0.1",
        native_format="n",
        capabilities=[],
        synthetic=False,
        modality=Modality(manifest("ajile12").modality or ""),
        invasive=True,
    )
    assert d.modality is Modality.ECOG
