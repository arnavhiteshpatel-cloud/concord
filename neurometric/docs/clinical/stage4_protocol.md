# Stage 4 protocol: validation with assistive-technology users (ALS, SCI, stroke)

> **DRAFT. Not submitted. Requires faculty PI and IRB review. No participants enrolled, no site
> or clinical partner committed.**
> Plan: `CLINICAL_VALIDATION_PLAN.md` §6. A Stage 4 SAP will be written from the template and
> locked before enrolment.

## 1. Objectives
1. **Confirmatory:**
   - known-groups validity (H4.1: KG2, direct selection vs switch scanning, on P2);
   - construct validity (H4.2: ≥ 75% of locked hypotheses confirmed);
   - floor (H4.3: ≤ 15% at floor per cohort).
2. **Secondary:** test–retest reliability with the participant's own AT (H4.4).
3. **Exploratory:** reliability invariance across diagnoses; responsiveness sub-study.

## 2. Participants
- 45 adults: about 15 ALS, about 15 SCI (C1–T6, ≥ 12 months post-injury), about 15 chronic
  stroke (≥ 6 months).
- Target ≥ 10 switch-scanning users across cohorts.
- Eligibility: plan §6. People with implanted BCIs are **not** recruited here (Stage 6 only).

**Recruitment routes** (each needs its own IRB approval; none is arranged):
- community and advocacy organizations' newsletters (flyer only; the organization is not engaged
  in research if it only distributes flyers [V, OPRS non-Illinois guidance]);
- UIUC DRES channels (if DRES agrees);
- Carle clinics through the Carle Research Services process [V route];
- self-referral from the study web page.

## 3. Visit schedule
| Visit | Setting (participant's choice; then held fixed) | Content | Minutes (with breaks) |
|---|---|---|---|
| Pre-visit call | Phone or video, or by email for AAC users | Eligibility; access method; positioning needs; transport; consent materials sent in the participant's preferred accessible format ≥ 3 days ahead | 20 |
| S0 | Lab or home | Accessible consent process (§5); demographics; diagnosis-specific intake (self-report: years since onset, access method, hours of AT use per day); setup and AT-settings record; core battery practice run | ≤ 75 |
| S1 | Same | Core battery; NASA-TLX raw; fatigue NRS; questionnaires: SUS for own AT, NeuroMetric original digital participation questionnaire (unvalidated); licensed instruments only if licences are granted (Neuro-QoL UE, PIADS, QUEST 2.0); care partner: Section GG self-care items (clinician- or researcher-entered), original assistance diary instructions | ≤ 90 (questionnaires may move to a separate 30-min remote visit) |
| Diary | Home | Care partner (or participant): 2-min daily assistance diary × 7 days | 14 total |
| S2 | Same | Core battery; fatigue NRS; global rating of change item | ≤ 75 |
| S3 (optional) | Same | Core battery | ≤ 75 |
| Longitudinal (optional consent) | Same | ALS: 3 and 6 months after S1; stroke: before and after the partner's rehab program | ≤ 75 each |

**Split-session rule.** If the fatigue stop rule triggers before the core battery is finished,
the remaining tasks are given within 48 h, in the same order and setting. The split is recorded,
and that session is flagged for sensitivity analysis.

## 4. Task procedures
- Core battery as in `stage1_protocol.md` §4, with the participant's accessibility profile.
- A5 is not given unless the participant opts in (no time pressure; WCAG 2.2.1 adjustable
  timing).
- The A2 32-px condition is excluded when `target_min_px` > 32. The profile is set at S0 and
  **frozen** for S1–S3.
- D1 uses drag-lock for users who cannot hold.
- E1 key size, scanning rate and dwell use the participant's own settings, recorded and frozen.

**AT settings record (S0; checked at every visit):** device and model; firmware/software
version; mounting position (photo of the device only, no person); dwell time; scan interval and
pattern; switch site(s); pointer gain; calibration quality as reported by the AT software; OS
accessibility features in use.

## 5. Accessible consent process (summary; full text in `docs/irb/consent_at_user.md`)
1. Consent documents are sent ≥ 3 days ahead in the format the participant chooses: accessible
   PDF/HTML (screen-reader and switch-navigable), large print, plain-language key-information
   summary, or loaded onto the participant's AAC device as pages.
2. The consent discussion is paced by the participant. There is no time pressure. It may span
   two sessions.
3. The participant communicates by their usual method: AAC device; eye gaze; partner-assisted
   scanning with an agreed yes/no signal; or reliable eye-blink or eye-movement yes/no checked
   with 3 neutral practice questions.
4. **Comprehension check:** 5 teach-back questions (original), answerable by yes/no or
   selection. ≥ 4/5 correct; re-explanation allowed. If the participant cannot reach 4/5 after
   two explanations, they are not enrolled, and this is handled kindly.
5. **Documentation:**
   - (a) the participant signs by hand, by mark, or by electronic signature with verified
     identity (OPRS e-signature guidance [V]); or
   - (b) if physically unable to sign, consent is given through their communication method in
     the presence of an **impartial witness**. The witness is not on the study team and not the
     care partner, if possible. The witness signs the OPRS Witness Signature Page attesting that
     the information was presented and consent was freely expressed [V: template exists].
6. **No LAR consent** in this stage.
7. The care partner may help with communication but may not answer for the participant. Staff
   confirm that each answer comes from the participant.
8. Ongoing consent: before each visit, staff ask "Do you still want to take part today?" using
   the participant's yes/no method.

## 6. Accessibility accommodations
| Domain | Accommodation |
|---|---|
| Positioning | Participant stays in their own wheelchair or bed if they prefer. Screen at the participant's usual viewing distance and angle; monitor arm or floor stand. Wheelchair tray or table height adjusted. Pressure relief at their usual interval. Trunk support as they normally use it. |
| Mounting | Use the participant's own mounts first (wheelchair-mounted tablet, desk mount). Lab mounts: articulating monitor arm, rolling floor stand, eye-tracker magnetic mount at the vendor-specified angle and distance. Mounts are photographed (device only) and positions measured so they can be repeated. |
| Switch placement | Use the participant's own switch and site (hand, head, chin, knee, foot, elbow, sip-and-puff). Mount it with an articulating switch-mount arm. Confirm a reliable activation and release on 10 practice activations. Record the site, the switch type and whether the scan interval is their usual setting. |
| Eye-gaze calibration | Participant's own system and calibration profile if they have one; otherwise a fresh calibration. Reduce glare and back-light. Glasses as usual. Recalibration allowed between tasks and logged as an ASSIST(calibration) event. Calibration quality is recorded as reported by the system. **Gaze coordinates are not stored.** |
| Head pointer, joystick, mouth joystick | Own device and settings. For a mouth-operated joystick, hygiene per the participant's routine. |
| Voice control | Allowed if it moves the OS pointer or grid. Note that spoken audio is processed by the participant's OS, not by NeuroMetric. NeuroMetric records no audio. |
| Breaks | ≥ 5 min every 15 min of task time; more on request; fatigue NRS stop rules (plan §2.3). |
| Communication during sessions | Agreed stop signal (e.g. look up, long switch press, AAC "stop" key); yes/no method confirmed at the start; questions presented one at a time. |
| Sensory | Large text; high contrast; captions or written instructions; reduced motion for B2. |
| Care partner | May attend; is compensated for time [HYP]; may help with setup (logged as ASSIST(setup)), not with tasks unless logged. |
| Travel | Accessible parking; paratransit or taxi reimbursement; home-visit option. |

## 7. Safety
- SCI T6 and above: the participant's autonomic dysreflexia plan is recorded at S0, the
  bladder-routine reminder is respected, and signs (pounding headache, flushing, sweating above
  the injury, nasal congestion, blurred vision [PK]) mean the session stops immediately and the
  participant's plan is followed. Staff must have training from the faculty PI or a clinical
  co-investigator before any SCI visit.
- ALS: respiratory comfort; their ventilation routine; stop on request.
- Stroke: no specific risks beyond fatigue [INF].
- Any fall or injury during a visit (e.g. a transfer) is recorded as an adverse event and
  reported if it meets the OPRS Unanticipated Problem criteria (10 business days [V]).
- Staff do not perform transfers. The participant's own care partner does transfers if needed.

## 8. Equipment
| Item | Note |
|---|---|
| Study laptop (Windows 11), browser pinned | As Stages 1–3 |
| Android tablet (for participants whose own access runs on Android) | Platform matrix: Android in-app or browser |
| Participant's own AT | Preferred. NeuroMetric is input-agnostic and receives OS pointer/key events |
| Loaner AT for lab visits (only if the participant asks) | Switch + interface; joystick; head pointer. No loaner eye tracker unless calibrated for that participant |
| Monitor arm; rolling floor stand; switch mount arm; wheelchair tray | |
| Disinfection supplies | Wipe all shared devices between participants |
| Bench timing profile for each modality class | Applied as `validation_profile_id` |

## 9. Burden and compensation
| Visit | Participant | Care partner |
|---|---|---|
| S0, S1, S2 (S3) | $40 per visit [HYP] | $20 per visit attended [HYP] |
| Diary | — | $2 per day [HYP] |
| Travel | Reimbursed | — |

## 10. Data, privacy, approvals
- See `docs/irb/data_management_plan.md` and `docs/irb/hipaa_ferpa.md`.
- Diagnosis is self-reported. Confirmation by clinician letter is optional and only with the
  participant's written permission.
- Approvals: UIUC IRB. Carle: Carle Research Services and reliance [V route]. Licences for any
  licensed instrument (`instruments.md`).
