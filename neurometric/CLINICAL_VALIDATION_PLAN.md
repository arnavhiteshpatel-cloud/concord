# NeuroMetric clinical validation plan (staged)

> **DRAFT. Not submitted. No IRB approval, no participants, no data, no collaborator commitments.**
> Prepared 2026-11-27 for review by a faculty Principal Investigator, a biostatistician and the
> University of Illinois Urbana-Champaign (UIUC) IRB. Every number below is a pre-specification
> proposal. None of it is a result. Evidence labels follow `docs/research/CONVENTIONS.md`.
> Web-search note: the shared web-search quota for this session ran out before this file was
> written. Institutional rules were checked by fetching the primary pages directly (marked [V],
> accessed 2026-11-27). Everything else is [PK], [INF] or [HYP].

Companion documents:

| Area | File |
|---|---|
| SAP template / filled SAP (stages 1–3) | `docs/clinical/STATISTICAL_ANALYSIS_PLAN_TEMPLATE.md`, `docs/clinical/sap_stage1_3.md` |
| Stage protocols | `docs/clinical/stage1_protocol.md` … `stage6_protocol.md` |
| Home-use feasibility (Stage 5) | `docs/clinical/HOME_USE_FEASIBILITY.md` |
| Measurement-chain longitudinal design | `docs/clinical/MEASUREMENT_CHAIN_STUDY.md` |
| Approach to Shirley Ryan AbilityLab | `docs/clinical/SRALAB_APPROACH.md` |
| IRB drafts (protocol summary, consents, recruitment, DMP, COI, reliance, CITI) | `docs/irb/` (start at `docs/irb/README.md`) |
| Psychometric code referenced | `src/neurometric/psychometrics/` (`icc`, `icc_mixed`, `sem_mdc`, `mdc`, `bland_altman`, `known_groups`, `correlation_ci`, `convergent_divergent`, `floor_ceiling`, `responsiveness`, `fit_repeated_measures_lmm`, `missing_data_summary`, `little_mcar_test`, `holm`, `tost`) |
| Task battery | `src/neurometric/tasks/battery.py` (v1.0.0, tasks A1–F7) |

---

## 0. Non-negotiable framing

1. **The student founder cannot be the Principal Investigator.** UIUC policy RP-19 ("Eligibility
   to Serve as Principal Investigator of a Research Activity Governed by Compliance
   Requirements", last revised May 16, 2025) says: "An individual with an appointment in one of
   the following categories may not serve as a Principal Investigator". The list includes
   "Undergraduate or graduate student employee". An IRB protocol is a "Compliance Protocol"
   under that policy. [V] https://cam.illinois.edu/policies/rp-19/
   The OPRS FAQ says that people who are not eligible "must find someone willing to oversee
   their research as the responsible PI". They are then listed as team members.
   [V] https://oprs.research.illinois.edu/faqs/who-can-be-principal-investigator-pi
   - RP-19's wording names student *employees*. Whether a student with no university appointment
     could ever be PI is not addressed on the pages read [UNR]. OPRS directs anyone not eligible
     to a responsible PI, so this plan assumes a **faculty PI** (tenure-system or other eligible
     professor) for every stage.
2. **The founder studies their own product. This is a conflict of interest.** Every stage
   operates under the COI management plan in `docs/irb/coi_management_plan.md`. In short:
   - an independent faculty PI;
   - the founder does not obtain consent or run confirmatory analyses;
   - the analysis plan is locked before data collection;
   - data custody stays with the university;
   - the company has no publication veto.
3. **Exemption and risk level are not ours to decide.** "Only OPRS and the IRB can make an
   exempt, minimal risk, or greater than minimal risk determination."
   [V] https://oprs.research.illinois.edu/research-topics/does-my-study-need-irb-approval
   We expect minimal risk for Stages 1–5 [INF]. That is a prediction, not a determination.
4. **The tasks are original, experimental and unvalidated** (battery manifest status:
   "experimental - not a validated clinical outcome assessment"). They are not the Shirley Ryan
   AbilityLab (SRAlab) Digital Assessment Interface (DAI). No claim of clinical validity,
   diagnostic use or minimal clinically important difference (MCID) is made at any stage. MCID
   is never computed from distributions (`psychometrics.validity.mcid_note`).
5. **No causal claims from correlational data** (see `docs/clinical/MEASUREMENT_CHAIN_STUDY.md`).
6. **COSMIN vocabulary** is used throughout (Mokkink et al. 2010, 2020) [PK; DOIs V-DOI in
   `docs/research/methods_references.md`]. The battery is a **performance outcome (PerfO)**
   instrument. The COSMIN risk-of-bias tool for reliability of outcome measurement instruments
   applies. It requires that we name the sources of variation that differ between repeated
   measurements: day, device setup, calibration, administrator.

---

## 1. Program overview

| Stage | Question (short) | Population | n enrolled (completers) | Primary decision rule | Confirmatory? |
|---|---|---|---|---|---|
| 1 | Do the tasks behave as specified (validity of the instrument mechanics, feasibility, floor/ceiling, timing, order/fatigue effects)? | Able-bodied adults | 42 (≥40) | Valid-trial rate lower 95% Wilson bound ≥ 0.90; Fitts linearity median R² ≥ 0.80 | No (pre-specified feasibility go/no-go) |
| 2 | Do scores separate input modalities in the expected direction, and how large are modality offsets? | Able-bodied adults using 4 modalities | 24 (24; replace dropouts to keep Williams balance) | Holm-adjusted paired contrasts on P2 (achieved bitrate) in the pre-specified direction | **Yes** (H2.1) |
| 3 | Test–retest reliability and measurement error after familiarization | Able-bodied adults, mouse | 60 (50) | ICC(A,1) lower 95% CI bound ≥ 0.75 for each of P1–P4 | **Yes** (H3.1, co-primary, intersection–union) |
| 4 | Reliability, known-groups and convergent validity, floor/ceiling in AT users (ALS, SCI, stroke); responsiveness sub-study | Adults using AT for computer access | 45 (36 for retest) | Known-groups AUC; ≥75% of construct hypotheses confirmed; ICC(A,1) lower bound ≥ 0.75 | **Yes** (H4.1–H4.3); reliability secondary-confirmatory |
| 5 | Is 2-week home use with aggregate telemetry feasible and acceptable? | 5 AT users + care partners | 5 (≥4) | ≥4/5 usable logs; ≥80% day completeness; burden ratings | No (feasibility) |
| 6 | Can NeuroMetric run inside a partner's neural-interface or rehabilitation-device study? | Partner's participants under partner's protocol/IRB | Partner-determined | Feasibility and agreement metrics only | No (descriptive), unless the partner's SAP says otherwise |

Stage dependencies: Stage 1 fixes the final task order, the P4 definition and the time caps
**before** the Stage 3 SAP is locked. Stage 2 can run in parallel with Stage 3. Stage 4 starts
only after Stage 3 passes, or after a documented decision to proceed with the failing primary
scores demoted. Stage 5 can overlap Stage 4. Stage 6 needs a partner.

### 1.1 Primary scores (provisional names; final definitions locked in the SAP)
| Code | Score | Task | Direction | Applies to |
|---|---|---|---|---|
| P1 | Effective throughput (bits/s), Soukoreff & MacKenzie 2004 mean-of-means, univariate We | A2 | higher = better | Pointing modalities only. Not computed for switch scanning |
| P2 | Achieved bitrate (bits/s), Nuyujukian et al. 2015 | A4 | higher = better | All modalities |
| P3 | Correct characters per minute (ccpm) | E1 (3 phrases in the core battery) | higher = better | All modalities |
| P4 | dADL time index: mean of log10(time to complete) over F2, F3 (4 trials) and F5. Assisted or incomplete trials are set to the task cap (cap fixed after Stage 1) | F2, F3, F5 | lower = better | All modalities |

Secondary scores: A2 error rate and path efficiency; A3 unintended dwell selections (dwell users);
A1 movement time; C1 time to select; D1 time and unintended drops; E1 total error rate (Soukoreff
& MacKenzie 2003); ASSIST-event counts; NASA-TLX raw; fatigue numeric rating scale (NRS).
Wolpaw ITR is reported only as flagged secondary, because its assumptions are violated
(`methods_references.md` §C).

**Core battery** (Stages 2–6): A1, A2, A4, C1, D1, E1 (3 phrases), F2, F3, F5, in that fixed
order unless Stage 1 shows a better order. **Full battery** (Stage 1 only): all 18 tasks A1–F7.

---

## 2. Cross-cutting design rules

### 2.1 Disentangling practice, learning, fatigue, device, ability, difficulty and session variability
These sources are separated **by design** first, then **by model**.

| Source | Design control | Model term (SAP §6) |
|---|---|---|
| Individual ability | Within-subject designs; each participant is their own control | Random intercept u_i (person) |
| Practice across sessions | Familiarization session S0 (not analysed for reliability); fixed inter-session interval 2–7 days | Session fixed effect (S0..S3) and test of S1→S3 trend |
| Learning within session | Practice block before each task; trial index logged | Trial-within-block slope (fixed); random slope if supported |
| Fatigue within session | Rest rules (§2.3); pre/post fatigue NRS; randomized task-family order in Stage 1 | Position-in-battery fixed effect; elapsed-time-on-task; fatigue NRS change |
| Device / modality differences | Williams Latin square for modality order (Stage 2); fixed device per participant in Stages 3–4 | Modality fixed effect; person × modality random effect |
| Task difficulty | Fitts design (A2: D × W, IDe 1.9–4.1 bits); A5 deadlines; D1 zone sizes | Index of difficulty or condition fixed effect |
| Session (day) variability | Same time of day ±2 h, same setup checklist, same administrator where possible | Person × session random effect (occasion variance), which enters SEM_agreement |
| Carry-over between modalities | Williams square, balanced for first-order carry-over | Sequence and period terms; carry-over term in sensitivity |
| Order of tasks | Williams 6 × 6 over task families (Stage 1) | Period/position term |
| Timing hardware | Pinned browser and OS; in-session timing self-checks (`browser_timing.md` §5) | Device-class covariate; invalid-trial exclusion rule |

The generic model, fitted with statsmodels `MixedLM` (variance components) and cross-checked in
R `lme4` [INF], is:

```
y_{i s m t} = β0 + β_session[s] + β_modality[m] + β_period[p] + β_position[q] + β_difficulty·ID_t
            + β_trial·trialindex_t + u_i + w_{i m} + v_{i s} + e_{i s m t}
u_i ~ N(0, τ²_person), w_{im} ~ N(0, τ²_person×modality), v_{is} ~ N(0, τ²_occasion), e ~ N(0, σ²)
```

- Trial-level outcomes (log MT, success) use this model; logistic GLMM is used for success.
- Session-level scores (P1–P4) drop the trial terms.
- `psychometrics.mixed.fit_repeated_measures_lmm` covers the random-intercept / random-slope
  repeated-measures case. The crossed person × session × modality model needs a variance-component
  extension, which must be implemented and verified against `lme4` before the SAP lock [INF; work
  item].

### 2.2 Randomization and counterbalancing
- **Modality order (Stage 2):** Williams design for 4 modalities. Sequences: ABDC, BCAD, CDBA,
  DACB. Every ordered pair appears once, so the design is balanced for first-order carry-over
  [PK, Williams 1949]. Allocation to sequence uses permuted blocks of 4. The sequence list is
  generated by a seeded script before enrolment (seed recorded in the SAP), and a
  non-founder team member holds it.
- **Task-family order (Stage 1):** Williams 6 × 6 over families A, B, C, D, E, F (6 sequences;
  n = 42 = 7 per sequence). Stage 1 is the only stage that randomizes task order. Stages 3–4 use
  one fixed order, because reliability requires identical conditions across sessions.
- **Within-task stimuli:** fixed seeds per session (`battery.stimuli(task_id, seed)`). Test
  sessions S1–S3 use **different seeds with identical parameters**, so that memorized target
  positions or phrases cannot inflate retest scores. The seed schedule is in the SAP.

### 2.3 Fatigue and rest rules (all stages)
- Fatigue NRS (0–10, an original NeuroMetric single item; unvalidated) is collected before the
  session, after each task family, and at the end.
- **Mandatory breaks:** ≥2 min between task families; ≥5 min after every 20 min of cumulative
  task time.
  - AT users: ≥5 min after every 15 min of task time, plus wheelchair pressure relief at the
    participant's usual interval, typically every 15–30 min [PK].
- Participant- or care-partner-initiated pause at any time (Space/switch "pause" and a verbal or
  AAC "stop" signal agreed at setup).
- **Stop or reschedule rule:** fatigue NRS ≥ 7, or a rise of ≥ 3 points from pre-session; any
  pain, eye strain or discomfort the participant wants to stop for; any safety sign in §2.4.
  Stopped sessions are rescheduled, not penalized. The stop is logged as a missing-data reason
  ("fatigue").
- **Hard session cap:** 90 min including setup for AT users, 75 min for able-bodied
  participants. AT sessions may be split over two days only by a pre-specified rule (Stage 4
  protocol).

### 2.4 Safety considerations
The interventions are computer tasks. Physical risk is low [INF]. Foreseeable risks are:
- fatigue;
- frustration or distress at poor performance;
- eye strain and dry eye (eye-gaze dwell);
- neck or shoulder strain (head pointer, joystick);
- skin pressure from prolonged sitting;
- in SCI at T6 and above, **autonomic dysreflexia** triggers such as a full bladder or pressure.
  Staff learn the signs, the participant's own management plan is followed, the session stops
  immediately, and the participant's care partner and clinician are contacted per their plan
  [PK].
- in ALS, respiratory fatigue: watch for dyspnoea, follow the participant's own non-invasive
  ventilation routine, stop on request;
- photosensitivity: the battery has no flashing stimuli; B2 has a reduced-motion option.

Privacy risk: a breach of pseudonymized performance data. No content, gaze coordinates, audio or
video recordings are stored (`docs/irb/data_management_plan.md`). Sessions are not diagnostic, and
scores are not interpreted clinically for the participant. PHQ-9 is **not** used in Stages 1–5,
because it would need a clinician-run item-9 safety workflow (`instruments.md`).

### 2.5 Missing data (all stages)
- **Prevention:** flexible scheduling, reminders, travel support, a home-session option (Stage 4)
  with the setting held fixed within a participant, and sessions split by rule.
- **Recording:** every missing session or task has a reason code (participant choice, fatigue,
  illness, technical failure, device unavailable, withdrawal, death). This uses the study
  module's `missing_data` table and `psychometrics.mixed.missing_data_summary`. Little's MCAR
  test (`little_mcar_test`) is descriptive only.
- **Primary assumption:** missing at random (MAR) given observed scores, session, modality,
  diagnosis and baseline fatigue. Mixed models use all observed data and are valid under MAR.
- **ICC:**
  - primary is complete-case two-way ANOVA ICC(A,1), with the subjects dropped and the reasons
    reported;
  - sensitivity 1: `icc(..., missing="mixed")` (REML on all available data);
  - sensitivity 2: multiple imputation by chained equations, m = 50, predictive mean matching,
    with Rubin's rules on Fisher-z-transformed ICCs.
  The psychometrics package does not implement multiple imputation. Use R `mice` or statsmodels
  `MICE`, and verify on simulated data before the SAP lock [INF].
- **Missing not at random (MNAR) sensitivity:** a delta-adjusted **tipping-point analysis**.
  Imputed scores of non-completers are shifted unfavourably by δ = 0, 0.1, …, 1.0 SD of the
  observed score until the confirmatory conclusion flips. The tipping δ is reported, and the
  plausibility of that δ is judged by the faculty PI and statistician. This matters most in ALS,
  where dropout is linked to progression [INF].
- **Task-level non-completion is data, not missingness.** A participant who cannot complete E1
  scores at the cap or floor and is counted in floor/ceiling (Terwee 2007 >15% rule, applied to
  capped or timed-out trials).

### 2.6 Withdrawal
Participants may withdraw at any time without penalty. Compensation is prorated to the end of the
last visit. Each consent form asks in advance whether, on withdrawal, data collected so far may be
**retained** (default) or **deleted**. This maps to the study module's
`withdrawal_action_default` ∈ {retain, delete} and per-scope withdrawal (`study/consent.py`).
Deletion cannot reach data already included in a locked, de-identified analysis dataset or a
publication. The consent form says so. Investigator-initiated withdrawal applies for safety, for
inability to follow procedures, or if eligibility is lost.

### 2.7 Retention of participants
- Reminders by the participant's preferred accessible channel.
- Same staff member where possible; transport and parking reimbursement; a home-visit option for
  AT users.
- Visit windows: ±3 days in Stage 3; ±7 days in Stage 4 longitudinal visits.
- No "completion-only" payment large enough to be coercive (§2.8).

### 2.8 Compensation (all amounts [HYP]; subject to funding, IRB and university payment rules)
| Stage | Proposed | Basis |
|---|---|---|
| 1 | $20 per visit (1 visit, ~75 min) | ≈ $16/h, typical campus-study range [HYP] |
| 2 | $25 per visit (2 visits) = $50 | longer setup and calibration |
| 3 | $20 per visit × 4 = $80, plus $10 if all visits completed (≤ 15% of total) | small completion bonus to cut attrition without coercion [HYP] |
| 4 | $40 per visit (≈ $30/h) + parking/travel reimbursement + $20 per visit for an accompanying care partner | higher burden; travel with AT is costly [HYP] |
| 5 | $30 setup + $15 per home battery (×3: days 1, 8, 14) + $2 per diary day (care partner, up to $28) + $30 closeout interview ≈ $133 per dyad | prorated [HYP] |
| 6 | Per partner protocol | — |

Payment route (gift card or university payment system) and tax-reporting thresholds: [UNR],
confirm with the faculty PI's unit business office. **If the founder's company funds any
payment**, that funding must go through a university-approved sponsored-research or gift route
and be disclosed in the COI review and in the consent form [INF].

### 2.9 Analysis-plan locking (all confirmatory hypotheses)
1. The SAP for each stage is written from `docs/clinical/STATISTICAL_ANALYSIS_PLAN_TEMPLATE.md`.
   The draft for Stages 1–3 is `docs/clinical/sap_stage1_3.md`.
2. Before the first participant is enrolled in that stage:
   a. the analysis code is frozen at a git commit, and its commit hash is recorded in the SAP;
   b. SAP v1.0 is exported to PDF and to the Markdown source, and `sha256sum` of each is
      recorded in the SAP header and in `docs/clinical/sap_hash_log.md` (created at lock time);
   c. the SAP and hashes are registered on **OSF Registries** (OSF preregistrations are frozen
      and time-stamped [PK]). The registration DOI is added to the IRB file as a protocol
      amendment if the IRB wants it.
3. A simulated "dry-run" dataset (`neurometric.simulator`) is analysed with the frozen code
   before locking, to prove the pipeline runs end to end. Simulated results are never reported
   as findings.
4. Changes after the lock are logged in the SAP deviations log, with date, reason, and whether
   unblinded data had been seen. Any change to a confirmatory rule after data access demotes that
   hypothesis to exploratory.
5. **Confirmatory hypotheses**: H2.1, H3.1, H4.1, H4.2, H4.3. All other hypotheses are
   secondary or exploratory and are labelled as such in reports.

### 2.10 Required approvals and preconditions (all stages)
| Item | Status | Source |
|---|---|---|
| Faculty PI agrees and is eligible under RP-19 | **Not obtained** | [V] RP-19 |
| UIUC IRB review via IRBOnline (OPRS decides exempt / expedited / full) | Not submitted | [V] https://oprs.research.illinois.edu/submissions/submitting-irb |
| CITI "Core IRB Training" for everyone engaged; valid 3 years | Not done (`docs/irb/citi_training_checklist.md`) | [V] https://oprs.research.illinois.edu/training/human-subjects-research-training-citi |
| COI disclosure: OPRS says the requirement covers "Any individual participating on a study reviewed by the IRB" (enforced from March 23, 2026 per the OPRS news page) | Not done | [V] https://oprs.research.illinois.edu/news/conflict-interest-coi-requirement-goes-100-live-march-23rd |
| COI management plan reviewed by the UIUC COI office (coi@illinois.edu per the research.illinois.edu page) | Draft only | [V] page; plan content [INF] |
| Carle sites or patients: Carle Research Services Request Form, reviewing IRB decided, reliance agreement documented | Not started | [V] https://oprs.research.illinois.edu/reliance/research-carle |
| SRAlab: Northwestern University IRB provides oversight for SRAlab under an MOU; a reliance or authorization agreement is needed | Not started | [V] https://irb.northwestern.edu/reliance/nu-affiliates-chicagoland-partners.html |
| Non-Illinois team members: Reliance Consultation Request to OPRS (not the Research Team Form) | Not started | [V] https://oprs.research.illinois.edu/research-topics/im-working-non-illinois-researchers-or-study-team-members |
| FERPA consent if student records are used; the IRB cannot waive FERPA consent | Avoided by design (no student records) | [V] https://oprs.research.illinois.edu/research-topics/research-illinois-students-and-student-data |
| Instrument licences (commercial user status; `instruments.md`) | Not requested | [V]/[UNR] per instrument |
| Data security / data-classification review by the university | Not started | [UNR] process name |
| OSF preregistration per stage | Not done | — |
| ClinicalTrials.gov registration | Probably not legally required: no FDA-regulated product is studied [INF]. Recommended for Stage 4 for transparency | [INF] |

---

## 3. Stage 1: controlled able-bodied functional testing

**Research question.** In able-bodied adults using a standard mouse, does each task produce
valid, complete, interpretable data with the expected speed–accuracy structure, and what are the
order, fatigue and floor/ceiling characteristics of the full battery?

**Hypotheses (pre-specified feasibility criteria; not confirmatory):**
- H1.1 (validity of instrument mechanics): valid trials / administered trials ≥ 0.95, with lower
  95% Wilson bound ≥ 0.90. A valid trial has no focus loss, no technical fault and a passed
  timing self-check.
- H1.2 (Fitts structure, A2): the per-participant linear regression of MT on IDe has median
  R² ≥ 0.80, and the group regression on condition means has R² ≥ 0.90 [HYP thresholds;
  consistent with HCI norms, PK].
- H1.3 (floor/ceiling): for P1–P4 and A-family success rates, ≤ 15% of participants are at the
  best or worst possible value (Terwee et al. 2007 criterion [PK]). Ceiling is expected for A1
  success in able-bodied users, so A1 success is a floor task, not a discriminating score. That
  is reported, not "failed".
- H1.4 (timing): ≥ 95% of sessions pass the in-session timing self-check (rAF interval stable,
  dropped frames ≤ 1% of task frames, `crossOriginIsolated` recorded).
- H1.5 (order/fatigue, estimation): the position-in-battery effect on log MT (A-family) has a
  95% CI that excludes a slowing of more than 10% per family position [HYP]. If it does not,
  the battery is shortened for Stages 3–4.

**Design.** Single-visit, cross-sectional, randomized task-family order (Williams 6 × 6).

**Eligibility.**
- Inclusion: age 18–65; self-reported normal or corrected vision; daily computer mouse use;
  English reading.
- Exclusion: self-reported neurological or upper-limb condition affecting computer use;
  photosensitive epilepsy; prior participation in NeuroMetric testing.
- Founder's classmates and direct reports are excluded from recruitment by the founder. See the
  COI plan.

**Sample size.** n = 42 (7 per Williams sequence). Justification:
- Precision of the valid-trial rate: with ~15,000 trials the per-trial estimate is very precise.
  The binding unit is the participant: if 40/42 participants have ≥ 95% valid trials, the Wilson
  95% CI for that proportion is about 0.84–0.99 (computed: 38/40 → 0.835–0.986).
- Fitts regressions: 6 conditions per participant give 4 residual df each. The group R² rests on
  42 participants.
- Balance needs a multiple of 6.

**Burden.** One visit of about 75 min: 10 min consent, 5 min setup, about 45 min of task time
(full battery), 15 min breaks and questionnaires (NASA-TLX raw after families A, E, F; SUS once at
the end).

**Data collected.** Canonical event logs; per-trial timing fields (`browser_timing.md` §6);
demographics (age band, sex, handedness, computer-use frequency); NASA-TLX; SUS; fatigue NRS.

**Analyses.**
- Descriptives per task.
- Fitts regressions.
- Mixed model for position effects (§2.1).
- `floor_ceiling`.
- Proposed P4 cap = the 99th percentile of able-bodied time × 3 [HYP rule].
- Decision on the final core-battery order.

**Approvals and safety.** Minimal risk expected [INF]. Standard fatigue rules.

## 4. Stage 2: input-modality comparison (able-bodied, emulated AT)

**Research question.** Do NeuroMetric scores order input modalities in the expected direction,
and how large are modality offsets compared with person-level variability?

**Modalities (A–D):**
- A = standard mouse;
- B = camera-based head pointer with dwell click;
- C = eye-gaze OS pointer with dwell (consumer eye tracker; gaze coordinates are not stored);
- D = single-switch row/column scanning via a USB switch interface. P1 is not computed for D.

**Hypotheses.**
- **H2.1 (confirmatory).** On P2 (achieved bitrate, A4): A > B, A > C, A > D, B > D, C > D.
  These are five directional paired contrasts on log P2 from the mixed model, Holm-adjusted at
  familywise α = 0.05 (one-sided per contrast).
  - Success criterion: all five significant in the predicted direction.
  - B vs C is two-sided exploratory, with no directional hypothesis.
- H2.2 (secondary): same ordering on P3 and P4.
- H2.3 (secondary): NASA-TLX raw is higher for B, C and D than for A (paired, Holm).
- H2.4 (estimation): modality offsets on the log scale with 95% CI. Bland–Altman (log scale,
  `bland_altman`) is used **only** to describe the systematic offset and limits between
  modalities. Modalities are not expected to agree, and interchangeability is not tested.

**Design.** Within-subject crossover, 4 modalities in a Williams square, 2 modalities per visit,
2 visits 2–7 days apart. Each modality block has a 5-min standardized training, then the core
battery subset A1, A2 (W ≥ 64 px for B/C), A4, E1 (2 phrases), F3.

**Eligibility.** As Stage 1. Additional exclusions: unable to calibrate the eye tracker after
3 attempts (recorded as a calibration failure, not missing at random); neck problems that
contraindicate head-pointer use.

**Sample size.** n = 24 (6 per sequence). For an expected standardized paired effect dz ≥ 0.8 on
log P2 between neighbouring modalities [HYP, plausible given known speed differences between
mouse and switch scanning, PK], the power of a one-sided paired t-test at Holm's most stringent
level (α = 0.05/5 = 0.01) with n = 24 is 0.91 (dz = 0.8), 0.99 (dz = 1.0) and 0.67 (dz = 0.6).
dz = 0.6 would need n ≈ 31 (computed, statsmodels `TTestPower`). The mixed model uses all four
periods, so it is at least as efficient as these paired tests [INF]. Contrasts against D are
expected to be much larger.

**Limitations (must be stated in every report).** Able-bodied novices using emulated AT do not
represent experienced AT users (learning, settings and strategies differ). Stage 2 shows that
the instrument **can detect** modality differences. It says nothing about AT-user norms.

**Burden.** Two visits of about 75 min each.

**Equipment.** See `docs/clinical/stage2_protocol.md`. Tobii devices carry licence restrictions
on analytical use. NeuroMetric uses only the OS pointer and stores no gaze data
(`platform_matrix.md`).

## 5. Stage 3: test–retest reliability and measurement error (able-bodied)

**Research question.** After familiarization, how reliable (ICC) and how precise (SEM, MDC95,
limits of agreement) are P1–P4 across days, on the same device and setup?

**Hypotheses.**
- **H3.1 (confirmatory, co-primary).** For each of P1, P2, P3 and P4, ICC(A,1) (two-way random,
  absolute agreement, single measurement; `psychometrics.icc`, form "2,1") over test sessions
  S1–S3 has a **McGraw–Wong lower 95% CI bound ≥ 0.75**. The battery-level claim needs all four
  to pass (intersection–union test, so no multiplicity adjustment is needed). Per-score claims
  are also reported with Bonferroni 98.75% lower bounds as a sensitivity analysis.
- H3.2 (secondary). SEM_agreement (variance components) and MDC95 = 1.96·√2·SEM with 95% CIs.
  Pre-specified precision target: the SEM 95% CI is within about ±15% of the estimate. With
  (n − 1)(k − 1) = 98 df, the chi-square-based multiplier interval is [0.88, 1.16].
- H3.3 (secondary, practice). The mean change S1→S3 for each primary score lies within
  ±0.5 × SEM (TOST, `psychometrics.tost`, 90% CI) [HYP margin]. Failure means a practice
  effect persists after S0. It is reported, and the number of familiarization sessions is
  revisited for Stage 4.
- H3.4 (secondary). Generalized confidence interval (GCI) lower bound for ICC(A,1), and
  ICC(C,1), are reported alongside H3.1.

**Design.** Four visits: S0 familiarization (full practice of the core battery, not analysed for
reliability), then S1, S2 and S3 at 2–7-day intervals, at the same time of day ±2 h, on the same
laptop/browser/mouse/display, with the same administrator where possible. Stimulus seeds differ
by session (§2.2). Task order is fixed (from Stage 1).

**Eligibility.** As Stage 1, plus availability for four visits within 4 weeks. People who took
part in Stage 1 or 2 are excluded, because they have prior exposure.

**Sample-size justification (calculations shown).**
1. *Analytic, hypothesis-testing approach* (Walter, Eliasziw & Donner 1998 [PK]):
   n = 1 + 2k(z_{1−α} + z_{1−β})² / [(ln C0)²(k − 1)], with
   C0 = (1 + kρ0/(1 − ρ0)) / (1 + kρ1/(1 − ρ1)), one-sided α = 0.025, power 0.80.
   - ρ0 = 0.75, ρ1 = 0.88, k = 2 → n = 49.4
   - ρ0 = 0.75, ρ1 = 0.88, k = 3 → n = 34.9
   - ρ0 = 0.75, ρ1 = 0.90, k = 2 → n = 32.5
   (Computed this session.)
2. *Analytic, precision approach* (Bonett 2002 [PK]; Zou 2012 adds assurance [PK]):
   n = 1 + 8z²(1 − ρ)²(1 + (k − 1)ρ)² / [k(k − 1)w²].
   - ρ = 0.85, k = 2, full width w = 0.20 → n = 30.6
   - ρ = 0.88, w = 0.15 → n = 35.8
3. *Both formulas assume no systematic session effect.* ICC(A,1) also penalizes systematic
   session shifts (practice), and its CI depends on the session variance, which k − 1 df
   estimate. A Monte Carlo study using the project's own `psychometrics.icc` (400 replicates per
   cell; two-way random model) gave P(McGraw–Wong lower bound ≥ 0.75):

   | n | k | session variance (share of total) | true ICC 0.75 (false-pass) | true 0.88 | true 0.90 |
   |---|---|---|---|---|---|
   | 50 | 2 | 0 | 0.010 | 0.80 | 0.94 |
   | 50 | 2 | 0.03 | 0.025 | 0.59 | 0.62 |
   | 50 | 3 | 0 | 0.015 | 0.91 | 0.99 |
   | 50 | 3 | 0.03 | 0.030 | 0.64 | 0.69 |
   | 50 | 3 | 0.08 | 0.068 | 0.36 | 0.32 |
   | 60 | 3 | 0 | 0.020 | 0.96 | 1.00 |

   The GCI lower bound was far more conservative in every scenario (P(pass) ≤ 0.08 with k = 2 and
   any session variance). That is why GCI is a sensitivity analysis, not the decision rule.
   **Interpretation [INF]:** with k ≤ 3, adding participants cannot fix uncertainty about
   systematic session shifts. Only design can: familiarization to a plateau, and more sessions.
   This is the reason for S0 plus three test sessions.
4. **Decision:** 50 completers with k = 3 test sessions. Enrol 60 to allow about 17% attrition
   over 4 visits [HYP attrition rate]. If the observed systematic S1→S3 shift is small
   (H3.3 passes), power is about 0.9 at true ICC 0.88. If practice persists, power falls to about
   0.6, and the plan says so in advance.

**Burden.** S0 about 50 min; S1–S3 about 40 min each (core battery about 20–25 min of task time
plus NASA-TLX, fatigue NRS and breaks). Total about 2 h 50 min over ≤ 4 weeks.

**Analyses.**
- `icc` (forms 2,1 / 3,1), with GCI and McGraw–Wong CIs.
- `icc_mixed` sensitivity.
- `sem_mdc` from variance components (de Vet et al. 2006).
- `bland_altman` on log scale for S1 vs S2 and S2 vs S3, with proportional bias.
- Mixed model with session fixed effects (practice).
- `floor_ceiling`.
- MDC is labelled **"distribution-based estimate, not an MCID"** (`DISTRIBUTION_LABEL`).

## 6. Stage 4: validation with AT users (ALS, SCI, stroke)

**Research questions.** In adults who use AT for computer access:
- (a) Can the scores tell apart groups that should differ (known-groups validity)?
- (b) Do they relate to other measures as predicted (convergent/divergent: COSMIN hypotheses
  testing)?
- (c) Are they reliable across days with the participant's own AT?
- (d) What are the floor/ceiling effects?
- (e) In a longitudinal sub-study, are they responsive to change where an external anchor exists?

**Cohorts.** About 15 each: ALS (any El Escorial category, self-reported diagnosis confirmed by
clinician letter or partner site); cervical/high-thoracic SCI (≥ 12 months post-injury); chronic
stroke (≥ 6 months) with upper-limb impairment affecting computer use. All use AT or adapted
access at least weekly: eye gaze, head pointer, joystick (incl. mouth joystick), trackball,
switch scanning, voice control with pointer grid, or adapted mouse.

**Eligibility.**
- Inclusion: age ≥ 18; able to consent (§6.4); able to see the screen; uses an access method
  supported by the battery; can tolerate a 60–90-min session with breaks.
- Exclusion: unable to give informed consent personally (no LAR consent in this program, §6.4);
  acute illness; a planned change of access method within the retest window.
- **People with implanted BCIs are not recruited by NeuroMetric** (Stage 6 only, under the
  device study's protocol).

**Known groups (pre-specified definitions).**
- **KG1:** AT users (Stage 4, own AT) vs able-bodied (Stage 3, mouse, S1). Expected large
  difference on P2 and P3: AUC ≥ 0.85 (d ≈ 1.5, AUC = Φ(d/√2) = 0.856). This is a weak
  validity test because modality and impairment are confounded. It is reported, but not
  overweighted.
- **KG2:** within AT users, direct-selection methods (any continuous pointer: eye gaze, head
  pointer, joystick, trackball, adapted mouse) vs switch scanning. Expected scanning < direct on
  P2 and P3, d ≈ 1.0, AUC ≈ 0.76.
- **KG3:** within AT users, care-partner- or self-reported need for help to use a computer or
  tablet on most days (from the NeuroMetric original assistance diary; unvalidated, so the
  hypothesis is labelled as resting on an unvalidated criterion) vs independent use. Expected
  lower P4 (worse dADL time) in the assisted group, d ≈ 0.8.

**Convergent/divergent hypotheses (direction and magnitude; COSMIN "sufficient" if ≥ 75% are
confirmed, Prinsen et al. 2018 [PK]).** Point estimates are judged against the predicted range.
95% CIs are reported (`correlation_ci`).

| # | Score | Comparator (licence status, `instruments.md`) | Predicted r |
|---|---|---|---|
| C1 | P3 ccpm | P2 achieved bitrate | ≥ 0.60 |
| C2 | P4 dADL time (log) | P2 | ≤ −0.50 |
| C3 | P2 | NASA-TLX raw overall (free) | −0.30 to −0.60 |
| C4 | P4 | SUS of the participant's own AT (free) | weak, \|r\| 0.10–0.40 (usability ≠ ability) |
| C5 | P1 (pointing users) | Neuro-QoL Upper Extremity / PROMIS PF upper-extremity items (**licence required**, commercial user) | 0.30–0.60 (stroke/SCI pointing users only) |
| C6 | P2 | QUEST 2.0 device satisfaction (**commercial terms UNR**) | weak, 0.10–0.40 |
| C7 | P2 | PIADS competence subscale (**commercial terms UNR**) | 0.20–0.50 |
| C8 | ASSIST-event rate per session | Care-partner diary digital-help minutes (original; unvalidated) | ≥ 0.40 |
| C9 | P2 | IRF-PAI Section GG self-care (free, public domain expected; confirm) | weak, 0.10–0.40 (different construct: divergent) |
| C10 | P1–P4 | Age | \|r\| ≤ 0.30 within cohort (divergent) |

If a licence is not granted before the SAP lock, that hypothesis is removed **before** locking,
and the 75% criterion is applied to the hypotheses that remain. COPM (licensed, COPM Inc.) is
used only as a semi-structured goal interview for content-validity notes, not as a scored anchor,
unless a licence covering electronic use is obtained. **We do not modify COPM.**

**Hypotheses.**
- **H4.1 (confirmatory, known groups).** KG2 on P2: AUC (`known_groups`, DeLong CI) ≥ 0.70 point
  estimate, with lower 95% bound > 0.50, in the predicted direction. KG1 is reported in support.
- **H4.2 (confirmatory, construct).** ≥ 75% of the locked convergent/divergent hypotheses are
  confirmed.
- **H4.3 (confirmatory, floor).** In each diagnostic cohort, ≤ 15% of participants are at the
  floor (zero correct selections or capped time) on P2 and P4. If this fails, the battery needs
  a lower-demand version for that group. That is an informative negative result.
- H4.4 (secondary-confirmatory, reliability). ICC(A,1) lower 95% bound ≥ 0.75 for each
  applicable primary score, own AT, S1 vs S2 (k = 2) after S0, with an optional S3.
- H4.5 (exploratory). Measurement invariance of reliability across diagnoses
  (`compare_icc_across_groups`; `INVARIANCE_SCOPE_NOTE`).

**Design.** S0 familiarization (own AT, settings recorded), S1 and S2 at 3–7-day intervals in
the participant's chosen setting (lab or home), held fixed. Home sessions are run with a
researcher present in person, or by video call if the IRB approves; no recording. An optional S3
gives planned-missing data for `icc_mixed`. Questionnaires are at S1 (participant and care
partner), and the care-partner assistance diary runs for the 7 days after S1.

**Sample size.**
- 45 enrolled (15 per cohort). We expect about 36 with S1 and S2 (20% attrition [HYP]; higher
  in ALS).
- KG2: with about 27 direct-selection vs 9 scanning users, two-sided t-test power at d = 1.0 is
  0.71, and at d = 1.2 is 0.86. With 24 vs 12, power at d = 1.0 is 0.79 (computed). Recruitment
  will target ≥ 10 switch-scanning users.
- Convergent correlations at n = 36: power vs ρ0 = 0 is 0.88 for r = 0.5 and 0.68 for r = 0.4.
  The 95% CI for an observed r = 0.5 is about 0.21–0.71 (computed). COSMIN judges magnitude
  against the prediction, so precision is the binding issue. This is stated as a limitation.
- Reliability (Monte Carlo with `psychometrics.icc`, n = 36):
  - k = 2, true ICC 0.90 (AT samples are heterogeneous, so between-person variance and ICC are
    plausibly higher [HYP]): P(pass) = 0.82 with no systematic session shift, 0.67 with 2%
    session variance;
  - k = 3: 0.93 / 0.79;
  - false-pass at true 0.75: ≤ 0.033.
  This is why H4.4 is secondary.
- Known groups KG1 (36 vs 50, d = 1.5): power about 1.0.
- The total of 45 is also a feasibility ceiling for a single academic site with no existing
  cohort [INF].

**Responsiveness sub-study (anchor-based; exploratory unless powered).**
- ALS participants who agree are re-tested at 3 and 6 months (expected decline).
- Stroke participants enrolled through a partner's rehabilitation program are tested before and
  after it.
- **Anchors:**
  - (a) participant global rating of change in digital-task ability (7-point, original item,
    unvalidated);
  - (b) ALSFRS-R change, clinician-administered by a certified rater at a clinical partner only
    (rights holder UNR: `instruments.md`);
  - (c) for stroke, the partner's existing clinical measure (e.g. FMA-UE or ARAT if the partner
    administers it).
- **Indices:** SRM, Guyatt RI with a stable group (anchor "no change"), and AUC of change scores
  (`responsiveness`); correlation of change with anchor change.
- **MIC** only if anchor–change correlation is ≥ 0.30 (Revicki et al. 2008) and ≥ 30 participants
  changed. Devji et al. 2020 credibility criteria are reported.
- **No MCID is invented.** MDC is reported as "distribution-based estimate, not an MCID".

### 6.4 Consent with limited speech or hand function
Consent is given by the participant through their usual communication method: AAC device, eye
gaze, partner-assisted scanning, or reliable yes/no.
- Comprehension is confirmed by a teach-back check (original questions, ≥ 4/5 correct, with
  re-explanation allowed).
- Signature is by electronic signature with verified identity, by a mark, or by a witness
  signature for a participant physically unable to sign. OPRS lists a Witness Signature Page
  among its consent templates. [V] https://oprs.research.illinois.edu/research-topics/consent-templates
- **No legally authorized representative (LAR) consent** is used. People who cannot consent
  personally are excluded, because this research offers no direct benefit and OPRS flags
  additional safeguards for impaired capacity. [V]
  https://oprs.research.illinois.edu/research-topics/vulnerable-populations
  Whether Illinois law permits research surrogate consent is [UNR] and is not relied on.

**Burden.** S0 about 60 min; S1 about 90 min (battery plus questionnaires); S2 about 60–75 min;
optional S3 about 60 min; care-partner diary 2 min/day for 7 days. All with breaks (§2.3).

**Approvals.** UIUC IRB. Carle (if recruiting Carle patients) through the Carle Research Services
route. Any external site needs a reliance consultation. HIPAA authorization applies where a
covered entity's records are used for recruitment or diagnosis confirmation.

## 7. Stage 5: home-use telemetry feasibility
See `docs/clinical/HOME_USE_FEASIBILITY.md`:
- n = 5 AT-user dyads for 2 weeks;
- Windows or Android per the platform matrix;
- weekly browser battery at home;
- aggregate telemetry only;
- a daily 2-min care-partner diary.

Success criteria: ≥ 4/5 usable logs; ≥ 80% of days complete; burden ratings at or below
pre-specified limits. **It cannot show** reliability, validity, real-world benefit or
generalizability.

## 8. Stage 6: clinical collaboration with neural-interface or rehabilitation-device users
See `docs/clinical/stage6_protocol.md` and `docs/clinical/SRALAB_APPROACH.md`.
- NeuroMetric is a **tool inside a partner's IRB-approved protocol**, for example SRAlab, a
  BrainGate site, or a Carle/JNERL rehabilitation study. It is never the sponsor of an implanted
  device study.
- Questions are set with the partner. Candidates include agreement between in-clinic and home
  performance, the sponsor-export join (Tier 2 telemetry), and the measurement chain
  (`MEASUREMENT_CHAIN_STUDY.md`).
- Sample size is set by the partner's cohort, typically 2–15 implanted participants
  (`clinical_trials.md` §2). The analysis is descriptive, with individual-level graphics, and no
  group-level validity claims.
- Data rights, IP, publication and the role of any device-company collaborator must be agreed in
  writing first.

---

## 9. Timeline (indicative only [HYP]; starts when a faculty PI agrees)
| Months from PI agreement | Activity |
|---|---|
| 0–2 | CITI; COI disclosure and management plan; IRB submission (Stages 1–3 as one protocol with stage-specific procedures); bench timing validation |
| 2–4 | IRB review; OSF lock of SAP v1.0 (Stages 1–2 parts) |
| 3–5 | Stage 1 |
| 5–6 | Lock Stage 3 SAP (P4 and caps from Stage 1); amendment |
| 5–9 | Stages 2 and 3 |
| 8–10 | Licences; Stage 4 amendment or new protocol; reliance (Carle) |
| 10–18 | Stage 4; Stage 5 overlaps from month 12 |
| Partner-dependent | Stage 6 |

## 10. What this program will not show
- Clinical benefit of any device.
- An MCID.
- Equivalence with or superiority over the SRAlab DAI or any licensed instrument.
- Diagnostic accuracy.
- Causal effects of device performance on independence or quality of life.
- Generalization beyond English-speaking adults at the sites used.
