// AT-24: TS SDK validates envelopes and detects delivery gaps / ordering problems.
import { describe, expect, it, vi } from "vitest";
import { ConcordStream, StreamTracker, validateEnvelope, type EventEnvelope } from ".";

function env(over: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    schema_version: "1.0",
    session_id: "ses_abcdef12",
    device_id: "dev",
    seq: 1,
    timestamp_ns: 1,
    device_timestamp_ns: null,
    event_type: "intent.pointer",
    capability: "pointer_intent",
    payload: { vx: 0.1, vy: 0.2 },
    quality: { score: 1, flags: ["synthetic"] },
    provenance: {
      kind: "simulated_intent",
      adapter: "x@1.0.0",
      synthetic: true,
      model_id: null,
      origin: "t",
      replayed: false,
    },
    ...over,
  };
}

describe("validateEnvelope", () => {
  it("accepts a valid envelope", () => {
    expect(validateEnvelope(env()).ok).toBe(true);
  });

  const bad: [string, unknown][] = [
    ["non-object", 42],
    ["wrong major", env({ schema_version: "2.0" })],
    ["unknown type", env({ event_type: "intent.mind" })],
    ["capability mismatch", env({ capability: "selection" })],
    ["NaN", env({ payload: { vx: Number.NaN, vy: 0 } })],
    ["out of range", env({ payload: { vx: 50, vy: 0 } })],
    ["negative seq", env({ seq: -1 })],
    ["label as intent", env({ provenance: { ...(env().provenance as object), kind: "behavioral_label" } })],
    ["non-synthetic simulated", env({ provenance: { ...(env().provenance as object), synthetic: false } })],
    [
      "decoded without model",
      env({ provenance: { ...(env().provenance as object), kind: "decoded_intent", synthetic: false } }),
    ],
    [
      "ragged recording",
      env({
        event_type: "recording.frame",
        capability: "recording",
        provenance: { ...(env().provenance as object), kind: "raw_signal" },
        payload: { sample_rate_hz: 1000, channel_count: 2, first_sample_index: 0, unit: "uV", samples: [[1, 2], [3]] },
      }),
    ],
  ];
  const prov = env().provenance as Record<string, unknown>;
  const feat = {
    event_type: "features.binned",
    capability: "neural_features",
    provenance: { ...prov, kind: "processed_feature", synthetic: false },
    payload: { feature: "spike_count", unit: "count", bin_ms: 20, bin_index: 0, channel_count: 2, counts: [0, 3] },
  };
  const beh = {
    event_type: "behavior.sample",
    capability: "behavior",
    provenance: { ...prov, kind: "behavioral_label", synthetic: false },
    payload: { quantity: "velocity", dims: ["tx", "ty"], unit: "arbitrary", values: [0.1, 0.2], sample_index: 0, valid: true },
  };
  const kin = {
    event_type: "intent.kinematics",
    capability: "kinematic_intent",
    provenance: { ...prov, kind: "decoded_intent", synthetic: false, model_id: "m1" },
    payload: { quantity: "velocity", dims: ["tx"], unit: "arbitrary", values: [0.1], space: "falcon_h1_7dof" },
  };
  it("accepts schema 1.2 feature vectors and rejects them as raw signal", () => {
    const fv = {
      event_type: "features.vector",
      capability: "neural_features",
      provenance: { ...prov, kind: "processed_feature", synthetic: false },
      payload: { feature: "log_band_power", unit: "log10(uV^2)", band_hz: [70, 150], bin_ms: 50, bin_index: 0, channel_count: 2, values: [1, 2] },
    };
    expect(validateEnvelope(env({ ...fv, schema_version: "1.2" })).ok).toBe(true);
    expect(validateEnvelope(env({ ...fv, provenance: { ...fv.provenance, kind: "raw_signal" } })).ok).toBe(false);
    expect(validateEnvelope(env({ ...fv, payload: { ...fv.payload, values: [1] } })).ok).toBe(false);
  });
  it("accepts schema 1.3 activate/cancel actions and rejects unknown ones", () => {
    const sel = {
      event_type: "intent.selection",
      capability: "selection",
      provenance: { ...prov, kind: "decoded_intent", synthetic: false, model_id: "m1" },
      payload: { action: "activate", confidence: 0.9 },
    };
    expect(validateEnvelope(env({ ...sel, schema_version: "1.3" })).ok).toBe(true);
    expect(validateEnvelope(env({ ...sel, payload: { action: "cancel", confidence: 0.6 } })).ok).toBe(true);
    expect(validateEnvelope(env({ ...sel, payload: { action: "stimulate", confidence: 0.6 } })).ok).toBe(false);
  });
  it("schema 1.4: navigation, control state, model_origin", () => {
    const nav = {
      event_type: "intent.navigate",
      capability: "navigation",
      provenance: { ...prov, kind: "decoded_intent", synthetic: false, model_id: "m1", model_origin: "concord" },
      payload: { direction: "next", confidence: 0.8 },
    };
    expect(validateEnvelope(env({ ...nav, schema_version: "1.4" })).ok).toBe(true);
    expect(validateEnvelope(env({ ...nav, payload: { direction: "jump", confidence: 0.8 } })).ok).toBe(false);
    const hist = { ...nav, provenance: { ...nav.provenance, model_origin: "historical", replayed: false } };
    expect(validateEnvelope(env(hist)).ok).toBe(false); // historical outputs are recorded data
    expect(validateEnvelope(env({ ...hist, provenance: { ...hist.provenance, replayed: true } })).ok).toBe(true);
    expect(validateEnvelope(env({ ...nav, provenance: { ...nav.provenance, model_origin: "mine" } })).ok).toBe(false);
    const cs = {
      event_type: "control.state",
      capability: "control_status",
      provenance: { ...prov, kind: "runtime", synthetic: false },
      payload: { active: false, capabilities: ["pointer_intent"], reason: "operator stop" },
    };
    expect(validateEnvelope(env(cs)).ok).toBe(true);
    expect(validateEnvelope(env({ ...cs, provenance: { ...cs.provenance, kind: "decoded_intent", model_id: "m" } })).ok).toBe(false);
    expect(validateEnvelope(env({ ...cs, payload: { active: "no", capabilities: [], reason: "" } })).ok).toBe(false);
  });
  it("accepts schema 1.1 feature, behavior and decoded kinematic events", () => {
    for (const e of [feat, beh, kin]) expect(validateEnvelope(env({ ...e, schema_version: "1.1" })).ok).toBe(true);
  });
  const bad11: [string, unknown][] = [
    ["features as raw_signal", env({ ...feat, provenance: { ...feat.provenance, kind: "raw_signal" } })],
    ["features as intent", env({ ...feat, provenance: { ...feat.provenance, kind: "decoded_intent", model_id: "m" } })],
    ["negative count", env({ ...feat, payload: { ...feat.payload, counts: [0, -1] } })],
    ["count/channel mismatch", env({ ...feat, payload: { ...feat.payload, counts: [1] } })],
    ["behavior as simulated intent", env({ ...beh, provenance: { ...beh.provenance, kind: "simulated_intent", synthetic: true } })],
    ["behavior dims mismatch", env({ ...beh, payload: { ...beh.payload, values: [1] } })],
    ["recorded behavior as kinematic intent", env({ ...kin, provenance: { ...kin.provenance, kind: "behavioral_label" } })],
    ["decoded kinematics without model", env({ ...kin, provenance: { ...kin.provenance, model_id: null } })],
    ["kinematics without space", env({ ...kin, payload: { ...kin.payload, space: undefined } })],
  ];
  for (const [name, value] of bad11) {
    it(`rejects 1.1 ${name}`, () => {
      expect(validateEnvelope(value).ok).toBe(false);
    });
  }

  for (const [name, value] of bad) {
    it(`rejects ${name}`, () => {
      expect(validateEnvelope(value).ok).toBe(false);
    });
  }
});

describe("StreamTracker", () => {
  const e = (seq: number, session = "ses_abcdef12") => ({ ...env({ seq, session_id: session }) }) as unknown as EventEnvelope;

  it("detects delivery gaps (server drops)", () => {
    const t = new StreamTracker();
    t.newConnection();
    t.observe(0, e(1));
    t.observe(1, e(2));
    t.observe(5, e(9));
    expect(t.stats.deliveryGaps).toBe(1);
    expect(t.stats.missedEvents).toBe(3);
    expect(t.stats.outOfOrder).toBe(0);
  });

  it("detects out-of-order envelope seq within a session but not across sessions", () => {
    const t = new StreamTracker();
    t.newConnection();
    t.observe(0, e(10));
    t.observe(1, e(5));
    t.observe(2, e(0, "ses_zzzzzz99"));
    expect(t.stats.outOfOrder).toBe(1);
  });

  it("resets delivery tracking on reconnect", () => {
    const t = new StreamTracker();
    t.newConnection();
    t.observe(0, e(1));
    t.observe(1, e(2));
    t.newConnection();
    t.observe(0, e(3));
    expect(t.stats.deliveryGaps).toBe(0);
    expect(t.stats.connections).toBe(2);
  });
});

class FakeWS {
  static last: FakeWS | null = null;
  sent: string[] = [];
  onopen: (() => void) | null = null;
  onmessage: ((m: { data: string }) => void) | null = null;
  onclose: (() => void) | null = null;
  constructor() {
    FakeWS.last = this;
  }
  send(s: string) {
    this.sent.push(s);
  }
  close() {
    this.onclose?.();
  }
}

describe("ConcordStream", () => {
  const make = () =>
    new ConcordStream({
      app: { id: "t", name: "t" },
      required: ["selection"],
      optional: ["pointer_intent"],
      url: "ws://x",
      webSocket: () => new FakeWS() as unknown as WebSocket,
    });

  it("sends hello, emits negotiation and only valid events", () => {
    const s = make();
    const events: EventEnvelope[] = [];
    const notices: string[] = [];
    s.on("event", (e) => events.push(e));
    s.on("notice", (n) => notices.push(n.code));
    s.connect();
    const ws = FakeWS.last!;
    ws.onopen?.();
    const hello = JSON.parse(ws.sent[0]!);
    expect(hello).toMatchObject({ type: "hello", protocol: "concord.stream/1", capabilities: { required: ["selection"] } });
    s.handle(
      JSON.stringify({
        type: "welcome",
        protocol: "concord.stream/1",
        schema_version: "1.0",
        connection_id: "c1",
        negotiation: { device_id: "d", status: "active", granted: ["selection"], rejected: [] },
        runtime: null,
      }),
    );
    expect(s.status).toBe("open");
    expect(s.granted).toEqual(["selection"]);
    s.handle(JSON.stringify({ type: "event", delivery_seq: 0, event: env() }));
    s.handle(JSON.stringify({ type: "event", delivery_seq: 1, event: env({ seq: 2, capability: "selection" }) }));
    expect(events).toHaveLength(1);
    expect(notices).toEqual(["invalid_event"]);
    expect(s.stats.invalid).toBe(1);
  });

  it("does not reconnect after a handshake rejection", () => {
    vi.useFakeTimers();
    const s = make();
    s.connect();
    const ws = FakeWS.last!;
    s.handle(JSON.stringify({ type: "error", code: "unknown_capability", message: "x" }));
    expect(s.status).toBe("rejected");
    ws.onclose?.();
    vi.advanceTimersByTime(10_000);
    expect(FakeWS.last).toBe(ws);
    vi.useRealTimers();
  });

  it("reconnects with backoff after an unexpected close", () => {
    vi.useFakeTimers();
    const s = make();
    s.connect();
    const first = FakeWS.last!;
    first.onclose?.();
    expect(s.status).toBe("reconnecting");
    vi.advanceTimersByTime(300);
    expect(FakeWS.last).not.toBe(first);
    s.close();
    vi.useRealTimers();
  });
});
