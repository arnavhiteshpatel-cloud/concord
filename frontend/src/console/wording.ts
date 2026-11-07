// Plain-language wording shared by the session screen. Everything here is derived from the
// device descriptor or server status; nothing is estimated.

import type { ConnectionStatus, DeviceDescriptor, RuntimeSnapshot } from "../sdk";
import { isLiveSource } from "./api";

export type Tone = "ok" | "caution" | "alarm" | "info" | "inactive";

/** What kind of data the connected source produces — derived only from the descriptor. */
export function sourceKind(device: DeviceDescriptor | null | undefined): { text: string; title: string } | null {
  if (!device) return null;
  if (device.synthetic)
    return { text: "Simulated data", title: "The connected source generates synthetic data" };
  if (device.kind === "stream")
    return {
      text: "Live stream, origin unverified",
      title: "External live stream: BrainOS cannot verify whether it comes from hardware, a file player or a simulator",
    };
  if (device.kind === "replay" && isLiveSource(device))
    // An external stream whose publisher declares prerecorded content: the declaration is not
    // verifiable, and the publisher's stream name never makes it "human".
    return {
      text: "Recorded data, streamed replay (declared)",
      title: "The publisher declares that this live stream replays prerecorded data — not a live implant",
    };
  if (device.kind === "replay") {
    const human = /human/i.test(device.display_name);
    return {
      text: human ? "Recorded human data, offline replay" : "Recorded data, offline replay",
      title: "Genuine recorded data replayed from a file — not a live implant",
    };
  }
  return { text: "Device data", title: "Non-synthetic data from a connected device" };
}

/** The title-bar status line: one plain sentence and a status tone. */
export function statusLine(conn: ConnectionStatus, runtime: RuntimeSnapshot | null): { text: string; tone: Tone } {
  if (conn === "connecting" || conn === "idle") return { text: "Connecting to BrainOS", tone: "info" };
  if (conn === "reconnecting") return { text: "Connection to BrainOS lost, reconnecting", tone: "caution" };
  if (conn !== "open" || !runtime) return { text: "Not connected to BrainOS", tone: "caution" };
  const kind = sourceKind(runtime.device)?.text;
  switch (runtime.state) {
    case "idle":
      return { text: "No source connected", tone: "inactive" };
    case "connecting":
      return { text: "Connecting to the source", tone: "info" };
    case "streaming":
      return { text: kind ? `Streaming · ${kind}` : "Streaming", tone: "ok" };
    case "paused":
      return { text: kind ? `Paused · ${kind}` : "Paused", tone: "caution" };
    case "reconnecting":
      return { text: "Source link lost, reconnecting", tone: "caution" };
    case "disconnecting":
      return { text: "Disconnecting", tone: "info" };
    case "error":
      return { text: "Source stopped with an error", tone: "alarm" };
    case "ended":
      return { text: "Source ended", tone: "inactive" };
  }
}

const PRESETS: Record<string, string> = {
  spikeband_threshold: "Spike-band threshold crossings",
  ecog_high_gamma: "High-gamma band power",
  band_power: "Band power",
  features_passthrough: "Source features (passthrough)",
};
export const presetLabel = (p: string | null | undefined): string => (p ? (PRESETS[p] ?? p) : "—");

function capParam(device: DeviceDescriptor | null | undefined, cap: string, key: string): number | null {
  const v = device?.capabilities.find((c) => c.capability === cap)?.params[key];
  return typeof v === "number" && Number.isFinite(v) ? v : null;
}

/** Channels the source declares: raw recording channels, else binned-feature channels. */
export function declaredChannels(device: DeviceDescriptor | null | undefined): number | null {
  return capParam(device, "recording", "channel_count") ?? capParam(device, "neural_features", "channel_count");
}

export function sampleRate(device: DeviceDescriptor | null | undefined): number | null {
  return capParam(device, "recording", "sample_rate_hz");
}

export const hasCapability = (device: DeviceDescriptor | null | undefined, cap: string): boolean =>
  !!device?.capabilities.some((c) => c.capability === cap);

/** "32 channels · 1,000 Hz" / "176 channels · 20 ms bins" — only what the descriptor declares. */
export function shapeSummary(device: DeviceDescriptor | null | undefined): string {
  const ch = declaredChannels(device);
  const parts: string[] = [];
  if (ch !== null) parts.push(`${ch.toLocaleString()} channels`);
  const fs = sampleRate(device);
  if (fs !== null) parts.push(`${fs.toLocaleString()} Hz`);
  else {
    const bin = capParam(device, "neural_features", "bin_ms");
    if (bin !== null) parts.push(`${bin} ms bins`);
  }
  return parts.join(" · ");
}

/** The default processing preset for a source (the operator can change it). */
export function defaultPreset(device: DeviceDescriptor | null | undefined): string {
  if (hasCapability(device, "neural_features")) return "features_passthrough";
  const fs = sampleRate(device);
  if (fs !== null && fs >= 10_000) return "spikeband_threshold";
  if (fs !== null && fs >= 400) return "ecog_high_gamma";
  return "band_power";
}

export function capitalize(s: string): string {
  return s ? s[0]!.toUpperCase() + s.slice(1) : s;
}

/** A server message as a sentence: capitalised, ending with a full stop. */
export function sentence(s: string): string {
  const t = capitalize(s.trim());
  return /[.!?]$/.test(t) ? t : `${t}.`;
}
