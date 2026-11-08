// Board v2 (component level, AT-22): the rendered board adapts to negotiation, acts only on
// commands the SDK guard passes (control.state active), stops at once on control.state
// inactive, labels input provenance and computer speech, and exposes a read-only snapshot.
import { act, cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { Board } from "./Board";
import { DEMONSTRATION_LABEL } from "./provenance";

class MockSocket {
  static instances: MockSocket[] = [];
  sent: string[] = [];
  onopen: (() => void) | null = null;
  onmessage: ((m: { data: string }) => void) | null = null;
  onclose: (() => void) | null = null;
  constructor(public url: string) {
    MockSocket.instances.push(this);
    setTimeout(() => this.onopen?.(), 0);
  }
  send(s: string) {
    this.sent.push(s);
  }
  close() {}
  push(msg: unknown) {
    this.onmessage?.({ data: JSON.stringify(msg) });
  }
}

type Prov = { kind: string; adapter: string; synthetic: boolean; model_id: string | null; origin: string; replayed: boolean; model_origin?: string | null };
const SIM: Prov = { kind: "simulated_intent", adapter: "x.sim@1.0.0", synthetic: true, model_id: null, origin: "t", replayed: false };
const DECODED: Prov = { kind: "decoded_intent", adapter: "concord.pipeline@0.4.0", synthetic: false, model_id: "m1", origin: "t", replayed: false };
const HISTORICAL: Prov = { ...DECODED, adapter: "x.cursorclick@0.1.0", model_id: "t15-original", model_origin: "historical", replayed: true };
const RUNTIME: Prov = { kind: "runtime", adapter: "concord.runtime@0.1.0", synthetic: false, model_id: null, origin: "runtime", replayed: false };

let seq = 0;
let deviceMs = 10_000;
const event = (event_type: string, capability: string, payload: unknown, provenance: Prov = SIM) => {
  deviceMs += 20;
  return {
    type: "event",
    delivery_seq: seq,
    event: {
      schema_version: "1.4",
      session_id: "ses_abcdef12",
      device_id: "whatever",
      seq: seq++,
      timestamp_ns: Date.now() * 1e6, // fresh: the guard drops stale commands
      device_timestamp_ns: event_type === "control.state" ? null : deviceMs * 1e6,
      event_type,
      capability,
      payload,
      quality: { score: 1, flags: [] },
      provenance,
    },
  };
};
const control = (active: boolean, capabilities: string[], reason: string) =>
  event("control.state", "control_status", { active, capabilities, reason }, RUNTIME);
const runtime = { state: "streaming", device: null, session_id: "ses_abcdef12", state_since_ns: 0, last_error: null, recording: null, apps: [] };
const welcome = (granted: string[]) => ({
  type: "welcome",
  protocol: "concord.stream/1",
  schema_version: "1.4",
  connection_id: "c",
  negotiation: { device_id: "dev-1", status: "active", granted, rejected: [] },
  runtime,
});

async function mount(url = "ws://test/api/v1/stream", search = "") {
  (globalThis as { WebSocket: unknown }).WebSocket = MockSocket;
  render(<Board streamUrl={url} search={search} />);
  await act(async () => new Promise((r) => setTimeout(r, 5)));
  return MockSocket.instances.at(-1)!;
}

const text = (id: string) => screen.getByTestId(id).textContent ?? "";

beforeEach(() => {
  window.localStorage.clear();
});
afterEach(() => {
  cleanup();
  MockSocket.instances = [];
  seq = 0;
  vi.unstubAllGlobals();
});

describe("<Board /> v2", () => {
  it("asks for no required capability and adapts: pointer+click, then scanning with text", async () => {
    const ws = await mount();
    const hello = JSON.parse(ws.sent[0]!);
    expect(hello.app.id).toBe("communication-board");
    expect(hello.capabilities.required).toEqual([]);
    expect(hello.capabilities.optional).toEqual(["pointer_intent", "selection", "navigation", "text_intent", "control_status"]);
    expect(text("board-mode")).toBe("Waiting");

    act(() => ws.push(welcome(["pointer_intent", "selection", "control_status"])));
    expect(text("board-mode")).toBe("Pointer and click");
    // granted, but the runtime has not said command delivery is active: nothing acts
    expect(screen.getByTestId("board-control").dataset.active).toBe("false");
    act(() => {
      for (let i = 0; i < 30; i++) ws.push(event("intent.pointer", "pointer_intent", { vx: -2, vy: -2 }));
    });
    expect(screen.getByTestId("board-cursor").style.left).toBe("50%");

    act(() => ws.push(control(true, ["pointer_intent", "selection"], "command input active")));
    expect(screen.getByTestId("board-control").dataset.active).toBe("true");
    act(() => {
      for (let i = 0; i < 30; i++) ws.push(event("intent.pointer", "pointer_intent", { vx: -2, vy: -2 }));
      ws.push(event("intent.selection", "selection", { action: "primary", confidence: 0.9 }));
    });
    expect(screen.getByTestId("tile-0").dataset.active).toBe("true");
    expect(text("board-message")).toBe("Yes");
    expect(text("board-input")).toContain("Input: simulated input");

    // renegotiation: no pointer, but selection + text -> scanning
    act(() =>
      ws.push({
        type: "negotiation",
        negotiation: { device_id: "dev-2", status: "active", granted: ["selection", "text_intent", "control_status"], rejected: [] },
      }),
    );
    act(() => ws.push(control(true, ["selection", "text_intent"], "command input active")));
    expect(text("board-mode")).toBe("Scanning");
    expect(screen.queryByTestId("board-cursor")).toBeNull();
    deviceMs += 400; // past the board's click/switch debounce
    act(() => {
      ws.push(event("intent.selection", "selection", { action: "primary", confidence: 0.8 }));
      ws.push(event("intent.text", "text_intent", { text: "!", mode: "character", confidence: 0.8 }));
    });
    expect(text("board-message")).toBe("Yes Yes!");
  });

  it("stops at once on control.state inactive: cursor frozen, reason shown, nothing selected", async () => {
    const ws = await mount();
    act(() => {
      ws.push(welcome(["pointer_intent", "selection", "control_status"]));
      ws.push(control(true, ["pointer_intent", "selection"], "decoded command output active"));
      for (let i = 0; i < 5; i++) ws.push(event("intent.pointer", "pointer_intent", { vx: 1, vy: 0 }, DECODED));
    });
    const left = screen.getByTestId("board-cursor").style.left;
    act(() => ws.push(control(false, [], "command output stopped: stopped by operator")));
    expect(text("board-control")).toContain("Paused — command output stopped: stopped by operator");
    expect(screen.getByTestId("board-cursor").className).toContain("cursor-frozen");
    act(() => {
      for (let i = 0; i < 10; i++) ws.push(event("intent.pointer", "pointer_intent", { vx: 1, vy: 0 }, DECODED));
      ws.push(event("intent.selection", "selection", { action: "primary", confidence: 0.9 }, DECODED));
    });
    expect(screen.getByTestId("board-cursor").style.left).toBe(left);
    expect(text("board-message")).toBe("Message appears here…");
    expect(window.__concordBoard?.counters.selections).toBe(0);
  });

  it("labels decoded and historical input; replayed text is a demonstration, not the participant's message", async () => {
    const ws = await mount();
    act(() => {
      ws.push(welcome(["pointer_intent", "selection", "control_status"]));
      ws.push(control(true, ["pointer_intent", "selection"], "on"));
      ws.push(event("intent.pointer", "pointer_intent", { vx: 0, vy: 0 }, DECODED));
    });
    expect(text("board-input")).toBe("Input: decoded by m1 (Concord)");
    act(() => {
      ws.push(event("intent.pointer", "pointer_intent", { vx: 0, vy: 0 }, HISTORICAL));
      ws.push(event("intent.selection", "selection", { action: "primary", confidence: 0.9 }, HISTORICAL));
    });
    expect(text("board-input")).toBe("Input: historical decoder replay (original research system) · recorded data replay");
    expect(text("board-text-label")).toBe(DEMONSTRATION_LABEL);
    const snap = window.__concordBoard!;
    expect(snap.textLabel).toBe(DEMONSTRATION_LABEL);
    expect(snap.selections[0]).toMatchObject({ tile: 10, via: "click", page: "phrases" }); // centre of 4 x 4
    expect(snap.selections[0]!.event!.input.modelOrigin).toBe("historical");
  });

  it("speaks with computer speech (labelled, not neural speech decoding) and records history", async () => {
    const speak = vi.fn();
    vi.stubGlobal("speechSynthesis", { speak, cancel: vi.fn() });
    vi.stubGlobal(
      "SpeechSynthesisUtterance",
      class {
        rate = 1;
        constructor(public text: string) {}
      },
    );
    const ws = await mount("ws://test/api/v1/stream", "?method=direct");
    act(() => {
      ws.push(welcome(["selection", "control_status"]));
      ws.push(control(true, ["selection"], "on"));
    });
    expect(text("board-mode")).toBe("Direct selection");
    const speakTile = screen.getAllByRole("gridcell").find((c) => c.textContent?.startsWith("Speak"))!;
    expect(speakTile.textContent).toContain("computer speech (not neural speech decoding)");
    const speakIndex = Number(speakTile.dataset.testid!.replace("tile-", ""));
    act(() => {
      ws.push(event("intent.selection", "selection", { action: "activate", confidence: 0.9 })); // "Yes"
    });
    // move the highlight to Speak with "select" (one per board debounce window)
    for (let i = 0; i < speakIndex; i++) {
      deviceMs += 400;
      act(() => ws.push(event("intent.selection", "selection", { action: "primary", confidence: 0.9 })));
    }
    deviceMs += 400;
    act(() => ws.push(event("intent.selection", "selection", { action: "activate", confidence: 0.9 })));
    expect(speak).toHaveBeenCalledTimes(1);
    expect((speak.mock.calls[0]![0] as { text: string }).text).toBe("Yes");
    expect(screen.getByTestId("history-1").textContent).toContain("Yes");
    expect(screen.getByTestId("history-1").textContent).toContain("simulated input — no participant");
  });

  it("exposes a read-only snapshot: a fresh copy on every read, never a control path", async () => {
    const ws = await mount("ws://test/api/v1/stream", "?layout=grid&n=14");
    act(() => {
      ws.push(welcome(["pointer_intent", "selection", "control_status"]));
      ws.push(control(true, ["pointer_intent", "selection"], "on"));
    });
    const a = window.__concordBoard!;
    expect(a.version).toBe(1);
    expect(a.layout).toMatchObject({ kind: "grid", page: "grid", cols: 14, rows: 14 });
    expect(a.layout.tiles).toHaveLength(196);
    expect(a.cursor).toEqual({ x: 0.5, y: 0.5 });
    expect(a.highlighted).toBe(7 * 14 + 7);
    a.cursor.x = 0;
    a.text = "injected";
    const b = window.__concordBoard!;
    expect(b.cursor.x).toBe(0.5);
    expect(b.text).toBe("");
    expect(screen.getByTestId("board-grid").dataset.cols).toBe("14");
  });
});
