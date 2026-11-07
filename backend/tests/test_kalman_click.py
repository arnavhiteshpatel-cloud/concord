"""Kalman and click decoders (M5, P0): maths, streaming == offline, malformed models refused.

Synthetic data generated here with a known linear-Gaussian model; the real-data checks are in
test_cursorclick_real.py.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import pytest

pytest.importorskip("scipy")

from brainos.decoding import click as clickdec
from brainos.decoding import kalman

INPUTS = [
    {"event_type": "features.binned", "feature": "threshold_crossing_count", "bin_ms": 10.0,
     "channel_count": 20, "channel_labels": None, "unit": "count"},
    {"event_type": "features.vector", "feature": "spike_band_power", "bin_ms": 10.0,
     "channel_count": 10, "channel_labels": None, "unit": "arbitrary^2"},
]  # fmt: skip


def synthetic(seed: int, n: int = 6000) -> tuple[np.ndarray, np.ndarray]:
    """Smooth 2-D velocity; features = tuned linear readout + noise (SBP part is exp'd)."""
    rng = np.random.default_rng(seed)
    v = np.zeros((n, 2))
    for t in range(1, n):
        v[t] = 0.98 * v[t - 1] + 0.02 * rng.normal(size=2)
    tuning = np.random.default_rng(99).normal(size=(30, 2))
    z = v @ tuning.T * 4 + rng.normal(scale=0.5, size=(n, 30))
    x = np.hstack([np.maximum(np.round(z[:, :20] + 3), 0), np.expm1(np.abs(z[:, 20:]) + 1)])
    return x, v


def fit_kalman(**kw: Any) -> kalman.KalmanDecoder:
    xs, ys = zip(*(synthetic(s) for s in (1, 2)), strict=True)
    args: dict[str, Any] = dict(
        inputs=INPUTS,
        transforms=["identity", "log1p"],
        smoothing_tau_ms=0.0,
        shrinkage=0.5,
        dims=["vx", "vy"],
        unit="u/s",
        space="test",
    )
    args.update(kw)
    return kalman.fit(list(xs), list(ys), **args)


def test_kalman_recovers_a_known_linear_system() -> None:
    model = fit_kalman()
    x, v = synthetic(7)
    pred = model.predict(x)
    r2 = 1 - ((pred - v) ** 2).sum() / ((v - v.mean(0)) ** 2).sum()
    assert r2 > 0.6
    shifted = model.predict(np.roll(x, 3000, axis=0))
    assert 1 - ((shifted - v) ** 2).sum() / ((v - v.mean(0)) ** 2).sum() < 0.1
    # dynamics fitted from labels: close to the generating 0.98
    assert np.allclose(np.diag(model.A), 0.98, atol=0.02)


@pytest.mark.parametrize("tau", [0.0, 50.0])
def test_kalman_streaming_equals_offline(tau: float) -> None:
    model = fit_kalman(smoothing_tau_ms=tau)
    x, _ = synthetic(3, 500)
    s = model.streaming()
    online = np.array([s.step(row) for row in x])
    assert np.allclose(online, model.predict(x), atol=1e-9)
    cov = s.covariance()
    assert cov.shape == (2, 2) and np.allclose(cov, cov.T) and np.all(np.diag(cov) >= 0)
    s.reset()
    assert np.allclose(s.step(x[0]), online[0])


def test_kalman_roundtrip_json(tmp_path: Path) -> None:
    model = fit_kalman()
    path = model.save(tmp_path / "m.json")
    data = json.loads(path.read_text())
    assert data["kind"] == "kalman" and data["inputs"][1]["feature"] == "spike_band_power"
    again = kalman.KalmanDecoder.load(path)
    x, _ = synthetic(4, 200)
    assert np.allclose(again.predict(x), model.predict(x))
    assert data["training"]["feature_stats"]["mean"] == model.x_mean
    assert len(data["training"]["behavior_std"]) == 2


@pytest.mark.parametrize(
    ("change", "match"),
    [
        ({"kind": "ridge"}, "kind"),
        ({"K": [[0.0]]}, "K has shape"),
        ({"transforms": ["identity", "sqrt"]}, "transforms"),
        ({"x_std": [0.0] * 30}, "x_std must be positive"),
        ({"M": [[1.5, 0.0], [0.0, 1.5]]}, "unstable"),
        ({"P": [[1.0, 0.5], [0.0, 1.0]]}, "symmetric"),
        ({"c0": [float("nan")] * 30}, "non-finite"),
        ({"unexpected": 1}, "unexpected"),
        ({"y_axis": "north"}, "y_axis"),
    ],
)
def test_malformed_kalman_model_refused(change: dict[str, Any], match: str) -> None:
    data = {**fit_kalman().to_dict(), **change}
    with pytest.raises(ValueError, match=match):
        kalman.KalmanDecoder.from_dict(data, "bad.json")


def test_kalman_rejects_wrong_feature_width() -> None:
    s = fit_kalman().streaming()
    with pytest.raises(ValueError, match="expected 30 features"):
        s.step(np.zeros(29))


# ---------------------------------------------------------------------------- click


def click_data(seed: int, n: int = 5000) -> tuple[np.ndarray, np.ndarray]:
    rng = np.random.default_rng(seed)
    state = (np.sin(np.arange(n) / 80.0) > 0.6).astype(float)  # "attempting a click" epochs
    w = np.random.default_rng(5).normal(size=30)
    x = rng.normal(size=(n, 30)) + np.outer(state, w) * 0.8
    x[:, :20] = np.maximum(np.round(x[:, :20] + 3), 0)
    x[:, 20:] = np.expm1(np.abs(x[:, 20:]))
    return x, state


def fit_click() -> clickdec.ClickDecoder:
    x, y = click_data(1)
    return clickdec.fit(
        [x], [y], inputs=INPUTS, transforms=["identity", "log1p"], smoothing_tau_ms=50.0,
        l2=10.0, space="test",
    )  # fmt: skip


def test_click_probability_separates_states_and_streams_identically() -> None:
    model = fit_click()
    assert model.dims == ["click"] and model.quantity == "click_probability"
    x, y = click_data(2)
    p = model.predict(x)[:, 0]
    assert np.all((p >= 0) & (p <= 1))
    assert p[y == 1].mean() > 0.7 and p[y == 0].mean() < 0.3
    s = model.streaming()
    online = np.array([s.step(r)[0] for r in x[:300]])
    assert np.allclose(online, p[:300], atol=1e-12)


def test_offline_click_rule_equals_the_command_router() -> None:
    """The evaluation's click rule is the router's: same clicks on the same probabilities."""
    from brainos.runtime.router import ClickRule, _RuleState, _step

    rng = np.random.default_rng(3)
    t = np.arange(3000)
    p = np.clip(0.5 + 0.45 * np.sin(t / 37.0) + rng.normal(0, 0.08, t.size), 0, 1)
    for th, hold, refr in ((0.5, 1, 100), (0.6, 10, 100), (0.7, 20, 30)):
        rule = ClickRule(
            **clickdec.router_click_rule(
                {"threshold": th, "hold_bins": hold, "refractory_ms": refr * 10}
            )
        )
        st, live = _RuleState(), []
        for t, v in enumerate(p):
            if _step(
                rule.threshold,
                rule.release_level,
                rule.debounce_ms,
                rule.refractory_ms,
                st,
                float(v),
                t * 10_000_000,
            ):
                live.append(t)
        assert clickdec.decision_events(p, th, hold, refr).tolist() == live
        assert live  # the case is not vacuous


def test_click_decision_rule_hold_and_refractory() -> None:
    p = np.zeros(400)
    p[10:30] = 0.9  # 20 bins above threshold
    p[40:45] = 0.9  # only 5 bins: below hold
    p[200:260] = 0.9
    ev = clickdec.decision_events(p, 0.5, 10, 100)
    assert ev.tolist() == [19, 209]  # fires on the 10th bin; 40-45 too short
    assert clickdec.decision_events(p, 0.5, 10, 300).tolist() == [19]


@pytest.mark.parametrize(
    ("change", "match"),
    [
        ({"kind": "lda"}, "kind"),
        ({"dims": ["x"]}, "click"),
        ({"weights": [0.0] * 3}, "entries"),
        ({"intercept": float("inf")}, "non-finite"),
    ],
)
def test_malformed_click_model_refused(change: dict[str, Any], match: str) -> None:
    data = {**fit_click().to_dict(), **change}
    with pytest.raises(ValueError, match=match):
        clickdec.ClickDecoder.from_dict(data, "bad.json")


def test_click_fit_requires_both_classes() -> None:
    x, _ = click_data(1, 500)
    with pytest.raises(ValueError, match="both 0 and 1"):
        clickdec.fit(
            [x], [np.zeros(500)], inputs=INPUTS, transforms=["identity", "log1p"],
            smoothing_tau_ms=0.0, l2=1.0, space="test",
        )  # fmt: skip
