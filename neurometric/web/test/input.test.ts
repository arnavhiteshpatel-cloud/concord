// Unit tests of the input adapter layer: recorder (seq, monotonic clamp, merge order, text
// privacy, validation), checkStream parity with Python semantics, scanning state machine, dwell,
// gamepad response curve, simulated stream and replay.
import { describe, expect, it, vi } from "vitest";
import { EventRecorder, TextNotAllowedError, type Clock } from "../src/input/recorder";
import { checkStream, compareEvents, mergeStreams, validateEvent, type InputEvent } from "../src/input/types";
import { Scanner, DEFAULT_SWITCH, recordScanAction, type ScanAction, type ScanTarget } from "../src/input/switch";
import { DwellSelector } from "../src/input/dwell";
import { axisToSpeed, DEFAULT_GAMEPAD } from "../src/input/gamepad";
import { SimulatedPointerStream, replayEvents } from "../src/input/simulated";

function fakeClock(): Clock & { set(t: number): void } {
  let t = 0;
  return { origin: 0, now: () => t, fromTimeStamp: (ts) => ts, set: (v) => (t = v) } as Clock & { set(t: number): void };
}

describe("EventRecorder", () => {
  it("numbers events per stream, clamps per-stream time to be monotonic and records the clamp", () => {
    const rec = new EventRecorder({ clock: fakeClock() });
    const a = rec.stream("in:a", "mouse");
    const b = rec.stream("in:b", "pen");
    a.emit({ kind: "pointer_move", x: 1, y: 1 }, { t: 10 });
    b.emit({ kind: "pointer_move", x: 2, y: 2 }, { t: 5 });
    const late = a.emit({ kind: "pointer_move", x: 3, y: 3 }, { t: 8 })!;
    expect(late.t_ms).toBe(10);
    expect(late.meta?.t_clamped_ms).toBe(2);
    expect(late.seq).toBe(1);
    const m = rec.merged();
    expect(m.map((e) => [e.stream_id, e.seq])).toEqual([["in:b", 0], ["in:a", 0], ["in:a", 1]]);
    expect(checkStream(m)).toMatchObject({ non_monotonic: 0, duplicate_seq: 0, seq_gaps: 0 });
  });
  it("orders simultaneous events by stream id so selections precede task markers", () => {
    const rec = new EventRecorder({ clock: fakeClock() });
    const task = rec.stream("task", "other");
    const ptr = rec.stream("in:pointer:mouse", "mouse");
    task.emit({ kind: "marker", meta: { marker: "trial_end" } }, { t: 100 });
    ptr.emit({ kind: "click", x: 1, y: 2 }, { t: 100 });
    expect(rec.merged().map((e) => e.kind)).toEqual(["click", "marker"]);
  });
  it("refuses text content outside copy typing", () => {
    const rec = new EventRecorder({ clock: fakeClock() });
    const s = rec.stream("in:text", "keyboard");
    expect(() => s.emit({ kind: "text_input", text: "a" })).toThrow(TextNotAllowedError);
    expect(() => s.emit({ kind: "key", key: "q" })).toThrow(TextNotAllowedError);
    expect(s.emit({ kind: "key", key: "Enter" })?.key).toBe("Enter");
    const rec2 = new EventRecorder({ clock: fakeClock(), allowText: true });
    expect(rec2.stream("in:text", "keyboard").emit({ kind: "text_input", text: "a" })?.text).toBe("a");
  });
  it("validates like Python validate_event", () => {
    const rec = new EventRecorder({ clock: fakeClock() });
    const s = rec.stream("ctl", "other");
    expect(() => s.emit({ kind: "assist", meta: { assist_type: "magic" } })).toThrow();
    expect(() => s.emit({ kind: "pointer_move" })).toThrow();
    expect(() => s.emit({ kind: "switch" })).toThrow();
    expect(() => s.emit({ kind: "select", confidence: 0.5 })).toThrow(/confidence_source/);
    expect(s.emit({ kind: "select", confidence: 0.5, meta: { confidence_source: "device" } })?.confidence).toBe(0.5);
    expect(s.emit({ kind: "assist", meta: { assist_type: "calibration" } })?.kind).toBe("assist");
    const ok: InputEvent = { t_ms: 0, kind: "scroll", session_id: "s", stream_id: "x", modality: "mouse", seq: 0, synthetic: false, schema_version: "1.0", dy: 3 };
    expect(() => validateEvent(ok)).not.toThrow();
  });
  it("serialises like InputEvent.to_dict (no null / empty fields)", () => {
    const rec = new EventRecorder({ clock: fakeClock(), sessionId: "sess_x" });
    const e = rec.stream("in:k", "keyboard").emit({ kind: "key", key: "Tab" }, { t: 3 })!;
    expect(Object.keys(e).sort()).toEqual(["key", "kind", "modality", "schema_version", "seq", "session_id", "stream_id", "synthetic", "t_ms"]);
  });
});

describe("checkStream / mergeStreams (same semantics as Python)", () => {
  const ev = (s: string, seq: number, t: number): InputEvent => ({ t_ms: t, kind: "pointer_move", session_id: "s", stream_id: s, modality: "mouse", seq, synthetic: false, schema_version: "1.0", x: 0, y: 0 });
  it("counts non-monotonic, duplicate and gaps", () => {
    const r = checkStream([ev("a", 0, 1), ev("a", 1, 0.5), ev("a", 1, 2), ev("a", 4, 3), ev("b", 0, 0)]);
    expect(r).toEqual({ n: 5, non_monotonic: 1, duplicate_seq: 1, seq_gaps: 1, gap_events: 2, streams: ["a", "b"] });
  });
  it("merges stably by (t, stream, seq)", () => {
    const m = mergeStreams([ev("b", 0, 1), ev("b", 1, 1)], [ev("a", 0, 1), ev("a", 1, 0)]);
    expect(m.map((e) => `${e.stream_id}${e.seq}`)).toEqual(["a1", "a0", "b0", "b1"]);
    expect(compareEvents(m[0], m[1])).toBeLessThan(0);
  });
});

function targets(n: number, rows = 1): ScanTarget[] {
  const hits: string[] = [];
  const ts = Array.from({ length: n }, (_, i) => ({ id: `t${i}`, row: Math.floor(i / Math.ceil(n / rows)), role: "task" as const, activate: () => hits.push(`t${i}`) }));
  (ts as unknown as { hits: string[] }).hits = hits;
  return ts;
}

describe("Scanner", () => {
  it("single-switch auto-scan: press starts, timer advances, press selects, restart from first", () => {
    vi.useFakeTimers();
    const ts = targets(4);
    const hl: string[] = [];
    const acts: ScanAction[] = [];
    const sc = new Scanner({ ...DEFAULT_SWITCH, rateMs: 100 }, () => ts, (t) => hl.push(t.map((x) => x.id).join()), (a) => acts.push(a), () => 0);
    sc.press(0);
    expect(hl.at(-1)).toBe("t0");
    vi.advanceTimersByTime(250);
    expect(hl.at(-1)).toBe("t2");
    sc.press(0);
    expect((ts as unknown as { hits: string[] }).hits).toEqual(["t2"]);
    expect(hl.at(-1)).toBe("t0");
    expect(acts.map((a) => a.type)).toEqual(["start", "select"]);
    sc.dispose();
    vi.useRealTimers();
  });
  it("stops after maxCycles without a choice, next press restarts", () => {
    vi.useFakeTimers();
    const ts = targets(3);
    const acts: ScanAction[] = [];
    const sc = new Scanner({ ...DEFAULT_SWITCH, rateMs: 10, maxCycles: 2 }, () => ts, () => {}, (a) => acts.push(a), () => 0);
    sc.press(0);
    vi.advanceTimersByTime(200);
    expect(sc.running).toBe(false);
    expect(acts.at(-1)?.type).toBe("stopped");
    sc.press(0);
    expect(sc.running).toBe(true);
    sc.dispose();
    vi.useRealTimers();
  });
  it("two-switch step scan: switch 1 steps, switch 2 selects", () => {
    const ts = targets(5);
    const sc = new Scanner({ ...DEFAULT_SWITCH, switches: 2, mode: "step" }, () => ts, () => {}, () => {}, () => 0);
    sc.press(0); // start at t0
    sc.press(0);
    sc.press(0);
    sc.press(1);
    expect((ts as unknown as { hits: string[] }).hits).toEqual(["t2"]);
    sc.press(1); // restart from first
    expect((ts as unknown as { hits: string[] }).hits).toEqual(["t2", "t0"]);
  });
  it("row-column scanning picks a row then an item", () => {
    const ts = targets(6, 2); // rows 0: t0-t2, 1: t3-t5
    const levels: string[] = [];
    const sc = new Scanner({ ...DEFAULT_SWITCH, switches: 2, mode: "step", rowColumn: true }, () => ts, (t, l) => levels.push(`${l}:${t.map((x) => x.id).join("")}`), () => {}, () => 0);
    sc.press(0); // start: row 0
    sc.press(0); // row 1
    sc.press(1); // enter row 1 -> t3
    sc.press(0); // t4
    sc.press(1); // select t4
    expect((ts as unknown as { hits: string[] }).hits).toEqual(["t4"]);
    expect(levels.slice(0, 4)).toEqual(["row:t0t1t2", "row:t3t4t5", "item:t3", "item:t4"]);
  });
  it("records only the selecting press as a switch (selection) event", () => {
    const rec = new EventRecorder({ clock: fakeClock() });
    const s = rec.stream("in:switch", "switch");
    const target: ScanTarget = { id: "7", x: 10, y: 20, role: "task", activate: () => {} };
    recordScanAction(s, DEFAULT_SWITCH, { type: "step", t: 1, switchIndex: 0 });
    recordScanAction(s, DEFAULT_SWITCH, { type: "select", t: 2, switchIndex: 0, target });
    recordScanAction(s, DEFAULT_SWITCH, { type: "select", t: 3, switchIndex: 0, target: { ...target, role: "control" } });
    expect(rec.merged().map((e) => e.kind)).toEqual(["key", "switch", "key"]);
    expect(rec.merged()[1]).toMatchObject({ switch_id: "switch1", x: 10, y: 20 });
  });
});

describe("DwellSelector", () => {
  const items = [{ id: "a", x: 0, y: 0 }, { id: "b", x: 100, y: 0 }];
  const hitTest = (x: number) => items.find((i) => Math.abs(i.x - x) <= 20) ?? null;
  it("fires once at entry + threshold, resets on leaving, refires only after re-entry", () => {
    const sel: [string, number][] = [];
    const d = new DwellSelector({ thresholdMs: 500, hitTest: (x) => hitTest(x), onSelect: (h, t) => sel.push([h.id, t]) });
    d.update(0, 0, 0);
    d.tick(300);
    d.update(100, 0, 350); // left a before threshold: reset
    expect(d.resets).toBe(1);
    d.tick(900);
    d.tick(2000);
    expect(sel).toEqual([["b", 850]]);
    d.update(50, 0, 2100); // empty space
    d.update(100, 0, 2200);
    d.tick(2700);
    expect(sel).toEqual([["b", 850], ["b", 2700]]);
  });
});

describe("Gamepad response curve", () => {
  it("dead zone, sign and full deflection", () => {
    expect(axisToSpeed(0.1, DEFAULT_GAMEPAD)).toBe(0);
    expect(axisToSpeed(1, DEFAULT_GAMEPAD)).toBe(DEFAULT_GAMEPAD.maxSpeed);
    expect(axisToSpeed(-1, DEFAULT_GAMEPAD)).toBe(-DEFAULT_GAMEPAD.maxSpeed);
    expect(axisToSpeed(0.575, DEFAULT_GAMEPAD)).toBeCloseTo(DEFAULT_GAMEPAD.maxSpeed * 0.25, 6);
  });
});

describe("Simulated stream and replay", () => {
  it("pumps a 1000 Hz synthetic stream deterministically", () => {
    const rec = new EventRecorder({ clock: fakeClock() });
    const s = new SimulatedPointerStream(rec, "line", (t) => ({ x: t / 10, y: 1 }), 1000, 0);
    expect(s.pumpTo(999)).toBe(1000);
    const ev = rec.merged();
    expect(ev[0]).toMatchObject({ modality: "simulated", synthetic: true, stream_id: "in:sim:line" });
    expect(checkStream(ev)).toMatchObject({ non_monotonic: 0, seq_gaps: 0 });
  });
  it("replays a log with modality replay, preserving relative timing", async () => {
    const src = new EventRecorder({ clock: fakeClock() });
    const p = src.stream("in:pointer:mouse", "eye_gaze");
    p.emit({ kind: "pointer_move", x: 1, y: 1 }, { t: 100 });
    p.emit({ kind: "dwell_select", x: 1, y: 1 }, { t: 900 });
    const rec = new EventRecorder({ clock: fakeClock() });
    await replayEvents(rec, src.merged(), { speed: Infinity, t0: 10 });
    const out = rec.merged();
    expect(out.map((e) => [e.t_ms, e.modality, e.stream_id, e.meta?.original_modality])).toEqual([
      [10, "replay", "in:replay:pointer:mouse", "eye_gaze"],
      [810, "replay", "in:replay:pointer:mouse", "eye_gaze"],
    ]);
  });
});
