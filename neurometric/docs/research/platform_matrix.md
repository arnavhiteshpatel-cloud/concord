# Platform matrix: input, accessibility and consented-telemetry APIs

Prepared 2026-11-27. Evidence labels follow `CONVENTIONS.md`. The row-level data, including per-row URLs, is in
`platform_matrix.csv` (36 rows; columns: platform, api, purpose, data_available, permission_required,
background_allowed, sandbox_limits, store_policy_limits, clinical_deployment_notes,
neurometric_recommendation, evidence_label, urls, accessed). This file holds the reasoning and the verdicts.
Companion files: `bci_hid_and_input_standards.md` and `browser_timing.md`.

**Scope rules applied throughout (NeuroMetric telemetry charter):** explicit opt-in; collect session durations,
interaction counts, modality and AT flags only. **Never** keystroke content, screenshots, passwords, messages,
browsing history or screen content. No covert monitoring. No bypassing OS permissions. On this basis, any API
whose capability includes reading key codes or screen content is marked **AVOID**, even where the OS would allow it
without a prompt.

Search-budget note: the shared web-search quota ran out during this work. Rows marked [PK] were not
re-verified against a primary source this session.

---

## 1. Feasibility verdicts for consented real-world usage telemetry

| Platform | Verdict | Feasible signal set | Why / blocking constraint |
|---|---|---|---|
| **Browser (battery itself)** | **YES, recommended baseline** | In-battery session duration, interaction counts per modality, AT settings, timing diagnostics | No OS permission needed, only study consent. Cannot see anything outside the battery page, which is a feature. [V] Pointer Events, HR-Time, Gamepad specs |
| **Windows** | **Technically yes; ethically constrained** | Active time (`GetLastInputInfo`, which carries no content) + per-device-class event counts (Raw Input with `RIDEV_INPUTSINK`; device usage page only) + AT presence | Raw Input and low-level hooks need **no OS consent prompt** [V]. NeuroMetric must therefore supply consent, a visible indicator and a kill switch itself. Avoid `WH_KEYBOARD_LL` and reading keyboard codes. Store policy 10.5.x needs a privacy policy, opt-in consent with revocation, modern crypto, and express consent for health data [V] |
| **macOS** | **Partial** | Idle/active time [PK API], HID device presence by usage page (IOHIDManager) [PK], optional mouse/scroll counts via `NSEvent` global monitor (key events require Accessibility trust [V]) | Global monitoring needs a user TCC grant (Accessibility / Input Monitoring) [V/PK]. Mac App Store requires App Sandbox [V], which in practice excludes global monitoring [PK]. Route: Developer ID + notarised agent or site MDM. PPPC cannot be used to bypass consent [PK] |
| **Linux** | **No for cross-app (Wayland); not recommended on X11** | In-battery only; X11 idle time at most | Wayland clients cannot observe global input by design. libinput runs in the compositor, not in apps [V]. The InputCapture portal *diverts* input to the app and is for input sharing, not monitoring [V]. evdev needs root or the input group and exposes key codes [V], so it is unacceptable on participant devices |
| **Android** | **Yes, limited** | Device/app foreground time via `UsageStatsManager` (user grants Usage Access in Settings) [V]; enabled-AT booleans via `AccessibilityManager` [V]; in-app events | **Do not use AccessibilityService for telemetry.** Play policy: only apps "designed to help people with disabilities" may declare `isAccessibilityTool`; "monitoring apps" are explicitly not tools; others need an in-app prominent disclosure + consent and the Permission Declaration Form (API 31+, since 2021-11-03) [V]. Sideloaded apps hit "restricted settings" for accessibility (Android 13+) [V help page]. Minimise per-app package names |
| **iOS / iPadOS** | **No cross-app; in-app only** | In-battery/native-wrapper events; `UIAccessibility` AT booleans (Switch Control, VoiceOver, AssistiveTouch*) [V] | Sandbox. Screen Time (`DeviceActivity`) report extensions run in a sandbox that "prevents your extension from making network requests or moving sensitive content outside the extension's address space" [V], so usage cannot be exported. FamilyControls entitlement needs Apple approval for distribution [V]. App Review 2.5.14 requires explicit consent plus a visible indicator when recording user activity; 5.1.3 requires consent and independent ethics review for health research [V] |
| **ChromeOS** | **Yes, on managed devices** | Active/idle/locked via `chrome.idle` in a consented, force-installed extension [V API; PK force-install] | Admin console "Recent activity" (last used, how long, 30 days) exists [V], but admin visibility is not participant consent. Use only with explicit consent |
| **Meta Ray-Ban Display + Neural Band** | **Battery subset only (exploratory)** | Arrow/Enter key events and pointer events in Web Apps [V] | No raw EMG documented [UNR]. 600×600 viewport. Developer-preview distribution [CC] |
| **BCI / AT device sponsors** | **Preferred for BCI usage** | Device-side session and selection counts, signal-quality summaries | Apple exposes no BCI telemetry to apps [INF]. Sponsors already log usage under clinical protocols. A data-use-agreement export is cheaper and lower-risk than any OS monitor [INF] |

\* `isAssistiveTouchRunning` returns a correct value only with Guided Access enabled, per Apple's doc. [V]

**Overall recommendation [INF].** Build telemetry in three tiers:
1. **Tier 0 (all platforms):** in-battery telemetry. This is the default and is always on under study consent.
2. **Tier 1 (opt-in agent):** a minimal *activity* agent on Windows, Android (UsageStats + AT flags) and
   ChromeOS (`chrome.idle`). It records active time, device-assisted-session flags and per-device-class counts,
   never key values. Each agent has an in-app consent screen, a persistent indicator, pause/withdraw controls,
   and on-device aggregation to daily totals.
3. **Tier 2 (sponsor export):** for BCI and dedicated AT devices, a sponsor/manufacturer aggregate export under a
   DUA, joined on pseudonymous study ID.

Do **not** build macOS key-capable monitors, Linux evdev readers, Android AccessibilityService monitors or iOS
Screen Time workarounds.

---

## 2. Per-platform API notes (summary of the CSV)

### Browser
- **Pointer Events.** `getCoalescedEvents()` is `[SecureContext]`. Coalesced samples have monotonically increasing,
  sorted `timeStamp`s. `pointerrawupdate` fires only in secure contexts and is not Baseline. [V]
  https://w3c.github.io/pointerevents/
- **HR-Time.** Coarsening to ≥100 µs, or ≥5 µs when cross-origin isolated, with optional jitter. [V]
  https://w3c.github.io/hr-time/
  Actual figures: Chrome 0.1 ms, Safari and Firefox 1 ms, in non-isolated contexts. [V] MDN.
- **Gamepad.** Pads are hidden until a gamepad user gesture. `Gamepad.timestamp` is updated on new data. [V]
- **WebHID.** Now a WHATWG Living Standard (updated 14 Nov 2026). Needs transient activation, has a blocklist,
  and is Chromium-only in practice. Not needed for the battery. [V] https://hid.spec.whatwg.org/
- Full timing analysis: `browser_timing.md`.

### macOS
- `NSEvent.addGlobalMonitorForEvents` can only observe. "Key-related events may only be monitored if accessibility
  is enabled or if your application is trusted for accessibility access". [V]
- `CGEvent.tapCreate`: a HID-level tap is root-only. Key events need root or accessibility enabled. Events the tap
  may not see are cleared from the mask. [V] Its permission pair is `CGPreflightListenEventAccess` /
  `CGRequestListenEventAccess`; the pages exist, but their discussion is empty. [V] The "Input Monitoring" TCC
  naming is [PK].
- App Sandbox is mandatory for the Mac App Store. [V]
- MDM PPPC payload `com.apple.TCC.configuration-profile-policy` needs user-approved MDM. [V] The rule that
  ListenEvent can be denied but not granted by profile is [PK].

### Windows
- Raw Input accepts "raw input from any HID". Background reception with `RIDEV_INPUTSINK`. [V]
- `LowLevelMouseProc`: timeout capped at 1000 ms (Windows 10 1709+). The hook is "silently removed" if slow.
  Microsoft: "In most cases where the application needs to use low level hooks, it should monitor raw input
  instead." [V]
- `GetLastInputInfo` is session-specific, and its tick is not guaranteed to be incremental. [V]
- Gaze APIs need the `gazeInput` capability and trigger a Windows consent dialog. Storing eye data must be
  disclosed. [V]
- Microsoft Store Policies v7.20 (effective 2026-10-22). 10.5.1 privacy policy; 10.5.2 opt-in consent with a
  revocation mechanism; 10.5.4 modern cryptography; 10.5.5 highly sensitive data (health) only when related to
  functionality and with express consent. [V] https://learn.microsoft.com/en-us/windows/apps/publish/store-policies
- Clinical deployment: a signed MSI/MSIX via site IT (Intune etc.) is more realistic than the Store. [INF]

### Linux
- evdev gives timestamped kernel events and is "the preferred interface for userspace". Device nodes are
  root-owned. [V] https://www.kernel.org/doc/html/latest/input/input.html
- "libinput is not used directly by Wayland applications, it is an input stack used by the compositor." [V]
- InputCapture portal v2: `Start()` "typically presents a dialog to the user". Events are sent to the app
  "instead of being used to update the pointer position on-screen". [V]
- X11 global observation (XInput2/XRecord) needs no permission. [PK] Wayland is the default on major distros.
  [PK]

### Android
- `UsageStatsManager` needs `PACKAGE_USAGE_STATS` "and the user of the device still needs to grant permission
  through the Settings application". `queryEventsForSelf` needs no permission. [V]
- `AccessibilityServiceInfo` flags expose window content, key filtering and screenshots. [V] These capabilities
  are why the charter forbids this route.
- Background execution: foreground-service type requirements (Android 14+) apply to any continuous agent. Prefer
  periodic UsageStats queries (WorkManager) to a continuous service. [PK]

### iOS / iPadOS / visionOS
- `UIEvent.timestamp` is seconds since system startup. [V]
- Switch Control status API and notification. [V] No BCI, eye-tracking or head-tracking status API was found. [INF]
- DeviceActivity, FamilyControls and ManagedSettings: export is blocked (see verdicts). [V]
- App Review Guidelines (last updated 16 Oct 2026): 2.5.4 background services only for intended purposes; 2.5.14
  consent plus indication for recording user activity; 5.1.2 data use and sharing; 5.1.3 (iii) research consent
  elements; 5.1.3 (iv) independent ethics review board approval. [V]
  https://developer.apple.com/app-store/review/guidelines/
- Apple BCI HID: see `bci_hid_and_input_standards.md` §1.

### ChromeOS
- `chrome.idle.queryState(detectionIntervalInSeconds)` returns "active", "idle" or "locked".
  `getAutoLockDelay()` is ChromeOS-only. Needs the "idle" permission. [V]
- The Admin console device page shows "Recent activity", when last used and for how long, for 30 days, if
  reporting is turned on. [V] https://support.google.com/chrome/a/answer/6179663

---

## 3. Clinical deployment notes (cross-platform) [INF unless labelled]

- **Regulatory framing.** Pure usage telemetry (durations and counts) used as an exploratory or real-world
  endpoint still enters the clinical data flow. Document it in the protocol, informed consent, DPIA, and
  21 CFR Part 11 / GCP data-integrity controls (audit trail, time sync). Labelling NeuroMetric software as a
  medical device is out of scope here. [INF]
- **App stores vs sites.** For trials, prefer **site-provisioned devices** (MDM-managed iPads in Guided Access,
  managed Chromebooks, Intune-managed Windows) running the browser battery. Public-store native apps add
  review risk: Apple 5.1.3 ethics proof and Play AccessibilityService declaration. [V for policies; INF for
  recommendation]
- **Sponsor export is usually more practical** for BCI and AT usage. Synchron-type investigational systems
  already run under clinical protocols. [CC] (Synchron COMMAND) https://synchron.com/news
  Ask sponsors for daily aggregates of: decoder-on time, selections, signal-quality summaries, and AT mode
  (Switch Control / pointer), keyed by pseudonymous study ID. [INF]
- **Gaze data.** HUT 0x12 says hosts "must not ... store gaze point data", including aggregates, for HID eye
  trackers. [V] The Tobii Pro SDK needs special licences for medical use, and for analytical use on consumer
  trackers. [V] Therefore: no gaze storage in Tiers 0–1.
