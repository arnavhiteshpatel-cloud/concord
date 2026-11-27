// Keyboard adapter. Records named keys (arrows, Enter, Space, Tab, Escape, Backspace...) by name.
// Printable characters are recorded ONLY when the recorder allows text (copy-typing task E1);
// otherwise they are not recorded at all (no text content outside copy typing).
// Switch interfaces that present as keys are handled by the switch adapter (switch.ts), which
// claims its configured keys before this adapter sees them.

import type { EventRecorder, StreamHandle } from "./recorder";
import type { Modality } from "./types";

const MODIFIERS = new Set(["Shift", "Control", "Alt", "Meta", "CapsLock", "AltGraph", "Fn"]);

export function keyName(ev: KeyboardEvent): string {
  if (ev.key === " ") return "Space";
  return ev.key;
}

export interface KeyboardAdapterOptions {
  recorder: EventRecorder;
  element: HTMLElement;
  modality?: Modality;
  /** Task action for a key (called after the key event, if any, has been recorded). */
  onKey?: (name: string, ev: KeyboardEvent, t: number, stream: StreamHandle) => void;
}

export class KeyboardAdapter {
  private off: (() => void)[] = [];
  readonly stream: StreamHandle;

  constructor(private o: KeyboardAdapterOptions) {
    this.stream = o.recorder.stream("in:keyboard", o.modality ?? "keyboard");
  }

  attach(): this {
    const el = this.o.element;
    const down = (ev: KeyboardEvent) => {
      if (ev.defaultPrevented) return; // claimed by the switch adapter / scanner
      const rec = this.o.recorder;
      const t = rec.clock.fromTimeStamp(ev.timeStamp);
      const name = keyName(ev);
      const printable = ev.key.length === 1 && name !== "Space";
      // Named keys are recorded by name (never text). Character keys are not recorded here: the
      // copy-typing task records them itself when (and only when) text is allowed.
      if (!rec.paused && !printable && !MODIFIERS.has(name)) {
        this.stream.emit({ kind: "key", key: name, meta: ev.repeat ? { repeat: true } : undefined }, { t });
      }
      this.o.onKey?.(name, ev, t, this.stream);
    };
    el.addEventListener("keydown", down);
    this.off.push(() => el.removeEventListener("keydown", down));
    return this;
  }

  detach(): void {
    for (const f of this.off.splice(0)) f();
  }
}
