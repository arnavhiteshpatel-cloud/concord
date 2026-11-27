// Dwell selection: holding the pointer on one item for `thresholdMs` selects it (eye-gaze and
// head-pointer style). The dwell timer resets when the pointer leaves the item. After a dwell
// selection the same item must be left before it can be dwell-selected again (prevents repeated
// "Midas touch" activations). A visible progress ring is driven by onProgress.
//
// The dwell_select event is stamped at the exact moment the threshold elapsed
// (entry time + threshold), independent of the frame on which it was detected.

export interface DwellHit {
  id: string;
  x: number; // item centre (task space)
  y: number;
}

export interface DwellOptions {
  thresholdMs: number;
  hitTest: (x: number, y: number) => DwellHit | null;
  onProgress?: (hit: DwellHit | null, fraction: number, px: number, py: number) => void;
  onSelect: (hit: DwellHit, t: number, px: number, py: number) => void;
}

export class DwellSelector {
  private cur: DwellHit | null = null;
  private enterT = 0;
  private fired = false;
  private px = 0;
  private py = 0;
  resets = 0;

  constructor(public o: DwellOptions) {}

  /** Feed a pointer sample (task space, session ms). */
  update(x: number, y: number, t: number): void {
    this.px = x;
    this.py = y;
    const hit = this.o.hitTest(x, y);
    if (!hit || !this.cur || hit.id !== this.cur.id) {
      if (this.cur && !this.fired) this.resets++;
      this.cur = hit;
      this.enterT = t;
      this.fired = false;
    }
    this.tick(t);
  }

  /** Advance time without movement (call from requestAnimationFrame). */
  tick(t: number): void {
    if (!this.cur) {
      this.o.onProgress?.(null, 0, this.px, this.py);
      return;
    }
    if (this.fired) {
      this.o.onProgress?.(this.cur, 0, this.px, this.py);
      return;
    }
    const frac = Math.min(1, Math.max(0, (t - this.enterT) / this.o.thresholdMs));
    this.o.onProgress?.(this.cur, frac, this.px, this.py);
    if (t - this.enterT >= this.o.thresholdMs) {
      this.fired = true;
      this.o.onSelect(this.cur, this.enterT + this.o.thresholdMs, this.px, this.py);
    }
  }

  /** Forget the current item (e.g. the screen changed). The pointer must re-enter an item. */
  reset(t: number, rearmCurrent = false): void {
    const hit = this.o.hitTest(this.px, this.py);
    this.cur = hit;
    this.enterT = t;
    this.fired = !rearmCurrent && hit !== null;
  }
}
