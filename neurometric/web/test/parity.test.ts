// Cross-language parity: the TypeScript ports must reproduce Python golden fixtures
// (web/scripts/make_golden.py) within 1e-9 relative, or exactly for integers / booleans.
// Randomised parts of the degradation model cannot match bit for bit (different PRNGs), so their
// statistics are compared instead.

import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import { DegradedChannel, PROFILES, config, roundHalfEven, type DegradationConfig } from "../src/demo/degraded";
import { Rng } from "../src/demo/rng";
import { achievedBitrate, fittsThroughput, trialMetrics, wolpawBits, type Trial } from "../src/metrics/pointing";
import { applyStream, msd, textEntryMetrics } from "../src/metrics/text";

const here = dirname(fileURLToPath(import.meta.url));
const load = (f: string) => JSON.parse(readFileSync(join(here, "golden", f), "utf8"));
const REL = 1e-9;

let compared = 0;
function close(actual: number, expected: number | null, label: string, abs = 1e-9): void {
  compared++;
  if (expected === null) {
    if (!Number.isNaN(actual) && Number.isFinite(actual)) throw new Error(`${label}: expected NaN/None, got ${actual}`);
    return;
  }
  const tol = Math.max(abs, REL * Math.abs(expected));
  if (!(Math.abs(actual - expected) <= tol)) throw new Error(`${label}: expected ${expected}, got ${actual} (|diff| ${Math.abs(actual - expected)} > ${tol})`);
}

describe("roundHalfEven matches numpy.round", () => {
  it("ties go to even", () => {
    expect([0.5, 1.5, 2.5, -0.5, -1.5, -2.5, 2.4999, 2.5001].map(roundHalfEven)).toEqual([0, 2, 2, -0, -2, -2, 2, 3]);
  });
});

describe("DegradedChannel deterministic parity (Python golden)", () => {
  const g = load("degraded_channel.json");
  for (const c of g.cases) {
    it(c.name, () => {
      const kw = { ...c.config };
      const cfg: DegradationConfig = config(kw);
      const ch = new DegradedChannel(cfg, c.dt_ms, c.mode, new Rng(0), c.session_minutes);
      const intents: [number, number][] = g.intents[c.mode];
      for (let k = 0; k < intents.length; k++) {
        const { out, select } = ch.step(intents[k], g.select_intent[k]);
        close(out[0], c.output[k][0], `${c.name} x[${k}]`);
        close(out[1], c.output[k][1], `${c.name} y[${k}]`);
        if (select !== c.select_out[k]) throw new Error(`${c.name} select[${k}] expected ${c.select_out[k]}`);
      }
    });
  }
});

describe("Pointing metrics parity (Python golden)", () => {
  const g = load("metrics.json");
  for (const set of g.pointing) {
    it(`trial metrics + Fitts throughput: ${set.name}`, () => {
      const trials: Trial[] = set.trials;
      trials.forEach((tr, i) => {
        const m = trialMetrics(tr);
        for (const k of ["movement_time_ms", "onset_ms", "distance_px", "path_length_px", "path_efficiency", "endpoint_error_px", "endpoint_dx_px", "amplitude_px", "overshoot_px"] as const) {
          close(m[k], set.expected.trial[k][i], `${set.name}[${i}].${k}`);
        }
        expect(m.target_reentries).toBe(set.expected.trial.target_reentries[i]);
        expect(m.success).toBe(set.expected.trial.success[i]);
        expect(m.error).toBe(set.expected.trial.error[i]);
        expect(m.timeout).toBe(set.expected.trial.timeout[i]);
      });
      const r = fittsThroughput(trials, set.D, set.W);
      const e = set.expected.fitts;
      for (const k of ["tp_effective_bps", "tp_nominal_bps", "we_px", "de_px", "ide_bits", "id_bits", "mt_ms", "error_rate"] as const) close(r[k], e[k], `${set.name}.fitts.${k}`);
      expect(r.n).toBe(e.n);
      expect(r.valid).toBe(e.valid);
    });
  }
  it("achieved bitrate", () => {
    for (const c of g.achieved_bitrate) close(achievedBitrate(c.n_correct, c.n_incorrect, c.n_targets, c.seconds), c.value, `bitrate ${JSON.stringify(c)}`);
  });
  it("Wolpaw bits", () => {
    for (const c of g.wolpaw_bits) close(wolpawBits(c.p, c.n), c.bits, `wolpaw p=${c.p} n=${c.n}`);
  });
});

describe("Text metrics parity (Python golden)", () => {
  const g = load("metrics.json");
  it("MSD", () => {
    for (const c of g.msd) expect(msd(c.a, c.b)).toBe(c.d);
  });
  for (const c of g.text) {
    it(`text entry: ${JSON.stringify(c.presented)} (${c.seconds}s)`, () => {
      expect(applyStream(c.stream)).toBe(c.transcribed);
      const r = textEntryMetrics(c.presented, c.stream, c.seconds) as unknown as Record<string, number>;
      for (const [k, v] of Object.entries(c.expected as Record<string, number | null>)) {
        if (["presented_len", "transcribed_len", "keystrokes", "msd", "C", "INF", "IF", "F"].includes(k)) expect(r[k]).toBe(v);
        else close(r[k], v, `text.${k}`);
      }
    });
  }
});

// ------------------------------------------------------------------ randomised parts: statistics
function lag1(x: number[]): number {
  const m = x.reduce((a, b) => a + b, 0) / x.length;
  let num = 0;
  let den = 0;
  for (let i = 0; i < x.length; i++) {
    den += (x[i] - m) ** 2;
    if (i) num += (x[i] - m) * (x[i - 1] - m);
  }
  return num / den;
}
function sd(x: number[]): number {
  const m = x.reduce((a, b) => a + b, 0) / x.length;
  return Math.sqrt(x.reduce((a, b) => a + (b - m) ** 2, 0) / x.length);
}

describe("Randomised degradation: statistics match Python reference", () => {
  const ref = load("random_stats.json");
  const T = 80000;
  const zero: [number, number] = [0, 0];
  it("white noise SD and whiteness", () => {
    const ch = new DegradedChannel(config({ white_noise: 40 }), 10, "velocity", new Rng(11));
    const xs: number[] = [];
    for (let k = 0; k < T; k++) xs.push(ch.step(zero, false).out[0]);
    expect(Math.abs(sd(xs) - 40) / 40).toBeLessThan(0.02);
    expect(Math.abs(sd(xs) - ref.white_noise_40.sd) / 40).toBeLessThan(0.03);
    expect(Math.abs(lag1(xs))).toBeLessThan(0.02);
  });
  it("AR(1) correlated noise: SD and lag-1 autocorrelation = exp(-dt/tau)", () => {
    const ch = new DegradedChannel(config({ correlated_noise: 50, correlated_tau_ms: 300 }), 10, "velocity", new Rng(12));
    const xs: number[] = [];
    for (let k = 0; k < T * 2; k++) xs.push(ch.step(zero, false).out[0]);
    expect(Math.abs(sd(xs) - 50) / 50).toBeLessThan(0.08);
    expect(Math.abs(lag1(xs) - ref.ar1_50_tau300.rho_expected)).toBeLessThan(0.01);
    expect(Math.abs(lag1(xs) - ref.ar1_50_tau300.lag1)).toBeLessThan(0.01);
  });
  it("false activation rate", () => {
    const ch = new DegradedChannel(config({ false_select_per_min: 30 }), 10, "velocity", new Rng(13));
    let n = 0;
    for (let k = 0; k < T; k++) n += ch.step(zero, false).select ? 1 : 0;
    const perMin = n / ((T * 10) / 60000);
    expect(Math.abs(perMin - 30) / 30).toBeLessThan(0.1);
    expect(Math.abs(perMin - ref.false_select_30pm.per_min) / 30).toBeLessThan(0.12);
  });
  it("dropout occupancy fraction", () => {
    const ch = new DegradedChannel(config({ dropout_enter_per_s: 0.5, dropout_mean_ms: 400 }), 10, "velocity", new Rng(14));
    for (let k = 0; k < T * 2; k++) ch.step([100, 100], false);
    const frac = ch.dropoutTicks / (T * 2);
    expect(Math.abs(frac - ref["dropout_0.5ps_400ms"].fraction_expected)).toBeLessThan(0.025);
  });
  it("selection miss rate", () => {
    const ch = new DegradedChannel(config({ select_miss_prob: 0.25 }), 10, "velocity", new Rng(15));
    let produced = 0;
    let intended = 0;
    for (let k = 0; k < T; k++) {
      const s = k % 10 === 0;
      if (s) intended++;
      produced += ch.step(zero, s).select ? 1 : 0;
    }
    expect(Math.abs(1 - produced / intended - 0.25)).toBeLessThan(0.03);
    expect(Math.abs(1 - produced / intended - ref["miss_0.25"].miss_rate)).toBeLessThan(0.04);
  });
  it("latency + jitter: mean delay and monotonic output", () => {
    const ch = new DegradedChannel(config({ latency_ms: 50, latency_jitter_ms: 30 }), 10, "velocity", new Rng(16));
    const outs: number[] = [];
    let delaySum = 0;
    for (let k = 0; k < 20000; k++) {
      const o = ch.step([k, k], false).out[0];
      outs.push(o);
      if (k >= 200) delaySum += k - o;
    }
    const meanDelayMs = (delaySum / (20000 - 200)) * 10;
    expect(Math.abs(meanDelayMs - ref.latency_50_jitter_30.mean_delay_ms)).toBeLessThan(5);
    for (let k = 201; k < outs.length; k++) expect(outs[k]).toBeGreaterThanOrEqual(outs[k - 1]);
  });
  it("profiles mirror Python PROFILES (spot check)", () => {
    expect(PROFILES.bci_poor.loss_of_control_per_min).toBe(0.5);
    expect(PROFILES.bci_moderate.bias_deg).toBe(10);
    expect(PROFILES.bci_good.update_hz).toBe(50);
  });
});

describe("parity bookkeeping", () => {
  it("compared a substantial number of values", () => {
    expect(compared).toBeGreaterThan(1000);
  });
});
