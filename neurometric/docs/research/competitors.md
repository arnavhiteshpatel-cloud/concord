# NeuroMetric competitive landscape (BCI / AT / home neuromodulation outcome evidence)

Prepared: 2026-11-27. Follows `CONVENTIONS.md` labels: [V] verified this session against a primary
source, [CC] company claim, [RF] peer-reviewed research, [AE] analyst/third-party/press, [INF] NeuroMetric
inference, [HYP] hypothesis, [PK] prior knowledge not re-verified, [UNR] unresolved.
All web sources accessed 2026-11-27 unless stated. Companion files: `competitors.csv`, `comparable_pricing.md`.

**Method and limits.** ClinicalTrials.gov API v2 queries (primary, [V]) for BCI-related studies and BCI sponsor
names; PubMed E-utilities (primary, [RF]); company and registry pages fetched directly; web search summaries
(press/trade coverage, labelled [AE] unless the primary page was opened). The session's web-search quota was
exhausted before every lead was closed; items not re-checked are labelled [PK] or [UNR]. Many trade-press
items (MassDevice, MDDI, Business Wire) returned HTTP 403 on direct fetch, so their content is [AE] via search
summaries, not [V].

**Bottom line up front** [INF]:
1. The market is not empty. The most direct competitor is not a software vendor but an academic instrument
   effort co-sponsored by the largest iBCI sponsor: Shirley Ryan AbilityLab's Digital Assessment Interface
   (DAI), NCT07407725, collaborator Neuralink, recruiting since 2026-01-08, primary completion est. 2026-12.
2. The second-most direct pressure is sponsor in-house infrastructure (Neuralink usage telemetry and Webgrid
   BPS, Synchron's Apple BCI-HID integration, Paradromics' SONIC and outcome-framework blog).
3. Large eCOA platforms (Signant+Ametris, Clario/Thermo Fisher, Medidata, Medable, YPrime, Suvoda, Castor)
   have Part 11 infrastructure, wearables and scale, but no BCI- or AT-specific task batteries or input-device
   telemetry found. They are partial overlaps and a likely "fast follower" risk if BCI volume grows.
4. The US implantable motor/communication BCI sponsor base is too concentrated (3 industry sponsors with
   active US motor/communication IDE studies today; roughly 5 to 8 plausible by 2028) to support a
   standalone iBCI-only business. A viable business must be input-agnostic (AT, non-invasive BCI, home
   neuromodulation) and/or partly grant- and academic-funded.
5. Recommended niche (section S4): neutral, cross-device home-use "digital independence" evidence
   (standardized task battery plus passive OS/app-level use telemetry plus care-partner burden), delivered as
   a Part 11-ready evidence package that implements the emerging consensus COAs rather than competing with
   them, first sold to non-dominant iBCI sponsors, non-invasive BCI makers and academic iBCI programs.

---

## Part A. BCI/AT-specific outcome instruments and standard-setters (most direct)

### A1. Shirley Ryan AbilityLab (SRAL) Digital Assessment Interface (DAI), NCT07407725
- **What it is** [V] (https://clinicaltrials.gov/study/NCT07407725 ; API record https://clinicaltrials.gov/api/v2/studies/NCT07407725):
  "Development of a Clinical Outcome Assessment for Assistive Technologies and Brain-Computer-Interfaces".
  Lead sponsor Shirley Ryan AbilityLab; **collaborator Neuralink Corp**; PI Arun Jayaraman (Max Nader Center
  for Rehabilitation Technologies & Outcomes Research). Status RECRUITING; start 2026-01-08 (actual);
  primary completion 2026-12 (est.); completion 2027-06 (est.); enrollment 60 (est.); last update 2026-11-06.
- **Functionality** [V]: a customized DAI simulating digital activities of daily living (dADLs: online
  shopping, texting, gaming, booking appointments); metrics per motor primitive (click, scroll, type,
  click-and-drag): click accuracy, time to target, errors, cursor trajectory, words per minute, % correct
  characters. A separate Digital Training Interface (8 practice levels). In-clinic and at-home sessions.
- **Input-device support** [V]: Tobii Dynavox PCEye 5 eye tracker, Jouse+ mouth joystick, Emotiv EPOC X EEG
  headset, Neuralink N1 implant, personal AT, voice control. This is explicitly cross-device.
- **Psychometrics** [V]: secondary objectives are validity, responsiveness, reliability, floor/ceiling effects
  "globally and across different devices and impairment levels", plus normative healthy-control reference.
- **Composite index** [V]: performance outcomes + clinician-reported + patient-reported (NASA-TLX patient and
  clinician, SUS patient and clinician, modified COPM, PIADS, WHOQOL-BREF, IRF-PAI Section GG, ALSFRS-R,
  ISNCSCI, ECAS).
- **Not in scope (as registered)** [V/INF]: no passive real-world use telemetry outcome, no care-partner
  burden measure, no stated commercial distribution or Part 11 platform. Cohorts: healthy controls, ALS/SCI with
  implanted BCI, ALS/SCI without implant (single site, Chicago).
- **Overlap: DIRECT** on functional task testing, cross-device benchmarking and psychometrics. **Threat: HIGH**
  [INF]: if published and adopted by iBCI-CC/FDA, it becomes the reference instrument, and its co-development
  with Neuralink gives it the largest implanted cohort in the field. Possible complement: NeuroMetric could
  offer to host/administer the DAI (or a licensed equivalent) at home and across sites [HYP].

### A2. Mount Sinai Digital IADL scale / "BCI Functional Outcome Measures Group"
- [RF] Sawyer A, Brannigan J, Spielman L, BCI Functional Outcome Measures Group, Putrino D, Fry A.
  "Development of a novel clinical outcome assessment: digital instrumental activities of daily living."
  EBioMedicine 2025;116:105732. PMID 40424668, doi:10.1016/j.ebiom.2025.105732.
  https://pubmed.ncbi.nlm.nih.gov/40424668/ . Adam Fry is listed as Synchron in a related paper (below).
- [CC] Paradromics' commentary says the scale is "still in early development and requires additional testing
  and validation" and that the authors suggest CMS CARE-scale-style scoring
  (https://www.paradromics.com/blog/measuring-what-matters-in-bci , 2025-11-25, page fetched).
- **Overlap: PARTIAL** (instrument, not platform). **Threat: MED-HIGH** [INF]: defines *what* will be
  measured; an instrument is free to use in academia and could be implemented by any eCOA vendor. Better
  treated as a partner/standard to implement.

### A3. iBCI-CC Clinical Study Endpoints Workgroup, BCI Society COA workshops, FDA/NIH COA workshop
- [V] iBCI Collaborative Community (Mass General Brigham, FDA-participating) lists seven workgroups including
  "Clinical Study Endpoints" and "Payor Interactions and Device Categorization"; 3rd annual meeting Oct 16
  (2026), Washington DC (https://ibci-cc.org/).
- [RF] Sawyer A, Welle CG, ... Angle MR (Paradromics), Herrmann D, McMullen D (Neuralink), Franklin R
  (Blackrock), Oxley T (Synchron), Dister J (Precision), Hochberg LR. "BCI clinical trial design considerations
  and COAs in pivotal studies: summary of the 11th BCI Society meeting 2025 workshop." J Neural Eng 2026 Sep
  11;23(5). PMID 42648341, doi:10.1088/1741-2552/ae9eee. Key text: challenges are "patient heterogeneity, the
  lack of widely validated and fit-for-purpose COAs, and the need to capture meaningful outcomes in home and
  daily-life environments"; aims for COAs "conducive to regulatory approval and reimbursement".
- [RF] Sawyer A et al. "Building consensus on COAs for BCI devices" (10th BCI Society meeting 2023 workshop).
  J Neural Eng 2025;22(1). PMID 39288794. Co-authors include Smartbox (AAC maker) and Blackrock, Synchron.
- [AE] FDA/NIH Joint Workshop "Developing Implanted BCI Clinical Outcome Assessments to Demonstrate Benefit",
  Sept 19-20, 2024, docket FDA-2024-N-2976 (https://www.fda.gov/news-events/fda-meetings-conferences-and-workshops/public-workshop-food-and-drug-administrationnational-institutes-health-joint-workshop-developing ; via search summary, prior cycle).
- [RF] Dohle E et al. Adv Sci 2025 (PMID 40697162): implantable motor BCI literature dominated by engineering
  outcomes; only a minority report clinical outcomes (17.9% per search summary; figure not re-read in full text [UNR]).
- **Role:** standard-setter, not a competitor. **Overlap: COMPLEMENT** [INF]. All four leading iBCI sponsors
  co-author the pivotal-COA paper, i.e., the field is converging pre-competitively on *instruments*; the open
  question is who *operationalizes* them (home administration, telemetry, audit trail, evidence packaging).

### A4. BCI Pioneers Coalition (user advocacy)
- [AE] Founded by BCI user Ian Burkhart; aims for companies, clinicians and regulators to hear directly from
  trial participants (Battelle 2026-05-11, https://www.battelle.org/insights/newsroom/news-details/2026/05/11/what-it-s-like-to-live-with-an-experimental-brain-implant ; MIT Tech Review 2026-11-13 https://technologyreview.com/2026/11/13/1148474/more-autonomy-fewer-ndas-volunteers-have-new-requests-for-brain-implant-trials ; search summaries).
- **Overlap: COMPLEMENT** (patient-priority input; potential advisory partner) [INF].

---

## Part B. Sponsor internal infrastructure (as publicly described)

### B1. Neuralink
- **Trials** [V] (ClinicalTrials.gov API): PRIME NCT06429735 (US, n=15 est., active not recruiting, sites
  Barrow and U Miami; primary outcomes AEs only); CONVOY-type "Control of Assistive Devices" NCT06710626
  (n=3, enrolling by invitation); VOICE NCT07224256 (communication, UTSW, n=6, recruiting; secondary
  "preliminary efficacy of N1 implant"); new EFS NCT07929792 (SCI/ALS/chronic stroke, U Miami, n=10,
  start 2026-11 est.); plus CAN-PRIME, GB-PRIME, UAE-PRIME. Collaborator on SRAL DAI (A1).
- **Scale** [AE]: 21 participants enrolled worldwide (Jan 2026, multiple press reports, e.g.
  https://gvwire.com/2026/01/28/elon-musks-neuralink-says-it-has-21-participants-enrolled-in-trials/);
  26-27 by mid-2026 (secondary blogs, [UNR] exact count).
- **Internal telemetry** [AE]: company blog posts report independent use of ~6.5 h/day and cumulative
  4,900+ h (one-year update), later 50,000+ cumulative hours and an 11.32 BPS Webgrid record from a "foundation
  model" (press summaries of neuralink.com/blog; https://neuralink.com/blog/prime-study-progress-update-user-experience/ 2024-05-08 [PK content]).
  Implication [INF]: Neuralink already captures passive use telemetry and a task benchmark in-house.
- **Webgrid** [V] (https://neuralink.com/webgrid): public browser game; BPS derived from net correct targets per
  minute, grid size and number of click types; page states trial participants exceeded 10 BPS. Third-party
  formula reconstruction (https://github.com/ofou/webgrid_eval) [AE].
- **Payer/coding** [V]: CMS ICD-10 Coordination & Maintenance Committee, Sept 15-16, 2026, Topic #12
  "Insertion of Brain Computer Interface Device" (Neuralink N1; requested implementation April 1, 2027;
  requestor "intends to submit a New Technology Add-on Payment (NTAP) application"; N1 Breakthrough
  designations 2020-07-23 and 2025-04-30) (https://www.cms.gov/files/document/fall-2026-icd-10-pcs-update-materials.pdf).
  Implication [INF]: the leading sponsor is already building payer evidence (NTAP needs "substantial clinical
  improvement" evidence) with its own resources and consultants.
- **Overlap: DIRECT** (in-house telemetry, task benchmark, COA co-development). **Threat: HIGH** as a
  non-buyer and standard-setter; low probability Neuralink buys neutral measurement except where FDA/CMS
  want independence [INF].

### B2. Synchron
- **Trials** [V]: COMMAND EFS NCT05035823 (US, n=6, active not recruiting); INTENT EFS NCT07543367 (US, n=10,
  start 2026-05-07, sites Mayo, Buffalo, Mount Sinai, UPMC, UTSW; outcomes: device SAEs, vessel patency,
  migration only); FOCUS-AUS NCT07533903 ("Functional Outcomes and Control Using Synchron BCI", n=10,
  Melbourne; outcomes safety only despite title); Canada version NCT07446114 TERMINATED (n=1).
- **Pause** [AE]: Nov 12-13, 2026 reports (WIRED via MDDI, Medical Daily) that Synchron voluntarily paused
  enrollment in second-generation Stentrode trials over a lead performance issue, not FDA-mandated, and is
  overhauling the platform (https://www.medicaldaily.com/synchron-pauses-wireless-brain-implant-trials-481309 ;
  https://www.mddionline.com/neurological/synchron-s-bci-trial-pause-what-went-wrong-with-stentrode ; 403 on
  direct fetch). Pivotal timing therefore [UNR].
- **Infrastructure** [CC]: native integration with Apple's BCI Human Interface Device protocol (May 2025)
  and thought-controlled iPad demo (Aug 2025) (https://www.businesswire.com/news/home/20250513927084/en ;
  https://businesswire.com/news/home/20250804537175/en ; via search summaries). Chiral "cognitive AI" brain
  foundation model roadmap on NVIDIA Holoscan, trained on ~20 patient-years of data (Mar 2025)
  (https://www.businesswire.com/news/home/20250319964709/en ; search summary).
- **Funding** [AE]: $200M Series D, total ~$345M (MassDevice via search summary).
- Implication [INF]: OS-level HID integration means BCI input can surface through standard accessibility
  pathways, which is a technical opening for input-agnostic telemetry, but Apple controls what third parties
  can log.
- **Overlap: PARTIAL** (in-house data, no published functional COA in registrations). **Threat: MED**; also a
  plausible **customer** once enrollment resumes [INF].

### B3. Paradromics
- **Trial** [V]: Connect-One EFS NCT07357428 (communication; UC Davis, MGH, U Michigan; n=2 registered est.;
  primary outcome device-related AEs). [AE] IDE granted Nov 2025; first implant at U Michigan announced
  2026-06-17 (https://www.businesswire.com/news/home/20260617963732/en/ ; search summary); ~10 patients planned [AE].
- **Benchmarking** [V]: SONIC open benchmark (sheep auditory cortex; mutual-information ITR; 200+ bps at 56 ms,
  100+ bps at 11 ms; "both engineering and clinical tests are important"), blog 2025-10-03
  (https://www.paradromics.com/blog/bci-benchmarking).
- **Outcome thinking** [V]: "Measuring what matters in BCI" (2025-11-25) argues for graded independence plus
  performance scales enabling cross-device comparison, explicitly tied to payer adoption; no in-house outcome
  tool or partner named.
- **Ecosystem** [AE]: APEX academic partnership program (Mar 2026), e.g., Stanford.
- **Overlap: PARTIAL**. **Threat: LOW-MED as competitor; HIGH relevance as early customer** [INF]: publicly
  wants cross-device graded outcomes but has not announced a tool.

### B4. Precision Neuroscience
- [AE] Layer 7 cortical interface 510(k)-cleared for up to 30 days (2025); July 2026 claim of real-time computer
  control without penetrating the brain; $250M Series D; fully implanted trial "expected 2026" (Freethink
  interview). [V-negative] No Precision Neuroscience BCI study found on ClinicalTrials.gov sponsor search
  (2026-11-27). **Overlap: NONE today; prospective customer** [INF].

### B5. Blackrock Neurotech
- [V] Collaborator (array supplier) on JHU INTENT NCT07521930 (n=5, start 2027-01 est.; outcomes include
  "number of participants achieving BCI control of assistive devices"). Arrays underpin most academic iBCI
  programs (BrainGate2 NCT00912041, Pitt NCT01894802, Caltech, UC Davis) [V for trials; supplier role PK].
- [AE] In-home system with University of Pittsburgh (older PR Newswire release; content not loaded).
- **Overlap: NONE/COMPLEMENT**; possible channel to academic iBCI programs [INF].

### B6. Cognixion (non-invasive EEG BCI + AR AAC)
- [V] NCT07871071 "Within-Subject Longitudinal Evaluation of the Cognixion ONE BCI Speech Generating Device in
  ALS" (n=30, start 2026-11-15 est., NIDCD collaborator). **Primary outcome: voluntary daily use time per input
  modality.** Secondary: communication rate, selection accuracy, ITR, modality preference, SUS, NASA-TLX,
  ALSSQOL-SF, **Zarit Burden Interview (care-partner burden)**, conversation metrics, ALSFRS-R.
  Also NCT06810219 and NCT07209943 (AR BCI longitudinal).
- Implication [INF]: a small sponsor is running almost exactly NeuroMetric's endpoint stack (home use time
  per input modality + functional rate + caregiver burden) in-house. This both validates demand and shows the
  build-it-yourself alternative.
- **Overlap: PARTIAL (in-house)**. **Threat: MED**; plausible customer/partner.

### B7. Other BCI/neurotech developers (sponsor universe for the concentration analysis)
| Company | Status relevant to US motor/communication iBCI 2026-28 | Label |
|---|---|---|
| Echo Neurotechnologies | Speech BCI; ~$50M Series A (Jan 2025, a16z); no registered trial found | [AE]/[UNR] |
| Merge Labs | ~$252M seed (Jan 2026), ultrasound/molecular approach; preclinical | [AE] (https://openai.com/index/investing-in-merge-labs/ via search) |
| Science Corp | PRIMA retinal (vision) trials; partner ecosystem (Neurosoft) | [V] CT.gov NCT04676854; [AE] |
| CorTec | Collaborator on Mayo epilepsy studies (NCT05439655, NCT06898138); Brain Interchange stroke rehab | [V]/[PK] |
| Axoft | Studies in Panama (NCT06673264 completed; NCT07953036 not yet recruiting) | [V] |
| Motif Neurotech | Depression stimulation (NCT07594483 recruiting US) - neuromodulation, not motor | [V] |
| Neurosoft Bioelectronics | $7.5M seed (May 2026), Europe | [AE] |
| Neuracle | China trials (NCT05920174, NCT06990412) | [V] |
| Phantom Neuro | Peripheral EMG implant (NCT07325708, Australia) | [V] |
| Onward Medical | ARC-IM (US, BP) and ARC-BCI (Europe, PK) | [V]/[PK] |

---

## Part C. BCI research and benchmarking software

| Tool | Functionality | Input support | Functional outcomes? | Overlap | Labels |
|---|---|---|---|---|---|
| **BCI2000** | Real-time acquisition, processing, feedback, storage; maintainer Peter Brunner (WashU); open source; NIH U24-NS109103, R01-EB026439; research not clinical use; Windows 10+ | EEG, ECoG, EMG, eye trackers, motion sensors | No (engineering/experimental) | COMPLEMENT (possible data source/integration) | [V] https://www.braininitiative.org/toolmakers/resources/bci2000/ |
| **BrainGate task software** | Cursor/typing tasks (e.g., radial and grid tasks), home-based research sessions in BrainGate2 | Intracortical arrays | Research performance metrics; not a commercial COA | COMPLEMENT | [PK]; BrainGate2 trials [V] NCT00912041, NCT06094205, NCT06511934, NCT07918768 |
| **FALCON** | Few-shot decoder robustness benchmark; 5 human/NHP datasets; EvalAI leaderboard, open indefinitely; SNEL (Pandarinath), NeurIPS 2024 | Intracortical | No (decoder consistency) | NONE/COMPLEMENT | [V] https://snel-repo.github.io/falcon/ ; [RF] NeurIPS 2024 |
| **MOABB** | Open EEG-BCI algorithm benchmark, BSD license, many public datasets | EEG | No | NONE | [RF] Jayaram & Barachant, J Neural Eng 2018; [AE] https://github.com/NeuroTechX/moabb |
| **Neuralink Webgrid** | Public BPS click-grid game | Any pointer | Single performance metric, not a COA | PARTIAL (task benchmark) | [V] https://neuralink.com/webgrid |
| **Paradromics SONIC** | Preclinical ITR benchmark | Implant (sheep) | No | NONE | [V] https://www.paradromics.com/blog/bci-benchmarking |

Implication [INF]: engineering benchmarks are open and free; none measures function in daily life, so
"cross-device benchmarking" alone is a weak commercial niche (free substitutes, academic norms), whereas a
*functional* cross-device benchmark is contested by SRAL's DAI.

---

## Part D. AT assessment, AAC logging and rehab measurement

### D1. Compass (Koester Performance Research)
- [V] https://kpronline.com/compass : computer-access assessment for AT professionals; 8 skill tests across
  pointing, text entry and switch use; speed and accuracy; configurable for alternative keyboards, pointing
  devices, mice, switches; reports compare tests; tracks change over time; Windows/Mac; 5 languages; claims
  "measurement validity" with publications page (not reviewed).
- [V] Price: **$179 per perpetual license; 5-pack $720**; volume discounts 20-40%
  (https://kpronline.com/purchase-compass).
- **Overlap: DIRECT** for clinic-based functional task testing of access methods (closest commercial analog of
  a cross-device performance battery), but no BCI support, no telemetry, no trial infrastructure. **Threat:
  LOW-MED** (sets a very low price anchor for clinic AT assessment) [INF].

### D2. Tobii Dynavox (Dynavox Group, Nasdaq Stockholm: DYVOX)
- [V] Gaze Viewer: eye-gaze assessment recording what was seen, order, fixations, heat maps; standalone or
  bundled; no price shown on page (https://us.tobiidynavox.com/products/gaze-viewer).
- [AE] TD Snap optional data tracking of button and modeling usage, reports at mytobiidynavox.com (support
  article via search summary).
- [CC] Q3 2026 revenue SEK 685M (+13%), Q2 SEK 670M, Q1 SEK 588M (Cision releases via search summary,
  e.g., https://news.cision.com/dynavox-group/r/dynavox-group-interim-report-second-quarter-2026,c4376655).
- [V] Its PCEye 5 is a comparator device in SRAL's DAI study.
- **Overlap: PARTIAL** (usage logging and gaze assessment within its own ecosystem only). **Threat: MED**
  (could extend analytics; owns AAC install base) and plausible **customer** (evidence for payers) [INF].

### D3. PRC-Saltillo (LAMP WFL, TouchChat, Accent/NovaChat/Via; Realize Language)
- [V] Device data logging records language usage per person; export via LogFile; privacy password
  (https://documentation.prc-saltillo.com/docs/language-development-data-logging-3).
- [V] Realize Language: online service that graphs device usage data, dashboards, progress over time,
  shareable reports; supports Accent, NovaChat, Via, LAMP WFL, TouchChat; 30-day free trial; **no price
  listed** (https://www.realizelanguage.com/).
- [PK] Logs historically use the LAM (Language Activity Monitoring) format.
- **Overlap: PARTIAL** (real-world use telemetry, single vendor, communication only). **Threat: LOW-MED** [INF].

### D4. Kinarm (BKIN Technologies)
- [RF] Robotic Kinarm Standard Tests quantify upper-limb sensory, motor and cognitive function in stroke, ALS,
  concussion, MS; test-retest thresholds published (J NeuroEng Rehabil 2020, doi:10.1186/s12984-020-00713-2).
  Pricing not found [UNR].
- **Overlap: PARTIAL** (functional task testing for rehab tech; in-lab hardware). **Threat: LOW** [INF].

### D5. Neurolutions IpsiHand (comparator for rehab BCI evidence)
- [AE] CMS established a HCPCS Level II code and DME classification for IpsiHand (BCI stroke rehab) (Business
  Wire 2024-03-12 via search; code E0738 per syndicated copy [UNR]). Not a competitor; a precedent that a BCI
  can reach payer coding, and a possible rehab-tech customer [INF].

---

## Part E. eCOA / ePRO / EDC / DCT platforms

Common pattern [INF]: all offer Part 11-oriented audit trails, ePRO/ClinRO, site and patient apps, and
increasingly AI agents and wearables; none was found to offer BCI/AT input-device-aware task batteries,
access-method telemetry, or AT-specific psychometric content. Sold per study to pharma; device/medtech
early-feasibility studies with n=2-15 are small for them.

### E1. Medidata (Dassault Systèmes)
- [AE] Medidata Sensors (Sensor Cloud): 50+ validated measures/algorithms, pairs sensor and eCOA data, offers
  FDA 510(k)-cleared sensors for some areas (2026 fact sheets via search summary,
  https://www.medidata.com/wp-content/uploads/2026/07/Medidata-Sensors-Fact-Sheet-Jun-26_JPN.pdf).
  Medidata Plus AI layer (July 2026, HIT Consultant). Everest Group eCOA PEAK Matrix leader 2025 [CC].
- [PK] Acquired by Dassault 2019 (~$5.8B); Rave EDC, eCOA, myMedidata; Part 11 compliance claimed.
- **Overlap: PARTIAL**; **Threat: MED** (platform breadth; would need BCI content) [INF].

### E2. Medable
- [CC] eCOA deployed in ~400 trials, 70 countries; PI Summary Agent for eCOA oversight (2026-01-28,
  https://www.businesswire.com/news/home/20260128381794/en/ via search). [AE] Total funding ~$507M; $2.1B
  valuation (Oct 2021); 2024 revenue est. $73.5M (ZoomInfo via Contrary Research,
  https://research.contrary.com/company/medable , fetched). Pricing undisclosed.
- **Overlap: PARTIAL**; **Threat: MED-LOW** [INF].

### E3. Signant Health (+ Ametris, formerly ActiGraph)
- [V] Acquired Ametris (formerly ActiGraph) 2026-05-14; combines eCOA with wearable-derived digital measures
  of physical activity and function; plans unified data flows, composite outcome measures, AI; Signant cites
  600+ sponsors/CROs and all top-20 pharma; terms undisclosed
  (https://signanthealth.com/company/news/signant-health-acquires-ametris).
- [AE] ActiGraph rebranded Ametris June 2025; device brands (LEAP, CentrePoint Insight Watch, wGT3X, ActiLife)
  kept; positioned as developer of qualified clinical outcome measures (PharmaVoice/Clinical Leader via search).
- [PK] Signant TrialMax eCOA, rater training (strong in CNS scales).
- **Overlap: PARTIAL** (eCOA + home telemetry + digital measure science, CNS focus). **Threat: MED-HIGH** as the
  incumbent most able to add a BCI/AT module quickly [INF].

### E4. Clario (Thermo Fisher Scientific)
- [AE] Thermo Fisher completed acquisition 2026-03-24 for $8.875B cash plus earn-outs (Applied Clinical
  Trials; announcement 2025-10-29). Offerings: eCOA, cardiac/respiratory, imaging, wearables. Thermo also owns
  PPD/Evidera (HEOR/RWE) (see G1).
- **Overlap: PARTIAL**. **Threat: MED** (eCOA + HEOR under one parent; low interest in n<20 device EFS) [INF].

### E5. Castor
- [CC] Unified EDC, eCOA/ePRO, eConsent, CDMS, Catalyst AI; Part 11, ISO 27001/9001, ICH GCP badges
  (https://www.castoredc.com/plan/pro/ , fetched); 300+ industry eCOA studies and C-Path eCOA Consortium
  member (2026-03-12). [CC] Free "Small Study" tier: 1 institute, 12 months, up to 125 inclusions, max 5 free
  studies per academic institute (help center via search summary; https://helpdesk.castoredc.com/when-is-my-study-free-of-charge).
- **Overlap: PARTIAL** (likely default for academic iBCI groups). **Threat: MED-LOW** [INF].

### E6. YPrime
- [AE] eCOA + IRT; PE investment from Flexpoint Ford (2019); acquired Tryl (2022); eCOA Participant Hub launch
  2026-04-07 (GlobeNewswire via search). **Overlap: PARTIAL; Threat: LOW** [INF].

### E7. Suvoda (+ Greenphire)
- [AE] Merged with Greenphire 2025; RTSM/IRT, eCOA, eConsent, payments, travel on one platform; AI (Sofia)
  (Clinical Leader 2026-11-02 via search). **Overlap: PARTIAL (trial ops); Threat: LOW** [INF].

### E8. OpenClinica and REDCap (academic defaults)
- [V] OpenClinica public pricing: Launch $750/mo; Core $3,000/mo per study (12-mo); Advanced $3,750/mo per study;
  claims Part 11, HIPAA, GDPR, SOC 2, ISO 27001 (https://www.openclinica.com/pricing).
- [PK] REDCap is free to consortium member institutions and widely used by academic BCI groups.
- **Overlap: PARTIAL (data capture only); Threat: LOW**, but they set the academic price floor [INF].

---

## Part F. Digital biomarker / DHT / RWE companies

| Company | Product and focus | Input/BCI relevance | Labels | Overlap / threat |
|---|---|---|---|---|
| **Koneksa** | Sensor-agnostic wearable + ePRO platform; 30+ validated measures claimed; Lodestar submission software (June 2026); KH007 Parkinson's study with Merck/Regeneron met primary compliance endpoint (Sept 2026); MJFF, Verily partners; Beacon Biosignals home-EEG partnership (2023) | Wearables; no AT/BCI | [CC] https://www.koneksahealth.com/ (fetched); [AE] $45M Series C (MobiHealthNews) | Partial / MED-LOW |
| **Ametris (ActiGraph)** | Wearable digital measures; now inside Signant | Actigraphy | see E3 | Partial / (via Signant) |
| **Evidation** | Direct-to-participant wearable + survey cohorts; RWE; CEO Leslie Oley Wilberforce (Mar 2025) | Consumer wearables | [CC]/[AE] https://evidation.com/ ; funding [PK] (>$300M) | Partial (RWE model) / LOW |
| **Cambridge Cognition** | CANTAB cognitive eCOA; H1 2026 revenue £5.0M (+16%), 89% clinical studies; FY26 ≥£10.0M; £2.6M raise July 2026; order book £16.1M | Touchscreen | [AE] RNS summaries (investegate; kalkinemedia) | Partial (psychometric eCOA in CNS) / LOW |
| **Linus Health** | DCTclock, Digital Clock and Recall; FDA Class II-listed tools; health-system brain health | Tablet/stylus | [AE]; $55M Series B [AE] | None-partial / LOW |
| **BioSensics** | PAMSys home wearables (activity, gait, falls, upper limb), LEGSys/BalanSens, BioDigit cognition/speech/video; ALS among areas; ISO 13485; 3 FDA ISTAND LOIs; 200+ studies | Wearables, video | [CC] https://biosensics.com/ (fetched) | Partial (home functional telemetry in ALS) / MED-LOW |
| **Altoida** | AR/AI digital cognitive "NeuroMarker"; investigational, not FDA cleared per Jan 2026 release; Mindspan pilot | Tablet AR | [AE] (Business Wire 2026-01-13 via search; 403 on fetch) | None / LOW |
| **Rune Labs** | StrivePD (Apple Watch) Parkinson's RWE; Medtronic BrainSense (DBS) data collaboration (2021); AI companion (Apr 2026) | Wearable + DBS sensing | [AE] | Partial (home neuromodulation RWE) / MED for neuromod segment |

---

## Part G. HEOR and market-access firms

| Firm | Relevant capability | Labels | Overlap / threat |
|---|---|---|---|
| **PPD Evidera (Thermo Fisher)** | RWE, HEOR, market access, patient-centered research, CorEvitas registries; HealthVerity claims-data collaboration (Apr 2026) | [AE] https://www.ppd.com/news-item/thermo-fisher-scientifics-ppd-clinical-research-business-collaborates-with-healthverity-to-expand-real-world-data-capabilities/ (search summary) | Partial (payer evidence prep) / MED |
| **IQVIA MedTech (incl. MCRA)** | Neuro device regulatory (claims 120+ neuro submissions/yr), reimbursement (CPT/HCPCS/ICD-10-PCS), HEOR models, payer engagement; lists BCIs among supported tech | [CC] https://www.iqvia.com/sub-brands/medtech/reimbursement ; MCRA-in-IQVIA per search summary [AE] | Partial / MED-HIGH for payer-evidence niche |
| **Avalere Health** | US policy, coverage, Medicare evidence strategy | [PK] | Partial / MED |
| **Cytel** | Biostatistics, trial design; perspectives on digital primary endpoints | [AE] https://cytel.com/perspectives/smartwatches-are-transforming-clinical-trials-insights-from-digital-primary-endpoints/ | Complement (stats partner) / LOW |
| **Specialist HEOR shops** (e.g., YHEC, Certara) | Cost-effectiveness, budget impact models, payer tools; quote-based | [CC] https://yhec.co.uk/yhecservice_type/economic-evaluations-device | Complement / LOW |

Implication [INF]: "payer evidence prep" as a standalone niche competes with well-resourced consultancies
that already serve neuro devices. NeuroMetric's defensible contribution is the *primary functional and
real-world data* those consultancies need, not the economic model itself.

Context [AE]: Health Affairs Forefront (2026-03-18) on Medicare and BCIs, and a Medtech Insight (2026-03-30)
headline that "BCI development outpaces CMS coverage" (403/paywall; headlines only).

---

## Part H. Neurotech CROs and "BCI outcomes" startups (2023-2026)

- **Kordata** [AE]: "neurotechnology-powered CRO" for CNS trials (neuromodulation devices etc.), continuous
  neural monitoring and objective outcome measurement; article dated 2026-07-01; no BCI mention; founders and
  funding not stated (https://www.precedenceresearch.com/news/kordata-ai-driven-cro-cns-clinical-research , fetched).
  **Partial / MED-LOW.**
- **Qortical Clinical Partners** [CC/AE] (neuro-device CRO, non-invasive stimulation), **Clinilabs** [CC]
  (CNS CRO incl. devices), **NAMSA** [CC] (lists a BCI stroke-rehab device in its experience). Partial / LOW.
- **Dedicated "BCI outcomes" / iBCI registry startups:** none identified in this session's searches [UNR].
  This is *not* evidence of an empty market: the search quota ran out, stealth companies are not indexed, and
  academic groups (SRAL, Mount Sinai, BrainGate) and sponsors already occupy the function. Next step: check
  Crunchbase/PitchBook, BCI Society 2026 exhibitor list, NIH RePORTER (SBIR awards with "brain-computer
  interface" + "outcome"), and Neurotech Notables newsletter.

---

## S. Synthesis

### S1. Capabilities matrix

Legend: ● strong/core, ◐ partial/adjacent, ○ absent or not found. [INF] judgments from the profiles above.

| Player | Input-agnostic (AT+BCI) | Functional task battery | Home passive use telemetry | Care-partner burden | Psychometric validation | Trial mgmt / Part 11 | Evidence/payer packaging | BCI specific |
|---|---|---|---|---|---|---|---|---|
| SRAL DAI (+Neuralink) | ● | ● | ○ | ○ | ● (planned) | ○ | ◐ | ● |
| Mount Sinai Digital IADL | ● | ◐ (rating scale) | ○ | ○ | ◐ (early) | ○ | ◐ | ● |
| Neuralink in-house | ○ (own device) | ◐ (Webgrid) | ● | ○ | ○ | ◐ | ● (NTAP/coding) | ● |
| Synchron in-house | ○ | ○ | ◐ | ○ | ○ | ◐ | ◐ | ● |
| Paradromics | ○ | ◐ (SONIC preclinical) | ○ | ○ | ○ | ◐ | ◐ | ● |
| Cognixion in-house | ◐ (multi-modality) | ◐ | ● (daily use/modality) | ● (ZBI) | ○ | ◐ | ○ | ● (non-invasive) |
| Compass (KPR) | ● (AT inputs) | ● | ○ | ○ | ◐ | ○ | ○ | ○ |
| Tobii Dynavox / PRC-Saltillo | ○ (own ecosystem) | ◐ | ● (AAC logs) | ○ | ○ | ○ | ◐ | ○ |
| BCI2000 / FALCON / MOABB | ◐ | ○ (engineering) | ○ | ○ | ○ | ○ | ○ | ● |
| Signant + Ametris | ○ | ◐ | ● (wearables) | ◐ (ePRO) | ● | ● | ◐ | ○ |
| Clario (Thermo) | ○ | ◐ | ● | ◐ | ● | ● | ◐ (via PPD) | ○ |
| Medidata | ○ | ○ | ● | ◐ | ◐ | ● | ○ | ○ |
| Medable / YPrime / Suvoda / Castor | ○ | ○ | ◐ | ◐ | ○ | ● | ○ | ○ |
| Koneksa / BioSensics | ○ | ◐ | ● | ◐ | ● | ◐ | ◐ | ○ |
| Rune Labs | ○ | ○ | ● | ○ | ◐ | ○ | ◐ | ○ (DBS) |
| Evidera / IQVIA MedTech | ○ | ○ | ○ | ◐ | ◐ | ◐ | ● | ○ |
| NeuroMetric (target) | ● | ● | ● | ● | ● | ◐→● | ◐ | ● |

### S2. Where capabilities overlap directly [INF]
1. **Cross-device functional task testing:** SRAL DAI (direct, BCI + AT, psychometrics planned), Compass
   (AT only, clinic, $179), Neuralink Webgrid (single metric). This is the most crowded slice of NeuroMetric's
   scope and the one where an academic, sponsor-backed instrument may become the de facto standard by 2027.
2. **Home real-world use telemetry:** sponsors log it themselves (Neuralink hours/day; Cognixion "daily use
   time per input modality" as a *primary* endpoint); AAC vendors log it within their ecosystems; eCOA/DHT
   vendors capture wearables but not access-method use. Direct overlap is with sponsor in-house systems, not
   with vendors.
3. **Care-partner burden:** only Cognixion's registration (ZBI) among BCI studies found; eCOA vendors can
   field ZBI as a generic ePRO. Low direct competition, but also low differentiation unless tied to
   use-telemetry context (e.g., assisted vs independent sessions).
4. **Psychometrics / COA development:** SRAL and Mount Sinai groups (academic), plus eCOA vendors'
   science teams (Signant, Clario) and COA consultancies. Direct overlap on method; not on BCI content except
   academia.
5. **Part 11 data capture and trial management:** fully commoditized by eCOA/EDC vendors; NeuroMetric should
   integrate or white-label, not compete.
6. **Payer evidence packaging:** IQVIA MedTech/MCRA, Evidera, Avalere and sponsors' own teams; Neuralink is
   already in the CMS coding process.

### S3. Most threatening competitors and why [INF]
1. **SRAL DAI + Neuralink (HIGH):** direct substitute for the functional-testing core, cross-device by design,
   psychometrics in scope, the largest implanted cohort behind it, and academic credibility for FDA/iBCI-CC.
   Mitigation: position NeuroMetric as the neutral operator/host and home-telemetry layer; seek a licence or
   data-sharing collaboration; avoid building a rival index.
2. **Sponsor in-house build (Neuralink first; Synchron, Cognixion) (HIGH):** sponsors already collect
   telemetry and run outcome batteries; the biggest sponsor is a non-buyer. Mitigation: sell independence
   (third-party, audit-ready), cross-sponsor comparability, and payer-grade documentation that in-house data
   cannot provide credibly.
3. **Mount Sinai Digital IADL + iBCI-CC Endpoints WG (MED-HIGH):** decide which instruments count; any
   vendor can implement them. Mitigation: be the fastest, best-validated implementer; contribute to the WG.
4. **Signant Health + Ametris (MED-HIGH, latent):** eCOA + home wearables + digital-measure science +
   CNS rater networks; could add an access-method module if BCI/AT volume justifies it.
5. **Clario + PPD Evidera under Thermo Fisher (MED, latent):** one parent spanning eCOA, wearables and HEOR,
   the integrated "evidence to payer" offer NeuroMetric wants, but aimed at pharma-scale studies.

Watch list: Cognixion (could productize its battery), Tobii Dynavox (install base + analytics), IQVIA
MedTech (payer niche), Kordata (neurotech CRO), Rune Labs (home neuromodulation RWE).

### S4. Candidate entry niches

| Niche | Evidence for | Evidence against | Assessment [INF] |
|---|---|---|---|
| Independent outcome measurement (general) | Field consensus on lack of fit-for-purpose COAs (PMID 42648341, 39288794); FDA/NIH workshop | Academic instruments emerging (SRAL, Mount Sinai); "independence" is a positioning, not a product | Necessary positioning; too broad as a niche |
| Home-use evidence (passive telemetry + periodic home tasks) | 2026 J Neural Eng workshop names home/daily-life capture as a key gap; Cognixion uses daily use time as primary endpoint; Neuralink publicizes use hours | Sponsors log it in-house; OS/app access for third-party logging is uncertain (Apple BCI-HID) | **Strongest wedge**: least served by academia, hardest to credibly self-report |
| Functional task testing | Clear need; psychometrics doable | SRAL DAI direct; Compass at $179 | Do not lead with it; adopt/host consensus tasks |
| Cross-device benchmarking | Paradromics and SRAL both call for cross-device comparison | Engineering benchmarks free (FALCON, MOABB, SONIC, Webgrid); sponsors resist head-to-head | Valuable as a byproduct of neutral data, not a sellable product early |
| Sponsor-specific study infrastructure | Sponsors need Part 11 capture for EFS/pivotal | eCOA/EDC commoditized; few sponsors; custom work does not scale | Avoid except as delivery vehicle |
| Rehab tech evaluation (stroke/SCI rehab devices, AT) | Larger device count; IpsiHand-type payer coding precedents | Lower prices; Kinarm/clinic tools; fragmented buyers | Good second segment for input-agnostic platform |
| Payer evidence prep | Neuralink NTAP intent; iBCI-CC payor WG; Medicare coverage debate | Strong incumbents (IQVIA/MCRA, Evidera, Avalere) | Partner with consultancies; supply the functional RWD they lack |
| Combination (recommended) | See below | | |

**Recommendation (most specific defensible niche)** [INF]:
*"Neutral home-use digital-independence evidence for communication and computer-access devices."*
Concretely: a cross-device kit that (a) logs real-world use of BCI and AT input methods at the OS/app layer
(hours used, independent vs. assisted sessions, task completion, communication rate), (b) administers a short,
periodic home version of the consensus functional battery (implementing SRAL DAI-style primitives and the
Digital IADL scale where licensable, not a proprietary rival index), (c) captures care-partner burden (e.g.,
ZBI) linked to the telemetry, and (d) outputs a Part 11-ready, audit-trailed evidence package for FDA COA
dossiers and CMS/NTAP/coverage submissions. First customers: non-dominant iBCI sponsors moving from EFS to
pivotal (Paradromics, Synchron once enrollment resumes, Precision), non-invasive BCI/AAC makers (Cognixion,
possibly Tobii Dynavox), and academic iBCI programs (BrainGate, Pitt, UC Davis, JHU) via grant budgets.

Why defensible [INF]: (1) home/daily-life capture is the gap the 2026 pivotal-COA workshop names; (2) a third
party is more credible than sponsor self-report for payers; (3) input-agnostic telemetry pools data across
devices, which sponsors cannot do; (4) it complements rather than fights the academic instruments.

**Evidence that would falsify it** [HYP tests]:
- F1: SRAL/Neuralink (or iBCI-CC) publish a free, home-administrable DAI with its own logging, adopted by ≥2
  other sponsors by end-2027.
- F2: In discovery calls, ≥3 of 5 non-Neuralink sponsors say home-use evidence will be produced in-house or by
  their existing eCOA vendor, or that FDA/CMS do not require third-party collection.
- F3: No sponsor or AT maker signs a paid pilot ≥$25K within 9 months of outreach.
- F4: Apple/Google/AT vendors do not permit third-party OS-level access telemetry, and sponsors refuse
  app-level SDK integration (technical infeasibility).
- F5: FDA pivotal guidance or iBCI-CC endpoints settle on in-clinic performance tests only, with no home
  real-world-use endpoint.
- F6: Signant/Clario announce a BCI/AT access module before NeuroMetric has 2 reference customers.

### S5. Is the US implantable-BCI sponsor market too concentrated? [INF unless labelled]

Count of plausible industry sponsors running **US motor/communication iBCI trials, 2026-2028**:
- **Active now (registered US IDE studies, [V] CT.gov 2026-11-27):** Neuralink (PRIME, CONVOY-type, VOICE,
  new EFS), Synchron (INTENT; enrollment paused Nov 2026 [AE]), Paradromics (Connect-One). **= 3.**
- **Plausible by 2028:** Precision Neuroscience (fully implanted trial "expected 2026" [AE], none registered
  [V-negative]); Blackrock Neurotech (currently supplier/collaborator, own pivotal [UNR]); Echo
  Neurotechnologies (speech, funded [AE], no trial found); CorTec (stroke motor rehab, [PK]). **≈ +2 to 4.**
- **Speculative/longer:** Merge Labs (preclinical ultrasound), Science Corp (vision first), Axoft (Panama),
  Neurosoft (Europe), Chinese sponsors (Neuracle) for US entry. **≈ +0 to 2.**
- **Total: 3 certain, roughly 5 to 8 plausible.** Plus ~10-12 academic/VA iBCI programs (BrainGate2 variants,
  Pitt, Caltech, JHU CortiCom/INTENT, UC Davis, UCSF, UT Houston RECLAIM, Miami, VA iBCI Optimization) [V
  trial list], funded mainly by NIH/VA.
- **Concentration:** Neuralink alone had ~21-27 implanted participants in 2026 [AE] versus single digits
  for every other sponsor [V enrollment targets], and is already co-developing its COA with SRAL and handling
  coding/NTAP itself.
- **Revenue ceiling math** [HYP]: 5-8 sponsors × 1-2 studies × $100-400K/study-year ≈ $0.5M-$6.4M/yr at
  full penetration; realistic 30-50% penetration of non-Neuralink sponsors ≈ $0.3M-$2M/yr.
- **Verdict:** Yes, an iBCI-only standalone business is too concentrated and too dependent on 2-4 buyers
  (one paused, one non-buyer). It is viable only as the high-credibility anchor segment of an input-agnostic
  business that also serves non-invasive BCI, AAC/AT makers and rehab/home-neuromodulation device sponsors,
  and that uses NIH/VA/academic grant budgets. Falsified if ≥6 US iBCI sponsors have registered IDE studies
  by end-2027 and ≥3 issue RFPs for third-party outcome services.

### S6. Open items [UNR]
- Neuralink and Synchron 2026 primary statements (blogs/press 403 or not opened).
- Precision IDE status; Blackrock own pivotal plans; Echo trial plans.
- Realize Language, Gaze Viewer, Kinarm prices.
- Presence of any 2023-2026 BCI-outcomes startup (requires Crunchbase/PitchBook/NIH RePORTER).
- Full text of PMID 42648341 (COA framework details), and SRAL DAI publication/licensing intent.
