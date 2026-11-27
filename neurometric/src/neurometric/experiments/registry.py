"""Experiment registry: the computational experiments B-N, P (see EXPERIMENT_REGISTRY.md).

Run:  python -m neurometric.experiments.registry [EXP_ID ...] [--processes 4] [--n 60]
Outputs: experiments/results/<EXP_ID>/{data.csv, properties.csv, summary.json, *.png}
"""
from __future__ import annotations

import argparse
import hashlib
import json
import time
from dataclasses import replace

import numpy as np
import pandas as pd

from ..simulator.decoder import PROFILES, DegradationConfig
from ..simulator.modalities import MODALITIES, sample_population
from ..simulator import tasks as T
from ..simulator.engine import Simulation
from ..tasks.battery import grid_items
from .analysis import LABELS, icc_a1, plot_sweep, style, sweep_properties, PALETTE
from .core import (METRIC_DIRECTION, RESULTS, battery_scores, run_grid_jobs, save, seed_for,
                   write_summary)

BASE = PROFILES["bci_good"]
CORE_METRICS = [m for m in METRIC_DIRECTION]
FIG_METRICS = ["iso_tp_bps", "iso_error_rate", "iso_mt_ms", "iso_path_efficiency",
               "iso_reentries", "grid_accuracy", "grid_bitrate_bps", "false_activations_per_min",
               "type_ccpm", "type_total_error_rate", "adl_completion_rate", "adl_time_s",
               "track_rms_px", "track_time_on_target", "track_lag_ms", "iso_dial_in_ms"]

SWEEPS = {
    "B_noise": ("noise scale (x base white 30 + AR 40 px/s)", [0, 0.5, 1, 2, 3, 4, 6],
                lambda s: BASE.with_(white_noise=30 * s, correlated_noise=40 * s), "bci_cursor_good_sim", {}),
    "C_latency": ("total decoder output latency (ms; base profile has 60)", [0, 60, 120, 200, 300, 450, 700],
                  lambda L: BASE.with_(latency_ms=L), "bci_cursor_good_sim", {}),
    "C2_latency_mouse": ("latency (ms), position-control pointer", [0, 60, 120, 200, 300, 450, 700],
                         lambda L: DegradationConfig(latency_ms=L), "mouse_sim", {}),
    "D_dropout": ("dropout episodes per second (mean 500 ms)", [0, 0.05, 0.1, 0.2, 0.4, 0.8],
                  lambda r: BASE.with_(dropout_enter_per_s=r, dropout_mean_ms=500), "bci_cursor_good_sim", {}),
    "E_drift": ("calibration deterioration index k", [0, 0.5, 1, 2, 4],
                lambda k: BASE.with_(drift_rate_per_min=8 * k, gain_decay_per_min=0.01 * k,
                                     noise_growth_per_min=0.03 * k),
                "bci_cursor_good_sim", {"session_minutes_start": 10.0}),
    "F_false_activation": ("false selections per minute", [0, 1, 2, 4, 8, 16],
                           lambda f: BASE.with_(false_select_per_min=f), "bci_cursor_good_sim", {}),
    "F2_missed_selection": ("missed-selection probability", [0, 0.1, 0.2, 0.4, 0.6],
                            lambda p: BASE.with_(select_miss_prob=p), "bci_cursor_good_sim", {}),
    "B2_bias": ("directional bias (deg)", [0, 15, 30, 45, 60],
                lambda b: BASE.with_(bias_deg=b), "bci_cursor_good_sim", {}),
    "B3_update_rate": ("decoder update interval (ms)", [10, 20, 50, 100, 200],
                       lambda ms: BASE.with_(update_hz=1000.0 / ms), "bci_cursor_good_sim", {}),
    "B4_gain": ("decoder gain", [0.4, 0.6, 0.8, 1.0, 1.4, 2.0],
                lambda g: BASE.with_(gain=g), "bci_cursor_good_sim", {}),
}


def run_sweep(exp_id: str, n: int = 60, processes: int = 4, reps: int = 2) -> dict:
    xlabel, levels, make, mod, opts = SWEEPS[exp_id]
    jobs = []
    for L in levels:
        for r in range(reps):
            kw = {}
            if "session_minutes_start" in opts:
                kw["session_minutes"] = np.full(n, opts["session_minutes_start"])
            jobs.append({"cond": f"{exp_id}:{L}", "rep": r, "modality": mod, "degradation": make(L),
                         "n": n, "kw": kw, "pop_seed": 0, "extra": {"level": L}})
    t0 = time.time()
    df = run_grid_jobs(exp_id, jobs, processes)
    df["experiment"] = exp_id
    save(exp_id, "data", df)
    metrics = [m for m in CORE_METRICS if m in df]
    # B4 gain is non-monotone by design: order by |log gain|
    lvl = "level"
    if exp_id == "B4_gain":
        df["level_abs"] = np.abs(np.log(df["level"]))
        lvl = "level_abs"
    props = sweep_properties(df[df.rep == 0], lvl, metrics)
    # test-retest ICC at each level (rep 0 vs rep 1, same virtual participants)
    iccs = []
    for L in levels:
        d = df[df.level == L]
        for m in metrics:
            w = d.pivot(index="participant", columns="rep", values=m).to_numpy()
            iccs.append({"level": L, "metric": m, "icc_a1": icc_a1(w)})
    icc = pd.DataFrame(iccs)
    save(exp_id, "properties", props)
    save(exp_id, "retest_icc", icc)
    plot_sweep(df[df.rep == 0], "level", [m for m in FIG_METRICS if m in df], LABELS, xlabel,
               f"{exp_id}", RESULTS / exp_id / "sweep.png")
    summ = {"levels": levels, "x": xlabel, "n_participants": n, "reps": reps,
            "modality": mod, "base_profile": "bci_good" if mod.startswith("bci") else "identity",
            "runtime_s": round(time.time() - t0, 1),
            "n_trials_simulated": int(_trial_count(df)),
            "properties": props.to_dict("records"),
            "median_retest_icc_by_metric": icc.groupby("metric")["icc_a1"].median().to_dict()}
    write_summary(exp_id, summ)
    return summ


def _trial_count(df):
    # ISO 2 conditions x 12 scored + grid 12 + typing keystrokes (~20) + ADL steps (~7)
    return len(df) * (24 + 12 + 20 + 7)


# --------------------------------------------------------------------------- G: metric comparison
def exp_G(**_):
    rows = []
    for exp in SWEEPS:
        p = RESULTS / exp / "properties.csv"
        if p.exists():
            d = pd.read_csv(p)
            d["sweep"] = exp
            rows.append(d)
    if not rows:
        return {}
    allp = pd.concat(rows)
    save("G_metric_comparison", "all_properties", allp)
    # sensitivity heatmap: -Spearman rho of (oriented) score with degradation level
    piv = allp.pivot_table(index="metric", columns="sweep", values="rho")
    piv = piv.loc[[m for m in METRIC_DIRECTION if m in piv.index]]
    plt = style()
    fig, ax = plt.subplots(figsize=(1.0 * piv.shape[1] + 3, 0.32 * piv.shape[0] + 1.5))
    im = ax.imshow(-piv.to_numpy(), cmap="Blues", vmin=0, vmax=1, aspect="auto")
    ax.set_xticks(range(piv.shape[1]), [c.replace("_", " ") for c in piv.columns], rotation=40,
                  ha="right")
    ax.set_yticks(range(piv.shape[0]), [LABELS.get(i, i) for i in piv.index])
    for i in range(piv.shape[0]):
        for j in range(piv.shape[1]):
            v = -piv.iat[i, j]
            if np.isfinite(v):
                ax.text(j, i, f"{v:.2f}", ha="center", va="center", fontsize=6,
                        color="white" if v > 0.6 else "#191919")
    ax.grid(False)
    fig.colorbar(im, ax=ax, label="sensitivity: -Spearman rho(score oriented 'higher=better', degradation)")
    ax.set_title("Metric sensitivity to each degradation type (simulation)")
    fig.tight_layout()
    fig.savefig(RESULTS / "G_metric_comparison" / "sensitivity_heatmap.png")
    plt.close(fig)
    # ranking: mean sensitivity across sweeps (excluding gain, non-monotone), retest ICC
    icc_rows = []
    for exp in SWEEPS:
        p = RESULTS / exp / "retest_icc.csv"
        if p.exists():
            d = pd.read_csv(p)
            d["sweep"] = exp
            icc_rows.append(d)
    icc = pd.concat(icc_rows)
    base_icc = icc[icc.level == icc.groupby("sweep")["level"].transform("min")]
    rank = pd.DataFrame({
        "mean_sensitivity": -allp[allp.sweep != "B4_gain"].groupby("metric")["rho"].mean(),
        "min_sensitivity": -allp[allp.sweep != "B4_gain"].groupby("metric")["rho"].max(),
        "mean_monotone_frac": allp[allp.sweep != "B4_gain"].groupby("metric")["monotone_frac"].mean(),
        "mean_auc_adjacent": allp.groupby("metric")["auc_adjacent"].mean(),
        "max_undefined_frac": allp.groupby("metric")["undefined_frac"].max(),
        "max_floor_frac": allp.groupby("metric")["floor_frac"].max(),
        "max_ceiling_frac": allp.groupby("metric")["ceiling_frac"].max(),
        "median_retest_icc": icc.groupby("metric")["icc_a1"].median(),
        "baseline_retest_icc": base_icc.groupby("metric")["icc_a1"].median(),
    }).sort_values("mean_sensitivity", ascending=False)
    save("G_metric_comparison", "ranking", rank.reset_index())
    summ = {"ranking": rank.reset_index().to_dict("records"), "sweeps": list(SWEEPS)}
    write_summary("G_metric_comparison", summ)
    return summ


# --------------------------------------------------------------------------- I: reliability vs length
def exp_I(n: int = 80, processes: int = 4, **_):
    """Test-retest reliability as a function of test length, and Spearman-Brown agreement."""
    lengths = [4, 8, 16, 32]
    jobs = []
    for mod in ["bci_cursor_good_sim", "bci_cursor_moderate_sim", "mouse_sim"]:
        for L in lengths:
            for r in range(2):
                kw = {"tasks": ("iso", "grid"), "n_iso": L + 1, "n_grid": L,
                      "iso_conditions": ((384, 64),)}
                jobs.append({"cond": f"I:{mod}:{L}", "rep": r, "modality": mod, "n": n, "kw": kw,
                             "pop_seed": 1, "ability_sd": 0.3,
                             "extra": {"length": L, "mod": mod}})
    df = run_grid_jobs("I_test_retest", jobs, processes)
    save("I_test_retest", "data", df)
    rows = []
    for (mod, L), d in df.groupby(["mod", "length"]):
        for m in ["iso_tp_bps", "iso_mt_ms", "iso_path_efficiency", "iso_error_rate",
                  "grid_accuracy", "grid_time_ms", "grid_bitrate_bps"]:
            w = d.pivot(index="participant", columns="rep", values=m).to_numpy()
            rows.append({"modality": mod, "length": L, "metric": m, "icc_a1": icc_a1(w),
                         "sd": float(np.nanstd(w)), "mean": float(np.nanmean(w))})
    res = pd.DataFrame(rows)
    # Spearman-Brown prediction from the shortest length
    pred = []
    for (mod, m), d in res.groupby(["modality", "metric"]):
        d = d.sort_values("length")
        r0, L0 = d.icc_a1.iloc[0], d.length.iloc[0]
        for _, row in d.iterrows():
            k = row.length / L0
            pred.append(k * r0 / (1 + (k - 1) * r0) if np.isfinite(r0) else np.nan)
    res = res.sort_values(["modality", "metric", "length"])
    res["spearman_brown_pred"] = pred
    res["sem"] = res["sd"] * np.sqrt(np.clip(1 - res["icc_a1"], 0, None))
    res["mdc95"] = 1.96 * np.sqrt(2) * res["sem"]
    save("I_test_retest", "reliability", res)
    plt = style()
    fig, axes = plt.subplots(1, 3, figsize=(10, 3), sharey=True)
    for ax, mod in zip(axes, res.modality.unique()):
        d = res[res.modality == mod]
        for i, m in enumerate(d.metric.unique()):
            dm = d[d.metric == m]
            ax.plot(dm.length, dm.icc_a1, marker="o", color=PALETTE[i % 8], label=LABELS.get(m, m))
            ax.plot(dm.length, dm.spearman_brown_pred, ls=":", color=PALETTE[i % 8], lw=1)
        ax.set_xscale("log", base=2)
        ax.set_title(mod)
        ax.set_xlabel("trials per session")
        ax.axhline(0.8, color="#666666", lw=0.8, ls="--")
    axes[0].set_ylabel("ICC(A,1) test-retest")
    axes[-1].legend(fontsize=6, loc="lower right")
    fig.suptitle("Simulated test-retest reliability vs test length (dotted: Spearman-Brown from shortest)")
    fig.tight_layout()
    fig.savefig(RESULTS / "I_test_retest" / "reliability_vs_length.png")
    plt.close(fig)
    summ = {"design": "80 virtual participants (latent ability SD 0.3) x 2 sessions x 4 lengths x 3 modalities",
            "results": res.to_dict("records")}
    write_summary("I_test_retest", summ)
    return summ


# --------------------------------------------------------------------------- K: responsiveness
def exp_K(n: int = 100, processes: int = 4, **_):
    """Half the participants get an improved decoder at session 2; the other half are stable."""
    lv1 = PROFILES["bci_moderate"]
    improved = replace(lv1, white_noise=lv1.white_noise * 0.6, correlated_noise=lv1.correlated_noise * 0.6,
                       false_select_per_min=0.5, select_miss_prob=0.05)
    jobs = [
        {"cond": "K:s1", "rep": 0, "modality": "bci_cursor_good_sim", "degradation": lv1, "n": n, "pop_seed": 2, "extra": {"session": 1}},
        {"cond": "K:s2_stable", "rep": 1, "modality": "bci_cursor_good_sim", "degradation": lv1, "n": n, "pop_seed": 2, "extra": {"session": 2, "arm": "stable"}},
        {"cond": "K:s2_improved", "rep": 1, "modality": "bci_cursor_good_sim", "degradation": improved, "n": n, "pop_seed": 2, "extra": {"session": 2, "arm": "improved"}},
    ]
    df = run_grid_jobs("K_responsiveness", jobs, processes)
    save("K_responsiveness", "data", df)
    s1 = df[df.session == 1].set_index("participant")
    rows = []
    half = np.arange(n) < n // 2  # first half -> improved arm (assignment fixed in advance)
    for m in [c for c in CORE_METRICS if c in df]:
        sgn = METRIC_DIRECTION[m]
        st = df[(df.session == 2) & (df.arm == "stable")].set_index("participant")[m]
        im = df[(df.session == 2) & (df.arm == "improved")].set_index("participant")[m]
        ch_imp = (im - s1[m])[half] * sgn
        ch_st = (st - s1[m])[~half] * sgn
        # MDC from the stable group (test-retest)
        w = np.c_[s1[m][~half], st[~half]]
        icc = icc_a1(w)
        sd = np.nanstd(w[:, 0], ddof=1)
        sem = sd * np.sqrt(max(1 - icc, 0)) if np.isfinite(icc) else np.nan
        mdc = 1.96 * np.sqrt(2) * sem
        srm = ch_imp.mean() / ch_imp.std(ddof=1) if ch_imp.std(ddof=1) > 0 else np.nan
        gri = ch_imp.mean() / ch_st.std(ddof=1) if ch_st.std(ddof=1) > 0 else np.nan
        from .analysis import auc
        rows.append({"metric": m, "srm_improved": srm, "guyatt_ri": gri,
                     "auc_improved_vs_stable": auc(ch_st.dropna().to_numpy(), ch_imp.dropna().to_numpy()),
                     "icc_stable": icc, "mdc95": mdc,
                     "frac_improved_exceeding_mdc": float(np.mean(ch_imp.dropna() > mdc)) if np.isfinite(mdc) else np.nan,
                     "frac_stable_exceeding_mdc": float(np.mean(ch_st.dropna() > mdc)) if np.isfinite(mdc) else np.nan})
    res = pd.DataFrame(rows).sort_values("auc_improved_vs_stable", ascending=False)
    save("K_responsiveness", "responsiveness", res)
    plt = style()
    fig, ax = plt.subplots(figsize=(6, 0.28 * len(res) + 1))
    y = np.arange(len(res))
    ax.barh(y, res.auc_improved_vs_stable - 0.5, left=0.5, color=PALETTE[0], height=0.6)
    ax.set_yticks(y, [LABELS.get(m, m) for m in res.metric])
    ax.axvline(0.5, color="#666666", lw=0.8)
    ax.set_xlim(0.4, 1.0)
    ax.invert_yaxis()
    ax.set_xlabel("AUC: change score separates improved from stable participants")
    ax.set_title("Responsiveness to a known decoder improvement (simulation)")
    fig.tight_layout()
    fig.savefig(RESULTS / "K_responsiveness" / "responsiveness_auc.png")
    plt.close(fig)
    summ = {"design": f"{n} virtual participants; session 1 bci_moderate; session 2: first half improved decoder (noise x0.6, fewer false/missed selections), second half unchanged",
            "results": res.to_dict("records"),
            "note": "MDC is statistically detectable change; it is NOT a minimal clinically important difference."}
    write_summary("K_responsiveness", summ)
    return summ


# --------------------------------------------------------------------------- L: cross-modality
def exp_L(n: int = 60, processes: int = 4, **_):
    mods = ["mouse_sim", "head_pointer_sim", "eye_gaze_sim", "bci_cursor_good_sim",
            "bci_cursor_moderate_sim", "bci_cursor_poor_sim", "switch_scan_sim", "switch_scan_fast_sim"]
    jobs = [{"cond": f"L:{m}", "rep": r, "modality": m, "n": n, "pop_seed": 3,
             "extra": {"mod": m}} for m in mods for r in range(2)]
    df = run_grid_jobs("L_cross_modality", jobs, processes)
    save("L_cross_modality", "data", df)
    d0 = df[df.rep == 0]
    metrics = [m for m in CORE_METRICS if m in df]
    table = d0.groupby("mod")[metrics].mean().loc[mods]
    applic = d0.groupby("mod")[metrics].apply(lambda x: x.notna().mean()).loc[mods]
    save("L_cross_modality", "means", table.reset_index())
    save("L_cross_modality", "applicability", applic.reset_index())
    icc = []
    for m_ in mods:
        d = df[df["mod"] == m_]
        for m in metrics:
            w = d.pivot(index="participant", columns="rep", values=m).to_numpy()
            icc.append({"mod": m_, "metric": m, "icc_a1": icc_a1(w)})
    save("L_cross_modality", "retest_icc", pd.DataFrame(icc))
    # rank concordance of modalities across metrics that apply to all
    common = [m for m in ["grid_accuracy", "grid_time_ms", "grid_bitrate_bps", "type_ccpm",
                          "adl_completion_rate", "adl_time_s"] if m in table]
    ranks = pd.DataFrame({m: (METRIC_DIRECTION[m] * table[m]).rank(ascending=False) for m in common})
    from scipy.stats import kendalltau
    taus = {f"{a}~{b}": float(kendalltau(ranks[a], ranks[b]).statistic)
            for i, a in enumerate(common) for b in common[i + 1:]}
    plt = style()
    show = ["grid_bitrate_bps", "type_ccpm", "adl_time_s", "grid_accuracy"]
    fig, axes = plt.subplots(1, len(show), figsize=(3.1 * len(show), 3.4))
    for ax, m in zip(axes, show):
        mu = d0.groupby("mod")[m].mean().loc[mods]
        se = d0.groupby("mod")[m].std().loc[mods] / np.sqrt(n)
        ax.barh(range(len(mods)), mu.values, xerr=1.96 * se.values, color=PALETTE[0], height=0.6)
        ax.set_yticks(range(len(mods)), [x.replace("_sim", "") for x in mods] if ax is axes[0] else [])
        ax.invert_yaxis()
        ax.set_title(LABELS.get(m, m))
    fig.suptitle("Same tasks across simulated input modalities (all modalities simulated)")
    fig.tight_layout()
    fig.savefig(RESULTS / "L_cross_modality" / "modalities.png")
    plt.close(fig)
    summ = {"modalities": mods, "means": table.reset_index().to_dict("records"),
            "rank_concordance_kendall_tau": taus,
            "applicability": "ISO throughput and tracking are undefined for scanning; tracking only for velocity-control users"}
    write_summary("L_cross_modality", summ)
    return summ


# --------------------------------------------------------------------------- M: person vs device variance
def exp_M(n: int = 60, processes: int = 4, **_):
    """Crossed design: user ability level x device degradation level; variance decomposition."""
    abilities = {"low": -1.0, "mid": 0.0, "high": 1.0}
    devices = {"good": PROFILES["bci_good"], "moderate": PROFILES["bci_moderate"],
               "poor": PROFILES["bci_poor"]}
    frames = []
    for an, a in abilities.items():
        for dn, dv in devices.items():
            mod = MODALITIES["bci_cursor_good_sim"]
            prng = np.random.default_rng(seed_for("M", an))
            users, z = sample_population(mod.user, n, prng, ability_sd=0.3,
                                         ability=np.full(n, a) + 0.3 * prng.standard_normal(n))
            rng = np.random.default_rng(seed_for("M", an, dn))
            df = battery_scores(mod, users, n, rng, degradation=dv, tasks=("iso", "grid", "typing", "adl"))
            df["ability"], df["device"] = an, dn
            frames.append(df)
    df = pd.concat(frames, ignore_index=True)
    save("M_user_variability", "data", df)
    import statsmodels.formula.api as smf
    from statsmodels.stats.anova import anova_lm
    rows = []
    for m in [c for c in CORE_METRICS if c in df]:
        d = df[["ability", "device", m]].dropna().rename(columns={m: "y"})
        if d["y"].std() == 0 or len(d) < 20:
            continue
        fit = smf.ols("y ~ C(ability) * C(device)", d).fit()
        a = anova_lm(fit, typ=2)
        ss = a["sum_sq"]
        tot = ss.sum()
        rows.append({"metric": m, "eta2_ability": ss["C(ability)"] / tot,
                     "eta2_device": ss["C(device)"] / tot,
                     "eta2_interaction": ss["C(ability):C(device)"] / tot,
                     "eta2_residual": ss["Residual"] / tot})
    res = pd.DataFrame(rows)
    save("M_user_variability", "variance_decomposition", res)
    plt = style()
    fig, ax = plt.subplots(figsize=(7, 0.3 * len(res) + 1.2))
    left = np.zeros(len(res))
    for i, c in enumerate(["eta2_device", "eta2_ability", "eta2_interaction", "eta2_residual"]):
        ax.barh(range(len(res)), res[c], left=left, color=PALETTE[i] if i < 3 else "#bdbdbd",
                label=c.replace("eta2_", ""), height=0.6, edgecolor="white", linewidth=1)
        left += res[c].to_numpy()
    ax.set_yticks(range(len(res)), [LABELS.get(m, m) for m in res.metric])
    ax.invert_yaxis()
    ax.set_xlabel("share of variance (eta squared)")
    ax.legend(ncol=4, fontsize=7, loc="upper center", bbox_to_anchor=(0.5, -0.12))
    ax.set_title("Device vs simulated-user variance in each metric (3x3 crossed design)")
    fig.tight_layout()
    fig.savefig(RESULTS / "M_user_variability" / "variance_decomposition.png")
    plt.close(fig)
    summ = {"design": "3 ability levels x 3 decoder profiles x 60 virtual participants",
            "results": res.to_dict("records")}
    write_summary("M_user_variability", summ)
    return summ


# --------------------------------------------------------------------------- N: missing data
def exp_N(n: int = 120, **_):
    """Effect of incomplete sessions on throughput / MT estimates: MCAR vs informative dropout."""
    mod = MODALITIES["bci_cursor_good_sim"]
    rng = np.random.default_rng(seed_for("N"))
    users, z = sample_population(mod.user, n, rng, ability_sd=0.3)
    tr, tp = T.run_iso(mod, users, n, rng, 384, 64, n_targets=25,
                       degradation=PROFILES["bci_moderate"], max_ms=10000)
    full = tr.groupby("participant")["movement_time_ms"].mean()
    full_succ = tr.groupby("participant")["success"].mean()
    rows = []
    for frac in [0.0, 0.1, 0.25, 0.4, 0.6]:
        for mech in ["MCAR", "MNAR_slow_abandon", "MAR_fatigue_late"]:
            r2 = np.random.default_rng(seed_for("N", frac, mech))
            d = tr.copy()
            if mech == "MCAR":
                keep = r2.random(len(d)) >= frac
            elif mech == "MNAR_slow_abandon":
                # participants abandon the session after a slow/failed trial
                d = d.sort_values(["participant", "selection_index"]).reset_index(drop=True)
                keep = np.ones(len(d), bool)
                for pid, g in d.groupby("participant"):
                    idx = g.index.to_numpy()
                    bad = (g["timeout"] | (g["movement_time_ms"] > g["movement_time_ms"].median() * 1.5)).to_numpy()
                    stop = np.nonzero(bad & (r2.random(len(g)) < frac * 1.5))[0]
                    if stop.size:
                        keep[idx[stop[0] + 1:]] = False
            else:
                # later trials missing more often (missing depends on observed trial index)
                p = frac * 2 * (d["selection_index"] / d["selection_index"].max())
                keep = r2.random(len(d)) >= p
            dk = d[keep]
            est = dk.groupby("participant")["movement_time_ms"].mean()
            est_s = dk.groupby("participant")["success"].mean()
            j = pd.concat([full, est], axis=1, keys=["full", "est"]).dropna()
            js = pd.concat([full_succ, est_s], axis=1, keys=["full", "est"]).dropna()
            rows.append({"missing_frac_target": frac, "mechanism": mech,
                         "actual_missing_frac": 1 - len(dk) / len(d),
                         "participants_with_data": len(j),
                         "mt_bias_ms": float((j.est - j.full).mean()),
                         "mt_rmse_ms": float(np.sqrt(((j.est - j.full) ** 2).mean())),
                         "success_bias": float((js.est - js.full).mean()),
                         "mt_rank_corr_with_full": float(j.corr(method="spearman").iloc[0, 1])})
    res = pd.DataFrame(rows)
    save("N_missing_data", "results", res)
    plt = style()
    fig, axes = plt.subplots(1, 2, figsize=(8, 3))
    for i, mech in enumerate(res.mechanism.unique()):
        d = res[res.mechanism == mech]
        axes[0].plot(d.actual_missing_frac, d.mt_bias_ms, marker="o", color=PALETTE[i], label=mech)
        axes[1].plot(d.actual_missing_frac, d.success_bias, marker="o", color=PALETTE[i], label=mech)
    axes[0].set_ylabel("bias in mean movement time (ms)")
    axes[1].set_ylabel("bias in success rate")
    for ax in axes:
        ax.set_xlabel("fraction of trials missing")
        ax.axhline(0, color="#666666", lw=0.8)
    axes[0].legend(fontsize=7)
    fig.suptitle("Incomplete sessions: complete-case bias by missingness mechanism (simulation)")
    fig.tight_layout()
    fig.savefig(RESULTS / "N_missing_data" / "missing_bias.png")
    plt.close(fig)
    summ = {"design": f"{n} virtual participants x 24 scored ISO selections (bci_moderate)", "results": res.to_dict("records")}
    write_summary("N_missing_data", summ)
    return summ


# --------------------------------------------------------------------------- H: adaptive vs fixed
def adaptive_grid(mod, users, n, rng, degradation, n_trials=40, sizes=None, cell=120,
                  rows=4, cols=6, start_size=100.0, step=1.4, min_size=6.0, max_size=116.0):
    """2-down/1-up staircase on item size (converges near 70.7% correct, Levitt 1971 [PK]).
    Returns per-participant threshold size (geometric mean of last 6 reversal sizes) and the
    trial log. Item spacing (cell) is fixed so only target size varies."""
    sim = Simulation(mod.user_model, users, degradation, n, rng)
    dwell = mod.dwell_ms if mod.selection == "dwell" else None
    base = grid_items(rows, cols, cell, 100)
    centers = np.array([[b["x"], b["y"]] for b in base])
    K = len(base)
    size = np.full(n, start_size)
    streak = np.zeros(n, int)
    last_dir = np.zeros(n, int)
    reversals = [[] for _ in range(n)]
    log = []
    for k in range(n_trials):
        cue = rng.integers(0, K, n)
        order = np.array([np.r_[c, np.delete(np.arange(K), c)] for c in cue])
        its = np.zeros((n, K, 4))
        its[:, :, :2] = centers[order]
        its[:, :, 2:] = (size / 2)[:, None, None]
        # same empty-click rule as the fixed grid (run_grid): empty-space clicks do not end a trial
        st = sim.acquire(its, dwell_ms=dwell, max_ms=10000, end_on_empty=False)
        ok = st.sel_item == 0
        log.append(pd.DataFrame({"participant": np.arange(n), "trial": k, "size": size.copy(),
                                 "success": ok, "time_ms": np.where(st.timed_out, 10000, st.sel_t)}))
        new_dir = np.zeros(n, int)
        streak = np.where(ok, streak + 1, 0)
        harder = ok & (streak >= 2)
        easier = ~ok
        new_dir[harder] = -1
        new_dir[easier] = +1
        streak[harder] = 0
        for i in np.nonzero((new_dir != 0) & (last_dir != 0) & (new_dir != last_dir))[0]:
            reversals[i].append(size[i])
        last_dir = np.where(new_dir != 0, new_dir, last_dir)
        size = np.where(harder, size / step, np.where(easier, size * step, size))
        size = np.clip(size, min_size, max_size)
    thr = np.array([np.exp(np.mean(np.log(r[-6:]))) if len(r) >= 2 else size[i]
                    for i, r in enumerate(reversals)])
    return thr, pd.concat(log), np.array([len(r) for r in reversals])


def exp_H(n: int = 60, **_):
    """Fixed-difficulty grid accuracy vs adaptive size threshold across a wide ability range."""
    noise_levels = [0, 1, 2, 4, 6, 8]
    rows = []
    for nl in noise_levels:
        deg = BASE.with_(white_noise=30 * nl, correlated_noise=40 * nl)
        mod = MODALITIES["bci_cursor_good_sim"]
        prng = np.random.default_rng(seed_for("H", "pop"))
        users, z = sample_population(mod.user, n, prng, ability_sd=0.3)
        for size_label, item in [("fixed_large_100px", 100), ("fixed_small_40px", 40)]:
            rng = np.random.default_rng(seed_for("H", nl, size_label))
            gd = T.run_grid(mod, users, n, rng, n_trials=40, item=item, max_ms=10000,
                            degradation=deg)
            acc = gd.groupby("participant")["success"].mean().to_numpy()
            rows.append(pd.DataFrame({"noise": nl, "design": size_label, "participant": np.arange(n),
                                      "score": acc, "latent": z}))
        rng = np.random.default_rng(seed_for("H", nl, "adaptive"))
        thr, log, nrev = adaptive_grid(mod, users, n, rng, deg, n_trials=40)
        rows.append(pd.DataFrame({"noise": nl, "design": "adaptive_size_threshold",
                                  "participant": np.arange(n), "score": -np.log(thr), "latent": z,
                                  "reversals": nrev}))
    df = pd.concat(rows, ignore_index=True)
    save("H_adaptive", "data", df)
    from scipy.stats import spearmanr
    res = []
    for des, d in df.groupby("design"):
        fl = ce = np.nan
        if des.startswith("fixed"):
            fl = float(np.mean(d.score <= 0.0 + 1e-9))
            ce = float(np.mean(d.score >= 1 - 1e-9))
        else:
            fl = float(np.mean(d.score <= -np.log(116) + 1e-6))
            ce = float(np.mean(d.score >= -np.log(6) - 1e-6))
        # discrimination of device level across the full range and within-level person ranking
        rho_dev = spearmanr(d.noise, d.score).statistic
        within = np.nanmean([spearmanr(g.latent, g.score).statistic for _, g in d.groupby("noise")
                             if g.score.nunique() > 1])
        adj = []
        from .analysis import auc
        for a, b in zip(noise_levels[:-1], noise_levels[1:]):
            adj.append(1 - auc(d[d.noise == a].score.to_numpy(), d[d.noise == b].score.to_numpy()))
        res.append({"design": des, "floor_frac": fl, "ceiling_frac": ce, "rho_with_device_noise": rho_dev,
                    "within_level_rho_with_latent_ability": within,
                    "min_adjacent_auc": float(np.nanmin(adj)), "mean_adjacent_auc": float(np.nanmean(adj))})
    res = pd.DataFrame(res)
    save("H_adaptive", "comparison", res)
    plt = style()
    fig, axes = plt.subplots(1, 3, figsize=(10, 3))
    for ax, des in zip(axes, ["fixed_large_100px", "fixed_small_40px", "adaptive_size_threshold"]):
        d = df[df.design == des]
        parts = [d[d.noise == nl].score.to_numpy() for nl in noise_levels]
        ax.boxplot(parts, tick_labels=[str(x) for x in noise_levels], widths=0.5)
        ax.set_title(des.replace("_", " "))
        ax.set_xlabel("noise scale")
    axes[0].set_ylabel("accuracy")
    axes[2].set_ylabel("-log(threshold size px)")
    fig.suptitle("Fixed vs adaptive difficulty across a wide range of simulated control quality")
    fig.tight_layout()
    fig.savefig(RESULTS / "H_adaptive" / "fixed_vs_adaptive.png")
    plt.close(fig)
    summ = {"design": "6 noise levels x 60 virtual participants; fixed 100 px and 40 px grids (40 trials) vs 40-trial 2-down/1-up size staircase (step x1.4, 6-116 px)",
            "results": res.to_dict("records"),
            "caveat": "Adaptive scores are on a different scale; comparability across battery versions must be maintained by fixing the staircase rule and version."}
    write_summary("H_adaptive", summ)
    return summ


# --------------------------------------------------------------------------- P: reproducibility
def exp_P(**_):
    """Re-run one condition in-process and in a 2-process pool; results must be bit-identical."""
    job = {"cond": "P:repro", "rep": 0, "modality": "bci_cursor_moderate_sim", "n": 20,
           "kw": {"tasks": ("iso", "grid", "typing")}, "pop_seed": 9}
    a = run_grid_jobs("P_reproducibility", [job], processes=1)
    b = run_grid_jobs("P_reproducibility", [job, dict(job, cond="P:other")], processes=2)
    b = b[b.cond == "P:repro"].reset_index(drop=True)
    cols = [c for c in a.columns if c != "runtime_s"]

    def h(df):
        return hashlib.sha256(pd.util.hash_pandas_object(df[cols].round(12), index=False).values.tobytes()).hexdigest()

    ha, hb = h(a), h(b)
    other = run_grid_jobs("P_reproducibility", [dict(job, rep=1)], processes=1)
    hc = h(other)
    summ = {"hash_in_process": ha, "hash_in_pool": hb, "identical": ha == hb,
            "different_seed_differs": ha != hc}
    write_summary("P_reproducibility", summ)
    return summ


EXPERIMENTS = {**{k: (lambda k=k: (lambda **kw: run_sweep(k, **kw)))() for k in SWEEPS},
               "I_test_retest": exp_I, "K_responsiveness": exp_K, "L_cross_modality": exp_L,
               "M_user_variability": exp_M, "N_missing_data": exp_N, "H_adaptive": exp_H,
               "P_reproducibility": exp_P, "G_metric_comparison": exp_G}


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("experiments", nargs="*")
    ap.add_argument("--processes", type=int, default=4)
    ap.add_argument("--n", type=int, default=None)
    a = ap.parse_args(argv)
    ids = a.experiments or list(EXPERIMENTS)
    for e in ids:
        t = time.time()
        kw = {"processes": a.processes}
        if a.n:
            kw["n"] = a.n
        print(f"[{time.strftime('%H:%M:%S')}] {e} ...", flush=True)
        EXPERIMENTS[e](**kw)
        print(f"[{time.strftime('%H:%M:%S')}] {e} done in {time.time() - t:.0f}s", flush=True)


if __name__ == "__main__":
    main()
