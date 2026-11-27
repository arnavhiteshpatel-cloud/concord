"""Experiment R — statistical implementation verification of ``neurometric.psychometrics``.

Three kinds of evidence:

(a) published worked examples (Shrout & Fleiss 1979 ICC table; Bland & Altman 1986 PEFR data;
    naniar's ``mcar_test(airquality)``; pingouin documentation examples);
(b) agreement with independent implementations on random data (pingouin, scipy, statsmodels);
(c) simulated data with KNOWN truth: recovery of the true value and 95 % CI coverage.

The slower full coverage study (``verify_coverage.run_study``) is marked ``slow`` and skipped
unless ``-m slow`` is given or ``NEUROMETRIC_RUN_SLOW=1`` is set.
"""
import json
import os

import numpy as np
import pandas as pd
import pytest
from scipy import stats

import neurometric.psychometrics as P
from neurometric.psychometrics import reliability as R

pg = pytest.importorskip("pingouin")

# Shrout & Fleiss (1979) Table 2: 6 targets x 4 judges
SF_Y = np.array([[9, 2, 5, 8], [6, 1, 3, 2], [8, 4, 6, 8],
                 [7, 1, 2, 6], [10, 5, 6, 9], [6, 2, 4, 7]], float)
SF_PUBLISHED = {"1,1": .17, "2,1": .29, "3,1": .71, "1,k": .44, "2,k": .62, "3,k": .91}


def _long(Y):
    return pd.DataFrame(Y).rename_axis("subject").reset_index() \
        .melt(id_vars="subject", var_name="session", value_name="score")


# ============================================================ (a) published worked examples
def test_shrout_fleiss_1979_icc_values():
    tab = P.icc_table(SF_Y)
    for f, v in SF_PUBLISHED.items():
        assert round(tab.loc[f"ICC({f})", "icc"], 2) == v, f


def test_shrout_fleiss_1979_mean_squares():
    # published: BMS = 11.24, WMS = 6.26, JMS = 32.49, EMS = 1.02
    ms = R.anova_mean_squares(SF_Y)
    assert round(ms["MSR"], 2) == 11.24
    assert round(ms["MSW"], 2) == 6.26
    assert round(ms["MSC"], 2) == 32.49
    assert round(ms["MSE"], 2) == 1.02


def test_shrout_fleiss_long_and_wide_inputs_agree():
    a = P.icc(SF_Y)["table"]
    b = P.icc(_long(SF_Y), "subject", "session", "score")["table"]
    for x, y in zip(a, b):
        assert x["icc"] == pytest.approx(y["icc"], abs=1e-12)
        assert x["ci_low"] == pytest.approx(y["ci_low"], abs=1e-12)


# Bland & Altman (1986) Lancet, peak expiratory flow rate, Wright vs mini Wright meter (first
# readings). Published: mean difference -2.1 l/min, SD 38.8, r = 0.94, limits = mean +/- 2 SD
# computed from those ROUNDED values (-2.1 -/+ 77.6 = -79.7 / 75.5). [PK: data and values
# recalled from the paper, not re-verified]
BA_WRIGHT = [494, 395, 516, 434, 476, 557, 413, 442, 650, 433, 417, 656, 267, 478, 178, 423, 427]
BA_MINI = [512, 430, 520, 428, 500, 600, 364, 380, 658, 445, 432, 626, 260, 477, 259, 350, 451]


def test_bland_altman_1986_pefr_example():
    r = P.bland_altman(BA_WRIGHT, BA_MINI, loa_z=2.0, loa_ci="ba1986")
    assert round(r["bias"], 1) == -2.1
    assert round(r["sd_diff"], 1) == 38.8
    assert round(r["bias"], 1) - 2 * round(r["sd_diff"], 1) == pytest.approx(-79.7)
    assert round(r["bias"], 1) + 2 * round(r["sd_diff"], 1) == pytest.approx(75.5)
    # unrounded limits differ from the published ones only by the intermediate rounding
    assert abs(r["loa_low"] - -79.7) < 0.1 and abs(r["loa_high"] - 75.5) < 0.1
    assert round(np.corrcoef(BA_WRIGHT, BA_MINI)[0, 1], 2) == 0.94
    # 1986 shortcut SE = sqrt(3 s^2 / n)
    assert r["loa_se"] == pytest.approx(np.sqrt(3 * r["sd_diff"] ** 2 / 17))


# airquality (R datasets), embedded; naniar::mcar_test(airquality) gives
# statistic 35.1, df 14, p.value 0.00142, missing.patterns 4. [PK]
_AQ = {
    "Ozone": "41 36 12 18 NA 28 23 19 8 NA 7 16 11 14 18 14 34 6 30 11 1 11 4 32 NA NA NA 23 45 "
             "115 37 NA NA NA NA NA NA 29 NA 71 39 NA NA 23 NA NA 21 37 20 12 13 NA NA NA NA NA "
             "NA NA NA NA NA 135 49 32 NA 64 40 77 97 97 85 NA 10 27 NA 7 48 35 61 79 63 16 NA "
             "NA 80 108 20 52 82 50 64 59 39 9 16 78 35 66 122 89 110 NA NA 44 28 65 NA 22 59 "
             "23 31 44 21 9 NA 45 168 73 NA 76 118 84 85 96 78 73 91 47 32 20 23 21 24 44 21 28 "
             "9 13 46 18 13 24 16 13 23 36 7 14 30 NA 14 18 20",
    "Solar.R": "190 118 149 313 NA NA 299 99 19 194 NA 256 290 274 65 334 307 78 322 44 8 320 "
               "25 92 66 266 NA 13 252 223 279 286 287 242 186 220 264 127 273 291 323 259 250 "
               "148 332 322 191 284 37 120 137 150 59 91 250 135 127 47 98 31 138 269 248 236 "
               "101 175 314 276 267 272 175 139 264 175 291 48 260 274 285 187 220 7 258 295 294 "
               "223 81 82 213 275 253 254 83 24 77 NA NA NA 255 229 207 222 137 192 273 157 64 "
               "71 51 115 244 190 259 36 255 212 238 215 153 203 225 237 188 167 197 183 189 95 "
               "92 252 220 230 259 236 259 238 24 112 237 224 27 238 201 238 14 139 49 20 193 "
               "145 191 131 223",
    "Wind": "7.4 8 12.6 11.5 14.3 14.9 8.6 13.8 20.1 8.6 6.9 9.7 9.2 10.9 13.2 11.5 12 18.4 "
            "11.5 9.7 9.7 16.6 9.7 12 16.6 14.9 8 12 14.9 5.7 7.4 8.6 9.7 16.1 9.2 8.6 14.3 9.7 "
            "6.9 13.8 11.5 10.9 9.2 8 13.8 11.5 14.9 20.7 9.2 11.5 10.3 6.3 1.7 4.6 6.3 8 8 10.3 "
            "11.5 14.9 8 4.1 9.2 9.2 10.9 4.6 10.9 5.1 6.3 5.7 7.4 8.6 14.3 14.9 14.9 14.3 6.9 "
            "10.3 6.3 5.1 11.5 6.9 9.7 11.5 8.6 8 8.6 12 7.4 7.4 7.4 9.2 6.9 13.8 7.4 6.9 7.4 "
            "4.6 4 10.3 8 8.6 11.5 11.5 11.5 9.7 11.5 10.3 6.3 7.4 10.9 10.3 15.5 14.3 12.6 9.7 "
            "3.4 8 5.7 9.7 2.3 6.3 6.3 6.9 5.1 2.8 4.6 7.4 15.5 10.9 10.3 10.9 9.7 14.9 15.5 6.3 "
            "10.9 11.5 6.9 13.8 10.3 10.3 8 12.6 9.2 10.3 10.3 16.6 6.9 13.2 14.3 8 11.5",
    "Temp": "67 72 74 62 56 66 65 59 61 69 74 69 66 68 58 64 66 57 68 62 59 73 61 61 57 58 57 "
            "67 81 79 76 78 74 67 84 85 79 82 87 90 87 93 92 82 80 79 77 72 65 73 76 77 76 76 "
            "76 75 78 73 80 77 83 84 85 81 84 83 83 88 92 92 89 82 73 81 91 80 81 82 84 87 85 "
            "74 81 82 86 85 82 86 88 86 83 81 81 81 82 86 85 87 89 90 90 92 86 86 82 80 79 77 "
            "79 76 78 78 77 72 75 79 81 86 88 97 94 96 94 91 92 93 93 87 84 80 78 75 73 81 76 "
            "77 71 71 78 67 76 68 82 64 71 81 69 63 70 77 75 76 68",
}


def _airquality():
    d = {k: [np.nan if t == "NA" else float(t) for t in v.split()] for k, v in _AQ.items()}
    days = [31, 30, 31, 31, 30]
    d["Month"] = [m for m, nd in zip(range(5, 10), days) for _ in range(nd)]
    d["Day"] = [day for nd in days for day in range(1, nd + 1)]
    return pd.DataFrame(d)


def test_little_mcar_airquality_matches_naniar():
    aq = _airquality()
    assert aq.shape == (153, 6) and aq.isna().sum().sum() == 44
    r = P.little_mcar_test(aq.to_numpy())
    assert round(r["statistic"], 1) == 35.1
    assert r["df"] == 14
    assert r["n_patterns"] == 4
    assert r["p"] == pytest.approx(0.00142, abs=5e-6)


def test_pingouin_documented_examples_tost_and_wine_icc():
    a, b = [4, 7, 8, 6, 3, 2], [6, 8, 7, 10, 11, 9]
    # pingouin docstring: TOST p = 0.965097 (Student), paired bound 0.5 -> 0.954854
    assert P.tost(a, b, low=1, welch=False)["p"] == pytest.approx(0.965097, abs=1e-6)
    assert P.tost(a, b, low=0.5, paired=True)["p"] == pytest.approx(0.954854, abs=1e-6)
    wine = pg.read_dataset("icc")
    tab = P.icc_table(wine, "Wine", "Judge", "Scores")
    # pingouin docstring rounded values
    assert round(tab.loc["ICC(1,1)", "icc"], 3) == 0.728
    assert round(tab.loc["ICC(3,k)", "icc"], 3) == 0.915


def test_spearman_brown_textbook_values():
    assert P.spearman_brown(0.5, 2) == pytest.approx(2 / 3)
    assert P.spearman_brown(0.8, 0.5) == pytest.approx(0.4 / 0.6)  # halving the test
    assert P.spearman_brown_length(0.5, 0.8) == pytest.approx(4.0)
    # round trip
    for rho, m in [(0.3, 3.0), (0.62, 1.7), (0.9, 0.25)]:
        assert P.spearman_brown_length(rho, P.spearman_brown(rho, m)) == pytest.approx(m)
    # ICC(1,k) and ICC(3,k) are exactly the Spearman–Brown step-up of the single forms
    tab = P.icc_table(SF_Y)
    for one, avg in (("1,1", "1,k"), ("3,1", "3,k"), ("2,1", "2,k")):
        if one == "2,1":
            continue  # A,k is not an exact SB of A,1 (session term enters differently)
        assert tab.loc[f"ICC({avg})", "icc"] == pytest.approx(
            P.spearman_brown(tab.loc[f"ICC({one})", "icc"], 4))
        assert tab.loc[f"ICC({avg})", "ci_low"] == pytest.approx(
            P.spearman_brown(tab.loc[f"ICC({one})", "ci_low"], 4))


# ===================================================== (b) independent implementations
@pytest.mark.parametrize("seed,n,k,miss", [(1, 12, 3, 0), (2, 40, 2, 0), (3, 25, 5, 3),
                                           (4, 8, 4, 0), (5, 60, 3, 6)])
def test_icc_matches_pingouin(seed, n, k, miss):
    rng = np.random.default_rng(seed)
    Y = rng.normal(0, 1, (n, 1)) * rng.uniform(0.3, 2) + rng.normal(0, 1, (n, k)) \
        + rng.normal(0, 0.5, k)
    if miss:
        Y[rng.choice(n, miss, replace=False), rng.integers(0, k, miss)] = np.nan
    long = _long(Y)
    ref = pg.intraclass_corr(long, "subject", "session", "score", nan_policy="omit") \
        .set_index("Type")
    mine = P.icc(long, "subject", "session", "score")
    assert mine["n_subjects_dropped"] == int(np.isnan(Y).any(axis=1).sum())
    names = {"1,1": "ICC(1,1)", "2,1": "ICC(A,1)", "3,1": "ICC(C,1)", "1,k": "ICC(1,k)",
             "2,k": "ICC(A,k)", "3,k": "ICC(C,k)"}
    for row in mine["table"]:
        r = ref.loc[names[row["key"]]]
        assert row["icc"] == pytest.approx(r["ICC"], abs=1e-10)
        assert row["F"] == pytest.approx(r["F"], rel=1e-10)
        assert row["df2"] == r["df2"]
        assert row["p"] == pytest.approx(r["pval"], rel=1e-8, abs=1e-14)
        # pingouin rounds its CI to 2 decimals -> agreement to rounding precision
        assert row["ci_low"] == pytest.approx(r["CI95"][0], abs=0.005 + 1e-9)
        assert row["ci_high"] == pytest.approx(r["CI95"][1], abs=0.005 + 1e-9)


def test_icc_ci_full_precision_against_formula():
    """Full-precision check of the M&W CIs against an independent re-derivation."""
    ms = R.anova_mean_squares(SF_Y)
    n, k = 6, 4
    F = ms["MSR"] / ms["MSE"]
    fl = F / stats.f.ppf(0.975, n - 1, (n - 1) * (k - 1))
    fu = F * stats.f.ppf(0.975, (n - 1) * (k - 1), n - 1)
    t = P.icc_table(SF_Y)
    assert t.loc["ICC(3,1)", "ci_low"] == pytest.approx((fl - 1) / (fl + k - 1), rel=1e-12)
    assert t.loc["ICC(3,1)", "ci_high"] == pytest.approx((fu - 1) / (fu + k - 1), rel=1e-12)
    # A,k CI equals the Spearman–Brown step-up of the A,1 CI
    lo1, hi1 = t.loc["ICC(2,1)", ["ci_low", "ci_high"]]
    assert t.loc["ICC(2,k)", "ci_low"] == pytest.approx(P.spearman_brown(lo1, k), rel=1e-10)
    assert t.loc["ICC(2,k)", "ci_high"] == pytest.approx(P.spearman_brown(hi1, k), rel=1e-10)
    # GCI exists for agreement forms only and brackets the estimate
    assert t.loc["ICC(2,1)", "gci_low"] < t.loc["ICC(2,1)", "icc"] < t.loc["ICC(2,1)", "gci_high"]
    rows = {r["key"]: r for r in P.icc(SF_Y)["table"]}
    assert rows["3,1"]["gci_low"] is None and rows["2,k"]["gci_low"] is not None


@pytest.mark.parametrize("form", ["1,1", "2,1", "3,1", "2,k"])
def test_mixed_model_icc_equals_anova_for_balanced_data(form):
    """REML variance components == ANOVA estimators for balanced data (positive components)."""
    rng = np.random.default_rng(11)
    Y = rng.normal(0, 1, (40, 1)) + rng.normal(0, 0.6, (40, 3)) + np.array([0, 0.5, 1.2])
    if form == "1,1":
        Y = Y - Y.mean(axis=0) + rng.normal(0, 0.01, 3)  # one-way data: no session effect
    m = P.icc_mixed(Y, form=form)
    a = P.icc_table(Y).loc[f"ICC({form})", "icc"]
    assert m["icc"] == pytest.approx(a, abs=2e-3)


def test_mixed_model_icc_handles_unbalanced_and_reports():
    rng = np.random.default_rng(12)
    Y = rng.normal(0, 1, (30, 1)) + rng.normal(0, 0.5, (30, 3))
    Y[rng.random(Y.shape) < 0.2] = np.nan
    r = P.icc(Y, missing="mixed", forms=["2,1", "3,1"])
    kept = ~np.isnan(Y).all(axis=1)  # subjects with no observation are dropped
    assert r["missing"] == "mixed" and r["n_missing_cells"] == int(np.isnan(Y[kept]).sum())
    assert 0.6 < r["table"][0]["icc"] < 0.95
    cc = P.icc(Y)
    assert cc["n_subjects_dropped"] > 0 and any("dropped" in w for w in cc["warnings"])


def test_cronbach_alpha_matches_pingouin():
    rng = np.random.default_rng(3)
    X = rng.normal(0, 1, (80, 1)) + rng.normal(0, 1.2, (80, 6))
    a = P.cronbach_alpha(X)
    ref, ci = pg.cronbach_alpha(pd.DataFrame(X))
    assert a["alpha"] == pytest.approx(ref, abs=1e-12)
    assert a["ci_low"] == pytest.approx(ci[0], abs=5e-4 + 1e-9)
    assert a["ci_high"] == pytest.approx(ci[1], abs=5e-4 + 1e-9)
    assert "ONE construct" in a["warnings"][0]
    assert "ONE construct" in P.cronbach_alpha.__doc__ or "ONE construct" in \
        P.INTERNAL_CONSISTENCY_WARNING


def test_omega_loadings_match_statsmodels_ml_factor():
    from statsmodels.multivariate.factor import Factor
    rng = np.random.default_rng(1)
    lam = np.array([1.0, 0.8, 0.6, 0.5, 0.9])
    psi = np.array([0.5, 0.6, 0.7, 0.8, 0.4])
    X = rng.normal(size=(600, 1)) * lam + rng.normal(size=(600, 5)) * np.sqrt(psi)
    om = P.mcdonald_omega(X)
    ref = np.abs(np.real(Factor(X, n_factor=1, method="ml").fit().loadings.ravel()))
    np.testing.assert_allclose(om["standardized_loadings"], ref, atol=1e-4)
    true_omega = lam.sum() ** 2 / (lam.sum() ** 2 + psi.sum())
    assert om["omega"] == pytest.approx(true_omega, abs=0.03)
    assert om["fit_p"] > 0.001  # one-factor model is true


def test_effect_sizes_match_pingouin():
    rng = np.random.default_rng(4)
    for n1, n2 in [(8, 11), (25, 30), (60, 45)]:
        x, y = rng.normal(0.4, 1, n1), rng.normal(0, 1.3, n2)
        assert P.cohens_d(x, y) == pytest.approx(pg.compute_effsize(x, y, eftype="cohen"))
        ga = P.hedges_g(x, y, correction="approx", ci="normal")
        assert ga["g"] == pytest.approx(pg.compute_effsize(x, y, eftype="hedges"), rel=1e-12)
        # Documented discrepancy: pingouin.compute_esci uses the Hedges-Olkin SE with a t
        # critical value (df = n1+n2-2); Hedges & Olkin (and we) use z. Same SE otherwise:
        ci = pg.compute_esci(stat=ga["g"], nx=n1, ny=n2, eftype="cohen", decimals=10)
        se = (ga["g"] - ga["ci_low"]) / stats.norm.ppf(0.975)
        tcrit = stats.t.ppf(0.975, n1 + n2 - 2)
        assert ga["g"] - tcrit * se == pytest.approx(ci[0], abs=1e-8)
        assert ga["g"] + tcrit * se == pytest.approx(ci[1], abs=1e-8)
        ge = P.hedges_g(x, y)  # exact J
        assert abs(ge["g"] - ga["g"]) < 2e-3 * abs(ga["g"]) + 1e-12
        assert ge["ci_low"] < ge["g"] < ge["ci_high"]
        # paired d_z
        yy = x + rng.normal(0.3, 1, n1)
        assert P.cohens_dz(x, yy)["dz"] == pytest.approx(
            pg.compute_effsize(x, yy, paired=True, eftype="cohen_dz"), rel=1e-12)
        # Cliff's delta: brute force and = 2*AUC - 1 = 2*CLES - 1
        brute = np.sign(x[:, None] - y[None, :]).mean()
        assert P.cliffs_delta(x, y) == pytest.approx(brute, abs=1e-12)
        assert P.cliffs_delta(x, y) == pytest.approx(
            2 * pg.compute_effsize(x, y, eftype="cles") - 1, abs=1e-12)


def test_hedges_exact_correction_values():
    from scipy.special import gamma
    for df in (5, 10, 38):
        J = gamma(df / 2) / (np.sqrt(df / 2) * gamma((df - 1) / 2))
        assert P.hedges_correction(df) == pytest.approx(J, rel=1e-12)
        assert abs(P.hedges_correction(df, "approx") - J) < 2e-3


def test_noncentral_t_ci_handles_extreme_effects():
    x = np.arange(10.0)
    r = P.hedges_g(x + 30, x)
    assert np.isfinite(r["ci_low"]) and r["ci_low"] < r["g"] < r["ci_high"]
    r = P.cohens_dz([-5.1, -4.9, -5.3, -4.8, -5.0, -5.2])
    assert np.isfinite(r["ci_high"]) and r["ci_low"] < r["dz"] < r["ci_high"]


def test_auc_and_delong_against_scipy_and_bruteforce():
    rng = np.random.default_rng(6)
    x = np.round(rng.normal(1, 1, 23), 1)
    y = np.round(rng.normal(0, 1, 31), 1)  # rounding creates ties
    U = stats.mannwhitneyu(x, y).statistic
    a = P.auc_delong(x, y)
    assert a["auc"] == pytest.approx(U / (len(x) * len(y)), abs=1e-12)
    psi = (x[:, None] > y[None, :]) + 0.5 * (x[:, None] == y[None, :])
    v10, v01 = psi.mean(axis=1), psi.mean(axis=0)
    var = v10.var(ddof=1) / len(x) + v01.var(ddof=1) / len(y)
    assert a["se"] == pytest.approx(np.sqrt(var), rel=1e-12)
    b = P.auc_bootstrap(x, y, n_boot=1500, seed=1)
    assert b["auc"] == a["auc"] and b["se"] == pytest.approx(a["se"], rel=0.2)


def test_known_groups_matches_scipy_and_pingouin():
    rng = np.random.default_rng(8)
    x, y = rng.normal(1, 1, 20), rng.normal(0, 2, 26)
    r = P.known_groups(x, y, expected="x>y")
    ref = pg.ttest(x, y, correction=True)
    assert r["welch_t"]["t"] == pytest.approx(ref["T"].iloc[0], rel=1e-10)
    assert r["welch_t"]["p"] == pytest.approx(ref["p_val"].iloc[0], rel=1e-8)
    assert r["welch_t"]["df"] == pytest.approx(ref["dof"].iloc[0], rel=1e-10)
    assert r["mann_whitney"]["p"] == pytest.approx(
        stats.mannwhitneyu(x, y, alternative="two-sided").pvalue)
    assert r["auc"]["auc"] == pytest.approx(
        stats.mannwhitneyu(x, y).statistic / (20 * 26), abs=1e-12)
    assert isinstance(r["hypothesis_supported"], bool)


def test_correlation_ci_matches_scipy_and_pingouin():
    rng = np.random.default_rng(9)
    xy = rng.multivariate_normal([0, 0], [[1, .6], [.6, 1]], 40)
    c = P.correlation_ci(xy[:, 0], xy[:, 1])
    ci = stats.pearsonr(xy[:, 0], xy[:, 1]).confidence_interval(0.95)
    assert c["ci_low"] == pytest.approx(ci.low, abs=1e-10)
    assert c["ci_high"] == pytest.approx(ci.high, abs=1e-10)
    ref = pg.corr(xy[:, 0], xy[:, 1])
    assert c["r"] == pytest.approx(ref["r"].iloc[0])
    assert c["ci_low"] == pytest.approx(ref["CI95"].iloc[0][0], abs=0.005 + 1e-9)
    s = P.correlation_ci(xy[:, 0], xy[:, 1], method="spearman")
    z = np.arctanh(s["r"])
    assert s["ci_high"] == pytest.approx(np.tanh(z + 1.959963984540054 * np.sqrt(1.06 / 37)))


def test_multiplicity_matches_statsmodels_and_scipy():
    from statsmodels.stats.multitest import multipletests
    rng = np.random.default_rng(10)
    p = np.concatenate([rng.uniform(0, 0.02, 5), rng.uniform(0, 1, 15), [0.04, 0.04]])
    h = P.holm(p)
    assert np.allclose(h["p_adjusted"], multipletests(p, method="holm")[1], atol=1e-14)
    assert h["reject"] == multipletests(p, method="holm")[0].tolist()
    b = P.benjamini_hochberg(p)
    assert np.allclose(b["p_adjusted"], multipletests(p, method="fdr_bh")[1], atol=1e-14)
    assert np.allclose(b["p_adjusted"], stats.false_discovery_control(p), atol=1e-14)


def test_bootstrap_ci_seeded_and_against_scipy():
    rng = np.random.default_rng(12)
    x = rng.exponential(1.0, 60)
    a = P.bootstrap_ci(np.mean, x, n_boot=3000, seed=5, method="bca")
    b = P.bootstrap_ci(np.mean, x, n_boot=3000, seed=5, method="bca")
    assert a == b  # deterministic
    ref = stats.bootstrap((x,), np.mean, n_resamples=3000, method="BCa",
                          random_state=np.random.default_rng(5)).confidence_interval
    assert a["ci_low"] == pytest.approx(ref.low, abs=0.03)
    assert a["ci_high"] == pytest.approx(ref.high, abs=0.03)
    p = P.bootstrap_ci(np.mean, x, n_boot=3000, seed=5)
    t = stats.t.interval(0.95, 59, x.mean(), x.std(ddof=1) / np.sqrt(60))
    assert p["ci_low"] == pytest.approx(t[0], abs=0.05)
    # paired resampling of a two-sample statistic
    y = x + rng.normal(0, 0.1, 60)
    pr = P.bootstrap_ci(lambda u, v: np.corrcoef(u, v)[0, 1], x, y, paired=True, seed=1,
                        n_boot=500)
    assert pr["ci_low"] < pr["estimate"] < pr["ci_high"]


def test_tost_matches_pingouin_welch_and_ci_rule():
    rng = np.random.default_rng(13)
    x, y = rng.normal(0.1, 1, 40), rng.normal(0, 1.5, 35)
    r = P.tost(x, y, low=0.6)
    ref = pg.tost(x, y, bound=0.6, correction=True)
    assert r["p"] == pytest.approx(ref["pval"].iloc[0], rel=1e-8)
    inside = r["low"] < r["ci_1_minus_2alpha"][0] and r["ci_1_minus_2alpha"][1] < r["high"]
    assert inside == r["equivalent"]


def test_lin_ccc_formula_identities():
    rng = np.random.default_rng(14)
    x = rng.normal(10, 2, 50)
    y = 1.1 * x + rng.normal(0.5, 1, 50)
    c = P.lin_ccc(x, y)
    sxy = np.cov(x, y, ddof=0)[0, 1]
    direct = 2 * sxy / (x.var() + y.var() + (x.mean() - y.mean()) ** 2)
    assert c["ccc"] == pytest.approx(direct, rel=1e-12)
    assert c["ccc"] == pytest.approx(c["pearson_r"] * c["accuracy_cb"], rel=1e-12)
    assert c["ci_low"] < c["ccc"] < c["ci_high"]
    assert P.lin_ccc(x, x + 1e-9 * rng.normal(size=50))["ccc"] == pytest.approx(1, abs=1e-6)


def test_bland_altman_ci_methods_and_proportional_bias():
    rng = np.random.default_rng(15)
    y = rng.uniform(10, 100, 300)
    x = y * 1.10 + rng.normal(0, 2, 300)  # proportional bias
    r = P.bland_altman(x, y)
    assert r["proportional_bias"]["p"] < 1e-6
    assert any("proportional bias" in w for w in r["warnings"])
    y2 = rng.normal(50, 10, 400)
    x2 = y2 + rng.normal(1, 3, 400)
    a, e = P.bland_altman(x2, y2), P.bland_altman(x2, y2, loa_ci="exact")
    # large n: approximate (1999) and exact (noncentral t) LoA CIs agree closely
    assert a["loa_high_ci"][0] == pytest.approx(e["loa_high_ci"][0], abs=0.05)
    assert a["loa_low_ci"][1] == pytest.approx(e["loa_low_ci"][1], abs=0.05)


def test_lmm_fixed_effects_and_variance_components():
    rng = np.random.default_rng(16)
    n, k = 60, 4
    u = rng.normal(0, 1.0, n)
    rows = [{"pid": i, "t": t, "y": 5 + 0.5 * t + u[i] + rng.normal(0, 0.7)}
            for i in range(n) for t in range(k)]
    df = pd.DataFrame(rows)
    r = P.fit_repeated_measures_lmm(df, "y", "pid", "t")
    slope = next(f for f in r["fixed_effects"] if f["term"] == "t")
    # balanced data: GLS fixed effects == OLS estimate
    ols = np.polyfit(df["t"], df["y"], 1)[0]
    assert slope["estimate"] == pytest.approx(ols, abs=1e-6)
    assert slope["ci_low"] < 0.5 < slope["ci_high"]
    true_icc = 1 / (1 + 0.49)
    assert r["icc"] == pytest.approx(true_icc, abs=0.12)
    # categorical sessions: variance-component ICC == ANOVA ICC(3,1)
    rc = P.fit_repeated_measures_lmm(df, "y", "pid", "t", time_as="categorical")
    a = P.icc_table(df, "pid", "t", "y").loc["ICC(3,1)", "icc"]
    assert rc["icc"] == pytest.approx(a, abs=1e-3)
    rs = P.fit_repeated_measures_lmm(df, "y", "pid", "t", random_slope=True)
    assert "subject_slope" in rs["variance_components"]
    assert any("ICC varies with time" in w for w in rs["warnings"])


def test_missing_data_summary_patterns():
    rows = []
    for i in range(30):
        for s in (1, 2, 3, 4):
            v = float(i + s)
            if i < 5 and s >= 3:      # dropout -> monotone
                continue
            if 5 <= i < 8 and s == 2:  # intermittent
                v = np.nan
            rows.append({"pid": i, "session": s, "score": v})
    df = pd.DataFrame(rows)
    m = P.missing_data_summary(df, "pid", "session", ["score"])
    pv = m["per_variable"]["score"]
    assert pv["subjects_monotone"] == 5
    assert pv["subjects_intermittent"] == 3
    assert pv["subjects_complete"] == 22
    assert pv["n_missing"] == 5 * 2 + 3
    assert m["patterns"]["score"]["XX.."] == 5


def test_em_mvn_complete_data_equals_ml_moments():
    rng = np.random.default_rng(17)
    X = rng.normal(size=(50, 3))
    mu, sig, _, conv = P.em_mvn(X)
    assert conv
    np.testing.assert_allclose(mu, X.mean(axis=0), atol=1e-12)
    np.testing.assert_allclose(sig, np.cov(X, rowvar=False, ddof=0), atol=1e-12)


# ============================================== (c) simulation with known true reliability
def _sim(rng, n, k, vs, vr, ve):
    return 10 + rng.normal(0, np.sqrt(vs), (n, 1)) + rng.normal(0, np.sqrt(vr), (1, k)) \
        + rng.normal(0, np.sqrt(ve), (n, k))


def test_icc_recovers_known_true_reliability():
    rng = np.random.default_rng(20)
    est = {"1,1": [], "2,1": [], "3,1": [], "3,k": []}
    for _ in range(200):
        Y = _sim(rng, 100, 3, 0.7, 0.0, 0.3)
        t = R._icc_from_ms(R.anova_mean_squares(Y))
        for f in est:
            est[f].append(t[f]["icc"])
    for f in ("1,1", "2,1", "3,1"):
        assert np.mean(est[f]) == pytest.approx(0.7, abs=0.01)
    assert np.mean(est["3,k"]) == pytest.approx(P.spearman_brown(0.7, 3), abs=0.01)


@pytest.mark.parametrize("n,k,vs,ve", [(30, 3, 0.7, 0.3), (20, 2, 0.5, 0.5)])
def test_icc_ci_coverage_500_replications(n, k, vs, ve):
    """Exact F-based CIs (ICC(1,1), ICC(3,1)) and M&W ICC(2,1) cover ~95 % without session
    effects. MC SE of a 95 % coverage over 500 reps is 0.0097; band = +/- 3 SE."""
    rng = np.random.default_rng(1000 + n)
    truth = vs / (vs + ve)
    hits = {"1,1": 0, "2,1": 0, "3,1": 0, "gci": 0}
    reps = 500
    for i in range(reps):
        Y = _sim(rng, n, k, vs, 0.0, ve)
        ms = R.anova_mean_squares(Y)
        t = R._icc_from_ms(ms)
        for f in ("1,1", "2,1", "3,1"):
            hits[f] += t[f]["ci"][0] <= truth <= t[f]["ci"][1]
        g = R._gci_agreement(ms, n_draws=2000, seed=i)["2,1"]
        hits["gci"] += g[0] <= truth <= g[1]
    for f, h in hits.items():
        assert abs(h / reps - 0.95) <= 0.03, (f, h / reps)


def test_agreement_icc_ci_with_session_effects_gci_vs_mcgraw_wong():
    """Documented finding: with systematic session variance comparable to error variance the
    McGraw & Wong ICC(A,1) interval under-covers; the generalized CI does not."""
    rng = np.random.default_rng(31)
    vs, vr, ve, n, k = 0.9, 0.05, 0.05, 100, 3
    truth = vs / (vs + vr + ve)
    mw = gci = 0
    reps = 400
    for i in range(reps):
        Y = _sim(rng, n, k, vs, vr, ve)
        ms = R.anova_mean_squares(Y)
        lo, hi = R._icc_from_ms(ms)["2,1"]["ci"]
        mw += lo <= truth <= hi
        g = R._gci_agreement(ms, n_draws=2000, seed=i)["2,1"]
        gci += g[0] <= truth <= g[1]
    assert mw / reps < 0.91          # M&W under-covers (method property, same as pingouin)
    assert abs(gci / reps - 0.95) <= 0.035


def test_sem_and_mdc_recover_true_error():
    rng = np.random.default_rng(21)
    sems, fp = [], []
    for _ in range(100):
        Y = _sim(rng, 80, 2, 1.0, 0.0, 0.25)  # true SEM = 0.5
        s = P.sem_mdc(Y)
        sems.append(s["by_definition"]["sqrt_mse"]["sem"])
        assert s["mdc95"] == pytest.approx(1.959963984540054 * np.sqrt(2) * s["sem"])
        assert s["mdc90"] == pytest.approx(1.6448536269514722 * np.sqrt(2) * s["sem"])
        assert s["by_definition"]["sd_icc"]["sem"] == pytest.approx(0.5, abs=0.15)
        Z = _sim(rng, 500, 2, 1.0, 0.0, 0.25)
        fp.append(np.mean(np.abs(Z[:, 1] - Z[:, 0]) > s["mdc95"]))
    assert np.mean(sems) == pytest.approx(0.5, abs=0.01)
    assert np.mean(fp) == pytest.approx(0.05, abs=0.01)  # MDC95 ~ 5 % false positives


def test_spearman_brown_predicts_reliability_of_longer_test():
    """Reliability of the mean of m parallel trials == Spearman–Brown of single-trial ICC."""
    rng = np.random.default_rng(22)
    n, m = 4000, 4
    T = rng.normal(0, 1, n)
    trials = lambda: T[:, None] + rng.normal(0, 1.5, (n, m))  # noqa: E731
    a, b = trials().mean(axis=1), trials().mean(axis=1)  # two sessions of an m-trial test
    rel_m = np.corrcoef(a, b)[0, 1]
    rel_1 = 1 / (1 + 1.5 ** 2)
    assert rel_m == pytest.approx(P.spearman_brown(rel_1, m), abs=0.02)
    assert P.spearman_brown_length(rel_1, P.spearman_brown(rel_1, m)) == pytest.approx(m)


def test_alpha_and_omega_recover_truth():
    rng = np.random.default_rng(23)
    k, lam, psi = 6, 0.8, 0.6
    X = rng.normal(size=(3000, 1)) * lam + rng.normal(size=(3000, k)) * np.sqrt(psi)
    truth = (k * lam) ** 2 / ((k * lam) ** 2 + k * psi)
    assert P.cronbach_alpha(X)["alpha"] == pytest.approx(truth, abs=0.01)
    assert P.mcdonald_omega(X)["omega"] == pytest.approx(truth, abs=0.01)
    # congeneric: alpha underestimates, omega does not
    lam2 = np.array([1.2, 1.0, 0.4, 0.3, 0.2, 1.1])
    X2 = rng.normal(size=(5000, 1)) * lam2 + rng.normal(size=(5000, k)) * np.sqrt(psi)
    t2 = lam2.sum() ** 2 / (lam2.sum() ** 2 + k * psi)
    assert P.mcdonald_omega(X2)["omega"] == pytest.approx(t2, abs=0.01)
    assert P.cronbach_alpha(X2)["alpha"] < t2 - 0.01


def test_effect_size_and_auc_ci_coverage():
    rng = np.random.default_rng(24)
    reps, cg, ca, cc = 300, 0, 0, 0
    tr_auc = stats.norm.cdf(0.8 / np.sqrt(2))
    for _ in range(reps):
        x, y = rng.normal(0.8, 1, 15), rng.normal(0, 1, 18)
        g = P.hedges_g(x, y)
        cg += g["ci_low"] <= 0.8 <= g["ci_high"]
        a = P.auc_delong(x, y)
        ca += a["ci_low"] <= tr_auc <= a["ci_high"]
        xy = rng.multivariate_normal([0, 0.2], [[1, .8], [.8, 1]], 40)
        c = P.lin_ccc(xy[:, 0], xy[:, 1])
        cc += c["ci_low"] <= 1.6 / (2 + 0.04) <= c["ci_high"]
    assert abs(cg / reps - 0.95) < 0.04   # exact (noncentral t)
    assert abs(ca / reps - 0.95) < 0.05   # DeLong: large-sample
    assert abs(cc / reps - 0.95) < 0.05   # CCC Fisher-z: large-sample


def test_little_mcar_calibrated_and_powered():
    rng = np.random.default_rng(25)
    cov = [[1, .6, .4], [.6, 1, .5], [.4, .5, 1]]
    rej_mcar = rej_mar = 0
    reps = 150
    for _ in range(reps):
        X = rng.multivariate_normal([0, 0, 0], cov, 200)
        M = X.copy()
        M[rng.random(200) < 0.2, 2] = np.nan
        rej_mcar += P.little_mcar_test(M)["p"] < 0.05
        A = X.copy()
        A[X[:, 0] > 0.3, 2] = np.nan  # MAR: depends on observed variable 0
        rej_mar += P.little_mcar_test(A)["p"] < 0.05
    assert rej_mcar / reps < 0.05 + 3 * np.sqrt(0.05 * 0.95 / reps)
    assert rej_mar / reps > 0.9


# ======================================================= validity / responsiveness / MCID
def test_floor_ceiling_flags():
    x = [0] * 20 + list(range(1, 81))  # 20 % at floor
    r = P.floor_ceiling(x, min_possible=0, max_possible=100)
    assert r["prop_floor"] == pytest.approx(0.2) and r["floor_flag"]
    assert r["prop_ceiling"] == 0 and not r["ceiling_flag"]
    assert P.floor_ceiling(x)["warnings"]  # observed bounds -> warning


def test_responsiveness_indices():
    rng = np.random.default_rng(26)
    b = rng.normal(50, 10, 200)
    f = b + rng.normal(5, 4, 200)
    sb = rng.normal(50, 10, 150)
    sf = sb + rng.normal(0, 4, 150)
    r = P.responsiveness(b, f, stable_baseline=sb, stable_follow_up=sf, mdc=6.0)
    c = f - b
    assert r["srm"] == pytest.approx(c.mean() / c.std(ddof=1))
    assert r["effect_size_kazis"] == pytest.approx(c.mean() / b.std(ddof=1))
    assert r["guyatt_ri"] == pytest.approx(c.mean() / (sf - sb).std(ddof=1))
    assert r["srm"] == pytest.approx(r["dz_ci"]["dz"])
    assert r["auc_changed_vs_stable"]["auc"] == pytest.approx(stats.norm.cdf(5 / np.sqrt(32)),
                                                              abs=0.06)
    assert r["prop_exceeding_mdc"] == pytest.approx(np.mean(c > 6.0))
    r2 = P.responsiveness(b, f)
    assert r2["guyatt_ri"] is None and r2["warnings"]


def test_mcid_note_and_distribution_label():
    note = P.mcid_note()
    assert "anchor" in note.lower() and "simulat" in note.lower()
    d = P.distribution_based_change_estimates(10.0, sem=2.0)
    assert all(v["label"] == "distribution-based estimate, not an MCID"
               for v in d["estimates"].values())
    # no public function claims to compute an MCID
    assert [n for n in P.__all__ if "mcid" in n.lower()] == ["mcid_note"]


def test_convergent_divergent_hypotheses():
    rng = np.random.default_rng(27)
    s = rng.normal(size=100)
    r = P.convergent_divergent(s, convergent={"close": s + rng.normal(0, .5, 100)},
                               divergent={"unrelated": rng.normal(size=100)})
    res = {x["measure"]: x for x in r["results"]}
    assert res["close"]["hypothesis_supported"] and res["unrelated"]["hypothesis_supported"]


def test_compare_icc_across_groups():
    rng = np.random.default_rng(28)
    rows = []
    for g, ve in (("eye", 0.2), ("bci", 0.2), ("switch", 2.0)):
        for i in range(40):
            t = rng.normal()
            rows += [{"pid": f"{g}{i}", "mod": g, "s": s, "y": t + rng.normal(0, np.sqrt(ve))}
                     for s in (1, 2)]
    df = pd.DataFrame(rows)
    r = P.compare_icc_across_groups(df, "y", "pid", "s", "mod", n_boot=300, margin=0.25)
    comp = {(c["group_a"], c["group_b"]): c for c in r["comparisons"]}
    assert comp[("bci", "eye")]["ci_low"] < 0 < comp[("bci", "eye")]["ci_high"]
    assert comp[("bci", "switch")]["ci_low"] > 0  # switch group much less reliable
    assert comp[("bci", "switch")]["equivalent"] is False
    assert "OUT OF SCOPE" in r["warnings"][0]


# ======================================================================== report
def _report_df(seed=29):
    rng = np.random.default_rng(seed)
    rows = []
    for i in range(36):
        g = "eye" if i % 2 else "bci"
        t = rng.normal(10 if g == "eye" else 8, 2)
        for s in (1, 2, 3):
            if rng.random() < 0.07:
                continue
            rows.append({"pid": f"p{i}", "session": s, "modality": g,
                         "throughput": t + 0.2 * s + rng.normal(0, 0.8),
                         "error_rate": float(np.clip(rng.normal(0.1, 0.05), 0, 1))})
    return pd.DataFrame(rows)


def test_psychometric_report_is_complete_and_json_serialisable():
    df = _report_df()
    rep = P.psychometric_report(df, ["throughput", "error_rate"], "pid", "session",
                                group_col="modality", bounds={"error_rate": (0, 1)},
                                equivalence_margins={"throughput": 0.5}, n_boot=200)
    s = json.dumps(rep)
    assert "NaN" not in s
    tp = rep["scores"]["throughput"]
    for sec in (tp["reliability"]["icc"], tp["reliability"]["sem_mdc"],
                tp["agreement"]["bland_altman"], tp["agreement"]["lin_ccc"],
                tp["floor_ceiling"], tp["change_over_sessions"], tp["missing_data"],
                tp["invariance_reliability"], tp["invariance_means_tost"],
                tp["known_groups"]["comparisons"][0], rep["multiplicity"]):
        for key in ("method", "n", "assumptions", "warnings"):
            assert key in sec, (key, sec.get("method"))
        assert "error" not in sec, sec.get("error")
    assert tp["reliability"]["icc"]["table"][1]["form"] == "ICC(2,1)"
    assert "icc_mixed" in tp["reliability"]  # there is missingness
    assert rep["internal_consistency"]["computed"] is False
    assert rep["scores"]["error_rate"]["change_thresholds"]["label"] == \
        "distribution-based estimate, not an MCID"
    md = rep["markdown"]
    assert md.startswith("# Psychometric report") and "ICC(2,1)" in md and "MCID" in md
    assert P.render_markdown(rep) == md


def test_report_without_groups_and_single_session():
    df = _report_df()
    rep = P.psychometric_report(df, ["throughput"], "pid", "session", include_markdown=False)
    assert "known_groups" not in rep["scores"]["throughput"] and "markdown" not in rep
    one = df[df["session"] == 1]
    rep1 = P.psychometric_report(one, ["throughput"], "pid", "session")
    assert "reliability" not in rep1["scores"]["throughput"]
    assert rep1["warnings"]


# ======================================================================== slow study
@pytest.mark.slow
def test_full_coverage_study(request, tmp_path):
    markexpr = request.config.getoption("-m") or ""
    if "slow" not in markexpr and not os.environ.get("NEUROMETRIC_RUN_SLOW"):
        pytest.skip("slow coverage study: run with -m slow or NEUROMETRIC_RUN_SLOW=1")
    from neurometric.psychometrics import verify_coverage as V
    summary = V.main(["--reps", "500", "--out", str(tmp_path)])
    df = pd.read_csv(tmp_path / "coverage_results.csv")
    assert (tmp_path / "coverage_results.json").exists()
    assert df["passes"].all(), df.loc[~df["passes"], ["analysis", "scenario", "value_checked"]]
    assert summary["n_pass"] == summary["n_rows"]
