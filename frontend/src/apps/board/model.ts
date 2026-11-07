// Communication board — pure state model.
//
// The board is device-agnostic: it never knows which device is connected. It
// adapts its interaction mode to the capabilities the runtime granted:
//   pointer_intent granted        -> "pointer": cursor driven by velocity, select hovered tile
//   selection only                -> "scan":    tiles highlighted in turn, select highlighted tile
//   text_intent granted (either)  -> text intents are appended to the message directly
// Workspace: unit square, x to the right, y downward; the tile grid fills it.

import type { Capability, NegotiationResult, AppStatus } from "../../sdk";

export type TileKind = "phrase" | "space" | "delete" | "clear" | "speak";
export interface Tile {
  label: string;
  kind: TileKind;
}

export const COLS = 4;
export const ROWS = 3;
export const TILES: readonly Tile[] = [
  { label: "Yes", kind: "phrase" },
  { label: "No", kind: "phrase" },
  { label: "Hello", kind: "phrase" },
  { label: "Thank you", kind: "phrase" },
  { label: "Please", kind: "phrase" },
  { label: "Help", kind: "phrase" },
  { label: "Water", kind: "phrase" },
  { label: "Wait", kind: "phrase" },
  { label: "Space", kind: "space" },
  { label: "Delete", kind: "delete" },
  { label: "Clear", kind: "clear" },
  { label: "Speak", kind: "speak" },
];
export const MAX_MESSAGE = 280;
export const MAX_DT_S = 0.1;

export type Mode = "pointer" | "scan" | "inactive";

export interface BoardState {
  mode: Mode;
  status: AppStatus;
  granted: Capability[];
  cursor: { x: number; y: number };
  hover: number | null;
  scanIndex: number;
  message: string;
  lastSelected: { index: number | null; seq: number } | null;
  selections: number;
  speakRequests: number;
  lastPointerNs: number | null;
}

export type BoardAction =
  | { type: "negotiation"; negotiation: NegotiationResult }
  | { type: "pointer"; vx: number; vy: number; timestampNs: number }
  | { type: "select" }
  | { type: "text"; text: string; mode: "character" | "word" }
  | { type: "scanTick" };

export function initialBoard(): BoardState {
  return {
    mode: "inactive",
    status: "no_device",
    granted: [],
    cursor: { x: 0.5, y: 0.5 },
    hover: tileAt(0.5, 0.5),
    scanIndex: 0,
    message: "",
    lastSelected: null,
    selections: 0,
    speakRequests: 0,
    lastPointerNs: null,
  };
}

export function modeFor(n: NegotiationResult): Mode {
  if (n.status !== "active") return "inactive";
  if (n.granted.includes("pointer_intent")) return "pointer";
  if (n.granted.includes("selection")) return "scan";
  return "inactive";
}

export function tileAt(x: number, y: number): number {
  const col = Math.min(COLS - 1, Math.max(0, Math.floor(x * COLS)));
  const row = Math.min(ROWS - 1, Math.max(0, Math.floor(y * ROWS)));
  return row * COLS + col;
}

const clamp01 = (v: number) => Math.min(1, Math.max(0, v));

export function applyTile(message: string, tile: Tile): string {
  switch (tile.kind) {
    case "phrase": {
      const sep = message.length === 0 || message.endsWith(" ") ? "" : " ";
      return (message + sep + tile.label).slice(0, MAX_MESSAGE);
    }
    case "space":
      return (message + " ").slice(0, MAX_MESSAGE);
    case "delete":
      return message.slice(0, -1);
    case "clear":
      return "";
    case "speak":
      return message;
  }
}

export function boardReducer(s: BoardState, a: BoardAction): BoardState {
  switch (a.type) {
    case "negotiation": {
      const mode = modeFor(a.negotiation);
      return {
        ...s,
        mode,
        status: a.negotiation.status,
        granted: a.negotiation.granted,
        lastPointerNs: null,
        scanIndex: mode === "scan" && s.mode !== "scan" ? 0 : s.scanIndex,
      };
    }
    case "pointer": {
      if (s.mode !== "pointer") return s;
      const dt =
        s.lastPointerNs === null
          ? 0.02
          : Math.min(MAX_DT_S, Math.max(0, (a.timestampNs - s.lastPointerNs) / 1e9));
      const x = clamp01(s.cursor.x + a.vx * dt);
      const y = clamp01(s.cursor.y + a.vy * dt);
      return { ...s, cursor: { x, y }, hover: tileAt(x, y), lastPointerNs: a.timestampNs };
    }
    case "select": {
      const index = s.mode === "pointer" ? s.hover : s.mode === "scan" ? s.scanIndex : null;
      if (index === null) return s;
      const tile = TILES[index];
      if (!tile) return s;
      return {
        ...s,
        message: applyTile(s.message, tile),
        lastSelected: { index, seq: s.selections + 1 },
        selections: s.selections + 1,
        speakRequests: tile.kind === "speak" ? s.speakRequests + 1 : s.speakRequests,
      };
    }
    case "text": {
      if (!s.granted.includes("text_intent")) return s;
      // characters are typed as-is; words are separated like phrases
      const message =
        a.mode === "word" ? applyTile(s.message, { label: a.text, kind: "phrase" }) : s.message + a.text;
      return { ...s, message: message.slice(0, MAX_MESSAGE) };
    }
    case "scanTick":
      return s.mode === "scan" ? { ...s, scanIndex: (s.scanIndex + 1) % TILES.length } : s;
  }
}
