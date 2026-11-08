// The console is itself a Concord stream client (kind "console") requesting every
// capability. High-rate data lives in refs; React re-renders on a 10 Hz tick.

import { useEffect, useRef, useState } from "react";
import {
  ConcordStream,
  CAPABILITIES,
  type ConnectionStatus,
  type EnvelopeOf,
  type EventEnvelope,
  type NegotiationResult,
  type RuntimeSnapshot,
  type TelemetryMetric,
} from "../sdk";
import { DATA_EVENT_TYPES } from "./integrity";
import { NeuralBuffer } from "./neuralBuffer";
import { SignalBuffer } from "./signalBuffer";

export const EVENT_LOG_SIZE = 400;
const STATUS_LOG_SIZE = 200;
const LATENCY_WINDOW = 1000;

export interface ConsoleStreamData {
  conn: ConnectionStatus;
  runtime: RuntimeSnapshot | null;
  negotiation: NegotiationResult | null;
  events: EventEnvelope[];
  telemetry: { metrics: TelemetryMetric[]; at: number; deviceId: string; sessionId: string } | null;
  signal: SignalBuffer;
  neural: NeuralBuffer;
  clientLatencyMs: number[];
  /** the most recent raw-signal / feature event: when it arrived here, and its channel count */
  lastData: { at: number; session: string; channels: number } | null;
  /** device.status events (kept apart from the ring above so none is missed); total = ever received */
  statusEvents: { list: EnvelopeOf<"device.status">[]; total: number };
  stats: ConcordStream["stats"];
  tick: number;
}

export function useConsoleStream(): ConsoleStreamData {
  const [conn, setConn] = useState<ConnectionStatus>("idle");
  const [runtime, setRuntime] = useState<RuntimeSnapshot | null>(null);
  const [negotiation, setNegotiation] = useState<NegotiationResult | null>(null);
  const [tick, setTick] = useState(0);
  const events = useRef<EventEnvelope[]>([]);
  const telemetry = useRef<ConsoleStreamData["telemetry"]>(null);
  const signal = useRef(new SignalBuffer());
  const neural = useRef(new NeuralBuffer());
  const latency = useRef<number[]>([]);
  const lastData = useRef<ConsoleStreamData["lastData"]>(null);
  const statusEvents = useRef<ConsoleStreamData["statusEvents"]>({ list: [], total: 0 });
  const streamRef = useRef<ConcordStream | null>(null);

  useEffect(() => {
    const stream = new ConcordStream({
      app: { id: "operator-console", name: "Operator Console", kind: "console" },
      required: [],
      optional: [...CAPABILITIES],
    });
    streamRef.current = stream;
    const offs = [
      stream.on("status", setConn),
      stream.on("runtime", setRuntime),
      stream.on("negotiation", setNegotiation),
      stream.on("event", (e) => {
        const log = events.current;
        log.push(e);
        if (log.length > EVENT_LOG_SIZE) log.splice(0, log.length - EVENT_LOG_SIZE);
        const lat = Date.now() - e.timestamp_ns / 1e6;
        latency.current.push(lat);
        if (latency.current.length > LATENCY_WINDOW) latency.current.shift();
        if (DATA_EVENT_TYPES.has(e.event_type) && "channel_count" in e.payload)
          lastData.current = { at: Date.now(), session: e.session_id, channels: e.payload.channel_count };
        if (e.event_type === "device.status") {
          const st = statusEvents.current;
          st.list.push(e);
          st.total += 1;
          if (st.list.length > STATUS_LOG_SIZE) st.list.splice(0, st.list.length - STATUS_LOG_SIZE);
        }
        if (e.event_type === "recording.frame") signal.current.push(e.session_id, e.payload);
        else if (e.event_type === "features.binned") neural.current.pushFeatures(e.session_id, e.payload);
        else if (e.event_type === "behavior.sample") neural.current.pushBehavior(e.session_id, e.payload);
        else if (e.event_type === "intent.kinematics" && e.provenance.kind === "decoded_intent")
          neural.current.pushDecoded(e.session_id, e.payload, e.provenance.model_id);
        else if (e.event_type === "telemetry.sample")
          telemetry.current = {
            metrics: e.payload.metrics,
            at: Date.now(),
            deviceId: e.device_id,
            sessionId: e.session_id,
          };
      }),
    ];
    stream.connect();
    const t = setInterval(() => setTick((n) => n + 1), 100);
    return () => {
      offs.forEach((off) => off());
      clearInterval(t);
      stream.close();
    };
  }, []);

  return {
    conn,
    // The snapshot is only true while the stream is open; never present it as live afterwards.
    runtime: conn === "open" ? runtime : null,
    negotiation,
    events: events.current,
    telemetry: telemetry.current,
    signal: signal.current,
    neural: neural.current,
    clientLatencyMs: latency.current,
    lastData: lastData.current,
    statusEvents: statusEvents.current,
    stats: streamRef.current?.stats ?? {
      received: 0,
      invalid: 0,
      deliveryGaps: 0,
      missedEvents: 0,
      outOfOrder: 0,
      connections: 0,
    },
    tick,
  };
}

export function percentile(values: number[], p: number): number | null {
  if (values.length === 0) return null;
  const s = [...values].sort((a, b) => a - b);
  return s[Math.min(s.length - 1, Math.round(p * (s.length - 1)))] ?? null;
}
