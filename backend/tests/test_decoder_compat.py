"""Milestone 5 (workstream A): compatibility before inference, families, model registry and
trust, drift monitor, calibration metrics. Pure (no runtime, no subprocesses)."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from brainos.decoding import model as models
from brainos.decoding.families import BuiltinFamily, family_for, register_family
from brainos.decoding.lda import fit_lda
from brainos.decoding.metrics import event_metrics, roc_auc, velocity_error
from brainos.decoding.monitor import DriftMonitor
from brainos.decoding.registry import ModelRegistry
from brainos.decoding.ridge import RidgeDecoder, fit

STREAM = {
    "event_type": "features.binned",
    "feature": "threshold_crossing_count",
    "bin_ms": 20.0,
    "channel_count": 4,
    "channel_labels": ["e1", "e2", "e3", "e4"],
    "unit": "count",
    "band_hz": None,
}


def manifest(**over: Any) -> dict[str, Any]:
    m: dict[str, Any] = {
        "schema": "brainos.decoder-manifest/1",
        "model_id": "m",
        "modalities": ["intracortical"],
        "inputs": [dict(STREAM)],
        "output": {"kind": "continuous", "dims": ["vx", "vy"]},
        "preprocessing": {"preset": None, "params": {}},
        "compatibility": {
            "participant_specific": True,
            "source_identity": "lsl:rig-a",
            "sessions": ["s1"],
        },
    }
    for k, v in over.items():
        m[k] = v
    return m


def check(
    m: dict[str, Any], streams: list[dict[str, Any]] | None = None, **kw: Any
) -> models.Compatibility:
    base: dict[str, Any] = {"stream_identity": "lsl:rig-a", "modality": "intracortical"}
    base.update(kw)
    return models.check_manifest(m, streams=streams or [dict(STREAM)], **base)


def test_matching_stream_is_compatible() -> None:
    c = check(manifest())
    assert c.ok and not c.cross_source and c.mapping == [None] and c.streams == [0]


@pytest.mark.parametrize(
    ("stream", "kw", "message"),
    [
        (
            {"feature": "spike_count"},
            {},
            "model expects features.binned/threshold_crossing_count, pipeline produces features.binned/spike_count",
        ),
        ({"bin_ms": 50.0}, {}, "model expects 20 ms bins, pipeline produces 50 ms"),
        ({"unit": "arbitrary"}, {}, "model expects features in count, pipeline produces arbitrary"),
        (
            {},
            {"modality": "eeg"},
            "model was trained on intracortical recordings; this source is eeg",
        ),
        (
            {},
            {"stream_identity": "lsl:rig-b"},
            "model was trained on source lsl:rig-a; this stream is lsl:rig-b",
        ),
        ({}, {"stream_session": "s1"}, "stream is from the model's training session s1"),
        (
            {},
            {"calibration_profile": "p2"},
            "model belongs to calibration profile p1; the selected profile is p2",
        ),
    ],
)
def test_mismatches_are_refused_with_actionable_reasons(
    stream: dict[str, Any], kw: dict[str, Any], message: str
) -> None:
    m = manifest()
    m["compatibility"]["calibration_profile"] = "p1"
    c = check(m, [{**STREAM, **stream}], **kw)
    assert not c.ok
    assert any(message in e for e in c.errors), c.errors


def test_channel_count_mismatch_names_both_sides() -> None:
    m = manifest(
        inputs=[
            {**STREAM, "channel_count": 256, "channel_labels": [f"array{i}" for i in range(256)]}
        ]
    )
    src = {**STREAM, "channel_count": 96, "channel_labels": [f"ch{i}" for i in range(96)]}
    c = check(m, [src])
    msg = " ".join(c.errors)
    assert "model expects 256 channels (256 channels labelled array0, array1, array2, …)" in msg
    assert "source has 96 (96 channels labelled ch0, ch1, ch2, …)" in msg
    assert "256 model labels are not in the source (e.g. array0)" in msg


def test_band_and_preset_parameters_are_checked() -> None:
    m = manifest(
        inputs=[
            {
                **STREAM,
                "event_type": "features.vector",
                "feature": "log_band_power",
                "unit": None,
                "band_hz": [8.0, 13.0],
            }
        ],
        preprocessing={
            "preset": "band_power",
            "params": {"band_low_hz": 8.0, "band_high_hz": 13.0},
        },
    )
    s = {**STREAM, "event_type": "features.vector", "feature": "log_band_power", "unit": None}
    c = check(
        m,
        [{**s, "band_hz": [70.0, 150.0]}],
        preset="band_power",
        preset_params={"band_low_hz": 70.0, "band_high_hz": 150.0},
    )
    assert any("trained on the 8-13 Hz band, pipeline computes 70-150 Hz" in e for e in c.errors)
    assert any(
        "band_power band_low_hz=8.0; the pipeline uses band_low_hz=70.0" in e for e in c.errors
    )
    c = check(m, [{**s, "band_hz": [8.0, 13.0]}], preset="ecog_high_gamma")
    assert any(
        "trained on features from the band_power preset; the pipeline runs ecog_high_gamma" in e
        for e in c.errors
    )
    assert check(
        m,
        [{**s, "band_hz": [8.0, 13.0]}],
        preset="band_power",
        preset_params={"band_low_hz": 8.0, "band_high_hz": 13.0},
    ).ok


def test_reordered_labels_need_the_explicit_mapping() -> None:
    src = {**STREAM, "channel_labels": ["e3", "e1", "e4", "e2"]}
    c = check(manifest(), [src])
    assert not c.ok and c.mapping_available
    assert "same set in a different order: enable explicit channel mapping by label" in c.errors[0]
    c = check(manifest(), [src], allow_channel_mapping=True)
    assert c.ok and c.mapping_applied and c.mapping == [[1, 3, 0, 2]]
    assert (
        "channels mapped by label as enabled by the operator: 4 model channels taken from 4 source channels (4 moved)"
        in c.mapping_notes[0]
    )


def test_mapping_selects_a_labelled_subset_but_never_guesses() -> None:
    src = {**STREAM, "channel_count": 6, "channel_labels": ["x", "e2", "e1", "y", "e4", "e3"]}
    c = check(manifest(), [src], allow_channel_mapping=True)
    assert c.ok and c.mapping == [[2, 1, 5, 4]] and "2 unused" in c.mapping_notes[0]
    # a missing label: no mapping possible
    c = check(
        manifest(),
        [{**src, "channel_labels": ["x", "e2", "e1", "y", "e4", "zz"]}],
        allow_channel_mapping=True,
    )
    assert not c.ok and not c.mapping_available and "e3" in c.errors[0]
    # duplicate labels: no mapping possible
    c = check(
        manifest(),
        [{**STREAM, "channel_labels": ["e1", "e1", "e3", "e4"]}],
        allow_channel_mapping=True,
    )
    assert not c.ok and not c.mapping_available
    # positional source (no labels): same count is assumed in order, with a warning
    c = check(manifest(), [{**STREAM, "channel_labels": None}])
    assert c.ok and any("cannot be verified" in w for w in c.warnings)


def test_cross_source_override_and_non_participant_models() -> None:
    c = check(manifest(), stream_identity="lsl:other", allow_cross_source=True)
    assert c.ok and c.cross_source and c.warnings[-1].startswith("CROSS-SOURCE OVERRIDE")
    m = manifest()
    m["compatibility"] = {"participant_specific": False, "source_identity": None, "sessions": []}
    c = check(m, stream_identity="lsl:other")
    assert c.ok and not c.cross_source and any("not participant-specific" in w for w in c.warnings)


def test_unknown_modality_is_a_warning_not_a_guess() -> None:
    c = check(manifest(), modality=None)
    assert c.ok and any("does not declare its modality" in w for w in c.warnings)
    c = check(manifest(modalities=[]))
    assert c.ok and any("does not declare the recording modality" in w for w in c.warnings)


def test_multi_input_models_find_each_stream() -> None:
    vec = {
        **STREAM,
        "event_type": "features.vector",
        "feature": "spike_band_power",
        "unit": "arbitrary^2",
    }
    m = manifest(inputs=[dict(STREAM), dict(vec)])
    c = check(m, [vec, dict(STREAM)])
    assert c.ok and c.streams == [1, 0]
    c = check(m, [dict(STREAM)])
    assert not c.ok and "model expects features.vector/spike_band_power (input 2)" in c.errors[0]


# ----------------------------------------------------------------------------- families


def _ridge(n: int = 400, ch: int = 7, seed: int = 0) -> tuple[RidgeDecoder, np.ndarray]:
    rng = np.random.default_rng(seed)
    x = rng.poisson(3.0, (n, ch)).astype(np.float64)
    y = x @ rng.standard_normal((ch, 2)) + rng.standard_normal((n, 2))
    m = fit(
        x, y, np.ones(n, bool), dims=["vx", "vy"], unit="u", bin_ms=20.0, space="s", training={}
    )
    return m, x


@pytest.mark.parametrize("ch", [1, 5, 13, 96])
def test_streaming_equals_offline_bit_for_bit(ch: int) -> None:
    m, x = _ridge(ch=ch, seed=ch)
    s = m.streaming()
    assert np.array_equal(np.array([s.step(r) for r in x]), m.predict_counts(x))
    labels = np.random.default_rng(ch).integers(0, 3, len(x)).astype(float)
    lda = fit_lda(
        np.log1p(x),
        labels,
        np.ones(len(x), bool),
        class_values=[0.0, 1.0, 2.0],
        class_names=["a", "b", "c"],
        bin_ms=20.0,
        space="s",
        training={},
        input_spec={},
    )
    st = lda.streaming()
    assert np.array_equal(
        np.array([st.step(r) for r in np.log1p(x)]), lda.predict_proba(np.log1p(x))
    )


def test_legacy_files_load_through_the_family_registry(tmp_path: Path) -> None:
    m, _ = _ridge()
    data = json.loads(json.dumps(m.__dict__))
    legacy = {k: v for k, v in data.items() if k not in ("kind", "inputs", "manifest")}
    assert family_for(legacy).name == "ridge"
    p = tmp_path / "legacy.json"
    p.write_text(json.dumps(legacy))
    loaded = models.load_model(p)
    assert isinstance(loaded, RidgeDecoder) and loaded.predict_counts(np.ones((3, 7))).shape == (
        3,
        2,
    )
    assert family_for({"outputs": {"type": "classes"}}).name == "lda"
    with pytest.raises(ValueError, match="unknown model kind 'gru'"):
        family_for({"kind": "gru"})
    bad = {**legacy, "weights": legacy["weights"][:-1]}
    p.write_text(json.dumps(bad))
    with pytest.raises(ValueError, match="does not match channels/dims"):
        models.load_model(p)


def test_register_family_refuses_conflicts() -> None:
    fam = family_for({"kind": "ridge"})
    register_family(fam)  # same object: no-op
    with pytest.raises(ValueError, match="already registered"):
        register_family(
            BuiltinFamily("ridge", frozenset({"x-ridge"}), "continuous", RidgeDecoder.from_dict)
        )
    with pytest.raises(ValueError, match="claims kinds"):
        register_family(
            BuiltinFamily("other", frozenset({"lda"}), "classes", RidgeDecoder.from_dict)
        )


def test_derived_manifest_states_only_what_the_file_records() -> None:
    m, _ = _ridge()
    m.training["behavior_std"] = [2.0, 3.0]
    man = models.manifest_for(m)
    assert man["family"] == "ridge" and man["modalities"] == []  # unknown stays unknown
    assert man["output"]["scale"] == [2.0, 3.0] and man["derived"] is True
    assert man["inputs"][0]["unit"] == "count" and man["inputs"][0]["channel_count"] == 7
    m.manifest = {**man, "derived": False, "schema": "brainos.decoder-manifest/1", "name": "stored"}
    assert models.manifest_for(m)["name"] == "stored"


# ----------------------------------------------------------------------------- registry


def _write_manifest(d: Path, model_id: str, fmt: str, content: bytes = b"x") -> Path:
    from brainos_decoder_sdk import (
        API_VERSION,
        InputSpec,
        Modality,
        ModelManifest,
        OutputKind,
        OutputSpec,
    )
    from brainos_decoder_sdk.formats import write_bundle

    src = d / f"src-{model_id}"
    src.write_bytes(content)
    man = ModelManifest(
        model_id=model_id,
        name=model_id,
        version="1.0.0",
        api_version=API_VERSION,
        family="sklearn",
        description="d",
        author="a",
        license="l",
        modalities=frozenset({Modality.INTRACORTICAL}),
        inputs=(InputSpec("features.binned", "threshold_crossing_count", 20.0, 4, None, "count"),),
        output=OutputSpec(OutputKind.CONTINUOUS, "velocity", ("vx", "vy"), "u", "s"),
    )
    return write_bundle(d, man, src, fmt)


def test_registry_lists_json_models_and_manifests_and_records_trust(tmp_path: Path) -> None:
    m, _ = _ridge()
    m.save(tmp_path / f"{m.model_id}.json")
    _write_manifest(tmp_path, "imported-onnx", "onnx")
    _write_manifest(tmp_path, "imported-pickle", "pickle")
    broken = tmp_path / "broken.manifest.json"
    broken.write_text(
        json.dumps(
            {
                **json.loads((tmp_path / "imported-onnx.manifest.json").read_text()),
                "model_id": "broken",
                "modalities": [],
            }
        )
    )
    reg = ModelRegistry(tmp_path)
    by = {r.model_id: r for r in reg.records()}
    assert by[m.model_id].origin == "brainos-trained" and by[m.model_id].execution == "in_process"
    assert by["imported-onnx"].origin == "imported" and by["imported-onnx"].execution == "isolated"
    assert by["broken"].status == "rejected" and "modalities" in (by["broken"].reason or "")
    pk = by["imported-pickle"]
    assert pk.unsafe_format and reg.trust_of(pk) is None
    t = reg.set_trust("imported-pickle", True, by="test operator")
    assert t is not None and t["by"] == "test operator" and t["sha256"] == pk.artifact_sha256
    assert reg.trust_of(reg.get("imported-pickle")) is not None  # type: ignore[arg-type]
    # changing the file voids the decision (trust names the old hash)
    _write_manifest(tmp_path, "imported-pickle", "pickle", b"other bytes")
    assert reg.trust_of(reg.get("imported-pickle")) is None  # type: ignore[arg-type]
    reg.set_trust("imported-pickle", False)
    assert "imported-pickle" not in json.loads((tmp_path / "_trust.json").read_text())
    with pytest.raises(KeyError):
        reg.set_trust(m.model_id, True)  # only model files can be trusted
    # the NWB catalog ignores manifests and the trust file
    assert all(
        not p.name.startswith("_")
        for p in tmp_path.glob("*.json")
        if p.name.endswith(".manifest.json")
    )


def test_nwb_catalog_attaches_only_ridge_models_and_ignores_other_families_quietly(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    from brainos.runtime.catalog import NWBCatalog

    m, x = _ridge()
    m.save(tmp_path / f"{m.model_id}.json")
    labels = (np.arange(len(x)) % 2).astype(float)
    lda = fit_lda(
        np.log1p(x),
        labels,
        np.ones(len(x), bool),
        class_values=[0.0, 1.0],
        class_names=["a", "b"],
        bin_ms=20.0,
        space="s",
        training={},
        input_spec={},
    )
    lda.save(tmp_path / f"{lda.model_id}.json")
    _write_manifest(tmp_path, "imported-onnx", "onnx")
    with caplog.at_level("WARNING"):
        found = NWBCatalog(tmp_path / "datasets", tmp_path)._decoders()
    assert [d.model_id for d in found] == [m.model_id]
    assert not [r for r in caplog.records if "ignoring model" in r.getMessage()]


def test_duplicate_model_ids_are_rejected(tmp_path: Path) -> None:
    m, _ = _ridge()
    m.save(tmp_path / f"{m.model_id}.json")
    d = json.loads((tmp_path / f"{m.model_id}.json").read_text())
    (tmp_path / "copy.json").write_text(json.dumps(d))
    recs = [r for r in ModelRegistry(tmp_path).records() if r.model_id == m.model_id]
    assert [r.status for r in recs].count("rejected") == 1


# ----------------------------------------------------------------------------- monitor


def _monitor(**kw: Any) -> DriftMonitor:
    base: dict[str, Any] = {
        "model_id": "m",
        "dims": ["vx", "vy"],
        "output_kind": "continuous",
        "bin_ms": 20.0,
        "feature_stats": {"mean": [3.0] * 8, "std": [1.0] * 8},
        "reference": {"r2": 0.6},
    }
    base.update(kw)
    return DriftMonitor(**base)


def test_drift_triggers_on_a_shifted_stream_and_not_on_an_unshifted_one() -> None:
    rng = np.random.default_rng(0)
    same, shifted = _monitor(), _monitor()
    for i in range(600):
        x = 3.0 + rng.standard_normal(8)
        same.add(i, x, np.zeros(2))
        shifted.add(i, x + np.r_[np.full(4, 1.5), np.zeros(4)], np.zeros(2))
    a, b = same.status(), shifted.status()
    assert not a["recalibration_recommended"] and a["features"]["shift_z_rms"] < 0.2
    assert b["recalibration_recommended"] and b["features"]["shift_z_rms"] > 0.5
    assert sorted(b["features"]["most_shifted_channels"][:4]) == [0, 1, 2, 3]
    assert any("moved" in r for r in b["reasons"])


def test_drift_needs_enough_bins_and_training_statistics() -> None:
    m = _monitor()
    for i in range(50):
        m.add(i, np.full(8, 9.0), np.zeros(2))
    assert not m.status()["recalibration_recommended"]  # < min_bins
    m = _monitor(feature_stats=None)
    m.add(0, np.zeros(8), np.zeros(2))
    st = m.status()
    assert (
        not st["features"]["available"]
        and "no training feature statistics" in st["features"]["reason"]
    )


def test_label_metrics_pair_by_bin_end_and_flag_degradation() -> None:
    rng = np.random.default_rng(1)
    good, bad = _monitor(), _monitor()
    bin_ns = 20_000_000
    for i in range(400):
        y = rng.standard_normal(2)
        ts = (i + 1) * bin_ns
        good.add_label(ts, list(y), True, ["vx", "vy"])  # labels may arrive first
        good.add(ts, 3.0 + rng.standard_normal(8), y + 0.1 * rng.standard_normal(2))
        bad.add(ts, 3.0 + rng.standard_normal(8), rng.standard_normal(2))
        bad.add_label(ts + 3_000_000, list(y), True, ["vx", "vy"])  # within half a bin
    g, b = good.status()["labels"], bad.status()["labels"]
    assert g["metric"] == "r2" and g["value"] > 0.9 and g["pairs"] >= 390
    assert b["value"] < 0.1 and bad.status()["recalibration_recommended"]
    assert not good.status()["recalibration_recommended"]
    other = _monitor()
    for i in range(20):
        other.add((i + 1) * bin_ns, np.full(8, 3.0), np.zeros(2))
        other.add_label((i + 1) * bin_ns, [1.0], True, ["cue"])
    assert "no common dimension" in other.status()["labels"]["note"]


def test_classifier_monitor_uses_balanced_accuracy() -> None:
    m = _monitor(
        dims=["rest", "go"],
        output_kind="classes",
        reference={"balanced_accuracy": 0.9, "chance_balanced_accuracy": 0.5},
    )
    for i in range(300):
        label = float(i % 2)
        m.add((i + 1) * 20_000_000, np.full(8, 3.0), np.array([0.9, 0.1]))  # always "rest"
        m.add_label((i + 1) * 20_000_000, [label], True, ["cue"])
    lab = m.status()["labels"]
    assert lab["metric"] == "balanced_accuracy" and lab["value"] == 0.5
    assert m.status()["recalibration_recommended"]
    assert m.status()["outputs"]["class_occupancy"] == {"rest": 1.0, "go": 0.0}


# ----------------------------------------------------------------------------- metrics


def test_velocity_error_and_auc() -> None:
    y = np.array([[1.0, 0.0], [0.0, 1.0]])
    e = velocity_error(y, y + np.array([[0.0, 0.5], [0.5, 0.0]]), ["vx", "vy"])
    assert e["mean_vector_error"] == 0.5 and e["mean_target_speed"] == 1.0
    assert e["rmse_per_dim"]["vx"] == pytest.approx(np.sqrt(0.125))
    assert roc_auc(np.array([0.1, 0.4, 0.35, 0.8]), np.array([0, 0, 1, 1])) == 0.75
    assert roc_auc(np.array([0.1]), np.array([1])) is None


def test_event_metrics_count_onsets_within_tolerance() -> None:
    label = np.zeros(200)
    label[[20, 21, 22, 80, 81, 150]] = 1  # three clicks
    prob = np.zeros(200)
    prob[[23, 24]] = 0.9  # 1 bin after a click: hit
    prob[[100, 101]] = 0.9  # false positive
    prob[[160]] = 0.9  # 10 bins (200 ms) after the third click: hit at 300 ms tolerance
    m = event_metrics(prob, label, np.ones(200, bool), bin_ms=20.0, tolerance_ms=300.0)
    assert (m["true_events"], m["detected_events"], m["event_hits"]) == (3, 3, 2)
    assert m["event_false_positives"] == 1 and m["event_misses"] == 1
    assert m["event_precision"] == pytest.approx(2 / 3) and m["event_recall"] == pytest.approx(
        2 / 3
    )
    assert m["false_positives_per_min"] == pytest.approx(1 / (200 * 0.02 / 60))
    strict = event_metrics(prob, label, np.ones(200, bool), bin_ms=20.0, tolerance_ms=100.0)
    assert strict["event_hits"] == 1


def test_model_check_wrapper_keeps_the_legacy_signature() -> None:
    m, _ = _ridge()
    c = models.check(
        m,
        event_type="features.binned",
        feature="spike_count",
        bin_ms=20.0,
        channel_count=7,
        channel_labels=None,
        stream_identity=None,
        allow_cross_source=True,
    )
    assert c.ok and c.cross_source
    c2 = models.check(
        copy.deepcopy(m),
        event_type="features.binned",
        feature="spike_count",
        bin_ms=50.0,
        channel_count=9,
        channel_labels=None,
        stream_identity=None,
    )
    assert {
        "model expects 20 ms bins, pipeline produces 50 ms",
        "model expects 7 channels, source has 9",
    } <= set(c2.errors)
