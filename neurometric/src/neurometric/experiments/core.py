"""Experiment infrastructure: run the simulated battery for a population and produce one row of
participant-level scores per (condition, participant, session).

Every row carries ``synthetic=True``. Seeds are derived from (experiment id, condition key,
replicate) with hashlib, so any single condition can be re-run in isolation and gives identical
results regardless of process count or ordering.
"""
from __future__ import annotations

import hashlib
import json
import os
import platform
import time
from dataclasses import asdict, replace
from multiprocessing import get_context
from pathlib import Path
from typing import Any, Callable, Optional

import numpy as np
import pandas as pd

from ..simulator.decoder import DegradationConfig
from ..simulator.modalities import MODALITIES, Modality, sample_population
from ..simulator import tasks as T
from ..tasks.battery import PHRASES

RESULTS = Path(__file__).resolve().parents[3] / "experiments" / "results"

DEFAULT_TASKS = ("iso", "grid", "typing", "adl", "tracking")


def seed_for(*parts) -> int:
    return int(hashlib.sha256("|".join(map(str, parts)).encode()).hexdigest()[:16], 16)


def battery_scores(mod: Modality, users, n: int, rng: np.random.Generator,
                   degradation: Optional[DegradationConfig] = None,
                   tasks=DEFAULT_TASKS, iso_conditions=((256, 64), (512, 48)),
                   n_iso: int = 13, n_grid: int = 12, phrases=None, adl=("F2",),
                   session_minutes=None, step_max_ms: float = 10000.0,
                   tracking_ms: float = 15000.0, rest_ms: float = 30000.0) -> pd.DataFrame:
    """Run the battery; return one row per participant of participant-level scores.

    One session clock runs through the whole battery (each task starts where the previous one
    ended plus ``rest_ms``), so time-dependent degradation (drift, calibration decay, fatigue)
    affects later tasks as it would in a real session (review C3).
    ISO conditions have distinct IDs (2.32 and 3.55 bits) (review I).
    ``iso_tp_bps`` is NaN for conditions whose throughput is invalid (error rate > 50%, < 10
    selections); ``iso_mt_ms`` counts timeouts at the time limit (censored), and
    ``iso_mt_completed_ms`` is the mean over selection-terminated trials only (review C2).
    """
    out = pd.DataFrame({"participant": np.arange(n)})
    deg = degradation if degradation is not None else (mod.degradation if mod.kind == "pointer" else None)
    pointer = mod.kind == "pointer"
    clock = np.zeros(n) if session_minutes is None else np.asarray(session_minutes, float).copy()
    rt_scale = None
    if not pointer:
        # scanning users inherit their individual reaction-time scale from the population (review C4)
        rt_scale = np.asarray(users.reaction_ms, float) / float(np.median(users.reaction_ms))

    def advance(ms):
        nonlocal clock
        clock = clock + (np.nan_to_num(np.asarray(ms, float)) + rest_ms) / 60000.0

    if "iso" in tasks and pointer:
        tps, trials = [], []
        for D, W in iso_conditions:
            tr, tp = T.run_iso(mod, users, n, rng, D, W, n_selections=n_iso - 1, max_ms=step_max_ms,
                               session_minutes=clock, degradation=deg)
            tps.append(tp)
            trials.append(tr)
            mt_full = np.where(tr["timeout"], step_max_ms, tr["movement_time_ms"])
            advance(pd.Series(mt_full).groupby(tr["participant"].values).sum().reindex(range(n)).values)
        tp = pd.concat(tps)
        tr = pd.concat(trials)
        tp["tp_valid_value"] = np.where(tp["tp_valid"], tp["tp_bps"], np.nan)
        g = tp.groupby("participant")
        out["iso_tp_bps"] = g["tp_valid_value"].mean().values  # NaN unless >=1 valid condition
        out["iso_tp_all_bps"] = g["tp_bps"].mean().values  # includes invalid conditions (diagnostic only)
        out["iso_tp_valid_frac"] = g["tp_valid"].mean().values
        out["iso_error_rate"] = g["error_rate"].mean().values
        tr = tr.assign(mt_censored=np.where(tr["timeout"], step_max_ms, tr["movement_time_ms"]))
        gt = tr.groupby("participant")
        out["iso_timeout_rate"] = gt["timeout"].mean().values
        out["iso_success_rate"] = gt["success"].mean().values
        out["iso_mt_ms"] = gt["mt_censored"].mean().values
        out["iso_mt_completed_ms"] = gt["movement_time_ms"].mean().values
        out["iso_path_efficiency"] = gt["path_efficiency"].mean().values
        out["iso_reentries"] = gt["target_reentries"].mean().values
        out["iso_overshoot_px"] = gt["overshoot_px"].mean().values
        out["iso_movement_variability_px"] = gt["movement_variability_px"].mean().values
        out["iso_endpoint_error_px"] = gt["endpoint_error_px"].mean().values
        out["iso_dial_in_ms"] = gt["dial_in_ms"].mean().values
        out["iso_submovements"] = gt["submovements"].mean().values
        out["iso_onset_ms"] = gt["onset_ms"].mean().values
    if "grid" in tasks:
        gd = T.run_grid(mod, users, n, rng, n_trials=n_grid, max_ms=step_max_ms,
                        session_minutes=clock, degradation=deg if pointer else None,
                        rt_scale=rt_scale)
        gs = T.grid_summary(gd)
        out["grid_accuracy"] = gs["accuracy"].values
        out["grid_time_ms"] = gs["mean_time_ms"].values
        out["grid_bitrate_bps"] = gs["achieved_bitrate_bps"].values
        secs = gd.groupby("participant")["movement_time_ms"].sum().values / 1000
        out["false_activations_per_min"] = gd.groupby("participant")["false_activations"].sum(min_count=1).values / (secs / 60)
        advance(secs * 1000)
    if "typing" in tasks:
        ph = phrases or PHRASES[:1]
        ty = T.run_typing(mod, users, n, rng, ph, session_minutes=clock,
                          degradation=deg if pointer else None, max_ms_per_key=step_max_ms,
                          rt_scale=rt_scale)
        g = ty.groupby("participant")
        out["type_wpm"] = g["wpm"].mean().values
        out["type_ccpm"] = g["ccpm"].mean().values
        out["type_total_error_rate"] = g["total_error_rate"].mean().values
        out["type_uncorrected_error_rate"] = g["uncorrected_error_rate"].mean().values
        out["type_kspc"] = g["kspc"].mean().values
        out["type_correction_burden"] = g["correction_burden"].mean().values
        out["type_aborted_frac"] = g["aborted"].mean().values
        advance(g["phrase_time_s"].sum().values * 1000)
    if "adl" in tasks:
        res = []
        for a in adl:
            r = T.run_adl(mod, users, n, rng, a, session_minutes=clock,
                          degradation=deg if pointer else None, step_max_ms=step_max_ms,
                          rt_scale=rt_scale)
            res.append(r)
            advance(r["time_spent_ms"].values)
        ad = pd.concat(res)
        g = ad.groupby("participant")
        out["adl_completion_rate"] = g["completed"].mean().values
        out["adl_time_s"] = (g["time_to_complete_ms"].mean() / 1000).values
        out["adl_wrong_selections"] = g["wrong_selections"].mean().values
    if "tracking" in tasks and pointer and mod.user_model == "feedback":
        tk = T.run_tracking(mod, users, n, rng, duration_ms=tracking_ms, degradation=deg,
                            session_minutes=clock)
        out["track_rms_px"] = tk["rms_error_px"].values
        out["track_time_on_target"] = tk["time_on_target"].values
        out["track_lag_ms"] = tk["lag_ms"].values
        advance(np.full(n, tracking_ms))
    out["session_minutes_end"] = clock
    out["selection_method"] = ("scanning" if not pointer else
                               f"dwell_{int(mod.dwell_ms)}ms" if mod.selection == "dwell" else "click")
    out["modality"] = mod.name
    out["synthetic"] = True
    return out


METRIC_DIRECTION = {  # +1: higher is better, -1: lower is better
    "iso_tp_bps": 1, "iso_error_rate": -1, "iso_timeout_rate": -1, "iso_success_rate": 1,
    "iso_mt_ms": -1, "iso_mt_completed_ms": -1, "iso_tp_all_bps": 1, "iso_path_efficiency": 1, "iso_reentries": -1, "iso_overshoot_px": -1,
    "iso_movement_variability_px": -1, "iso_endpoint_error_px": -1, "iso_dial_in_ms": -1,
    "iso_submovements": -1, "iso_onset_ms": -1,
    "grid_accuracy": 1, "grid_time_ms": -1, "grid_bitrate_bps": 1, "false_activations_per_min": -1,
    "type_wpm": 1, "type_ccpm": 1, "type_total_error_rate": -1, "type_uncorrected_error_rate": -1,
    "type_kspc": -1, "type_correction_burden": -1, "type_aborted_frac": -1,
    "adl_completion_rate": 1, "adl_time_s": -1, "adl_wrong_selections": -1,
    "track_rms_px": -1, "track_time_on_target": 1, "track_lag_ms": -1,
}

METRIC_BOUNDS = {  # natural floor / ceiling (for floor-ceiling analysis)
    "iso_error_rate": (0, 1), "iso_success_rate": (0, 1), "iso_timeout_rate": (0, 1),
    "grid_accuracy": (0, 1), "grid_bitrate_bps": (0, None), "adl_completion_rate": (0, 1),
    "type_ccpm": (0, None), "type_wpm": (None, None), "track_time_on_target": (0, 1),
    "type_total_error_rate": (0, 1), "false_activations_per_min": (0, None),
    "iso_path_efficiency": (0, 1), "adl_wrong_selections": (0, None), "iso_reentries": (0, None),
}


def _job(args):
    (exp_id, cond_key, rep, mod_name, deg_dict, n, ability_sd, user_over, kw, pop_seed, day_sd) = args
    mod = MODALITIES[mod_name]
    if user_over:
        mod = replace(mod, user=replace(mod.user, **user_over))
    deg = DegradationConfig(**{**deg_dict, "dims": tuple(deg_dict.get("dims", (True, True)))}) \
        if deg_dict is not None else None
    # population: drawn from pop_seed (shared across conditions -> same virtual people)
    prng = np.random.default_rng(seed_for(exp_id, "population", pop_seed))
    users, z = sample_population(mod.user, n, prng, ability_sd=ability_sd)
    rng = np.random.default_rng(seed_for(exp_id, cond_key, rep))
    if day_sd > 0:
        # day-to-day within-person variation, independent per session (replicate): without it,
        # repeated sessions differ only in noise streams and reliability is overstated (review I)
        drng = np.random.default_rng(seed_for(exp_id, "day", pop_seed, rep))
        users = replace(users, vmax=users.vmax * np.exp(day_sd * drng.standard_normal(n)),
                        reaction_ms=users.reaction_ms * np.exp(day_sd * drng.standard_normal(n)),
                        motor_noise=users.motor_noise * np.exp(day_sd * drng.standard_normal(n)),
                        sub_c=users.sub_c * np.exp(day_sd * drng.standard_normal(n)),
                        fixation_jitter=users.fixation_jitter * np.exp(day_sd * drng.standard_normal(n)))
    t0 = time.time()
    df = battery_scores(mod, users, n, rng, degradation=deg, **kw)
    df["latent_ability"] = z
    df["cond"] = cond_key
    df["rep"] = rep
    df["runtime_s"] = time.time() - t0
    return df


def run_grid_jobs(exp_id: str, jobs: list[dict], processes: int = 4) -> pd.DataFrame:
    """jobs: dicts with keys cond, rep, modality, degradation (DegradationConfig|None), n,
    ability_sd, user_over, kw, pop_seed, plus any extra columns to attach."""
    args = []
    for j in jobs:
        d = j.get("degradation")
        args.append((exp_id, j["cond"], j.get("rep", 0), j["modality"],
                     None if d is None else asdict(d), j.get("n", 60), j.get("ability_sd", 0.25),
                     j.get("user_over"), j.get("kw", {}), j.get("pop_seed", 0),
                     j.get("day_sd", 0.10)))
    if processes > 1:
        with get_context("fork").Pool(processes) as pool:
            frames = pool.map(_job, args, chunksize=1)
    else:
        frames = [_job(a) for a in args]
    for f, j in zip(frames, jobs):
        for k, v in j.get("extra", {}).items():
            f[k] = v
    return pd.concat(frames, ignore_index=True)


def save(exp_id: str, name: str, df: pd.DataFrame) -> Path:
    d = RESULTS / exp_id
    d.mkdir(parents=True, exist_ok=True)
    p = d / f"{name}.csv"
    df.to_csv(p, index=False)
    return p


def write_summary(exp_id: str, summary: dict) -> Path:
    d = RESULTS / exp_id
    d.mkdir(parents=True, exist_ok=True)
    import neurometric
    summary = {"experiment": exp_id, "generated_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
               "software": {"neurometric": getattr(neurometric, "__version__", "0.1.0"),
                            "python": platform.python_version(), "numpy": np.__version__,
                            "pandas": pd.__version__},
               "synthetic": True,
               "disclaimer": "Simulation results. They characterise the measurement system under "
                             "modelled input degradation; they are not human or clinical data.",
               **summary}
    if summary.get("synthetic") is False:
        summary["disclaimer"] = ("Real public data processed by NeuroMetric. See caveats; not a "
                                 "clinical population unless stated.")
    p = d / "summary.json"
    p.write_text(json.dumps(summary, indent=2, default=_json_default))
    return p


def _json_default(o):
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.floating,)):
        return None if np.isnan(o) else float(o)
    if isinstance(o, np.ndarray):
        return o.tolist()
    if isinstance(o, (np.bool_,)):
        return bool(o)
    return str(o)
