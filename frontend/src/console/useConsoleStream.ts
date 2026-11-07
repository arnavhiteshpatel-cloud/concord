// The console is itself a BrainOS stream client (kind "console") requesting every
// capability. High-rate data lives in refs; React re-renders on a 10 Hz tick.

import { useEffect, useRef, useState } from "react";
import {
  BrainOSStream,
  CAPABILITIES,
  type ConnectionStatus,
  type EventEnvelope,
  type NegotiationResult,
  type RuntimeSnapshot,
  type TelemetryMetric,
} from "../sdk";
import { SignalBuffer } from "./signalBuffer";

export const EVENT_LOG_SIZE = 400;
const LATENCY_WINDOW = 1000;

export interface ConsoleStreamData {
  conn: ConnectionStatus;
  runtime: RuntimeSnapshot | null;
  negotiation: NegotiationResult | null;
  events: EventEnvelope[];
  telemetry: { metrics: TelemetryMetric[]; at: number; deviceId: string; sessionId: string } | null;
  signal: SignalBuffer;
  clientLatencyMs: number[];
  stats: BrainOSStream["stats"];
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
  const latency = useRef<number[]>([]);
  const streamRef = useRef<BrainOSStream | null>(null);

  useEffect(() => {
    const stream = new BrainOSStream({
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
        if (e.event_type === "recording.frame") signal.current.push(e.session_id, e.payload);
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
    clientLatencyMs: latency.current,
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
