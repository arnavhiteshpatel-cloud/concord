// The session screen as a whole: title-bar status and Stop control, the four rows, the
// session log, Advanced collapsed by default, and — regression — when the connection to the
// server is lost, the console must not keep presenting the last known state as live.
import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { EventEnvelope } from "../sdk";
import { App } from "./App";
import type { PipelineStatus } from "./api";
import { FaultInjection, RecordingPanel, isBuiltInSimulator } from "./components/ControlsPanel";
import { summary } from "./components/EventStream";

class MockSocket {
  static instances: MockSocket[] = [];
  onopen: (() => void) | null = null;
  onmessage: ((m: { data: string }) => void) | null = null;
  onclose: (() => void) | null = null;
  constructor(public url: string) {
    MockSocket.instances.push(this);
  }
  send() {}
  close() {}
  push(msg: unknown) {
    this.onmessage?.({ data: JSON.stringify(msg) });
  }
}

const device = {
  device_id: "sim-a",
  display_name: "Simulated Profile A",
  kind: "simulated",
  adapter: "concord.sim.profile_a@0.1.0",
  description: "",
  native_format: "",
  capabilities: [{ capability: "recording", params: { channel_count: 2, sample_rate_hz: 1000 }, description: "" }],
  synthetic: true,
};
const streaming = {
  state: "streaming",
  device,
  session_id: "ses_abcdef12",
  state_since_ns: 1,
  last_error: null,
  recording: null,
  apps: [],
};
const negotiation = { device_id: "sim-a", status: "active", granted: [], rejected: [] };
const diagnostics = {
  uptime_s: 1,
  measured_at_ns: 1,
  counters: { subscriber_drops: 0 },
  event_types: [{ event_type: "intent.pointer", total: 500, rate_hz: 50 }],
  pipeline_latency: { count: 1, p50_us: 300, p95_us: 600, p99_us: 900, max_us: 1000 },
  delivery_latency: { count: 1, p50_us: 300, p95_us: 600, p99_us: 900, max_us: 1000 },
  switches: [],
  recent_errors: [] as { at_ns: number; kind: string; device_id: string | null; message: string }[],
  apps: [],
  process: {},
};
const stats = { count: 0, p50: null, p95: null, p99: null, max: null };
const router = { enabled: true, x_dim: "vx", y_dim: "vy", gain: 1.5, deadzone: 0.3, invert_y: true, max_speed: 2 };
const controlStatus = {
  router_on: true,
  model_id: "m",
  provides: ["pointer_intent"],
  router,
  stall_limit_ms: 1000,
  last_stop: null,
  apps: [],
  history: [],
};
const pipelineOff: PipelineStatus = {
  available: true,
  unavailable_reason: null,
  running: false,
  device_id: null,
  session_id: null,
  preset: null,
  stages: [],
  input_event_type: null,
  output: null,
  warmup_remaining_s: 0,
  decoder: null,
  compatibility_warnings: [],
  cross_source_override: false,
  router: null,
  counters: {},
  processing_us: stats,
  pipeline_latency_ms: stats,
  last_error: null,
  started_at_ns: null,
};
const pipelineControlOn: PipelineStatus = {
  ...pipelineOff,
  running: true,
  device_id: "sim-a",
  session_id: "ses_abcdef12",
  preset: "features_passthrough",
  decoder: { model_id: "ridge-abc", dims: ["vx", "vy"] },
  router,
};

let serverUp = true;
let pipeline: PipelineStatus = pipelineOff;
let calls: { method: string; path: string; body: unknown }[] = [];
const json = (body: unknown) => new Response(JSON.stringify(body), { status: 200 });

beforeEach(() => {
  serverUp = true;
  pipeline = pipelineOff;
  calls = [];
  diagnostics.recent_errors = [];
  MockSocket.instances = [];
  vi.stubGlobal("WebSocket", MockSocket);
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      if (!serverUp) throw new TypeError("Failed to fetch");
      const url = String(input);
      const method = init?.method ?? "GET";
      const body = typeof init?.body === "string" ? (JSON.parse(init.body) as unknown) : undefined;
      calls.push({ method, path: url.replace(/^\/api\/v1/, ""), body });
      if (url.includes("/diagnostics")) return json(diagnostics);
      if (url.endsWith("/pipeline/router")) {
        pipeline = { ...pipeline, router: body as typeof router };
        return json(pipeline);
      }
      if (url.endsWith("/control/stop")) {
        pipeline = { ...pipeline, router: pipeline.router ? { ...pipeline.router, enabled: false } : null };
        return json({ ...controlStatus, router_on: false });
      }
      if (url.endsWith("/control")) return json(controlStatus);
      if (url.endsWith("/pipeline")) return json(pipeline);
      if (url.includes("/devices")) return json([device]);
      if (url.includes("/runtime/")) return json(streaming);
      return json([]);
    }),
  );
  HTMLCanvasElement.prototype.getContext = vi.fn(() => null);
});

afterEach(() => {
  cleanup();
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

const envelope = (seq: number, event_type: string, payload: unknown, provenance = "raw_signal") => ({
  schema_version: "1.2",
  session_id: "ses_abcdef12",
  device_id: "sim-a",
  seq,
  timestamp_ns: Date.now() * 1e6,
  device_timestamp_ns: null,
  event_type,
  capability: event_type === "recording.frame" ? "recording" : "device_status",
  quality: { score: 1, flags: ["synthetic"] },
  provenance: { kind: provenance, adapter: "a@1", synthetic: true, model_id: null, origin: "o", replayed: false },
  payload,
});

function open(runtime: unknown = streaming) {
  render(<App />);
  const socket = MockSocket.instances[0]!;
  act(() => {
    socket.push({
      type: "welcome",
      protocol: "concord.stream/1",
      schema_version: "1.2",
      connection_id: "con_1",
      negotiation,
      runtime,
    });
  });
  return socket;
}

describe("title bar", () => {
  it("shows the source and a plain status line, and a disabled Stop control while output is off", async () => {
    open();
    expect(screen.getByTestId("runtime-device").textContent).toBe("Simulated Profile A");
    const status = screen.getByTestId("status-line");
    expect(status.getAttribute("aria-live")).toBe("polite");
    expect(status.textContent).toBe("Streaming · Simulated data");
    const stop = screen.getByTestId("stop-control") as HTMLButtonElement;
    expect(stop.textContent).toBe("Stop control");
    await waitFor(() => expect(calls.some((c) => c.path === "/pipeline")).toBe(true));
    expect(stop.disabled).toBe(true);
    expect(stop.title).toBe("Command output is off");
  });

  it("enables Stop control while output is on; it calls the control stop (router off, mapping kept)", async () => {
    pipeline = pipelineControlOn;
    open();
    const stop = screen.getByTestId("stop-control") as HTMLButtonElement;
    await waitFor(() => expect(stop.disabled).toBe(false));
    fireEvent.click(stop);
    await waitFor(() => expect(calls.some((c) => c.path === "/control/stop")).toBe(true));
    expect(calls.find((c) => c.path === "/control/stop")!.method).toBe("POST");
    expect(calls.some((c) => c.path === "/pipeline/router")).toBe(false);
    await waitFor(() => expect(stop.disabled).toBe(true));
    expect(pipeline.router).toEqual({ ...router, enabled: false });
    // the change appears in the session log
    await waitFor(() => expect(screen.getByTestId("session-log").textContent).toContain("Control stopped"));
  });
});

describe("session screen", () => {
  it("shows the four rows, the session log and one collapsed Advanced section", () => {
    open({ ...streaming, state: "idle", device: null, session_id: null });
    for (const id of ["row-source", "row-integrity", "row-decoder", "row-control"]) expect(screen.getByTestId(id)).toBeTruthy();
    expect(screen.getAllByRole("heading", { level: 2 }).map((h) => h.textContent)).toEqual([
      "Acquisition source",
      "Signal integrity",
      "Decoder",
      "Command output",
      "Session log",
    ]);
    expect(screen.getByText("Where the brain data comes from.")).toBeTruthy();
    expect(screen.getByTestId("status-line").textContent).toBe("No source connected");
    // only one primary action when nothing is connected
    const source = within(screen.getByTestId("row-source"));
    expect(source.getByTestId("connect-source").textContent).toBe("Connect a source");
    expect(source.queryByTestId("disconnect")).toBeNull();
    expect(source.queryByTestId("pause")).toBeNull();
    expect(screen.queryByTestId("start-decoding-open")).toBeNull();
    expect(screen.queryByTestId("router-on")).toBeNull();
    expect(screen.getByTestId("verdict").textContent).toBe("No signal");
    // Advanced: a single collapsed disclosure; nothing technical rendered until opened
    const adv = screen.getByTestId("advanced-toggle");
    expect(adv.getAttribute("aria-expanded")).toBe("false");
    expect(screen.queryByTestId("event-stream")).toBeNull();
    fireEvent.click(adv);
    for (const id of ["adv-events", "adv-pipeline", "adv-acquisition", "adv-diagnostics", "adv-recording", "adv-contract", "adv-apps", "adv-board", "adv-tests"])
      expect(screen.getByTestId(`${id}-toggle`).getAttribute("aria-expanded")).toBe("false");
    expect(screen.queryByTestId("adv-simulator")).toBeNull(); // only with the built-in simulator connected
    expect(screen.queryByTestId("event-stream")).toBeNull();
    fireEvent.click(screen.getByTestId("adv-events-toggle"));
    expect(screen.getByTestId("event-stream")).toBeTruthy();
  });

  it("source row actions call the runtime: picker -> connect, disconnect, pause", async () => {
    const socket = open({ ...streaming, state: "idle", device: null, session_id: null });
    fireEvent.click(screen.getByTestId("connect-source"));
    fireEvent.click(await screen.findByTestId("device-sim-a"));
    await waitFor(() => expect(calls.some((c) => c.path === "/runtime/connect")).toBe(true));
    expect(calls.find((c) => c.path === "/runtime/connect")!.body).toEqual({ device_id: "sim-a" });
    await waitFor(() => expect(screen.queryByTestId("source-picker")).toBeNull());
    act(() => socket.push({ type: "runtime", runtime: streaming }));
    expect(screen.getByTestId("source-name").textContent).toBe("Simulated Profile A");
    fireEvent.click(screen.getByTestId("source-options-toggle"));
    fireEvent.click(screen.getByTestId("pause"));
    await waitFor(() => expect(calls.some((c) => c.path === "/runtime/pause")).toBe(true));
    await waitFor(() => expect((screen.getByTestId("disconnect") as HTMLButtonElement).disabled).toBe(false));
    fireEvent.click(screen.getByTestId("disconnect"));
    await waitFor(() => expect(calls.some((c) => c.path === "/runtime/disconnect")).toBe(true));
  });

  it("derives the verdict and channel count from data events, and logs device status", async () => {
    const socket = open();
    expect(screen.getByTestId("verdict").textContent).toBe("No signal");
    act(() => {
      socket.push({
        type: "event",
        delivery_seq: 1,
        event: envelope(1, "recording.frame", {
          sample_rate_hz: 1000,
          channel_count: 2,
          first_sample_index: 0,
          unit: "uV",
          samples: [
            [1, 2],
            [3, 4],
          ],
        }),
      });
      socket.push({
        type: "event",
        delivery_seq: 2,
        event: envelope(2, "device.status", { state: "reconnecting", detail: "link dropped" }, "runtime"),
      });
    });
    await waitFor(() => expect(screen.getByTestId("verdict").textContent).toBe("Good"));
    expect(screen.getByTestId("fig-channels").textContent).toBe("2 of 2");
    expect(screen.getByTestId("fig-received").textContent).toBe("—"); // the simulator reports no loss counters
    expect(screen.getByTestId("trace-caption").textContent).toMatch(/^Showing 2 of 2 channels/);
    await waitFor(() =>
      expect(screen.getByTestId("session-log").textContent).toContain("Link lost, reconnecting: link dropped"),
    );
    // the log shows entries with a time stamp, newest first
    const first = screen.getByTestId("session-log").querySelector("li")!;
    expect(first.querySelector("time")!.textContent).toMatch(/^\d\d:\d\d:\d\d$/);
    expect(first.textContent).toContain("Link lost");
  });

  it("logs new runtime errors from diagnostics, but not those from before the page loaded", async () => {
    diagnostics.recent_errors = [{ at_ns: 1, kind: "decode_error", device_id: "sim-a", message: "old" }];
    open();
    await waitFor(() => expect(calls.some((c) => c.path === "/diagnostics")).toBe(true));
    diagnostics.recent_errors = [
      ...diagnostics.recent_errors,
      { at_ns: Date.now() * 1e6 + 5e9, kind: "decode_error", device_id: "sim-a", message: "malformed packet" },
    ];
    await waitFor(() => expect(screen.getByTestId("session-log").textContent).toContain("Decode error: malformed packet"), {
      timeout: 2500,
    });
    expect(screen.getByTestId("session-log").textContent).not.toContain("old");
  });
});

describe("console when the server connection is lost", () => {
  it("stops showing the last runtime state and metrics as live", async () => {
    const socket = open();
    expect(screen.getByTestId("status-line").getAttribute("data-state")).toBe("streaming");
    fireEvent.click(screen.getByTestId("advanced-toggle"));
    fireEvent.click(screen.getByTestId("adv-diagnostics-toggle"));
    await waitFor(() => expect(screen.getByText("600 µs")).toBeTruthy());

    serverUp = false;
    act(() => socket.onclose?.());

    expect(screen.getByTestId("status-line").textContent).toBe("Connection to Concord lost, reconnecting");
    expect(screen.getByTestId("status-line").getAttribute("data-state")).toBe("unknown");
    expect(screen.queryByTestId("runtime-device")).toBeNull();
    expect(screen.queryByTestId("source-name")).toBeNull();
    await waitFor(() => expect(screen.queryByText("600 µs")).toBeNull(), { timeout: 2500 });
    expect(screen.queryByText(/Failed to fetch/)).toBeNull(); // the outage itself is not an error message
    expect(screen.getByTestId("session-log").textContent).toContain("Connection to Concord lost");
  });
});

describe("Advanced: recording and simulator", () => {
  const dev = (over: Partial<typeof device>) => ({ ...device, ...over }) as never;
  const rt = (d: never) => ({ ...streaming, device: d }) as never;
  it("records a live LSL stream, with 'features and labels only' passed through", async () => {
    const calls2: unknown[] = [];
    vi.stubGlobal(
      "fetch",
      vi.fn(async (_u: RequestInfo | URL, init?: RequestInit) => {
        calls2.push(JSON.parse(String(init?.body)));
        return json({ name: "r" });
      }),
    );
    render(<RecordingPanel runtime={rt(dev({ device_id: "lsl:ephys" }))} recordings={[]} onRecordingsChanged={vi.fn()} />);
    const btn = screen.getByTestId("rec-start") as HTMLButtonElement;
    expect(btn.disabled).toBe(false);
    fireEvent.click(btn);
    await waitFor(() => expect(calls2.length).toBe(1));
    fireEvent.click(screen.getByTestId("rec-exclude-raw"));
    fireEvent.click(btn);
    await waitFor(() => expect(calls2.length).toBe(2));
    expect(calls2).toEqual([{}, { exclude_raw: true }]);
  });
  it("cannot record a local file replay", () => {
    render(<RecordingPanel runtime={rt(dev({ device_id: "replay:x", kind: "replay" }))} recordings={[]} onRecordingsChanged={vi.fn()} />);
    expect((screen.getByTestId("rec-start") as HTMLButtonElement).disabled).toBe(true);
  });
  it("offers fault injection only for the built-in simulator", () => {
    expect(isBuiltInSimulator(rt(dev({})))).toBe(true);
    expect(isBuiltInSimulator(rt(dev({ device_id: "lsl:ephys" })))).toBe(false); // declared-synthetic external stream
    // regression (0.3.1): a plugin's synthetic board (e.g. BrainFlow) showed dead simulator controls
    expect(isBuiltInSimulator(rt(dev({ device_id: "plugin:concord-brainflow:synthetic" })))).toBe(false);
    expect(isBuiltInSimulator({ ...streaming, state: "idle" } as never)).toBe(false);
    render(<FaultInjection />);
    expect(screen.getByTestId("fault-link_drop")).toBeTruthy();
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
    adapter: "concord.pipeline@0.3.0",
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
