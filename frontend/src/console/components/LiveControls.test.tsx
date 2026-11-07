// Milestone 3 changes to existing panels: recording live sources (optionally without raw
// frames), no fault buttons for external streams, device grouping, decoded model ids.
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { DeviceDescriptor, EventEnvelope, RuntimeSnapshot } from "../../sdk";
import { ControlsPanel } from "./ControlsPanel";
import { DevicesPanel } from "./DevicesPanel";
import { summary } from "./EventStream";

afterEach(cleanup);

const dev = (over: Partial<DeviceDescriptor>): DeviceDescriptor => ({
  device_id: "sim-a",
  display_name: "Simulated Profile A",
  kind: "simulated",
  adapter: "a@1.0.0",
  description: "",
  native_format: "",
  capabilities: [],
  synthetic: true,
  ...over,
});
const on = (device: DeviceDescriptor): RuntimeSnapshot => ({
  state: "streaming",
  device,
  session_id: "ses_1",
  state_since_ns: 1,
  last_error: null,
  recording: null,
  apps: [],
});
const controls = (runtime: RuntimeSnapshot, onStartRecording = vi.fn()) =>
  render(
    <ControlsPanel
      runtime={runtime}
      busy={false}
      recordings={[]}
      onPause={vi.fn()}
      onResume={vi.fn()}
      onDisconnect={vi.fn()}
      onStartRecording={onStartRecording}
      onStopRecording={vi.fn()}
      onFault={vi.fn()}
    />,
  );

describe("ControlsPanel with live sources", () => {
  it("records a live LSL stream, with 'features + labels only' passed through", () => {
    const start = vi.fn();
    controls(on(dev({ device_id: "lsl:ephys", kind: "simulated", synthetic: true })), start);
    const btn = screen.getByTestId("rec-start") as HTMLButtonElement;
    expect(btn.disabled).toBe(false);
    fireEvent.click(btn);
    fireEvent.click(screen.getByTestId("rec-exclude-raw"));
    fireEvent.click(btn);
    expect(start.mock.calls).toEqual([[false], [true]]);
  });
  it("offers no fault injection for an external stream declared synthetic", () => {
    controls(on(dev({ device_id: "lsl:ephys", kind: "simulated", synthetic: true })));
    expect((screen.getByTestId("fault-link_drop") as HTMLButtonElement).disabled).toBe(true);
  });
  it("still injects faults into the built-in simulator", () => {
    controls(on(dev({})));
    expect((screen.getByTestId("fault-link_drop") as HTMLButtonElement).disabled).toBe(false);
  });
  it("cannot record a local file replay", () => {
    controls(on(dev({ device_id: "replay:x", kind: "replay" })));
    expect((screen.getByTestId("rec-start") as HTMLButtonElement).disabled).toBe(true);
  });
});

describe("DevicesPanel grouping", () => {
  it("lists live sources separately and keeps only dataset files in the dataset group", () => {
    render(
      <DevicesPanel
        devices={[
          dev({}),
          dev({ device_id: "lsl:falcon", kind: "replay", synthetic: false, display_name: "LSL · counts — declared prerecorded" }),
          dev({ device_id: "replay:lsl-rec", kind: "replay", synthetic: false, display_name: "Replay · lsl-rec" }),
          dev({ device_id: "nwb:sub-x_ses-1", kind: "replay", synthetic: false, description: "sub-x_ses-1.nwb (DANDI 000954)." }),
        ]}
        runtime={null}
        busy={false}
        onConnect={vi.fn()}
      />,
    );
    const live = screen.getByTestId("live-source-list");
    expect(live.querySelector('[data-testid="device-lsl:falcon"]')).toBeTruthy();
    const datasets = screen.getByTestId("dataset-list");
    expect(datasets.querySelector('[data-testid="device-nwb:sub-x_ses-1"]')).toBeTruthy();
    expect(datasets.querySelector('[data-testid="device-replay:lsl-rec"]')).toBeNull();
    expect(datasets.querySelector('[data-testid="device-lsl:falcon"]')).toBeNull();
  });
});

describe("EventStream summary", () => {
  const base = {
    schema_version: "1.2",
    session_id: "ses_1",
    device_id: "lsl:ephys",
    seq: 1,
    timestamp_ns: 1,
    device_timestamp_ns: null,
    quality: { score: 1, flags: [] },
  };
  const prov = (kind: "decoded_intent" | "simulated_intent", model_id: string | null) => ({
    kind,
    adapter: "brainos.pipeline@0.3.0",
    synthetic: false,
    model_id,
    origin: "o",
    replayed: false,
  });
  it("names the model for decoded pointer and kinematics events", () => {
    const ptr = {
      ...base,
      event_type: "intent.pointer",
      capability: "pointer_intent",
      payload: { vx: 0.1, vy: -0.2 },
      provenance: prov("decoded_intent", "ridge-abc"),
    } as EventEnvelope;
    expect(summary(ptr)).toBe("vx 0.100  vy -0.200  ⟵ ridge-abc");
    const kin = {
      ...base,
      event_type: "intent.kinematics",
      capability: "kinematic_intent",
      payload: { quantity: "velocity", dims: ["vx"], unit: "arbitrary", values: [0.5], space: "s" },
      provenance: prov("decoded_intent", "ridge-abc"),
    } as EventEnvelope;
    expect(summary(kin)).toMatch(/⟵ ridge-abc$/);
    const sim = { ...ptr, provenance: prov("simulated_intent", null) } as EventEnvelope;
    expect(summary(sim)).toBe("vx 0.100  vy -0.200");
  });
});
