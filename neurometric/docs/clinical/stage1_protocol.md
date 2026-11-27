# Stage 1 protocol: controlled able-bodied functional testing

> **DRAFT. Not submitted. Requires faculty PI and IRB review. No participants enrolled.**
> Plan context: `CLINICAL_VALIDATION_PLAN.md` §3. Analysis: `sap_stage1_3.md` Part A.
> This file also holds the **standard task procedures** (§4) that Stages 2–6 refer to.

## 1. Objectives
1. Check that every battery task (v1.0.0, A1–F7) gives valid, complete data with a standard
   mouse.
2. Characterize the Fitts' law structure (A2), floor/ceiling, timing self-checks, and
   order/fatigue effects.
3. Fix, from the data, the core-battery order and the P4 caps for Stage 3.

## 2. Participants
- n = 42 able-bodied adults aged 18–65.
- Eligibility: see the plan §3.
- Recruitment: IRB-approved flyer and email (`docs/irb/recruitment_materials.md`). **No use of
  student records.** No recruitment by the founder in their own classes, clubs or residence.

## 3. Visit schedule (single visit, about 75 min)
| Step | Minutes | Who | Notes |
|---|---|---|---|
| Welcome; eligibility confirmation | 5 | Study staff (not the founder) | |
| Informed consent (`docs/irb/consent_able_bodied.md`) | 10 | Consent-trained staff (not the founder) | Questions answered; copy offered |
| Setup and timing self-check | 5 | Staff | Chair height, monitor at arm's length, top of screen at eye level, mouse on the dominant side; record browser, OS, display |
| Demographics (age band, sex, handedness, computer-use hours) | 3 | Participant | |
| Fatigue NRS (pre) | 1 | Participant | "How tired do you feel right now, 0 = not at all tired, 10 = as tired as you can imagine" (original item, unvalidated) |
| Task families in the Williams-assigned order (§4), with practice | about 45 | Participant | 2-min break between families; 5-min break after 20 min of task time |
| NASA-TLX raw after families A, E, F | 6 | Participant | NASA-TLX is free to use [V per `instruments.md`] |
| Fatigue NRS after each family and at the end | 1 each | Participant | Stop rules: plan §2.3 |
| SUS (battery software) | 2 | Participant | Cite Brooke 1996 |
| Debrief, compensation | 3 | Staff | No scores are interpreted for the participant |

**Williams 6 × 6 family orders** (families A, B, C, D, E, F = 1–6; standard Williams
construction for an even number of treatments [PK]):

| Seq | Order |
|---|---|
| 1 | 1 2 6 3 5 4 |
| 2 | 2 3 1 4 6 5 |
| 3 | 3 4 2 5 1 6 |
| 4 | 4 5 3 6 2 1 |
| 5 | 5 6 4 1 3 2 |
| 6 | 6 1 5 2 4 3 |

(Checked computationally on 2026-11-27: all 30 ordered pairs of adjacent families occur exactly
once, and each family occupies each position once.)
Within a family, tasks run in ID order (A1, A2, …).

## 4. Standard task procedures (all stages)
- Every task starts with a practice block: 3 trials, or 1 trial for F tasks. Practice is not
  scored.
- Instructions are shown on screen **and** read aloud by staff, verbatim. For AAC users they are
  also given in written large print.
- General instruction before every task: "Work as quickly and as accurately as you can. If you
  need a break, say so or press pause at any time. There is no penalty for pausing."
  Zhai et al. 2004 recommend consistent speed–accuracy instructions [PK].

| Task | Family | What the participant sees and does (verbatim instruction) | Trials / limit | Typical minutes (mouse) | Typical minutes (AT, plan estimate [INF]) |
|---|---|---|---|---|---|
| A1 | Target acquisition | "Select the start button in the middle. A circle will appear. Move to it and select it." | 12 trials or 6 min; max 20 s per trial | 2–3 | 4–6 |
| A2 | Target acquisition | "Circles are arranged in a ring. Select the highlighted circle; the next one lights up on the other side. Keep going until the ring is finished." | 6 conditions × 13 selections; max 15 s per selection | 3–6 | 8–15 (W = 32 px may be excluded by profile) |
| A3 | Target acquisition | "Move onto the highlighted circle and hold still until the ring fills. Do not hold still on other circles." | 2 conditions × 13; dwell 800 ms default | 2–3 | 4–8 |
| A4 | Target acquisition | "One square in the grid will be marked. Select it. Selecting a different square counts as an error." | 24 trials; max 20 s per trial | 2–3 | 5–10 |
| A5 | Target acquisition | "Select the circle before the timer runs out." *(off for profiles with "no time pressure")* | 16 trials; deadlines 2 s / 4 s | 1–2 | not given in Stages 4–5 unless the participant opts in |
| B1 | Cursor control | "Move from the start zone to the end zone without leaving the path." | 8 trials | 1–2 | 3–5 |
| B2 | Cursor control | "Keep the pointer on the moving target for 30 seconds." | 3 × 30 s | 2–3 | 2–3 (reduced-motion option) |
| C1 | Scrolling | "Scroll until the named item is inside the highlighted band, then select it." | 10 trials; max 30 s | 2–3 | 4–8 |
| D1 | Drag and drop | "Pick up the object and drop it inside the zone." Drag-lock: "Select once to pick up, select again to drop." | 10 trials; max 30 s | 2–3 | 4–8 |
| E1 | Text | "Copy the phrase shown at the top using the on-screen keyboard. Fix mistakes if you notice them. Press Done when finished." | 5 phrases (Stage 1); 3 phrases (core battery); 3 min cap per phrase | 4–6 (5 phrases) | 6–9 (3 phrases) |
| E2 | Text | "Select the phrase that is named." | 12 trials | 1–2 | 3–5 |
| F1 | dADL | "Find and open the contact named on the card." (fictional contacts) | 1 trial | 0.5–1 | 1–3 |
| F2 | dADL | "Open messages, choose the named person, build the message shown using the tiles, and press send. Nothing is really sent." | 1 trial | 1 | 2–4 |
| F3 | dADL | "Open the named menu and choose the named item." | 4 trials | 1–2 | 2–5 |
| F4 | dADL | "Book the appointment shown: pick the date, then the time, then confirm." | 1 trial | 1 | 2–4 |
| F5 | dADL | "Fill in the form with the answers shown, then submit." (no personal data) | 1 trial | 1 | 2–4 |
| F6 | dADL | "Use the word board to build the 3-word message shown." | 2 trials | 1 | 2–5 |
| F7 | dADL | "On this practice web page, follow the link to find the named item." (no network access) | 1 trial | 1 | 2–4 |

- Full battery task time with a mouse is about 30–45 min, plus practice and instructions.
- Core battery (A1, A2, A4, C1, D1, E1 with 3 phrases, F2, F3, F5) is about 20–25 min with a
  mouse and about 40–70 min with AT.
- **Assistance:** any help is logged in the assistance panel as an ASSIST event (setup,
  physical, verbal, troubleshooting, calibration, task_completion). An assisted trial is
  "assisted", never "failed".
- **Staff must not coach strategy** during scored trials. Allowed verbal assistance is limited to
  repeating the instruction, and is logged as verbal.

## 5. Accessibility accommodations (Stage 1)
Large-print consent; a seated or standing desk; left-handed mouse setup; breaks on request;
captions or written instructions for participants who are deaf or hard of hearing. Stage 1
excludes people whose condition affects computer use, by design. They are the Stage 4
population, not an accommodation case.

## 6. Equipment (Stage 1)
| Item | Specification | Note |
|---|---|---|
| Laptop | Windows 11, ≥ 8 GB RAM, dedicated to the study, managed account | Same unit for all participants where possible |
| Browser | Chrome, version pinned in the protocol at IRB submission | Cross-origin isolation enabled on the battery server |
| Display | External 24-inch, 1920 × 1080, 60 Hz; brightness fixed | Refresh rate recorded by self-check |
| Mouse | Wired USB optical mouse, 125 Hz polling, OS pointer speed default, "enhance pointer precision" **off** | Recorded |
| Bench timing validation | Photodiode + actuator rig (Black Box Toolkit-class) run before the study for this configuration | `browser_timing.md` §5 |
| Battery server | University-hosted instance (not a company server) | See DMP |
| Furniture | Height-adjustable chair and desk | |

## 7. Safety and stopping
Plan §2.3–2.4. Expected risks are fatigue, boredom and mild eye strain. There are no physical
procedures.

## 8. Data handling
Pseudonymous ID (`NM-XXXXXXXXXX`). Canonical events and scores are stored on the university
instance. Consent forms are stored separately. See `docs/irb/data_management_plan.md`.
