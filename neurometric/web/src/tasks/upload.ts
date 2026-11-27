// Session upload to the NeuroMetric backend (src/neurometric/api, same origin), with local
// fallback. Contract (api/app.py, api/models.py SessionIn):
//   POST /api/auth/login {username, password} -> {token, ...}
//   POST /api/participants/{pid}/sessions  Authorization: Bearer <token>
//        {task_id, events, stimulus_seed, stimulus_hash, battery_version, provenance, modality, performed_at}
// The server re-validates every event, checks the stimulus hash and computes the authoritative
// scores. The browser's numbers are provisional only.

import type { TaskRun } from "./session";

export async function serverAvailable(): Promise<boolean> {
  try {
    const r = await fetch("api/health", { headers: { accept: "application/json" } });
    if (!r.ok) return false;
    const j = await r.json();
    return j && j.status === "ok";
  } catch {
    return false;
  }
}

export async function login(username: string, password: string): Promise<string> {
  const r = await fetch("api/auth/login", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ username, password }),
  });
  const j = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(j.message || `login failed (${r.status})`);
  return j.token as string;
}

export function sessionBody(run: TaskRun): Record<string, unknown> {
  return {
    task_id: run.task_id,
    events: run.events,
    stimulus_seed: run.stimulus_seed,
    stimulus_hash: run.stimulus_hash,
    battery_version: run.battery_version,
    provenance: run.provenance,
    modality: run.modality,
    performed_at: new Date(run.started_at_epoch_ms).toISOString(),
  };
}

export async function uploadRun(run: TaskRun, participantId: string, token: string): Promise<Record<string, unknown>> {
  const r = await fetch(`api/participants/${encodeURIComponent(participantId)}/sessions`, {
    method: "POST",
    headers: { "content-type": "application/json", authorization: `Bearer ${token}` },
    body: JSON.stringify(sessionBody(run)),
  });
  const j = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(j.message || `upload failed (${r.status})`);
  return j;
}

const LOCAL_KEY = "neurometric.runs.v1";

/** Keep finished runs in this browser (best effort; storage may be unavailable or full). */
export function saveLocal(run: TaskRun): boolean {
  try {
    const list: TaskRun[] = JSON.parse(localStorage.getItem(LOCAL_KEY) ?? "[]");
    list.push(run);
    while (list.length > 20) list.shift();
    localStorage.setItem(LOCAL_KEY, JSON.stringify(list));
    return true;
  } catch {
    return false;
  }
}

export function loadLocal(): TaskRun[] {
  try {
    return JSON.parse(localStorage.getItem(LOCAL_KEY) ?? "[]");
  } catch {
    return [];
  }
}

export function downloadJson(name: string, data: unknown): void {
  const blob = new Blob([JSON.stringify(data, null, 1)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
