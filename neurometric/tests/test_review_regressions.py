"""Regression tests for findings of docs/review/SCIENCE_CORE_REVIEW.md."""
import numpy as np
import pytest

from neurometric.events.model import EventKind, InputEvent, Modality
from neurometric.metrics.pointing import PointingTrials, trial_metrics
from neurometric.metrics.session import session_summary, tracking_metrics
from neurometric.simulator import tasks as T
from neurometric.simulator.decoder import DegradationConfig, PROFILES
from neurometric.simulator.modalities import MODALITIES, sample_population
from neurometric.experiments.core import battery_scores


def test_C1_performance_rises_with_ability_for_velocity_users():
    mod = MODALITIES["bci_cursor_good_sim"]
    res = []
    for a in (-1.5, 0.0, 1.5):
        rng = np.random.default_rng(3)
        users, _ = sample_population(mod.user, 40, rng, ability_sd=0.3, ability=np.full(40, a))
        tr, tp = T.run_iso(mod, users, 40, rng, 384, 64, n_selections=10, max_ms=10000)
        res.append(np.nanmean(np.where(tr.timeout, 10000, tr.movement_time_ms)))
    assert res[0] > res[1] > res[2]


def test_C2_invalid_throughput_is_nan_and_mt_censored():
    mod = MODALITIES["bci_cursor_good_sim"]
    rng = np.random.default_rng(1)
    users, _ = sample_population(mod.user, 8, rng)
    bad = PROFILES["bci_good"].with_(white_noise=600, correlated_noise=800)
    df = battery_scores(mod, users, 8, rng, degradation=bad, tasks=("iso",), n_iso=6, step_max_ms=3000)
    assert (df.iso_tp_valid_frac == 0).all() and df.iso_tp_bps.isna().all()
    assert (df.iso_mt_ms >= df.iso_mt_completed_ms.fillna(0)).all()


def test_C3_session_clock_runs_through_battery():
    mod = MODALITIES["bci_cursor_good_sim"]
    rng = np.random.default_rng(2)
    users, _ = sample_population(mod.user, 4, rng)
    df = battery_scores(mod, users, 4, rng, tasks=("grid", "tracking"), n_grid=3,
                        session_minutes=np.full(4, 10.0), tracking_ms=3000)
    assert (df.session_minutes_end > 10.0 + 3000 / 60000).all()


def test_C4_scanning_population_varies():
    mod = MODALITIES["switch_scan_sim"]
    rng = np.random.default_rng(4)
    users, _ = sample_population(mod.user, 30, rng, ability_sd=0.4)
    df = battery_scores(mod, users, 30, rng, tasks=("grid",), n_grid=12)
    assert df.grid_time_ms.std() > 50


def test_C5_typing_clock_starts_at_first_keystroke():
    mod = MODALITIES["mouse_sim"]
    rng = np.random.default_rng(5)
    users, _ = sample_population(mod.user, 5, rng)
    ty = T.run_typing(mod, users, 5, rng, ["the kettle is on"])
    assert (ty.seconds < ty.phrase_time_s).all()


def test_typing_terminates_without_any_keystrokes():
    mod = MODALITIES["bci_cursor_good_sim"]
    rng = np.random.default_rng(6)
    users, _ = sample_population(mod.user, 3, rng)
    dead = DegradationConfig(dropout_enter_per_s=1e6, dropout_mean_ms=1e9)
    ty = T.run_typing(mod, users, 3, rng, ["hi"], degradation=dead, max_ms_per_key=200)
    assert ty.aborted.all()


def test_tracking_lag_unbiased():
    t = np.arange(3000) * 10.0
    tgt = np.stack([300 * np.sin(2 * np.pi * 0.2 * t / 1000) + 100 * np.sin(2 * np.pi * 0.37 * t / 1000 + 1),
                    np.zeros_like(t)], 1)
    cur = np.roll(tgt, 20, axis=0)  # 200 ms lag
    m = tracking_metrics(t[100:], cur[100:], tgt[100:], 40)
    assert m["lag_ms"] == pytest.approx(200, abs=10)


def test_repeated_pause_not_double_counted():
    mk = lambda t, k: InputEvent(t_ms=t, kind=k, session_id="s", stream_id="x", modality=Modality.MOUSE)
    evs = [mk(0, EventKind.MARKER), mk(1000, EventKind.PAUSE), mk(2000, EventKind.PAUSE),
           mk(3000, EventKind.RESUME), mk(6000, EventKind.MARKER)]
    s = session_summary(evs, 1, 1)
    assert s["rest_min"] == pytest.approx(2000 / 60000)


def test_reentries_and_axis_crossings_known_counts():
    # path: overshoot past target, come back (TRE=1), zig-zag across the axis twice (TAC=2)
    pts = np.array([[0, 0], [150, 20], [300, -20], [340, 0], [300, 0]], float)
    seg = [np.linspace(pts[i], pts[i + 1], 21)[:-1] for i in range(4)] + [pts[-1:]]
    p = np.concatenate(seg) + [100, 400]
    t = np.linspace(0, 1000, len(p))
    tr = PointingTrials(p[None], t[None], np.array([[100, 400.]]), np.array([[400, 400.]]),
                        np.array([[15, 15.]]), np.array([1000.]), p[-1:], np.array([0]), np.array([0]))
    m = trial_metrics(tr)
    assert m["target_reentries"][0] == 1
    assert m["task_axis_crossings"][0] == 1
