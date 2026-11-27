# Payer and regulator evidence matrix

Prepared 2026-11-27 from `docs/research/regulatory_landscape.md` and `docs/research/health_economics_payer.md`.
Labels per `CONVENTIONS.md`. **This matrix describes evidence expectations. It is not legal or reimbursement advice
and it guarantees nothing: no evidence package, NeuroMetric's or anyone's, guarantees FDA authorization, a CMS
national coverage determination, a code, a payment amount, or a commercial payer coverage decision.**

Status key: **Established** = statute, regulation, final guidance or written policy in force. **Evolving** =
proposed, draft, consensus-in-progress, or individual-payer practice that varies. **Unvalidated** = no validated
instrument or accepted method exists yet for BCI/AT use; would need formal validation.

## 1. Evidence type × decision-maker

| Evidence type | FDA (PMA / De Novo / 510(k); IDE) | CMS / Medicare (NCD, RAPID, CED, DME) | Commercial payers / MA / Medicaid | NeuroMetric role [INF] | Sources |
|---|---|---|---|---|---|
| Safety (AEs, SAEs, explant), ≥1 yr | **Established** (iBCI guidance) | **Established** as input to CED/RAPID | **Established** practice | None (sponsor/CRO) | [V] iBCI guidance; RAPID fact sheet |
| Validated primary effectiveness endpoint with MCID | **Established** expectation; **Unvalidated** for iBCI (no COA MDDT-qualified) | **Evolving** (RAPID: outcomes FDA determines and CMS confirms) | **Established** expectation | Implement consensus COAs; supply reliability/MDC data | [V] MDDT list; RAPID |
| Device performance (accuracy, WPM, ITR/BPS) | **Established** as supportive | Low weight alone | Low weight alone | Measure input-agnostically as level 1 of the chain | [V]/[INF] |
| Functional / activity outcome (digital ADL, independence) | **Evolving** (PFDD Guidance 3 final Oct 2025; COA fit-for-purpose) | **Evolving** (iBCI-CC measurement chain; Section GG is CMS-native) | **Evolving** | Core: home tasks + passive digital-activity telemetry | [V] PFDD; iBCI-CC 1 Oct 2026 |
| Home / real-world use | **Established** (iBCI guidance "Home Use") | **Evolving** (generalisability; RWD for CED) | **Evolving**; explicit gap in Anthem DME.00052 | Core: passive use minutes, independent vs assisted sessions | [V] iBCI guidance; [V] Anthem DME.00052 |
| Care-partner burden / care time | **Established** for caregiver safety and ability to assist; burden optional | **Evolving** (iBCI-CC: "particularly for payor decision-making") | **Evolving** | Core: ZBI + time diary linked to telemetry | [V] iBCI-CC; [V] NCT07871071, NCT07147881 use ZBI |
| PROs (QoL, psychosocial impact: PIADS, QUEST, WHOQOL-BREF) | **Established** if a claim rests on them | **Evolving** (MEDCAC 2018 PRO precedent cited by iBCI-CC) | **Evolving** | Administer licensed instruments electronically | [V] |
| Comparative effectiveness vs existing AT (eye-gaze, switches, SGD) | Optional | **Evolving** ("reasonable and necessary" vs alternatives) | **Established** practice (least costly alternative) | Input-agnostic comparator framework; only NCT07407725 compares devices today | [V]/[INF] |
| Medical-vs-convenience use separation | N/A | **Established** for SGDs (NCD 50.1 excludes general computing, games, video conferencing) | **Evolving** | Tag communication-of-needs, safety, self-management vs leisure use | [V] NCD 50.1 |
| Benefit-category fit (DME / prosthetic / service) | N/A | **Established** statute; **Unresolved** for iBCI | Benefit design varies | None (sponsor counsel) | [V]/[INF] |
| Medicare-beneficiary enrollment | N/A | **Evolving** (RAPID requires it) | N/A | Report age/entitlement subgroups | [V] RAPID |
| Cost-effectiveness / budget impact | N/A | Not used formally in NCDs | **Evolving** (HTA, P&T, Medicaid) | Supply inputs only; HEOR partner builds models | [PK] |
| Care-time valuation (replacement / opportunity cost) | N/A | N/A | **Unvalidated** for BCI/AT; never equal to healthcare savings | Hypothetical scenarios only until measured (`care_economics.py`) | [V] BLS wage; [INF] |
| Long-term durability, device support | **Established** (≥1 yr; post-approval) | **Evolving** (CED time-limited) | **Established** expectation | Longitudinal home telemetry | [V] |
| Data integrity (Part 11, audit trail, source data location) | **Established** (21 CFR 11; eSystems Q&A Oct 2024) | Indirect | Indirect | Platform requirement; validation package | [V] |
| Post-market RWE registry | **Established** (PAS) where required | **Established** mechanism if CED | **Evolving** | Registry add-on (e.g., Mobia GRASP n=1,000 uses self-reported MAL) | [V] NCT05301140 |

## 2. Documentation manufacturers may need (by pathway)

| Pathway / audience | Documents commonly assembled [PK/INF unless labelled] | What NeuroMetric could contribute [INF] |
|---|---|---|
| FDA pivotal / De Novo / PMA (iBCI, home neuromod) | Protocol with endpoint rationale; COA dossier (concept of interest, context of use, content validity, reliability, construct validity, responsiveness, MCID); DHT verification/validation (DHT guidance Dec 2023 [V]); Part 11 system validation summary; statistical analysis plan | Home-use and functional measurement module; reliability/MDC reports; system validation package; audit-trail exports |
| CMS RAPID pre-IDE meeting (if finalized) | Proposed outcomes CMS would accept as improved health outcomes; Medicare-beneficiary enrollment plan; benefit-category argument [V RAPID text] | Mapping of NeuroMetric measures to the measurement chain; feasibility data in Medicare-age/disability-entitled users |
| Medicare DME / SGD claims (AAC, eye-gaze, possibly BCI communication components) | Physician order; SLP evaluation; documentation that the device meets NCD 50.1 (speech generation, messaging) [V]; DME MAC LCD requirements (L33739 [PK, not re-verified]) | Logs separating communication use from general computing; SLP-facing summaries |
| Commercial payer medical policy review (e.g., Anthem DME.00052) | Peer-reviewed RCTs, independent replication, durability, real-world function and daily-living independence [V Anthem criticisms] | Independent remote assessment, real-world use, ZBI, durability follow-up; mapping to each stated criticism |
| Letters of medical necessity / prior authorization (e.g., ARC-EX home via PRIA program [CC]) | Prescription, clinical notes, functional goals, evidence summary | Patient-level home-use and goal-attainment summaries (only with patient consent; HIPAA BAA if provider-deployed) |
| HTA / budget-impact (private payers, Medicaid, non-US HTA) | Cost-effectiveness or cost-consequence model, budget impact, utility inputs (EQ-5D ceiling/floor issues in severe paralysis [PK]) | Primary functional and care-time data as model inputs; never the model's conclusions |

## 3. Care-partner time: hypothetical valuation grid (not results, not savings)

Generated with `python -c "from neurometric.economics.care_economics import *; print(render_sensitivity_markdown(sensitivity_table()))"`.

**HYPOTHETICAL SCENARIO: annual value of care-partner time per participant (USD/yr).** Hours/day are assumptions, not results.

| Wage basis | Label | $/h | 0.25 h/day | 0.5 h/day | 1 h/day | 2 h/day |
|---|---|---:|---:|---:|---:|---:|
| BLS median wage, home health and personal care aides (replacement) | [V] | 17.21 | $1,570 | $3,141 | $6,282 | $12,563 |
| Home health aide agency charge (order of magnitude) (replacement) | [PK] | 34.00 | $3,102 | $6,205 | $12,410 | $24,820 |
| BLS all-occupations mean wage (opportunity cost) (opportunity) | [INF] | 33.54 | $3,061 | $6,121 | $12,242 | $24,484 |

This is a valuation of care-partner time. It is NOT healthcare cost savings, NOT payer savings, NOT a budget impact
and NOT a return on investment. No money changes hands because informal care time is valued.

Sources: BLS OOH home health and personal care aides, $17.21/h (2025 median pay), $35,800 median annual (May 2025)
[V] https://www.bls.gov/ooh/healthcare/home-health-aides-and-personal-care-aides.htm ; BLS OEWS May 2025 mean annual
wage $69,770 [V] https://www.bls.gov/news.release/ocwage.nr0.htm (hourly = /2,080 [INF]); agency charge [PK].
No registered US implanted-BCI trial measures caregiver time (`health_economics_payer.md` s3.3).

## 4. Rules for anything NeuroMetric publishes or sends [INF]

1. Never state or imply that NeuroMetric evidence will obtain coverage, a code or a payment.
2. Never convert task-time or performance gains into care hours, and never convert care hours into healthcare savings.
3. Label every economic figure as hypothetical until it comes from an observed study effect with a confidence interval.
4. Cite the status column above (established / evolving / unvalidated) whenever an evidence type is described.
