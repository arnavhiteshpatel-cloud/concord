// Runtime validation of incoming envelopes. The server already validates every
// event; the SDK re-checks the contract rules apps depend on, so a buggy or
// spoofed server cannot hand an app e.g. a behavioral label disguised as intent.

import {
  ALLOWED_PROVENANCE,
  EVENT_CAPABILITY,
  SCHEMA_MAJOR,
  type EventEnvelope,
  type EventType,
} from "./types";

export type ValidationResult = { ok: true; event: EventEnvelope } | { ok: false; error: string };

const isObj = (x: unknown): x is Record<string, unknown> =>
  typeof x === "object" && x !== null && !Array.isArray(x);
const isNum = (x: unknown): x is number => typeof x === "number" && Number.isFinite(x);
const isInt = (x: unknown): x is number => isNum(x) && Number.isInteger(x);
const isStr = (x: unknown): x is string => typeof x === "string";
const inRange = (x: unknown, lo: number, hi: number) => isNum(x) && x >= lo && x <= hi;

function checkPayload(type: EventType, p: Record<string, unknown>): string | null {
  switch (type) {
    case "intent.pointer":
      return inRange(p.vx, -10, 10) && inRange(p.vy, -10, 10) ? null : "pointer vx/vy invalid";
    case "intent.selection":
      return (p.action === "primary" || p.action === "activate" || p.action === "cancel") && inRange(p.confidence, 0, 1) ? null : "selection invalid";
    case "intent.text":
      return isStr(p.text) &&
        p.text.length >= 1 &&
        p.text.length <= 64 &&
        (p.mode === "character" || p.mode === "word") &&
        inRange(p.confidence, 0, 1)
        ? null
        : "text intent invalid";
    case "recording.frame": {
      const s = p.samples;
      if (!isInt(p.channel_count) || !isNum(p.sample_rate_hz) || !Array.isArray(s))
        return "recording frame invalid";
      if (s.length !== p.channel_count) return "recording channel_count mismatch";
      if (p.unit !== "uV" && p.unit !== "arbitrary") return "recording unit invalid";
      const n = Array.isArray(s[0]) ? s[0].length : -1;
      for (const ch of s) {
        if (!Array.isArray(ch) || ch.length !== n || !ch.every(isNum))
          return "recording samples invalid";
      }
      return null;
    }
    case "recording.annotation":
      return isStr(p.label) ? null : "annotation invalid";
    case "telemetry.sample":
      return Array.isArray(p.metrics) &&
        p.metrics.length > 0 &&
        p.metrics.every((m) => isObj(m) && isStr(m.name) && isNum(m.value) && isStr(m.unit))
        ? null
        : "telemetry invalid";
    case "device.status":
      return isStr(p.state) ? null : "status invalid";
    case "features.binned":
      return isInt(p.channel_count) &&
        inRange(p.bin_ms, 0, 10_000) &&
        isInt(p.bin_index) &&
        Array.isArray(p.counts) &&
        p.counts.length === p.channel_count &&
        p.counts.every((c) => isInt(c) && c >= 0)
        ? null
        : "features invalid";
    case "features.vector":
      return isInt(p.channel_count) &&
        inRange(p.bin_ms, 0, 10_000) &&
        isInt(p.bin_index) &&
        Array.isArray(p.values) &&
        p.values.length === p.channel_count &&
        p.values.every(isNum)
        ? null
        : "feature vector invalid";
    case "behavior.sample":
    case "intent.kinematics": {
      const ok =
        Array.isArray(p.dims) &&
        p.dims.every(isStr) &&
        Array.isArray(p.values) &&
        p.values.length === p.dims.length &&
        p.values.every(isNum) &&
        isStr(p.unit) &&
        isStr(p.quantity);
      if (!ok) return `${type} invalid`;
      if (type === "intent.kinematics" && !isStr(p.space)) return "kinematic intent requires space";
      return null;
    }
  }
}

export function validateEnvelope(x: unknown): ValidationResult {
  if (!isObj(x)) return { ok: false, error: "not an object" };
  if (!isStr(x.schema_version) || !/^\d+\.\d+$/.test(x.schema_version))
    return { ok: false, error: "bad schema_version" };
  if (Number(x.schema_version.split(".")[0]) !== SCHEMA_MAJOR)
    return { ok: false, error: `unsupported schema ${x.schema_version}` };
  if (!isStr(x.session_id) || !isStr(x.device_id)) return { ok: false, error: "missing ids" };
  if (!isInt(x.seq) || x.seq < 0) return { ok: false, error: "bad seq" };
  if (!isNum(x.timestamp_ns)) return { ok: false, error: "bad timestamp_ns" };
  const type = x.event_type;
  if (!isStr(type) || !(type in EVENT_CAPABILITY))
    return { ok: false, error: `unknown event_type ${String(type)}` };
  const et = type as EventType;
  if (x.capability !== EVENT_CAPABILITY[et])
    return { ok: false, error: `capability ${String(x.capability)} does not match ${et}` };
  const q = x.quality;
  if (!isObj(q) || !inRange(q.score, 0, 1) || !Array.isArray(q.flags))
    return { ok: false, error: "bad quality" };
  const prov = x.provenance;
  if (!isObj(prov) || !isStr(prov.kind)) return { ok: false, error: "bad provenance" };
  const allowed = ALLOWED_PROVENANCE[et] as readonly string[];
  if (!allowed.includes(prov.kind))
    return { ok: false, error: `provenance ${prov.kind} not allowed for ${et}` };
  if (prov.kind === "simulated_intent" && prov.synthetic !== true)
    return { ok: false, error: "simulated_intent must be synthetic" };
  if (prov.kind === "decoded_intent" && !isStr(prov.model_id))
    return { ok: false, error: "decoded_intent requires model_id" };
  if (!isObj(x.payload)) return { ok: false, error: "bad payload" };
  const perr = checkPayload(et, x.payload);
  if (perr) return { ok: false, error: perr };
  return { ok: true, event: x as unknown as EventEnvelope };
}
