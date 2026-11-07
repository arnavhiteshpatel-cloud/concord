// Four live traces in a dark well, like a bedside monitor. Raw sources: the first four
// channels' samples as received (each auto-scaled). Binned-feature sources: four channels'
// counts per bin over the last ~5 s, on a common scale.

import { useEffect, useRef } from "react";
import { NEURAL_WINDOW_BINS, type NeuralBuffer } from "../neuralBuffer";
import { WINDOW_S, type SignalBuffer } from "../signalBuffer";

export const TRACE_COUNT = 4;
const TRACE = "#4cc27a";
const LABEL = TRACE; // channel labels in the trace colour, at the left edge
const BASE = "rgba(255,255,255,0.07)";

/** The four most active channels of the window (ties: lower index first). */
export function mostActive(counts: number[][], channels: number, n = TRACE_COUNT): number[] {
  const totals = new Array<number>(channels).fill(0);
  for (const row of counts) for (let c = 0; c < channels; c++) totals[c]! += row[c] ?? 0;
  return totals
    .map((t, c) => [t, c] as const)
    .sort((a, b) => b[0] - a[0] || a[1] - b[1])
    .slice(0, Math.min(n, channels))
    .map(([, c]) => c)
    .sort((a, b) => a - b);
}

export function Traces({
  mode,
  signal,
  neural,
}: {
  mode: "raw" | "binned";
  signal: SignalBuffer;
  neural: NeuralBuffer;
}) {
  const canvas = useRef<HTMLCanvasElement>(null);
  // binned: channels picked once per session, after the first second of data
  const pick = useRef<{ session: string; channels: number[]; settled: boolean }>({
    session: "",
    channels: [],
    settled: false,
  });

  useEffect(() => {
    let raf = 0;
    const draw = () => {
      raf = requestAnimationFrame(draw);
      const c = canvas.current;
      if (!c) return;
      const dpr = window.devicePixelRatio || 1;
      const w = c.clientWidth;
      const h = c.clientHeight;
      if (c.width !== Math.round(w * dpr) || c.height !== Math.round(h * dpr)) {
        c.width = Math.round(w * dpr);
        c.height = Math.round(h * dpr);
      }
      const ctx = c.getContext("2d");
      if (!ctx) return;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.clearRect(0, 0, w, h);
      const lane = h / TRACE_COUNT;
      ctx.font = "12px -apple-system, BlinkMacSystemFont, 'Segoe UI', system-ui, sans-serif";
      ctx.lineJoin = "round";
      const labelX = 10;
      const left = 64;
      const plotW = w - left - 10;

      const baseline = (k: number) => {
        ctx.strokeStyle = BASE;
        ctx.lineWidth = 1;
        ctx.beginPath();
        ctx.moveTo(left, lane * k + lane / 2);
        ctx.lineTo(left + plotW, lane * k + lane / 2);
        ctx.stroke();
      };

      if (mode === "raw") {
        const n = Math.min(TRACE_COUNT, signal.channels.length);
        const cap = signal.capacity;
        for (let k = 0; k < n; k++) {
          baseline(k);
          const data = signal.ordered(k);
          let peak = 1e-9;
          for (const v of data) peak = Math.max(peak, Math.abs(v));
          const mid = lane * k + lane / 2;
          const scale = (lane * 0.42) / peak;
          ctx.strokeStyle = TRACE;
          ctx.lineWidth = 1.25;
          ctx.beginPath();
          const offset = cap - data.length; // newest sample at the right edge
          const step = Math.max(1, Math.floor(data.length / (plotW * 1.5)));
          for (let i = 0; i < data.length; i += step) {
            const x = left + ((offset + i) / cap) * plotW;
            const y = mid - data[i]! * scale;
            if (i === 0) ctx.moveTo(x, y);
            else ctx.lineTo(x, y);
          }
          ctx.stroke();
          ctx.fillStyle = LABEL;
          ctx.fillText(`Ch ${k + 1}`, labelX, mid + 4);
        }
        return;
      }

      const nb = neural;
      const p = pick.current;
      if (p.session !== nb.session) pick.current = { session: nb.session, channels: [], settled: false };
      const cur = pick.current;
      if (!cur.settled && nb.channelCount > 0) {
        cur.channels = mostActive(nb.counts, nb.channelCount);
        if (nb.counts.length >= 50) cur.settled = true;
      }
      const chans = cur.channels;
      let peak = 1;
      for (const row of nb.counts) for (const ch of chans) peak = Math.max(peak, row[ch] ?? 0);
      const offset = NEURAL_WINDOW_BINS - nb.counts.length;
      chans.forEach((ch, k) => {
        baseline(k);
        const bottom = lane * k + lane * 0.85;
        const scale = (lane * 0.7) / peak;
        ctx.strokeStyle = TRACE;
        ctx.lineWidth = 1.25;
        ctx.beginPath();
        nb.counts.forEach((row, i) => {
          const x = left + ((offset + i + 0.5) / NEURAL_WINDOW_BINS) * plotW;
          const y = bottom - (row[ch] ?? 0) * scale;
          if (i === 0) ctx.moveTo(x, y);
          else ctx.lineTo(x, y);
        });
        ctx.stroke();
        ctx.fillStyle = LABEL;
        ctx.fillText(`Ch ${ch + 1}`, labelX, lane * k + lane / 2 + 4);
      });
    };
    draw();
    return () => cancelAnimationFrame(raf);
  }, [mode, signal, neural]);

  return (
    <div className="well">
      <canvas ref={canvas} className="traces" data-testid="traces" aria-label="Live traces of four channels" role="img" />
    </div>
  );
}

export const traceWindowS = (mode: "raw" | "binned", binMs: number): number =>
  mode === "raw" ? WINDOW_S : (NEURAL_WINDOW_BINS * binMs) / 1000;
