// Milestone 5 (D): research session strip (new session, export, end), Safe stop & disconnect,
// Stored data (deletion with confirmation, retention), Support report. Every control must call
// the runtime; these tests check the exact requests.
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { RuntimeSnapshot } from "../../sdk";
import type { RecordingInfo } from "../api";
import { LogContext, type LogWriter } from "../context";
import type { ResearchSession, SafeStopReport, SessionLogEntry } from "../researchApi";
import { safeStopText } from "../researchApi";
import { stubFetch } from "../testFetch";
import { SessionBar, entryText, somethingRunning } from "./SessionBar";
import { StoredData, dataDirPrivacy, retentionText } from "./StoredData";
import { SupportReport } from "./SupportReport";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const session: ResearchSession = {
  id: "20261107-101500-ab12",
  name: "pilot 1",
  operator: "A. Researcher",
  notes: "first try",
  created_at_ns: 1_762_510_500_000_000_000,
  closed_at_ns: null,
  status: "active",
  end_reason: null,
  concord_version: "0.3.0",
  recordings: ["cal-1"],
  models: ["m-1"],
  log_entries: 3,
};
const recording: RecordingInfo = {
  name: "cal-1",
  device_id: "lsl:x",
  device_name: "x",
  synthetic: true,
  created_at_ns: 1,
  size_bytes: 2048,
  events: null,
  active: false,
  complete: false,
  recovery: { status: "incomplete", reason: "Concord stopped", valid_events: 120, discarded_bytes: 17 },
};
const streaming = { state: "streaming", device: { device_id: "sim-a" }, recording: "r", session_id: "s" } as unknown as RuntimeSnapshot;
const stopReport: SafeStopReport = {
  at_ns: 1,
  reason: "safe stop by operator",
  state: "idle",
  ok: true,
  steps: [
    { step: "command_output", done: true, detail: "command output turned off", error: null, ms: 0.1 },
    { step: "recording", done: true, detail: "recording r closed", error: null, ms: 1 },
    { step: "decoding", done: false, detail: "decoding was not running", error: null, ms: 0 },
    { step: "source", done: true, detail: "source disconnected", error: null, ms: 3 },
  ],
};
const storage = {
  data_dir: "/data",
  usage: {
    recordings: { count: 1, bytes: 2048 },
    models: { count: 1, bytes: 100 },
    sessions: { count: 1, bytes: 10 },
    exports: { count: 0, bytes: 0 },
  },
  retention: { recordings_days: 30, sessions_days: null, exports_days: null, models_days: null },
  last_retention: null,
  recovered_recordings: ["cal-1"],
  interrupted_sessions: [],
};

function withLog(ui: React.ReactElement): { entries: string[] } {
  const entries: string[] = [];
  const writer: LogWriter = (_tone, text) => entries.push(text);
  render(<LogContext.Provider value={writer}>{ui}</LogContext.Provider>);
  return { entries };
}

describe("research session strip", () => {
  it("New session sends name, operator and notes; the strip then shows the session", async () => {
    let active: ResearchSession | null = null;
    const calls = stubFetch({
      "GET /sessions": () => ({ active, sessions: active ? [active] : [] }),
      "POST /sessions": (body) => {
        active = { ...session, ...(body as object) };
        return active;
      },
      "GET /storage": () => storage,
    });
    const { entries } = withLog(
      <SessionBar runtime={null} pipelineRunning={false} controlOn={false} recordings={[]} onChanged={() => {}} />,
    );
    await screen.findByTestId("no-session");
    // nothing is running: the safe stop is offered but disabled
    expect((screen.getByTestId("safe-stop") as HTMLButtonElement).disabled).toBe(true);
    await waitFor(() => expect(entries.some((e) => e.includes("Recording cal-1 was interrupted"))).toBe(true));
    fireEvent.click(screen.getByTestId("new-session"));
    const sheet = within(screen.getByTestId("new-session-sheet"));
    expect((sheet.getByTestId("session-create") as HTMLButtonElement).disabled).toBe(true); // a name is required
    fireEvent.change(sheet.getByTestId("session-name-input"), { target: { value: "pilot 1" } });
    fireEvent.change(sheet.getByTestId("session-operator-input"), { target: { value: "A. Researcher" } });
    fireEvent.change(sheet.getByTestId("session-notes-input"), { target: { value: "first try" } });
    fireEvent.click(sheet.getByTestId("session-create"));
    await waitFor(() => expect(calls.some((c) => c.method === "POST" && c.path === "/sessions")).toBe(true));
    expect(calls.find((c) => c.method === "POST" && c.path === "/sessions")!.body).toEqual({
      name: "pilot 1",
      operator: "A. Researcher",
      notes: "first try",
    });
    await waitFor(() => expect(screen.getByTestId("session-name").textContent).toBe("pilot 1"));
    expect(screen.getByTestId("session-summary").textContent).toContain("1 recording");
    expect(entries).toContain("Research session started: pilot 1");
  });

  it("Safe stop & disconnect calls the runtime and logs what it stopped", async () => {
    const calls = stubFetch({
      "GET /sessions": () => ({ active: null, sessions: [] }),
      "GET /storage": () => ({ ...storage, recovered_recordings: [] }),
      "POST /safe-stop": () => stopReport,
    });
    const changed = vi.fn();
    const { entries } = withLog(
      <SessionBar runtime={streaming} pipelineRunning={false} controlOn={true} recordings={[]} onChanged={changed} />,
    );
    const btn = screen.getByTestId("safe-stop") as HTMLButtonElement;
    expect(btn.disabled).toBe(false);
    fireEvent.click(btn);
    await waitFor(() => expect(calls.some((c) => c.method === "POST" && c.path === "/safe-stop")).toBe(true));
    await waitFor(() => expect(entries).toContain("Safe stop: stopped command output, recording, source"));
    expect(changed).toHaveBeenCalled();
  });

  it("exports with the chosen options, links the bundle, and ends the session after confirmation", async () => {
    const exportInfo = {
      session_id: session.id,
      file: `concord-session-${session.id}-20261107-103000.zip`,
      size_bytes: 4096,
      sha256: "a".repeat(64),
      created_at_ns: 2,
      files: 12,
      included_recordings: ["cal-1"],
      omitted_recordings: [],
      missing_recordings: [],
      models: ["m-1"],
      missing_models: [],
      options: { include_recordings: true, include_personal: false },
    };
    let active: ResearchSession | null = session;
    const log: SessionLogEntry[] = [
      { at_ns: 1, kind: "session_created" },
      { at_ns: 2, kind: "operator_action", action: "pipeline_start", status: 200 },
      { at_ns: 3, kind: "calibration", model_id: "m-1", status: 200 },
    ];
    const calls = stubFetch({
      "GET /sessions": () => ({ active, sessions: [session] }),
      "GET /storage": () => ({ ...storage, recovered_recordings: [] }),
      [`GET /sessions/${session.id}`]: () => ({ session, log, log_total: 3, exports: [] }),
      [`POST /sessions/${session.id}/export`]: () => exportInfo,
      [`POST /sessions/${session.id}/close`]: () => {
        active = null;
        return { session: { ...session, status: "closed" }, safe_stop: stopReport };
      },
    });
    const { entries } = withLog(
      <SessionBar runtime={null} pipelineRunning={false} controlOn={false} recordings={[recording]} onChanged={() => {}} />,
    );
    fireEvent.click(await screen.findByTestId("session-details"));
    const sheet = within(screen.getByTestId("session-sheet"));
    expect(sheet.getByTestId("session-recordings").textContent).toBe("cal-1 (2.0 KB, incomplete)");
    await waitFor(() => expect(sheet.getByTestId("session-entries").textContent).toContain("Decoder calibrated: m-1"));
    fireEvent.click(sheet.getByTestId("export-recordings"));
    fireEvent.click(sheet.getByTestId("export-create"));
    await waitFor(() => expect(sheet.getByTestId("export-result")).toBeTruthy());
    expect(calls.find((c) => c.path === `/sessions/${session.id}/export`)!.body).toEqual({
      include_recordings: true,
      include_personal: false,
    });
    const link = sheet.getByTestId("export-download") as HTMLAnchorElement;
    expect(link.getAttribute("href")).toBe(`/api/v1/sessions/${session.id}/exports/${exportInfo.file}`);
    expect(entries).toContain(`Session exported: ${exportInfo.file}`);
    // End session: asks first, then closes with a safe stop
    fireEvent.click(sheet.getByTestId("session-end"));
    expect(calls.some((c) => c.path.endsWith("/close"))).toBe(false);
    fireEvent.click(sheet.getByTestId("session-end-confirm"));
    await waitFor(() => expect(calls.some((c) => c.path === `/sessions/${session.id}/close`)).toBe(true));
    expect(calls.find((c) => c.path.endsWith("/close"))!.body).toEqual({ safe_stop: true });
    await waitFor(() => expect(entries).toContain("Research session ended: pilot 1"));
    await waitFor(() => expect(screen.queryByTestId("session-sheet")).toBeNull());
  });
});

describe("stored data", () => {
  it("deletes only after a second, explicit confirmation and shows incomplete recordings", async () => {
    let recordings: RecordingInfo[] = [recording];
    const calls = stubFetch({
      "GET /storage": () => storage,
      "GET /recordings": () => recordings,
      "GET /models": () => [{ summary: { model_id: "m-1", dims: ["vx"], created_at: "2026-11-07" }, compatible: null, errors: [], warnings: [] }],
      "GET /sessions": () => ({ active: null, sessions: [{ ...session, status: "closed" }] }),
      "DELETE /recordings/cal-1": () => {
        recordings = [];
        return { deleted: "cal-1", bytes: 2048, also_deleted: [] };
      },
      [`DELETE /sessions/${session.id}`]: () => ({ deleted: session.id, bytes: 10, also_deleted: ["cal-1"] }),
    });
    const changed = vi.fn();
    const { entries } = withLog(<StoredData onChanged={changed} />);
    await screen.findByTestId("stored-recordings");
    expect(screen.getByTestId("incomplete-cal-1").textContent).toContain("incomplete (120 events kept)");
    expect(screen.getByTestId("retention-policy").textContent).toContain("recordings 30 days");
    expect(screen.getByTestId("model-trust").textContent).toContain("trust");
    fireEvent.click(screen.getByTestId("delete-recording-cal-1"));
    expect(calls.some((c) => c.method === "DELETE")).toBe(false); // first click only asks
    expect(screen.getByTestId("delete-recording-cal-1-ask").textContent).toContain("Delete cal-1 permanently?");
    fireEvent.click(screen.getByTestId("delete-recording-cal-1-confirm"));
    await waitFor(() => expect(calls.some((c) => c.method === "DELETE" && c.path === "/recordings/cal-1")).toBe(true));
    await waitFor(() => expect(entries).toContain("Deleted recording cal-1 (2.0 KB)"));
    expect(changed).toHaveBeenCalled();
    // a session with its recordings
    fireEvent.click(screen.getByTestId(`delete-session-recordings-${session.id}`));
    fireEvent.click(screen.getByTestId(`delete-session-${session.id}`));
    fireEvent.click(screen.getByTestId(`delete-session-${session.id}-confirm`));
    await waitFor(() => expect(entries).toContain("Deleted session pilot 1 and 1 recording(s) (10 B)"));
  });

  it("sends the confirmation the server requires", async () => {
    const urls: string[] = [];
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        urls.push(`${init?.method ?? "GET"} ${String(input)}`);
        return new Response(JSON.stringify({ deleted: "x", bytes: 1, also_deleted: [] }), { status: 200 });
      }),
    );
    const { researchApi } = await import("../researchApi");
    await researchApi.deleteRecording("rec a");
    await researchApi.deleteModel("m-1");
    await researchApi.deleteSession(session.id, true);
    expect(urls).toEqual([
      "DELETE /api/v1/recordings/rec%20a?confirm=rec%20a",
      "DELETE /api/v1/models/m-1?confirm=m-1",
      `DELETE /api/v1/sessions/${session.id}?confirm=${session.id}&delete_recordings=true`,
    ]);
  });
});

describe("support report", () => {
  it("creates the report on the server and offers it for download", async () => {
    const calls = stubFetch({
      "GET /system/doctor": () => ({
        format: "concord.support-report/1",
        generated_at: "now",
        summary: { ok: 10, info: 2, warn: 1, fail: 0 },
        checks: [{ id: "disk", title: "Disk space", status: "warn", detail: "1.2 GiB free", hint: "free space" }],
        excluded: ["neural data of any kind"],
      }),
    });
    vi.stubGlobal("URL", Object.assign(URL, { createObjectURL: () => "blob:report", revokeObjectURL: () => {} }));
    withLog(<SupportReport />);
    fireEvent.click(screen.getByTestId("support-create"));
    await screen.findByTestId("support-result");
    expect(calls.some((c) => c.path === "/system/doctor")).toBe(true);
    expect(screen.getByTestId("support-summary").textContent).toBe("0 failed · 1 warnings · 10 ok");
    expect(screen.getByText(/1.2 GiB free/)).toBeTruthy();
    expect((screen.getByTestId("support-json") as HTMLAnchorElement).getAttribute("href")).toBe("blob:report");
    expect((screen.getByTestId("support-md") as HTMLAnchorElement).getAttribute("href")).toBe("/api/v1/system/doctor?format=markdown");
    expect(screen.getByText("neural data of any kind")).toBeTruthy();
  });
});

describe("wording", () => {
  it("formats safe stops, session log entries, retention and running state", () => {
    expect(safeStopText(stopReport)).toBe("Safe stop: stopped command output, recording, source");
    expect(safeStopText({ ...stopReport, steps: stopReport.steps.map((s) => ({ ...s, done: false })) })).toBe(
      "Safe stop: nothing was running",
    );
    expect(entryText({ at_ns: 1, kind: "operator_action", action: "pipeline_start", status: 409 })).toBe(
      "pipeline start (refused 409)",
    );
    expect(entryText({ at_ns: 1, kind: "device_status", device_id: "sim-a", state: "streaming" })).toBe("Source sim-a: streaming");
    expect(entryText({ at_ns: 1, kind: "recording_started", recording: "r1" })).toBe("Recording started: r1");
    expect(retentionText({ recordings_days: null })).toContain("No retention policy");
    // Windows has no 0700 folders: privacy there depends on the folder being in the profile
    expect(dataDirPrivacy("/home/ana/.local/share/concord/data")).toBe("only your user can read it");
    expect(dataDirPrivacy("C:\\Users\\Ana\\AppData\\Local\\Concord\\data")).toContain("cannot open it");
    expect(dataDirPrivacy("D:\\lab\\concord")).toContain("may be able to read it");
    expect(somethingRunning(null, false, false)).toBe(false);
    expect(somethingRunning(null, true, false)).toBe(true);
  });
});
