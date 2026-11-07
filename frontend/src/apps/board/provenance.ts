// Communication board — where the input comes from, in plain words, and the scientific
// limitation on attributing composed text. Pure.

import type { EventEnvelope, Provenance } from "../../sdk";

export interface InputTag {
  kind: Provenance["kind"];
  modelId: string | null;
  modelOrigin: "brainos" | "external" | "historical" | null;
  replayed: boolean;
  synthetic: boolean;
  adapter: string;
}

/** A reference to the event that caused a board action (for the evaluation snapshot). */
export interface EventRef {
  seq: number;
  sessionId: string;
  timestampNs: number;
  deviceTimestampNs: number | null;
  eventType: string;
  input: InputTag;
}

export function tagOf(e: EventEnvelope): InputTag {
  const p = e.provenance;
  return {
    kind: p.kind,
    modelId: p.model_id,
    modelOrigin: p.model_origin ?? null,
    replayed: p.replayed,
    synthetic: p.synthetic,
    adapter: p.adapter,
  };
}

export function refOf(e: EventEnvelope): EventRef {
  return {
    seq: e.seq,
    sessionId: e.session_id,
    timestampNs: e.timestamp_ns,
    deviceTimestampNs: e.device_timestamp_ns,
    eventType: e.event_type,
    input: tagOf(e),
  };
}

/** "simulated input", "decoded by m1 (BrainOS)", "historical decoder replay (original research system)", … */
export function inputLabel(t: InputTag): string {
  if (t.kind === "simulated_intent") return "simulated input";
  if (t.kind === "decoded_intent") {
    if (t.modelOrigin === "historical") return "historical decoder replay (original research system)";
    if (t.modelOrigin === "external") return `decoded by ${t.modelId ?? "an external decoder"} (external decoder)`;
    // only the BrainOS pipeline's command router emits decoded commands without an origin
    if (t.modelOrigin === "brainos" || t.adapter.startsWith("brainos.pipeline")) return `decoded by ${t.modelId} (BrainOS)`;
    return `decoded by ${t.modelId}`;
  }
  return t.kind.replace(/_/g, " ");
}

/** Qualifiers shown next to the label: what the underlying data is. */
export function dataQualifiers(t: InputTag): string[] {
  const q: string[] = [];
  if (t.replayed) q.push("recorded data replay");
  if (t.synthetic) q.push("synthetic data");
  return q;
}

/**
 * Text composed from replayed recordings is a demonstration: the person recorded did another
 * task (e.g. a cursor task), so the text is never their message.
 */
export const DEMONSTRATION_LABEL = "demonstration — not the participant's message";
export const SIMULATION_LABEL = "simulated input — no participant";

export function isDemonstration(t: InputTag): boolean {
  return t.replayed || t.modelOrigin === "historical";
}

export function compositionLabel(sources: readonly InputTag[]): string | null {
  if (sources.some(isDemonstration)) return DEMONSTRATION_LABEL;
  if (sources.length && sources.every((s) => s.kind === "simulated_intent" || s.synthetic)) return SIMULATION_LABEL;
  return null;
}
