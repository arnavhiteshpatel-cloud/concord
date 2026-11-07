// The pipeline status is shared by the Decoder and Command output rows, the title-bar Stop
// button and Advanced. Polled every second; an action's response is shown until the next poll.

import { useEffect, useState } from "react";
import { labApi, type DiscreteRule, type ModelSummary, type PipelineStatus, type RouterSpec } from "./api";
import { usePoll } from "./hooks";

export interface PipelineState {
  status: PipelineStatus | null;
  error: string | null;
  /** show an action's response immediately (superseded by the next poll) */
  set: (s: PipelineStatus) => void;
}

export function usePipeline(): PipelineState {
  const poll = usePoll("pipeline", labApi.pipeline, 1000);
  const [override, setOverride] = useState<PipelineStatus | null>(null);
  useEffect(() => setOverride(null), [poll.value]);
  return { status: override ?? poll.value, error: poll.error, set: setOverride };
}

/** The running decoder, if the pipeline runs one. */
export const runningDecoder = (s: PipelineStatus | null) => (s?.running ? s.decoder : null);

/** Class names if the decoder is a classifier (discrete decoding), else null. */
export function decoderClasses(d: Pick<ModelSummary, "outputs"> | null | undefined): string[] | null {
  return d?.outputs?.type === "classes" ? d.outputs.classes : null;
}

export const controlOn = (s: PipelineStatus | null): boolean => !!(s?.running && s.router?.enabled);

/** The router spec that turns command output off, keeping the rest of the current mapping. */
export function stopSpec(s: PipelineStatus | null): RouterSpec | null {
  const r = s?.router;
  if (!r) return null;
  return { ...r, enabled: false };
}

/** What an app sees for a discrete action. */
export function actionLabel(r: Pick<DiscreteRule, "action" | "text">): string {
  if (r.action === "text") return `text "${r.text ?? ""}"`;
  if (r.action.startsWith("navigate:")) return `move ${r.action.slice("navigate:".length)}`;
  return r.action === "primary" ? "select" : r.action;
}

export function mappingText(r: Pick<RouterSpec, "x_dim" | "y_dim" | "gain" | "invert_y" | "discrete" | "click">): string {
  const parts: string[] = [];
  if (r.x_dim && r.y_dim) parts.push(`x ← ${r.x_dim}, y ← ${r.y_dim}${r.invert_y ? " (inverted)" : ""}, gain ${r.gain}`);
  if (r.click) parts.push(`click ← ${r.click.output}`);
  for (const d of r.discrete ?? []) parts.push(`${actionLabel(d)} ← ${d.output}`);
  return parts.join("; ") || "nothing mapped";
}
