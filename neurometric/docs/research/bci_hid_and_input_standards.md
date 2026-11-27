# BCI HID, input standards and accessibility standards

Prepared 2026-11-27 for the NeuroMetric functional task battery (multi-modal input) and the opt-in
usage-telemetry framework. Evidence labels follow `CONVENTIONS.md`. All web sources accessed
2026-11-27 unless stated otherwise.

Search-budget note: the shared web-search quota for this session ran out partway through the work.
Every item below that could not be fetched directly from a primary URL is labelled [PK] or [UNR]
and marked "not re-verified". The main gaps are the IEEE P2731/P2794 status, Tobii Game Integration
terms, and the switch-interface vendor pages.

---

## 1. Apple BCI Human Interface Device (BCI HID) protocol

### 1.1 What it is

- **Announcement.** Apple's 13 May 2025 accessibility preview said: "iOS, iPadOS, and visionOS will add a
  new protocol to support Switch Control for Brain Computer Interfaces (BCIs), an emerging technology
  that allows users to control their device without physical movement." [V]
  https://www.apple.com/newsroom/2025/05/apple-unveils-powerful-accessibility-features-coming-later-this-year/
- **Specification.** The specification is the Apple developer article *"Brain-computer interface HID reference for connecting
  to Apple platforms"*. The Accessibility framework lists it alongside the Braille HID reference.
  Its listed availability is **iOS 26.0+, iPadOS 26.0+ and visionOS 26.0+. macOS is not listed.** [V]
  https://developer.apple.com/documentation/accessibility/brain-computer-interface-hid-reference-for-connecting-to-apple-platforms
  (A machine-readable copy is at the same URL with a `.md` suffix. Copyright line 2026, so the page has been
  revised since the 2025 launch.)
- **Audience.** The article is written "for manufacturers of third-party brain-computer interface hardware devices
  who want to build in firmware support". It is a **firmware/device-side** spec, not an app API. [V] (same URL)
- **Design intent (Apple's wording).** The device identifies through a HID descriptor so it "can be recognized by
  a host computing device ... without requiring specialized drivers". Assistive features "like switch
  software ... can recognize the device as a dedicated accessibility control interface". The descriptor
  "can support bidirectional communication", which lets the device switch decoding models based on context.
  The device manufacturer decides how to turn neural signals into commands. [V] (same URL)
- **System features driven.** The article names Switch Control and AssistiveTouch. [V]

### 1.2 Descriptor and reports (as published on 2026-11-27) [V]

The descriptor uses a top-level Application collection on **Usage Page 0x60, labelled "Brain Control
Interface" in Apple's example**, Usage 0x01 "BCI Application".

| Report | Direction | Usage page / usage | Payload | Host behaviour |
|---|---|---|---|---|
| ID 1 Signal quality | Input | 0x60 / 0x02 | `signalQuality[0]` = button number ID; `[1]` = neural-activity strength scaled 0–100 % → 0–255 | Host may show it in the UI. iOS draws an animated overlay when the Switch Control cursor has focus |
| ID 2 Buttons | Input | Button page 0x09, usages 1–32 | 32 one-bit absolute button states | Mapped to actions. The iOS list includes Select, MoveToNextItem, MoveToPreviousItem, ToggleAssistiveTechnologyMenu, Activate, Start/StopSequentialNavigation, TriggerAutomation, ToggleAppSwitcher, Home, Notifications, Assistant, Volume, Dictation, ToggleAccessibilityFeature, QuickSettings, Escape, Scroll Up/Down/Left/Right |
| ID 3 Pointer | Input | Generic Desktop 0x01 Pointer; X/Y/Z | Three SInt8 values, −127…127. **−128 (0x80) marks the axis as absent** | Valid axes set the mode per report: 1D = Switch Control gliding cursor; 2D = pointer equivalent to head tracking; 3D = visionOS spatial point picker. Relative (default) or absolute, chosen by the descriptor's Input flag (0x06 vs 0x02). The 3D pointer is always relative |
| ID 4 Item selection | Input | 0x60 / 0x04 | `itemIndex` 0–255 | Sends Switch Control focus or activation straight to an item |
| ID 4 Scan information | Output (host→device) | 0x60 / 0x03 | 6 bytes: selectedItem, numberOfItems, seed (scan-cycle ID), itemControlType (0 discrete / 1 continuous), uiScanningLatencyInt, uiScanningLatencyFrac (/255) | Gives the decoder the scanning context. **Privacy note in the spec: the host does not send focused-item information when the item is a keyboard key (for example a software keyboard).** |

The sample code uses the IOKit calls `IOHIDUserDeviceHandleReportWithTimeStamp` and
`IOHIDUserDeviceRegisterInputReportCallback` with `mach_absolute_time()` timestamps. The spec says
firmware stacks differ and the examples should be adapted. [V] Our reading is that the samples are
illustrative, for example for prototyping a virtual device, and do not mean a Mac host is supported. [INF]

### 1.3 Is usage page 0x60 a USB-IF standard? No, it is not in HUT 1.7

- The USB-IF **HID Usage Tables 1.7 (26 January 2026)** list 0x5A–0x7F as **Reserved**. There is no BCI or
  "Brain Control Interface" page. [V] https://usb.org/sites/default/files/hut1_7.pdf
- The approved review-request list runs to HUTRR119 (Contextual Assistance, Google, approved 6-0 in March 2026).
  It contains no BCI request. [V] https://usb.org/approved-usage-table-review-requests
- **Implication.** Apple's BCI HID uses a page that the USB-IF has not allocated. It is a de facto Apple profile,
  not a cross-vendor standard. Windows and Linux hosts do not recognise it (section 1.6). A future HUTRR could change
  this. [INF]

### 1.4 What a third-party app (or the NeuroMetric web battery) can observe

- **Raw BCI reports.** Apple documents no app-facing API that exposes BCI HID reports, signal quality or decoder
  state to third-party apps. The reports are consumed by the system's assistive technology. [INF from the absence
  of any app API in the Accessibility framework docs. Status: UNR, so do not assume access.]
- **What an app does see.** An app sees the *result*: Switch Control or AssistiveTouch focus movement, activations
  and scrolling, delivered through the normal UIKit/SwiftUI or WebKit event and accessibility paths. A
  BCI-driven selection therefore reaches a web page as an ordinary activation (for example a `click` or focus change).
  The page cannot reliably tell it apart from a hardware switch. [INF]
- **Status flags.** Apps can read `UIAccessibility.isSwitchControlRunning` and subscribe to
  `switchControlStatusDidChangeNotification`. [V]
  https://developer.apple.com/documentation/uikit/uiaccessibility/isswitchcontrolrunning
  There is **no** documented flag for "BCI connected". [INF/UNR]
  `isAssistiveTouchRunning` documentation adds: "The user must enable Guided Access for the correct value to
  return." [V] https://developer.apple.com/documentation/uikit/uiaccessibility/isassistivetouchrunning
- **Recommendation.** NeuroMetric records the BCI as a **participant/site-declared input modality**, plus
  the observable assistive-technology state where a native wrapper exists. NeuroMetric does not try to infer
  BCI use from timing. A BCI selection time includes Switch Control scan intervals and decoder latency,
  neither of which the app can see. [INF]

### 1.5 Synchron's claims

- 13/14 May 2025 press release: Synchron "will be the first BCI company to achieve native integration with a
  new BCI Human Interface Device (BCI HID) profile announced by Apple on May 13". It says users "can control
  iPhone, iPad and Apple Vision Pro directly with their thoughts", that the system "will seamlessly integrate
  with Apple's built-in accessibility features, including Switch Control", and that "Controlled rollouts with
  trial participants using BCI HID-compatible features are expected to begin later this year." [CC]
  https://www.biospace.com/press-releases/synchron-to-achieve-first-native-brain-computer-interface-integration-with-iphone-ipad-and-apple-vision-pro
  (BusinessWire original returned 403 to our fetcher.)
- 4 August 2025 press release, "Synchron Debuts First Thought-Controlled iPad Experience Using Apple's New BCI
  Human Interface Device Protocol". Synchron lists it on its news page. [V that the release exists]
  https://synchron.com/news
  Secondary reports of its content say the user was a COMMAND study participant with ALS, used Switch Control,
  and that the protocol lets the device share "contextual screen data" with the decoder. [CC via secondary,
  not re-fetched; BusinessWire 403]
- Synchron's devices remain investigational. Synchron reported its COMMAND early feasibility study results in
  September 2024 (news page lists "Positive Results from U.S. COMMAND Study"). [CC] https://synchron.com/news
  The specific regulatory status of any BCI HID rollout was not re-verified. [UNR]

### 1.6 Windows / Linux equivalents

- **Windows.** The in-box HID top-level collections are: mouse (0x01/0x02) and keyboard (0x01/0x06–07), opened
  *exclusively* by the Raw Input Manager; game controllers (0x01/0x04–05) shared; consumer controls; digitizers
  (pen/touch/PTP) exclusive; sensors; UPS battery; barcode scanner. There is **no BCI page, and no eye-tracker
  page (0x12) entry**, in that table. [V] https://learn.microsoft.com/en-us/windows-hardware/drivers/hid/hid-architecture
  A BCI therefore reaches Windows as a standard mouse, keyboard or gamepad, or through a vendor driver or app.
  Windows Eye Control and gaze APIs are covered in section 3. [INF]
- **Linux.** The kernel's `include/linux/hid.h` defines usage-page constants for Generic Desktop, Button,
  Keyboard, Consumer, Digitizer, Haptic, Sensor and others. There is **no constant for 0x12 (eye/head trackers)
  or 0x60**. [V] https://raw.githubusercontent.com/torvalds/linux/master/include/linux/hid.h
  Pointer and button collections inside an Apple-style descriptor would likely be mapped by `hid-input`. The
  0x60 reports would reach user space only through hidraw. [INF, not tested]
- **Net.** Apple is the only platform vendor with a published BCI-specific HID profile. Everywhere else, BCI
  vendors emulate mouse, keyboard or switch input or ship their own software. [INF]

### 1.7 Meta Neural Band (sEMG wristband), input model for developers

- Meta's display-glasses developer blog (14 May 2026) says Web Apps get "access to motion and orientation data,
  phone GPS, input from the Meta Neural Band and local storage". The Device Access Toolkit (iOS/Android SDK) was
  then in developer preview. [CC] https://developers.meta.com/blog/build-for-display-glasses/
- Web Apps build guide: directional navigation and activation from the touchpad or band are delivered "as
  standard arrow key" events (`ArrowUp/Down/Left/Right`, `Enter`). "Continuous arm movement provides positional
  input delivered as pointer events". Drag is off by default and is enabled with `touch-action: none` on `<body>`.
  The display is a fixed 600×600 viewport. "No mouse, touchscreen, or physical keyboard is available".
  `requestPointerLock()` is not supported. [V]
  https://wearables.developer.meta.com/docs/develop/webapps/build/
- Meta Connect recap (24 Sep 2026): Device Access Toolkit 1.0 is described as stable; web apps can "tune into ...
  wrist motion from Meta Neural Band". [CC] https://developers.meta.com/blog/meta-connect-recap-ai-glasses/
- **No documentation found of raw EMG or neuromotor signal access for third parties.** [UNR] Gestures are
  abstracted to key and pointer events. [V, build guide]
- **Recommendation.** If the battery handles arrow keys, Enter and focus correctly, it already works with the
  Neural Band through Web Apps. Store `input_modality = "emg_wristband_keys"` as a declared modality. Treat
  timing as keyboard-class with unknown gesture-recognition latency. [INF]

---

## 2. USB-IF HID usages relevant to NeuroMetric (HUT 1.7, 2026-01-26) [V]

Source: https://usb.org/sites/default/files/hut1_7.pdf

| Page | Relevant usages | Why it matters |
|---|---|---|
| 0x01 Generic Desktop | Pointer, Mouse, Joystick, Gamepad, X/Y/Z axes; **Assistive Control (CA, usage 0x10)**, defined as "A manual control or cursor device. An assistive control device may consist of buttons or a pointing input control to communicate" (HUTRR68, corrected by HUTRR81, 2017); **System Accessibility Binding (0xAA, OOC, HUTRR116, 2024)**, which toggles a user-bound system accessibility UI or feature | A switch or joystick device *may* identify as an Assistive Control. Host support is not guaranteed ("creation of a new Usage does not imply support ... by any USB HID Host vendor", per the RR list page) |
| 0x09 Button | Buttons 1..n | Used by Apple BCI HID report 2 and by most switch interfaces in gamepad mode |
| 0x0D Digitizers | Touchscreen, pen, touchpad | Touch and stylus input |
| **0x12 Eye and Head Trackers** | Eye Tracker, Head Tracker, Gaze Point, Head Direction Point, Sensor Timestamp (64-bit), Tracker Quality, Sampling Frequency, etc. Units default to micrometres and radians | **Normative privacy note in HUT:** "the usages in this page should only be used for interactive use cases. This means that a host that implements this interface must not transfer gaze point data to any other device, nor store gaze point data for later transfer to any other device. This applies both to raw gaze point data, as well as any aggregate of this." → NeuroMetric must **not** store gaze points, or aggregates of them, obtained through a HID eye-tracker interface |
| 0x41 Braille Display | — | Apple publishes a companion Braille HID reference |
| 0x5A–0x7F | Reserved | Apple's BCI page 0x60 sits in this reserved range |

Review requests still in progress: HUTRR118 (Haptics Expansion) and HUTRR119 (Contextual Assistance). Neither
relates to BCI. [V] https://usb.org/hid

---

## 3. Eye gaze, head pointer, switch, sip-and-puff and joystick integration options

| Option | How it reaches the battery | Data / licensing constraints | NeuroMetric stance | Label |
|---|---|---|---|---|
| **Windows Eye Control** (supported trackers include Tobii Eye Tracker 4C, EyeX, Tobii Dynavox PCEye Plus, EyeMobile Mini/Plus, per Microsoft) | Drives the Windows mouse/launchpad, so the browser sees pointer and click events | Microsoft support page "Get started with eye control in Windows" | Supported as **pointer modality "eye_gaze_os"**. Raw gaze is never accessed | [V] https://support.microsoft.com/en-us/windows/get-started-with-eye-control-in-windows-1a170a20-1083-2452-8f42-17a7d4fe89a9 |
| **Windows gaze APIs** (`Windows.Devices.Input.Preview`, GazeInputSourcePreview) | Native app only | Apps must declare the **`gazeInput` capability**. Windows then shows a consent dialog at first run. "If your app collects, stores, or transfers eye tracking data, you must describe this in your app's privacy statement" | Do not use for telemetry. Optionally use in a native lab tool to compute on-device dwell metrics, with no gaze storage (see HUT note) | [V] https://learn.microsoft.com/en-us/windows/apps/design/input/gaze-interactions |
| **Tobii Pro SDK** | Native/Python/.NET research SDK | Tobii's "Allowed usage" table: Interactive Use "possible but not optimized"; **Analytical Use "Freely on Tobii Pro eye trackers. Also possible on consumer devices with Tobii eye tracking, in combination with a special license key"**; **Medical Use "Only with special license"**; High-risk Use "Only with special license" | Any NeuroMetric analysis of stored gaze needs Tobii Pro hardware or a special licence. **Clinical/medical use needs a special licence**, so contact Tobii before any regulated deployment | [V] https://developer.tobii.com/tobii-pro-sdk/ |
| Tobii licensing model | — | Three licence types (Getting Started, Commercial, Research). Tobii's **Eye Tracking Data Transparency Policy** "applies to solutions that store or transfer Tobii eye tracking data, presence or position data, regardless of the purpose" | Comply with the transparency policy if any Tobii data is stored | [V] https://developer.tobii.com/pc-gaming/ ; https://developer.tobii.com/license-agreement/ |
| Tobii Game Integration / consumer SDK | Gaming SDK | Long understood to restrict storing or analysing gaze data from consumer trackers ("interactive use only"); terms page not machine-readable this session | Do not use for analytics | [PK, not re-verified] |
| **iPadOS/iOS Eye Tracking** (iOS/iPadOS 18) | Front camera with on-device ML. Dwell Control activates elements, so the page sees activations | Apple: "all data used to set up and control this feature is kept securely on device, and isn't shared with Apple". No app access to gaze | Supported as **"eye_gaze_os"**, declared modality. iOS/iPadOS 26 adds the option to use a switch or dwell to select | [V] https://www.apple.com/newsroom/2024/05/apple-announces-new-accessibility-features-including-eye-tracking/ ; [V] 2025 newsroom URL in §1.1 |
| **Head Tracking (iOS/iPadOS 26)** and macOS Head Pointer | System pointer driven by head movement | Head Tracking on iPhone/iPad was announced May 2025 [V, 2025 newsroom]. macOS Head Pointer is a camera-based system feature [PK] | Declared modality **"head_pointer_os"** | [V]/[PK] |
| **WebGazer.js** | In-page webcam gaze estimation | Runs client-side ("no video data needs to be sent to a server"). GPLv3, or LGPLv3 for companies valued under $1M [V] https://github.com/brownhci/WebGazer . A 2026 controlled evaluation found mean angular error of about **10.3–13.6°** (mean spatial error about 1009–1383 device px) depending on calibration density [RF] Psarra, Krassanakis & Kesidis 2026, J Eye Mov Res, doi:10.3390/jemr19050099 | **Not suitable as an outcome measure or as the primary input** for motor-impaired users. It could only serve as an exploratory, consented, on-device signal, and storing gaze still needs specific consent and DPIA | [V]/[RF] |
| Camera Mouse, Enable Viacam (free webcam head mice), NaturalPoint SmartNav (IR head mouse) | Emulate the OS mouse, so the page sees pointer events | — | Declared modality **"head_pointer_sw"**. SmartNav product availability not checked [UNR] | [PK] |
| **USB/Bluetooth switch interfaces** (for example AbleNet Hitch, Blue2) | Emulate keyboard keys (Space/Enter/arrows or configurable) or mouse clicks, or act as iOS Switch Control switches | Typical mappings are vendor-configurable | Battery must support 1- and 2-switch operation through key events and an in-app scanning mode with adjustable scan rate (WCAG 2.2.1) | [PK, vendor pages not re-fetched] |
| **Sip-and-puff** | Usually through a switch interface (key/click) or a joystick/mouse emulator | — | Treat as switch or pointer by its emulation class | [PK] |
| **Joystick / gamepad / adapted controllers** | Gamepad API (browser) or mouse emulation | Gamepad API hides pads until a "gamepad user gesture" (fingerprinting mitigation) | Support Gamepad API polled in rAF, with `Gamepad.timestamp` stored | [V] https://w3c.github.io/gamepad/ |
| **Apple BCI HID** | Switch Control / AssistiveTouch actions | §1 | Declared modality **"bci_switch_control"** | [V] |
| **Meta Neural Band** | Arrow/Enter keys plus pointer events in Meta Web Apps | §1.7 | Declared modality **"emg_wristband_keys"** | [V] |

---

## 4. Accessibility standards most relevant to motor-impaired users

### 4.1 WCAG 2.2 (W3C Recommendation, 12 December 2024) [V] https://www.w3.org/TR/WCAG22/

| SC | Level | Requirement (abridged from the Rec) | Battery implication |
|---|---|---|---|
| 2.1.1 Keyboard | A | All functionality operable through a keyboard interface "without requiring specific timings for individual keystrokes", except path-dependent input | All tasks must be fully operable by keys/switches. **Timed RT tasks are in tension with this.** Treat the timing as the *measured construct*, document the exception, and always offer an untimed operability path for navigation, consent and settings |
| 2.1.4 Character Key Shortcuts | A | Single-character shortcuts can be turned off or remapped | Switch interfaces often send letters, so make response keys remappable |
| 2.2.1 Timing Adjustable | A | Turn off, adjust (≥10× default), or extend (warn, ≥20 s, at least 10×). Exceptions: real-time, **Essential ("extending it would invalidate the activity")**, >20 h | Response windows in speeded tasks may claim the **Essential** exception. Instruction screens, consent, breaks and scan rates **must** be adjustable. Store the per-participant setting |
| 2.2.2 Pause, Stop, Hide | A | Moving or auto-updating content can be paused | Scanning highlights and animations need pause control outside measured trials |
| 2.4.7 Focus Visible | AA | Keyboard focus indicator visible | Essential for switch scanning and Neural Band arrow navigation |
| 2.4.11 Focus Not Obscured (Minimum) | AA (new in 2.2) | Focused component not entirely hidden by author content | No sticky overlays covering scanned targets |
| 2.4.13 Focus Appearance | AAA (new) | Indicator ≥ 2 CSS px perimeter area, 3:1 contrast | Recommend meeting it anyway for low-vision and switch users |
| 2.5.1 Pointer Gestures | A | Multipoint or path gestures have a single-pointer alternative | No pinch or swipe-only tasks |
| 2.5.2 Pointer Cancellation | A | No down-event execution, or abort/undo/up-reversal | **Conflict for RT tasks that score on pointerdown.** Score on pointerdown only within measured trials and document as essential. Use up-event activation everywhere else |
| 2.5.4 Motion Actuation | A | Motion-operated functions have UI alternatives and can be disabled | Relevant to device-motion tasks and Neural Band "wrist motion" |
| 2.5.7 Dragging Movements | AA (new) | Dragging has a single-pointer non-drag alternative | Tracing or drag tasks need a click-to-place alternative, or a documented essential exception |
| 2.5.8 Target Size (Minimum) | AA (new) | ≥ 24×24 CSS px, or spacing / equivalent / inline / UA / essential exceptions | Battery default should be **≥ 44×44 CSS px (2.5.5 AAA)** for motor-impaired users. Store the effective target size per trial |
| 3.3.8 Accessible Authentication (Minimum) | AA (new) | No cognitive function test for login without alternative or assistance | Participant login must allow paste and password managers, or passkeys or magic links |

### 4.2 Section 508 (US)

"The Revised 508 Standards incorporate by reference the WCAG 2.0 Level AA Success Criteria, and apply
[them] ... to both web and non-web electronic content." [V]
https://www.section508.gov/develop/applicability-conformance/
WCAG 2.2 AA is a superset in practice. Meeting 2.2 AA covers 508's web criteria. [INF] (2.2 removed 4.1.1 Parsing,
so it is not a strict superset. Keep valid markup anyway. [PK])

### 4.3 EN 301 549 (EU)

- **EN 301 549 V4.1.1 (2026-09)** is published on ETSI's deliver server. Its foreword says clauses 9 (web),
  10 (non-web documents) and 11 (software) "have all been updated to align with the WCAG 2.2 recommendation". It
  was prepared under standardisation request C(2022) 6456 as one voluntary means of conforming to the
  **European Accessibility Act (Directive (EU) 2019/882)**, with Annex ZB. Presumption of conformity applies
  "once the present document is cited in the Official Journal". [V]
  https://www.etsi.org/deliver/etsi_en/301500_301599/301549/04.01.01_60/en_301549v040101p.pdf
- OJEU citation status of V4.1.1 was not checked this session. [UNR] V3.2.1 (2021) is the prior version. [V, same
  directory listing]
- Clause 11 (software) matters if NeuroMetric ships native wrappers or a telemetry agent. [INF]

### 4.4 WAI-ARIA patterns to use

Use the APG patterns for **listbox, radiogroup, grid (roving tabindex), dialog (focus trap and restore), slider
(with keyboard increments), and button**. Announce trial-state changes through a polite live region, never
during a measured response window, because screen-reader speech competes with timing. [PK, APG not
re-fetched: https://www.w3.org/WAI/ARIA/apg/]
Never use `aria-hidden` on focusable elements. Ensure the in-app scanning mode follows DOM focus order. [PK]

---

## 5. BCI terminology and data standards

| Item | Status as known | Label |
|---|---|---|
| **IEEE P2731**, *Standard for a Unified Terminology for Brain-Computer Interfaces* (IEEE SA BCI working group) | Active project. Status/approval date **not re-verified**: the IEEE SA pages returned 403 or unrelated content, and the search quota was exhausted | [PK, not re-verified] |
| **IEEE P2794**, *Reporting Standard for in vivo Neural Interface Research* (RSNIR) | Active project. Status **not re-verified** | [PK, not re-verified] |
| IEEE SA Industry Connections "Neurotechnologies for Brain-Machine Interfacing" roadmap (2020) | Published roadmap report | [PK] |
| BIDS extensions for EEG/iEEG (BIDS-EEG, BIDS-iEEG) | Community data standard for neural recordings | [PK] |
| Apple BCI HID | De facto vendor profile, not USB-IF standardised (§1.3) | [V] |
| USB-IF HUT Eye and Head Trackers page 0x12 | Standardised; normative-style privacy restriction on storing gaze | [V] |

**Recommendation.** NeuroMetric's BCI-session metadata should follow P2731 terminology once published.
Until then, store free-text device class plus a controlled vocabulary of
`{implanted_endovascular, implanted_cortical, noninvasive_eeg, emg_wristband, other}`, and map it when the
standard is final. [INF]
