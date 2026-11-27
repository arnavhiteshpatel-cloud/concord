r"""Effect sizes, a seeded bootstrap CI helper and multiplicity corrections.

References
----------
* Cohen J (1988). Statistical Power Analysis for the Behavioral Sciences, 2nd ed. [PK]
* Hedges LV, Olkin I (1985). Statistical Methods for Meta-Analysis. Academic Press. [PK]
* Lakens D (2013). Calculating and reporting effect sizes to facilitate cumulative science.
  Front Psychol 4:863. [PK]
* Steiger JH, Fouladi RT (1997). Noncentrality interval estimation and the evaluation of
  statistical models. In: What if there were no significance tests? [PK]
* Cliff N (1993). Dominance statistics: ordinal analyses to answer ordinal questions. Psychol
  Bull 114(3):494-509. [PK]
* Efron B, Tibshirani RJ (1993). An Introduction to the Bootstrap. Chapman & Hall (BCa). [PK]
* Holm S (1979). A simple sequentially rejective multiple test procedure. Scand J Stat 6:65-70.
* Benjamini Y, Hochberg Y (1995). Controlling the false discovery rate. J R Stat Soc B
  57(1):289-300.

[PK] = cited from prior knowledge, details not re-verified.
"""
from __future__ import annotations

from typing import Callable, Sequence

import numpy as np
from scipy import optimize, special, stats

from ._util import as_1d, paired_arrays

__all__ = ["cohens_d", "hedges_g", "hedges_correction", "cohens_dz", "cliffs_delta",
           "bootstrap_ci", "holm", "benjamini_hochberg"]


def hedges_correction(df: float, method: str = "exact") -> float:
    r"""Small-sample bias correction factor :math:`J` for Cohen's d.

    ``exact``: :math:`J=\dfrac{\Gamma(df/2)}{\sqrt{df/2}\,\Gamma((df-1)/2)}` (Hedges 1981);
    ``approx``: :math:`J\approx1-\dfrac{3}{4df-1}` (the formula used by pingouin and most
    software; differs from exact by < 1e-3 for df >= 10).
    """
    if method == "exact":
        return float(np.exp(special.gammaln(df / 2) - special.gammaln((df - 1) / 2))
                     / np.sqrt(df / 2))
    if method == "approx":
        return 1 - 3 / (4 * df - 1)
    raise ValueError("method must be 'exact' or 'approx'")


def _nct_ci_delta(t_obs: float, df: float, scale: float, alpha: float) -> tuple[float, float]:
    """CI for a standardised mean difference by inverting the noncentral t (Steiger & Fouladi).

    Finds noncentrality ``nc`` with P(T <= t_obs | nc) = 1-alpha/2 and alpha/2, then
    delta = nc * scale (scale = sqrt(1/n1+1/n2) for two groups, 1/sqrt(n) for one sample).
    """
    def solve(p):
        f = lambda nc: stats.nct.cdf(t_obs, df, nc) - p
        lo, hi = t_obs - 10 - abs(t_obs), t_obs + 10 + abs(t_obs)
        return optimize.brentq(f, lo, hi, xtol=1e-12)
    return solve(1 - alpha / 2) * scale, solve(alpha / 2) * scale


def cohens_d(x, y) -> float:
    r"""Cohen's d for two independent groups: :math:`(\bar x-\bar y)/s_p`,
    :math:`s_p=\sqrt{\frac{(n_1-1)s_1^2+(n_2-1)s_2^2}{n_1+n_2-2}}`."""
    x, y = as_1d(x), as_1d(y)
    n1, n2 = len(x), len(y)
    sp = np.sqrt(((n1 - 1) * x.var(ddof=1) + (n2 - 1) * y.var(ddof=1)) / (n1 + n2 - 2))
    return float((x.mean() - y.mean()) / sp)


def hedges_g(x, y, *, alpha: float = 0.05, correction: str = "exact",
             ci: str = "noncentral_t") -> dict:
    r"""Hedges' g (bias-corrected Cohen's d) for two independent groups with a CI.

    :math:`g=J(df)\,d`, :math:`df=n_1+n_2-2` (see :func:`hedges_correction`).

    CI methods:

    * ``"noncentral_t"`` (default): exact under normality and equal variances — invert the
      noncentral t distribution of :math:`t=d/\sqrt{1/n_1+1/n_2}` for the noncentrality, then
      multiply the delta bounds by :math:`J`.
    * ``"normal"``: :math:`g\pm z\,SE`, :math:`SE=\sqrt{\frac{n_1+n_2}{n_1n_2}+
      \frac{g^2}{2(n_1+n_2)}}` (Hedges & Olkin 1985; the formula pingouin's ``compute_esci``
      uses).
    """
    x, y = as_1d(x), as_1d(y)
    n1, n2 = len(x), len(y)
    if n1 < 2 or n2 < 2:
        raise ValueError("each group needs >= 2 observations")
    df = n1 + n2 - 2
    d = cohens_d(x, y)
    J = hedges_correction(df, correction)
    g = J * d
    if ci == "noncentral_t":
        scale = np.sqrt(1 / n1 + 1 / n2)
        lo, hi = _nct_ci_delta(d / scale, df, scale, alpha)
        lo, hi = J * lo, J * hi
    elif ci == "normal":
        se = np.sqrt((n1 + n2) / (n1 * n2) + g ** 2 / (2 * (n1 + n2)))
        q = stats.norm.ppf(1 - alpha / 2)
        lo, hi = g - q * se, g + q * se
    else:
        raise ValueError("ci must be 'noncentral_t' or 'normal'")
    return {"g": float(g), "d": float(d), "J": float(J), "ci_low": float(lo),
            "ci_high": float(hi), "n1": n1, "n2": n2, "alpha": alpha,
            "method": f"Hedges g ({correction} J), CI: {ci}",
            "assumptions": ["normal outcomes", "equal population variances (pooled SD)"]}


def cohens_dz(x, y=None, *, alpha: float = 0.05) -> dict:
    r"""Cohen's :math:`d_z` for paired data: :math:`\bar D/s_D` with ``D = x - y``
    (or one-sample ``x`` if ``y`` is None). Equals :math:`t/\sqrt n` of the paired t-test.

    CI by inverting the noncentral t with :math:`df=n-1` (exact under normality).
    """
    if y is None:
        dif = as_1d(x)
        n_drop = 0
    else:
        a, b, n_drop = paired_arrays(x, y)
        dif = a - b
    n = len(dif)
    dz = dif.mean() / dif.std(ddof=1)
    lo, hi = _nct_ci_delta(dz * np.sqrt(n), n - 1, 1 / np.sqrt(n), alpha)
    return {"dz": float(dz), "ci_low": float(lo), "ci_high": float(hi), "n": n,
            "n_dropped": n_drop, "alpha": alpha,
            "method": "Cohen d_z = mean(D)/SD(D); noncentral-t CI",
            "assumptions": ["normally distributed differences"]}


def cliffs_delta(x, y) -> float:
    r"""Cliff's delta: :math:`\delta=P(X>Y)-P(X<Y)` over all :math:`n_1n_2` pairs.

    Ordinal, distribution-free; :math:`\delta=2\,AUC-1` with AUC the Mann–Whitney probability
    :math:`P(X>Y)+\tfrac12P(X=Y)`. For a CI use :func:`bootstrap_ci`.
    """
    x, y = as_1d(x), np.sort(as_1d(y))
    gt = np.searchsorted(y, x, side="left").sum()          # y strictly below each x
    lt = (len(y) - np.searchsorted(y, x, side="right")).sum()  # y strictly above each x
    return float((gt - lt) / (len(x) * len(y)))


def bootstrap_ci(stat: Callable, *samples, n_boot: int = 2000, alpha: float = 0.05,
                 method: str = "percentile", seed: int = 0, paired: bool = False) -> dict:
    r"""Seeded nonparametric bootstrap confidence interval for ``stat(*samples)``.

    * ``paired=False``: each sample is resampled independently (two-group statistics).
    * ``paired=True``: all samples must have equal length and rows are resampled jointly.
    * ``method="percentile"``: :math:`[\hat\theta^*_{(\alpha/2)},\hat\theta^*_{(1-\alpha/2)}]`.
    * ``method="bca"``: bias-corrected and accelerated (Efron & Tibshirani 1993), with
      :math:`z_0=\Phi^{-1}(\#\{\hat\theta^*<\hat\theta\}/B)` and jackknife acceleration
      :math:`a=\sum(\bar\theta_{(\cdot)}-\theta_{(i)})^3/(6[\sum(\bar\theta_{(\cdot)}-
      \theta_{(i)})^2]^{3/2})` (jackknife over all observations of all samples).

    Uses ``numpy.random.default_rng(seed)``; identical inputs and seed give identical output.
    """
    arrs = [np.asarray(s, dtype=float) for s in samples]
    rng = np.random.default_rng(seed)
    est = float(stat(*arrs))
    boots = np.empty(n_boot)
    if paired:
        n = len(arrs[0])
        if any(len(a) != n for a in arrs):
            raise ValueError("paired bootstrap needs equal-length samples")
        for b in range(n_boot):
            idx = rng.integers(0, n, n)
            boots[b] = stat(*[a[idx] for a in arrs])
    else:
        for b in range(n_boot):
            boots[b] = stat(*[a[rng.integers(0, len(a), len(a))] for a in arrs])
    boots = boots[np.isfinite(boots)]
    if method == "percentile":
        lo, hi = np.quantile(boots, [alpha / 2, 1 - alpha / 2])
    elif method == "bca":
        prop = np.clip((boots < est).mean() + 0.5 * (boots == est).mean(), 1e-10, 1 - 1e-10)
        z0 = stats.norm.ppf(prop)
        jack = []
        if paired:
            n = len(arrs[0])
            for i in range(n):
                keep = np.arange(n) != i
                jack.append(stat(*[a[keep] for a in arrs]))
        else:
            for j, a in enumerate(arrs):
                for i in range(len(a)):
                    sub = list(arrs)
                    sub[j] = np.delete(a, i)
                    jack.append(stat(*sub))
        jack = np.asarray(jack, float)
        dm = jack.mean() - jack
        den = 6 * (dm ** 2).sum() ** 1.5
        acc = (dm ** 3).sum() / den if den > 0 else 0.0
        zs = stats.norm.ppf([alpha / 2, 1 - alpha / 2])
        adj = stats.norm.cdf(z0 + (z0 + zs) / (1 - acc * (z0 + zs)))
        lo, hi = np.quantile(boots, adj)
    else:
        raise ValueError("method must be 'percentile' or 'bca'")
    return {"estimate": est, "ci_low": float(lo), "ci_high": float(hi),
            "se_boot": float(boots.std(ddof=1)), "n_boot": int(len(boots)), "seed": seed,
            "method": f"nonparametric bootstrap ({method}), {'paired' if paired else 'independent'}"
                      " resampling"}


def _pvals(p: Sequence[float]) -> np.ndarray:
    p = np.asarray(p, dtype=float).ravel()
    if np.any((p < 0) | (p > 1)):
        raise ValueError("p-values must be in [0, 1]")
    return p


def holm(pvals: Sequence[float], alpha: float = 0.05) -> dict:
    r"""Holm (1979) step-down adjustment (controls the family-wise error rate).

    Sorted :math:`p_{(1)}\le\dots\le p_{(m)}`: :math:`\tilde p_{(i)}=\max_{j\le i}
    \min(1,(m-j+1)p_{(j)})`. Reject where :math:`\tilde p\le\alpha`.
    """
    p = _pvals(pvals)
    m = len(p)
    order = np.argsort(p)
    adj_sorted = np.minimum(1, np.maximum.accumulate((m - np.arange(m)) * p[order]))
    adj = np.empty(m)
    adj[order] = adj_sorted
    return {"p_adjusted": adj.tolist(), "reject": (adj <= alpha).tolist(), "alpha": alpha,
            "method": "Holm (1979) step-down, FWER"}


def benjamini_hochberg(pvals: Sequence[float], alpha: float = 0.05) -> dict:
    r"""Benjamini–Hochberg (1995) step-up adjustment (controls the false discovery rate under
    independence or positive dependence).

    :math:`\tilde p_{(i)}=\min_{j\ge i}\min(1,\tfrac{m}{j}p_{(j)})`. Reject where
    :math:`\tilde p\le\alpha`.
    """
    p = _pvals(pvals)
    m = len(p)
    order = np.argsort(p)
    ranked = p[order] * m / np.arange(1, m + 1)
    adj_sorted = np.minimum(1, np.minimum.accumulate(ranked[::-1])[::-1])
    adj = np.empty(m)
    adj[order] = adj_sorted
    return {"p_adjusted": adj.tolist(), "reject": (adj <= alpha).tolist(), "alpha": alpha,
            "method": "Benjamini-Hochberg (1995) step-up, FDR"}
