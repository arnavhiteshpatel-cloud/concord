# Platform usage probes (UNTESTED SOURCE — contracts only)

These files implement `neurometric.adapters.probes.contract.UsageProbe` on each platform, as
specified in docs/research/platform_matrix.md. **None has been compiled or run on a real device
in this session** (no Windows/macOS/Android hardware; BLOCKERS X-7). They are starting points for
the Exp U9/B8 platform spike, to be reviewed for privacy before any participant use.

Shared rules (every probe):
* Collect only: OS idle state (active within threshold), counts of input reports per coarse
  device class, whether the study device produced input. Never key codes, characters, pointer
  coordinates, window titles, app names (except coarse categories with a separate consent),
  URLs, screenshots or audio.
* Visible indicator whenever sampling; pause/stop controls; no background start without consent.
* Aggregates leave the device as `nm.telemetry/1` payloads (see src/neurometric/study/telemetry.py);
  the participant can review every payload before it is sent.

| Platform | Mechanism | Permission | Status |
|---|---|---|---|
| Windows | `GetLastInputInfo` idle + Raw Input `WM_INPUT` per-device-class counts (`RIDEV_INPUTSINK`), no key codes read | none at OS level → NeuroMetric's own consent + tray indicator | source sketch |
| macOS | `CGEventSource.secondsSinceLastEventType` (idle, no permission) + IOHIDManager device presence | none for idle; Input Monitoring would be needed for counts → not used | source sketch |
| Android | `UsageStatsManager.queryEvents` aggregated to minutes per coarse category + `AccessibilityManager` enabled-services list (no AccessibilityService) | Usage access (user grants in Settings) | source sketch |
| iOS/iPadOS | in-app only (Screen Time extensions cannot export) → use the browser battery + sponsor export | — | not implemented by design |
| Linux (Wayland) | not feasible (no global input observation by design) | — | not implemented |
| ChromeOS | `chrome.idle` in a managed, force-installed extension | admin policy | not implemented |
