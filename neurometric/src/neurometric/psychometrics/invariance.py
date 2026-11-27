r"""Pragmatic measurement-invariance checks across groups (e.g. input modality).

Scope (v1)
----------
NeuroMetric scores are single task metrics (throughput, error rate, ...), not multi-item latent
scales. The questions we can answer with the data we will have are:

(a) *Is the score equally reliable in each group?* — compare test–retest ICCs across groups
    with a bootstrap CI of the difference (:func:`compare_icc_across_groups`), optionally an
    equivalence decision against a user-given margin;
(b) *Are mean scores equivalent across groups?* — two one-sided tests (TOST) against a
    user-given equivalence margin (:func:`tost`).

Out of scope for v1, by design — see :data:`INVARIANCE_SCOPE_NOTE`.

References
----------
* Schuirmann DJ (1987). A comparison of the two one-sided tests procedure and the power
  approach for assessing the equivalence of average bioavailability. J Pharmacokinet Biopharm
  15(6):657-680. [PK]
* Lakens D (2017). Equivalence tests: a practical primer for t tests, correlations, and
  meta-analyses. Soc Psychol Personal Sci 8(4):355-362. [PK]
* Vandenberg RJ, Lance CE (2000). A review and synthesis of the measurement invariance
  literature. Organ Res Methods 3(1):4-70. [PK]
* Meredith W (1993). Measurement invariance, factor analysis and factorial invariance.
  Psychometrika 58:525-543. [PK]

[PK] = cited from prior knowledge, details not re-verified.
"""
from __future__ import annotations

from itertools import combinations

import numpy as np
import pandas as pd
from scipy import stats

from ._util import as_1d, paired_arrays
from .reliability import ICC_FORMS, _icc_from_ms, anova_mean_squares, to_wide

__all__ = ["tost", "compare_icc_across_groups", "INVARIANCE_SCOPE_NOTE"]

INVARIANCE_SCOPE_NOTE = (
    "Formal measurement invariance (multi-group confirmatory factor analysis testing configural, "
    "metric/weak, scalar/strong and strict invariance; Meredith 1993; Vandenberg & Lance 2000) "
    "and differential item functioning are OUT OF SCOPE for v1 because: (1) NeuroMetric task "
    "scores are single observed metrics, not multiple reflective indicators of one latent "
    "factor, so a factor model per group is not identified or not meaningful; (2) "
    "multi-group CFA needs several hundred participants per group for stable estimates, far "
    "beyond the planned pilot samples; (3) no CFA/SEM engine is among the vetted dependencies. "
    "v1 therefore checks the observable consequences that matter for using a score across "
    "input modalities: equal reliability (ICC difference with bootstrap CI) and equivalent "
    "means within a pre-specified margin (TOST). Neither establishes that the score measures "
    "the same construct in each group; that requires construct-validity evidence per group."
)


def tost(x, y=None, *, low: float, high: float | None = None, paired: bool = False,
         welch: bool = True, alpha: float = 0.05) -> dict:
    r"""Two one-sided tests (TOST) for equivalence of means (Schuirmann 1987).

    Equivalence region :math:`(\Delta_L,\Delta_U)` for :math:`\mu_x-\mu_y`; ``high`` defaults to
    ``-low`` if ``low < 0`` else ``low`` with ``low -> -low`` (symmetric margin given as one
    positive number). Tests :math:`H_{01}:\Delta\le\Delta_L` and :math:`H_{02}:\Delta\ge
    \Delta_U`; :math:`p_{TOST}=\max(p_1,p_2)`. Equivalence is declared if
    :math:`p_{TOST}<\alpha`, equivalently if the :math:`1-2\alpha` CI lies within the margin.

    Independent groups use Welch's SE/df (``welch=True``) or the pooled-variance Student test;
    ``paired=True`` uses the differences; ``y=None`` is a one-sample test against 0.
    The margin must be justified a priori (e.g. smaller than the MDC or a fraction of the
    between-subject SD); it cannot be chosen after seeing the data.
    """
    if high is None:
        m = abs(low)
        low, high = -m, m
    if not low < high:
        raise ValueError("need low < high")
    if y is None or paired:
        if paired:
            a, b, _ = paired_arrays(x, y)
            d = a - b
        else:
            d = as_1d(x)
        n = len(d)
        diff, se, df = d.mean(), d.std(ddof=1) / np.sqrt(n), n - 1
        design = "paired" if paired else "one-sample"
    else:
        x, y = as_1d(x), as_1d(y)
        n1, n2 = len(x), len(y)
        v1, v2 = x.var(ddof=1), y.var(ddof=1)
        diff = x.mean() - y.mean()
        if welch:
            se = np.sqrt(v1 / n1 + v2 / n2)
            df = (v1 / n1 + v2 / n2) ** 2 / ((v1 / n1) ** 2 / (n1 - 1) + (v2 / n2) ** 2 / (n2 - 1))
        else:
            sp2 = ((n1 - 1) * v1 + (n2 - 1) * v2) / (n1 + n2 - 2)
            se = np.sqrt(sp2 * (1 / n1 + 1 / n2))
            df = n1 + n2 - 2
        design = "independent (Welch)" if welch else "independent (Student)"
    t1 = (diff - low) / se
    t2 = (diff - high) / se
    p1 = stats.t.sf(t1, df)
    p2 = stats.t.cdf(t2, df)
    p = max(p1, p2)
    tq = stats.t.ppf(1 - alpha, df)
    ci = (diff - tq * se, diff + tq * se)
    return {"diff": float(diff), "se": float(se), "df": float(df), "low": float(low),
            "high": float(high), "t_lower": float(t1), "p_lower": float(p1),
            "t_upper": float(t2), "p_upper": float(p2), "p": float(p),
            "ci_1_minus_2alpha": [float(ci[0]), float(ci[1])],
            "equivalent": bool(p < alpha), "alpha": alpha, "design": design,
            "method": "TOST (Schuirmann 1987)",
            "assumptions": ["margin pre-specified", "approx. normal means"]}


def _icc_value(W: np.ndarray, form: str) -> float:
    return float(_icc_from_ms(anova_mean_squares(W))[form]["icc"])


def compare_icc_across_groups(df: pd.DataFrame, score_col: str, subject_col: str,
                              session_col: str, group_col: str, *, form: str = "2,1",
                              margin: float | None = None, n_boot: int = 2000,
                              alpha: float = 0.05, seed: int = 0) -> dict:
    r"""Compare test–retest ICCs between groups (e.g. input modalities).

    Per group: complete-case ICC of ``form`` with its McGraw & Wong CI. For each pair of groups
    the difference :math:`\Delta=ICC_a-ICC_b` gets a percentile bootstrap CI from resampling
    subjects with replacement *within* each group (independent groups; seeded). If ``margin`` is
    given, reliability is declared equivalent when the :math:`1-2\alpha` bootstrap CI lies
    inside :math:`(-margin, margin)` (CI-inclusion form of TOST).

    Subjects must belong to exactly one group.
    """
    if form not in ICC_FORMS:
        raise ValueError(f"unknown form {form}")
    gmap = df.groupby(subject_col)[group_col].nunique()
    if (gmap > 1).any():
        raise ValueError("some subjects appear in more than one group")
    rng = np.random.default_rng(seed)
    per_group, mats = {}, {}
    from .reliability import icc as _icc
    for g, sub in df.groupby(group_col):
        w = to_wide(sub, subject_col, session_col, score_col)
        W = w.dropna().to_numpy(float)
        mats[g] = W
        r = _icc(w, forms=[form], alpha=alpha)
        per_group[str(g)] = {**r["table"][0], "n_subjects_used": r["n_subjects_used"],
                             "n_subjects_dropped": r["n_subjects_dropped"]}
    boots = {}
    for g, W in mats.items():
        b = np.empty(n_boot)
        n = W.shape[0]
        for i in range(n_boot):
            b[i] = _icc_value(W[rng.integers(0, n, n)], form)
        boots[g] = b
    comps = []
    for a, b in combinations(sorted(mats, key=str), 2):
        diff = _icc_value(mats[a], form) - _icc_value(mats[b], form)
        db = boots[a] - boots[b]
        db = db[np.isfinite(db)]
        ci = np.quantile(db, [alpha / 2, 1 - alpha / 2])
        ci2 = np.quantile(db, [alpha, 1 - alpha])
        row = {"group_a": str(a), "group_b": str(b), "icc_diff": float(diff),
               "ci_low": float(ci[0]), "ci_high": float(ci[1]),
               "ci_1_minus_2alpha": [float(ci2[0]), float(ci2[1])],
               "margin": margin, "equivalent": None}
        if margin is not None:
            row["equivalent"] = bool(-margin < ci2[0] and ci2[1] < margin)
        comps.append(row)
    warn = [INVARIANCE_SCOPE_NOTE]
    if any(v["n_subjects_used"] < 20 for v in per_group.values()):
        warn.append("fewer than 20 complete subjects in a group: bootstrap ICC CIs are "
                    "unstable and equivalence is unlikely to be demonstrable")
    return {"form": f"ICC({form})", "per_group": per_group, "comparisons": comps,
            "n_boot": n_boot, "seed": seed, "alpha": alpha,
            "method": "per-group ANOVA ICC; difference CI by stratified subject bootstrap "
                      "(percentile)",
            "assumptions": ["subjects independent and nested in groups",
                            "same session protocol in each group"],
            "warnings": warn}
