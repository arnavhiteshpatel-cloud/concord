# EVIDENCE LEDGER

Status of the founder playbook's claims (Playbook B, 27 Nov 2026) after independent checking in
this session, plus key new findings. Labels: [V] verified with source, [CC] company claim, [RF]
research finding, [AE] analyst/third-party estimate, [INF] inference, [HYP] hypothesis, [PK]
prior knowledge not re-verified, [UNR] unresolved. Original labels are kept where a claim could
not be re-checked. Machine-readable detail: `docs/research/ledger_regulatory.csv` (43 rows) and
the CSVs in `docs/research/`. Sources (URLs, access dates) are in the linked research files.

## A. Playbook claims — checked

| # | Playbook claim (label) | Finding | Now | Source file |
|---|---|---|---|---|
| 1 | Neuralink LINK Pivotal Study approved 25 Nov 2026 [V] | Only a company announcement; FDA does not publish IDE approvals; not on ClinicalTrials.gov; ALS only; endpoints not public | **[CC]** (downgraded) | regulatory_landscape.md, clinical_trials.md |
| 2 | RAPID announced Apr 2026, procedural notice 11 Aug 2026 [V] | Confirmed: announced 23 Apr 2026; FR notice 2026-16368 on 11 Aug 2026; comments closed 13 Oct 2026; **still proposed**; admits devices before IDE study start, which likely excludes LINK [INF] | [V] + caveat | regulatory_landscape.md |
| 3 | iBCI-CC 1 Oct 2026: no single existing measure suffices; "shared measurement chain" [V] | Confirmed; wording is hedged ("unlikely … sufficient"); "shared measurement chain" verbatim; responds to a July 2026 CUC report not found publicly | [V] | regulatory_landscape.md |
| 4 | FDA iBCI guidance asks for validated effectiveness endpoint, MCID, ≥1 yr, home use, "caregiver metrics" [V] | Validation "recommended", feasibility studies exempt; caregiver language is about caregiver **safety and ability to assist**, not caregiver burden; Enhanced software documentation level confirmed | [V] with correction | regulatory_landscape.md |
| 5 | NCT07407725 DAI: 60 participants, primary completion Dec 2026, Neuralink collaborator; "registry lists no named PI" | Recruiting; 60; start 8 Jan 2026; primary completion Dec 2026 (est.); **PI is named: Arun Jayaraman**; randomized within-subject crossover; 3 cohorts; comparators Tobii PCEye 5, Jouse+, EMOTIV EPOC X, voice, personal AT, Neuralink N1; outcomes: DAI performance metrics (click accuracy, time to target, errors, trajectory, WPM, % correct characters) + NASA-TLX, SUS, modified COPM, PIADS; secondary ISNCSCI, ALSFRS-R, IRF-PAI GG, ECAS, WHOQOL-BREF; no home-logging outcome | [V], PI claim corrected | clinical_trials.md, collaborators.md |
| 6 | Sponsor feasibility studies list safety as primary [V] | Confirmed (Neuralink PRIME, Synchron COMMAND, Paradromics Connect-One) | [V] | trials.csv |
| 7 | Dohle et al. 2025: 17.9% of iBCI studies report clinical outcomes [RF] | Confirmed (20 of 112) | [RF] | regulatory_landscape.md |
| 8 | Sawyer et al. JNE (10.1088/1741-2552/ae9eee) [V] | Confirmed, published 11 Sep 2026 | [V] | published_bci_functional_measures.md |
| 9 | Health Affairs Forefront Mar 2026 [V] | Exists (10.1377/forefront.20260318.235606, 20 Mar 2026); full text blocked | [V] existence; content [UNR] | regulatory_landscape.md |
| 10 | NSCEB BCI paper Sep 2026 [V] | Confirmed; recommends adding BCIs to RAPID | [V] | regulatory_landscape.md |
| 11 | ONWARD ARC-EX home 510(k) Nov 2025 [V] | Home clearance K251821 (14 Nov 2025) confirmed; original authorization was **De Novo** DEN240014 | [V] corrected | neuromodulation_market.md |
| 12 | NCT06140706 is ONWARD's home study with NASA-TLX, QUEST, GRASSP, CUE-Q, DASH, COPM [V] | Instruments confirmed; study run by **VA Palo Alto** with ONWARD as collaborator; still "not yet recruiting", not updated since Apr 2025 | [V] corrected | neuromodulation_market.md |
| 13 | "Bioness (PoNS), chronic-stroke gait clearance 2026" | Confirmed with longer chain: Bioventus sold Bioness to Accelmed (closed 31 Dec 2024); Helius renamed Solana Company; Bioness acquired PoNS ~Apr 2026; K253061 decision 13 May 2026 | [V] | neuromodulation_market.md |
| 14 | "IpsiHand's maker" | Neurolutions merged into **Kandu, Inc.** (Apr 2025); Kandu registered an RWE study NCT07147881 including Zarit | [V] | prospects.md |
| 15 | Synchron ~$345M, Precision ~$430M, Neuralink $650M Series E [CC] | Not all re-verified; Synchron **paused** second-generation trials Nov 2026 [AE] | [CC]/[AE] | prospects.md |
| 16 | NIH STTR PA-27-102; Phase I $314,363 cap; Phase II $2,095,748 | PA-27-102 exists; due 5 Jan / 5 Apr 2027; IC-specific caps differ (NINDS $700k / $3.0M; NICHD $400k / $2.5M) | [V] corrected | funding.md |
| 17 | SBIR/STTR available | Authority lapsed 1 Oct 2025; NIH expired notices 17 Nov 2025; **reauthorized by P.L. 119-83 (13 Apr 2026) to 30 Sep 2031** | [V] | funding.md |
| 18 | RFA-NS-25-021 "encourages businesses" + UH3 companion | It is not a small-business RFA (implant studies needing IDE; any org); **expired 29 Sep 2026**; companion RFA-NS-25-022 | [V] corrected | funding.md |
| 19 | NOT-NS-26-005 changed key dates | Only added a 15 Jun 2026 date to RFA-NS-25-017/018, which expired 16 Jun 2026 | [V] corrected | funding.md |
| 20 | NSF SBIR Phase I up to $305K; deadlines 4 Mar & 7 Jul 2027; 51% PI rule | 51% rule confirmed; dates/amount see funding.md | [V]/[UNR] per row | funding.md |
| 21 | Jennifer French "coordinator" of iBCI-CC | Organizer; Jessica Kelemen is program manager; Clinical Study Endpoints workgroup co-led by Mariska Vansteensel and Vivek Pinto | [V] corrected | collaborators.md |
| 22 | David McMullen (consensus contributor) | Now at Neuralink | [V] | collaborators.md |
| 23 | Cozad (~1 Feb 2027 registration; $100K grand prize) | Registration open; 2026 grand prize $100k SAFE; healthcare prizes need a Carle Illinois medical student on the team | [V] | funding.md |
| 24 | Apple BCI HID reference [V] | iOS/iPadOS/visionOS 26+ (macOS not listed); HID usage page 0x60 still "Reserved" in USB-IF HUT 1.7; no documented way for third-party apps to read BCI reports | [V] | bci_hid_and_input_standards.md |
| 25 | iOS sandboxing limits cross-app logging [PK] | Confirmed; Screen Time report extensions cannot make network requests | [V] | platform_matrix.md |
| 26 | Per-participant pricing ~$95/participant-month (Jeeva) [CC] | Not re-checked; comparables: OpenClinica $36–45K/yr per study; EDC year-1 $10–50K small studies [AE] | [CC]/[AE] | comparable_pricing.md |
| 27 | Prices $25–75K pilots; $100–400K per study-year; $100–300K/yr maker contracts | Remain **[HYP]**; $100–400K looks high for 2–15-participant feasibility studies | [HYP] | comparable_pricing.md |
| 28 | Concord's intent schema becomes the normalisation layer | Concord is proprietary-labelled, has no degradation simulator; NeuroMetric built clean-room events + an importer | [V] (audit) | concord_reuse_audit.md |

## B. New decision-relevant findings
* **Direct overlap:** the SRAlab DAI (with Neuralink) tests the same digital primitives across
  devices, with psychometric validation and a normative cohort planned [V]. Mount Sinai's
  **Digital IADL** scale (content-validity stage) and the iBCI-CC endpoints work are adjacent
  [RF/V]. Signant acquired Ametris (ex-ActiGraph) 14 May 2026 [V]. Cognixion's ALS trial
  (NCT07871071) uses daily use time as primary endpoint plus Zarit [V].
* No BCI COA is qualified under FDA MDDT [V]. Caregiver burden is almost never registered as an
  endpoint in iBCI trials [V].
* Only 3 companies run active US motor/communication implant studies now [V]; ~5–8 plausible by
  2028 [INF].
* Licensing: PROMIS/Neuro-QoL commercial use needs HealthMeasures licensing ($750 digital review
  per measure; CAT via $18k/yr API) [V]; Zarit exclusively via Mapi [V]; NASA-TLX and PHQ-9 free
  [V]; SUS free with citation [AE]; FIM/MoCA/ASHA-FACS not recommended [V/AE].
* Browser timing: absolute response-time lags of 71–87 ms with SD 8–28 ms across platforms
  (Anwyl-Irvine 2021) [RF] → NeuroMetric claims within-setup comparisons, not ms-accurate
  absolute times.

## C. Things NeuroMetric itself established (this session, simulation/engineering)
See EXPERIMENT_REGISTRY.md — all simulation-derived and labelled synthetic.
