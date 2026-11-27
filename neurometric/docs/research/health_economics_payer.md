# Health economics and payer evidence for BCI / AT functional outcomes

Prepared for NeuroMetric. Accessed 2026-11-27. Labels per `CONVENTIONS.md`.
Limitation: this session's web-search quota was exhausted. Several HEOR reference values (AARP,
Genworth/CareScout, ISPOR guidance) are prior knowledge [PK], **not re-verified**, and must be
checked before external use.

---

## 1. What payers need (versus FDA)

**Core distinction.** FDA asks whether a device is safe and effective. Medicare asks whether it
falls within a **benefit category** and is "**reasonable and necessary**" for diagnosis or treatment
of illness or injury (§1862(a)(1)(A)) [PK]. The iBCI-CC consensus statement puts it this way:
"FDA evaluates evidence relevant to device safety and effectiveness, whereas CMS evaluates whether
an item or service meets applicable coverage requirements, including whether it is reasonable and
necessary".
https://www.ibci-cc.org/s/iBCI-CC-Assessment-of-the-iBCI-Endpoints-for-Clinical-Utility.pdf [V]

What payers typically want, in addition to FDA evidence [PK unless labeled]:
1. **Improved health outcomes in the payer's population.** For Medicare, that means beneficiaries:
   people over 65 and disability-entitled people (e.g., ALS, whose Medicare waiting period is
   waived [PK]). RAPID makes this explicit: the IDE must "enroll Medicare beneficiaries" and study
   outcomes CMS confirms would show improved health outcomes.
   https://www.cms.gov/newsroom/fact-sheets/regulatory-alignment-predictable-immediate-device-coverage-pathway-cms-3487-nc-procedural-notice [V]
2. **Clinically meaningful magnitude.** MCID or responder definitions, and durability (≥1 year).
3. **Generalizability.** Real-world settings (home), diverse users, and the role of caregivers.
4. **Medical (not convenience) benefit.**
   - NCD 50.1 covers speech generation and messaging as DME.
   - It excludes general computing, games and video conferencing ("the cost of these features are
     the responsibility of the beneficiary").
   - https://www.cms.gov/medicare-coverage-database/view/ncd.aspx?ncdid=274 [V]
   - The Health Affairs Forefront piece (Mar 2026) reportedly argues that trials focused on
     environmental control or video games may not establish medical necessity. Full text was
     blocked (HTTP 403). [UNR]
5. **Budget impact and cost-effectiveness.** Private payers, Medicaid and health-technology-
   assessment bodies want these. Medicare NCDs do not formally use cost-effectiveness. [PK]
6. **Post-coverage evidence** (CED registries, time-limited). RAPID says "higher risk devices are
   more likely to have remaining evidence gaps" and CED "should be time-limited". [V]
7. **Care-partner burden, functional communication and participation**: the outcomes the iBCI-CC
   positions as "key outcomes of interest, particularly for payor decision-making". [V]

NSCEB (Sept 2026): "Even if a BCI were approved, there is currently no active Centers for Medicare
& Medicaid Services (CMS) reimbursement coverage for implantable BCIs". It recommends explicit
inclusion of BCIs in RAPID.
https://www.biotech.senate.gov/wp-content/uploads/2026/09/NSCEB-BCI-Issue-Paper-Final.pdf [V]

---

## 2. HEOR frameworks relevant to AT and iBCI

| Framework | Use for BCI/AT | Notes | Label |
|---|---|---|---|
| Cost-utility (QALY) | Standard HTA (NICE, ICER, CADTH) | Generic utilities (EQ-5D) have known **ceiling and floor and insensitivity problems** in severe paralysis and ALS. Dohle et al. note EQ-5D-5L use in ALS iBCI studies. QALY use is restricted in some US federal contexts (e.g., IRA rules on QALY-based discrimination). | [PK]; Dohle [V] |
| Cost-consequence analysis | Present costs alongside a dashboard of outcomes (communication, independence, caregiver hours, QoL) | Suits multi-dimensional "measurement chain" outputs. Payer-friendly when QALYs are contested. | [PK] |
| Budget impact analysis | Small, identifiable populations (ALS, high cervical SCI, brainstem stroke) | Usually decisive for commercial and Medicaid payers. | [PK] |
| Capability / wellbeing approaches (ICECAP-A, ASCOT) | Social-care-related QoL, relevant to AT | ASCOT captures control over daily life, which matches digital independence. | [PK] |
| AT outcome frameworks (e.g., PIADS, QUEST, ATD PA; ICF-based) | AT abandonment and device-user match | PIADS predicts adoption and abandonment (per NCT07407725 record text). | [PK]; record text [V] |
| Caregiver time valuation (Section 3) | Translate L3/L4 changes into dollars | Core NeuroMetric HEOR output. | see below |
| Societal perspective (productivity, caregiver productivity) | Return to work or study (e.g., Neuralink's claims of participants pursuing education or work) | Company anecdotes only. | [CC] |

**Validation status.** None of these frameworks has a published, validated BCI-specific model linking
performance metrics (BPS, WPM) to utilities or care hours. Building such a mapping is
**[HYP]** work for NeuroMetric.

---

## 3. Valuing caregiver time

### 3.1 Methods [PK unless noted]
- **Replacement (proxy-good) cost.** Value informal care hours at the wage of a market substitute,
  usually a home health or personal care aide.
  - Variants: the *wage* (what the worker earns) or the *agency charge* (what a family or payer
    pays, often about 2× the wage). [PK]
- **Opportunity cost.** Value hours at the caregiver's forgone wage (their own or a population
  average), with adjustments for non-working caregivers (leisure valued at a fraction of wage).
- **Contingent valuation / well-being valuation.** Willingness to pay or accept, or life-satisfaction
  methods. Rarely used by payers.
- **Formal-care cost offsets.** Measured reductions in paid home-care hours, nursing-facility days,
  or hospitalizations, valued at Medicaid/Medicare fee schedules. These are most persuasive to
  payers because they are direct budget items.
- Practice: report replacement-cost and opportunity-cost results as a range. Measure time with
  validated instruments (time diaries, the Caregiver Reaction Assessment, or the **Zarit Burden
  Interview** for burden [registered in NCT07871071, V]) rather than recall alone.

### 3.2 Wage inputs
| Input | Value | Source | Label |
|---|---|---|---|
| Home health and personal care aides, **median hourly wage** | **$17.21/hour** (May 2025) | BLS Occupational Outlook Handbook, https://www.bls.gov/ooh/healthcare/home-health-aides-and-personal-care-aides.htm | [V] |
| Same, **median annual wage** | **$35,800** (May 2025) | same | [V] |
| Projected employment growth 2025–35 | 18%; ~760,500 openings/yr | same | [V] |
| All-occupations median hourly wage (opportunity cost) | Not retrieved (the BLS OEWS national table needs data.bls.gov) | https://www.bls.gov/oes/current/oes_nat.htm (index only) | [UNR] |
| Agency charge for home health aide (market price) | Prior-cycle surveys (Genworth/CareScout Cost of Care) reported national medians in the low-to-mid $30s/hour around 2023–2024 | not re-verified | [PK] |
| AARP "Valuing the Invaluable" (2023 update) | Valued US family caregiving at roughly $600B (2021 data), at about $16.59/hour | not re-verified; prior cycle | [PK] |

### 3.3 Illustrative arithmetic (not a result) [INF]
- Annual value = hours saved/day × 365 × hourly value.
  - 1 hour/day × 365 × $17.21 = **$6,282/year** at the BLS median aide wage (May 2025).
  - The same hour at an assumed $34/hour agency charge ([PK] order of magnitude) = about $12,410/year.
- The **number of hours saved is unknown** for any iBCI. **No registered US implanted-BCI trial
  measures caregiver time** (see `clinical_trials.md` Section 3.1, item 7). This is [HYP] until
  measured.
- Caution: in ALS, disease progression *increases* care needs over time. Benefit may show up as a
  *slower increase* in care hours or as *substitution* (e.g., fewer night-time call checks). That
  argues for controlled or within-subject designs. [INF]

---

## 4. Payer evidence requirements matrix

Status key:
- **REQ**: explicitly required or recommended by that decision-maker's published document
- **EXP**: commonly expected (prior knowledge)
- **EVOL**: under development or proposed
- **N/A**: not typically relevant

| Evidence type | FDA (PMA / De Novo for iBCI) | CMS / Medicare (NCD, RAPID, CED) | Private payers (commercial, MA plans, Medicaid) | Current status for iBCIs | Label |
|---|---|---|---|---|---|
| Safety (AEs, explant, SAEs), ≥1 yr | **REQ**: iBCI guidance III.O(2)(c)(iii),(vii)(1) | **REQ**: risk informs CED (RAPID fact sheet) | **EXP** | Registered as primary in nearly all EFS | [V] |
| Primary effectiveness endpoint, validated, with MCID | **REQ** (recommended; EFS exempt): III.O(2)(c)(vii)(2) | **REQ** in substance: "clinical outcomes FDA determines are appropriate … and that CMS confirms" (RAPID) | **EXP** | **Gap: no validated iBCI COA; none MDDT-qualified** | [V] |
| Device performance (ITR/BPS/WPM/accuracy) | **EXP** as supportive; L2 | Low weight alone (not a health outcome) | Low weight alone | Abundant but non-comparable | [V]/[INF] |
| Functional / activity outcome (dADL, independence) | **EXP** (COA per PFDD 3) | **EXP**: iBCI-CC chain; Section GG is CMS-native | **EXP** | **EVOL**: Digital IADL (content validity only); SRAL DAI index in development | [V]/[RF] |
| Health outcome / care burden / participation | Optional (PRO/COA) | **EXP**: iBCI-CC says "particularly for payor decision-making" | **EXP**: drives budget impact | **Gap**: caregiver burden rarely registered | [V] |
| PROs (QoL, psychosocial impact) | **REQ** if a claim is based on them; context-of-use validation (III.O(2)(c)(vii)(3)) | **EXP**: MEDCAC 2018 CAR-T PRO precedent cited by iBCI-CC | **EXP** | PIADS, QUEST, WHOQOL-BREF used inconsistently | [V] |
| Home / real-world use | **REQ**: III.O(2)(b) "Home Use" | **EXP**: generalizability; RWD for CED | **EXP** | Usage-hour logging common outside US; few US registrations | [V] |
| Caregiver safety and ability to assist | **REQ**: III.O(2)(b) | N/A directly | N/A | Rarely registered | [V] |
| Patient preference information | Optional (encouraged): III.O(2)(c)(vii)(3) | **EXP** (benefit-risk context) | Low | Not seen in registries | [V] |
| Enrollment of Medicare beneficiaries | N/A | **REQ** for RAPID | N/A | ALS cohorts likely qualify; SCI cohorts are often under 65 (Medicare via SSDI after 24 months) | [V] RAPID / [PK] eligibility |
| Benefit-category fit (DME / prosthetic / service) | N/A | **REQ** (statute; RAPID eligibility screen) | **EXP** (benefit design) | **Unresolved for iBCI**; NCD 50.1 is the SGD analog | [V]/[INF] |
| Comparative effectiveness vs existing AT (eye-gaze, switches, SGDs) | Optional (control or performance goal) | **EXP** (reasonable and necessary vs alternatives) | **EXP** (step therapy / least costly alternative) | **Gap**: only NCT07407725 compares BCI with eye-gaze, joystick, EEG and voice (not as an efficacy trial) | [V]/[INF] |
| Cost-effectiveness / budget impact | N/A | Not formally used in NCDs | **EXP** (HTA, P&T, Medicaid) | None published for iBCI found this session | [PK]/[UNR] |
| Long-term durability and device support (maintenance, explant, obsolescence) | **REQ** (≥1 yr; post-approval) | **EXP** (CED) | **EXP** | GAO flagged long-term support as a policy challenge | [V] iBCI guidance; GAO [AE] |
| Data integrity (Part 11, source data, audit trail) | **REQ** for submissions | Indirect (relies on FDA data) | Indirect | Platform-dependent | [V] |
| Post-market RWE registry | **EXP** (PAS) | **REQ** if CED | **EXP** | Planned only (Neuralink Patient Registry is recruitment-oriented) | [CC]/[INF] |

---

## 5. Implications for NeuroMetric [INF]
1. **Value proposition to sponsors.** NeuroMetric can supply the two gap rows (validated functional
   outcome; care burden and home use) in one Part 11-ready chain. That serves FDA, and RAPID-style
   CMS alignment, at the same time.
2. **Value proposition to payers.** Neutral, cross-device comparative effectiveness against
   existing AT is exactly what a "reasonable and necessary vs alternatives" test needs, and no
   sponsor has an incentive to produce it.
3. **HEOR product.** Pair task logs with a validated caregiver-time module (diary plus Zarit) and
   report replacement-cost and opportunity-cost ranges, using BLS May 2025 aide wages as the
   default replacement rate.
4. **Benefit-category evidence.** Instrument the *medical* uses (communication of needs, emergency
   calls, medication and appointment self-management, telehealth) separately from leisure use, so
   sponsors can argue SGD/prosthetic-type medical necessity.
5. **Hypotheses to test** [HYP]:
   - Sponsors will pay for a neutral endpoint chain before pivotal launch.
   - Payers will accept CARE-scaled digital independence as a health outcome.
   - Caregiver-hour reductions are detectable within 6–12 months in ALS and SCI.
