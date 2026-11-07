// Signal integrity verdict and the numbers behind it. Every input is a real measurement:
// time since the last data event arrived in this tab, the runtime state, and loss counters
// reported by the adapter, the pipeline, the runtime and this tab's own stream tracker.

import type { RuntimeState } from "../sdk";
import type { Tone } from "./wording";

/** Event types that carry the neural signal itself (raw samples or binned features). */
export const DATA_EVENT_TYPES = new Set(["recording.frame", "features.binned", "features.vector"]);

export const NO_SIGNAL_AFTER_MS = 2000;
export const GAP_WINDOW_MS = 10_000;

export const VERDICT_RULE =
  "Interrupted — reconnecting: the runtime is reconnecting to the source. " +
  "Paused: the operator paused the source. " +
  "No signal: no raw-signal or feature event arrived in the last 2 s. " +
  "Gaps detected: a loss counter (stream gaps, estimated missing samples, missed messages, " +
  "incomplete blocks, pipeline dropped inputs, dropped deliveries) increased in the last 10 s. " +
  "Good: none of the above.";

export interface VerdictInput {
  connected: boolean;
  state: RuntimeState | null;
  /** ms since the last data event of the current session arrived; null: none yet */
  msSinceData: number | null;
  /** ms since a loss counter last increased; null: never in this session */
  msSinceLoss: number | null;
}

/**
 * The verdict, in priority order (see VERDICT_RULE, also shown as the tooltip):
 *  reconnecting -> "Interrupted — reconnecting"; paused -> "Paused";
 *  no data event in the last 2 s -> "No signal"; a loss counter rose in the last 10 s ->
 *  "Gaps detected"; otherwise "Good".
 */
export function integrityVerdict(i: VerdictInput): { text: string; tone: Tone } {
  if (!i.connected) return { text: "No signal", tone: "inactive" };
  if (i.state === "reconnecting") return { text: "Interrupted — reconnecting", tone: "caution" };
  if (i.state === "paused") return { text: "Paused", tone: "inactive" };
  if (i.msSinceData === null || i.msSinceData > NO_SIGNAL_AFTER_MS) return { text: "No signal", tone: "caution" };
  if (i.msSinceLoss !== null && i.msSinceLoss <= GAP_WINDOW_MS) return { text: "Gaps detected", tone: "caution" };
  return { text: "Good", tone: "ok" };
}

type Obj = Record<string, unknown>;
const isObj = (v: unknown): v is Obj => typeof v === "object" && v !== null && !Array.isArray(v);
const num = (v: unknown): number => (typeof v === "number" && Number.isFinite(v) ? v : 0);

/** Adapter counters whose increase means data was lost (LSL `stats`, Open Ephys `counters`). */
const LOSS_KEYS = [
  "gaps",
  "estimated_missing_samples",
  "lost",
  "missed_messages",
  "missing_samples",
  "incomplete_blocks",
];

export function liveCounters(meta: Obj | null | undefined): Obj | null {
  if (!meta) return null;
  return isObj(meta.stats) ? meta.stats : isObj(meta.counters) ? meta.counters : null;
}

export function lossTotal(parts: {
  liveMeta: Obj | null;
  pipelineDropped: number;
  subscriberDrops: number;
  streamMissed: number;
}): number {
  const c = liveCounters(parts.liveMeta);
  const adapter = c ? LOSS_KEYS.reduce((a, k) => a + num(c[k]), 0) : 0;
  return adapter + parts.pipelineDropped + parts.subscriberDrops + parts.streamMissed;
}

/**
 * Percentage of data received, only where the source reports both sides:
 * LSL samples vs estimated missing samples; Open Ephys data messages vs missed messages.
 * null: the source reports nothing to compute it from (shown as "—", never estimated).
 */
export function dataReceived(meta: Obj | null | undefined): { pct: number; basis: string } | null {
  const c = liveCounters(meta);
  if (!c) return null;
  if (typeof c.samples === "number" && typeof c.estimated_missing_samples === "number") {
    const total = c.samples + c.estimated_missing_samples;
    if (total <= 0) return null;
    return { pct: (100 * c.samples) / total, basis: "samples received vs samples estimated missing (LSL)" };
  }
  if (typeof c.data_messages === "number" && typeof c.missed_messages === "number") {
    const total = c.data_messages + c.missed_messages;
    if (total <= 0) return null;
    return { pct: (100 * c.data_messages) / total, basis: "data messages received vs missed (Open Ephys)" };
  }
  return null;
}

/** Remembers when a cumulative loss total last increased; a new key (session) starts afresh. */
export class LossTracker {
  private key: string | null = null;
  private last = 0;
  lastIncreaseAt: number | null = null;

  update(key: string | null, total: number, now: number): number | null {
    if (key !== this.key) {
      this.key = key;
      this.last = total;
      this.lastIncreaseAt = null;
      return null;
    }
    if (total > this.last) this.lastIncreaseAt = now;
    this.last = total;
    return this.lastIncreaseAt === null ? null : now - this.lastIncreaseAt;
  }
}
