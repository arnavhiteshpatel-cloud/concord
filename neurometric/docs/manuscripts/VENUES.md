# Publication and presentation venues: suitability and what to verify

> Prepared 2026-11-27. **No venue requirement below was re-checked against the venue's website in
> this session; all requirement notes are [PK]** (prior knowledge) unless marked. Before each
> submission, verify on the venue's current author guidelines: scope, article types, length and
> figure limits, open-access options and article processing charges (APCs), preprint policy,
> data/code-availability rules, reporting checklists, and deadlines. Labels per
> `docs/research/CONVENTIONS.md`.

## 1. Mapping papers to venues

| Paper | First choice | Second choice | Conference outlet |
|---|---|---|---|
| P1 simulated-decoder framework | J Neural Eng | IEEE TNSRE | BCI Society Meeting poster |
| P2 metric properties, adaptive testing, statistical verification | JNER (methodology) or Behavior Research Methods | IEEE TNSRE; Assistive Technology (floor/ceiling + adaptive part) | RESNA; ACRM |
| P3 privacy-preserving home measurement (design) | RESNA conference paper (design + verification) | ASSETS/CHI after the feasibility study; JMIR family | ASSETS poster/demo |
| Protocol paper | BMJ Open | JMIR Research Protocols; JNER | — |
| Future human validation (Stages 1–4) | J Neural Eng / Arch Phys Med Rehabil / JNER | Assistive Technology | ACRM; RESNA; BCI Society |

## 2. Venue notes

| Venue | Scope fit for NeuroMetric | What to verify [PK] |
|---|---|---|
| **Journal of Neural Engineering** (IOP) | High for BCI outcome-measure methods; published the 2026 BCI Society/iBCI-CC COA workshop report (Sawyer et al. 2026, 10.1088/1741-2552/ae9eee) [V] and Fry et al. 2022 [V] | Article types (Paper, Perspective, Tutorial); data-availability statement; preprint policy; open-access APC vs subscription route; whether simulation-only methods papers are in scope without human data |
| **IEEE Transactions on Neural Systems and Rehabilitation Engineering** | High: rehabilitation engineering, AT, BCI performance metrics; historical home of Wolpaw ITR work in IEEE TRE [V-DOI] | Fully open-access with an APC; page limit and over-length charges; IEEE template; code/data policy |
| **Journal of NeuroEngineering and Rehabilitation** (BMC) | Good for methods and protocols in rehabilitation technology | APC and waivers; "Methodology" and "Study protocol" article types; reporting checklists (COSMIN for measurement studies) |
| **Assistive Technology** (RESNA journal) | Good for AT outcome measurement, floor/ceiling, access methods, home use | Article types and length; whether simulation papers fit; APC for open access |
| **ACM CHI** | Medium: HCI methods (Fitts, text entry), accessibility | Annual deadline (usually September [PK]); full papers expect user studies; anonymisation; page-length rules; ACM open-access transition |
| **ACM ASSETS** | High for accessibility and AT users, including privacy of AT telemetry | Annual deadline (usually spring/summer [PK]); strong expectation of participation by disabled people; accessible-submission requirements (accessible PDF, alt text) |
| **BCI Society Meeting** | High audience fit (BCI endpoints community, iBCI-CC) | Meeting is not annual in every year [PK]; abstract deadline and format; check the next meeting date and whether workshops on COAs recur |
| **RESNA Annual Conference** | High for AT practitioners; design and student papers | Paper/poster formats and deadline (usually early in the year [PK]); student design competition eligibility |
| **ACRM Annual Conference** | Good for rehabilitation outcome measurement and clinical audiences (late-breaking and outcome-measurement networking groups [PK]) | Abstract deadline (usually spring [PK]); requires clinical relevance; human data strongly preferred |
| BMJ Open / JMIR Research Protocols | Protocol paper | Ethics approval and registration before submission; APC |
| Behavior Research Methods; BMC Medical Research Methodology | Psychometric/simulation methodology (P2; the ICC interval note) | Scope; check whether Ionan et al. 2014 already covers the ICC(A,1) interval result |

## 3. Cross-cutting checks before any submission
1. **Honest labelling:** simulation results are synthetic and are not described as human or
   clinical evidence; the one real dataset is a public **macaque hand-cursor** dataset (NLB MC_RTT,
   DANDI:000129).
2. **Competing interests:** the founder's company interest; any faculty co-author's interest.
3. **Code and data availability:** licence decided (`pyproject.toml` currently says
   "Proprietary – all rights reserved (pending founder IP decision)"); Zenodo DOI for the exact
   commit; MC_RTT cited per its DANDI README.
4. **IP:** publication can create prior art and starts patent grace periods [PK]; decide on any
   filing (Landuyt IP Clinic) before submitting P1 (`docs/grants/I_CORPS_AND_ACCELERATORS.md` §4).
5. **Review history:** describe the independent code review and fixes
   (`docs/review/RESPONSE_TO_SCIENCE_CORE_REVIEW.md`) in methods or supplementary material.
6. **Preprint:** consider arXiv (cs.HC / q-bio.NC) or medRxiv/bioRxiv for P1/P2 if the target
   journal allows [PK].
