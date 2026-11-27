// Human-readable labels for task, metric, modality and visit codes.
import { humanize } from './ui.js';

const METRICS = {
  fitts_throughput_bps: 'Throughput (bit/s)',
  achieved_bitrate_bps: 'Achieved bit rate (bit/s)',
  wpm_mean: 'Text entry speed (words/min)',
  movement_time_ms_mean: 'Movement time (ms)',
  success_rate: 'Success rate',
};
const MODALITIES = {
  mouse_sim: 'Mouse (sim.)',
  bci_cursor_good_sim: 'BCI cursor (sim.)',
  eye_gaze_sim: 'Eye gaze (sim.)',
  switch_scan_sim: 'Switch scanning (sim.)',
  bci: 'BCI', eye_gaze: 'Eye gaze', switch: 'Switch', mouse: 'Mouse',
};
const TASK_SHORT = {
  A2: 'Pointing (ISO ring)', A4: 'Grid selection', E1: 'Copy typing', F1: 'Select a contact',
};

export function labels(battery) {
  const names = {};
  for (const t of (battery && battery.tasks) || []) names[t.id] = t.name;
  return {
    task: (id) => `${id} · ${TASK_SHORT[id] || names[id] || id}`,
    taskLong: (id) => names[id] || id,
    metric: (m) => METRICS[m] || humanize(m),
    modality: (m) => MODALITIES[m] || humanize(m),
    visit: (v) => {
      if (!v) return '—';
      if (v === 'baseline') return 'Baseline';
      let m = /^week_(\d+)$/.exec(v);
      if (m) return `Week ${Number(m[1])}`;
      m = /^home_(\d+)$/.exec(v);
      if (m) return `Home ${Number(m[1])}`;
      return humanize(v);
    },
  };
}
