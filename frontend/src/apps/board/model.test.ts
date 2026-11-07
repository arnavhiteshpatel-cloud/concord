// AT-22: board model — pointer integration, hit-testing, selection, scan, text, negotiation.
import { describe, expect, it } from "vitest";
import type { NegotiationResult } from "../../sdk";
import { COLS, TILES, applyTile, boardReducer, initialBoard, modeFor, tileAt, type BoardState } from "./model";

const neg = (granted: NegotiationResult["granted"], status: NegotiationResult["status"] = "active"): NegotiationResult => ({
  device_id: "any",
  status,
  granted,
  rejected: [],
});

const withMode = (granted: NegotiationResult["granted"]): BoardState =>
  boardReducer(initialBoard(), { type: "negotiation", negotiation: neg(granted) });

describe("mode negotiation", () => {
  it("chooses pointer mode when pointer_intent is granted", () => {
    expect(modeFor(neg(["selection", "pointer_intent"]))).toBe("pointer");
  });
  it("falls back to scan mode with selection only", () => {
    expect(modeFor(neg(["selection", "text_intent"]))).toBe("scan");
  });
  it("is inactive when suspended or without a device", () => {
    expect(modeFor(neg([], "suspended"))).toBe("inactive");
    expect(modeFor(neg([], "no_device"))).toBe("inactive");
  });
  it("switches mode on renegotiation without losing the message", () => {
    let s = withMode(["selection"]);
    s = boardReducer(s, { type: "select" }); // scan index 0 -> "Yes"
    expect(s.message).toBe("Yes");
    s = boardReducer(s, { type: "negotiation", negotiation: neg(["selection", "pointer_intent"]) });
    expect(s.mode).toBe("pointer");
    expect(s.message).toBe("Yes");
  });
});

describe("pointer mode", () => {
  it("integrates velocity over event timestamps and hit-tests tiles", () => {
    let s = withMode(["selection", "pointer_intent"]);
    expect(s.cursor).toEqual({ x: 0.5, y: 0.5 });
    const t0 = 1_000_000_000;
    s = boardReducer(s, { type: "pointer", vx: 1, vy: 0, timestampNs: t0 }); // first: dt = 20 ms
    expect(s.cursor.x).toBeCloseTo(0.52);
    for (let i = 1; i <= 10; i++) s = boardReducer(s, { type: "pointer", vx: 1, vy: 0, timestampNs: t0 + i * 20e6 });
    expect(s.cursor.x).toBeCloseTo(0.72);
    expect(s.hover).toBe(tileAt(0.72, 0.5));
  });
  it("clamps dt after gaps and clamps cursor to the workspace", () => {
    let s = withMode(["selection", "pointer_intent"]);
    s = boardReducer(s, { type: "pointer", vx: 0, vy: 0, timestampNs: 0 });
    s = boardReducer(s, { type: "pointer", vx: 10, vy: -10, timestampNs: 5e9 }); // 5 s gap -> dt 0.1
    expect(s.cursor).toEqual({ x: 1, y: 0 });
  });
  it("selects the hovered tile", () => {
    let s = withMode(["selection", "pointer_intent"]);
    // move to top-left tile ("Yes")
    for (let i = 0; i < 40; i++) s = boardReducer(s, { type: "pointer", vx: -2, vy: -2, timestampNs: i * 20e6 });
    expect(s.hover).toBe(0);
    s = boardReducer(s, { type: "select" });
    expect(s.message).toBe("Yes");
    expect(s.lastSelected?.index).toBe(0);
  });
  it("ignores pointer events in scan mode", () => {
    const s = withMode(["selection"]);
    expect(boardReducer(s, { type: "pointer", vx: 1, vy: 1, timestampNs: 1 })).toBe(s);
  });
});

describe("scan mode", () => {
  it("advances the highlight and selects the highlighted tile", () => {
    let s = withMode(["selection"]);
    s = boardReducer(s, { type: "scanTick" });
    s = boardReducer(s, { type: "scanTick" });
    expect(s.scanIndex).toBe(2);
    s = boardReducer(s, { type: "select" });
    expect(s.message).toBe(TILES[2]!.label);
  });
  it("wraps around", () => {
    let s = withMode(["selection"]);
    for (let i = 0; i < TILES.length; i++) s = boardReducer(s, { type: "scanTick" });
    expect(s.scanIndex).toBe(0);
  });
});

describe("text intent", () => {
  it("appends text only when text_intent is granted", () => {
    const without = boardReducer(withMode(["selection"]), { type: "text", text: "h", mode: "character" });
    expect(without.message).toBe("");
    let s = withMode(["selection", "text_intent"]);
    s = boardReducer(s, { type: "text", text: "h", mode: "character" });
    s = boardReducer(s, { type: "text", text: "i", mode: "character" });
    expect(s.message).toBe("hi");
    s = boardReducer(s, { type: "text", text: "there", mode: "word" });
    expect(s.message).toBe("hi there");
  });
});

describe("tiles", () => {
  it("hit-tests a 4x3 grid over the unit square", () => {
    expect(COLS).toBe(4);
    expect(tileAt(0, 0)).toBe(0);
    expect(tileAt(0.99, 0)).toBe(3);
    expect(tileAt(0, 0.99)).toBe(8);
    expect(tileAt(1, 1)).toBe(11);
  });
  it("applies phrase, space, delete, clear", () => {
    const phrase = TILES.find((t) => t.label === "Water")!;
    expect(applyTile("", phrase)).toBe("Water");
    expect(applyTile("Hello", phrase)).toBe("Hello Water");
    expect(applyTile("Hi ", phrase)).toBe("Hi Water");
    expect(applyTile("ab", { label: "Delete", kind: "delete" })).toBe("a");
    expect(applyTile("ab", { label: "Space", kind: "space" })).toBe("ab ");
    expect(applyTile("ab", { label: "Clear", kind: "clear" })).toBe("");
  });
  it("counts speak requests", () => {
    let s = withMode(["selection"]);
    for (let i = 0; i < 11; i++) s = boardReducer(s, { type: "scanTick" });
    s = boardReducer(s, { type: "select" });
    expect(TILES[11]!.kind).toBe("speak");
    expect(s.speakRequests).toBe(1);
  });
  it("does nothing on select when inactive", () => {
    const s = initialBoard();
    expect(boardReducer(s, { type: "select" })).toBe(s);
  });
});
