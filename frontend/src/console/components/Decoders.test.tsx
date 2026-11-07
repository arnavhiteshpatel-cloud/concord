// Milestone 5 (workstream A): the Decoder row says what runs (origin, family, where), whether it
// fits the source, drift; the start sheet offers decoded passthrough and the channel mapping
// only when they apply; unsafe model files need an explicit trust decision; calibration starts
// from the output the decoder should produce.
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { RuntimeSnapshot } from "../../sdk";
import type { CalibrationResult, ModelInfo, PipelineStatus } from "../api";
import { driftLine, originLabel } from "../decoders";
import type { PipelineState } from "../pipeline";
import { apiError, stubFetch } from "../testFetch";
import { CalibrationPanel } from "./CalibrationPanel";
import { DecoderRow } from "./DecoderRow";
import { buildStartRequest } from "./PipelineControl";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const stats = { count: 0, p50: null, p95: null, p99: null, max: null };
const base: PipelineStatus = {
  available: true,
  unavailable_reason: null,
  running: true,
  device_id: "t15:block",
  session_id: "ses_1",
  preset: "features_passthrough",
  stages: [],
  input_event_type: "features.binned",
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
  started_at_ns: 1,
};
const monitor = (recommended: boolean) => ({
  window_bins: 500,
  bins: 600,
  features: { available: true, shift_z_rms: recommended ? 1.4 : 0.1 },
  labels: null,
  recalibration_recommended: recommended,
  reasons: recommended ? ["input features moved 1.40 training SD (RMS over channels; threshold 0.5)"] : [],
});
const plugin = {
  model_id: "example-mi-lateralization-0.1.0",
  dims: ["rest", "left", "right"],
  outputs: { type: "classes" as const, classes: ["rest", "left", "right"] },
  origin: "plugin" as const,
  family: "example-lateralization",
  execution: "isolated" as const,
  state: "ready" as const,
  compatibility: { ok: true, errors: [], warnings: [], cross_source: false, mapping_applied: true, mapping_notes: [] },
  monitor: monitor(false),
};
const pipe = (status: PipelineStatus | null): PipelineState => ({ status, error: null, set: vi.fn() });
const device = (caps: string[]) => ({
  device_id: "t15:block",
  display_name: "T15",
  kind: "replay" as const,
  adapter: "brainos.cursorclick@0.1.0",
  description: "",
  native_format: "",
  capabilities: caps.map((c) => ({ capability: c as "neural_features", params: {}, description: "" })),
  synthetic: false,
});
const runtime = (caps: string[] = ["neural_features"]): RuntimeSnapshot => ({
  state: "streaming",
  device: device(caps),
  session_id: "ses_1",
  state_since_ns: 1,
  last_error: null,
  recording: null,
  apps: [],
});
const row = (status: PipelineStatus | null, rt = runtime()) =>
  render(<DecoderRow runtime={rt} pipeline={pipe(status)} recordings={[]} replayedModel={null} onRecordingsChanged={vi.fn()} />);

describe("Decoder row (M5)", () => {
  it("names origin, family and where the decoder runs; mapping and compatibility", () => {
    row({ ...base, decoder: plugin, decoders: [plugin], channel_mapping: true });
    expect(screen.getByTestId("decoder-origin").textContent).toBe(
      "Decoder plugin · example-lateralization · isolated process · compatible with this source · channels mapped by label (operator enabled)",
    );
    expect(screen.getByTestId("decoder-drift").textContent).toBe("No drift from the training data detected");
  });

  it("recommends recalibration with the reason, and reports a stopped decoder", () => {
    const failed = { ...plugin, state: "failed" as const, error: "InvalidOutput: decoder produced an invalid output", monitor: monitor(true) };
    row({ ...base, decoder: failed, decoders: [failed] });
    expect(screen.getByTestId("decoder-drift").textContent).toBe(
      "Recalibration recommended: input features moved 1.40 training SD (RMS over channels; threshold 0.5)",
    );
    expect(screen.getByTestId("decoder-drift").className).toContain("caution-text");
    expect(screen.getByTestId("decoder-failed").textContent).toBe("Decoder stopped: InvalidOutput: decoder produced an invalid output");
  });

  it("shows the source's own decoders in decoded passthrough, labelled historical or external", () => {
    const src = (id: string, origin: "historical" | "external", dims: string[], q: string) => ({
      model_id: id,
      dims,
      quantity: q,
      origin,
      model_origin: origin,
      family: "decoded_passthrough",
      received: 120,
    });
    row({
      ...base,
      preset: "decoded_passthrough",
      source_decoders: [
        src("t15-historical-velocity", "historical", ["vx", "vy"], "velocity"),
        src("bci2000:control", "external", ["ch1"], "control_signal"),
      ],
    });
    const text = screen.getByTestId("decoder-source-outputs").textContent!;
    expect(text).toContain("Historical decoder replay (original research system): t15-historical-velocity → vx, vy (velocity, 120 received)");
    expect(text).toContain("External decoder: bci2000:control → ch1");
    expect(screen.getByTestId("decoder-state").textContent).toBe("Running · Source decoder outputs (passthrough)");
    expect(screen.queryByText("No model: features only.")).toBeNull();
  });

  it("offers decoded passthrough only for sources that provide decoder outputs", async () => {
    const presets = { features_passthrough: "Passthrough", band_power: "Any rate", decoded_passthrough: "Source decoders" };
    const calls = stubFetch({ "GET /pipeline/presets": () => presets, "GET /models": () => [], "POST /pipeline/start": () => base });
    row({ ...base, running: false }, runtime(["neural_features"]));
    fireEvent.click(screen.getByTestId("start-decoding-open"));
    const sel = (await screen.findByTestId("pl-preset")) as HTMLSelectElement;
    expect([...sel.options].map((o) => o.value)).toEqual(["features_passthrough", "band_power"]);
    cleanup();
    row({ ...base, running: false }, runtime(["neural_features", "kinematic_intent"]));
    fireEvent.click(screen.getByTestId("start-decoding-open"));
    const sel2 = (await screen.findByTestId("pl-preset")) as HTMLSelectElement;
    fireEvent.change(sel2, { target: { value: "decoded_passthrough" } });
    expect(screen.queryByTestId("pl-model")).toBeNull();
    expect(screen.getByTestId("pl-passthrough").textContent).toMatch(/No model is loaded/);
    fireEvent.click(screen.getByTestId("pl-start"));
    await waitFor(() => expect(calls.some((c) => c.path === "/pipeline/start")).toBe(true));
    expect(calls.find((c) => c.path === "/pipeline/start")!.body).toEqual({
      processing: { preset: "decoded_passthrough" },
      model_id: null,
      allow_cross_source: false,
    });
  });

  it("offers the channel mapping only when it applies, and sends it explicitly", async () => {
    const info = (id: string, mapping: boolean): ModelInfo => ({
      summary: { ...plugin, model_id: id, input: { feature: "log_band_power", bin_ms: 100, channel_count: 2 } },
      compatible: false,
      errors: ["input 1 (log_band_power): model expects 2 channels labelled C3, C4; source provides 8 channels"],
      warnings: [],
      mapping_available: mapping,
      checked_against: "band_power preview",
    });
    const calls = stubFetch({
      "GET /pipeline/presets": () => ({ features_passthrough: "Passthrough" }),
      "GET /models": () => [info("needs-map", true), info("no-map", false)],
      "POST /pipeline/start": () => base,
    });
    row({ ...base, running: false });
    fireEvent.click(screen.getByTestId("start-decoding-open"));
    await screen.findByRole("option", { name: "needs-map (incompatible)" });
    fireEvent.change(screen.getByTestId("pl-model"), { target: { value: "no-map" } });
    expect(screen.queryByTestId("pl-mapping")).toBeNull();
    fireEvent.change(screen.getByTestId("pl-model"), { target: { value: "needs-map" } });
    expect(screen.getByTestId("model-origin").textContent).toBe("Decoder plugin · example-lateralization · isolated process");
    expect(screen.getByTestId("model-compat").textContent).toBe("Not compatible with this processing (band_power preview).");
    fireEvent.click(screen.getByTestId("pl-mapping"));
    expect(screen.getByTestId("pl-mapping-warning").textContent).toMatch(/logged and shown/);
    fireEvent.click(screen.getByTestId("pl-start"));
    await waitFor(() => expect(calls.some((c) => c.path === "/pipeline/start")).toBe(true));
    expect(calls.find((c) => c.path === "/pipeline/start")!.body).toMatchObject({
      model_id: "needs-map",
      allow_channel_mapping: true,
    });
  });

  it("refuses an unsafe model file until the operator marks it trusted", async () => {
    const pk: ModelInfo = {
      summary: { model_id: "pickled", dims: ["vx", "vy"], origin: "imported", family: "sklearn", execution: "isolated", format: "pickle", unsafe_format: true, trust: null },
      compatible: false,
      errors: ["this file format can run code when loaded; it stays refused until you mark this exact file trusted"],
      warnings: [],
    };
    const calls = stubFetch({
      "GET /pipeline/presets": () => ({ features_passthrough: "Passthrough" }),
      "GET /models": () => [pk],
      "POST /models/pickled/trust": () => ({ model_id: "pickled", trust: { sha256: "ab", by: "operator", at_ns: 1, format: "pickle", file: "p.pkl" } }),
    });
    row({ ...base, running: false });
    fireEvent.click(screen.getByTestId("start-decoding-open"));
    await screen.findByRole("option", { name: "pickled (incompatible)" });
    fireEvent.change(screen.getByTestId("pl-model"), { target: { value: "pickled" } });
    expect(screen.getByTestId("model-trust").textContent).toMatch(/runs code from the file when it is loaded/);
    fireEvent.click(screen.getByTestId("model-trust-btn"));
    await waitFor(() => expect(calls.some((c) => c.path === "/models/pickled/trust")).toBe(true));
    expect(calls.find((c) => c.path === "/models/pickled/trust")!.body).toEqual({ trusted: true });
  });
});

describe("Calibration by output capability", () => {
  const rec = { name: "cc", device_id: "t15", device_name: "T15", synthetic: false, created_at_ns: 1, size_bytes: 1, events: 1, active: false };
  const options = {
    capabilities: [
      { name: "continuous", label: "Continuous movement", needs: "continuous targets", metrics: "R²", default_family: "ridge", families: [{ name: "ridge", description: "" }, { name: "kalman", description: "" }] },
      { name: "classes", label: "Discrete classes", needs: "class codes", metrics: "", default_family: "lda", families: [{ name: "lda", description: "" }] },
      { name: "click", label: "Click", needs: "a 0/1 click label", metrics: "", default_family: "lda", families: [{ name: "lda", description: "" }, { name: "click", description: "" }] },
    ],
  };

  it("checks the labels for the chosen output and reports click events", async () => {
    const result: CalibrationResult = {
      model: { model_id: "click-1", dims: ["click"] },
      report: {
        model_id: "click-1", recordings: ["cc"], source_identity: "t15", prerecorded_source: true, synthetic_source: false,
        bins_total: 1000, labelled_bins: 1000, train_bins: 800, gap_bins: 12, test_bins: 188, alpha: 0, samples: 180,
        r2: undefined as unknown as number, r2_per_dim: {}, control_mean_predictor_r2: 0, capability: "click", family: "click",
        events: { event_precision: 0.75, event_recall: 0.6, event_f1: 0.667, true_events: 5, detected_events: 4, false_positives_per_min: 0.3, roc_auc: 0.91, tolerance_ms: 300 },
      },
      report_markdown: "",
    };
    const calls = stubFetch({
      "GET /calibration/options": () => options,
      "POST /calibration/check": (b) =>
        (b as { label_dim?: string }).label_dim === "vx"
          ? { capability: "click", ok: false, problems: ["a click label must be 0 (no click) / 1 (click); 'vx' has values [-0.4, 0.2]"], notes: [], label_dims: [], bins: 0, labelled_bins: 0, classes: null, events: null }
          : { capability: "click", ok: true, problems: [], notes: [], label_dims: ["click"], bins: 1000, labelled_bins: 1000, classes: ["no_click", "click"], events: 25 },
      "POST /calibration/train": () => result,
    });
    render(<CalibrationPanel recordings={[rec]} onTrained={vi.fn()} />);
    await waitFor(() => expect(calls.some((c) => c.path === "/calibration/options")).toBe(true));
    fireEvent.click(screen.getByTestId("cal-rec-cc"));
    fireEvent.change(screen.getByTestId("cal-capability"), { target: { value: "click" } });
    expect(screen.getByTestId("cal-needs").textContent).toMatch(/One calibration task does not fit every modality/);
    fireEvent.change(screen.getByTestId("cal-label-dim"), { target: { value: "vx" } });
    fireEvent.click(screen.getByTestId("cal-check"));
    expect((await screen.findByTestId("cal-check-result")).textContent).toMatch(/must be 0 \(no click\) \/ 1/);
    fireEvent.change(screen.getByTestId("cal-label-dim"), { target: { value: "click" } });
    fireEvent.change(await screen.findByTestId("cal-family"), { target: { value: "click" } });
    fireEvent.click(screen.getByTestId("cal-check"));
    await waitFor(() => expect(screen.getByTestId("cal-check-result").textContent).toMatch(/25 click events/));
    fireEvent.click(screen.getByTestId("cal-train"));
    await screen.findByTestId("cal-report");
    expect(calls.find((c) => c.path === "/calibration/train")!.body).toEqual({
      recordings: ["cc"],
      train_fraction: 0.8,
      gap_bins: 12,
      feature_source: null,
      capability: "click",
      family: "click",
      label_dim: "click",
    });
    expect(screen.getByTestId("cal-events").textContent).toMatch(/precision 0\.750 · recall 0\.600/);
    expect(screen.getByTestId("cal-events").textContent).toMatch(/5 clicks, 4 detected within ±300 ms/);
  });

  it("shows the server's refusal when the recordings lack the labels", async () => {
    stubFetch({
      "GET /calibration/options": () => options,
      "POST /calibration/train": () => apiError(400, "protocol_error", "calibration failed: the behavior dims ['click'] hold small integer codes, not continuous targets"),
    });
    render(<CalibrationPanel recordings={[rec]} onTrained={vi.fn()} />);
    fireEvent.click(screen.getByTestId("cal-rec-cc"));
    fireEvent.click(screen.getByTestId("cal-train"));
    expect((await screen.findByTestId("cal-error")).textContent).toMatch(/small integer codes, not continuous targets/);
  });
});

describe("decoder wording", () => {
  it("never relabels external or historical outputs", () => {
    expect(originLabel("historical")).toBe("Historical decoder replay (original research system)");
    expect(originLabel("external")).toBe("External decoder");
    expect(originLabel("brainos-trained")).toBe("BrainOS-trained");
    expect(driftLine(null)).toBeNull();
  });

  it("buildStartRequest leaves the mapping out unless enabled with a model", () => {
    const form = { preset: "band_power" as const, binMs: "100", thresholdK: "", bandLow: "8", bandHigh: "13", modelId: "", allowCrossSource: false, allowChannelMapping: true };
    expect(buildStartRequest(form).request).not.toHaveProperty("allow_channel_mapping");
    expect(buildStartRequest({ ...form, modelId: "m" }).request).toMatchObject({ allow_channel_mapping: true });
  });
});
