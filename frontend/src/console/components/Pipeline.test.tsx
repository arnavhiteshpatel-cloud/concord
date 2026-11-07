// Milestone 3 pipeline controls: start request built from the form, server refusals shown
// verbatim, status counters rendered, router mapping posted, calibration report shown.
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { RuntimeSnapshot } from "../../sdk";
import type { CalibrationResult, ModelInfo, PipelineStatus, RecordingInfo } from "../api";
import { apiError, stubFetch } from "../testFetch";
import { CalibrationPanel } from "./CalibrationPanel";
import { buildStartRequest } from "./PipelineControl";
import { PipelineView } from "./PipelineView";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const stats = { count: 0, p50: null, p95: null, p99: null, max: null };
const stopped: PipelineStatus = {
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
  counters: { inputs: 0, dropped_inputs: 0, features_out: 0, decoded_out: 0, commands_out: 0, errors: 0, queue_depth: 0 },
  processing_us: stats,
  pipeline_latency_ms: stats,
  last_error: null,
  started_at_ns: null,
};
const decoder = { model_id: "ridge-abc", dims: ["vx", "vy"] };
const running: PipelineStatus = {
  ...stopped,
  running: true,
  device_id: "lsl:ephys",
  session_id: "ses_1",
  preset: "spikeband_threshold",
  stages: ["bandpass 250-5000 Hz", "common average reference", "threshold crossings at -4.5 x RMS"],
  input_event_type: "recording.frame",
  output: {
    event_type: "features.binned",
    feature: "threshold_crossing_count",
    bin_ms: 20,
    channel_count: 16,
    channel_labels: null,
    unit: "count",
  },
  warmup_remaining_s: 0.4,
  decoder,
  counters: { inputs: 120, dropped_inputs: 3, features_out: 60, decoded_out: 60, commands_out: 0, errors: 0, queue_depth: 1 },
  processing_us: { count: 120, p50: 210, p95: 400, p99: 500, max: 900 },
  pipeline_latency_ms: { count: 60, p50: 1.25, p95: 2.5, p99: 3, max: 4 },
  compatibility_warnings: ["trained on another session"],
};
const presets = {
  spikeband_threshold: "Intracortical broadband",
  ecog_high_gamma: "ECoG",
  band_power: "Any rate",
  features_passthrough: "Passthrough",
};
const model: ModelInfo = {
  summary: {
    model_id: "ridge-abc",
    dims: ["vx", "vy"],
    input: { event_type: "features.binned", feature: "threshold_crossing_count", bin_ms: 20, channel_count: 16 },
    trained_on: "syn-cal.brainos.jsonl",
    held_out_r2: 0.612,
    held_out_samples: 200,
    control_mean_predictor_r2: -0.01,
  },
  compatible: null,
  errors: [],
  warnings: [],
};
const runtime: RuntimeSnapshot = {
  state: "streaming",
  device: null,
  session_id: "ses_1",
  state_since_ns: 1,
  last_error: null,
  recording: null,
  apps: [],
};

describe("buildStartRequest", () => {
  const base = {
    preset: "spikeband_threshold" as const,
    binMs: "",
    thresholdK: "-4.5",
    bandLow: "",
    bandHigh: "",
    modelId: "",
    allowCrossSource: true,
  };
  it("omits blank optional parameters and ignores cross-source without a model", () => {
    expect(buildStartRequest(base).request).toEqual({
      processing: { preset: "spikeband_threshold", threshold_k: -4.5 },
      model_id: null,
      allow_cross_source: false,
    });
  });
  it("sends only the parameters of the chosen preset", () => {
    const r = buildStartRequest({ ...base, preset: "band_power", binMs: "100", bandLow: "8", bandHigh: "30", modelId: "m" });
    expect(r.request).toEqual({
      processing: { preset: "band_power", bin_ms: 100, band_low_hz: 8, band_high_hz: 30 },
      model_id: "m",
      allow_cross_source: true,
    });
    expect(buildStartRequest({ ...base, preset: "features_passthrough", binMs: "20" }).request?.processing).toEqual({
      preset: "features_passthrough",
    });
  });
  it("rejects missing band edges and non-numbers locally", () => {
    expect(buildStartRequest({ ...base, preset: "band_power", bandLow: "8" }).problem).toMatch(/band/);
    expect(buildStartRequest({ ...base, binMs: "abc" }).problem).toBe("bin_ms must be a number");
  });
});

describe("PipelineView", () => {
  it("starts with the form's request and shows an incompatible-decoder refusal verbatim", async () => {
    const calls = stubFetch({
      "GET /pipeline": () => stopped,
      "GET /pipeline/presets": () => presets,
      "GET /models": () => [model],
      "POST /pipeline/start": () =>
        apiError(409, "incompatible_decoder", "model expects 20 ms bins; pipeline outputs 50 ms"),
    });
    render(<PipelineView runtime={runtime} recordings={[]} notify={vi.fn()} />);
    await screen.findByRole("option", { name: "ridge-abc" });
    fireEvent.change(screen.getByTestId("pl-bin"), { target: { value: "50" } });
    fireEvent.change(screen.getByTestId("pl-model"), { target: { value: "ridge-abc" } });
    expect(screen.getByTestId("model-details").textContent).toContain("0.612");
    expect(screen.getByTestId("model-compat").textContent).toMatch(/checked against the pipeline output when it starts/);
    fireEvent.click(screen.getByTestId("pl-cross"));
    expect(screen.getByTestId("pl-cross-warning").textContent).toMatch(/not expected to be meaningful/);
    fireEvent.click(screen.getByTestId("pl-start"));
    expect((await screen.findByTestId("pl-error")).textContent).toBe(
      "incompatible_decoder: model expects 20 ms bins; pipeline outputs 50 ms",
    );
    expect(calls.find((c) => c.path === "/pipeline/start")?.body).toEqual({
      processing: { preset: "spikeband_threshold", bin_ms: 50, threshold_k: -4.5 },
      model_id: "ridge-abc",
      allow_cross_source: true,
    });
  });

  it("cannot start without a connected device", async () => {
    stubFetch({ "GET /pipeline": () => stopped, "GET /pipeline/presets": () => presets, "GET /models": () => [] });
    render(<PipelineView runtime={{ ...runtime, state: "idle" }} recordings={[]} notify={vi.fn()} />);
    await screen.findByRole("option", { name: "band_power" });
    expect((screen.getByTestId("pl-start") as HTMLButtonElement).disabled).toBe(true);
  });

  it("renders status: stages, output, warm-up, counters, latency percentiles, warnings", async () => {
    stubFetch({ "GET /pipeline": () => running, "GET /pipeline/presets": () => presets, "GET /models": () => [] });
    render(<PipelineView runtime={runtime} recordings={[]} notify={vi.fn()} />);
    await screen.findByTestId("pl-stages");
    expect(screen.getByTestId("pl-running").textContent).toBe("running");
    expect(screen.getByTestId("pl-output").textContent).toBe(
      "features.binned · threshold_crossing_count · 20 ms · 16 ch · count",
    );
    expect(screen.getByTestId("pl-warmup").textContent).toMatch(/0\.4 s/);
    const counters = screen.getByTestId("pl-counters");
    for (const [k, v] of [
      ["inputs", "120"],
      ["dropped_inputs", "3"],
      ["features_out", "60"],
      ["decoded_out", "60"],
      ["commands_out", "0"],
      ["errors", "0"],
      ["queue_depth", "1"],
    ])
      expect(counters.querySelector(`[data-counter="${k}"] .kpi-value`)!.textContent).toBe(v);
    expect(counters.querySelector('[data-counter="dropped_inputs"] .kpi')!.className).toContain("tone-warn");
    const lat = screen.getByTestId("pl-latency").textContent!;
    expect(lat).toContain("210");
    expect(lat).toContain("1.25");
    expect(screen.getByTestId("pl-warnings").textContent).toContain("trained on another session");
    expect(screen.getByTestId("router-state").textContent).toMatch(/OFF — no commands reach apps/);
  });

  it("turns the router on with dims from the loaded decoder", async () => {
    const calls = stubFetch({
      "GET /pipeline": () => running,
      "GET /pipeline/presets": () => presets,
      "GET /models": () => [],
      "POST /pipeline/router": (b) => ({ ...running, router: b }),
    });
    const notify = vi.fn();
    render(<PipelineView runtime={runtime} recordings={[]} notify={notify} />);
    const x = (await screen.findByTestId("router-x")) as HTMLSelectElement;
    expect([...x.options].map((o) => o.value)).toEqual(["vx", "vy"]);
    expect((screen.getByTestId("router-y") as HTMLSelectElement).value).toBe("vy");
    fireEvent.change(screen.getByTestId("router-gain"), { target: { value: "0.5" } });
    fireEvent.click(screen.getByTestId("router-invert"));
    fireEvent.click(screen.getByTestId("router-on"));
    await waitFor(() => expect(notify).toHaveBeenCalledWith("Router ON: vx/vy → pointer"));
    expect(calls.find((c) => c.path === "/pipeline/router")?.body).toEqual({
      enabled: true,
      x_dim: "vx",
      y_dim: "vy",
      gain: 0.5,
      deadzone: 0.3,
      invert_y: true,
      max_speed: 2,
    });
  });

  it("shows no router controls without a decoder", async () => {
    stubFetch({
      "GET /pipeline": () => ({ ...running, decoder: null }),
      "GET /pipeline/presets": () => presets,
      "GET /models": () => [],
    });
    render(<PipelineView runtime={runtime} recordings={[]} notify={vi.fn()} />);
    await screen.findByTestId("pl-stages");
    expect(screen.queryByTestId("router-on")).toBeNull();
    expect(screen.getByTestId("router-panel").textContent).toMatch(/only while the router is ON/);
  });
});

const rec = (name: string, active = false): RecordingInfo => ({
  name,
  device_id: "lsl:ephys",
  device_name: "LSL",
  synthetic: true,
  created_at_ns: 1,
  size_bytes: 2048,
  events: 900,
  active,
});
const result: CalibrationResult = {
  model: { model_id: "ridge-new", dims: ["vx", "vy"] },
  report: {
    model_id: "ridge-new",
    recordings: ["syn-cal.brainos.jsonl"],
    source_identity: "lsl:brainos-synthetic-ephys",
    prerecorded_source: false,
    synthetic_source: true,
    bins_total: 1000,
    labelled_bins: 990,
    train_bins: 800,
    gap_bins: 12,
    test_bins: 188,
    alpha: 1,
    samples: 180,
    r2: 0.55,
    r2_per_dim: { vx: 0.6, vy: 0.5 },
    control_mean_predictor_r2: -0.02,
  },
  report_markdown: "",
};

describe("CalibrationPanel", () => {
  it("trains on the selected closed recordings and shows the returned report", async () => {
    const calls = stubFetch({ "POST /calibration/train": () => result });
    const onTrained = vi.fn();
    render(<CalibrationPanel recordings={[rec("syn-cal"), rec("live-now", true)]} onTrained={onTrained} />);
    expect(screen.queryByTestId("cal-rec-live-now")).toBeNull(); // still being written
    expect((screen.getByTestId("cal-train") as HTMLButtonElement).disabled).toBe(true);
    fireEvent.click(screen.getByTestId("cal-rec-syn-cal"));
    fireEvent.change(screen.getByTestId("cal-source"), { target: { value: "brainos.pipeline" } });
    fireEvent.change(screen.getByTestId("cal-fraction"), { target: { value: "0.7" } });
    fireEvent.click(screen.getByTestId("cal-train"));
    await screen.findByTestId("cal-report");
    expect(calls[0]!.body).toEqual({
      recordings: ["syn-cal"],
      train_fraction: 0.7,
      gap_bins: 12,
      feature_source: "brainos.pipeline",
    });
    expect(onTrained).toHaveBeenCalledWith(result);
    expect(screen.getByTestId("cal-model-id").textContent).toBe("ridge-new");
    expect(screen.getByTestId("cal-r2").textContent).toBe("0.550");
    const report = screen.getByTestId("cal-report").textContent!;
    expect(report).toContain("vx 0.600 · vy 0.500");
    expect(report).toContain("train 800 · gap 12 · held-out 188");
    expect(report).toContain("synthetic data");
    expect(screen.getByTestId("cal-disclaimer").textContent).toMatch(/does not establish closed-loop performance/);
  });

  it("shows the server's message when calibration fails", async () => {
    stubFetch({
      "POST /calibration/train": () => apiError(400, "protocol_error", "calibration failed: only 12 labelled bins"),
    });
    render(<CalibrationPanel recordings={[rec("short")]} onTrained={vi.fn()} />);
    fireEvent.click(screen.getByTestId("cal-rec-short"));
    fireEvent.click(screen.getByTestId("cal-train"));
    expect((await screen.findByTestId("cal-error")).textContent).toBe(
      "protocol_error: calibration failed: only 12 labelled bins",
    );
  });
});
