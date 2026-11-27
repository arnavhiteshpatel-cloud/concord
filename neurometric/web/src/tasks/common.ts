// Shared helpers for task components.
import type { Trial } from "../metrics/pointing";
import type { TaskApi } from "./api";

/** Collects the observable record of one pointing trial for PROVISIONAL feedback. */
export class TrialCollector {
  private samples: { t: number; x: number; y: number }[] = [];
  active = false;
  start: [number, number] = [0, 0];
  target: [number, number] = [0, 0];
  half: [number, number] = [0, 0];

  begin(start: [number, number], target: [number, number], half: [number, number]): void {
    this.samples = [];
    this.active = true;
    this.start = start;
    this.target = target;
    this.half = half;
  }

  add(x: number, y: number, t: number): void {
    if (this.active) this.samples.push({ t, x, y });
  }

  /** Build a Trial relative to onsetT (stimulus_on). selT is absolute session time or null. */
  end(onsetT: number, selT: number | null, selPos: [number, number], selItem: number): Trial {
    this.active = false;
    const s = this.samples.filter((p) => p.t >= onsetT - 1e-9);
    const tr: Trial = {
      t_ms: s.map((p) => p.t - onsetT),
      xy: s.map((p) => [p.x, p.y] as [number, number]),
      start: this.start,
      target: this.target,
      half: this.half,
      sel_t: selT === null ? null : selT - onsetT,
      sel_pos: selPos,
      sel_item: selItem,
    };
    if (!tr.xy.length) {
      tr.t_ms = [0];
      tr.xy = [this.start];
    }
    return tr;
  }
}

export function limitN(api: TaskApi, key: "trials" | "blocks" | "n", full: number, short: number): number {
  const v = api.limits[key];
  if (v !== undefined && Number.isFinite(v) && v > 0) return Math.min(full, Math.floor(v));
  return api.settings.short ? Math.min(full, short) : full;
}

export function mean(a: number[]): number {
  const f = a.filter((v) => Number.isFinite(v));
  return f.length ? f.reduce((x, y) => x + y, 0) / f.length : NaN;
}
