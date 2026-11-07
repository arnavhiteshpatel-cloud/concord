// Ring buffers for offline neural data: binned counts, recorded behavior (ground truth),
// and decoded kinematics — kept strictly separate, aligned by bin/sample index.

import type {
  BehaviorSamplePayload,
  FeaturesBinnedPayload,
  KinematicIntentPayload,
} from "../sdk";

export const NEURAL_WINDOW_BINS = 250; // 5 s at 20 ms bins

export class NeuralBuffer {
  session = "";
  channelCount = 0;
  binMs = 0;
  feature = "";
  dims: string[] = [];
  behaviorUnit = "";
  modelId: string | null = null;
  /** counts[k] = per-channel counts for bin bins[k] */
  bins: number[] = [];
  counts: number[][] = [];
  behavior = new Map<number, { values: number[]; valid: boolean }>();
  decoded = new Map<number, number[]>();
  lastBin = -1;

  private reset(session: string) {
    this.session = session;
    this.bins = [];
    this.counts = [];
    this.behavior.clear();
    this.decoded.clear();
    this.lastBin = -1;
    this.modelId = null;
  }

  private check(session: string) {
    if (session !== this.session) this.reset(session);
  }

  pushFeatures(session: string, p: FeaturesBinnedPayload): void {
    this.check(session);
    if (p.bin_index < this.lastBin) {
      // replay looped: start a fresh window rather than mixing passes
      this.reset(session);
    }
    this.channelCount = p.channel_count;
    this.binMs = p.bin_ms;
    this.feature = p.feature;
    this.bins.push(p.bin_index);
    this.counts.push(p.counts);
    this.lastBin = p.bin_index;
    const drop = this.bins.length - NEURAL_WINDOW_BINS;
    if (drop > 0) {
      for (const b of this.bins.slice(0, drop)) {
        this.behavior.delete(b);
        this.decoded.delete(b);
      }
      this.bins.splice(0, drop);
      this.counts.splice(0, drop);
    }
  }

  pushBehavior(session: string, p: BehaviorSamplePayload): void {
    this.check(session);
    this.dims = p.dims;
    this.behaviorUnit = p.unit;
    this.behavior.set(p.sample_index, { values: p.values, valid: p.valid });
  }

  /** Decoded output for the most recent bin (emitted right after its features event). */
  pushDecoded(session: string, p: KinematicIntentPayload, modelId: string | null): void {
    this.check(session);
    this.modelId = modelId;
    if (this.lastBin >= 0) this.decoded.set(this.lastBin, p.values);
  }
}
