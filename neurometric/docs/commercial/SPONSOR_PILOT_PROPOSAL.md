# Sponsor / manufacturer evidence pilot: proposal template

**Template prepared 2026-11-27. Not sent to anyone. All prices are hypotheses [HYP] to be tested in discovery
(`PRICING_HYPOTHESES.md`).** Replace bracketed fields per prospect. Labels per `docs/research/CONVENTIONS.md`.

**Status statement to keep in every version:** NeuroMetric is early-stage research software, not a medical device.
Its technical results to date come from simulation only; it has no clinical validation, no regulatory
qualification and no customers or partners. The pilot is designed to generate the first real-world feasibility
evidence, under the sponsor's (or its academic site's) IRB-approved protocol.

---

## 1. Purpose

Show, in [N ≤ 10] participants over ≤ 6 months, whether a neutral, input-agnostic measurement layer can capture
**home real-world use**, **functional digital-task performance** and **care-partner burden** for [device] with
acceptable feasibility, data completeness and participant burden, and produce an evidence summary that
[sponsor]'s clinical, regulatory or market-access team can evaluate.

Public context to cite (choose per prospect; all [V] unless marked):
- [iBCI sponsor] FDA iBCI guidance has a "Home Use" section and caregiver metrics; the iBCI-CC consensus
  (1 Oct 2026) calls for real-world data and a measurement chain from device performance to function to care burden.
- [Home neuromod / rehab maker] Anthem DME.00052 (reviewed 2026-08-13) lists missing real-world arm use,
  daily-living independence and independent replication for BCI rehabilitation devices.
- [AAC / non-invasive BCI maker] NCD 50.1 covers speech generation and messaging, not general computing; evidence
  that separates medical communication use from leisure use is relevant to SGD funding files.

## 2. Scope

| Module | Included | Notes |
|---|---|---|
| A. Home-use telemetry | Read-only, application-level event logging (selections, text entry, session start/stop, assisted vs independent sessions); import of sponsor device logs if exportable | No OS-level hooks by default (DECISIONS D-008); no device control, no stimulation access, ever |
| B. Periodic home task battery | Short pointing / selection / text-entry tasks every [2-4] weeks; implements consensus primitives (click, scroll, type, drag) rather than a proprietary index | Licensed instruments (e.g., Digital IADL, DAI) only with permission of their owners |
| C. Care-partner module | Zarit Burden Interview (or sponsor's chosen instrument, licence permitting) + brief care-time diary | Time is reported as time; any dollar valuation is labelled hypothetical |
| D. Psychometrics | Test-retest reliability, minimal detectable change, missing-data profile, agreement with sponsor clinic measures | Pre-specified analysis plan agreed before data lock |
| E. Evidence summary | Feasibility report, data dictionary, audit-trail export, mapping to FDA/CMS/payer evidence types (`PAYER_EVIDENCE_MATRIX.md`) | Does not claim regulatory acceptance or coverage |

Out of scope: device control or configuration; clinical decision support; diagnostic or treatment claims; payer
negotiations; HEOR modelling (can be referred to a partner); CRO site monitoring.

## 3. Deliverables

1. Statistical/psychometric analysis plan (week 4).
2. Configured deployment kit and participant/care-partner instructions (week 6).
3. Monthly data-completeness dashboard (weeks 8-22).
4. Final feasibility and psychometric report with data dictionary and audit-trail export (week 26).
5. 60-minute read-out with [sponsor] team; recommendation on whether and how to scale.

## 4. Timeline (26 weeks)

| Weeks | Activity | Dependency |
|---|---|---|
| 0-4 | Kick-off; protocol fit; data-flow and security review; analysis plan | Sponsor vendor qualification questionnaire |
| 4-6 | Configuration; IRB amendment support (documents only; IRB owned by sponsor/site) | IRB approval |
| 6-22 | Home deployment; monthly task sessions; care-partner module | Participant consent |
| 22-26 | Analysis, report, read-out | Data lock |

## 5. Assumptions

- Sponsor (or its academic site) holds IRB approval, consent and participant relationships.
- Data are de-identified before reaching NeuroMetric unless a separate agreement (and, where NeuroMetric acts for a
  covered entity, a HIPAA business associate agreement) is executed.
- Platform status: Part 11-*ready design* (audit trail, access control, time-stamping); a formal computerised-system
  validation package is [not yet complete / in progress] and will be shared when complete. The pilot is not
  intended as a pivotal data source.
- State neural-data laws are reviewed by counsel for the deployment states; NeuroMetric logs interaction events,
  not raw neural signals.
- Sponsor retains ownership of study data; NeuroMetric retains its software and generic, non-identifying method
  improvements. Any cross-sponsor pooling requires separate written consent.
- Insurance: NeuroMetric will carry E&O and cyber cover before deployment (amount [HYP], no quote yet).

## 6. Price options (hypotheses, for discovery testing only)

| Option | Scope | Price range [HYP] |
|---|---|---|
| 1. Retrospective analysis | Modules D + E applied to existing de-identified sponsor logs/task data; no deployment | $25-35K |
| 2. Home pilot | Modules A-E, ≤10 participants, 6 months | $40-60K |
| 3. Home pilot + payer-oriented summary | Option 2 + mapping to a named payer policy's stated evidence gaps | $60-75K |

Payment terms [HYP]: 50% at kick-off, 50% at report. Fixed fee; no auto-renewal. Comparables: OpenClinica
Core/Advanced $36-45K per study-year [V]; small EDC studies $10-50K year 1 [AE].

## 7. Success criteria (agreed before start)

- ≥80% of planned task sessions completed; ≥70% of participant-days with usable telemetry [HYP thresholds].
- Participant and care-partner burden acceptable (e.g., median added time ≤15 min/week) [HYP].
- Reliability (ICC) and MDC reported with confidence intervals, whatever their value.
- Sponsor decision recorded: scale / modify / stop.
