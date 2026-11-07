// What the running pipeline is doing, as reported by GET /pipeline (polled).

import type { LatencyStats, PipelineStatus } from "../api";
import { Kpi, fmt } from "./ui";

const COUNTER_ORDER = [
  "inputs",
  "input_samples",
  "dropped_inputs",
  "features_out",
  "decoded_out",
  "commands_out",
  "errors",
  "queue_depth",
];
const BAD = new Set(["dropped_inputs", "errors"]);

function Percentiles({ title, s, unit, digits }: { title: string; s: LatencyStats; unit: string; digits: number }) {
  return (
    <tr>
      <td>{title}</td>
      <td className="r mono">{fmt.num(s.p50, digits)}</td>
      <td className="r mono">{fmt.num(s.p95, digits)}</td>
      <td className="r mono">{fmt.num(s.p99, digits)}</td>
      <td className="r mono">{fmt.num(s.max, digits)}</td>
      <td className="r mono">{fmt.num(s.count)}</td>
      <td className="muted">{unit}</td>
    </tr>
  );
}

export function PipelineStatusPanel({ status }: { status: PipelineStatus | null }) {
  if (!status) return <div className="empty">Pipeline status unavailable.</div>;
  if (!status.available)
    return (
      <div className="alert" data-testid="pl-unavailable">
        Pipeline unavailable: {status.unavailable_reason}
      </div>
    );
  const keys = [
    ...COUNTER_ORDER.filter((k) => k in status.counters),
    ...Object.keys(status.counters).filter((k) => !COUNTER_ORDER.includes(k)),
  ];
  const out = status.output;
  return (
    <div data-testid="pipeline-status">
      <div className="pl-head">
        <span className={`chip ${status.running ? "text-ok" : "muted"}`} data-testid="pl-running">
          {status.running ? "running" : "stopped"}
        </span>
        {status.running && (
          <span className="mono small">
            {status.preset} on {status.device_id}
          </span>
        )}
        {status.running && status.warmup_remaining_s > 0 && (
          <span className="chip text-warn" data-testid="pl-warmup">
            warm-up {status.warmup_remaining_s.toFixed(1)} s (estimating thresholds)
          </span>
        )}
      </div>

      {status.running && (
        <table className="table kv">
          <tbody>
            <tr>
              <td>stages</td>
              <td>
                <ol className="stages" data-testid="pl-stages">
                  {status.stages.map((s) => (
                    <li key={s}>{s}</li>
                  ))}
                </ol>
              </td>
            </tr>
            <tr>
              <td>input</td>
              <td className="mono">{status.input_event_type ?? "—"}</td>
            </tr>
            <tr>
              <td>output</td>
              <td className="mono" data-testid="pl-output">
                {out
                  ? `${out.event_type} · ${out.feature} · ${fmt.num(out.bin_ms, out.bin_ms % 1 ? 1 : 0)} ms · ${out.channel_count} ch · ${out.unit}`
                  : "—"}
              </td>
            </tr>
            <tr>
              <td>decoder</td>
              <td data-testid="pl-decoder">
                {status.decoder ? (
                  <>
                    <span className="mono">{status.decoder.model_id}</span> → intent.kinematics [
                    {status.decoder.dims.join(", ")}] (decoded_intent)
                  </>
                ) : (
                  <span className="muted">none (features only)</span>
                )}
                {status.cross_source_override && (
                  <div className="text-warn small">cross-source override active: decoded quality reduced</div>
                )}
              </td>
            </tr>
            <tr>
              <td>router</td>
              <td className="mono">
                {status.router?.enabled
                  ? `ON · ${status.router.x_dim} → vx, ${status.router.y_dim} → vy`
                  : "off (no commands reach apps)"}
              </td>
            </tr>
          </tbody>
        </table>
      )}

      <div className="kpis kpis-small" data-testid="pl-counters" style={{ marginTop: 10 }}>
        {keys.map((k) => {
          const v = status.counters[k] ?? 0;
          return (
            <div key={k} data-counter={k}>
              <Kpi label={k.replace(/_/g, " ")} value={fmt.num(v)} tone={BAD.has(k) && v > 0 ? "warn" : undefined} />
            </div>
          );
        })}
      </div>

      <table className="table" data-testid="pl-latency">
        <thead>
          <tr>
            <th>measured</th>
            <th className="r">p50</th>
            <th className="r">p95</th>
            <th className="r">p99</th>
            <th className="r">max</th>
            <th className="r">n</th>
            <th />
          </tr>
        </thead>
        <tbody>
          <Percentiles title="processing per input" s={status.processing_us} unit="µs" digits={0} />
          <Percentiles title="input event → derived event" s={status.pipeline_latency_ms} unit="ms" digits={2} />
        </tbody>
      </table>

      {status.compatibility_warnings.length > 0 && (
        <ul className="notes text-warn small" data-testid="pl-warnings">
          {status.compatibility_warnings.map((w) => (
            <li key={w}>{w}</li>
          ))}
        </ul>
      )}
      {status.last_error && (
        <div className="alert" data-testid="pl-last-error">
          last error: {status.last_error}
        </div>
      )}
    </div>
  );
}
