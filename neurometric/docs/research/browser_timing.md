# Browser timing: what NeuroMetric can claim, how to measure it, what to store

Prepared 2026-11-27. Evidence labels follow `CONVENTIONS.md`. Sources were accessed 2026-11-27.

## 1. Bottom line (recommendation)

1. **Do not claim millisecond accuracy for absolute response times collected in a browser.** Two independent
   hardware-validated studies found that a browser's recorded RT exceeds the true RT by a roughly constant amount,
   **tens of milliseconds** (mean 71–87 ms by platform in one study; 8–67 ms across packages and browsers in the
   other). Variability (SD) runs from under 1 ms to about 28 ms, depending on the platform, browser, OS and keyboard.
   [RF] (§3)
2. **What can be claimed:**
   - Event timestamps carry the **clock resolution** of the browser. The spec floor is 100 µs, or 5 µs when
     cross-origin isolated. Shipping browsers coarsen more: Chrome 0.1 ms (0.005 ms isolated); Safari and Firefox
     1 ms (0.02 ms isolated); Firefox with resistFingerprinting 16.67 ms. [V]
   - **Within-participant, same-device, same-browser, same-modality comparisons** (change over time, condition
     differences) are the defensible primary analysis. The constant device lag largely cancels out. Variance
     inflation is quantified per device class. [RF + INF]
   - Absolute RT is reported **with a device-class lag/precision band** taken from NeuroMetric's own bench
     validation (photodiode + actuator). A literature value is not enough. [RF: "We stress the importance of
     scientists making their own timing validation measurements"]
3. **For assistive inputs (switch scanning, dwell, eye gaze, head pointer, BCI)** the measured interval is a
   **selection time**. It includes assistive-technology parameters such as scan interval, dwell time and decoder
   latency. Report it as "selection time" and store the AT settings, not "reaction time". [INF]
4. **Never** compare raw RT across participants who used different modalities, devices or browsers without
   modelling those factors. [RF: Anwyl-Irvine et al. recommend within-participant designs and limiting browsers]

Suggested wording for protocol or labelling:

> "Response timing was recorded in the browser using high-resolution event timestamps (resolution 0.005–1 ms,
> browser-dependent). End-to-end latency from physical input to timestamp is device-dependent and was
> characterised on bench for each supported device class (median lag X ms, SD Y ms). Primary endpoints use
> within-participant change on a fixed device/browser/input configuration; absolute timings are reported with
> device-class uncertainty."

## 2. What the specs actually guarantee

| Mechanism | Guarantee | Label / source |
|---|---|---|
| `performance.now()` / HR-Time "coarsen time" | Resolution of **100 µs or coarser**, or **5 µs or coarser** when cross-origin isolated. The implementation may also **jitter** timestamps. Monotonic clock | [V] https://w3c.github.io/hr-time/ |
| Actual browser coarsening | Chrome 0.1 ms (isolated 0.005 ms); Safari 1 ms (isolated 0.02 ms); Firefox 1 ms via `privacy.reduceTimerPrecision` (isolated 0.02 ms); Firefox resistFingerprinting 16.667 ms | [V] https://developer.mozilla.org/en-US/docs/Web/API/Event/timeStamp ; https://developer.mozilla.org/en-US/docs/Web/API/Performance/now |
| Cross-origin isolation | Requires `Cross-Origin-Opener-Policy: same-origin` + `Cross-Origin-Embedder-Policy: require-corp` (or `credentialless`). Check with `self.crossOriginIsolated` | [PK] (MDN `crossOriginIsolated` page referenced from performance.now page [V]) |
| Sleep behaviour | MDN notes the monotonic clock may stop during OS sleep on non-Windows platforms (browser bugs cited) | [V] performance.now MDN |
| `Event.timeStamp` | DOM: returns the value it was initialised with. MDN: ms since time origin "when the event was created", precision may be reduced. The spec does not guarantee that it marks hardware input time. Chromium sets it from the platform input timestamp in practice | [V] https://dom.spec.whatwg.org/ ; [V] MDN; Chromium behaviour [PK] |
| Pointer Events `getCoalescedEvents()` | [SecureContext]. Coalesced events have monotonically increasing `timeStamp`, sorted, ≤ dispatched event | [V] https://w3c.github.io/pointerevents/ |
| `pointerrawupdate` | Fired only in secure contexts, "as soon as possible and as frequently as the JavaScript can handle". **Not Baseline**: limited browser support | [V] spec + https://developer.mozilla.org/en-US/docs/Web/API/Element/pointerrawupdate_event |
| `requestAnimationFrame(ts)` | `ts` = "end time of the previous frame's rendering", minimal precision 1 ms, equal to `document.timeline.currentTime`. Generally matches the display refresh (60/75/120/144 Hz). **Paused in background tabs/hidden iframes** | [V] https://developer.mozilla.org/en-US/docs/Web/API/Window/requestAnimationFrame |
| Event Timing API (`PerformanceEventTiming`) | Baseline since December 2025. `processingStart − startTime` = input delay; `duration` to next paint **rounded to 8 ms** | [V] https://developer.mozilla.org/en-US/docs/Web/API/PerformanceEventTiming |
| Gamepad API | Pads are not exposed until a "gamepad user gesture" (fingerprinting mitigation). `Gamepad.timestamp` = current high-resolution time whenever new button/axis data is received. Must be **polled** (rAF) | [V] https://w3c.github.io/gamepad/ |
| WebHID | Now a **WHATWG Living Standard** (last updated 14 Nov 2026). `requestDevice()` requires transient user activation and a window context. A HID blocklist applies. Permissions-Policy integrated. **Not Baseline** (Chromium-only in practice) | [V] https://hid.spec.whatwg.org/ ; https://developer.mozilla.org/en-US/docs/Web/API/WebHID_API |

**Consequence.** No web API gives the photon-onset time of a stimulus. Stimulus onset is estimated as the next
frame after the rAF callback that changed the DOM. It is uncertain by about one refresh interval (16.7 ms at
60 Hz), plus compositor and display latency that the page cannot see. [INF, consistent with RF §3]

## 3. Published validation results (what to cite)

- **Bridges, Pitiot, MacAskill & Peirce (2020)**, *The timing mega-study*, PeerJ 8:e9414,
  doi:10.7717/peerj.9414 (PMC7512138). Tested with a Black Box Toolkit across 110,000+ trials. Lab packages reached
  sub-ms precision. Online: "most of the packages achieved precision at least under 10 ms in all browsers, with
  PsychoPy achieving a precision under 3.5 ms in all". There was "considerable variability between OS/browser
  combinations, especially in audio-visual synchrony". Also: "We stress the importance of scientists making their
  own timing validation measurements". [RF] https://europepmc.org/article/PMC/PMC7512138
  As summarised by Anwyl-Irvine et al. (2021): RT lags 8–67 ms, precision < 1–8 ms, visual lag 0–2 frames, and
  auditory delays "in the hundreds of milliseconds". [RF]
- **Anwyl-Irvine, Dalmaijer, Hodges & Evershed (2021)**, *Realistic precision and accuracy of online experiment
  platforms, web browsers, and devices*, Behav Res Methods 53:1407–1425, doi:10.3758/s13428-020-01501-5
  (PMC8367876). Robotic actuator on real keyboards:
  - **RT delay mean (SD) by platform:** Gorilla 78.5 (8.3) ms; Lab.js 71.3 (28.2); PsychoJS 82.3 (16.4);
    jsPsych 87.4 (15.3). By browser: Chrome 78.8 (18.5), Edge 80.1 (19.8), Firefox 82.3 (18.6), Safari 76.5 (21.9).
    By device: Windows laptop 73.7 (20.3) to macOS desktop 85.4 (18.3). [RF]
  - **Visual duration delay mean (SD):** Chrome 11.5 (15.4) ms, Edge 18.7 (17.9), Firefox 22.6 (19.8),
    Safari 30.0 (15.1). Windows 12.4 (17.1) vs macOS 25.5 (17.2). [RF]
  - Recommendation: within-participant designs; limit browsers. [RF] https://europepmc.org/article/PMC/PMC8367876
- These studies used 2019–2020 browser versions and keyboard input. **No equivalent validation exists for switch
  interfaces, eye-gaze OS control, head pointers or BCI HID**, so NeuroMetric must generate its own. [INF]

## 4. Input-device and display contributions (budget)

| Source | Typical magnitude | Label |
|---|---|---|
| USB full-speed HID polling | bInterval-defined. Many standard mice and keyboards poll at 125 Hz (≤ 8 ms quantisation); gaming devices at 1000 Hz (≤ 1 ms) | [PK] |
| Keyboard matrix scan / debounce | Several ms, varies by model. Laptop and desktop keyboards differed in Anwyl-Irvine | [PK] / [RF] |
| Bluetooth HID (many switch interfaces, Neural Band→glasses) | Connection-interval dependent, typically several to tens of ms, variable | [PK] |
| OS/browser event pipeline | Visible as `processingStart − startTime` in Event Timing; main-thread blocking adds delay | [V] (API), magnitude [INF] |
| Display refresh quantisation | 1 frame = 16.7 ms @ 60 Hz, 8.3 ms @ 120 Hz | [INF] (arithmetic) |
| Display/compositor latency | Panel- and mode-dependent; often one or more frames; unknowable from the page | [PK] |
| AT layer (scan interval, dwell, Switch Control, BCI decoder) | Hundreds of ms to seconds, user-configured. Apple's BCI HID output report even carries `uiScanningLatency` to the *device*, not to apps | [V] (Apple BCI HID spec), magnitudes [INF] |

## 5. How to measure (NeuroMetric validation protocol)

1. **Bench rig per supported device class** (Windows/Chrome, macOS/Safari, iPadOS/Safari, Android/Chrome,
   ChromeOS/Chrome × keyboard, mouse, touch, USB switch interface, gamepad). Use a photodiode on the stimulus patch
   and a solenoid/robotic actuator on the input. A Black Box Toolkit-class device was used in both reference
   studies. Run ≥ 1,000 trials per configuration at several requested durations. Report mean lag, SD, p5/p50/p95,
   and dropped or extra frames. [RF method; INF protocol]
2. **For assistive inputs:** actuate the switch (relay into the switch jack), and for OS eye/head control use a
   scripted dwell. Measure the full chain to on-page timestamp. Record the AT settings used. [INF]
3. **In-session self-checks (every participant session, no hardware needed):**
   - estimate the refresh interval (median rAF delta over 120 frames) and count frames > 1.5× median;
   - record `crossOriginIsolated`, timer resolution (smallest non-zero `performance.now()` delta);
   - collect Event Timing input delay for responses;
   - track `visibilitychange`/`blur` during trials and invalidate trials with focus loss.
4. Re-validate after major browser/OS releases (quarterly), and pin supported browser versions in the protocol. [INF]

## 6. Fields to store per trial / per session

Per session:
`session_id, battery_version, ua_brand_version (UA-CH), os_name_version, device_class (declared+detected),
cross_origin_isolated, timer_resolution_ms_observed, refresh_interval_ms_est, refresh_interval_p95_ms,
viewport_css_px, device_pixel_ratio, input_modality_declared (enum: mouse|touch|pen|keyboard|switch_1|switch_2|
gamepad|eye_gaze_os|head_pointer_os|head_pointer_sw|bci_switch_control|emg_wristband_keys|other),
at_settings_declared (scan_rate_ms, dwell_ms, switch_count, os_feature), time_limit_multiplier (WCAG 2.2.1),
target_size_css_px, validation_profile_id (bench lag/SD band applied), time_origin_epoch_ms (performance.timeOrigin)`

Per trial:
`trial_id, stimulus_raf_ts_ms (rAF ts of frame that showed stimulus), stimulus_commit_now_ms, response_event_ts_ms
(event.timeStamp), response_handler_now_ms, event_type, pointer_type, is_trusted, coalesced_count,
event_timing_input_delay_ms, event_timing_duration_ms (8 ms-rounded), gamepad_ts_ms (if gamepad),
response_action (task-level action label such as select|next|left|right, never raw characters or text),
frames_dropped_during_trial, visibility_or_focus_lost (bool), trial_valid (bool), rt_ms = response_event_ts −
stimulus_raf_ts (labelled "selection_time_ms" for AT modalities)`

**Do not store:** typed text, key characters outside the task's response mapping, clipboard, screenshots,
gaze coordinates (HUT 0x12 privacy rule; see `bci_hid_and_input_standards.md`), or any cross-site data. [INF,
aligned with the telemetry privacy charter]
