# Stage 3 protocol: test–retest reliability and measurement error (able-bodied)

> **DRAFT. Not submitted. Requires faculty PI and IRB review. No participants enrolled.**
> Plan: `CLINICAL_VALIDATION_PLAN.md` §5. Analysis: `sap_stage1_3.md` Part C (locked after
> Stage 1, before Stage 3 enrolment).

## 1. Objective
Estimate ICC(A,1), SEM_agreement, MDC95 and Bland–Altman limits for P1–P4, and test the
confirmatory H3.1: each McGraw–Wong lower 95% bound is ≥ 0.75 across S1–S3.

## 2. Participants
- 60 enrolled, target 50 completers.
- Eligibility as in Stage 1. Participants must also be available for 4 visits in ≤ 4 weeks, at
  a consistent time of day.
- Prior NeuroMetric participation excludes.

## 3. Schedule
| Visit | Window | Content | Minutes |
|---|---|---|---|
| S0 familiarization | Day 0 | Consent, demographics, setup; core battery run **twice** back-to-back (practice to plateau); not used for reliability | about 50 + 10 consent |
| S1 | S0 + 2–7 days | Core battery (fixed order from Stage 1), fatigue NRS pre/post, NASA-TLX raw at the end | about 40 |
| S2 | S1 + 2–7 days | Same as S1 | about 40 |
| S3 | S2 + 2–7 days | Same as S1; SUS; debrief | about 45 |

**Fixed conditions across S1–S3:**
- same laptop, display, browser build, mouse and chair/desk setup (photo of the setup taken
  with no person in frame, and setup checklist signed);
- the same administrator where possible (the administrator ID is logged so that it can be a
  sensitivity covariate);
- time of day ±2 h;
- no caffeine instruction (participants keep their usual routine and record any deviation);
- stimulus seeds differ by session with identical parameters.

**What counts as a protocol deviation:**
- a visit outside its window;
- a device or browser change (that session leaves the per-protocol set);
- a different administrator (noted only);
- illness (noted).

## 4. Task procedures
Core battery per `stage1_protocol.md` §4: A1, A2, A4, C1, D1, E1 (3 phrases), F2, F3, F5, with a
2-min break after the A family and after E1.

## 5. Burden and compensation
About 2 h 50 min over ≤ 4 weeks. $20 per visit plus a $10 completion bonus [HYP]. The bonus is
≤ 15% of the total, to limit undue influence.

## 6. Retention
- Book all four visits at consent.
- Send reminders 24 h before by the participant's chosen channel.
- Allow one reschedule inside the window.

## 7. Equipment
As in Stage 1 (mouse configuration). Bench timing validation must be complete before S0 of the
first participant.

## 8. Safety
Minimal [INF]. Fatigue rules as in plan §2.3.

## 9. Analysis outline
`psychometrics.icc` (forms 2,1 and 3,1; MW and GCI), `sem_mdc`, `bland_altman` (log scale),
`fit_repeated_measures_lmm` (practice S0–S3), `tost` (H3.3), `floor_ceiling`. Missing data: see
the SAP §8 (complete case primary; `icc_mixed`; MI; tipping point).
