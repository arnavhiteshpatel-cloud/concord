// Communication board — read-only state snapshot for tests and evaluation harnesses.
//
// `window.__concordBoard` returns a fresh plain-object copy of the board state on every read.
// It is NOT a control path: nothing written to it reaches the board, and the board is driven
// only by runtime events. Field names are stable (version 1) and documented in
// docs/APPLICATIONS.md ("Evaluation snapshot").

import type { AppStatus, Capability, ConnectionStatus, GuardStats } from "../../sdk";
import type { ControlStateInfo } from "../../sdk";
import { METHOD_LABEL, type Method } from "./methods";
import { buildPage, focusTile, type BoardState, type HistoryEntry, type PageKind, type SelectionRecord } from "./model";
import { compositionLabel, dataQualifiers, inputLabel } from "./provenance";
import type { BoardSettings } from "./settings";

export const SNAPSHOT_VERSION = 1;

export interface BoardSnapshot {
  version: number;
  connection: ConnectionStatus;
  status: AppStatus;
  granted: Capability[];
  usable: Capability[];
  /** command capabilities waiting for the operator's authorization of this app */
  waitingForAuthorization: Capability[];
  method: Method | null;
  methodLabel: string;
  /** the method may act now */
  active: boolean;
  stopReason: string | null;
  /** the runtime's latest control.state for this app */
  control: ControlStateInfo | null;
  layout: {
    kind: "communication" | "grid";
    page: PageKind;
    cols: number;
    rows: number;
    /** tile labels in index order (index = row * cols + col) */
    tiles: string[];
    geometry: string;
  };
  /** cursor in the unit-square workspace, x right, y down */
  cursor: { x: number; y: number };
  /** the tile under the cursor or the highlight; null without an input method */
  highlighted: number | null;
  pending: { page: PageKind; tile: number } | null;
  text: string;
  /** "demonstration — not the participant's message" etc. */
  textLabel: string | null;
  input: { label: string; qualifiers: string[] } | null;
  selections: SelectionRecord[];
  history: HistoryEntry[];
  counters: BoardState["counters"] & { selections: number };
  guard: GuardStats | null;
  settings: BoardSettings;
}

export const GEOMETRY =
  "unit square workspace, x to the right, y down, origin top-left; the page's cols x rows tiles fill it; " +
  "tile index = row * cols + col; the cursor starts at (0.5, 0.5) and is clamped to [0, 1]";

export function snapshot(
  s: BoardState,
  extra: { connection: ConnectionStatus; control: ControlStateInfo | null; guard: GuardStats | null },
): BoardSnapshot {
  const page = buildPage(s);
  const snap: BoardSnapshot = {
    version: SNAPSHOT_VERSION,
    connection: extra.connection,
    status: s.status,
    granted: s.granted,
    usable: s.usable,
    waitingForAuthorization: s.waiting,
    method: s.method,
    methodLabel: s.method ? METHOD_LABEL[s.method] : "Waiting",
    active: s.active,
    stopReason: s.active ? null : s.stopReason,
    control: extra.control,
    layout: {
      kind: s.settings.layout,
      page: s.page,
      cols: page.cols,
      rows: page.rows,
      tiles: page.tiles.map((t) => t.label),
      geometry: GEOMETRY,
    },
    cursor: s.cursor,
    highlighted: focusTile(s),
    pending: s.pending ? { page: s.pending.page, tile: s.pending.tile } : null,
    text: s.message,
    textLabel: compositionLabel(s.sources),
    input: s.lastInput ? { label: inputLabel(s.lastInput), qualifiers: dataQualifiers(s.lastInput) } : null,
    selections: s.selections,
    history: s.history,
    counters: { ...s.counters, selections: s.selectionCount },
    guard: extra.guard,
    settings: s.settings,
  };
  return JSON.parse(JSON.stringify(snap)) as BoardSnapshot; // a copy: reading never shares state
}

declare global {
  interface Window {
    __concordBoard?: BoardSnapshot;
  }
}

/** Install the read-only getter; returns a function that removes it. */
export function exposeSnapshot(read: () => BoardSnapshot): () => void {
  Object.defineProperty(window, "__concordBoard", { get: read, configurable: true, enumerable: false });
  return () => {
    delete (window as { __concordBoard?: BoardSnapshot }).__concordBoard;
  };
}
