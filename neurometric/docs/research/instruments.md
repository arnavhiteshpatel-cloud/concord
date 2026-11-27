# Candidate COA instruments: licensing, validity and fit for NeuroMetric

Accessed 2026-11-27. Evidence labels follow `CONVENTIONS.md`. The machine-readable table is
`instruments.csv`: 34 rows and 17 columns, with every field for every instrument. This file
summarizes it, records how each source was checked, and gives the recommendations.

**Method and limits.** Licensing was checked against licensor and developer pages where they could
be reached: HealthMeasures fees and terms, PROMIS T&C PDF, Oxford University Innovation (OUI),
Pitt Innovation, MoCA Cognition, ECAS, NASA, ASIA, WHO and the ClinicalTrials.gov API. The
SRAlab Rehabilitation Measures Database was used for cost, item counts and administration fields.

- Mapi's ePROVIDE (eprovide.mapi-trust.org) redirected to an ICON maintenance notice when accessed,
  so no Mapi-held instrument terms could be read directly [UNR].
- Validation references marked [PK] are standard citations from prior knowledge. They were not
  re-fetched this session and their DOIs are given only where known.
- The web-search budget for this session ran out during Part 3. Anything not checked before that
  point is marked [UNR].
- "Free" on SRAlab means free to obtain. It does **not** mean commercial use is allowed.

**Key framing [V].** HealthMeasures defines "commercial" as any entity that is not tax-exempt or
that operates for profit (https://healthmeasures.net/services/fees/). NeuroMetric is therefore a
commercial user even in a single research study. Most "free for research" terms do not cover us.

---

## 1. Summary table

| Instrument | Respondent | Owner / licensor | Licence status for a for-profit company | Decision |
|---|---|---|---|---|
| Zarit Burden Interview (22/12/4) | Care partner (PRO) | Mapi Research Trust (exclusive, incl. e-versions) [V] | Commercial licence via ePROVIDE; fee by quote [V/UNR] | license-first |
| Caregiver Burden Inventory | Care partner | Novak & Guest 1989 (GSA journal) | No licensor found [UNR] | license-first (author/publisher letter) |
| Caregiver Reaction Assessment | Care partner | Given et al. 1992 (Wiley) | No licensor found [UNR] | license-first |
| PROMIS PF / Fatigue / Social Roles + CAT | PRO | PROMIS Health Org / HealthMeasures | Commercial permission + per-measure digital review fees; API licence for CAT [V] | license-first |
| Neuro-QoL | PRO | HealthMeasures | As PROMIS [V] | license-first |
| SCI-QOL | PRO | Tulsky et al. / U Delaware | Free (non-commercial); commercial terms not published [V/UNR] | license-first |
| ALSAQ-40 / ALSAQ-5 | PRO | Oxford University Innovation | "Request a licence" via OUI; ePRO supported [V] | license-first |
| ALSFRS-R | ClinRO (also self-report versions) | Rights holder unconfirmed; Columbia licenses one self-administered version [V-search] | Unknown [UNR]; NEALS/ENCALS rater certification in trials [V] | license-first |
| ROADS | PRO | Fournier et al. (Emory) | "Publicly available at no charge" [V-search excerpt] | license-first (confirmation only) |
| WHOQOL-BREF | PRO | WHO / national centres | WHO permission for commercial use; NZ centre charges NZ$500 per commercially funded study [V] | license-first |
| EQ-5D-5L | PRO | EuroQol | Registration; commercial fee set case by case; separate digital fee structure [V/AE] | license-first |
| PIADS | PRO | Jutai & Day | Free per SRAlab; commercial unknown [V/UNR] | license-first |
| QUEST 2.0 | PRO | Demers et al. | Free per SRAlab; commercial unknown [V/UNR] | license-first |
| MPT / ATD-PA | PRO + ClinRO | Institute for Matching Person & Technology | Free/ordered via IMPT; commercial unknown [V/UNR] | license-first |
| FMA / FEW | PRO (FEW-C PerfO) | University of Pittsburgh | FMA commercial: $10k per study ($5k small) or $5k-$20k per year, non-negotiable [V] | license-first (low priority) |
| COPM | PRO via interview | COPM Inc. | Purchase/subscription; software integration terms unknown [V/UNR] | license-first |
| GAS | ClinRO/PRO | Method (Kiresuk & Sherman) | Free method [V] | **Y-free** |
| NASA-TLX | PRO | NASA Ames | No permission needed, including modifications [V] | **Y-free** |
| SUS | PRO | J. Brooke | Free; cite Brooke 1996 [AE] | **Y-free** |
| Fatigue Severity Scale | PRO | L. Krupp | Free non-profit; pharma/commercial needs permission [AE] | license-first |
| CHART / CHART-SF | PRO | Craig Hospital | Free per SRAlab; commercial not stated [V/UNR] | license-first (courtesy) |
| IPA | PRO | Cardol et al. | "Not free, cost not known" per SRAlab [V] | license-first |
| SCIM III / SCIM-SR | ClinRO / PRO | Catz & Itzkovich; Jefferson COM procedures | Free per SRAlab; no modification without permission [V]; commercial [UNR] | license-first |
| FIM | ClinRO | UDSMR | Proprietary licence, fees vary [V] | **no** |
| IRF-PAI Section GG | ClinRO | US CMS | Federal work, no copyright expected [INF] | **Y-free (confirm)** |
| ISNCSCI | ClinRO exam | ASIA / ISCoS | CC BY-NC-ND 4.0; commercial, derivative and trial use need ASIA permission [V] | license-first |
| ECAS | PerfO + carer report | University of Edinburgh (Abrahams) | Free non-commercial; commercial licence required, incl. sponsored trials [V] | license-first |
| MoCA | PerfO | MoCA Cognition | Commercial/pharma needs written licence; certification mandatory since 1 Sep 2019 [V] | **no** |
| PHQ-9 | PRO | Kroenke/Spitzer/Williams (Pfizer grant) | No permission needed to reproduce, translate, display or distribute [V] | **Y-free** |
| CPIB | PRO | University of Washington (Baylor et al.) | Not determined [UNR] | license-first |
| CETI | ObsRO | Lomas et al. 1989 | Not determined [UNR] | license-first |
| ASHA FACS | ClinRO | ASHA (commercial product) | Purchase; no digital licence [V/UNR] | **no** |
| Caregiver assistance time (RUD, CAS, iVICQ) | Care partner | Various | Not determined [UNR]; dementia-centric | **no**: build original diary |
| SRAlab DAI (NCT07407725) | PerfO + ClinRO + PRO index | Shirley Ryan AbilityLab (Neuralink collaborator) | Unpublished, no licence [UNR] | **no**: original design only |

---

## 2. Instrument notes (what is not obvious from the CSV)

### Caregiver / care-partner reported
- **ZBI** [V licensor; PK refs]. Mapi Research Trust says it partnered with Dr Zarit "to be the
  exclusive licensor, distributor and translator of the ZBI and all its derivatives including
  translations and electronic versions" (Mapi news page excerpt,
  https://mapi-trust.org/news-events/news/zarit-burden-interview-(z). Any electronic NeuroMetric
  version is therefore a licensed derivative. Expect a fee, Mapi's e-migration process
  (screenshots, equivalence statement), and use of Mapi's translations only.
- **CBI and CRA** [UNR]. Both appear only in journal articles, and no licensing body was found.
  Treat them as copyrighted. Before electronic or commercial use, get a written author
  permission letter plus publisher clearance (OUP/GSA for CBI, Wiley for CRA).
- **Assistance time**. No validated ALS- or SCI-specific instrument for informal-care hours was
  found [UNR].
  - RUD (dementia) records monthly ADL, IADL and supervision hours (systematic review
    https://www.ncbi.nlm.nih.gov/pmc/articles/PMC8449888/) [V].
  - The Caregiver Activity Survey is described as a validated time report with high test-retest
    reliability (registry text, https://clinicaltrials.gov/study/NCT03360019) [V].
  - CHART Physical Independence includes hours of paid and unpaid assistance [PK].
  - The ALS Association's ALS Focus survey found 68% of caregivers giving more than 30 h/week, but
    it is a self-selected survey, not an instrument (https://als.org/es/node/4417) [V].

### PROMIS / Neuro-QoL / SCI-QOL (HealthMeasures family) [V]
Terms are from https://healthmeasures.net/select-measures/measure-library/ and
https://healthmeasures.net/services/fees/.
- English and Spanish versions are free "for individual research or individual clinical use".
- "Commercial Users must seek permission to use, reproduce, or distribute ... regardless of
  purpose, at all times."
- Integration into "computerized adaptive tests, apps, and web portals" requires written approval.
- No adaptation or alteration of items is allowed without written permission. The PROMIS T&C also
  forbid modifying wording or layout, distributing, or translating.

Published fees (2026-11-27):

| Item | Fee |
|---|---|
| Digital-administration screenshot review, standard English measure, commercial | $750 per measure, for the study duration or a 3-year term |
| Same, custom English form, commercial | $900 |
| Existing translation | $1,100 per language |
| Assessment Center API, Single Institution | $6,000/yr |
| Assessment Center API, Distributor (commercial distribution) | $18,000/yr |
| T-score table for a custom form | $1,500 per measure |
| Scoring Service and scoring manuals | Free |

Implications:
- A PROMIS CAT inside NeuroMetric needs either the Assessment Center API (Distributor licence if
  we deliver to customers) or written permission to run our own CAT engine on PROMIS
  calibrations [INF].
- **Accessibility migration.** Switch, eye-gaze or BCI response modes change the "layout". Ask
  explicitly whether alternative-access presentation (scanning highlight, dwell buttons,
  single-item-per-screen) is acceptable under screenshot review [INF].
- SCI-QOL is listed free on SRAlab; the CAT app costs $500/yr for up to 10 iPads [V]. Its
  commercial terms are not published, so ask sci-qol@udel.edu (the public project inbox in the
  NINDS CDE guideline) [V].

### ALS-specific
- **ALSAQ-40/5** [V]. Owned and licensed by OUI. The page lists "ePRO/eCOA – Electronic
  administration" and links a language list. Licence via the "Request a licence" route
  (process.innovation.ox.ac.uk/clinical; general inbox enquiries@innovation.ox.ac.uk). Fees are
  not published [UNR]. CADTH notes limited construct validity for the communication and ADL
  domains (https://www.ncbi.nlm.nih.gov/books/NBK542356/) [V].
- **ALSFRS-R** [UNR rights]. No authoritative licence statement was found. Several facts were
  confirmed:
  - Trial raters must be NEALS-certified, e.g. in the HEALEY platform protocol
    (https://cdn.clinicaltrials.gov/large-docs/83/NCT04297683/Prot_000.pdf) [V].
  - Several self-administered versions exist, with "subtle but important differences" (2025
    review, https://eprints.whiterose.ac.uk/id/eprint/228986) [V].
  - Columbia Technology Ventures lists a self-administered ALSFRS-R for licensing (CU25205) [V].

  For NeuroMetric: never present our own self-report wording as "ALSFRS-R". Either license an
  established self-administered version or record a clinician-administered score that a certified
  rater enters.
- **ROADS** is a free, patient-reported ALS disability alternative (JAMA abstract excerpt:
  "publicly available ... at no charge") [V-search]. Commercial-use wording still needs
  confirmation.
- **ECAS** [V] (https://ecas.psy.ed.ac.uk/license/). "Freely available for non-commercial academic
  research and health purposes". A "commercial licence agreement is required ... for any other
  purpose whatsoever, including commercially sponsored clinical trials". It was designed for
  people with motor impairment, which is the best fit for cognition screening in BCI candidates.

### AT-specific
- **PIADS, QUEST 2.0 and ATD-PA** are all "free" on SRAlab [V], but none publishes commercial
  terms [UNR]. These three are the AT-outcome core and are cheap to clear. Prioritize author
  letters.
- **FMA** [V] (https://inventions.pitt.edu/licenses/functional-mobility-assessment--238). Pitt's
  commercial licence is $10,000 per commercial study ($5,000 for 50 or fewer employees and 100 or
  fewer participants), or a yearly per-use licence of $5,000-$20,000. Commercial licences are "not
  negotiable". Self-made translations must be assigned to Pitt. The FMA's wheelchair-mobility
  content barely touches digital access, so it is low priority. FEW licensing was not determined
  [UNR].
- **COPM** [V/UNR]. Sold by COPM Inc. (web app, digital PDF). SRAlab 2012 prices were CAD 52.45
  for a manual/form kit and CAD 225.45 for the DVD kit. Third-party software integration is not
  addressed publicly. SRAlab's DAI study uses a *modified* COPM interview, which suggests even
  academic users adapt it, but we must not.

### Generic / workload / usability
- **NASA-TLX** [V]. NASA states it is "open source ... available for immediate use by any person or
  organization" and that permission is not needed even for modifications such as translation
  (https://www.nasa.gov/human-systems-integration-division/nasa-task-load-index-tlx/).
- **SUS** [AE]. Free; Brooke's single condition is acknowledgement of the source (Brooke 1996).
  The retrospective is Brooke 2013, J Usability Stud 8(2):29-40 (https://uxpa.org/?p=3799). The
  exact wording was not re-read this session.
- **PHQ-9** [V]. Form notices say "No permission is required to reproduce, translate, display or
  distribute". Copyright (Pfizer) is contested by patient.info [AE]. Item 9 needs a safety
  escalation workflow in any electronic deployment [INF].
- **MoCA** [V] (https://mocacognition.com/permission and /terms-of-use).
  - Training and certification are mandatory since 1 Sep 2019. They are now optional for
    screening/triage on the total score and still required for interpreting subscores.
  - Commercial entities need prior written permission and a licensing agreement.
  - Cube, clock and trails items need a pen, so the test is invalid for most target users [INF].
- **FIM** [V]. UDSMR proprietary licence. CMS replaced FIM items with Section GG in IRF-PAI
  (Oct 2019, per secondary source) [AE]. Do not implement.
- **Section GG** [INF]. A CMS/US-government work, so no copyright is expected (17 USC 105). Confirm
  with counsel. Free CMS manuals and decision trees exist [V].
- **ISNCSCI** [V]. The worksheet is CC BY-NC-ND 4.0. Commercial use, derivatives (an electronic
  worksheet is one) and clinical-trial use need ASIA permission. ASIA accepts translation requests
  only from organizations.

### Communication
- **CPIB** [UNR licence]. 46-item bank and 10-item General Short Form with T-score table (Baylor
  et al. 2013 JSLHR). The development sample included ALS [PK]. Most relevant PRO for AAC/BCI
  communication. Ask UW for written permission.
- **CETI** [UNR]: proxy-rated, aphasia-oriented. **ASHA FACS** [V/UNR] is a purchased ASHA
  product, so we will not implement it.

### SRAlab DAI / NCT07407725 [V]
From the ClinicalTrials.gov API, record last updated 2026-11-06:
- Title: "Development of a Clinical Outcome Assessment for Assistive Technologies and
  Brain-Computer Interfaces". Sponsor Shirley Ryan AbilityLab; Neuralink Corp is a collaborator.
- Recruiting; started 2026-01-08; primary completion Dec 2026 (est.); study completion Jun 2027
  (est.); n ≈ 60 (SCI C1-T1, ALS, healthy controls).
- Devices: Tobii Dynavox PCEye 5, Jouse+, EMOTIV EPOC X, implanted BCI (primarily Neuralink N1),
  the participant's own AT, and voice control.
- The DAI simulates online shopping, texting, gaming and booking appointments. Its metrics are
  click accuracy, time to target, error count, cursor trajectory, WPM and % correct characters.
  These are combined with ClinRO and PRO measures into an index that will be tested for validity,
  reliability, responsiveness and floor/ceiling.
- PROs and ClinROs: NASA-TLX, SUS, modified COPM, PIADS. Intake: abbreviated ISNCSCI, ALSFRS-R,
  ECAS, IRF-PAI Section GG, WHOQOL-BREF.
- No publication, task specification or licence terms were found [UNR]. The SRAlab press search
  was cut short by the exhausted search budget.

Implication [INF]: SRAlab and Neuralink are building the reference COA in this space. NeuroMetric's
differentiation has to rest on openly specified, input-agnostic task definitions and published
psychometrics.

---

## 3. Recommendations

### 3a. Implement now (free; attribution only) [V unless noted]
1. **NASA-TLX** (raw TLX by default; weighted optional).
2. **SUS** (cite Brooke 1996).
3. **PHQ-9**, only with a clinician-reviewed safety workflow for item 9. Flag somatic-item
   confounding in ALS/SCI.
4. **GAS** (method, with Turner-Stokes T-score formula). Build our own goal-setting forms; do not
   copy proprietary GAS-light templates.
5. **IRF-PAI Section GG items** as a clinician-entered intake [INF: public domain; confirm with
   counsel].

### 3b. Licensing inquiry package (send before any electronic build)
One email per licensor, each with the same attachment pack:
- (a) company description and for-profit status;
- (b) intended use: research studies, commercial product, or both, with expected annual
  administrations;
- (c) populations: ALS, SCI, stroke, other paralysis; adults; care partners;
- (d) administration mode: web/tablet with **alternative access** (switch scanning, eye-gaze dwell,
  BCI cursor, voice). Include screenshots of each access mode with item text unaltered;
- (e) languages;
- (f) whether scores are shown to clinicians or to sponsors;
- (g) a request for any e-migration / equivalence requirements and a fee quote.

| Priority | Licensor (public route) | Instruments | Specific asks |
|---|---|---|---|
| 1 | HealthMeasures (help@healthmeasures.net) | PROMIS PF, Fatigue, Ability to Participate in Social Roles; Neuro-QoL UE Fine Motor/ADL, Communication, Fatigue | Commercial permission; screenshot-review quote ($750/measure list price); Distributor API vs own CAT engine; alternative-access layout acceptability |
| 1 | U Delaware SCI-QOL team (sci-qol@udel.edu) | SCI-QOL Independence, Ability to Participate, Basic Mobility | Commercial terms; CAT outside the app |
| 1 | Oxford University Innovation (process.innovation.ox.ac.uk/clinical) | ALSAQ-40, ALSAQ-5 | Commercial ePRO licence; fee; translations |
| 1 | University of Edinburgh, ECAS (contact via https://ecas.psy.ed.ac.uk/license/) | ECAS (incl. remote) | Commercial licence; electronic or remote administration by our platform |
| 1 | Mapi Research Trust / ePROVIDE | Zarit Burden Interview (ZBI-12 preferred) | Commercial e-version licence; migration process |
| 1 | Columbia Technology Ventures (CU25205) and NEALS | Self-administered ALSFRS-R; rater certification | Licence terms; who holds ALSFRS-R rights [UNR] |
| 2 | Authors of PIADS (Jutai/Day), QUEST 2.0 (Demers), IMPT (ATD-PA) | AT-outcome core | Written commercial permission; e-version wording |
| 2 | COPM Inc. | COPM | Third-party software integration; per-administration licence |
| 2 | EuroQol | EQ-5D-5L | Commercial digital licence quote |
| 2 | WHO permissions | WHOQOL-BREF | Commercial permission; per-country centres |
| 2 | ASIA (asia.office@asia-spinalinjury.org) | ISNCSCI electronic worksheet / algorithm | Commercial derivative permission |
| 3 | UW CPIB developers; Craig Hospital (CHART); L. Krupp (FSS); Novak/Guest (CBI); Given (CRA); Cardol/Amsterdam UMC (IPA); Jefferson COM / Loewenstein (SCIM III); Emory (ROADS); Lomas (CETI) | Remaining | Written commercial permission letters |
| 4 | U Pittsburgh Innovation | FMA | Only if a partner needs wheelchair outcomes. Fixed price of $5k-$20k |

Do **not** pursue: FIM (UDSMR), MoCA (use ECAS instead), ASHA FACS.

### 3c. Replace with original NeuroMetric questionnaires
Every item must be written from scratch and the instrument labelled "NeuroMetric research
questionnaire, unvalidated, vX". Do not paraphrase existing items. [INF throughout]
1. **Care-partner assistance-time diary** (24-h yesterday recall plus 7-day typical week; ADL,
   IADL, device setup/calibration time, supervision, digital-access help). This fills a real gap,
   since no ALS/SCI-specific validated instrument was found [UNR].
2. **Digital-access participation and satisfaction questionnaire**, input-agnostic, covering the
   texting, email, banking, shopping, social media and gaming contexts that SRAlab also targets.
   Use it until CPIB/Neuro-QoL licences arrive and later as a construct-validity comparator.
3. **Device-session fatigue and effort single items** (pre/post-session NRS 0-10) as an
   always-available complement to FSS or PROMIS Fatigue.
4. **Care-partner device-burden module** (setup, troubleshooting, charging, skin/headset care),
   which ZBI, CBI and CRA do not cover.

All originals should go through cognitive interviewing with ALS/SCI users (eye-gaze/switch
access) and care partners before any psychometric claim. COSMIN content validity standards apply
(see `methods_references.md`).
