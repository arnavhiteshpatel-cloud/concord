// Canonical InputEvent schema: a TypeScript mirror of src/neurometric/events/model.py.
// Field names, enum values and validation rules are identical to the Python reference; Python
// remains the validator of record (tests/web runs neurometric.events.model.validate_event on
// every exported event).

export const SCHEMA_VERSION = "1.0";

export const EVENT_KINDS = [
  "pointer_move", "pointer_down", "pointer_up", "click", "drag_start", "drag_end", "scroll",
  "text_input", "key", "dwell_select", "switch", "select", "cancel", "pause", "resume", "assist",
  "marker",
] as const;
export type EventKind = (typeof EVENT_KINDS)[number];

export const MODALITIES = [
  "mouse", "trackpad", "touch", "pen", "keyboard", "switch", "eye_gaze", "head_pointer",
  "joystick", "gamepad", "bci_cursor", "bci_select", "simulated", "replay", "other",
] as const;
export type Modality = (typeof MODALITIES)[number];

export const SELECTION_KINDS: ReadonlySet<EventKind> = new Set<EventKind>([
  "click", "dwell_select", "select", "switch",
]);

export const ASSIST_TYPES = [
  "setup", "physical", "verbal", "troubleshooting", "calibration", "task_completion",
] as const;
export type AssistType = (typeof ASSIST_TYPES)[number];

/** Canonical event as serialised (Python InputEvent.to_dict(): None and {} are omitted). */
export interface InputEvent {
  t_ms: number;
  kind: EventKind;
  session_id: string;
  stream_id: string;
  modality: Modality;
  seq: number;
  x?: number;
  y?: number;
  dx?: number;
  dy?: number;
  button?: number;
  key?: string;
  text?: string;
  switch_id?: string;
  confidence?: number;
  calibration_state?: string;
  synthetic: boolean;
  meta?: Record<string, unknown>;
  schema_version: string;
}

export type EventInit = Omit<InputEvent, "session_id" | "stream_id" | "seq" | "schema_version" | "synthetic" | "modality"> & {
  synthetic?: boolean;
  modality?: Modality;
};

export class EventValidationError extends Error {}

const POSITIONAL: ReadonlySet<EventKind> = new Set<EventKind>([
  "pointer_move", "pointer_down", "pointer_up", "click", "dwell_select", "drag_start", "drag_end",
]);

/** Same rules as neurometric.events.model.validate_event. */
export function validateEvent(ev: InputEvent): void {
  if (typeof ev.t_ms !== "number" || !Number.isFinite(ev.t_ms) || ev.t_ms < 0)
    throw new EventValidationError(`t_ms must be a finite non-negative number, got ${ev.t_ms}`);
  if (!(EVENT_KINDS as readonly string[]).includes(ev.kind)) throw new EventValidationError(`bad kind ${ev.kind}`);
  if (!(MODALITIES as readonly string[]).includes(ev.modality)) throw new EventValidationError(`bad modality ${ev.modality}`);
  if (POSITIONAL.has(ev.kind)) {
    if (ev.x === undefined || ev.y === undefined) throw new EventValidationError(`${ev.kind} requires x and y`);
    if (!Number.isFinite(ev.x) || !Number.isFinite(ev.y)) throw new EventValidationError("x/y must be finite");
  }
  if (ev.kind === "scroll" && ev.dx === undefined && ev.dy === undefined)
    throw new EventValidationError("scroll requires dx or dy");
  if (ev.kind === "text_input" && ev.text === undefined) throw new EventValidationError("text_input requires text");
  if (ev.kind === "switch" && !ev.switch_id) throw new EventValidationError("switch requires switch_id");
  if (ev.kind === "assist") {
    const at = ev.meta?.assist_type;
    if (!(ASSIST_TYPES as readonly unknown[]).includes(at))
      throw new EventValidationError(`assist requires meta.assist_type in ${ASSIST_TYPES.join(",")}`);
  }
  if (ev.confidence !== undefined) {
    if (!(ev.confidence >= 0 && ev.confidence <= 1)) throw new EventValidationError("confidence must be within [0, 1]");
    if (!ev.meta?.confidence_source)
      throw new EventValidationError("confidence present without meta.confidence_source");
  }
  if (!ev.session_id || !ev.stream_id) throw new EventValidationError("session_id and stream_id are required");
}

/** Stable merge ordering key (t_ms, stream_id, seq), identical to merge_streams in Python. */
export function compareEvents(a: InputEvent, b: InputEvent): number {
  if (a.t_ms !== b.t_ms) return a.t_ms - b.t_ms;
  if (a.stream_id !== b.stream_id) return a.stream_id < b.stream_id ? -1 : 1;
  return a.seq - b.seq;
}

export function mergeStreams(...streams: InputEvent[][]): InputEvent[] {
  const out: InputEvent[] = [];
  for (const s of streams) for (const e of s) out.push(e);
  // Array.prototype.sort is stable (ES2019), matching Python's stable sort on equal keys.
  return out.sort(compareEvents);
}

export interface StreamReport {
  n: number;
  non_monotonic: number;
  duplicate_seq: number;
  seq_gaps: number;
  gap_events: number;
  streams: string[];
}

/** Same counts as neurometric.events.model.check_stream. */
export function checkStream(events: Iterable<InputEvent>): StreamReport {
  const lastT = new Map<string, number>();
  const lastSeq = new Map<string, number>();
  const seen = new Set<string>();
  const r: StreamReport = { n: 0, non_monotonic: 0, duplicate_seq: 0, seq_gaps: 0, gap_events: 0, streams: [] };
  const streams = new Set<string>();
  for (const ev of events) {
    r.n++;
    const s = ev.stream_id;
    streams.add(s);
    const lt = lastT.get(s);
    if (lt !== undefined && ev.t_ms < lt) r.non_monotonic++;
    lastT.set(s, Math.max(ev.t_ms, lt ?? ev.t_ms));
    const key = `${s}\u0000${ev.seq}`;
    if (seen.has(key)) r.duplicate_seq++;
    seen.add(key);
    const ls = lastSeq.get(s);
    if (ls !== undefined && ev.seq > ls + 1) {
      r.seq_gaps++;
      r.gap_events += ev.seq - ls - 1;
    }
    lastSeq.set(s, Math.max(ev.seq, ls ?? ev.seq));
  }
  r.streams = [...streams].sort();
  return r;
}
