# Customer discovery plan (Dec 2026 - Feb 2027)

Prepared 2026-11-27. Uses `docs/research/interview_guides.md` (7 guides, Mom-Test rules) and
`PROSPECT_PIPELINE.md`. **No interviews have been run; every expectation below is a hypothesis [HYP].**

**Provenance note.** The playbook's own experiments and decision rules **E1–E9** are transcribed in
`docs/research/PLAYBOOK_B_DECISION_RULES.md` and are authoritative. Section 4 below adds supplementary
commercial rules **C1–C9** derived from the research files (competitors.md falsifiers F1–F6,
comparable_pricing.md, funding.md gates); they refine, not replace, E1–E9.

## 1. Who (target: ≥20 interviews in 90 days)

| Interviewee type | Guide | Target count | First names in pipeline |
|---|---|---|---|
| BCI sponsors - clinical/regulatory | 1 | 4 | Paradromics, Precision, Cognixion (Synchron on hold) |
| BCI market access / HEOR | 2 | 2 | Cognixion funding lead; any iBCI sponsor HEOR owner |
| Rehab / neuromodulation device makers | 3 | 5 | ONWARD, Kandu, Bioness, Mobia, Myomo |
| Clinical researchers / PIs | 4 | 5 | JNERL, SRAlab DAI, BrainGate, Mount Sinai, UMC Utrecht |
| AT clinicians (OT, SLP, ATP) | 5 | 3 | Via DRES, Carle, SRAlab clinicians |
| Payer evidence specialists | 6 | 1 | IQVIA MedTech (or another HEOR consultant) |
| Clinical research software vendors | 7 | 2 | Castor, OpenClinica |
| **Total** | | **22** | |

## 2. Sequence

| Weeks | Focus | Why first |
|---|---|---|
| 1-2 (Dec 2026) | Academic and standards: JNERL, iBCI-CC, SRAlab, Mount Sinai, Fried-Oken; DRES | Low barrier, fast learning, STTR partner needed early; vocabulary for sponsor calls |
| 3-5 (mid-Dec - Jan) | Tier-1 makers with public evidence gaps: Cognixion, Kandu, ONWARD, Bioness, Mobia | Visible triggers and budgets; most likely LOIs |
| 5-8 (Jan) | iBCI sponsors (Paradromics, Precision); AAC makers (Tobii Dynavox, PRC-Saltillo) | Test iBCI demand and AAC payer-evidence framing |
| 6-10 (Jan - Feb) | eCOA vendors and HEOR consultancy | Partnership vs competition; what they decline |
| 10-13 (Feb) | Follow-ups, LOI conversations, 90-day gate review | Gate on 28 Feb 2027 |

## 3. Hypotheses to falsify

| ID | Hypothesis [HYP] | Disconfirming evidence | Source of hypothesis |
|---|---|---|---|
| H1 | Home real-world-use evidence is an unsolved, funded need for makers and sponsors | Interviewees describe an owned, working in-house process with no complaints | competitors.md S4 |
| H2 | Third-party (independent) collection adds credibility with FDA/payers | ≥3 of 5 non-Neuralink sponsors say in-house or existing eCOA vendor is sufficient (F2) | competitors.md F2 |
| H3 | Sponsors/makers will pay ≥$50K for a 6-month evidence pilot | ≥3 of first 8 qualified conversations reject ≥$50K | comparable_pricing.md s5 |
| H4 | Care-partner burden data are wanted | No interest and a clear rationale (e.g., FDA said not needed) | interview_guides.md 1 |
| H5 | Read-only log export or app-level SDK is technically and contractually feasible | Makers refuse log export and SDK integration (F4) | competitors.md F4 |
| H6 | Academic partners can budget NeuroMetric in grants | Partners prefer free tools (REDCap/Castor) and decline budget lines | comparable_pricing.md |
| H7 | eCOA vendors are partners, not imminent competitors | A vendor already sells a device-agnostic access-method module (F6) | competitors.md F6 |
| H8 | AAC/AT and rehab segments value SGD/AT documentation support | Clinicians report documentation is not a bottleneck | PAYER_EVIDENCE_MATRIX.md |
| H9 | Standards bodies welcome an implementer rather than see a competitor | SRAlab/iBCI-CC publish a free home-administrable DAI with logging adopted by ≥2 sponsors (F1) | competitors.md F1 |

## 4. Supplementary decision rules C1–C9 (use alongside playbook E1–E9)

| Rule | Trigger (measured at day 45 and day 90) | Decision |
|---|---|---|
| **C1 Problem** | ≥60% of qualified maker/sponsor interviews describe a recent, specific home-use or care-burden evidence gap with time or money already spent | Continue niche. Otherwise re-scope to research tooling (scenario A) |
| **C2 Independence** | ≥3 of 5 non-Neuralink sponsors say in-house/eCOA is sufficient | Drop "independence" as the lead message; sell speed/cost of home measurement; lower price hypotheses |
| **C3 Price** | ≥3 of first 8 qualified conversations reject ≥$50K for a 6-month pilot | Re-price pilots to $25-35K; shift weight to grant-funded academic work |
| **C4 Buyer** | Named decision-maker and budget line found in ≥3 organisations | Required before any proposal is sent; else keep interviewing, no proposals |
| **C5 Segment lead** | Count LOIs and pain scores by segment at day 90 | Lead with the segment with most LOIs: neuromod/AAC → scenario D sequencing; iBCI → scenario B; neither → A |
| **C6 Technical access** | ≥2 makers confirm read-only export or SDK feasible | Proceed with integrations; else rely on app-level tasks + wearables and revise product scope |
| **C7 Standards** | F1 occurs, or SRAlab/Mount Sinai prefer to license their instrument to us | Become implementer/host; never build a rival index |
| **C8 Grant path** | Faculty partner confirmed by ~15 Jan 2027 | Submit STTR 5 Apr 2027; else target 5 Sep 2027 and check NSF (PI must be ≥51% company-employed [V]) |
| **C9 Continue / stop** | Day 90: <2 LOIs **and** no academic anchor | Stop sponsor-sales track; continue only as open research software or stop. ≥2 LOIs + anchor → phase 1 |

## 5. Logistics

- Interview log fields: date, organisation type, role, guide, pain 0-3, spend (none/time/money/both), current
  solution, decision-maker (y/n), next step (y/n), price reaction (verbatim), most surprising statement.
- Score within 24 h; review weekly; never record identifiable patient information or confidential sponsor data.
- Feed I-Corps Boost eligibility (≥20 interviews) [V `funding.md`].
