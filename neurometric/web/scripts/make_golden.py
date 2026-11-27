"""Golden fixtures for the cross-language parity tests (Python is the reference; D-003).

Writes web/test/golden/degraded_channel.json and web/test/golden/metrics.json.

(a) Deterministic DegradedChannel outputs: configs WITHOUT randomness (gain, bias, asymmetry,
    smoothing, quantization, direction_bins, update_hz, latency_ms, gain decay, dims, selection
    latency) applied to fixed intent sequences, in velocity and position mode.
(b) Metric values (path efficiency, endpoint error, MT, Fitts effective throughput, achieved
    bitrate, Wolpaw bits, MSD, WPM, CCPM, total error rate, ...) on fixed trial / text fixtures.
(c) Reference statistics of the randomised parts (white-noise SD, AR(1) lag-1 autocorrelation,
    false-activation rate, dropout fraction, miss rate) from long Python runs. These cannot match
    bit-for-bit (different PRNGs), so the TypeScript tests compare statistics with tolerances.

    python web/scripts/make_golden.py
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(ROOT / "src"))

from neurometric.metrics.pointing import (  # noqa: E402
    PointingTrials, achieved_bitrate, fitts_throughput, trial_metrics, wolpaw_itr_bits)
from neurometric.metrics.text import BACKSPACE, apply_stream, msd, text_entry_metrics  # noqa: E402
from neurometric.simulator.decoder import DegradationConfig, DegradedChannel  # noqa: E402
from neurometric.simulator.engine import Simulation  # noqa: E402
from neurometric.simulator.modalities import MODALITIES  # noqa: E402

OUT = HERE.parent / "test" / "golden"
DT = 10.0


def jnum(v):
    """JSON-safe number (NaN/inf -> None)."""
    if isinstance(v, (np.bool_, bool)):
        return bool(v)
    if isinstance(v, (np.integer,)):
        return int(v)
    f = float(v)
    return f if math.isfinite(f) else None


def jl(a):
    a = np.asarray(a)
    if a.ndim == 0:
        return jnum(a)
    return [jl(x) for x in a]


# ----------------------------------------------------------------------------- (a) channel
def velocity_intents(T=240):
    t = np.arange(T) * DT / 1000.0
    vx = 420 * np.sin(2 * np.pi * 0.7 * t) + 90 * np.cos(2 * np.pi * 2.3 * t)
    vy = -310 * np.cos(2 * np.pi * 0.45 * t) + 60 * np.sin(2 * np.pi * 3.1 * t + 0.4)
    v = np.stack([vx, vy], 1)
    v[100:115] = 0.0  # a stretch of rest
    v[150:160, 0] = -250.0  # a constant leftward segment
    return v


def position_intents(T=240):
    t = np.arange(T) * DT / 1000.0
    x = 640 + 380 * np.sin(2 * np.pi * 0.35 * t) + 25 * np.sin(2 * np.pi * 2.9 * t)
    y = 400 + 260 * np.sin(2 * np.pi * 0.22 * t + 1.0) - 18 * np.cos(2 * np.pi * 3.7 * t)
    p = np.stack([x, y], 1)
    p[120:140] = p[120]  # pointer held still
    return p


def select_intents(T=240):
    s = np.zeros(T, bool)
    for a, b in [(20, 35), (60, 61), (90, 130), (170, 175), (200, 239)]:
        s[a:b] = True
    return s


DET_CONFIGS = {
    "identity": {},
    "gain_1.3": {"gain": 1.3},
    "gain_0.6": {"gain": 0.6},
    "bias_15": {"bias_deg": 15.0},
    "bias_-30": {"bias_deg": -30.0},
    "asym_0.3": {"asymmetry": 0.3},
    "smooth_50": {"smoothing_tau_ms": 50.0},
    "quant_25": {"quantization": 25.0},
    "dirbins_8": {"direction_bins": 8},
    "update_20hz": {"update_hz": 20.0},
    "update_30hz": {"update_hz": 30.0},
    "latency_70": {"latency_ms": 70.0},
    "latency_5": {"latency_ms": 5.0},
    "gain_decay": {"gain_decay_per_min": 0.4},
    "dims_y_only": {"dims": [False, True]},
    "select_latency_60": {"select_latency_ms": 60.0},
    "combined": {"gain": 0.8, "bias_deg": 10.0, "asymmetry": 0.2, "smoothing_tau_ms": 40.0,
                 "quantization": 5.0, "direction_bins": 16, "update_hz": 25.0, "latency_ms": 50.0,
                 "select_latency_ms": 30.0},
}


def run_channel(cfg_kw, mode, intents, sel, session_minutes=0.0):
    kw = dict(cfg_kw)
    if "dims" in kw:
        kw["dims"] = tuple(kw["dims"])
    cfg = DegradationConfig(**kw)
    ch = DegradedChannel(cfg, 1, DT, mode, np.random.default_rng(0),
                         session_minutes=np.array([session_minutes]))
    out, sel_out = [], []
    for k in range(len(intents)):
        v, s = ch.step(intents[k][None, :], np.array([sel[k]]))
        out.append(v[0].tolist())
        sel_out.append(bool(s[0]))
    return out, sel_out


def golden_channel():
    vi, pi, si = velocity_intents(), position_intents(), select_intents()
    cases = []
    for name, kw in DET_CONFIGS.items():
        for mode, intents in (("velocity", vi), ("position", pi)):
            sm = 1.5 if name == "gain_decay" else 0.0
            out, sel_out = run_channel(kw, mode, intents, si, sm)
            cases.append({"name": f"{name}/{mode}", "config": kw, "mode": mode, "dt_ms": DT,
                          "session_minutes": sm, "output": out, "select_out": sel_out})
    return {"generator": "web/scripts/make_golden.py", "dt_ms": DT,
            "intents": {"velocity": vi.tolist(), "position": pi.tolist()},
            "select_intent": si.tolist(), "cases": cases}


# ----------------------------------------------------------------------------- (c) statistics
def stats_reference():
    rng = np.random.default_rng(12345)
    T, B = 20000, 4
    out = {}
    # white noise only (velocity, zero intent): per-axis SD == white_noise
    ch = DegradedChannel(DegradationConfig(white_noise=40.0), B, DT, "velocity", rng)
    xs = np.array([ch.step(np.zeros((B, 2)), np.zeros(B, bool))[0] for _ in range(T)])
    out["white_noise_40"] = {"sd": float(xs.std()), "lag1": float(_lag1(xs[:, 0, 0]))}
    ch = DegradedChannel(DegradationConfig(correlated_noise=50.0, correlated_tau_ms=300.0), B, DT,
                         "velocity", rng)
    xs = np.array([ch.step(np.zeros((B, 2)), np.zeros(B, bool))[0] for _ in range(T)])
    out["ar1_50_tau300"] = {"sd": float(xs.std()), "lag1": float(np.mean([_lag1(xs[:, b, 0]) for b in range(B)])),
                            "rho_expected": float(np.exp(-DT / 300.0))}
    ch = DegradedChannel(DegradationConfig(false_select_per_min=30.0), B, DT, "velocity", rng)
    fs = np.array([ch.step(np.zeros((B, 2)), np.zeros(B, bool))[1] for _ in range(T)])
    out["false_select_30pm"] = {"per_min": float(fs.sum() / (B * T * DT / 60000.0))}
    ch = DegradedChannel(DegradationConfig(dropout_enter_per_s=0.5, dropout_mean_ms=400.0), B, DT,
                         "velocity", rng)
    for _ in range(T):
        ch.step(np.ones((B, 2)) * 100, np.zeros(B, bool))
    p_in = 1 - math.exp(-0.5 * DT / 1000)
    p_out = 1 - math.exp(-DT / 400.0)
    out["dropout_0.5ps_400ms"] = {"fraction": float(ch.dropout_ticks.sum() / (B * T)),
                                  "fraction_expected": p_in / (p_in + p_out)}
    ch = DegradedChannel(DegradationConfig(select_miss_prob=0.25), B, DT, "velocity", rng)
    sel = np.zeros(T, bool)
    sel[::10] = True  # one tick pulses: 2000 intended selections
    produced = 0
    for k in range(T):
        produced += int(ch.step(np.zeros((B, 2)), np.full(B, sel[k]))[1].sum())
    out["miss_0.25"] = {"miss_rate": 1 - produced / (B * sel.sum())}
    ch = DegradedChannel(DegradationConfig(latency_ms=50.0, latency_jitter_ms=30.0), B, DT,
                         "velocity", rng)
    ramp = np.arange(T, dtype=float)
    outs = np.array([ch.step(np.full((B, 2), ramp[k]), np.zeros(B, bool))[0][:, 0] for k in range(T)])
    delay = ramp[:, None] - outs  # ticks of delay
    out["latency_50_jitter_30"] = {"mean_delay_ms": float(delay[200:].mean() * DT),
                                   "monotonic_output": bool(np.all(np.diff(outs[200:], axis=0) >= 0))}
    return out


def _lag1(x):
    x = x - x.mean()
    return float(np.dot(x[1:], x[:-1]) / np.dot(x, x))


# ----------------------------------------------------------------------------- (b) metrics
def pointing_fixture():
    """Realistic trajectories from the simulator (mouse_sim + bci_good), stored as plain lists."""
    rng = np.random.default_rng(7)
    sets = []
    for mod_name, D, W in (("mouse_sim", 512, 64), ("bci_cursor_good_sim", 256, 96),
                           ("bci_cursor_poor_sim", 512, 32)):
        mod = MODALITIES[mod_name]
        B = 14
        start = np.tile([640 - D / 2, 400.0], (B, 1))
        sim = Simulation(mod.user_model, mod.user, mod.degradation, B, rng, start=start)
        tgt = np.tile([[640 + D / 2, 400.0, W / 2, W / 2]], (B, 1, 1))
        st = sim.acquire(tgt, max_ms=6000, end_on_empty=True)
        tr = PointingTrials.from_step(st)
        # one artificial timeout & one empty-space selection for coverage
        trials = []
        for i in range(B):
            k = int(np.sum(~np.isnan(tr.traj[i, :, 0])))
            trials.append({
                "t_ms": tr.t_ms[i, :k].tolist(), "xy": tr.traj[i, :k].tolist(),
                "start": tr.start[i].tolist(), "target": tr.target_c[i].tolist(),
                "half": tr.target_h[i].tolist(), "sel_t": jnum(tr.sel_t[i]),
                "sel_pos": jl(tr.sel_pos[i]), "sel_item": int(tr.sel_item[i]),
                "n_empty": int(tr.n_empty_selects[i])})
        sets.append({"name": f"{mod_name}_D{D}_W{W}", "D": D, "W": W, "trials": trials,
                     "expected": _expected_pointing(tr, D, W)})
    return sets


def _expected_pointing(tr, D, W):
    tm = trial_metrics(tr)
    keys = ["movement_time_ms", "onset_ms", "distance_px", "path_length_px", "path_efficiency",
            "endpoint_error_px", "endpoint_dx_px", "amplitude_px", "overshoot_px",
            "target_reentries", "success", "error", "timeout"]
    per = {k: jl(tm[k]) for k in keys}
    r = fitts_throughput(tr, D, W)
    return {"trial": per, "fitts": {"tp_effective_bps": jnum(r.tp_effective_bps),
                                    "tp_nominal_bps": jnum(r.tp_nominal_bps),
                                    "we_px": jnum(r.we_px), "de_px": jnum(r.de_px),
                                    "ide_bits": jnum(r.ide_bits), "id_bits": jnum(r.id_bits),
                                    "mt_ms": jnum(r.mt_ms), "error_rate": jnum(r.error_rate),
                                    "n": r.n, "valid": bool(r.valid)}}


def handmade_pointing():
    """Small hand-made trials incl. a timeout, a miss and a re-entry, for edge-case coverage."""
    trials = [
        {"t_ms": [0, 10, 20, 30, 40, 50], "xy": [[100, 100], [150, 110], [220, 95], [300, 102],
                                                 [330, 99], [312, 101]],
         "start": [100, 100], "target": [300, 100], "half": [20, 20], "sel_t": 50,
         "sel_pos": [312, 101], "sel_item": 0, "n_empty": 0},
        {"t_ms": [0, 16.7, 33.4, 50.1, 66.8], "xy": [[300, 100], [250, 140], [180, 190],
                                                    [140, 205], [130, 210]],
         "start": [300, 100], "target": [100, 200], "half": [20, 20], "sel_t": 66.8,
         "sel_pos": [130, 210], "sel_item": -1, "n_empty": 1},
        {"t_ms": [0, 10, 20, 30], "xy": [[100, 200], [100, 200], [101, 200], [101, 201]],
         "start": [100, 200], "target": [500, 400], "half": [30, 30], "sel_t": None,
         "sel_pos": [101, 201], "sel_item": -2, "n_empty": 0},
        {"t_ms": [0, 10, 20, 30, 40, 50, 60, 70], "xy": [[500, 400], [520, 380], [560, 350],
                                                         [600, 300], [640, 260], [600, 300],
                                                         [585, 305], [598, 299]],
         "start": [500, 400], "target": [600, 300], "half": [25, 25], "sel_t": 65,
         "sel_pos": [598, 299], "sel_item": 0, "n_empty": 0},
    ]
    tr = _to_trials(trials)
    return {"name": "handmade", "D": 224, "W": 40, "trials": trials,
            "expected": _expected_pointing(tr, 224, 40)}


def _to_trials(trials):
    N = len(trials)
    T = max(len(t["t_ms"]) for t in trials)
    traj = np.full((N, T, 2), np.nan)
    tms = np.full((N, T), np.nan)
    for i, t in enumerate(trials):
        k = len(t["t_ms"])
        traj[i, :k] = np.asarray(t["xy"], float)
        tms[i, :k] = np.asarray(t["t_ms"], float)
    f = lambda key: np.array([t[key] for t in trials], float)  # noqa: E731
    return PointingTrials(traj, tms, f("start"), f("target"), f("half"),
                          np.array([np.nan if t["sel_t"] is None else t["sel_t"] for t in trials]),
                          f("sel_pos"), np.array([t["sel_item"] for t in trials], np.int64),
                          np.array([t["n_empty"] for t in trials], np.int64))


def golden_metrics():
    bitrate = []
    for nc, ni, n, s in [(20, 4, 24, 61.3), (24, 0, 24, 30.0), (3, 9, 24, 50.0), (10, 2, 12, 17.25),
                         (5, 5, 2, 9.0), (7, 1, 1, 3.0), (7, 1, 9, 0.0)]:
        bitrate.append({"n_correct": nc, "n_incorrect": ni, "n_targets": n, "seconds": s,
                        "value": jnum(achieved_bitrate(nc, ni, n, s))})
    wolpaw = []
    for p, n in [(1.0, 24), (0.9, 24), (0.75, 4), (0.5, 2), (0.2, 4), (0.95, 12), (0.6, 1),
                 (0.3333, 3), (0.0, 5)]:
        wolpaw.append({"p": p, "n": n, "bits": jnum(wolpaw_itr_bits(p, n))})
    text = []
    B = BACKSPACE
    cases = [
        ("the kettle is on", list("the kettle is on"), 12.5),
        ("the kettle is on", list("the kettel is on"), 10.0),
        ("please open the window", list("please opne") + [B, B, B] + list("en the windw"), 31.2),
        ("my feet are cold", list("my fet") + [B] + list("et are cold") + [B, B] + list("ld"), 20.0),
        ("can you help me", list("can you"), 8.0),
        ("see you next week", list("see you next week extra"), 22.0),
        ("i am a little tired", [B, B] + list("i am a litle tired"), 25.5),
        ("good morning to you", list("x"), 1.0),
        ("how was your day", list("how was your day"), 0.0),
    ]
    for p, stream, secs in cases:
        r = text_entry_metrics(p, stream, secs).to_dict()
        text.append({"presented": p, "stream": stream, "seconds": secs,
                     "transcribed": apply_stream(stream),
                     "expected": {k: jnum(v) for k, v in r.items()}})
    msd_pairs = [("kitten", "sitting"), ("", "abc"), ("abc", ""), ("flaw", "lawn"),
                 ("the quick", "teh quikc"), ("same", "same")]
    return {"generator": "web/scripts/make_golden.py",
            "pointing": pointing_fixture() + [handmade_pointing()],
            "achieved_bitrate": bitrate, "wolpaw_bits": wolpaw, "text": text,
            "msd": [{"a": a, "b": b, "d": msd(a, b)} for a, b in msd_pairs]}


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "degraded_channel.json").write_text(json.dumps(golden_channel()) + "\n")
    (OUT / "metrics.json").write_text(json.dumps(golden_metrics()) + "\n")
    (OUT / "random_stats.json").write_text(json.dumps(stats_reference(), indent=1) + "\n")
    print(f"wrote golden fixtures to {OUT}")


if __name__ == "__main__":
    main()
