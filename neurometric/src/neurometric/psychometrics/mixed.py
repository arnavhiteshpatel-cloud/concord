r"""Repeated-measures linear mixed models and missing-data diagnostics.

References
----------
* Laird NM, Ware JH (1982). Random-effects models for longitudinal data. Biometrics
  38(4):963-974. [PK]
* Little RJA (1988). A test of missing completely at random for multivariate data with missing
  values. J Am Stat Assoc 83(404):1198-1202. [PK]
* Dempster AP, Laird NM, Rubin DB (1977). Maximum likelihood from incomplete data via the EM
  algorithm. J R Stat Soc B 39(1):1-38. [PK]
* Tierney N et al. naniar R package, ``mcar_test`` (airquality example: chi2 = 35.1, df = 14,
  p = 0.00142, 4 patterns) — reproduced in the test-suite. [PK]

[PK] = cited from prior knowledge, details not re-verified.
"""
from __future__ import annotations

import warnings as _warnings
from typing import Sequence

import numpy as np
import pandas as pd
from scipy import stats

__all__ = ["fit_repeated_measures_lmm", "missing_data_summary", "little_mcar_test",
           "em_mvn"]


def fit_repeated_measures_lmm(df: pd.DataFrame, outcome: str, subject_col: str,
                              time_col: str, *, covariates: Sequence[str] = (),
                              time_as: str = "numeric", random_slope: bool = False,
                              reml: bool = True, alpha: float = 0.05) -> dict:
    r"""Linear mixed model for repeated measures (statsmodels ``MixedLM``).

    Model (``time_as='numeric'``):
    :math:`y_{it}=\beta_0+\beta_1 t+\gamma^\top x_{i}+u_{0i}+u_{1i}t+e_{it}` with
    :math:`u_{0i}\sim N(0,\tau_0^2)`, optional random slope :math:`u_{1i}\sim N(0,\tau_1^2)`
    (``random_slope=True``; with covariance :math:`\tau_{01}`), :math:`e\sim N(0,\sigma^2)`.
    ``time_as='categorical'`` replaces :math:`\beta_1t` by session dummies (no shape
    assumption; random slope not available then). Covariates enter as fixed effects; string
    columns are treated as categorical.

    Returns fixed effects with Wald CIs (:math:`\hat\beta\pm z_{1-\alpha/2}SE`), variance
    components, and — for the random-intercept model — the variance-component ICC
    :math:`\tau_0^2/(\tau_0^2+\sigma^2)` (reliability of a single observation after removing
    fixed time effects; equivalent to ICC(3,1) for balanced complete data). With a random
    slope the ICC depends on time; it is reported at ``t = 0`` and flagged.

    Uses all available observations (valid under MAR given the model); subjects with a
    single observation contribute to fixed effects only.
    """
    import statsmodels.formula.api as smf

    cols = [outcome, subject_col, time_col, *covariates]
    d = df[cols].dropna().copy()
    n_drop_rows = int(len(df) - len(d))
    d = d.rename(columns={outcome: "_y", subject_col: "_subj", time_col: "_time"})
    terms = ["_time" if time_as == "numeric" else "C(_time)"]
    for c in covariates:
        terms.append(f"Q('{c}')" if pd.api.types.is_numeric_dtype(d[c])
                     else f"C(Q('{c}'))")
    formula = "_y ~ " + " + ".join(terms)
    if random_slope and time_as != "numeric":
        raise ValueError("random_slope requires time_as='numeric'")
    re_formula = "~_time" if random_slope else "~1"
    md = smf.mixedlm(formula, d, groups="_subj", re_formula=re_formula)
    caught: list[str] = []
    fit = None
    with _warnings.catch_warnings(record=True) as wl:
        _warnings.simplefilter("always")
        for meth in ("lbfgs", "bfgs", "powell", "nm"):
            try:
                fit = md.fit(reml=reml, method=meth)
            except (np.linalg.LinAlgError, ValueError):
                continue
            if fit.converged:
                break
        caught = sorted({str(w.message).splitlines()[0] for w in wl})
    if fit is None:
        raise RuntimeError("MixedLM failed to fit")
    q = stats.norm.ppf(1 - alpha / 2)
    fe = []
    names = list(fit.model.exog_names)
    for i, name in enumerate(names):
        est, se = float(fit.fe_params.iloc[i]), float(fit.bse_fe.iloc[i])
        nice = name.replace("_time", time_col).replace("Q('", "").replace("')", "")
        fe.append({"term": nice, "estimate": est, "se": se, "z": est / se,
                   "p": float(2 * stats.norm.sf(abs(est / se))),
                   "ci_low": est - q * se, "ci_high": est + q * se})
    cov_re = np.asarray(fit.cov_re, float)
    vc = {"subject_intercept": float(cov_re[0, 0]), "residual": float(fit.scale)}
    warn = list(caught)
    if random_slope:
        vc["subject_slope"] = float(cov_re[1, 1])
        vc["intercept_slope_cov"] = float(cov_re[0, 1])
        warn.append("random slope model: ICC varies with time; reported ICC is at time = 0")
    icc = vc["subject_intercept"] / (vc["subject_intercept"] + vc["residual"])
    if not fit.converged:
        warn.append("MixedLM did not converge")
    if vc["subject_intercept"] < 1e-8:
        warn.append("random-intercept variance estimated at ~0 (boundary)")
    n_subj = int(d["_subj"].nunique())
    obs_per = d.groupby("_subj").size()
    return {
        "fixed_effects": fe, "variance_components": vc, "icc": float(icc),
        "icc_definition": "tau0^2 / (tau0^2 + sigma^2)",
        "n_observations": int(len(d)), "n_subjects": n_subj,
        "n_rows_dropped_missing": n_drop_rows,
        "obs_per_subject": {"min": int(obs_per.min()), "max": int(obs_per.max()),
                            "mean": float(obs_per.mean())},
        "converged": bool(fit.converged), "reml": reml, "loglik": float(fit.llf),
        "formula": formula.replace("_y", outcome).replace("_time", time_col)
                   .replace("Q('", "").replace("')", ""),
        "random_effects": "intercept + slope(time)" if random_slope else "intercept",
        "alpha": alpha,
        "method": f"linear mixed model ({'REML' if reml else 'ML'}), statsmodels MixedLM; "
                  "Wald CIs for fixed effects",
        "assumptions": ["normal random effects and residuals", "missing at random (MAR)",
                        "linear time trend" if time_as == "numeric" else "session as factor",
                        "homoscedastic residuals, conditional independence given random "
                        "effects"],
        "warnings": warn,
    }


# --------------------------------------------------------------------------- missing data
def em_mvn(X: np.ndarray, *, max_iter: int = 1000, tol: float = 1e-10) -> tuple:
    r"""ML mean and covariance of a multivariate normal from incomplete data (EM; DLR 1977).

    Rows that are entirely missing are ignored. E-step per missingness pattern:
    :math:`\hat x_m=\mu_m+\Sigma_{mo}\Sigma_{oo}^{-1}(x_o-\mu_o)`, conditional covariance
    :math:`\Sigma_{mm}-\Sigma_{mo}\Sigma_{oo}^{-1}\Sigma_{om}`; M-step: sample moments of the
    completed data. Returns ``(mu, sigma, n_iter, converged)``.
    """
    X = np.asarray(X, float)
    X = X[~np.isnan(X).all(axis=1)]
    N, p = X.shape
    miss = np.isnan(X)
    pats, inv = np.unique(miss, axis=0, return_inverse=True)
    inv = inv.ravel()
    mu = np.nanmean(X, axis=0)
    sigma = np.diag(np.nanvar(X, axis=0))
    groups = [np.where(inv == g)[0] for g in range(len(pats))]
    converged = False
    for it in range(1, max_iter + 1):
        T1 = np.zeros(p)
        T2 = np.zeros((p, p))
        for pat, rows in zip(pats, groups):
            o, m = ~pat, pat
            Xo = X[np.ix_(rows, o)]
            Xc = np.empty((len(rows), p))
            Xc[:, o] = Xo
            C = np.zeros((p, p))
            if m.any():
                Soo = sigma[np.ix_(o, o)]
                Smo = sigma[np.ix_(m, o)]
                B = np.linalg.solve(Soo, Smo.T).T  # Smo Soo^-1
                Xc[:, m] = mu[m] + (Xo - mu[o]) @ B.T
                C[np.ix_(m, m)] = sigma[np.ix_(m, m)] - B @ Smo.T
            T1 += Xc.sum(axis=0)
            T2 += Xc.T @ Xc + len(rows) * C
        mu_new = T1 / N
        sig_new = T2 / N - np.outer(mu_new, mu_new)
        delta = max(np.abs(mu_new - mu).max(), np.abs(sig_new - sigma).max())
        mu, sigma = mu_new, sig_new
        if delta < tol:
            converged = True
            break
    return mu, sigma, it, converged


def little_mcar_test(data) -> dict:
    r"""Little's (1988) chi-square test of missing completely at random (MCAR).

    :math:`d^2=\sum_{j=1}^{J}n_j(\bar y_{j}-\hat\mu_{o_j})^\top\hat\Sigma_{o_j}^{-1}
    (\bar y_j-\hat\mu_{o_j})`, with :math:`J` missingness patterns, :math:`\bar y_j` the
    observed-variable means in pattern :math:`j`, and :math:`\hat\mu,\hat\Sigma` the EM
    maximum-likelihood estimates. Under MCAR (and multivariate normality)
    :math:`d^2\sim\chi^2_{\sum_j p_j-p}`. Rows with all values missing are excluded (as in
    naniar's ``mcar_test``).

    Caveats: a non-significant result does not prove MCAR (low power with small n); the test
    assumes multivariate normality and cannot distinguish MAR from MNAR.
    """
    X = np.asarray(data, float)
    X = X[~np.isnan(X).all(axis=1)]
    n, p = X.shape
    mu, sigma, n_it, conv = em_mvn(X)
    miss = np.isnan(X)
    pats, inv = np.unique(miss, axis=0, return_inverse=True)
    inv = inv.ravel()
    d2 = 0.0
    dfsum = 0
    for g, pat in enumerate(pats):
        o = ~pat
        rows = X[inv == g][:, o]
        diff = rows.mean(axis=0) - mu[o]
        d2 += len(rows) * diff @ np.linalg.solve(sigma[np.ix_(o, o)], diff)
        dfsum += int(o.sum())
    df = dfsum - p
    pval = float(stats.chi2.sf(d2, df)) if df > 0 else None
    return {"statistic": float(d2), "df": int(df), "p": pval, "n_patterns": int(len(pats)),
            "n": int(n), "em_iterations": int(n_it), "em_converged": bool(conv),
            "method": "Little (1988) MCAR chi-square with EM (ML) estimates",
            "assumptions": ["multivariate normality", "large-sample chi-square approximation"],
            "warnings": ([] if df > 0 else ["no missingness (or one pattern): test undefined"])}


def missing_data_summary(df: pd.DataFrame, subject_col: str, session_col: str,
                         value_cols: Sequence[str], *,
                         expected_sessions: Sequence | None = None) -> dict:
    r"""Describe missingness of repeated measures.

    * per-variable missingness over the expected subject x session grid (a session row that is
      absent counts as missing for every variable);
    * per variable, subjects classified as ``complete``, ``monotone`` (dropout: once missing,
      missing at all later sessions) or ``intermittent`` (a missing session followed by an
      observed one), using the session order of ``expected_sessions`` (default: sorted unique);
    * missingness patterns (subject x session matrix, per variable) with counts;
    * Little's MCAR test on the wide subject x session matrix of each variable
      (:func:`little_mcar_test`) when there is any missingness and >= 2 sessions.
    """
    sessions = list(expected_sessions) if expected_sessions is not None \
        else sorted(df[session_col].dropna().unique())
    subjects = sorted(df[subject_col].dropna().unique())
    grid = pd.MultiIndex.from_product([subjects, sessions], names=[subject_col, session_col])
    full = df.set_index([subject_col, session_col])[list(value_cols)]
    if full.index.duplicated().any():
        raise ValueError("duplicate subject-session rows")
    full = full.reindex(grid)
    per_var, patterns, mcar = {}, {}, {}
    for v in value_cols:
        w = full[v].unstack(session_col)[sessions]
        M = w.isna().to_numpy()
        cls = []
        for row in M:
            if not row.any():
                cls.append("complete")
            elif row.all():
                cls.append("all_missing")
            else:
                first = int(np.argmax(row))
                cls.append("monotone" if row[first:].all() else "intermittent")
        cls = pd.Series(cls)
        per_var[v] = {"n_cells": int(M.size), "n_missing": int(M.sum()),
                      "prop_missing": float(M.mean()),
                      "prop_missing_by_session": dict(zip(map(str, sessions),
                                                          M.mean(axis=0).tolist())),
                      "subjects_complete": int((cls == "complete").sum()),
                      "subjects_monotone": int((cls == "monotone").sum()),
                      "subjects_intermittent": int((cls == "intermittent").sum()),
                      "subjects_all_missing": int((cls == "all_missing").sum())}
        pat_str = ["".join("." if m else "X" for m in row) for row in M]
        patterns[v] = pd.Series(pat_str).value_counts().to_dict()
        if M.any() and len(sessions) >= 2 and (~M.all(axis=1)).sum() > len(sessions):
            try:
                mcar[v] = little_mcar_test(w.to_numpy(float))
            except np.linalg.LinAlgError:
                mcar[v] = {"statistic": None, "p": None,
                           "warnings": ["singular covariance; MCAR test not computed"]}
    return {"sessions": [str(s) for s in sessions], "n_subjects": len(subjects),
            "per_variable": per_var,
            "patterns": patterns, "pattern_legend": "X = observed, . = missing, in session "
                                                    "order",
            "little_mcar": mcar,
            "method": "missingness over the full subject x session grid; Little (1988) MCAR "
                      "test per variable on the wide session matrix",
            "assumptions": ["absent session rows are missing data (not by design)"],
            "warnings": [] if not mcar else
            ["Little's test has low power in small samples; non-rejection does not establish "
             "MCAR, and it cannot separate MAR from MNAR"]}
