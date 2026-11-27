# Stage 2 protocol: input-modality comparison (able-bodied, emulated assistive input)

> **DRAFT. Not submitted. Requires faculty PI and IRB review. No participants enrolled.**
> Plan: `CLINICAL_VALIDATION_PLAN.md` §4. Analysis: `sap_stage1_3.md` Part B. Task procedures:
> `stage1_protocol.md` §4.

## 1. Objective
Test whether NeuroMetric scores order four input modalities in the pre-specified direction
(H2.1, confirmatory), and estimate the size of the modality offsets.

## 2. Participants
- n = 24 able-bodied adults, 6 per Williams sequence.
- Eligibility as in Stage 1. Additional exclusions:
  - neck pain or a condition that makes head-pointer use uncomfortable;
  - known inability to use eye trackers (e.g. some hard contact lenses or eye conditions). This
    is self-reported. Calibration failures on the day are logged, not excluded after the fact.
- Prior participation in Stage 1 or 3 is not allowed.

## 3. Modalities and settings (fixed for all participants)
| Code | Modality | Setting held fixed | Primary scores applicable |
|---|---|---|---|
| A | Standard USB mouse | OS default speed, acceleration off | P1–P4 |
| B | Camera-based head pointer (software head tracking moving the OS cursor) with dwell click | Gain and smoothing at the software default; dwell 800 ms; webcam at 60 cm, centred | P1–P4 (A2 W ≥ 64 px only) |
| C | Eye-gaze OS pointer (consumer eye tracker + OS eye control) with dwell | Vendor calibration until accuracy is accepted by the software; dwell 800 ms | P1–P4 (A2 W ≥ 64 px only) |
| D | Single-switch automatic row/column scanning | USB switch interface sending one key; scan interval 1000 ms; 1 auto-restart | P2–P4 (P1 not applicable) |

Product names are chosen at IRB submission from what the lab owns or borrows. No purchase or
vendor arrangement exists. **No gaze coordinates, camera images or video are stored.** The
battery sees only OS pointer events and key events. Vendor licence terms for research use of
consumer eye trackers must be checked (`platform_matrix.md`: Tobii licence notes [V]).

## 4. Williams square and visits
| Sequence | Visit 1 (periods 1, 2) | Visit 2 (periods 3, 4) |
|---|---|---|
| 1 | A, B | D, C |
| 2 | B, C | A, D |
| 3 | C, D | B, A |
| 4 | D, A | C, B |

Visits are 2–7 days apart. Each ordered pair of modalities occurs once across sequences
(checked computationally).

## 5. Per-modality block (about 30 min)
1. **Setup and calibration** (5 min).
   - B: centre the head; recentre if the pointer drifts.
   - C: calibrate; up to 3 attempts. If all fail, log `calibration_failed` and give no block.
   - D: place the switch at the participant's preferred hand position.
2. **Standard training** (5 min). A fixed tutorial in the battery's practice mode: pointing,
   dwell or scan selection, pausing.
3. **Core subset:** A1, A2 (conditions with W ≥ 64 px for B, C; skipped for D), A4, E1
   (2 phrases), F3. Procedures as in `stage1_protocol.md` §4.
4. NASA-TLX raw for the modality (2 min) and fatigue NRS.
5. Break, ≥ 5 min, before the next modality.

## 6. Accessibility and comfort
- Head pointer: offer neck rests and remind participants to blink and relax. Stop on neck
  discomfort.
- Eye gaze: dim glare; allow breaks for dry eyes. Recalibrate between tasks if accuracy drifts,
  and log it as a calibration ASSIST event.
- Switch: place it where it is comfortable, and swap hands if asked.

## 7. Equipment
| Item | Specification |
|---|---|
| Laptop, display, browser | As in Stage 1, the same configuration |
| Mouse | As in Stage 1 |
| Webcam | 1080p USB webcam at 30–60 fps, fixed mount on the monitor |
| Head-pointer software | Selected at submission; version pinned; must run locally with no cloud video upload |
| Eye tracker | Consumer screen-mounted tracker supported by Windows eye control, mounted per the vendor; version pinned |
| Switch | Round button switch, 2.5–3 inch (65–75 mm), 3.5 mm jack |
| Switch interface | USB HID switch interface mapped to a single key |
| Bench timing | Lag/precision for each modality configuration measured on the bench before the study (`browser_timing.md` §5) |

## 8. Burden and compensation
Two visits of about 75 min ($25 each [HYP]).

## 9. Safety
Plan §2.3–2.4. Eye strain and neck strain are the specific risks. Stop rules apply.

## 10. Data
As in Stage 1. Modality and settings are stored as session metadata (`input_modality_declared`,
`at_settings_declared`).
