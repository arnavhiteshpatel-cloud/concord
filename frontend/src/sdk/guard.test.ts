// CommandGuard (TS SDK): authorization state, immediate stops, stale/late drops, dead-man.
import { describe, expect, it, vi } from "vitest";
import { BrainOSStream } from "./client";
import { CommandGuard, attachGuard } from "./guard";
import type { Capability, EnvelopeOf, EventEnvelope, NegotiationResult, RuntimeSnapshot } from "./types";

class Clock {
  wall = 1_700_000_000_000;
  mono = 5_000;
  advance(ms: number) {
    this.wall += ms;
    this.mono += ms;
  }
}

const neg = (granted: Capability[], rejected: [Capability, NegotiationResult["rejected"][number]["reason"], boolean][] = []): NegotiationResult => ({
  device_id: "d",
  status: rejected.some((r) => r[2]) ? "suspended" : "active",
  granted,
  rejected: rejected.map(([capability, reason, required]) => ({ capability, reason, required })),
});

const runtime = (state: RuntimeSnapshot["state"] = "streaming", session_id: string | null = "ses_aaaaaaaa") => ({ state, session_id });

function cmd(clock: Clock, type: "intent.pointer" | "intent.selection" = "intent.pointer", ageMs = 0, payload?: object): EventEnvelope {
  const base = {
    schema_version: "1.3",
    session_id: "ses_aaaaaaaa",
    device_id: "d",
    seq: 1,
    timestamp_ns: (clock.wall - ageMs) * 1e6,
    device_timestamp_ns: null,
    quality: { score: 1, flags: [] },
    provenance: { kind: "decoded_intent" as const, adapter: "brainos.pipeline@0.4.0", synthetic: true, model_id: "m1", origin: "o", replayed: false },
  };
  return type === "intent.pointer"
    ? { ...base, event_type: "intent.pointer", capability: "pointer_intent", payload: { vx: 0.5, vy: 0.1, ...payload } }
    : { ...base, event_type: "intent.selection", capability: "selection", payload: { action: "primary", confidence: 0.9 } };
}

function guard(clock: Clock, stops: string[], opts: ConstructorParameters<typeof CommandGuard>[0] = {}) {
  const g = new CommandGuard({ onStop: (r) => stops.push(r), wallMs: () => clock.wall, monoMs: () => clock.mono, ...opts });
  g.onRuntime(runtime());
  return g;
}

describe("CommandGuard", () => {
  it("waits for authorization, accepts once granted, stops at once on revocation", () => {
    const clock = new Clock();
    const stops: string[] = [];
    const g = guard(clock, stops);
    g.onNegotiation(neg([], [["selection", "not_authorized", true]]));
    expect(g.waitingForAuthorization).toEqual(["selection"]);
    expect(g.accept(cmd(clock, "intent.selection"))).toBe(false);
    g.onNegotiation(neg(["selection"]));
    expect(g.isActive("selection")).toBe(true);
    expect(g.accept(cmd(clock, "intent.selection"))).toBe(true);
    g.onNegotiation(neg([], [["selection", "not_authorized", true]]));
    expect(stops).toEqual(["authorization revoked"]);
    expect(g.accept(cmd(clock, "intent.selection"))).toBe(false);
    expect(g.stats.droppedInactive).toBe(2);
  });

  it.each([
    ["command output stopped", (g: CommandGuard) => g.onNegotiation(neg([], [["pointer_intent", "unsupported_by_device", true]]))],
    ["source disconnected", (g: CommandGuard) => g.onNegotiation({ device_id: null, status: "no_device", granted: [], rejected: [] })],
    ["source paused", (g: CommandGuard) => g.onRuntime(runtime("paused"))],
    ["connection lost", (g: CommandGuard) => g.onConnection("reconnecting")],
    ["stream closed", (g: CommandGuard) => g.onConnection("closed")],
  ])("stops immediately: %s", (reason, fn) => {
    const clock = new Clock();
    const stops: string[] = [];
    const g = guard(clock, stops);
    g.onNegotiation(neg(["pointer_intent"]));
    expect(g.accept(cmd(clock))).toBe(true);
    expect(g.velocity).toEqual([0.5, 0.1]);
    fn(g);
    expect(stops).toEqual([reason]);
    expect(g.velocity).toEqual([0, 0]);
  });

  it("drops stale commands (wall clock) and late ones (relative delivery delay)", () => {
    const clock = new Clock();
    const g = guard(clock, [], { maxAgeMs: 300 });
    g.onNegotiation(neg(["pointer_intent"]));
    expect(g.accept(cmd(clock, "intent.pointer", 20))).toBe(true);
    expect(g.accept(cmd(clock, "intent.pointer", 301))).toBe(false);
    expect(g.stats.droppedStale).toBe(1);
    const g2 = guard(clock, [], { maxAgeMs: 300, compareWallClock: false });
    g2.onNegotiation(neg(["pointer_intent"]));
    expect(g2.accept(cmd(clock, "intent.pointer", 5000))).toBe(true); // skewed clocks
    clock.advance(100);
    expect(g2.accept(cmd(clock, "intent.pointer", 5400))).toBe(false); // held up 400 ms
    expect(g2.stats.droppedLate).toBe(1);
  });

  it("dead-man: zero velocity after deadmanMs without a pointer command, once per idle period", () => {
    const clock = new Clock();
    const onDeadman = vi.fn();
    const stops: string[] = [];
    const g = guard(clock, stops, { deadmanMs: 200, onDeadman });
    g.onNegotiation(neg(["pointer_intent"]));
    g.accept(cmd(clock, "intent.pointer", 0, { vx: 1, vy: -1 }));
    clock.advance(150);
    expect(g.tick()).toBe(false);
    expect(g.velocity).toEqual([1, -1]);
    clock.advance(60);
    expect(g.tick()).toBe(true);
    expect(g.velocity).toEqual([0, 0]);
    clock.advance(500);
    expect(g.tick()).toBe(false);
    expect(onDeadman).toHaveBeenCalledTimes(1);
    expect(stops).toEqual([]); // not a stop: commands may resume
  });

  it("rejects a bad configuration", () => {
    expect(() => new CommandGuard({ maxAgeMs: 0 })).toThrow(/positive/);
  });
});

describe("attachGuard", () => {
  it("passes only fresh, usable commands and detaches cleanly", () => {
    const stream = new BrainOSStream({ app: { id: "a", name: "A" }, required: ["selection"], webSocket: () => ({}) as WebSocket });
    const stops: string[] = [];
    const g = new CommandGuard({ onStop: (r) => stops.push(r) });
    const got: EventEnvelope[] = [];
    const detach = attachGuard(stream, g, (e) => got.push(e));
    const rt = { state: "streaming", device: null, session_id: "ses_aaaaaaaa", state_since_ns: 0, last_error: null, recording: null, apps: [] };
    stream.handle(JSON.stringify({ type: "welcome", protocol: "brainos.stream/1", schema_version: "1.3", connection_id: "c", negotiation: neg([], [["selection", "not_authorized", true]]), runtime: rt }));
    const now = new Clock();
    now.wall = Date.now();
    const sel = cmd(now, "intent.selection");
    stream.handle(JSON.stringify({ type: "event", delivery_seq: 0, event: sel }));
    expect(got).toHaveLength(0);
    stream.handle(JSON.stringify({ type: "negotiation", negotiation: neg(["selection"]) }));
    stream.handle(JSON.stringify({ type: "event", delivery_seq: 1, event: sel }));
    expect(got).toHaveLength(1);
    stream.handle(JSON.stringify({ type: "negotiation", negotiation: neg([], [["selection", "unsupported_by_device", true]]) }));
    expect(stops).toEqual(["command output stopped"]);
    detach();
    stream.handle(JSON.stringify({ type: "negotiation", negotiation: neg(["selection"]) }));
    expect(g.isActive("selection")).toBe(false); // detached: no longer updated
  });
});

// ------------------------------------------------------------------ schema 1.4 (M5-C)

function ctl(active: boolean, capabilities: string[], reason: string, session_id = "ses_aaaaaaaa"): EnvelopeOf<"control.state"> {
  return {
    schema_version: "1.4",
    session_id,
    device_id: "d",
    seq: 2,
    timestamp_ns: Date.now() * 1e6,
    device_timestamp_ns: null,
    quality: { score: 1, flags: [] },
    provenance: { kind: "runtime", adapter: "brainos.runtime@0.1.0", synthetic: false, model_id: null, origin: "runtime", replayed: false },
    event_type: "control.state",
    capability: "control_status",
    payload: { active, capabilities, reason },
  };
}

function nav(clock: Clock): EventEnvelope {
  const base = cmd(clock, "intent.selection");
  return { ...base, event_type: "intent.navigate", capability: "navigation", payload: { direction: "next", confidence: 0.8 } };
}

describe("CommandGuard + control.state (schema 1.4)", () => {
  it("gates commands on the runtime's control.state and stops with its reason", () => {
    const clock = new Clock();
    const stops: string[] = [];
    const states: string[] = [];
    const g = guard(clock, stops, { onControlState: (c) => states.push(c.reason) });
    g.onNegotiation(neg(["selection", "navigation", "control_status"]));
    expect(g.isActive("selection")).toBe(false);
    expect(g.state("selection")).toBe("control_inactive");
    expect(g.accept(cmd(clock, "intent.selection"))).toBe(false);
    g.onControlState(ctl(true, ["navigation", "selection"], "operator authorized this application"));
    expect(g.isActive("navigation")).toBe(true);
    expect(g.accept(nav(clock))).toBe(true);
    g.onControlState(ctl(true, ["selection"], "authorization revoked by operator (navigation)"));
    expect(stops).toEqual(["authorization revoked by operator (navigation)"]);
    expect(g.isActive("selection")).toBe(true);
    g.onControlState(ctl(false, [], "command output stopped: input stalled"));
    expect(stops.at(-1)).toBe("command output stopped: input stalled");
    expect(g.accept(cmd(clock, "intent.selection"))).toBe(false);
    expect(states).toHaveLength(3);
    // another session's notice never re-enables commands
    g.onRuntime(runtime("streaming", "ses_bbbbbbbb"));
    g.onControlState(ctl(true, ["selection"], "stale", "ses_aaaaaaaa"));
    expect(g.isActive("selection")).toBe(false);
    expect(g.controlState).toBeNull();
  });

  it("without control_status granted, navigation works like any command and notices do not gate", () => {
    const clock = new Clock();
    const stops: string[] = [];
    const g = guard(clock, stops);
    g.onNegotiation(neg(["navigation"]));
    expect(g.accept(nav(clock))).toBe(true);
    g.onControlState(ctl(false, [], "not asked for"));
    expect(g.isActive("navigation")).toBe(true);
    expect(stops).toEqual([]);
  });

  it("attachGuard feeds control.state from the stream before any command", () => {
    const stream = new BrainOSStream({ app: { id: "a", name: "A" }, required: [], webSocket: () => ({}) as WebSocket });
    const stops: string[] = [];
    const g = new CommandGuard({ onStop: (r) => stops.push(r) });
    const got: EventEnvelope[] = [];
    attachGuard(stream, g, (e) => got.push(e));
    const rt = { state: "streaming", device: null, session_id: "ses_aaaaaaaa", state_since_ns: 0, last_error: null, recording: null, apps: [] };
    stream.handle(JSON.stringify({ type: "welcome", protocol: "brainos.stream/1", schema_version: "1.4", connection_id: "c", negotiation: neg(["selection", "control_status"]), runtime: rt }));
    const now = new Clock();
    now.wall = Date.now();
    stream.handle(JSON.stringify({ type: "event", delivery_seq: 0, event: cmd(now, "intent.selection") }));
    expect(got).toHaveLength(0); // no control.state yet
    stream.handle(JSON.stringify({ type: "event", delivery_seq: 1, event: ctl(true, ["selection"], "on") }));
    stream.handle(JSON.stringify({ type: "event", delivery_seq: 2, event: cmd(now, "intent.selection") }));
    expect(got).toHaveLength(1);
    stream.handle(JSON.stringify({ type: "event", delivery_seq: 3, event: ctl(false, [], "command output stopped: stopped by operator") }));
    stream.handle(JSON.stringify({ type: "event", delivery_seq: 4, event: cmd(now, "intent.selection") }));
    expect(got).toHaveLength(1);
    expect(stops).toEqual(["command output stopped: stopped by operator"]);
  });
});
