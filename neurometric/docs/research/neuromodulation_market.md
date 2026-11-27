# Neuromodulation and home neuro-rehabilitation: market check for an evidence companion module

Prepared 2026-11-27 for NeuroMetric commercial strategy. All web sources accessed 2026-11-27.
Labels follow `CONVENTIONS.md`: [V] verified against a primary source this session, [CC] company claim
(press release, company site, or trade press relaying one), [RF] peer-reviewed finding, [AE] third-party
estimate, [INF] NeuroMetric inference, [HYP] hypothesis, [PK] prior knowledge not re-verified, [UNR] unresolved.

How the labels were applied here:
- FDA database entries (openFDA 510(k)/De Novo/PMA, FDA 510(k) summary PDFs), ClinicalTrials.gov API v2
  records, SEC filings and payer policy pages are treated as primary sources and labelled [V]. Note that a
  ClinicalTrials.gov record is itself sponsor-entered; [V] means "the registry says this", not "the trial did this".
- News articles that relay a company announcement are labelled [CC] and linked.
- The founder playbook was not found in the repository (searched `/home/user/concord` on 2026-11-27), so the
  playbook claims below are taken from the task brief.

NeuroMetric scope reminder [INF]: NeuroMetric measures function, real-world use and care-partner burden and
packages evidence. It never controls a device or changes stimulation. Every "use case" below assumes read-only
data access (device logs exported by the manufacturer, or separate sensors/questionnaires), never a control link.

---

## 1. Playbook claims vs what was verified

| Playbook claim (as given in brief) | Finding 2026-11-27 | Label / source |
|---|---|---|
| ONWARD received a Nov 2025 510(k) for ARC-EX home use | Confirmed. K251821, decision 2025-11-14, announced 2025-11-17. Indication: transcutaneous spinal cord stimulation "in conjunction with functional task practice in the clinic and with take-home exercises in the home" to improve hand sensation and strength, ages 18-75, chronic incomplete SCI C2-C8; operated at home "by Patients and Persons Providing Assistance". **Nuance the playbook misses:** the 510(k) states no new clinical data were needed ("the information provided in the previously cleared De Novo submission remains valid"). Home effectiveness is therefore not separately demonstrated in the clearance. Original authorization was De Novo DEN240014 (2024-12-19), not a 510(k). | [V] https://www.accessdata.fda.gov/cdrh_docs/pdf25/K251821.pdf ; [V] https://api.fda.gov/device/510k.json?search=applicant:%22ONWARD%22 ; [CC] https://live.euronext.com/en/products/equities/company-news/2025-11-17-onward-medical-receives-fda-510k-clearance-expanding-arc |
| NCT06140706 is ONWARD's home study using NASA-TLX, QUEST, GRASSP, CUE-Q, DASH, COPM | Instruments confirmed: primary NASA-TLX and QUEST 2.0 at 8 weeks; secondary GRASSP, CUE-Q, DASH, COPM at baseline and 8 weeks. **Differences:** lead sponsor is VA Palo Alto Health Care System (investigator-initiated); ONWARD Medical, Inc. is a *collaborator*, not sponsor. Registry status NOT_YET_RECRUITING, n=10 (estimated), estimated start 2025-09-01, last update posted 2025-04-10, status verified 2025-04. The record is stale; actual status unknown. It is a feasibility study of a *video-telehealth* home model, intervention labelled "behavioral". | [V] https://clinicaltrials.gov/study/NCT06140706 |
| "Bioness (PoNS)" | Correct as of April 2026, but the chain is not what the playbook implies. Bioventus sold its Advanced Rehabilitation business (Bioness L300/L360/H200, Vector, BITS) to private-equity firm Accelmed Partners; closed 2024-12-31. The now-independent Bioness Medical, Inc. bought the PoNS product line from Helius (reported April 2026; terms undisclosed). Helius Medical Technologies renamed itself Solana Company (crypto treasury pivot) in 2025. Bioness also bought the assets of Harmonic Bionics (upper-limb rehab robot) in June 2025. | [V] Bioventus 8-K https://www.sec.gov/Archives/edgar/data/1665988/000162828024042266/exhibit991pressrelease-adv.htm ; [V] Bioventus 10-Q https://www.sec.gov/Archives/edgar/data/1665988/000162828025022401/bvs-20250329.htm ; [CC] https://multiplesclerosisnewstoday.com/news-posts/2026/04/14/bioness-medical-acquires-pons-device-used-walking-balance-ms/ ; [CC] https://www.tipranks.com/news/the-fly/helius-medical-announces-corporate-name-change-to-solana-company-thefly ; [CC] https://www.prnewswire.com/news-releases/bioness-medical-announces-acquisition-of-the-assets-and-business-of-harmonic-bionics-302485121.html |
| PoNS "chronic-stroke gait clearance 2026" | Confirmed. K253061, FDA decision letter dated 2026-05-13 (applicant of record "Helius Medical, Inc"), publicly announced by Bioness Medical 2026-06-29. Indication: "treatment of dynamic gait deficit due to chronic symptoms from stroke ... as an adjunct to a supervised therapeutic exercise program in patients 22 years of age and over by prescription". Protocol: 60 min/day, ≥3-4 days/week for 12 weeks, **4 weeks in clinic then 8 weeks at home independently**. Primary endpoint Functional Gait Assessment (FGA). Enrolment discrepancy: 510(k) summary says 152 across 3 trials; Helius/press said 159. FGA change 5.18 pts active vs 3.31 sham (510(k) summary); press reports 5.37. | [V] https://api.fda.gov/device/510k.json?search=k_number:K253061 ; [V] https://www.accessdata.fda.gov/cdrh_docs/pdf25/K253061.pdf ; [CC] https://www.neurologylive.com/view/fda-clears-pons-device-stroke-rehabilitation-expanding-neurostimulation-beyond-ms-indication |
| IpsiHand by Neurolutions | Neurolutions merged with Kandu Health in April 2025 to form Kandu, Inc. (with $30M new funding reported); Neurolutions, Inc. is now a wholly owned subsidiary. IpsiHand authorized via De Novo DEN200046 (2021-04-23). | [V] https://api.fda.gov/device/510k.json?search=applicant:%22Neurolutions%22 ; [CC] https://www.medtechdive.com/news/kandu-health-merges-neurolutions-bci/744824/ ; [V] subsidiary wording quoted in Anthem policy DME.00052 https://www.anthem.com/medpolicies/abcbs/active/mp_pw_e003193.html |
| MicroTransponder Vivistim | Company renamed **Mobia Medical, Inc.** effective 2026-02-24; Nasdaq IPO (MOBI) priced 2026-05-07/08 at $15, ~$150M raised. Vivistim PMA P210007 (2021-08-27); 2024-2026 supplements are manufacturing/supplier changes, no new indication found. | [V] https://www.accessdata.fda.gov/scripts/cdrh/cfdocs/cfpma/pma.cfm?ID=P210007 ; [CC] https://www.biospace.com/press-releases/microtransponder-announces-corporate-name-change-to-mobia-medical ; [CC] https://www.renaissancecapital.com/IPO-Center/News/118869/Nerve-stimulation-device-maker-Mobia-Medical-prices-IPO-at-$15-the-midpoint |

Other material changes found that a 2025-era playbook would not have:
- Flow Neuroscience FL-100 (home tDCS, depression) received FDA **PMA** P230024 on 2025-12-08 [V] (openFDA PMA query, https://api.fda.gov/device/pma.json?search=applicant:%22Flow%20Neuroscience%22). Neurolief ProlivRx received PMA P250010 on 2025-12-31 [V] (https://api.fda.gov/device/pma.json?search=applicant:%22Neurolief%22).
- BrainQ's EMAGINE 2.0 pivotal (NCT06386874) was **terminated for poor accrual** (completion 2026-04-07, n=62) [V] https://clinicaltrials.gov/study/NCT06386874.
- DIH Holding US (parent of Hocoma and Motek) was delisted from Nasdaq, trading suspended 2025-11-07 [CC/8-K] https://www.streetinsider.com/SEC+Filings/Form+8-K+DIH+HOLDING+US%2C+INC.+For%3A+Nov+05/25565519.html.
- A major commercial payer (Anthem, DME.00052, reviewed 2026-08-13) classes BCI rehabilitation devices including IpsiHand as investigational, citing lack of evidence on real-world arm use, daily-living independence and durability [V] https://www.anthem.com/medpolicies/abcbs/active/mp_pw_e003193.html. This is the clearest documented demand signal for NeuroMetric's category found in this session.

---

## 2. Company profiles

Each profile: status and ownership; regulatory; clinical evidence; home-use capability; product capabilities;
outcome measures used in trials; implications for a NeuroMetric evidence companion module.
Headquarters locations in the headings are [PK] (not re-verified) unless they appear in a cited source.

### 2.1 ONWARD Medical N.V. (Eindhoven NL / Lausanne CH / US) — ARC-EX, ARC-IM, ARC-BCI

- **Status/ownership:** Listed (Euronext Brussels/Amsterdam; ticker ONWD) [CC]. H1 2026: revenue and other income EUR 4.2M; ARC-EX sales EUR 3.4M; 159 ARC-EX systems sold or supplied via paid evaluation in H1 (up 430% y/y); >130 US clinics; operating loss EUR 23.3M; cash EUR 81.5M [CC] https://www.trivano.com/persbericht/onward-medical-reports-first-half-2026-results-with-strong-product-revenue-growth-and-continued-progress-across-arc-therapy-pipeline-758795.html. Q1 2026 release reported an additional ~EUR 40M equity raise and cash runway to Q1 2028 [CC] https://www.biospace.com/press-releases/onward-medical-reports-first-quarter-2026-results-with-strong-commercial-momentum-and-key-clinical-milestones. A reported USD 50M BlackRock debt facility [UNR] (aggregator only: https://briefglance.com/companies/onward-medical-n-v/pulses/76117).
- **Regulatory:** ARC-EX De Novo DEN240014 (2024-12-19), home-use 510(k) K251821 (2025-11-14) [V]. ARC-EX also commercially available in Europe [CC]. ARC-IM and ARC-BCI are investigational [CC].
- **Clinical evidence:** Up-LIFT pivotal (NCT04697472; n=65; completed 2022): primary = SAE incidence and "number of participants with change in upper extremity strength and function"; secondary = superiority of FTP+ARC vs FTP alone [V] https://clinicaltrials.gov/study/NCT04697472. The detailed composite (GRASSP strength/sensation, prehension, CUE-T etc.) was published in Nature Medicine 2024 [PK, not re-verified]. LIFT Home Study (NCT05284201; n=17; completed 2022): primary = all AEs; secondary = "extended use of the LIFT System at home" [V] https://clinicaltrials.gov/study/NCT05284201. Pathfinder2 cited by ONWARD as supporting the home clearance [CC].
- **Pipeline trials:** Empower BP pivotal for ARC-IM (NCT07147296; n=60 est.; recruiting; primary = proportion achieving change in hypotension domain of ADFSCI short-form, seated SBP elevation, serious adverse device effects) [V] https://clinicaltrials.gov/study/NCT07147296. First participant implanted Q1 2026 at Craig Hospital [CC] https://www.finanznachrichten.de/nachrichten-2026-02/67607655-onward-medical-nv-onward-medical-announces-first-participant-enrolled-in-global-pivotal-study-evaluating-arc-im-system-to-address-blood-pressure-inst-399.htm. ARC-BCI (with Clinatec/EPFL) participant counts conflict between FY2025 and Q1 2026 releases (FY2025 says seven participants) [CC, conflicting]. EPFL/.NeuroRestore academic trials of "ARC-BSI" (brain-spine interface): NCT05665998 (cervical SCI; GRASSP, ARAT, CUE-T) and NCT07610850 (chronic stroke; FMA-LE/UE, 10MWT, 6MWT, TUG, ARAT, BBT, SS-QOL, PIADS, SIS, GAS, PGIC) [V] https://clinicaltrials.gov/study/NCT05665998 , https://clinicaltrials.gov/study/NCT07610850.
- **Home use:** Cleared; first home systems sold to individuals in H1 2026 including within the US VA community [CC]. A home app (MyARCEX) exists; home programming is restricted to clinician-predefined settings [V] (K251821 summary). Reimbursement support program for the "ARC-EX Personal System for home use" is run by PRIA Healthcare; requires prescription and Letter of Medical Necessity; explicitly no coverage guarantee [CC] https://www.onwd.com/wp-content/uploads/2026/08/ARC-EX-Reimbursement-Support-Program-Overview.pdf. No ARC-EX-specific HCPCS code was found [UNR].
- **Outcome measures seen:** GRASSP, CUE-T/CUE-Q, ARAT, DASH, COPM, NASA-TLX, QUEST 2.0, ISNCSCI, SCIM III (via collaborators), ADFSCI (autonomic), seated BP tests; for ARC-BSI stroke: PIADS, GAS, PGIC, SIS, SS-QOL.
- **Implications [INF]:** Highest-fit neuromodulation prospect. (1) The home indication rests on clinic data; payers and VA prescribers will want home adherence, home-exercise completion and functional carry-over data, which ONWARD's own app may log only partially (unknown, [UNR]). (2) The VA telehealth study already chose NASA-TLX, QUEST, COPM, i.e., burden + satisfaction + participation, which maps directly onto NeuroMetric's module. (3) NeuroMetric must not touch stimulation parameters; position as a neutral, device-agnostic evidence layer that ONWARD can cite in letters of medical necessity and payer dossiers. (4) Risk: ONWARD may build in-house on MyARCEX; ask how they plan to evidence home benefit.

### 2.2 Bioness Medical, Inc. (Valencia CA; owned by Accelmed Partners) — PoNS, L300 Go, L360, H200, Vector, BITS, Harmonic upper-limb robot

- **Status/ownership:** Divested by Bioventus to Accelmed Partners, closed 2024-12-31, USD 45M total consideration incl. earn-outs [V] SEC links above. Bioness describes itself as an independent neuro-rehab company; acquired Harmonic Bionics assets 2025-06-18 ("first acquisition since becoming independent"; robot to be sold "upon regulatory clearance") [CC]; acquired PoNS product line ~April 2026 (one report calls it the third acquisition under Accelmed; the second was not identified, [UNR]) [CC].
- **Regulatory:** PoNS De Novo DEN200050 (2021-03-26, MS gait) and K253061 (2026-05-13, chronic stroke gait) [V]. L300 Go / L360 / H200 / StimRouter 510(k)s 2011-2022 [V] https://api.fda.gov/device/510k.json?search=applicant:%22Bioness%22. Note StimRouter was not in the Accelmed asset list [V] (Bioventus 8-K lists L100, L300 Go, L360, H200, Vector, BITS).
- **Clinical evidence (PoNS stroke):** Stroke Registrational Program = pivotal double-blind sham RCT (n=64), pivotal open-label single arm (n=38), investigator-initiated sham RCT (n=50); primary FGA; durability at week 24 (89.7% retained ≥70% of week-12 FGA) [V] K253061 summary. Registry records: NCT06336720 (single arm, n=30) and NCT06470009 (n=60) list only "primary safety endpoints" in the registry [V] https://clinicaltrials.gov/study/NCT06470009. MS: Therapeutic Experience Program NCT05437276 with *adherence* as primary outcome [V]; MS registry NCT06930339 (n=150; self-reported symptom change) [V].
- **Home use:** PoNS protocol is 4 weeks supervised in clinic then 8 weeks independent home use; human-factors validation covered clinic and home environments; IEC 60601-1-11 home-healthcare testing [V] K253061 summary.
- **Outcome measures seen:** FGA, DGI, SOT/Berg balance (TBI programs), adherence, 10MWT, BBS (L300 vs AFO NCT01138995), 2MWT, BSW satisfaction questionnaire, Brief Pain Inventory (StimRouter).
- **Implications [INF]:** Strong fit. The 8-week independent home phase is exactly where clinicians and payers lose visibility (adherence, real-world walking, falls, care-partner load). PoNS coverage has historically been weak [PK]; Bioness is a PE-backed roll-up building a portfolio (FES + robotics + PoNS + VR) and may want one cross-product outcomes layer. Ask whether the PoNS controller logs sessions and whether those logs leave the device.

### 2.3 Helius Medical Technologies → Solana Company (formerly PoNS developer)

- Renamed Solana Company (keeps HSDT ticker) after pivoting away from neurotech in 2025 [CC] https://www.tipranks.com/news/the-fly/helius-medical-announces-corporate-name-change-to-solana-company-thefly. PoNS assets sold to Bioness [CC]. **Not a prospect.** Remove from target lists; route PoNS conversations to Bioness.

### 2.4 Kandu, Inc. (formerly Neurolutions + Kandu Health) — IpsiHand Upper Extremity Rehabilitation System (non-invasive EEG BCI + powered hand orthosis)

- **Status/ownership:** Merger announced 2025-04-14; CEO from Neurolutions; $30M new funding reported [CC] https://www.fiercebiotech.com/medtech/stroke-tech-developers-kandu-neurolutions-combine-30m-new-funding.
- **Regulatory:** De Novo DEN200046 (2021-04-23), product code QOL [V].
- **Clinical evidence:** Fully remote home RCT NCT05965713 (n=109 actual; completed 2025-09-12; NICHD-funded; primary UEFM at 12 weeks) [V] https://clinicaltrials.gov/study/NCT05965713. Results presented Feb 2026 (ISC) and published (Leuthardt 2026, *Stroke: Vascular and Interventional Neurology*) [CC] https://www.massdevice.com/kandu-trial-positive-outcomes-ipsihand-bci-system/. Earlier single-arm NCT04338971 (FMA-UE, AMAT) [V].
- **Payer position:** Anthem DME.00052 (last review 2026-08-13) considers BCI rehab devices incl. IpsiHand investigational; criticises differential attrition, no sham/blinding, no post-treatment follow-up, no independent replication, and says activity-level outcomes, *real-world arm use* and *daily-living independence* have not been consistently shown [V] https://www.anthem.com/medpolicies/abcbs/active/mp_pw_e003193.html.
- **Planned RWE:** NCT07147881 prospective real-world evidence study (n=100; status NOT_YET_RECRUITING, est. start 2025-09-01, last update 2025-08; record stale): primary FM-UE; secondary Barthel Index, **Zarit Burden Interview (care-partner burden)**, PSFS, EQ-5D-5L, follow-up to 24 months [V] https://clinicaltrials.gov/study/NCT07147881.
- **Home use:** Designed for home use; the RCT was fully remote [V].
- **Implications [INF]:** Top-tier prospect. The payer has written the gap down in public, and Kandu has already registered an RWE study that includes care-partner burden. NeuroMetric's offer: independent, blinded-assessor-compatible remote functional assessment, objective real-world arm-use telemetry (wearable accelerometry; read-only), ZBI capture, and payer-ready packaging. Independence from the manufacturer is the selling point the Anthem critique implicitly asks for.

### 2.5 Mobia Medical, Inc. (formerly MicroTransponder; Austin TX) — Vivistim Paired VNS System (implanted)

- **Status/ownership:** Renamed 2026-02-24; Nasdaq: MOBI since 2026-05-08; IPO ~USD 150M; 2025 sales ~USD 32M; >1,000 systems implanted (700 in 2025); going-concern language in filings; 83 sales staff end-2025 [CC] https://xtalks.com/mobia-medical-ipo-raises-150m-for-stroke-recovery-device-4877/ , https://www.medtechdive.com/news/mobia-medical-plans-ipo/819292/.
- **Regulatory:** PMA P210007 (2021-08-27), Class III, Breakthrough [V].
- **Payer:** "Most commercial payors view Vivistim as experimental or investigational and require prior authorization"; CMS assigned a new-technology APC after pass-through expired [CC, relayed from IPO filing coverage].
- **Clinical evidence and registries:** VNS-REHAB pivotal NCT03131960 (n=108; FMA-UE, WMFT) [V]; GRASP registry NCT05301140 (n=1,000 est.; recruiting; FM-A, WMFT, SIS, MAL; 6 months) [V] https://clinicaltrials.gov/study/NCT05301140; VNS-REHAB At-Home post-market NCT05691023 (n=50; primary **in-home therapist time**; secondary FMA; est. primary completion 2026-12-31; single site Moxie OT) [V] https://clinicaltrials.gov/study/NCT05691023. SCI feasibility NCT05601661 (UTHealth; TRI-HFT, GRASSP-like, SCIM, SCI-QOL) [V].
- **Home use:** Patients can self-initiate 30-minute stimulation at home with a magnet [CC]; therapist-directed home delivery is under study [V NCT05691023].
- **Implications [INF]:** Good fit and fundable (post-IPO). A 1,000-patient registry using clinic-administered FMA/WMFT plus MAL and SIS is ripe for a remote, standardized real-world-use add-on (MAL is self-report; objective arm use would strengthen payer files). Caution: implanted device, Class III — NeuroMetric data must be clearly non-device, read-only.

### 2.6 Synchron, Inc. (New York / Melbourne) — Stentrode endovascular BCI
Profiled in `prospects.md` (BCI segment). Neuromodulation-relevant point: November 2026 voluntary pause of second-generation Stentrode trials over a lead performance issue, not FDA-mandated [CC] https://www.medicaldaily.com/synchron-pauses-wireless-brain-implant-trials-481309.

### 2.7 BrainQ Technologies (Israel) — BQ / Q Therapeutic System (frequency-tuned low-intensity EMF, home use)

- CE mark for BQ 2.0 (Jan 2025) and FDA Breakthrough designation [CC] https://prnewswire.com/news-releases/brainq-achieves-ce-mark-for-its-breakthrough-therapy-for-reducing-disability-following-stroke-and-welcomes-stacey-pugh-as-chairman-of-the-board-302349118.html. EMAGINE (NCT05044507; n=100) did not reach statistical significance on mRS [CC]. EMAGINE 2.0 pivotal NCT06386874 **terminated: poor accrual** (n=62; completion 2026-04-07) [V]. Investigator studies continue at Burke (NCT06979466), University of Florida (NCT07095920) and Kessler (NCT07499310; not yet recruiting) [V].
- **Outcome measures:** mRS (ordinal shift), FMA-UE, SIS-16 and SIS hand domain, BBT, 10MWT, 9HPT, FAC, EQ-5D-5L, GDS; SCI study used GRASSP, CUE-T, SCIM III, SCI-QOL.
- **Implications [INF]:** Regulatory path uncertain after pivotal termination; budget likely constrained. Tier 3 watch; possible fit if they pivot to chronic-stroke home RWE.

### 2.8 Flow Neuroscience AB (Malmö SE) — FL-100 home tDCS headset (depression)

- PMA P230024 approved 2025-12-08; design supplement S001 2026-07-14 [V]. Pivotal "Empower" home tDCS NCT05202119 (n=174; HDRS-17) [V]. US launch reported as planned for 2026, price target USD 500-800 [CC] https://psychiatrictimes.com/view/fda-approves-first-at-home-brain-stimulation-device-for-treatment-of-depression; launch completion not verified [UNR].
- **Implications [INF]:** Outside NeuroMetric's functional-motor/communication core. Adjacent only for adherence/home-use telemetry and care-partner burden. Tier 3.

### 2.9 Fisher Wallace Laboratories (New York) — cranial electrotherapy stimulator

- Trials: NCT05384041 (MDD; BDI-II, PHQ-9, QIDS), NCT07093736 (anxiety; BAI) [V]. A company-hosted annual report copy (fiscal 2025) states an anxiety 510(k) submission in April 2026 and a planned depression PMA by end-2026 [UNR — document provenance unclear]. No FDA decision found in openFDA [V-negative].
- **Implications:** Psychiatric indication, consumer-style marketing. Not a fit. Excluded.

### 2.10 NeuroOne Medical Technologies (Eden Prairie MN; Nasdaq NMTC)

- 510(k)s for Evo sEEG, cortical electrodes and OneRF ablation (2019-2025) [V]. RWE registry for OneRF in epilepsy NCT07546253 (seizure outcomes) [V].
- **Implications:** Diagnostic/ablation in epilepsy; no home functional-rehab component. Not a fit. Excluded.

### 2.11 Cala Health, Inc. (San Mateo CA) — Cala Trio / Cala kIQ / kIQ Plus (wrist TAPS for tremor)

- kIQ Plus 510(k) K253587 (2026-03-17) for action hand tremor in ET and PD [V] https://www.accessdata.fda.gov/scripts/cdrh/cfdocs/cfPMN/pmn.cfm?ID=K253587. Reported ~USD 50M raise April 2026 tied to launch and Medicare reimbursement [CC] https://media.startuphealth.com/p/cala-health-secures-50m-to-scale-wearable-tremor-therapy-startup-health-insights-week-of-apr-28-2026.
- Trials: RWE study NCT05540626 (n=276; tremor power from device sensors; BF-ADL) [V]; NCT03597100 (TETRAS, BF-ADL, device kinematics) [V].
- **Home use:** Fully home, and the device already measures tremor kinematics itself [V registry outcomes].
- **Implications [INF]:** Cala already has strong built-in telemetry. NeuroMetric's value would be limited to independent ADL/participation and care-partner measures. Tier 2, moderate fit.

### 2.12 electroCore, Inc. (Rockaway NJ; Nasdaq ECOR) — gammaCore nVNS, Quell

- Q3 2026 net sales USD 9.7M (+12%); VA is the main Rx channel (~200 VA facilities purchasing as of Q1 2026) [CC] https://finviz.com/news/415846/electrocore-announces-third-quarter-2026-financial-results , https://investor.electrocore.com/news-releases/news-release-details/electrocore-announces-first-quarter-2026-financial-results. 510(k)/De Novo history 2017-2021 [V].
- Trials are headache/migraine-centric (migraine days, HIT-6, EQ-5D) [V]; investigator studies in PTSD (NCT07523685), stroke and SAH [V].
- **Implications:** Pain/headache, not function. Tier 3; possible PTSD/TBI adjacency only.

### 2.13 Myomo, Inc. (Burlington MA; NYSE American MYO) — MyoPro myoelectric elbow-wrist-hand orthosis

- Q3 2026 revenue record USD 12.3M (+22%); FY2026 guidance USD 46-47M; Medicare Part B was 51% of Q1 2026 revenue [CC] https://finviz.com/news/419501/myomo-reports-third-quarter-2026-financial-and-operating-results , https://www.businesswire.com/news/home/20260507836938/en/myomo-reports-first-quarter-2026-financial-and-operating-results/.
- Regulatory: 510(k) K062631 (2007, Myomo e100) is the only Myomo entry in openFDA [V]; MyoPro's current regulatory basis not re-verified [PK].
- Trials: retrospective DASH study NCT05575674; outcome-measures study NCT04900896 (strength, ROM, QoL); NCT02544672 (FMA-UE, MAS, BBT) [V].
- **Implications [INF]:** Home-use daily-wear device with Medicare benefit category; needs ongoing documentation of use and functional benefit for O&P billing and payer appeals. Good fit for real-world-use telemetry + DASH/COPM capture. Tier 2 (need exists but they are already reimbursed).

### 2.14 Motus Nova (Atlanta GA) — Hand Mentor / Foot Mentor home robotic therapy

- No ClinicalTrials.gov sponsor records and no openFDA applicant hits for "Motus Nova" [V-negative]. Home stroke robotic rehab with remote therapist monitoring [PK]. Tier 3 pending basic verification.

### 2.15 Kinestica (Ljubljana SI) — Bimeo (upper-limb home/clinic sensor-based rehab)

- No registry or FDA hits; Bimeo described as sensor-based upper-limb rehab [PK]. Tier 3.

### 2.16 Bionik Laboratories (Toronto / Watertown MA) — InMotion arm/hand robots

- An undated company update claims ~450 InMotion installations worldwide [CC, undated, UNR]. No 2026 corporate status confirmed [UNR]. Clinic-based, not home. Tier 3.

### 2.17 Hocoma (Volketswil CH; part of DIH) — Lokomat, Armeo

- Hocoma states it is part of DIH Medical group [CC] https://www.hocoma.com/us/solutions/lokomat/software/. DIH Holding US delisted from Nasdaq Nov 2025 after MVLS, bid-price and late-filing deficiencies; said needed capital may be unavailable [CC/8-K]. Clinic robotics; device-generated performance reports already exist. Burke-Hocoma study NCT03555825 (FMA-UE, BBT, SIS, SF-36) [V]. Tier 3 (financial distress, clinic-only).

### 2.18 Saebo, Inc. (Charlotte NC) — SaeboFlex, SaeboGlove, SaeboStim, SaeboVR

- No 2026 news found; older Kessler studies (NCT00489580: grip, ARAT, FMA, SIS) [V]. Home orthoses and NMES [PK]. Tier 3.

### 2.19 Tyromotion GmbH (Graz AT) — Amadeo, Diego, Pablo, Myro

- Industry listing only; no 2026 news found [AE]. Pablo used in at-home/daily-life studies (e.g., NCT03294187 Zurich, MAL-14 amount of use, FMA-UE, ARAT, EQ-5D-5L) [V]. Tier 3 (possible EU partner for sensor-based home assessment).

### 2.20 Harmonic Bionics (Austin TX)

- Assets acquired by Bioness Medical 2025-06-18; robot not yet FDA-cleared at the time [CC]. Shirley Ryan study NCT05251077 (UE-FMA, ARAT) [V]. Treat as part of Bioness.

### 2.21 Other home neuro-rehabilitation / neuromodulation companies noted

| Company | Device | Status found | Fit |
|---|---|---|---|
| Neurolief (IL) | Relivion (migraine), ProlivRx (depression) | PMA P250010 2025-12-31 [V] | Psychiatric/pain; not a fit |
| g.tec medical engineering (AT) | recoveriX (EEG BCI + FES stroke rehab), clinic franchise | CE-marked per company [PK]; no FDA clearance for recoveriX found [V-negative: openFDA lists only amplifiers, cortiQ, g.Estim]. Trials: NCT07537530 (10MWT, TUG, MAS), NCT06940635 (GUSS, BIAS-R, COAST, FMA-UE, NHPT, BBT, EQ-5D-3L), NCT06690931 PD (MDS-UPDRS III, PDQ, TUG, 10MWT) [V] | Moderate (EU clinics, BCI-rehab evidence) |
| Phantom Neuro (Austin TX) | Phantom X implanted EMG sensor for prosthesis control | Trial NCT07325708 measures **at-home wear duration** and **at-home IMU limb-usage pattern** [V] | Good conceptual fit (home real-world use); see prospects |
| Cognixion (Santa Barbara CA) | Cognixion ONE / Axon-R AR-BCI | See prospects; trial uses daily use time and Zarit | High |
| EPFL / .NeuroRestore / CHUV | ARC-BSI (with ONWARD/Clinatec) | Academic trials with PIADS, GAS, PGIC | Research customer |

---

## 3. Outcome measures by company (from registry records unless noted)

| Company / program | Motor / function | Participation / goal | Use / adherence | Burden / workload | Satisfaction / AT impact | QoL / global |
|---|---|---|---|---|---|---|
| ONWARD ARC-EX (Up-LIFT, VA home NCT06140706, EPFL UP2) | GRASSP, CUE-T / CUE-Q, ARAT, DASH, grasp/pinch force, ISNCSCI | COPM | "extended use at home" (LIFT Home) | NASA-TLX | QUEST 2.0 | — |
| ONWARD ARC-IM (Empower BP) | — | — | — | — | — | ADFSCI hypotension domain; seated SBP |
| EPFL ARC-BSI stroke | FMA-LE/UE, 10MWT, 6MWT, TUG, ARAT, BBT, CMSA, MAS | GAS | — | — | PIADS | SS-QOL, SIS, PGIC |
| Bioness PoNS | FGA (primary), DGI, SOT, Berg | — | adherence (MS TEP primary) | — | — | self-reported symptom change (MS registry) |
| Bioness L300 | 10MWT, 2MWT, BBS | — | — | — | user satisfaction, BSW | — |
| Kandu IpsiHand | FMA-UE (primary), AMAT, ARAT/BBT (investigator) | PSFS | — | **Zarit Burden Interview** (RWE) | — | Barthel, EQ-5D-5L |
| Mobia Vivistim | FMA-UE, WMFT | — | MAL; in-home therapist time | — | — | SIS |
| BrainQ | FMA-UE, BBT, 9HPT, 10MWT, FAC, GRASSP, CUE-T | — | — | — | — | mRS, SIS-16, EQ-5D-5L, GDS, SCI-QOL |
| Myomo | FMA-UE, DASH, BBT, MAS, strength/ROM | — | — | — | OPUS satisfaction (investigator) | QoL rating |
| Cala | tremor power (device), TETRAS, UPDRS-III | — | device usage | — | — | BF-ADL |
| g.tec | 10MWT, TUG, FMA-UE, NHPT, BBT, MDS-UPDRS III | — | — | — | — | EQ-5D-3L, PDQ |
| Phantom Neuro | ACMC, targeted BBT, gesture accuracy | — | **at-home wear duration; IMU limb use** | — | satisfaction, intuitiveness | — |
| Flow / Fisher Wallace / electroCore | (psychiatric/pain scales: HDRS-17, BDI-II, BAI, migraine days, HIT-6) | — | — | — | — | EQ-5D |

Pattern [INF]: clinic-administered impairment scales (FMA, GRASSP, FGA) dominate primary endpoints. Real-world use,
participation (COPM/GAS/PSFS), care-partner burden (ZBI) and AT-impact scales (PIADS/QUEST) appear mainly as
secondary or investigator-initiated measures, and almost never with objective home telemetry. That is the gap.

---

## 4. Implications for a NeuroMetric evidence companion module [INF unless labelled]

1. **Lead with payer-documented gaps, not technology.** The Anthem BCI-rehab policy [V] and Vivistim's commercial-payer
   position [CC] both say the missing evidence is real-world use, daily-living independence and durability. A module
   that captures these remotely, with assessor independence from the manufacturer, answers the stated objection.
2. **Home phases created by recent clearances are the wedge.** ARC-EX home (K251821, no new clinical data) [V] and PoNS
   stroke (8 of 12 weeks at home) [V] each create a period in which the manufacturer has little standardized evidence.
3. **A minimum common measure set** that would cover most profiled programs [HYP]: COPM or GAS (participation),
   QUEST 2.0 and PIADS (AT impact), NASA-TLX (workload), ZBI (care-partner burden), EQ-5D-5L, plus objective
   device-agnostic real-world-use metrics (wear time, active-use minutes, task-specific arm/gait use from wearables).
   Condition-specific anchors (FMA-UE, GRASSP, FGA, CUE-Q) would be imported from the sponsor's clinic data, not re-administered.
4. **Telemetry posture:** read-only ingestion of device logs (session counts, adherence) where the manufacturer exports
   them; otherwise independent wearables. Never write-back. Several devices already self-measure (Cala tremor power,
   Hocoma reports), so the value there is independence and harmonisation, not raw sensing.
5. **Regulatory framing to test:** whether sponsors want NeuroMetric outputs as (a) exploratory/secondary endpoints in IDE
   or post-market studies, (b) registry add-ons (Vivistim GRASP, IpsiHand RWE), or (c) payer dossiers only. Each implies a
   different validation burden (FDA COA qualification vs. payer-acceptable RWE) [HYP].
6. **Competitive watch:** Shirley Ryan AbilityLab + Neuralink are building a "digital independence" COA (NCT07407725) [V];
   the iBCI Collaborative Community has endpoints and user-priorities working groups [CC]. NeuroMetric should engage
   these as standard-setters rather than compete with a proprietary scale.

---

## 5. Unresolved items

- Actual recruitment status of NCT06140706 (registry stale since April 2025) [UNR].
- Whether ONWARD's MyARCEX app logs and exports home session data [UNR].
- Bioness's second acquisition under Accelmed; PoNS deal date and terms [UNR].
- Kandu's RWE study NCT07147881 real start date (registry still "not yet recruiting") [UNR].
- Myomo MyoPro regulatory basis; Motus Nova, Kinestica, Bionik, Saebo, Tyromotion corporate status in 2026 [UNR/PK].
- Medicare treatment of BCI and home neuromodulation: one search result reported that CMS paused new TCET candidates in favour
  of a "RAPID" pathway; not verified against a CMS primary document [UNR] (context: https://www.healthaffairs.org/content/forefront/unlocking-future-medicare-and-brain-computer-interfaces).
