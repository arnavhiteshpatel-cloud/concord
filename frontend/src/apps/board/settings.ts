// Communication board — settings with operational effect. Validated and clamped; read from the
// page URL (for evaluation harnesses) over this browser's saved settings over the defaults.
//
// Deliberately absent: cursor gain or smoothing. Mapping decoder output to pointer velocity is
// the command router's job (operator, BrainOS console); the board integrates what it receives.

import type { MethodChoice } from "./methods";

export type LayoutKind = "communication" | "grid";
export type TileSize = "large" | "standard" | "small";
export type ScanPattern = "linear" | "row_column";
export type ConfirmStyle = "none" | "repeat";

export interface BoardSettings {
  /** "auto" picks the best input method the negotiated capabilities support */
  method: MethodChoice;
  /** "communication": phrase page + letter/word keyboard page; "grid": an N×N word grid */
  layout: LayoutKind;
  /** task grid size N (N×N tiles over a square workspace) */
  gridN: number;
  /** word-list file for the task grid (one per line), fetched by the board; null = built-in */
  wordsUrl: string | null;
  /** phrase-page targets: large 3×3, standard 4×4, small 5×5 */
  tileSize: TileSize;
  /** text size multiplier */
  textScale: number;
  /** cursor + dwell (and navigation without selection): time on one tile that selects it */
  dwellMs: number;
  scanIntervalMs: number;
  scanPattern: ScanPattern;
  /** board-side debounce: a selection/click within this time of the previous accepted one
   *  (event clock: device timestamps when present) is ignored, so one click selects once */
  clickRefractoryMs: number;
  /** "repeat": a tile must be selected twice in a row (within confirmMs) to be chosen */
  confirm: ConfirmStyle;
  confirmMs: number;
  /** short audio tick on every selection */
  audioTick: boolean;
  /** conventional text-to-speech (Web Speech API) of the composed text on "Speak" */
  speech: boolean;
  speechRate: number;
}

export const DEFAULT_SETTINGS: BoardSettings = {
  method: "auto",
  layout: "communication",
  gridN: 14,
  wordsUrl: null,
  tileSize: "standard",
  textScale: 1,
  dwellMs: 1000,
  scanIntervalMs: 1100,
  scanPattern: "linear",
  clickRefractoryMs: 300,
  confirm: "none",
  confirmMs: 3000,
  audioTick: false,
  speech: true,
  speechRate: 1,
};

export const LIMITS = {
  gridN: [2, 20],
  textScale: [0.75, 2],
  dwellMs: [300, 5000],
  scanIntervalMs: [400, 5000],
  clickRefractoryMs: [0, 3000],
  confirmMs: [1000, 10000],
  speechRate: [0.5, 2],
} as const satisfies Record<string, readonly [number, number]>;

const METHODS = ["auto", "cursor_click", "cursor_dwell", "scan", "navigate", "direct"] as const;
const clamp = (v: number, [lo, hi]: readonly [number, number]) => Math.min(hi, Math.max(lo, v));
const oneOf = <T extends string>(v: unknown, opts: readonly T[], d: T): T =>
  typeof v === "string" && (opts as readonly string[]).includes(v) ? (v as T) : d;
const num = (v: unknown, lim: readonly [number, number], d: number): number => {
  const n = typeof v === "number" ? v : typeof v === "string" && v.trim() !== "" ? Number(v) : NaN;
  return Number.isFinite(n) ? clamp(n, lim) : d;
};
const bool = (v: unknown, d: boolean): boolean =>
  typeof v === "boolean" ? v : v === "1" || v === "true" ? true : v === "0" || v === "false" ? false : d;

/** Validate untrusted settings (URL, storage); anything invalid falls back to `base`. */
export function normalizeSettings(raw: Record<string, unknown>, base: BoardSettings = DEFAULT_SETTINGS): BoardSettings {
  const words = raw.wordsUrl;
  return {
    method: oneOf(raw.method, METHODS, base.method),
    layout: oneOf(raw.layout, ["communication", "grid"] as const, base.layout),
    gridN: Math.round(num(raw.gridN, LIMITS.gridN, base.gridN)),
    wordsUrl: typeof words === "string" && words.length > 0 && words.length < 500 ? words : words === null ? null : base.wordsUrl,
    tileSize: oneOf(raw.tileSize, ["large", "standard", "small"] as const, base.tileSize),
    textScale: num(raw.textScale, LIMITS.textScale, base.textScale),
    dwellMs: Math.round(num(raw.dwellMs, LIMITS.dwellMs, base.dwellMs)),
    scanIntervalMs: Math.round(num(raw.scanIntervalMs, LIMITS.scanIntervalMs, base.scanIntervalMs)),
    scanPattern: oneOf(raw.scanPattern, ["linear", "row_column"] as const, base.scanPattern),
    clickRefractoryMs: Math.round(num(raw.clickRefractoryMs, LIMITS.clickRefractoryMs, base.clickRefractoryMs)),
    confirm: oneOf(raw.confirm, ["none", "repeat"] as const, base.confirm),
    confirmMs: Math.round(num(raw.confirmMs, LIMITS.confirmMs, base.confirmMs)),
    audioTick: bool(raw.audioTick, base.audioTick),
    speech: bool(raw.speech, base.speech),
    speechRate: num(raw.speechRate, LIMITS.speechRate, base.speechRate),
  };
}

/** URL query names (snake_case) → settings keys. Documented in docs/APPLICATIONS.md. */
export const URL_PARAMS: Record<string, keyof BoardSettings> = {
  method: "method",
  layout: "layout",
  n: "gridN",
  words: "wordsUrl",
  tile_size: "tileSize",
  text_scale: "textScale",
  dwell_ms: "dwellMs",
  scan_interval_ms: "scanIntervalMs",
  scan_pattern: "scanPattern",
  click_refractory_ms: "clickRefractoryMs",
  confirm: "confirm",
  confirm_ms: "confirmMs",
  audio_tick: "audioTick",
  speech: "speech",
  speech_rate: "speechRate",
};

export function settingsFromQuery(search: string): Record<string, unknown> {
  const q = new URLSearchParams(search);
  const out: Record<string, unknown> = {};
  for (const [name, key] of Object.entries(URL_PARAMS)) {
    const v = q.get(name);
    if (v !== null) out[key] = v;
  }
  return out;
}

const STORAGE_KEY = "brainos.board.settings.v2";

export function loadSettings(search: string): BoardSettings {
  let saved: Record<string, unknown> = {};
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (raw) saved = JSON.parse(raw) as Record<string, unknown>;
  } catch {
    /* storage unavailable or corrupt: defaults */
  }
  const fromStorage = normalizeSettings(saved && typeof saved === "object" ? saved : {});
  return normalizeSettings(settingsFromQuery(search), fromStorage);
}

export function saveSettings(s: BoardSettings): void {
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(s));
  } catch {
    /* not persisted: settings still apply to this page */
  }
}
