# Deck outlines: (a) investor pitch, (b) research demonstration

Prepared 2026-11-27. Slide-by-slide content only; no design. Labels per `docs/research/CONVENTIONS.md`.
**Computational results are being generated now. Every results slot below is a placeholder of the form
`[insert from experiments/results/... ]`; do not fill them with numbers that are not in those files, and copy each
file's own `disclaimer` field onto the slide.** All market, price and financial figures are [HYP] unless sourced.

Standing footer for every slide: "NeuroMetric is research software, not a medical device. Results are from
simulation; no clinical validation; no customers or partners yet."

---

## (a) Investor pitch deck (12-15 minutes)

| # | Slide | Content | Sources / slots |
|---|---|---|---|
| 1 | Title | NeuroMetric - neutral evidence of what people can do with their neural interface or assistive technology, at home. Founder name, UIUC, date. | `FOUNDER_INTRO.md` |
| 2 | Problem | BCIs and home neurotech are reaching pivotal studies and payers, but the field lacks fit-for-purpose functional outcomes and home-use evidence. Quote iBCI-CC (1 Oct 2026): a single existing measure is "unlikely" to be sufficient; need "flexible pathways… to generate real-world data". No BCI COA is MDDT-qualified. | [V] `regulatory_landscape.md` s5-6 |
| 3 | Market evolution | 2024 FDA/NIH COA workshop → 2025-26 BCI Society COA papers → SRAlab DAI study (2026) → iBCI-CC consensus (Oct 2026) → RAPID proposed (Aug 2026, not final) → first US iBCI pivotal announced (Nov 2026, [CC]). Home neuromod: ONWARD home 510(k), PoNS stroke home phase, Mobia IPO. | [V]/[CC] `regulatory_landscape.md`, `neuromodulation_market.md` |
| 4 | Why evidence matters | FDA asks for home use and caregiver metrics; CMS needs improved health outcomes; a commercial payer (Anthem DME.00052) lists missing real-world use and independence for BCI rehab devices. Show the measurement chain: device performance → function → health outcome / care burden. | [V] `PAYER_EVIDENCE_MATRIX.md` |
| 5 | Initial customer | Non-invasive BCI/AAC makers and home-neuromod/rehab makers with public evidence gaps (e.g., registered daily-use and caregiver-burden endpoints; payer policy gaps), academic BCI/rehab programs via grants; non-dominant iBCI sponsors as anchor. State: no customer yet; discovery in progress. | `COMMERCIALIZATION.md` s2; `PROSPECT_PIPELINE.md` |
| 6 | Alternatives today | Sponsor in-house logging; academic clinic instruments (SRAlab DAI, Digital IADL); clinic AT tests (Compass $179 [V]); eCOA/EDC platforms (no access-method telemetry found); HEOR consultancies. | `competitors.md` S1 |
| 7 | Differentiation | Input-agnostic; home-first; implements consensus instruments instead of a rival score; care-partner burden linked to observed use; audit-trail design for Part 11; never controls devices. Be explicit about what is *intended* vs *built*. | `DECISIONS.md`; `competitors.md` S1 |
| 8 | Demo | 90-second screen recording: same task battery with mouse, switch-scanning and a simulated degraded BCI cursor; event log → metrics → report. Label "simulated input". | `[insert demo video path]` |
| 9 | Computational results | Three panels max: measurement sensitivity under modelled degradation; reliability under simulation; reproducibility. Each panel shows the experiment's own disclaimer. | `[insert from experiments/results/B_noise/summary.json ]`; `[insert from experiments/results/R_statistical_verification/summary.json ]`; `[insert from experiments/results/P_reproducibility/summary.json ]` |
| 10 | Clinical validation required | What is not yet shown: test-retest reliability in real users, validity against clinic measures, responsiveness/MCID, home-use feasibility, care-partner burden feasibility, Part 11 validation. Plan: STTR Phase I aims (`ACADEMIC_COLLABORATION_PROPOSAL.md`). | [INF] |
| 11 | Commercial entry | 90-day gate (≥2 LOIs, ≥20 interviews, academic anchor, incorporation); 6-month fixed-fee evidence pilots; pricing hypotheses with tests. | `COMMERCIALIZATION.md` s8; `PRICING_HYPOTHESES.md` |
| 12 | Expansion | Study-year contracts (pivotal iBCI), registry add-ons, rehab-provider subscriptions for SGD/AT justification, manufacturer SDK integrations, payer evidence with HEOR partners; long-term: shared, possibly MDDT-qualified implementation. | `COMMERCIALIZATION.md` s2.3 |
| 13 | Competitive risks | SRAlab DAI as free reference; sponsor in-house build; Signant+Ametris fast follower; small buyer universe (~$5M/yr at 100% penetration by 2031 [HYP]); third-party telemetry access. Show mitigations. | `COMMERCIALIZATION.md` s5, s7 |
| 14 | Business model | Pilots $25-75K, study-years $100-400K, maker programs $100-300K/yr, academic $15-40K/yr [all HYP]. Scenario table A-D from the model (2029 revenue, ARR, total capital); state plainly that no scenario breaks even by 2031 at current assumptions. | `financial_model_outputs.md` |
| 15 | Funding milestones | M0-3: incorporation, IP, 20 interviews, ≥2 LOIs. M4: STTR Phase I submitted (5 Apr 2027). M5-12: first paid pilot; partner-IRB deployment. M12-18: Phase I award (if funded), DCEO match, Part 11 package. M18-30: Phase II submission, study-year contracts. | `funding.md` s5 |
| 16 | Team requirements | Today: founder (UIUC undergraduate). Needed: faculty STTR PI/advisor, psychometrician (fractional), clinical research lead, quality/regulatory (fractional), CI MED teammate for Cozad, lived-experience advisors (via DRES). No names until people agree. | `collaborators.md`; `FOUNDER_INTRO.md` |
| 17 | Use of funds | Pre-seed $150-400K [HYP]: incorporation/legal/IP (~10%), engineering and security (~45%), validation studies with partners (~25%), discovery and travel (~10%), buffer (~10%). Seed $1.5-3M [HYP]: Part 11/SOC 2, clinical/psychometric hires, first study-year deliveries. Link to model lines. | `financial_model_outputs.md` (scenario B/D 2027-2028) |
| 18 | Ask and close | [Amount, instrument] - to be decided by founder. Restate status honestly. | — |

## (b) Research demonstration deck (20-30 minutes, academic / standards audiences)

| # | Slide | Content | Sources / slots |
|---|---|---|---|
| 1 | Title and disclaimer | Research software; simulation results; no clinical claims. | — |
| 2 | Problem | Measurement chain gap (device performance → function → care burden); home and daily-life capture named as a key challenge (J Neural Eng 2026). | [RF]/[V] |
| 3 | Market/field evolution | Consensus timeline (as investor slide 3), framed as a scientific need, not a market. | [V] |
| 4 | Initial users | Academic programs, AT clinicians, device teams needing comparable metrics. | [INF] |
| 5 | Why evidence matters | FDA/CMS/payer expectations matrix (one table). | `PAYER_EVIDENCE_MATRIX.md` |
| 6 | Alternatives | DAI, Digital IADL, Compass, Webgrid, BCI2000/FALCON/MOABB; what each measures and does not. | `competitors.md` Part A, C, D |
| 7 | Differentiation (method) | Canonical event schema; observable-only metrics (D-006); closed-loop virtual users with delayed perception (D-005); deterministic stimuli (D-004); Python scoring as source of truth (D-003). | `DECISIONS.md` |
| 8 | Demo | Live or recorded: run battery, show event stream, recompute metrics in Python, show parity with browser subset. | `[insert demo video path]` |
| 9 | Results: degradation sensitivity | Metric behaviour vs modelled noise/drift/latency. | `[insert from experiments/results/B_noise/summary.json ]` |
| 10 | Results: statistical verification | Estimator bias/coverage checks. | `[insert from experiments/results/R_statistical_verification/summary.json ]` |
| 11 | Results: missing data | Bias under missingness patterns. | `[insert from experiments/results/N_missing_data/summary.json ]` |
| 12 | Results: event latency / timing | Browser event timing characterisation. | `[insert from experiments/results/S_event_latency/summary.json ]` |
| 13 | Results: public-data replay | Processing of a public non-human dataset (DANDI:000129); copy its caveats verbatim. | `[insert from experiments/results/X1_external_mc_rtt/summary.json ]` |
| 14 | Results: reproducibility and security checks | Re-run determinism; security test summary. | `[insert from experiments/results/P_reproducibility/summary.json ]`; `[insert from experiments/results/security/ ]` |
| 15 | Clinical validation requirements | Reliability (ICC, MDC), validity (known-groups, convergent with clinic measures), responsiveness/MCID, home feasibility, care-partner module feasibility, Part 11 validation; MDDT as a long-term option. | `regulatory_landscape.md` s5, s11 |
| 16 | Commercial entry (brief) | How research use and commercial pilots relate; data ownership and neutrality commitments. | `SPONSOR_PILOT_PROPOSAL.md` |
| 17 | Expansion | Cross-device dataset; contribution to iBCI-CC; open metric definitions. | [INF] |
| 18 | Competitive risks / limits | Simulation ≠ people; access to OS-level telemetry; instrument licensing; neutrality with sponsor-affiliated collaborators. | [INF] |
| 19 | Business model (one line) | Sustained by grants and fixed-fee pilots; open method definitions remain free. | [HYP] |
| 20 | Funding milestones | STTR timeline; partner IRB studies. | `funding.md` |
| 21 | Team requirements | Collaborator roles sought (PI, psychometrics, clinicians, lived-experience advisors). | `collaborators.md` |
| 22 | Use of funds / asks | For academic audiences: data-sharing, validation partnership, workgroup contribution - no money ask. | — |
