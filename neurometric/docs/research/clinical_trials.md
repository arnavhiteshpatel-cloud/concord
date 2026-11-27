# BCI and assistive neural-interface clinical trials: endpoints and instruments

Prepared for NeuroMetric. Registry data come from the ClinicalTrials.gov API v2
(`https://clinicaltrials.gov/api/v2/studies/{NCT}`). All records were **accessed 2026-11-27**.
The registry's data snapshot ("versionHolder") is 2026-11-25. Labels follow `CONVENTIONS.md`.
Registry facts are [V] (verified against the registry). They reflect what sponsors *registered*,
not what was achieved.

Companion file: `trials.csv` (65 rows: 63 registered studies + 2 "none found" rows for Neuralink
LINK pivotal and Precision Neuroscience).

---

## 1. NCT07407725: Shirley Ryan AbilityLab "Clinical Outcome Assessment for AT & BCI" (the DAI study)

URL: https://clinicaltrials.gov/study/NCT07407725 [V]

| Field | Registry value |
|---|---|
| Official title | "Development of a Clinical Outcome Assessment for Assistive Technologies and Brain-Computer-Interfaces" |
| Org study ID | STU00224714 |
| Sponsor | Shirley Ryan AbilityLab (responsible party: PI Arun Jayaraman, PT, PhD, Director, Max Nader Center for Rehabilitation Technologies & Outcomes Research) |
| Collaborator | **Neuralink Corp** (industry) |
| Status | **RECRUITING**; status verified 2026-11 |
| Dates | Start **2026-01-08 (actual)**; primary completion **2026-12 (estimated)**; study completion **2027-06 (estimated)**; first submitted 2026-01-22; first posted 2026-02-12; **last update submitted 2026-11-05, posted 2026-11-06** |
| Design | Interventional, phase N/A. Intervention model: **CROSSOVER**. "randomized, within-subject crossover … participants complete standardized digital tasks using multiple assistive technologies in randomized order. There is one arm per technology within each participant." Allocation field: N/A. Masking: none. Primary purpose: supportive care. |
| FDA-regulated device study? | No (isFdaRegulatedDevice = false); no DMC |
| Enrollment | **60 (estimated)** |
| Conditions | Spinal cord injury; ALS. Keywords include iBCI, COA, "dADL", "digital activities of daily living". |
| Cohorts (eligibility text) | Three cohorts: (1) healthy participants; (2) ALS/SCI participants **with an implanted invasive BCI**; (3) ALS/SCI participants **without** an implanted BCI. SCI must be at T1 or above (C1–T1). All adults ≥18 who can tolerate a ~3-hour session. Healthy volunteers accepted. |
| Single site | Shirley Ryan AbilityLab, Chicago, IL |
| IPD sharing | **No** |

**Arm and interventions** (single arm "AT/BCI User", with devices in randomized order):
- Eye tracker: Tobii Dynavox PCEye 5
- Mouth-operated joystick: Jouse+
- Non-invasive EEG headset: EMOTIV EPOC X (registry spells it "EMOTIVE")
- **Implantable BCI: "primarily recruited via Neuralink, will use the Neuralink N1 or any other implanted BCI"**. One 40-minute training session, because participants already have device experience.
- Personal assistive technology: one session
- Voice control

Training uses a "customized **Digital Training Interface**". It practices motor primitives (clicking,
typing, scrolling, drawing) through a tutorial and eight 3-minute levels, or until 20 correct
targets. New devices get two 40-minute sessions. "In-clinic and at-home sessions are scheduled on
separate days".

**Primary outcomes (verbatim measure names; descriptions abridged but quoted where key):**
1. **Performance Outcomes (PerfOs)**: "Quantitative metrics will be extracted from a customized
   **Digital Assessment Interface** simulating digital activities of daily living (dADLs, e.g., online
   shopping, texting, gaming, booking appointments). Metrics will be collected for each motor
   primitive (clicking, scrolling, typing, click-and-drag) to evaluate performance, including **click
   accuracy, time to target, number of errors, cursor trajectory, words per minute, and percentage of
   correct letters/characters**." Time frame: every visit during the DAI.
2. **Demographics and Medical Intake Questionnaire** (Day 1)
3. **NASA Task Load Index** (participant self-report after each DAI attempt)
4. **NASA Task Load Index – Clinician's perspective** (used as a ClinRO of fatigue)
5. **System Usability Scale (SUS)** (participant)
6. **System Usability Scale (SUS) – Clinician's perspective** (ClinRO)
7. **Qualitative Questionnaire**: "Modified version of the **Canadian Occupational Performance
   Measure (COPM)** to better capture functional digital independence" (semi-structured interview;
   goals; performance and satisfaction ratings)
8. **Psychosocial Impact of Assistive Devices (PIAD[S])**

**Secondary outcomes (Day 1, used for validation and device characterization):**
- ISNCSCI (abbreviated, converted to a modified ASIA score)
- ALSFRS-R
- Clinical Evaluation (AT comfort and experience)
- **IRF-PAI Section GG** (CMS self-care/mobility items, 6-point assistance scale; the same CARE-derived scale family proposed for the Digital IADL)
- ECAS (Edinburgh Cognitive and Behavioural ALS Screen)
- WHOQOL-BREF

**Stated objectives** (brief summary): primary, "to develop an index" quantifying functional performance
with ATs/BCIs, "comprised of performance outcomes, clinician-reported outcomes, and patient-reported
outcomes". Secondary: psychometric evaluation ("validity, responsiveness, reliability, and
floor/ceiling effects both globally and across different devices and impairment levels") and
characterization against a "normative healthy control population". [V]

**Background references listed in the record** include Sawyer et al. 2025 *EBioMedicine*
(Digital IADL), Dohle et al. medRxiv 2024 (iBCI outcome-measure review), Mois & Rogers 2024 (dADL
framework), the MoDAT mobile device assessment tool (Fairman et al. 2025), PIADS, and the IRF-PAI
Section GG validity paper. [V]

**Playbook check:** "NCT07407725, 60 participants, primary completion Dec 2026, Neuralink
collaborator" is **confirmed** [V]. "Digital Assessment Interface (DAI)" is the registry's term.
The playbook omits several things that matter:
- **Six** primary outcomes are questionnaires or clinician ratings (NASA-TLX x2, SUS x2,
  modified COPM, PIADS), not only performance data.
- It is a **crossover** study with a **healthy-control normative cohort**.
- The comparators are commercial AT: Tobii PCEye 5, Jouse+, EMOTIV EPOC X, and voice control.
- IPD will **not** be shared.
- It is **not** an FDA-regulated device study.
- Primary completion in Dec 2026 is only ~11 months after start, so the first index is likely
  development-stage (cross-sectional) rather than longitudinal responsiveness evidence. [INF]

**Implications for NeuroMetric [INF]:**
- A Neuralink-collaborating academic group is building an *index-type* COA. It is device-agnostic
  by design (it compares BCI with eye-gaze, joystick, EEG and voice) and anchored to CMS's Section
  GG / CARE family.
- It is a direct analog of, and potential competitor or partner to, a neutral measurement product.
- Its outputs (task battery, scoring) are not publicly shared (IPD = No), and the DAI software
  appears custom. That leaves room for an independent, interoperable, home-deployable
  implementation, but also a risk that the SRAL index becomes the de facto reference.

---

## 2. Landscape summary by sponsor (registry-verified unless labeled)

### 2.1 Neuralink
| NCT | Study | Status (registry) | Primary | Notable secondary / instruments |
|---|---|---|---|---|
| NCT06429735 | PRIME (US EFS) | Active, not recruiting; n=15 est.; start 2024-01-09; PC 2027-09; last update 2026-11-24 | Device- and procedure-related AEs at 12 mo | AEs to 72 mo. **No effectiveness or functional outcome registered.** |
| NCT06700304 | CAN-PRIME (Toronto) | Recruiting; n=6 | AEs 12 mo | MoCA, PHQ-9, GAD-7 |
| NCT06992596 | UAE-PRIME (Abu Dhabi) | Recruiting; n=10 | AEs | MoCA, PHQ-9, GAD-7, neuro exam |
| NCT07127172 | GB-PRIME (UCLH, Newcastle) | Recruiting; n=7 | AEs | MoCA, PHQ-9, GAD-7 |
| NCT06710626 | CONVOY (robotic arm) | Enrolling by invitation; n=3 | "Ability of participants to modulate brain activity for controlling an assistive device" (3 mo) | **PIADS; ATD PA** |
| NCT07224256 | VOICE (speech) | Recruiting; n=6; start 2025-10-03 | AEs | **Monthly max correct words per minute (CWPM)**; % electrodes inserted |
| NCT07929792 | "PRIME2" EFS (SCI, ALS, **chronic ischemic stroke**) | Recruiting; n=10; start 2026-11 (est.); posted with last update 2026-11-12 | Serious adverse device effects through 90 days | Summary: will assess "**digital daily activities, computer-control performance, independent use of the system, and participant-, clinician-, and caregiver-reported outcomes**". No instruments named. |
| — | **LINK Pivotal Study** | **No registry record found** (sponsor search 2026-11-27) | Not disclosed | Company: "first pivotal trial for an implantable brain-computer interface in the US", **ALS** population, "focus on functional outcomes that improve independence in daily life". [CC] |

Sources: registry records above [V]. LINK: https://neuralink.com/updates/neuralink-receives-fda-approval-to-launch-link-pivotal-study/ (dated **Nov 25, 2026**) [CC].
FDA does not publish IDE approvals, so "FDA approved" stays a **company claim**.
**Playbook check:** "LINK Pivotal Study approved 25 Nov 2026" matches the company announcement date [CC]. It is not independently verifiable [UNR for FDA-side confirmation].
The pivotal is in **ALS only** (per company), not SCI. Neuralink now reports ">30 implanted participants" across US/Canada/UK EFS [CC].

### 2.2 Synchron
| NCT | Study | Status | Primary | Secondary |
|---|---|---|---|---|
| NCT03834857 | SWITCH (Australia FIH) | Completed; n=5 | Treatment-related AEs (CTCAE v4.0), 12 mo | Signal fidelity: impedance, noise, SNR |
| NCT05041114 | SWITCH II | Withdrawn ("Study moved to U.S.") | — | — |
| NCT05035823 | COMMAND (US EFS) | Active, not recruiting; n=6 actual; PC 2024-09-19 (actual); last update 2026-09-08; **no results posted** | Treatment-related SAEs at 12 mo | none |
| NCT07543367 | **INTENT** EFS (ALS; Mayo Jacksonville, Buffalo, Mount Sinai, UPMC, UTSW) | Active, not recruiting; n=10 est.; start 2026-05-07; PC 2027-01 | Device-related SAEs to 180 days | SAEs to 1 yr; vessel patency and migration (CT venography) |
| NCT07533903 | FOCUS-AUS (Royal Melbourne) | Active, not recruiting; n=10; start 2026-05-22; PC 2026-09-22 (actual) | Device-related SAEs (death / permanent disability) to 90 days | Patency, migration |
| NCT07446114 | FOCUS-CAN (Toronto) | **Terminated** ("Insufficient recruitment"); n=1 actual | as FOCUS-AUS | as FOCUS-AUS |

**Playbook check:** "Synchron INTENT NCT07543367" **exists** [V]. Its registered outcomes are
safety and imaging only. Despite the names ("INdependence…", "Functional Outcomes and Control…"),
**no functional instrument is registered** in any Synchron record. The registry text frames the
device as intended "to restore **clinically meaningful control of digital devices**" and "to
replace the function of motor neurons". The home-training eligibility criteria require a caregiver
and a "suitable home environment for BCI training, including an internet connection". [V]
Name collision: **NCT07521930 "INTENT"** is a separate Johns Hopkins / Blackrock / APL study. [V]

### 2.3 Paradromics
- **NCT07357428 Connect-One** EFS of the Connexus BCI.
  - Status: recruiting; n=2 est.; start 2026-03-31; PC 2027-05.
  - Sites: UC Davis, MGH, Michigan (registry lists these as collaborators).
  - Registered outcomes: **safety only** (device-related AEs to 12 mo and to 6 yr).
  - Intended uses: imagined-speech/language communication and computer control.
  - Requires a "study care partner" and residence within 4 h of a site. [V]
- Paradromics publicly advocates a graded "independence × performance" COA framework and achieved
  ITR with latency reporting (SONIC benchmark). This is company advocacy, not a registered
  endpoint (see `published_bci_functional_measures.md`). [CC]

### 2.4 Academic intracortical / ECoG programs
| Program | NCT | Key registered efficacy measures |
|---|---|---|
| BrainGate2 (MGH/Brown/Stanford/Emory/UC Davis/VA) | NCT00912041 (umbrella, n=27, PC 2038) | Safety at 1 yr. Feasibility "indices of measurement, success criteria, and endpoints" left open. |
| BrainGate BG-Speech-01 | NCT05724173 | **≥5 WPM and median word error rate threshold** (secondary) |
| BrainGate BG-Speech-02 (UC Davis speech BCI) | NCT06094205 | **Word error rate, phoneme error rate** |
| BrainGate BG-Tablet-01 | NCT06511934 | Safety only |
| BrainGate BG-Aphasia-01 / -02 (new, not yet recruiting) | NCT07791459 / NCT07918768 | Speech-decoding feasibility / safety only |
| CortiCom (JHU) | NCT03567213 | **Success rate (successful/total trials); time to complete successful trials (s)**. Primary is time to explant. |
| CortiCom-Utrecht (UMC Utrecht) | NCT06207591 | **Primary usability bundle**: accuracy/sensitivity thresholds (>80% 1-command; 90%/80% 6-command), characters or keywords/min, VAS workload, **NASA-TLX, PIADS, QUEST 2.0**, home-software usability, degrees of freedom. Secondary: **hours of independent home use/day**. |
| Utrecht Neural Prosthesis (completed) | NCT02224469 | Copy-spelling proficiency (30 chars in 30 min, ≤20% errors); QUEST 2.0; PIADS; ACSA; **hours of home use/day** |
| JHU Summit (withdrawn) | NCT04576650 | Letters/min; **caregiver-calling signal**; ACSA; home-use logs |
| JHU BiCNS | NCT03161067 | ARAT with assistive device; ICMS percepts |
| JHU/Blackrock INTENT | NCT07521930 | Simultaneous control of ≥2 assistive devices; sensory feedback |
| Pittsburgh CRS-BMI | NCT01894802 | Safety; signal quality, DOF, performance |
| Pittsburgh microelectrode BMI (terminated) | NCT01364480 | Modified ARAT with 7- and 10-DOF prosthetic arm |
| Cleveland ReHAB (BCI + FES) | NCT03898804 | Center-out success rate; **ADL Abilities Test; Grasp Release Test** |
| Caltech/Rancho/USC | NCT01849822, NCT01958086 | Accuracy vs chance; **computer-interface competency exam (tablet)**; **QOLI** |
| UT Southwestern MindEx | NCT05936619 | Trajectory and icon selection vs chance; QOLI |
| UCSF BRAVO (ECoG speech) | NCT03698149 | Text and synthesized-speech communication objectives (no metric named) |
| UTHealth Houston RECLAIM | NCT07933549 | **WER, PER, BLEU, BERTScore** |
| Ottawa NCC | NCT03100110 | **McGill QoL (primary)**; % time on each AAC tech; **ITR (bits/s)** |

### 2.5 Clinatec / EPFL / ONWARD brain-spine interface (WIMAGINE ECoG + ARC)
- **NCT04632290 STIMO-BSI**: safety primary. Secondary outcomes: WISCI II, 10MWT, 6MWT, TUG,
  **SCIM III**, ASIA, MAS, Berg, **WHOQOL-BREF**, decoding accuracy.
- **NCT05665998 UP2**: upper limb; GRASSP, ARAT, CUE-T, ISNCSCI.
- **NCT06243952 Think2Go**: 10MWT, 6MWT, TUG, WISCI II, Berg, NRS, SCI-FAI.
- **NCT07745686 VALSE**: identified by search only; record not fetched in detail.
- Grenoble stroke: **NCT07477613** (FMA-UE, ARAT, BBT).
- Grenoble speech, locked-in: **NCT07698496** (≥20 intelligible items).
- Grenoble exoskeleton: **NCT02550522**.

These use *established rehabilitation* COAs because their goal is motor recovery, not digital
control. [V]
ONWARD itself sponsors no registered ARC-BCI trial. The BCI studies are EPFL-sponsored. [V] (sponsor search)

### 2.6 China (fast-moving, industry-sponsored)
| NCT | Sponsor | Notable measures |
|---|---|---|
| NCT05920174 | Neuracle (NEO) | Classification accuracy; bit rate (commands/min); **hours of use/month**; investigator-designed patient/**caregiver** satisfaction |
| NCT06990412 | Neuracle (NEO), completed, n=32 | **Primary: BCI-assisted ARAT grasp response rate at 3 mo**; usage time/month |
| NCT06829212 | StairMed (RISE) | **BPS (net correct targets/min × grid size)**, i.e., webgrid-style; usage hours; **caregiver burden checklist** |
| NCT06944834 | StairMed (STAIR) | Cursor accuracy, path efficiency, task time; SF-36; MoCA; PHQ-9; HAMA/HAMD |
| NCT07647315 | StairMed (WISE, Mandarin speech) | Characters/min; character error rate |
| NCT07720882 | NeuroXess ("Triple-F"), n=32 | **Primary: BCI-assisted ARAT responders ≥ MCID**; Barthel Index |
| NCT07784088 | BCIFlex (LEAP), n=34 | Primary: brain-control task success rate. Secondary: **Digital IADL (dIADL)**; **"Brain Control Fluency Index" = mean ITR on Web-Grid task**; PIADS; WHOQOL-BREF; PHQ-9; HADS-A |
| NCT07457645 | Shanghai Zhongshan | Grasp success rate; broad SCI battery |
| NCT07934914 | Nanjing (endovascular) | Barthel; SF-36; QUEST 2.0; ADL-task success with robotic arm |

### 2.7 Non-invasive / AAC BCI comparators (relevant because NeuroMetric is input-agnostic)
- **NCT07871071 Cognixion ONE** (ALS, n=30, NIDCD-funded, FDA-regulated device study).
  - Primary: **voluntary daily use time per modality from telemetry**. The registry explains this
    is "robust to learning effects, communication-partner effects, and prompt-driven artifacts".
  - Secondary: WPM, accuracy, ITR (bits/min), modality preference, SUS, NASA-TLX, ALSSQOL-SF,
    **Zarit Burden Interview**, conversation metrics, ALSFRS-R.
  - Home use over 12 weeks.
  - This is the most "real-world-use" endpoint design in the set. [V]
- **NCT04468919 OHSU BCI-FIT**: typing accuracy, correct characters/min, **ITR via mutual information with a language model**, NASA-TLX.
- **NCT04026581 Pittsburgh AAC-BCI** (observational): **monthly change in daily communication rate from SGD logs** at home.
- **NCT05951556 Shirley Ryan AbilityLab** telehealth EEG-BCI: home communication logs.

### 2.8 Other implanted neural interfaces in the CSV
- Inbrain graphene (NCT06368310, intraoperative)
- Axoft soft probe (NCT06673264; FINESSE II NCT07953036)
- Motif Neurotech DOT/XCS for depression (NCT07594483 RESONATE, NCT07684794), with MADRS endpoints. Relevant to "home neuromodulation" adjacency.

Precision Neuroscience: **no registry record found** under sponsor or intervention searches [UNR].
Its 510(k)-cleared Layer 7 interface (2025) is [PK], not re-verified.

---

## 3. Synthesis

### 3.1 What recurs
1. **Safety is the only primary endpoint in almost every company-sponsored US EFS.** This covers
   Neuralink PRIME family, Synchron COMMAND/INTENT/FOCUS, Paradromics Connect-One and BrainGate
   sub-studies. Functional effectiveness is, at most, a secondary measure, and often not
   registered at all. [V]
2. **Performance metrics** dominate effectiveness reporting:
   - accuracy / success rate (CortiCom, ReHAB, Neuracle, StairMed, BCIFlex)
   - speed: time to target, characters, words or CWPM per minute (VOICE, BG-Speech-01, CortiCom-Utrecht, Cognixion)
   - error rates: WER, PER, CER (UC Davis/BrainGate, RECLAIM, StairMed WISE)
   - information rate: ITR or bits per second (Ottawa, OHSU, Cognixion, Neuracle "bit rate"; StairMed and BCIFlex use webgrid-style BPS)
3. **AT-satisfaction and psychosocial PROs recur across groups:**
   - **PIADS**: Neuralink CONVOY, Utrecht x2, BCIFlex, SRAL DAI
   - **QUEST 2.0**: Utrecht x2, Nanjing
   - **NASA-TLX**: Utrecht, OHSU, Cognixion, SRAL DAI
   - **SUS**: SRAL DAI, Cognixion
4. **Mood and cognition safety PROs**: MoCA, PHQ-9 and GAD-7 in every non-US Neuralink record and
   in StairMed STAIR. These are safety monitoring, not benefit. [V]
5. **Upper-limb rehab COAs** (ARAT, GRASSP, FMA-UE, Barthel, SCIM) appear where the BCI drives an
   effector (robot arm, FES, glove, spinal stimulation). The Chinese pivotal-style studies use
   **"BCI-assisted ARAT response rate ≥ MCID"** as primary, the clearest MCID-anchored primary in
   the set. [V]
6. **Real-world use (hours/day or month from device logs)** appears in Utrecht, Neuracle, StairMed,
   NeuroXess, BCIFlex and Cognixion. It is primary only in Cognixion. [V]
7. **Caregiver outcomes are rare.** Zarit Burden Interview appears only in Cognixion (non-invasive).
   A "caregiver burden checklist" appears in StairMed RISE, investigator-designed caregiver
   satisfaction in Neuracle, and a caregiver-calling signal in JHU Summit (withdrawn). **No US
   implanted-BCI company registers a caregiver-burden outcome**, despite the FDA iBCI guidance and
   the iBCI-CC consensus. [V]
8. **Digital-function COAs are just emerging:**
   - **Digital IADL** is registered only in BCIFlex LEAP (NCT07784088).
   - The **SRAL DAI index** (NCT07407725) is in development.
   - Neuralink PRIME2's summary *mentions* "digital daily activities" without naming an instrument.
   - CortiCom's success rate and time are the US academic precursor. [V]

### 3.2 How companies differ
| Company | Registered functional measure | Implicit metric philosophy |
|---|---|---|
| Neuralink | CWPM (speech); PIADS/ATD-PA (robot arm); collaborator on SRAL DAI; publicly reports **webgrid BPS** (company metric) | Throughput (BPS), plus an emerging dADL index via an academic partner [V]/[CC] |
| Synchron | None registered; "clinically meaningful control of digital devices" in descriptions | Independence/ADL framing. Authors of the Digital IADL paper disclose Synchron consulting/stock (Sawyer et al. 2025 COI statement). [V]/[RF] |
| Paradromics | None registered (safety only) | Achieved ITR + latency (SONIC); graded independence × performance [CC] |
| BrainGate / UC Davis / UCSF / UTHealth | WPM, WER, PER, BLEU, BERTScore | Speech-decoding accuracy |
| JHU / Utrecht (CortiCom) | Success rate, speed, NASA-TLX, PIADS, QUEST, home independent use | Usability + home use |
| Clinatec / EPFL | Gait and upper-limb rehab COAs, SCIM, WHOQOL-BREF | Motor recovery |
| China (Neuracle, NeuroXess, StairMed, BCIFlex) | ARAT responder ≥MCID, webgrid BPS/ITR, dIADL, usage hours, caregiver burden | Most "pivotal-like" registered efficacy endpoints |

### 3.3 Functional measures that exist (and their validation status)
For detail, see `published_bci_functional_measures.md`.
- **CortiCom success rate / time to completion**: task-level performance, not a validated COA. [V] (registry)
- **Typing rate** (CCPM/WPM, CWPM): widely used; task-dependent; no MCID. [RF]/[PK]
- **ITR / achieved bitrate / webgrid BPS**: engineering metrics. The Wolpaw ITR assumptions are
  often violated. Webgrid BPS is a company task. [V] (Neuralink formula) / [PK]
- **Digital IADL** (Sawyer et al. 2025): 9 domains, 37 items. Development stage; "will be submitted
  to further validation". [RF]
- **CARE scale** (CMS Section GG 6-point independence scale): validated in post-acute care, not in
  BCI. Proposed as the Digital IADL response scale. Paradromics argues it misses performance
  quality. [CC]/[PK]
- **SRAL DAI index**: in development (NCT07407725). [V]
- **AT outcome PROs with prior validation in AT populations**: PIADS, QUEST 2.0, ATD PA, COPM, SUS,
  NASA-TLX. [PK] They are validated as AT instruments, not as iBCI effectiveness endpoints.

### 3.4 Gaps NeuroMetric could fill [INF]
1. A **cross-modality, home-deployable measurement chain** that logs device-agnostic interaction
   primitives and maps them to dADL task success. The DAI and Digital IADL concepts need exactly
   this to scale beyond one site.
2. **Real-world use telemetry standards**: hours of independent use, voluntary-use share by modality
   (the Cognixion model). These are increasingly used but not standardized.
3. **Caregiver burden and care-time linkage**, which payers want (iBCI-CC Principle 3) and nearly
   no iBCI trial registers.
4. **Neutral benchmarking** across sponsors, since registry endpoints are not comparable today.
5. **Risk:** SRAL/Neuralink may establish the reference index first. LINK pivotal endpoints are
   undisclosed. Partnering or interoperability with DAI/Digital IADL may beat competing with them. [HYP]

---

## 4. Method notes
- Searches: ClinicalTrials.gov API v2 `query.term` for "brain-computer interface", "intracortical",
  "neural interface paralysis", "speech neuroprosthesis", "stentrode", "BrainGate", "brain-spine
  interface", "WIMAGINE", "microelectrode array tetraplegia", "BCI ALS communication", and others.
  Also `query.spons` for Neuralink, Synchron, Paradromics, Precision Neuroscience, Blackrock,
  ONWARD, INBRAIN, Science Corp and Axoft. About 440 hits were screened by hand. Records judged
  relevant were fetched in full.
- Excluded:
  - non-invasive EEG rehabilitation trials (except AAC/communication BCIs relevant to input-agnostic measurement)
  - intraoperative mapping-only studies (except Inbrain, included as a neural-interface company)
  - NCT05014841 (UCSF speech neuroscience, not a device trial)
- Not found in the registry: Neuralink LINK pivotal, Precision Neuroscience, Science Corp (PRIMA is
  vision, out of scope), and a Blackrock-sponsored trial (Blackrock appears only as collaborator on
  NCT07521930).
- Registry "home_use" in the CSV: Y only where the record explicitly describes home sessions or home
  use; N for intraoperative or acute studies; otherwise UNR.
