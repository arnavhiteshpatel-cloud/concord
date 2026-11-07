// Communication board v2 — pure model: every input method, safe stop, text composition,
// provenance labels, device-clock integration and the task-grid geometry.
import { describe, expect, it } from "vitest";
import type { Capability, NegotiationResult } from "../../sdk";
import { availableMethods, chooseMethod } from "./methods";
import {
  MAX_DT_S,
  boardReducer,
  buildPage,
  deleteWord,
  dwellProgress,
  focusTile,
  initialBoard,
  pageDims,
  tileAt,
  type BoardAction,
  type BoardState,
} from "./model";
import { DEMONSTRATION_LABEL, SIMULATION_LABEL, compositionLabel, inputLabel, type EventRef, type InputTag } from "./provenance";
import { DEFAULT_SETTINGS, normalizeSettings, settingsFromQuery, type BoardSettings } from "./settings";
import { CORE_WORDS, PHRASES, parseWordList, predictions } from "./vocabulary";

const SIM: InputTag = { kind: "simulated_intent", modelId: null, modelOrigin: null, replayed: false, synthetic: true, adapter: "brainos.sim@0.1.0" };
const BRAINOS: InputTag = { kind: "decoded_intent", modelId: "m1", modelOrigin: null, replayed: false, synthetic: false, adapter: "brainos.pipeline@0.4.0" };
const HISTORICAL: InputTag = { kind: "decoded_intent", modelId: "t15-orig", modelOrigin: "historical", replayed: true, synthetic: false, adapter: "brainos.cursorclick@0.1.0" };
const EXTERNAL: InputTag = { kind: "decoded_intent", modelId: "bci2000", modelOrigin: "external", replayed: false, synthetic: false, adapter: "brainos.bci2000@0.1.0" };

let seq = 0;
/** an event reference; `t` in ms on the device clock (null = no device timestamp) */
function ref(t: number | null, input: InputTag = SIM, wallMs = 1000): EventRef {
  seq += 1;
  return {
    seq,
    sessionId: "ses_aaaaaaaa",
    timestampNs: wallMs * 1e6,
    deviceTimestampNs: t === null ? null : Math.round(t * 1e6),
    eventType: "intent.pointer",
    input,
  };
}

const neg = (granted: Capability[], status: NegotiationResult["status"] = "active"): NegotiationResult => ({ device_id: "any", status, granted, rejected: [] });

/** A board with `granted` negotiated and usable (as the guard would report), and settings. */
function board(granted: Capability[], settings: Partial<BoardSettings> = {}, usable: Capability[] = granted): BoardState {
  let s = initialBoard({ ...DEFAULT_SETTINGS, ...settings });
  s = boardReducer(s, { type: "negotiation", negotiation: neg(granted) });
  return boardReducer(s, { type: "usable", caps: usable, reason: null });
}

const run = (s: BoardState, ...actions: BoardAction[]) => actions.reduce(boardReducer, s);
const select = (action: "primary" | "activate" | "cancel", t: number, input: InputTag = SIM, nowMs = t): BoardAction => ({ type: "select", action, ref: ref(t, input), nowMs });
const pointer = (vx: number, vy: number, t: number | null, input: InputTag = SIM, wallMs = 1000): BoardAction => ({ type: "pointer", vx, vy, ref: ref(t, input, wallMs), nowMs: 0 });
const tick = (nowMs: number): BoardAction => ({ type: "tick", nowMs });
const nav = (direction: "up" | "down" | "left" | "right" | "next" | "previous", t = 0): BoardAction => ({ type: "navigate", direction, ref: ref(t), nowMs: t });

/** move the cursor to the centre of tile `index` of the current page: home to (0,0), then go there */
function moveTo(s: BoardState, index: number, t0: number): [BoardState, number] {
  const [cols, rows] = pageDims(s);
  const x = ((index % cols) + 0.5) / cols;
  const y = (Math.floor(index / cols) + 0.5) / rows;
  let t = t0;
  let st = run(s, pointer(0, 0, t)); // sets the clock
  for (let i = 0; i < 30; i++) st = run(st, pointer(-2, -2, (t += 20)));
  for (let i = 0; i < 25; i++) st = run(st, pointer(x / 0.5, y / 0.5, (t += 20)));
  return [st, t];
}

describe("input methods: availability and automatic choice", () => {
  it("offers each method only when the negotiated capabilities support it", () => {
    expect(availableMethods(["pointer_intent", "selection"])).toEqual(["cursor_click", "cursor_dwell", "direct", "scan"]);
    expect(availableMethods(["pointer_intent"])).toEqual(["cursor_dwell"]);
    expect(availableMethods(["navigation"])).toEqual(["navigate"]);
    expect(availableMethods(["selection", "text_intent"])).toEqual(["direct", "scan"]);
    expect(availableMethods(["text_intent", "control_status"])).toEqual([]);
  });
  it("chooses automatically, honours an available override, ignores an unavailable one", () => {
    expect(chooseMethod("auto", ["pointer_intent", "selection"], false)).toBe("cursor_click");
    expect(chooseMethod("auto", ["pointer_intent"], false)).toBe("cursor_dwell");
    expect(chooseMethod("auto", ["navigation", "selection"], false)).toBe("navigate");
    expect(chooseMethod("auto", ["selection"], false)).toBe("scan");
    expect(chooseMethod("auto", ["selection"], true)).toBe("direct"); // the source sent activate/cancel
    expect(chooseMethod("cursor_dwell", ["pointer_intent", "selection"], false)).toBe("cursor_dwell");
    expect(chooseMethod("cursor_click", ["selection"], false)).toBe("scan");
    expect(chooseMethod("auto", [], false)).toBeNull();
  });
  it("is waiting (no method) when suspended, without a device, or with nothing usable", () => {
    expect(board([]).method).toBeNull();
    const s = boardReducer(initialBoard(), { type: "negotiation", negotiation: neg([], "no_device") });
    expect(s.method).toBeNull();
    const notYet = board(["pointer_intent", "selection"], {}, []);
    expect(notYet.method).toBe("cursor_click");
    expect(notYet.active).toBe(false);
  });
});

describe("cursor + click", () => {
  it("integrates velocity on the device clock and the click selects the tile under the cursor", () => {
    let s = board(["pointer_intent", "selection"]);
    expect(s.method).toBe("cursor_click");
    expect(s.cursor).toEqual({ x: 0.5, y: 0.5 });
    s = run(s, pointer(1, 0, 1000)); // the first event only sets the clock
    expect(s.cursor.x).toBe(0.5);
    for (let i = 1; i <= 10; i++) s = run(s, pointer(1, 0, 1000 + i * 20));
    expect(s.cursor.x).toBeCloseTo(0.7);
    const [moved, t] = moveTo(s, 2, 2000);
    expect(moved.hover).toBe(2);
    expect(buildPage(moved).tiles[2]!.label).toBe("Hello");
    s = run(moved, select("primary", t + 100));
    expect(s.message).toBe("Hello");
    expect(s.selections.at(-1)).toMatchObject({ n: 1, page: "phrases", tile: 2, label: "Hello", via: "click" });
    expect(s.selections.at(-1)!.cursor).toEqual(moved.cursor);
  });
  it("reproduces the same trajectory at any replay speed (device timestamps, not arrival)", () => {
    const path = (wallStep: number) => {
      let s = board(["pointer_intent", "selection"]);
      for (let i = 0; i < 40; i++) s = run(s, pointer(0.8, -0.3, 5000 + i * 10, SIM, 1000 + i * wallStep));
      return s.cursor;
    };
    expect(path(10)).toEqual(path(10 / 8)); // 1x vs 8x
    expect(path(10).x).toBeCloseTo(0.5 + 0.8 * 0.39);
  });
  it("falls back to the runtime clock without device timestamps and clamps dt and the workspace", () => {
    let s = board(["pointer_intent", "selection"]);
    s = run(s, pointer(0, 0, null, SIM, 1000), pointer(10, -10, null, SIM, 6000)); // 5 s gap -> dt 0.1
    expect(MAX_DT_S).toBe(0.1);
    expect(s.cursor).toEqual({ x: 1, y: 0 });
  });
  it("debounces clicks on the event clock: one click selects once, at any replay speed", () => {
    let [s, t] = moveTo(board(["pointer_intent", "selection"], { clickRefractoryMs: 300 }), 0, 0);
    s = run(s, select("primary", t + 10), select("primary", t + 20), select("primary", t + 250));
    expect(s.message).toBe("Yes");
    expect(s.counters.debounced).toBe(2);
    s = run(s, select("primary", t + 400));
    expect(s.message).toBe("Yes Yes");
  });
  it("ignores pointer and clicks while not usable (guard says so)", () => {
    const s = board(["pointer_intent", "selection"], {}, ["selection"]);
    expect(s.active).toBe(false);
    const after = run(s, pointer(1, 1, 0), pointer(1, 1, 20), select("primary", 40));
    expect(after.cursor).toEqual({ x: 0.5, y: 0.5 });
    expect(after.message).toBe("");
    expect(after.counters.ignoredInactive).toBe(3);
  });
});

describe("cursor + dwell (a board interaction, never a neural click)", () => {
  it("selects after resting for the dwell time and cancels when the cursor leaves", () => {
    let [s, t] = moveTo(board(["pointer_intent"], { dwellMs: 800 }), 5, 0);
    expect(s.method).toBe("cursor_dwell");
    s = run(s, tick(10_000)); // starts the dwell on tile 5
    expect(dwellProgress(s, 10_400)).toBeCloseTo(0.5);
    s = run(s, tick(10_500));
    expect(s.message).toBe("");
    // leave for tile 6 before the dwell completes: the dwell restarts there
    for (let i = 0; i < 8; i++) s = run(s, pointer(1, 0, (t += 20))); // +0.16: into tile 6
    expect(s.hover).toBe(6);
    s = run(s, tick(10_700), tick(11_000));
    expect(s.message).toBe(""); // 300 ms on tile 6, 0 more on tile 5
    s = run(s, tick(11_500));
    expect(s.message).toBe(PHRASES[6]);
    expect(s.selections.at(-1)).toMatchObject({ via: "dwell", tile: 6 });
    // staying does not select again; leaving and coming back does
    s = run(s, tick(13_000));
    expect(s.selectionCount).toBe(1);
  });
  it("ignores clicks: dwell needs no selection capability", () => {
    const s = board(["pointer_intent", "selection"], { method: "cursor_dwell" });
    expect(run(s, select("primary", 0)).message).toBe("");
  });
});

describe("scanning (binary switch)", () => {
  it("linear: the highlight advances each interval and the switch selects it", () => {
    let s = board(["selection"], { scanIntervalMs: 1000 });
    expect(s.method).toBe("scan");
    s = run(s, tick(0), tick(999));
    expect(s.highlight).toBe(0);
    s = run(s, tick(1000), tick(2000));
    expect(s.highlight).toBe(2);
    s = run(s, select("primary", 2100));
    expect(s.message).toBe("Hello");
    expect(s.highlight).toBe(0); // scanning restarts from the first tile
  });
  it("row then column: first press picks the row, second the tile; cancel returns to rows", () => {
    let s = board(["selection"], { scanIntervalMs: 500, scanPattern: "row_column" });
    s = run(s, tick(0), tick(500)); // row 1
    expect(s.highlight).toBe(4);
    s = run(s, select("primary", 600));
    expect(s.scan.stage).toBe("cell");
    s = run(s, tick(1100), tick(1600)); // tiles 5, 6
    expect(s.highlight).toBe(6);
    s = run(s, select("primary", 1700));
    expect(s.message).toBe("Water");
    // cancel in the cell stage goes back to row scanning (nothing chosen)
    s = run(s, tick(2200), select("primary", 2300), select("cancel", 2700));
    expect(s.scan.stage).toBe("row");
    expect(s.message).toBe("Water");
  });
});

describe("directional navigation", () => {
  it("moves the highlight in the grid and selection chooses it", () => {
    let s = board(["navigation", "selection"]);
    expect(s.method).toBe("navigate");
    s = run(s, nav("right"), nav("right"), nav("down"), nav("left"), nav("up"), nav("up"));
    expect(s.highlight).toBe(1); // (0,1)
    s = run(s, nav("previous"), nav("previous"));
    expect(s.highlight).toBe(15); // wraps linearly
    s = run(s, nav("next"), nav("down"));
    expect(s.highlight).toBe(4);
    s = run(s, select("activate", 100));
    expect(s.message).toBe("Please");
    expect(s.selections.at(-1)!.via).toBe("navigate");
  });
  it("without selection, resting on the highlighted tile chooses it (dwell selection)", () => {
    let s = board(["navigation"], { dwellMs: 1000 });
    s = run(s, nav("next"), tick(0), tick(999));
    expect(s.message).toBe("");
    s = run(s, nav("next"), tick(1000), tick(1500)); // moved: the dwell restarts
    expect(s.message).toBe("");
    s = run(s, tick(2001));
    expect(s.message).toBe("Hello");
  });
});

describe("direct selection (several discrete actions)", () => {
  it("select moves, activate chooses, cancel undoes; an activate switches 'auto' from scanning", () => {
    let s = board(["selection"]);
    expect(s.method).toBe("scan");
    s = run(s, select("activate", 0)); // chooses the highlighted tile and reveals direct selection
    expect(s.method).toBe("direct");
    expect(s.message).toBe("Yes");
    s = run(s, select("primary", 1000), select("primary", 2000), select("activate", 3000));
    expect(s.message).toBe("Yes Hello");
    s = run(s, select("cancel", 4000));
    expect(s.message).toBe("Yes");
  });
});

describe("text composition", () => {
  it("phrases, letters with word prediction, space, delete, undo, clear and history", () => {
    let s = board(["navigation", "selection"]);
    const choose = (label: string, t: number) => {
      const i = buildPage(s).tiles.findIndex((x) => x.label === label);
      expect(i, label).toBeGreaterThanOrEqual(0);
      s = { ...s, highlight: i };
      s = run(s, select("primary", t));
    };
    choose("Thank you", 0);
    choose("Letters", 1000);
    expect(s.page).toBe("letters");
    choose("W", 2000);
    choose("A", 3000);
    expect(s.message).toBe("Thank youwa"); // capital only at the start of a sentence
    expect(predictions("Thank youwa")).toEqual([]);
    choose("Delete", 4000);
    choose("Delete", 5000);
    choose("Space", 6000);
    choose("W", 7000);
    choose("A", 8000);
    expect(s.message).toBe("Thank you wa");
    const pred = buildPage(s).tiles.slice(0, 3).map((t) => t.label);
    expect(pred).toContain("water");
    choose("water", 9000);
    expect(s.message).toBe("Thank you water ");
    choose("Undo", 10_000);
    expect(s.message).toBe("Thank you wa");
    choose("Phrases", 11_000);
    choose("Delete word", 12_000);
    expect(s.message).toBe("Thank you");
    choose("Save", 13_000); // speech unavailable here: the tile says Save and records history
    expect(s.history).toHaveLength(1);
    expect(s.history[0]).toMatchObject({ n: 1, text: "Thank you", input: "simulated input", label: SIMULATION_LABEL });
    expect(s.speech).toBeNull();
    choose("Clear", 14_000);
    expect(s.message).toBe("");
    choose("Undo", 15_000);
    expect(s.message).toBe("Thank you");
    expect(deleteWord("a b  ")).toBe("a");
  });
  it("Speak requests computer speech only when it is available and enabled", () => {
    let s = boardReducer(board(["navigation", "selection"]), { type: "speechAvailable", available: true });
    const speakIdx = buildPage(s).tiles.findIndex((t) => t.kind === "speak");
    expect(buildPage(s).tiles[speakIdx]!.label).toBe("Speak");
    s = run({ ...s, highlight: 0 }, select("primary", 0));
    s = run({ ...s, highlight: speakIdx }, select("primary", 1000));
    expect(s.speech).toEqual({ n: 1, text: "Yes" });
    const off = boardReducer(s, { type: "settings", settings: { ...s.settings, speech: false } });
    expect(buildPage(off).tiles[speakIdx]!.label).toBe("Save");
  });
  it("appends text intents only while text_intent is usable", () => {
    let s = board(["selection"], {}, ["selection"]);
    s = run(s, { type: "text", text: "hi", mode: "word", ref: ref(0), nowMs: 0 });
    expect(s.message).toBe("");
    s = board(["selection", "text_intent"]);
    s = run(s, { type: "text", text: "h", mode: "character", ref: ref(0), nowMs: 0 }, { type: "text", text: "there", mode: "word", ref: ref(1), nowMs: 1 });
    expect(s.message).toBe("h there");
  });
});

describe("safe stop", () => {
  it("losing usable input freezes the cursor and cancels dwell, confirmation and row selection", () => {
    // dwell in progress
    let [s, t] = moveTo(board(["pointer_intent"], { dwellMs: 800 }), 0, 0);
    s = run(s, tick(0), tick(700));
    s = boardReducer(s, { type: "usable", caps: [], reason: "command output stopped: stopped by operator" });
    expect(s.active).toBe(false);
    expect(s.stopReason).toBe("command output stopped: stopped by operator");
    expect(s.dwell.sinceMs).toBeNull();
    s = run(s, tick(5000), pointer(1, 1, (t += 20)));
    expect(s.message).toBe(""); // the dwell never completes
    expect(s.cursor.x).toBeCloseTo(0.125); // frozen on tile 0
    expect(s.cursor.y).toBeCloseTo(0.125);
    // back on: the dwell starts from zero and the first pointer event only sets the clock
    s = boardReducer(s, { type: "usable", caps: ["pointer_intent"], reason: null });
    s = run(s, tick(6000), tick(6500));
    expect(s.message).toBe("");
    expect(s.lastPointer).toBeNull();

    // a pending confirmation
    let [c, t2] = moveTo(board(["pointer_intent", "selection"], { confirm: "repeat" }), 1, 0);
    c = run(c, select("primary", t2 + 10));
    expect(c.pending).toMatchObject({ tile: 1 });
    expect(c.message).toBe("");
    c = boardReducer(c, { type: "usable", caps: ["pointer_intent"], reason: "authorization revoked" });
    expect(c.pending).toBeNull();
    c = boardReducer(c, { type: "usable", caps: ["pointer_intent", "selection"], reason: null });
    c = run(c, select("primary", t2 + 500));
    expect(c.message).toBe(""); // a fresh first selection, not a confirmation
    c = run(c, select("primary", t2 + 1000));
    expect(c.message).toBe("No");

    // a row picked in row/column scanning
    let r = board(["selection"], { scanPattern: "row_column" });
    r = run(r, select("primary", 0));
    expect(r.scan.stage).toBe("cell");
    r = boardReducer(r, { type: "usable", caps: [], reason: "source paused" });
    expect(r.scan.stage).toBe("row");
    expect(run(r, tick(10_000), tick(20_000)).highlight).toBe(r.highlight); // no scanning while stopped
  });
});

describe("provenance and the scientific limitation", () => {
  it("labels where input comes from", () => {
    expect(inputLabel(SIM)).toBe("simulated input");
    expect(inputLabel(BRAINOS)).toBe("decoded by m1 (BrainOS)");
    expect(inputLabel({ ...BRAINOS, modelOrigin: "brainos", adapter: "x@1.0.0" })).toBe("decoded by m1 (BrainOS)");
    expect(inputLabel(HISTORICAL)).toBe("historical decoder replay (original research system)");
    expect(inputLabel(EXTERNAL)).toBe("decoded by bci2000 (external decoder)");
  });
  it("text composed from replayed recordings is never the participant's message", () => {
    expect(compositionLabel([HISTORICAL])).toBe(DEMONSTRATION_LABEL);
    expect(compositionLabel([{ ...BRAINOS, replayed: true }])).toBe(DEMONSTRATION_LABEL);
    expect(compositionLabel([BRAINOS, SIM])).toBeNull();
    expect(compositionLabel([SIM])).toBe(SIMULATION_LABEL);
    expect(DEMONSTRATION_LABEL).toBe("demonstration — not the participant's message");
    let [s, t] = moveTo(board(["pointer_intent", "selection"]), 3, 0);
    s = run(s, select("primary", t + 50, HISTORICAL));
    expect(s.message).toBe("Thank you");
    expect(compositionLabel(s.sources)).toBe(DEMONSTRATION_LABEL);
    expect(s.selections.at(-1)!.event!.input.modelOrigin).toBe("historical");
  });
});

describe("task grid (evaluation layout)", () => {
  it("N x N tiles over the unit square; a click lands on the tile containing the cursor", () => {
    let s = board(["pointer_intent", "selection"], { layout: "grid", gridN: 14 });
    const p = buildPage(s);
    expect([p.kind, p.cols, p.rows, p.tiles.length]).toEqual(["grid", 14, 14, 196]);
    expect(p.tiles.map((t) => t.label)).toEqual(CORE_WORDS.slice(0, 196));
    expect(tileAt(0.5, 0.5, 14, 14)).toBe(7 * 14 + 7);
    expect(tileAt(0.07, 0.07, 14, 14)).toBe(0); // 1/14 = 0.0714…
    expect(tileAt(0.0715, 0.0715, 14, 14)).toBe(1 + 14);
    s = run(s, pointer(0, 0, 0));
    for (let i = 1; i <= 10; i++) s = run(s, pointer(-0.3, 0.2, i * 10)); // 100 ms
    expect(s.cursor.x).toBeCloseTo(0.47);
    expect(s.cursor.y).toBeCloseTo(0.52);
    expect(focusTile(s)).toBe(Math.floor(0.52 * 14) * 14 + Math.floor(0.47 * 14));
    s = run(s, select("primary", 200));
    expect(s.selections.at(-1)).toMatchObject({ page: "grid", tile: 7 * 14 + 6, label: CORE_WORDS[7 * 14 + 6] });
    const custom = boardReducer(s, { type: "words", words: ["alpha", "beta"] });
    expect(buildPage(custom).tiles.slice(0, 3).map((t) => t.label)).toEqual(["alpha", "beta", ""]);
  });
});

describe("settings", () => {
  it("parses URL parameters, validates and clamps them", () => {
    const s = normalizeSettings(settingsFromQuery("?layout=grid&n=99&dwell_ms=50&method=cursor_click&words=/w.txt&speech=0&confirm=bogus"));
    expect(s).toMatchObject({ layout: "grid", gridN: 20, dwellMs: 300, method: "cursor_click", wordsUrl: "/w.txt", speech: false, confirm: "none" });
    expect(normalizeSettings({ textScale: "abc", tileSize: "large" })).toMatchObject({ textScale: 1, tileSize: "large" });
    expect(buildPage({ ...initialBoard({ ...DEFAULT_SETTINGS, tileSize: "large" }) }).tiles).toHaveLength(9);
    expect(buildPage({ ...initialBoard({ ...DEFAULT_SETTINGS, tileSize: "small" }) }).tiles).toHaveLength(25);
  });
  it("reads word lists: one per line, comments and blanks ignored", () => {
    expect(parseWordList("# header\nyes\n\n no \nthank you # polite\n")).toEqual(["yes", "no", "thank you"]);
    expect(CORE_WORDS.length).toBeGreaterThanOrEqual(196);
    expect(new Set(CORE_WORDS).size).toBe(CORE_WORDS.length);
  });
});
