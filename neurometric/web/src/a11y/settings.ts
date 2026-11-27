// Participant / session settings: input modality declaration, selection method, dwell, switch
// scanning, timing (WCAG 2.2.1), display (theme, text size, motion). Stored per browser only
// (localStorage, wrapped: the app works without storage).

import { DEFAULT_SWITCH, type SwitchConfig } from "../input/switch";
import { DEFAULT_GAMEPAD, type GamepadConfig } from "../input/gamepad";
import type { Modality } from "../input/types";

export type SelectionMethod = "click" | "dwell" | "scan" | "keyboard" | "gamepad";
export type Theme = "system" | "light" | "dark" | "contrast";
export type Motion = "system" | "reduce" | "full";

export interface Settings {
  participantCode: string;
  /** Declared modality: what the participant actually uses (the browser cannot tell). */
  modality: Modality | "auto";
  selection: SelectionMethod;
  dwellMs: number;
  switch: SwitchConfig;
  /** Switch scanning also drives the app's own screens (setup, task list, dialogs). */
  uiScanning: boolean;
  noTimePressure: boolean;
  timeMultiplier: number;
  theme: Theme;
  textScale: number;
  motion: Motion;
  targetMinPx: number;
  short: boolean;
  gamepad: GamepadConfig;
}

export const DEFAULT_SETTINGS: Settings = {
  participantCode: "",
  modality: "auto",
  selection: "click",
  dwellMs: 800,
  switch: { ...DEFAULT_SWITCH },
  uiScanning: false,
  noTimePressure: true,
  timeMultiplier: 1,
  theme: "system",
  textScale: 1,
  motion: "system",
  targetMinPx: 0,
  short: false,
  gamepad: { ...DEFAULT_GAMEPAD },
};

const KEY = "neurometric.settings.v1";

export function loadSettings(): Settings {
  let s: Settings = { ...DEFAULT_SETTINGS, switch: { ...DEFAULT_SWITCH } };
  try {
    const raw = localStorage.getItem(KEY);
    if (raw) {
      const p = JSON.parse(raw);
      s = { ...s, ...p, switch: { ...DEFAULT_SWITCH, ...(p.switch ?? {}) }, gamepad: { ...DEFAULT_GAMEPAD, ...(p.gamepad ?? {}) } };
    }
  } catch {
    /* storage unavailable: defaults */
  }
  // URL overrides (used by staff links and automated tests), e.g. #/tasks?selection=scan&scan_ms=300
  try {
    const q = new URLSearchParams(location.hash.split("?")[1] ?? "");
    const sel = q.get("selection");
    if (sel && ["click", "dwell", "scan", "keyboard", "gamepad"].includes(sel)) s.selection = sel as SelectionMethod;
    if (q.get("dwell_ms")) s.dwellMs = Number(q.get("dwell_ms"));
    if (q.get("scan_ms")) s.switch = { ...s.switch, rateMs: Number(q.get("scan_ms")) };
    if (q.get("scan_mode") === "step") s.switch = { ...s.switch, mode: "step", switches: 2 };
    if (q.get("ui_scanning") === "1") s.uiScanning = true;
    if (q.get("short") === "1") s.short = true;
    if (q.get("theme")) s.theme = q.get("theme") as Theme;
  } catch {
    /* ignore */
  }
  return s;
}

export function saveSettings(s: Settings): void {
  try {
    localStorage.setItem(KEY, JSON.stringify(s));
  } catch {
    /* storage unavailable */
  }
}

export function prefersReducedMotion(s: Settings): boolean {
  if (s.motion === "reduce") return true;
  if (s.motion === "full") return false;
  try {
    return matchMedia("(prefers-reduced-motion: reduce)").matches;
  } catch {
    return false;
  }
}

export function modalityFor(s: Settings, fallback: Modality): Modality {
  return s.modality === "auto" ? fallback : s.modality;
}

export const MODALITY_LABELS: [Modality | "auto", string][] = [
  ["auto", "Detect from device (mouse, pen or touch)"],
  ["mouse", "Mouse"],
  ["trackpad", "Trackpad"],
  ["touch", "Touch screen"],
  ["pen", "Pen / stylus"],
  ["keyboard", "Keyboard"],
  ["switch", "Switch(es)"],
  ["eye_gaze", "Eye gaze (through the operating system pointer)"],
  ["head_pointer", "Head pointer (through the operating system pointer)"],
  ["joystick", "Joystick"],
  ["gamepad", "Gamepad"],
  ["bci_cursor", "BCI cursor (exposed as a pointer)"],
  ["bci_select", "BCI selection (exposed as a switch or key)"],
  ["other", "Other"],
];

export const SELECTION_LABELS: [SelectionMethod, string][] = [
  ["click", "Click / tap"],
  ["dwell", "Dwell (hold still on an item)"],
  ["scan", "Switch scanning"],
  ["keyboard", "Keyboard (Tab, arrows, Enter)"],
  ["gamepad", "Gamepad / joystick"],
];
