# Data room structure

Prepared 2026-11-27. A folder plan for diligence by investors, grant reviewers or sponsor vendor-qualification
teams. **Most folders are empty today**; status column says what exists. Never place participant-identifiable data,
unpublished sponsor data or anything under NDA in a shared data room.

| # | Folder | Contents | Status (Nov 2026) | Source in repo |
|---|---|---|---|---|
| 00 | `00_README` | Index, version, contact, disclosure ("research software; simulation-only results; no partners") | To create | `docs/commercial/ONE_PAGER.md` |
| 01 | `01_Company` | Certificate of incorporation, cap table, bylaws, founder IP assignment, UIUC OTM ownership confirmation | **Not incorporated** | `funding.md` s3.2 |
| 02 | `02_Team` | Founder bio (factual), advisor letters (only with permission), hiring plan | Template only | `FOUNDER_INTRO.md` |
| 03 | `03_Product` | Architecture, decision log, event schema, metric definitions, task battery, demo video | Partly exists | `DECISIONS.md`, `src/`, `web/` |
| 04 | `04_Technical_Evidence` | Simulation experiment protocols and results, reproducibility checks, limitations | Being generated | `experiments/results/` |
| 05 | `05_Clinical_Validation` | Validation plans, IRB approvals (partner-held), reliability/validity reports | **None yet** | — |
| 06 | `06_Regulatory_Quality` | Intended-use statement, device-status analysis, Part 11 validation plan/report, SOPs, risk analysis | Analysis exists; validation not started | `docs/research/regulatory_landscape.md` |
| 07 | `07_Security_Privacy` | SOC 2 readiness, security policies, pen-test results, HIPAA BAA template, neural-data law review | Not started | `docs/security/` (empty) |
| 08 | `08_Market` | Competitor map, prospect database (no personal data), market counts, payer matrix | Exists | `docs/research/`, `COMMERCIALIZATION.md` |
| 09 | `09_Customers` | Discovery interview log (anonymised), LOIs, pilot proposals, references | **No LOIs** | `CUSTOMER_DISCOVERY_PLAN.md`, `SPONSOR_PILOT_PROPOSAL.md` |
| 10 | `10_Financials` | Financial model code and outputs, assumption register, use of funds, bank statements | Model exists (all HYP) | `src/neurometric/economics/`, `docs/commercial/financial_model_outputs.md` |
| 11 | `11_Grants` | Funding map, STTR drafts, letters of support (only if given), award notices | Map exists | `docs/research/funding.md`, `docs/grants/` |
| 12 | `12_Legal_IP` | Licences (open-source inventory), instrument licences (ZBI, PIADS, Digital IADL), trademarks, contracts | Not started | `pyproject.toml` (licence pending) |
| 13 | `13_Insurance` | E&O, cyber, general liability certificates | Not started | — |

Access rules [INF]: investors see 00-04, 08, 10, 11; sponsor vendor-qualification sees 00, 03, 06, 07, 12, 13;
grant reviewers see what the application requires. Log every access. Watermark financial projections
"Hypothetical - not a forecast".
