# Funding pathway, months 0–30, tied to evidence gates

> **DRAFT PLAN.** Prepared 2026-11-27; M0 = December 2026. Dates of future cycles that have not
> been announced are inferred from past cycles and labelled [INF]; amounts and dates marked [V]
> were checked on 2026-11-27 in `docs/research/funding.md`. No application has been submitted and
> no funder, partner or investor has made any commitment. Every gate below is a decision point:
> if the evidence is not there, the money behind it is not pursued.

---

## 1. Evidence gates

| Gate | Earliest | Evidence required (quantitative where possible) | Who decides |
|---|---|---|---|
| **E0. Company and IP basics** | M2 (Jan 2027) | Incorporated; OTM confirms founder ownership of NeuroMetric (and Concord) code; EIN, SAM.gov UEI, Grants.gov, eRA Commons, SBA registry started (≥ 6 weeks) [V warning] | Founder + counsel |
| **E1. Discovery and academic anchor** (= 90-day gate, `COMMERCIALIZATION.md` §8) | M3 (end Feb 2027) | ≥ 20 interviews across ≥ 4 types; ≥ 1 faculty member willing to be STTR PD/PI (written); ≥ 2 non-binding LOIs for a paid pilot is the commercial pass bar | Founder + advisers |
| **E2. Technical readiness** | M3 | Bench lag/precision profile for ≥ 2 input classes; one healthy-volunteer **demonstration** session with ≥ 2 inputs under an appropriate determination (product demo or IRB-approved pilot; no research data claimed without IRB) [INF]; all computational studies complete with no `[RESULT PENDING]` left in the grant | Founder + PD/PI |
| **E3. Instrument mechanics (Aim 1b)** | ≈ M7 after award | Valid-trial rate Wilson lower bound ≥ 0.90; median Fitts R² ≥ 0.80 | PD/PI |
| **E4. Reliability (Aim 1d) and modality ordering (Aim 1c)** | ≈ M13 after award | ≥ 3 of P1–P4 with ICC(A,1) ≥ 0.75 and generalized-CI lower bound ≥ 0.60; H2.1 all five contrasts | PD/PI + biostatistician |
| **E5. Validity in AT users (Aim 2) and home feasibility (Aim 3)** | ≈ M21–22 after award | AUC ≥ 0.70 (lower bound > 0.50) direct vs scanning; ≥ 75% construct hypotheses; ≤ 15% floor per cohort; home F1–F7 with zero privacy breaches | PD/PI |
| **E6. Commercial traction** | M18–24 | ≥ 1 paid pilot delivered; ≥ 1 maker confirms a feasible data export or SDK route | Founder / board |

The research gates E3–E5 are the STTR milestones M1–M4 in `NIH_STTR_PHASE1.md` §4.8, counted from
the award date. If the Phase I starts about December 2027 (see below), E3 ≈ M19, E4 ≈ M25 and
E5 ≈ M33 on this calendar, i.e. E5 falls just after the 30-month window.

---

## 2. Month-by-month pathway

| Window (calendar) | Gate in play | Funding actions | If the gate fails |
|---|---|---|---|
| **M0–2** (Dec 2026–Jan 2027) | E0 | Cozad 2027 registration (deadline ≈ early Feb [INF]); recruit a CI MED teammate for healthcare prizes [V rule, confirm 2027]; Illinois I-Corps application **by 5 Feb 2027** [V]; contact candidate faculty PD/PIs; iBCI-CC membership form [V] | Without incorporation by ≈ mid-January, drop the 5 Apr 2027 NIH date and target September 2027 [INF] |
| **M2–4** (Feb–Mar 2027) | E1, E2 | I-Corps workshop (Feb–Apr) [V]; ≥ 20 interviews → I-Corps Boost eligibility [V]; NSF SBIR/STTR Project Pitch only if someone can be ≥ 51% company-employed PI (NSF dates 4 Mar and 7 Jul 2027 [V]); request letters (`LETTERS_OF_SUPPORT_TEMPLATES.md`); program-officer contact (NINDS, NICHD/NCMRR) | No faculty PD/PI → no STTR in April; continue as Cozad/I-Corps-funded research software; revisit September |
| **M4–5** (Apr 2027) | E1 + E2 passed | **NIH STTR Phase I, PA-27-102, due 5 Apr 2027** [V] (`NIH_STTR_PHASE1.md`, `BUDGET.md`); Cozad finals ≈ April [INF]; Spring IP Clinic (if eligible) [CC] | Submit only if the PD/PI, subaward and registrations are in place; otherwise September |
| **M5–9** (May–Sep 2027) | — | If April missed or not discussed: **NIH STTR ≈ 5 Sep 2027** under the reissued NOFO [INF; number/date UNR]; NSF Phase I 7 Jul 2027 [V] (only with an eligible PI); watch FY27 DoD **ALSRP COBA** (≤ $1.0M; FY26 pre-application was 24 Jun 2026) [V prior cycle] with an ALS clinical partner; iVenture summer cohort if the window is open [UNR]; Illinois Ventures conversations only after E1 | Without an ALS clinical partner, skip COBA |
| **M9–13** (Sep–Dec 2027) | E6 (early) | **NIDILRR SBIR Phase I** ≈ Dec 2027 [INF from the 16 Dec 2026 FY27 forecast; $95–100k] (SBIR: company PI rules apply, so this needs a company PI who is "primarily employed" [V/UNR]); Illinois Ventures pre-seed ($100–300k) or Illini Angels discussions [V/CC] **only after** ≥ 1 paid pilot or a fundable STTR score | No pilot → no equity raise; stay grant-funded |
| **M12–18** (Dec 2027–May 2028) | E3 | Earliest STTR Phase I start ≈ Dec 2027 if submitted in April (summer review, October council) [INF]; **Illinois DCEO SBIR/STTR Phase I match up to $75k**, apply within 12 months of award and before the Phase II submission; DCEO NOFO window runs to 30 Jun 2027 — renewal [UNR] [V rules] | Phase I not funded → resubmit once with reviewers' changes; meanwhile seek a faculty-led pilot grant through the partner RI |
| **M18–24** (Jun–Nov 2028) | E4, E6 | Prepare **Phase II** (NINDS up to $3.0M; NICHD up to $2.5M [V]); join FY28 DoD SCIRP/ALSRP clinical awards as a subawardee [INF]; first study-year contract only with Part 11 work under way | E4 fails → demote failing scores, lengthen tasks (Study I relation), delay Phase II; do not raise on a failing reliability result |
| **M24–30** (Dec 2028–May 2029) | E5 (E5 may land just after M30 if Phase I started Dec 2027) | Phase II submission once E4 + E5 met; **DCEO Phase II match up to $250k** after a Phase II award [V]; seed round only with Phase II submitted and ≥ 2 paying customers [INF]; the $30M Strategic Breakthrough award needs a prior Phase II and 100% matching funds, so it is out of scope [V rule] | If E5 validity fails → revise constructs; restrict Phase II to the components that passed |

---

## 3. Budget envelope by source (planning ranges, not commitments)

| Source | Amount | Earliest | Condition | Label |
|---|---|---|---|---|
| Cozad prizes (SAFE) | $0–100k | Apr 2027 | Placement | [V 2026 amounts] |
| NSF I-Corps National Teams | $50k | mid/late 2027 | Workshop + nomination | [V/PK] |
| iVenture | $10k + stipends | summer 2027 or 2028 | Admission | [CC] |
| NIH STTR Phase I (NINDS) | up to $700k (draft budget $696k over 24 months) | ≈ Dec 2027 | Funded score | [V cap] / `BUDGET.md` |
| Illinois DCEO match | up to $75k (Phase I) / $250k (Phase II) | after award | Illinois principal place of business | [V] |
| NIDILRR SBIR Phase I | $95–100k | ≈ 2028 | Company PI | [V forecast amount] |
| DoD ALSRP COBA | up to $1.0M | FY27/28 cycle | ALS clinical partner; appropriations | [V prior cycle] |
| Illinois Ventures pre-seed / Illini Angels | $100–300k | ≥ M12 | Traction | [V/CC] |
| NIH STTR Phase II | up to $3.0M (NINDS) | ≥ M24 | Phase I aims met | [V cap] |

---

## 4. Principles
1. Non-dilutive money first; equity only after a paid pilot or a funded STTR.
2. Never let a funding deadline push data collection ahead of IRB approval or SAP locking.
3. Keep HHS application counts well under the cap of 9 per fiscal year [V].
4. Every application uses only results that exist in `experiments/results/` (with their file
   paths) and labels them computational; human data are reported only after the relevant gate.
