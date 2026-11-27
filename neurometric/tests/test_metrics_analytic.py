"""Deterministic fixtures with analytically known metric values."""
import numpy as np
import pytest

from neurometric.metrics.pointing import (WE_FACTOR, PointingTrials, achieved_bitrate,
                                          fitts_throughput, trial_metrics, wolpaw_itr_bits)
from neurometric.metrics.text import BACKSPACE, apply_stream, msd, text_entry_metrics


def straight_trial(D=300.0, n=31, T_ms=600.0, W=40.0, overshoot=0.0, sel_offset=0.0):
    """Cursor moves in a straight line along +x from (100,400) to the target, MT = T_ms."""
    xs = np.linspace(0, D + overshoot, n)
    if overshoot:
        xs = np.r_[xs, np.linspace(D + overshoot, D + sel_offset, 6)[1:]]
    t = np.linspace(0, T_ms, len(xs))
    traj = np.stack([100 + xs, np.full_like(xs, 400.0)], 1)[None]
    return PointingTrials(traj=traj, t_ms=t[None], start=np.array([[100.0, 400.0]]),
                          target_c=np.array([[100 + D, 400.0]]),
                          target_h=np.array([[W / 2, W / 2]]), sel_t=np.array([T_ms]),
                          sel_pos=traj[:, -1], sel_item=np.array([0]),
                          n_empty_selects=np.array([0]))


def test_straight_line_path_efficiency_is_one():
    m = trial_metrics(straight_trial())
    assert m["success"][0]
    assert m["path_efficiency"][0] == pytest.approx(1.0)
    assert m["path_length_px"][0] == pytest.approx(300.0)
    assert m["endpoint_error_px"][0] == pytest.approx(0.0, abs=1e-9)
    assert m["movement_time_ms"][0] == 600.0
    assert m["target_reentries"][0] == 0
    assert m["task_axis_crossings"][0] == 0
    assert m["movement_variability_px"][0] == pytest.approx(0.0, abs=1e-9)
    # onset: first sample beyond 10% of D (30 px) -> sample index 4 at 40 px (10 px spacing)
    assert m["onset_ms"][0] == pytest.approx(600.0 / 30 * 3)


def test_overshoot_measured():
    m = trial_metrics(straight_trial(overshoot=50.0))
    # target half width 20 -> overshoot beyond far edge = 50 - 20 = 30
    assert m["overshoot_px"][0] == pytest.approx(30.0)
    assert m["path_length_px"][0] == pytest.approx(300 + 50 + 50)
    assert m["orthogonal_direction_changes"][0] == 1


def test_lateral_detour_efficiency():
    # path goes up 100 then across 300 then down 100: efficiency 300/500
    pts = np.array([[0, 0], [0, -100], [300, -100], [300, 0]], float)
    seg = [np.linspace(pts[i], pts[i + 1], 51)[:-1] for i in range(3)] + [pts[-1:]]
    p = np.concatenate(seg) + [100, 400]
    t = np.linspace(0, 1000, len(p))
    tr = PointingTrials(p[None], t[None], np.array([[100, 400.]]), np.array([[400, 400.]]),
                        np.array([[20, 20.]]), np.array([1000.]), p[-1:], np.array([0]),
                        np.array([0]))
    m = trial_metrics(tr)
    assert m["path_efficiency"][0] == pytest.approx(0.6)
    assert m["movement_offset_px"][0] < 0  # path is above the axis (y negative, perp = (0,1))


def test_fitts_throughput_known_values():
    # 20 trials with endpoint dx alternating +s/-s around the target centre => SD known exactly
    s = 5.0
    n = 20
    dx = np.array([s if i % 2 == 0 else -s for i in range(n)])
    D, W = 400.0, 40.0
    start = np.tile([100.0, 400.0], (n, 1))
    tc = np.tile([500.0, 400.0], (n, 1))
    sel = tc + np.stack([dx, np.zeros(n)], 1)
    traj = np.stack([start, sel], 1)
    t = np.tile([0.0, 800.0], (n, 1))
    tr = PointingTrials(traj, t, start, tc, np.full((n, 2), W / 2), np.full(n, 800.0), sel,
                        np.zeros(n, int), np.zeros(n, int))
    r = fitts_throughput(tr, D, W)
    sd = np.std(dx, ddof=1)
    we = WE_FACTOR * sd
    ide = np.log2(D / we + 1)
    assert r.we_px == pytest.approx(we)
    assert r.de_px == pytest.approx(D)
    assert r.tp_effective_bps == pytest.approx(ide / 0.8)
    assert r.tp_nominal_bps == pytest.approx(np.log2(D / W + 1) / 0.8)
    assert r.valid and r.error_rate == 0


def test_fitts_flags_high_error_rate():
    n = 12
    start = np.tile([100.0, 400.0], (n, 1))
    tc = np.tile([500.0, 400.0], (n, 1))
    sel = tc + np.stack([np.linspace(-60, 60, n), np.zeros(n)], 1)
    tr = PointingTrials(np.stack([start, sel], 1), np.tile([0.0, 500.0], (n, 1)), start, tc,
                        np.full((n, 2), 10.0), np.full(n, 500.0), sel,
                        np.where(np.abs(sel[:, 0] - 500) <= 10, 0, -1), np.zeros(n, int))
    r = fitts_throughput(tr, 400, 20)
    assert not r.valid
    assert any("error rate" in f for f in r.flags)


def test_wolpaw_itr():
    assert wolpaw_itr_bits(1.0, 2) == pytest.approx(1.0)
    assert wolpaw_itr_bits(1.0, 32) == pytest.approx(5.0)
    assert wolpaw_itr_bits(0.5, 2) == 0.0
    p, n = 0.9, 4
    expected = np.log2(4) + 0.9 * np.log2(0.9) + 0.1 * np.log2(0.1 / 3)
    assert wolpaw_itr_bits(p, n) == pytest.approx(expected)


def test_achieved_bitrate():
    assert achieved_bitrate(10, 0, 9, 10.0) == pytest.approx(3.0)
    assert achieved_bitrate(10, 4, 9, 10.0) == pytest.approx(1.8)
    assert achieved_bitrate(3, 5, 9, 10.0) == 0.0


def test_msd():
    assert msd("kitten", "sitting") == 3
    assert msd("", "abc") == 3
    assert msd("abc", "abc") == 0


def test_text_entry_perfect():
    r = text_entry_metrics("hello world", list("hello world"), 10.0)
    assert r.msd == 0 and r.total_error_rate == 0
    assert r.wpm == pytest.approx((11 - 1) / 10 * 60 / 5)
    assert r.ccpm == pytest.approx(11 / (10 / 60))
    assert r.kspc == 1.0


def test_text_entry_corrected_and_uncorrected():
    # type "the" as "tge" <bs><bs> "he", then "x" instead of nothing: transcribed "thex"
    stream = list("tg") + [BACKSPACE] + list("hex")
    assert apply_stream(stream) == "thex"
    r = text_entry_metrics("the", stream, 6.0)
    assert r.F == 1
    assert r.IF == 1  # 'g' was entered and erased
    assert r.INF == 1  # extra 'x'
    assert r.C == 3
    assert r.total_error_rate == pytest.approx(2 / 5)
    assert r.corrected_error_rate == pytest.approx(1 / 5)
    assert r.uncorrected_error_rate == pytest.approx(1 / 5)
    assert r.correction_burden == pytest.approx(1 / 4)
