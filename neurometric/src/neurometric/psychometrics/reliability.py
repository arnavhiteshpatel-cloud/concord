r"""Reliability: intraclass correlation, SEM / MDC, Spearman–Brown, internal consistency.

All functions are pure (no I/O) and operate on numpy arrays or pandas DataFrames.

Data layout
-----------
Reliability functions accept either

* a **wide** matrix ``Y`` of shape ``(n_subjects, k_sessions)`` (ndarray or DataFrame whose
  columns are sessions / raters / trials), or
* a **long** DataFrame plus ``subject_col``, ``session_col`` and ``score_col``.

Notation (two-way ANOVA without replication; Shrout & Fleiss 1979; McGraw & Wong 1996)
--------------------------------------------------------------------------------------
``n`` subjects (targets), ``k`` sessions (raters / measurements). With :math:`\bar y_{i\cdot}`
the subject means, :math:`\bar y_{\cdot j}` the session means and :math:`\bar y` the grand mean

.. math::

    MS_R &= \frac{k\sum_i (\bar y_{i\cdot}-\bar y)^2}{n-1} \quad\text{(between subjects / rows)}\\
    MS_C &= \frac{n\sum_j (\bar y_{\cdot j}-\bar y)^2}{k-1} \quad\text{(between sessions / columns)}\\
    MS_E &= \frac{SS_T - SS_R - SS_C}{(n-1)(k-1)} \quad\text{(residual)}\\
    MS_W &= \frac{SS_T - SS_R}{n(k-1)} \quad\text{(within subjects, one-way model)}

ICC forms (Shrout & Fleiss name / McGraw & Wong name):

=========  ==========  ==============================================================
S&F        M&W         Formula
=========  ==========  ==============================================================
ICC(1,1)   ICC(1)      :math:`(MS_R-MS_W)/(MS_R+(k-1)MS_W)`
ICC(2,1)   ICC(A,1)    :math:`(MS_R-MS_E)/(MS_R+(k-1)MS_E+\tfrac{k}{n}(MS_C-MS_E))`
ICC(3,1)   ICC(C,1)    :math:`(MS_R-MS_E)/(MS_R+(k-1)MS_E)`
ICC(1,k)   ICC(k)      :math:`(MS_R-MS_W)/MS_R`
ICC(2,k)   ICC(A,k)    :math:`(MS_R-MS_E)/(MS_R+(MS_C-MS_E)/n)`
ICC(3,k)   ICC(C,k)    :math:`(MS_R-MS_E)/MS_R`
=========  ==========  ==============================================================

Confidence intervals are the exact F-based intervals of McGraw & Wong (1996, Table 7) for
ICC(1), ICC(C,·) and the Satterthwaite-type approximation for ICC(A,·) (their eqs. for
"Case 2A"), see :func:`icc` for the formulas.

References
----------
* Shrout PE, Fleiss JL (1979). Intraclass correlations: uses in assessing rater reliability.
  Psychol Bull 86(2):420-428.  (worked example verified numerically in the test-suite)
* McGraw KO, Wong SP (1996). Forming inferences about some intraclass correlation
  coefficients. Psychol Methods 1(1):30-46. [PK]
* Koo TK, Li MY (2016). A guideline of selecting and reporting intraclass correlation
  coefficients for reliability research. J Chiropr Med 15(2):155-163. [PK]
* Weir JP (2005). Quantifying test-retest reliability using the intraclass correlation
  coefficient and the SEM. J Strength Cond Res 19(1):231-240. [PK]
* de Vet HCW, Terwee CB, Knol DL, Bouter LM (2006). When to use agreement versus reliability
  measures. J Clin Epidemiol 59(10):1033-1039. [PK]
* Feldt LS, Woodruff DJ, Salih FA (1987). Statistical inference for coefficient alpha.
  Appl Psychol Meas 11(1):93-103. [PK]
* McDonald RP (1999). Test Theory: A Unified Treatment. Erlbaum. [PK]
* Cronbach LJ (1951). Coefficient alpha and the internal structure of tests. Psychometrika
  16:297-334. [PK]

[PK] = cited from prior knowledge; the bibliographic details were not re-verified for this
module. Formulas are verified numerically against independent implementations (pingouin,
statsmodels) and simulation in ``tests/test_psychometrics.py``.
"""
from __future__ import annotations

import warnings as _warnings
from typing import Sequence

import numpy as np
import pandas as pd
from scipy import optimize, stats

__all__ = [
    "ICC_FORMS",
    "to_wide",
    "anova_mean_squares",
    "icc",
    "icc_table",
    "icc_mixed",
    "sem_mdc",
    "sem_from_icc",
    "mdc",
    "spearman_brown",
    "spearman_brown_length",
    "cronbach_alpha",
    "mcdonald_omega",
    "INTERNAL_CONSISTENCY_WARNING",
]

#: Supported ICC forms (Shrout & Fleiss notation) -> metadata.
ICC_FORMS: dict[str, dict] = {
    "1,1": {"mw": "ICC(1)", "model": "one-way random", "type": "absolute agreement",
            "unit": "single"},
    "2,1": {"mw": "ICC(A,1)", "model": "two-way random", "type": "absolute agreement",
            "unit": "single"},
    "3,1": {"mw": "ICC(C,1)", "model": "two-way mixed", "type": "consistency",
            "unit": "single"},
    "1,k": {"mw": "ICC(k)", "model": "one-way random", "type": "absolute agreement",
            "unit": "average of k"},
    "2,k": {"mw": "ICC(A,k)", "model": "two-way random", "type": "absolute agreement",
            "unit": "average of k"},
    "3,k": {"mw": "ICC(C,k)", "model": "two-way mixed", "type": "consistency",
            "unit": "average of k"},
}

INTERNAL_CONSISTENCY_WARNING = (
    "Internal-consistency coefficients (Cronbach alpha, McDonald omega) are only meaningful "
    "for a set of items that are intended to measure ONE construct (a reflective, "
    "unidimensional scale, e.g. the items of a questionnaire). They are NOT appropriate for an "
    "arbitrary set of task metrics (e.g. throughput, error rate, path efficiency, latency): "
    "such metrics are formative/heterogeneous, may legitimately be uncorrelated, and a low or "
    "high alpha says nothing about the reliability of any single metric. Use test-retest ICC "
    "for task metrics."
)


# ----------------------------------------------------------------------------- data handling
def to_wide(data, subject_col: str | None = None, session_col: str | None = None,
            score_col: str | None = None) -> pd.DataFrame:
    """Return a subjects x sessions DataFrame.

    If ``subject_col``/``session_col``/``score_col`` are given, ``data`` is treated as long
    format and pivoted (duplicate subject-session cells raise ``ValueError``). Otherwise ``data``
    is taken to already be wide (ndarray or DataFrame). Missing cells are NaN.
    """
    if subject_col is not None or session_col is not None or score_col is not None:
        if None in (subject_col, session_col, score_col):
            raise ValueError("long format needs subject_col, session_col and score_col")
        d = pd.DataFrame(data)
        if d.duplicated([subject_col, session_col]).any():
            raise ValueError("duplicate subject-session rows; aggregate them first")
        w = d.pivot(index=subject_col, columns=session_col, values=score_col)
        return w.sort_index(axis=1).astype(float)
    if isinstance(data, pd.DataFrame):
        return data.astype(float)
    a = np.asarray(data, dtype=float)
    if a.ndim != 2:
        raise ValueError("wide data must be 2-D (subjects x sessions)")
    return pd.DataFrame(a)


def _complete_case(w: pd.DataFrame) -> tuple[np.ndarray, int, int]:
    ok = w.notna().all(axis=1)
    return w.loc[ok].to_numpy(float), int(len(w)), int((~ok).sum())


def anova_mean_squares(Y) -> dict:
    """Two-way ANOVA (no replication) sums of squares and mean squares for a complete matrix.

    Returns a dict with ``n, k, SSR, SSC, SSE, SST, SSW, MSR, MSC, MSE, MSW`` and degrees of
    freedom ``df_R = n-1``, ``df_C = k-1``, ``df_E = (n-1)(k-1)``, ``df_W = n(k-1)``.
    """
    Y = np.asarray(Y, dtype=float)
    if np.isnan(Y).any():
        raise ValueError("anova_mean_squares needs a complete matrix (no NaN)")
    n, k = Y.shape
    if n < 2 or k < 2:
        raise ValueError("need at least 2 subjects and 2 sessions")
    g = Y.mean()
    rm, cm = Y.mean(axis=1), Y.mean(axis=0)
    sst = ((Y - g) ** 2).sum()
    ssr = k * ((rm - g) ** 2).sum()
    ssc = n * ((cm - g) ** 2).sum()
    sse = max(sst - ssr - ssc, 0.0)
    ssw = max(sst - ssr, 0.0)
    dfr, dfc, dfe, dfw = n - 1, k - 1, (n - 1) * (k - 1), n * (k - 1)
    return {"n": n, "k": k, "SST": sst, "SSR": ssr, "SSC": ssc, "SSE": sse, "SSW": ssw,
            "df_R": dfr, "df_C": dfc, "df_E": dfe, "df_W": dfw,
            "MSR": ssr / dfr, "MSC": ssc / dfc, "MSE": sse / dfe, "MSW": ssw / dfw}


def _icc_from_ms(ms: dict, alpha: float = 0.05) -> dict[str, dict]:
    """All six ICCs with McGraw & Wong (1996) F-based CIs from ANOVA mean squares."""
    n, k = ms["n"], ms["k"]
    msr, msc, mse, msw = ms["MSR"], ms["MSC"], ms["MSE"], ms["MSW"]
    dfr, dfe, dfw = ms["df_R"], ms["df_E"], ms["df_W"]
    q = 1 - alpha / 2
    out: dict[str, dict] = {}
    with np.errstate(divide="ignore", invalid="ignore"):
        # ---- one-way (Case 1): F = MSR/MSW on (n-1, n(k-1)); exact
        f1 = msr / msw
        fl = f1 / stats.f.ppf(q, dfr, dfw)
        fu = f1 * stats.f.ppf(q, dfw, dfr)
        p1 = stats.f.sf(f1, dfr, dfw)
        out["1,1"] = dict(icc=(msr - msw) / (msr + (k - 1) * msw),
                          ci=((fl - 1) / (fl + k - 1), (fu - 1) / (fu + k - 1)),
                          F=f1, df1=dfr, df2=dfw, p=p1)
        out["1,k"] = dict(icc=(msr - msw) / msr, ci=(1 - 1 / fl, 1 - 1 / fu),
                          F=f1, df1=dfr, df2=dfw, p=p1)
        # ---- consistency (Case 3 / C): F = MSR/MSE on (n-1, (n-1)(k-1)); exact
        f3 = msr / mse
        fl = f3 / stats.f.ppf(q, dfr, dfe)
        fu = f3 * stats.f.ppf(q, dfe, dfr)
        p3 = stats.f.sf(f3, dfr, dfe)
        out["3,1"] = dict(icc=(msr - mse) / (msr + (k - 1) * mse),
                          ci=((fl - 1) / (fl + k - 1), (fu - 1) / (fu + k - 1)),
                          F=f3, df1=dfr, df2=dfe, p=p3)
        out["3,k"] = dict(icc=(msr - mse) / msr, ci=(1 - 1 / fl, 1 - 1 / fu),
                          F=f3, df1=dfr, df2=dfe, p=p3)
        # ---- absolute agreement (Case 2 / A): approximate (Satterthwaite) df
        r2 = (msr - mse) / (msr + (k - 1) * mse + k * (msc - mse) / n)
        a = k * r2 / (n * (1 - r2))
        b = 1 + k * r2 * (n - 1) / (n * (1 - r2))
        v = (a * msc + b * mse) ** 2 / ((a * msc) ** 2 / (k - 1) + (b * mse) ** 2 / dfe)
        fs = stats.f.ppf(q, dfr, v)   # F*  (upper quantile, n-1 and v df)
        fs2 = stats.f.ppf(q, v, dfr)  # F_* (upper quantile, v and n-1 df)
        lo = n * (msr - fs * mse) / (fs * (k * msc + (k * n - k - n) * mse) + n * msr)
        hi = n * (fs2 * msr - mse) / (k * msc + (k * n - k - n) * mse + n * fs2 * msr)
        out["2,1"] = dict(icc=r2, ci=(lo, hi), F=f3, df1=dfr, df2=dfe, p=p3, v=v)
        # average-measure A,k: McGraw & Wong closed form == Spearman–Brown of the A,1 bounds
        lo_k = n * (msr - fs * mse) / (fs * (msc - mse) + n * msr)
        hi_k = n * (fs2 * msr - mse) / (msc - mse + n * fs2 * msr)
        out["2,k"] = dict(icc=(msr - mse) / (msr + (msc - mse) / n), ci=(lo_k, hi_k),
                          F=f3, df1=dfr, df2=dfe, p=p3, v=v)
    return out


def _gci_agreement(ms: dict, alpha: float = 0.05, n_draws: int = 10000,
                   seed: int = 0) -> dict[str, tuple[float, float]]:
    r"""Generalized confidence interval (GCI) for ICC(A,1) and ICC(A,k).

    Generalized pivotal quantities (Weerahandi 1993; evaluated for the ICC by Ionan et al.
    2014 [PK]) with independent :math:`\chi^2` draws :math:`U_R\sim\chi^2_{n-1}`,
    :math:`U_C\sim\chi^2_{k-1}`, :math:`U_E\sim\chi^2_{(n-1)(k-1)}`:
    :math:`\sigma^{2*}_e=SS_E/U_E`, :math:`\sigma^{2*}_s=\max(0,(SS_R/U_R-\sigma^{2*}_e)/k)`,
    :math:`\sigma^{2*}_r=\max(0,(SS_C/U_C-\sigma^{2*}_e)/n)`; the CI is the
    :math:`\alpha/2,1-\alpha/2` quantiles of :math:`\sigma^{2*}_s/(\sigma^{2*}_s+\sigma^{2*}_r+
    \sigma^{2*}_e)` (single) or :math:`\sigma^{2*}_s/(\sigma^{2*}_s+(\sigma^{2*}_r+
    \sigma^{2*}_e)/k)` (average). Seeded, so deterministic.

    Motivation: the McGraw & Wong Satterthwaite interval for ICC(A,·) under-covers when the
    session variance is comparable to the error variance (Experiment R found 78-92 % coverage
    for k = 2-6, var_session = var_error; see docs/science/PSYCHOMETRICS.md); the GCI kept
    94-96 % in the same scenarios.
    """
    n, k = ms["n"], ms["k"]
    rng = np.random.default_rng(seed)
    ur = rng.chisquare(n - 1, n_draws)
    uc = rng.chisquare(k - 1, n_draws)
    ue = rng.chisquare((n - 1) * (k - 1), n_draws)
    e = ms["SSE"] / ue
    sv = np.maximum((ms["SSR"] / ur - e) / k, 0.0)
    rv = np.maximum((ms["SSC"] / uc - e) / n, 0.0)
    q = [alpha / 2, 1 - alpha / 2]
    with np.errstate(invalid="ignore", divide="ignore"):
        one = np.nan_to_num(sv / (sv + rv + e))
        avg = np.nan_to_num(sv / (sv + (rv + e) / k))
    return {"2,1": tuple(float(v) for v in np.quantile(one, q)),
            "2,k": tuple(float(v) for v in np.quantile(avg, q))}


def icc(data, subject_col: str | None = None, session_col: str | None = None,
        score_col: str | None = None, *, forms: Sequence[str] = tuple(ICC_FORMS),
        alpha: float = 0.05, missing: str = "complete_case",
        gci_draws: int = 10000, seed: int = 0) -> dict:
    r"""Intraclass correlation coefficients (Shrout & Fleiss 1979 / McGraw & Wong 1996).

    Parameters
    ----------
    data : wide matrix (n_subjects x k_sessions) or long DataFrame (then give the column names)
    forms : subset of ``"1,1","2,1","3,1","1,k","2,k","3,k"``
    alpha : 1 - confidence level of the intervals (default 0.05 -> 95 % CI)
    missing : ``"complete_case"`` (default; subjects with any missing session are dropped and
        the count is reported) or ``"mixed"`` (variance components from a linear mixed model
        fitted by REML to all available observations, see :func:`icc_mixed`; no F-based CI).

    Confidence intervals (McGraw & Wong 1996, Table 7), :math:`F_{q}(d_1,d_2)` the upper
    :math:`q=1-\alpha/2` quantile:

    * ICC(1,·): :math:`F_0=MS_R/MS_W`, :math:`F_L=F_0/F_q(n-1,n(k-1))`,
      :math:`F_U=F_0\,F_q(n(k-1),n-1)`; single: :math:`(F_L-1)/(F_L+k-1)`,
      :math:`(F_U-1)/(F_U+k-1)`; average: :math:`1-1/F_L`, :math:`1-1/F_U`.
    * ICC(3,·) / ICC(C,·): identical with :math:`F_0=MS_R/MS_E` on :math:`(n-1,(n-1)(k-1))` df.
    * ICC(2,1) / ICC(A,1): with :math:`\hat\rho` the point estimate,
      :math:`a=k\hat\rho/(n(1-\hat\rho))`, :math:`b=1+k\hat\rho(n-1)/(n(1-\hat\rho))`,
      :math:`v=(aMS_C+bMS_E)^2/[(aMS_C)^2/(k-1)+(bMS_E)^2/((n-1)(k-1))]`,
      :math:`F^*=F_q(n-1,v)`, :math:`F_*=F_q(v,n-1)`;
      :math:`L=n(MS_R-F^*MS_E)/(F^*(kMS_C+(kn-k-n)MS_E)+nMS_R)`,
      :math:`U=n(F_*MS_R-MS_E)/(kMS_C+(kn-k-n)MS_E+nF_*MS_R)`.
    * ICC(2,k) / ICC(A,k): :math:`L=n(MS_R-F^*MS_E)/(F^*(MS_C-MS_E)+nMS_R)`,
      :math:`U=n(F_*MS_R-MS_E)/(MS_C-MS_E+nF_*MS_R)` (algebraically the Spearman–Brown
      step-up of the ICC(A,1) bounds).

    The p-value tests H0: ICC = 0 (``F``, ``df1``, ``df2``).

    For the absolute-agreement forms an additional **generalized confidence interval**
    (``gci_low``, ``gci_high``; :func:`_gci_agreement`, ``gci_draws`` seeded draws) is reported
    because the McGraw & Wong interval under-covers when sessions differ systematically and k is
    small (verified in Experiment R). Set ``gci_draws=0`` to skip it.

    Returns
    -------
    dict with ``table`` (list of per-form dicts: ``form, mw_label, model, type, unit, icc,
    ci_low, ci_high, F, df1, df2, p``), ``n_subjects_total``, ``n_subjects_used``,
    ``n_subjects_dropped``, ``k``, ``mean_squares``, ``method``, ``alpha``, ``assumptions``,
    ``warnings``.
    """
    bad = [f for f in forms if f not in ICC_FORMS]
    if bad:
        raise ValueError(f"unknown ICC forms {bad}; use {list(ICC_FORMS)}")
    w = to_wide(data, subject_col, session_col, score_col)
    if missing == "mixed":
        return _icc_via_mixed(w, forms, alpha)
    if missing != "complete_case":
        raise ValueError("missing must be 'complete_case' or 'mixed'")
    Y, n_total, n_drop = _complete_case(w)
    warn: list[str] = []
    if n_drop:
        warn.append(f"{n_drop} of {n_total} subjects dropped (complete-case analysis: at least "
                    "one session missing). Consider missing='mixed'.")
    if Y.shape[0] < 2:
        raise ValueError("fewer than 2 complete subjects")
    ms = anova_mean_squares(Y)
    res = _icc_from_ms(ms, alpha)
    gci = _gci_agreement(ms, alpha, gci_draws, seed) if gci_draws else {}
    table = []
    for f in forms:
        r = res[f]
        g = gci.get(f, (None, None))
        table.append({"form": f"ICC({f})", "key": f, "mw_label": ICC_FORMS[f]["mw"],
                      "model": ICC_FORMS[f]["model"], "type": ICC_FORMS[f]["type"],
                      "unit": ICC_FORMS[f]["unit"], "icc": float(r["icc"]),
                      "ci_low": float(r["ci"][0]), "ci_high": float(r["ci"][1]),
                      "gci_low": g[0], "gci_high": g[1],
                      "F": float(r["F"]), "df1": float(r["df1"]), "df2": float(r["df2"]),
                      "p": float(r["p"])})
    if ms["n"] < 15:
        warn.append(f"only {ms['n']} subjects: ICC confidence intervals are wide "
                    "(Koo & Li 2016 suggest >= 30 subjects and >= 3 sessions/raters) [PK].")
    if any(t["icc"] < 0 for t in table):
        warn.append("negative ICC estimate(s): between-subject variance is ~0 relative to "
                    "error; interpret as no reliability.")
    return {
        "method": "two-way ANOVA mean squares; ICC per Shrout & Fleiss (1979) / McGraw & Wong "
                  f"(1996); {100 * (1 - alpha):.0f}% CI F-based (McGraw & Wong 1996); "
                  "agreement forms also get a generalized CI (gci_low/gci_high, "
                  f"{gci_draws} draws, seed {seed})",
        "alpha": alpha, "missing": "complete_case", "table": table,
        "n_subjects_total": n_total, "n_subjects_used": int(Y.shape[0]),
        "n_subjects_dropped": n_drop, "k": int(Y.shape[1]),
        "n": int(Y.shape[0]),
        "mean_squares": {k_: float(v) for k_, v in ms.items()},
        "assumptions": ["scores are interval-scaled and approximately normal",
                        "subject and error effects independent; homoscedastic error",
                        "no subject x session interaction (two-way models)",
                        "sessions treated as random (A forms, ICC(1)) or fixed (C forms)"],
        "warnings": warn,
    }


def icc_table(data, subject_col=None, session_col=None, score_col=None, **kw) -> pd.DataFrame:
    """:func:`icc` result as a DataFrame indexed by form (convenience)."""
    return pd.DataFrame(icc(data, subject_col, session_col, score_col, **kw)["table"]) \
        .set_index("form")


# ---------------------------------------------------------------------------- mixed-model ICC
def _robust_fit(md, reml: bool = True):
    """Fit a statsmodels MixedLM trying several optimisers (first converged fit wins)."""
    last_err, fallback = None, None
    for meth in ("bfgs", "lbfgs", "powell", "nm"):
        try:
            fit = md.fit(reml=reml, method=meth)
        except (np.linalg.LinAlgError, ValueError) as e:  # singular start etc.
            last_err = e
            continue
        if getattr(fit, "converged", True):
            return fit
        fallback = fallback or fit
    if fallback is not None:
        return fallback
    raise RuntimeError(f"MixedLM failed with all optimisers: {last_err}")


def _fit_mixed_components(long: pd.DataFrame, model: str) -> dict:
    """Variance components by REML (statsmodels MixedLM).

    model = "agreement": y = mu + s_i + r_j + e  with crossed random subject and session effects
    model = "consistency": y = mu + beta_j (fixed sessions) + s_i + e
    model = "oneway": y = mu + s_i + e
    """
    import statsmodels.formula.api as smf
    from statsmodels.tools.sm_exceptions import ConvergenceWarning

    d = long.copy()
    caught: list[str] = []
    with _warnings.catch_warnings(record=True) as wlist:
        _warnings.simplefilter("always")
        if model == "agreement":
            d["_one"] = 1
            md = smf.mixedlm("y ~ 1", d, groups="_one", re_formula="0",
                             vc_formula={"subject": "0 + C(subject)",
                                         "session": "0 + C(session)"})
            fit = _robust_fit(md)
            names = list(md.exog_vc.names)
            vc = dict(zip(names, np.asarray(fit.vcomp, float)))
            comps = {"subject": vc["subject"], "session": vc["session"],
                     "residual": float(fit.scale)}
        else:
            formula = "y ~ C(session)" if model == "consistency" else "y ~ 1"
            md = smf.mixedlm(formula, d, groups="subject")
            fit = _robust_fit(md)
            comps = {"subject": float(np.asarray(fit.cov_re)[0, 0]), "session": 0.0,
                     "residual": float(fit.scale)}
        for w_ in wlist:
            if issubclass(w_.category, (ConvergenceWarning, UserWarning, RuntimeWarning)):
                caught.append(str(w_.message).splitlines()[0])
    comps = {k_: max(float(v), 0.0) for k_, v in comps.items()}
    return {"components": comps, "converged": bool(getattr(fit, "converged", True)),
            "fit_warnings": sorted(set(caught))}


def _long_from_wide(w: pd.DataFrame) -> pd.DataFrame:
    long = w.copy()
    long.index = pd.Index(range(len(long)), name="subject")
    long.columns = pd.Index(range(long.shape[1]), name="session")
    long = long.stack().rename("y").reset_index()
    return long.dropna()


def _icc_from_components(c: dict, model: str, k: int) -> dict[str, float]:
    s, r, e = c["subject"], c["session"], c["residual"]
    out = {}
    if model == "oneway":
        out["1,1"] = s / (s + e)
        out["1,k"] = s / (s + e / k)
    elif model == "consistency":
        out["3,1"] = s / (s + e)
        out["3,k"] = s / (s + e / k)
    else:
        out["2,1"] = s / (s + r + e)
        out["2,k"] = s / (s + (r + e) / k)
    return out


_FORM_MODEL = {"1,1": "oneway", "1,k": "oneway", "2,1": "agreement", "2,k": "agreement",
               "3,1": "consistency", "3,k": "consistency"}


def icc_mixed(data, subject_col: str | None = None, session_col: str | None = None,
              score_col: str | None = None, *, form: str = "2,1", n_boot: int = 0,
              alpha: float = 0.05, seed: int = 0) -> dict:
    r"""ICC from linear-mixed-model variance components (REML; tolerates unbalanced data).

    Models (fitted with ``statsmodels`` ``MixedLM``):

    * ``"1,1"``/``"1,k"`` (one-way): :math:`y_{ij}=\mu+s_i+e_{ij}`,
      ICC = :math:`\sigma^2_s/(\sigma^2_s+\sigma^2_e)`.
    * ``"2,1"``/``"2,k"`` (agreement): crossed random subject and session effects
      :math:`y_{ij}=\mu+s_i+r_j+e_{ij}`, ICC(A,1) = :math:`\sigma^2_s/(\sigma^2_s+\sigma^2_r+
      \sigma^2_e)`, ICC(A,k) = :math:`\sigma^2_s/(\sigma^2_s+(\sigma^2_r+\sigma^2_e)/k)`.
    * ``"3,1"``/``"3,k"`` (consistency): fixed session effects, random subject intercept,
      ICC(C,1) = :math:`\sigma^2_s/(\sigma^2_s+\sigma^2_e)`.

    For complete balanced data with positive ANOVA variance estimates, REML equals the ANOVA
    (method-of-moments) estimates, so these agree with :func:`icc` (checked in tests). With only
    2-3 sessions :math:`\sigma^2_r` is estimated very imprecisely.

    Confidence interval: none by default (``ci_low``/``ci_high`` = None). With ``n_boot>0`` a
    percentile cluster bootstrap that resamples subjects (seeded) is used — slow (one model fit
    per resample).
    """
    if form not in ICC_FORMS:
        raise ValueError(f"unknown form {form}")
    w = to_wide(data, subject_col, session_col, score_col)
    w = w.loc[w.notna().any(axis=1)]
    long = _long_from_wide(w)
    k = int(w.shape[1])
    model = _FORM_MODEL[form]
    fit = _fit_mixed_components(long, model)
    est = _icc_from_components(fit["components"], model, k)[form]
    warn = list(fit["fit_warnings"])
    n_missing_cells = int(w.isna().to_numpy().sum())
    ci = (None, None)
    if n_boot > 0:
        rng = np.random.default_rng(seed)
        boots = []
        W = w.to_numpy(float)
        for _ in range(n_boot):
            idx = rng.integers(0, W.shape[0], W.shape[0])
            lb = _long_from_wide(pd.DataFrame(W[idx]))
            try:
                c = _fit_mixed_components(lb, model)["components"]
                boots.append(_icc_from_components(c, model, k)[form])
            except Exception:  # pragma: no cover - rare singular resample
                continue
        boots = np.asarray(boots)
        ci = tuple(float(v) for v in np.quantile(boots, [alpha / 2, 1 - alpha / 2]))
        if len(boots) < n_boot:
            warn.append(f"{n_boot - len(boots)} bootstrap fits failed and were skipped")
    return {
        "form": f"ICC({form})", "key": form, "mw_label": ICC_FORMS[form]["mw"],
        "icc": float(est), "ci_low": ci[0], "ci_high": ci[1],
        "ci_method": (f"cluster (subject) percentile bootstrap, B={n_boot}, seed={seed}"
                      if n_boot else None),
        "variance_components": fit["components"], "converged": fit["converged"],
        "n_subjects": int(w.shape[0]), "k": k, "n_observations": int(len(long)),
        "n_missing_cells": n_missing_cells,
        "method": f"REML linear mixed model ({model}) via statsmodels MixedLM; ICC from variance "
                  "components",
        "assumptions": ["normal random effects and residuals", "missing at random (MAR)",
                        "no subject x session interaction"],
        "warnings": warn,
    }


def _icc_via_mixed(w: pd.DataFrame, forms, alpha) -> dict:
    table, warn, comps = [], [], {}
    fits: dict[str, dict] = {}
    for f in forms:
        model = _FORM_MODEL[f]
        if model not in fits:
            fits[model] = icc_mixed(w, form=f)
        k = fits[model]["k"]
        val = _icc_from_components(fits[model]["variance_components"], model, k)[f]
        comps[model] = fits[model]["variance_components"]
        warn += fits[model]["warnings"]
        table.append({"form": f"ICC({f})", "key": f, "mw_label": ICC_FORMS[f]["mw"],
                      "model": ICC_FORMS[f]["model"], "type": ICC_FORMS[f]["type"],
                      "unit": ICC_FORMS[f]["unit"], "icc": float(val), "ci_low": None,
                      "ci_high": None, "gci_low": None, "gci_high": None, "F": None, "df1": None, "df2": None, "p": None})
    any_fit = next(iter(fits.values()))
    return {"method": "REML linear mixed model variance components (statsmodels MixedLM); "
                      "no F-based CI (use icc_mixed(n_boot=...) for a bootstrap CI)",
            "alpha": alpha, "missing": "mixed", "table": table,
            "n_subjects_total": any_fit["n_subjects"], "n_subjects_used": any_fit["n_subjects"],
            "n_subjects_dropped": 0, "k": any_fit["k"], "n": any_fit["n_subjects"],
            "n_missing_cells": any_fit["n_missing_cells"], "variance_components": comps,
            "assumptions": ["normal random effects and residuals", "missing at random (MAR)"],
            "warnings": sorted(set(warn))}


# ------------------------------------------------------------------------------- SEM and MDC
def sem_from_icc(sd: float, icc_value: float) -> float:
    r"""SEM = :math:`SD\sqrt{1-ICC}` (classical test theory; ICC clipped to [0, 1])."""
    return float(sd * np.sqrt(1 - np.clip(icc_value, 0.0, 1.0)))


def mdc(sem: float, level: float = 0.95) -> float:
    r"""Minimal detectable change of an individual's change score.

    :math:`MDC_{level}=z_{(1+level)/2}\,\sqrt 2\,SEM`; ``level=0.95`` gives :math:`1.96\sqrt2
    SEM` (MDC95), ``0.90`` gives :math:`1.645\sqrt2 SEM` (MDC90). The :math:`\sqrt2` accounts
    for measurement error in both the baseline and the follow-up score.
    """
    z = stats.norm.ppf(0.5 + level / 2)
    return float(z * np.sqrt(2.0) * sem)


def sem_mdc(data, subject_col=None, session_col=None, score_col=None, *, icc_form: str = "2,1",
            primary: str = "sqrt_mse") -> dict:
    r"""Standard error of measurement and minimal detectable change (complete cases).

    Three SEM definitions are reported and labelled; ``primary`` selects the one used for the
    headline ``sem``/``mdc95``/``mdc90``:

    * ``"sd_icc"``: :math:`SEM=SD_{pooled}\sqrt{1-ICC}` with :math:`SD_{pooled}=\sqrt{\tfrac1k
      \sum_j s_j^2}` (mean of per-session variances, ddof=1) and the ICC of ``icc_form``.
      Depends on the sample's between-subject heterogeneity through both SD and ICC.
    * ``"sqrt_mse"``: :math:`SEM=\sqrt{MS_E}` (two-way residual mean square; Weir 2005). This is
      the *consistency* SEM: it excludes systematic session (learning / practice) effects.
    * ``"agreement"``: :math:`SEM=\sqrt{\hat\sigma^2_{session}+MS_E}` with
      :math:`\hat\sigma^2_{session}=\max(0,(MS_C-MS_E)/n)` (de Vet et al. 2006). Includes
      systematic session differences.

    MDC95 = :math:`1.96\sqrt2\,SEM`, MDC90 = :math:`1.645\sqrt2\,SEM` (see :func:`mdc`).
    """
    w = to_wide(data, subject_col, session_col, score_col)
    Y, n_total, n_drop = _complete_case(w)
    ms = anova_mean_squares(Y)
    icc_val = _icc_from_ms(ms)[icc_form]["icc"]
    sd_pooled = float(np.sqrt(np.mean(Y.var(axis=0, ddof=1))))
    sems = {
        "sd_icc": sem_from_icc(sd_pooled, icc_val),
        "sqrt_mse": float(np.sqrt(ms["MSE"])),
        "agreement": float(np.sqrt(max(0.0, (ms["MSC"] - ms["MSE"]) / ms["n"]) + ms["MSE"])),
    }
    if primary not in sems:
        raise ValueError(f"primary must be one of {list(sems)}")
    detail = {k_: {"sem": v, "mdc95": mdc(v, 0.95), "mdc90": mdc(v, 0.90)}
              for k_, v in sems.items()}
    warn = []
    if n_drop:
        warn.append(f"{n_drop} of {n_total} subjects dropped (complete-case)")
    return {
        "sem": sems[primary], "mdc95": detail[primary]["mdc95"],
        "mdc90": detail[primary]["mdc90"], "primary": primary,
        "primary_definition": {"sd_icc": "SD_pooled*sqrt(1-ICC)",
                               "sqrt_mse": "sqrt(MS_error) [consistency SEM]",
                               "agreement": "sqrt(var_session + MS_error) [agreement SEM]"}
                              [primary],
        "by_definition": detail, "sd_pooled": sd_pooled, "icc_form": f"ICC({icc_form})",
        "icc": float(icc_val), "n": int(Y.shape[0]), "k": int(Y.shape[1]),
        "method": "SEM from two-way ANOVA; MDC = z*sqrt(2)*SEM",
        "assumptions": ["homoscedastic measurement error (same SEM at all score levels)",
                        "normally distributed error (for the z multipliers)"],
        "warnings": warn,
    }


# ------------------------------------------------------------------------------ Spearman–Brown
def spearman_brown(rho, m):
    r"""Spearman–Brown prophecy: reliability of a test lengthened by factor ``m``.

    :math:`\rho_m=\dfrac{m\rho}{1+(m-1)\rho}`. ``m`` may be fractional (shortening, ``m<1``).
    Applies to averaging parallel measurements (e.g. ``m`` sessions or ``m``-times as many
    trials), assuming the added parts are parallel (equal true-score and error variances).
    """
    rho = np.asarray(rho, float)
    m = np.asarray(m, float)
    out = m * rho / (1 + (m - 1) * rho)
    return float(out) if out.ndim == 0 else out


def spearman_brown_length(rho, target):
    r"""Inverse Spearman–Brown: length factor needed to reach ``target`` reliability.

    :math:`m=\dfrac{\rho^*(1-\rho)}{\rho(1-\rho^*)}`. Multiply the current number of
    trials/sessions by ``m`` (round up in practice).
    """
    rho = np.asarray(rho, float)
    target = np.asarray(target, float)
    if np.any((rho <= 0) | (rho >= 1)) or np.any((target <= 0) | (target >= 1)):
        raise ValueError("reliabilities must lie strictly in (0, 1)")
    out = target * (1 - rho) / (rho * (1 - target))
    return float(out) if out.ndim == 0 else out


# ----------------------------------------------------------------------- internal consistency
def _items_matrix(items) -> tuple[np.ndarray, int]:
    X = np.asarray(items, dtype=float)
    if X.ndim != 2 or X.shape[1] < 2:
        raise ValueError("items must be a 2-D array (n_respondents x k_items), k >= 2")
    ok = ~np.isnan(X).any(axis=1)
    return X[ok], int((~ok).sum())


def cronbach_alpha(items, alpha: float = 0.05) -> dict:
    r"""Cronbach's coefficient alpha with Feldt (1987) F-based confidence interval.

    .. warning::
       Only applies to items intended to measure ONE construct. See
       :data:`INTERNAL_CONSISTENCY_WARNING`; do **not** compute alpha over a set of different
       task metrics.

    :math:`\alpha=\frac{k}{k-1}\left(1-\frac{\sum_i s_i^2}{s_X^2}\right)` with
    :math:`s_X^2` the variance of the item sum. CI (Feldt et al. 1987):
    :math:`[1-(1-\hat\alpha)F_{1-a/2},\;1-(1-\hat\alpha)F_{a/2}]`, quantiles of
    :math:`F(n-1,(n-1)(k-1))`. Listwise deletion of incomplete rows.
    """
    X, n_drop = _items_matrix(items)
    n, k = X.shape
    C = np.cov(X, rowvar=False, ddof=1)
    a = k / (k - 1) * (1 - np.trace(C) / C.sum())
    df1, df2 = n - 1, (n - 1) * (k - 1)
    lo = 1 - (1 - a) * stats.f.ppf(1 - alpha / 2, df1, df2)
    hi = 1 - (1 - a) * stats.f.ppf(alpha / 2, df1, df2)
    return {"alpha": float(a), "ci_low": float(lo), "ci_high": float(hi), "n": n, "k": k,
            "n_dropped": n_drop, "method": "Cronbach (1951); Feldt (1987) F-based CI",
            "assumptions": ["unidimensional items measuring one construct",
                            "essentially tau-equivalent items (otherwise alpha <= reliability)",
                            "uncorrelated errors"],
            "warnings": [INTERNAL_CONSISTENCY_WARNING]}


def _one_factor_ml(S: np.ndarray, max_iter: int = 2000) -> tuple[np.ndarray, np.ndarray, bool]:
    """Maximum-likelihood single-factor model Sigma = l l' + diag(psi) fitted to covariance S.

    Minimises F = log|Sigma| + tr(S Sigma^-1) - log|S| - p (Joreskog 1967 [PK]) with an
    analytic gradient; uniquenesses are parameterised on the log scale (kept > 0).
    """
    p = S.shape[0]
    d = np.diag(S)
    ev, evec = np.linalg.eigh(S)
    lam0 = evec[:, -1] * np.sqrt(ev[-1])
    lam0 = lam0 * np.sign(lam0.sum() or 1.0)
    psi0 = np.maximum(d - lam0 ** 2, 0.05 * d)
    _, logdet_s = np.linalg.slogdet(S)

    def fun(theta):
        lam, psi = theta[:p], np.exp(theta[p:])
        sig = np.outer(lam, lam) + np.diag(psi)
        sign, logdet = np.linalg.slogdet(sig)
        if sign <= 0:
            return 1e10, np.zeros_like(theta)
        inv = np.linalg.inv(sig)
        f = logdet + np.trace(S @ inv) - logdet_s - p
        delta = inv @ (sig - S) @ inv
        g = np.concatenate([2 * delta @ lam, np.diag(delta) * psi])
        return f, g

    theta0 = np.concatenate([lam0, np.log(psi0)])
    bounds = [(None, None)] * p + [(np.log(1e-6 * d.max()), None)] * p
    r = optimize.minimize(fun, theta0, jac=True, method="L-BFGS-B", bounds=bounds,
                          options={"maxiter": max_iter, "gtol": 1e-10, "ftol": 1e-14})
    lam, psi = r.x[:p], np.exp(r.x[p:])
    if lam.sum() < 0:
        lam = -lam
    return lam, psi, bool(r.success)


def mcdonald_omega(items) -> dict:
    r"""McDonald's omega (total) from a one-factor maximum-likelihood factor model.

    .. warning::
       Only applies to items intended to measure ONE construct. See
       :data:`INTERNAL_CONSISTENCY_WARNING`.

    With loadings :math:`\lambda_i` and uniquenesses :math:`\psi_i` of the congeneric
    one-factor model :math:`\Sigma=\lambda\lambda^\top+\Psi` fitted to the item covariance
    matrix, :math:`\omega=\dfrac{(\sum\lambda_i)^2}{(\sum\lambda_i)^2+\sum\psi_i}` (model-implied
    total-score variance in the denominator; McDonald 1999). Also returned:
    ``omega_observed_denominator`` using the observed variance of the item sum, standardized
    loadings, and the ML chi-square test of one-factor fit (Bartlett-corrected).
    """
    X, n_drop = _items_matrix(items)
    n, p = X.shape
    if p < 3:
        raise ValueError("omega needs >= 3 items (a one-factor model is not identified for 2)")
    S = np.cov(X, rowvar=False, ddof=1)
    lam, psi, ok = _one_factor_ml(S)
    num = lam.sum() ** 2
    omega = num / (num + psi.sum())
    omega_obs = num / S.sum()
    sig = np.outer(lam, lam) + np.diag(psi)
    fmin = (np.linalg.slogdet(sig)[1] + np.trace(S @ np.linalg.inv(sig))
            - np.linalg.slogdet(S)[1] - p)
    df = ((p - 1) ** 2 - (p + 1)) / 2  # p(p+1)/2 - 2p
    chi2 = (n - 1 - (2 * p + 5) / 6) * fmin
    pval = float(stats.chi2.sf(chi2, df)) if df > 0 else None
    warn = [INTERNAL_CONSISTENCY_WARNING]
    if not ok:
        warn.append("one-factor ML optimisation did not report convergence")
    if np.any(psi <= 1e-5 * np.diag(S).max()):
        warn.append("Heywood case (a uniqueness at its lower bound)")
    return {"omega": float(omega), "omega_observed_denominator": float(omega_obs),
            "loadings": lam.tolist(), "uniquenesses": psi.tolist(),
            "standardized_loadings": (lam / np.sqrt(np.diag(sig))).tolist(),
            "fit_chi2": float(chi2), "fit_df": float(df), "fit_p": pval, "n": n, "k": p,
            "n_dropped": n_drop, "converged": ok,
            "method": "one-factor maximum-likelihood factor model; omega_total (McDonald 1999)",
            "assumptions": ["unidimensional (congeneric) items", "uncorrelated errors",
                            "approximately multivariate normal (ML)"],
            "warnings": warn}
