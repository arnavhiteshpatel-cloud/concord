# Statistical Analysis Plan (SAP): locked template

> **DRAFT TEMPLATE. No study approved; no data exist.** Copy this file to
> `docs/clinical/sap_<stage>.md`, fill every field, then lock it as described in §0. Do not
> delete sections. Write "not applicable" and give the reason. Labels follow
> `docs/research/CONVENTIONS.md`.

---

## 0. Version control and lock

| Field | Value |
|---|---|
| SAP title | |
| Stage(s) / protocol | |
| IRB protocol number | *(to be assigned by UIUC IRB)* |
| Faculty Principal Investigator | *[FACULTY PI NAME, DEPARTMENT]*. The student founder cannot be PI under UIUC RP-19 [V] |
| SAP author(s) | |
| Independent statistician (no NeuroMetric financial interest) | *[NAME]*. Required by the COI management plan |
| SAP version | e.g. 1.0 |
| Status | DRAFT / LOCKED / AMENDED |
| Date locked (UTC) | |
| SHA-256 of this file (Markdown, as locked) | `<64 hex>` |
| SHA-256 of PDF export | `<64 hex>` |
| Analysis code repository and commit | `<repo>@<40-hex commit>` |
| Psychometrics package version | `neurometric.psychometrics` @ commit `<hash>` |
| Battery version / task specs hash | `BATTERY_VERSION = 1.0.0`; manifest SHA-256 `<hash>` |
| OSF registration DOI / URL | |
| Date first participant consented | must be **after** the lock date |
| Data access status at lock | "No participant data exist" / describe |

**Lock procedure.**
1. Freeze the code at a tagged commit.
2. Run the full pipeline on a simulated dataset (`neurometric.simulator`) and archive the output
   as "dry run, simulated, not results".
3. Run `sha256sum` on the SAP Markdown and PDF.
4. Upload the SAP, hashes and dry-run output to OSF Registries.
5. Record everything in `docs/clinical/sap_hash_log.md`.
6. File the registration with the IRB if requested.

## 1. Background and objectives
- 1.1 Rationale (one paragraph; cite the protocol).
- 1.2 Objectives: primary, secondary, exploratory.
- 1.3 Hypotheses. Label each one **confirmatory**, **secondary** or **exploratory**. For each
  confirmatory hypothesis, give the exact decision rule (statistic, threshold, CI level, sidedness).

## 2. Study design summary
Design type; arms or conditions; visits and windows; randomization and counterbalancing (seed,
generator script and commit, who holds the list); blinding (usually none; say who is unblinded
to what); setting; devices.

## 3. Estimands
For each primary and key secondary objective, use the ICH E9(R1) attributes [PK]:

| Attribute | Entry |
|---|---|
| Population | |
| Variable (endpoint) | |
| Intercurrent events and strategy (e.g. AT setting change → while-on-setting; session stopped for fatigue → treatment-policy or hypothetical; device failure → hypothetical) | |
| Population-level summary | e.g. ICC(A,1) with 95% CI; mean difference; AUC |

## 4. Endpoints and scores
- 4.1 Primary endpoints: exact computation, software function, units, transformation (e.g.
  log10), direction, handling of capped or timed-out trials, minimum valid trials per score.
- 4.2 Secondary endpoints.
- 4.3 Exploratory endpoints.
- 4.4 Trial-validity rules (focus loss, timing self-check failure, technical fault). These are
  applied before scoring, and the excluded count is reported.
- 4.5 Outlier rule, pre-specified (e.g. Soukoreff & MacKenzie misfire rule for A2), applied
  automatically, with a sensitivity analysis that does not apply it.

## 5. Analysis populations
| Population | Definition |
|---|---|
| Enrolled | consented |
| Full analysis set (FAS) | ≥ 1 valid scored session |
| Reliability set | valid S1 and ≥ 1 further test session (complete-case for the primary ICC; all available data for mixed-model sensitivity) |
| Per-protocol set | all scheduled sessions within window, same device/setup, no major deviation |
| Safety set | anyone who started a session |

## 6. Statistical models
- 6.1 Primary model(s), written as equations, with software and function names.
- 6.2 Reliability: ICC form (McGraw & Wong label and Shrout & Fleiss label), model, type, unit;
  CI method (McGraw–Wong F-based; GCI as sensitivity); SEM_agreement from variance components;
  MDC95; Bland–Altman (scale, proportional bias, repeated-measures correction).
- 6.3 Validity: known-groups (AUC with DeLong CI; Hedges g); convergent/divergent (Pearson or
  Spearman with Fisher-z CI; predicted ranges); floor/ceiling (15% rule).
- 6.4 Responsiveness: anchors and their credibility; SRM; Guyatt RI; AUC; MIC method (only
  anchor-based). The statement "no MCID is derived from distribution-based quantities" is
  mandatory.
- 6.5 Mixed models for nuisance structure (practice, learning, fatigue, modality, difficulty,
  session variability). Fixed and random terms; covariance structure; estimation (REML); how
  convergence failures are handled (simplification order pre-specified).
- 6.6 Model assumptions and checks (residual plots, normality of random effects, log-transform
  rule).

## 7. Multiplicity
State the family, the method (Holm, Bonferroni, intersection–union, hierarchical gatekeeping)
and why. Exploratory analyses are not adjusted and are labelled exploratory.

## 8. Missing data
- 8.1 Expected mechanisms and reasons (reason codes).
- 8.2 Primary assumption (MAR given …) and primary handling.
- 8.3 Multiple imputation: model, variables, m, software, pooling (Rubin's rules; Fisher z for
  correlations and ICCs).
- 8.4 MNAR sensitivity: delta-adjusted tipping point (δ grid, direction, which arm or group).
- 8.5 Task-level non-completion: scored as data (cap or floor), not as missing.

## 9. Sensitivity analyses (pre-specified list)
Each with its rationale and with the result that would change interpretation.

## 10. Subgroup analyses
Pre-specified subgroups only; interaction tests; labelled exploratory.

## 11. Interim analyses and stopping
Usually none for measurement studies. Feasibility monitoring (recruitment, attrition, safety)
does not look at outcome data by group.

## 12. Reporting
- Tables and figures list (shells).
- Reporting guideline: COSMIN reporting items for reliability and measurement error; STROBE for
  observational elements [PK].
- Every simulated or dry-run output is labelled "SIMULATED – NOT A RESULT".

## 13. Software and reproducibility
Python version; package versions (lock file hash); R version for cross-checks; random seeds;
container image digest.

## 14. Deviations log (append-only after lock)
| # | Date (UTC) | Section | Change | Reason | Data seen before change? (none / blinded aggregate / unblinded) | Effect on confirmatory status | Approved by (PI, statistician) |
|---|---|---|---|---|---|---|---|
| 1 | | | | | | | |

## 15. Sign-off
| Role | Name | Date | Signature / attestation |
|---|---|---|---|
| Faculty PI | | | |
| Independent statistician | | | |
| Student investigator (founder): attests that they will not alter the locked SAP or code | | | |
