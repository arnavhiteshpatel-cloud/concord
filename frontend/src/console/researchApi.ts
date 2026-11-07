// Milestone 5 (D): research sessions, export, safe stop, stored data, support report.
// Shapes mirror backend/src/brainos/server/session_routes.py and runtime/{sessions,export,
// safe_stop,retention,recorder}.py. Console-only: applications never use these.

import { apiCall } from "../sdk";

export interface ResearchSession {
  id: string;
  name: string;
  operator: string | null;
  notes: string | null;
  created_at_ns: number;
  closed_at_ns: number | null;
  status: "active" | "closed" | "interrupted";
  end_reason: string | null;
  brainos_version: string;
  recordings: string[];
  models: string[];
  log_entries: number;
}

export interface SessionsStatus {
  active: ResearchSession | null;
  sessions: ResearchSession[];
}

export interface SessionLogEntry {
  at_ns: number;
  kind: string;
  action?: string;
  status?: number;
  [key: string]: unknown;
}

export interface ExportFile {
  file: string;
  size_bytes: number;
  created_at_ns: number;
}

export interface SessionDetail {
  session: ResearchSession;
  log: SessionLogEntry[];
  log_total: number;
  exports: ExportFile[];
}

export interface ExportOptions {
  include_recordings: boolean;
  include_personal: boolean;
}

export interface ExportInfo {
  session_id: string;
  file: string;
  size_bytes: number;
  sha256: string;
  created_at_ns: number;
  files: number;
  included_recordings: string[];
  omitted_recordings: string[];
  missing_recordings: string[];
  models: string[];
  missing_models: string[];
  options: ExportOptions;
}

export interface SafeStopStep {
  step: "command_output" | "recording" | "decoding" | "source";
  done: boolean;
  detail: string;
  error: string | null;
  ms: number;
}

export interface SafeStopReport {
  at_ns: number;
  reason: string;
  steps: SafeStopStep[];
  state: string;
  ok: boolean;
}

export interface RetentionAction {
  kind: string;
  name: string;
  age_days: number;
  bytes: number;
}

export interface StorageStatus {
  data_dir: string;
  usage: Record<"recordings" | "models" | "sessions" | "exports", { count: number; bytes: number }>;
  retention: Record<string, number | null>;
  last_retention: { ran_at_ns: number; deleted: RetentionAction[]; kept_in_use: string[]; errors: string[] } | null;
  recovered_recordings: string[];
  interrupted_sessions: string[];
}

export interface Deleted {
  deleted: string;
  bytes: number;
  also_deleted: string[];
}

export interface DoctorCheck {
  id: string;
  title: string;
  status: "ok" | "info" | "warn" | "fail";
  detail: string;
  hint?: string;
}

export interface DoctorReport {
  format: string;
  generated_at: string;
  summary: Record<"ok" | "info" | "warn" | "fail", number>;
  checks: DoctorCheck[];
  excluded: string[];
  [key: string]: unknown;
}

const enc = encodeURIComponent;

export const researchApi = {
  sessions: () => apiCall<SessionsStatus>("/sessions"),
  createSession: (name: string, operator: string | null, notes: string | null) =>
    apiCall<ResearchSession>("/sessions", {
      method: "POST",
      body: { name, ...(operator ? { operator } : {}), ...(notes ? { notes } : {}) },
    }),
  session: (id: string) => apiCall<SessionDetail>(`/sessions/${enc(id)}?tail=50`),
  closeSession: (id: string) =>
    apiCall<{ session: ResearchSession; safe_stop: SafeStopReport | null }>(`/sessions/${enc(id)}/close`, {
      method: "POST",
      body: { safe_stop: true },
    }),
  exportSession: (id: string, options: ExportOptions) =>
    apiCall<ExportInfo>(`/sessions/${enc(id)}/export`, { method: "POST", body: options }),
  exportUrl: (id: string, file: string) => `/api/v1/sessions/${enc(id)}/exports/${enc(file)}`,
  safeStop: () => apiCall<SafeStopReport>("/safe-stop", { method: "POST", body: {} }),
  storage: () => apiCall<StorageStatus>("/storage"),
  deleteRecording: (name: string) =>
    apiCall<Deleted>(`/recordings/${enc(name)}?confirm=${enc(name)}`, { method: "DELETE" }),
  deleteModel: (id: string) => apiCall<Deleted>(`/models/${enc(id)}?confirm=${enc(id)}`, { method: "DELETE" }),
  deleteSession: (id: string, withRecordings: boolean) =>
    apiCall<Deleted>(`/sessions/${enc(id)}?confirm=${enc(id)}&delete_recordings=${withRecordings}`, {
      method: "DELETE",
    }),
  doctor: () => apiCall<DoctorReport>("/system/doctor"),
  doctorMarkdownUrl: "/api/v1/system/doctor?format=markdown",
};

const STEP_WORDS: Record<SafeStopStep["step"], string> = {
  command_output: "command output",
  recording: "recording",
  decoding: "decoding",
  source: "source",
};

/** One line for the session log: what a safe stop actually stopped. */
export function safeStopText(r: SafeStopReport): string {
  const done = r.steps.filter((s) => s.done).map((s) => STEP_WORDS[s.step]);
  const failed = r.steps.filter((s) => s.error).map((s) => `${STEP_WORDS[s.step]} (${s.error})`);
  const head = done.length ? `Safe stop: stopped ${done.join(", ")}` : "Safe stop: nothing was running";
  return failed.length ? `${head}; failed: ${failed.join(", ")}` : head;
}
