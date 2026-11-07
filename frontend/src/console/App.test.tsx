// Regression: when the connection to the server is lost, the console must not keep
// presenting the last known runtime state and metrics as if they were live.
import { act, cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { App } from "./App";

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
  adapter: "brainos.sim.profile_a@0.1.0",
  description: "",
  native_format: "",
  capabilities: [],
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
  counters: {},
  event_types: [{ event_type: "intent.pointer", total: 500, rate_hz: 50 }],
  pipeline_latency: { count: 1, p50_us: 300, p95_us: 600, p99_us: 900, max_us: 1000 },
  delivery_latency: { count: 1, p50_us: 300, p95_us: 600, p99_us: 900, max_us: 1000 },
  switches: [],
  recent_errors: [],
  apps: [],
  process: {},
};

let serverUp = true;
const json = (body: unknown) => new Response(JSON.stringify(body), { status: 200 });

beforeEach(() => {
  serverUp = true;
  MockSocket.instances = [];
  vi.stubGlobal("WebSocket", MockSocket);
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL) => {
      if (!serverUp) throw new TypeError("Failed to fetch");
      const url = String(input);
      if (url.includes("/diagnostics")) return json(diagnostics);
      if (url.includes("/devices")) return json([device]);
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

describe("console when the server connection is lost", () => {
  it("stops showing the last runtime state and metrics as live", async () => {
    render(<App />);
    const socket = MockSocket.instances[0];
    expect(socket).toBeDefined();
    act(() => {
      socket?.push({
        type: "welcome",
        protocol: "brainos.stream/1",
        schema_version: "1.0",
        connection_id: "con_1",
        negotiation,
        runtime: streaming,
      });
    });
    expect(screen.getByTestId("runtime-state").textContent).toBe("streaming");
    expect(screen.getByTestId("runtime-device").textContent).toBe("Simulated Profile A");
    await waitFor(() => expect(screen.getByText("600 µs")).toBeTruthy());

    serverUp = false;
    act(() => socket?.onclose?.());

    expect(screen.getByText("stream reconnecting")).toBeTruthy();
    expect(screen.getByTestId("runtime-state").textContent).toBe("unknown");
    expect(screen.getByTestId("runtime-device").textContent).toBe("none");
    await waitFor(() => expect(screen.queryByText("600 µs")).toBeNull(), { timeout: 2500 });
    expect(screen.queryByText(/Failed to fetch/)).toBeNull(); // the outage itself is not a toast
  });
});
