// Switch input and scanning.
//
// Switch interfaces (USB/Bluetooth switch boxes, a BCI exposed as a switch, sip-and-puff, EMG
// wristband gestures) present to the browser as KEYS (commonly Space / Enter, or configurable).
// The browser cannot know which device produced the key, so the modality is declared in setup.
//
// Scanning modes
//   * single switch, auto-scan: the highlight advances every `rateMs`; a press selects.
//   * two switches, step-scan:  switch 1 advances the highlight, switch 2 selects.
//   * two switches, auto-scan:  switch 2 selects, switch 1 steps / restarts.
//   * row-column (optional): first selection picks a row (group), the next an item in it.
// Scan restart after a selection: from the first item, or continue from the selected item.
// Auto-scan stops after `maxCycles` cycles without a selection; any press restarts it.
// Scanning is dwell-free: no hold/acceptance time is needed (acceptanceMs = 0 by default).
//
// Recording (see INPUT_ABSTRACTION.md): only the press that SELECTS an item is a `switch`
// event (a selection kind for scoring). Presses that start the scan, step the highlight or pick a
// row are `key` events with switch_id and meta.scan_action, so they never count as selections.

import type { EventRecorder, StreamHandle } from "./recorder";
import type { Modality } from "./types";

export interface SwitchConfig {
  switches: 1 | 2;
  mode: "auto" | "step";
  rateMs: number;
  restart: "first" | "continue";
  maxCycles: number; // 0 = unlimited
  rowColumn: boolean;
  keys: [string, string]; // KeyboardEvent.code values for switch 1, switch 2
  acceptanceMs: number; // minimum press duration (0 = dwell-free, immediate)
  initialDelayMs: number; // extra time on the first item of a cycle
}

export const DEFAULT_SWITCH: SwitchConfig = {
  switches: 1,
  mode: "auto",
  rateMs: 1000,
  restart: "first",
  maxCycles: 4,
  rowColumn: false,
  keys: ["Space", "Enter"],
  acceptanceMs: 0,
  initialDelayMs: 0,
};

export interface ScanTarget {
  id: string;
  /** Row / group for row-column scanning. */
  row?: number;
  /** Task-space centre (recorded with the selection) if the target is a task item. */
  x?: number;
  y?: number;
  el?: HTMLElement | null;
  label?: string;
  /** "task" targets are scored selections; "control" targets (pause, stop...) are not. */
  role: "task" | "control";
  activate: (t: number) => void;
}

export type ScanAction =
  | { type: "start" | "step" | "row" | "stopped"; t: number; switchIndex: number }
  | { type: "select"; t: number; switchIndex: number; target: ScanTarget };

export type HighlightFn = (targets: ScanTarget[], level: "item" | "row" | "none") => void;

/** Map a KeyboardEvent to a switch index (0/1) or -1. Matches on `code`, falling back to `key`. */
export function switchIndexOf(cfg: SwitchConfig, ev: KeyboardEvent): number {
  const n = cfg.switches === 2 || cfg.mode === "step" ? 2 : 1;
  for (let i = 0; i < n; i++) {
    const k = cfg.keys[i];
    if (ev.code === k || ev.key === k || (k === "Space" && ev.key === " ")) return i;
  }
  return -1;
}

/**
 * Generic scanner over a list of targets. Pure state machine + a timer; the caller supplies the
 * targets (re-read on every step so a changing screen is handled) and renders the highlight.
 */
export class Scanner {
  private idx = -1;
  private rowIdx = -1;
  private level: "row" | "item" = "item";
  private timer: ReturnType<typeof setTimeout> | null = null;
  private cycles = 0;
  running = false;

  constructor(
    public cfg: SwitchConfig,
    private getTargets: () => ScanTarget[],
    private onHighlight: HighlightFn,
    private onAction: (a: ScanAction) => void,
    private now: () => number,
  ) {}

  private rows(): number[] {
    const rs = new Set<number>();
    for (const t of this.getTargets()) rs.add(t.row ?? 0);
    return [...rs].sort((a, b) => a - b);
  }

  private useRows(): boolean {
    return this.cfg.rowColumn && this.rows().length > 1;
  }

  private current(): ScanTarget[] {
    const ts = this.getTargets();
    if (this.level === "row") {
      const r = this.rows()[this.rowIdx];
      return ts.filter((t) => (t.row ?? 0) === r);
    }
    const pool = this.useRows() && this.rowIdx >= 0 ? ts.filter((t) => (t.row ?? 0) === this.rows()[this.rowIdx]) : ts;
    return pool[this.idx] ? [pool[this.idx]] : [];
  }

  private pool(): ScanTarget[] {
    const ts = this.getTargets();
    if (this.useRows() && this.level === "item" && this.rowIdx >= 0) return ts.filter((t) => (t.row ?? 0) === this.rows()[this.rowIdx]);
    return ts;
  }

  private render(): void {
    this.onHighlight(this.running || this.idx >= 0 || this.rowIdx >= 0 ? this.current() : [], this.running || this.idx >= 0 || this.rowIdx >= 0 ? this.level : "none");
  }

  private schedule(): void {
    this.clearTimer();
    if (!this.running || this.cfg.mode !== "auto") return;
    const first = (this.level === "row" ? this.rowIdx : this.idx) === 0;
    this.timer = setTimeout(() => this.advance(true), this.cfg.rateMs + (first ? this.cfg.initialDelayMs : 0));
  }

  private clearTimer(): void {
    if (this.timer) clearTimeout(this.timer);
    this.timer = null;
  }

  /** Begin scanning at the first item (or row). */
  start(): void {
    this.running = true;
    this.cycles = 0;
    if (this.useRows()) {
      this.level = "row";
      this.rowIdx = 0;
      this.idx = -1;
    } else {
      this.level = "item";
      this.rowIdx = -1;
      this.idx = 0;
    }
    this.render();
    this.schedule();
  }

  stop(): void {
    this.running = false;
    this.clearTimer();
    this.idx = -1;
    this.rowIdx = -1;
    this.level = "item";
    this.render();
  }

  /** Advance the highlight one step (auto-scan tick or step switch). */
  advance(auto = false): void {
    if (this.level === "row") {
      const n = this.rows().length;
      this.rowIdx = (this.rowIdx + 1) % Math.max(n, 1);
      if (this.rowIdx === 0) this.cycles++;
    } else {
      const n = this.pool().length;
      this.idx = (this.idx + 1) % Math.max(n, 1);
      if (this.idx === 0) {
        this.cycles++;
        if (this.useRows() && this.rowIdx >= 0) {
          // item level exhausted without a selection: go back to row scanning
          this.level = "row";
          this.idx = -1;
        }
      }
    }
    if (auto && this.cfg.maxCycles > 0 && this.cycles >= this.cfg.maxCycles) {
      this.running = false;
      this.clearTimer();
      this.idx = -1;
      this.rowIdx = -1;
      this.level = "item";
      this.render();
      this.onAction({ type: "stopped", t: this.now(), switchIndex: -1 });
      return;
    }
    this.render();
    this.schedule();
  }

  /** A switch press (index 0 or 1) at session time t. */
  press(switchIndex: number, t: number = this.now()): void {
    const twoSwitchStep = this.cfg.mode === "step";
    const isSelect = twoSwitchStep || this.cfg.switches === 2 ? switchIndex === 1 : true;
    if (!this.running && this.idx < 0 && this.rowIdx < 0) {
      if (twoSwitchStep) {
        this.running = true;
        this.level = this.useRows() ? "row" : "item";
        if (this.level === "row") this.rowIdx = 0;
        else this.idx = 0;
        this.render();
        this.onAction({ type: "start", t, switchIndex });
        return;
      }
      this.start();
      this.onAction({ type: "start", t, switchIndex });
      return;
    }
    if (!isSelect) {
      if (!this.running) this.running = true;
      this.advance(false);
      this.onAction({ type: "step", t, switchIndex });
      return;
    }
    if (this.level === "row") {
      this.level = "item";
      this.idx = 0;
      this.cycles = 0;
      this.render();
      this.schedule();
      this.onAction({ type: "row", t, switchIndex });
      return;
    }
    const cur = this.current()[0];
    if (!cur) return;
    this.onAction({ type: "select", t, switchIndex, target: cur });
    cur.activate(t);
    // restart policy
    this.cycles = 0;
    if (this.cfg.restart === "first" || this.useRows()) {
      if (this.useRows()) {
        this.level = "row";
        this.rowIdx = 0;
        this.idx = -1;
      } else {
        this.idx = 0;
      }
    } else {
      const n = this.pool().length;
      if (this.idx >= n) this.idx = 0;
    }
    if (this.cfg.mode === "auto") {
      this.running = true;
      this.render();
      this.schedule();
    } else this.render();
  }

  /** The target list changed (new screen): restart from the first target. */
  reset(): void {
    const wasRunning = this.running;
    this.clearTimer();
    this.idx = -1;
    this.rowIdx = -1;
    this.level = "item";
    this.cycles = 0;
    if (wasRunning && this.cfg.mode === "auto") this.start();
    else {
      this.running = false;
      this.render();
    }
  }

  dispose(): void {
    this.clearTimer();
  }
}

/** Records scanner actions as canonical events (see header comment for the kinds used). */
export function recordScanAction(stream: StreamHandle, cfg: SwitchConfig, a: ScanAction, extraMeta: Record<string, unknown> = {}): void {
  if (a.type === "stopped") {
    stream.emit({ kind: "marker", meta: { marker: "scan_stopped", scan_ms: cfg.rateMs } }, { t: a.t });
    return;
  }
  const switch_id = `switch${a.switchIndex + 1}`;
  const key = cfg.keys[a.switchIndex] ?? "Space";
  if (a.type === "select" && a.target.role === "task") {
    stream.emit(
      {
        kind: "switch",
        switch_id,
        x: a.target.x,
        y: a.target.y,
        meta: { scan_action: "select", item: a.target.id, scan_ms: cfg.rateMs, scan_mode: cfg.mode, row_column: cfg.rowColumn, ...extraMeta },
      },
      { t: a.t },
    );
  } else {
    stream.emit(
      { kind: "key", key, switch_id, meta: { scan_action: a.type === "select" ? "activate_control" : a.type, scan_ms: cfg.rateMs } },
      { t: a.t },
    );
  }
}

export function switchStream(rec: EventRecorder, declared: Modality = "switch"): StreamHandle {
  return rec.stream("in:switch", declared);
}
