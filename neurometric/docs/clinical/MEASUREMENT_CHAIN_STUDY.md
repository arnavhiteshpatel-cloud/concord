# Measurement-chain longitudinal study design

> **DRAFT. Not submitted. Requires faculty PI and IRB review. No participants, no data.**
> It builds on Stage 4 (longitudinal sub-study), Stage 5 (home telemetry) and Stage 6 (partner
> cohorts). Concepts: `docs/science/INDEPENDENCE_AND_CHAIN.md` (levels L1–L6, independence
> states, between/within decomposition). Field context: the iBCI-CC consensus calls for a
> "shared measurement chain extending from device performance, to functional or activity-level
> outcome, to health outcome or change in care burden" [V, `regulatory_landscape.md` §6].

## 1. Aim and explicit non-aims
**Aim.** Describe how measures at six levels co-vary **within** people over time and **between**
people, and how strong those associations are, with honest uncertainty.

**Non-aims.**
- No causal claim ("improving device performance increases independence").
- No economic claim.
- No MCID.

Every association is reported as associational. Wording such as "drives", "causes", "leads to"
or "effect of" is banned from reports unless the design is an experiment. A device or decoder
randomization run by a partner would be such an experiment, and even then only for that
contrast.

## 2. Levels and measures
| Level | Construct | Measure (status) | Frequency |
|---|---|---|---|
| L1 Device performance | Signal or decoder or AT-system quality | Partner/sponsor daily aggregates (decoder-on time, selections, signal-quality summary) under a DUA; for non-BCI AT: calibration quality reported by the AT software; AT settings | Daily (export) / per session |
| L2 Task performance | Battery P1–P4 | NeuroMetric core battery (experimental; Stage 3–4 reliability) | Monthly home battery; in-clinic at baseline, 3, 6 months |
| L3 Real-world use | Active device use | Tier 0/1 telemetry daily totals (consented, aggregate) | Daily |
| L4 Independence | Doing digital activities without help | Battery independence states per attempt (experimental assistance-weighted score); participant-reported independent digital activities (original, unvalidated) | Monthly |
| L5 Care-partner assistance | Help time and burden | Original assistance diary (minutes by type; unvalidated); Zarit Burden Interview-12 **only if licensed** (Mapi, commercial e-licence) | Diary 7 days per month; ZBI at 0, 3, 6 months |
| L6 Participation / QoL | Participation and quality of life | Licensed only: PROMIS/Neuro-QoL Ability to Participate in Social Roles (HealthMeasures commercial permission), WHOQOL-BREF (WHO permission), ALSAQ-40 for ALS (OUI licence); original digital participation questionnaire (unvalidated) | 0, 3, 6 months |
| Covariates | Severity and progression; time since onset; age; care setting; care-partner availability; mood/fatigue; device type changes; internet access | ALSFRS-R at a clinical partner (certified rater; rights UNR); fatigue NRS; event log of device/setting changes | Per wave |

If a licence is not obtained, that measure is dropped before the SAP lock. **It is never
replaced by a paraphrase.**

## 3. Design
- Prospective observational cohort: Stage 4 participants who consent to longitudinal follow-up,
  plus partner cohorts (Stage 6).
- 6 months in the first protocol. 12 months if funded and the burden is acceptable.
- Monthly measurement windows: a 7-day block of diary plus telemetry, ending with a home battery.
- **Planned sample [HYP]:** 30–45 participants × 7 waves (0–6 months). Daily telemetry adds about
  180 days per person for Tier 1 users.
- **Burden per month:** one battery (40–70 min) plus diary (about 14 min) plus quarterly
  questionnaires (about 20 min). The ALS group is expected to have higher attrition, and the
  timing of disease-related dropout is recorded.

## 4. Analysis
### 4.1 Primary approach: multilevel models with between/within decomposition
For a pair of adjacent levels (e.g. L2 → L5):

```
y_it = γ00 + γ01·x̄_i + γ10·(x_it − x̄_i) + γ20·t + γ·covariates_it + u0i + u1i·(x_it − x̄_i) + e_it
```

- γ10 is the **within-person** association: in months when a person performs better than their
  own average, is assistance lower?
- γ01 is the **between-person** association. It is confounded by stable traits (severity, care
  setting, resources).
- The pooled correlation is descriptive only.
- Time (t) and progression covariates are included so that shared trends do not produce spurious
  within-person associations.
- Detrending sensitivity: person-specific linear time slopes.
- Software: `fit_repeated_measures_lmm` with person-mean-centred covariates. The chain module
  (`docs/science/INDEPENDENCE_AND_CHAIN.md`) implements this decomposition and was checked on
  synthetic data with a known structure.

### 4.2 Cross-lagged panel models: only if there are enough waves and people
- Lagged questions ("does better L2 this month go with less L5 next month?") would use the
  **random-intercept cross-lagged panel model** (RI-CLPM; Hamaker et al. 2015 [PK]). The
  traditional CLPM mixes between- and within-person variance [PK].
- **Pre-specified feasibility rule [HYP]:** fit the RI-CLPM only with ≥ 4 waves and ≥ 100
  participants with ≥ 3 observed waves. Simulation studies suggest smaller samples give unstable
  estimates [PK]. Before the SAP lock, a simulation (`neurometric.simulator` plus chain module)
  checks this rule for the expected effect sizes.
- With N ≈ 30–45, the RI-CLPM is **not** fitted. The alternative for daily data (telemetry plus
  diary) is dynamic multilevel models: multilevel AR(1) with lagged predictors, or DSEM in a
  Bayesian framework [PK]. These use many time points per person, and are labelled exploratory.
- **N-of-1 analyses** for implanted-BCI participants (Stage 6): per-person time-series plots and
  lagged associations with autocorrelation-robust CIs. Descriptive.

### 4.3 Mediation: only with stated assumptions
Questions such as "is the association between L2 and L5 accounted for by L3 (real-world use)?"
are estimated as an **associational decomposition** within the multilevel framework (1-1-1
multilevel mediation, within-person paths) [PK]. Reports must list the assumptions, which are
untestable here:
1. temporal ordering (X measured before M, M before Y; lagged waves enforce this);
2. no unmeasured X–Y, X–M or M–Y confounding, given the covariates;
3. no M–Y confounder affected by X (e.g. fatigue);
4. correct functional form, and no X×M interaction (or it is modelled);
5. measurement error in M (unreliability attenuates indirect paths, and the Stage 3/4 ICC is
   used to bound this);
6. consistency, no interference (care partners shared across participants are unlikely, but
   recorded).

The report then says "under these assumptions, the data are consistent with …". It never says
"mediates".

### 4.4 Confounding assessment
- A **DAG** drafted with clinicians and lived-experience advisors before the SAP lock. It shows
  severity/progression, fatigue, mood, care setting, care-partner availability, device
  changes, internet access, motivation and season.
- Adjustment sets are derived from the DAG (minimal sufficient set), and alternatives are
  reported.
- **Negative controls:**
  - a negative-control outcome not plausibly related to digital performance (e.g. hours of
    sleep, if collected);
  - a negative-control exposure (e.g. future L2 predicting past L5).
  Associations here signal residual confounding or shared method variance.
- **E-values** (VanderWeele & Ding 2017 [PK]) for the key within- and between-person
  associations. They are computed on the risk-ratio scale after an approximate conversion from
  standardized coefficients (the conversion is stated). An E-value says how strong an unmeasured
  confounder would have to be to explain the association away. It does **not** show that there
  is no confounding.
- **Sensitivity:** the complete-case vs MI comparison (MAR); delta-adjusted MNAR tipping point
  for dropout related to progression (ALS); alternative time trends; excluding months with
  device or setting changes.

### 4.5 Missing data
Intermittent missingness (diary days, telemetry gaps) is modelled under MAR. Telemetry gaps are
classified by the validator receipts (device off / agent paused / technical). A pause by the
participant is **not** treated as zero use. Death and withdrawal are handled as truncation, not
as missing outcomes. Estimands are "while alive and enrolled".

### 4.6 Power and precision
Exploratory. Before the SAP lock, a simulation with assumed variance components (within-person
ICC of L5 about 0.5, within-person standardized slope 0.2–0.3 [HYP]) reports the expected CI
widths for γ10 at N = 30, 45 and 60 with 7 waves. Results are reported as estimates with CIs,
not as significance claims.

## 5. Reporting rules
- Always show the within- and between-person estimates side by side.
- Never interpret the between-person estimate as what happens within a person.
- Never present the pooled correlation as evidence of a chain link.
- Every figure that shows simulated data carries the label "SIMULATED".
- Limitations come first in the abstract: observational design; small N; unvalidated original
  instruments; selection (people willing to be monitored).

## 6. Approvals
UIUC IRB (faculty PI); partner IRBs for Stage 6 cohorts; DUAs for sponsor exports; instrument
licences; COI plan.
