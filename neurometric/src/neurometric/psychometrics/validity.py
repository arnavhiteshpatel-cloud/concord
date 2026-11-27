r"""Construct validity, floor/ceiling effects and responsiveness.

Known-groups validity, convergent/divergent validity (hypothesis testing in the COSMIN sense),
floor/ceiling effects, and responsiveness indices. :func:`mcid_note` explains why no function
here produces a *minimal clinically important difference*.

References
----------
* DeLong ER, DeLong DM, Clarke-Pearson DL (1988). Comparing the areas under two or more
  correlated ROC curves: a nonparametric approach. Biometrics 44(3):837-845. [PK]
* Hanley JA, McNeil BJ (1982). The meaning and use of the area under a ROC curve. Radiology
  143:29-36. [PK]
* Fieller EC, Hartley HO, Pearson ES (1957). Tests for rank correlation coefficients I.
  Biometrika 44:470-481. [PK]  (Spearman Fisher-z SE = sqrt(1.06/(n-3)))
* Bonett DG, Wright TA (2000). Sample size requirements for estimating Pearson, Kendall and
  Spearman correlations. Psychometrika 65:23-28. [PK]
* Terwee CB et al. (2007). Quality criteria were proposed for measurement properties of health
  status questionnaires. J Clin Epidemiol 60(1):34-42. [PK]  (floor/ceiling > 15 %)
* Husted JA, Cook RJ, Farewell VT, Gladman DD (2000). Methods for assessing responsiveness: a
  critical review and recommendations. J Clin Epidemiol 53:459-468. [PK]
* Guyatt G, Walter S, Norman G (1987). Measuring change over time: assessing the usefulness of
  evaluative instruments. J Chronic Dis 40(2):171-178. [PK]
* Kazis LE, Anderson JJ, Meenan RF (1989). Effect sizes for interpreting changes in health
  status. Med Care 27(3 Suppl):S178-S189. [PK]
* Liang MH (2000). Longitudinal construct validity: establishment of clinical meaning in
  patient evaluative instruments. Med Care 38(9 Suppl):II84-II90. [PK]
* Revicki D, Hays RD, Cella D, Sloan J (2008). Recommended methods for determining
  responsiveness and minimally important differences for patient-reported outcomes. J Clin
  Epidemiol 61(2):102-109. [PK]
* de Vet HCW, Terwee CB (2010). The minimal detectable change should not replace the minimal
  important difference. J Clin Epidemiol 63(7):804-805. [PK]

[PK] = cited from prior knowledge, details not re-verified.
"""
from __future__ import annotations


import numpy as np
from scipy import stats

from ._util import as_1d, paired_arrays
from .effects import bootstrap_ci, hedges_g

__all__ = ["auc", "auc_delong", "auc_bootstrap", "known_groups", "correlation_ci",
           "convergent_divergent", "floor_ceiling", "responsiveness", "mcid_note",
           "distribution_based_change_estimates", "DISTRIBUTION_LABEL"]

#: Label attached to every distribution-based change threshold.
DISTRIBUTION_LABEL = "distribution-based estimate, not an MCID"


# ----------------------------------------------------------------------------------- AUC
def auc(pos, neg) -> float:
    r"""Area under the ROC curve = Mann–Whitney probability
    :math:`P(X_{pos}>X_{neg})+\tfrac12P(X_{pos}=X_{neg})` (higher scores indicate 'positive')."""
    pos, neg = as_1d(pos), np.sort(as_1d(neg))
    below = np.searchsorted(neg, pos, side="left")
    ties = np.searchsorted(neg, pos, side="right") - below
    return float((below.sum() + 0.5 * ties.sum()) / (len(pos) * len(neg)))


def auc_delong(pos, neg, *, alpha: float = 0.05) -> dict:
    r"""AUC with DeLong et al. (1988) variance and Wald CI (clipped to [0, 1]).

    Structural components :math:`V_{10}(X_i)=\frac1{n}\sum_j\psi(X_i,Y_j)`,
    :math:`V_{01}(Y_j)=\frac1m\sum_i\psi(X_i,Y_j)` with :math:`\psi=1,\tfrac12,0` for
    :math:`X>Y`, :math:`X=Y`, :math:`X<Y`;
    :math:`\widehat{Var}(AUC)=S_{10}/m+S_{01}/n` with :math:`S` the sample variances (ddof=1)
    of the components.
    """
    x, y = as_1d(pos), as_1d(neg)
    m, n = len(x), len(y)
    if m < 2 or n < 2:
        raise ValueError("each group needs >= 2 observations")
    ys = np.sort(y)
    xs = np.sort(x)
    v10 = (np.searchsorted(ys, x, "left") + 0.5 * (np.searchsorted(ys, x, "right")
                                                    - np.searchsorted(ys, x, "left"))) / n
    v01 = ((m - np.searchsorted(xs, y, "right"))
           + 0.5 * (np.searchsorted(xs, y, "right") - np.searchsorted(xs, y, "left"))) / m
    a = v10.mean()
    var = v10.var(ddof=1) / m + v01.var(ddof=1) / n
    se = np.sqrt(var)
    q = stats.norm.ppf(1 - alpha / 2)
    return {"auc": float(a), "se": float(se), "ci_low": float(max(0.0, a - q * se)),
            "ci_high": float(min(1.0, a + q * se)), "n_pos": m, "n_neg": n, "alpha": alpha,
            "method": "Mann-Whitney AUC; DeLong (1988) variance; Wald CI clipped to [0,1]"}


def auc_bootstrap(pos, neg, *, alpha: float = 0.05, n_boot: int = 2000, seed: int = 0,
                  method: str = "percentile") -> dict:
    """AUC with a seeded stratified (per-group) bootstrap CI (see :func:`effects.bootstrap_ci`)."""
    r = bootstrap_ci(auc, as_1d(pos), as_1d(neg), n_boot=n_boot, alpha=alpha, seed=seed,
                     method=method)
    return {"auc": r["estimate"], "se": r["se_boot"], "ci_low": r["ci_low"],
            "ci_high": r["ci_high"], "n_pos": len(as_1d(pos)), "n_neg": len(as_1d(neg)),
            "alpha": alpha, "method": "Mann-Whitney AUC; " + r["method"] + f", B={n_boot}, "
                                      f"seed={seed}"}


# --------------------------------------------------------------------------- known groups
def known_groups(x, y, *, alpha: float = 0.05, auc_ci: str = "delong", n_boot: int = 2000,
                 seed: int = 0, expected: str | None = None) -> dict:
    r"""Known-groups validity: does the score separate groups expected to differ?

    ``x`` = group expected to score higher (if ``expected='x>y'``), ``y`` = comparison group.
    Returns Welch's t-test (unequal variances), the Mann–Whitney U test (two-sided, scipy's
    exact/asymptotic choice), Hedges' g with noncentral-t CI, and the AUC = P(X > Y) with a
    DeLong (``auc_ci='delong'``) or bootstrap (``'bootstrap'``) CI. If ``expected`` is given
    (``'x>y'`` or ``'x<y'``), ``hypothesis_supported`` reports whether the Welch test is
    significant in that direction.
    """
    x, y = as_1d(x), as_1d(y)
    wt = stats.ttest_ind(x, y, equal_var=False)
    wci = wt.confidence_interval(1 - alpha)
    mw = stats.mannwhitneyu(x, y, alternative="two-sided")
    g = hedges_g(x, y, alpha=alpha)
    a = auc_delong(x, y, alpha=alpha) if auc_ci == "delong" else \
        auc_bootstrap(x, y, alpha=alpha, n_boot=n_boot, seed=seed)
    supported = None
    if expected is not None:
        sign = {"x>y": 1, "x<y": -1}[expected]
        supported = bool(wt.pvalue < alpha and np.sign(x.mean() - y.mean()) == sign)
    warn = []
    if min(len(x), len(y)) < 10:
        warn.append("fewer than 10 per group: CIs are wide and normal approximations crude")
    return {
        "n1": len(x), "n2": len(y), "mean1": float(x.mean()), "mean2": float(y.mean()),
        "sd1": float(x.std(ddof=1)), "sd2": float(y.std(ddof=1)),
        "welch_t": {"t": float(wt.statistic), "df": float(wt.df), "p": float(wt.pvalue),
                    "mean_diff": float(x.mean() - y.mean()),
                    "ci": [float(wci.low), float(wci.high)]},
        "mann_whitney": {"U": float(mw.statistic), "p": float(mw.pvalue)},
        "hedges_g": g, "auc": a, "expected": expected, "hypothesis_supported": supported,
        "alpha": alpha,
        "method": "Welch t; Mann-Whitney U; Hedges g (noncentral-t CI); AUC "
                  f"({auc_ci} CI)",
        "assumptions": ["independent groups", "Welch t: approx. normal means (CLT)",
                        "groups defined independently of the score being validated"],
        "warnings": warn,
    }


# ---------------------------------------------------------------------- correlations / CIs
def correlation_ci(x, y, *, method: str = "pearson", alpha: float = 0.05,
                   spearman_se: str = "fieller") -> dict:
    r"""Pearson or Spearman correlation with a Fisher-z confidence interval.

    :math:`z=\tanh^{-1}r`, CI :math:`\tanh(z\pm z_{1-\alpha/2}SE)` with
    :math:`SE=1/\sqrt{n-3}` (Pearson). For Spearman, ``spearman_se='fieller'`` uses
    :math:`\sqrt{1.06/(n-3)}` (Fieller et al. 1957), ``'bonett_wright'`` uses
    :math:`\sqrt{(1+r_s^2/2)/(n-3)}` (Bonett & Wright 2000).
    """
    x, y, n_drop = paired_arrays(x, y)
    n = len(x)
    if n < 4:
        raise ValueError("need at least 4 complete pairs")
    if method == "pearson":
        res = stats.pearsonr(x, y)
        r, p = res.statistic, res.pvalue
        se = 1 / np.sqrt(n - 3)
    elif method == "spearman":
        res = stats.spearmanr(x, y)
        r, p = res.statistic, res.pvalue
        se = {"fieller": np.sqrt(1.06 / (n - 3)),
              "bonett_wright": np.sqrt((1 + r ** 2 / 2) / (n - 3))}[spearman_se]
    else:
        raise ValueError("method must be 'pearson' or 'spearman'")
    q = stats.norm.ppf(1 - alpha / 2)
    z = np.arctanh(np.clip(r, -1 + 1e-15, 1 - 1e-15))
    return {"r": float(r), "p": float(p), "ci_low": float(np.tanh(z - q * se)),
            "ci_high": float(np.tanh(z + q * se)), "n": n, "n_dropped": n_drop,
            "method": f"{method} correlation; Fisher-z CI"
                      + (f" (SE: {spearman_se})" if method == "spearman" else ""),
            "alpha": alpha}


def convergent_divergent(score, convergent: dict | None = None,
                         divergent: dict | None = None, *, method: str = "spearman",
                         alpha: float = 0.05, convergent_min: float = 0.5,
                         divergent_max: float = 0.3) -> dict:
    r"""Hypothesis-testing construct validity.

    ``convergent``/``divergent`` map a name to a comparison measure (same length as ``score``).
    A convergent hypothesis is supported if :math:`|r|\ge` ``convergent_min``; a divergent one if
    :math:`|r|<` ``divergent_max``. The default thresholds (0.5 / 0.3) are conventions
    (COSMIN-style) and should be pre-registered per measure with the expected sign. [PK]
    """
    rows = []
    for kind, dct in (("convergent", convergent or {}), ("divergent", divergent or {})):
        for name, other in dct.items():
            c = correlation_ci(score, other, method=method, alpha=alpha)
            ok = abs(c["r"]) >= convergent_min if kind == "convergent" \
                else abs(c["r"]) < divergent_max
            rows.append({"measure": name, "kind": kind, **c, "hypothesis_supported": bool(ok)})
    return {"results": rows, "thresholds": {"convergent_min_abs_r": convergent_min,
                                            "divergent_max_abs_r": divergent_max},
            "method": f"{method} correlations with Fisher-z CIs vs pre-specified thresholds",
            "assumptions": ["thresholds and expected directions pre-specified"],
            "warnings": []}


# --------------------------------------------------------------------------- floor/ceiling
def floor_ceiling(x, *, min_possible: float | None = None, max_possible: float | None = None,
                  threshold: float = 0.15, tol: float = 0.0) -> dict:
    r"""Proportion of observations at the scale minimum (floor) and maximum (ceiling).

    Uses the theoretical bounds if given, else the observed min/max (then the result only tells
    you how many share the extreme value — say so in reporting). A value counts as "at" a bound
    if within ``tol``. Flags proportions > ``threshold`` (15 %, Terwee et al. 2007).
    """
    x = as_1d(x)
    lo = float(np.min(x)) if min_possible is None else float(min_possible)
    hi = float(np.max(x)) if max_possible is None else float(max_possible)
    pf = float(np.mean(x <= lo + tol))
    pc = float(np.mean(x >= hi - tol))
    warn = []
    if min_possible is None or max_possible is None:
        warn.append("theoretical bounds not supplied: observed min/max used")
    return {"floor_value": lo, "ceiling_value": hi, "prop_floor": pf, "prop_ceiling": pc,
            "floor_flag": pf > threshold, "ceiling_flag": pc > threshold,
            "threshold": threshold, "n": int(len(x)),
            "method": "proportion at bound; flag > threshold (Terwee et al. 2007)",
            "assumptions": ["bounds are the true scale limits"], "warnings": warn}


# ---------------------------------------------------------------------------- responsiveness
def responsiveness(baseline, follow_up, *, stable_baseline=None, stable_follow_up=None,
                   mdc: float | None = None, improvement: str = "increase",
                   alpha: float = 0.05) -> dict:
    r"""Responsiveness indices for a group expected to change.

    With change :math:`c=\text{follow\_up}-\text{baseline}` in the changed group:

    * standardized response mean :math:`SRM=\bar c/s_c` (Liang 2000);
    * effect size (Kazis 1989) :math:`ES=\bar c/s_{baseline}`;
    * paired Cohen :math:`d_z` CI (= SRM with noncentral-t CI);
    * Guyatt responsiveness index :math:`RI=\bar c/s_{c,stable}` — **requires** a stable group
      (``stable_baseline``/``stable_follow_up``); otherwise ``None`` with a warning;
    * AUC for distinguishing changed vs stable subjects by their change scores (DeLong CI);
    * proportion of the changed group whose change exceeds ``mdc`` (in the direction of
      ``improvement`` and in absolute value), plus the same in the stable group (false-positive
      rate of the MDC rule).

    None of these is an MCID; see :func:`mcid_note`.
    """
    from .effects import cohens_dz

    b, f, n_drop = paired_arrays(baseline, follow_up)
    c = f - b
    sign = 1 if improvement == "increase" else -1
    out = {"n_changed": int(len(c)), "n_dropped": n_drop,
           "mean_change": float(c.mean()), "sd_change": float(c.std(ddof=1)),
           "srm": float(c.mean() / c.std(ddof=1)),
           "effect_size_kazis": float(c.mean() / b.std(ddof=1)),
           "dz_ci": cohens_dz(f, b, alpha=alpha), "guyatt_ri": None, "auc_changed_vs_stable":
               None, "prop_exceeding_mdc": None, "mdc": mdc,
           "method": "SRM, Kazis ES, Guyatt RI (stable-group SD), AUC of change scores",
           "assumptions": ["the changed group truly changed (external anchor)",
                           "stable group truly stable"],
           "warnings": []}
    if stable_baseline is not None and stable_follow_up is not None:
        sb, sf, _ = paired_arrays(stable_baseline, stable_follow_up)
        sc = sf - sb
        out["n_stable"] = int(len(sc))
        out["sd_change_stable"] = float(sc.std(ddof=1))
        out["guyatt_ri"] = float(c.mean() / sc.std(ddof=1))
        out["auc_changed_vs_stable"] = auc_delong(sign * c, sign * sc, alpha=alpha)
        if mdc is not None:
            out["prop_stable_exceeding_mdc"] = float(np.mean(sign * sc > mdc))
    else:
        out["warnings"].append("Guyatt responsiveness index and changed-vs-stable AUC need a "
                               "stable (unchanged) group; not computed")
    if mdc is not None:
        out["prop_exceeding_mdc"] = float(np.mean(sign * c > mdc))
        out["prop_exceeding_mdc_abs"] = float(np.mean(np.abs(c) > mdc))
    return out


# ------------------------------------------------------------------------------------- MCID
def mcid_note() -> str:
    """Explain why NeuroMetric does not compute a minimal clinically important difference."""
    return (
        "MCID / MID cannot be computed by this software. A minimal clinically important "
        "difference is the smallest change that users, clinicians or caregivers judge to be "
        "important; establishing it requires ANCHOR-BASED evidence from real participants - e.g. "
        "a global rating of change, a patient-reported or clinician-rated functional anchor, or "
        "achievement of a meaningful real-world goal - linked to observed score changes "
        "(Revicki et al. 2008; de Vet & Terwee 2010) [PK]. It cannot be derived from simulated "
        "users, from the score distribution alone, or from reliability statistics: the minimal "
        "detectable change (MDC) says what change exceeds measurement noise (statistically "
        "detectable), not what change matters (clinically important). Distribution-based "
        "quantities (0.5 SD, 1 SEM, MDC) are reported only as '" + DISTRIBUTION_LABEL + "' and "
        "may be used as supportive evidence to triangulate anchor-based estimates in a future "
        "participant study."
    )


def distribution_based_change_estimates(baseline_sd: float, sem: float | None = None) -> dict:
    """Distribution-based change thresholds (0.2 SD, 0.5 SD, 1 SEM, 1.96*sqrt(2)*SEM).

    Every entry is labelled ``DISTRIBUTION_LABEL`` ('distribution-based estimate, not an
    MCID'). See :func:`mcid_note`.
    """
    est = {"0.2_sd": 0.2 * baseline_sd, "0.5_sd": 0.5 * baseline_sd}
    if sem is not None:
        est["1_sem"] = float(sem)
        est["mdc95"] = float(1.959963984540054 * np.sqrt(2) * sem)
    return {"estimates": {k: {"value": float(v), "label": DISTRIBUTION_LABEL}
                          for k, v in est.items()},
            "label": DISTRIBUTION_LABEL, "note": mcid_note()}
