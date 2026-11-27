// Session clock + event recorder: the single point where every adapter's output becomes a
// canonical InputEvent. Each adapter owns one or more streams; each stream has its own seq
// counter and a per-stream monotonic clamp. Merged order is (t_ms, stream_id, seq).
//
// Stream naming rule: input streams are "in:<source>" and the task-engine marker stream is
// "task" and session control (pause/resume/assist) is "ctl". Because "ctl" < "in:" < "task" in
// code-unit order, at an identical t_ms a selection always sorts before the trial_end /
// stimulus_on markers the task emits in response to it (see docs/science/INPUT_ABSTRACTION.md).

import { InputEvent, EventInit, Modality, SCHEMA_VERSION, compareEvents, validateEvent } from "./types";

export interface Clock {
  /** Session-relative monotonic ms (performance.now() based). */
  now(): number;
  /** Convert a DOMHighResTimeStamp (Event.timeStamp / rAF ts / Gamepad.timestamp) to session ms. */
  fromTimeStamp(ts: number): number;
  /** performance.now() value of session t_ms = 0. */
  readonly origin: number;
}

export function makeClock(origin: number = performance.now()): Clock {
  return {
    origin,
    now: () => performance.now() - origin,
    fromTimeStamp: (ts: number) => ts - origin,
  };
}

export function newId(prefix = "s"): string {
  const c = globalThis.crypto;
  if (c && "randomUUID" in c) return `${prefix}_${c.randomUUID()}`;
  return `${prefix}_${Date.now().toString(36)}_${Math.floor(Math.random() * 1e9).toString(36)}`;
}

interface StreamState {
  id: string;
  modality: Modality;
  synthetic: boolean;
  seq: number;
  lastT: number;
  clamped: number;
}

export interface EmitOptions {
  /** Explicit session time (ms). Defaults to clock.now(). */
  t?: number;
}

export type EventListenerFn = (ev: InputEvent, createdAtNow: number) => void;

export class StreamHandle {
  constructor(private rec: EventRecorder, readonly state: StreamState) {}
  get id(): string {
    return this.state.id;
  }
  get modality(): Modality {
    return this.state.modality;
  }
  set modality(m: Modality) {
    this.state.modality = m;
  }
  emit(init: EventInit, opts: EmitOptions = {}): InputEvent | null {
    return this.rec.emitOn(this.state, init, opts);
  }
}

export interface RecorderOptions {
  sessionId?: string;
  clock?: Clock;
  /** Copy-typing tasks only: allow text content in text_input / key events. */
  allowText?: boolean;
  /** Validate every event as it is created (cheap; on by default). */
  validate?: boolean;
}

export class TextNotAllowedError extends Error {}

export class EventRecorder {
  readonly sessionId: string;
  readonly clock: Clock;
  allowText: boolean;
  private validate: boolean;
  private streams = new Map<string, StreamState>();
  private events: InputEvent[] = [];
  private listeners = new Set<EventListenerFn>();
  private outOfOrder = false;
  paused = false;

  constructor(opts: RecorderOptions = {}) {
    this.sessionId = opts.sessionId ?? newId("sess");
    this.clock = opts.clock ?? makeClock();
    this.allowText = opts.allowText ?? false;
    this.validate = opts.validate ?? true;
  }

  stream(id: string, modality: Modality, synthetic = false): StreamHandle {
    let st = this.streams.get(id);
    if (!st) {
      st = { id, modality, synthetic, seq: 0, lastT: -Infinity, clamped: 0 };
      this.streams.set(id, st);
    } else {
      st.modality = modality;
      st.synthetic = synthetic;
    }
    return new StreamHandle(this, st);
  }

  onEvent(fn: EventListenerFn): () => void {
    this.listeners.add(fn);
    return () => this.listeners.delete(fn);
  }

  emitOn(st: StreamState, init: EventInit, opts: EmitOptions): InputEvent | null {
    const createdAtNow = performance.now();
    let t = opts.t ?? createdAtNow - this.clock.origin;
    if (t < 0) t = 0;
    let meta = init.meta;
    if (t < st.lastT) {
      // Per-stream monotonic clamp. Recorded so the original order problem stays visible.
      meta = { ...(meta ?? {}), t_clamped_ms: st.lastT - t };
      t = st.lastT;
      st.clamped++;
    }
    if (!this.allowText && (init.kind === "text_input" || (init.kind === "key" && init.key && init.key.length === 1))) {
      throw new TextNotAllowedError("text content is only recorded in copy-typing tasks");
    }
    const ev: InputEvent = {
      t_ms: t,
      kind: init.kind,
      session_id: this.sessionId,
      stream_id: st.id,
      modality: init.modality ?? st.modality,
      seq: st.seq++,
      synthetic: init.synthetic ?? st.synthetic,
      schema_version: SCHEMA_VERSION,
    };
    for (const k of ["x", "y", "dx", "dy", "button", "key", "text", "switch_id", "confidence", "calibration_state"] as const) {
      const v = init[k];
      if (v !== undefined && v !== null) (ev as unknown as Record<string, unknown>)[k] = v;
    }
    if (meta && Object.keys(meta).length) ev.meta = meta;
    if (this.validate) validateEvent(ev);
    st.lastT = t;
    const prev = this.events[this.events.length - 1];
    if (prev && compareEvents(prev, ev) > 0) this.outOfOrder = true;
    this.events.push(ev);
    for (const fn of this.listeners) fn(ev, createdAtNow);
    return ev;
  }

  /** Merged session timeline, stable (t_ms, stream_id, seq) order. */
  merged(): InputEvent[] {
    if (this.outOfOrder) {
      this.events.sort(compareEvents);
      this.outOfOrder = false;
    }
    return this.events;
  }

  get length(): number {
    return this.events.length;
  }

  streamStats(): Record<string, { modality: Modality; n: number; clamped: number; synthetic: boolean }> {
    const out: Record<string, { modality: Modality; n: number; clamped: number; synthetic: boolean }> = {};
    for (const s of this.streams.values()) out[s.id] = { modality: s.modality, n: s.seq, clamped: s.clamped, synthetic: s.synthetic };
    return out;
  }
}
