# Academic collaboration proposal (template)

**Prepared 2026-11-27. Not sent. No collaborator has agreed to anything.** Names come from public sources in
`docs/research/collaborators.md`; each is a *candidate* only. Labels per `CONVENTIONS.md`.

## 1. Why collaborate

NeuroMetric needs independent, peer-reviewable validation evidence before any commercial claim. Academic programs
need low-cost, well-documented tooling to measure function and real-world use across input methods. A
collaboration produces publishable psychometric evidence and, where eligible, NIH STTR funding.

Status to state up front: research software; simulation-only results; no clinical validation; pre-incorporation
(incorporation planned before any award) [INF].

## 2. Three collaboration formats

| Format | Partner type | What the partner gets | What NeuroMetric gets | Funding |
|---|---|---|---|---|
| A. NIH STTR Phase I (PA-27-102) | UIUC/Carle faculty PI (candidate: Yuan Yang, JNERL) | Funded aims; ≥30% subaward to the institution [V]; software and analysis support | Validation data; Phase II path | NICHD/NCMRR up to $400K, NINDS up to $700K Phase I [V]; due 5 Apr 2027 or 5 Sep 2027 [V/INF] |
| B. Bridging sub-study under an existing protocol | SRAlab DAI team (NCT07407725) or another site running home sessions | Home/real-world extension of in-clinic measures; psychometric tooling | Concurrent-validity data against an emerging reference instrument | Partner's existing budget or a small subcontract [HYP] |
| C. Data-analysis collaboration | Groups with de-identified task logs (BrainGate, BCI-FIT, UMC Utrecht) | Cross-input comparable metrics on their data; co-authorship | Real-data checks of metric definitions | No money; data-use agreement |

## 3. Draft STTR Phase I aims (for discussion with a faculty PI)

**Title (working):** Input-agnostic measurement of digital independence after stroke and paralysis.

- **Aim 1 - Reliability and validity.** In [n = 30-40, HYP] chronic stroke survivors and AT/BCI users using
  different inputs (mouse, switch, eye-gaze, EEG-BCI), estimate test-retest reliability (ICC, MDC) and known-groups
  validity of NeuroMetric digital-task metrics; agreement with clinic measures (e.g., FMA-UE, ARAT where collected).
- **Aim 2 - Home real-world use.** Over 4-8 weeks of home use, test whether passive digital-activity metrics relate
  to in-clinic task performance and to a participation measure (e.g., COPM), and characterise missing data.
- **Aim 3 - Care-partner module feasibility.** Completion and burden of ZBI + care-time diary linked to telemetry.
  No economic claims; any valuation is labelled hypothetical (`care_economics.py`).

Milestones / go-no-go [HYP]: ICC ≥ 0.75 for primary metrics; ≥70% usable home-days; burden ≤15 min/week.

## 4. Roles, IP, data

- PI holds formal commitment to NeuroMetric (≥10% effort; may be unpaid) [V NIH STTR rule]; research institution
  performs ≥30% of the work [V]. IP allocation agreement between NeuroMetric and the institution before award
  [PK, required by SBA policy; not re-verified].
- Founder IP: UIUC OTM confirmation that NeuroMetric code was built outside sponsored/RA work, before filing
  (`funding.md` s3.2) [INF].
- Data stay under the institution's IRB and data-governance rules; NeuroMetric receives de-identified data only.
- Publication: academic partners publish freely; NeuroMetric may request a 30-day review for confidential
  information only, never to suppress results [INF].
- Conflicts: faculty equity or consulting triggers UIUC COI disclosure [PK]; Synchron-affiliated or
  Neuralink-collaborating investigators need neutrality safeguards (`collaborators.md`) [INF].

## 5. Timeline

| Date | Step |
|---|---|
| Dec 2026 - Jan 2027 | Introductory conversation; agree whether April or September submission is realistic |
| Jan 2027 | Incorporation, SAM/UEI, eRA Commons (6+ weeks) [V warning] |
| Feb - Mar 2027 | Aims page, budget, subaward, letters |
| 5 Apr 2027 | NIH STTR Phase I submission (or 5 Sep 2027 fallback) |
| ~Dec 2027 | Earliest start if funded [INF] |

## 6. Budget sketch (Phase I, HYP)

| Item | Amount [HYP] |
|---|---|
| Research-institution subaward (≥30%; planned 35%) | ~$140K |
| NeuroMetric personnel (engineering, psychometrics, coordination) | ~$190K |
| Participant compensation, devices, hosting, security | ~$45K |
| Fee / other | ~$25K |
| **Total (NICHD cap)** | **$400K** |
