// Simulated streams and replay of recorded event logs.
//
// * SimulatedPointerStream: emits pointer_move samples from a function of time at a fixed rate
//   (modality "simulated", synthetic = true). Can run in real time (timer) or be pumped to a
//   given session time (fast-forward, used by tests and the long-session stability run).
// * replayEvents: re-emits a recorded canonical log into a new recorder with modality "replay"
//   (original modality kept in meta), preserving relative timing (optionally time-scaled).

import type { EventRecorder, StreamHandle } from "./recorder";
import type { InputEvent } from "./types";

export type PathFn = (tMs: number) => { x: number; y: number } | null;

export class SimulatedPointerStream {
  readonly stream: StreamHandle;
  private timer: ReturnType<typeof setInterval> | null = null;
  private nextT: number;
  emitted = 0;

  constructor(private rec: EventRecorder, id: string, private path: PathFn, private rateHz: number, t0?: number) {
    this.stream = rec.stream(`in:sim:${id}`, "simulated", true);
    this.nextT = t0 ?? rec.clock.now();
  }

  /** Emit all samples up to session time tEnd (inclusive). */
  pumpTo(tEnd: number): number {
    const dt = 1000 / this.rateHz;
    let n = 0;
    while (this.nextT <= tEnd) {
      const p = this.path(this.nextT);
      if (p) {
        this.stream.emit({ kind: "pointer_move", x: p.x, y: p.y }, { t: this.nextT });
        n++;
      }
      this.nextT += dt;
    }
    this.emitted += n;
    return n;
  }

  start(): void {
    this.timer = setInterval(() => this.pumpTo(this.rec.clock.now()), Math.max(4, 1000 / this.rateHz));
  }

  stop(): void {
    if (this.timer) clearInterval(this.timer);
    this.timer = null;
  }
}

export interface ReplayOptions {
  speed?: number; // 1 = real time; Infinity = all at once
  t0?: number; // session time of the first replayed event
  onEvent?: (ev: InputEvent) => void;
}

/** Map a recorded event to its replay form (stream "in:replay:<orig>", modality "replay"). */
function replayInit(ev: InputEvent): { stream: string; init: Parameters<StreamHandle["emit"]>[0] } {
  const meta: Record<string, unknown> = { ...(ev.meta ?? {}), original_modality: ev.modality, original_session_id: ev.session_id, original_seq: ev.seq };
  const init: Parameters<StreamHandle["emit"]>[0] = { kind: ev.kind, meta, synthetic: ev.synthetic };
  for (const k of ["x", "y", "dx", "dy", "button", "key", "text", "switch_id", "confidence", "calibration_state"] as const) {
    if (ev[k] !== undefined) (init as Record<string, unknown>)[k] = ev[k];
  }
  const orig = ev.stream_id.replace(/^in:/, "");
  const stream = ev.kind === "marker" ? "task" : `in:replay:${orig}`;
  return { stream, init };
}

/**
 * Replay a recorded log. With speed = Infinity everything is emitted synchronously and the
 * returned promise resolves immediately; otherwise events are scheduled with setTimeout.
 */
export function replayEvents(rec: EventRecorder, events: InputEvent[], o: ReplayOptions = {}): Promise<number> {
  const speed = o.speed ?? 1;
  const t0 = o.t0 ?? rec.clock.now();
  const base = events.length ? events[0].t_ms : 0;
  const streams = new Map<string, StreamHandle>();
  const get = (id: string) => {
    let s = streams.get(id);
    if (!s) streams.set(id, (s = rec.stream(id, "replay")));
    return s;
  };
  const emitOne = (ev: InputEvent) => {
    const { stream, init } = replayInit(ev);
    const t = t0 + (ev.t_ms - base) / (Number.isFinite(speed) ? speed : 1);
    const out = get(stream).emit(init, { t });
    if (out) o.onEvent?.(out);
  };
  if (!Number.isFinite(speed)) {
    for (const ev of events) emitOne(ev);
    return Promise.resolve(events.length);
  }
  return new Promise((resolve) => {
    let i = 0;
    const step = () => {
      const now = rec.clock.now();
      while (i < events.length && t0 + (events[i].t_ms - base) / speed <= now) emitOne(events[i++]);
      if (i >= events.length) resolve(events.length);
      else setTimeout(step, Math.max(0, t0 + (events[i].t_ms - base) / speed - now));
    };
    step();
  });
}
