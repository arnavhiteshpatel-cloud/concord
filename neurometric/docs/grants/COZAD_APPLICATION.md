# Cozad New Venture Challenge 2027: application draft

> **DRAFT. Not registered, not submitted.** Prepared 2026-11-27. The 2027 application form and
> rule book were **not** available to this session; the questions below are the usual
> venture-competition topics, not Cozad's verified form [UNR]. Copy the answers into the real form
> and cut to its word limits. Nothing here claims a customer, partner, pilot, letter of intent or
> human result: there are none. Labels per `docs/research/CONVENTIONS.md`; facts about Cozad come
> from `docs/research/funding.md` §4.1.

---

## 0. Eligibility and timing checklist

| Item | Status | Source |
|---|---|---|
| ≥ 1 full-time, degree-seeking UIUC student on the team; solo entry allowed; idea stage acceptable | Founder qualifies (confirm enrolment status) | [V] Cozad FAQ (funding.md §4.1) |
| **Healthcare Innovation prizes require ≥ 1 Carle Illinois College of Medicine (CI MED) student on the team**; teams without one compete only for the main prize pool | **Not met.** Recruit a CI MED teammate before registration closes | [V] from the 2024-25 rules page; **confirm in the 2027 rule book** |
| 2027 registration | Opened Fall 2026 [V]; deadline about early February 2027 [INF from the 2026 pattern: registration due 1 Feb, finals mid-April] | funding.md §4.1 |
| Prize form | 2026 grand prize $100k paid as a SAFE; top cash prizes as SAFEs; Health Innovation Prizes were $15k / $7k / $3k in 2026 | [V] |
| IP | University and Landuyt Center take **no IP** from participation or prizes | [V] Cozad FAQ |
| Incorporation | Not required to enter [INF; FAQ silent]. A SAFE needs a company to issue it, so plan to incorporate before receiving a prize [INF] | — |
| International founders | Cozad FAQ warns that company-registration rules differ and visa status should be protected | [V] |
| Unlocks | Landuyt IP Clinic eligibility (spring) | [CC] funding.md §4.1 |

**Team to assemble [HYP roles; nobody recruited yet]:**
1. Founder (UIUC undergraduate): CEO / technical lead.
2. **CI MED student**: clinical lead (required for Healthcare prizes); role: clinical workflow,
   patient-safety and IRB framing, clinician interviews. Recruit through Carle Illinois student
   channels; describe the honest status first.
3. Optional: a business or I-School student (customer discovery, pricing) and a person with lived
   experience of AT use as an adviser (not as a research subject).
4. Mentors/advisers: only list people who have agreed.

---

## 1. Venture summary (≈ 100 words)

NeuroMetric builds neutral software that measures whether brain-computer interfaces (BCIs) and
assistive technologies actually help people do things on a computer, and how independently. Any
input (a BCI cursor, eye gaze, a head pointer, a switch, a mouse) is logged as the same kind of
event stream and scored the same way, so devices can be compared fairly. Short standardized
digital tasks, care-partner assistance tracking and privacy-bounded home-use summaries produce
evidence that device makers, researchers and, later, regulators and payers need. We are
pre-incorporation, with working research software and simulation-only results; our next step is
validation with people who use assistive technology.

## 2. Problem

- People with ALS, spinal cord injury or stroke rely on BCIs, eye-gaze trackers and switches to
  communicate and use computers. Device makers mostly report engineering metrics (decoding
  accuracy, bits per second) that do not show whether a person can do daily digital activities
  independently.
- A 2025 review of 112 implanted-BCI studies found only 17.9% assessed clinical outcomes
  [V/RF, Dohle et al. 2025].
- FDA asks implanted-BCI pivotal studies for a validated effectiveness endpoint, home-use data and
  measures of the caregiver's ability to assist; no BCI outcome tool is qualified in FDA's MDDT
  program [V].
- The iBCI Collaborative Community (1 Oct 2026) concluded that no single existing measure is likely
  to be enough and called for a "shared measurement chain" from device performance to function to
  care burden [V].
- Each company measures its own device its own way, so results cannot be compared across inputs,
  and almost nothing is measured at home.

## 3. Solution

- **Input-agnostic event model**: every input becomes the same canonical, hashed event stream.
- **18-task digital battery** (pointing, typing, scrolling, dragging, phrase selection and seven
  simulated daily digital activities such as composing a message or booking an appointment),
  scored only from what a real deployment can record.
- **Assistance as data**: help from a care partner is recorded, not counted as failure.
- **Privacy-bounded home measurement**: daily totals (active minutes, counts of selections) only;
  never text, screens, URLs or audio.
- **Verified statistics** for reliability and validity, and an evidence package designed for
  audit-trail expectations.
- What it is not: it does not control devices, does not process neural signals, and makes no
  diagnostic or treatment claims.

## 4. Technology status and evidence (honest)

- Working research software: event schema and adapters, task battery (browser), scoring, a
  psychometrics library, a study-management module with consent gating, and a closed-loop
  **simulated-decoder harness** with virtual users.
- **Simulation result (synthetic, not human):** in a 52,920-trial simulated noise sweep, typing
  rate (correct characters per minute) and pointing throughput fell steadily as simulated decoder
  noise increased (Spearman ρ −0.917 and −0.892), while "did the digital task get completed?" was
  at its ceiling in 90.7% of simulated sessions, which is why we measure time and assistance, not
  just completion (`experiments/results/B_noise/summary.json`).
- **Statistics verified:** 86 of 86 known-truth simulation checks pass; we found that a standard
  reliability interval under-covers and switched to a better method
  (`experiments/results/R_statistical_verification/coverage_results.json`).
- **Real data check:** the scoring pipeline ran on a public dataset of a monkey moving a cursor by
  hand (541 reaches; `experiments/results/X1_external_mc_rtt/summary.json`). Not human, not BCI.
- No human-subject data yet. Human studies need a faculty principal investigator and IRB approval
  (the student founder cannot be the IRB PI under UIUC policy RP-19 [V]).

## 5. Customers and market (hypotheses under test)

- **First users:** academic BCI and rehabilitation research programmes (grant-funded).
- **First paying customers [HYP]:** non-invasive BCI and AAC device makers and home
  neuro-rehabilitation device makers that need evidence of real-world use and independence.
- **Later [HYP]:** implanted-BCI companies preparing pivotal studies; rehabilitation providers
  documenting AT needs; payer-evidence partners.
- **Market reality:** only about 3 US companies run active implanted motor/communication BCI
  studies today [V]; an implant-only business is too small (≈ $0.38–0.88M/yr at full penetration
  under our own price hypothesis) [HYP] (`COMMERCIALIZATION.md` §0). The business must serve the
  much larger AT/AAC and rehabilitation-device space.
- **Pricing hypotheses (untested):** evidence pilots $25–75K; study-year contracts; maker evidence
  programmes (`docs/commercial/PRICING_HYPOTHESES.md`).

## 6. Competition and differentiation

| Alternative | What it does | Our difference |
|---|---|---|
| Shirley Ryan AbilityLab Digital Assessment Interface (with Neuralink as collaborator; 60-participant study) | Clinic-based digital-ADL performance battery plus questionnaires; in development | We focus on home use, assistance capture and any input; we aim to be complementary and to use consensus instruments where licensable, not to build a rival index |
| Mount Sinai Digital IADL scale | Patient-derived rating scale (content-validity stage) | Performance-based and home-measured complement |
| Device makers' in-house tools | Each measures its own device | Neutral and comparable across devices |
| eCOA / clinical-trial platforms (e.g. Signant + Ametris) | Questionnaires and wearables in trials | No access-method measurement today [INF] |
Sources: `docs/research/competitors.md`.

## 7. Business model and go-to-market

1. Grant-funded academic validation (NIH STTR Phase I with a faculty PI, target 5 Apr 2027).
2. Paid pilots with makers whose evidence gaps are public.
3. Study infrastructure for device studies once the software is validated and audit-ready.
Details: `COMMERCIALIZATION.md` §2.

## 8. Milestones and use of prize funds

| Use | Amount [HYP] | Milestone |
|---|---|---|
| Incorporation, registrations, IP/OTM review, counsel | $3–5k | Company exists; ownership of code confirmed |
| Bench-timing rig and test devices | $5–7k | Measured input lag per device class |
| Accessibility testing with disabled testers (paid) | $5k | Battery usable by switch, gaze and screen-reader users |
| Customer discovery travel and interview incentives | $2–3k | 20+ structured interviews |
| Prize ≥ $50k: part-time engineer | remainder | Home agent and audit-trail features ready for the STTR studies |

Upcoming milestones: 20+ discovery interviews and a faculty partner (Feb 2027); NIH STTR
submission (Apr 2027, if a partner agrees); first IRB-approved able-bodied sessions (after award or
under a faculty-led pilot protocol).

## 9. Team

[Founder name], UIUC [major, year]: built the NeuroMetric software, simulator and statistics
library. [CI MED teammate, if recruited]. [Advisers, only with their agreement.]
What the team still lacks: a faculty PI, clinical research experience (CI MED teammate helps),
regulatory/quality expertise, and sales experience.

## 10. Risks we know about
- A sponsor-backed instrument (the SRAlab DAI) may become the free reference.
- Device makers may build their own tools.
- Willingness to pay for "independence evidence" is unproven.
- Recruiting AT users is slow.
- Simulation results may not transfer to people.

## 11. Pitch outline (5 minutes, for Demo Day)
1. A person, a device and one question: can they do it on their own? (30 s)
2. Why today's metrics don't answer it; FDA and the field say so (45 s)
3. NeuroMetric in one diagram: any input → events → tasks → assistance → home (60 s)
4. What we have: software + simulation + verified statistics; what we don't: human data (45 s)
5. Who pays and why the implant market alone is too small (45 s)
6. Plan: STTR with a faculty PI, first pilots, what the prize buys (45 s)
7. Team and ask (30 s)

## 12. Before submitting
- Confirm the 2027 form, word limits, deadline and CI MED rule with the Landuyt Center (published
  general inbox).
- Have the CI MED teammate review §2–4 for clinical accuracy.
- Remove any statement a teammate or adviser has not approved.
- Keep the "simulation-only" status visible in every section judges may read in isolation.
