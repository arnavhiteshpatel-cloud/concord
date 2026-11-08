// Compatibility view (M5, workstream F): a read-only table of GET /compatibility. Levels come
// from the registry as derived by the backend; the view adds nothing and offers no action
// other than reloading.
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { CompatEntry, CompatibilityResponse, CompatLiveStatus, CompatRegistry } from "../compat";
import { evidenceText, levelText, liveText } from "../compat";
import { apiError, stubFetch } from "../testFetch";
import { CompatibilityView } from "./CompatibilityView";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const LEVELS: CompatRegistry["levels"] = [
  { id: "software_implemented", number: 1, name: "Software-implemented", meaning: "…" },
  { id: "protocol_tested", number: 2, name: "Protocol-tested", meaning: "…" },
  { id: "hardware_verified", number: 3, name: "Hardware-verified", meaning: "…" },
  { id: "human_validated", number: 4, name: "Human-participant validated", meaning: "…" },
];

const entry = (over: Partial<CompatEntry>): CompatEntry => ({
  id: "brainos.lsl",
  display_name: "Lab Streaming Layer",
  kind: "builtin_adapter",
  ecosystem: "lsl",
  protocol: "LSL inlet",
  package: "brainos",
  version: "0.3.0",
  adapter: "brainos.lsl",
  entry_point: null,
  module: "brainos.adapters.lsl",
  in_checkout: true,
  synthetic_only: false,
  modalities_declared: [],
  modality_note: null,
  read_only: { statement: "Receive-only.", verified_by: [] },
  level: "protocol_tested",
  level_number: 2,
  real_data_replay: true,
  level_basis: ["software_implemented (R1): test_lsl.py", "protocol_tested (R2): test_lsl.py"],
  evidence: [
    {
      type: "test",
      path: "backend/tests/test_lsl.py",
      description: "Against genuine liblsl outlets.",
      date: "2026-11-07",
      supports: "protocol_tested",
      counted: true,
      note: null,
      protocol_reference: "Genuine liblsl outlets",
      runs_in_ci: true,
      record: null,
      real_data: false,
      claim: null,
      certify: null,
    },
  ],
  not_tested: ["Third-party LSL producers."],
  limitations: [],
  requires_modules: ["pylsl"],
  ...over,
});

const bci2000 = entry({
  id: "brainos-bci2000",
  display_name: "BCI2000 App Connector",
  kind: "source_plugin",
  ecosystem: "bci2000",
  protocol: "App Connector",
  package: "brainos-bci2000",
  version: "0.1.0",
  adapter: null,
  entry_point: "bci2000",
  module: "brainos_bci2000",
  real_data_replay: false,
  evidence: [
    {
      type: "certify_report",
      path: "docs/compatibility/bci2000-app-connector.certify.json",
      description: "brainos-certify run",
      date: "2026-11-07",
      supports: "software_implemented",
      counted: false,
      note: "Evidence for an earlier revision of this version: plugin source changed after this run (plugin.py)",
      protocol_reference: null,
      runs_in_ci: null,
      record: null,
      real_data: false,
      claim: null,
      certify: null,
    },
    {
      type: "test",
      path: "packages/brainos-bci2000/tests/test_bci_real_bci2000.py",
      description: "Opt-in live test.",
      date: "2026-11-07",
      supports: "protocol_tested",
      counted: true,
      note: "Opt-in test, not run in CI; its execution is recorded in docs/ECOSYSTEMS.md",
      protocol_reference: "Genuine BCI2000 3.6",
      runs_in_ci: false,
      record: "docs/ECOSYSTEMS.md",
      real_data: false,
      claim: null,
      certify: null,
    },
  ],
  not_tested: ["No amplifier."],
});

const t15 = entry({
  id: "brainos.cursorclick.t15",
  display_name: "Cursor + click recordings",
  kind: "offline_dataset",
  in_checkout: false,
  level: null,
  level_number: null,
  real_data_replay: false,
  level_basis: ["not in this checkout"],
  evidence: [],
  not_tested: [],
});

const sim = entry({
  id: "brainos.sim.profile_a",
  display_name: "Simulated Profile A",
  level: "software_implemented",
  level_number: 1,
  real_data_replay: false,
  synthetic_only: true,
});

const registry: CompatRegistry = {
  registry_version: "1.0",
  notice: "Levels are derived from the evidence. No entry has reached hardware_verified (level 3) or human_validated (level 4).",
  brainos_version: "0.3.0",
  levels: LEVELS,
  rules: ["R1 …"],
  sources: { curated: "compat/sources.json", certify_reports: [], validation_levels: "docs/VALIDATION_LEVELS.md" },
  summary: { software_implemented: 1, protocol_tested: 2, hardware_verified: 0, human_validated: 0, no_level: 1 },
  entries: [sim, entry({}), t15, bci2000],
};

const live = (state: CompatLiveStatus["state"], detail: string, version: string | null = null): CompatLiveStatus => ({
  state,
  installed_version: version,
  version_matches: state === "installed" ? true : state === "different_version" ? false : null,
  detail,
});

const response = (over: Partial<CompatibilityResponse> = {}): CompatibilityResponse => ({
  available: true,
  source: "registry.json",
  error: null,
  brainos_version: "0.3.0",
  registry,
  live: {
    "brainos.sim.profile_a": live("installed", "Built into BrainOS 0.3.0", "0.3.0"),
    "brainos.lsl": live("unavailable", "Needs pylsl, which is not installed", "0.3.0"),
    "brainos.cursorclick.t15": live("not_installed", "Not part of this installation"),
    "brainos-bci2000": live(
      "different_version",
      "Evidence for a different version: the evidence is for 0.1.0, 0.2.0 is installed",
      "0.2.0",
    ),
  },
  plugin_discovery: { discovering: false, discovered_at_ns: 1, error: null },
  ...over,
});

describe("CompatibilityView", () => {
  it("renders one row per integration with the derived level, evidence and not-tested notes", async () => {
    stubFetch({ "GET /compatibility": () => response() });
    render(<CompatibilityView />);
    await screen.findByTestId("compat-view");
    expect(screen.getByTestId("compat-notice").textContent).toContain("No entry has reached hardware_verified");
    const headers = screen.getAllByRole("columnheader").map((h) => h.textContent);
    expect(headers).toEqual(["Integration", "Kind", "Level", "Evidence", "Not tested"]);

    const lsl = within(screen.getByTestId("compat-brainos.lsl"));
    expect(screen.getByTestId("compat-level-brainos.lsl").textContent).toBe("Level 2 · Protocol-tested");
    expect(lsl.getByText("Real-data replay (recorded data, not live)")).toBeTruthy();
    expect(lsl.getByText("backend/tests/test_lsl.py")).toBeTruthy();
    expect(lsl.getByText("test · supports Protocol-tested · 2026-11-07")).toBeTruthy();
    expect(lsl.getByText("Third-party LSL producers.")).toBeTruthy();
    expect(lsl.getByText("Built-in adapter")).toBeTruthy();
    expect(screen.getByTestId("compat-live-brainos.lsl").textContent).toBe(
      "This installation: Needs pylsl, which is not installed",
    );

    expect(screen.getByTestId("compat-level-brainos.sim.profile_a").textContent).toBe("Level 1 · Software-implemented");
    expect(within(screen.getByTestId("compat-brainos.sim.profile_a")).getByText("Synthetic data only")).toBeTruthy();

    const t = within(screen.getByTestId("compat-brainos.cursorclick.t15"));
    expect(screen.getByTestId("compat-level-brainos.cursorclick.t15").textContent).toBe("No level: not in this build");
    expect(t.getByText("None in this build")).toBeTruthy();
    expect(t.getByText("Offline dataset")).toBeTruthy();
  });

  it("marks evidence that was not counted and evidence for a different version", async () => {
    stubFetch({ "GET /compatibility": () => response() });
    render(<CompatibilityView />);
    const row = within(await screen.findByTestId("compat-brainos-bci2000"));
    expect(row.getByText(/^Not counted: Evidence for an earlier revision of this version/)).toBeTruthy();
    expect(row.getByText("certification report · 2026-11-07")).toBeTruthy(); // not counted: supports nothing
    expect(row.getByText("test · supports Protocol-tested · not run in CI · 2026-11-07")).toBeTruthy();
    const liveLine = screen.getByTestId("compat-live-brainos-bci2000");
    expect(liveLine.textContent).toBe(
      "This installation: Evidence for a different version: the evidence is for 0.1.0, 0.2.0 is installed",
    );
    expect(liveLine.className).toBe("caution-text");
    // the level is the evidence's; the installed version does not change it
    expect(screen.getByTestId("compat-level-brainos-bci2000").textContent).toBe("Level 2 · Protocol-tested");
  });

  it("offers no control other than Reload, which fetches again", async () => {
    const calls = stubFetch({ "GET /compatibility": () => response() });
    render(<CompatibilityView />);
    const view = await screen.findByTestId("compat-view");
    const buttons = within(view).getAllByRole("button");
    expect(buttons.map((b) => b.textContent)).toEqual(["Reload"]);
    expect(within(view).queryAllByRole("textbox")).toEqual([]);
    fireEvent.click(buttons[0]!);
    await waitFor(() => expect(calls.filter((c) => c.path === "/compatibility")).toHaveLength(2));
    expect(calls.every((c) => c.method === "GET")).toBe(true);
  });

  it("says when the registry is missing, without a table", async () => {
    stubFetch({
      "GET /compatibility": () =>
        response({
          available: false,
          registry: null,
          live: {},
          error: "compatibility registry unavailable (registry.json): [Errno 2] No such file",
        }),
    });
    render(<CompatibilityView />);
    const msg = await screen.findByTestId("compat-unavailable");
    expect(msg.textContent).toContain("compatibility registry unavailable (registry.json)");
    expect(msg.textContent).toContain("make compat");
    expect(screen.queryByRole("table")).toBeNull();
  });

  it("shows a server error", async () => {
    stubFetch({ "GET /compatibility": () => apiError(500, "internal", "boom") });
    render(<CompatibilityView />);
    expect((await screen.findByText(/boom/)).className).toBe("error-text");
  });

  it("renders the committed registry: every entry, no level 3 or 4", async () => {
    const committed = JSON.parse(
      readFileSync(resolve(__dirname, "../../../../compat/registry.json"), "utf8"),
    ) as CompatRegistry;
    stubFetch({ "GET /compatibility": () => response({ registry: committed, live: {} }) });
    render(<CompatibilityView />);
    await screen.findByTestId("compat-view");
    for (const e of committed.entries) {
      const text = screen.getByTestId(`compat-level-${e.id}`).textContent ?? "";
      expect(text).toBe(levelText(e, committed));
      expect(text).not.toMatch(/Hardware-verified|Human-participant validated/);
      expect(screen.getByTestId(`compat-live-${e.id}`).textContent).toBe("This installation: Not reported");
    }
  });
});

describe("compat wording", () => {
  it("names levels as VALIDATION_LEVELS.md does", () => {
    for (const def of LEVELS) {
      const e = entry({ level: def.id, level_number: def.number });
      expect(levelText(e, registry)).toBe(`Level ${def.number} · ${def.name}`);
    }
    expect(levelText(entry({ level: null, level_number: null }), registry)).toBe("No level: no counted evidence");
  });

  it("describes evidence and live status plainly", () => {
    const realData = { ...entry({}).evidence[0]!, real_data: true, supports: "software_implemented" as const };
    expect(evidenceText(realData)).toBe("test · supports Software-implemented · real recorded data · 2026-11-07");
    expect(liveText(undefined)).toBe("Not reported");
    expect(liveText(live("not_checked", "x"))).toBe("Not checked yet: the plugin search has not run");
    expect(liveText(live("not_installed", "x"))).toBe("Not installed here");
    expect(liveText(live("installed", "Installed, version 0.1.0"))).toBe("Installed, version 0.1.0");
  });
});
