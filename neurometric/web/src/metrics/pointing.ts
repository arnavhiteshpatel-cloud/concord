// Small TypeScript subset of neurometric.metrics.pointing for PROVISIONAL in-browser feedback
// and the live degradation demo. Authoritative scoring is server-side (Python, D-003); this
// subset is checked against Python golden fixtures (test/parity.test.ts).

export const WE_FACTOR = Math.sqrt(2 * Math.PI * Math.E);

export interface Trial {
  t_ms: number[]; // sample times relative to stimulus onset
  xy: [number, number][]; // cursor samples
  start: [number, number];
  target: [number, number];
  half: [number, number]; // half sizes
  sel_t: number | null; // terminating selection time (null = none)
  sel_pos: [number, number];
  sel_item: number; // 0 target, >0 other item, -1 empty space, -2 none (timeout)
  n_empty?: number;
}

export interface TrialMetrics {
  success: boolean;
  error: boolean;
  timeout: boolean;
  movement_time_ms: number;
  onset_ms: number;
  distance_px: number;
  path_length_px: number;
  path_efficiency: number;
  endpoint_error_px: number;
  endpoint_dx_px: number;
  amplitude_px: number;
  overshoot_px: number;
  target_reentries: number;
}

export function trialMetrics(tr: Trial, onsetFrac = 0.1): TrialMetrics {
  const dx0 = tr.target[0] - tr.start[0];
  const dy0 = tr.target[1] - tr.start[1];
  const D = Math.hypot(dx0, dy0);
  const den = Math.max(D, 1e-9);
  const u: [number, number] = [dx0 / den, dy0 / den];
  const selT = tr.sel_t === null || tr.sel_t === undefined ? Infinity : tr.sel_t;
  const n = tr.xy.length;
  const valid: boolean[] = new Array(n);
  for (let i = 0; i < n; i++) {
    const t = tr.t_ms[i];
    valid[i] = Number.isFinite(tr.xy[i][0]) && (Number.isFinite(t) ? t : Infinity) <= selT + 1e-9;
  }
  let path = 0;
  for (let i = 1; i < n; i++) {
    if (valid[i] && valid[i - 1]) path += Math.hypot(tr.xy[i][0] - tr.xy[i - 1][0], tr.xy[i][1] - tr.xy[i - 1][1]);
  }
  const end = tr.sel_pos;
  const disp = Math.hypot(end[0] - tr.start[0], end[1] - tr.start[1]);
  const success = tr.sel_item === 0;
  const timeout = tr.sel_item === -2;
  const error = !success && !timeout;
  let onset = NaN;
  let maxProj = -Infinity;
  for (let i = 0; i < n; i++) {
    if (!valid[i]) continue;
    const p = (tr.xy[i][0] - tr.start[0]) * u[0] + (tr.xy[i][1] - tr.start[1]) * u[1];
    if (Number.isNaN(onset) && p >= onsetFrac * D) onset = tr.t_ms[i];
    if (p > maxProj) maxProj = p;
  }
  let eff = path > 0 ? disp / Math.max(path, 1e-9) : NaN;
  if (timeout) eff = NaN;
  const hAlong = Math.abs(u[0]) * tr.half[0] + Math.abs(u[1]) * tr.half[1];
  // target re-entries (rectangular hit test, as in Python)
  let entries = 0;
  let prevIn = false;
  for (let i = 0; i < n; i++) {
    const ins = valid[i] && Math.abs(tr.xy[i][0] - tr.target[0]) <= tr.half[0] && Math.abs(tr.xy[i][1] - tr.target[1]) <= tr.half[1];
    if (ins && (i === 0 || !prevIn)) entries++;
    prevIn = ins;
  }
  return {
    success, error, timeout,
    movement_time_ms: tr.sel_t === null || tr.sel_t === undefined ? NaN : tr.sel_t,
    onset_ms: onset,
    distance_px: D,
    path_length_px: path,
    path_efficiency: eff,
    endpoint_error_px: Math.hypot(end[0] - tr.target[0], end[1] - tr.target[1]),
    endpoint_dx_px: (end[0] - tr.target[0]) * u[0] + (end[1] - tr.target[1]) * u[1],
    amplitude_px: (end[0] - tr.start[0]) * u[0] + (end[1] - tr.start[1]) * u[1],
    overshoot_px: Math.max(0, maxProj - (D + hAlong)),
    target_reentries: Math.max(entries - 1, 0),
  };
}

export interface ThroughputResult {
  tp_effective_bps: number;
  tp_nominal_bps: number;
  we_px: number;
  de_px: number;
  ide_bits: number;
  id_bits: number;
  mt_ms: number;
  error_rate: number;
  n: number;
  valid: boolean;
  flags: string[];
}

function mean(a: number[]): number {
  let s = 0;
  for (const v of a) s += v;
  return s / a.length;
}

function sd1(a: number[]): number {
  const m = mean(a);
  let s = 0;
  for (const v of a) s += (v - m) * (v - m);
  return Math.sqrt(s / (a.length - 1));
}

/** ISO 9241-411 effective throughput for ONE condition (same definition as Python). */
export function fittsThroughput(trials: Trial[], D: number, W: number, opts: { dwell?: boolean; minN?: number; maxErrorRate?: number } = {}): ThroughputResult {
  const minN = opts.minN ?? 10;
  const maxErr = opts.maxErrorRate ?? 0.5;
  const sel = trials.filter((t) => t.sel_item !== -2);
  const n = sel.length;
  const ID = Math.log2(D / W + 1);
  if (n < 2) return { tp_effective_bps: NaN, tp_nominal_bps: NaN, we_px: NaN, de_px: NaN, ide_bits: NaN, id_bits: ID, mt_ms: NaN, error_rate: NaN, n, valid: false, flags: ["fewer than 2 selections"] };
  const tm = sel.map((t) => trialMetrics(t));
  const sd = sd1(tm.map((m) => m.endpoint_dx_px));
  const We = WE_FACTOR * sd;
  const De = mean(tm.map((m) => m.amplitude_px));
  const IDe = We > 0 ? Math.log2(De / We + 1) : NaN;
  const mt = mean(tm.map((m) => m.movement_time_ms)) / 1000;
  const err = mean(tm.map((m) => (m.success ? 0 : 1)));
  const timeouts = trials.length - n;
  const flags: string[] = [];
  if (n < minN) flags.push(`n=${n} < ${minN} selections`);
  if (err > maxErr) flags.push(`error rate ${err.toFixed(2)} > ${maxErr}: speed-accuracy assumption violated`);
  if (timeouts) flags.push(`${timeouts} timeouts excluded (throughput is conditional on selection)`);
  if (opts.dwell) flags.push("dwell selection: MT includes a fixed dwell time");
  if (!(We > 0) || !Number.isFinite(IDe)) flags.push("degenerate endpoint spread");
  const valid = n >= minN && err <= maxErr && We > 0 && Number.isFinite(IDe);
  return {
    tp_effective_bps: mt > 0 ? IDe / mt : NaN,
    tp_nominal_bps: mt > 0 ? ID / mt : NaN,
    we_px: We, de_px: De, ide_bits: IDe, id_bits: ID, mt_ms: mt * 1000, error_rate: err, n, valid, flags,
  };
}

/** Achieved bitrate (Nuyujukian et al. 2015 style): log2(N-1) * max(Sc - Si, 0) / t. */
export function achievedBitrate(nCorrect: number, nIncorrect: number, nTargets: number, seconds: number): number {
  if (nTargets < 2 || seconds <= 0) return NaN;
  return (Math.log2(nTargets - 1) * Math.max(nCorrect - nIncorrect, 0)) / seconds;
}

/** Wolpaw bits per selection (assumptions: equiprobable targets, uniform errors). */
export function wolpawBits(p: number, n: number): number {
  if (n < 2) return NaN;
  p = Math.min(1, Math.max(0, p));
  if (p <= 1 / n) return 0;
  let b = Math.log2(n) + p * Math.log2(p);
  if (p < 1) b += (1 - p) * Math.log2((1 - p) / (n - 1));
  return b;
}
