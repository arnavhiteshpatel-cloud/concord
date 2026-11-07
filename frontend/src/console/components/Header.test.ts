// The data-kind badge must never call non-human or simulated data "recorded human data".
import { describe, expect, it } from "vitest";
import type { DeviceDescriptor } from "../../sdk";
import { dataBadge } from "./Header";

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

describe("dataBadge", () => {
  it("labels simulated devices as simulated", () => {
    expect(dataBadge(dev({}))?.text).toBe("SIMULATED DATA");
  });
  it("labels human recordings as recorded human data, offline", () => {
    const d = dev({ kind: "replay", synthetic: false, display_name: "Recorded Human Intracranial Data — Offline Replay" });
    expect(dataBadge(d)?.text).toBe("RECORDED HUMAN DATA · OFFLINE REPLAY");
  });
  it("does not call a non-human recording human", () => {
    const d = dev({ kind: "replay", synthetic: false, display_name: "Recorded Neural Data — Offline Replay" });
    expect(dataBadge(d)?.text).toBe("RECORDED DATA · OFFLINE REPLAY");
  });
  it("does not call a non-synthetic live device an offline replay", () => {
    expect(dataBadge(dev({ kind: "hardware", synthetic: false }))?.text).not.toMatch(/REPLAY/);
  });
  it("shows nothing without a device", () => {
    expect(dataBadge(null)).toBeNull();
  });
});
