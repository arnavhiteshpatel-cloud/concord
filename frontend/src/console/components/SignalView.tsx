import { useEffect, useRef } from "react";
import type { RuntimeSnapshot, TelemetryMetric } from "../../sdk";
import { isLiveSource } from "../api";
import { MAX_CHANNELS_SHOWN, WINDOW_S, type SignalBuffer } from "../signalBuffer";
import { Panel } from "./ui";

const COLORS = ["#6cb6ff", "#5ad1e6", "#3fcf8e", "#b392f0", "#e3b341", "#f47067", "#e0a458", "#8b9bb0"];

export function SignalView({ signal, runtime }: { signal: SignalBuffer; runtime: RuntimeSnapshot | null }) {
  const canvas = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    let raf = 0;
    const draw = () => {
      raf = requestAnimationFrame(draw);
      const c = canvas.current;
      if (!c) return;
      const dpr = window.devicePixelRatio || 1;
      const w = c.clientWidth;
      const h = c.clientHeight;
      if (c.width !== w * dpr || c.height !== h * dpr) {
        c.width = w * dpr;
        c.height = h * dpr;
      }
      const ctx = c.getContext("2d");
      if (!ctx) return;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.clearRect(0, 0, w, h);
      ctx.strokeStyle = "rgba(139,155,176,0.08)";
      ctx.lineWidth = 1;
      for (let i = 1; i < 4; i++) {
        const x = (w * i) / 4;
        ctx.beginPath();
        ctx.moveTo(x, 0);
        ctx.lineTo(x, h);
        ctx.stroke();
      }
      const n = signal.channels.length;
      if (n === 0) return;
      const cap = signal.capacity;
      const lane = h / n;
      for (let ch = 0; ch < n; ch++) {
        const data = signal.ordered(ch);
        let peak = 1;
        for (const v of data) peak = Math.max(peak, Math.abs(v));
        const mid = lane * ch + lane / 2;
        const scale = (lane * 0.45) / peak;
        ctx.strokeStyle = COLORS[ch % COLORS.length]!;
        ctx.lineWidth = 1;
        ctx.beginPath();
        const offset = cap - data.length; // right-align: newest sample at the right edge
        const step = Math.max(1, Math.floor(data.length / (w * 1.5)));
        for (let i = 0; i < data.length; i += step) {
          const x = ((offset + i) / cap) * w;
          const y = mid - data[i]! * scale;
          if (i === 0) ctx.moveTo(x, y);
          else ctx.lineTo(x, y);
        }
        ctx.stroke();
        ctx.fillStyle = "rgba(139,155,176,0.7)";
        ctx.font = "10px ui-monospace, Menlo, monospace";
        const unit = signal.unit === "uV" ? "µV" : "(arbitrary units)";
        ctx.fillText(`ch${ch}  ±${peak.toFixed(0)} ${unit}`, 6, lane * ch + 12);
      }
    };
    draw();
    return () => cancelAnimationFrame(raf);
  }, [signal]);

  const rec = runtime?.device?.capabilities.find((c) => c.capability === "recording");
  const external = isLiveSource(runtime?.device);
  return (
    <Panel
      title={external ? "Raw signal · live source" : "Recording (synthetic signal)"}
      className="signal-panel"
      right={
        <span className="muted">
          {rec
            ? `${Math.min(Number(rec.params.channel_count), MAX_CHANNELS_SHOWN)} of ${rec.params.channel_count} ch · ${rec.params.sample_rate_hz} Hz · ${WINDOW_S}s window`
            : "no recording capability"}
        </span>
      }
    >
      <canvas ref={canvas} className="signal-canvas" data-testid="signal-canvas" />
      {external ? (
        <p className="muted small">
          Samples as received from the connected stream (first {MAX_CHANNELS_SHOWN} channels, each auto-scaled). What the
          stream is — hardware, playback or simulation — is shown by the data badge.
        </p>
      ) : (
        <p className="muted small">
          Noise + sinusoids from the simulator. Not physiological and not coupled to any intent.
        </p>
      )}
    </Panel>
  );
}

export function TelemetryPanel({
  telemetry,
  runtime,
}: {
  telemetry: { metrics: TelemetryMetric[]; at: number; deviceId: string; sessionId: string } | null;
  runtime: RuntimeSnapshot | null;
}) {
  const current = telemetry && telemetry.sessionId === runtime?.session_id ? telemetry : null;
  const telCap = runtime?.device?.capabilities.find((c) => c.capability === "telemetry");
  return (
    <Panel
      title="Telemetry"
      right={
        <span className="muted">
          {current ? `${current.deviceId} · ${((Date.now() - current.at) / 1000).toFixed(0)}s ago` : "—"}
        </span>
      }
    >
      <div className="telemetry">
        {current ? (
          current.metrics.map((m) => (
            <div key={m.name} className="metric">
              <div className="metric-name">{m.name}</div>
              <div className="metric-value mono">
                {Number.isInteger(m.value) ? m.value : m.value.toFixed(2)}
                <span className="kpi-unit">{m.unit}</span>
              </div>
            </div>
          ))
        ) : (
          <div className="empty">
            {telCap
              ? `Waiting for telemetry from this session (${telCap.params.rate_hz} Hz).`
              : "No telemetry for the current session."}
          </div>
        )}
      </div>
    </Panel>
  );
}
