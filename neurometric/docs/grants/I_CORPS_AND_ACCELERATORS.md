# Illinois I-Corps, iVenture, Landuyt IP Clinic and related programmes: drafted answers

> **DRAFT. Nothing submitted.** Prepared 2026-11-27. Programme facts come from
> `docs/research/funding.md` §4.1 (labels kept). The actual application forms were not available
> to this session, so the questions below are the typical ones for each programme [UNR]; map the
> answers onto the real forms. No interviews have been done, no mentor has agreed and no team
> member besides the founder exists yet.

---

## 1. Programme summary and dates

| Programme | What it gives | Key dates / requirements | Label | Fit |
|---|---|---|---|---|
| **Illinois I-Corps workshop series (Lean LaunchPad)** | Customer-discovery training at EnterpriseWorks (Feb–Apr); route to NSF I-Corps National Teams ($50k) | **Applications due 5 Feb 2027; Prep-Course by 12 Feb 2027.** The page lists dates under a 2027 heading without stating the year explicitly | [V] | High |
| NSF I-Corps National Teams | $50k grant; national cohort | Team: Technical Lead, Entrepreneurial Lead, Industry Mentor [PK]; usually needs a regional/site nomination [PK] | [PK] | High (after the Illinois workshop) |
| I-Corps Boost | Free; Great Lakes Hub nomination | **≥ 20 customer-discovery interviews completed** | [V] | Medium (after interviews) |
| **iVenture Accelerator (Gies)** | Non-dilutive: $10k capacity funding + $2.5k stipends for up to 4 full-time members; no equity | Full-time summer sprint + 11 months of education; most of the team takes BADM 463/464; **next deadline [UNR]** (prior pattern: apply in fall for the next summer) | [CC] | High |
| **Landuyt Center / TEC IP Clinic** (with the College of Law) | Free patent and trademark drafting; founders pay USPTO fees | Spring semester only; for startups from Cozad, the Illinois Innovation Prize and iVenture | [CC] | Medium |
| EnterpriseWorks (Research Park) | Space, mentoring, FAST Center SBIR resources | Student-startup route needs an enrolled founder; tenant route needs incorporation and a tax ID; costs [UNR] | [V]/[UNR] | Medium |
| Cozad New Venture Challenge | Prizes (SAFE), mentoring | See `COZAD_APPLICATION.md` | [V] | High |

**Before any of these:** get UIUC OTM confirmation that the founder owns the NeuroMetric code
(`STTR_STRUCTURE.md` §4), because IP Clinic filings and accelerator equity-free funding both assume
clear ownership.

---

## 2. Illinois I-Corps workshop: drafted answers (due 5 Feb 2027)

**Team.**
- Entrepreneurial Lead: [Founder], UIUC undergraduate, built NeuroMetric.
- Technical Lead: [to recruit; I-Corps national teams favour a faculty or graduate technical
  lead [PK] — ideally the prospective STTR faculty partner or a graduate student in their lab,
  **only if they agree**].
- Mentor: [to recruit; someone with medical-device or AT-industry experience; must agree].

**What is the technology?**
Software that measures functional use of brain-computer interfaces and assistive technology the
same way regardless of input: canonical event logging, an 18-task digital battery, assistance
capture and privacy-bounded home summaries, plus a verified statistics library and a simulated-
decoder harness for testing measures before human studies. Status: research software;
simulation-only results; no human data.

**What problem do you believe it solves, and for whom? (hypotheses)**
- H1: BCI and AT device makers lack credible, comparable evidence that their device improves
  users' digital independence at home, and spend staff time building ad hoc measures.
- H2: Academic BCI/rehab researchers need a reusable, validated battery that works across access
  methods.
- H3: Clinicians and AT specialists need objective documentation of computer-access performance
  to justify devices.
- H4: Care partners' assistance time is invisible in current evidence.
Each is untested.

**Who are your likely customers and beneficiaries? List segments.**
Non-invasive BCI makers; AAC and eye-gaze makers; home neuro-rehabilitation device makers;
implanted-BCI sponsors; academic BCI and rehabilitation programmes; AT clinics and rehab
providers; payers and HEOR firms (evidence consumers); people who use AT and their care partners
(beneficiaries, not buyers).

**What have you learned so far?**
Desk research only: registry endpoints, FDA guidance, the iBCI-CC consensus and competitor
programmes (`docs/research/`). The closest effort (SRAlab Digital Assessment Interface, with
Neuralink as collaborator) is clinic-based; we have not yet spoken to anyone in any segment.

**Interview plan (what you will do in the workshop).**
- Target ≥ 20 interviews in 6 weeks across ≥ 4 interviewee types using the guides in
  `docs/research/interview_guides.md` (past behaviour, no pitching, spend and workarounds).
- Priority types: BCI/AT maker clinical or regulatory leads; academic BCI/rehab researchers; AT
  clinicians (OT/SLP/AT specialists); care partners and AT users (as discovery interviews, not
  research data — no IRB needed for product discovery, but no health information is recorded)
  [INF]; payer/HEOR people.
- Scoring within 24 h: pain (0–3), evidence of spend, current solution, decision-maker, next step.

**Why now / why you?**
FDA and the field have named the gap in 2021–2026 documents [V]; the founder has already built
the software and the simulation framework, and is at a university with a medical college
(Carle Illinois) and a large disability-services community.

**Commitment.** The Entrepreneurial Lead commits to all sessions and the interview quota;
[Technical Lead commitment to be stated by that person].

---

## 3. iVenture Accelerator: drafted answers (deadline [UNR])

**Team and full-time availability.** iVenture requires a full-time summer sprint and most of the
team in BADM 463/464 [CC]. The founder can commit [confirm]; other members [to recruit]. For an
international founder, check whether the $2.5k stipend is payable and under what authorisation
[PK].

**Describe your venture (≈ 150 words).** Use the Cozad summary (`COZAD_APPLICATION.md` §1).

**What will you accomplish during the programme?**
1. Complete ≥ 40 customer-discovery interviews and decide the first paying segment.
2. Convert at least one segment conversation into a scoped pilot proposal (no commitment assumed).
3. Ship the home-use module (Tier 0 battery + opt-in Tier 1 agent on Windows/Android) to
   research-ready quality, with an external accessibility audit.
4. Support the NIH STTR application/resubmission with a faculty partner (if one has agreed).

**How will you use the $10k?** Bench-timing rig and test devices (~$5k), paid accessibility
testers (~$3k), incorporation and IP review (~$2k) [HYP amounts].

**Biggest risk and how you will test it.** Willingness to pay for independence evidence: price
tests in interviews (`docs/commercial/PRICING_HYPOTHESES.md`), stopping rule from the 90-day gate
(`COMMERCIALIZATION.md` §8).

---

## 4. Landuyt IP Clinic: request outline (spring semester; eligibility via Cozad or iVenture)

**What we would ask for.**
1. **Trademark search and filing for "NeuroMetric"** (clearance first; the name may be in use
   by others [UNR]).
2. **Patentability opinion (not a filing commitment)** on candidate methods [INF; prior-art search
   not done]:
   - closed-loop simulated-decoder evaluation of outcome-measure sensitivity (may be better
     published openly; see P1 manuscript);
   - assistance-event capture and assistance-weighted independence scoring;
   - privacy-preserving aggregate telemetry validator for AT usage.
   Open publication and open-source release may be more valuable than patents for a neutral
   measurement company; decide with the clinic before the first manuscript is submitted, because
   publication starts the US grace period and bars most foreign filings [PK].
3. Review of the STTR allocation-of-rights agreement terms (whether the clinic covers this is
   [UNR]).

**Pre-conditions.** OTM ownership confirmation; invention disclosure if any university resources
were involved.

---

## 5. Sequencing (Dec 2026–Jun 2027) [INF]
| When | Action |
|---|---|
| Dec 2026 | OTM meeting; Cozad registration; recruit CI MED teammate and an I-Corps Technical Lead and mentor (only with agreement) |
| by 5 Feb 2027 | Illinois I-Corps application; Prep-Course by 12 Feb |
| Feb–Apr 2027 | I-Corps workshop; ≥ 20 interviews → I-Corps Boost nomination possible |
| Apr 2027 | Cozad finals [INF timing]; NIH STTR 5 Apr if a faculty partner agreed |
| Spring 2027 | IP Clinic (if eligible through Cozad) |
| Fall 2027 | iVenture application for summer 2028, or summer 2027 if the window is still open [UNR] |
