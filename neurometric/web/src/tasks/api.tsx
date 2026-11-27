// Contract between the task runner (input pipeline, pause/assist, scanning, recording) and the
// individual task components. Tasks never touch DOM listeners or adapters directly.

import { memo } from "react";
import type { StreamHandle } from "../input/recorder";
import type { InputEvent } from "../input/types";
import type { Settings } from "../a11y/settings";
import type { Stimuli } from "./stimuli";
import type { ProvisionalSummary, TaskSession } from "./session";

export interface TaskItem {
  id: string;
  x: number; // centre, task space
  y: number;
  w: number;
  h: number;
  label?: string;
  row?: number; // row-column scanning group
  shape?: "circle" | "rect";
}

export type SelectVia = "click" | "dwell" | "switch" | "keyboard" | "gamepad";

export interface Selection {
  t: number;
  x: number;
  y: number;
  item: TaskItem | null;
  via: SelectVia;
  event: InputEvent | null;
}

export interface TaskHandlers {
  onSelect?: (s: Selection) => void;
  onMove?: (x: number, y: number, t: number) => void;
  /** Raw pointer tasks (D1 drag) receive presses/releases instead of click selections. */
  rawPointer?: boolean;
  onPointerDown?: (x: number, y: number, t: number, stream: StreamHandle) => void;
  onPointerUp?: (x: number, y: number, t: number, stream: StreamHandle) => void;
  onWheel?: (dx: number, dy: number, t: number, stream: StreamHandle) => void;
  /** Return true when the key was used by the task. */
  onKey?: (name: string, ev: KeyboardEvent, t: number, stream: StreamHandle) => boolean | void;
  onPause?: () => void;
  onResume?: () => void;
  /** Selections on empty space end the trial (ISO sequences) instead of being counted only. */
  emptyEndsTrial?: boolean;
  /** Keyboard users steer a virtual cursor with the arrow keys (pointing tasks). */
  virtualCursor?: boolean;
  /** Extra meta for a selection event (e.g. {correct: false} in digital-ADL tasks). */
  selectMeta?: (item: TaskItem | null) => Record<string, unknown>;
  /** Skip the current trial (recorded as trial_end outcome "abandoned"). */
  onSkip?: () => void;
  /** Provisional summary of the trials so far (used when the task is stopped early). */
  summarize?: () => ProvisionalSummary;
}

/** Short-configuration limits (practice runs, automated tests): ?trials=&blocks=&n= */
export interface Limits {
  trials?: number;
  blocks?: number;
  n?: number;
}

export interface TaskApi {
  session: TaskSession;
  stim: Stimuli;
  settings: Settings;
  reducedMotion: boolean;
  now(): number;
  paused(): boolean;
  setInstruction(text: string): void;
  announce(text: string): void;
  setItems(items: TaskItem[]): void;
  handlers: TaskHandlers;
  finish(summary: ProvisionalSummary): void;
  pointer(): { x: number; y: number } | null;
  /** Programmatic selection of an item (keyboard activation of an item button). */
  keyboardSelect(item: TaskItem): void;
  /** Per-frame callback (rAF), returns an unsubscribe function. */
  onFrame(fn: (t: number, rafTs: number) => void): () => void;
  /** Emit stimulus_on on the frame that first shows the stimulus. */
  stimulusOnNextFrame(meta: Record<string, unknown>): void;
  timeLimit(ms: number): number;
  limits: Limits;
}

export const ItemButton = memo(function ItemButton(props: {
  api: TaskApi;
  item: TaskItem;
  className?: string;
  children?: React.ReactNode;
  pressed?: boolean;
  describedBy?: string;
}) {
  const { api, item, className, children, pressed, describedBy } = props;
  const kb = api.settings.selection === "keyboard";
  return (
    <button
      type="button"
      data-item-id={item.id}
      className={`titem ${item.shape === "circle" ? "circle" : ""} ${className ?? ""}`}
      style={{ left: item.x, top: item.y, width: item.w, height: item.h }}
      tabIndex={kb ? 0 : -1}
      aria-label={item.label}
      aria-pressed={pressed}
      aria-describedby={describedBy}
      onClick={(e) => {
        // Pointer clicks are handled geometrically by the runner (detail >= 1). Keyboard and
        // screen-reader activation (detail 0) is a selection of this item.
        if (e.detail === 0) api.keyboardSelect(item);
      }}
    >
      {children ?? item.label}
    </button>
  );
});

export function hitTest(items: TaskItem[], x: number, y: number): TaskItem | null {
  // Rectangular hit test, identical to the scorer and simulator (circles use their bounding square).
  for (const it of items) if (Math.abs(x - it.x) <= it.w / 2 && Math.abs(y - it.y) <= it.h / 2) return it;
  return null;
}

export function fmt(v: number, digits = 2): string {
  return Number.isFinite(v) ? v.toFixed(digits) : "n/a";
}
