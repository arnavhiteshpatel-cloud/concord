# Conflict-of-interest disclosure and proposed management plan

**DRAFT — not submitted — requires faculty PI and IRB review**

**Why this is critical.** The student investigator founded NeuroMetric. The studies evaluate
NeuroMetric's own software. Favourable reliability and validity results could raise the value of
the founder's financial interest. That creates a risk of biased design, conduct, analysis and
reporting, and a risk of undue influence on participants. **Neither the student nor this draft
can decide how the conflict is managed.** The UIUC COI office and the IRB decide.

## 1. Disclosure facts (to be completed truthfully by the student)
| Item | Entry |
|---|---|
| Entity | *[NeuroMetric legal name, or "not yet incorporated"]* |
| Student's role | Founder; *[officer/director roles]* |
| Equity | *[percentage or "not yet issued"]* |
| Income, compensation, IP | *[none / describe]*; IP ownership of the software under UIUC policy is **unresolved** (see `DECISIONS.md` D-002 and the founder handoff) [UNR] |
| Other investigators' interests | Faculty PI: *[none expected; must disclose]*. Statistician: none (required) |
| Funding of this research by the entity | *[none / describe]* |

**UIUC requirement.** OPRS announced that the COI requirement, "including disclosure of
Significant Financial Interests (SFIs)", applies to "all investigators", and to "Any individual
participating on a study reviewed by the IRB", enforced from March 23 (page posted 2026-03-03)
[V]. https://oprs.research.illinois.edu/news/conflict-interest-coi-requirement-goes-100-live-march-23rd
The disclosure mechanism named there is a "Sponsor Specific Questionnaire Disclosure" [V]. Campus
COI office: coi@illinois.edu (per https://research.illinois.edu/compliance-safety/conflict-commitment-interest) [V].
Whether a student with no appointment files through the same system is [UNR]. Ask the COI office.

## 2. Proposed management measures [INF; for the COI office and IRB to accept, change or reject]
| # | Measure | Risk addressed |
|---|---|---|
| M1 | Independent **faculty PI** with no financial interest holds overall responsibility, including AE determinations | Conduct, safety |
| M2 | The founder **does not recruit, screen or obtain consent**, and does not run sessions for people they know | Undue influence |
| M3 | **SAP locked and preregistered** (SHA-256 plus OSF) before enrolment; deviations log; change after data access demotes a hypothesis to exploratory | Analytic flexibility |
| M4 | **Confirmatory analyses run by an independent statistician** from frozen code. The founder may write code before the lock only. After the lock, any change goes through a logged deviation approved by the PI and statistician | Analysis bias |
| M5 | **Data custody at the university.** The founder has no access to identifiable data. Pseudonymous data access is read-only and limited to roles in this plan | Confidentiality, integrity |
| M6 | **Publication:** the faculty PI controls publication. The company has no right to delay beyond a short IP-review window (e.g. ≤ 30 days [HYP], via a university agreement) or to suppress results. **Negative and null results are published** (OSF at minimum) | Reporting bias |
| M7 | **Disclosure** in consent forms, recruitment pages (PI and IRB only, no product marketing), presentations and papers | Transparency |
| M8 | **Software change control:** battery version and scoring code are frozen per stage (`BATTERY_VERSION`, commit hash). Any change during data collection needs PI approval and is logged | Measurement integrity |
| M9 | **Separation of company funds:** any company funding goes through a university-approved agreement. Participant payments are not made directly by the company [INF] | Undue influence, conflict |
| M10 | **Academic separation:** the faculty PI is not the founder's course instructor for credit-bearing evaluation during the study, or a second faculty member evaluates any related academic credit [INF] | Power dynamics |
| M11 | **Annual review** of the plan by the COI office; an outside monitor if the COI office requires one | Ongoing oversight |
| M12 | **No marketing use of study data** until results are published or posted. Marketing never uses the words "validated" or "clinical" beyond what the published results support | Misrepresentation |

## 3. Consent-form disclosure text (plain language)
"*[Student name]*, a student on this research team, started a company that may sell the software
used in this study. If the study shows the software works well, the company could be worth more.
To protect the study: a professor with no financial interest leads it; the student does not ask
you to join or collect your consent; the analysis plan is fixed and made public before the study
starts; and the university oversees this arrangement."

## 4. Open questions for the COI office
1. Which disclosure system applies to an undergraduate with no appointment?
2. Is an outside monitor required?
3. Is the founder allowed to be listed as a co-investigator, or only as "software provider"?
   (The founder still needs CITI if engaged [V training rule].)
4. How does UIUC IP policy apply to software the founder wrote as a student, possibly with
   university resources? [UNR]
