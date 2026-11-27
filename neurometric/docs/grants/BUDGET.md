# NIH STTR Phase I: draft budget and justification

> **DRAFT ESTIMATES ONLY.** Prepared 2026-11-27. Every salary, rate, price and fringe figure is a
> **[HYP] planning estimate** unless a source is given. No institution has provided a rate, no
> person has agreed to an effort level, and no quote has been obtained. UIUC's negotiated F&A
> and fringe rates are **[UNR]**; replace the placeholders with the rates from UIUC Sponsored
> Programs before any submission. The arithmetic was done with a small script so that totals
> are internally consistent; the inputs are assumptions.

---

## 1. Frame

| Item | Value | Source |
|---|---|---|
| Opportunity | NIH STTR Phase I, PA-27-102 | [V] `docs/research/funding.md` |
| Cap used | **NINDS: up to $700,000** Phase I (NOFO budget table) | [V] funding.md §1. Treated here as a **total-cost** cap (direct + F&A + fee) [PK: confirm whether the NINDS figure is total costs] |
| Alternative cap | NICHD (NCMRR) or NIDCD: $400,000 Phase I | [V] funding.md §1; reduced budget in §4 |
| Period | 24 months (two 12-month budget periods) | Phase I duration over 1 year needs justification [PK] |
| Company F&A | 40% of company direct costs (small businesses without a negotiated rate may request up to 40% of total direct costs [PK]) | Confirm in the NIH Grants Policy Statement / SBIR-STTR instructions |
| Fee | 7% of company costs (direct + F&A) [PK: NIH allows a fee up to 7% of total costs; this draft computes it on company costs only, which is conservative] | — |
| Partner RI F&A | **58% of MTDC — placeholder [HYP]**; MTDC excludes participant payments in this draft [PK: institution-specific] | UIUC rate [UNR] |
| Equipment | No item reaches the federal equipment threshold (raised to $10,000 per unit in the 2024 Uniform Guidance revision [PK]); all devices are supplies | — |
| Equipment list source | `docs/founder/EQUIPMENT.md` **does not exist**; items come from `docs/clinical/stage2_protocol.md` §7, `stage4_protocol.md` §8 and `stage5_protocol.md` §3 | Prices [HYP] |

---

## 2. Summary table (US dollars, rounded to the dollar)

| Line | Year 1 | Year 2 | Total |
|---|---:|---:|---:|
| **A. Company (NeuroMetric, Inc.)** | | | |
| Personnel (founder hourly; software engineer 0.4 FTE) | 77,120 | 77,120 | 154,240 |
| Fringe / payroll taxes | 11,930 | 11,930 | 23,860 |
| Consultant: quality / Part 11 computer-system validation | 7,000 | 7,000 | 14,000 |
| Contractual: accessibility audit (Y1), penetration test (Y2) | 6,000 | 6,000 | 12,000 |
| Supplies: bench-timing rig, development test devices | 7,100 | 0 | 7,100 |
| Other: cloud tooling, instrument licences, publication charges | 6,000 | 6,500 | 12,500 |
| Travel: one scientific meeting | 0 | 3,000 | 3,000 |
| **Company direct costs** | **115,150** | **111,550** | **226,700** |
| Company F&A (40%) | 46,060 | 44,620 | 90,680 |
| **Company total costs (excluding fee)** | **161,210** | **156,170** | **317,380** |
| **B. Subaward to partner RI (`[PARTNER RI]`, candidate UIUC)** | | | |
| Salaries (PD/PI, clinical co-I, coordinator, undergraduate RAs, biostatistician) | 63,000 | 77,500 | 140,500 |
| Fringe (placeholder rates) | 23,450 | 29,975 | 53,425 |
| Study supplies, accessible consent materials, local travel, IRB/site fees | 11,360 | 6,000 | 17,360 |
| Modified total direct costs (MTDC) | 97,810 | 113,475 | 211,285 |
| F&A (58% of MTDC, placeholder) | 56,730 | 65,816 | 122,546 |
| Participant and care-partner payments, travel reimbursement (outside MTDC) | 7,440 | 15,245 | 22,685 |
| **Subaward total** | **161,980** | **194,536** | **356,516** |
| **C. Fee (7% of company total costs)** | 11,285 | 10,932 | 22,217 |
| **TOTAL REQUESTED (A + B + C)** | **334,474** | **361,637** | **696,112** |

Totals may differ by $1 from the component sums because of rounding.

**STTR work split** (share of total costs excluding fee; measurement basis [PK]):
company $317,380 (**47.1%**), partner RI $356,516 (**52.9%**). Both minimums (company ≥ 40%,
RI ≥ 30% [V]) are met. If UIUC's real F&A rate is higher than the placeholder, the RI share rises;
the company share stays above 40% unless the subaward grows by more than about $120,000 [INF,
arithmetic on this table]. Reviewers may prefer the company to perform the larger share; moving
the bench-timing work or the engineer's effort up would do that.

---

## 3. Justification

### 3.1 Company personnel
| Role | Effort | Basis [HYP] | Tasks |
|---|---|---|---|
| Founder, technical lead (part-time student employee) | 1,120 h/yr (20 h/week for 32 term weeks + 40 h/week for 12 summer weeks) at $26/h; payroll taxes 8% | Hourly student-employee pay; requires company payroll; international-student work authorisation must be checked first [PK] | Battery and event-model maintenance, scoring pipeline, simulator, analysis-code freezing for each SAP, home agent, bench-timing rig, documentation. **Not** consent, recruitment or confirmatory analysis (COI plan) |
| Software engineer | 0.4 FTE of a $120,000 salary; fringe 20% | Part-time hire or contractor-to-employee | Code review, security hardening, accessibility fixes, Windows/Android Tier 1 agent, release engineering, Part 11-oriented audit trail and validation documentation |

### 3.2 Company other direct costs
- **Quality / Part 11 consultant** (40 h/yr × $175/h): computer-system-validation plan and
  traceability for the study software (FDA eSystems Q&A expectations; `regulatory_landscape.md`
  §4). No compliance claim is made in Phase I (`BLOCKERS.md` X-9).
- **Accessibility audit** ($6,000, Y1): manual testing by people who use screen readers, switch
  access and eye gaze; automated axe tests already exist but do not replace this (MASTER_PLAN
  row 10: "automated only").
- **Penetration test** ($6,000, Y2): before home telemetry is used at scale (Aim 3 runs in
  months 18–22; the test may move earlier if the IRB or university security review asks).
- **Bench-timing rig and development devices** ($7,100): photodiode, microcontroller-driven
  actuator and logic analyser for end-to-end lag (Aim 1a; `browser_timing.md` §5); test devices
  for each supported platform (Windows laptop, Android tablet, Chromebook, Mac mini) and a switch
  interface for development. Participant-facing devices are in the subaward.
- **Cloud and tooling** ($2,500/yr): development, CI and documentation hosting. **No participant
  data** are stored on company infrastructure in Phase I; participant data are hosted by the RI.
- **Instrument licences** ($3,500, Y1): HealthMeasures screenshot review at $750 per measure for
  two PROMIS/Neuro-QoL measures [V price, `EVIDENCE_LEDGER.md` §B] plus a placeholder for
  PIADS/QUEST permissions (fees [UNR]). Licensing is needed for the Aim 2 convergent hypotheses
  (`instruments.md` §3b).
- **Travel** ($3,000, Y2): one meeting (e.g. BCI Society or RESNA) to present Aim 1 results.
- **Publication** ($4,000, Y2): one open-access article processing charge [HYP].

### 3.3 Subaward to the partner research institution
| Role | Effort | Basis [HYP] | Tasks |
|---|---|---|---|
| Faculty PD/PI | 10% (1.2 calendar months) of $150,000; fringe 40% placeholder | NIH STTR minimum 10% effort [V] | IRB PI; scientific direction; SAP ownership; data custody; supervision |
| Clinical co-investigator (PM&R, neurology, OT or SLP) | 2.5% of $200,000 | — | Eligibility, safety procedures (autonomic dysreflexia, respiratory fatigue), recruitment links, interpretation |
| Research coordinator | 0.5 FTE Y1, 0.75 FTE Y2 of $58,000; fringe 45% placeholder | Stage 4 recruitment and home visits drive Y2 | Recruitment, consent, sessions, scheduling, payments, data quality |
| Undergraduate research assistants | $8,000/yr hourly | Not the founder; founder's classmates are excluded from recruitment roles (COI plan) | Session support, data entry checks |
| Biostatistician | 5% of $120,000 | — | SAP, power simulation of the GCI decision rule, confirmatory analyses |

**Study supplies (Y1, $9,860 [HYP prices]):** 2 study laptops with pinned OS/browser ($3,000),
2 external monitors ($600), 2 consumer screen-mounted eye trackers supported by Windows eye
control ($600), 3 switches with USB HID switch interfaces ($660), 1 joystick ($200), 2 USB
webcams for head pointing ($200), monitor arm, floor stand, switch mount arm and wheelchair tray
($1,200), 2 Android tablets ($800), 3 loaner Windows laptops for home use ($2,400), disinfection
supplies ($200). Participants' own AT is preferred in Aims 2–3 (`stage4_protocol.md` §8); no
clinical-grade eye-gaze system is bought.

**Participant payments** (amounts from `CLINICAL_VALIDATION_PLAN.md` §2.8, all [HYP] there):

| Stage (Aim) | Calculation | Amount |
|---|---|---:|
| Stage 1 (1b) | 42 × $20 | 840 |
| Stage 2 (1c) | 24 × $50 | 1,200 |
| Stage 3 (1d) | 60 × ($80 + $10 completion) | 5,400 |
| **Year 1** | | **7,440** |
| Stage 4 (2) | 45 × (4 visits × $40 + care partner 3 × $20 + diary 7 × $2) = 45 × $234 | 10,530 |
| Stage 4 travel | 45 × 3 visits × $30 [HYP] | 4,050 |
| Stage 5 (3) | 5 dyads × $133 | 665 |
| **Year 2** | | **15,245** |

Payment route and tax-reporting thresholds are [UNR] (plan §2.8). If company funds ever pay
participants, they must go through a university-approved route and be disclosed in the consent
form and COI review.

**Other subaward costs:** accessible consent materials ($1,000/yr), local travel for home
sessions ($500 Y1; $2,000 Y2), IRB reliance or clinical-site fee placeholder ($3,000 Y2; whether
UIUC or Carle charges such fees is [UNR]).

---

## 4. Reduced version for a $400,000 cap (NICHD/NCMRR or NIDCD)

18 months; changes from §2 [HYP]:
- Drop Aim 1c (modality crossover, Stage 2); keep Aims 1a, 1b, 1d.
- Aim 2 reduced to 30 AT users (two cohorts, e.g. SCI and stroke, or all three at 10 each);
  known-groups hypothesis H4.1 becomes estimation-only (power too low).
- Aim 3 unchanged (5 dyads).
- Software engineer 0.25 FTE; no clinical co-investigator salary (advisory letter instead); no
  penetration test (moved to Phase II).

| Block | Estimate |
|---:|---:|
| Company direct (founder 18 months, engineer 0.25 FTE, consultant, accessibility audit, supplies $3,000, tooling, licences) | 123,674 |
| Company F&A (40%) | 49,470 |
| Subaward MTDC (PD/PI 10%, coordinator 0.5 FTE, RAs, biostatistician 5%, supplies, consent materials, travel) | 124,675 |
| Subaward F&A (58% placeholder) | 72,312 |
| Participant payments (Stage 1 $840; Stage 3 $5,400; Stage 4 30 × $324 incl. travel; Stage 5 $665) | 16,625 |
| Fee (7% of company costs) | 12,120 |
| **Total** | **≈ 398,876** |

Work split ≈ 44.8% company / 55.2% RI (same basis as §2).

---

## 5. What must happen before these numbers are real
1. UIUC Sponsored Programs: negotiated F&A rate, fringe rates, tuition rules, MTDC exclusions,
   subaward budget and letter of intent signed by the institutional official.
2. Faculty PD/PI and clinical co-investigator effort agreed in writing.
3. Company payroll and work authorisation for the founder; engineer hiring plan.
4. Quotes for the accessibility audit, penetration test and devices.
5. Instrument licence fees (`instruments.md` §3b).
6. Confirm the cap definition, fee base and small-business F&A rule in PA-27-102 and the NIH
   Grants Policy Statement.
7. Illinois DCEO SBIR/STTR match (up to $75,000 for Phase I [V]) is **not** part of this budget;
   apply after award (`FUNDING_PATHWAY.md`).
