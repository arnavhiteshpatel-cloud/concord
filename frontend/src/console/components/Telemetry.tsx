import type { RuntimeSnapshot, TelemetryMetric } from "../../sdk";
import { Panel } from "./ui";

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
      title="Device telemetry"
      right={current ? <span className="hint">{((Date.now() - current.at) / 1000).toFixed(0)} s ago</span> : undefined}
    >
      <div className="telemetry">
        {current ? (
          current.metrics.map((m) => (
            <div key={m.name} className="metric">
              <div className="metric-name">{m.name.replace(/_/g, " ")}</div>
              <div className="metric-value num">
                {Number.isInteger(m.value) ? m.value : m.value.toFixed(2)}
                <span className="kpi-unit">{m.unit}</span>
              </div>
            </div>
          ))
        ) : (
          <p className="value-muted">
            {telCap
              ? `Waiting for telemetry from this session (${telCap.params.rate_hz} Hz).`
              : "No telemetry for the current session."}
          </p>
        )}
      </div>
    </Panel>
  );
}
