"""Milestone 4: streaming LDA classifier (decoding/lda.py) and classifier calibration.

Accuracy numbers here come from SYNTHETIC data (tests/mi_source.py) and only show that the
implementation recovers a structure that was put into the data on purpose.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from concord.decoding import model as models
from concord.decoding.calibrate import CalibrationError, calibrate_classifier, class_layout
from concord.decoding.lda import (
    LDAClassifier,
    evaluate_lda,
    fit_lda,
    ledoit_wolf_shrinkage,
)
from concord.decoding.ridge import RidgeDecoder

INPUT = {
    "event_type": "features.vector",
    "feature": "log_band_power",
    "bin_ms": 200.0,
    "channel_count": 4,
    "channel_labels": None,
}


def _blobs(n: int, seed: int = 0) -> tuple[np.ndarray, np.ndarray]:
    rng = np.random.default_rng(seed)
    y = rng.integers(0, 3, n).astype(np.float64)
    means = np.array([[0, 0, 0, 0], [1.5, 0, 0, 0], [0, 1.5, 0, 0]], dtype=np.float64)
    x = means[y.astype(int)] + rng.normal(0, 1, (n, 4))
    return x, y


def _fit(x: np.ndarray, y: np.ndarray, tau: float = 0.0) -> LDAClassifier:
    return fit_lda(
        x,
        y,
        np.ones(len(y), dtype=bool),
        class_values=[0.0, 1.0, 2.0],
        class_names=["rest", "left", "right"],
        bin_ms=200.0,
        tau_ms=tau,
        space="classes_test",
        training={},
        input_spec=INPUT,
        source={"identity": "test"},
    )


def test_ledoit_wolf_matches_the_reference_formula() -> None:
    rng = np.random.default_rng(1)
    x = rng.normal(0, 1, (40, 6)) @ np.diag([1, 2, 3, 1, 1, 0.5])
    x = x - x.mean(axis=0)
    n, p = x.shape
    s = x.T @ x / n
    mu = np.trace(s) / p
    # Ledoit & Wolf (2004): d2 = ||S - mu I||^2 / p, b2 = min(d2, mean_k ||x_k x_k^T - S||^2 / n / p)
    d2 = np.sum((s - mu * np.eye(p)) ** 2) / p
    b2 = sum(np.sum((np.outer(r, r) - s) ** 2) for r in x) / n**2 / p
    expected = min(b2, d2) / d2
    assert ledoit_wolf_shrinkage(x) == pytest.approx(expected, rel=1e-9)
    # anisotropic covariance, many samples -> little shrinkage; isotropic -> the target is
    # right, so shrink a lot; fewer samples than features -> strong shrinkage
    big = rng.normal(0, 1, (5000, 6)) @ np.diag([1, 2, 3, 1, 1, 0.5])
    assert ledoit_wolf_shrinkage(big - big.mean(0)) < 0.05
    iso = rng.normal(0, 1, (5000, 6))
    assert ledoit_wolf_shrinkage(iso - iso.mean(0)) > 0.5
    small = rng.normal(0, 1, (4, 20))
    assert ledoit_wolf_shrinkage(small - small.mean(0)) > 0.3


def test_streaming_equals_offline_and_posteriors_are_probabilities() -> None:
    x, y = _blobs(600)
    m = _fit(x[:400], y[:400], tau=600.0)
    assert len(m.kernel) == 3
    off = m.predict_proba(x[400:])
    s = m.streaming()
    on = np.vstack([s.step(row) for row in x[400:]])
    np.testing.assert_allclose(on, off, rtol=1e-12, atol=1e-12)
    assert np.all(on >= 0) and np.allclose(on.sum(axis=1), 1.0)
    assert m.dims == ["rest", "left", "right"] and m.quantity == "class_posterior"
    assert m.outputs == {"type": "classes", "classes": ["rest", "left", "right"]}


def test_model_file_round_trip_and_registry_dispatch(tmp_path: Path) -> None:
    x, y = _blobs(300)
    m = _fit(x, y)
    p = m.save(tmp_path / f"{m.model_id}.json")
    data = json.loads(p.read_text())
    assert data["schema"] == "concord.model/1" and data["kind"] == "lda"
    assert data["input"] == INPUT and data["source"]["identity"] == "test"
    loaded = models.load_model(p)
    assert isinstance(loaded, LDAClassifier)
    np.testing.assert_allclose(loaded.predict_proba(x), m.predict_proba(x))
    assert models.output_classes(loaded) == ["rest", "left", "right"]
    summary = models.summary(loaded)
    assert summary["outputs"] == {"type": "classes", "classes": ["rest", "left", "right"]}
    # ridge models still load as ridge; broken LDA files are ignored by the listing
    ridge = RidgeDecoder(
        model_id="r1",
        space="s",
        quantity="velocity",
        dims=["a"],
        unit="u",
        bin_ms=20.0,
        tau_ms=240.0,
        kernel=[1.0],
        x_mean=[0.0],
        x_std=[1.0],
        weights=[[1.0]],
        intercept=[0.0],
        alpha=1.0,
        training={},
    )
    ridge.save(tmp_path / "r1.json")
    assert isinstance(models.load_model(tmp_path / "r1.json"), RidgeDecoder)
    assert models.output_classes(models.load_model(tmp_path / "r1.json")) is None
    bad = dict(data, coef=data["coef"][:2])
    (tmp_path / "bad.json").write_text(json.dumps(bad))
    with pytest.raises(ValueError, match="shapes"):
        models.load_model(tmp_path / "bad.json")
    assert sorted(x.model_id for x in models.list_models(tmp_path)) == sorted([m.model_id, "r1"])


def test_evaluation_reports_chance_levels_and_controls() -> None:
    x, y = _blobs(1500, seed=2)
    m = _fit(x[:1000], y[:1000])
    r = evaluate_lda(m, x[1000:], y[1000:], np.ones(500, dtype=bool))
    k = 3
    assert r["samples"] == 500 and np.asarray(r["confusion"]).sum() == 500
    assert r["chance_balanced_accuracy"] == pytest.approx(1 / k)
    counts = np.bincount(y[1000:].astype(int))
    assert r["chance_majority_accuracy"] == pytest.approx(counts.max() / 500)
    assert r["balanced_accuracy"] > 0.6 and r["beats_all_shifts"]
    assert abs(r["control_time_shift_balanced_accuracy"] - 1 / k) < 0.08  # labels i.i.d.
    assert set(r["per_class_accuracy"]) == {"rest", "left", "right"}


def test_fit_refuses_too_few_bins_per_class() -> None:
    x, y = _blobs(100)
    y[y == 2] = 1
    y[:5] = 2
    with pytest.raises(ValueError, match="too few training bins per class"):
        _fit(x, y)


@pytest.mark.parametrize(
    ("labels", "names", "match"),
    [
        ([0, 0, 0], None, "1 distinct value"),
        ([0, 0.5, 1], None, "not a class label"),
        ([0, 1, -1], None, "not a class label"),
        ([0, 1, 2], ["a", "b"], "no class name for label value 2"),
        ([0, 1], ["a", "a"], "unique"),
        ([0, 1], ["a", "b c"], "1-32 characters"),
    ],
)
def test_class_layout_rejects_malformed_labels(
    labels: list[float], names: list[str] | None, match: str
) -> None:
    arr = np.asarray(labels, dtype=np.float64)
    with pytest.raises(CalibrationError, match=match):
        class_layout(arr, np.ones(len(arr), dtype=bool), names, None)


def test_class_layout_names() -> None:
    v = np.ones(4, dtype=bool)
    assert class_layout(np.array([0.0, 2, 1, 2]), v, None, None)[1] == [
        "class_0",
        "class_1",
        "class_2",
    ]
    assert class_layout(np.array([0.0, 2]), v[:2], None, ["rest", "left", "right"]) == (
        [0.0, 2.0],
        ["rest", "right"],
    )
    assert class_layout(np.array([0.0, 1]), v[:2], ["a", "b"], ["x", "y"])[1] == ["a", "b"]


def _recording(path: Path, rows: list[tuple[list[float], float]], dims: list[str]) -> None:
    lines: list[dict[str, Any]] = [{"format": "concord.recording/1", "device": {}}]
    for i, (feat, label) in enumerate(rows):
        ts = (i + 1) * 200_000_000
        lines.append(
            {
                "event_type": "features.vector",
                "device_timestamp_ns": ts,
                "provenance": {"adapter": "x@1.0.0", "origin": "o"},
                "payload": {"feature": "log_band_power", "bin_ms": 200.0, "values": feat},
            }
        )
        lines.append(
            {
                "event_type": "behavior.sample",
                "device_timestamp_ns": ts,
                "payload": {
                    "dims": dims,
                    "values": [label] * len(dims),
                    "valid": True,
                    "unit": "class",
                    "quantity": "cue_class",
                },
            }
        )
    path.write_text("\n".join(json.dumps(x) for x in lines))


def test_classifier_calibration_refusals(tmp_path: Path) -> None:
    x, y = _blobs(300)
    p = tmp_path / "a.concord.jsonl"
    _recording(p, [(list(r), float(c)) for r, c in zip(x, y, strict=True)], ["a", "b"])
    with pytest.raises(CalibrationError, match="choose the class label with label_dim"):
        calibrate_classifier([p])
    with pytest.raises(CalibrationError, match="no dimension 'c'"):
        calibrate_classifier([p], label_dim="c")
    model, report = calibrate_classifier([p], label_dim="a", gap_bins=5, tau_ms=0)
    assert report["classes"] == ["class_0", "class_1", "class_2"]
    assert report["train_bins"] + report["gap_bins"] + report["test_bins"] == 300
    short = tmp_path / "b.concord.jsonl"
    _recording(short, [(list(r), float(c)) for r, c in zip(x[:60], y[:60], strict=True)], ["c"])
    with pytest.raises(CalibrationError, match="only 60 labelled bins"):
        calibrate_classifier([short])
    del model
