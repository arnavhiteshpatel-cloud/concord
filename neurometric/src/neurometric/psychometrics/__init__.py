"""NeuroMetric psychometrics: reliability, agreement, validity, effect sizes, mixed models.

Pure functions on numpy / pandas. Every formula is documented in the function docstring with
its reference; references marked [PK] are cited from prior knowledge and were not re-verified.
Implementations are verified in ``tests/test_psychometrics.py`` against published worked
examples, independent implementations (pingouin, scipy, statsmodels) and Monte-Carlo studies
with known truth (``verify_coverage.py``). See ``docs/science/PSYCHOMETRICS.md``.
"""
from .agreement import bland_altman, lin_ccc
from .effects import (benjamini_hochberg, bootstrap_ci, cliffs_delta, cohens_d, cohens_dz,
                      hedges_correction, hedges_g, holm)
from .invariance import INVARIANCE_SCOPE_NOTE, compare_icc_across_groups, tost
from .mixed import em_mvn, fit_repeated_measures_lmm, little_mcar_test, missing_data_summary
from .reliability import (ICC_FORMS, INTERNAL_CONSISTENCY_WARNING, anova_mean_squares,
                          cronbach_alpha, icc, icc_mixed, icc_table, mcdonald_omega, mdc,
                          sem_from_icc, sem_mdc, spearman_brown, spearman_brown_length, to_wide)
from .report import psychometric_report, render_markdown
from .validity import (DISTRIBUTION_LABEL, auc, auc_bootstrap, auc_delong, convergent_divergent,
                       correlation_ci, distribution_based_change_estimates, floor_ceiling,
                       known_groups, mcid_note, responsiveness)

__all__ = [
    # reliability
    "ICC_FORMS", "to_wide", "anova_mean_squares", "icc", "icc_table", "icc_mixed", "sem_mdc",
    "sem_from_icc", "mdc", "spearman_brown", "spearman_brown_length", "cronbach_alpha",
    "mcdonald_omega", "INTERNAL_CONSISTENCY_WARNING",
    # agreement
    "bland_altman", "lin_ccc",
    # validity
    "auc", "auc_delong", "auc_bootstrap", "known_groups", "correlation_ci",
    "convergent_divergent", "floor_ceiling", "responsiveness", "mcid_note",
    "distribution_based_change_estimates", "DISTRIBUTION_LABEL",
    # effects
    "cohens_d", "hedges_g", "hedges_correction", "cohens_dz", "cliffs_delta", "bootstrap_ci",
    "holm", "benjamini_hochberg",
    # mixed
    "fit_repeated_measures_lmm", "missing_data_summary", "little_mcar_test", "em_mvn",
    # invariance
    "tost", "compare_icc_across_groups", "INVARIANCE_SCOPE_NOTE",
    # report
    "psychometric_report", "render_markdown",
]
