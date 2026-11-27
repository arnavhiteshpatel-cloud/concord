// TypeScript port of neurometric.simulator.decoder.DegradedChannel (single stream, B = 1).
//
// SIMULATED input degradation: an experimental model of what a degraded control channel does to
// an intended signal. It is NOT a model of neural physiology or of any specific BCI.
//
// The deterministic parts (gain, bias, asymmetry, smoothing, quantisation, direction bins,
// update rate, latency, gain decay, dims, selection latency) reproduce Python to floating-point
// precision (golden tests). The random parts use a different PRNG and are checked by statistics.
// Python's round() and numpy's np.round() round half to EVEN; roundHalfEven mirrors that.

import { Rng } from "./rng";

export type ControlMode = "velocity" | "position";

export interface DegradationConfig {
  gain: number;
  bias_deg: number;
  asymmetry: number;
  white_noise: number;
  correlated_noise: number;
  correlated_tau_ms: number;
  drift: number;
  drift_rate_per_min: number;
  smoothing_tau_ms: number;
  quantization: number;
  direction_bins: number;
  update_hz: number;
  latency_ms: number;
  latency_jitter_ms: number;
  dropout_enter_per_s: number;
  dropout_mean_ms: number;
  gain_decay_per_min: number;
  noise_growth_per_min: number;
  loss_of_control_per_min: number;
  loss_of_control_mean_ms: number;
  recovery_ms: number;
  select_miss_prob: number;
  select_latency_ms: number;
  false_select_per_min: number;
  dims: [boolean, boolean];
}

export const IDENTITY: DegradationConfig = {
  gain: 1.0, bias_deg: 0.0, asymmetry: 0.0, white_noise: 0.0, correlated_noise: 0.0,
  correlated_tau_ms: 300.0, drift: 0.0, drift_rate_per_min: 0.0, smoothing_tau_ms: 0.0,
  quantization: 0.0, direction_bins: 0, update_hz: 0.0, latency_ms: 0.0, latency_jitter_ms: 0.0,
  dropout_enter_per_s: 0.0, dropout_mean_ms: 0.0, gain_decay_per_min: 0.0, noise_growth_per_min: 0.0,
  loss_of_control_per_min: 0.0, loss_of_control_mean_ms: 0.0, recovery_ms: 0.0,
  select_miss_prob: 0.0, select_latency_ms: 0.0, false_select_per_min: 0.0, dims: [true, true],
};

export function config(over: Partial<DegradationConfig> = {}): DegradationConfig {
  return { ...IDENTITY, ...over };
}

/** Same values as neurometric.simulator.decoder.PROFILES (illustrative stress profiles). */
export const PROFILES: Record<string, DegradationConfig> = {
  identity: config(),
  bci_good: config({ white_noise: 30, correlated_noise: 40, correlated_tau_ms: 400, smoothing_tau_ms: 60, latency_ms: 60, update_hz: 50, false_select_per_min: 0.3, select_miss_prob: 0.05, select_latency_ms: 60 }),
  bci_moderate: config({ white_noise: 60, correlated_noise: 80, correlated_tau_ms: 500, smoothing_tau_ms: 80, latency_ms: 100, update_hz: 50, bias_deg: 10, gain: 0.85, false_select_per_min: 1.0, select_miss_prob: 0.1, select_latency_ms: 100, dropout_enter_per_s: 0.02, dropout_mean_ms: 400 }),
  bci_poor: config({ white_noise: 100, correlated_noise: 130, correlated_tau_ms: 600, smoothing_tau_ms: 100, latency_ms: 150, update_hz: 20, bias_deg: 20, gain: 0.7, drift: 20, false_select_per_min: 3.0, select_miss_prob: 0.2, select_latency_ms: 150, dropout_enter_per_s: 0.05, dropout_mean_ms: 800, loss_of_control_per_min: 0.5, loss_of_control_mean_ms: 1500, recovery_ms: 1000 }),
};

/** numpy.round / Python round: round half to even. */
export function roundHalfEven(x: number): number {
  if (!Number.isFinite(x)) return x;
  const f = Math.floor(x);
  const d = x - f;
  const r = d > 0.5 ? f + 1 : d < 0.5 ? f : f % 2 === 0 ? f : f + 1;
  return r === 0 && x < 0 ? -0 : r; // numpy keeps the sign of zero
}

type V2 = [number, number];

export class DegradedChannel {
  readonly cfg: DegradationConfig;
  readonly dt: number;
  readonly mode: ControlMode;
  private rng: Rng;
  tMin: number;
  private ar: V2 = [0, 0];
  private rho: number;
  private smooth: V2 = [0, 0];
  private smoothInit = false;
  private alpha: number;
  private R: [number, number, number, number];
  private driftDir: V2;
  private holdEvery: number;
  private tick = 0;
  private held: V2 = [0, 0];
  private latTicks: number;
  private bufLen: number;
  private buf: V2[];
  private bufFilled = 0;
  private lastRead = -1;
  private globalTick = 0;
  inDropout = false;
  inLoc = false;
  private recoverLeft = 0;
  private lastOut: V2 = [0, 0];
  private posTrack: V2 | null = null;
  private prevIntent: V2 | null = null;
  private prevSelIntent = false;
  private selLat: number;
  private selBuf: boolean[];
  private dims: V2;
  dropoutTicks = 0;
  locTicks = 0;
  falseSelects = 0;
  missedSelects = 0;

  constructor(cfg: DegradationConfig, dtMs: number, mode: ControlMode, rng: Rng = new Rng(1), sessionMinutes = 0) {
    const c = (this.cfg = cfg);
    this.dt = dtMs;
    this.mode = mode;
    this.rng = rng;
    this.tMin = sessionMinutes;
    this.rho = c.correlated_tau_ms > 0 ? Math.exp(-dtMs / c.correlated_tau_ms) : 0;
    this.alpha = c.smoothing_tau_ms > 0 ? Math.exp(-dtMs / c.smoothing_tau_ms) : 0;
    const th = (c.bias_deg * Math.PI) / 180;
    this.R = [Math.cos(th), -Math.sin(th), Math.sin(th), Math.cos(th)];
    const ang = rng.uniform(0, 2 * Math.PI);
    this.driftDir = [Math.cos(ang), Math.sin(ang)];
    this.holdEvery = c.update_hz > 0 ? Math.max(1, roundHalfEven(1000 / c.update_hz / dtMs)) : 1;
    this.latTicks = roundHalfEven(c.latency_ms / dtMs);
    this.bufLen = this.latTicks + Math.ceil((Math.max(c.latency_jitter_ms, 0) * 8) / dtMs) + 2;
    this.buf = Array.from({ length: this.bufLen }, () => [0, 0] as V2);
    this.selLat = roundHalfEven(c.select_latency_ms / dtMs);
    this.selBuf = new Array(this.selLat + 1).fill(false);
    this.dims = [c.dims[0] ? 1 : 0, c.dims[1] ? 1 : 0];
  }

  private hazard(perS: number): number {
    return perS > 0 ? 1 - Math.exp((-perS * this.dt) / 1000) : 0;
  }

  /**
   * Advance one tick. intent = velocity (px/s) or position (px); selectIntent = the user is
   * trying to select (level). Returns the degraded output and a selection edge.
   */
  step(intentIn: V2, selectIntent: boolean): { out: V2; select: boolean } {
    const c = this.cfg;
    const rng = this.rng;
    const intent: V2 = [intentIn[0] * this.dims[0], intentIn[1] * this.dims[1]];
    const tmin = this.tMin;
    // --- episodes
    if (c.dropout_enter_per_s > 0 && c.dropout_mean_ms > 0) {
      const enter = !this.inDropout && rng.random() < this.hazard(c.dropout_enter_per_s);
      const leave = this.inDropout && rng.random() < 1 - Math.exp(-this.dt / c.dropout_mean_ms);
      this.inDropout = (this.inDropout || enter) && !leave;
    }
    if (c.loss_of_control_per_min > 0 && c.loss_of_control_mean_ms > 0) {
      const enter = !this.inLoc && rng.random() < this.hazard(c.loss_of_control_per_min / 60);
      const leave = this.inLoc && rng.random() < 1 - Math.exp(-this.dt / c.loss_of_control_mean_ms);
      if (leave) this.recoverLeft = c.recovery_ms;
      this.inLoc = (this.inLoc || enter) && !leave;
    }
    let rec = 1;
    if (c.recovery_ms > 0) {
      rec = this.recoverLeft > 0 ? 1 - this.recoverLeft / c.recovery_ms : 1;
      this.recoverLeft = Math.max(0, this.recoverLeft - this.dt);
    }
    // --- deterministic transform
    const g = c.gain * Math.max(0, 1 - c.gain_decay_per_min * tmin);
    let v: V2;
    if (this.mode === "velocity") {
      v = [intent[0], intent[1]];
      if (c.asymmetry) v[0] = v[0] > 0 ? v[0] * (1 + c.asymmetry) : v[0] * (1 - c.asymmetry);
      if (c.bias_deg) v = this.rotate(v);
      const k = g * rec;
      v = [v[0] * k, v[1] * k];
      if (this.inLoc) v = [0, 0];
    } else {
      if (this.posTrack === null) {
        this.posTrack = [intent[0], intent[1]];
        this.prevIntent = [intent[0], intent[1]];
        this.lastOut = [intent[0], intent[1]];
      }
      let d: V2 = [intent[0] - this.prevIntent![0], intent[1] - this.prevIntent![1]];
      if (c.asymmetry) d[0] = d[0] > 0 ? d[0] * (1 + c.asymmetry) : d[0] * (1 - c.asymmetry);
      if (c.bias_deg) d = this.rotate(d);
      const k = g * rec;
      d = [d[0] * k, d[1] * k];
      if (this.inLoc) d = [0, 0];
      this.posTrack = [this.posTrack[0] + d[0], this.posTrack[1] + d[1]];
      this.prevIntent = [intent[0], intent[1]];
      v = [this.posTrack[0], this.posTrack[1]];
    }
    // --- noise
    const growth = 1 + c.noise_growth_per_min * tmin;
    if (c.white_noise) {
      const s = c.white_noise * growth;
      v = [v[0] + rng.normal() * s, v[1] + rng.normal() * s];
    }
    if (c.correlated_noise) {
      const s = Math.sqrt(1 - this.rho ** 2) * c.correlated_noise * growth;
      this.ar = [this.rho * this.ar[0] + rng.normal() * s, this.rho * this.ar[1] + rng.normal() * s];
      v = [v[0] + this.ar[0], v[1] + this.ar[1]];
    }
    if (c.drift || c.drift_rate_per_min) {
      const m = c.drift + c.drift_rate_per_min * tmin;
      v = [v[0] + this.driftDir[0] * m, v[1] + this.driftDir[1] * m];
    }
    v = [v[0] * this.dims[0], v[1] * this.dims[1]];
    // --- smoothing
    if (this.alpha > 0) {
      if (!this.smoothInit) {
        this.smooth = [v[0], v[1]];
        this.smoothInit = true;
      }
      const a = this.alpha;
      this.smooth = [a * this.smooth[0] + (1 - a) * v[0], a * this.smooth[1] + (1 - a) * v[1]];
      v = [this.smooth[0], this.smooth[1]];
    }
    // --- quantisation
    if (c.direction_bins > 0) {
      const mag = Math.hypot(v[0], v[1]);
      let ang = Math.atan2(v[1], v[0]);
      const st = (2 * Math.PI) / c.direction_bins;
      ang = roundHalfEven(ang / st) * st;
      v = [mag * Math.cos(ang), mag * Math.sin(ang)];
    }
    if (c.quantization > 0) {
      const q = c.quantization;
      v = [roundHalfEven(v[0] / q) * q, roundHalfEven(v[1] / q) * q];
    }
    // --- update rate (sample and hold)
    if (this.holdEvery > 1) {
      if (this.tick % this.holdEvery === 0) this.held = [v[0], v[1]];
      v = [this.held[0], this.held[1]];
    }
    // --- latency
    if (this.bufLen > 2 || this.latTicks) {
      const pos = this.globalTick % this.bufLen;
      this.buf[pos] = [v[0], v[1]];
      this.bufFilled = Math.min(this.bufFilled + 1, this.bufLen);
      let delay = this.latTicks;
      if (c.latency_jitter_ms > 0) delay += roundHalfEven(rng.exponential(c.latency_jitter_ms) / this.dt);
      delay = Math.min(delay, this.bufFilled - 1);
      let read = this.globalTick - delay;
      read = Math.max(read, this.lastRead); // outputs never go back in time
      this.lastRead = read;
      if (this.globalTick - this.latTicks < 0) {
        v = this.mode === "velocity" ? [0, 0] : [this.lastOut[0], this.lastOut[1]];
        if (this.mode === "position" && this.globalTick === 0) v = [intent[0], intent[1]];
      } else {
        const b = this.buf[read % this.bufLen];
        v = [b[0], b[1]];
      }
    }
    // --- dropout
    if (this.inDropout) v = this.mode === "velocity" ? [0, 0] : [this.lastOut[0], this.lastOut[1]];
    // --- selection channel
    const edge = selectIntent && !this.prevSelIntent;
    this.prevSelIntent = selectIntent;
    let produced = edge;
    if (c.select_miss_prob > 0) {
      const miss = produced && rng.random() < c.select_miss_prob;
      if (miss) {
        this.missedSelects++;
        produced = false;
      }
    }
    const blocked = this.inDropout || this.inLoc;
    if (produced && blocked) this.missedSelects++;
    produced = produced && !blocked;
    if (c.false_select_per_min > 0) {
      const fa = rng.random() < this.hazard(c.false_select_per_min / 60) && !selectIntent;
      if (fa) {
        this.falseSelects++;
        produced = true;
      }
    }
    let selOut = produced;
    if (this.selLat > 0) {
      this.selBuf.shift();
      this.selBuf.push(produced);
      selOut = this.selBuf[0];
    }
    // --- bookkeeping
    if (this.inDropout) this.dropoutTicks++;
    if (this.inLoc) this.locTicks++;
    this.lastOut = [v[0], v[1]];
    this.tick++;
    this.globalTick++;
    this.tMin += this.dt / 60000;
    return { out: v, select: selOut };
  }

  private rotate(v: V2): V2 {
    const R = this.R;
    return [v[0] * R[0] + v[1] * R[1], v[0] * R[2] + v[1] * R[3]];
  }
}
