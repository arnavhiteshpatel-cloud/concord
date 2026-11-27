# NeuroMetric commercialization strategy

Prepared 2026-11-27 by the NeuroMetric commercialization workstream. Evidence labels follow
`docs/research/CONVENTIONS.md`: [V] verified, [CC] company claim, [RF] peer-reviewed, [AE] analyst/third party,
[INF] inference, [HYP] hypothesis, [PK] prior knowledge not re-verified, [UNR] unresolved.
**All prices, willingness to pay, customer counts and market sizes are [HYP] unless a source is given.**

**Honest status.** NeuroMetric is pre-incorporation research software (not a medical device) built by a UIUC
undergraduate founder. It has simulation-only technical results, no clinical validation, no customers, no
partners and no letters of intent. No one listed in this document has been contacted. Nothing here is a claim of
interest or partnership by any organization.

Companion files: `docs/commercial/` (financial model outputs, pricing, payer matrix, proposals, outreach drafts,
pipeline, discovery plan, deck outlines) and `src/neurometric/economics/` (model code; tests in
`tests/test_economics.py`).

---

## 0. Summary

1. **Recommended entry niche [INF]:** *neutral home-use evidence of digital independence for communication and
   computer-access devices*, input-agnostic (BCI, eye-gaze, switch, EMG, voice), combining (a) passive home-use
   telemetry, (b) a short periodic home version of consensus functional tasks (implementing SRAlab DAI-style
   primitives and the Mount Sinai Digital IADL scale where licensable, not a rival index), (c) care-partner burden
   capture, and (d) a Part 11-ready evidence package. This is the competitor workstream's recommendation
   (`docs/research/competitors.md` S4) and we adopt it.
2. **Is the implantable-BCI (iBCI) market alone too concentrated? Yes.** 3 US industry sponsors have active
   motor/communication IDE studies today (Neuralink, Synchron, Paradromics; CT.gov [V]); about 5-8 are plausible by
   2028 [INF]. Neuralink (21-27 participants in 2026 [AE]) builds in-house and co-develops its COA with SRAlab;
   Synchron paused second-generation enrollment in Nov 2026 [AE]. Excluding Neuralink, the addressable iBCI universe
   is 3 organisations in 2027 rising to ~7 by 2031 [INF]. At a $125K/study-year price hypothesis, **100% penetration
   of that universe is ~$0.38M (2027) to ~$0.88M (2031) per year** [HYP], below the ~$1.8M annual opex of even the
   sponsor-infrastructure scenario (B). An iBCI-only company is not viable; iBCI is the credibility anchor of an
   input-agnostic business.
3. **Sequencing [INF]:** (i) 90-day discovery gate (Dec 2026-Feb 2027); (ii) grant-backed academic validation
   (NIH STTR Phase I with a UIUC/Carle faculty PI, target 5 Apr 2027) plus 1-2 paid pilots with non-invasive
   BCI/AAC makers or home-neuromodulation makers whose evidence gaps are already public (Cognixion, Kandu, ONWARD);
   (iii) Part 11 validation and SOC 2 in 2028 to take study-year contracts with non-dominant iBCI sponsors moving
   to pivotal (Paradromics, Precision, Synchron when enrollment resumes); (iv) rehab-provider subscriptions
   for SGD/AT justification and payer packages with HEOR partners from 2029.
4. **Model headline (all [HYP]; `docs/commercial/financial_model_outputs.md`):** 2029 commercial revenue
   A $0.38M / B $0.84M / C $1.44M / D $1.00M; 2029 ARR run-rate A $0.48M / B $1.12M / C $2.23M / D $1.33M
   (playbook: $0.23M / $1.1M / $2.8M). **No scenario reaches operating break-even by 2031.** Total capital
   2027-2031: A $1.6M, B $3.2M, C $11.8M, D $5.1M. Grants (STTR I/II, DCEO match) carry 2028-2030.
5. **Biggest commercial risks [INF]:** sponsor in-house build (Neuralink, Cognixion), SRAlab DAI becoming the free
   reference instrument, eCOA incumbents adding an access-method module (Signant+Ametris), a small buyer universe
   (the whole reachable universe at hypothesised prices is ~$4-5M/yr; section 5), and unproven willingness to pay
   for independence.

---

## 1. Business-model comparison

Scores 1-5 (5 = best for NeuroMetric now) [INF]. "Sales cycle": 5 = short. "Founder feasibility": can a
pre-incorporation undergraduate founder with advisors deliver it in the next 12-18 months?

| # | Business model | Buyer clarity | Budget | Sales cycle | Margin | Defensibility | Founder feasibility | Total /30 | Key evidence |
|---|---|---|---|---|---|---|---|---|---|
| 1 | Per-study functional testing (clinic/home task battery per study) | 4 | 3 | 3 | 3 | 2 | 3 | 18 | SRAlab DAI is a direct, sponsor-backed substitute (NCT07407725 [V]); Compass sells clinic AT testing at $179 [V] |
| 2 | Research software licensing (labs run it themselves) | 3 | 2 | 4 | 5 | 2 | 5 | 21 | Free academic alternatives: Castor free tier [CC], REDCap [PK], BCI2000 [V] |
| 3 | Sponsor evidence infrastructure (Part 11 platform per study) | 4 | 4 | 2 | 3 | 3 | 2 | 18 | eCOA/EDC commoditized (OpenClinica $36-45K/study-yr [V]); FDA may inspect IT providers (eSystems Q&A [V]) |
| 4 | **Home-outcome measurement** (home-use telemetry + periodic home tasks + care burden) | 4 | 4 | 3 | 3 | 4 | 3 | **21** | Named gap in J Neural Eng 2026 pivotal-COA workshop [RF]; iBCI guidance requires home-use data [V]; Cognixion registers daily use time as primary (NCT07871071 [V]); Anthem DME.00052 cites missing real-world use [V] |
| 5 | Clinical study operations (CRO-like) | 4 | 4 | 2 | 2 | 1 | 1 | 14 | Neuro-device CROs exist (NAMSA, Clinilabs, Qortical [CC]); needs clinical staff and insurance |
| 6 | Independent validation services (psychometric/COA validation of sponsor measures) | 3 | 3 | 3 | 4 | 3 | 2 | 18 | No BCI COA MDDT-qualified [V]; needs credentialed psychometrician |
| 7 | Academic subcontracting (grant-funded) | 5 | 2 | 3 | 3 | 2 | 5 | 20 | NIH STTR PI can stay at university [V]; BRAIN UG3/UH3 required "clinically robust" outcome measures [V, expired RFA] |
| 8 | Manufacturer SDK integration (log export / event SDK in maker software) | 3 | 3 | 2 | 4 | 4 | 2 | 18 | Apple BCI-HID integration (Synchron [CC]) shows OS-level paths; third-party access uncertain (F4) |
| 9 | Rehab outcome analytics (provider subscriptions for SGD/AT justification) | 3 | 2 | 2 | 4 | 2 | 3 | 16 | NCD 50.1 SGD documentation [V]; hospital procurement + BAA (45 CFR 160.103 [V]); clinic tools priced in hundreds of dollars [V] |
| 10 | Payer evidence preparation (dossiers, budget impact) | 3 | 3 | 3 | 4 | 2 | 1 | 16 | IQVIA MedTech/MCRA, Evidera, Avalere already serve neuro devices [CC/AE]; Neuralink already in CMS coding process [V] |

**Reading [INF].** Models 4, 2 and 7 score highest, for different reasons: 4 is the defensible need, 2 and 7 are
what the founder can deliver now. The recommended model is **4 delivered through 7 and 2 first** (grant-funded
academic deployments and research licences that generate validation evidence), then **4 sold as sponsor/maker
pilots and study-year contracts**, with 3, 8 and 10 added as *capabilities or partnerships*, not as standalone
businesses. Model 5 (CRO) is explicitly avoided: lowest defensibility, highest liability, lowest feasibility.

---

## 2. Recommended entry niche and sequencing

### 2.1 The niche
*Neutral home-use digital-independence evidence for communication and computer-access devices* [INF].

Why this niche [INF unless labelled]:
- **Least served:** sponsors log use internally; academia builds clinic instruments (SRAlab DAI, Digital IADL);
  eCOA vendors capture wearables but no access-method telemetry (`competitors.md` S1-S2).
- **Required by the field:** the iBCI-CC consensus (1 Oct 2026) calls for "flexible pathways… to generate
  real-world data" and a "shared measurement chain" from device performance to function to health outcome or
  care burden [V]; the 2026 J Neural Eng workshop names "the need to capture meaningful outcomes in home and
  daily-life environments" [RF]; FDA's iBCI guidance has a "Home Use" section and caregiver metrics [V].
- **Independence matters to payers:** Anthem DME.00052 criticises lack of independent replication and real-world
  arm use for BCI rehabilitation devices [V]. Third-party collection is more credible than sponsor self-report [INF].
- **Input-agnostic by design:** pooling across BCI, eye-gaze, switch and EMG is what no single sponsor can do,
  and it opens AAC/AT and rehab segments that are larger than iBCI.

What we deliberately do **not** do: control devices or stimulation; build a proprietary rival index to the
SRAlab DAI or the Digital IADL scale; make diagnostic or treatment claims (which could make the software a
device; `regulatory_landscape.md` s10); promise coverage outcomes.

### 2.2 Sequencing

| Phase | Window | Focus | Exit criterion |
|---|---|---|---|
| 0. Discovery gate | Dec 2026 - Feb 2027 (day 0-90) | 20+ interviews, incorporate, OTM IP confirmation, STTR faculty partner, iBCI-CC membership | 90-day gate (section 8) |
| 1. Validation + first pilots | Mar - Dec 2027 | NIH STTR Phase I submission 5 Apr 2027 [V date]; academic deployments (JNERL stroke/BCI; SRAlab DAI-to-home bridge if invited); 1-2 paid pilots with Cognixion / Kandu / ONWARD-type makers | ≥1 paid pilot delivered; reliability data in healthy volunteers and a first patient cohort under a partner IRB |
| 2. Study infrastructure | 2028 | Part 11 validation package, SOC 2 Type I, insurance; study-year contracts; non-dominant iBCI sponsors preparing pivotal | ≥2 study-year contracts; Phase I aims met; Phase II submitted |
| 3. Expansion | 2029-2031 | Rehab-provider subscriptions (SGD/AT justification), manufacturer SDK integrations, payer-evidence packages with HEOR partners, MDDT exploration | ARR and gross-margin targets in the chosen scenario |

### 2.3 Adjacent entry points that keep the long-term vision

| Entry point | Why it is adjacent (same capability) | Public trigger | First prospects | Label |
|---|---|---|---|---|
| AT/AAC makers and rehab hospitals for SGD/AT justification | Same input-agnostic telemetry + functional tasks; SGD funding needs documentation of medical communication use | NCD 50.1 covers speech generation and messaging, not general computing [V]; Tobii Dynavox reports health-economic studies and "drawn-out" reimbursement [CC] | Tobii Dynavox, PRC-Saltillo, Control Bionics; SCI/TBI Model Systems centres [PK] | [INF] |
| Home neuromodulation / home rehab makers | Same home-phase evidence gap; read-only logs + wearables + ZBI | ONWARD home 510(k) K251821 with no new clinical data [V]; PoNS stroke 8-week home phase (K253061) [V]; Anthem DME.00052 [V]; Mobia GRASP registry n=1,000 [V] | ONWARD, Kandu, Bioness, Mobia (tier 1) | [V]/[INF] |
| Non-invasive BCI | Same communication/computer-access outcomes; smaller budgets but faster cycles | Cognixion NCT07871071 primary = daily use time per input modality; ZBI secondary [V] | Cognixion, g.tec | [V]/[INF] |
| Academic programs | Grant budgets; validation evidence; reference sites | BrainGate, Pitt, UC Davis, JHU, UMC Utrecht home-use studies [V registry] | JNERL (UIUC/Carle), SRAlab, BrainGate, UMC Utrecht | [V]/[INF] |

The long-term vision (a neutral, shared evidence layer for neural interfaces, potentially an MDDT-qualified COA
implementation) is kept: every adjacent deployment produces cross-device data on the same event schema, which is
the asset an iBCI sponsor cannot build alone [INF].

---

## 3. Is the iBCI market alone too concentrated?

**Answer: yes** [INF, based on the counts below].

| Measure | Value | Label / source |
|---|---|---|
| US industry sponsors with active motor/communication iBCI IDE studies (Nov 2026) | 3 (Neuralink, Synchron, Paradromics) | [V] CT.gov via `competitors.md` S5 |
| Plausible by 2028 | ~5-8 (adds Precision, Blackrock, Echo, CorTec; speculative Merge, Axoft, Neurosoft) | [INF] `competitors.md` S5 |
| Largest sponsor's share of implanted participants | Neuralink ~21-27 participants in 2026 vs single-digit enrollment targets elsewhere | [AE] press; [V] CT.gov targets |
| Largest sponsor as buyer | Unlikely: in-house telemetry, Webgrid, COA co-development with SRAlab, own CMS coding request | [V] CMS ICD-10-PCS Topic #12; [INF] |
| Second sponsor | Synchron paused second-generation enrollment Nov 2026 | [AE] |
| Participants per EFS | 2-15 | [V] CT.gov |
| Addressable universe excl. Neuralink | 3 (2027) → 5 (2028) → 6 → 6 → 7 (2031) | [INF] `MARKET_UNIVERSE` in `financial_model.py` |
| Revenue at 100% penetration, $125K/study-year | $0.38M (2027) → $0.88M (2031) per year | [HYP] arithmetic |
| Competitor workstream ceiling | 5-8 sponsors × 1-2 studies × $100-400K = $0.5-6.4M at full penetration; realistic $0.3-2M | [HYP] `competitors.md` S5 |
| Annual opex of the leanest sponsor-infrastructure scenario (B) in 2030 | ~$1.7M (plus ~$0.55M COGS) | [HYP] model |

**Falsification:** the verdict would change if ≥6 US iBCI sponsors have registered IDE studies by end-2027 **and**
≥3 issue requests for third-party outcome services (`competitors.md` S5).

---

## 4. Pricing hypotheses (summary; detail in `docs/commercial/PRICING_HYPOTHESES.md`)

| Offer | Hypothesis | Comparable | Label | Test |
|---|---|---|---|---|
| Evidence pilot (6 months) | $25-75K; model uses $40-50K for makers/sponsors, $15K academic | OpenClinica Core/Advanced $36-45K per study-year [V]; small EDC study $10-50K yr-1 [AE] | [HYP] | ≥3 of first 8 qualified sponsor/maker conversations will not consider ≥$50K → revise down (comparable_pricing.md s5) |
| iBCI study-year (EFS) | $100-150K | EDC Phase II $50-150K yr-1 [AE]; EFS n=2-15 [V] | [HYP] | Proposal-option test (3 scoped options with prices) in ≥4 sponsor conversations |
| iBCI study-year (pivotal) | $250-400K | EDC Phase III $150-500K+ [AE] | [HYP] | Only after an EFS customer; test with pivotal-preparing sponsors |
| Maker evidence program | $100-300K/yr (model base $100-150K) | Veeva median $188K/yr [AE] | [HYP] | Frame around payer evidence (Anthem DME.00052), not software seats |
| Academic subcontract/licence | $15-40K/yr | Castor free tier [CC]; REDCap free [PK]; OpenClinica Launch $750/mo [V] | [HYP] | Budget lines in ≥2 grant applications written with partners |
| Rehab-provider subscription | $12-20K/site-yr | Compass $179/licence [V] (floor, clinic tool) | [HYP] | Pilot at ≥2 AT/AAC clinics; measure documentation time saved (not healthcare savings) |

---

## 5. Bottom-up market analysis: plausible initial customers (organisations, not patients)

Method [INF]: count named or registry-identifiable organisations that could plausibly buy in each year, from
`prospects.md`/`prospects.csv` (67 records; 5 Tier-1, 26 Tier-2, 27 Tier-3), `competitors.md` S5 and
`neuromodulation_market.md`. Patients are never counted. The same table is the ceiling enforced by the model.

| Segment | 2027 | 2028 | 2029 | 2030 | 2031 | Named examples | Source / label |
|---|---:|---:|---:|---:|---:|---|---|
| Implantable BCI sponsors (US, excl. Neuralink) | 3 | 5 | 6 | 6 | 7 | Synchron, Paradromics, Precision; later Blackrock, Echo, CorTec | `competitors.md` S5 [V for 3 active; INF for ramp] |
| Non-invasive BCI and AAC/AT makers | 5 | 7 | 9 | 10 | 11 | Cognixion, g.tec, Tobii Dynavox, PRC-Saltillo, Control Bionics, Smartbox, Eyegaze Inc., AbleNet, Augmental | `prospects.md` s3 (AAC/AT 3 T2 + 6 T3) [INF] |
| Home neuromodulation / rehab-device makers | 5 | 7 | 9 | 11 | 12 | ONWARD, Kandu, Bioness, Mobia (T1); Myomo, Cala, Phantom Neuro; BrainQ, Motus Nova | `prospects.md` s3 (4 T1 + 2 T2 + 9 T3), `neuromodulation_market.md` [INF] |
| Academic BCI / rehab programs | 14 | 16 | 18 | 19 | 20 | BrainGate, Pitt RNEL, UC Davis, JHU, UCSF, UTHealth, Case Western, Miami, UMC Utrecht, Calgary, EPFL, SRAlab, JNERL | `prospects.md` (14 Tier-2 academic) [V registry; INF] |
| Rehab hospitals and AT/AAC clinics | 15 | 18 | 22 | 26 | 30 | SCI/TBI Model Systems centres, AT/AAC clinics at large rehab hospitals | [PK] counts not re-verified |
| **Total plausible initial customers** | **42** | **53** | **64** | **72** | **80** | | [INF] |

**Revenue pool at 100% penetration** (universe × base contract-value hypothesis; [HYP]):
2027 $2.4M; 2028 $3.3M; 2029 $4.0M; 2030 $4.5M; 2031 $5.0M (largest pools: home neuromod/rehab makers $1.8M and
AAC/non-invasive BCI makers $1.1M in 2031; iBCI $0.9M).

Implications [INF]:
- The reachable US-centred universe at the hypothesised prices is small (~$5M/yr by 2031). Scenario B needs
  ~$3.3M revenue at its 2031 cost base to break even, i.e., about two-thirds of the entire universe. A venture-scale
  outcome therefore depends on (a) prices toward the top of the playbook ranges (validated by discovery), (b) multiple
  studies per customer (pivotal + post-market + registries), (c) Europe (EPFL, UMC Utrecht, Clinatec, Smartbox,
  Tyromotion) and/or (d) extension into neurology eCOA modules via partners.
- Rehab providers are the largest count but the smallest price; they are a phase-3 volume play, not an entry point.

---

## 6. Financial model (summary)

Driver-based model in `src/neurometric/economics/financial_model.py` (every input carries a label and source);
outputs regenerated into `docs/commercial/financial_model_outputs.md`. All figures [HYP].

| Scenario | 2029 revenue | 2029 ARR | 2031 revenue | GM 2029 | Operating break-even | Total capital 2027-31 |
|---|---:|---:|---:|---:|---|---:|
| A Small independent evidence software company | $0.38M | $0.48M | $0.65M | 45% | after 2031 | $1.57M |
| B Sponsor-funded clinical research infrastructure | $0.84M | $1.12M | $1.42M | 43% | after 2031 | $3.22M |
| C Broader neurotech evidence platform | $1.44M | $2.23M | $3.18M | 49% | after 2031 | $11.84M |
| D Rehab & AT expansion | $1.00M | $1.33M | $1.71M | 45% | after 2031 | $5.14M |

What the model says [INF]:
1. The playbook Year-3 ARR hypotheses are arithmetically reachable (B ≈ base $1.1M; C ≈ 80% of upside $2.8M;
   A above the $0.23M conservative case) **but none of the scenarios breaks even by 2031** at the hypothesised prices
   and a services-heavy delivery model. Prices +50% in B bring the cash trough from -$2.6M to -$0.9M but still no
   operating break-even by 2031.
2. Capital: the playbook's $150-400K (months 0-12) is at or slightly below what 2027 needs (B needs ~$0.39M with a
   3-month buffer), and $1.5-3M (months 12-30) covers 2028-2029 in B and D. B then needs a further ~$0.8M in
   2030-2031; C and D assume a 2030 growth round ($8M / $3M) and still need ~$0.3-0.4M of bridge in 2027-2029.
3. Grants are structural, not optional: removing them raises B's total capital need from $3.2M to $5.0M.
4. Gross margin starts low (pilots, setup-heavy) and reaches ~55-63% by 2031 only if delivery hours fall ~30% as
   tooling matures; +30% delivery hours costs B ~$0.6M of extra capital.
5. Recommended financial posture: run as A (lean, grant-backed) until the 90-day and 12-month gates; move to D if
   neuromod/AAC makers sign first, to B if iBCI sponsors sign first; C only with a validated price point and
   evidence that buyers exist beyond the US-centred universe.

Care-partner time economics (`src/neurometric/economics/care_economics.py`) are kept separate and guarded: any
valuation is labelled **hypothetical scenario** unless fed an observed care-partner-time effect with a confidence
interval, and the module refuses to convert task-time gains or care time into healthcare cost savings. Default
replacement rate: BLS median wage for home health and personal care aides, $17.21/h (2025 median pay; median annual
$35,800 in May 2025) [V] https://www.bls.gov/ooh/healthcare/home-health-aides-and-personal-care-aides.htm
(accessed 2026-11-27).

---

## 7. Competitive risks

| Risk | Severity | Evidence | Mitigation [INF] |
|---|---|---|---|
| SRAlab DAI (with Neuralink) becomes the free reference digital-independence COA | HIGH | NCT07407725: cross-device, psychometrics, in-clinic and at-home sessions; primary completion est. 2026-12 [V] | Implement/host, do not compete; offer DAI-to-home bridge; contribute to iBCI-CC |
| Sponsor in-house build | HIGH | Neuralink telemetry and Webgrid [AE/V]; Cognixion registers our endpoint stack in-house (NCT07871071) [V] | Sell independence, cross-sponsor comparability and audit-ready packaging; integrate with sponsor logs read-only |
| eCOA incumbents add an access-method module | MED-HIGH (latent) | Signant acquired Ametris (wearables) 2026-05-14 [V]; Clario under Thermo Fisher with PPD Evidera [AE] | Partner/white-label (Castor, OpenClinica); speed to 2 reference customers (F6) |
| Instrument standards settle on clinic tests only | MED | Falsifier F5 (`competitors.md`) | Keep home tasks modular; participate in Endpoints WG |
| Third-party OS-level telemetry blocked | MED | Apple controls BCI-HID logging access [INF] | App-level SDK and sponsor-export import (DECISIONS D-008) |
| HEOR consultancies own payer packaging | MED | IQVIA MedTech/MCRA, Evidera, Avalere [CC/AE] | Supply primary functional RWD to them; partner, do not compete |
| Small buyer universe and trial pauses | HIGH | section 5; Synchron pause [AE]; BrainQ pivotal terminated for poor accrual [V] | Input-agnostic segments; grants; Europe later |
| Liability and data-protection exposure | MED | Part 11, FDA may inspect IT providers [V]; HIPAA BA status when deployed by providers [V]; state neural-data laws [V/PK] | E&O/cyber insurance (budgeted [HYP]); BAA templates; legal review of neural-data definitions |

---

## 8. The 90-day gate

**Note on provenance:** the founder playbook text is not in this repository (`neuromodulation_market.md` notes it
was not found). The gate below follows the brief ("≥2 LOIs etc.") and the research files; the founder should
reconcile wording and numbering with the playbook [INF].

Window: day 0 = 1 Dec 2026, day 90 = 28 Feb 2027.

| # | Gate criterion | Threshold | Evidence to file in the data room |
|---|---|---|---|
| G1 | Letters of intent | **≥2 signed, non-binding LOIs** for a paid pilot (≥$25K [HYP]) from sponsors or makers | LOI PDFs (not binding, no exclusivity) |
| G2 | Discovery depth | ≥20 interviews across ≥4 interviewee types (`interview_guides.md`); ≥8 qualified sponsor/maker conversations | Interview log with 24-h scoring |
| G3 | Price signal | Fewer than 3 of the first 8 qualified sponsor/maker conversations reject ≥$50K for a 6-month pilot | Price-test log (`PRICING_HYPOTHESES.md`) |
| G4 | Academic anchor | ≥1 faculty partner willing to be NIH STTR PI (or co-I) for 5 Apr 2027, or a documented decision to target 5 Sep 2027 | Email/letter of intent to collaborate (no commitment implied before signed) |
| G5 | Company basics | Incorporated; UIUC OTM confirms founder ownership of code; SAM/UEI, Grants.gov, eRA Commons started (6+ weeks) | Certificate, OTM letter, registration receipts |
| G6 | Technical demonstration | End-to-end demo on simulation and one healthy-volunteer session with ≥2 input methods; no clinical claims | Demo video, experiment summaries |
| G7 | Neutrality and access | ≥2 makers confirm read-only log export or app-level SDK is feasible (or explain why not) | Interview notes |

**Decision:** pass = G1 + G2 + at least four of G3-G7 → proceed to phase 1 with pilots. Partial (G2 met, G1 not) →
continue as grant-funded research software (scenario A posture) for one more 90-day cycle. Fail (G1 and G4 both
missing) → stop the sponsor-sales track; keep NeuroMetric as an open research tool or stop. Detailed decision rules
E1-E9 are in `docs/commercial/CUSTOMER_DISCOVERY_PLAN.md`.

---

## 9. Open items

- Founder playbook reconciliation (90-day gate wording; E1-E9 numbering).
- Prices for COA licences (ZBI, PIADS, QUEST), SOC 2 and insurance quotes [UNR].
- 2026 NIH SBIR/STTR caps from the primary NIH notice; NIDILRR FY28 timing [UNR].
- Whether MyARCEX, PoNS controller and IpsiHand logs are exportable [UNR].
- SRAlab DAI licensing intent and publication timeline [UNR].
