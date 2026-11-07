// Fixed-size per-channel ring buffers for the signal view.

import type { RecordingFramePayload } from "../sdk";

export const WINDOW_S = 2;
export const MAX_CHANNELS_SHOWN = 8;

export class SignalBuffer {
  sampleRate = 0;
  channelCount = 0;
  key = "";
  channels: Float32Array[] = [];
  written = 0; // total samples written per channel

  get capacity(): number {
    return this.channels[0]?.length ?? 0;
  }

  reset(key: string, sampleRate: number, channelCount: number): void {
    this.key = key;
    this.sampleRate = sampleRate;
    this.channelCount = channelCount;
    const cap = Math.max(1, Math.round(sampleRate * WINDOW_S));
    const shown = Math.min(channelCount, MAX_CHANNELS_SHOWN);
    this.channels = Array.from({ length: shown }, () => new Float32Array(cap));
    this.written = 0;
  }

  push(sessionKey: string, p: RecordingFramePayload): void {
    const key = `${sessionKey}:${p.sample_rate_hz}:${p.channel_count}`;
    if (key !== this.key) this.reset(key, p.sample_rate_hz, p.channel_count);
    const cap = this.capacity;
    const n = p.samples[0]?.length ?? 0;
    for (let c = 0; c < this.channels.length; c++) {
      const buf = this.channels[c]!;
      const src = p.samples[c]!;
      for (let i = 0; i < n; i++) buf[(this.written + i) % cap] = src[i]!;
    }
    this.written += n;
  }

  /** Samples of channel `c` in chronological order (oldest first). */
  ordered(c: number): Float32Array {
    const buf = this.channels[c];
    if (!buf) return new Float32Array(0);
    const cap = buf.length;
    const len = Math.min(this.written, cap);
    const out = new Float32Array(len);
    const start = this.written - len;
    for (let i = 0; i < len; i++) out[i] = buf[(start + i) % cap]!;
    return out;
  }
}
