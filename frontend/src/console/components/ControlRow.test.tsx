// Command output row (Milestone 4): authorized applications (default deny, Authorize / Revoke,
// what each app would receive) and the discrete-action rules editor for classifier decoders.
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { AppControl, ControlStatus, PipelineStatus, RouterSpec } from "../api";
import type { PipelineState } from "../pipeline";
import { stubFetch } from "../testFetch";
import { CalibrationPanel } from "./CalibrationPanel";
import { ControlRow, defaultRules, describeApp, discreteSpec, routerSpec } from "./ControlRow";
import { actionLabel, mappingText } from "../pipeline";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const stats = { count: 0, p50: null, p95: null, p99: null, max: null };
const base: PipelineStatus = {
  available: true,
  unavailable_reason: null,
  running: true,
  device_id: "mi",
  session_id: "ses_1",
  preset: "band_power",
  stages: [],
  input_event_type: "recording.frame",
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
const classifier: PipelineStatus = {
  ...base,
  decoder: { model_id: "mi-lda-1", dims: ["rest", "left", "right"], outputs: { type: "classes", classes: ["rest", "left", "right"] } },
};
const ridge: PipelineStatus = { ...base, decoder: { model_id: "ridge-1", dims: ["vx", "vy"], outputs: { type: "continuous" } } };
const state = (status: PipelineStatus, set = vi.fn()): PipelineState => ({ status, error: null, set });

const app = (over: Partial<AppControl>): AppControl => ({
  app_id: "reference-menu",
  name: "Reference menu app",
  kind: "sdk",
  connections: 1,
  status: "suspended",
  requested: ["selection", "text_intent"],
  required: ["selection"],
  authorized: [],
  authorized_at_ns: null,
  receiving: [],
  waiting: [
    { capability: "selection", reason: "not_authorized", required: true },
    { capability: "text_intent", reason: "unsupported_by_device", required: false },
  ],
  refused_commands: 0,
  ...over,
});
const discreteRouter: RouterSpec = {
  enabled: true,
  x_dim: null,
  y_dim: null,
  gain: 1,
  deadzone: 0.3,
  invert_y: false,
  max_speed: 2,
  discrete: [
    { output: "left", action: "primary", threshold: 0.8, hold_ms: 300, refractory_ms: 1000 },
    { output: "right", action: "activate", threshold: 0.8, hold_ms: 300, refractory_ms: 1000 },
  ],
};
const control = (apps: AppControl[], over: Partial<ControlStatus> = {}): ControlStatus => ({
  router_on: true,
  model_id: "mi-lda-1",
  provides: ["selection"],
  router: discreteRouter,
  stall_limit_ms: 1000,
  last_stop: null,
  apps,
  history: [],
  ...over,
});

describe("Authorized applications", () => {
  it("describes each app in one plain sentence: what it would receive, or receives", () => {
    expect(describeApp(app({}), ["selection"], discreteRouter)).toBe(
      "Not authorized. Would receive discrete actions (select, activate).",
    );
    expect(
      describeApp(app({ authorized: ["selection"], receiving: ["selection"], status: "active", waiting: [] }), ["selection"], discreteRouter),
    ).toBe("Receiving discrete actions (select, activate).");
    expect(describeApp(app({ connections: 0, authorized: ["selection"] }), [], null)).toBe("Not connected. Authorized for discrete actions.");
    const board = app({
      requested: ["selection", "pointer_intent"],
      waiting: [
        { capability: "selection", reason: "unsupported_by_device", required: true },
        { capability: "pointer_intent", reason: "not_authorized", required: false },
      ],
    });
    expect(describeApp(board, ["pointer_intent"], null)).toBe(
      "Not authorized. Would receive pointer movement. It cannot run without discrete actions, which command output does not provide now.",
    );
    expect(describeApp(app({ requested: ["pointer_intent"] }), [], null)).toBe(
      "Not authorized. Asks for pointer movement; command output does not provide it now.",
    );
  });

  it("authorizes and revokes by app id; hides the console and logs nothing it did not do", async () => {
    let current = control([app({}), app({ app_id: "operator-console", name: "Operator Console", kind: "console" })]);
    const calls = stubFetch({
      "GET /control": () => current,
      "GET /pipeline": () => classifier,
      "POST /control/apps/reference-menu/authorize": (b) => {
        current = control([app({ authorized: ["selection", "text_intent"], receiving: ["selection"], status: "active", waiting: [] })]);
        expect(b).toEqual({ capabilities: ["selection", "text_intent"] });
        return current;
      },
      "POST /control/apps/reference-menu/revoke": () => {
        current = control([app({})]);
        return current;
      },
    });
    render(<ControlRow pipeline={state({ ...classifier, router: discreteRouter })} apps={[]} />);
    await screen.findByTestId("control-apps");
    expect(screen.queryByTestId("control-app-operator-console")).toBeNull();
    expect(screen.getByTestId("control-app-line-reference-menu").textContent).toMatch(/^Not authorized/);
    expect(screen.queryByTestId("revoke-reference-menu")).toBeNull();
    fireEvent.click(screen.getByTestId("authorize-reference-menu"));
    await waitFor(() => expect(screen.getByTestId("control-app-line-reference-menu").textContent).toMatch(/^Receiving/));
    expect(screen.queryByTestId("authorize-reference-menu")).toBeNull();
    fireEvent.click(screen.getByTestId("revoke-reference-menu"));
    await waitFor(() => expect(calls.some((c) => c.path === "/control/apps/reference-menu/revoke")).toBe(true));
    await waitFor(() => expect(screen.getByTestId("control-app-line-reference-menu").textContent).toMatch(/^Not authorized/));
  });

  it("shows nothing when no application asks for commands", async () => {
    stubFetch({ "GET /control": () => control([]) });
    render(<ControlRow pipeline={state(classifier)} apps={[]} />);
    await waitFor(() => expect(screen.getByTestId("router-state")).toBeTruthy());
    await new Promise((r) => setTimeout(r, 20));
    expect(screen.queryByTestId("control-apps")).toBeNull();
  });
});

describe("Discrete actions (classifier decoders)", () => {
  it("defaults: rest does nothing, other classes get select, activate, cancel", () => {
    expect(defaultRules(["rest", "left", "right", "feet"]).map((r) => r.action)).toEqual(["", "primary", "activate", "cancel"]);
    const rules = defaultRules(["rest", "left"]);
    rules[1] = { ...rules[1]!, action: "text", text: " yes " };
    expect(discreteSpec(rules, true).spec?.discrete).toEqual([
      { output: "left", action: "text", threshold: 0.8, hold_ms: 300, refractory_ms: 1000, text: "yes" },
    ]);
    expect(discreteSpec(defaultRules(["rest"]), true).problem).toMatch(/at least one class/);
    const bad = defaultRules(["a", "b"]);
    bad[0] = { ...bad[0]!, threshold: "1.5" };
    expect(discreteSpec(bad, true).problem).toMatch(/threshold/);
  });

  it("the rules editor appears only for a classifier, and Start control posts the rules", async () => {
    const calls = stubFetch({ "POST /pipeline/router": (b) => ({ ...classifier, router: b }), "GET /control": () => control([]) });
    const set = vi.fn();
    render(<ControlRow pipeline={state(classifier, set)} apps={[]} />);
    expect(screen.getByTestId("control-what").textContent).toBe(
      "When started, authorized apps receive select when left is held, activate when right is held.",
    );
    fireEvent.click(screen.getByTestId("control-settings-toggle"));
    expect(screen.queryByTestId("router-x")).toBeNull(); // no pointer mapping for a classifier
    expect(screen.queryByTestId("rule-threshold-rest")).toBeNull(); // no action -> no fields
    fireEvent.change(screen.getByTestId("rule-action-right"), { target: { value: "cancel" } });
    fireEvent.change(screen.getByTestId("rule-hold-left"), { target: { value: "500" } });
    fireEvent.click(screen.getByTestId("router-on"));
    await waitFor(() => expect(set).toHaveBeenCalled());
    expect(calls.find((c) => c.path === "/pipeline/router")?.body).toEqual({
      enabled: true,
      x_dim: null,
      y_dim: null,
      gain: 1,
      deadzone: 0.3,
      invert_y: false,
      max_speed: 2,
      discrete: [
        { output: "left", action: "primary", threshold: 0.8, hold_ms: 500, refractory_ms: 1000 },
        { output: "right", action: "cancel", threshold: 0.8, hold_ms: 300, refractory_ms: 1000 },
      ],
    });
  });

  it("a continuous decoder gets the pointer settings, never the rules editor", () => {
    stubFetch({ "GET /control": () => control([]) });
    render(<ControlRow pipeline={state(ridge)} apps={[]} />);
    fireEvent.click(screen.getByTestId("control-settings-toggle"));
    expect(screen.getByTestId("router-x")).toBeTruthy();
    expect(screen.queryByTestId("rules-editor")).toBeNull();
  });

  it("states the active rules when on, and why control last stopped when off", () => {
    stubFetch({ "GET /control": () => control([]) });
    render(<ControlRow pipeline={state({ ...classifier, router: discreteRouter })} apps={[]} />);
    expect(screen.getByTestId("router-state").textContent).toBe("On · select ← left; activate ← right");
    cleanup();
    const stop = { at_ns: 1, on: false, reason: "input stalled: no decoder input for 1200 ms (limit 1000)" };
    render(<ControlRow pipeline={state({ ...classifier, router: { ...discreteRouter, enabled: false }, last_router_stop: stop })} apps={[]} />);
    expect(screen.getByTestId("router-last-stop").textContent).toBe(`Last stopped: ${stop.reason}.`);
  });
});

describe("CalibrationPanel (classifier)", () => {
  it("trains a classifier with class names and shows accuracy against chance and the confusion matrix", async () => {
    const report = {
      kind: "classifier",
      model_id: "classes-cue-lda-1",
      recordings: ["mi.concord.jsonl"],
      source_identity: "concord:test",
      prerecorded_source: false,
      synthetic_source: true,
      classes: ["rest", "left", "right"],
      balanced_accuracy: 0.659,
      accuracy: 0.649,
      chance_balanced_accuracy: 1 / 3,
      chance_majority_accuracy: 0.387,
      control_time_shift_balanced_accuracy: 0.313,
      per_class_accuracy: { rest: 0.67, left: 0.8, right: 0.5 },
      confusion: [
        [51, 18, 7],
        [11, 72, 7],
        [36, 16, 53],
      ],
      samples: 271,
    };
    const calls = stubFetch({
      "POST /calibration/train": () => ({ model: { model_id: "classes-cue-lda-1", dims: ["rest", "left", "right"] }, report, report_markdown: "" }),
    });
    const rec = { name: "mi", device_id: "mi", device_name: "MI", synthetic: true, created_at_ns: 1, size_bytes: 1, events: 1, active: false };
    render(<CalibrationPanel recordings={[rec]} onTrained={vi.fn()} />);
    expect(screen.queryByTestId("cal-classes")).toBeNull(); // only for a classifier
    fireEvent.click(screen.getByTestId("cal-rec-mi"));
    fireEvent.change(screen.getByTestId("cal-capability"), { target: { value: "classes" } });
    fireEvent.change(screen.getByTestId("cal-classes"), { target: { value: "rest, left ,right" } });
    fireEvent.click(screen.getByTestId("cal-train"));
    await screen.findByTestId("cal-report");
    expect(calls.find((c) => c.path === "/calibration/train")?.body).toEqual({
      recordings: ["mi"],
      train_fraction: 0.8,
      gap_bins: 12,
      feature_source: null,
      capability: "classes",
      class_names: ["rest", "left", "right"],
    });
    expect(screen.getByTestId("cal-bacc").textContent).toBe("0.659");
    expect(screen.getByTestId("cal-report").textContent).toContain("chance 0.333");
    expect(screen.getByTestId("cal-report").textContent).toContain("synthetic data");
    expect(screen.getByTestId("cal-confusion").querySelectorAll("tbody tr")).toHaveLength(3);
  });
});

describe("Schema 1.4 command output settings (M5-C)", () => {
  const form = { x_dim: "vx", y_dim: "vy", gain: "1", deadzone: "0", invert_y: true, max_speed: "2" };
  it("adds a click from a separate decoder output, and refuses a click on a pointer dimension", () => {
    const ok = routerSpec({ ...form, click_dim: "click", click_threshold: "0.6", click_min_confidence: "0.7", click_refractory_ms: "400" }, true);
    expect(ok.spec?.click).toEqual({ output: "click", threshold: 0.6, min_confidence: 0.7, refractory_ms: 400 });
    expect(mappingText(ok.spec!)).toContain("click ← click");
    expect(routerSpec({ ...form, click_dim: "vx" }, true).problem).toMatch(/cannot come from a dimension that moves the pointer/);
    expect(routerSpec({ ...form, click_dim: "click", click_threshold: "2" }, true).problem).toMatch(/Check the click/);
    expect(routerSpec(form, true).spec?.click).toBeUndefined();
  });
  it("labels navigate actions and keeps them out of the selection detail", () => {
    expect(actionLabel({ action: "navigate:next" })).toBe("move next");
    const rules = [
      { output: "left", action: "navigate:previous" as const, threshold: "0.8", hold_ms: "300", refractory_ms: "1000", text: "" },
      { output: "right", action: "primary" as const, threshold: "0.8", hold_ms: "300", refractory_ms: "1000", text: "" },
    ];
    const { spec } = discreteSpec(rules, true);
    expect(spec?.discrete?.map((d) => d.action)).toEqual(["navigate:previous", "primary"]);
  });
});
