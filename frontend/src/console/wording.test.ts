// Wording on the session screen: data-kind honesty labels, the status line, preset defaults,
// the integrity verdict rules and session-log lines.
import { describe, expect, it } from "vitest";
import type { DeviceDescriptor, RuntimeSnapshot } from "../sdk";
import { LossTracker, dataReceived, integrityVerdict, lossTotal } from "./integrity";
import { errorEntry, statusEntry } from "./sessionLog";
import { defaultPreset, shapeSummary, sourceKind, statusLine } from "./wording";

const dev = (over: Partial<DeviceDescriptor>): DeviceDescriptor => ({
  device_id: "x",
  display_name: "X",
  kind: "simulated",
  adapter: "a@1.0.0",
  description: "",
  native_format: "",
  capabilities: [],
  synthetic: true,
  ...over,
});
const rt = (state: RuntimeSnapshot["state"], device: DeviceDescriptor | null = dev({})): RuntimeSnapshot => ({
  state,
  device,
  session_id: "ses_1",
  state_since_ns: 1,
  last_error: null,
  recording: null,
  apps: [],
});

describe("sourceKind (the data-kind label must never overstate)", () => {
  it("labels simulated devices as simulated", () => {
    expect(sourceKind(dev({}))?.text).toBe("Simulated data");
  });
  it("labels human recordings as recorded human data, offline", () => {
    const d = dev({ kind: "replay", synthetic: false, display_name: "Recorded Human Intracranial Data — Offline Replay" });
    expect(sourceKind(d)?.text).toBe("Recorded human data, offline replay");
  });
  it("does not call a non-human recording human", () => {
    const d = dev({ kind: "replay", synthetic: false, display_name: "Recorded Neural Data — Offline Replay" });
    expect(sourceKind(d)?.text).toBe("Recorded data, offline replay");
  });
  it("does not call a non-synthetic live device a replay", () => {
    expect(sourceKind(dev({ kind: "hardware", synthetic: false }))?.text).not.toMatch(/replay/i);
  });
  it("labels an external stream of unverifiable origin as such", () => {
    expect(sourceKind(dev({ device_id: "lsl:ephys", kind: "stream", synthetic: false }))?.text).toBe(
      "Live stream, origin unverified",
    );
    expect(sourceKind(dev({ device_id: "openephys:127.0.0.1:5556", kind: "stream", synthetic: false }))?.text).toBe(
      "Live stream, origin unverified",
    );
  });
  it("keeps 'simulated' for an LSL stream declared synthetic", () => {
    expect(sourceKind(dev({ device_id: "lsl:syn", kind: "simulated", synthetic: true }))?.text).toBe("Simulated data");
  });
  it("never calls a declared-prerecorded LSL stream human or offline, whatever its name", () => {
    const d = dev({
      device_id: "lsl:falcon",
      kind: "replay",
      synthetic: false,
      display_name: "LSL · Human spikes (SpikeCounts) — declared prerecorded",
    });
    const text = sourceKind(d)?.text ?? "";
    expect(text).toBe("Recorded data, streamed replay (declared)");
    expect(text).not.toMatch(/human|offline/i);
  });
  it("shows nothing without a device", () => {
    expect(sourceKind(null)).toBeNull();
  });
});

describe("statusLine", () => {
  it("states the runtime state with the data kind, in plain words", () => {
    expect(statusLine("open", rt("streaming"))).toEqual({ text: "Streaming · Simulated data", tone: "ok" });
    expect(statusLine("open", rt("paused")).text).toBe("Paused · Simulated data");
    expect(statusLine("open", rt("idle", null))).toEqual({ text: "No source connected", tone: "inactive" });
    expect(statusLine("open", rt("reconnecting")).tone).toBe("caution");
    expect(statusLine("open", rt("error")).tone).toBe("alarm");
  });
  it("never shows a runtime state while the server connection is down", () => {
    expect(statusLine("reconnecting", rt("streaming")).text).toBe("Connection to BrainOS lost, reconnecting");
    expect(statusLine("closed", null).text).toBe("Not connected to BrainOS");
  });
});

describe("defaultPreset and shapeSummary", () => {
  const rec = (rate: number) =>
    dev({ capabilities: [{ capability: "recording", params: { channel_count: 16, sample_rate_hz: rate }, description: "" }] });
  it("prefers passthrough for feature sources, spike band >= 10 kHz, band power otherwise", () => {
    const feat = dev({ capabilities: [{ capability: "neural_features", params: { channel_count: 176, bin_ms: 20 }, description: "" }] });
    expect(defaultPreset(feat)).toBe("features_passthrough");
    expect(defaultPreset(rec(30000))).toBe("spikeband_threshold");
    expect(defaultPreset(rec(1000))).toBe("ecog_high_gamma");
    expect(defaultPreset(rec(250))).toBe("band_power");
    expect(shapeSummary(feat)).toBe("176 channels · 20 ms bins");
    expect(shapeSummary(rec(30000))).toBe("16 channels · 30,000 Hz");
  });
});

describe("integrityVerdict (rules documented in integrity.ts)", () => {
  const base = { connected: true, state: "streaming" as const, msSinceData: 100, msSinceLoss: null };
  it("Good when data arrives and no loss counter rose", () => {
    expect(integrityVerdict(base)).toEqual({ text: "Good", tone: "ok" });
  });
  it("No signal when no data event arrived in the last 2 s (or none yet)", () => {
    expect(integrityVerdict({ ...base, msSinceData: 2001 }).text).toBe("No signal");
    expect(integrityVerdict({ ...base, msSinceData: null }).text).toBe("No signal");
    expect(integrityVerdict({ ...base, msSinceData: 1999 }).text).toBe("Good");
    expect(integrityVerdict({ ...base, connected: false }).tone).toBe("inactive");
  });
  it("Interrupted while reconnecting, even with recent data; Paused when paused", () => {
    expect(integrityVerdict({ ...base, state: "reconnecting" }).text).toBe("Interrupted — reconnecting");
    expect(integrityVerdict({ ...base, state: "paused", msSinceData: 9000 }).text).toBe("Paused");
  });
  it("Gaps detected when a loss counter rose in the last 10 s", () => {
    expect(integrityVerdict({ ...base, msSinceLoss: 9_000 })).toEqual({ text: "Gaps detected", tone: "caution" });
    expect(integrityVerdict({ ...base, msSinceLoss: 10_001 }).text).toBe("Good");
  });
});

describe("loss counters and data received", () => {
  it("sums only adapter loss counters plus pipeline, subscriber and stream drops", () => {
    const meta = { stats: { samples: 1000, gaps: 2, estimated_missing_samples: 30, lost: 1, chunks: 50 } };
    expect(lossTotal({ liveMeta: meta, pipelineDropped: 3, subscriberDrops: 4, streamMissed: 5 })).toBe(2 + 30 + 1 + 3 + 4 + 5);
    const oe = { counters: { data_messages: 9, missed_messages: 1, incomplete_blocks: 2, missing_samples: 3, malformed: 7 } };
    expect(lossTotal({ liveMeta: oe, pipelineDropped: 0, subscriberDrops: 0, streamMissed: 0 })).toBe(6);
  });
  it("computes received % only from counters the source reports", () => {
    expect(dataReceived({ stats: { samples: 990, estimated_missing_samples: 10 } })?.pct).toBeCloseTo(99);
    expect(dataReceived({ counters: { data_messages: 95, missed_messages: 5 } })?.pct).toBeCloseTo(95);
    expect(dataReceived({ stats: { samples: 10 } })).toBeNull();
    expect(dataReceived(null)).toBeNull();
  });
  it("LossTracker reports the time since the last increase and restarts on a new key", () => {
    const t = new LossTracker();
    expect(t.update("a", 5, 0)).toBeNull(); // baseline, not an increase
    expect(t.update("a", 5, 1000)).toBeNull();
    expect(t.update("a", 6, 2000)).toBe(0);
    expect(t.update("a", 6, 5000)).toBe(3000);
    expect(t.update("b", 50, 6000)).toBeNull(); // new session: cumulative counters are not "new" loss
  });
});

describe("session log lines", () => {
  it("turns device.status events into plain sentences with status tones", () => {
    expect(statusEntry({ state: "reconnecting", detail: "link dropped" })).toEqual({
      tone: "caution",
      text: "Link lost, reconnecting: link dropped",
    });
    expect(statusEntry({ state: "connected", detail: "connected to Simulated Profile A" }).text).toBe(
      "Connected to Simulated Profile A",
    );
    expect(statusEntry({ state: "streaming", detail: "streaming" })).toEqual({ tone: "ok", text: "Streaming" });
    expect(statusEntry({ state: "error", detail: "link lost" }).tone).toBe("alarm");
  });
  it("keeps technical errors neutral and only session-stopping ones red", () => {
    expect(errorEntry("decode_error", "bad packet")).toEqual({ tone: "info", text: "Decode error: bad packet" });
    expect(errorEntry("pump_crash", "boom").tone).toBe("alarm");
  });
});
