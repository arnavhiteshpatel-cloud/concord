// NeuroMetric Windows usage probe — UNTESTED SKETCH (see ../README.md). Counts only; never key codes.
using System; using System.Runtime.InteropServices; using System.Collections.Generic;

public sealed class UsageProbe {
    [StructLayout(LayoutKind.Sequential)] struct LASTINPUTINFO { public uint cbSize; public uint dwTime; }
    [DllImport("user32.dll")] static extern bool GetLastInputInfo(ref LASTINPUTINFO plii);
    public const int IdleThresholdMs = 60_000;
    readonly Dictionary<string,int> counts = new() { ["pointer"]=0, ["select"]=0, ["scroll"]=0, ["switch_activations"]=0 };
    public bool Paused { get; set; }
    public bool ConsentActive { get; set; }

    public bool IsActive() {
        var info = new LASTINPUTINFO { cbSize = (uint)Marshal.SizeOf<LASTINPUTINFO>() };
        GetLastInputInfo(ref info);
        return unchecked((uint)Environment.TickCount - info.dwTime) < IdleThresholdMs;
    }

    // Called from the WM_INPUT handler (RegisterRawInputDevices with RIDEV_INPUTSINK for usage pages
    // 0x01/0x02 mouse and 0x01/0x06 keyboard). Only the device CLASS and button-state flags are read.
    public void OnRawInput(string deviceClass, bool buttonDown, bool wheel) {
        if (Paused || !ConsentActive) return;
        if (deviceClass == "mouse") { counts["pointer"]++; if (buttonDown) counts["select"]++; if (wheel) counts["scroll"]++; }
        else if (deviceClass == "keyboard") { counts["switch_activations"]++; } // switch interfaces present as keys; key code NOT read
    }

    public Dictionary<string,int> TakeCounts() { var c = new Dictionary<string,int>(counts); foreach (var k in c.Keys) counts[k] = 0; return c; }
}
