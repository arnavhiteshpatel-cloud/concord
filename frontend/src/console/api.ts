// Console-only API wrappers: diagnostics, recordings, test reports and the
// simulation operator endpoints. Applications never use these.

import { apiCall, type ConnectedApp } from "../sdk";

export interface LatencySummary {
  count: number;
  p50_us: number | null;
  p95_us: number | null;
  p99_us: number | null;
  max_us: number | null;
}

export interface DiagnosticsSnapshot {
  uptime_s: number;
  measured_at_ns: number;
  counters: {
    events_published: number;
    decode_errors: number;
    validation_errors: number;
    undeclared_capability: number;
    timestamp_regressions: number;
    discarded_while_paused: number;
    link_errors: number;
    reconnect_attempts: number;
    reconnect_successes: number;
    subscriber_drops: number;
  };
  event_types: { event_type: string; total: number; rate_hz: number }[];
  pipeline_latency: LatencySummary;
  delivery_latency: LatencySummary;
  switches: { from_device: string | null; to_device: string; duration_ms: number; at_ns: number }[];
  recent_errors: { at_ns: number; kind: string; device_id: string | null; message: string }[];
  apps: ConnectedApp[];
  process: Record<string, string>;
}

export interface RecordingInfo {
  name: string;
  device_id: string;
  device_name: string;
  synthetic: boolean;
  created_at_ns: number;
  size_bytes: number;
  events: number | null;
  active: boolean;
}

export interface TestCase {
  suite: string;
  name: string;
  status: "passed" | "failed" | "skipped";
  time_s: number;
  message: string | null;
}

export interface TestReport {
  name: string;
  source: string;
  available: boolean;
  generated_at_ns: number | null;
  total: number;
  passed: number;
  failed: number;
  skipped: number;
  duration_s: number;
  cases: TestCase[];
  error: string | null;
}

export interface CapabilityInfo {
  capability: string;
  description: string;
  event_types: string[];
}

export type Fault = "link_drop" | "link_fail" | "malformed_packet" | "timestamp_regression";

export const consoleApi = {
  diagnostics: () => apiCall<DiagnosticsSnapshot>("/diagnostics"),
  recordings: () => apiCall<RecordingInfo[]>("/recordings"),
  startRecording: (name?: string) =>
    apiCall<{ name: string }>("/recordings/start", { method: "POST", body: name ? { name } : {} }),
  stopRecording: () => apiCall<RecordingInfo>("/recordings/stop", { method: "POST" }),
  tests: () => apiCall<TestReport[]>("/system/tests"),
  capabilities: () => apiCall<CapabilityInfo[]>("/capabilities"),
  simPointer: (vx: number, vy: number) =>
    apiCall<unknown>("/sim/pointer", { method: "POST", body: { vx, vy } }),
  simSelect: () => apiCall<unknown>("/sim/select", { method: "POST" }),
  simText: (text: string) => apiCall<unknown>("/sim/text", { method: "POST", body: { text } }),
  simFault: (fault: Fault) => apiCall<unknown>("/sim/faults", { method: "POST", body: { fault } }),
};
