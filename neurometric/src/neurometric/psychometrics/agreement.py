r"""Agreement between two measurements of the same quantity: Bland–Altman and Lin's CCC.

Typical NeuroMetric uses: session 1 vs session 2 of the same task metric (test–retest
agreement in the metric's own units), browser vs. Python scoring of the same events, or two
input modalities measured on the same participants.

References
----------
* Bland JM, Altman DG (1986). Statistical methods for assessing agreement between two methods
  of clinical measurement. Lancet 327(8476):307-310. (PEFR worked example reproduced in tests)
* Bland JM, Altman DG (1999). Measuring agreement in method comparison studies. Stat Methods
  Med Res 8(2):135-160. [PK]
* Lin LI-K (1989). A concordance correlation coefficient to evaluate reproducibility.
  Biometrics 45(1):255-268; correction (2000) Biometrics 56:324-325. [PK]
* Carkeet A (2015). Exact parametric confidence intervals for Bland-Altman limits of
  agreement. Optom Vis Sci 92(3):e71-e80. [PK]

[PK] = cited from prior knowledge, details not re-verified.
"""
from __future__ import annotations

import numpy as np
from scipy import stats

from ._util import paired_arrays

__all__ = ["bland_altman", "lin_ccc"]


def bland_altman(x, y, *, alpha: float = 0.05, loa_z: float | None = None,
                 loa_ci: str = "ba1999") -> dict:
    r"""Bland–Altman analysis of paired measurements (differences ``d = x - y``).

    * bias :math:`\bar d`, with t-based CI :math:`\bar d\pm t_{1-\alpha/2,n-1}\,s_d/\sqrt n`.
    * limits of agreement (LoA) :math:`\bar d\pm z\,s_d`, :math:`z=1.96` by default
      (``loa_z=2`` reproduces the rounded multiplier of Bland & Altman 1986).
    * CI of each LoA: :math:`LoA\pm t_{1-\alpha/2,n-1}\,SE_{LoA}` with

      - ``loa_ci="ba1999"`` (default): :math:`SE_{LoA}=s_d\sqrt{1/n+z^2/(2(n-1))}`
        (Bland & Altman 1999, approximate variance of :math:`\bar d+z s_d`);
      - ``loa_ci="ba1986"``: :math:`SE_{LoA}\approx\sqrt{3s_d^2/n}` (1986 shortcut, z≈2);
      - ``loa_ci="exact"``: exact tolerance-factor interval via the non-central t
        (Carkeet 2015): :math:`\bar d\pm s_d\,t'_{q}(n-1,\,z\sqrt n)/\sqrt n`.

    * proportional bias: OLS regression of ``d`` on the pairwise mean ``(x+y)/2`` (slope, CI,
      p). A significant slope means the difference depends on magnitude, so a single pair of
      LoA is misleading (consider log transformation or regression-based LoA).

    Pairs with a missing value are dropped (reported in ``n_dropped``). Assumes differences are
    independent (one pair per subject) and approximately normal; repeated pairs per subject
    need the Bland & Altman (2007) repeated-measures variant (not implemented). [PK]
    """
    x, y, n_drop = paired_arrays(x, y)
    n = len(x)
    if n < 3:
        raise ValueError("need at least 3 complete pairs")
    z = stats.norm.ppf(1 - alpha / 2) if loa_z is None else float(loa_z)
    d = x - y
    m = (x + y) / 2
    bias = d.mean()
    sd = d.std(ddof=1)
    t = stats.t.ppf(1 - alpha / 2, n - 1)
    se_bias = sd / np.sqrt(n)
    lo, hi = bias - z * sd, bias + z * sd
    if loa_ci == "ba1999":
        se = sd * np.sqrt(1 / n + z ** 2 / (2 * (n - 1)))
        lo_ci = (lo - t * se, lo + t * se)
        hi_ci = (hi - t * se, hi + t * se)
    elif loa_ci == "ba1986":
        se = np.sqrt(3 * sd ** 2 / n)
        lo_ci = (lo - t * se, lo + t * se)
        hi_ci = (hi - t * se, hi + t * se)
    elif loa_ci == "exact":
        se = None
        nc = z * np.sqrt(n)
        kq_hi = stats.nct.ppf(1 - alpha / 2, n - 1, nc) / np.sqrt(n)
        kq_lo = stats.nct.ppf(alpha / 2, n - 1, nc) / np.sqrt(n)
        hi_ci = (bias + kq_lo * sd, bias + kq_hi * sd)
        lo_ci = (bias - kq_hi * sd, bias - kq_lo * sd)
    else:
        raise ValueError("loa_ci must be 'ba1999', 'ba1986' or 'exact'")
    # proportional bias
    reg = stats.linregress(m, d)
    tdf = stats.t.ppf(1 - alpha / 2, n - 2)
    sh_p = stats.shapiro(d).pvalue if 3 <= n <= 5000 else np.nan
    warn = []
    if reg.pvalue < alpha:
        warn.append(f"proportional bias: slope of difference on mean = {reg.slope:.3g} "
                    f"(p = {reg.pvalue:.3g}); constant LoA may be misleading")
    if sh_p < alpha:
        warn.append(f"differences deviate from normality (Shapiro-Wilk p = {sh_p:.3g}); "
                    "LoA coverage may not be 95%")
    if n_drop:
        warn.append(f"{n_drop} incomplete pairs dropped")
    return {
        "bias": float(bias), "bias_ci": [float(bias - t * se_bias), float(bias + t * se_bias)],
        "sd_diff": float(sd), "loa_z": float(z),
        "loa_low": float(lo), "loa_high": float(hi),
        "loa_low_ci": [float(v) for v in lo_ci], "loa_high_ci": [float(v) for v in hi_ci],
        "loa_se": None if se is None else float(se), "loa_ci_method": loa_ci,
        "proportional_bias": {"slope": float(reg.slope), "intercept": float(reg.intercept),
                              "slope_ci": [float(reg.slope - tdf * reg.stderr),
                                           float(reg.slope + tdf * reg.stderr)],
                              "p": float(reg.pvalue)},
        "shapiro_p_diff": None if np.isnan(sh_p) else float(sh_p),
        "n": n, "n_dropped": n_drop, "alpha": alpha,
        "method": "Bland-Altman (1986, 1999): bias, LoA = bias +/- z*SD(d), "
                  f"LoA CI method '{loa_ci}'; proportional bias by OLS of d on mean",
        "assumptions": ["one independent pair per subject", "differences approx. normal",
                        "bias and SD of differences constant over the measurement range"],
        "warnings": warn,
    }


def lin_ccc(x, y, *, alpha: float = 0.05) -> dict:
    r"""Lin's concordance correlation coefficient with Fisher-z confidence interval.

    :math:`\hat\rho_c=\dfrac{2s_{xy}}{s_x^2+s_y^2+(\bar x-\bar y)^2}` using the 1/n
    (maximum-likelihood) moments of Lin (1989). :math:`\hat\rho_c = r\,C_b` with precision
    :math:`r` (Pearson) and accuracy :math:`C_b=2/(v+1/v+u^2)`, :math:`v=s_x/s_y`,
    :math:`u=(\bar x-\bar y)/\sqrt{s_xs_y}`.

    CI: :math:`\hat z=\tanh^{-1}\hat\rho_c` with asymptotic variance (Lin 1989, corrected 2000)

    .. math::
        \sigma^2_z=\frac{1}{n-2}\left[\frac{(1-r^2)\rho_c^2}{(1-\rho_c^2)r^2}
        +\frac{2\rho_c^3(1-\rho_c)u^2}{r(1-\rho_c^2)^2}-\frac{\rho_c^4u^4}{2r^2(1-\rho_c^2)^2}
        \right]

    back-transformed with tanh.
    """
    x, y, n_drop = paired_arrays(x, y)
    n = len(x)
    if n < 4:
        raise ValueError("need at least 4 complete pairs")
    mx, my = x.mean(), y.mean()
    sx2, sy2 = x.var(ddof=0), y.var(ddof=0)
    sxy = ((x - mx) * (y - my)).mean()
    ccc = 2 * sxy / (sx2 + sy2 + (mx - my) ** 2)
    r = sxy / np.sqrt(sx2 * sy2)
    u = (mx - my) / (sx2 * sy2) ** 0.25
    cb = ccc / r if r != 0 else np.nan
    with np.errstate(divide="ignore", invalid="ignore"):
        var_z = (((1 - r ** 2) * ccc ** 2) / ((1 - ccc ** 2) * r ** 2)
                 + (2 * ccc ** 3 * (1 - ccc) * u ** 2) / (r * (1 - ccc ** 2) ** 2)
                 - (ccc ** 4 * u ** 4) / (2 * r ** 2 * (1 - ccc ** 2) ** 2)) / (n - 2)
        zc = np.arctanh(ccc)
        q = stats.norm.ppf(1 - alpha / 2)
        se_z = np.sqrt(var_z)
        lo, hi = np.tanh(zc - q * se_z), np.tanh(zc + q * se_z)
    warn = [f"{n_drop} incomplete pairs dropped"] if n_drop else []
    return {"ccc": float(ccc), "ci_low": float(lo), "ci_high": float(hi),
            "pearson_r": float(r), "accuracy_cb": float(cb), "location_shift_u": float(u),
            "scale_shift_v": float(np.sqrt(sx2 / sy2)), "se_z": float(se_z), "n": n,
            "n_dropped": n_drop, "alpha": alpha,
            "method": "Lin (1989) CCC, 1/n moments; Fisher-z CI with Lin's asymptotic variance",
            "assumptions": ["paired continuous measurements", "approx. bivariate normal"],
            "warnings": warn}
