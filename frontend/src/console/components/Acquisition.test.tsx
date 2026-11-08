// Acquisition: the source picker (groups, connect, remove), LSL discovery/registration,
// Open Ephys registration and the live-source counters (only fields present are rendered).
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { DeviceDescriptor, RuntimeSnapshot } from "../../sdk";
import type { LSLStreamInfo } from "../api";
import { apiError, stubFetch } from "../testFetch";
import { LslSources } from "./LslSources";
import { OpenEphysForm } from "./OpenEphysForm";
import { SignalIntegrity } from "./SignalIntegrity";
import { SourcePicker } from "./SourcePicker";

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
    render(<LslSources onSourcesChanged={changed} />);
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
    await waitFor(() => expect(changed).toHaveBeenCalledTimes(2));
    expect(calls.at(-1)).toEqual({
      method: "POST",
      path: "/sources/lsl",
      body: { signal: "ephys", behavior: "ephys-behavior", markers: "words" },
    });
  });

  it("shows the server's message when registration is refused", async () => {
    stubFetch({
      "GET /sources/lsl": () => discovered,
      "POST /sources/lsl": () => apiError(400, "protocol_error", "behavior stream has no numeric channels"),
    });
    render(<LslSources onSourcesChanged={vi.fn()} />);
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
    render(<OpenEphysForm onSourcesChanged={changed} />);
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
    render(<OpenEphysForm onSourcesChanged={vi.fn()} />);
    fireEvent.change(screen.getByTestId("oe-port"), { target: { value: "70000" } });
    expect((screen.getByTestId("oe-register") as HTMLButtonElement).disabled).toBe(true);
  });
});

const liveDev = (id: string): DeviceDescriptor => ({
  device_id: id,
  display_name: id,
  kind: "stream",
  adapter: "concord.lsl@0.1.0",
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

const sim = (id: string, name: string): DeviceDescriptor => ({ ...liveDev(id), kind: "simulated", synthetic: true, display_name: name });

describe("SourcePicker", () => {
  const devices = [
    sim("sim-a", "Simulated Profile A"),
    liveDev("lsl:a"),
    liveDev("lsl:b"),
    { ...liveDev("replay:rec-1"), kind: "replay" as const, display_name: "Replay · rec-1" },
    {
      ...liveDev("nwb:sub-x_ses-1"),
      kind: "replay" as const,
      display_name: "Recorded Human Intracranial Data — Offline Replay",
      description: "sub-x_ses-1.nwb (DANDI 000954).",
    },
  ];
  const lslIdle = { "GET /sources/lsl": () => ({ library: null, discovered_at_ns: null, streams: [], error: null }) };

  it("groups sources: simulated, recorded data files only, session recordings, live streams", () => {
    stubFetch(lslIdle);
    render(<SourcePicker devices={devices} runtime={null} onClose={vi.fn()} onSourcesChanged={vi.fn()} />);
    const sims = screen.getByTestId("sim-list");
    expect(sims.querySelector('[data-testid="device-sim-a"]')).toBeTruthy();
    const datasets = screen.getByTestId("dataset-list");
    expect(datasets.querySelector('[data-testid="device-nwb:sub-x_ses-1"]')).toBeTruthy();
    expect(datasets.querySelector('[data-testid="device-replay:rec-1"]')).toBeNull();
    expect(datasets.querySelector('[data-testid="device-lsl:a"]')).toBeNull();
    expect(screen.getByTestId("recording-list").querySelector('[data-testid="device-replay:rec-1"]')).toBeTruthy();
    expect(screen.getByTestId("live-source-list").querySelector('[data-testid="device-lsl:a"]')).toBeTruthy();
    // LSL discovery and Open Ephys stay collapsed until asked for
    expect(screen.getByTestId("find-lsl-toggle").getAttribute("aria-expanded")).toBe("false");
    expect(screen.queryByTestId("lsl-discover")).toBeNull();
    expect(screen.queryByTestId("oe-register")).toBeNull();
  });

  it("shows four dataset files until 'Show all', labelled by session", () => {
    stubFetch(lslIdle);
    const files = Array.from({ length: 6 }, (_, i) => ({
      ...liveDev(`nwb:f${i}`),
      kind: "replay" as const,
      description: `sub-HumanPitt-held-in-calib_ses-1925010${i}T111022.nwb (DANDI 000954).`,
    }));
    render(<SourcePicker devices={files} runtime={null} onClose={vi.fn()} onSourcesChanged={vi.fn()} />);
    const list = screen.getByTestId("dataset-list");
    expect(list.querySelectorAll("li").length).toBe(4);
    expect(list.textContent).toContain("Session 19250100T111022");
    expect(list.textContent).toContain("DANDI 000954 · held-in-calib");
    fireEvent.click(screen.getByTestId("datasets-more"));
    expect(screen.getByTestId("dataset-list").querySelectorAll("li").length).toBe(6);
  });

  it("connects when idle, switches when connected, and closes on success", async () => {
    const calls = stubFetch({ ...lslIdle, "POST /runtime/connect": () => ({}), "POST /runtime/switch": () => ({}) });
    const onClose = vi.fn();
    const { unmount } = render(
      <SourcePicker devices={devices} runtime={null} onClose={onClose} onSourcesChanged={vi.fn()} />,
    );
    fireEvent.click(screen.getByTestId("device-sim-a"));
    await waitFor(() => expect(onClose).toHaveBeenCalled());
    expect(calls.find((c) => c.path === "/runtime/connect")?.body).toEqual({ device_id: "sim-a" });
    unmount();
    render(<SourcePicker devices={devices} runtime={runtimeOn(devices[0]!)} onClose={vi.fn()} onSourcesChanged={vi.fn()} />);
    expect(screen.getByTestId("device-lsl:a").textContent).toBe("Switch");
    expect(screen.queryByTestId("device-sim-a")).toBeNull(); // the connected one is marked, not offered
    fireEvent.click(screen.getByTestId("device-lsl:a"));
    await waitFor(() => expect(calls.some((c) => c.path === "/runtime/switch")).toBe(true));
  });

  it("removes an idle live source but never the connected one, and shows refusals verbatim", async () => {
    const calls = stubFetch({
      ...lslIdle,
      "DELETE /sources/lsl:b": () => ({ removed: true }),
      "POST /runtime/switch": () => apiError(409, "invalid_state", "runtime is busy"),
    });
    const changed = vi.fn();
    render(<SourcePicker devices={devices} runtime={runtimeOn(liveDev("lsl:a"))} onClose={vi.fn()} onSourcesChanged={changed} />);
    expect(screen.queryByTestId("remove-sim-a")).toBeNull();
    expect(screen.queryByTestId("remove-lsl:a")).toBeNull();
    fireEvent.click(screen.getByTestId("remove-lsl:b"));
    await waitFor(() => expect(changed).toHaveBeenCalled());
    expect(calls.some((c) => c.method === "DELETE" && c.path === "/sources/lsl:b")).toBe(true);
    fireEvent.click(screen.getByTestId("device-sim-a"));
    expect((await screen.findByTestId("picker-error")).textContent).toBe("invalid_state: runtime is busy");
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
