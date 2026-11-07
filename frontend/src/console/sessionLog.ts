// The session log: what happened, newest first. Entries come from real sources only —
// device.status events, runtime/server state, operator actions and their refusals,
// pipeline and command-output changes, recordings, calibration results and the
// runtime's recent-error list.

import { useCallback, useRef, useState } from "react";
import type { DeviceStatusPayload } from "../sdk";
import { capitalize, type Tone } from "./wording";

export const LOG_CAP = 200;

export interface LogEntry {
  id: number;
  /** wall-clock ms */
  at: number;
  tone: Tone;
  text: string;
}

export interface SessionLog {
  entries: LogEntry[];
  add: (tone: Tone, text: string, at?: number) => void;
}

export function useSessionLog(): SessionLog {
  const [entries, setEntries] = useState<LogEntry[]>([]);
  const next = useRef(0);
  const add = useCallback((tone: Tone, text: string, at: number = Date.now()) => {
    const id = ++next.current;
    setEntries((list) => {
      const out = [{ id, at, tone, text }, ...list];
      // newest first by time; entries can arrive slightly out of order (polls vs events)
      out.sort((a, b) => b.at - a.at || b.id - a.id);
      return out.slice(0, LOG_CAP);
    });
  }, []);
  return { entries, add };
}

/** A device.status event as a log line. */
export function statusEntry(p: DeviceStatusPayload): { tone: Tone; text: string } {
  const detail = p.detail.trim();
  switch (p.state) {
    case "connected":
      return { tone: "info", text: capitalize(detail || "Connected") };
    case "streaming":
      return { tone: "ok", text: detail && detail !== "streaming" ? `Streaming (${detail})` : "Streaming" };
    case "paused":
      return { tone: "inactive", text: detail ? `Paused (${detail})` : "Paused" };
    case "reconnecting":
      return { tone: "caution", text: detail ? `Link lost, reconnecting: ${detail}` : "Link lost, reconnecting" };
    case "disconnected":
      return { tone: "inactive", text: detail ? `Disconnected (${detail})` : "Disconnected" };
    case "error":
      return { tone: "alarm", text: detail ? `Source error: ${detail}` : "Source error" };
    case "ended":
      return { tone: "inactive", text: detail ? `Source ended: ${detail}` : "Source ended" };
  }
}

/** Runtime error kinds already reported by a device.status event (not logged twice). */
export const ERRORS_COVERED_BY_STATUS = new Set(["link_error", "reconnect_failed"]);

/** Runtime errors that stop the session are high priority (red); the rest are technical (neutral). */
const STOPPING_ERRORS = new Set(["pump_crash", "reconnect_failed"]);

export function errorEntry(kind: string, message: string): { tone: Tone; text: string } {
  return {
    tone: STOPPING_ERRORS.has(kind) ? "alarm" : "info",
    text: `${capitalize(kind.replace(/_/g, " "))}: ${message}`,
  };
}

export function clock(ms: number): string {
  const d = new Date(ms);
  const p = (n: number) => String(n).padStart(2, "0");
  return `${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`;
}
