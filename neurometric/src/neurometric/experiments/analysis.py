"""Metric-property analysis for simulation sweeps, and the figure style."""
from __future__ import annotations

from typing import Optional

import numpy as np
import pandas as pd
from scipy import stats

from .core import METRIC_BOUNDS, METRIC_DIRECTION

# Reference categorical palette (light mode), fixed order, never cycled.
PALETTE = ["#257de0", "#f47230", "#00b894", "#f2a600", "#ee7fac", "#008a17", "#6a4ce2", "#ec4647"]
TEXT, TEXT2, GRID = "#191919", "#666666", "#e6e6e6"


def style():
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    plt.rcParams.update({
        "figure.dpi": 150, "savefig.dpi": 150, "font.size": 9, "axes.titlesize": 10,
        "axes.edgecolor": TEXT2, "axes.labelcolor": TEXT, "xtick.color": TEXT2,
        "ytick.color": TEXT2, "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.6,
        "axes.spines.top": False, "axes.spines.right": False, "lines.linewidth": 2,
        "lines.markersize": 5, "legend.frameon": False, "axes.prop_cycle":
            matplotlib.cycler(color=PALETTE)})
    return plt


def auc(a: np.ndarray, b: np.ndarray) -> float:
    """P(b > a) + 0.5 P(tie) (Mann-Whitney AUC)."""
    a, b = a[~np.isnan(a)], b[~np.isnan(b)]
    if a.size == 0 or b.size == 0:
        return np.nan
    u = stats.mannwhitneyu(b, a, alternative="two-sided").statistic
    return float(u / (a.size * b.size))


def sweep_properties(df: pd.DataFrame, level_col: str, metrics: list[str],
                     paired: bool = True) -> pd.DataFrame:
    """Measurement properties of each metric across a monotone degradation sweep.

    For each metric (oriented so that higher = better using METRIC_DIRECTION):
      rho            Spearman correlation of score with degradation level (expected negative)
      monotone_frac  fraction of adjacent level means that move in the expected direction
      d_first        standardised difference baseline vs first degraded level (paired d_z if
                     the same virtual participants are measured at every level)
      min_detect     lowest level at which |d| >= 0.5 vs baseline (NaN if never)
      auc_adjacent   mean AUC separating adjacent levels (0.5 = no discrimination)
      undefined_frac fraction of NaN scores (metric undefined, e.g. no successful trials)
      floor/ceiling  fraction of participants at the natural bound (pooled over levels)
    """
    levels = sorted(df[level_col].unique())
    rows = []
    for m in metrics:
        if m not in df:
            continue
        sgn = METRIC_DIRECTION.get(m, 1)
        x = df[[level_col, "participant", m]].copy()
        x["s"] = sgn * x[m]
        und = float(x["s"].isna().mean())
        ok = x.dropna()
        if ok[level_col].nunique() < 2:
            continue
        rho = stats.spearmanr(ok[level_col], ok["s"]).statistic
        means = [ok.loc[ok[level_col] == L, "s"].mean() for L in levels]
        diffs = np.diff(means)
        mono = float(np.mean(diffs[~np.isnan(diffs)] <= 0)) if len(diffs) else np.nan
        base = x[x[level_col] == levels[0]].set_index("participant")["s"]

        def d_at(L):
            cur = x[x[level_col] == L].set_index("participant")["s"]
            if paired:
                j = pd.concat([base, cur], axis=1, keys=["b", "c"]).dropna()
                if len(j) < 3:
                    return np.nan
                dd = j["c"] - j["b"]
                sd = dd.std(ddof=1)
                return float(dd.mean() / sd) if sd > 0 else (0.0 if dd.mean() == 0 else -np.inf * np.sign(-dd.mean()))
            b, c = base.dropna(), cur.dropna()
            sp = np.sqrt((b.var(ddof=1) + c.var(ddof=1)) / 2)
            return float((c.mean() - b.mean()) / sp) if sp > 0 else np.nan

        ds = [d_at(L) for L in levels[1:]]
        det = next((L for L, d in zip(levels[1:], ds) if np.isfinite(d) and d <= -0.5), np.nan)
        aucs = []
        for L0, L1 in zip(levels[:-1], levels[1:]):
            a = ok.loc[ok[level_col] == L0, "s"].to_numpy()
            b = ok.loc[ok[level_col] == L1, "s"].to_numpy()
            aucs.append(1 - auc(a, b))  # P(better at lower degradation)
        lo, hi = METRIC_BOUNDS.get(m, (None, None))
        raw = df[m].dropna()
        floor = float(np.mean(np.isclose(raw, lo))) if lo is not None and len(raw) else np.nan
        ceil = float(np.mean(np.isclose(raw, hi))) if hi is not None and len(raw) else np.nan
        rows.append({"metric": m, "rho": rho, "monotone_frac": mono,
                     "d_first": ds[0] if ds else np.nan, "min_detect_level": det,
                     "auc_adjacent": float(np.nanmean(aucs)) if aucs else np.nan,
                     "undefined_frac": und, "floor_frac": floor, "ceiling_frac": ceil})
    return pd.DataFrame(rows)


def icc_a1(wide: np.ndarray) -> float:
    """ICC(2,1)/ICC(A,1), two-way random, absolute agreement, single measure (complete cases).
    Kept here (small, dependency-free) for experiment loops; the full implementation with CIs
    lives in neurometric.psychometrics."""
    Y = wide[~np.isnan(wide).any(1)]
    n, k = Y.shape
    if n < 3:
        return np.nan
    gm = Y.mean()
    ssr = k * ((Y.mean(1) - gm) ** 2).sum()
    ssc = n * ((Y.mean(0) - gm) ** 2).sum()
    sst = ((Y - gm) ** 2).sum()
    sse = sst - ssr - ssc
    msr, msc = ssr / (n - 1), ssc / (k - 1)
    mse = sse / ((n - 1) * (k - 1))
    den = msr + (k - 1) * mse + k * (msc - mse) / n
    return float((msr - mse) / den) if den > 0 else np.nan


def plot_sweep(df: pd.DataFrame, level_col: str, metrics: list[str], labels: dict,
               xlabel: str, title: str, path, ncols: int = 4, logx: bool = False):
    plt = style()
    n = len(metrics)
    nrows = int(np.ceil(n / ncols))
    fig, axes = plt.subplots(nrows, ncols, figsize=(ncols * 2.6, nrows * 2.2), squeeze=False)
    groups = df["group"].unique() if "group" in df else [None]
    for ax, m in zip(axes.flat, metrics):
        for gi, g in enumerate(groups):
            d = df if g is None else df[df["group"] == g]
            s = d.groupby(level_col)[m]
            mu, se = s.mean(), s.std() / np.sqrt(s.count())
            ax.errorbar(mu.index, mu.values, yerr=1.96 * se.values, marker="o", capsize=2,
                        color=PALETTE[gi], label=str(g) if g is not None else None, lw=1.6)
        ax.set_title(labels.get(m, m), color=TEXT)
        if logx:
            ax.set_xscale("symlog")
    for ax in list(axes.flat)[n:]:
        ax.axis("off")
    if groups[0] is not None and len(groups) > 1:
        axes.flat[0].legend(fontsize=7)
    fig.suptitle(title + "  (simulation; mean ± 95% CI over virtual participants)", fontsize=10,
                 color=TEXT)
    fig.supxlabel(xlabel, fontsize=9, color=TEXT2)
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)


LABELS = {
    "iso_tp_bps": "Fitts throughput (bit/s)", "iso_error_rate": "ISO error rate",
    "iso_timeout_rate": "ISO timeout rate", "iso_success_rate": "ISO success rate",
    "iso_mt_ms": "Movement time (ms)", "iso_path_efficiency": "Path efficiency",
    "iso_reentries": "Target re-entries", "iso_overshoot_px": "Overshoot (px)",
    "iso_movement_variability_px": "Movement variability (px)",
    "iso_endpoint_error_px": "Endpoint error (px)", "iso_dial_in_ms": "Dial-in time (ms)",
    "iso_submovements": "Submovements", "iso_onset_ms": "Movement onset (ms)",
    "grid_accuracy": "Grid accuracy", "grid_time_ms": "Grid selection time (ms)",
    "grid_bitrate_bps": "Achieved bitrate (bit/s)",
    "false_activations_per_min": "Empty-space selections /min",
    "type_wpm": "Typing WPM", "type_ccpm": "Correct chars /min",
    "type_total_error_rate": "Total error rate", "type_uncorrected_error_rate": "Uncorrected error rate",
    "type_kspc": "Keystrokes per char", "type_correction_burden": "Correction burden",
    "adl_completion_rate": "ADL completion", "adl_time_s": "ADL time (s)",
    "adl_wrong_selections": "ADL wrong selections", "track_rms_px": "Tracking RMS error (px)",
    "track_time_on_target": "Tracking time on target", "track_lag_ms": "Tracking lag (ms)",
}
