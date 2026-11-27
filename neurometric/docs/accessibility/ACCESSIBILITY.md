# NeuroMetric web app: accessibility

Scope: the browser task battery, setup, results and degradation demo in `web/` (Vite + React +
TypeScript). Target: WCAG 2.2 Level A and AA. Prepared 2026-11-27.

**Status in one paragraph.** The app was designed for people who use switches, eye gaze, head
pointers, BCIs exposed as pointers or switches, keyboards and screen readers. Automated checks
pass: axe-core reports zero violations of any impact on 58 screen/theme combinations; reflow,
text-size and text-spacing checks pass; and end-to-end runs complete tasks keyboard-only, by
two-switch scanning and by dwell, and complete setup with a single switch. **No testing with real
assistive technology or with disabled participants has been done.** The manual protocol in §5 is
required before any claim of conformance. Automated tools find only part of WCAG failures, so
"implemented" below means *designed and, where marked, checked automatically*, not *verified with
users*.

## 1. What is built in

* **Native elements first.** Buttons, links, fieldsets, `<dialog>`, tables with `<th scope>` and
  `<output>` are used throughout. Toggles and choices are native buttons with `aria-pressed`.
  Numeric settings are −/+ steppers made of native buttons (operable with one switch).
* **Keyboard-only operation everywhere.** All setup, navigation, dialogs and results controls are
  native and focusable. In item tasks (A4, C1, E1, E2, F1–F7) every item is a button: Tab to it
  and press Enter or Space. In pointing tasks (A1, A2, A3, A5, B1, B2, D1) the arrow keys move a
  visible keyboard cursor (10 px, or 40 px with Shift) and Enter or Space selects. Escape pauses
  any task.
* **Switch scanning operates every control**, including the setup screens. This can be on for the
  whole app ("Switch scanning for this app") or come from the "Switch scanning" selection method.
  * Modes: one switch with auto-scan, or two switches with step-scan (switch 1 moves, switch 2
    selects).
  * Configurable: scan interval (300–5000 ms), restart from the first item or continue, stop after
    N empty cycles, row-column scanning, and the switch keys (default Space / Enter).
  * Scanning is dwell-free and needs no hold time.
  * The highlight is a 6 px outline plus a halo, and the highlighted control also receives
    keyboard focus, so screen readers announce it.
  * Sliders (demo only) step on each activation and wrap. Text inputs receive focus; staff types
    into them.
  * During a task, Pause, Skip trial, Record assistance and Stop are scanned after the task items.
    While paused, only Resume and the controls are scanned.
* **Dwell selection.** Dwell time is configurable (200–4000 ms). A progress ring fills while the
  pointer rests on an item; leaving the item resets it, and the item must be left before it can be
  selected again (avoiding "Midas touch").
* **Timing (WCAG 2.2.1).** There are no time limits by default ("No time pressure" is on). The
  time-constrained task A5 is not offered while that setting is on. When time pressure is
  switched on, a multiplier of ×1–×10 applies. Every task can be paused at any time (Pause or
  Escape); the current trial is set aside and presented again on resume.
* **Screen-reader support.**
  * Each task has a visible instruction in an `aria-live="polite"` region and a feedback
    `role="status"` region ("Correct.", "Paused…", "Assistance recorded…").
  * Route changes move focus to the new page heading; the task canvas receives focus when a task
    starts.
  * Pointing-task targets are `aria-hidden` visual stimuli (see 1.1.1); item tasks expose
    labelled buttons, and the cued item is announced as "(cued)".
* **Visible focus.** A 4 px outline with a 3 px offset, with a different colour per theme.
* **Large targets.** All UI controls are at least 44 × 44 CSS px. Task stimuli are fixed in task
  space and scale with the canvas (see 2.5.8).
* **Themes.** Follow system, light, dark and high contrast (black / yellow / cyan). Each is set
  through CSS custom properties, and `forced-colors` is respected. Text size can be set from 100 %
  to 200 %, on top of browser zoom.
* **Motion.** `prefers-reduced-motion` is honoured, with an override in setup. When motion is
  reduced, B2 tracking uses a path at half speed, and transitions and animations are disabled.
* **Error recovery and confirmation.**
  * Stopping a task needs an in-app confirmation ("Yes, stop" / "No, continue"); a native
    `confirm()` was avoided because switch scanning cannot reach it.
  * In the digital-ADL tasks a wrong selection opens a screen whose only action is Back.
  * Skip trial is always available.
  * When an upload fails, a message says that nothing was lost and offers a JSON download.
* **Assistance panel.** A native modal `<dialog>` records ASSIST events (setup, physical, verbal,
  troubleshooting, calibration, task_completion) and who helped. It is reachable by keyboard,
  pointer and scanning.

## 2. WCAG 2.2 A / AA mapping

Status key:

* **Implemented**: designed in, and checked automatically where marked [auto].
* **Partially**: known limits are stated.
* **Untested**: no check has been run.
* **N/A**: no such content exists.

"Manual AT verification" (§5) is outstanding for every row.

| SC | Level | Status | How / evidence / limits |
|---|---|---|---|
| 1.1.1 Non-text Content | A | Partially | Controls have text names [auto: axe]. Pointing stimuli (A1–A3, A5, B1, B2, D1) are visual-motor *tests*. WCAG's exception for tests that would be invalid as text applies, and they are `aria-hidden` with text instructions. Blind participants cannot take these tasks; the battery records this as a construct limit, not as a failure. |
| 1.2.1–1.2.5 Media | A/AA | N/A | No audio or video. |
| 1.3.1 Info and Relationships | A | Implemented [auto] | Fieldset/legend, label/for, table th/scope, headings, `role="group"` toolbars. |
| 1.3.2 Meaningful Sequence | A | Implemented | DOM order equals visual order; task items are listed in scan order. |
| 1.3.3 Sensory Characteristics | A | Partially | Instructions name shape and position ("filled (highlighted) circle", "shaded box at the left end"). Some tasks still rely on spatial layout by design. |
| 1.3.4 Orientation | AA | Implemented | No orientation lock; the canvas scales. |
| 1.3.5 Identify Input Purpose | AA | Implemented | `autocomplete="username"` and `"current-password"` on upload; the study code uses `autocomplete="off"` (not personal data). |
| 1.4.1 Use of Color | A | Implemented | The cue uses border thickness plus a ★ glyph; the ISO target is filled while others are outline only; pressed buttons show ✓. |
| 1.4.2 Audio Control | A | N/A | No audio. |
| 1.4.3 Contrast (Minimum) | AA | Implemented [auto] | axe color-contrast: 0 violations in light, dark and high-contrast themes. |
| 1.4.4 Resize Text | AA | Implemented [auto] | A 200 % text setting causes no horizontal scroll on 7 screens. Task-canvas text scales with the canvas, not with the text setting. |
| 1.4.5 Images of Text | AA | Implemented | None used. |
| 1.4.10 Reflow | AA | Implemented [auto] | At 320 CSS px, 7 screens show no horizontal page scroll. The 1280×800 task canvas is scaled as one 2-D object (exception for content that needs 2-D layout); wide tables scroll inside a focusable region. |
| 1.4.11 Non-text Contrast | AA | Implemented (partly auto) | Item borders and focus/scan outlines use ≥ 3:1 colours per theme (canvas borders were changed from 2.5:1 after review). ISO non-target circles are decorative. |
| 1.4.12 Text Spacing | AA | Implemented [auto] | With the WCAG spacing overrides injected, there is no horizontal overflow on 7 screens. Clipping inside fixed-size task items is untested. |
| 1.4.13 Content on Hover or Focus | AA | N/A | No hover or focus pop-ups. |
| 2.1.1 Keyboard | A | Implemented [auto: e2e] | All functions work by keyboard, including a keyboard cursor in pointing tasks. Path-dependent tasks (B1, B2, D1) fall under the path exception but still work with the keyboard cursor. |
| 2.1.2 No Keyboard Trap | A | Implemented | The modal dialog closes with Escape or Cancel. Focus in the canvas can leave with Tab. |
| 2.1.4 Character Key Shortcuts | A | Implemented | The only shortcut is Escape (not a character key). Switch keys are active only when scanning is on and can be remapped. |
| 2.2.1 Timing Adjustable | A | Implemented | No limits by default; A5 is disabled; ×1–×10 multiplier; the auto-scan rate is adjustable and scanning stops after N cycles. |
| 2.2.2 Pause, Stop, Hide | A | Implemented | The B2 moving target is the task itself and can be paused or stopped; the scan highlight is user-started. |
| 2.3.1 Three Flashes | A | Implemented | No flashing content. |
| 2.4.1 Bypass Blocks | A | Implemented | Skip link to main. |
| 2.4.2 Page Titled | A | Implemented | The title changes per route ("Setup – NeuroMetric"…). |
| 2.4.3 Focus Order | A | Implemented | DOM order; focus moves to the heading on navigation, to the canvas on task start, to Resume on pause, and to the confirmation on Stop. |
| 2.4.4 Link Purpose | A | Implemented [auto] | Links read "Start A2", "Continue to tasks"… |
| 2.4.5 Multiple Ways | AA | Partially | A single-purpose app with persistent navigation; there is no search or site map. |
| 2.4.6 Headings and Labels | AA | Implemented [auto] | |
| 2.4.7 Focus Visible | AA | Implemented | 4 px outline; scan highlight 6 px. Not machine-verified. |
| 2.4.11 Focus Not Obscured (Minimum) | AA | Implemented | No sticky or fixed overlays except the modal dialog. Untested at 400 % zoom. |
| 2.5.1 Pointer Gestures | A | Implemented | No multipoint gestures. D1 dragging has a drag-lock alternative (select to pick up, select to drop) for every selection method except "click". |
| 2.5.2 Pointer Cancellation | A | Partially | UI controls activate on release (native). **Task stimuli are selected on press (down-event)**, the measurement convention for pointing tasks (the timing is essential). Recovery is by Skip trial or Back. |
| 2.5.3 Label in Name | A | Implemented [auto] | Visible text is the accessible name; −/+ steppers have names such as "Increase Dwell time". |
| 2.5.4 Motion Actuation | A | N/A | No device-motion input. |
| 2.5.7 Dragging Movements | AA | Partially | D1 measures dragging. A single-pointer alternative (drag-lock) is used automatically for dwell, keyboard, scanning and gamepad, but not offered in "click" mode. |
| 2.5.8 Target Size (Minimum) | AA | Partially | UI controls are ≥ 44 px [auto: axe target-size]. Task stimuli are essential presentations (exception), but A2's 32 task-px targets can fall below 24 CSS px on small screens; "Smallest target in task A2" can exclude them. |
| 3.1.1 Language of Page | A | Implemented | `lang="en"`. |
| 3.1.2 Language of Parts | AA | N/A | English only (no translations yet). |
| 3.2.1 On Focus / 3.2.2 On Input | A | Implemented | Focus (including scan focus) never activates anything; settings apply immediately without changing context. |
| 3.2.3 Consistent Navigation / 3.2.4 Consistent Identification | AA | Implemented | The same header and control bar on every screen. |
| 3.2.6 Consistent Help | A | N/A | No help mechanism yet; when one is added it must sit in a consistent place. |
| 3.3.1 Error Identification | A | Implemented | Upload and login errors appear as text; wrong selections are announced. |
| 3.3.2 Labels or Instructions | A | Implemented [auto] | |
| 3.3.3 Error Suggestion | AA | Implemented | Messages say what to do (Back, download JSON…). |
| 3.3.4 Error Prevention | AA | Implemented | Stop needs confirmation; upload is explicit; data is never deleted. |
| 3.3.7 Redundant Entry | A | Implemented | Settings are remembered per browser. |
| 3.3.8 Accessible Authentication (Minimum) | AA | Implemented | Username/password with autocomplete, so paste and password managers work; no cognitive test. |
| 4.1.2 Name, Role, Value | A | Implemented [auto] | Native elements; `aria-pressed`; `<output>`. |
| 4.1.3 Status Messages | AA | Implemented | `role="status"` and `aria-live` for feedback, scan results and upload messages. |

## 3. Automated test results (2026-11-27, headless Chromium, `tests/web`)

| Check | Result | File |
|---|---|---|
| axe-core 4.10.3, tags wcag2a/2aa/21a/21aa/22aa/best-practice. 58 scans: 5 static screens × 3 themes; the watch-demo × 3 themes; all 17 tasks running × 2 themes; A5 with time pressure on; pause overlay, assistance dialog, stop confirmation, results with data, setup with an active scan highlight. | **0 violations** (0 critical, 0 serious, 0 moderate, 0 minor). The only "needs review" rule was `color-contrast` (on 11 scans), which axe cannot decide over the scaled task canvas or overlapping content; it needs manual review. | `experiments/results/Q_accessibility/axe_summary.json`, `axe_violations.csv` |
| Reflow 320 px, 200 % text, WCAG text spacing (7 screens each) | No horizontal page scroll (21/21) | `reflow_text_spacing.csv` |
| E2E: A4 keyboard-only with two-switch step scanning | Completed; Python scorer success 1.0 | `e2e_tasks_summary.json` |
| E2E: Setup → task list with **one switch** (auto-scan, 150 ms) | Completed | `e2e_tasks_summary.json` |
| E2E: E1 copy typing by dwell (300 ms), with one corrected error | Completed; MSD error 0, corrected error rate 0.048 | `e2e_tasks_summary.json` |
| E2E: A2 with pointer, pause/resume and an ASSIST record | Completed; PAUSE, RESUME and ASSIST validated by Python | `e2e_tasks_summary.json` |
| Upload of a keyboard/pointer session to the real backend (synthetic demo study) | Stored and scored server-side | `e2e_backend_upload.json` |

The automated input is synthetic (CDP mouse, keyboard keys standing in for switches). It shows
that the logic works. It does **not** show that real switch interfaces, eye trackers, head
pointers or screen readers work with the app.

## 4. Known accessibility gaps

1. **Not tested with any real AT or with disabled users.** This is the main gap (§5).
2. Pointing-task stimuli cannot be perceived without vision (construct limit). There is no audio
   cueing for E2 or A4, so low-vision and blind participants are limited to item tasks with a
   screen reader. Usability for them is unverified.
3. Task stimuli are selected on press (2.5.2).
4. D1 has no drag-lock option in "click" mode.
5. Small A2 targets fall below 24 CSS px on small screens unless excluded.
6. Scanning a text field only focuses it; one-switch users cannot enter the optional study code.
   It is optional and staff-entered.
7. There is no audio feedback or auditory scanning (spoken item names). Many switch users rely on
   these, so this should be added.
8. Only English is available; there is no plain-language review yet.
9. Forced-colors (Windows High Contrast) mode is handled with `forced-color-adjust` on task cues,
   but has not been viewed on Windows.
10. Mobile browsers (VoiceOver iOS, TalkBack) and Switch Control / Switch Access on phones and
    tablets have not been tried.

## 5. Manual test protocol (REQUIRED, NOT YET DONE)

None of the following has been carried out. Results go in `experiments/results/Q_accessibility/`
as `manual_<date>_<at>.md`, one per session. Record the AT name and version, browser and version,
OS, settings, tasks attempted, completion, assistance needed and issues (WCAG SC, severity).

**Participants and testers.** Recruit at least 2 expert AT users per AT class below (IRB/ethics
approval per site, compensated), plus an accessibility specialist. Testing must include users who
actually rely on each AT daily. Simulated use by able-bodied testers does not count.

| # | AT / configuration | Platforms | What to do | Pass criteria |
|---|---|---|---|---|
| 1 | Screen readers: NVDA (latest) + Firefox and Chrome; JAWS + Chrome; VoiceOver + Safari (macOS); VoiceOver (iOS) + Safari; TalkBack + Chrome (Android) | Win 11, macOS 15+, iOS 18+, Android 15+ | Full setup; task list; A4, E2, F1–F7 and C1 with the screen reader only; pause, assistance, stop; results and upload | All controls named and operable; instructions and feedback announced once, not repeatedly; no focus loss after each selection; dialog focus is trapped and restored |
| 2 | Switch hardware: USB switch interface (e.g. sending Space/Enter) with 1 and 2 switches; Bluetooth switch | Win, macOS, ChromeOS | One switch: complete setup, start A4, E1 (row-column), F2, pause, record assistance, stop, upload screen. Two switches: step-scan the same. Change scan rate and restart policy | Every control reachable; no accidental double activation from the native key behaviour; scan stops and restarts as configured; timing settings usable at 1–3 s |
| 3 | OS switch access: iOS/iPadOS Switch Control, Android Switch Access, macOS Switch Control | iPad, Android tablet, Mac | Use the OS scanner instead of the in-app scanner for the same flows | OS focus order matches the visual order; item buttons are actionable; the in-app scanner can be turned off without conflict |
| 4 | Eye trackers: Tobii (or equivalent) with Windows Eye Control or Tobii software; iPadOS eye tracking | Win 11, iPadOS | Mouse emulation + in-app dwell (A3, A4, E1, F2) versus OS dwell-click with in-app click mode | Dwell ring visible; no unintended selections with OS dwell plus in-app dwell together; calibration drift is handled by pause, recalibration and an ASSIST(calibration) record |
| 5 | Head pointers: camera head mouse (e.g. OS head pointer, Enable Viacam) | Win, macOS, iPadOS | A1, A2 with the "64 px and larger" setting, A4, E1 with dwell | Targets reachable; dwell tolerances reasonable; fatigue noted |
| 6 | BCI exposed as OS pointer or switch (where a research device is available, e.g. via Apple BCI HID Switch Control) | Per device | Declared modality `bci_cursor` / `bci_select`; A4, E2, F tasks | Events recorded with the declared modality; no browser-side assumptions about the device |
| 7 | Keyboard only (no pointer) | All desktop | Every screen and every task (pointing tasks via the keyboard cursor) | Visible focus at all times; no traps; Escape pauses |
| 8 | Voice control: Dragon, macOS/iOS Voice Control, Windows Voice Access | Win, macOS, iOS | "Click Start A2", "Click Pause", item tasks by name or number grid | Visible labels match spoken names (2.5.3) |
| 9 | Magnification and zoom: browser zoom 200 %/400 %, ZoomText, macOS Zoom | Win, macOS | Setup, task list, tasks at 400 % | No loss of content or function; focus not obscured |
| 10 | Display: Windows High Contrast / forced colours; in-app high-contrast theme; dark mode; reduced motion | Win, macOS | Look at every screen; run B2 with reduced motion | Cues and focus visible; B2 slower path used |
| 11 | Cognitive walkthrough with participants with cognitive or communication impairments and their care partners | Any | First-time setup and two tasks with minimal staff help | Instructions understood; error recovery used successfully; assistance recorded accurately |

Report every failure with the screen, SC, AT and severity. Fix and re-test before data collection
with participants. Repeat the protocol after any major UI change and at least once per battery
version.
