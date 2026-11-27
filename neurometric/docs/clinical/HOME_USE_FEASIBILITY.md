# Stage 5: two-week home-use feasibility of the NeuroMetric logger and home battery

> **DRAFT. Not submitted. Requires faculty PI and IRB review. No participants, no devices
> deployed.** Procedures, accommodations and equipment: `stage5_protocol.md`. Consent:
> `docs/irb/consent_home_telemetry.md` and `docs/irb/consent_care_partner.md`.

## 1. Question
Can five AT users and their care partners use the NeuroMetric home battery and consented
aggregate telemetry for 14 days, producing usable data at acceptable burden?

**This is a feasibility study.** It is not powered for, and will not report, reliability,
validity, effectiveness or real-world benefit.

## 2. Participants
- 5 dyads: an adult AT user (ALS, SCI or stroke; same eligibility as Stage 4) and a care partner
  aged ≥ 18 who helps at least weekly.
- A user without a care partner may take part. The diary is then self-completed, and the
  "dyad" criterion is reported as not applicable.
- Platform: the participant's main device must be **Windows or Android**. These are the two
  platforms where the platform matrix rates a consented activity agent feasible (Windows:
  "technically yes; ethically constrained"; Android: "yes, limited"). macOS, iOS and Linux users
  can take part with **Tier 0 only** (in-battery data), recorded as a separate stratum.
- Stage 4 completers may be invited; they need fresh consent.

## 3. What is collected (exactly)
| Tier | Data | Collected? |
|---|---|---|
| 0: in-battery | Canonical task events and scores from the weekly home battery; session duration; interaction counts; AT settings declared; timing self-checks | Yes |
| 1: opt-in activity agent | Per-day totals: active minutes; device-assisted-session flags; counts of pointer, select, scroll, switch activations, dwell selections; **number** of text characters typed (never the characters); interruptions | Only if the participant ticks the separate Tier 1 box |
| 1: app categories | Minutes per coarse category (communication, web, media, productivity, social, games, health, smart_home, accessibility_tools, other) | Only with a separate opt-in (`telemetry_app_categories` scope) |
| Diary | Care partner: minutes of help yesterday by type; burden 0–10 | Yes |
| Self-report | Participant: fatigue and burden 0–10 at each home battery | Yes |

**Never collected:** keystroke content; typed text outside the copy-typing task; passwords;
messages; email; browsing history; URLs; window titles; screenshots; screen content; audio;
video; camera images; gaze coordinates; location; contacts; app names (only categories, if opted
in).

The telemetry validator (`src/neurometric/study/telemetry.py`) rejects any payload key or value
outside the allowlist and stores only a receipt for rejected batches.

## 4. Schedule (14 days)
| Day | Activity | Minutes |
|---|---|---|
| −7 to −1 | Pre-visit call; consent materials sent in the chosen accessible format | 20 |
| 0 | Setup visit (home or lab): consent (participant and care partner); install or open the battery; Tier 1 agent if opted in; freeze the accessibility profile; practice; diary training | 90 |
| 1 | Home battery #1 (RA available by phone or video if wanted) | 40–70 |
| 1–14 | Diary daily (care partner, 2 min); telemetry runs if opted in | 2/day |
| 8 | Home battery #2 | 40–70 |
| 14 | Home battery #3 | 40–70 |
| 15–21 | Closeout: uninstall the agent (verified with the participant); burden and acceptability questionnaire (original); 20-min semi-structured interview (notes only, no audio unless separately consented) | 45 |

"Weekly" means 3 batteries, at days 1, 8 and 14. The 14-day battery doubles as the end-of-study
measure.

## 5. Success criteria (pre-specified; all must hold for "feasible")
| # | Criterion | Threshold | Rationale |
|---|---|---|---|
| F1 | Usable logs | ≥ 4 of 5 participants have a usable log: ≥ 2 of 3 home batteries scored with ≥ 1 valid P2 and P3, **and**, if Tier 1 is opted in, ≥ 10 of 14 days of valid telemetry batches | Brief-specified threshold |
| F2 | Completeness | Across participants, ≥ 80% of the 70 participant-days have a diary entry **and** (if opted in) a telemetry batch | Brief-specified threshold |
| F3 | Burden (participant) | Median participant burden for the home battery ≤ 5/10 and no participant > 8/10 [HYP thresholds] | Original 0–10 item |
| F4 | Burden (care partner) | Median diary time ≤ 3 min/day self-reported; median burden ≤ 4/10 [HYP] | 2-min design target |
| F5 | Privacy integrity | 0 accepted batches containing a disallowed field (validator receipts audited) | Hard requirement; any breach stops the study and is reported to the IRB |
| F6 | Technical support load | ≤ 2 unscheduled support contacts per dyad over 14 days [HYP] | Scalability signal |
| F7 | Retention | ≥ 4/5 complete day 14 | — |

With n = 5, 4/5 has a Wilson 95% CI of about 0.38–0.96 (computed). The study can show gross
infeasibility. It cannot estimate rates precisely. Results are reported as counts, not
percentages.

## 6. Analysis
- Descriptive per dyad: a calendar heat map of data presence, and battery scores per week (no
  inference).
- Telemetry: active minutes per day (median, range).
- Diary: help minutes.
- Interview notes are summarized thematically by two people, one of whom is not the founder.
- Failure reasons are coded: technical, burden, illness, device unavailable, forgot.
- **No correlation of telemetry with outcomes is reported as evidence**, because n = 5.

## 7. What this study cannot show
- That the home battery is reliable or valid at home. That needs a home test–retest in a larger
  sample.
- That telemetry measures independence, participation or benefit.
- Anything generalizable to people without a stable home internet connection, people on
  macOS/iOS (Tier 1), or people who decline telemetry. Decliners are counted and reasons are
  recorded if they are willing to give them.
- Whether the care-partner diary is accurate. There is no observation or comparator.
- Long-term adherence beyond 14 days.

## 8. Risks and mitigations
| Risk | Mitigation |
|---|---|
| Perceived surveillance | Tier 1 is opt-in and separate; visible indicator; pause and withdraw controls; data are daily totals only; a printed "what we collect" card |
| Data breach | Aggregates only; pseudonymous; university-hosted; TLS; least-privilege access (DMP) |
| Burden or fatigue | Split-battery option; reminders limited to 1 per battery |
| Device problems caused by the agent | Signed build; tested on the loaner first; uninstall verified at closeout; support line during business hours |
| Care-partner strain | Diary ≤ 2 min; skip allowed; burden monitored; stop on request |

## 9. Compensation (all [HYP])
$30 setup; $15 per home battery (×3); $2 per diary day (up to $28); $30 closeout. That is about $133 per dyad if
everything is completed. It is prorated.

## 10. Approvals
UIUC IRB (faculty PI). University data-security review of the agent and server [UNR process].
The COI plan applies.
