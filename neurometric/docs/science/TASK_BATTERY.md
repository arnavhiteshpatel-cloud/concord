# Digital functional task battery v1.0.0 (EXPERIMENTAL)

Generated from `src/neurometric/tasks/battery.py` (single source of truth). Status: experimental - not a validated clinical outcome assessment.

These are ORIGINAL tasks built from general HCI and rehabilitation principles. They are not an implementation of the Shirley Ryan AbilityLab Digital Assessment Interface or any licensed instrument, and imply no endorsement.

Task space 1280x800 CSS px; stimuli generated from a seed (`stimuli(task_id, seed)`) and identical in browser and simulator (`stimulus_hash`).

| ID | Family | Task | Construct | Simulated |
|---|---|---|---|---|
| A1 | target_acquisition | Single target selection | Basic pointing and selection: can the user move to and select one target. | yes |
| A2 | target_acquisition | Multidirectional target acquisition (ISO-style ring) | Speed-accuracy of aimed pointing (Fitts throughput). | yes |
| A3 | target_acquisition | Dwell selection | Selection by holding the pointer still (gaze / head-pointer style). | yes |
| A4 | target_acquisition | Selection among distractors (grid) | Choosing one item among many: the core of on-screen keyboards, menus and communication boards. | yes |
| A5 | target_acquisition | Time-constrained acquisition | Ability to act within a deadline (e.g. answering a prompt in time). | yes |
| B1 | cursor_control | Straight-line steering (tunnel) | Constrained movement along a path (steering law). | browser only |
| B2 | cursor_control | Continuous tracking | Continuous closed-loop control; sensitive to latency and smoothing. | yes |
| C1 | scrolling | Scroll to target | Navigating long content by scrolling. | browser only |
| D1 | drag_and_drop | Drag object to zone | Selecting, holding and relocating an object (hold-state reliability). | browser only |
| E1 | text_communication | Copy typing (on-screen keyboard) | Written communication rate and accuracy. | yes |
| E2 | text_communication | Structured phrase selection | Message selection from a set (AAC-style communication). | yes |
| F1 | digital_adl | Select a contact (simulated) | Simulated digital activity: find and open a contact. | yes |
| F2 | digital_adl | Compose a predefined message (simulated) | Communication activity: open a conversation and send a predefined message composed from tiles. | yes |
| F3 | digital_adl | Menu navigation (simulated) | Navigate a two-level application menu. | yes |
| F4 | digital_adl | Calendar booking (simulated) | Schedule an appointment: pick a date, a time slot, confirm. | yes |
| F5 | digital_adl | Form completion (simulated) | Fill a short form with predefined choices (no personal data). | yes |
| F6 | digital_adl | Communication board (simulated) | Express a predefined need using a symbol/word board (AAC). | yes |
| F7 | digital_adl | Simulated browser navigation | Follow a link on a simulated web page and find a named item. | yes |

## Specifications

### A1 — Single target selection (v1.0.0)

- **Construct:** Basic pointing and selection: can the user move to and select one target.
- **Rationale:** Lowest-demand primitive; floor task for severe impairment; reaction and movement onset.
- **Stimuli:** Start button at canvas centre, then one circular target at random direction, distance D in {200, 350} px, width W in {80, 120} px.
- **Timing:** Stimulus onset = target shown (marker stimulus_on). MT = onset to terminating selection. Max 20 s per trial (configurable).
- **Errors:** Selection outside the target = error (ends trial). Timeout = no selection by max time.
- **Completion:** 12 trials or 6 minutes, whichever first; participant may pause at any time.
- **Assistance:** Assistance is recorded as ASSIST events (setup, physical, verbal, troubleshooting, calibration, task_completion) by the participant, care partner or staff via the assistance panel; any assistance during a trial marks it 'assisted', never 'failed'.
- **Accessibility:** Large targets; no time pressure by default; works with click, dwell, switch-activated click; keyboard alternative Space/Enter at the cursor.
- **Scoring:** success, movement_time_ms, onset_ms, path_efficiency, endpoint_error_px
- **Defaults:** `{'D': [200, 350], 'W': [80, 120], 'n': 12, 'max_ms': 20000}`

### A2 — Multidirectional target acquisition (ISO-style ring) (v1.0.0)

- **Construct:** Speed-accuracy of aimed pointing (Fitts throughput).
- **Rationale:** Follows the ISO 9241-411 multidirectional tapping paradigm so throughput is comparable to the HCI literature; varying D and W gives a range of difficulty.
- **Stimuli:** 13 circular targets equally spaced on a circle of diameter D; the highlighted target alternates across the circle. D in {256, 512} px, W in {32, 64, 96} px (IDs 1.9-4.1 bits); conditions counterbalanced by seed.
- **Timing:** Sequential: MT = time between successive selections (first selection of each sequence starts the clock and is not scored). Max 15 s per selection.
- **Errors:** Selection outside the highlighted target = miss (counts in We; trial ends).
- **Completion:** 6 conditions x 13 selections; ~3-6 min with mouse.
- **Assistance:** Assistance is recorded as ASSIST events (setup, physical, verbal, troubleshooting, calibration, task_completion) by the participant, care partner or staff via the assistance panel; any assistance during a trial marks it 'assisted', never 'failed'.
- **Accessibility:** Smallest W (32 px) can be excluded via the accessibility profile (target_min_px); throughput then computed only over administered conditions.
- **Scoring:** fitts_throughput_bps (effective, per condition then averaged), error_rate, movement_time_ms, path_efficiency, target_reentries, overshoot_px, movement_variability_px, dial_in_ms
- **Defaults:** `{'D': [256, 512], 'W': [32, 64, 96], 'n_per_condition': 13, 'max_ms': 15000}`

### A3 — Dwell selection (v1.0.0)

- **Construct:** Selection by holding the pointer still (gaze / head-pointer style).
- **Rationale:** Dwell is the dominant selection method for eye-gaze and many head-pointer users; isolates stability (holding still) from clicking.
- **Stimuli:** Same geometry as A2 with D=384, W in {64, 96}; dwell threshold configurable (default 800 ms).
- **Timing:** MT includes the dwell time; dwell resets when the pointer leaves the item.
- **Errors:** Dwell completed on a non-target item = unintended selection (Midas-touch error).
- **Completion:** 2 conditions x 13 selections.
- **Assistance:** Assistance is recorded as ASSIST events (setup, physical, verbal, troubleshooting, calibration, task_completion) by the participant, care partner or staff via the assistance panel; any assistance during a trial marks it 'assisted', never 'failed'.
- **Accessibility:** Dwell threshold and visual dwell-progress indicator configurable.
- **Scoring:** success, movement_time_ms, dwell_resets, unintended_dwell_selections
- **Defaults:** `{'D': [384], 'W': [64, 96], 'n_per_condition': 13, 'dwell_ms': 800, 'max_ms': 15000}`

### A4 — Selection among distractors (grid) (v1.0.0)

- **Construct:** Choosing one item among many: the core of on-screen keyboards, menus and communication boards.
- **Rationale:** Allows achieved-bitrate (penalised for errors) comparable to BCI grid tasks.
- **Stimuli:** Grid of R x C square items (default 4 x 6, 120 px cells, 100 px items); one cued item per trial; cue sequence from seed.
- **Timing:** MT = cue onset to selection; max 20 s.
- **Errors:** Selecting a non-cued item = wrong selection (ends trial). Empty-space clicks are counted but do not end the trial.
- **Completion:** 24 trials.
- **Assistance:** Assistance is recorded as ASSIST events (setup, physical, verbal, troubleshooting, calibration, task_completion) by the participant, care partner or staff via the assistance panel; any assistance during a trial marks it 'assisted', never 'failed'.
- **Accessibility:** Cell size configurable; scanning order for switch users.
- **Scoring:** success, movement_time_ms, achieved_bitrate_bps, wolpaw_itr_bpm (flagged), wrong_item_selections
- **Defaults:** `{'rows': 4, 'cols': 6, 'cell': 120, 'item': 100, 'n': 24, 'max_ms': 20000}`

### A5 — Time-constrained acquisition (v1.0.0)

- **Construct:** Ability to act within a deadline (e.g. answering a prompt in time).
- **Rationale:** Real interfaces impose time limits (call answer, dialog timeout); success-within-deadline is interpretable for function.
- **Stimuli:** As A1 with deadline in {2000, 4000} ms.
- **Timing:** Trial ends at deadline.
- **Errors:** No selection by deadline = timeout error.
- **Completion:** 16 trials.
- **Assistance:** Assistance is recorded as ASSIST events (setup, physical, verbal, troubleshooting, calibration, task_completion) by the participant, care partner or staff via the assistance panel; any assistance during a trial marks it 'assisted', never 'failed'.
- **Accessibility:** Off by default for participants whose profile sets 'no time pressure' (WCAG 2.2.1 adjustable timing).
- **Scoring:** success_within_deadline, movement_time_ms
- **Defaults:** `{'D': [250], 'W': [100], 'deadline_ms': [2000, 4000], 'n': 16}`

### B1 — Straight-line steering (tunnel) (v1.0.0)

- **Construct:** Constrained movement along a path (steering law).
- **Rationale:** Captures path control that aimed pointing does not (e.g. dragging along menus).
- **Stimuli:** Horizontal tunnel of length 600 px, width in {40, 80} px; start and end zones.
- **Timing:** MT = leaving the start zone to entering the end zone.
- **Errors:** Leaving the tunnel = exit error (trial continues; count reported).
- **Completion:** 8 trials.
- **Assistance:** Assistance is recorded as ASSIST events (setup, physical, verbal, troubleshooting, calibration, task_completion) by the participant, care partner or staff via the assistance panel; any assistance during a trial marks it 'assisted', never 'failed'.
- **Accessibility:** Tunnel width configurable.
- **Scoring:** success, movement_time_ms, tunnel_exits, rms_path_deviation_px
- **Defaults:** `{'L': 600, 'W': [40, 80], 'n': 8}`

### B2 — Continuous tracking (v1.0.0)

- **Construct:** Continuous closed-loop control; sensitive to latency and smoothing.
- **Rationale:** Discrete selections can hide latency; tracking exposes it directly (lag).
- **Stimuli:** Target moves on a sum-of-sines path (0.1-0.4 Hz components), 30 s per trial; target radius 40 px.
- **Timing:** Sampled at display rate; first 3 s excluded.
- **Errors:** None (continuous).
- **Completion:** 3 trials of 30 s.
- **Assistance:** Assistance is recorded as ASSIST events (setup, physical, verbal, troubleshooting, calibration, task_completion) by the participant, care partner or staff via the assistance panel; any assistance during a trial marks it 'assisted', never 'failed'.
- **Accessibility:** Speed scale configurable; reduced-motion profiles substitute a slower path.
- **Scoring:** rms_error_px, time_on_target, lag_ms
- **Defaults:** `{'duration_ms': 30000, 'radius': 40, 'n': 3}`

### C1 — Scroll to target (v1.0.0)

- **Construct:** Navigating long content by scrolling.
- **Rationale:** Scrolling is one of the commonest real digital actions and uses a different control mapping (rate control) from pointing.
- **Stimuli:** Vertical list of 60 items (60 px rows) in a 400 px viewport; cued item must be brought into the highlighted band and selected; direction up or down.
- **Timing:** Time from cue to selection; max 30 s.
- **Errors:** Selecting while the cued item is outside the band = error.
- **Completion:** 10 trials.
- **Assistance:** Assistance is recorded as ASSIST events (setup, physical, verbal, troubleshooting, calibration, task_completion) by the participant, care partner or staff via the assistance panel; any assistance during a trial marks it 'assisted', never 'failed'.
- **Accessibility:** Scroll by wheel, scroll buttons (for switch / dwell), or keys.
- **Scoring:** success, time_to_select_ms, band_passes, reversals
- **Defaults:** `{'rows': 60, 'row_px': 60, 'viewport_px': 400, 'n': 10, 'max_ms': 30000}`

### D1 — Drag object to zone (v1.0.0)

- **Construct:** Selecting, holding and relocating an object (hold-state reliability).
- **Rationale:** Dragging requires sustained selection; BCI click decoders and dwell systems often struggle with holds.
- **Stimuli:** Object (60 px) at start; drop zone width in {80, 160} px at D=400 px.
- **Timing:** Time from cue to successful drop; max 30 s.
- **Errors:** Release outside the zone = drop error (object stays; participant re-grabs).
- **Completion:** 10 trials.
- **Assistance:** Assistance is recorded as ASSIST events (setup, physical, verbal, troubleshooting, calibration, task_completion) by the participant, care partner or staff via the assistance panel; any assistance during a trial marks it 'assisted', never 'failed'.
- **Accessibility:** Drag-lock mode (click to pick up, click to drop) available for users who cannot hold.
- **Scoring:** success, time_ms, unintended_drops, placement_error_px
- **Defaults:** `{'D': 400, 'zone': [80, 160], 'n': 10}`

### E1 — Copy typing (on-screen keyboard) (v1.0.0)

- **Construct:** Written communication rate and accuracy.
- **Rationale:** Communication is the highest-value outcome for people with paralysis; copy typing gives a controlled, content-free measure (no private text).
- **Stimuli:** Presented phrases from NeuroMetric's original phrase set (short, common, lowercase); on-screen QWERTY keyboard with space and backspace; pointer or scanning.
- **Timing:** Clock starts at first keystroke; ends at the Done key or time limit (3 min/phrase).
- **Errors:** Uncorrected errors (MSD) and corrected errors (IF) reported separately.
- **Completion:** 5 phrases.
- **Assistance:** Assistance is recorded as ASSIST events (setup, physical, verbal, troubleshooting, calibration, task_completion) by the participant, care partner or staff via the assistance panel; any assistance during a trial marks it 'assisted', never 'failed'.
- **Accessibility:** Key size, scanning rate and dwell configurable; no free text is stored.
- **Scoring:** wpm, ccpm, msd_error_rate, total_error_rate, kspc, correction_burden
- **Defaults:** `{'n_phrases': 5, 'key': 90}`

### E2 — Structured phrase selection (v1.0.0)

- **Construct:** Message selection from a set (AAC-style communication).
- **Rationale:** Many AAC users communicate via phrase/word selection rather than spelling.
- **Stimuli:** Board of 12 phrases; spoken/written cue names the phrase to select.
- **Timing:** MT = cue to selection.
- **Errors:** Wrong phrase = error.
- **Completion:** 12 trials.
- **Assistance:** Assistance is recorded as ASSIST events (setup, physical, verbal, troubleshooting, calibration, task_completion) by the participant, care partner or staff via the assistance panel; any assistance during a trial marks it 'assisted', never 'failed'.
- **Accessibility:** Large tiles; scanning order.
- **Scoring:** success, movement_time_ms, achieved_bitrate_bps
- **Defaults:** `{'n': 12}`

### F1 — Select a contact (simulated) (v1.0.0)

- **Construct:** Simulated digital activity: find and open a contact.
- **Rationale:** Ecological composite of scroll + select; in-app only, no real contacts.
- **Stimuli:** Simulated contact list (fictional names) with 20 entries; target named in cue.
- **Timing:** Time to complete; steps logged.
- **Errors:** Opening the wrong contact = error; 'back' returns.
- **Completion:** 1 trial per session.
- **Assistance:** Assistance is recorded as ASSIST events (setup, physical, verbal, troubleshooting, calibration, task_completion) by the participant, care partner or staff via the assistance panel; any assistance during a trial marks it 'assisted', never 'failed'.
- **Accessibility:** All controls reachable by keyboard / scanning.
- **Scoring:** completed, time_to_complete_ms, wrong_selections, assisted
- **Defaults:** `{}`

### F2 — Compose a predefined message (simulated) (v1.0.0)

- **Construct:** Communication activity: open a conversation and send a predefined message composed from tiles.
- **Rationale:** In-app only; nothing is sent.
- **Stimuli:** Open messages -> choose recipient -> select 3 message tiles -> press send.
- **Timing:** Time to complete.
- **Errors:** Wrong tile/recipient = error.
- **Completion:** 1 trial per session.
- **Assistance:** Assistance is recorded as ASSIST events (setup, physical, verbal, troubleshooting, calibration, task_completion) by the participant, care partner or staff via the assistance panel; any assistance during a trial marks it 'assisted', never 'failed'.
- **Accessibility:** 
- **Scoring:** completed, time_to_complete_ms, wrong_selections, assisted
- **Defaults:** `{}`

### F3 — Menu navigation (simulated) (v1.0.0)

- **Construct:** Navigate a two-level application menu.
- **Rationale:** Common desktop interaction.
- **Stimuli:** Menu bar with 5 menus x 6 items; target named in cue.
- **Timing:** Time to complete.
- **Errors:** Wrong menu or item = error.
- **Completion:** 4 trials.
- **Assistance:** Assistance is recorded as ASSIST events (setup, physical, verbal, troubleshooting, calibration, task_completion) by the participant, care partner or staff via the assistance panel; any assistance during a trial marks it 'assisted', never 'failed'.
- **Accessibility:** 
- **Scoring:** completed, time_to_complete_ms, wrong_selections, assisted
- **Defaults:** `{}`

### F4 — Calendar booking (simulated) (v1.0.0)

- **Construct:** Schedule an appointment: pick a date, a time slot, confirm.
- **Rationale:** Multi-step goal-directed activity.
- **Stimuli:** Month grid + time-slot list + confirm.
- **Timing:** Time to complete.
- **Errors:** Wrong date/slot = error.
- **Completion:** 1 trial.
- **Assistance:** Assistance is recorded as ASSIST events (setup, physical, verbal, troubleshooting, calibration, task_completion) by the participant, care partner or staff via the assistance panel; any assistance during a trial marks it 'assisted', never 'failed'.
- **Accessibility:** 
- **Scoring:** completed, time_to_complete_ms, wrong_selections, assisted
- **Defaults:** `{}`

### F5 — Form completion (simulated) (v1.0.0)

- **Construct:** Fill a short form with predefined choices (no personal data).
- **Rationale:** Forms are ubiquitous in health portals and daily admin.
- **Stimuli:** 4 fields with choice buttons + submit.
- **Timing:** Time to complete.
- **Errors:** Wrong choice = error.
- **Completion:** 1 trial.
- **Assistance:** Assistance is recorded as ASSIST events (setup, physical, verbal, troubleshooting, calibration, task_completion) by the participant, care partner or staff via the assistance panel; any assistance during a trial marks it 'assisted', never 'failed'.
- **Accessibility:** 
- **Scoring:** completed, time_to_complete_ms, wrong_selections, assisted
- **Defaults:** `{}`

### F6 — Communication board (simulated) (v1.0.0)

- **Construct:** Express a predefined need using a symbol/word board (AAC).
- **Rationale:** Core AAC interaction.
- **Stimuli:** 4 x 5 board of words; build a 3-word message.
- **Timing:** Time to complete.
- **Errors:** Wrong word = error (delete key available).
- **Completion:** 2 trials.
- **Assistance:** Assistance is recorded as ASSIST events (setup, physical, verbal, troubleshooting, calibration, task_completion) by the participant, care partner or staff via the assistance panel; any assistance during a trial marks it 'assisted', never 'failed'.
- **Accessibility:** 
- **Scoring:** completed, time_to_complete_ms, wrong_selections, assisted
- **Defaults:** `{}`

### F7 — Simulated browser navigation (v1.0.0)

- **Construct:** Follow a link on a simulated web page and find a named item.
- **Rationale:** Web use is a key participation activity.
- **Stimuli:** Static simulated page with links.
- **Timing:** Time to complete.
- **Errors:** Wrong link = error ('back' available).
- **Completion:** 1 trial.
- **Assistance:** Assistance is recorded as ASSIST events (setup, physical, verbal, troubleshooting, calibration, task_completion) by the participant, care partner or staff via the assistance panel; any assistance during a trial marks it 'assisted', never 'failed'.
- **Accessibility:** No external network access.
- **Scoring:** completed, time_to_complete_ms, wrong_selections, assisted
- **Defaults:** `{}`

## Considered and excluded

- **Obstacle navigation** — Overlaps with B1 steering and A4 selection among distractors; adds layout complexity without a distinct construct. Kept as a web demo only.
- **Free text entry** — Requires storing personal text; offered only with explicit consent and never stored by default (character counts and timing only).

## Which tasks are scientifically meaningful (from the simulation study)
See EXPERIMENT_REGISTRY.md, experiment G. Summary rule used to keep a task in the core battery:
it must (a) respond monotonically to at least one degradation type, (b) add sensitivity to a
degradation type that other tasks miss, or (c) measure a functional construct (communication,
activities) that the primitives do not. Version history: v1.0.0 (2026-11-27) initial.
