// What the running pipeline is doing, as reported by GET /pipeline (polled).

import type { LatencyStats, PipelineStatus } from "../api";
import { sentence } from "../wording";
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
      <td className="r num">{fmt.num(s.p50, digits)}</td>
      <td className="r num">{fmt.num(s.p95, digits)}</td>
      <td className="r num">{fmt.num(s.p99, digits)}</td>
      <td className="r num">{fmt.num(s.max, digits)}</td>
      <td className="r num">{fmt.num(s.count)}</td>
      <td className="hint">{unit}</td>
    </tr>
  );
}

export function PipelineStatusPanel({ status }: { status: PipelineStatus | null }) {
  if (!status) return <p className="value-muted">Pipeline status unavailable.</p>;
  if (!status.available)
    return (
      <p className="error-text" data-testid="pl-unavailable">
        Pipeline unavailable: {status.unavailable_reason}
      </p>
    );
  const keys = [
    ...COUNTER_ORDER.filter((k) => k in status.counters),
    ...Object.keys(status.counters).filter((k) => !COUNTER_ORDER.includes(k)),
  ];
  const out = status.output;
  return (
    <div data-testid="pipeline-status">
      <div className="pl-head">
        <span data-testid="pl-running">{status.running ? "Running" : "Stopped"}</span>
        {status.running && (
          <span className="hint">
            {" "}
            · {status.preset} on {status.device_id}
          </span>
        )}
        {status.running && status.warmup_remaining_s > 0 && (
          <span className="hint" data-testid="pl-warmup">
            {" "}
            · warm-up {status.warmup_remaining_s.toFixed(1)} s (estimating thresholds)
          </span>
        )}
      </div>

      {status.running && (
        <table className="table kv">
          <tbody>
            <tr>
              <td>Stages</td>
              <td>
                <ol className="stages" data-testid="pl-stages">
                  {status.stages.map((s) => (
                    <li key={s}>{s}</li>
                  ))}
                </ol>
              </td>
            </tr>
            <tr>
              <td>Input</td>
              <td>{status.input_event_type ?? "—"}</td>
            </tr>
            <tr>
              <td>Output</td>
              <td data-testid="pl-output">
                {out
                  ? `${out.event_type} · ${out.feature} · ${fmt.num(out.bin_ms, out.bin_ms % 1 ? 1 : 0)} ms · ${out.channel_count} ch · ${out.unit}`
                  : "—"}
              </td>
            </tr>
            <tr>
              <td>Decoder</td>
              <td data-testid="pl-decoder">
                {status.decoder ? (
                  <>
                    <span>{status.decoder.model_id}</span> → intent.kinematics [
                    {status.decoder.dims.join(", ")}] (decoded_intent)
                  </>
                ) : (
                  <span className="hint">none (features only)</span>
                )}
                {status.cross_source_override && (
                  <div className="caution-text">Cross-source override active: decoded quality reduced.</div>
                )}
              </td>
            </tr>
            <tr>
              <td>Command router</td>
              <td>
                {status.router?.enabled
                  ? `On · ${status.router.x_dim} → vx, ${status.router.y_dim} → vy`
                  : "Off (no commands reach apps)"}
              </td>
            </tr>
          </tbody>
        </table>
      )}

      <div className="kpis" data-testid="pl-counters">
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
            <th>Measured</th>
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
        <ul className="warnings caution-text" data-testid="pl-warnings">
          {status.compatibility_warnings.map((w) => (
            <li key={w}>{sentence(w)}</li>
          ))}
        </ul>
      )}
      {status.last_error && (
        <p className="error-text" data-testid="pl-last-error">
          Last error: {status.last_error}
        </p>
      )}
    </div>
  );
}
