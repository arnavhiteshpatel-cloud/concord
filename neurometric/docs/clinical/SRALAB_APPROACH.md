# Approaching the Shirley Ryan AbilityLab DAI team

> **DRAFT. Nothing has been sent and no one has been contacted.** There is no relationship,
> agreement or commitment with SRAlab, Northwestern or Neuralink. This file is internal guidance
> for the founder **and the faculty PI**. The email should go out with, or from, the faculty
> advisor, not as a cold pitch from a student company.

## 1. What is publicly known (registry, verified 2026-11-27)
- **Study:** NCT07407725, "Development of a Clinical Outcome Assessment for Assistive
  Technologies and Brain-Computer-Interfaces".
- **Sponsor:** Shirley Ryan AbilityLab. **Collaborator:** Neuralink Corp.
- **Status:** recruiting; started 2026-01-08; primary completion 2026-12 (estimated); study
  completion 2027-06 (estimated); enrolment about 60.
- **PI (location record):** Arun Jayaraman, PhD.
- **Registry central contacts:**
  - Arun Jayaraman, PT, PhD, ajayaraman@sralab.org
  - Richa Rai, PhD, rrai@sralab.org
- **Site contacts** also include Sara Prokup, PT, DPT. The registry lists phone numbers. They are
  deliberately not copied here.
- [V] https://clinicaltrials.gov/study/NCT07407725 (API v2 record, accessed 2026-11-27)
- **Etiquette [INF]:** registry contacts are published mainly for participant recruitment. Use
  them for a professional enquiry at most once, briefly, and say in the first line that it is a
  research-collaboration enquiry, not a participant enquiry. An alternative route is the public
  SRAlab researcher profile (https://www.sralab.org/researchers/arun-jayaraman-pt-phd [V via
  `collaborators.md`]) or an introduction through a UIUC faculty member who knows the group.
- **IRB:** "Regulatory oversight is provided by the Northwestern University IRB for Shirley Ryan
  Ability Lab (SRAlab)" under an MOU [V]
  https://irb.northwestern.edu/reliance/nu-affiliates-chicagoland-partners.html. Northwestern
  participates in SMART IRB [V] https://irb.northwestern.edu/reliance/smart-irb-irex.html.
  Whether UIUC participates in SMART IRB was not confirmed this session [UNR]. Any joint work
  needs a reliance or authorization arrangement, set up through OPRS (Reliance Consultation
  Request) [V route]. Investigators cannot set this up themselves.

## 2. Positioning: what NeuroMetric offers, and what it is not
**It is not a rival index.** The DAI team is building an index with PerfO, ClinRO and PRO
components, with a Neuralink collaborator, in a funded, IRB-approved study. NeuroMetric should
not claim to replace it, benchmark against it, or "validate" it.

Possible contributions [INF/HYP]. Offer them as questions, not deliverables.
1. **Implementation and home extension:** a browser-based, input-agnostic battery and event
   logger that could carry DAI-like performance primitives into home sessions, with aggregate
   home telemetry (Stage 5 design).
2. **AT-input validation:** an openly specified pipeline for switch scanning, dwell, head-pointer
   and eye-gaze metrics (scan steps per character, unintended dwell selections, achieved
   bitrate), and a bench timing-validation protocol per input class.
3. **Simulation harness:** closed-loop simulated users with degradation profiles (latency, noise,
   dropout) to stress-test scoring rules **before** they meet participants. Simulated output is
   never presented as human data.
4. **Psychometric tooling:** open, tested code for ICC(A,1) with GCI, SEM/MDC, Bland–Altman,
   known-groups AUC, and responsiveness (`src/neurometric/psychometrics`).
5. **Student effort** on a well-defined sub-question that the DAI team chooses, under their
   supervision and IRB.

## 3. What to ask (open questions)
1. Is there an interest or need for home-based extension of DAI tasks, or for data on
   AT-input-specific metrics?
2. What would a useful contribution from a small external team look like, if any? What would
   *not* be useful?
3. Are there plans to publish the DAI task specifications or scoring? What terms would apply to
   using them? We would not reimplement DAI tasks without permission.
4. What are the constraints from the Neuralink collaboration (confidentiality, data rights,
   publication)?
5. Would a student observer or volunteer role (no data access) be possible, to learn the
   protocol?
6. Is there any interest in a separate, low-burden methods collaboration, such as bench timing
   validation of AT inputs, which involves no participants?

## 4. What not to claim or do
- Do not say NeuroMetric is "validated", "clinical-grade", "FDA-ready" or "compatible with the
  DAI".
- Do not imply that any UIUC, Carle or other affiliation or partnership exists beyond what is
  true.
- Do not mention or imply access to Neuralink devices or data.
- Do not ask for participant data, DAI software or scoring code in the first email.
- Do not attach a pitch deck. Do not ask for a letter of support in the first contact.
- Do not contact participants or patient groups to reach DAI participants.
- Do not follow up more than once, and only after ≥ 2 weeks.

## 5. IP and licensing questions to raise (later, through the faculty PI and UIUC offices)
- Who owns improvements made jointly (SRAlab/Northwestern policy, UIUC policy, the company)?
  UIUC IP policy may apply to the student founder's work [INF; see DECISIONS D-002 note].
- Licence terms for any SRAlab-owned task specifications or software, if shared.
- Data-use agreement scope: pseudonymized event data only; purposes; retention; publication.
- Background IP: NeuroMetric's code is clean-room (D-002). Its licence for academic partners
  (e.g. a free research licence) must be decided **before** offering it.
- COI disclosure to the Northwestern IRB if the founder is engaged in research there.

## 6. Draft email (NOT SENT; to be revised and sent by or with the faculty PI)

> **Subject:** Research collaboration enquiry (not a participant enquiry): home and AT-input extension of digital performance measures
>
> Dear Dr. Jayaraman,
>
> I am writing with *[FACULTY PI NAME]*, *[TITLE, DEPARTMENT]*, University of Illinois
> Urbana-Champaign. This is a research enquiry, not a participant enquiry. I apologise for using
> the registry contact for it.
>
> We read the registry record for NCT07407725 with great interest. I am an undergraduate student
> developing an open, input-agnostic digital task battery and logging pipeline (pointing, grid
> selection, scrolling, drag, copy typing, and simulated digital activities), with tooling for
> test–retest reliability and AT-specific metrics for switch scanning and dwell. It is early
> work. It has not been tested with participants and is not a validated measure. I also have a
> financial interest in it through a student company, which I want to disclose up front.
>
> We are not trying to build an alternative to your index. We wondered whether a small,
> supervised contribution could be useful to your team. Two examples: help with home-based or
> AT-input-specific measurement questions, or bench timing validation of assistive inputs, which
> involves no participants. If none of this is useful, that is a helpful answer too.
>
> Would you or a member of your team be open to a 20-minute call in the coming months? We are
> happy to work around your schedule, or to be pointed to a more appropriate contact.
>
> With thanks,
> *[STUDENT NAME]*, undergraduate, *[DEPARTMENT]*, University of Illinois Urbana-Champaign
> *[FACULTY PI NAME AND TITLE]* (cc)

Notes:
- Address Dr. Jayaraman as the registry PI. Copy Dr. Rai only if the faculty PI agrees.
- Send from university email addresses, not a company domain.
- Disclose the COI in the first message (done above).
