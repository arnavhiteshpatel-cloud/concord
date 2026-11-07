import { useEffect, useRef, useState } from "react";
import { NEURAL_WINDOW_BINS, type NeuralBuffer } from "../neuralBuffer";
import { Panel } from "./ui";

const RECORDED = "#e3b341"; // behavioral ground truth
const DECODED = "#b392f0"; // decoded_intent (offline model)

function sizeCanvas(c: HTMLCanvasElement): CanvasRenderingContext2D | null {
  const dpr = window.devicePixelRatio || 1;
  const w = c.clientWidth;
  const h = c.clientHeight;
  if (c.width !== w * dpr || c.height !== h * dpr) {
    c.width = w * dpr;
    c.height = h * dpr;
  }
  const ctx = c.getContext("2d");
  ctx?.setTransform(dpr, 0, 0, dpr, 0, 0);
  return ctx;
}

/**
 * "offline": a verified dataset file replayed by BrainOS (features + recorded behavior + an
 * offline-evaluated decoder). "pipeline": features computed by the BrainOS pipeline from the
 * connected raw source, plus that source's behavior stream and the loaded decoder, if any.
 */
export function NeuralView({ neural, source }: { neural: NeuralBuffer; source: "offline" | "pipeline" }) {
  const raster = useRef<HTMLCanvasElement>(null);
  const traces = useRef<HTMLCanvasElement>(null);
  const [dim, setDim] = useState(0);
  const dimRef = useRef(dim);
  dimRef.current = dim;

  useEffect(() => {
    let raf = 0;
    const draw = () => {
      raf = requestAnimationFrame(draw);
      const n = neural;
      // --- raster: x = time (bins), y = channel, brightness = count
      const rc = raster.current;
      const ctx = rc && sizeCanvas(rc);
      if (rc && ctx) {
        const w = rc.clientWidth;
        const h = rc.clientHeight;
        ctx.fillStyle = "#0b0f14";
        ctx.fillRect(0, 0, w, h);
        const ch = n.channelCount;
        if (ch > 0 && n.counts.length) {
          const cw = w / NEURAL_WINDOW_BINS;
          const rh = h / ch;
          const offset = NEURAL_WINDOW_BINS - n.counts.length;
          for (let k = 0; k < n.counts.length; k++) {
            const row = n.counts[k]!;
            const x = (offset + k) * cw;
            for (let c = 0; c < ch; c++) {
              const v = row[c]!;
              if (v === 0) continue;
              const a = Math.min(1, v / 4);
              ctx.fillStyle = `rgba(90, 209, 230, ${0.25 + 0.75 * a})`;
              ctx.fillRect(x, c * rh, Math.max(1, cw), Math.max(1, rh));
            }
          }
        }
      }
      // --- traces: recorded behavior vs decoded, one dimension
      const tc = traces.current;
      const tx = tc && sizeCanvas(tc);
      if (tc && tx) {
        const w = tc.clientWidth;
        const h = tc.clientHeight;
        tx.clearRect(0, 0, w, h);
        tx.strokeStyle = "rgba(139,155,176,0.15)";
        tx.beginPath();
        tx.moveTo(0, h / 2);
        tx.lineTo(w, h / 2);
        tx.stroke();
        const d = dimRef.current;
        const bins = n.bins;
        const rec = bins.map((b) => n.behavior.get(b));
        const dec = bins.map((b) => n.decoded.get(b));
        let peak = 1e-9;
        for (const r of rec) if (r) peak = Math.max(peak, Math.abs(r.values[d] ?? 0));
        for (const v of dec) if (v) peak = Math.max(peak, Math.abs(v[d] ?? 0));
        const offset = NEURAL_WINDOW_BINS - bins.length;
        const xOf = (k: number) => ((offset + k) / NEURAL_WINDOW_BINS) * w;
        const yOf = (v: number) => h / 2 - (v / peak) * (h * 0.42);
        const line = (vals: (number | undefined)[], color: string, dash: number[]) => {
          tx.strokeStyle = color;
          tx.lineWidth = 1.6;
          tx.setLineDash(dash);
          tx.beginPath();
          let started = false;
          vals.forEach((v, k) => {
            if (v === undefined) {
              started = false;
              return;
            }
            if (!started) tx.moveTo(xOf(k), yOf(v));
            else tx.lineTo(xOf(k), yOf(v));
            started = true;
          });
          tx.stroke();
          tx.setLineDash([]);
        };
        line(rec.map((r) => (r && r.valid ? r.values[d] : undefined)), RECORDED, []);
        line(dec.map((v) => v?.[d]), DECODED, [5, 3]);
      }
    };
    draw();
    return () => cancelAnimationFrame(raf);
  }, [neural]);

  const hasDecoded = neural.decoded.size > 0;
  return (
    <Panel
      title={source === "offline" ? "Recorded neural activity · offline replay" : "Pipeline features · processed_feature"}
      className="neural-panel"
      testId={source === "offline" ? "neural-view" : "pipeline-neural-view"}
      right={
        <span className="muted">
          {neural.channelCount} ch · {neural.binMs} ms bins · {neural.feature.replace(/_/g, " ")} · last{" "}
          {neural.binMs ? `${((NEURAL_WINDOW_BINS * neural.binMs) / 1000).toFixed(0)} s` : "—"}
        </span>
      }
    >
      <canvas ref={raster} className="raster-canvas" data-testid="raster-canvas" />
      <div className="trace-head">
        <label className="small muted">
          velocity dimension{" "}
          <select value={dim} onChange={(e) => setDim(Number(e.target.value))} data-testid="dim-select">
            {(neural.dims.length ? neural.dims : ["—"]).map((d, i) => (
              <option key={d} value={i}>
                {d}
              </option>
            ))}
          </select>
        </label>
        <span className="legend">
          {neural.behavior.size > 0 && (
            <span style={{ color: RECORDED }}>━ recorded (behavioral ground truth, valid samples)</span>
          )}
          {hasDecoded && <span style={{ color: DECODED }}>┅ decoded_intent ({neural.modelId})</span>}
        </span>
      </div>
      <canvas ref={traces} className="trace-canvas" data-testid="trace-canvas" />
      {source === "offline" ? (
        <p className="muted small">
          Real spike counts from a human intracortical recording, replayed from a file. Kinematics are the dataset's
          recorded (cued) velocity in arbitrary units.{" "}
          {hasDecoded
            ? "The dashed line is an offline baseline decoder on a held-out block — not real-time control."
            : "No decoder is attached to this file."}
        </p>
      ) : (
        <p className="muted small">
          Binned features computed by the BrainOS pipeline from the connected source (see the data badge for what that
          source is). Solid: the source's behavior stream, if one is attached.{" "}
          {hasDecoded
            ? "Dashed: decoded_intent from the loaded model — calibrated offline, not validated for closed-loop control."
            : "No decoder loaded."}
        </p>
      )}
    </Panel>
  );
}
