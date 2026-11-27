"""Measurement-chain engine: link observations across levels without over-claiming.

Levels (the iBCI-CC "shared measurement chain", extended):
  L1 device performance  -> L2 task (functional capacity) -> L3 real-world activity
  -> L4 independence -> L5 care-partner assistance -> L6 participation / quality of life

Observations are stored long-form: (participant, time, level, variable, value, source,
provenance). Analysis functions return estimates with the *type* of claim they support:
'association' always; 'within-person association' when the within/between decomposition is used;
never 'causal effect'. Mediation output is an associational decomposition that has a causal
reading only under the listed (untestable) assumptions.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import numpy as np
import pandas as pd
from scipy import stats

LEVELS = {
    "L1": "device performance", "L2": "functional task performance",
    "L3": "real-world activity", "L4": "independence",
    "L5": "care-partner assistance", "L6": "participation / quality of life",
}


@dataclass
class ChainResult:
    estimate: float
    ci: tuple
    n_participants: int
    n_observations: int
    method: str
    claim_type: str
    assumptions: list = field(default_factory=list)
    warnings: list = field(default_factory=list)
    extra: dict = field(default_factory=dict)


def wide(obs: pd.DataFrame) -> pd.DataFrame:
    """Long observations -> participant x time table with one column per level:variable."""
    o = obs.copy()
    o["col"] = o["level"] + ":" + o["variable"]
    return o.pivot_table(index=["participant", "time"], columns="col", values="value").reset_index()


def within_between(df: pd.DataFrame, x: str, y: str, subject: str = "participant",
                   time: str = "time") -> dict[str, ChainResult]:
    """Decompose an x-y association into a between-person part (person means) and a
    within-person part (deviations from person means, mixed model with random intercepts).

    The pooled correlation mixes both and can even have the opposite sign of the within-person
    association (ecological fallacy); both are reported separately.
    """
    import statsmodels.formula.api as smf
    d = df[[subject, time, x, y]].dropna().copy()
    d.columns = ["s", "t", "x", "y"]
    out = {}
    pm = d.groupby("s")[["x", "y"]].mean()
    if len(pm) >= 4:
        r, p = stats.pearsonr(pm.x, pm.y)
        z = np.arctanh(np.clip(r, -0.999999, 0.999999))
        se = 1 / np.sqrt(len(pm) - 3)
        out["between"] = ChainResult(float(r), (float(np.tanh(z - 1.96 * se)), float(np.tanh(z + 1.96 * se))),
                                     len(pm), len(d), "Pearson r of person means (Fisher z CI)",
                                     "between-person association",
                                     ["linear", "independent persons"],
                                     ["confounded by any stable person characteristic (ability, care setting)"])
    d["xm"] = d.groupby("s")["x"].transform("mean")
    d["xw"] = d["x"] - d["xm"]
    d["tc"] = d["t"] - d["t"].mean()
    warns = ["within-person association can still be confounded by time-varying factors "
             "(practice, fatigue, disease progression, care changes)"]
    try:
        fit = smf.mixedlm("y ~ xw + xm + tc", d, groups=d["s"]).fit(reml=True)
        b = float(fit.params["xw"])
        ci = tuple(float(v) for v in fit.conf_int().loc["xw"])
        out["within"] = ChainResult(b, ci, d.s.nunique(), len(d),
                                    "linear mixed model y ~ x_within + x_between + time, random intercept",
                                    "within-person association (slope per unit x)",
                                    ["linearity", "random-intercept structure", "MAR missingness"],
                                    warns, {"between_slope": float(fit.params["xm"]),
                                            "time_slope": float(fit.params["tc"])})
    except Exception as e:  # pragma: no cover - reported, not hidden
        out["within"] = ChainResult(np.nan, (np.nan, np.nan), d.s.nunique(), len(d), "mixedlm failed",
                                    "none", [], [f"model failed: {e}"])
    r, _ = stats.pearsonr(d.x, d.y) if len(d) > 3 else (np.nan, None)
    out["pooled"] = ChainResult(float(r), (np.nan, np.nan), d.s.nunique(), len(d),
                                "pooled Pearson r (ignores clustering)", "descriptive only",
                                [], ["ignores repeated measures; do not interpret"])
    return out


def mediation_bootstrap(df: pd.DataFrame, x: str, m: str, y: str, covariates=(), n_boot=2000,
                        seed=0) -> ChainResult:
    """Product-of-coefficients indirect effect a*b with percentile bootstrap CI (person-level
    data). Returned as an ASSOCIATIONAL decomposition."""
    import statsmodels.api as sm
    d = df[[x, m, y, *covariates]].dropna()
    rng = np.random.default_rng(seed)

    def ab(dd):
        X1 = sm.add_constant(dd[[x, *covariates]])
        a = sm.OLS(dd[m], X1).fit().params[x]
        X2 = sm.add_constant(dd[[x, m, *covariates]])
        b = sm.OLS(dd[y], X2).fit().params[m]
        return a * b

    est = ab(d)
    boots = [ab(d.iloc[rng.integers(0, len(d), len(d))]) for _ in range(n_boot)]
    lo, hi = np.percentile(boots, [2.5, 97.5])
    return ChainResult(float(est), (float(lo), float(hi)), len(d), len(d),
                       "product of coefficients, percentile bootstrap",
                       "associational decomposition (NOT a causal mediation effect)",
                       ["no unmeasured x-m, m-y, x-y confounding", "no m-y confounder affected by x",
                        "correct temporal order x -> m -> y", "linearity, no x*m interaction"],
                       ["assumptions are untestable from observational data; report as hypothesis-generating"])


def e_value_rr(rr: float, lo: Optional[float] = None) -> dict:
    """E-value (VanderWeele & Ding 2017) for a risk ratio and its CI limit closest to 1."""
    def ev(r):
        r = 1 / r if r < 1 else r
        return float(r + np.sqrt(r * (r - 1)))
    out = {"e_value_point": ev(rr)}
    if lo is not None:
        out["e_value_ci"] = 1.0 if (lo <= 1 <= rr or rr <= 1 <= lo) else ev(lo)
    return out


def synthetic_chain(n=60, waves=6, seed=0, within_slope=0.5, confound=1.0) -> pd.DataFrame:
    """SYNTHETIC longitudinal chain data with KNOWN structure (for verification only).

    A stable person factor u raises both task performance (L2) and lowers assistance minutes (L5)
    between persons (confounding); within persons, a device change shifts L2 and L5 responds with
    slope ``within_slope`` (negative = less assistance). Never use as evidence.
    """
    rng = np.random.default_rng(seed)
    u = rng.standard_normal(n)
    rows = []
    for i in range(n):
        dev = np.cumsum(rng.normal(0, 0.5, waves))
        for t in range(waves):
            l1 = dev[t] + rng.normal(0, 0.3)
            l2 = 0.8 * l1 + confound * u[i] + rng.normal(0, 0.3)
            l3 = 0.6 * l2 + rng.normal(0, 0.5)
            l5 = 60 - 10 * (within_slope * (l2 - confound * u[i]) + 2.0 * confound * u[i]) + rng.normal(0, 5)
            for lvl, var, val in [("L1", "decoder_quality", l1), ("L2", "grid_bitrate", l2),
                                  ("L3", "active_minutes", l3), ("L5", "assist_minutes", l5)]:
                rows.append({"participant": f"SYN-{i:03d}", "time": t, "level": lvl,
                             "variable": var, "value": val, "source": "synthetic",
                             "synthetic": True})
    return pd.DataFrame(rows)
