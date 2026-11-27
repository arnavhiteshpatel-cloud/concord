// NeuroMetric Android usage probe — UNTESTED SKETCH (see ../README.md).
// Uses UsageStatsManager (user grants "Usage access" in Settings). No AccessibilityService.
package org.neurometric.probe

import android.app.usage.UsageEvents
import android.app.usage.UsageStatsManager
import android.content.Context
import android.view.accessibility.AccessibilityManager

class UsageProbe(private val ctx: Context, private val categoryOf: (String) -> String) {
    var paused = false
    var consentActive = false

    /** Minutes in the foreground per COARSE category (requires the separate app-category consent). */
    fun categoryMinutes(startMs: Long, endMs: Long): Map<String, Double> {
        if (paused || !consentActive) return emptyMap()
        val usm = ctx.getSystemService(Context.USAGE_STATS_SERVICE) as UsageStatsManager
        val ev = usm.queryEvents(startMs, endMs); val e = UsageEvents.Event()
        val open = HashMap<String, Long>(); val out = HashMap<String, Double>()
        while (ev.hasNextEvent()) { ev.getNextEvent(e)
            when (e.eventType) {
                UsageEvents.Event.ACTIVITY_RESUMED -> open[e.packageName] = e.timeStamp
                UsageEvents.Event.ACTIVITY_PAUSED -> open.remove(e.packageName)?.let {
                    val cat = categoryOf(e.packageName)        // package name never leaves the device
                    out[cat] = (out[cat] ?: 0.0) + (e.timeStamp - it) / 60000.0 }
            } }
        return out
    }

    /** Which assistive tools are enabled (names mapped to a fixed list on-device). */
    fun assistiveToolsEnabled(): Boolean {
        val am = ctx.getSystemService(Context.ACCESSIBILITY_SERVICE) as AccessibilityManager
        return am.isEnabled
    }
}
