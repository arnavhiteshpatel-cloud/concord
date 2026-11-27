# Regulatory landscape for BCI / AT functional-outcome measurement

Prepared for NeuroMetric. Access date for all web sources: **2026-11-27** unless noted.
Labels follow `CONVENTIONS.md`: [V] verified this session, [CC] company claim, [RF] peer-reviewed,
[AE] analyst/third party, [INF] NeuroMetric inference, [HYP] hypothesis, [PK] prior knowledge not
re-verified, [UNR] unresolved.

Status tags used below:
- **ESTABLISHED**: statute, regulation, or final guidance in force.
- **EVOLVING**: proposed, draft, consensus-in-progress, or recently announced and not yet final.
- **NEEDS FORMAL VALIDATION**: a measurement or tool claim that would need psychometric / analytical
  validation or regulatory qualification before it can carry a regulatory or coverage decision.

Research limit: this session's web-search quota ran out partway through. Items that could only be
checked by search, and were not fetched from a primary source, are labeled [PK] or [UNR]. The main
gaps are the state neural-data laws other than Colorado and the full text of the Health Affairs piece.

---

## 0. Bottom line for NeuroMetric

1. **FDA expects a validated primary effectiveness endpoint with an MCID for a pivotal iBCI study.
   It also wants home-use study and caregiver metrics.** No BCI-specific clinical outcome
   assessment (COA) has been qualified, either through MDDT or any other route. The
   endpoint gap is real and recognized. [V] (iBCI guidance, MDDT list)
2. **The field's own consensus (iBCI-CC, 1 Oct 2026) says no single existing measure is likely to be
   enough.** It calls for a "shared measurement chain" running from device performance to
   function/activity to health outcome or care burden. That is very close to NeuroMetric's thesis.
   The wording is hedged ("unlikely"), and the statement is not a regulatory standard. [V]
3. **The first US pivotal iBCI study (Neuralink LINK, announced 25 Nov 2026) has no public registry
   record and no disclosed endpoints.** The Shirley Ryan AbilityLab DAI study (NCT07407725), with
   Neuralink as collaborator, is building a digital-ADL index from PerfO + ClinRO + PRO components
   and is due for primary completion in Dec 2026. A de facto Neuralink-aligned COA may emerge from it. [V]/[CC]
4. **RAPID (CMS–FDA) could make the outcomes agreed with CMS before the IDE the coverage endpoints.
   It is still only proposed (comments closed 13 Oct 2026; no final notice found).** It only
   admits devices *at the IDE pre-submission stage*. On the face of the fact sheet, that would
   exclude devices whose pivotal IDE is already approved or underway, such as LINK. [V] for the
   text; the exclusion applied to LINK is [INF].
5. **A neutral measurement tool used only to collect data in trials is likely *not* itself a
   regulated device.** But FDA expects it to be "fit-for-purpose", verified and validated under
   the DHT guidance whether or not it is a device. As a clinical-investigation electronic system,
   it must also meet Part 11 / eSystems Q&A expectations (validation, audit trails, IT-service-
   provider oversight). [V] for guidance text; [INF] for the application to NeuroMetric.

---

## 1. FDA iBCI guidance (2021)

**Document.** "Implanted Brain-Computer Interface (BCI) Devices for Patients with Paralysis or
Amputation – Non-clinical Testing and Clinical Considerations". Final guidance issued **May 20,
2021**; draft Feb 22, 2019. Docket FDA-2014-N-1130. A cover note added later points sponsors to the
June 14, 2023 "Content of Premarket Submissions for Device Software Functions" guidance.
URL: https://www.fda.gov/media/120362/download [V] **ESTABLISHED** (nonbinding guidance)

Key requirements, quoted briefly, with section references from the PDF's table of contents:

| Topic | What the guidance says | Section | Label |
|---|---|---|---|
| Primary effectiveness endpoint, validation, MCID | Sponsors "should include how the primary effectiveness endpoint was validated (if applicable) for the intended use population/subjects, the minimal clinically important difference, and how the timing of the assessments is appropriate and clinically meaningful." Also: "Although validated endpoints are recommended, FDA realizes that feasibility studies may be used to validate desired clinical metrics and may not require a priori validated clinical endpoints." | III.O(2)(c)(vii)(2) "Endpoints and Other Outcomes" | [V] |
| PROs / COAs | A PROM should be "validated for the appropriate 'context of use'". PROMs "are often used in conjunction with other clinical outcome assessments (COAs) as part of a composite endpoint". Cross-cultural validity is required for multinational trials. | III.O(2)(c)(vii)(3) "Patient Input" | [V] |
| Patient preference information | PPI "may be an important factor in the design and benefit-risk evaluation". Daily calibration, fatigue and inconsistent performance may affect risk tolerance. | III.O(2)(c)(vii)(3) | [V] |
| Home use | "It is important to study BCI devices in realistic, home use environments since lab conditions may not adequately reflect the possible risks and/or benefits". | III.O(2)(b) "Home Use" | [V] |
| Caregiver metrics | "it is important to incorporate assessment of caregiver safety and their ability to assist the user (i.e., time, attention and physical ability) in the clinical study metrics". The guidance also asks sponsors to describe caregiver training and how its effectiveness will be assessed. | III.O(2)(b) | [V] |
| Follow-up | "A long-term follow up period of at least 1 year is recommended". | III.O(2)(c)(iii) "Study Duration and Follow-up Schedule" | [V] |
| Pivotal SAP | A detailed, pre-specified SAP; Bayesian and adaptive designs are acceptable. | III.O(2)(e) | [V] |
| Risk class | iBCIs are "generally" significant-risk devices under 21 CFR 812. | III.O(2) | [V] |
| Software documentation level | Cover note: iBCIs "should generally address the recommendations for an **Enhanced Documentation Level**" (formerly "Major Level of Concern") under the 2023 device-software-functions guidance. | Cover note (pre-preface) and III.C "Software" | [V] |
| Caregiver as inclusion criterion | "Willingness and ability of caregiver to monitor for surgical site complications and behavioral changes of the patient on a daily basis". | III.O(2)(c)(iv) | [V] |

**Nuance vs the playbook.** The playbook says the guidance "asks for validated primary effectiveness
endpoint, MCID, >=1 year follow-up, home use, caregiver metrics". That is broadly accurate, with two
qualifications. (a) Validation is "recommended", and feasibility studies are explicitly allowed to
use non-validated endpoints. (b) The "caregiver metrics" are about caregiver *safety and ability to
assist* (time, attention, physical ability), not caregiver *burden* as a benefit outcome. Caregiver
burden as a payer-relevant outcome comes from the iBCI-CC consensus (Section 6), not from this
guidance. [V]

**Implication.** A pivotal sponsor needs an endpoint with documented validity in the target
population, an MCID, and home-use data. A neutral, validated, home-deployable measurement chain
targets exactly these gaps. [INF]

---

## 2. FDA COA / Patient-Focused Drug Development (PFDD) guidance series and devices

| Guidance | Status | Relevance to devices | URL | Label |
|---|---|---|---|---|
| PFDD 1: Collecting Comprehensive and Representative Input | Final | Methods for patient-input sampling | https://www.fda.gov/drugs/development-approval-process-drugs/fda-patient-focused-drug-development-guidance-series-enhancing-incorporation-patients-voice-medical | [V] |
| PFDD 2: Methods to Identify What Is Important to Patients | Final | Qualitative methods for "meaningful aspects of health" (MAH) | same | [V] |
| PFDD 3: Selecting, Developing, or Modifying Fit-for-Purpose COAs | **Final, October 2025** (docket FDA-2022-D-1385). **CDRH is listed among the issuing offices.** | Core reference for selecting/modifying a COA (concept of interest → context of use → evidence). The iBCI-CC consensus statement cites it. | https://www.fda.gov/regulatory-information/search-fda-guidance-documents/patient-focused-drug-development-selecting-developing-or-modifying-fit-purpose-clinical-outcome | [V] |
| PFDD 4: Incorporating COAs into Endpoints for Regulatory Decision-Making | **Draft, April 2023** (FDA-2023-D-0026) | Meaningful within-patient change, endpoint construction; device teams borrow it | https://www.fda.gov/regulatory-information/search-fda-guidance-documents/patient-focused-drug-development-incorporating-clinical-outcome-assessments-endpoints-regulatory | [V] |
| CDRH "Principles for Selecting, Developing, Modifying, and Adapting PRO Instruments for Use in Medical Device Evaluation" | Draft (Jan 2022) per prior knowledge; the landing page could not be fetched (404) | Device-specific PRO guidance | not fetched | [PK] |
| PRO guidance (2009) "Patient-Reported Outcome Measures: Use in Medical Product Development to Support Labeling Claims" | Final; cited in the iBCI guidance | PRO validation for labeling claims | cited in iBCI guidance, footnote 40 | [V] (as cited) |

**Status:** PFDD 3 is **ESTABLISHED** (final). PFDD 4 and the CDRH PRO guidance are **EVOLVING**
(draft). Any NeuroMetric composite or index is **NEEDS FORMAL VALIDATION** under PFDD 3 logic:
content validity with patients, construct validity, reliability, ability to detect change, and
meaningful-change thresholds. [INF]

---

## 3. FDA DHT guidance: "Digital Health Technologies for Remote Data Acquisition in Clinical Investigations" (Dec 2023)

Final guidance, **December 2023**, joint CDER/CBER/CDRH/OCE; docket FDA-2021-D-1128.
URL: https://www.fda.gov/regulatory-information/search-fda-guidance-documents/digital-health-technologies-remote-data-acquisition-clinical-investigations ;
PDF https://www.fda.gov/media/155022/download [V] **ESTABLISHED**

What "fit-for-purpose" means (quoted):
- Fit-for-purpose means "the level of validation associated with the DHT is sufficient to support
  the use, including the interpretability of its data in the clinical investigation", considering
  both the DHT's form and its function(s). (Sec. I) [V]
- **Verification** is "confirmation by examination and provision of objective evidence that the
  parameter that the DHT measures (e.g., acceleration, temperature, pressure) is measured
  accurately and precisely." (Sec. IV.C) [V]
- **Validation** is "confirmation by examination and provision of objective evidence that the
  selected DHT appropriately assesses the clinical event or characteristic in the proposed
  participant population". (Sec. IV.C) [V]
- "Verification and validation should be addressed **regardless of whether the DHT meets the
  definition of a device** under section 201(h)". (Sec. IV.C) [V]
- Usability evaluations and validation studies may involve healthy volunteers and patients across
  disease severity. (Sec. IV.C) [V]
- For DHTs that *are* devices but are used only for remote data collection in a clinical
  investigation: when sponsors do the recommended V&V, "FDA does not intend to otherwise assess
  sponsors' compliance with design control requirements". This policy "does not apply when a DHT
  that is a device is intended for use outside of a clinical investigation." (Sec. III) [V]
- Other sections cover endpoint evaluation with DHT data (IV.D), statistics (IV.E), risk (IV.F) and
  record protection and retention (IV.G, which cross-references the eSystems Q&A). [V]

**Application to NeuroMetric [INF]:**
- Verification means the logged primitives (click latency, cursor path, keystroke timing, error
  counts, session duration) are accurate and precise across BCI, eye-gaze, switch and voice inputs.
- Validation means the derived measures (e.g., a digital-ADL index or task success) reflect the
  clinical concept in iBCI/AT populations.
- Being input-agnostic increases the V&V burden. Equivalence must be shown *per input modality*.

---

## 4. Electronic records: 21 CFR Part 11 and the eSystems Q&A (Oct 2024)

- **21 CFR Part 11** (in force). § 11.1 applies to electronic records "created, modified, maintained,
  archived, retrieved, or transmitted, under any records requirements set forth in agency
  regulations" and to records submitted under the FD&C Act. § 11.10 closed-system controls
  include "(a) Validation of systems…", "(e) Use of secure, computer-generated, time-stamped audit
  trails…", access limits and authority checks.
  eCFR: https://www.ecfr.gov/current/title-21/chapter-I/subchapter-A/part-11 [V] **ESTABLISHED**
- **"Electronic Systems, Electronic Records, and Electronic Signatures in Clinical Investigations:
  Questions and Answers"**: final guidance, **October 2024**, Procedural Revision 1; docket
  FDA-2017-D-1105; Federal Register notice of Oct 2, 2024. It finalizes the March 2023 draft and
  supersedes the 2007 "Computerized Systems Used in Clinical Investigations".
  PDF: https://www.fda.gov/media/166215/download [V] **ESTABLISHED**
  Points relevant to a measurement vendor [V]:
  - Q7: a **risk-based approach** to validating electronic systems. When validation is done by an
    IT service provider, the regulated entity may review the provider's documentation.
  - Section III.C (Q17–Q19): regulated entities "are responsible for ensuring that electronic
    records meet applicable part 11 requirements" when using IT service providers. **FDA "may
    inspect IT service providers"** who have assumed regulatory responsibilities, or where there
    are data-integrity concerns.
  - Q20–Q23 (DHTs): data attribution, transfer, and **source-data location**. For DHTs, source data
    are considered located in "the durable electronic data repository (e.g., EDC system, … cloud-
    based digital platform)". FDA "does not intend to inspect individual DHTs".
  - Q12–Q13: audit-trail expectations.

**Implication [INF]:** if NeuroMetric's cloud platform is the durable repository for BCI/AT
performance data in an IDE study, *it is the source-data location*. It needs Part 11-grade
controls (validation package, audit trails, access control, time synchronization) and contracts
that support sponsor oversight and FDA inspection.

---

## 5. MDDT program (Medical Device Development Tools)

- The FDA MDDT page lists qualified tools in three categories: COA, biomarker test, and nonclinical
  assessment model. Qualification has a Proposal phase and a Qualification phase, each tied to a
  specific **context of use**. URL: https://www.fda.gov/medical-devices/medical-device-development-tools-mddt [V]
- **Qualified COAs on the list (as of 2026-11-27):** KCCQ (2017-10-19), MLHFQ (2018-03-19), INSPIRE
  questionnaires (2020-06-24), BREAST-Q Reconstruction (2020-08-20), PROWL-SS (2021-06-17), FACE-Q
  Aesthetics (2022-04-26), AIOLIS (2024-05-16), WOUND-Q (2024-11-08). The newest tools are
  MolecuLightDX (2026-01-26, biomarker) and IVIES (2026-02-03, nonclinical). [V]
- **No BCI, AT, neurology-function, or digital-ADL COA is qualified.** The only neurology entry is
  the OSIRIX CDE Software Module (biomarker test, 2019). [V]
- **Status:** the MDDT route is **ESTABLISHED** as a process. A BCI COA via MDDT would be **NEEDS
  FORMAL VALIDATION**, a multi-year effort. Note that a qualified MDDT "will be accepted by the FDA
  without the need to reconfirm the suitability and utility of the tool within the same context of
  use". This is the regulatory value of a *neutral, shared* tool. [V] (page text) / [INF] (strategy)

---

## 6. Field consensus relevant to regulators and payers (iBCI-CC)

- The **iBCI Collaborative Community (iBCI-CC)** is convened by Mass General Brigham. FDA
  announced its participation in May 2024. It has seven workgroups, including Clinical Study
  Endpoints and Payor Interactions & Device Categorization. https://www.ibci-cc.org/ [V]
- **"Consensus Statement for the Assessment of iBCI Endpoints for Clinical Utility"**, dated
  **1 October 2026**. PDF title: "iBCI-CC: Consensus Statement for the Assessment of iBCI Endpoints
  for Clinical Utility"; filename "iBCI-CC-Assessment-of-the-iBCI-Endpoints-for-Clinical-Utility.pdf".
  Authors: Haggstrom, Lang, McMullen, Moses, Pinto, Putrino, Sarkar, Serruya, Strauss, Vansteensel,
  Welle. https://www.ibci-cc.org/s/iBCI-CC-Assessment-of-the-iBCI-Endpoints-for-Clinical-Utility.pdf [V] **EVOLVING**
  - Context: it responds to RAPID and to a report by an **"iBCI Clinical Utility Consortium (CUC)"**,
    an "ad hoc commercial, outside interest consortium". The CUC report is titled "A Framework for
    Demonstrating Clinically Meaningful Benefit for Medicare: A Review of Potential Outcome Measures
    for Implantable Brain-Computer Interfaces" (July 2026). The CUC report itself was not found
    publicly. [V] that it is described / [UNR] its content
  - Principle 1 (quote): "it is **unlikely** that a single, existing outcome measure or collection of
    existing measures will be sufficient to characterize the clinical benefit conferred by the
    first generation of iBCI systems." Three strategies: (1) a combinatory strategy using
    fit-for-purpose COAs (composite or suite); (2) new validated instruments; (3) a mix. "flexible
    pathways are needed to generate real-world data." [V]
  - Principle 2 (quote): FDA and CMS have distinct statutory standards. The iBCI-CC recommends
    "a **shared measurement chain** extending from device performance, to functional or
    activity-level outcome, to health outcome or change in care burden". [V]
  - Principle 3: PROs, quality-of-life and participation outcomes should not be "categorically
    treated as secondary". "care partner burden, functional communication, and participation in
    meaningful activities can be positioned as key outcomes of interest, particularly for payor
    decision-making." [V]
- **Playbook check.** The playbook paraphrase ("no single existing outcome measure suffices",
  "shared measurement chain", 1 Oct 2026) is substantively correct. Exact title: "Consensus Statement
  for the Assessment of iBCI Endpoints for Clinical Utility". The PDF is named "Assessment of *the*
  iBCI Endpoints…". The language is "unlikely … sufficient", not a categorical "no". [V]
- Companion paper: Sawyer A, Welle CG, … Hochberg LR. "Brain–computer interface clinical trial
  design considerations and clinical outcome assessments in pivotal studies: a summary of the 11th
  BCI Society Meeting 2025 workshop." *J Neural Eng* 2026;23(5), published 2026-09-11, CC-BY,
  DOI 10.1088/1741-2552/ae9eee. It frames a **MAH → COI → COA** framework and names as key
  challenges "patient heterogeneity, the lack of widely validated and fit-for-purpose COAs, and the
  need to capture meaningful outcomes in home and daily-life environments". It uses ADAPT-PD as a
  lesson for home and daily-life measurement. Co-authors include Matthew Angle (Paradromics CEO,
  per the Paradromics blog byline) and Thomas Oxley (Synchron founder [PK]). David McMullen was
  welcomed to Neuralink on 9 Dec 2025 according to a Neuralink updates page entry; this session
  did not check his affiliation on the paper. Other authors' affiliations were not checked.
  Crossref: https://api.crossref.org/works/10.1088/1741-2552/ae9eee [V]/[RF]

---

## 7. Medicare and FDA–CMS coverage initiatives

### 7.1 RAPID (Regulatory Alignment for Predictable and Immediate Device coverage pathway)
- Announced by CMS and FDA on **April 23, 2026**.
  https://www.cms.gov/newsroom/press-releases/cms-fda-announce-rapid-coverage-pathway-accelerate-patient-access-life-changing-medical-devices [V]
- Procedural notice CMS-3487-NC, "Medicare Program; Regulatory Alignment for Predictable and
  Immediate Device (RAPID) Coverage Pathway". **Published in the Federal Register 2026-08-11**
  (FR Doc. 2026-16368, 91 FR 51710). **Comments closed 2026-10-13.** CMS fact sheet dated Aug 7, 2026.
  https://www.federalregister.gov/documents/2026/08/11/2026-16368/medicare-program-regulatory-alignment-for-predictable-and-immediate-device-rapid-coverage-pathway ;
  https://www.cms.gov/newsroom/fact-sheets/regulatory-alignment-predictable-immediate-device-coverage-pathway-cms-3487-nc-procedural-notice [V]
- **Status: EVOLVING.** A Federal Register API query on 2026-11-27 found no final RAPID notice. CMS
  says the effective date comes with the final notice. [V]
- Key mechanics [V, CMS fact sheet]:
  - Eligible: Class III Breakthrough devices planning a PMA (with or without TAP), and presumptive
    Class II Breakthrough devices in TAP planning a De Novo.
  - The device must be at the **IDE pre-submission stage**. The manufacturer must plan "an IDE study
    that enrolls Medicare beneficiaries and evaluates clinical outcomes that FDA determines are
    appropriate … and that CMS confirms" would show improved health outcomes. **"Devices beyond the
    IDE pre-submission stage (such as those market authorized or with an IDE study underway) are
    not appropriate for RAPID."**
  - There must be no evidence that "immediately makes clear that the device will not fall under a
    Medicare benefit category". The device must be separately payable and not already under a
    controlling NCD.
  - CMS will post a proposed NCD on the day of FDA authorization (30-day comment period), with a
    final NCD targeted at about 60 days (Class II) or 90 days (Class III).
  - Higher-risk devices "are more likely to have remaining evidence gaps". CED may apply and is to
    be time-limited and aligned with FDA post-approval studies.
- **TCET is paused for new candidates** while CMS implements RAPID (press release). [V]
- **Playbook check:** "RAPID announced Apr 2026, procedural notice 11 Aug 2026" is **confirmed**
  (FR publication date 2026-08-11; CMS's own fact sheet is dated 2026-08-07). [V]
- **Implication [INF]:** RAPID makes "outcomes agreed with CMS before the IDE" the gating item. That
  raises demand for pre-specified, validated function and health-outcome measures that work in
  Medicare-age and disability-entitled populations. On a literal reading, iBCI programs whose
  pivotal IDE is already approved (e.g., Neuralink LINK) would not qualify for RAPID. They would
  use the standard NCD process (TCET is paused for new entrants). This reading should be confirmed
  against the final notice.
- NSCEB's September 2026 paper explicitly recommends ensuring "BCI technologies are explicitly
  included in the new FDA and CMS RAPID program" (Section 9). [V]

### 7.2 TCET (Transitional Coverage for Emerging Technologies)
- Final procedural notice published **2024-08-12** (FR Doc. 2024-17603); proposed 2023-06-27.
  https://www.federalregister.gov/documents/2024/08/12/2024-17603/medicare-program-transitional-coverage-for-emerging-technologies [V]
  Breakthrough-device NCD pathway with up to 5 candidates/year and evidence-development
  expectations. [PK] **ESTABLISHED but paused for new candidates (Apr 2026)**. [V]

### 7.3 Breakthrough device coverage and CED
- MCIT (Medicare Coverage of Innovative Technology) was finalized in Jan 2021 and repealed in Nov
  2021. [PK]
- Coverage with Evidence Development (CED) operates under §1862(a)(1)(E) and CMS's 2024 CED guidance
  document. [PK] **ESTABLISHED**
- Breakthrough designation is relevant to the NTAP alternative pathway (inpatient) and TCAP. Law-firm
  commentary (Ropes & Gray, May 2026) reports a *proposed repeal* of the NTAP alternative pathway
  for Breakthrough devices. Outcome not verified. [AE]/[UNR]
- Neuralink has publicly stated Breakthrough Device Designations, including one for speech
  (Neuralink updates list "neuralink-receives-breakthrough-device-designation-for-speech" and
  "...-for-blindsight"). Dates not re-verified. [CC]

### 7.4 Medicare benefit category: the core BCI coverage problem
- Medicare covers items only if they fall into a statutory **benefit category** *and* are
  "reasonable and necessary" (§1862(a)(1)(A)). [PK] **ESTABLISHED**
- Candidate categories for an iBCI system [INF/PK]:
  - (i) the implant procedure as a physician/hospital service. The implanted device is bundled
    into facility payment, with potential pass-through or NTAP.
  - (ii) **prosthetic device** (§1861(s)(8): devices that "replace all or part of an internal body
    organ … or … the function of" one). Synchron's registry text explicitly frames its device as
    intended "to **replace the function of motor neurons**", which reads like prosthetic-device
    framing. [V] for the registry text (NCT07543367, NCT07533903); [INF] for the motive.
  - (iii) **DME** (§1861(n)) for external components, e.g., processors or speech-output devices.
- **NCD 50.1 Speech Generating Devices** is the closest analog. Benefit category: **Durable Medical
  Equipment**. Version 2 effective **07/29/2015**. It covers devices generating speech for patients
  with severe speech impairment, plus "the capability to generate email, text, or phone messages".
  It does **not** cover non-speech computing functions (documents, spreadsheets, games, music,
  video conferencing); "the cost of these features are the responsibility of the beneficiary".
  "computers and tablets are generally not DME".
  https://www.cms.gov/medicare-coverage-database/view/ncd.aspx?ncdid=274 [V]
  The DME MAC LCD for SGDs (L33739) and its accessory codes (e.g., eye-tracking access) were not
  re-verified. [PK]
- **Implication [INF]:** a BCI's general *computer-control* functions risk falling into NCD 50.1's
  "not covered" bucket. Communication and messaging functions fit the existing SGD benefit. Payers
  will look for evidence that links digital control to *medical* outcomes (communication of needs,
  safety calls, self-management, reduced care time), not to gaming or general computing. The Health
  Affairs Forefront piece (Section 9) reportedly makes the same point; that is [UNR] because the
  full text was blocked.

---

## 8. Neural-data privacy and HIPAA

### 8.1 State neural-data laws
| Jurisdiction | Law | What it does | Status / date | Label |
|---|---|---|---|---|
| Colorado | **HB24-1058** "Protect Privacy of Biological Data" | Amends the Colorado Privacy Act. Adds "biological data", with "neural data" as a subset defined as information generated by measuring activity of the central or peripheral nervous system, to "sensitive data" (opt-in consent). | Signed **2024-04-17**, Ch. 68, effective **2024-08-07** | [V] https://leg.colorado.gov/bills/hb24-1058 |
| California | **SB 1223** | Adds "neural data" to "sensitive personal information" under the CCPA/CPRA. | Signed Sept 2024, effective Jan 1, 2025 (leginfo returned HTTP 403) | [PK] |
| Montana | **SB 163 (2025)** | Extends the Genetic Information Privacy Act to "neurotechnology data". | Enacted 2025, effective Oct 1, 2025 (bill site needs JavaScript; not verified) | [PK] |
| Connecticut | **SB 1295 (2025)** | Adds neural data to "sensitive data" under the CT Data Privacy Act. | Enacted 2025; reported effective July 1, 2026 (not verified) | [PK] |
| Federal | **MIND Act** (Senate bill, 2025) | Would direct the FTC to study neural-data governance. | Introduced 2025 per prior knowledge; status not verified | [PK]/[UNR] |
| Other 2025–2026 state bills | Several states considered neural-data bills | | Not verified this session (search quota exhausted) | [UNR] |

**Status: EVOLVING** (a patchwork of statutes). Most state consumer-privacy laws exempt PHI covered
by HIPAA and data collected in human-subjects research under the Common Rule / ICH GCP. The
exemption wording varies by state. [PK]

### 8.2 HIPAA applicability to a measurement vendor
- A **business associate** is a person who, "on behalf of such covered entity … creates, receives,
  maintains, or transmits protected health information for a function or activity regulated by
  this subchapter", or provides data-aggregation, management or administrative services involving
  PHI. 45 CFR 160.103. https://www.ecfr.gov/current/title-45/subtitle-A/subchapter-C/part-160/subpart-A/section-160.103 [V]
- **Implications [INF]:**
  - When NeuroMetric is deployed by a hospital, clinic or rehab provider (a covered entity), it is
    likely a business associate and needs a BAA and HIPAA Security Rule controls.
  - When contracted by a *device sponsor* for an IDE study, the sponsor is usually not a covered
    entity. Data then flow under research authorization and consent, and HIPAA may not apply
    directly to NeuroMetric. State neural-data laws, the FTC Act and the FTC Health Breach
    Notification Rule could apply instead, especially for direct-to-consumer or home use. [PK] for
    the HBNR 2024 amendments.
  - Raw neural signals versus derived performance metrics: NeuroMetric's input-agnostic design
    (logging *interaction events*, not raw neural signals) may keep it outside the "neural data"
    definitions in CO/CA/MT. Each statute's definition must be checked, because Colorado covers
    data "generated by the measurement of" nervous-system activity, which may arguably include
    decoded outputs. This needs legal review. [INF]
- The NSCEB paper (via Axios coverage) and the GAO's 2024 report flag open questions about BCI data
  ownership and HIPAA applicability. GAO-25-106952: https://www.gao.gov/products/gao-25-106952
  [AE] (GAO report existence per the iBCI-CC news page; content not re-read).

---

## 9. Policy signals (2026)

- **NSCEB issue paper**: "Securing U.S. Leadership in Brain-Computer Interfaces", dated **September
  2026** on its cover. It came out of an April 2026 expert convening.
  https://www.biotech.senate.gov/wp-content/uploads/2026/09/NSCEB-BCI-Issue-Paper-Final.pdf [V]
  - It states: "In March 2026, China became the first country to approve an implantable BCI for
    commercial use". [V] that NSCEB says it; the underlying fact is not independently verified.
  - "Even if a BCI were approved, there is currently no active Centers for Medicare & Medicaid
    Services (CMS) reimbursement coverage for implantable BCIs". A novel Class III PMA "can face an
    FDA review cycle of 12–18 months after submission." [V]
  - New policy option: "Ensure BCI technologies are explicitly included in the new FDA and CMS
    RAPID program." It also covers data infrastructure for clinical-performance databases and
    multi-site IRB / FDA process reforms. [V]
  - Its disclaimer says the content "do[es] not necessarily represent positions officially" of the
    Commission. [V]
- **Health Affairs Forefront**: "Unlocking The Future: Medicare And Brain-Computer Interfaces",
  DOI 10.1377/forefront.20260318.235606, Crossref publication date **2026-03-20**.
  https://www.healthaffairs.org/content/forefront/unlocking-future-medicare-and-brain-computer-interfaces
  Existence and date are [V] via Crossref. The full text returned HTTP 403. Per search snippets
  only, it argues that iBCIs lack a coverage framework, that Medicare's improved-health-outcomes
  standard differs from FDA's, and that trials focused on environmental control or video games may
  not show medical necessity. Content [UNR].

---

## 10. Is a downstream measurement tool itself a medical device?

| Scenario | Analysis | Status | Label |
|---|---|---|---|
| Software that only **transfers, stores, converts formats, or displays** device data | FD&C §520(o)(1)(D) excludes from "device" software "for transferring, storing, converting formats, or displaying clinical laboratory test or other device data and results … **unless such function is intended to interpret or analyze**" those data. https://www.law.cornell.edu/uscode/text/21/360j | ESTABLISHED | [V] |
| Software that **computes a clinical index/score** used to diagnose, monitor progression, or guide treatment (e.g., "digital independence impairment score" used clinically) | Likely "interpret or analyze", so potentially a device software function (SaMD). The risk class depends on intended use. CDS criteria under §520(o)(1)(E) likely do not fit, since the data are a "signal from … a signal acquisition system". | Needs regulatory determination (513(g) or Pre-Sub) | [INF] |
| Tool used **only in clinical investigations** to collect endpoint data | DHT guidance: V&V for fit-for-purpose applies regardless of device status. If it *is* a device used only for remote data collection, FDA does not intend to otherwise assess design-control compliance. Significant-risk status is settled through a Q-Sub. | ESTABLISHED (guidance) | [V] |
| Tool **qualified as an MDDT COA** | MDDT qualification is about the tool's evidentiary suitability for a context of use, not a marketing authorization. A qualified COA is not by itself a device. | ESTABLISHED | [V] (program) / [INF] |
| Tool is a **component/accessory of the BCI** (e.g., the BCI's own calibration or performance software) | It is part of the sponsor's device and falls under the sponsor's design controls and Enhanced Documentation Level. | ESTABLISHED | [V] (iBCI guidance) / [INF] |
| Tool as a **clinical-investigation electronic system** (eCOA/EDC-like) | Part 11 and the eSystems Q&A apply to records. Device status is separate. | ESTABLISHED | [V] |

**Bottom line [INF]:**
- Measuring and reporting task performance for trial endpoints or RWE, with no diagnostic or
  treatment claim, is most likely **not a device**. It still must be fit-for-purpose and Part
  11-compliant.
- A clinician-facing product that *interprets* the data to monitor disease or adjust therapy (e.g.,
  flag decline in ALS, titrate neuromodulation) may become **device software**.
- NeuroMetric should define its intended use carefully and consider a 513(g) request if it plans
  clinical-decision features.

---

## 11. Summary table: established vs evolving vs needs validation

| Item | Status | Label |
|---|---|---|
| iBCI guidance requirements (endpoint validation, MCID, ≥1-yr follow-up, home use, caregiver safety and ability metrics, Enhanced Documentation Level) | ESTABLISHED (nonbinding guidance) | [V] |
| PFDD Guidance 3 (fit-for-purpose COAs), final Oct 2025, CDRH co-issuer | ESTABLISHED | [V] |
| PFDD Guidance 4 (COA-based endpoints) | EVOLVING (draft 2023) | [V] |
| DHT remote-data-acquisition guidance (Dec 2023) | ESTABLISHED | [V] |
| Part 11 + eSystems Q&A (Oct 2024) | ESTABLISHED | [V] |
| MDDT program; no BCI COA qualified | ESTABLISHED / gap | [V] |
| iBCI-CC consensus (Oct 2026) and Sawyer et al. JNE 2026 MAH-COI-COA framework | EVOLVING (consensus, not a standard) | [V]/[RF] |
| RAPID | EVOLVING (proposed; comments closed 2026-10-13; no final notice found) | [V] |
| TCET | ESTABLISHED but paused for new candidates | [V] |
| Medicare benefit category for iBCI | UNRESOLVED in policy | [INF] |
| NCD 50.1 SGD as analog | ESTABLISHED | [V] |
| State neural-data laws (CO verified; CA, MT, CT from prior knowledge) | EVOLVING patchwork | [V]/[PK] |
| Device status of a neutral measurement tool | Depends on intended use; NEEDS FORMAL DETERMINATION if analytic claims are made | [INF] |
| Any digital-ADL index, CARE-based scoring, or composite as a pivotal endpoint | NEEDS FORMAL VALIDATION | [INF] |
