// NeuroMetric macOS usage probe — UNTESTED SKETCH (see ../README.md).
// Uses the system idle timer only (no Accessibility / Input Monitoring permission requested).
import Foundation
import CoreGraphics

final class UsageProbe {
    let idleThreshold: TimeInterval = 60
    var paused = false
    var consentActive = false

    func isActive() -> Bool {
        let anyInput = CGEventType(rawValue: ~0)!
        let idle = CGEventSource.secondsSinceLastEventType(.combinedSessionState, eventType: anyInput)
        return idle < idleThreshold
    }

    /// Device presence only (e.g. a switch interface or eye tracker is connected), via IOHIDManager
    /// matching on vendor/product IDs configured by the study — no report contents are read.
    func studyDeviceConnected(vendorID: Int, productID: Int) -> Bool {
        // IOHIDManagerCreate + IOHIDManagerSetDeviceMatching + IOHIDManagerCopyDevices (omitted)
        return false
    }
}
