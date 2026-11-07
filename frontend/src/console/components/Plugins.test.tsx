// Source plugins in the console: the picker's Plugins group (status, devices, options form
// generated from the plugin's option specs, connect) and the Acquisition row's plugin line.
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { DeviceDescriptor, RuntimeSnapshot } from "../../sdk";
import type { PluginInfo, PluginsStatus } from "../api";
import { apiError, stubFetch } from "../testFetch";
import { integrationLine, modalityWords } from "../wording";
import { changedOptions } from "./PluginSources";
import { SourcePicker } from "./SourcePicker";
import { SourceRow } from "./SourceRow";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const DEVICE_ID = "plugin:example-mi-eeg:mi-eeg";

const example: PluginInfo = {
  name: "example-mi-eeg",
  entry: "brainos_example_adapter.plugin:MotorImageryEEGPlugin",
  package: "brainos-example-adapter",
  package_version: "0.1.0",
  status: "compatible",
  reason: null,
  display_name: "Example: motor-imagery EEG generator",
  description: "Declared-synthetic EEG",
  version: "0.1.0",
  api_version: "1.0",
  author: "BrainOS developers",
  license: "Proprietary",
  homepage: "",
  ecosystem: null,
  network: false,
  roles: ["behavior", "markers", "signal"],
  options: [
    { name: "seed", type: "int", description: "Random seed", default: 1, required: false, choices: [] },
    { name: "montage", type: "choice", description: "Channel set", default: "8", required: false, choices: ["8", "16"] },
    { name: "realtime", type: "bool", description: "Pace in real time", default: true, required: false, choices: [] },
  ],
  problems: [],
  error: null,
  devices: [
    {
      device_key: "mi-eeg",
      display_name: "Motor-imagery EEG generator",
      description: "Synthetic EEG with a cue schedule.",
      details: {},
      device_id: DEVICE_ID,
      reason: null,
      configured: false,
    },
  ],
  discovery_error: null,
  log_tail: [],
};

const rejected: PluginInfo = {
  ...example,
  name: "future-plugin",
  package: "future-plugin",
  package_version: "3.0.0",
  version: "3.0.0",
  display_name: "Future plugin",
  status: "rejected",
  reason: "api_version: written for adapter SDK API 2.0; this BrainOS supports API 1.0 (major versions differ)",
  devices: [],
};

const broken: PluginInfo = {
  ...example,
  name: "broken",
  package: "broken-plugin",
  package_version: "0.0.1",
  version: null,
  display_name: null,
  status: "load_error",
  reason: "loading plugin 'broken' failed: ImportError: no module named vendorlib",
  options: [],
  devices: [],
};

const status = (plugins: PluginInfo[]): PluginsStatus => ({
  host_api_version: "1.0",
  sdk_version: "1.0.0",
  python: "/venv/bin/python",
  discovering: false,
  discovered_at_ns: Date.now() * 1e6,
  error: null,
  plugins,
});

const descriptor: DeviceDescriptor = {
  device_id: DEVICE_ID,
  display_name: "Motor-imagery EEG generator",
  kind: "simulated",
  adapter: "brainos-example-adapter@0.1.0",
  description: "Provided by the plugin …",
  native_format: "BrainOS adapter SDK 1.0 plugin",
  capabilities: [
    { capability: "recording", params: { channel_count: 8, sample_rate_hz: 250, unit: "uV" }, description: "" },
    { capability: "device_status", params: {}, description: "" },
  ],
  synthetic: true,
  modality: "eeg",
  invasive: false,
  integration: { kind: "plugin", package: "brainos-example-adapter", version: "0.1.0", api_version: "1.0", isolated: true },
};

const simA: DeviceDescriptor = {
  ...descriptor,
  device_id: "sim-a",
  display_name: "Simulated Profile A",
  adapter: "brainos.sim.profile_a@0.1.0",
  modality: null,
  invasive: null,
  integration: null,
};

const runtime = (device: DeviceDescriptor | null, state: RuntimeSnapshot["state"] = "streaming"): RuntimeSnapshot => ({
  state,
  device,
  session_id: device ? "ses_abcdef" : null,
  state_since_ns: 0,
  last_error: null,
  recording: null,
  apps: [],
});

describe("Plugins group in the source picker", () => {
  it("lists compatible and rejected plugins with plain reasons; plugin devices are not 'simulated profiles'", async () => {
    stubFetch({ "GET /plugins": () => status([example, rejected, broken]) });
    render(<SourcePicker devices={[simA, descriptor]} runtime={runtime(null, "idle")} onClose={vi.fn()} onSourcesChanged={vi.fn()} />);
    await screen.findByTestId("plugin-list");
    expect(screen.getByTestId("plugin-status-example-mi-eeg").textContent).toBe("brainos-example-adapter@0.1.0 · compatible");
    expect(screen.getByTestId("plugin-status-future-plugin").textContent).toMatch(
      /^future-plugin@3\.0\.0 · rejected: api_version: written for adapter SDK API 2\.0/,
    );
    expect(screen.getByTestId("plugin-status-broken").textContent).toMatch(/failed to load: .*ImportError/);
    // rejected plugins offer nothing to connect
    expect(within(screen.getByTestId("plugin-future-plugin")).queryByRole("button")).toBeNull();
    // the plugin's simulated device is in the Plugins group, not with the simulated profiles
    expect(within(screen.getByTestId("sim-list")).queryByText("Motor-imagery EEG generator")).toBeNull();
    const dev = screen.getByTestId(`plugin-device-${DEVICE_ID}`);
    expect(within(dev).getByText(/Simulated data · 8 channels · 250 Hz · EEG, noninvasive/)).toBeTruthy();
  });

  it("generates the options form and connects with the changed options only", async () => {
    const calls = stubFetch({
      "GET /plugins": () => status([example]),
      [`POST /plugins/example-mi-eeg/configure`]: () => descriptor,
      "POST /runtime/connect": () => runtime(descriptor),
    });
    const closed = vi.fn();
    const changed = vi.fn();
    render(<SourcePicker devices={[]} runtime={runtime(null, "idle")} onClose={closed} onSourcesChanged={changed} />);
    fireEvent.click(await screen.findByTestId(`plugin-options-${DEVICE_ID}-toggle`));
    const montage = screen.getByTestId(`${DEVICE_ID}-opt-montage`) as HTMLSelectElement;
    expect([...montage.options].map((o) => o.value)).toEqual(["8", "16"]);
    expect(montage.value).toBe("8");
    expect((screen.getByTestId(`${DEVICE_ID}-opt-seed`) as HTMLInputElement).value).toBe("1");
    expect((screen.getByTestId(`${DEVICE_ID}-opt-realtime`) as HTMLInputElement).checked).toBe(true);
    fireEvent.change(montage, { target: { value: "16" } });
    fireEvent.change(screen.getByTestId(`${DEVICE_ID}-opt-seed`), { target: { value: " 7 " } });
    fireEvent.click(screen.getByTestId(`plugin-connect-${DEVICE_ID}`));
    await waitFor(() => expect(closed).toHaveBeenCalled());
    const configure = calls.find((c) => c.path === "/plugins/example-mi-eeg/configure");
    expect(configure?.body).toEqual({ device_key: "mi-eeg", options: { seed: "7", montage: "16" } });
    expect(calls.at(-1)).toMatchObject({ method: "POST", path: "/runtime/connect", body: { device_id: DEVICE_ID } });
    expect(changed).toHaveBeenCalled();
  });

  it("shows the runtime's refusal (e.g. invalid options) and stays open", async () => {
    stubFetch({
      "GET /plugins": () => status([example]),
      [`POST /plugins/example-mi-eeg/configure`]: () =>
        apiError(400, "protocol_error", "invalid options: options.seed: 'x': expected an integer"),
    });
    const closed = vi.fn();
    render(<SourcePicker devices={[]} runtime={runtime(null, "idle")} onClose={closed} onSourcesChanged={vi.fn()} />);
    fireEvent.click(await screen.findByTestId(`plugin-connect-${DEVICE_ID}`));
    expect((await screen.findByTestId("plugin-error")).textContent).toBe(
      "protocol_error: invalid options: options.seed: 'x': expected an integer",
    );
    expect(closed).not.toHaveBeenCalled();
  });

  it("marks the connected plugin device and hides its controls", async () => {
    stubFetch({ "GET /plugins": () => status([example]) });
    render(<SourcePicker devices={[descriptor]} runtime={runtime(descriptor)} onClose={vi.fn()} onSourcesChanged={vi.fn()} />);
    const dev = await screen.findByTestId(`plugin-device-${DEVICE_ID}`);
    expect(within(dev).getByText("Connected")).toBeTruthy();
    expect(within(dev).queryByRole("button")).toBeNull();
  });

  it("says when no plugin is installed and can search again", async () => {
    const calls = stubFetch({
      "GET /plugins": () => status([]),
      "POST /plugins/discover": () => status([example]),
    });
    render(<SourcePicker devices={[]} runtime={runtime(null, "idle")} onClose={vi.fn()} onSourcesChanged={vi.fn()} />);
    expect((await screen.findByTestId("no-plugins")).textContent).toMatch(/No plugins installed/);
    fireEvent.click(screen.getByTestId("plugins-search"));
    await screen.findByTestId("plugin-example-mi-eeg");
    expect(calls.some((c) => c.method === "POST" && c.path === "/plugins/discover")).toBe(true);
  });
});

describe("Acquisition row for a plugin source", () => {
  it("shows the package, isolation and modality in words", () => {
    stubFetch({});
    render(<SourceRow runtime={runtime(descriptor)} onPick={vi.fn()} />);
    expect(screen.getByTestId("source-integration").textContent).toBe(
      "Plugin · brainos-example-adapter@0.1.0 · isolated · EEG, noninvasive",
    );
  });

  it("says when a plugin does not declare its modality; built-in sources without one show no line", () => {
    stubFetch({});
    render(<SourceRow runtime={runtime({ ...descriptor, modality: null, invasive: null })} onPick={vi.fn()} />);
    expect(screen.getByTestId("source-integration").textContent).toBe(
      "Plugin · brainos-example-adapter@0.1.0 · isolated · modality not declared",
    );
    cleanup();
    render(<SourceRow runtime={runtime(simA)} onPick={vi.fn()} />);
    expect(screen.queryByTestId("source-integration")).toBeNull();
  });
});

describe("plugin wording", () => {
  it("describes modality and invasiveness only as declared", () => {
    expect(modalityWords({ ...descriptor, modality: "intracortical", invasive: true })).toBe("Intracortical, implanted");
    expect(modalityWords({ ...descriptor, modality: "ecog", invasive: null })).toBe("ECoG, invasiveness not declared");
    expect(modalityWords({ ...descriptor, modality: null, invasive: true })).toBe("modality not declared, implanted");
    expect(modalityWords({ ...descriptor, modality: undefined, invasive: undefined })).toBe("modality not declared");
    expect(integrationLine(simA)).toBeNull();
    expect(integrationLine({ ...descriptor, integration: { kind: "plugin", package: "p", version: "1.2.3", isolated: false } })).toBe(
      "Plugin · p@1.2.3",
    );
  });

  it("sends only options the operator changed", () => {
    expect(changedOptions(example.options, { seed: "1", montage: "8", realtime: true })).toEqual({});
    expect(changedOptions(example.options, { seed: "", montage: "16", realtime: false })).toEqual({
      montage: "16",
      realtime: false,
    });
  });
});
