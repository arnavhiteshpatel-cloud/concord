// AT-22 (component level): the rendered board adapts to negotiation pushed by
// the runtime and reacts only to runtime events.
import { act, cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { Board } from "./Board";

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

const prov = { kind: "simulated_intent", adapter: "x@1.0.0", synthetic: true, model_id: null, origin: "t", replayed: false };
let seq = 0;
const event = (event_type: string, capability: string, payload: unknown) => ({
  type: "event",
  delivery_seq: seq,
  event: {
    schema_version: "1.0",
    session_id: "ses_abcdef12",
    device_id: "whatever",
    seq: seq++,
    timestamp_ns: seq * 20_000_000,
    device_timestamp_ns: null,
    event_type,
    capability,
    payload,
    quality: { score: 1, flags: [] },
    provenance: prov,
  },
});

afterEach(() => {
  cleanup();
  MockSocket.instances = [];
  seq = 0;
});

describe("<Board />", () => {
  it("switches from pointer mode to scan mode on renegotiation and keeps working", async () => {
    (globalThis as { WebSocket: unknown }).WebSocket = MockSocket;
    render(<Board streamUrl="ws://test/api/v1/stream" />);
    await act(async () => new Promise((r) => setTimeout(r, 5)));
    const ws = MockSocket.instances[0]!;
    expect(JSON.parse(ws.sent[0]!).app.id).toBe("communication-board");

    act(() =>
      ws.push({
        type: "welcome",
        protocol: "brainos.stream/1",
        schema_version: "1.0",
        connection_id: "c",
        negotiation: { device_id: "dev-1", status: "active", granted: ["selection", "pointer_intent"], rejected: [] },
        runtime: null,
      }),
    );
    expect(screen.getByTestId("board-mode").getAttribute("data-mode")).toBe("pointer");
    expect(screen.getByTestId("board-cursor")).toBeTruthy();

    // move up-left into tile 0 and select it
    act(() => {
      for (let i = 0; i < 30; i++) ws.push(event("intent.pointer", "pointer_intent", { vx: -2, vy: -2 }));
      ws.push(event("intent.selection", "selection", { action: "primary", confidence: 0.9 }));
    });
    expect(screen.getByTestId("board-message").textContent).toContain("Yes");

    // device switch: runtime renegotiates without pointer_intent but with text_intent
    act(() =>
      ws.push({
        type: "negotiation",
        negotiation: {
          device_id: "dev-2",
          status: "active",
          granted: ["selection", "text_intent"],
          rejected: [{ capability: "pointer_intent", reason: "unsupported_by_device", required: false }],
        },
      }),
    );
    expect(screen.getByTestId("board-mode").getAttribute("data-mode")).toBe("scan");
    expect(screen.queryByTestId("board-cursor")).toBeNull();
    expect(screen.getByTestId("tile-0").dataset.active).toBe("true");

    act(() => {
      ws.push(event("intent.selection", "selection", { action: "primary", confidence: 0.8 }));
      ws.push(event("intent.text", "text_intent", { text: "!", mode: "character", confidence: 0.8 }));
    });
    expect(screen.getByTestId("board-message").textContent).toContain("Yes Yes!");
  });
});
