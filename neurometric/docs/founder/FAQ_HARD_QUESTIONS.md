# Hard questions and honest answers

Thirty questions investors, clinicians, device sponsors and IRB reviewers are likely to ask, with answers
grounded in the research files. Prepared 2026-11-27. Labels follow
[`../research/CONVENTIONS.md`](../research/CONVENTIONS.md). The levels L1–L8 are defined in
[`KNOWLEDGE_BASE.md`](KNOWLEDGE_BASE.md) §0.

Ground rules for using these answers:
- Say "we don't know yet" when that is true. Every answer below separates what is **verified**, what is
  **inferred**, and what is a **hypothesis**.
- Never claim validation, compliance, partnerships or customers that do not exist. As of today NeuroMetric has
  research software, simulations, protocols and drafts — no human data, no customers and no agreements.
- Short version first (the line in bold), then the detail.

---

## Investors

### Q1. "Isn't Shirley Ryan AbilityLab already doing this?"
**Partly, yes — and we treat that as validation of the need, not as something to compete with head-on.**
- What SRAlab is doing ([V], [`clinical_trials.md`](../research/clinical_trials.md) §1): NCT07407725, a
  ~60-person single-site crossover study with Neuralink as collaborator, building a *Digital Assessment
  Interface* index from performance tasks (click, scroll, type, drag in simulated dADLs) plus NASA-TLX, SUS,
  modified COPM and PIADS, anchored to Section GG. Primary completion is estimated for Dec 2026. IPD will not
  be shared; the software appears custom.
- Our analysis rates it the most direct competitor ([INF], [`competitors.md`](../research/competitors.md) S3).
- What it is not: a home-deployable, multi-site, openly specified, input-agnostic system with real-world use
  telemetry, care-partner burden and a Part 11-ready evidence package. A development-stage, cross-sectional
  index from one site leaves room for that ([INF]).
- Our stance: implement and extend consensus instruments rather than build a rival index; approach the DAI
  team as a potential collaborator, through a faculty PI
  ([`../clinical/SRALAB_APPROACH.md`](../clinical/SRALAB_APPROACH.md)).
- What would prove us wrong (falsification test F1 in `competitors.md` S4): SRAlab/Neuralink or the iBCI-CC
  publish a free, home-administrable DAI with its own logging, adopted by ≥ 2 other sponsors by end-2027.

### Q2. "Why would Neuralink use you?"
**Probably they won't, at least not first — and the plan does not depend on them.**
- Neuralink already captures usage telemetry in-house, runs its own benchmark (webgrid BPS), co-develops a COA
  with SRAlab, and is handling CMS coding and NTAP itself ([V]/[AE], `competitors.md` B1).
- The case for Neuralink would only be independence: if FDA or CMS want third-party collection or
  cross-device comparison that sponsor self-report cannot credibly provide ([INF]). That is a later, optional
  upside.
- First customers are non-dominant iBCI sponsors moving toward pivotal studies, non-invasive BCI and AAC makers,
  home neuromodulation companies, and academic programmes on grant budgets ([INF], `competitors.md` S4).

### Q3. "Isn't the iBCI market too small and concentrated?"
**Yes, for an iBCI-only business. That is why NeuroMetric is input-agnostic.**
- Three industry sponsors have active US motor/communication iBCI IDE studies today; roughly 5–8 are plausible
  by 2028; one dominant sponsor is a likely non-buyer, and one (Synchron) reportedly paused enrolment
  ([V]/[AE]/[INF], `competitors.md` S5).
- Revenue ceiling at full penetration of that segment is in the low millions per year ([HYP], same section).
- The business has to include AT and AAC makers, non-invasive BCI, rehab and home neuromodulation sponsors
  (ARC-EX, PoNS, Vivistim, IpsiHand; [`neuromodulation_market.md`](../research/neuromodulation_market.md)), and
  grant-funded academic work. iBCI is the credibility anchor, not the revenue base.

### Q4. "Why won't Signant, Clario or Medidata just add this?"
**They could. Our bet is speed, domain depth and neutrality in a niche too small for them today.**
- Large eCOA platforms have Part 11 infrastructure, wearables and scale, but no BCI/AT task batteries or
  access-method telemetry were found ([INF], `competitors.md` overview and S3).
- Signant + Ametris is rated a latent MED-HIGH threat (F6: an eCOA vendor launches a BCI/AT module before we
  have two reference customers).
- Strategy: integrate with or white-label onto eCOA/EDC for Part 11 capture rather than compete on it
  (`competitors.md` S2 item 5).

### Q5. "What's the moat if your task definitions are open?"
**Openness is deliberate; the defensible assets are validation evidence, data across devices, and trust.**
- A neutral measure is only useful if others can inspect and adopt it (MDDT logic: a qualified tool is accepted
  without re-confirming suitability in the same context of use; [V] `regulatory_landscape.md` §5).
- Hard-to-copy assets [INF/HYP]: published psychometric evidence per modality and population; a cross-device
  reference dataset; Part 11 validation package; relationships with sites and sponsors; licences for
  instruments. None exist yet — they are the plan.

### Q6. "Who pays, and how much?"
**Unknown; current figures are hypotheses to test in discovery.**
- Founder price hypotheses: pilots $25–75K; $100–400K per study-year; $100–300K/yr maker contracts ([HYP],
  [`comparable_pricing.md`](../research/comparable_pricing.md)).
- Public comparables are scarce: e.g. OpenClinica EDC at $36–45K per study-year list price ([V], same file).
  No public price exists for any BCI-specific outcome service.
- Falsification test F3: no paid pilot ≥ $25K within 9 months of outreach (`competitors.md` S4).

### Q7. "Why are you the right founder?"
**Honest answer: domain-relevant engineering (Concord), biomedical research experience, and the discipline to
label evidence — but clinical, regulatory and psychometric credibility must come from advisors and partners.**
- Plan: work under a faculty PI and university IRB for human studies (the SRAlab outreach note says the first
  email should come with or from a faculty advisor); recruit a rehab clinician, a psychometrician and a
  regulatory advisor; follow the 12-week plan in [`LEARNING_GUIDE.md`](LEARNING_GUIDE.md).

### Q8. "Isn't this just Concord repackaged? Who owns the IP?"
**No code was copied; IP ownership still needs a formal answer.**
- Concord is marked "Proprietary (internal preview)" with no LICENSE file; NeuroMetric is written clean-room and
  reuses concepts with attribution, plus an importer for Concord recordings (`DECISIONS.md` D-002;
  [`concord_reuse_audit.md`](../research/concord_reuse_audit.md)).
- The founder is a UIUC student; university IP policy may apply to work done with university resources. This
  needs a written determination from the university's technology transfer office before fundraising [INF].

### Q9. "What if iBCI pivotal timelines slip?"
**They probably will for some sponsors; the input-agnostic design and the neuromodulation segment are the
hedge.**
- Evidence of slippage risk: Synchron's reported enrolment pause (Nov 2026; [AE]); most US studies are still
  early feasibility with safety-only primary endpoints ([V] `clinical_trials.md` §3.1).
- Neuromodulation devices already on the market have unobserved home phases now (PoNS 8 weeks independent home
  use; ARC-EX home 510(k) relying on prior clinical data; [V] `neuromodulation_market.md`).

---

## Clinicians

### Q10. "How is this different from ARAT, COPM or Section GG?"
**Those measure body function, goals or independence; NeuroMetric measures how well a person operates digital
interfaces (L3) and completes digital tasks (L4–L5), across any access method.**
- ARAT/GRASSP/FMA measure arm and hand function — relevant when a BCI drives an effector, not when it drives a
  computer ([`published_bci_functional_measures.md`](../research/published_bci_functional_measures.md) §4.5).
- Section GG is CMS's independence scale but is not validated for digital tasks (same file §4.2).
- We intend to *use* such instruments as anchors and comparators, not to replace them.

### Q11. "Will this exhaust my patients?"
**It might, which is why burden is a design constraint and is measured.**
- The SRAlab study requires tolerating ~3-hour sessions ([V] `clinical_trials.md` §1); our Stage 2 plan is two
  ~75-minute visits ([`../../CLINICAL_VALIDATION_PLAN.md`](../../CLINICAL_VALIDATION_PLAN.md) §4).
- The validation plan includes rest rules, pre/post fatigue ratings and position-in-battery analysis (same
  plan, Stage 1). Short home "core" batteries are the target for people with ALS or high SCI.

### Q12. "Is it fair to compare a switch user with an eye-gaze user?"
**Not on raw scores. Comparisons are within person or modelled with modality as a factor, and some metrics do
not apply to some modalities.**
- Selection time with AT includes scan intervals or dwell; it is reported as "selection time", with settings
  stored, never as reaction time ([`browser_timing.md`](../research/browser_timing.md) §1).
- Fitts throughput is not computed for switch scanning (Stage 2 plan: "P1 is not computed for D").
- Measurement invariance across modalities is an open validation question, not an assumption.

### Q13. "What's your MCID?"
**We don't have one, and nobody has one for these measures yet. Claiming one now would be wrong.**
- No BCI-specific COA has an MCID or MDDT qualification; ITR/BPS/WPM have none
  ([V]/[PK], `published_bci_functional_measures.md` §6).
- How we will estimate it (methods in [`methods_references.md`](../research/methods_references.md) §E):
  anchor-based (global rating of change and clinician ratings, anchors correlating ≥ ~0.3–0.5 with change),
  triangulated across anchors, checked with Devji et al.'s credibility criteria, with distribution-based values
  (0.5 SD, SEM, MDC) as support only. An MCID smaller than the MDC is undetectable in an individual.
- Timing: needs longitudinal data in the target population with real change — after reliability (Stage 3)
  and in Stage 4+.

### Q14. "Is the test reliable?"
**In simulation, some metrics are; in humans, unknown until the Stage 3 test–retest study.**
- Simulation reliability is an *upper bound*: simulated users have no bad days, illness, or set-up variation.
- Stage 3 will report ICC(A,1) with 95% CI, SEM from variance components, MDC95 and Bland–Altman limits
  (`methods_references.md` §D; `CLINICAL_VALIDATION_PLAN.md` §5).
- For BCIs, day-to-day decoder drift is real variation in the system, so the protocol must define which
  sources of variation the "retest" includes (COSMIN 2020 for performance instruments).

### Q15. "Throughput is a lab number. Does it predict real life?"
**That is exactly the open question, and we will test it rather than assume it.**
- Dohle et al. found clinical outcomes in only 17.9% of iBCI studies ([V]); lab-to-life links are mostly
  unmeasured.
- Correlations between L3 and L5 can be confounded by ability, practice, care-partner support, selection,
  reverse causation and regression to the mean ([`KNOWLEDGE_BASE.md`](KNOWLEDGE_BASE.md) §9). Our measurement-
  chain study uses within-person longitudinal designs to test the link
  ([`../clinical/MEASUREMENT_CHAIN_STUDY.md`](../clinical/MEASUREMENT_CHAIN_STUDY.md)).

### Q16. "Can I use the scores to make clinical decisions?"
**No. NeuroMetric is research software, not a diagnostic or treatment tool.**
- Software that interprets device data to guide therapy may become device software
  ([INF], [`regulatory_landscape.md`](../research/regulatory_landscape.md) §10). We will not make such claims
  without a regulatory determination (513(g) or Pre-Sub).

---

## Device sponsors

### Q17. "Are you a medical device?"
**As intended today — measuring and reporting task performance for research and trial endpoints, with no
diagnostic or treatment claim — most likely not. That is our analysis, not an FDA determination.**
- FD&C §520(o)(1)(D) excludes software that only transfers, stores, converts or displays device data, "unless
  such function is intended to interpret or analyze" it ([V] `regulatory_landscape.md` §10).
- Computing a clinical index used to monitor disease or adjust therapy could be device software ([INF]).
- Either way, FDA's DHT guidance expects verification and validation "regardless of whether the DHT meets the
  definition of a device" ([V] same file §3).
- If clinical-decision features are ever planned: intended-use statement, then a 513(g) or Pre-Sub.

### Q18. "Is this Part 11 compliant?"
**Not yet, and we will not say it is until there is a validation package and a sponsor audit. The design
targets Part 11 controls.**
- Part 11 §11.10 requires validation, secure time-stamped audit trails, access controls and more; the Oct 2024
  eSystems Q&A says regulated entities stay responsible when using IT service providers and FDA may inspect
  those providers ([V] `regulatory_landscape.md` §4).
- If our platform is the durable repository for DHT data in an IDE study, it is the source-data location
  ([V]/[INF], same section).
- What exists: an audit log, permissions and security modules in `src/neurometric/study/` (research code,
  unvalidated). What is missing: a formal computer-system validation package, SOPs, change control, training
  records, e-signature controls and an independent audit. Near-term, running on an eCOA/EDC partner's Part
  11 platform may be faster (`competitors.md` S2).

### Q19. "Is your simulator valid?"
**It is valid for one narrow purpose — checking that metrics respond correctly to known, injected
degradations — and not for predicting human performance.**
- What it is: a closed-loop model of a user perceiving a degraded cursor with feedback delay and correcting
  (`DECISIONS.md` D-005, after Willett et al. 2019), with explicit degradation parameters (noise, latency,
  dropout, drift, false/missed selections) defaulting to none (`src/neurometric/simulator/decoder.py`).
- What it can show: metric sensitivity, direction and monotonicity under each degradation; whether metric code
  is correct (observable-only metrics validated against stored ground truth, D-006); statistical properties
  of analysis pipelines.
- What it cannot show: human reliability, MCIDs, or that any L3 change matters at L5–L6. Reliability
  estimated in simulation is an upper bound.
- External checks so far: the metric pipeline was run on real (non-human primate, hand-controlled, not BCI)
  reaching data from the Neural Latents Benchmark MC_RTT set; this checks the pipeline on real kinematics, not
  the simulator's realism (`experiments/results/X1_external_mc_rtt/`; dataset licence CC-BY-4.0 [V]).
- Next: compare simulator output ranges with published human BCI results and public human datasets
  ([`datasets.md`](../research/datasets.md)), then with Stage 1–2 human data.

### Q20. "Why not just use webgrid BPS?"
**Use it — alongside measures that cover what it misses.**
- BPS is a useful peak throughput benchmark, but it is a company task: sensitive to grid size, click types and
  error definition; not a COA; not validated against function
  ([CC]/[INF], `published_bci_functional_measures.md` §3.3).
- It says nothing about latency (Paradromics' critique; [CC]), typical daily performance, text entry,
  real-world use or independence. We compute achieved bitrate on comparable grid tasks and report peak and
  typical performance side by side.

### Q21. "Browsers aren't millisecond-accurate. Why trust your timing?"
**We agree, and we don't claim millisecond accuracy for absolute times.**
- Hardware-validated studies found browser response times lag true times by tens of milliseconds, with SD
  from under 1 ms to ~28 ms depending on platform ([RF] `browser_timing.md` §3).
- Primary analyses are within-person, same device/browser/modality comparisons; absolute times carry a
  device-class lag band measured on our own photodiode bench ([`EQUIPMENT.md`](EQUIPMENT.md) §8).

### Q22. "Will you publish data that makes our device look bad?"
**Neutrality is the product, so we cannot promise favourable results — but we can promise process.**
- Pre-specified analysis plans, sponsor data rights set in contract, de-identified and aggregated publication
  rules agreed in advance, and no cross-sponsor comparisons published without consent [INF/HYP terms to
  negotiate].
- The reason a sponsor buys third-party measurement is credibility with FDA and payers, which depends on not
  being able to suppress inconvenient results ([INF]).

### Q23. "How will you capture real-world use when Apple and Google don't let third parties monitor apps?"
**Mostly through sponsor exports and in-battery telemetry, not OS surveillance.**
- iOS: no cross-app usage export (Screen Time report extensions cannot send data off the device); Linux/Wayland:
  no global input observation; Android: limited usage stats with user grant; Windows: technically possible
  but we must supply consent, indicator and kill switch ([V] `platform_matrix.md` §1).
- Three tiers: in-battery telemetry always; an opt-in activity agent on Windows/Android/ChromeOS (durations and
  counts only); sponsor or manufacturer aggregate exports under a data-use agreement — usually the most
  practical source for BCI use.
- Falsification test F4: platforms and sponsors both refuse (`competitors.md` S4).

### Q24. "Will FDA accept your measures as endpoints?"
**Not automatically. FDA accepts endpoints that are fit for purpose in a context of use; that requires
evidence we have not generated yet.**
- FDA's iBCI guidance asks pivotal sponsors for a validated primary effectiveness endpoint with an MCID, while
  allowing feasibility studies to use non-validated endpoints ([V] `regulatory_landscape.md` §1).
- PFDD Guidance 3 (final, Oct 2025, CDRH co-issuer) sets the logic: concept of interest → context of use →
  evidence ([V] §2). No BCI COA is MDDT-qualified ([V] §5); MDDT qualification would be a multi-year effort.
- Near-term role: exploratory and secondary endpoints in early studies, generating the validation evidence.

### Q25. "How does this help us get paid by CMS?"
**By measuring the outcomes payers say they need and almost nobody registers: function, real-world use, care
burden and comparison with existing AT.**
- iBCI-CC (Oct 2026): care-partner burden, functional communication and participation are key outcomes
  "particularly for payor decision-making" ([V] `regulatory_landscape.md` §6).
- No US implanted-BCI company registers a caregiver-burden outcome ([V] `clinical_trials.md` §3.1 item 7).
- Medical-necessity framing: separate *medical* uses (communication of needs, emergency calls, self-management)
  from general computing, because NCD 50.1 covers speech generation and messaging but not general computing
  ([V] `health_economics_payer.md` §1).
- RAPID could make outcomes agreed with CMS before the IDE the coverage endpoints, but it is still proposed
  ([V] `regulatory_landscape.md` §7.1).

---

## IRB reviewers

### Q26. "How do you avoid surveillance?"
**By collecting only what the study needs: durations, counts, modality and AT settings — never content — with
explicit opt-in, visible indicators and easy withdrawal.**
- Charter ([V scope rules], [`platform_matrix.md`](../research/platform_matrix.md)): never keystroke content,
  screenshots, passwords, messages, browsing history, screen content or gaze coordinates; no covert monitoring;
  no bypassing OS permissions. APIs capable of reading key codes or screen content are marked AVOID even
  where the OS would allow them silently.
- Telemetry agents aggregate on the device to daily totals; participants can pause or withdraw; the default
  build ships with no OS-level hooks (`DECISIONS.md` D-008).
- Care partners and household members are not monitored; a shared device is flagged, not profiled.

### Q27. "Do you collect neural data? Do neural-data privacy laws apply?"
**NeuroMetric does not record raw neural signals; it logs interaction events. Whether decoded outputs count as
"neural data" under some state laws needs legal review.**
- Colorado HB24-1058 defines neural data as information generated by measuring nervous-system activity ([V]);
  California, Montana and Connecticut have related laws ([PK]) (`regulatory_landscape.md` §8.1).
- Decoded clicks arriving as OS events are arguably not "generated by the measurement of" nervous-system
  activity, but this is an open legal question ([INF]). Sponsor exports might include signal-quality
  summaries; we would treat those as sensitive.

### Q28. "Is NeuroMetric a HIPAA business associate?"
**It depends on who deploys it.**
- Deployed by a hospital or rehab provider (a covered entity): likely a business associate, needing a BAA and
  Security Rule controls ([V] definition 45 CFR 160.103; [INF] application).
- Contracted by a device sponsor for an IDE study: data usually flow under research consent and authorization;
  HIPAA may not apply directly, but state privacy laws and FTC rules might (`regulatory_landscape.md` §8.2).
- Stage 1–3 studies run on a university-hosted instance under the university's IRB and data management plan
  (`../clinical/stage1_protocol.md` §6).

### Q29. "How do people with locked-in syndrome or advanced ALS give informed consent?"
**Through their own communication method, with extra time, comprehension checks and a witness — and by
excluding people who cannot reliably communicate yes/no.**
- Present information in accessible formats; allow consent through AAC, eye gaze or a reliable yes/no
  signal; confirm understanding with teach-back questions; document the method used; involve a witness or
  legally authorized representative where state law and the IRB require it [PK/INF].
- Re-confirm willingness at each session (ongoing consent), especially as disease progresses; provide a
  simple, always-available stop signal.
- Stages 1–3 enrol able-bodied adults; AT-user stages need this procedure approved first
  ([`../irb/protocol_summary.md`](../irb/protocol_summary.md)).

### Q30. "Small populations are easy to re-identify, and a care partner might use the device. How do you
handle that?"
**Minimise, aggregate, separate identifiers, restrict access, and flag rather than guess attribution.**
- Re-identification: iBCI cohorts are tiny and publicised, so dates, sites and device model can identify
  people. Pseudonymous IDs; identifiers kept separately; coarsened dates and small-cell suppression in
  reports; no individual-level public release without specific consent [INF].
- Attribution: a downstream system cannot always tell who operated the device (input uncertainty;
  `KNOWLEDGE_BASE.md` §4.5). Sessions are tagged "independent", "assisted" or "unknown" from participant/care-
  partner report and context; uncertain sessions are reported as such, not silently counted.
- Safety items: if a PRO with a suicide-risk item (e.g. PHQ-9 item 9) is used, a clinician-reviewed
  escalation workflow is required before deployment ([INF], [`instruments.md`](../research/instruments.md) §2).
