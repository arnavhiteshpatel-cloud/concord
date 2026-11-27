// Pointer Events adapter (mouse, pen, touch; and anything the OS presents as a pointer: eye-gaze
// and head-pointer OS control, a BCI cursor exposed as a HID mouse). The browser cannot tell
// these apart, so the modality is DECLARED in setup and stamped on the stream; the observed
// pointerType is kept in session metadata.
//
// Listeners are attached to the task canvas element only (never window/document).
// getCoalescedEvents() is used when available so high-rate devices are not down-sampled to the
// display rate.

import type { EventRecorder, StreamHandle } from "./recorder";
import type { Modality } from "./types";
import { TASK_H, TASK_W } from "./space";

export type DeclaredPointerModality = "auto" | Modality;

export interface PointerSample {
  x: number;
  y: number;
  t: number;
}

export interface PointerAdapterOptions {
  recorder: EventRecorder;
  element: HTMLElement;
  declared?: DeclaredPointerModality;
  useCoalesced?: boolean;
  onMove?: (s: PointerSample) => void;
  onDown?: (s: PointerSample & { button: number; pointerType: string }, stream: StreamHandle) => void;
  onUp?: (s: PointerSample & { button: number }, stream: StreamHandle) => void;
  onWheel?: (dx: number, dy: number, t: number, stream: StreamHandle) => void;
  /** Observed pointer types (for metadata). */
  observed?: Set<string>;
}

export function pointerTypeToModality(pt: string): Modality {
  if (pt === "mouse") return "mouse";
  if (pt === "pen") return "pen";
  if (pt === "touch") return "touch";
  return "other";
}

/** Map client coordinates to 1280x800 task space using the element's rendered rect. */
export function toTaskSpace(rect: DOMRect, clientX: number, clientY: number): { x: number; y: number } {
  return {
    x: ((clientX - rect.left) * TASK_W) / rect.width,
    y: ((clientY - rect.top) * TASK_H) / rect.height,
  };
}

export class PointerAdapter {
  private streams = new Map<string, StreamHandle>();
  private off: (() => void)[] = [];
  last: PointerSample | null = null;
  coalescedTotal = 0;
  dispatchedTotal = 0;

  constructor(private o: PointerAdapterOptions) {}

  private streamFor(pointerType: string): StreamHandle {
    const declared = this.o.declared ?? "auto";
    const modality = declared === "auto" ? pointerTypeToModality(pointerType) : declared;
    const id = `in:pointer:${pointerType || "unknown"}`;
    let s = this.streams.get(id);
    if (!s) {
      s = this.o.recorder.stream(id, modality, modality === "simulated");
      this.streams.set(id, s);
    }
    return s;
  }

  attach(): this {
    const el = this.o.element;
    const useCoalesced = this.o.useCoalesced ?? true;
    const clock = this.o.recorder.clock;
    const move = (ev: PointerEvent) => {
      if (!ev.isPrimary || this.o.recorder.paused) return;
      this.o.observed?.add(ev.pointerType);
      const rect = el.getBoundingClientRect();
      const s = this.streamFor(ev.pointerType);
      let list: PointerEvent[] = [];
      if (useCoalesced && typeof ev.getCoalescedEvents === "function") list = ev.getCoalescedEvents();
      if (!list.length) list = [ev];
      this.dispatchedTotal++;
      this.coalescedTotal += list.length;
      for (const ce of list) {
        const p = toTaskSpace(rect, ce.clientX, ce.clientY);
        const t = clock.fromTimeStamp(ce.timeStamp);
        const e = s.emit({ kind: "pointer_move", x: p.x, y: p.y }, { t });
        if (e) {
          this.last = { x: e.x!, y: e.y!, t: e.t_ms };
          this.o.onMove?.(this.last);
        }
      }
    };
    const down = (ev: PointerEvent) => {
      if (!ev.isPrimary || this.o.recorder.paused) return;
      this.o.observed?.add(ev.pointerType);
      const rect = el.getBoundingClientRect();
      const p = toTaskSpace(rect, ev.clientX, ev.clientY);
      const s = this.streamFor(ev.pointerType);
      const e = s.emit({ kind: "pointer_down", x: p.x, y: p.y, button: ev.button }, { t: clock.fromTimeStamp(ev.timeStamp) });
      if (!e) return;
      try {
        el.setPointerCapture(ev.pointerId);
      } catch {
        /* synthetic events have no capturable pointer */
      }
      this.last = { x: e.x!, y: e.y!, t: e.t_ms };
      this.o.onDown?.({ ...this.last, button: ev.button, pointerType: ev.pointerType }, s);
    };
    const up = (ev: PointerEvent) => {
      if (!ev.isPrimary || this.o.recorder.paused) return;
      const rect = el.getBoundingClientRect();
      const p = toTaskSpace(rect, ev.clientX, ev.clientY);
      const s = this.streamFor(ev.pointerType);
      const e = s.emit({ kind: "pointer_up", x: p.x, y: p.y, button: ev.button }, { t: clock.fromTimeStamp(ev.timeStamp) });
      if (!e) return;
      this.last = { x: e.x!, y: e.y!, t: e.t_ms };
      this.o.onUp?.({ ...this.last, button: ev.button }, s);
    };
    const wheel = (ev: WheelEvent) => {
      if (this.o.recorder.paused || !this.o.onWheel) return;
      ev.preventDefault();
      const s = this.streamFor("mouse");
      const scale = ev.deltaMode === 1 ? 20 : ev.deltaMode === 2 ? 400 : 1;
      this.o.onWheel(ev.deltaX * scale, ev.deltaY * scale, clock.fromTimeStamp(ev.timeStamp), s);
    };
    el.addEventListener("pointermove", move);
    el.addEventListener("pointerdown", down);
    el.addEventListener("pointerup", up);
    el.addEventListener("wheel", wheel, { passive: false });
    this.off.push(
      () => el.removeEventListener("pointermove", move),
      () => el.removeEventListener("pointerdown", down),
      () => el.removeEventListener("pointerup", up),
      () => el.removeEventListener("wheel", wheel),
    );
    return this;
  }

  detach(): void {
    for (const f of this.off.splice(0)) f();
  }
}
