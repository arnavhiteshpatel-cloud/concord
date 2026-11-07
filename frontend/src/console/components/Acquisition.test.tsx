// Milestone 3 acquisition controls: LSL discovery/registration, Open Ephys registration,
// source removal and the signal-integrity view (only fields present are rendered).
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { DeviceDescriptor, RuntimeSnapshot } from "../../sdk";
import type { LSLStreamInfo } from "../api";
import { apiError, stubFetch } from "../testFetch";
import { AcquisitionView } from "./AcquisitionView";
import { LslSources } from "./LslSources";
import { OpenEphysForm } from "./OpenEphysForm";
import { SignalIntegrity } from "./SignalIntegrity";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const stream = (over: Partial<LSLStreamInfo>): LSLStreamInfo => ({
  key: "k",
  device_id: "lsl:k",
  name: "S",
  type: "EEG",
  source_id: "k",
  hostname: "host",
  channel_count: 16,
  nominal_srate: 30000,
  channel_format: "float32",
  channels_described: true,
  units: ["microvolts"],
  declared_prerecorded: false,
  declared_synthetic: true,
  usable_as_signal: true,
  reason: null,
  ...over,
});

const discovered = {
  library: "git:abc/branch:refs/tags/v1.18.0.b6/build:Release",
  discovered_at_ns: Date.now() * 1e6,
  error: null,
  streams: [
    stream({ key: "ephys", name: "Synthetic ephys" }),
    stream({ key: "ephys-behavior", name: "latent velocity", type: "Behavior", channel_count: 2, nominal_srate: 100 }),
    stream({
      key: "words",
      name: "Words",
      type: "Markers",
      channel_count: 1,
      nominal_srate: 0,
      channel_format: "string",
      channels_described: false,
      units: [],
      declared_prerecorded: null,
      declared_synthetic: null,
      usable_as_signal: false,
      reason: "string-valued streams cannot be a signal",
    }),
  ],
};

describe("LslSources", () => {
  it("discovers streams, shows metadata and refusal reasons, registers with behavior", async () => {
    const calls = stubFetch({
      "GET /sources/lsl": () => ({ library: null, discovered_at_ns: null, streams: [], error: null }),
      "POST /sources/lsl/discover": () => discovered,
      "POST /sources/lsl": () => ({ device_id: "lsl:ephys" }),
    });
    const changed = vi.fn();
    const notify = vi.fn();
    render(<LslSources onSourcesChanged={changed} notify={notify} />);
    fireEvent.click(screen.getByTestId("lsl-discover"));
    const table = await screen.findByTestId("lsl-streams");
    expect(calls.find((c) => c.path === "/sources/lsl/discover")?.body).toEqual({ wait_s: 1.5 });
    expect(changed).toHaveBeenCalledTimes(1); // discovery registers usable streams
    const row = (k: string) => within(table.querySelector(`[data-stream-key="${k}"]`) as HTMLElement);
    expect(row("ephys").getByText("30,000 Hz")).toBeTruthy();
    expect(row("ephys").getByText("microvolts")).toBeTruthy();
    expect(row("ephys").getByText("synthetic")).toBeTruthy();
    expect(row("words").getByText("string-valued streams cannot be a signal")).toBeTruthy();
    expect(row("words").getByText("irregular")).toBeTruthy();
    expect(row("words").getByText("channels not described")).toBeTruthy();
    expect(row("words").getByText("no declaration")).toBeTruthy();
    expect(screen.queryByTestId("lsl-use-words")).toBeNull(); // unusable: no button

    fireEvent.click(screen.getByTestId("lsl-use-ephys"));
    const behavior = screen.getByTestId("lsl-behavior") as HTMLSelectElement;
    // the signal itself is not offered as its own behavior stream
    expect([...behavior.options].map((o) => o.value)).toEqual(["", "ephys-behavior", "words"]);
    fireEvent.change(behavior, { target: { value: "ephys-behavior" } });
    fireEvent.change(screen.getByTestId("lsl-markers"), { target: { value: "words" } });
    fireEvent.click(screen.getByTestId("lsl-register"));
    await waitFor(() => expect(notify).toHaveBeenCalled());
    expect(calls.at(-1)).toEqual({
      method: "POST",
      path: "/sources/lsl",
      body: { signal: "ephys", behavior: "ephys-behavior", markers: "words" },
    });
    expect(changed).toHaveBeenCalledTimes(2);
  });

  it("shows the server's message when registration is refused", async () => {
    stubFetch({
      "GET /sources/lsl": () => discovered,
      "POST /sources/lsl": () => apiError(400, "protocol_error", "behavior stream has no numeric channels"),
    });
    render(<LslSources onSourcesChanged={vi.fn()} notify={vi.fn()} />);
    fireEvent.click(await screen.findByTestId("lsl-use-ephys"));
    fireEvent.click(screen.getByTestId("lsl-register"));
    expect((await screen.findByTestId("lsl-error")).textContent).toBe(
      "protocol_error: behavior stream has no numeric channels",
    );
  });
});

describe("OpenEphysForm", () => {
  it("defaults to 127.0.0.1:5556 with unit unknown and says units are not transmitted", async () => {
    const calls = stubFetch({ "POST /sources/openephys": () => ({ device_id: "openephys:127.0.0.1:5556" }) });
    const changed = vi.fn();
    render(<OpenEphysForm onSourcesChanged={changed} notify={vi.fn()} />);
    expect((screen.getByTestId("oe-host") as HTMLInputElement).value).toBe("127.0.0.1");
    expect((screen.getByTestId("oe-port") as HTMLInputElement).value).toBe("5556");
    expect((screen.getByTestId("oe-unit") as HTMLSelectElement).value).toBe("unknown");
    expect(screen.getByTestId("openephys-form").textContent).toMatch(/does not transmit units/);
    fireEvent.change(screen.getByTestId("oe-unit"), { target: { value: "uV" } });
    fireEvent.click(screen.getByTestId("oe-register"));
    await waitFor(() => expect(changed).toHaveBeenCalled());
    expect(calls[0]!.body).toEqual({ host: "127.0.0.1", data_port: 5556, unit: "uV" });
  });

  it("disables registration for an invalid port", () => {
    stubFetch({});
    render(<OpenEphysForm onSourcesChanged={vi.fn()} notify={vi.fn()} />);
    fireEvent.change(screen.getByTestId("oe-port"), { target: { value: "70000" } });
    expect((screen.getByTestId("oe-register") as HTMLButtonElement).disabled).toBe(true);
  });
});

const liveDev = (id: string): DeviceDescriptor => ({
  device_id: id,
  display_name: id,
  kind: "stream",
  adapter: "brainos.lsl@0.1.0",
  description: "",
  native_format: "",
  capabilities: [],
  synthetic: false,
});
const runtimeOn = (device: DeviceDescriptor): RuntimeSnapshot => ({
  state: "streaming",
  device,
  session_id: "ses_1",
  state_since_ns: 1,
  last_error: null,
  recording: null,
  apps: [],
});

describe("AcquisitionView registered sources", () => {
  it("removes an idle source and refuses (disabled) to remove the connected one", async () => {
    const calls = stubFetch({
      "GET /sources/lsl": () => ({ library: null, discovered_at_ns: null, streams: [], error: null }),
      "DELETE /sources/lsl:b": () => ({ removed: true }),
    });
    const changed = vi.fn();
    render(
      <AcquisitionView
        devices={[liveDev("lsl:a"), liveDev("lsl:b"), { ...liveDev("sim-a"), kind: "simulated" }]}
        runtime={runtimeOn(liveDev("lsl:a"))}
        liveMeta={{ protocol: "lsl", stats: { samples: 10 } }}
        liveError={null}
        diag={null}
        onSourcesChanged={changed}
        notify={vi.fn()}
      />,
    );
    expect(screen.queryByTestId("remove-sim-a")).toBeNull();
    expect((screen.getByTestId("remove-lsl:a") as HTMLButtonElement).disabled).toBe(true);
    fireEvent.click(screen.getByTestId("remove-lsl:b"));
    await waitFor(() => expect(changed).toHaveBeenCalled());
    expect(calls.some((c) => c.method === "DELETE" && c.path === "/sources/lsl:b")).toBe(true);
    expect(screen.getByTestId("signal-integrity")).toBeTruthy();
  });
});

describe("SignalIntegrity", () => {
  it("renders LSL counters, per-stream gaps and clock correction from the dict only", () => {
    render(
      <SignalIntegrity
        meta={{
          protocol: "lsl",
          library: "lib",
          interpretation: "raw",
          unit: "uV",
          stats: { chunks: 5, samples: 3000, gaps: 2, estimated_missing_samples: 60, lost: 0, stalls: 0 },
          streams: [
            {
              role: "signal",
              name: "Synthetic ephys",
              type: "EEG",
              received_samples: 3000,
              gaps: 2,
              estimated_missing_samples: 60,
              time_correction_s: 0.0001234,
              last_timestamp_s: 12.5,
            },
          ],
          notes: ["Dropped samples are estimated from timestamp gaps."],
        }}
        error={null}
        diag={null}
      />,
    );
    const counters = screen.getByTestId("integrity-counters");
    expect(counters.querySelectorAll("[data-counter]").length).toBe(6);
    expect(counters.querySelector('[data-counter="gaps"]')!.className).toContain("counter-warn");
    expect(counters.querySelector('[data-counter="samples"]')!.className).not.toContain("counter-warn");
    expect(screen.getByTestId("integrity-streams").textContent).toContain("0.123 ms");
    expect(screen.getByTestId("integrity-notes").textContent).toContain("timestamp gaps");
    // Open Ephys-only fields are absent, so not rendered
    expect(screen.queryByText("heartbeat")).toBeNull();
    expect(screen.queryByText("clock offset")).toBeNull();
  });

  it("renders Open Ephys counters, heartbeat, clock offset and last error", () => {
    render(
      <SignalIntegrity
        meta={{
          protocol: "openephys-zmq",
          host: "127.0.0.1",
          data_port: 5556,
          unit_configured: "unknown",
          unit_emitted: "arbitrary",
          unit_note: "units not transmitted by the protocol",
          heartbeat: { status: "ok" },
          counters: { data_messages: 40, malformed: 1, missed_messages: 0 },
          sender_to_local_offset_ms: { last: 1.5, min: 0.25, note: "local minus sender" },
          last_message_num: 41,
          last_error: "bad header",
        }}
        error={null}
        diag={null}
      />,
    );
    expect(screen.getByText("127.0.0.1:5556")).toBeTruthy();
    expect(screen.getByText("ok")).toBeTruthy();
    expect(screen.getByText(/last 1\.500 ms · min 0\.250 ms/)).toBeTruthy();
    expect(screen.getByTestId("integrity-counters").querySelector('[data-counter="malformed"]')!.className).toContain(
      "counter-warn",
    );
    expect(screen.getByTestId("integrity-last-error").textContent).toBe("bad header");
    expect(screen.getByTestId("integrity-notes").textContent).toContain("units not transmitted");
    expect(screen.queryByTestId("integrity-streams")).toBeNull();
  });
});
