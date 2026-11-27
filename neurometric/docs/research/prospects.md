# NeuroMetric prospect database (BCI, neuromodulation, AAC/AT, academic, channel)

Prepared 2026-11-27. All web sources accessed 2026-11-27. Machine-readable companion: `prospects.csv`
(same records, one row per organization). Neuromodulation detail and outcome-measure matrix: `neuromodulation_market.md`.
Interview guides: `interview_guides.md`.

Labels follow `CONVENTIONS.md`. FDA database entries, ClinicalTrials.gov API v2 records, SEC filings and payer
policies are treated as primary sources ([V]); a registry record is sponsor-entered, so [V] means "the registry says
this". Trade press relaying company statements is [CC]. Everything under "NeuroMetric use case" and all fit scores
and tiers are NeuroMetric inference [INF]; any price or willingness-to-pay idea is [HYP] and none is asserted here.

**Contacts policy.** No individual names, emails or phone numbers are recorded. Contact routes are role-level
targets plus public routes only: company contact pages, investor-relations pages, LinkedIn company pages, published
press-release distribution, and ClinicalTrials.gov registry central contacts. Domains marked "not re-verified" are
prior knowledge and must be checked before use. Nothing was sent to anyone.

## 1. How prospects were found and qualified

1. Sponsor queries on ClinicalTrials.gov API v2 for each named company, plus term searches for active
   "brain-computer interface", "intracortical", "speech neuroprosthesis", "BrainGate" and "neuroprosthesis tetraplegia"
   studies (about 690 lines of registry output reviewed). Full records pulled for every trial cited.
2. openFDA 510(k)/De Novo/PMA queries by applicant; FDA 510(k) summary PDFs read for ARC-EX home (K251821) and PoNS stroke (K253061).
3. News and company releases for status, ownership and funding (labelled [CC]).
4. One commercial payer policy (Anthem DME.00052, BCI rehabilitation devices) read in full as a demand signal.

## 2. Tier and fit definitions [INF]

**Fit score (1-5)** = how directly NeuroMetric's four capabilities (neutral functional-outcome measurement, home
real-world-use telemetry, care-partner burden capture, evidence packaging) address a documented need of this
organization, adjusted for scope (motor/communication function) and for in-house build risk.
5 = documented gap that NeuroMetric's capabilities address one-for-one; 4 = strong fit, need inferred from trial design or
reimbursement position; 3 = plausible fit, need not yet visible or strong in-house capability; 2 = adjacent; 1 = minimal; 0 = not a customer.

**Tier 1 (qualified near-term)** requires all four: (a) fit 4-5; (b) a visible trigger within ~12 months (new home
indication, payer rejection, registered or starting study whose endpoints include function/use/burden, or registry expansion);
(c) evidence of budget (revenue, recent raise or grant); (d) a reachable public route.
**Tier 2** = good fit but missing one of (b)-(c), or high in-house build likelihood, or research customer with grant-limited budget.
**Tier 3** = early-stage, out of core scope, geography/data-transfer barriers, channel only, or status unverified.
**X** = excluded (reason given). **Partner** = standards body, not a buyer.

## 3. Tier summary

| Tier | Organization | Segment | Fit | One-line reason |
|---|---|---|---|---|
| 1 | ONWARD Medical N.V. | Neuromodulation - SCI (non-invasive + implanted) | 5 | Independent home-phase evidence pack: adherence/active-use minutes (read-only from MyARCEX export or wearables), remote CUE-Q/DASH/COPM, NASA-TLX and care-partner burden |
| 1 | Cognixion | Non-invasive BCI (AR/EEG) - AAC | 5 | Independent real-world-use and caregiver-burden analytics, comparator framework vs eye-gaze SGD, evidence package for FDA submission and SGD funding (payer) files |
| 1 | Kandu, Inc. (Neurolutions subsidiary) | Non-invasive BCI stroke rehabilitation (home) | 5 | Run or support the RWE study as an independent measurement layer: remote standardized FMA-UE/ARAT video protocol with blinded raters, wrist-worn real-world arm-use telemetry, ZBI and PSFS capture, durability follow-up, payer-ready evidence package addressing each Anthem criticism |
| 1 | Mobia Medical, Inc. (formerly MicroTransponder) | Implanted neuromodulation - stroke rehab | 4 | Registry add-on: objective real-world arm-use telemetry to complement MAL, remote SIS/COPM, care-partner burden |
| 1 | Bioness Medical, Inc. (Accelmed Partners) | Neuromodulation + FES + rehab robotics | 4 | Home-phase companion for PoNS stroke: session adherence (read-only controller logs if exportable), daily-life walking metrics from wearables, falls diary, care-partner burden |
| 2 | Shirley Ryan AbilityLab (COA for AT & BCI) | Academic - outcome measure development | 4 | Partner for a home and real-world extension of their in-clinic index plus a care-partner module (also the closest competitor to a NeuroMetric COA) |
| 2 | University of Calgary (BCI@Home, pediatric) | Academic home BCI (pediatric) | 4 | Home real-world-use telemetry and family/caregiver burden module |
| 2 | UMC Utrecht (Brain Center BCI program) | Academic iBCI (home use) | 4 | Home-use outcome tooling partner |
| 2 | VA Palo Alto Health Care System (SCI home tSCS) | Academic/VA neuromodulation | 4 | Instrument harmonisation and home telemetry for the VA study and VA ARC-EX home roll-out |
| 2 | Synchron, Inc. | Implantable BCI (endovascular) | 4 | Pivotal-grade functional and real-world-use endpoint package (digital-independence tasks, home use minutes, caregiver burden, AT comparators) |
| 2 | Paradromics, Inc. | Implantable BCI (intracortical, speech) | 4 | Communication-participation and home-use evidence (daily use, conversation partners, caregiver burden, ALS progression context) to prepare pivotal endpoints |
| 2 | Phantom Neuro Inc. | Implanted peripheral neural interface (prosthetics) | 4 | Neutral home real-world-use analytics and participation/satisfaction PROs packaged for FDA and O&P payers |
| 2 | Myomo, Inc. | Wearable powered orthosis (home) | 4 | Real-world wear/use telemetry and DASH/COPM capture for medical-necessity documentation and payer appeals |
| 2 | Control Bionics Ltd | AAC / EMG switch AT (ALS) | 3 | Real-world-use and participation evidence for SGD funding |
| 2 | Dynavox Group AB (Tobii Dynavox) | AAC / eye-gaze AT | 3 | Real-world use + participation evidence for SGD funding files |
| 2 | PRC-Saltillo | AAC devices and software | 3 | Outcomes and use evidence for SGD funding |
| 2 | EPFL / .NeuroRestore / CHUV | Academic brain-spine interface | 3 | Home real-world-use telemetry and harmonised PRO capture across ONWARD-linked studies |
| 2 | BrainGate consortium (MGH, Brown, Stanford, Emory, Providence VA) | Academic iBCI | 3 | Standardised home-use logging and participant/caregiver outcomes across sites |
| 2 | Johns Hopkins University (CortiCom; INTENT with Blackrock/APL) | Academic iBCI | 3 | Home-use and participation outcomes for INTENT |
| 2 | CHU Grenoble Alpes / Clinatec (CEA) | Academic iBCI (WIMAGINE) | 3 | Daily-life function and caregiver outcomes |
| 2 | University of Pittsburgh RNEL / University of Chicago | Academic iBCI (sensorimotor) | 3 | Functional and home-use outcome layer |
| 2 | UC Davis Neuroprosthetics Lab | Academic iBCI (speech) | 3 | Communication participation and caregiver measures |
| 2 | UTHealth Houston (RECLAIM speech iBCI) | Academic iBCI (speech) | 3 | Communication participation and caregiver outcomes |
| 2 | UCSF (Chang lab; Ganguly lab) | Academic iBCI (speech, ECoG) | 3 | Communication-participation and caregiver outcomes |
| 2 | Case Western Reserve / UH Cleveland (ReHAB) | Academic iBCI + FES | 3 | Home functional use outcomes |
| 2 | University of Miami / Miami Project to Cure Paralysis | Academic neuromodulation + iBCI site | 3 | Home-use and participation outcomes |
| 2 | Blackrock Neurotech | Implantable BCI (Utah array supplier) | 3 | Harmonised multi-site functional and home-use outcomes for a MoveAgain regulatory file |
| 2 | Neuralink Corp | Implantable BCI (intracortical) | 3 | Independent home-use and caregiver-burden evidence |
| 2 | Precision Neuroscience Corp | Implantable BCI (thin-film cortical) | 3 | Outcome framework for a future chronic-implant study |
| 2 | g.tec medical engineering GmbH | Non-invasive BCI rehab + DoC assessment | 3 | Standardised outcome registry across recoveriX clinics |
| 2 | Cala Health, Inc. | Wearable neuromodulation (tremor, home) | 3 | Independent ADL/participation and care-partner measures to complement device tremor data |
| 3 | BrainQ Technologies | Home EMF neuromodulation - stroke | 3 | Chronic-stroke home RWE with participation, real-world use and care-partner measures if they re-plan the US path |
| 3 | Motus Nova | Home rehab robotics - stroke | 3 | Real-world use + function evidence for home robotics |
| 3 | Echo Neurotechnologies | Implantable BCI (speech) | 3 | Communication-participation endpoints when a trial is registered |
| 3 | Smartbox Assistive Technology | AAC software and devices | 2 | UK/EU AAC outcome evidence |
| 3 | Caltech (Andersen lab) with Rancho Los Amigos / USC / Casa Colina / UCLA | Academic iBCI | 2 | Limited (basic-science orientation) |
| 3 | Medtech CROs (e.g., NAMSA, Avania, Medpace Medical Device, IQVIA MedTech) | CRO / channel | 2 | White-label or subcontracted measurement module for neuro-device studies |
| 3 | Bionik Laboratories | Clinic rehab robotics | 2 | Low - clinic robotics |
| 3 | Hocoma AG (DIH Holding US) | Clinic rehab robotics | 2 | Low - clinic robotics |
| 3 | Eyegaze Inc. (LC Technologies) | Eye-gaze AT | 2 | Comparator data partner |
| 3 | Flow Neuroscience AB | Home neuromodulation - depression | 2 | Adherence/home-use evidence and payer packaging (adjacent only) |
| 3 | electroCore, Inc. | Home neuromodulation - headache/pain | 2 | Limited - possibly PTSD/TBI function studies |
| 3 | Saebo, Inc. | Home orthoses / NMES | 2 | Low-moderate |
| 3 | Kinestica d.o.o. | Home/clinic upper-limb sensor rehab | 2 | EU partner for sensor-based home assessment |
| 3 | BCIFlex Medical Technology | Implantable BCI (China) | 2 | Methods partner at most |
| 3 | NeuroXess (Shanghai) | Implantable BCI (China) | 2 | Post-market RWE (China) |
| 3 | Shanghai StairMed Technology | Implantable BCI (China) | 2 | Methods partner at most |
| 3 | Neuracle Medical Technology (Shanghai) | Implantable BCI (epidural, China) | 2 | Post-market RWE (data residency and PIPL constraints) |
| 3 | Axoft, Inc. | Implantable BCI (soft materials) | 2 | Later-stage only |
| 3 | INBRAIN Neuroelectronics | Implantable interface (graphene) | 2 | Later-stage only |
| 3 | Augmental | Intraoral tongue interface AT | 2 | Comparator/alternative-access evidence if it pursues FDA/reimbursement |
| 3 | Tyromotion GmbH | Rehab robotics / sensor devices | 2 | EU partner for home assessment |
| 3 | AbleNet, Inc. | Switches / AT access | 2 | Low |
| 3 | Glassouse | Head-mouse AT | 1 | Low |
| 3 | Quha Oy | Head/gyro mouse AT | 1 | Low |
| 3 | Merge Labs | Non-invasive BCI (ultrasound, preclinical) | 1 | Too early |
| 3 | Subsense | Non-surgical nanoparticle BCI | 1 | Too early |
| 3 | Forest Neurotech | Nonprofit BCI research org (ultrasound) | 1 | Too early |
| Partner | Implantable BCI Collaborative Community (iBCI-CC) | Standards body (FDA-participating collaborative community) | - | Not a customer |

### Count of prospects by segment and tier (excluding standards bodies and excluded organizations)

| Segment | Tier 1 (qualified near-term) | Tier 2 | Tier 3 |
|---|---|---|---|
| Neuromodulation / rehab devices | 4 | 2 | 9 |
| BCI makers | 1 | 7 | 10 |
| Academic / research programs | 0 | 14 | 1 |
| AAC / assistive technology | 0 | 3 | 6 |
| CRO / channel | 0 | 0 | 1 |
| **Total** | **5** | **26** | **27** |

Kandu (IpsiHand) is counted under neuromodulation/rehab devices because it is a cleared home rehabilitation device, although technically a non-invasive BCI. [INF]

## 4. Tier 1 profiles (qualified near-term)

### 4.1 ONWARD Medical N.V. - fit 5
- **Devices / stage:** ARC-EX transcutaneous spinal cord stimulation, De Novo DEN240014 (2024-12-19) and home-use
  510(k) K251821 (2025-11-14) [V]. The home 510(k) added a home app (MyARCEX, clinician-preset settings only) and states
  that no new clinical data were needed [V] https://www.accessdata.fda.gov/cdrh_docs/pdf25/K251821.pdf.
  First home systems sold in H1 2026, including within the US VA community; 159 systems sold/supplied in H1 2026 [CC].
  ARC-IM pivotal (Empower BP, NCT07147296) recruiting; ARC-BCI investigational [V]/[CC].
- **Why now:** home use is newly cleared without home-specific effectiveness data; reimbursement for the "ARC-EX Personal
  System for home use" depends on letters of medical necessity and individual payer decisions (PRIA-run support program;
  no coverage guarantee) [CC] https://www.onwd.com/wp-content/uploads/2026/08/ARC-EX-Reimbursement-Support-Program-Overview.pdf.
- **Existing outcome approach:** Up-LIFT (NCT04697472) strength/function responder composite; LIFT Home (NCT05284201) AEs and
  "extended use at home"; VA-led home tSCS telehealth feasibility (NCT06140706; ONWARD collaborator) uses NASA-TLX and QUEST 2.0
  as primary and GRASSP, CUE-Q, DASH, COPM as secondary [V].
- **NeuroMetric use case [INF]:** a neutral home-phase evidence companion: read-only adherence and active-use minutes (from
  MyARCEX export if available, otherwise wearables), remote CUE-Q/DASH/COPM, NASA-TLX and care-partner burden, packaged as
  payer/VA summaries and LMN appendices; aligned to the VA study's instrument set so data pool.
- **Target roles:** VP Clinical Affairs; Head of Market Access / Reimbursement; HEOR lead; Head of Regulatory; Clinical Program Manager
  for ARC-EX home; VA PI (study collaborator).
- **Public routes:** onwd.com contact page; ONWARD investor relations; LinkedIn company page; ClinicalTrials.gov central contacts.
- **Funding:** [CC] cash EUR 81.5M at 30 June 2026; ~EUR 40M equity raise reported in Q1 2026 release; runway to Q1 2028 (company claim).
- **Uncertainties:** whether MyARCEX already logs and exports home sessions; whether ONWARD prefers in-house; NCT06140706 registry is stale.

### 4.2 Kandu, Inc. (IpsiHand; Neurolutions subsidiary) - fit 5
- **Devices / stage:** IpsiHand EEG-BCI-driven hand orthosis for chronic stroke, De Novo DEN200046 (2021) [V]; merged with Kandu
  Health April 2025 ($30M new funding reported) [CC]. Fully remote home RCT NCT05965713 (n=109, completed 2025-09; primary UEFM) [V],
  published 2026 [CC].
- **Why now:** Anthem DME.00052 (last reviewed 2026-08-13) rates BCI rehabilitation devices, naming IpsiHand, as investigational and
  lists the missing evidence: sham/blinding, post-treatment durability, independent replication, real-world arm use and
  daily-living independence [V] https://www.anthem.com/medpolicies/abcbs/active/mp_pw_e003193.html. Kandu has registered a
  100-patient RWE study (NCT07147881) with FM-UE, Barthel, **Zarit Burden Interview**, PSFS, EQ-5D-5L to 24 months; registry
  still shows "not yet recruiting" (last update 2025-08) [V].
- **NeuroMetric use case [INF]:** independent measurement layer for the RWE study: blinded remote rater workflow for FM-UE/ARAT
  video, wrist-worn real-world arm-use metrics, ZBI/PSFS capture, durability follow-up, and a payer-facing package that maps each
  Anthem criticism to the evidence collected.
- **Target roles:** Chief Medical/Clinical Officer; VP Clinical Affairs; Head of Market Access; HEOR lead; RWE Program Manager.
- **Public routes:** Kandu and Neurolutions company contact pages; LinkedIn company pages; ClinicalTrials.gov contact for NCT07147881.
- **Uncertainties:** RWE study start; budget; whether Kandu's own care platform will host the data.

### 4.3 Bioness Medical, Inc. (Accelmed Partners) - fit 4
- **Devices / stage:** PoNS chronic-stroke gait 510(k) K253061 (decision 2026-05-13; announced 2026-06-29) [V]/[CC]; MS gait De Novo
  DEN200050 [V]; L300 Go, L360, H200 FES [V]; Harmonic upper-limb robot (assets acquired 2025; clearance pending at the time) [CC].
  Independent since Bioventus sold the business to Accelmed (closed 2024-12-31) [V SEC].
- **Why now:** PoNS stroke protocol is 4 weeks in clinic then **8 weeks independent home use**; evidence is clinic FGA at fixed
  visits [V K253061 summary]. A newly expanded indication and a PE-funded portfolio build both need payer evidence.
- **Existing outcome approach:** FGA primary; durability at week 24; adherence as primary in the MS experience program
  (NCT05437276); MS registry with self-reported symptoms (NCT06930339) [V].
- **NeuroMetric use case [INF]:** home-phase companion (session adherence from controller logs if exportable, daily-life walking
  metrics from wearables, falls, care-partner burden) and a common outcomes layer across PoNS, FES and robotics for payer files.
- **Target roles:** VP Clinical Affairs; Head of Market Access / Reimbursement; HEOR lead; Head of Regulatory; PoNS product lead.
- **Public routes:** bionessrehab.com contact page; LinkedIn company page; PR Newswire releases.
- **Uncertainties:** exportability of PoNS logs; PE priorities; PoNS deal terms undisclosed.

### 4.4 Mobia Medical, Inc. (formerly MicroTransponder; Vivistim) - fit 4
- **Devices / stage:** Vivistim Paired VNS (implanted), PMA P210007 (2021) [V]; renamed 2026-02-24; Nasdaq IPO (MOBI) May 2026 raising
  ~$150M; >1,000 systems implanted; ~USD 32M 2025 sales [CC].
- **Why now:** most commercial payers treat Vivistim as experimental and require prior authorization [CC, relayed from IPO filing
  coverage]; 1,000-patient GRASP registry (NCT05301140; FM-A, WMFT, SIS, MAL) recruiting; VNS-REHAB At-Home post-market study
  (NCT05691023; primary in-home therapist time) with estimated primary completion 2026-12-31 [V].
- **NeuroMetric use case [INF]:** registry add-on that adds objective real-world arm use to self-reported MAL, remote SIS/COPM and
  care-partner burden; evidence summaries for prior-authorization appeals. Strictly read-only; no interaction with stimulation.
- **Target roles:** VP Clinical Affairs; Head of Medical Affairs; Head of Market Access; HEOR lead; Registry Program Manager.
- **Public routes:** Mobia Medical investor relations; company contact page; LinkedIn company page.
- **Uncertainties:** going-concern language; existing registry vendor; Class III sensitivities.

### 4.5 Cognixion - fit 5
- **Devices / stage:** Cognixion ONE / Axon-R non-invasive AR-EEG BCI speech-generating device; FDA Breakthrough reported [CC];
  NIDCD-collaborating within-subject ALS trial NCT07871071 (n=30; start est. 2026-11-15) comparing AR-BCI, screen BCI and the
  participant's existing eye-gaze SGD [V].
- **Why now:** the registered primary endpoint is **voluntary daily use time per input modality**; secondaries include SUS, NASA-TLX,
  ALSSQOL-SF, **Zarit Burden Interview**, conversation metrics and ALSFRS-R; "caregiver setup time" is an exploratory outcome [V]
  https://clinicaltrials.gov/study/NCT07871071. This is NeuroMetric's capability set written as a protocol.
- **NeuroMetric use case [INF]:** independent real-world-use and caregiver analytics; a pre-specified comparator framework versus
  eye-gaze AAC that could later serve FDA and SGD funding files.
- **Target roles:** Head of Clinical/Regulatory; trial PI; Clinical Program Manager; funding/market-access lead for SGDs.
- **Public routes:** cognixion.com contact page; ClinicalTrials.gov contact on NCT07871071; LinkedIn company page.
- **Funding:** [CC] ~USD 25M venture (undated report), ALS Association ALS Accel support, NIDCD collaboration.
- **Uncertainties:** small company with in-trial logging already designed; budget; device uncleared.

**Tier-1 watch list (move up when the trigger resolves):** Synchron (resume after the Nov 2026 trial pause; pivotal endpoints),
Paradromics (Connect-One expanding beyond first participants), Myomo (if payers tighten MyoPro documentation),
Shirley Ryan AbilityLab COA project (partner/competitor decision once the index is published).

## 5. Tier 2 and Tier 3 profiles

Compact profiles generated from the same records as `prospects.csv`. Labels inside fields follow CONVENTIONS.md; the `Evidence` line gives the dominant label for the record.

### Tier 2

#### Shirley Ryan AbilityLab (COA for AT & BCI) (US) - fit 4/5
- **Segment / devices:** Academic - outcome measure development - Multi-device digital-independence assessment (eye tracker, mouth joystick, EEG, implanted BCI)
- **Stage:** Recruiting since 2026-01 (n=60; primary completion est. 2026-12); Neuralink collaborator
- **Trials:** NCT07407725; NCT05251077
- **Known endpoints:** PerfOs on simulated digital tasks, NASA-TLX (patient and clinician), SUS (patient and clinician), qualitative questionnaire, PIADS; ISNCSCI, ALSFRS-R, ECAS, IRF-PAI GG, WHOQOL-BREF
- **Current outcome approach:** Building a composite 'digital independence' index (PerfO + ClinRO + PRO)
- **NeuroMetric use case [INF]:** Partner for a home and real-world extension of their in-clinic index plus a care-partner module (also the closest competitor to a NeuroMetric COA)
- **Target roles:** PI; Research Ops Lead; Technology transfer office
- **Public contact route:** sralab.org research pages; ClinicalTrials.gov contact on NCT07407725
- **Funding:** [INF] institutional + Neuralink collaboration
- **Uncertainties:** Competitive overlap; IP ownership of the index
- **Evidence:** V (registry). Sources (accessed 2026-11-27): https://clinicaltrials.gov/study/NCT07407725

#### University of Calgary (BCI@Home, pediatric) (CA) - fit 4/5
- **Segment / devices:** Academic home BCI (pediatric) - Non-invasive home BCI systems for youth
- **Stage:** Recruiting (n=18)
- **Trials:** NCT07073378
- **Known endpoints:** COPM (primary); implementation reach
- **Current outcome approach:** Home deployment with COPM
- **NeuroMetric use case [INF]:** Home real-world-use telemetry and family/caregiver burden module
- **Target roles:** PI; Research Ops Lead
- **Public contact route:** Alberta Children's Hospital / BCI@Home pages; ClinicalTrials.gov contact
- **Funding:** [PK] grants/philanthropy
- **Uncertainties:** Pediatric scope; grant budget
- **Evidence:** V (registry). Sources (accessed 2026-11-27): https://clinicaltrials.gov/study/NCT07073378

#### UMC Utrecht (Brain Center BCI program) (NL) - fit 4/5
- **Segment / devices:** Academic iBCI (home use) - HD-ECoG BCI; cortical communication system
- **Stage:** Recruiting (n=1 SCI; prior CCS study)
- **Trials:** NCT07640711; NCT06207591
- **Known endpoints:** Accuracy, speed, VAS workload, NASA-TLX, QUEST, PIADS, signal stability; 'validation of software for independent home-use of advanced BCIs'
- **Current outcome approach:** Explicit home-use validation with AT-impact measures
- **NeuroMetric use case [INF]:** Home-use outcome tooling partner
- **Target roles:** PI; Research Ops Lead
- **Public contact route:** UMC Utrecht research pages; ClinicalTrials.gov contact
- **Funding:** [PK] EU/NWO grants
- **Uncertainties:** n=1; grant budget
- **Evidence:** V (registry). Sources (accessed 2026-11-27): https://clinicaltrials.gov/study/NCT07640711

#### VA Palo Alto Health Care System (SCI home tSCS) (US) - fit 4/5
- **Segment / devices:** Academic/VA neuromodulation - ARC-EX-based home tSCS via video telehealth
- **Stage:** Not yet recruiting per stale registry (last update 2025-04)
- **Trials:** NCT06140706
- **Known endpoints:** NASA-TLX, QUEST 2.0 (primary); GRASSP, CUE-Q, DASH, COPM
- **Current outcome approach:** Telehealth-supervised home program
- **NeuroMetric use case [INF]:** Instrument harmonisation and home telemetry for the VA study and VA ARC-EX home roll-out
- **Target roles:** PI; VA research office
- **Public contact route:** VA Palo Alto research office; ClinicalTrials.gov contact
- **Funding:** [V] VA (federal) sponsor
- **Uncertainties:** Actual status unknown; VA procurement
- **Evidence:** V (registry). Sources (accessed 2026-11-27): https://clinicaltrials.gov/study/NCT06140706

#### Synchron, Inc. (US/AU) - fit 4/5
- **Segment / devices:** Implantable BCI (endovascular) - Stentrode + Synchron BCI (first- and second-generation)
- **Stage:** COMMAND EFS (n=6) active; 2026 INTENT EFS (US, 5 sites) and FOCUS-AUS; FOCUS-Canada terminated (insufficient recruitment, n=1); pivotal targeted for 2026 [CC]; Nov 2026 voluntary pause of second-gen trials over lead performance [CC]
- **Trials:** NCT05035823; NCT07543367; NCT07533903; NCT07446114; NCT03834857
- **Known endpoints:** Device-related SAEs, vessel patency, migration, signal stability, time to activation, 'Synchron BCI use up to 1 year' (other outcome)
- **Current outcome approach:** Safety-centric registered endpoints; functional outcomes implied by study names (FOCUS) but not registered
- **NeuroMetric use case [INF]:** Pivotal-grade functional and real-world-use endpoint package (digital-independence tasks, home use minutes, caregiver burden, AT comparators); HEOR inputs for CMS coverage
- **Target roles:** VP Clinical Affairs; Head of Regulatory; HEOR / Market Access lead; Clinical Program Manager
- **Public contact route:** synchron.com contact page; LinkedIn company page; ClinicalTrials.gov central contacts
- **Funding:** [CC] Series D USD 200M (Nov 2025), total ~USD 345M
- **Uncertainties:** Trial pause duration; pivotal endpoint choice may already be locked; in-house capability
- **Evidence:** V (registry); CC (funding, pause). Sources (accessed 2026-11-27): https://clinicaltrials.gov/study/NCT07543367; https://clinicaltrials.gov/study/NCT07533903; https://clinicaltrials.gov/study/NCT07446114; https://www.massdevice.com/synchron-raises-200m-seriesd-bci-commercialization/; https://www.medicaldaily.com/synchron-pauses-wireless-brain-implant-trials-481309

#### Paradromics, Inc. (US) - fit 4/5
- **Segment / devices:** Implantable BCI (intracortical, speech) - Connexus BCI (421 electrodes, fully implanted, chest transceiver)
- **Stage:** FDA IDE Nov 2025; Connect-One EFS: first implant June 2026 (U Michigan); sites U Michigan, UC Davis, MGH; real-time speech reported [CC]; plans ~10 patients [CC]
- **Trials:** NCT07357428
- **Known endpoints:** Primary safety (device-related AEs to 12 months); long-term safety to 6 years
- **Current outcome approach:** Registered endpoints safety-only; speech metrics presumably internal [INF]
- **NeuroMetric use case [INF]:** Communication-participation and home-use evidence (daily use, conversation partners, caregiver burden, ALS progression context) to prepare pivotal endpoints
- **Target roles:** VP Clinical/Regulatory; Clinical Program Manager; site PIs
- **Public contact route:** paradromics.com contact page; LinkedIn company page; ClinicalTrials.gov central contact
- **Funding:** [UNR] not re-verified this session
- **Uncertainties:** EFS very small; pivotal timing; in-house analytics
- **Evidence:** V (registry); CC (implant, IDE). Sources (accessed 2026-11-27): https://clinicaltrials.gov/study/NCT07357428; https://www.businesswire.com/news/home/20260617963732/en/Paradromics-and-University-of-Michigan-Complete-First-Connexus-BCI-Implantation-for-the-FDA-Approved-Connect-One-Clinical-Study

#### Phantom Neuro Inc. (US/AU) - fit 4/5
- **Segment / devices:** Implanted peripheral neural interface (prosthetics) - Phantom X implantable EMG sensor for myoelectric prosthesis control
- **Stage:** FDA Breakthrough + TAP (2025) [CC]; EFS NCT07325708 recruiting since 2026-04
- **Trials:** NCT07325708; NCT06446037
- **Known endpoints:** Safety; ACMC; targeted Box and Blocks; gesture accuracy; SNR; at-home wear duration; at-home IMU limb-usage pattern
- **Current outcome approach:** Device + IMU home telemetry planned in-trial
- **NeuroMetric use case [INF]:** Neutral home real-world-use analytics and participation/satisfaction PROs packaged for FDA and O&P payers
- **Target roles:** VP Clinical/Regulatory; Clinical Program Manager
- **Public contact route:** company website contact page; LinkedIn company page
- **Funding:** [CC] Series A USD 19M (April 2025, Ottobock lead)
- **Uncertainties:** Prosthetics adjacent to core; small EFS
- **Evidence:** V (registry); CC. Sources (accessed 2026-11-27): https://clinicaltrials.gov/study/NCT07325708; https://techcrunch.com/2025/04/15/phantom-neuro-grabs-19m-to-help-amputees-gain-control-of-their-phantom-limbs

#### Myomo, Inc. (US) - fit 4/5
- **Segment / devices:** Wearable powered orthosis (home) - MyoPro myoelectric elbow-wrist-hand orthosis
- **Stage:** Commercial; record Q3 2026 revenue USD 12.3M; Medicare Part B ~51% of Q1 2026 revenue
- **Trials:** NCT05575674; NCT04900896; NCT02544672
- **Known endpoints:** DASH (retrospective); strength, ROM, QoL; FMA-UE, MAS, BBT
- **Current outcome approach:** Retrospective clinic outcomes; O&P documentation for Medicare/payer claims
- **NeuroMetric use case [INF]:** Real-world wear/use telemetry and DASH/COPM capture for medical-necessity documentation and payer appeals; published RWE
- **Target roles:** VP Clinical/Medical Affairs; Head of Reimbursement; HEOR lead; Clinical Program Manager
- **Public contact route:** myomo.com contact page; Myomo investor relations; LinkedIn company page
- **Funding:** [CC] Public (NYSE American MYO); FY2026 revenue guidance USD 46-47M
- **Uncertainties:** Already reimbursed - urgency lower; device's own sensors may already log use; MyoPro regulatory basis not re-verified
- **Evidence:** V (registry, openFDA); CC (financials). Sources (accessed 2026-11-27): https://finviz.com/news/419501/myomo-reports-third-quarter-2026-financial-and-operating-results; https://www.businesswire.com/news/home/20260507836938/en/myomo-reports-first-quarter-2026-financial-and-operating-results/; https://clinicaltrials.gov/study/NCT05575674

#### Control Bionics Ltd (AU/US) - fit 3/5
- **Segment / devices:** AAC / EMG switch AT (ALS) - NeuroNode (EMG + eye-gaze SGD), DROVE autonomous wheelchair module (TGA Class I), NextLevel iOS speech devices (US JV)
- **Stage:** Commercial; ASX: CBL; US billing code for NextLevel devices with first revenue targeted Sept 2026 [CC]; distribution via Tobii Dynavox (DE) and PRC-Saltillo [CC]
- **Trials:** none found
- **Known endpoints:** n/a
- **Current outcome approach:** Funding documentation [PK]
- **NeuroMetric use case [INF]:** Real-world-use and participation evidence for SGD funding; ALS caregiver burden
- **Target roles:** CEO; Clinical/Funding lead
- **Public contact route:** controlbionics.com contact page; ASX CBL announcements
- **Funding:** [CC] ASX-listed small cap
- **Uncertainties:** Small budget
- **Evidence:** CC. Sources (accessed 2026-11-27): https://smallcaps.com.au/article/control-bionics-seals-us-joint-venture-for-ios-speech-devices-with-nextlevel-assistive-technology; https://announcements.asx.com.au/asxpdf/20261029/pdf/075y1sf8hj4sj0.pdf

#### Dynavox Group AB (Tobii Dynavox) (SE/US) - fit 3/5
- **Segment / devices:** AAC / eye-gaze AT - TD I-Series eye-gaze SGDs, TD Snap, TD Pilot; distributes Control Bionics NeuroNode in Germany
- **Stage:** Commercial; H1 2026 revenue SEK 1,257M; acquisitions SR Labs (IT, closed 2026-04) and German resellers; U.S. health-economic study 'Exploring the Benefits of Assistive Communication' reported
- **Trials:** none found in registry
- **Known endpoints:** Company-reported: QoL improvement and social return on investment (US, Swedish, German studies)
- **Current outcome approach:** Health-economic studies; funding/prescription paperwork via SLP teams; reimbursement processes 'drawn-out'
- **NeuroMetric use case [INF]:** Real-world use + participation evidence for SGD funding files; comparator data vs BCI-based AAC; partner channel to AAC clinics
- **Target roles:** Head of Market Access / Funding; HEOR lead; Clinical (SLP) director
- **Public contact route:** dynavoxgroup.com investor relations; tobiidynavox.com contact page; LinkedIn company page
- **Funding:** [CC] Listed Nasdaq Stockholm
- **Uncertainties:** May view BCI evidence as competitive; litigation with AbleNet; willingness to fund third-party outcomes
- **Evidence:** CC. Sources (accessed 2026-11-27): https://news.cision.com/dynavox-group/r/dynavox-group-interim-report-second-quarter-2026,c4376655; https://news.cision.com/dynavox-group/r/dynavox-group-to-acquire-sr-labs-healthcare-in-italy,c4285990

#### PRC-Saltillo (US) - fit 3/5
- **Segment / devices:** AAC devices and software - Accent / NovaChat SGDs, LAMP WFL, Unity; Therapy Box apps (acquired Jan 2026)
- **Stage:** Commercial (private) [PK]
- **Trials:** none found
- **Known endpoints:** n/a
- **Current outcome approach:** Funding reports via SLPs [PK]
- **NeuroMetric use case [INF]:** Outcomes and use evidence for SGD funding; partner for BCI-vs-AAC comparator
- **Target roles:** Funding/Market Access lead; Clinical (SLP) lead
- **Public contact route:** prc-saltillo.com contact page; LinkedIn company page
- **Funding:** [PK] private
- **Uncertainties:** Ownership/funding not verified
- **Evidence:** CC; PK. Sources (accessed 2026-11-27): https://www.aap.com.au/aapreleases/cision20260120ae65683

#### EPFL / .NeuroRestore / CHUV (CH) - fit 3/5
- **Segment / devices:** Academic brain-spine interface - ARC-BSI cervical and stroke systems (with ONWARD, Clinatec)
- **Stage:** Recruiting
- **Trials:** NCT05665998; NCT07610850; NCT06243952; NCT07745686
- **Known endpoints:** GRASSP, ARAT, CUE-T; FMA-LE/UE, 10MWT, 6MWT, TUG; PIADS, GAS, PGIC, SIS, SS-QOL
- **Current outcome approach:** Rich clinic battery incl. PIADS/GAS monthly
- **NeuroMetric use case [INF]:** Home real-world-use telemetry and harmonised PRO capture across ONWARD-linked studies
- **Target roles:** PI; Research Ops Lead
- **Public contact route:** EPFL .NeuroRestore pages; ClinicalTrials.gov contacts
- **Funding:** [PK] Swiss/EU grants
- **Uncertainties:** Ties to ONWARD
- **Evidence:** V (registry). Sources (accessed 2026-11-27): https://clinicaltrials.gov/study/NCT07610850; https://clinicaltrials.gov/study/NCT05665998

#### BrainGate consortium (MGH, Brown, Stanford, Emory, Providence VA) (US) - fit 3/5
- **Segment / devices:** Academic iBCI - BrainGate Neural Interface System (Utah arrays)
- **Stage:** Long-running feasibility; speech, tablet and aphasia sub-studies; VA mobile iBCI (not yet recruiting 2027)
- **Trials:** NCT00912041; NCT05724173; NCT06511934; NCT07791459; NCT05470478
- **Known endpoints:** Safety; feasibility; decoded speech accuracy; closed-loop cursor performance
- **Current outcome approach:** Lab performance metrics; at-home sessions in participants' residences [PK]
- **NeuroMetric use case [INF]:** Standardised home-use logging and participant/caregiver outcomes across sites; contribute to COA development
- **Target roles:** PI; Research Ops Lead; Clinical research coordinator lead
- **Public contact route:** braingate.org; institutional lab pages; ClinicalTrials.gov contacts
- **Funding:** [V] NIH (NIDCD, NINDS) and VA collaborators listed in registry
- **Uncertainties:** Grant-limited budgets; procurement cycles
- **Evidence:** V (registry). Sources (accessed 2026-11-27): https://clinicaltrials.gov/study/NCT00912041; https://clinicaltrials.gov/study/NCT05724173; https://clinicaltrials.gov/study/NCT05470478

#### Johns Hopkins University (CortiCom; INTENT with Blackrock/APL) (US) - fit 3/5
- **Segment / devices:** Academic iBCI - CortiCom ECoG; INTENT neural interface system
- **Stage:** CortiCom recruiting; INTENT starts 2027-01
- **Trials:** NCT03567213; NCT07521930; NCT03161067
- **Known endpoints:** Time to explant; BCI success rate and speed; BCI control of assistive devices; sensory feedback
- **Current outcome approach:** Lab metrics
- **NeuroMetric use case [INF]:** Home-use and participation outcomes for INTENT
- **Target roles:** PI; Research Ops Lead
- **Public contact route:** JHU lab pages; ClinicalTrials.gov contacts
- **Funding:** [V] NINDS collaborator
- **Uncertainties:** Budget
- **Evidence:** V (registry). Sources (accessed 2026-11-27): https://clinicaltrials.gov/study/NCT03567213; https://clinicaltrials.gov/study/NCT07521930

#### CHU Grenoble Alpes / Clinatec (CEA) (FR) - fit 3/5
- **Segment / devices:** Academic iBCI (WIMAGINE) - WIMAGINE wireless ECoG; ARC-BCI partner
- **Stage:** Stroke BCI recruiting; speech BCI not yet recruiting
- **Trials:** NCT07477613; NCT07698496; NCT02550522
- **Known endpoints:** Safety; efficacy of BCI-driven task-oriented rehab on daily-life movements; speech feasibility
- **Current outcome approach:** Clinic
- **NeuroMetric use case [INF]:** Daily-life function and caregiver outcomes
- **Target roles:** PI; Research Ops Lead
- **Public contact route:** Clinatec website; ClinicalTrials.gov contacts
- **Funding:** [PK] public funding
- **Uncertainties:** Language/EU procurement
- **Evidence:** V (registry). Sources (accessed 2026-11-27): https://clinicaltrials.gov/study/NCT07477613

#### University of Pittsburgh RNEL / University of Chicago (US) - fit 3/5
- **Segment / devices:** Academic iBCI (sensorimotor) - CRS arrays (record + stimulate)
- **Stage:** Recruiting (n=30 est.)
- **Trials:** NCT01894802
- **Known endpoints:** Safety; long-term recording and control of external devices
- **Current outcome approach:** Lab task performance
- **NeuroMetric use case [INF]:** Functional and home-use outcome layer
- **Target roles:** PI; Research Ops Lead
- **Public contact route:** Pitt Rehab Neural Engineering Labs pages; ClinicalTrials.gov contact
- **Funding:** [PK] NIH/DARPA
- **Uncertainties:** Budget
- **Evidence:** V (registry). Sources (accessed 2026-11-27): https://clinicaltrials.gov/study/NCT01894802

#### UC Davis Neuroprosthetics Lab (US) - fit 3/5
- **Segment / devices:** Academic iBCI (speech) - BrainGate2 speech; Paradromics Connect-One site
- **Stage:** Recruiting speech studies
- **Trials:** NCT06094205; NCT07918768; NCT07357428
- **Known endpoints:** Implant duration without SAEs; decoded speech accuracy
- **Current outcome approach:** Lab metrics
- **NeuroMetric use case [INF]:** Communication participation and caregiver measures; home-use logging
- **Target roles:** PI; Research Ops Lead
- **Public contact route:** UC Davis Health lab pages; ClinicalTrials.gov contacts
- **Funding:** [V] NIDCD collaborator
- **Uncertainties:** Budget
- **Evidence:** V (registry). Sources (accessed 2026-11-27): https://clinicaltrials.gov/study/NCT06094205; https://clinicaltrials.gov/study/NCT07918768

#### UTHealth Houston (RECLAIM speech iBCI) (US) - fit 3/5
- **Segment / devices:** Academic iBCI (speech) - RECLAIM intracortical system
- **Stage:** Not yet recruiting (2026-11 est.)
- **Trials:** NCT07933549
- **Known endpoints:** AEs; WER, PER, BLEU, BERT score
- **Current outcome approach:** Language-model metrics
- **NeuroMetric use case [INF]:** Communication participation and caregiver outcomes
- **Target roles:** PI
- **Public contact route:** ClinicalTrials.gov contact
- **Funding:** [PK] NIH
- **Uncertainties:** Early
- **Evidence:** V (registry). Sources (accessed 2026-11-27): https://clinicaltrials.gov/study/NCT07933549

#### UCSF (Chang lab; Ganguly lab) (US) - fit 3/5
- **Segment / devices:** Academic iBCI (speech, ECoG) - ECoG BMI (PMT/Blackrock combination device)
- **Stage:** Recruiting
- **Trials:** NCT03698149
- **Known endpoints:** Safety; NIDCD objectives (not detailed in registry)
- **Current outcome approach:** Lab metrics
- **NeuroMetric use case [INF]:** Communication-participation and caregiver outcomes
- **Target roles:** PI; Research Ops Lead
- **Public contact route:** UCSF lab pages; ClinicalTrials.gov contact
- **Funding:** [V] NIDCD collaborator
- **Uncertainties:** Chang co-founded Echo Neurotechnologies - potential conflict
- **Evidence:** V (registry). Sources (accessed 2026-11-27): https://clinicaltrials.gov/study/NCT03698149

#### Case Western Reserve / UH Cleveland (ReHAB) (US) - fit 3/5
- **Segment / devices:** Academic iBCI + FES - ReHAB system (BCI + implanted FES)
- **Stage:** Recruiting
- **Trials:** NCT03898804; NCT07225582
- **Known endpoints:** AEs; cursor target acquisition; ADL Abilities Test; Grasp Release Test
- **Current outcome approach:** Clinic tests
- **NeuroMetric use case [INF]:** Home functional use outcomes
- **Target roles:** PI; Research Ops Lead
- **Public contact route:** ClinicalTrials.gov contacts; institutional pages
- **Funding:** [PK] NIH/VA
- **Uncertainties:** Budget
- **Evidence:** V (registry). Sources (accessed 2026-11-27): https://clinicaltrials.gov/study/NCT03898804

#### University of Miami / Miami Project to Cure Paralysis (US) - fit 3/5
- **Segment / devices:** Academic neuromodulation + iBCI site - Neuralink site; ECoG/SCS studies; task practice + SCS
- **Stage:** Active
- **Trials:** NCT06533969; NCT06406855; NCT06494020; NCT07929792 (Neuralink)
- **Known endpoints:** GRASSP, SCIM III, MEP, kinematics, QoL
- **Current outcome approach:** Clinic scales
- **NeuroMetric use case [INF]:** Home-use and participation outcomes
- **Target roles:** PI; Research Ops Lead
- **Public contact route:** Miami Project website; ClinicalTrials.gov contacts
- **Funding:** [PK] DoD/NIH/philanthropy
- **Uncertainties:** Budget
- **Evidence:** V (registry). Sources (accessed 2026-11-27): https://clinicaltrials.gov/study/NCT06533969; https://clinicaltrials.gov/study/NCT06494020

#### Blackrock Neurotech (US) - fit 3/5
- **Segment / devices:** Implantable BCI (Utah array supplier) - NeuroPort / Utah array; MoveAgain (Breakthrough) [CC]
- **Stage:** Array supplier to most academic iBCI trials; collaborator on JHU INTENT (starts 2027-01); 2026 corporate milestones unverified
- **Trials:** NCT07521930; (supplier to NCT00912041, NCT01894802, NCT03698149)
- **Known endpoints:** Via academic partners: safety, BCI control of assistive devices, sensory feedback
- **Current outcome approach:** Academic partner protocols
- **NeuroMetric use case [INF]:** Harmonised multi-site functional and home-use outcomes for a MoveAgain regulatory file
- **Target roles:** Head of Clinical/Regulatory; Clinical Program Manager
- **Public contact route:** company website contact page; LinkedIn company page
- **Funding:** [CC] Tether USD 200M majority stake (2024)
- **Uncertainties:** Strategy and pivotal plans unclear [UNR]
- **Evidence:** V (registry); CC. Sources (accessed 2026-11-27): https://clinicaltrials.gov/study/NCT07521930; https://www.theblock.co/post/291414/tether-invests-200-million-blackrock-neurotech

#### Neuralink Corp (US) - fit 3/5
- **Segment / devices:** Implantable BCI (intracortical) - N1 Implant, R1 surgical robot; Blindsight (vision)
- **Stage:** Multiple EFS (US, CA, UK, UAE); 21 participants as of Jan 2026 [CC]; VOICE speech EFS; new EFS adds chronic ischemic stroke (U Miami, Nov 2026); no pivotal registered
- **Trials:** NCT06429735; NCT06710626; NCT07224256; NCT07929792; NCT06700304; NCT07127172; NCT06992596; NCT07407725 (collaborator)
- **Known endpoints:** Device/procedure AEs; MoCA, PHQ-9, GAD-7; CONVOY: PIADS and ATD-PA every 3 months; ability to control assistive robotic arm
- **Current outcome approach:** In-house performance metrics; co-developing a 'digital independence' COA with Shirley Ryan AbilityLab
- **NeuroMetric use case [INF]:** Independent home-use and caregiver-burden evidence; HEOR inputs; but more likely a standards/partner interaction than a buyer
- **Target roles:** Head of Clinical; Head of Regulatory; Clinical Research Director
- **Public contact route:** neuralink.com (patient registry / contact); LinkedIn company page
- **Funding:** [CC] Series E USD 650M (June 2025, ~USD 9B pre-money)
- **Uncertainties:** Strong in-house build preference; already partnered on COA; access difficult
- **Evidence:** V (registry); CC (participants, funding). Sources (accessed 2026-11-27): https://clinicaltrials.gov/study/NCT06710626; https://clinicaltrials.gov/study/NCT07929792; https://clinicaltrials.gov/study/NCT07407725; https://pharmaphorum.com/news/neuralink-raises-650m-widen-use-brain-implants; https://www.yahoo.com/news/articles/elon-musks-neuralink-says-21-183038116.html

#### Precision Neuroscience Corp (US) - fit 3/5
- **Segment / devices:** Implantable BCI (thin-film cortical) - Layer 7 cortical interface (Layer 7-T 510(k) K242618, temporary)
- **Stage:** Temporary/intraoperative commercial use; >100 procedures [CC]; Series D funds clinical expansion and further FDA review [CC]; no chronic BCI trial found in registry
- **Trials:** none found under sponsor name
- **Known endpoints:** n/a (intraoperative research)
- **Current outcome approach:** Academic intraoperative studies (Penn, UChicago, Mount Sinai, WVU) [CC]
- **NeuroMetric use case [INF]:** Outcome framework for a future chronic-implant study
- **Target roles:** VP Clinical Affairs; Head of Regulatory
- **Public contact route:** company website contact page; LinkedIn company page
- **Funding:** [CC] Series D USD 250M (Sept 2026), ~USD 430M total
- **Uncertainties:** Chronic program timing unknown
- **Evidence:** V (openFDA); CC. Sources (accessed 2026-11-27): https://api.fda.gov/device/510k.json?search=applicant:%22Precision%20Neuroscience%22; https://hlth.com/insights/news/precision-neuroscience-raises-250m-to-advance-layer-7-brain-computer-interface

#### g.tec medical engineering GmbH (AT) - fit 3/5
- **Segment / devices:** Non-invasive BCI rehab + DoC assessment - recoveriX (EEG BCI + FES), mindBEAGLE, research amplifiers
- **Stage:** recoveriX CE-marked per company [PK]; no FDA clearance for recoveriX found; active stroke/PD trials
- **Trials:** NCT07537530; NCT06940635; NCT06690931; NCT06426602 (mindBEAGLE, investigator)
- **Known endpoints:** 10MWT, TUG, MAS; GUSS, BIAS-R, COAST, FMA-UE, NHPT, BBT, EQ-5D-3L; MDS-UPDRS III, PDQ
- **Current outcome approach:** Clinic-administered scales in franchise clinics
- **NeuroMetric use case [INF]:** Standardised outcome registry across recoveriX clinics; US-entry evidence
- **Target roles:** CEO / Clinical research lead
- **Public contact route:** gtec.at contact page; LinkedIn company page
- **Funding:** [UNR] private
- **Uncertainties:** US regulatory status; willingness to pay
- **Evidence:** V (registry, openFDA). Sources (accessed 2026-11-27): https://www.gtec.at/product/recoverix-neurorehabilitation/; https://clinicaltrials.gov/study/NCT07537530

#### Cala Health, Inc. (US) - fit 3/5
- **Segment / devices:** Wearable neuromodulation (tremor, home) - Cala Trio, Cala kIQ, Cala kIQ Plus (TAPS wrist stimulator)
- **Stage:** Commercial; kIQ Plus 510(k) K253587 (2026-03-17); ~USD 50M raise April 2026 reported
- **Trials:** NCT05540626; NCT03597100; NCT05012579
- **Known endpoints:** Tremor power (device sensor), TETRAS, BF-ADL, UPDRS-III
- **Current outcome approach:** Device-native kinematic telemetry plus clinician scales
- **NeuroMetric use case [INF]:** Independent ADL/participation and care-partner measures to complement device tremor data; payer evidence packaging
- **Target roles:** VP Clinical Affairs; HEOR / Market Access lead
- **Public contact route:** calahealth.com contact page; LinkedIn company page
- **Funding:** [CC] ~USD 50M (April 2026, StartUp Health report)
- **Uncertainties:** Strong in-house telemetry reduces need; tremor is outside NeuroMetric's core motor-rehab/communication scope
- **Evidence:** V (FDA, registry); CC (funding). Sources (accessed 2026-11-27): https://www.accessdata.fda.gov/scripts/cdrh/cfdocs/cfPMN/pmn.cfm?ID=K253587; https://clinicaltrials.gov/study/NCT05540626; https://media.startuphealth.com/p/cala-health-secures-50m-to-scale-wearable-tremor-therapy-startup-health-insights-week-of-apr-28-2026

### Tier 3

#### BrainQ Technologies (IL/US) - fit 3/5
- **Segment / devices:** Home EMF neuromodulation - stroke - BQ / Q Therapeutic System (frequency-tuned low-intensity EMF; home)
- **Stage:** CE mark (BQ 2.0, Jan 2025); FDA Breakthrough; EMAGINE 2.0 pivotal terminated for poor accrual (2026-04); investigator studies at Burke, UF, Kessler
- **Trials:** NCT06386874; NCT05044507; NCT06979466; NCT07095920; NCT07499310
- **Known endpoints:** mRS (primary), FMA-UE, SIS-16, SIS hand, BBT, 10MWT, EQ-5D-5L
- **Current outcome approach:** Clinic-administered disability and motor scales
- **NeuroMetric use case [INF]:** Chronic-stroke home RWE with participation, real-world use and care-partner measures if they re-plan the US path
- **Target roles:** VP Clinical; Head of Regulatory
- **Public contact route:** company website contact page; LinkedIn company page
- **Funding:** [UNR] not verified this session
- **Uncertainties:** Regulatory path unclear after pivotal termination; budget
- **Evidence:** V (registry); CC (CE mark). Sources (accessed 2026-11-27): https://clinicaltrials.gov/study/NCT06386874; https://prnewswire.com/news-releases/brainq-achieves-ce-mark-for-its-breakthrough-therapy-for-reducing-disability-following-stroke-and-welcomes-stacey-pugh-as-chairman-of-the-board-302349118.html

#### Motus Nova (US) - fit 3/5
- **Segment / devices:** Home rehab robotics - stroke - Hand Mentor / Foot Mentor [PK]
- **Stage:** [PK] commercial home robotic therapy; no registry or openFDA hits found
- **Trials:** none found
- **Known endpoints:** none found
- **Current outcome approach:** [PK] remote therapist monitoring
- **NeuroMetric use case [INF]:** Real-world use + function evidence for home robotics
- **Target roles:** CEO / Clinical lead
- **Public contact route:** company website contact page (not re-verified)
- **Funding:** [UNR]
- **Uncertainties:** Basic corporate status not verified
- **Evidence:** PK; UNR. Sources (accessed 2026-11-27): https://clinicaltrials.gov/api/v2/studies?query.spons=Motus%20Nova

#### Echo Neurotechnologies (US) - fit 3/5
- **Segment / devices:** Implantable BCI (speech) - Speech neuroprosthesis platform (UCSF Chang lineage)
- **Stage:** Private; no company-sponsored trial found in registry
- **Trials:** none found
- **Known endpoints:** n/a
- **Current outcome approach:** n/a
- **NeuroMetric use case [INF]:** Communication-participation endpoints when a trial is registered
- **Target roles:** Clinical lead
- **Public contact route:** company website / careers page; LinkedIn company page
- **Funding:** [AE] ~USD 50M incl. a16z (PitchBook via Bloomberg, Jan 2025)
- **Uncertainties:** Stage unknown
- **Evidence:** AE; CC. Sources (accessed 2026-11-27): https://www.bloomberg.com/news/articles/2025-01-30/andreessen-horowitz-backs-rival-to-musk-s-neuralink-in-new-funding-round

#### Smartbox Assistive Technology (UK) - fit 2/5
- **Segment / devices:** AAC software and devices - Grid software, Grid Pad eye-gaze devices
- **Stage:** Commercial; Verdane partnership Jan 2026 (nature unconfirmed)
- **Trials:** none found
- **Known endpoints:** n/a
- **Current outcome approach:** n/a
- **NeuroMetric use case [INF]:** UK/EU AAC outcome evidence
- **Target roles:** Clinical/Product lead
- **Public contact route:** thinksmartbox.com contact page (not re-verified)
- **Funding:** [UNR] Verdane deal unconfirmed
- **Uncertainties:** Deal nature unknown
- **Evidence:** UNR. Sources (accessed 2026-11-27): https://verdane.com/?p=5003

#### Caltech (Andersen lab) with Rancho Los Amigos / USC / Casa Colina / UCLA (US) - fit 2/5
- **Segment / devices:** Academic iBCI - Neural Prosthetic System 2; Neural Communication System
- **Stage:** Active
- **Trials:** NCT01964261 (Rancho, USC); NCT01958086 (Casa Colina, UCLA)
- **Known endpoints:** End-effector control; tablet control; safety
- **Current outcome approach:** Lab metrics
- **NeuroMetric use case [INF]:** Limited (basic-science orientation)
- **Target roles:** PI
- **Public contact route:** Caltech lab page; ClinicalTrials.gov contacts
- **Funding:** [PK] NIH
- **Uncertainties:** Basic-science focus
- **Evidence:** V (registry). Sources (accessed 2026-11-27): https://clinicaltrials.gov/study/NCT01964261; https://clinicaltrials.gov/study/NCT01958086

#### Medtech CROs (e.g., NAMSA, Avania, Medpace Medical Device, IQVIA MedTech) (US/EU) - fit 2/5
- **Segment / devices:** CRO / channel - n/a
- **Stage:** n/a
- **Trials:** n/a
- **Known endpoints:** n/a
- **Current outcome approach:** [PK] run IDE/post-market studies; subcontract eCOA/wearables
- **NeuroMetric use case [INF]:** White-label or subcontracted measurement module for neuro-device studies
- **Target roles:** Head of Medical Device Strategy; Business development (scientific partnerships)
- **Public contact route:** corporate partnership pages
- **Funding:** [PK]
- **Uncertainties:** Not researched this session
- **Evidence:** PK. Sources (accessed 2026-11-27): none (prior knowledge only)

#### Bionik Laboratories (CA/US) - fit 2/5
- **Segment / devices:** Clinic rehab robotics - InMotion ARM / ARM-HAND
- **Stage:** [CC, undated] ~450 installations; 2026 status unverified
- **Trials:** none found
- **Known endpoints:** none found
- **Current outcome approach:** Device performance reports [PK]
- **NeuroMetric use case [INF]:** Low - clinic robotics
- **Target roles:** Clinical lead
- **Public contact route:** company website contact page (not re-verified)
- **Funding:** [UNR]
- **Uncertainties:** Corporate status 2026 unknown
- **Evidence:** CC; UNR. Sources (accessed 2026-11-27): https://roboticsandautomationnews.com/?p=20773

#### Hocoma AG (DIH Holding US) (CH/US) - fit 2/5
- **Segment / devices:** Clinic rehab robotics - Lokomat, Armeo, Andago
- **Stage:** Commercial; parent DIH delisted from Nasdaq Nov 2025
- **Trials:** NCT03555825 (Burke-Hocoma)
- **Known endpoints:** FMA-UE, BBT, SIS, SF-36
- **Current outcome approach:** Device-generated reports
- **NeuroMetric use case [INF]:** Low - clinic robotics; financial distress
- **Target roles:** Clinical/Scientific affairs
- **Public contact route:** hocoma.com contact page
- **Funding:** [CC/8-K] parent states capital may be unavailable
- **Uncertainties:** Financial distress
- **Evidence:** V (registry); CC (8-K coverage). Sources (accessed 2026-11-27): https://www.streetinsider.com/SEC+Filings/Form+8-K+DIH+HOLDING+US%2C+INC.+For%3A+Nov+05/25565519.html; https://www.hocoma.com/us/solutions/lokomat/software/

#### Eyegaze Inc. (LC Technologies) (US) - fit 2/5
- **Segment / devices:** Eye-gaze AT - Eyegaze Edge [PK]
- **Stage:** [PK] commercial
- **Trials:** none found
- **Known endpoints:** n/a
- **Current outcome approach:** n/a
- **NeuroMetric use case [INF]:** Comparator data partner
- **Target roles:** Clinical lead
- **Public contact route:** company website contact page (not re-verified)
- **Funding:** [UNR]
- **Uncertainties:** Not researched beyond prior knowledge
- **Evidence:** PK. Sources (accessed 2026-11-27): none (prior knowledge only)

#### Flow Neuroscience AB (SE/US) - fit 2/5
- **Segment / devices:** Home neuromodulation - depression - FL-100 home tDCS headset
- **Stage:** FDA PMA P230024 (2025-12-08); US launch planned 2026 (completion unverified)
- **Trials:** NCT05202119
- **Known endpoints:** HDRS-17
- **Current outcome approach:** App-based home use + clinician scales
- **NeuroMetric use case [INF]:** Adherence/home-use evidence and payer packaging (adjacent only)
- **Target roles:** Head of Clinical; Market Access lead
- **Public contact route:** flowneuroscience.com contact page; LinkedIn company page
- **Funding:** [UNR] not verified this session
- **Uncertainties:** Psychiatric indication outside core scope
- **Evidence:** V (FDA PMA, registry); CC. Sources (accessed 2026-11-27): https://api.fda.gov/device/pma.json?search=applicant:%22Flow%20Neuroscience%22; https://clinicaltrials.gov/study/NCT05202119; https://psychiatrictimes.com/view/fda-approves-first-at-home-brain-stimulation-device-for-treatment-of-depression

#### electroCore, Inc. (US) - fit 2/5
- **Segment / devices:** Home neuromodulation - headache/pain - gammaCore nVNS; Quell
- **Stage:** Commercial; Q3 2026 net sales USD 9.7M; VA main Rx channel
- **Trials:** NCT02378844; NCT07523685 (investigator PTSD)
- **Known endpoints:** Migraine days, HIT-6, EQ-5D; CAPS-5 (PTSD)
- **Current outcome approach:** Headache diaries; VA purchasing
- **NeuroMetric use case [INF]:** Limited - possibly PTSD/TBI function studies
- **Target roles:** Medical Affairs; HEOR
- **Public contact route:** investor.electrocore.com; company contact page
- **Funding:** [CC] Public (Nasdaq ECOR)
- **Uncertainties:** Indication mismatch
- **Evidence:** V (registry, openFDA); CC (financials). Sources (accessed 2026-11-27): https://finviz.com/news/415846/electrocore-announces-third-quarter-2026-financial-results; https://clinicaltrials.gov/study/NCT02378844

#### Saebo, Inc. (US) - fit 2/5
- **Segment / devices:** Home orthoses / NMES - SaeboFlex, SaeboGlove, SaeboStim, SaeboVR [PK]
- **Stage:** [PK] commercial; no 2026 news found
- **Trials:** NCT00489580 (Kessler, 2005)
- **Known endpoints:** Grip, ARAT, FMA, SIS
- **Current outcome approach:** Clinic outcomes
- **NeuroMetric use case [INF]:** Low-moderate
- **Target roles:** Clinical education lead
- **Public contact route:** company website contact page (not re-verified)
- **Funding:** [UNR]
- **Uncertainties:** Small; evidence spending unclear
- **Evidence:** V (registry); PK. Sources (accessed 2026-11-27): https://clinicaltrials.gov/study/NCT00489580

#### Kinestica d.o.o. (SI) - fit 2/5
- **Segment / devices:** Home/clinic upper-limb sensor rehab - Bimeo [PK]
- **Stage:** [PK]
- **Trials:** none found
- **Known endpoints:** none found
- **Current outcome approach:** [PK]
- **NeuroMetric use case [INF]:** EU partner for sensor-based home assessment
- **Target roles:** CEO / Clinical lead
- **Public contact route:** company website contact page (not re-verified)
- **Funding:** [UNR]
- **Uncertainties:** Status not verified
- **Evidence:** PK; UNR. Sources (accessed 2026-11-27): https://clinicaltrials.gov/api/v2/studies?query.spons=Kinestica

#### BCIFlex Medical Technology (CN) - fit 2/5
- **Segment / devices:** Implantable BCI (China) - Implantable wireless BCI system (IWBCIS)
- **Stage:** Multicenter trial recruiting (n=34)
- **Trials:** NCT07784088
- **Known endpoints:** Brain-control success; dIADL; PHQ-9; monthly usage; WHOQOL-BREF; HADS-A; PIADS; satisfaction
- **Current outcome approach:** Registry PROs + usage
- **NeuroMetric use case [INF]:** Methods partner at most
- **Target roles:** Clinical lead
- **Public contact route:** company website (not verified)
- **Funding:** [UNR]
- **Uncertainties:** China data rules
- **Evidence:** V (registry). Sources (accessed 2026-11-27): https://clinicaltrials.gov/study/NCT07784088

#### NeuroXess (Shanghai) (CN) - fit 2/5
- **Segment / devices:** Implantable BCI (China) - Fully implanted wireless BCI
- **Stage:** Confirmatory study recruiting (n=32)
- **Trials:** NCT07720882
- **Known endpoints:** BCI-assisted ARAT response; ADL; ISNCSCI; device reliability
- **Current outcome approach:** Clinic tasks
- **NeuroMetric use case [INF]:** Post-market RWE (China)
- **Target roles:** Clinical lead
- **Public contact route:** company website
- **Funding:** [UNR]
- **Uncertainties:** China data rules
- **Evidence:** V (registry). Sources (accessed 2026-11-27): https://clinicaltrials.gov/study/NCT07720882

#### Shanghai StairMed Technology (CN) - fit 2/5
- **Segment / devices:** Implantable BCI (China) - Wireless intracortical BCI; Mandarin speech neuroprosthesis
- **Stage:** Several trials incl. SCI efficacy study (n=34)
- **Trials:** NCT07603752; NCT06829212; NCT07647315; NCT06944834
- **Known endpoints:** Brain-control success, usage duration, WHOQOL-BREF, dIADL, wheelchair control, caregiver burden, CPM/CER speech
- **Current outcome approach:** Includes caregiver burden and usage hours in registry
- **NeuroMetric use case [INF]:** Methods partner at most
- **Target roles:** Clinical lead
- **Public contact route:** company website
- **Funding:** [CC] ~CNY 500M round led by Alibaba
- **Uncertainties:** China data rules
- **Evidence:** V (registry); CC. Sources (accessed 2026-11-27): https://clinicaltrials.gov/study/NCT07603752; https://clinicaltrials.gov/study/NCT06829212

#### Neuracle Medical Technology (Shanghai) (CN) - fit 2/5
- **Segment / devices:** Implantable BCI (epidural, China) - NEO wireless semi-invasive BCI
- **Stage:** NMPA registration 2026-03-13 (hand motor augmentation, SCI); NHSA insurance code assigned [CC]
- **Trials:** NCT06990412; NCT05920174
- **Known endpoints:** BCI-assisted ARAT response rate; ISNCSCI; average monthly device usage time; QoL; satisfaction; caregiver satisfaction
- **Current outcome approach:** Registry-style device usage + clinic ARAT
- **NeuroMetric use case [INF]:** Post-market RWE (data residency and PIPL constraints)
- **Target roles:** Clinical/Regulatory lead
- **Public contact route:** company website; LinkedIn company page
- **Funding:** [UNR]
- **Uncertainties:** China data-export rules; channel
- **Evidence:** V (registry); CC. Sources (accessed 2026-11-27): https://clinicaltrials.gov/study/NCT06990412; https://www.fiercebiotech.com/medtech/china-approves-first-brain-computer-interface-implant-paralyzed-patients-sector-heats

#### Axoft, Inc. (US) - fit 2/5
- **Segment / devices:** Implantable BCI (soft materials) - Fleuron-based soft neural probe
- **Stage:** FIH completed 2025 (n=5); disorders-of-consciousness feasibility not yet recruiting (2027)
- **Trials:** NCT06673264; NCT07953036
- **Known endpoints:** AEs, recording feasibility, use
- **Current outcome approach:** Acute/subchronic research
- **NeuroMetric use case [INF]:** Later-stage only
- **Target roles:** Clinical lead
- **Public contact route:** company website; LinkedIn company page
- **Funding:** [CC] Series A USD 55M (April 2026)
- **Uncertainties:** Early, acute use
- **Evidence:** V (registry); CC. Sources (accessed 2026-11-27): https://clinicaltrials.gov/study/NCT07953036; https://hitconsultant.net/2026/04/30/axoft-series-a-funding-bio-inspired-ibci-fleuron/

#### INBRAIN Neuroelectronics (ES) - fit 2/5
- **Segment / devices:** Implantable interface (graphene) - Graphene cortical interface
- **Stage:** FIH (Manchester) completed; speech-decoding trial announced Feb 2026 [CC]; PD Breakthrough (2023) [CC]
- **Trials:** NCT06368310
- **Known endpoints:** Safety, recording/stimulation ability, usability questionnaire
- **Current outcome approach:** Acute intraoperative
- **NeuroMetric use case [INF]:** Later-stage only
- **Target roles:** Clinical lead
- **Public contact route:** company website; LinkedIn company page
- **Funding:** [CC] Series B USD 50M (Oct 2024)
- **Uncertainties:** Early stage
- **Evidence:** V (registry); CC. Sources (accessed 2026-11-27): https://clinicaltrials.gov/study/NCT06368310; https://www.massdevice.com/inbrain-completes-enrollment-first-human-bci-trial/

#### Augmental (US) - fit 2/5
- **Segment / devices:** Intraoral tongue interface AT - MouthPad (tongue trackpad), Vox (beta)
- **Stage:** Public US launch 2026-07-22 at USD 1,400; no FDA clearance referenced (out-of-pocket)
- **Trials:** none found
- **Known endpoints:** n/a
- **Current outcome approach:** n/a
- **NeuroMetric use case [INF]:** Comparator/alternative-access evidence if it pursues FDA/reimbursement
- **Target roles:** CEO / Clinical lead
- **Public contact route:** augmental.tech contact page (not re-verified); PR Newswire
- **Funding:** [UNR] pre-seed/seed only
- **Uncertainties:** Consumer channel
- **Evidence:** CC. Sources (accessed 2026-11-27): https://www.prnewswire.com/news-releases/mouthpad-the-first-ever-tongue-trackpad-launches-to-the-public-alongside-new-wearable-vox-302832412.html

#### Tyromotion GmbH (AT) - fit 2/5
- **Segment / devices:** Rehab robotics / sensor devices - Amadeo, Diego, Pablo, Myro
- **Stage:** [AE] commercial; no 2026 news found
- **Trials:** NCT03294187 (Zurich, Pablo daily-life)
- **Known endpoints:** MAL-14 amount of use, FMA-UE, ARAT, EQ-5D-5L
- **Current outcome approach:** Device assessment modules
- **NeuroMetric use case [INF]:** EU partner for home assessment
- **Target roles:** Clinical/Research lead
- **Public contact route:** company website contact page (not re-verified)
- **Funding:** [UNR]
- **Uncertainties:** Status not verified
- **Evidence:** V (registry); AE. Sources (accessed 2026-11-27): https://clinicaltrials.gov/study/NCT03294187

#### AbleNet, Inc. (US) - fit 2/5
- **Segment / devices:** Switches / AT access - Switches, mounts, AAC accessories [PK]
- **Stage:** Commercial; in litigation with Tobii Dynavox [CC]
- **Trials:** none found
- **Known endpoints:** n/a
- **Current outcome approach:** n/a
- **NeuroMetric use case [INF]:** Low
- **Target roles:** Product lead
- **Public contact route:** ablenetinc.com contact page
- **Funding:** [PK] private
- **Uncertainties:** Low evidence spend
- **Evidence:** CC; PK. Sources (accessed 2026-11-27): https://news.cision.com/dynavox-group/r/dynavox-group-interim-report-second-quarter-2026,c4376655

#### Glassouse (TR/US [PK]) - fit 1/5
- **Segment / devices:** Head-mouse AT - Glassouse head mouse [PK]
- **Stage:** [PK]
- **Trials:** none found
- **Known endpoints:** n/a
- **Current outcome approach:** n/a
- **NeuroMetric use case [INF]:** Low
- **Target roles:** CEO
- **Public contact route:** company website (not re-verified)
- **Funding:** [UNR]
- **Uncertainties:** Not researched beyond prior knowledge
- **Evidence:** PK. Sources (accessed 2026-11-27): none (prior knowledge only)

#### Quha Oy (FI) - fit 1/5
- **Segment / devices:** Head/gyro mouse AT - Quha Zono [PK]
- **Stage:** [PK]
- **Trials:** none found
- **Known endpoints:** n/a
- **Current outcome approach:** n/a
- **NeuroMetric use case [INF]:** Low
- **Target roles:** CEO
- **Public contact route:** company website (not re-verified)
- **Funding:** [UNR]
- **Uncertainties:** Not researched beyond prior knowledge
- **Evidence:** PK. Sources (accessed 2026-11-27): none (prior knowledge only)

#### Merge Labs (US) - fit 1/5
- **Segment / devices:** Non-invasive BCI (ultrasound, preclinical) - Ultrasound/molecular interface (Forest-1 imaging system reported)
- **Stage:** Preclinical; USD 252M seed Jan 2026 (OpenAI among investors)
- **Trials:** none
- **Known endpoints:** n/a
- **Current outcome approach:** n/a
- **NeuroMetric use case [INF]:** Too early
- **Target roles:** n/a
- **Public contact route:** company website
- **Funding:** [CC] USD 252M seed
- **Uncertainties:** No clinical program
- **Evidence:** CC. Sources (accessed 2026-11-27): https://www.techcrunch.com/2026/01/15/openai-invests-in-sam-altmans-brain-computer-interface-startup-merge-labs/; https://openai.com/blog/investing-in-merge-labs

#### Subsense (US) - fit 1/5
- **Segment / devices:** Non-surgical nanoparticle BCI - Intranasal nanoparticle interface
- **Stage:** Preclinical (mouse studies)
- **Trials:** none
- **Known endpoints:** n/a
- **Current outcome approach:** n/a
- **NeuroMetric use case [INF]:** Too early
- **Target roles:** n/a
- **Public contact route:** company website
- **Funding:** [CC] USD 17M seed (USD 27M also reported)
- **Uncertainties:** Preclinical
- **Evidence:** CC. Sources (accessed 2026-11-27): https://neurotechreports.com/pages/subsense-nanoparticles.html

#### Forest Neurotech (US) - fit 1/5
- **Segment / devices:** Nonprofit BCI research org (ultrasound) - Ultrasound neurotech research
- **Stage:** Research FRO; Merge Labs reported spin-out
- **Trials:** none
- **Known endpoints:** n/a
- **Current outcome approach:** n/a
- **NeuroMetric use case [INF]:** Too early
- **Target roles:** n/a
- **Public contact route:** convergentresearch.org/ecosystem/forest
- **Funding:** [AE] ~USD 14M philanthropic
- **Uncertainties:** Not a buyer
- **Evidence:** AE. Sources (accessed 2026-11-27): https://www.convergentresearch.org/ecosystem/forest

### Standards / partner (not a customer)

#### Implantable BCI Collaborative Community (iBCI-CC) (US) - fit n/a/5
- **Segment / devices:** Standards body (FDA-participating collaborative community) - n/a
- **Stage:** Active; working groups incl. clinical trial endpoints and user priorities; ASNR 2026 workshop on defining success
- **Trials:** n/a
- **Known endpoints:** n/a
- **Current outcome approach:** Consensus on endpoints/COAs
- **NeuroMetric use case [INF]:** Not a customer; venue to align NeuroMetric measures with emerging consensus
- **Target roles:** Working group chairs (via public membership route)
- **Public contact route:** iBCI-CC website / membership page
- **Funding:** n/a
- **Uncertainties:** Membership terms
- **Evidence:** CC. Sources (accessed 2026-11-27): https://gcp.medtechdive.com/news/mass-general-fda-brain-computer-interface-group/710112; https://www.asnr.com/asnr2026/pre-conference-workshop

## 6. Excluded organizations

| Organization | Segment | Reason | Source |
|---|---|---|---|
| Neurable | Consumer EEG headphones | Consumer focus/wellness | https://www.businesswire.com/news/home/20251219993709/en |
| Fisher Wallace Laboratories | Cranial electrotherapy (psychiatric) | Psychiatric indications; regulatory status unresolved | https://clinicaltrials.gov/study/NCT05384041 |
| Wisear (acquired by Naqi Logix, Jan 2026) | Earbud neural interface | Consumer/XR interface; revisit only if Naqi pursues medical AT | https://wearable-technologies.com/news/naqi-logix-acquires-neurotech-startup-wisear |
| Helius Medical Technologies (now Solana Company) | Former PoNS developer | Exited neurotech; PoNS now at Bioness | https://www.tipranks.com/news/the-fly/helius-medical-announces-corporate-name-change-to-solana-company-thefly |
| Science Corporation | Implantable BCI (vision) | PRIMA retinal implant (CE mark July 2026) - vision restoration; outside motor/communication scope | https://www.massdevice.com/science-corp-launches-prima-bci-europe/ |
| Motif Neurotech | Implantable neuromodulation (depression) | DOT for treatment-resistant depression (NCT07594483, NCT07684794) - psychiatric, outside scope | https://clinicaltrials.gov/study/NCT07594483 |
| Kernel | Non-invasive neuroimaging (TD-fNIRS) | Biomarker/research headset; no device-outcome evidence need in scope | https://clinicaltrials.gov/study/NCT06002100 |
| NeuroOne Medical Technologies | sEEG / ablation (epilepsy) | Diagnostic/ablation, no home functional rehab | https://clinicaltrials.gov/study/NCT07546253 |

## 7. Cross-cutting observations [INF unless labelled]

1. **Registered BCI endpoints are still safety-first.** Synchron, Neuralink (except CONVOY), Paradromics and BrainGate register
   device/procedure AEs as primary endpoints [V registry]. Functional and real-world-use measures appear as secondary or "other"
   outcomes: Neuralink CONVOY (PIADS, ATD-PA) [V], Synchron INTENT ("Synchron BCI use up to 1 year") [V], Neuracle NEO and StairMed
   (monthly usage time, caregiver burden) [V], BCIFlex (dIADL, PIADS) [V], UMC Utrecht (QUEST, PIADS, NASA-TLX, home-use software
   validation) [V]. The move to pivotal studies is when sponsors must choose functional endpoints, and that is NeuroMetric's window.
2. **Care-partner burden is entering protocols.** The Zarit Burden Interview appears in Kandu's RWE study (NCT07147881) and
   Cognixion's ALS trial (NCT07871071); StairMed lists "caregiver burden" (NCT06829212) [V].
3. **A standard is being built in public.** Shirley Ryan AbilityLab with Neuralink as collaborator is developing a digital-independence
   index combining PerfOs, ClinROs and PROs (NCT07407725, primary completion est. 2026-12) [V]. The iBCI Collaborative Community has
   endpoint and user-priority working groups [CC] https://gcp.medtechdive.com/news/mass-general-fda-brain-computer-interface-group/710112 ,
   and FDA/NIH held a 2024 workshop on implanted-BCI COAs [V] https://fda.gov/media/182567/download. NeuroMetric should align
   with, and ideally contribute to, these rather than introduce a proprietary scale.
4. **Coverage pathway for implanted BCIs is unsettled.** Health Affairs commentary argues a Medicare pathway still needs to be built
   [AE] https://www.healthaffairs.org/content/forefront/unlocking-future-medicare-and-brain-computer-interfaces. A report that CMS
   paused new TCET candidates was not verified against a CMS primary source [UNR]. HEOR roles at BCI companies may not exist yet;
   ask who owns payer evidence.
5. **China.** Neuracle received NMPA registration (2026-03-13) and an insurance code within 48 hours [CC]; several Chinese sponsors
   already register usage time and caregiver burden. Data-export and personal-information rules make them Tier 3 for a US/EU
   startup, but their protocols are useful design references.

## 8. Major uncertainties for the whole database

- Contact domains marked "not re-verified" and all [PK] corporate statuses need checking before outreach.
- Several registry records are stale (NCT06140706, NCT07147881); real study status must be asked, not assumed.
- Funding figures for private companies come from press or aggregators and may be incomplete.
- Fit scores assume NeuroMetric can deliver read-only integrations and remote assessments of acceptable validity; that is itself
  a hypothesis to test in discovery interviews (see `interview_guides.md`) [HYP].
