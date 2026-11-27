# STTR structure: company vs research institution, PI options, IP, and the student founder's role

> **DRAFT for discussion with a prospective faculty PD/PI, UIUC Sponsored Programs, the Office of
> Technology Management (OTM) and counsel. Not legal advice.** Prepared 2026-11-27. No
> institution, faculty member or clinical site has agreed to anything. Labels per
> `docs/research/CONVENTIONS.md`; most rules come from `docs/research/funding.md` (fetched
> 2026-11-27) and are marked [V] there. [PK] items must be confirmed in the current NOFO, the SBA
> SBIR/STTR Policy Directive and university policy before anyone relies on them.

---

## 1. Rules that shape the structure

| Rule | NIH STTR (PA-27-102) | NIH SBIR (PA-27-100) | NSF SBIR/STTR (NSF 26-510) | Source |
|---|---|---|---|---|
| Who receives the award | The small business, "regardless of the PD/PI employment" | Small business | Small business | [V] funding.md §3.1 |
| PD/PI employment | PD/PI may be employed by the small business **or by the single partnering non-profit research institution**, with a formal appointment with or commitment to the applicant company (need not be paid); **≥ 10% effort** for each PD/PI | PD/PI "should be primarily employed by the small business" [V]; > 50% at award [PK] | PI **≥ 51% employed by the company** at award and throughout, for **both SBIR and STTR**; outside employment > 19.6 h/week conflicts; STTR co-PI from the RI | [V] funding.md §3.1 |
| Minimum work split | **≥ 40% small business; ≥ 30% one partnering non-profit research institution** | Phase I ≈ 67% company | RI minimum not stated in the solicitation [V]; statutory 30% [PK] | [V] funding.md §3.1 |
| Ownership | > 50% owned by US citizens or permanent residents (or by qualifying VC/PE firms) | Same | Similar [PK] | [V] funding.md §3.1 |
| IP between company and RI | **Allocation-of-rights (IP) agreement required before award** (SBA Policy Directive) | Normal university rules | STTR IP agreement required [PK]; NSF takes no equity [V] | [PK] funding.md §3.1 |
| Foreign subawards | Not allowed | Not allowed | — | [V] funding.md §2 |
| HHS application cap | ≤ 9 new/resubmitted Phase I, Fast-Track and Direct-to-Phase II applications per company per fiscal year | Same | — | [V] NOT-OD-26-090 |

**Consequence [INF].** NIH STTR is the only federal route in the next 12 months where a
university or Carle faculty member can lead while staying at their institution, and where a
part-time student founder can contribute without being the PI. NSF is a poor first fit unless a
founder or hire can be ≥ 51% employed by the company.

---

## 2. Proposed work split (Phase I)

### 2.1 Who does what
| Work package | Performed by | Why there |
|---|---|---|
| Software engineering of the battery, event model, scoring pipeline, browser app, home agent (Tier 1) | **Company** | Company-owned product; founder and engineer |
| Bench timing rig and per-device lag/precision profiles (Aim 1a) | **Company** (rig) with RI lab access | Engineering verification, no participants |
| Simulated-decoder harness, computational studies, analysis-code freezing, simulated dry runs | **Company** | Exists in the company code base |
| Accessibility audit, security testing, Part 11-oriented documentation | **Company** (with external vendors) | Product quality |
| Recruitment, consent, data collection (Stages 1–5), participant payments | **Research institution** under the PD/PI | IRB jurisdiction; independence; founder COI |
| Confirmatory statistical analysis and SAP ownership | **Research institution** (PD/PI + biostatistician) | COI plan: founder does not run confirmatory analyses |
| Data custody of identifiable and pseudonymised participant data | **Research institution** | DMS plan; COI plan |
| Clinical advice and AT-user recruitment | RI clinical co-investigator; `[CLINICAL SITE]` via the RI or a separate subcontract | Only **one** partnering RI counts toward the 30% (the NOFO speaks of "the single, 'partnering' non-profit research institution" [V]); other organisations are ordinary subcontractors/consultants [PK] |

### 2.2 Proposed percentages
From the draft budget (`BUDGET.md` §2): the company performs about **51%** and the partner RI about
**49%** of the work, measured as each party's share of total costs excluding the fee [PK: confirm
the SBA measurement basis]. Both statutory minimums (≥ 40% / ≥ 30%) are met with a margin, so a
moderate rebudget (for example a higher university F&A rate than assumed) does not break the rule.
Re-check the split each time the budget changes.

### 2.3 Choice of partner research institution
| Option | For | Against / to check |
|---|---|---|
| **UIUC** (candidate PD/PI in Bioengineering / Carle Illinois; see `docs/research/collaborators.md` #2) | IRB, OTM and sponsored-programs infrastructure; founder's campus; existing draft IRB materials target UIUC OPRS | UIUC F&A rate [UNR]; OTM IP terms; COI rules for faculty with equity |
| **Carle Foundation Hospital / Carle Health** | Direct access to ALS, SCI and stroke patients and AT clinicians | Must qualify as a non-profit research institution [PK]; Carle research request and reliance process [V route in `CLINICAL_VALIDATION_PLAN.md` §2.10]; can instead be a subcontract under UIUC |
| Shirley Ryan AbilityLab (SRAlab) | Strongest scientific fit (DAI study) | Northwestern IRB oversight under an MOU [V]; Neuralink is a collaborator on the DAI study, which raises data-rights and confidentiality questions; no contact made |

Recommendation [INF]: UIUC as the single partnering RI, with any Carle recruitment run through
the UIUC protocol and the UIUC–Carle reliance route.

---

## 3. PD/PI options

| Option | Description | NIH STTR | NSF | Assessment [INF] |
|---|---|---|---|---|
| **A. Faculty PD/PI at the RI (recommended)** | A UIUC (or Carle) faculty member is the contact PD/PI, keeps their university employment, signs a formal commitment letter to NeuroMetric (may be unpaid by the company), ≥ 10% effort charged to the subaward | **Allowed** [V] | Not allowed as sole PI (needs ≥ 51% company employment) [V] | Strongest for reviewers; matches UIUC RP-19 (student cannot be IRB PI) |
| B. Multiple PD/PI: faculty + company scientist | Contact PD/PI at the RI plus a company PD/PI; each must meet the 10% effort and formal-commitment test [V] | Allowed if NIH multi-PI rules are met [PK] | — | Only if the company hires a credentialed scientist; a full-time undergraduate as MPI is a hard sell and the eligibility question is [UNR] (ask NIH SEED / program officer) |
| C. Company PD/PI (SBIR instead of STTR) | Founder or hire as PI, primarily employed by the company | SBIR only | NSF SBIR/STTR | Weak now: a full-time student cannot credibly be "primarily employed" [INF; UNR whether permitted] |
| D. Clinician-scientist at Carle as PD/PI | As A, with Carle as partner RI | Allowed if Carle qualifies [PK] | — | Good clinical fit; heavier site-agreement work |

**Faculty PD/PI commitments to request (none obtained):** formal commitment letter to the company;
≥ 10% effort (1.2 calendar months/yr in the draft budget); IRB PI role under UIUC RP-19; SAP
ownership; data custody; agreement to the COI management plan; a letter of support
(`LETTERS_OF_SUPPORT_TEMPLATES.md` §1). NIH's per-PI application limit (reported as 6 per calendar
year since 2025 [PK]) may matter for a busy faculty member.

---

## 4. Intellectual-property agreement (allocation of rights)

Required between NeuroMetric and the partner RI **before award** [PK: SBA Policy Directive;
confirm the timing NIH enforces]. Items it should cover [INF; to be drafted by OTM and counsel]:

1. **Background IP.** NeuroMetric's existing code base (event model, battery, simulator,
   psychometrics, study module, web app) is listed as company background IP. **Precondition:**
   OTM confirms in writing that the founder (and therefore the company, after assignment) owns it.
   UIUC claims IP made with significant university resources, in university employment or under
   sponsored projects; students outside those conditions generally own their work [AE: UIUC
   General Rules Art. III, text not fetched]. Record that the code was written outside any RA job
   or lab resources (funding.md §3.2 item 5; `BLOCKERS.md` X-4).
2. **Concord.** Earlier code in the founder's Concord repository is labelled "Proprietary
   (internal preview)" and has no licence; NeuroMetric is a clean-room implementation that only
   imports Concord recordings (`DECISIONS.md` D-002). OTM should confirm Concord's ownership too.
3. **Foreground IP.** Default proposal: inventions made solely by company personnel belong to
   the company; solely by RI personnel to the RI; joint inventions jointly owned, with the company
   holding an option to an exclusive licence on commercially reasonable terms within a fixed
   period [HYP terms].
4. **Software and data.** The RI keeps the right to use the software for non-commercial research
   and teaching; participant data stay with the RI and are shared under the DMS plan; the company
   receives de-identified, aggregate or consented data under a data-use agreement.
5. **Publication.** The RI and PD/PI may publish freely; the company may review for confidential
   information and patentable subject matter for a short period (for example 30–60 days) but has
   **no veto** (COI plan requirement).
6. **SBIR/STTR data rights.** Federal SBIR/STTR data-rights protections for the company's
   technical data [PK: protection period and marking rules in the current Policy Directive].
7. **Open-source components.** If parts are released openly (e.g. the psychometrics library or
   simulator for reproducibility), the licence and which components are open are decided before
   publication.
8. **Bayh-Dole reporting.** Invention disclosure and election of title through iEdison [PK].

The Cozad New Venture Challenge takes **no IP** from participants [V] (funding.md §4.1).

---

## 5. What the student founder can and cannot do

| Area | Can | Cannot / must not | Source |
|---|---|---|---|
| **Corporate** | Incorporate; be an officer and majority owner; sign as company authorised representative | — (check: > 50% ownership by US citizens or permanent residents is required for SBIR/STTR eligibility [V]; an international founder must check eligibility and visa rules before incorporating, taking a salary or signing as an officer [PK; Cozad FAQ warns about visa status V]) | funding.md §3.1–3.2 |
| **Employment** | Be paid by the company as a part-time hourly employee from the company's share of the award (requires company payroll); work full-time in summer | Be paid twice for the same work (company and subaward); exceed university limits on student hours during term if also a university employee [UNR: UIUC limit]; international students: CPT/OPT authorisation needed [PK] | funding.md §3.2 item 4 |
| **PD/PI role** | Be key personnel (technical lead) | Be NIH STTR PD/PI in practice (Option C/B issues above); be NSF PI unless ≥ 51% employed by the company | funding.md §3 |
| **IRB / human subjects** | Be a research-team member after CITI training; build and maintain the software; train staff on the software; see de-identified data per the DMS plan | **Be IRB PI** (UIUC RP-19 lists "undergraduate or graduate student employee" among those who may not be PI; OPRS requires a responsible PI) [V]; obtain consent; recruit classmates or direct reports; hold the randomisation list; run confirmatory analyses; have access to identifiable data beyond what the IRB approves | `CLINICAL_VALIDATION_PLAN.md` §0; `docs/irb/README.md` |
| **Conflict of interest** | Disclose the company interest on every IRB study (OPRS COI requirement for "any individual participating on a study reviewed by the IRB", enforced from 23 Mar 2026 [V]); follow the COI management plan | Influence data custody, analysis decisions after the SAP lock, or publication content | `CLINICAL_VALIDATION_PLAN.md` §2.10 |
| **Faculty PD/PI COI** | — | A faculty PD/PI or advisor who takes equity or paid company roles triggers UIUC COI/conflict-of-commitment disclosure and possibly a management plan [PK]; NIH financial COI rules (42 CFR 50 Subpart F) apply to NIH-funded investigators, with an SBIR/STTR **Phase I exemption** for the applicant small business [PK, confirm] | funding.md §3.2 item 6 |
| **Academic** | Use the work for course credit or a thesis only if the course/advisor rules and the COI plan allow and IP terms are clear | Use university lab resources for company development without an agreement (it can create university IP claims) [AE/INF] | funding.md §3.2 item 5 |

---

## 6. Sequence of steps (owner: founder unless stated)
1. OTM ownership confirmation for NeuroMetric and Concord code (before Cozad filings, any IP Clinic
   work, or incorporation transfer of code).
2. Identify and meet candidate faculty PD/PIs with the one-page aims; nothing is assumed until a
   written commitment exists.
3. Incorporate (Delaware C-corp or Illinois corporation; counsel decides) by about mid-January 2027
   to make the 5 Apr 2027 date [INF]; start EIN, SAM.gov UEI, Grants.gov, eRA Commons and SBA
   company registry immediately (≥ 6 weeks) [V warning].
4. UIUC Sponsored Programs: subaward budget, F&A rate, letter of intent to subcontract signed by
   the institutional official.
5. Draft the allocation-of-rights agreement (OTM + company counsel).
6. COI disclosures and management plan reviewed by the UIUC COI office before IRB submission.
7. Program-officer contact (NINDS, NICHD/NCMRR).
