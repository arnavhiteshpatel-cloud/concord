// The pipeline status is shared by the Decoder and Command output rows, the title-bar Stop
// button and Advanced. Polled every second; an action's response is shown until the next poll.

import { useEffect, useState } from "react";
import { labApi, type PipelineStatus, type RouterSpec } from "./api";
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

export const controlOn = (s: PipelineStatus | null): boolean => !!(s?.running && s.router?.enabled);

/** The router spec that turns command output off, keeping the rest of the current mapping. */
export function stopSpec(s: PipelineStatus | null): RouterSpec | null {
  const r = s?.router;
  if (!r) return null;
  return { ...r, enabled: false };
}

export function mappingText(r: Pick<RouterSpec, "x_dim" | "y_dim" | "gain" | "invert_y">): string {
  return `x ← ${r.x_dim}, y ← ${r.y_dim}${r.invert_y ? " (inverted)" : ""}, gain ${r.gain}`;
}
