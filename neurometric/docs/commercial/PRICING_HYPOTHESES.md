# Pricing hypotheses and how to test them

Prepared 2026-11-27. Labels per `docs/research/CONVENTIONS.md`. **Every price on this page is a hypothesis [HYP].**
No price has been quoted to, or accepted by, any organisation. Comparables come from
`docs/research/comparable_pricing.md` (all URLs accessed 2026-11-27).

## 1. Principles [INF]

1. **Price the evidence deliverable, not software seats.** The clinic-tool anchor is $179 per Compass licence [V];
   free academic EDC exists (Castor small-study tier [CC], REDCap [PK]). Seats lose; a decision-grade evidence
   package (validation report, home-use summary, care-partner module, audit trail) is what a sponsor or maker can
   budget against.
2. **Scope drives price, and participants drive cost.** iBCI studies have 2-15 participants [V CT.gov]; neuromod
   registries can have hundreds [V]. Quote per study-year with a participant band, not per participant.
3. **Pilot first, fixed fee, 6 months, explicit exit.** Pilots convert or end; no auto-renewal.
4. **No discounting for logos.** Discount only for data-sharing rights that improve the cross-device dataset,
   and only with the sponsor's and participants' consent.

## 2. Hypothesised price points

| Offer | Unit | Hypothesis | Model value (scenario B) | Comparable | Comparable label |
|---|---|---|---|---|---|
| Evidence pilot (makers, sponsors) | fixed fee, ≤6 months, ≤10 participants | $25-75K | $40-50K | OpenClinica Core $36K / Advanced $45K per study-year | [V] https://www.openclinica.com/pricing |
| Academic pilot | fixed fee | $10-20K | $15K | Castor free small-study tier; REDCap | [CC] / [PK] |
| iBCI early-feasibility study-year | per study-year, ≤15 participants | $100-150K | $125K | EDC Phase II year-1 $50-150K (5-50 sites) | [AE] IntuitionLabs |
| iBCI pivotal study-year | per study-year | $250-400K | $175K blended in scenario C only | EDC Phase III year-1 $150-500K+ | [AE] |
| Maker evidence program (AAC / non-invasive BCI) | per year | $60-120K | $100K | Veeva portfolio median $188K/yr | [AE] Vendr via IntuitionLabs |
| Maker evidence program (home neuromod / rehab) | per year, registry/RWE add-on | $90-175K | $150K | same; HEOR services quote-based | [AE] / [UNR] |
| Academic subcontract / research licence | per year | $25-40K | $35K | OpenClinica Launch $750/month | [V] |
| Rehab-provider subscription (SGD/AT documentation) | per site-year | $12-20K | $18K | Compass $179 perpetual licence (clinic tool floor) | [V] https://kpronline.com/purchase-compass |
| Services add-on (validation, training) | % of year-1 licence | 30-60% | inside contract value | services ratio | [AE] |
| Hourly consulting (out-of-scope work) | per hour | $200-300 | not modelled | OpenClinica $275-350/h | [V] |

Founder playbook ranges tested: pilots $25-75K (plausible; academic at the low end), $100-400K per study-year
(upper end at risk for n<15 EFS; better fit for pivotal), $100-300K/yr maker contracts (plausible only for
payer-evidence programs, not clinic tools) (`comparable_pricing.md` s5) [INF].

## 3. Tests (run during the 90-day discovery window)

| ID | Hypothesis | Test | Pass | Fail → action |
|---|---|---|---|---|
| P1 | Sponsors/makers will pay ≥$50K for a 6-month evidence pilot | Ask about past spend on comparable outside measurement work (Mom-test), then, at close, show a one-page scope with three priced options ($30K / $50K / $75K) | <3 of the first 8 qualified conversations reject ≥$50K | ≥3 reject → re-price pilots to $25-35K and shift toward grant-funded academic work (scenario A) |
| P2 | EFS sponsors will budget $100-150K per study-year | Ask how the last outside eCOA/EDC/wearable vendor was budgeted (range, line item, who signed) | ≥2 of 4 sponsors cite comparable line items ≥$100K | Price EFS at $60-90K and require multi-study scope |
| P3 | Makers fund payer-evidence programs ≥$100K/yr | Ask market-access leads what they spent on the last payer dossier / RWE study and who paid | ≥2 makers cite ≥$100K spend on evidence generation in the last 2 years | Sell as per-study RWE add-ons, not annual programs |
| P4 | Academic programs can include $25-40K/yr in grant budgets | Co-write budget pages with 2 partners for STTR/R01/CDMRP applications | 2 budgets carry the line without pushback | Offer free research licence + paid support hours |
| P5 | Rehab providers pay $12-20K/site-year | 2 AT/AAC clinic pilots; measure staff documentation time (not healthcare savings) | ≥1 site renews at ≥$12K | Fold into maker channel (maker pays for clinic tools) |
| P6 | Independence carries a premium over in-house | Ask sponsors whether FDA/payers have asked who collected home-use data | ≥3 of 8 cite a credibility or audit concern | Position as cost/speed, not independence; lower prices |

Record every price reaction verbatim in the interview log, with role, organisation type and date. Do not treat
"sounds reasonable" as acceptance; only an LOI, a purchase order or a budget line counts as evidence [INF].

## 4. What would change the model

- P1 fails → use the `prices -30%` sensitivity in `financial_model_outputs.md` (scenario B total capital $3.2M →
  $4.4M) [HYP].
- P2/P3 pass at the top of range → `prices +50%` sensitivity (B cash trough -$2.6M → -$0.9M) [HYP].
