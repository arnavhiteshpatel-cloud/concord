"""Simulator determinism and parameter verification."""
import numpy as np
import pytest

from neurometric.simulator.decoder import DegradationConfig, DegradedChannel, PROFILES
from neurometric.simulator.engine import Simulation
from neurometric.simulator.scanning import ScanConfig, scan_select
from neurometric.users.models import UserParams


def run_channel(cfg, intent, sel=None, mode="velocity", seed=0, B=None):
    T = intent.shape[0]
    B = B or intent.shape[1]
    ch = DegradedChannel(cfg, B, 10.0, mode, np.random.default_rng(seed))
    outs, sels = [], []
    for k in range(T):
        s = np.zeros(B, bool) if sel is None else sel[k]
        o, so = ch.step(intent[k], s)
        outs.append(o.copy())
        sels.append(so.copy())
    return np.array(outs), np.array(sels), ch


def test_identity_is_identity():
    rng = np.random.default_rng(1)
    intent = rng.normal(size=(200, 5, 2)) * 100
    out, _, _ = run_channel(DegradationConfig(), intent)
    np.testing.assert_allclose(out, intent)
    outp, _, _ = run_channel(DegradationConfig(), intent, mode="position")
    np.testing.assert_allclose(outp, intent)


def test_fixed_latency_shifts_signal():
    intent = np.zeros((100, 1, 2))
    intent[10:, 0, 0] = 100.0
    out, _, _ = run_channel(DegradationConfig(latency_ms=150), intent)
    first = np.argmax(out[:, 0, 0] > 0)
    assert first == 10 + 15


def test_latency_jitter_never_reorders():
    intent = np.arange(400, dtype=float)[:, None, None].repeat(3, 1).repeat(2, 2)
    out, _, _ = run_channel(DegradationConfig(latency_ms=50, latency_jitter_ms=40), intent)
    assert np.all(np.diff(out[20:, :, 0], axis=0) >= 0)


def test_white_noise_sd():
    intent = np.zeros((5000, 4, 2))
    out, _, _ = run_channel(DegradationConfig(white_noise=50.0), intent)
    assert np.std(out) == pytest.approx(50.0, rel=0.05)


def test_correlated_noise_sd_and_autocorrelation():
    intent = np.zeros((20000, 2, 2))
    out, _, _ = run_channel(DegradationConfig(correlated_noise=40.0, correlated_tau_ms=200), intent)
    x = out[1000:, 0, 0]
    assert np.std(x) == pytest.approx(40.0, rel=0.15)
    r1 = np.corrcoef(x[:-1], x[1:])[0, 1]
    assert r1 == pytest.approx(np.exp(-10 / 200), abs=0.03)


def test_gain_and_bias():
    intent = np.tile([[100.0, 0.0]], (50, 1, 1))
    out, _, _ = run_channel(DegradationConfig(gain=0.5, bias_deg=90), intent)
    np.testing.assert_allclose(out[-1, 0], [0.0, 50.0], atol=1e-9)


def test_asymmetry():
    intent = np.array([[[100.0, 0.0], [-100.0, 0.0]]] * 5)
    out, _, _ = run_channel(DegradationConfig(asymmetry=0.2), intent)
    np.testing.assert_allclose(out[-1, :, 0], [120.0, -80.0])


def test_update_rate_sample_and_hold():
    intent = np.arange(100, dtype=float)[:, None, None].repeat(2, 2)
    out, _, _ = run_channel(DegradationConfig(update_hz=20), intent)
    vals = out[:, 0, 0]
    assert len(np.unique(vals[:50])) == 10  # one new value every 5 ticks at 100 Hz


def test_dropout_fraction_matches_markov_expectation():
    B, T = 200, 3000
    intent = np.ones((T, B, 2)) * 100
    cfg = DegradationConfig(dropout_enter_per_s=0.5, dropout_mean_ms=500)
    out, _, ch = run_channel(cfg, intent, B=B)
    frac = (out[:, :, 0] == 0).mean()
    p_enter = 1 - np.exp(-0.5 * 0.01)
    p_exit = 1 - np.exp(-10 / 500)
    expected = p_enter / (p_enter + p_exit)
    assert frac == pytest.approx(expected, rel=0.15)
    assert ch.dropout_ticks.sum() / (B * T) == pytest.approx(frac, rel=0.02)


def test_false_selections_rate():
    B, T = 100, 6000  # 60 s each
    intent = np.zeros((T, B, 2))
    _, sel, ch = run_channel(DegradationConfig(false_select_per_min=2.0), intent, B=B)
    assert sel.sum() / B == pytest.approx(2.0, rel=0.1)
    assert ch.false_selects.sum() == sel.sum()


def test_select_miss_probability_and_latency():
    B, T = 2000, 40
    sel_int = np.zeros((T, B), bool)
    sel_int[5:15] = True
    intent = np.zeros((T, B, 2))
    _, sel, ch = run_channel(DegradationConfig(select_miss_prob=0.3, select_latency_ms=100),
                             intent, sel=sel_int, B=B)
    produced = sel.any(0).mean()
    assert produced == pytest.approx(0.7, abs=0.04)
    assert np.all(np.argmax(sel[:, sel.any(0)], 0) == 15)


def test_drift_grows_with_session_time():
    intent = np.zeros((6000, 1, 2))
    out, _, _ = run_channel(DegradationConfig(drift=0.0, drift_rate_per_min=60.0), intent)
    mag = np.hypot(out[:, 0, 0], out[:, 0, 1])
    assert mag[-1] == pytest.approx(60.0, rel=0.02)
    assert mag[0] == pytest.approx(0.0, abs=0.1)


def test_simulation_is_deterministic():
    def go(seed):
        sim = Simulation("feedback", UserParams(), PROFILES["bci_moderate"], 20,
                         np.random.default_rng(seed))
        items = np.tile([[900, 400, 30, 30]], (20, 1, 1)).astype(float)
        r = sim.acquire(items)
        return r.sel_t, r.traj
    a, ta = go(7)
    b, tb = go(7)
    c, _ = go(8)
    np.testing.assert_array_equal(np.nan_to_num(a), np.nan_to_num(b))
    np.testing.assert_array_equal(np.nan_to_num(ta), np.nan_to_num(tb))
    assert not np.array_equal(np.nan_to_num(a), np.nan_to_num(c))


def test_intent_and_output_are_distinguished():
    """With a fully blocking dropout the user intends selections but none are produced."""
    cfg = DegradationConfig(dropout_enter_per_s=1e6, dropout_mean_ms=1e9)
    sim = Simulation("feedback", UserParams(), cfg, 10, np.random.default_rng(0),
                     start=np.tile([880.0, 400.0], (10, 1)))
    items = np.tile([[900, 400, 60, 60]], (10, 1, 1)).astype(float)
    r = sim.acquire(items, max_ms=3000)
    assert r.timed_out.all()
    assert (r.gt_intended_selects > 0).all()
    assert (r.gt_missed_selects > 0).all()


def test_scanning_timing():
    rng = np.random.default_rng(0)
    cfg = ScanConfig(scan_ms=1000, rt_ms=300, rt_sigma=1e-6, miss_prob=0.0)
    r = scan_select(rng, 50, np.full(50, 7), 3, 4, cfg)  # row 1, col 3
    # row: 1 step (index 1) + 300 ms; col: index 3 + 300 ms
    assert np.allclose(r["time_ms"], 1000 + 300 + 3000 + 300)
    assert (r["selected"] == 7).all()
    slow = ScanConfig(scan_ms=500, rt_ms=700, rt_sigma=1e-6, miss_prob=0.0)
    r = scan_select(rng, 10, np.full(10, 0), 3, 4, slow)
    assert (r["selected"] != 0).all()  # reaction slower than the scan period lands late
