// Stimuli are generated in Python (neurometric.tasks.battery.stimuli, seed 0) and exported to
// public/battery/*.json by web/scripts/export_battery.py. The browser never generates stimuli
// with its own PRNG (DECISIONS D-004), so it presents byte-identical stimuli (stimulus_hash).

export interface Stimuli {
  task_id: string;
  battery_version: string;
  seed: number;
  params: Record<string, any>;
  canvas: [number, number];
  stimulus_hash: string;
  blocks?: { D: number; W: number; targets: { x: number; y: number; w: number; idx: number }[] }[];
  trials?: any[];
  items?: { id: number; x: number; y: number; w: number; h: number }[];
  cues?: number[];
  phrases?: string[];
  keys?: { key: string; x: number; y: number; w: number; h: number }[];
  path?: { f: number; ax: number; ay: number; px: number; py: number }[];
}

export interface TaskSpec {
  id: string;
  family: string;
  name: string;
  version: string;
  construct: string;
  stimuli: string;
  timing: string;
  completion: string;
  accessibility: string;
  defaults: Record<string, any>;
}

export interface Manifest {
  battery_version: string;
  status: string;
  tasks: TaskSpec[];
}

export interface AdlScreen {
  items: { x: number; y: number; w: number; h: number }[];
  target: number;
}

const cache = new Map<string, Promise<any>>();

function getJson<T>(path: string): Promise<T> {
  let p = cache.get(path);
  if (!p) {
    p = fetch(path).then((r) => {
      if (!r.ok) throw new Error(`could not load ${path} (${r.status})`);
      return r.json();
    });
    cache.set(path, p);
    p.catch(() => cache.delete(path));
  }
  return p as Promise<T>;
}

export const loadStimuli = (taskId: string) => getJson<Stimuli>(`battery/${taskId}.json`);
export const loadManifest = () => getJson<Manifest>("battery/manifest.json");
export const loadPhrases = () => getJson<{ phrases: string[] }>("battery/phrases.json").then((d) => d.phrases);
export const loadAdl = () => getJson<Record<string, AdlScreen[]>>("battery/adl_layouts.json");

export const IMPLEMENTED = ["A1", "A2", "A3", "A4", "A5", "B1", "B2", "C1", "D1", "E1", "E2", "F1", "F2", "F3", "F4", "F5", "F6", "F7"];
