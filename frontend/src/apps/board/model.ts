// Communication board v2 — pure state model (no DOM, no clocks: time comes in with actions).
//
// The board is device-agnostic: it never knows which device is connected. It adapts to the
// capabilities the runtime granted (see methods.ts) and acts only on commands the SDK's
// CommandGuard passed as usable (`usable`). Geometry (stable, documented in
// docs/APPLICATIONS.md): the workspace is the unit square, x to the right, y DOWN, origin at
// the top-left; the current page's cols × rows tiles fill it; tile index = row * cols + col.
// The cursor starts at the centre (0.5, 0.5) and is clamped to the workspace.

import type { AppStatus, Capability, NegotiationResult } from "../../sdk";
import { chooseMethod, methodNeeds, type Method } from "./methods";
import { compositionLabel, inputLabel, type EventRef, type InputTag } from "./provenance";
import { DEFAULT_SETTINGS, type BoardSettings, type TileSize } from "./settings";
import { CORE_WORDS, LETTERS, PHRASES, predictions } from "./vocabulary";

export type PageKind = "phrases" | "letters" | "grid";
export type TileKind = "phrase" | "word" | "letter" | "predict" | "space" | "delete" | "undo" | "clear" | "speak" | "page" | "punct";

export interface Tile {
  label: string;
  kind: TileKind;
  /** letter/punctuation to type, page to open, "word"/"char" for delete */
  value?: string;
}

export interface Page {
  kind: PageKind;
  cols: number;
  rows: number;
  tiles: Tile[];
}

export type Via = "click" | "dwell" | "scan" | "navigate" | "direct";

export interface SelectionRecord {
  n: number;
  page: PageKind;
  tile: number;
  label: string;
  via: Via;
  atMs: number;
  cursor: { x: number; y: number } | null;
  event: EventRef | null;
}

export interface HistoryEntry {
  n: number;
  text: string;
  atMs: number;
  /** e.g. "decoded by m1 (BrainOS)" */
  input: string | null;
  /** "demonstration — not the participant's message" etc., or null */
  label: string | null;
}

interface UndoEntry {
  message: string;
  sources: InputTag[];
}

export interface BoardState {
  settings: BoardSettings;
  words: readonly string[];
  speechAvailable: boolean;
  status: AppStatus;
  granted: Capability[];
  /** command capabilities the guard says are usable now */
  usable: Capability[];
  /** command capabilities the runtime withholds until the operator authorizes this app */
  waiting: Capability[];
  stopReason: string | null;
  sawDirectActions: boolean;
  method: Method | null;
  /** the method that was in effect when input was lost (its frozen cursor stays visible) */
  heldMethod: Method | null;
  /** the method may act now (all it needs is usable) */
  active: boolean;
  page: PageKind;
  cursor: { x: number; y: number };
  hover: number;
  /** highlight for scan / navigate / direct */
  highlight: number;
  /** last pointer event time on its clock (ns), the clock, and the session */
  lastPointer: { t: number; clock: "device" | "runtime"; session: string } | null;
  /** the cursor / highlight has moved since input became active: dwell arms only then, so
   *  resting where the cursor happens to be when input (re)starts never selects anything */
  moved: boolean;
  scan: { stage: "row" | "cell"; lastMs: number | null; cycles: number };
  dwell: { tile: number | null; sinceMs: number | null; armed: boolean };
  pending: { page: PageKind; tile: number; atMs: number } | null;
  lastClick: { t: number; clock: "device" | "runtime"; session: string } | null;
  message: string;
  sources: InputTag[];
  undo: UndoEntry[];
  history: HistoryEntry[];
  selections: SelectionRecord[];
  selectionCount: number;
  lastChosen: { n: number; page: PageKind; tile: number; label: string } | null;
  speech: { n: number; text: string } | null;
  lastInput: InputTag | null;
  counters: { debounced: number; pendingConfirmations: number; ignoredInactive: number; texts: number };
}

export type SelectAction = "primary" | "activate" | "cancel";
export type Direction = "up" | "down" | "left" | "right" | "next" | "previous";

export type BoardAction =
  | { type: "negotiation"; negotiation: NegotiationResult }
  | { type: "usable"; caps: Capability[]; reason: string | null; waiting?: Capability[] }
  | { type: "settings"; settings: BoardSettings }
  | { type: "words"; words: string[] }
  | { type: "speechAvailable"; available: boolean }
  | { type: "pointer"; vx: number; vy: number; ref: EventRef; nowMs: number }
  | { type: "select"; action: SelectAction; ref: EventRef; nowMs: number }
  | { type: "navigate"; direction: Direction; ref: EventRef; nowMs: number }
  | { type: "text"; text: string; mode: "character" | "word"; ref: EventRef; nowMs: number }
  | { type: "tick"; nowMs: number }
  | { type: "clearHistory" };

export const MAX_MESSAGE = 280;
/** pointer integration: a longer gap between two pointer events does not teleport the cursor */
export const MAX_DT_S = 0.1;
const MAX_UNDO = 50;
const MAX_HISTORY = 50;
export const MAX_SELECTIONS = 5000;
const SCAN_CYCLES_PER_ROW = 2;

// ------------------------------------------------------------------------------- pages

const PHRASE_GRID: Record<TileSize, [number, number]> = { large: [3, 3], standard: [4, 4], small: [5, 5] };

function phraseControls(speak: string): Tile[] {
  return [
    { label: "Letters", kind: "page", value: "letters" },
    { label: "Delete word", kind: "delete", value: "word" },
    { label: "Undo", kind: "undo" },
    { label: "Clear", kind: "clear" },
    { label: speak, kind: "speak" },
  ];
}

export function speakLabel(s: Pick<BoardState, "speechAvailable" | "settings">): string {
  return s.speechAvailable && s.settings.speech ? "Speak" : "Save";
}

export function buildPage(s: Pick<BoardState, "page" | "settings" | "words" | "message" | "speechAvailable">): Page {
  if (s.settings.layout === "grid") {
    const n = s.settings.gridN;
    const tiles: Tile[] = Array.from({ length: n * n }, (_, i) => ({ label: s.words[i] ?? "", kind: "word" as const }));
    return { kind: "grid", cols: n, rows: n, tiles };
  }
  const speak = speakLabel(s);
  if (s.page === "letters") {
    const pred = predictions(s.message, 3, s.words.length ? s.words : CORE_WORDS);
    const tiles: Tile[] = [
      ...[0, 1, 2].map((i) => ({ label: pred[i] ?? "", kind: "predict" as const })),
      { label: "Space", kind: "space" },
      { label: "Delete", kind: "delete", value: "char" },
      { label: "Phrases", kind: "page", value: "phrases" },
      ...LETTERS.map((l) => ({ label: l, kind: "letter" as const, value: l })),
      { label: ".", kind: "punct", value: "." },
      { label: "Undo", kind: "undo" },
      { label: "Clear", kind: "clear" },
      { label: speak, kind: "speak" },
    ];
    return { kind: "letters", cols: 6, rows: 6, tiles };
  }
  const [cols, rows] = PHRASE_GRID[s.settings.tileSize];
  const controls = phraseControls(speak);
  const phrases = PHRASES.slice(0, cols * rows - controls.length).map((p) => ({ label: p, kind: "phrase" as const }));
  return { kind: "phrases", cols, rows, tiles: [...phrases, ...controls] };
}

/** cols × rows of the current page (cheap: used on every pointer event). */
export function pageDims(s: Pick<BoardState, "page" | "settings">): [number, number] {
  if (s.settings.layout === "grid") return [s.settings.gridN, s.settings.gridN];
  if (s.page === "letters") return [6, 6];
  return PHRASE_GRID[s.settings.tileSize];
}

export function tileAt(x: number, y: number, cols: number, rows: number): number {
  const col = Math.min(cols - 1, Math.max(0, Math.floor(x * cols)));
  const row = Math.min(rows - 1, Math.max(0, Math.floor(y * rows)));
  return row * cols + col;
}

// ------------------------------------------------------------------------------- text

const clamp01 = (v: number) => Math.min(1, Math.max(0, v));
const cut = (m: string) => m.slice(0, MAX_MESSAGE);

export function appendWord(message: string, word: string): string {
  const sep = message.length === 0 || message.endsWith(" ") ? "" : " ";
  return cut(message + sep + word);
}

function typeLetter(message: string, letter: string): string {
  const start = message.length === 0 || /[.!?]\s*$/.test(message);
  return cut(message + (start ? letter.toUpperCase() : letter.toLowerCase()));
}

function completeWord(message: string, word: string): string {
  return cut(message.replace(/[A-Za-z']+$/, "") + word + " ");
}

export function deleteWord(message: string): string {
  return message.replace(/\s*\S+\s*$/, "");
}

// ------------------------------------------------------------------------------- state

export function initialBoard(settings: BoardSettings = DEFAULT_SETTINGS): BoardState {
  return {
    settings,
    words: CORE_WORDS,
    speechAvailable: false,
    status: "no_device",
    granted: [],
    usable: [],
    waiting: [],
    stopReason: null,
    sawDirectActions: false,
    method: null,
    heldMethod: null,
    active: false,
    page: settings.layout === "grid" ? "grid" : "phrases",
    cursor: { x: 0.5, y: 0.5 },
    hover: 0,
    highlight: 0,
    lastPointer: null,
    moved: false,
    scan: { stage: "row", lastMs: null, cycles: 0 },
    dwell: { tile: null, sinceMs: null, armed: true },
    pending: null,
    lastClick: null,
    message: "",
    sources: [],
    undo: [],
    history: [],
    selections: [],
    selectionCount: 0,
    lastChosen: null,
    speech: null,
    lastInput: null,
    counters: { debounced: 0, pendingConfirmations: 0, ignoredInactive: 0, texts: 0 },
  };
}

/** Cancel everything in flight: dwell, pending confirmation, row selection, pointer integration. */
function freeze(s: BoardState): BoardState {
  return {
    ...s,
    lastPointer: null,
    moved: false,
    dwell: { tile: null, sinceMs: null, armed: true },
    pending: null,
    scan: { stage: "row", lastMs: null, cycles: 0 },
  };
}

/** Recompute method / active / page geometry after anything that can change them. */
function settle(s: BoardState): BoardState {
  const method = chooseMethod(s.settings.method, s.granted, s.sawDirectActions);
  const page: PageKind = s.settings.layout === "grid" ? "grid" : s.page === "grid" ? "phrases" : s.page;
  const active = s.status === "active" && method !== null && methodNeeds(method, s.granted).every((c) => s.usable.includes(c));
  const heldMethod = method !== null ? null : s.method !== null && s.active ? s.method : s.heldMethod;
  let next: BoardState = { ...s, method, page, active, heldMethod };
  if (method !== s.method || page !== s.page || (s.active && !active)) next = freeze(next);
  const [cols, rows] = pageDims(next);
  if (next.highlight >= cols * rows) next = { ...next, highlight: 0 };
  const hover = tileAt(next.cursor.x, next.cursor.y, cols, rows);
  return hover === next.hover ? next : { ...next, hover };
}

function clockOf(ref: EventRef): { t: number; clock: "device" | "runtime"; session: string } {
  return ref.deviceTimestampNs !== null
    ? { t: ref.deviceTimestampNs, clock: "device", session: ref.sessionId }
    : { t: ref.timestampNs, clock: "runtime", session: ref.sessionId };
}

function pushUndo(s: BoardState): UndoEntry[] {
  return [...s.undo, { message: s.message, sources: s.sources }].slice(-MAX_UNDO);
}

function withSource(sources: InputTag[], t: InputTag | null): InputTag[] {
  if (!t) return sources;
  const key = (x: InputTag) => `${inputLabel(x)}|${x.replayed}|${x.synthetic}`;
  return sources.some((x) => key(x) === key(t)) ? sources : [...sources, t];
}

/** Apply a chosen tile's effect on the text / page. */
function applyTile(s: BoardState, tile: Tile, input: InputTag | null, nowMs: number): BoardState {
  const edit = (message: string): BoardState => ({
    ...s,
    undo: pushUndo(s),
    message,
    sources: message ? withSource(s.sources, input) : [],
  });
  switch (tile.kind) {
    case "phrase":
    case "word":
      return tile.label ? edit(appendWord(s.message, tile.label)) : s;
    case "letter":
    case "punct":
      return edit(typeLetter(s.message, tile.value ?? tile.label));
    case "predict":
      return tile.label ? edit(completeWord(s.message, tile.label)) : s;
    case "space":
      return s.message && !s.message.endsWith(" ") ? edit(cut(s.message + " ")) : s;
    case "delete":
      return s.message ? edit(tile.value === "char" ? s.message.slice(0, -1) : deleteWord(s.message)) : s;
    case "clear":
      return s.message ? { ...edit(""), sources: [] } : s;
    case "undo": {
      const last = s.undo[s.undo.length - 1];
      return last ? { ...s, undo: s.undo.slice(0, -1), message: last.message, sources: last.sources } : s;
    }
    case "page":
      return { ...s, page: tile.value === "letters" ? "letters" : "phrases", highlight: 0, dwell: { tile: null, sinceMs: null, armed: true } };
    case "speak": {
      if (!s.message.trim()) return s;
      const n = (s.history[s.history.length - 1]?.n ?? 0) + 1;
      const last = s.sources[s.sources.length - 1] ?? null;
      const entry: HistoryEntry = {
        n,
        text: s.message,
        atMs: nowMs,
        input: last ? inputLabel(last) : null,
        label: compositionLabel(s.sources),
      };
      return {
        ...s,
        history: [...s.history, entry].slice(-MAX_HISTORY),
        speech: s.speechAvailable && s.settings.speech ? { n: (s.speech?.n ?? 0) + 1, text: s.message } : s.speech,
      };
    }
  }
}

/** Choose tile `index` of the current page (with the confirmation style). */
function choose(s: BoardState, index: number, via: Via, ref: EventRef | null, nowMs: number): BoardState {
  const page = buildPage(s);
  const tile = page.tiles[index];
  if (!tile) return s;
  if (s.settings.confirm === "repeat") {
    const p = s.pending;
    const confirmed = p !== null && p.page === s.page && p.tile === index && nowMs - p.atMs <= s.settings.confirmMs;
    if (!confirmed) {
      return {
        ...s,
        pending: { page: s.page, tile: index, atMs: nowMs },
        counters: { ...s.counters, pendingConfirmations: s.counters.pendingConfirmations + 1 },
      };
    }
  }
  const n = s.selectionCount + 1;
  const rec: SelectionRecord = {
    n,
    page: s.page,
    tile: index,
    label: tile.label,
    via,
    atMs: nowMs,
    cursor: via === "click" || via === "dwell" ? { ...s.cursor } : null,
    event: ref,
  };
  // dwell has no triggering event: the text comes from the input that positioned the cursor
  const applied = applyTile({ ...s, pending: null }, tile, ref?.input ?? s.lastInput, nowMs);
  return settle({
    ...applied,
    selectionCount: n,
    selections: [...s.selections, rec].slice(-MAX_SELECTIONS),
    lastChosen: { n, page: s.page, tile: index, label: tile.label },
  });
}

function undoOrCancel(s: BoardState, ref: EventRef, nowMs: number): BoardState {
  if (s.pending) return { ...s, pending: null };
  if (s.scan.stage === "cell" && s.method === "scan") return { ...s, scan: { stage: "row", lastMs: nowMs, cycles: 0 } };
  const last = s.undo[s.undo.length - 1];
  if (!last) return s;
  return { ...s, undo: s.undo.slice(0, -1), message: last.message, sources: last.sources, lastInput: ref.input };
}

function moveHighlight(s: BoardState, d: Direction): BoardState {
  const p = buildPage(s);
  const n = p.tiles.length;
  const i = s.highlight;
  const row = Math.floor(i / p.cols);
  const col = i % p.cols;
  let j = i;
  if (d === "next") j = (i + 1) % n;
  else if (d === "previous") j = (i - 1 + n) % n;
  else if (d === "up" && row > 0) j = i - p.cols;
  else if (d === "down" && row < p.rows - 1 && i + p.cols < n) j = i + p.cols;
  else if (d === "left" && col > 0) j = i - 1;
  else if (d === "right" && col < p.cols - 1 && i + 1 < n) j = i + 1;
  return j === i ? s : { ...s, highlight: j, pending: null, dwell: { tile: null, sinceMs: null, armed: true } };
}

function debounced(s: BoardState, ref: EventRef): { skip: boolean; next: BoardState } {
  const c = clockOf(ref);
  const last = s.lastClick;
  const ms = s.settings.clickRefractoryMs;
  if (last && ms > 0 && last.session === c.session && last.clock === c.clock && c.t >= last.t && (c.t - last.t) / 1e6 < ms) {
    return { skip: true, next: { ...s, counters: { ...s.counters, debounced: s.counters.debounced + 1 } } };
  }
  return { skip: false, next: { ...s, lastClick: c } };
}

function inactive(s: BoardState): BoardState {
  return { ...s, counters: { ...s.counters, ignoredInactive: s.counters.ignoredInactive + 1 } };
}

export function boardReducer(s: BoardState, a: BoardAction): BoardState {
  switch (a.type) {
    case "negotiation":
      return settle({ ...s, status: a.negotiation.status, granted: a.negotiation.granted });
    case "usable":
      return settle({ ...s, usable: a.caps, stopReason: a.reason, waiting: a.waiting ?? [] });
    case "settings": {
      const layoutChanged = a.settings.layout !== s.settings.layout;
      const base: BoardState = { ...s, settings: a.settings };
      return settle(layoutChanged ? { ...freeze(base), page: a.settings.layout === "grid" ? "grid" : "phrases", highlight: 0 } : base);
    }
    case "words":
      return settle({ ...s, words: a.words.length ? a.words : CORE_WORDS });
    case "speechAvailable":
      return { ...s, speechAvailable: a.available };

    case "pointer": {
      if (!s.active || (s.method !== "cursor_click" && s.method !== "cursor_dwell")) return inactive(s);
      const c = clockOf(a.ref);
      const last = s.lastPointer;
      // integrate on the event clock (device timestamps when present): replay speed does not
      // change the trajectory; the first event after a (re)start only sets the clock
      const dt =
        last && last.clock === c.clock && last.session === c.session ? Math.min(MAX_DT_S, Math.max(0, (c.t - last.t) / 1e9)) : 0;
      const x = clamp01(s.cursor.x + a.vx * dt);
      const y = clamp01(s.cursor.y + a.vy * dt);
      const [cols, rows] = pageDims(s);
      const moved = s.moved || x !== s.cursor.x || y !== s.cursor.y;
      return { ...s, cursor: { x, y }, hover: tileAt(x, y, cols, rows), lastPointer: c, lastInput: a.ref.input, moved };
    }

    case "select": {
      const next = select(s, a);
      // a source that sends activate / cancel offers direct selection: "auto" uses it from the
      // next event on (this one was handled by the method in effect when it arrived)
      const direct = a.action === "activate" || a.action === "cancel";
      return direct && !next.sawDirectActions && next.status === "active" ? settle({ ...next, sawDirectActions: true }) : next;
    }

    case "navigate": {
      if (!s.active || s.method !== "navigate") return inactive(s);
      return { ...moveHighlight(s, a.direction), lastInput: a.ref.input, moved: true };
    }

    case "text": {
      if (!s.usable.includes("text_intent") || s.status !== "active") return inactive(s);
      const message = a.mode === "word" ? appendWord(s.message, a.text) : cut(s.message + a.text);
      return {
        ...s,
        undo: pushUndo(s),
        message,
        sources: withSource(s.sources, a.ref.input),
        lastInput: a.ref.input,
        counters: { ...s.counters, texts: s.counters.texts + 1 },
      };
    }

    case "tick":
      return tick(s, a.nowMs);
    case "clearHistory":
      return { ...s, history: [] };
  }
}

function select(s: BoardState, a: Extract<BoardAction, { type: "select" }>): BoardState {
  if (!s.active || s.method === null || s.method === "cursor_dwell") return inactive(s);
  if (s.method === "navigate" && !s.granted.includes("selection")) return inactive(s);
  const d = debounced(s, a.ref);
  if (d.skip) return d.next;
  const t: BoardState = { ...d.next, lastInput: a.ref.input };
  if (a.action === "cancel") return undoOrCancel(t, a.ref, a.nowMs);
  switch (t.method) {
    case "cursor_click":
      return choose(t, t.hover, "click", a.ref, a.nowMs);
    case "navigate":
      return choose(t, t.highlight, "navigate", a.ref, a.nowMs);
    case "direct":
      return a.action === "primary" ? moveHighlight(t, "next") : choose(t, t.highlight, "direct", a.ref, a.nowMs);
    case "scan": {
      if (t.settings.scanPattern === "row_column" && t.scan.stage === "row") {
        const [cols] = pageDims(t);
        const row = Math.floor(t.highlight / cols);
        return { ...t, highlight: row * cols, scan: { stage: "cell", lastMs: a.nowMs, cycles: 0 } };
      }
      const chosen = choose(t, t.highlight, "scan", a.ref, a.nowMs);
      if (chosen.pending) return { ...chosen, scan: { ...t.scan, lastMs: a.nowMs } }; // confirm: stay
      // after a choice, scanning starts again from the first tile
      return { ...chosen, highlight: 0, scan: { stage: "row", lastMs: a.nowMs, cycles: 0 } };
    }
    default:
      return t;
  }
}

function tick(s0: BoardState, nowMs: number): BoardState {
  let s = s0;
  if (s.pending && nowMs - s.pending.atMs > s.settings.confirmMs) s = { ...s, pending: null };
  if (!s.active) return s;
  const dwellTarget =
    s.method === "cursor_dwell" ? s.hover : s.method === "navigate" && !s.granted.includes("selection") ? s.highlight : null;
  if (dwellTarget !== null) {
    const d = s.dwell;
    if (!s.moved) return s; // nothing moved since input became active: no dwell yet
    if (d.tile !== dwellTarget || d.sinceMs === null) return { ...s, dwell: { tile: dwellTarget, sinceMs: nowMs, armed: true } };
    if (d.armed && nowMs - d.sinceMs >= s.settings.dwellMs) {
      const chosen = choose(s, dwellTarget, s.method === "navigate" ? "navigate" : "dwell", null, nowMs);
      // a pending confirmation re-arms (keep resting to confirm); a choice needs leaving the tile
      const again = chosen.pending !== null;
      return { ...chosen, dwell: { tile: dwellTarget, sinceMs: nowMs, armed: again } };
    }
    return s;
  }
  if (s.method === "scan") {
    if (s.scan.lastMs === null) return { ...s, scan: { ...s.scan, lastMs: nowMs } };
    if (nowMs - s.scan.lastMs < s.settings.scanIntervalMs) return s;
    const p = buildPage(s);
    const n = p.tiles.length;
    if (s.settings.scanPattern === "linear") return { ...s, highlight: (s.highlight + 1) % n, scan: { ...s.scan, lastMs: nowMs } };
    const row = Math.floor(s.highlight / p.cols);
    if (s.scan.stage === "row") {
      const nextRow = (row + 1) % p.rows;
      return { ...s, highlight: nextRow * p.cols, scan: { ...s.scan, lastMs: nowMs } };
    }
    const col = s.highlight % p.cols;
    const lastCol = Math.min(p.cols, n - row * p.cols) - 1;
    if (col < lastCol) return { ...s, highlight: s.highlight + 1, scan: { ...s.scan, lastMs: nowMs } };
    const cycles = s.scan.cycles + 1;
    return cycles >= SCAN_CYCLES_PER_ROW
      ? { ...s, highlight: row * p.cols, scan: { stage: "row", lastMs: nowMs, cycles: 0 } }
      : { ...s, highlight: row * p.cols, scan: { stage: "cell", lastMs: nowMs, cycles } };
  }
  return s;
}

/** The tile the participant is on: the cursor's tile, or the highlight. */
export function focusTile(s: BoardState): number | null {
  if (s.method === "cursor_click" || s.method === "cursor_dwell") return s.hover;
  if (s.method === "scan" || s.method === "navigate" || s.method === "direct") return s.highlight;
  return null;
}

/** Dwell progress 0..1 on the dwell tile (for the visual ring), or null. */
export function dwellProgress(s: BoardState, nowMs: number): number | null {
  const d = s.dwell;
  if (!s.active || !d.armed || d.sinceMs === null || d.tile === null) return null;
  return Math.min(1, Math.max(0, (nowMs - d.sinceMs) / s.settings.dwellMs));
}

/** Tiles in the row currently offered by row/column scanning (row stage), else null. */
export function scanRow(s: BoardState): number | null {
  if (s.method !== "scan" || s.settings.scanPattern !== "row_column" || s.scan.stage !== "row") return null;
  const p = buildPage(s);
  return Math.floor(s.highlight / p.cols);
}
