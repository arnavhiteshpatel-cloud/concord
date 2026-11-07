// Plain-language wording for decoders (Milestone 5). Everything is derived from what the
// server reports (decoding/registry.py, runtime/pipeline.py); nothing is estimated here.

import type { ModelSummary, PipelineStatus } from "./api";

/** "BrainOS-trained" / "Plugin" / "Imported model file" / "External decoder" / historical replay. */
export function originLabel(origin: string | null | undefined): string {
  switch (origin) {
    case "brainos-trained":
      return "BrainOS-trained";
    case "imported":
      return "Imported model file";
    case "plugin":
      return "Decoder plugin";
    case "historical":
      return "Historical decoder replay (original research system)";
    case "external":
      return "External decoder";
    default:
      return origin ?? "unknown origin";
  }
}

const FAMILY: Record<string, string> = {
  ridge: "ridge regression",
  lda: "LDA classifier",
  kalman: "Kalman filter",
  click: "click classifier",
  onnx: "ONNX",
  sklearn: "scikit-learn",
  torchscript: "TorchScript",
  decoded_passthrough: "source decoder outputs",
};

export const familyLabel = (f: string | null | undefined): string => (f ? (FAMILY[f] ?? f) : "—");

/** "BrainOS-trained · ridge regression · in BrainOS" / "Decoder plugin · … · isolated process". */
export function decoderLine(d: Pick<ModelSummary, "origin" | "family" | "execution">): string {
  const where = d.execution === "isolated" ? "isolated process" : d.execution === "in_process" ? "in BrainOS" : null;
  return [originLabel(d.origin), familyLabel(d.family), where].filter(Boolean).join(" · ");
}

/** What the running decoders' drift monitors say, as one line (null when nothing to say). */
export function driftLine(s: PipelineStatus | null): { text: string; tone: "ok" | "caution" | "inactive" } | null {
  const decs = s?.running ? (s.decoders ?? []) : [];
  const mons = decs.map((d) => d.monitor).filter((m): m is NonNullable<typeof m> => !!m);
  if (!mons.length) return null;
  if (mons.some((m) => m.recalibration_recommended)) {
    const reasons = mons.flatMap((m) => m.reasons);
    return { text: `Recalibration recommended: ${reasons[0] ?? "drift detected"}`, tone: "caution" };
  }
  if (mons.every((m) => !m.features.available)) {
    return { text: `Drift monitor: ${mons[0]!.features.reason ?? "no training statistics"}`, tone: "inactive" };
  }
  const bins = Math.min(...mons.map((m) => m.bins));
  const enough = mons.every((m) => m.bins >= Math.min(200, m.window_bins));
  return enough
    ? { text: "No drift from the training data detected", tone: "ok" }
    : { text: `Drift monitor warming up (${bins} bins)`, tone: "inactive" };
}

/** A manifest's input, in words: "threshold crossing count · 20 ms · 4 ch (labelled)". */
export function inputWords(i: { feature?: string; bin_ms?: number; channel_count?: number; channel_labels?: string[] | null; inferred?: boolean } | null | undefined): string {
  if (!i) return "?";
  const labels = i.channel_labels?.length ? "labelled" : "positional";
  return `${i.feature?.replace(/_/g, " ") ?? "?"} · ${i.bin_ms ?? "?"} ms · ${i.channel_count ?? "?"} ch (${labels})${i.inferred ? " (inferred)" : ""}`;
}
